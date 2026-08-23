from __future__ import annotations

from typing import Literal

from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.agents.state import AgentState
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import normalize_text

RequestMode = Literal["information", "support_action"]
ResolutionMode = Literal["information_only", "self_serve", "human_required"]


_DIRECT_OPERATION_MARKERS = (
    # Explicit requests for the assistant/staff to inspect or act on a personal record.
    "can you check", "could you check", "please check", "check my", "verify my",
    "look up my", "find my booking", "find my reservation", "track my luggage",
    "trace my luggage", "find my luggage", "locate my luggage", "resend my",
    "send it to me", "send me the", "process my", "process a refund", "refund me",
    "refund my", "can you cancel my", "could you cancel my", "please cancel my",
    "cancel my booking for me", "cancel my reservation for me",
    "can you change my booking", "could you change my booking", "please change my booking",
    "change my booking for me", "change my reservation for me",
    "modify my booking for me", "book it for me", "do it for me", "contact them for me",
    "create a ticket", "open a ticket", "raise a ticket", "escalate this to support",
    "ban kiem tra", "vui long kiem tra", "kiem tra booking cua toi",
    "kiem tra dat cho cua toi", "xac minh cho toi", "tra cuu cho toi",
    "tim hanh ly cua toi", "theo doi hanh ly cua toi", "gui lai cho toi",
    "hoan tien cho toi", "huy booking giup toi", "huy dat phong giup toi",
    "huy dat cho giup toi", "doi booking giup toi", "doi dat cho giup toi",
    "thay doi dat cho giup toi", "lam giup toi", "xu ly giup toi",
    "ban kiem tra giup", "vui long xu ly", "vui long huy", "hay huy",
    "tao ticket", "tao phieu ho tro", "chuyen cho nhan vien",
)


def _looks_like_contact_guidance_question(text: str) -> bool:
    """Return True when the user asks *who/where/how to contact* for a process.

    Asking for a hotline/contact channel is informational guidance, not a request
    for the bot to mutate a booking. This distinction prevents turns such as
    "Nếu tôi hủy thì liên hệ ai?" from auto-creating a ticket.
    """
    normalized = normalize_text(text)
    if not normalized:
        return False

    contact_markers = (
        "lien he ai", "lien he o dau", "lien he dau", "lien he so nao",
        "so dien thoai nao", "hotline nao", "goi ai", "goi so nao",
        "who do i contact", "who should i contact", "who can i contact",
        "where do i contact", "where can i contact", "how do i contact",
        "how can i contact", "which number", "what number", "contact number",
        "contact details", "contact information",
    )
    asks_contact = any(marker in normalized for marker in contact_markers)
    if not asks_contact:
        return False

    return not any(marker in normalized for marker in _DIRECT_OPERATION_MARKERS)


def _looks_like_self_serve_procedure_question(text: str) -> bool:
    """Recognize how-to cancellation/refund/change questions as guidance.

    A user asking how a process works may need instructions, but that is still
    different from asking the assistant to execute the process on their record.
    """
    normalized = normalize_text(text)
    if not normalized:
        return False
    if any(marker in normalized for marker in _DIRECT_OPERATION_MARKERS):
        return False

    markers = (
        "how do i cancel", "how can i cancel", "how to cancel",
        "what should i do to cancel", "steps to cancel",
        "how do i request a refund", "how can i request a refund",
        "how can i get a refund", "how to get a refund", "how to request a refund",
        "what should i do for a refund", "steps to get a refund",
        "how do i change my booking", "how can i change my booking",
        "how to change my booking", "how do i reschedule", "how can i reschedule",
        "lam sao de huy", "cach huy", "muon huy thi lam sao",
        "lam the nao de huy", "thu tuc huy",
        "lam sao de hoan tien", "cach hoan tien", "muon hoan tien thi lam sao",
        "lam the nao de hoan tien", "thu tuc hoan tien",
        "lam sao de doi dat cho", "cach doi dat cho", "thu tuc doi dat cho",
    )
    return any(marker in normalized for marker in markers)


