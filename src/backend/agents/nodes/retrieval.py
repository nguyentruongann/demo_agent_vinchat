from src.backend.agents.state import AgentState
from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.config import get_settings
from src.backend.services.llm import LLMService
from src.backend.services.rag import get_rag_service, text_has_price_evidence
from src.backend.services.retrieval_enrichment import (
    enrich_retrieved_documents,
    preferred_currency_for_language,
)

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

def _answer_mode(state: AgentState, diagnostics: dict) -> str:
    intents = set(diagnostics.get("intents") or [])
    input_task_type = str(state.get("input_task_type") or "general")
    if int(state.get("request_task_count") or 0) > 1:
        return "MULTI_INTENT"
    if input_task_type == "place_structure_clarification":
        return "PLACE_STRUCTURE_QA"
    if input_task_type == "property_detail":
        return "PROPERTY_DETAIL"
    if input_task_type == "brand_detail":
        return "BRAND_DETAIL"
    if input_task_type == "comparison":
        return "ENTITY_COMPARISON"
    if diagnostics.get("cost_estimate_requested"):
        return "PRICE_ESTIMATE"
    if diagnostics.get("price_requested"):
        return "PRICE_LOOKUP"
    if str(state.get("context_request_kind") or "") == "conversation_meta":
        return "MEMORY_RECALL"
    if "policy" in intents or "payment" in intents:
        return "POLICY_QA"
    if len(intents) > 1:
        return "MULTI_INTENT"
    if "hotel" in intents:
        return "HOTEL_RECOMMENDATION"
    if "attraction" in intents or str(diagnostics.get("intent_origin") or "") == "generic_discovery":
        return "DESTINATION_RECOMMENDATION"
    return "GENERAL_QA"


def _planned_retrieval_requirements(state: AgentState) -> tuple[list[str], bool, bool, bool]:
    intents: list[str] = []
    price_requested = False
    cost_estimate_requested = False
    exhaustive_catalog_requested = False
    for task in state.get("request_tasks") or []:
        if not isinstance(task, dict):
            continue
        for value in task.get("retrieval_intents") or []:
            intent = str(value or "").strip().lower()
            if intent and intent not in intents:
                intents.append(intent)
        task_type = str(task.get("task_type") or "").strip().lower()
        if task_type in {"price_lookup", "price_estimate"}:
            price_requested = True
        if task_type == "price_estimate":
            cost_estimate_requested = True
        if str(task.get("result_scope") or "normal").strip().lower() == "exhaustive":
            exhaustive_catalog_requested = True
    return intents, price_requested, cost_estimate_requested, exhaustive_catalog_requested


def _build_exhaustive_retrieval_packet(
    documents: list[dict],
    requested_intents: list[str],
    *,
    complete: bool,
) -> dict:
    """Build a compact, generic complete-set packet from exhaustive RAG rows.

    Unlike the structured booking-price packet, this works for any retrieval intent
    (hotel/service/attraction/dining/...). Duplicate entities that legitimately appear
    in several semantic branches are represented once with all matched intents.
    """
    requested = [str(value or "").strip() for value in requested_intents if str(value or "").strip()]
    entities: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}
    branch_keys: dict[str, list[str]] = {intent: [] for intent in requested}

    for item in documents or []:
        intent = str(item.get("matched_intent") or "").strip()
        if requested and intent not in requested:
            continue
        metadata = item.get("metadata", {}) or {}
        entity_type = str(metadata.get("entity_type") or metadata.get("category") or "entity").strip() or "entity"
        entity_name = str(metadata.get("entity_name") or metadata.get("source_file") or "").strip()
        entity_id = str(metadata.get("entity_id") or item.get("id") or entity_name).strip()
        if not entity_id and not entity_name:
            continue
        key = (entity_type, entity_id or entity_name)
        row = by_key.get(key)
        if row is None:
            raw_text = " ".join(str(item.get("text") or "").split())
            row = {
                "entity_key": f"{entity_type}:{entity_id or entity_name}",
                "name": entity_name or entity_id,
                "entity_type": entity_type,
                "destination_id": str(metadata.get("destination_id") or item.get("matched_destination_id") or "").strip(),
                "source_url": metadata.get("source_url"),
                # A short source-faithful excerpt lets the answerer give useful
                # context without serializing every full crawled page.
                "evidence_excerpt": raw_text[:650] + ("…" if len(raw_text) > 650 else ""),
                "matched_intents": [],
            }
            by_key[key] = row
            entities.append(row)
        if intent and intent not in row["matched_intents"]:
            row["matched_intents"].append(intent)
        if intent in branch_keys and row["entity_key"] not in branch_keys[intent]:
            branch_keys[intent].append(row["entity_key"])

    branches = {
        intent: {"entity_count": len(keys), "entity_keys": keys}
        for intent, keys in branch_keys.items()
    }
    return {
        "complete": bool(complete),
        "requested_intents": requested,
        "entity_count": len(entities),
        "branches": branches,
        "entities": entities,
    }


