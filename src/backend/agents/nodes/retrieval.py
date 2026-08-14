from src.backend.agents.state import AgentState
from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.config import get_settings
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import normalize_text
from src.backend.services.rag import get_rag_service


CATALOG_INTENTS = {
    "hotel", "service", "dining", "promotion", "attraction", "event", "golf", "mice"
}


def retrieve_context(state: AgentState) -> AgentState:
    rag = get_rag_service()
    documents, diagnostics = rag.hybrid_search(
        query=state["rag_query"],
        user_message=effective_user_message(state),
    )
    return {
        "retrieved_documents": documents,
        "context": rag.build_context(documents),
        "retrieval_mode": diagnostics.get("mode"),
        "detected_destination": diagnostics.get("destination_id"),
        "detected_destination_name": diagnostics.get("destination_name"),
        "detected_destinations": diagnostics.get("destinations", []),
        "detected_destination_ids": diagnostics.get("destination_ids", []),
        "detected_destination_names": diagnostics.get("destination_names", []),
        "detected_intent": diagnostics.get("intent"),
        "detected_intents": diagnostics.get("intents", []),
        "intent_results": diagnostics.get("intent_results", {}),
        "keyword_candidate_count": int(diagnostics.get("keyword_candidate_count") or 0),
        "missing_destination_ids": diagnostics.get("missing_destination_ids", []),
    }


def _is_catalog_existence_question(message: str) -> bool:
    normalized = normalize_text(message)
    if not normalized:
        return False

    english_markers = (
        "is there ", "are there ", "do you have ", "does it have ",
        "does this place have ", "any golf",
    )
    if any(marker in f"{normalized} " for marker in english_markers):
        return True

    if "co " in f"{normalized} " and any(
        marker in f" {normalized} "
        for marker in (" khong ", " ko ", " k ", " hong ", " khong vay ")
    ):
        return True

    return False


def _is_catalog_query(state: AgentState) -> bool:
    intents = set(state.get("detected_intents", []) or [])
    if not intents and state.get("detected_intent"):
        intents.add(str(state.get("detected_intent")))
    return bool(intents) and intents.issubset(CATALOG_INTENTS)


def _insufficiency_action(state: AgentState) -> str:
    """Choose what to do when RAG cannot safely resolve the current request.

    Ticket creation is based on the semantic support mode, not a fixed keyword
    list or topic name. Informational discovery questions get a safe no-data
    answer. A user who is actively troubleshooting gets a ticket only when RAG
    cannot provide grounded self-service guidance.
    """
    request_mode = state.get("request_mode", "information")
    resolution_mode = state.get("resolution_mode", "information_only")

    if resolution_mode == "human_required":
        return "ticket"
    if request_mode == "support_action":
        return "ticket"

    # Informational/catalog questions should never create a ticket merely because
    # the knowledge base does not contain the requested category.
    return "no_data"


def _insufficient(state: AgentState, reason: str, best_score: float) -> AgentState:
    return {
        "enough_information": False,
        "assessment_reason": reason,
        "best_relevance_score": best_score,
        "insufficiency_action": _insufficiency_action(state),
    }