def _asks_explicit_personal_operation(text: str) -> bool:
    """Return True only when the user asks the assistant/staff to act on a case.

    First-person wording ("my booking") and a process verb ("cancel") are not
    sufficient. Questions asking for policy, steps, or contact information stay
    informational/self-service; explicit inspect/mutate/process requests escalate.
    """
    normalized = normalize_text(text)
    if not normalized:
        return False
    if _looks_like_contact_guidance_question(normalized):
        return False
    if _looks_like_self_serve_procedure_question(normalized):
        return False
    return any(marker in normalized for marker in _DIRECT_OPERATION_MARKERS)


def _looks_like_permission_or_policy_question(text: str) -> bool:
    """Recognize permission/eligibility questions without mistaking them for operations.

    Phrases such as "Can I change my booking?" or "tôi có thể đổi đặt chỗ không?"
    normally ask what the policy permits. They should remain informational unless the
    user separately asks the assistant/staff to perform, inspect, verify, or process a
    personal case.
    """
    normalized = normalize_text(text)
    if not normalized:
        return False

    permission_markers = (
        "can i ", "may i ", "am i allowed", "is it possible for me",
        "is it possible to ", "do i need to ", "do i have to ",
        "toi co the ", "minh co the ", "toi co duoc ", "minh co duoc ",
        "co the doi ", "co the thay doi ", "co duoc doi ", "co duoc thay doi ",
    )
    asks_permission = any(marker in f"{normalized} " for marker in permission_markers)
    if not asks_permission:
        return False

    explicit_operation_markers = (
        "can you ", "could you ", "would you ", "please ",
        "help me change", "help me cancel", "help me refund",
        "check my booking", "check my reservation", "check my transaction",
        "verify my ", "process my ", "change it for me", "cancel it for me",
        "ban co the ", "vui long ", "giup toi ", "giup minh ",
        "kiem tra booking", "kiem tra dat cho", "kiem tra giao dich",
        "doi giup toi", "doi giup minh", "huy giup toi", "huy giup minh",
        "hoan tien cho toi", "hoan tien cho minh",
    )
    return not any(marker in normalized for marker in explicit_operation_markers)


def _heuristic_fallback(
    message: str,
    rag_query: str = "",
) -> tuple[RequestMode, ResolutionMode, str, float]:
    """Conservative fallback used when semantic triage is unavailable.

    ``rag_query`` is the language/control node's faithful English rewrite. Using it
    together with the original message keeps deterministic safety rules language-
    independent instead of accidentally favouring Vietnamese/English wording.
    """
    text = normalize_text(f"{message} {rag_query}")

    if _looks_like_contact_guidance_question(text):
        return (
            "information",
            "information_only",
            "User asks for a contact channel/person for a process, not for record mutation.",
            0.97,
        )

    if _looks_like_self_serve_procedure_question(text):
        return (
            "support_action",
            "self_serve",
            "User asks for process instructions that can be answered as self-service guidance.",
            0.93,
        )

    personal_markers = (
        "toi ", "cua toi", "cho toi", "giao dich cua", "booking cua",
        "minh ", "cua minh", "cho minh", "giup minh",
        "my ", "me ", "i was", "i have", "i did",
    )
    transaction_problem_markers = (
        "bi tru tien 2 lan", "bi tru tien hai lan", "charged twice", "double charged",
        "chuyen khoan 2 lan", "chuyen khoan hai lan", "transfer twice", "transferred twice",
        "thanh toan 2 lan", "thanh toan hai lan", "paid twice", "duplicate payment",
        "chuyen khoan nham", "chuyen nham", "wrong transfer", "mistaken transfer",
        "thanh toan nham", "wrong payment",
        "tien da bi tru", "money was charged",
    )
    has_personal = any(marker in f"{text} " for marker in personal_markers)
    has_operational = _asks_explicit_personal_operation(text)
    has_transaction_problem = any(marker in text for marker in transaction_problem_markers)
    permission_or_policy_question = _looks_like_permission_or_policy_question(text)
    if (has_operational and not permission_or_policy_question) or (has_personal and has_transaction_problem):
        return (
            "support_action",
            "human_required",
            "Detected a personal case requiring record access, verification, or an operational action.",
            0.95,
        )

    problem_markers = (
        "bi loi",
        "khong dung duoc",
        "khong su dung duoc",
        "khong thanh toan duoc",
        "loi thanh toan",
        "error",
        "failed",
        "not working",
        "cannot use",
        "can t use",
        "khong nhan duoc",
        "problem",
        "su co",
    )
    guidance_markers = (
        "lam sao",
        "cach xu ly",
        "huong dan",
        "how to",
        "what should i do",
        "help me troubleshoot",
    )
    if any(marker in text for marker in problem_markers):
        return (
            "support_action",
            "self_serve",
            "Detected a troubleshooting/support request that may be solvable with grounded guidance.",
            0.78,
        )

    if any(marker in text for marker in guidance_markers):
        return (
            "support_action",
            "self_serve",
            "Detected a request for procedural guidance.",
            0.65,
        )

    return (
        "information",
        "information_only",
        "Classified the message as an informational request.",
        0.70,
    )