def retrieve_context(state: AgentState) -> AgentState:
    rag = get_rag_service()
    planned_intents, planned_price, planned_cost_estimate, planned_exhaustive = _planned_retrieval_requirements(state)
    exhaustive_booking_semantic = bool(
        planned_exhaustive and "booking_product" in planned_intents
    )
    documents, diagnostics = rag.hybrid_search(
        query=state["rag_query"],
        user_message=effective_user_message(state),
        resolved_destinations=state.get("resolved_destinations"),
        excluded_destination_ids=state.get("excluded_destination_ids") or [],
        excluded_entity_names=state.get("excluded_entity_names") or [],
        planned_intents=planned_intents,
        force_price_requested=planned_price,
        force_cost_estimate_requested=planned_cost_estimate,
        exhaustive_requested=planned_exhaustive,
    )

    exhaustive_booking_requested = bool(
        exhaustive_booking_semantic
        and (planned_price or diagnostics.get("price_requested"))
    )
    # Generic exhaustive coverage is independent of money. The structured booking
    # catalog remains a specialised price lane, while the generic exhaustive packet
    # below covers hotel/service/attraction/dining and mixed destination discovery.
    exhaustive_retrieval_requested = bool(planned_exhaustive)

    memory_turns = _select_memory_turns(state)
    memory_documents: list[dict] = []
    memory_queries: list[str] = []
    # Memory retrieval augments evidence only.  The semantic intent of the CURRENT
    # request must remain owned by current-query parsing; otherwise a previous turn
    # can leak ``hotel``/``payment``/... into an unrelated follow-up and trigger the
    # wrong assessment branch.
    current_intent_results = dict(diagnostics.get("intent_results", {}) or {})
    current_intents = list(diagnostics.get("intents", []) or [])

    for turn in memory_turns:
        previous_query = str(turn.get("rag_query") or "").strip()
        previous_message = str(turn.get("user_message") or "").strip()
        if not previous_query:
            continue
        memory_queries.append(previous_query)
        previous_docs, _ = rag.hybrid_search(
            query=previous_query,
            user_message=previous_message,
            top_k=min(3, max(1, get_settings().top_k)),
            resolved_destinations=turn.get("resolved_destinations") or None,
        )
        for item in previous_docs:
            copied = dict(item)
            copied["memory_retrieved"] = True
            memory_documents.append(copied)
        # Do not merge previous-turn diagnostics into the current turn. Those
        # diagnostics describe why an OLD query retrieved its documents, not what
        # the user is asking now.

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

    # Second-stage structured retrieval: Chroma decides *which* entities are
    # relevant; PostgreSQL then re-hydrates their non-null fields. Money requests
    # also receive destination-scoped room/booking price rows so the final model
    # can produce a grounded estimate instead of redirecting to the website.
    preferred_output_currency = preferred_currency_for_language(
        state.get("original_language"),
        state.get("original_language_name"),
    )
    resolved_price_scope_ids = [
        str(item.get("id") or "").strip()
        for item in (state.get("resolved_destinations") or [])
        if str(item.get("id") or "").strip()
    ]
    enrichment_destination_ids = (
        resolved_price_scope_ids
        if resolved_price_scope_ids
        else list(diagnostics.get("destination_ids", []) or [])
    )
    documents, enrichment = enrich_retrieved_documents(
        documents,
        destination_ids=enrichment_destination_ids,
        price_requested=bool(diagnostics.get("price_requested", False)),
        cost_estimate_requested=bool(diagnostics.get("cost_estimate_requested", False)),
        exhaustive_booking_requested=exhaustive_booking_requested,
        catalog_query=f"{effective_user_message(state)}\n{state.get('rag_query', '')}",
        preferred_output_currency=preferred_output_currency,
    )
    if int(enrichment.get("structured_price_document_count") or 0) > 0:
        retrieval_mode = f"{retrieval_mode}+structured_price"

    primary_intent = current_intents[0] if current_intents else diagnostics.get("intent")

    exhaustive_retrieval_complete = bool(
        exhaustive_retrieval_requested
        and diagnostics.get("exhaustive_retrieval_complete", False)
    )
    exhaustive_retrieval_packet = _build_exhaustive_retrieval_packet(
        documents,
        current_intents or planned_intents,
        complete=exhaustive_retrieval_complete,
    ) if exhaustive_retrieval_requested else {}
    context, context_diagnostics = rag.build_context_with_diagnostics(
        documents, exhaustive=exhaustive_retrieval_requested
    )

    return {
        "retrieved_documents": documents,
        "context": context,
        "context_document_count": int(context_diagnostics.get("document_count") or 0),
        "context_branch_counts": dict(context_diagnostics.get("branch_counts") or {}),
        "context_intents": list(context_diagnostics.get("intents") or []),
        "context_entity_keys": list(context_diagnostics.get("entity_keys") or []),
        "exhaustive_retrieval_requested": exhaustive_retrieval_requested,
        "exhaustive_retrieval_complete": exhaustive_retrieval_complete,
        "exhaustive_retrieval_packet": exhaustive_retrieval_packet,
        "retrieval_mode": retrieval_mode,
        "detected_destination": diagnostics.get("destination_id"),
        "detected_destination_name": diagnostics.get("destination_name"),
        "detected_destinations": diagnostics.get("destinations", []),
        "detected_destination_ids": diagnostics.get("destination_ids", []),
        "detected_destination_names": diagnostics.get("destination_names", []),
        "detected_intent": primary_intent,
        "detected_intents": current_intents,
        "explicit_intents": list(diagnostics.get("explicit_intents", []) or []),
        "constraint_derived_intents": list(diagnostics.get("constraint_derived_intents", []) or []),
        "has_budget_constraint": bool(diagnostics.get("has_budget_constraint", False)),
        "budget_vnd": diagnostics.get("budget_vnd"),
        "price_requested": bool(diagnostics.get("price_requested", False)),
        "booking_evidence_preferred": bool(diagnostics.get("booking_evidence_preferred", False)),
        "cost_estimate_requested": bool(diagnostics.get("cost_estimate_requested", False)),
        "exhaustive_catalog_requested": bool(enrichment.get("exhaustive_catalog_requested", exhaustive_booking_requested)),
        "exhaustive_catalog_complete": bool(enrichment.get("exhaustive_catalog_complete", False)),
        "exhaustive_catalog_count": int(enrichment.get("exhaustive_catalog_count") or 0),
        "exhaustive_catalog_scope": dict(enrichment.get("exhaustive_catalog_scope") or {}),
        "exhaustive_catalog_packet": dict(enrichment.get("exhaustive_catalog_packet") or {}),
        "price_data_as_of": enrichment.get("price_data_as_of"),
        "price_evidence_summary": str(enrichment.get("price_evidence_summary") or ""),
        "price_estimate_packet": enrichment.get("price_estimate_packet") or {},
        "price_estimate_destination_ids": list(enrichment.get("price_estimate_destination_ids") or []),
        "preferred_output_currency": str(enrichment.get("preferred_output_currency") or preferred_output_currency),
        "currency_conversion_guidance": str(enrichment.get("currency_conversion_guidance") or ""),
        "answer_mode": _answer_mode(state, diagnostics),
        "structured_enrichment_count": int(enrichment.get("structured_enrichment_count") or 0),
        "structured_price_document_count": int(enrichment.get("structured_price_document_count") or 0),
        "intent_origin": str(diagnostics.get("intent_origin") or "none"),
        "intent_results": current_intent_results,
        "keyword_candidate_count": int(diagnostics.get("keyword_candidate_count") or 0),
        "missing_destination_ids": diagnostics.get("missing_destination_ids", []),
        "memory_retrieval_queries": memory_queries,
        "memory_augmented": bool(memory_documents),
    }