def assess_information(state: AgentState) -> AgentState:
    documents = state.get("retrieved_documents", [])
    settings = get_settings()
    intent_results = state.get("intent_results", {}) or {}
    detected_intents = state.get("detected_intents", []) or []

    # Native partial-answer behavior for multi-intent informational turns. One
    # missing catalog branch must not erase the evidence from other branches. For
    # active support/troubleshooting, however, a missing requested branch means the
    # chatbot may not have enough guidance to resolve the user's problem safely.
    if len(detected_intents) > 1 and intent_results:
        found = [name for name, result in intent_results.items() if result.get("status") == "found"]
        missing = [name for name, result in intent_results.items() if result.get("status") == "not_found"]
        if found:
            scores = [float(item.get("score", 0.0) or 0.0) for item in documents]
            best_score = max(scores, default=0.0)
            request_mode = state.get("request_mode", "information")
            resolution_mode = state.get("resolution_mode", "information_only")

            if request_mode == "information" or not missing:
                reason = (
                    f"Partial multi-intent retrieval: evidence found for {', '.join(found)}"
                    + (f"; no grounded KB evidence for {', '.join(missing)}." if missing else ".")
                )
                print("\n===== RAG ASSESSMENT =====")
                print(f"Question: {effective_user_message(state)}")
                print(f"Detected intents: {detected_intents}")
                print(f"Intent results: {intent_results}")
                print(f"Request mode: {request_mode}; resolution mode: {resolution_mode}")
                print("Enough: True (partial informational answer allowed)")
                print(f"Reason: {reason}")
                print("==========================\n")
                return {
                    "enough_information": True,
                    "assessment_reason": reason,
                    "best_relevance_score": best_score,
                    "insufficiency_action": "no_data",
                }

            return _insufficient(
                state,
                (
                    f"Support request has evidence for {', '.join(found)} but lacks grounded "
                    f"guidance for {', '.join(missing)}."
                ),
                best_score,
            )

    if not documents:
        return _insufficient(
            state,
            "No matching documents were retrieved for the requested destination(s)/intent(s).",
            0.0,
        )

    scores = [float(item.get("score", 0.0) or 0.0) for item in documents]
    best_score = max(scores, default=0.0)

    if best_score < settings.min_relevance_score:
        return _insufficient(
            state,
            (
                f"Best relevance score {best_score:.4f} is below the configured "
                f"minimum {settings.min_relevance_score:.4f}."
            ),
            best_score,
        )

    context = state.get("context", "").strip()
    if not context:
        return _insufficient(
            state,
            "Retrieved documents exist but the assembled context is empty.",
            best_score,
        )

    missing = state.get("missing_destination_ids", [])
    detected_ids = state.get("detected_destination_ids", [])
    if len(detected_ids) > 1 and missing:
        return _insufficient(
            state,
            (
                "Comparison requested across multiple destinations but the knowledge base "
                f"has no matching retrieval candidates for: {', '.join(missing)}."
            ),
            best_score,
        )

    # Clear-pass fast path: for a normal informational request, destination-aware
    # keyword+embedding retrieval has already enforced the destination constraint
    # and intent branch. If every requested branch is found, the context is non-empty,
    # and relevance already passed the configured threshold, another LLM sufficiency
    # judge adds latency but little safety value. Ambiguous semantic-fallback queries
    # and self-service support still keep the LLM judge.
    retrieval_mode = str(state.get("retrieval_mode") or "")
    statuses = [str(result.get("status") or "") for result in intent_results.values()]
    all_requested_branches_found = bool(statuses) and all(status == "found" for status in statuses)
    is_destination_scoped = bool(detected_ids) and retrieval_mode.startswith("keyword")
    is_information = state.get("request_mode", "information") == "information"

    if (
        is_information
        and is_destination_scoped
        and all_requested_branches_found
        and not missing
    ):
        reason = (
            "Deterministic clear-pass: destination-scoped retrieval found every requested "
            "branch with non-empty context above the configured relevance threshold."
        )
        print("\n===== RAG ASSESSMENT =====")
        print(f"Question: {effective_user_message(state)}")
        print(f"Retrieval mode: {retrieval_mode}")
        print(f"Detected intents: {detected_intents or [state.get('detected_intent')]}")
        print(f"Intent results: {intent_results}")
        print(f"Best score: {best_score:.4f}")
        print("Enough: True (deterministic clear-pass)")
        print(f"Reason: {reason}")
        print("==========================\n")
        return {
            "enough_information": True,
            "assessment_reason": reason,
            "best_relevance_score": best_score,
            "insufficiency_action": "no_data",
        }

    llm = LLMService()
    result = llm.json(
        system_prompt=(
            "You are an evidence sufficiency judge for a Vinpearl/VinWonders RAG assistant. "
            "Decide only whether the supplied retrieved context contains enough information "
            "to give a useful, grounded answer to the user's current question. Do not use "
            "outside knowledge. Mark enough=true when the context directly contains the requested "
            "facts or enough information for a useful partial answer. Do not mark false merely "
            "because every possible detail is absent. Mark enough=false only when key facts are "
            "genuinely missing or contradictory. Do not decide ticket escalation here; support triage is "
            "provided separately. Return valid JSON only with keys enough and reason."
        ),
        user_prompt=f"""
Question:
{effective_user_message(state)}

Standalone retrieval query:
{state.get("rag_query", "")}

Detected destinations:
{', '.join(state.get("detected_destination_names", [])) or 'none'}

Detected intents:
{', '.join(detected_intents) or state.get('detected_intent') or 'none'}

Support request mode:
{state.get('request_mode', 'information')}

Support resolution mode:
{state.get('resolution_mode', 'information_only')}

Intent retrieval status:
{intent_results}

Retrieval mode:
{state.get("retrieval_mode", "unknown")}

Best retrieval score:
{best_score:.4f}

Retrieved context:
{context}

Return exactly:
{{"enough": true, "reason": "brief evidence-based reason"}}
""",
    )

    enough = bool(result.get("enough", False))
    reason = str(result.get("reason") or "LLM judge returned no reason.").strip()
    action = "no_data" if enough else _insufficiency_action(state)

    print("\n===== RAG ASSESSMENT =====")
    print(f"Question: {effective_user_message(state)}")
    print(f"RAG query: {state.get('rag_query', '')}")
    print(f"Retrieval mode: {state.get('retrieval_mode', 'unknown')}")
    print(f"Detected intents: {detected_intents or [state.get('detected_intent')]}")
    print(f"Intent results: {intent_results}")
    print(f"Best score: {best_score:.4f}")
    print(f"Enough: {enough}")
    print(f"Reason: {reason}")
    if not enough:
        print(f"Insufficiency action: {action}")
    print("==========================\n")

    return {
        "enough_information": enough,
        "assessment_reason": reason,
        "best_relevance_score": best_score,
        "insufficiency_action": action,
    }