def _strong_fast_path(
    state: AgentState,
) -> tuple[RequestMode, ResolutionMode, str, float] | None:
    """Return a deterministic triage only when the signal is strong.

    Normal travel/catalog questions should not pay for a semantic support classifier.
    Ambiguous personal booking/refund/complaint wording deliberately falls through to
    the LLM so speed never comes at the cost of unsafe escalation decisions.
    """
    message = effective_user_message(state)
    rag_query = state.get("rag_query", "")
    # Evaluate deterministic markers on both the original wording and the canonical
    # English retrieval rewrite. This is essential for zh/ja/ko and any other
    # language whose literal text will not match Vietnamese/English marker lists.
    text = normalize_text(f"{message} {rag_query}")
    if not text:
        return (
            "information",
            "information_only",
            "Empty/neutral RAG turn treated as information.",
            0.90,
        )

    # Contact-channel questions and how-to process questions are explicitly
    # non-operational. Evaluate them before FAQ/personal-case heuristics so a noisy
    # retrieval rewrite cannot turn "who should I contact?" into "cancel my booking".
    if _looks_like_contact_guidance_question(text):
        return (
            "information",
            "information_only",
            "Contact/how-to-reach-support question; no personal-record operation requested.",
            0.99,
        )

    if _looks_like_self_serve_procedure_question(text):
        return (
            "support_action",
            "self_serve",
            "Procedural cancellation/refund/change guidance requested without asking the bot to execute it.",
            0.96,
        )

    # A high-confidence canonical FAQ match is informational by default. This rule
    # is intentionally evaluated before the generic "I lost / my booking" heuristic
    # because many official FAQ questions are written in first person. Keep escalation
    # only for an explicit request to inspect or mutate the user's own case.
    retrieval_mode = str(state.get("retrieval_mode") or "")
    if retrieval_mode.startswith("faq_") and not _asks_explicit_personal_operation(text):
        return (
            "information",
            "information_only",
            "Canonical FAQ match with no explicit personal-record operation requested.",
            0.99,
        )

    fallback = _heuristic_fallback(message, rag_query)
    if fallback[1] == "human_required":
        return fallback

    # A completed personal payment followed by an explicit request to obtain a
    # refund is an operational, case-specific action. This must be language-
    # invariant: e.g. Chinese/Japanese/Korean messages are recognized through the
    # faithful English ``rag_query`` produced by the control node.
    explicit_refund_policy_markers = (
        "refund policy", "cancellation policy", "refund conditions",
        "refund terms", "what is the refund", "what are the refund",
        "chinh sach hoan tien", "dieu kien hoan tien",
    )
    completed_payment_markers = (
        "paid", "payment", "i paid", "i have paid", "i ve paid", "already paid",
        "made a payment", "have made a payment", "payment was made",
        "payment completed", "was charged", "money was charged",
        "toi da thanh toan", "toi thanh toan roi", "da thanh toan",
    )
    refund_action_markers = (
        "get a refund", "want a refund", "request a refund",
        "need a refund", "refund me", "refund my", "refund this",
        "process a refund", "money back", "muon hoan tien",
        "lam sao de hoan tien", "yeu cau hoan tien",
    )
    has_explicit_policy_question = any(
        marker in text for marker in explicit_refund_policy_markers
    )
    if (
        not has_explicit_policy_question
        and any(marker in text for marker in completed_payment_markers)
        and any(marker in text for marker in refund_action_markers)
    ):
        return (
            "support_action",
            "human_required",
            "Detected a completed personal payment followed by a case-specific refund request.",
            0.98,
        )

    # A clear technical/use failure without a personal-record action can be handled
    # as self-service. Do not fast-path vague personal booking/account problems.
    strong_problem_markers = (
        "bi loi", "loi thanh toan", "khong thanh toan duoc",
        "khong dung duoc", "khong su dung duoc",
        "error", "payment failed", "failed payment", "not working",
        "cannot use", "can t use", "voucher failed",
    )
    vague_personal_case_markers = (
        "booking cua toi", "dat phong cua toi", "giao dich cua toi",
        "tai khoan cua toi", "my booking", "my reservation",
        "my transaction", "my account",
    )
    if any(marker in text for marker in strong_problem_markers):
        if not any(marker in text for marker in vague_personal_case_markers):
            return (
                "support_action",
                "self_serve",
                "Strong troubleshooting signal; grounded self-service guidance may resolve it.",
                0.90,
            )

    # Explicit policy/factual wording is safe to classify as information when it
    # does not refer to a personal record. This prevents questions such as
    # "What is the refund policy?" from paying for support triage.
    clear_information_markers = (
        "policy", "policies", "chinh sach", "quy dinh", "dieu khoan",
        "terms", "conditions", "dieu kien", "what is the refund",
        "refund policy", "cancellation policy", "chinh sach hoan tien",
        "chinh sach huy",
    )
    if (
        any(marker in text for marker in clear_information_markers)
        and not any(marker in text for marker in vague_personal_case_markers)
    ):
        return (
            "information",
            "information_only",
            "Explicit policy/factual wording with no personal-record action.",
            0.95,
        )

    # Modal permission/eligibility wording is usually a FAQ/policy question, even
    # when it contains first-person language ("Can I change my booking?"). Keep it
    # informational unless an earlier rule found an actual failure/refund operation.
    if _looks_like_permission_or_policy_question(text):
        return (
            "information",
            "information_only",
            "Permission/eligibility wording indicates a policy question, not a request to mutate a personal record.",
            0.95,
        )

    # These terms are intentionally ambiguous: policy/info and personal operations
    # can share the same word. Keep the semantic LLM judge for them unless a stronger
    # rule above already resolved the case.
    ambiguous_support_markers = (
        "refund", "hoan tien", "cancel", "huy booking", "huy dat phong",
        "change booking", "doi booking", "doi dat phong",
        "complaint", "khieu nai", "lost property", "mat do", "de quen do",
        "booking cua toi", "dat phong cua toi", "my booking", "my reservation",
        "giao dich cua toi", "my transaction", "tai khoan cua toi", "my account",
        "problem with booking", "booking problem", "van de voi booking",
        "help with booking", "giup booking",
    )
    if any(marker in text for marker in ambiguous_support_markers):
        return None

    # Payment/transaction wording is often informational (for example, asking
    # which payment methods are accepted), so do not escalate on the topic alone.
    # However, when payment context is combined with a personal-case/problem
    # signal, let the semantic classifier decide instead of fast-pathing the turn
    # as information. This covers unforeseen wording such as "I accidentally sent
    # the transfer twice, please help" without turning every payment FAQ into a
    # ticket.
    payment_case_context = (
        "chuyen khoan", "thanh toan", "giao dich", "bi tru tien",
        "bank transfer", "payment", "transaction", "charged",
    )
    personal_case_signal = (
        "minh ", "toi ", "cua minh", "cua toi", "my ",
        "giup minh", "giup toi", "help me", "kiem tra", "check",
        "nham", "lo ", "2 lan", "hai lan", "twice", "duplicate",
        "wrong", "mistake", "refund", "hoan tien",
    )
    if (
        any(marker in text for marker in payment_case_context)
        and any(marker in text for marker in personal_case_signal)
    ):
        return None

    # At this point the request has already been routed to RAG and contains no
    # meaningful support/action signal. Treat normal destination/catalog/policy/
    # payment-information questions as information without another LLM call.
    return (
        "information",
        "information_only",
        "No support-action signal detected; normal RAG request treated as information.",
        0.94,
    )