def _insufficiency_action(state: AgentState) -> str:
    """Choose what to do when RAG cannot safely resolve the current request.

    Ticket creation is based on the semantic support mode, not a fixed keyword
    list or topic name. Informational discovery questions get a safe no-data
    answer. A user who is actively troubleshooting gets a ticket only when RAG
    cannot provide grounded self-service guidance.
    """
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

    # Price is a requested fact/constraint, not merely another intent label.
    # Multi-intent partial-answer logic must not declare success when the user
    # explicitly asked for a price but none of the selected chunks contains an
    # actual numeric price. This check is deterministic and leaves all existing
    # partial-answer behavior unchanged for non-price questions.
    if state.get("price_requested") and documents:
        price_documents = [
            item for item in documents if text_has_price_evidence(item.get("text", ""))
        ]
        if not price_documents:
            best_price_score = max(
                (float(item.get("score", 0.0) or 0.0) for item in documents),
                default=0.0,
            )
            return _insufficient(
                state,
                "The user explicitly requested pricing, but the retrieved context contains no numeric price evidence.",
                best_price_score,
            )

    # FAQ-first retrieval is already a high-confidence evidence decision against
    # the canonical FAQ file. Do not send it through the generic LLM sufficiency
    # judge again: that adds latency/rate-limit pressure and can incorrectly reject
    # an authoritative FAQ answer that the deterministic matcher already identified.
    retrieval_mode = str(state.get("retrieval_mode") or "")
    input_task_type = str(state.get("input_task_type") or "general")

    if retrieval_mode.startswith("faq_") and documents and input_task_type not in {"property_detail", "brand_detail", "place_structure_clarification"}:
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
    # Only CURRENT-user or deterministic generic-discovery intents may use the
    # multi-intent fast-path.  Intents inferred solely from an LLM rewrite are
    # retrieval hints and must still pass the evidence judge, because the rewrite
    # may introduce category words the user never asked for.
    intent_origin = str(state.get("intent_origin") or "none")
    fast_path_intents_are_authoritative = intent_origin in {
        "current_explicit",
        "generic_discovery",
        "constraint_derived",
    }
    def branch_is_confident(result: dict) -> bool:
        if result.get("status") != "found":
            return False
        if result.get("faq_match"):
            return True
        try:
            branch_score = float(result.get("best_score") or 0.0)
        except (TypeError, ValueError):
            branch_score = 0.0
        return branch_score >= settings.min_relevance_score

    # Aggregate cost estimates are allowed to be synthesized from structured
    # component prices. They do not require a pre-written package or an exact
    # "solo 3D2N" offer row. If the enrichment lane produced any structured
    # price evidence, the final answerer can produce a grounded estimate with
    # assumptions and destination-level breakdowns.
    if state.get("cost_estimate_requested") and int(state.get("structured_price_document_count") or 0) > 0:
        best_score = max(
            (float(item.get("score", 0.0) or 0.0) for item in documents),
            default=0.0,
        )
        reason = (
            "Cost-estimate clear-pass: structured PostgreSQL price evidence is available, "
            "so the answerer can build a grounded destination-level estimate from components rather than requiring an exact package row."
        )
        print("\n===== RAG ASSESSMENT =====")
        print(f"Question: {effective_user_message(state)}")
        print(f"RAG query: {state.get('rag_query', '')}")
        print(f"Retrieval mode: {state.get('retrieval_mode', 'unknown')}")
        print(f"Detected intents: {detected_intents or [state.get('detected_intent')]}")
        print(f"Intent origin: {state.get('intent_origin', 'none')}")
        print(f"Structured price docs: {state.get('structured_price_document_count')}")
        print(f"Estimate destinations: {state.get('price_estimate_destination_ids') or []}")
        print(f"Best score: {best_score:.4f}")
        print("Enough: True (cost-estimate structured clear-pass)")
        print(f"Reason: {reason}")
        print("==========================\n")
        return {
            "enough_information": True,
            "assessment_reason": reason,
            "best_relevance_score": best_score,
            "insufficiency_action": "no_data",
        }

    if state.get("exhaustive_catalog_requested") and state.get("exhaustive_catalog_complete"):
        catalog_count = int(state.get("exhaustive_catalog_count") or 0)
        if catalog_count > 0:
            best_score = max(
                (float(item.get("score", 0.0) or 0.0) for item in documents),
                default=0.0,
            )
            reason = (
                "Exhaustive structured-catalog clear-pass: PostgreSQL returned the complete "
                f"canonical booking-product set for the resolved scope ({catalog_count} records)."
            )
            print("\n===== RAG ASSESSMENT =====")
            print(f"Question: {effective_user_message(state)}")
            print(f"RAG query: {state.get('rag_query', '')}")
            print(f"Retrieval mode: {state.get('retrieval_mode', 'unknown')}")
            print(f"Catalog scope: {state.get('exhaustive_catalog_scope') or {}}")
            print(f"Catalog count: {catalog_count}")
            print(f"Best score: {best_score:.4f}")
            print("Enough: True (exhaustive structured-catalog clear-pass)")
            print(f"Reason: {reason}")
            print("==========================\n")
            return {
                "enough_information": True,
                "assessment_reason": reason,
                "best_relevance_score": best_score,
                "insufficiency_action": "no_data",
            }

    if state.get("exhaustive_retrieval_requested"):
        packet = state.get("exhaustive_retrieval_packet") or {}
        if state.get("exhaustive_retrieval_complete") and isinstance(packet, dict):
            entity_count = int(packet.get("entity_count") or 0)
            if entity_count > 0:
                best_score = max(
                    (float(item.get("score", 0.0) or 0.0) for item in documents),
                    default=0.0,
                )
                reason = (
                    "Exhaustive retrieval clear-pass: the resolved destination/intents were "
                    f"enumerated as a complete indexed entity set ({entity_count} unique entities), "
                    "independent of normal top-k sampling."
                )
                print("\n===== RAG ASSESSMENT =====")
                print(f"Question: {effective_user_message(state)}")
                print(f"Retrieval mode: {state.get('retrieval_mode', 'unknown')}")
                print(f"Exhaustive branches: {packet.get('branches') or {}}")
                print(f"Context branches actually serialized: {state.get('context_branch_counts') or {}}")
                print(f"Best score: {best_score:.4f}")
                print("Enough: True (generic exhaustive clear-pass)")
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
                "Exhaustive enumeration completed for the resolved scope but found no indexed entities to answer with.",
                0.0,
            )

    # Current-task clear-passes. These protect against an LLM sufficiency judge
    # rejecting usable entity evidence just because the customer's wording contained
    # a mistaken assumption (for example "2 nơi hả?") or because it expected a
    # pre-written review. Retrieval evidence by entity type is enough for the final
    # answerer to clarify/review without hallucinating.
    entity_types = {
        str((item.get("metadata", {}) or {}).get("entity_type") or "").strip()
        for item in documents
    }
    if input_task_type == "property_detail" and entity_types & {"property", "room"}:
        best_score = max((float(item.get("score", 0.0) or 0.0) for item in documents), default=0.0)
        reason = "Property-detail clear-pass: retrieved evidence contains property/room records for the named entity."
        print("\n===== RAG ASSESSMENT =====")
        print(f"Question: {effective_user_message(state)}")
        print(f"RAG query: {state.get('rag_query', '')}")
        print(f"Retrieval mode: {state.get('retrieval_mode', 'unknown')}")
        print(f"Answer mode: {state.get('answer_mode', '')}")
        print(f"Entity types: {sorted(entity_types)}")
        print(f"Best score: {best_score:.4f}")
        print("Enough: True (property-detail clear-pass)")
        print(f"Reason: {reason}")
        print("==========================\n")
        return {
            "enough_information": True,
            "assessment_reason": reason,
            "best_relevance_score": best_score,
            "insufficiency_action": "no_data",
        }

    if input_task_type == "place_structure_clarification" and documents:
        best_score = max((float(item.get("score", 0.0) or 0.0) for item in documents), default=0.0)
        useful_types = {"property", "room", "complex", "attraction", "booking_product", "destination"}
        if entity_types & useful_types or state.get("context_uses_memory"):
            reason = (
                "Place-structure clear-pass: current turn asks to clarify/group previously mentioned items; "
                "retrieved or memory evidence is sufficient to answer as one place with components unless distinct places are grounded."
            )
            print("\n===== RAG ASSESSMENT =====")
            print(f"Question: {effective_user_message(state)}")
            print(f"RAG query: {state.get('rag_query', '')}")
            print(f"Retrieval mode: {state.get('retrieval_mode', 'unknown')}")
            print(f"Answer mode: {state.get('answer_mode', '')}")
            print(f"Entity types: {sorted(entity_types)}")
            print(f"Best score: {best_score:.4f}")
            print("Enough: True (place-structure clear-pass)")
            print(f"Reason: {reason}")
            print("==========================\n")
            return {
                "enough_information": True,
                "assessment_reason": reason,
                "best_relevance_score": best_score,
                "insufficiency_action": "no_data",
            }

    # Cross-cutting constraints must be satisfied, not merely accompanied by some
    # other useful branch. For example, a generic destination article cannot rescue
    # a "2 million VND" recommendation if the derived promotion branch found no
    # explicit offer/ticket price within that ceiling. Retrieval already filters the
    # derived budget branch to price-fitting evidence, so this remains deterministic.
    derived_constraints = list(state.get("constraint_derived_intents", []) or [])
    if state.get("has_budget_constraint") and derived_constraints and intent_results:
        missing_constraints = [
            name
            for name in derived_constraints
            if not branch_is_confident(intent_results.get(name, {}))
            or intent_results.get(name, {}).get("constraint_satisfied") is False
        ]
        if missing_constraints:
            best_constraint_score = max(
                (float(intent_results.get(name, {}).get("best_score") or 0.0) for name in derived_constraints),
                default=0.0,
            )
            budget_vnd = state.get("budget_vnd")
            budget_text = f"{int(budget_vnd):,} VND" if budget_vnd else "the requested budget"
            return _insufficient(
                state,
                (
                    f"Budget constraint is not grounded: no price-bearing evidence within {budget_text} "
                    f"was found for {', '.join(missing_constraints)}."
                ),
                best_constraint_score,
            )

    # For authoritative current-turn intents, retrieval metadata is the source of
    # truth about whether matching evidence exists. Do not let unrelated global or
    # memory-augmented documents rescue an intent that the retriever marked missing.
    # This is the invariant that prevents identical near-threshold runs from
    # flipping solely because the LLM sufficiency judge interpreted stray context.
    if detected_intents and intent_results and fast_path_intents_are_authoritative:
        confident_branches = [
            name for name, result in intent_results.items() if branch_is_confident(result)
        ]
        if not confident_branches:
            best_branch_score = max(
                (float(result.get("best_score") or 0.0) for result in intent_results.values()),
                default=0.0,
            )
            return _insufficient(
                state,
                "No requested intent branch has grounded evidence above the configured relevance threshold.",
                best_branch_score,
            )

    if len(detected_intents) > 1 and intent_results and fast_path_intents_are_authoritative:
        serialized_intents = set(str(value or "") for value in (state.get("context_intents") or []) if str(value or ""))
        found = [
            name for name, result in intent_results.items()
            if branch_is_confident(result) and name in serialized_intents
        ]
        missing = [
            name for name, result in intent_results.items()
            if not branch_is_confident(result) or name not in serialized_intents
        ]
        if found:
            best_score = max(
                (float(intent_results[name].get("best_score") or 0.0) for name in found),
                default=0.0,
            )
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
                print(f"Intent origin: {intent_origin}")
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
    context_intents = set(str(value or "") for value in (state.get("context_intents") or []) if str(value or ""))
    requested_found_intents = {
        str(name) for name, result in intent_results.items() if str(result.get("status") or "") == "found"
    }
    # Retrieval coverage and serialized-context coverage are different contracts.
    # A branch may be found upstream but absent from the 18k answer context. Never
    # clear-pass that mismatch as if the final model had actually received it.
    context_covers_found_branches = bool(requested_found_intents) and requested_found_intents.issubset(context_intents)

    if (
        is_information
        and is_destination_scoped
        and all_requested_branches_found
        and context_covers_found_branches
        and not missing
    ):
        reason = (
            "Deterministic clear-pass: destination-scoped retrieval found every requested "
            "branch and every found branch is present in the context actually serialized for the answer model."
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

Intent provenance:
{state.get('intent_origin', 'none')}

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
    print(f"Intent origin: {state.get('intent_origin', 'none')}")
    if state.get("has_budget_constraint"):
        print(f"Budget constraint: {state.get('budget_vnd')} VND")
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
