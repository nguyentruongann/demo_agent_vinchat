from __future__ import annotations

from src.backend.agents.state import AgentState
from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.services.llm import LLMService


def _get_language(state: AgentState) -> str:
    language = state.get("original_language", "en")
    if not isinstance(language, str) or not language.strip():
        return "en"
    return language.strip()


def _language_group(language: str) -> str | None:
    code = language.lower().replace("_", "-")
    for prefix in ("vi", "en", "ko", "ja", "zh"):
        if code == prefix or code.startswith(prefix + "-"):
            return prefix
    return None


def _llm_fallback(state: AgentState, instruction: str, details: str = "") -> str:
    """Preserve arbitrary-language support without slowing the common 5 languages."""
    language = _get_language(state)
    return LLMService().text(
        system_prompt=(
            "Reply only in the explicitly detected language. Keep the response brief. "
            + instruction
        ),
        user_prompt=f"Detected language: {language}\nCurrent message: {effective_user_message(state)}\n{details}",
    )


def greeting_response(state: AgentState) -> AgentState:
    language = _get_language(state)
    group = _language_group(language)
    templates = {
        "vi": "Xin chào! Mình có thể hỗ trợ bạn về điểm đến, khách sạn, vui chơi, ưu đãi, chính sách, golf, sự kiện và hướng dẫn thanh toán của Vinpearl/VinWonders.",
        "en": "Hello! I can help with Vinpearl/VinWonders destinations, hotels, attractions, promotions, policies, golf, events, and payment guidance.",
        "ko": "안녕하세요! Vinpearl/VinWonders의 여행지, 호텔, 즐길 거리, 프로모션, 정책, 골프, 이벤트 및 결제 안내를 도와드릴 수 있습니다.",
        "ja": "こんにちは！Vinpearl/VinWondersの旅行先、ホテル、アクティビティ、プロモーション、ポリシー、ゴルフ、イベント、決済案内についてお手伝いできます。",
        "zh": "您好！我可以为您提供 Vinpearl/VinWonders 的目的地、酒店、娱乐项目、优惠、政策、高尔夫、活动及付款指引。",
    }
    answer = templates.get(group)
    if answer is None:
        answer = _llm_fallback(
            state,
            "Greet the user as a friendly Vinpearl/VinWonders travel assistant and briefly state what you can help with.",
        )
    return {"answer": answer}


def out_of_scope_response(state: AgentState) -> AgentState:
    language = _get_language(state)
    group = _language_group(language)
    templates = {
        "vi": "Mình chỉ có thể hỗ trợ các nội dung liên quan đến Vinpearl/VinWonders và hướng dẫn thanh toán. Bạn có thể hỏi mình về điểm đến, khách sạn, vui chơi, ưu đãi hoặc chính sách nhé.",
        "en": "I can only assist with Vinpearl/VinWonders travel services and payment guidance. You can ask me about destinations, hotels, attractions, promotions, or policies.",
        "ko": "저는 Vinpearl/VinWonders 여행 서비스와 결제 안내 관련 내용만 도와드릴 수 있습니다. 여행지, 호텔, 즐길 거리, 프로모션 또는 정책에 대해 질문해 주세요.",
        "ja": "Vinpearl/VinWondersの旅行サービスと決済案内に関する内容のみサポートできます。旅行先、ホテル、アクティビティ、プロモーション、ポリシーについてご質問ください。",
        "zh": "我只能协助 Vinpearl/VinWonders 旅游服务及付款指引相关内容。您可以询问目的地、酒店、娱乐项目、优惠或政策。",
    }
    answer = templates.get(group)
    if answer is None:
        answer = _llm_fallback(
            state,
            "Politely refuse the out-of-scope request. Do not answer it. Explain that you only support Vinpearl/VinWonders travel services and payment guidance.",
        )
    return {"answer": answer}


def sensitive_content_response(state: AgentState) -> AgentState:
    """Refuse semantically sensitive/harmful requests without answering them."""
    language = _get_language(state)
    group = _language_group(language)
    templates = {
        "vi": (
            "Mình không thể hỗ trợ yêu cầu này vì nội dung thuộc nhóm nhạy cảm hoặc có thể gây hại. "
            "Mình vẫn có thể hỗ trợ các nội dung an toàn liên quan đến Vinpearl/VinWonders như điểm đến, "
            "khách sạn, vui chơi, chính sách, ưu đãi hoặc liên hệ hỗ trợ."
        ),
        "en": (
            "I can't help with this request because it involves sensitive or potentially harmful content. "
            "I can still help with safe Vinpearl/VinWonders topics such as destinations, hotels, attractions, "
            "policies, promotions, or support guidance."
        ),
        "ko": (
            "이 요청은 민감하거나 잠재적으로 유해한 내용이 포함되어 있어 도와드릴 수 없습니다. "
            "대신 Vinpearl/VinWonders의 여행지, 호텔, 즐길 거리, 정책, 프로모션 또는 안전한 지원 안내를 도와드릴 수 있습니다."
        ),
        "ja": (
            "このリクエストはセンシティブまたは有害となる可能性のある内容を含むため、お手伝いできません。"
            "Vinpearl/VinWondersの旅行先、ホテル、アクティビティ、ポリシー、プロモーション、安全なサポート案内についてはお手伝いできます。"
        ),
        "zh": (
            "由于该请求涉及敏感或可能造成伤害的内容，我无法提供帮助。"
            "我仍可以协助处理 Vinpearl/VinWonders 的安全相关咨询，例如目的地、酒店、娱乐项目、政策、优惠或客服指引。"
        ),
    }
    answer = templates.get(group)
    if answer is None:
        answer = _llm_fallback(
            state,
            "Politely refuse the request because it was classified as sensitive or potentially harmful. "
            "Do not answer, summarize, translate, transform, or provide instructions for the sensitive content. "
            "Offer only safe Vinpearl/VinWonders travel/service assistance.",
            f"Internal safety category: {state.get('safety_category', 'other_sensitive')}",
        )
    return {"answer": answer, "ticket_id": None}