def analyze_support_request(state: AgentState) -> AgentState:
    """Classify information vs self-service vs human-required support.

    Strong, unambiguous cases use deterministic rules. The semantic LLM is reserved
    for genuinely ambiguous support wording.
    """
    message = effective_user_message(state)

    fast = _strong_fast_path(state)
    if fast is not None:
        request_mode, resolution_mode, reason, confidence = fast
        source = "deterministic-fast-path"
    else:
        llm = LLMService()
        source = "llm-ambiguous-case"
        try:
            result = llm.json(
                system_prompt=(
                    "You are a support-triage classifier for a Vinpearl/VinWonders RAG assistant. "
                    "Classify the CURRENT user message semantically; do not trigger on keywords alone. "
                    "Return request_mode and resolution_mode. request_mode=information when the user only "
                    "asks for facts, availability, policy, prices, locations, or general explanations. "
                    "request_mode=support_action when the user reports a problem or asks for help resolving it. "
                    "resolution_mode=information_only for factual questions. resolution_mode=self_serve when "
                    "the user has a problem but grounded instructions from the knowledge base could reasonably "
                    "solve it without accessing or changing a personal record. resolution_mode=human_required "
                    "ONLY when the user asks for or clearly needs case-specific investigation, verification, "
                    "account/transaction/booking access, cancellation/change/refund execution, lost-property "
                    "handling, complaint handling, or another operational action the chatbot cannot perform. "
                    "A phrase like 'help me' by itself is NOT enough for human_required. A known policy or guide "
                    "does not remove the need for human support when the requested action is case-specific. "
                    "Examples: 'What is the refund policy?' => information/information_only. "
                    "'Payment fails, how do I fix it?' => support_action/self_serve. "
                    "'I was charged twice; check my transaction' => support_action/human_required. "
                    "'My booking was not confirmed; please check it' => support_action/human_required. "
                    "Use conversation history only to resolve references, never to inherit an old support mode. "
                    "Return valid JSON only with request_mode, resolution_mode, reason, confidence."
                ),
                user_prompt=f"""
Current message:
{message}

Standalone retrieval query:
{state.get('rag_query', '')}

Detected destination(s):
{', '.join(state.get('detected_destination_names', [])) or 'none'}

Detected intent(s):
{', '.join(state.get('detected_intents', [])) or state.get('detected_intent') or 'none'}

Return exactly:
{{
  "request_mode": "information|support_action",
  "resolution_mode": "information_only|self_serve|human_required",
  "reason": "brief semantic reason",
  "confidence": 0.0
}}
""",
            )

            request_mode = str(result.get("request_mode") or "").strip()
            resolution_mode = str(result.get("resolution_mode") or "").strip()
            reason = str(result.get("reason") or "").strip()
            try:
                confidence = float(result.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0

            if request_mode not in {"information", "support_action"}:
                raise ValueError(f"invalid request_mode={request_mode!r}")
            if resolution_mode not in {"information_only", "self_serve", "human_required"}:
                raise ValueError(f"invalid resolution_mode={resolution_mode!r}")

            if request_mode == "information":
                resolution_mode = "information_only"
            elif resolution_mode == "information_only":
                resolution_mode = "self_serve"

            fallback_request, fallback_resolution, fallback_reason, fallback_confidence = _heuristic_fallback(message, state.get("rag_query", ""))
            if fallback_resolution == "human_required" and resolution_mode != "human_required":
                request_mode = fallback_request
                resolution_mode = fallback_resolution
                reason = f"{reason} Safety override: {fallback_reason}".strip()
                confidence = max(confidence, fallback_confidence)

            confidence = max(0.0, min(1.0, confidence))
            if not reason:
                reason = "Semantic support triage completed."

        except Exception as exc:
            request_mode, resolution_mode, reason, confidence = _heuristic_fallback(message, state.get("rag_query", ""))
            reason = f"{reason} Classifier fallback reason: {exc}"
            source = "heuristic-fallback-after-llm-error"

    print("\n===== SUPPORT TRIAGE =====")
    print(f"Question: {message}")
    print(f"Decision source: {source}")
    print(f"Request mode: {request_mode}")
    print(f"Resolution mode: {resolution_mode}")
    print(f"Confidence: {confidence:.2f}")
    print(f"Reason: {reason}")
    print("==========================\n")

    return {
        "request_mode": request_mode,
        "resolution_mode": resolution_mode,
        "support_triage_reason": reason,
        "support_triage_confidence": confidence,
    }
