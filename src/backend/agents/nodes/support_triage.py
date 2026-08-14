from __future__ import annotations

from typing import Literal

from src.backend.agents.state import AgentState
from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import normalize_text


RequestMode = Literal["information", "support_action"]
ResolutionMode = Literal["information_only", "self_serve", "human_required"]


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

    personal_markers = (
        "toi ", "cua toi", "cho toi", "giao dich cua", "booking cua",
        "my ", "me ", "i was", "i have", "i did",
    )
    operational_markers = (
        "kiem tra giao dich", "check my transaction", "kiem tra booking", "check my booking",
        "hoan tien cho toi", "refund my", "huy booking", "cancel my booking",
        "doi booking", "change my booking", "xac minh", "verify my",
        "toi de quen do", "i lost", "khong nhan duoc xac nhan", "did not receive confirmation",
    )
    transaction_problem_markers = (
        "bi tru tien 2 lan", "bi tru tien hai lan", "charged twice", "double charged",
        "tien da bi tru", "money was charged",
    )
    has_personal = any(marker in f"{text} " for marker in personal_markers)
    has_operational = any(marker in text for marker in operational_markers)
    has_transaction_problem = any(marker in text for marker in transaction_problem_markers)
    if has_operational or (has_personal and has_transaction_problem):
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