def conversation_context_response(state: AgentState) -> AgentState:
    language = _get_language(state)
    group = _language_group(language)
    recent = state.get("recent_destinations", []) or []

    if not recent:
        templates = {
            "vi": "Mình chưa xác định được địa điểm bạn đang nhắc tới từ lịch sử cuộc trò chuyện hiện tại.",
            "en": "I can't determine the destination you're referring to from the current conversation history.",
            "ko": "현재 대화 기록만으로는 말씀하신 목적지를 확인할 수 없습니다.",
            "ja": "現在の会話履歴だけでは、参照している目的地を特定できません。",
            "zh": "根据当前对话记录，我还无法确定您所指的目的地。",
        }
        answer = templates.get(group)
        if answer is None:
            answer = _llm_fallback(
                state,
                "The user asks which destination a conversational reference means, but structured memory has no destination. Say that it cannot be determined from current conversation memory. Do not use outside knowledge.",
            )
        return {"answer": answer}

    active = recent[0]
    destination_name = str(active.get("name") or active.get("id") or "").strip()
    templates = {
        "vi": f"Ở đây bạn đang nhắc tới **{destination_name}**.",
        "en": f"Here, you're referring to **{destination_name}**.",
        "ko": f"여기서 말씀하신 곳은 **{destination_name}**입니다.",
        "ja": f"ここで指している場所は **{destination_name}** です。",
        "zh": f"这里您指的是 **{destination_name}**。",
    }
    answer = templates.get(group)
    if answer is None:
        answer = _llm_fallback(
            state,
            "Use ONLY the supplied structured conversation-memory destination to clarify what 'here/there/that place' refers to. Add no external facts.",
            f"Structured destination: {destination_name}",
        )
    return {"answer": answer}


def no_data_response(state: AgentState) -> AgentState:
    language = _get_language(state)
    group = _language_group(language)
    destinations = state.get("detected_destination_names", []) or []
    if not destinations:
        destinations = [
            item.get("name")
            for item in state.get("recent_destinations", [])
            if item.get("name")
        ]
    destination_text = ", ".join(str(x) for x in destinations if x)

    if destination_text:
        templates = {
            "vi": f"Hiện cơ sở dữ liệu Vinpearl/VinWonders chưa có đủ thông tin để xác nhận nội dung này cho **{destination_text}**.",
            "en": f"The current Vinpearl/VinWonders knowledge base does not contain enough information to confirm this for **{destination_text}**.",
            "ko": f"현재 Vinpearl/VinWonders 지식 베이스에는 **{destination_text}**에 대해 이 내용을 확인할 충분한 정보가 없습니다.",
            "ja": f"現在のVinpearl/VinWondersナレッジベースには、**{destination_text}**についてこの内容を確認するための十分な情報がありません。",
            "zh": f"当前 Vinpearl/VinWonders 知识库没有足够信息来确认 **{destination_text}** 的这一内容。",
        }
    else:
        templates = {
            "vi": "Hiện cơ sở dữ liệu Vinpearl/VinWonders chưa có đủ thông tin để xác nhận nội dung này.",
            "en": "The current Vinpearl/VinWonders knowledge base does not contain enough information to confirm this.",
            "ko": "현재 Vinpearl/VinWonders 지식 베이스에는 이 내용을 확인할 충분한 정보가 없습니다.",
            "ja": "現在のVinpearl/VinWondersナレッジベースには、この内容を確認するための十分な情報がありません。",
            "zh": "当前 Vinpearl/VinWonders 知识库没有足够信息来确认这一内容。",
        }

    answer = templates.get(group)
    if answer is None:
        answer = _llm_fallback(
            state,
            "State ONLY that the current Vinpearl/VinWonders knowledge base lacks enough evidence to confirm the request. Do not claim real-world non-existence and do not create a ticket.",
            f"Resolved destinations: {destination_text or '(none)'}",
        )
    return {"answer": answer, "ticket_id": None}
