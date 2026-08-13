from uuid import UUID

from src.backend.agents.state import AgentState
from src.backend.services.db import open_session
from src.backend.services.llm import LLMService
from src.backend.services.ticket import TicketService
from src.data_postgre.db.app import AppUser


def _language_group(language: str) -> str | None:
    code = str(language or "en").lower().replace("_", "-")
    for prefix in ("vi", "en", "ko", "ja", "zh"):
        if code == prefix or code.startswith(prefix + "-"):
            return prefix
    return None


def _missing_contact_answer(language: str) -> str | None:
    group = _language_group(language)
    messages = {
        "vi": (
            "Yêu cầu này cần chuyển cho nhân viên hỗ trợ. Để tạo ticket, hệ thống cần "
            "họ tên và ít nhất một thông tin liên hệ (email hoặc số điện thoại). "
            "Bạn vui lòng đăng nhập/đăng ký tài khoản hoặc gửi yêu cầu tại trang Hỗ trợ."
        ),
        "en": (
            "This request needs human support. To create a ticket, the system requires "
            "your name and at least one contact method (email or phone number). "
            "Please sign in/register or submit the request through the Support page."
        ),
        "ko": (
            "이 요청은 상담원 지원이 필요합니다. 티켓을 생성하려면 이름과 최소 한 가지 "
            "연락처(이메일 또는 전화번호)가 필요합니다. 로그인/회원가입 후 다시 요청하거나 "
            "지원 페이지에서 문의해 주세요."
        ),
        "ja": (
            "このリクエストにはスタッフの対応が必要です。チケット作成には、お名前と少なくとも1つの "
            "連絡先（メールまたは電話番号）が必要です。ログイン／登録するか、サポートページからお問い合わせください。"
        ),
        "zh": (
            "此请求需要人工客服协助。创建工单需要您的姓名以及至少一种联系方式（邮箱或电话号码）。"
            "请先登录/注册，或通过“支持”页面提交请求。"
        ),
    }
    return messages.get(group)


def _ticket_template(language: str, ticket_id: str, human_required: bool) -> str | None:
    group = _language_group(language)
    if group is None:
        return None
    if human_required:
        messages = {
            "vi": f"Yêu cầu này cần nhân viên hỗ trợ kiểm tra hoặc xử lý theo trường hợp cụ thể. Mình đã tạo ticket **{ticket_id}** cho bạn.",
            "en": f"This request requires case-specific review or action by human support. I created ticket **{ticket_id}** for you.",
            "ko": f"이 요청은 상담원의 개별 확인 또는 처리가 필요합니다. 지원 티켓 **{ticket_id}**를 생성했습니다.",
            "ja": f"このリクエストにはスタッフによる個別確認または対応が必要です。サポートチケット **{ticket_id}** を作成しました。",
            "zh": f"此请求需要人工客服进行个案核查或处理。我已为您创建工单 **{ticket_id}**。",
        }
    else:
        messages = {
            "vi": f"Cơ sở dữ liệu hiện chưa có đủ hướng dẫn đáng tin cậy để xử lý sự cố này. Mình đã tạo ticket **{ticket_id}** để nhân viên hỗ trợ tiếp nhận.",
            "en": f"The current knowledge base does not contain enough reliable guidance to resolve this issue. I created ticket **{ticket_id}** for human follow-up.",
            "ko": f"현재 지식 베이스만으로는 이 문제를 해결할 충분히 신뢰할 수 있는 안내가 없습니다. 상담원 후속 지원을 위해 티켓 **{ticket_id}**를 생성했습니다.",
            "ja": f"現在のナレッジベースには、この問題を解決するための十分に信頼できる案内がありません。スタッフ対応用にチケット **{ticket_id}** を作成しました。",
            "zh": f"当前知识库没有足够可靠的指引来解决此问题。我已创建工单 **{ticket_id}**，由人工客服继续处理。",
        }
    return messages[group]


def create_ticket(state: AgentState) -> AgentState:
    assessment_reason = state.get(
        "assessment_reason",
        "The request could not be safely resolved by the grounded knowledge base.",
    )
    resolution_mode = state.get("resolution_mode", "information_only")
    support_reason = state.get("support_triage_reason", "")

    if resolution_mode == "human_required":
        ticket_reason = support_reason or (
            "The user requested case-specific verification or an operational action that requires human support."
        )
    else:
        ticket_reason = assessment_reason

    contact_user = None
    raw_user_id = state.get("user_id")
    if raw_user_id:
        try:
            with open_session() as db:
                contact_user = db.get(AppUser, UUID(str(raw_user_id)))
                if contact_user:
                    db.expunge(contact_user)
        except (ValueError, TypeError):
            contact_user = None

    has_contact = bool(
        contact_user
        and (contact_user.display_name or "").strip()
        and ((contact_user.email or "").strip() or (contact_user.phone or "").strip())
    )
    language = str(state.get("original_language") or "und")
    if not has_contact:
        answer = _missing_contact_answer(language)
        if answer is None:
            answer = LLMService().text(
                system_prompt=(
                    "Reply only in the target language from the current user turn. Explain briefly that "
                    "this request needs human support, but a ticket cannot be created until the system "
                    "has the user's name and at least one contact method (email or phone). Ask the user "
                    "to sign in/register or use the Support page. Do not add any other facts."
                ),
                user_prompt=(
                    f"TARGET_LANGUAGE: {state.get('original_language_name') or language} ({language})\n"
                    f"CURRENT_MESSAGE: {state.get('user_message', '')}"
                ),
            )
        return {"ticket_id": None, "answer": answer}

    ticket_id = TicketService().create(
        message=state["user_message"],
        language=state.get("original_language", "unknown"),
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
        reason=ticket_reason,
        conversation_turns=state.get("conversation_turns", []),
    )

    answer = _ticket_template(
        language=language,
        ticket_id=ticket_id,
        human_required=resolution_mode == "human_required",
    )
    if answer is not None:
        return {"ticket_id": ticket_id, "answer": answer}

    # Preserve arbitrary-language behavior for languages outside the primary five.
    llm = LLMService()
    if resolution_mode == "human_required":
        system_prompt = (
            "Reply in the user's current original language. Explain that this request requires "
            "case-specific verification or an operational action by human support, so a support "
            "ticket has been created. Include the ticket ID exactly as provided. Do not promise "
            "a response time and do not claim that you inspected private records."
        )
    else:
        system_prompt = (
            "Reply in the user's current original language. Explain that the grounded knowledge "
            "base does not contain enough reliable guidance to resolve the reported support issue, "
            "so a support ticket has been created. Include the ticket ID exactly as provided. "
            "Do not promise a response time or expose internal retrieval details."
        )

    answer = llm.text(
        system_prompt=system_prompt,
        user_prompt=f"Original language: {language}\nTicket ID: {ticket_id}",
    )
    return {"ticket_id": ticket_id, "answer": answer}
