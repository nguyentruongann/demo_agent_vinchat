from src.backend.agents.state import AgentState
from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.config import get_settings
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import normalize_text
from src.backend.services.rag import get_rag_service


CATALOG_INTENTS = {
    "hotel", "service", "dining", "promotion", "attraction", "event", "golf", "mice"
}


def _select_memory_turns(state: AgentState, limit: int = 6) -> list[dict]:
    """Select prior factual turns chosen by the semantic context resolver.

    The resolver sees the current request plus closed refs for recent turns and
    decides whether the current factual request genuinely depends on prior context.
    This avoids topic-specific recap keywords and scales to unseen follow-up forms.
    We still re-run retrieval for the selected turns instead of trusting old
    assistant prose as evidence.
    """
    selected_refs = [
        str(value or "").strip()
        for value in (state.get("selected_memory_turn_refs") or [])
        if str(value or "").strip()
    ]
    if not selected_refs:
        return []

    selected_set = set(selected_refs[: max(1, limit)])
    turns = [
        turn
        for turn in (state.get("conversation_turns") or [])
        if str(turn.get("memory_ref") or "") in selected_set
        and str(turn.get("route") or "") == "rag"
        and str(turn.get("rag_query") or "").strip()
    ]
    # Preserve conversational order, not resolver output order.
    return turns[-max(1, limit):]


def _dedupe_documents(documents: list[dict]) -> list[dict]:
    output: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in documents:
        metadata = item.get("metadata", {}) or {}
        key = (
            str(metadata.get("entity_type") or ""),
            str(
                item.get("id")
                or metadata.get("entity_id")
                or metadata.get("entity_name")
                or item.get("text", "")[:160]
            ),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _merge_intent_results(base: dict, extra: dict) -> dict:
    merged = {key: dict(value) for key, value in (base or {}).items()}
    for intent, result in (extra or {}).items():
        result = dict(result or {})
        if intent not in merged:
            merged[intent] = result
            continue
        current = merged[intent]
        if result.get("status") == "found":
            current["status"] = "found"
        current["document_count"] = int(current.get("document_count") or 0) + int(
            result.get("document_count") or 0
        )
        current["candidate_count"] = int(current.get("candidate_count") or 0) + int(
            result.get("candidate_count") or 0
        )
        current["best_score"] = max(
            float(current.get("best_score") or 0.0),
            float(result.get("best_score") or 0.0),
        )
        if result.get("faq_match"):
            current["faq_match"] = True
            current["matched_question"] = result.get("matched_question")
        merged[intent] = current
    return merged


def retrieve_context(state: AgentState) -> AgentState:
    rag = get_rag_service()
    documents, diagnostics = rag.hybrid_search(
        query=state["rag_query"],
        user_message=effective_user_message(state),
        resolved_destinations=state.get("resolved_destinations"),
    )

    memory_turns = _select_memory_turns(state)
    memory_documents: list[dict] = []
    memory_queries: list[str] = []
    merged_intent_results = dict(diagnostics.get("intent_results", {}) or {})
    merged_intents = list(diagnostics.get("intents", []) or [])

    for turn in memory_turns:
        previous_query = str(turn.get("rag_query") or "").strip()
        previous_message = str(turn.get("user_message") or "").strip()
        if not previous_query:
            continue
        memory_queries.append(previous_query)
        previous_docs, previous_diag = rag.hybrid_search(
            query=previous_query,
            user_message=previous_message,
            top_k=min(3, max(1, get_settings().top_k)),
            resolved_destinations=turn.get("resolved_destinations") or None,
        )
        for item in previous_docs:
            copied = dict(item)
            copied["memory_retrieved"] = True
            memory_documents.append(copied)
        merged_intent_results = _merge_intent_results(
            merged_intent_results,
            previous_diag.get("intent_results", {}),
        )
        for intent in previous_diag.get("intents", []) or []:
            if intent and intent not in merged_intents:
                merged_intents.append(intent)

    if memory_documents:
        # For recap/synthesis, previously grounded branches are the most useful
        # evidence. Put them before the broad current retrieval so the context
        # character budget cannot hide a short authoritative FAQ behind a long
        # regulations document.
        documents = _dedupe_documents(memory_documents + documents)
        retrieval_mode = f"memory_augmented:{diagnostics.get('mode') or 'unknown'}"
        print(
            "[MEMORY RETRIEVAL] "
            f"selected_turns={len(memory_turns)} queries={len(memory_queries)} "
            f"memory_docs={len(memory_documents)} merged_docs={len(documents)}"
        )
    else:
        retrieval_mode = diagnostics.get("mode")

    primary_intent = merged_intents[0] if merged_intents else diagnostics.get("intent")

    return {
        "retrieved_documents": documents,
        "context": rag.build_context(documents),
        "retrieval_mode": retrieval_mode,
        "detected_destination": diagnostics.get("destination_id"),
        "detected_destination_name": diagnostics.get("destination_name"),
        "detected_destinations": diagnostics.get("destinations", []),
        "detected_destination_ids": diagnostics.get("destination_ids", []),
        "detected_destination_names": diagnostics.get("destination_names", []),
        "detected_intent": primary_intent,
        "detected_intents": merged_intents,
        "intent_results": merged_intent_results,
        "keyword_candidate_count": int(diagnostics.get("keyword_candidate_count") or 0),
        "missing_destination_ids": diagnostics.get("missing_destination_ids", []),
        "memory_retrieval_queries": memory_queries,
        "memory_augmented": bool(memory_documents),
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

    # Do not auto-create tickets merely because a self-service/how-to branch lacks
    # enough data. Automatic escalation is reserved for requests that triage has
    # explicitly classified as case-specific human-required work. This keeps policy,
    # refund/cancellation procedure, and contact-information questions from creating
    # tickets unexpectedly.
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

    # FAQ-first retrieval is already a high-confidence evidence decision against
    # the canonical FAQ file. Do not send it through the generic LLM sufficiency
    # judge again: that adds latency/rate-limit pressure and can incorrectly reject
    # an authoritative FAQ answer that the deterministic matcher already identified.
    retrieval_mode = str(state.get("retrieval_mode") or "")
    if retrieval_mode.startswith("faq_") and documents:
        scores = [float(item.get("score", 0.0) or 0.0) for item in documents]
        best_score = max(scores, default=0.0)
        if best_score >= settings.min_relevance_score:
            reason = (
                "Deterministic FAQ clear-pass: canonical FAQ-first retrieval returned "
                "authoritative evidence above the configured relevance threshold."
            )
            print("\n===== RAG ASSESSMENT =====")
            print(f"Question: {effective_user_message(state)}")
            print(f"Retrieval mode: {retrieval_mode}")
            print(f"Detected intents: {detected_intents or [state.get('detected_intent')]}")
            print(f"Intent results: {intent_results}")
            print(f"Best score: {best_score:.4f}")
            print("Enough: True (deterministic FAQ clear-pass)")
            print(f"Reason: {reason}")
            print("==========================\n")
            return {
                "enough_information": True,
                "assessment_reason": reason,
                "best_relevance_score": best_score,
                "insufficiency_action": "no_data",
            }

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
            "facts or enough information for a useful partial answer. For comparison requests, if the context contains "
            "grounded descriptions of each compared entity, that is enough to synthesize a comparison even when no source "
            "contains an explicit pre-written comparison. Do not mark false merely because every possible detail is absent. "
            "Mark enough=false only when key facts are "
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
