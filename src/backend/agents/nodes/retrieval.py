from src.backend.agents.state import AgentState
from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.config import get_settings
from src.backend.services.llm import LLMService
from src.backend.services.rag import get_rag_service, text_has_price_evidence
from src.backend.services.query_parser import normalize_text
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


def _metadata_identifier_values(value) -> set[str]:
    raw = str(value or "").strip().casefold()
    if not raw:
        return set()
    values = {raw}
    for component in raw.split("|"):
        component = component.strip()
        if not component:
            continue
        values.add(component)
        if "=" in component:
            _field, scalar = component.split("=", 1)
            scalar = scalar.strip()
            if scalar:
                values.add(scalar)
    return values


def _filter_memory_documents_to_entity_scope(
    documents: list[dict],
    scope: dict,
) -> tuple[list[dict], int]:
    """Keep old-turn evidence only when it belongs to the current entity target."""
    normalized_names = {
        normalize_text(value)
        for value in (scope.get("normalized_names") or scope.get("names") or [])
        if normalize_text(value)
    }
    entity_ids = {
        str(value or "").strip().casefold()
        for value in (scope.get("entity_ids") or [])
        if str(value or "").strip()
    }
    if not normalized_names and not entity_ids:
        return documents, 0

    kept: list[dict] = []
    for item in documents:
        metadata = item.get("metadata", {}) or {}
        entity_name = normalize_text(metadata.get("entity_name"))
        direct_name_match = bool(entity_name and entity_name in normalized_names)
        structural_match = any(
            _metadata_identifier_values(metadata.get(field)) & entity_ids
            for field in (
                "entity_id", "property_id", "complex_id", "venue_id",
                "attraction_id", "promotion_id",
            )
        )
        if direct_name_match or structural_match:
            kept.append(item)
    return kept, max(0, len(documents) - len(kept))

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


def _planned_retrieval_queries(state: AgentState) -> list[dict]:
    """Return atomic task goals as bounded semantic retrieval variants.

    The request planner already decomposes customer-visible outcomes, but the old
    retrieval path used only the combined ``rag_query`` and discarded those atomic
    goals. A compound query could therefore retrieve smoking regulations while
    crowding out the separate FAQ that explains whom to contact. Keep task identity
    and task-local intents so RAG can batch the variants and preserve diagnostics.
    """
    output: list[dict] = []
    seen: set[str] = set()
    for task in state.get("request_tasks") or []:
        if not isinstance(task, dict) or task.get("needs_retrieval") is False:
            continue
        base_task_id = str(task.get("task_id") or f"t{len(output) + 1}")
        intents = [
            str(value or "").strip().lower()
            for value in (task.get("retrieval_intents") or [])
            if str(value or "").strip()
        ]
        candidates = [task.get("goal"), *(task.get("retrieval_queries") or [])]
        for query_index, value in enumerate(candidates):
            query = str(value or "").strip()
            normalized = " ".join(query.lower().split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            output.append({
                "task_id": (
                    base_task_id
                    if query_index == 0
                    else f"{base_task_id}.q{query_index}"
                ),
                "query": query,
                "intents": intents,
            })
    return output


def _retrieval_tasks(state: AgentState) -> list[dict]:
    """Return normalized atomic tasks that actually require factual evidence."""
    output: list[dict] = []
    for index, raw in enumerate(state.get("request_tasks") or [], start=1):
        if not isinstance(raw, dict) or raw.get("needs_retrieval") is False:
            continue
        task = dict(raw)
        task["task_id"] = str(task.get("task_id") or f"t{index}").strip() or f"t{index}"
        task["goal"] = str(task.get("goal") or task.get("source_text") or "").strip()
        task["source_text"] = str(task.get("source_text") or task.get("goal") or "").strip()
        if not task["goal"] and not task["source_text"]:
            continue
        output.append(task)
    return output


def _task_query_payload(task: dict) -> tuple[str, str, list[dict]]:
    """Build a faithful primary query plus task-local semantic variants."""
    task_id = str(task.get("task_id") or "task")
    intents = [
        str(value or "").strip().lower()
        for value in (task.get("retrieval_intents") or [])
        if str(value or "").strip()
    ]
    source_text = str(task.get("source_text") or task.get("goal") or "").strip()
    candidates = [
        *(task.get("retrieval_queries") or []),
        task.get("goal"),
        source_text,
    ]
    queries: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        query = str(value or "").strip()
        normalized = " ".join(query.casefold().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        queries.append(query[:500])
    primary = queries[0] if queries else source_text
    additional = [
        {
            "task_id": f"{task_id}.q{index}",
            "query": query,
            "intents": intents,
        }
        for index, query in enumerate(queries[1:], start=1)
    ]
    return primary, source_text or primary, additional


def _result_is_confident(result: dict, minimum_score: float) -> bool:
    if str(result.get("status") or "") != "found":
        return False
    if result.get("faq_match"):
        return True
    try:
        return float(result.get("best_score") or 0.0) >= minimum_score
    except (TypeError, ValueError):
        return False


def _task_retrieval_result(
    task: dict,
    documents: list[dict],
    diagnostics: dict,
    *,
    minimum_score: float,
) -> dict:
    """Summarize evidence without collapsing independent same-intent tasks."""
    task_id = str(task.get("task_id") or "")
    requested_intents = [
        str(value or "").strip().lower()
        for value in (task.get("retrieval_intents") or [])
        if str(value or "").strip()
    ]
    intent_results = dict(diagnostics.get("intent_results") or {})
    confident_intents = [
        intent for intent in requested_intents
        if _result_is_confident(intent_results.get(intent, {}), minimum_score)
    ]
    missing_intents = [intent for intent in requested_intents if intent not in confident_intents]
    best_score = max(
        (float(item.get("score", 0.0) or 0.0) for item in documents),
        default=0.0,
    )
    faq_found = bool(
        (diagnostics.get("faq_match") or {}).get("accepted")
        or any(
            str((item.get("metadata", {}) or {}).get("entity_type") or "").lower() == "faq"
            and float(item.get("score", 0.0) or 0.0) >= minimum_score
            for item in documents
        )
    )
    evidence_found = bool(documents) and (
        faq_found
        or best_score >= minimum_score
        or bool(confident_intents)
    )
    if not evidence_found:
        status = "not_found"
    elif missing_intents:
        status = "partial"
    else:
        status = "found"

    return {
        "task_id": task_id,
        "task_type": str(task.get("task_type") or "general_qa"),
        "goal": str(task.get("goal") or ""),
        "source_text": str(task.get("source_text") or ""),
        "status": status,
        "document_count": len(documents),
        "serialized_document_count": 0,
        "best_score": round(best_score, 4),
        "requested_intents": requested_intents,
        "found_intents": confident_intents,
        "missing_intents": missing_intents,
        "intent_results": intent_results,
        "retrieval_mode": str(diagnostics.get("mode") or "unknown"),
        "price_requested": str(task.get("task_type") or "") in {"price_lookup", "price_estimate"},
        "has_numeric_price_evidence": any(
            text_has_price_evidence(item.get("text", "")) for item in documents
        ),
    }


def _merge_task_document_groups(groups: list[list[dict]]) -> list[dict]:
    """Round-robin atomic branches and merge duplicate evidence provenance."""
    output: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}
    max_len = max((len(group) for group in groups), default=0)
    for offset in range(max_len):
        for group in groups:
            if offset >= len(group):
                continue
            item = dict(group[offset])
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
            existing = by_key.get(key)
            task_ids = [
                str(value or "").strip()
                for value in (item.get("matched_task_ids") or [item.get("matched_task_id")])
                if str(value or "").strip()
            ]
            if existing is not None:
                merged_ids = list(existing.get("matched_task_ids") or [])
                for task_id in task_ids:
                    if task_id not in merged_ids:
                        merged_ids.append(task_id)
                existing["matched_task_ids"] = merged_ids
                continue
            item["matched_task_ids"] = task_ids
            by_key[key] = item
            output.append(item)
    return output


def _merge_task_intent_results(task_results: dict[str, dict]) -> dict[str, dict]:
    """Expose backward-compatible intent diagnostics while retaining per-task rows."""
    output: dict[str, dict] = {}
    for task_id, task_result in task_results.items():
        for intent, raw in (task_result.get("intent_results") or {}).items():
            result = dict(raw or {})
            bucket = output.setdefault(
                str(intent),
                {
                    "status": "not_found",
                    "document_count": 0,
                    "candidate_count": 0,
                    "best_score": 0.0,
                    "missing_destination_ids": [],
                    "task_ids": [],
                    "per_task": {},
                },
            )
            bucket["per_task"][task_id] = result
            if task_id not in bucket["task_ids"]:
                bucket["task_ids"].append(task_id)
            bucket["document_count"] += int(result.get("document_count") or 0)
            bucket["candidate_count"] += int(result.get("candidate_count") or 0)
            bucket["best_score"] = round(max(
                float(bucket.get("best_score") or 0.0),
                float(result.get("best_score") or 0.0),
            ), 4)
            for destination_id in result.get("missing_destination_ids") or []:
                if destination_id not in bucket["missing_destination_ids"]:
                    bucket["missing_destination_ids"].append(destination_id)
            if str(result.get("status") or "") == "found":
                bucket["status"] = "found"
            if result.get("faq_match"):
                bucket["faq_match"] = True
    return output


def _retrieve_atomic_task_branches(
    rag,
    state: AgentState,
    tasks: list[dict],
) -> tuple[list[dict], dict]:
    """Retrieve every atomic customer question independently, then merge evidence."""
    settings = get_settings()
    task_groups: list[list[dict]] = []
    task_results: dict[str, dict] = {}
    per_task_diagnostics: dict[str, dict] = {}
    all_intents: list[str] = []
    all_explicit_intents: list[str] = []
    all_derived_intents: list[str] = []
    all_destinations: list[dict] = []
    destination_ids: list[str] = []
    destination_names: list[str] = []
    missing_destination_ids: list[str] = []
    named_scope_names: list[str] = []
    named_scope_normalized_names: list[str] = []
    named_scope_entity_ids: list[str] = []
    modes: list[str] = []
    keyword_candidates = 0
    price_requested = False
    cost_estimate_requested = False
    booking_evidence_preferred = False
    exhaustive_complete = True

    for task in tasks:
        task_id = str(task.get("task_id") or f"t{len(task_results) + 1}")
        primary_query, source_text, additional_queries = _task_query_payload(task)
        task_intents = [
            str(value or "").strip().lower()
            for value in (task.get("retrieval_intents") or [])
            if str(value or "").strip()
        ]
        task_type = str(task.get("task_type") or "").strip().lower()
        task_price = task_type in {"price_lookup", "price_estimate"}
        task_cost_estimate = task_type == "price_estimate"
        task_exhaustive = str(task.get("result_scope") or "normal").lower() == "exhaustive"

        branch_documents, branch_diagnostics = rag.hybrid_search(
            query=primary_query or state.get("rag_query", ""),
            user_message=source_text or effective_user_message(state),
            top_k=max(2, int(settings.top_k)),
            resolved_destinations=state.get("resolved_destinations"),
            excluded_destination_ids=state.get("excluded_destination_ids") or [],
            excluded_entity_names=state.get("excluded_entity_names") or [],
            planned_intents=task_intents,
            planned_queries=additional_queries,
            force_price_requested=task_price,
            force_cost_estimate_requested=task_cost_estimate,
            exhaustive_requested=task_exhaustive,
            resolved_entity_names=state.get("resolved_entity_names") or [],
        )

        annotated: list[dict] = []
        for document in branch_documents:
            copied = dict(document)
            copied["matched_task_id"] = task_id
            copied["matched_task_ids"] = [task_id]
            copied["matched_task_goal"] = str(task.get("goal") or "")
            annotated.append(copied)
        task_groups.append(annotated)
        task_results[task_id] = _task_retrieval_result(
            task,
            annotated,
            branch_diagnostics,
            minimum_score=float(settings.min_relevance_score),
        )
        print(
            "[ATOMIC TASK RETRIEVAL] "
            f"task={task_id} status={task_results[task_id].get('status')} "
            f"intents={task_results[task_id].get('requested_intents')} "
            f"documents={task_results[task_id].get('document_count')} "
            f"best_score={task_results[task_id].get('best_score')} "
            f"source_text={task_results[task_id].get('source_text')!r}"
        )
        per_task_diagnostics[task_id] = dict(branch_diagnostics)

        mode = str(branch_diagnostics.get("mode") or "unknown")
        if mode not in modes:
            modes.append(mode)
        for field, target in (
            ("intents", all_intents),
            ("explicit_intents", all_explicit_intents),
            ("constraint_derived_intents", all_derived_intents),
        ):
            for value in branch_diagnostics.get(field) or []:
                text = str(value or "").strip()
                if text and text not in target:
                    target.append(text)
        for destination in branch_diagnostics.get("destinations") or []:
            destination_id = str(destination.get("id") or "")
            if destination_id and destination_id not in destination_ids:
                destination_ids.append(destination_id)
                all_destinations.append(destination)
        for name in branch_diagnostics.get("destination_names") or []:
            text = str(name or "").strip()
            if text and text not in destination_names:
                destination_names.append(text)
        for destination_id in branch_diagnostics.get("missing_destination_ids") or []:
            if destination_id not in missing_destination_ids:
                missing_destination_ids.append(destination_id)
        branch_scope = branch_diagnostics.get("named_entity_scope") or {}
        for field, target in (
            ("names", named_scope_names),
            ("normalized_names", named_scope_normalized_names),
            ("entity_ids", named_scope_entity_ids),
        ):
            for value in branch_scope.get(field) or []:
                text = str(value or "").strip()
                if text and text not in target:
                    target.append(text)
        keyword_candidates += int(branch_diagnostics.get("keyword_candidate_count") or 0)
        price_requested = price_requested or bool(branch_diagnostics.get("price_requested")) or task_price
        cost_estimate_requested = cost_estimate_requested or bool(branch_diagnostics.get("cost_estimate_requested")) or task_cost_estimate
        booking_evidence_preferred = booking_evidence_preferred or bool(branch_diagnostics.get("booking_evidence_preferred"))
        if task_exhaustive:
            exhaustive_complete = exhaustive_complete and bool(
                branch_diagnostics.get("exhaustive_retrieval_complete")
            )

    documents = _merge_task_document_groups(task_groups)
    intent_results = _merge_task_intent_results(task_results)
    primary_destination = all_destinations[0] if all_destinations else None
    diagnostics = {
        "mode": "task_aware_multi:" + "+".join(modes),
        "destination_id": primary_destination.get("id") if primary_destination else None,
        "destination_name": (
            primary_destination.get("name_vi") or primary_destination.get("name_en")
            if primary_destination else None
        ),
        "destinations": all_destinations,
        "destination_ids": destination_ids,
        "destination_names": destination_names,
        "intent": all_intents[0] if all_intents else None,
        "intents": all_intents,
        "explicit_intents": all_explicit_intents,
        "constraint_derived_intents": all_derived_intents,
        "planned_intents": list(all_intents),
        "has_budget_constraint": any(
            bool(value.get("has_budget_constraint")) for value in per_task_diagnostics.values()
        ),
        "budget_vnd": next((
            value.get("budget_vnd") for value in per_task_diagnostics.values()
            if value.get("budget_vnd") is not None
        ), None),
        "price_requested": price_requested,
        "booking_evidence_preferred": booking_evidence_preferred,
        "cost_estimate_requested": cost_estimate_requested,
        "exhaustive_requested": any(
            str(task.get("result_scope") or "normal").lower() == "exhaustive"
            for task in tasks
        ),
        "exhaustive_retrieval_complete": exhaustive_complete,
        "intent_origin": "request_tasks",
        "intent_results": intent_results,
        "task_results": task_results,
        "task_diagnostics": per_task_diagnostics,
        "keyword_candidate_count": keyword_candidates,
        "missing_destination_ids": missing_destination_ids,
        "named_entity_scope": {
            "names": named_scope_names,
            "normalized_names": named_scope_normalized_names,
            "entity_ids": named_scope_entity_ids,
        },
    }
    return documents, diagnostics


def _build_exhaustive_retrieval_packet(
    documents: list[dict],
    requested_intents: list[str],
    *,
    complete: bool,
    entity_scope: dict | None = None,
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
        "entity_scope": dict(entity_scope or {}),
        "entity_count": len(entities),
        "branches": branches,
        "entities": entities,
    }


def retrieve_context(state: AgentState) -> AgentState:
    rag = get_rag_service()
    planned_intents, planned_price, planned_cost_estimate, planned_exhaustive = _planned_retrieval_requirements(state)
    planned_queries = _planned_retrieval_queries(state)
    atomic_tasks = _retrieval_tasks(state)
    exhaustive_booking_semantic = bool(
        planned_exhaustive and "booking_product" in planned_intents
    )
    # A compound turn must be retrieved by atomic customer task, not merely by the
    # union of intent labels.  This is especially important for two independent
    # clauses that share one intent (e.g. hotline guidance + check-in time): an
    # intent-only search can return one FAQ and falsely mark both clauses answered.
    if len(atomic_tasks) > 1:
        documents, diagnostics = _retrieve_atomic_task_branches(rag, state, atomic_tasks)
    else:
        documents, diagnostics = rag.hybrid_search(
            query=state["rag_query"],
            user_message=effective_user_message(state),
            resolved_destinations=state.get("resolved_destinations"),
            excluded_destination_ids=state.get("excluded_destination_ids") or [],
            excluded_entity_names=state.get("excluded_entity_names") or [],
            planned_intents=planned_intents,
            planned_queries=planned_queries,
            force_price_requested=planned_price,
            force_cost_estimate_requested=planned_cost_estimate,
            exhaustive_requested=planned_exhaustive,
            resolved_entity_names=state.get("resolved_entity_names") or [],
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
    task_retrieval_results = dict(diagnostics.get("task_results", {}) or {})
    current_intents = list(diagnostics.get("intents", []) or [])

    replay_memory_turns = memory_turns
    if exhaustive_retrieval_requested and (diagnostics.get("named_entity_scope") or {}).get("names"):
        # Memory has already done its semantic job by resolving the standalone
        # entity-scoped RAG query. Replaying an older broad query here would be both
        # slower and capable of polluting a fresh complete child-record enumeration.
        replay_memory_turns = []
        print(
            "[MEMORY RETRIEVAL] semantic memory retained; old evidence replay skipped "
            f"for exhaustive entity scope={(diagnostics.get('named_entity_scope') or {}).get('names') or []}"
        )

    for turn in replay_memory_turns:
        previous_query = str(turn.get("rag_query") or "").strip()
        previous_message = str(turn.get("sanitized_user_request") or previous_query).strip()
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

    if memory_documents and diagnostics.get("named_entity_scope"):
        if exhaustive_retrieval_requested:
            # A fresh closed enumeration already owns the complete answer set.
            # Replaying an older broad turn can only add peer entities and corrupt
            # "all children of this entity" into "all entities at destination".
            filtered_count = len(memory_documents)
            memory_documents = []
        else:
            memory_documents, filtered_count = _filter_memory_documents_to_entity_scope(
                memory_documents,
                diagnostics.get("named_entity_scope") or {},
            )
        if filtered_count:
            print(
                "[MEMORY RETRIEVAL] filtered stale entity evidence "
                f"discarded={filtered_count} kept={len(memory_documents)} "
                f"scope={(diagnostics.get('named_entity_scope') or {}).get('names') or []}"
            )

    if memory_documents:
        # For recap/synthesis, previously grounded branches are the most useful
        # evidence. Put them before the broad current retrieval so the context
        # character budget cannot hide a short authoritative FAQ behind a long
        # regulations document.
        documents = _dedupe_documents(
            (documents + memory_documents)
            if task_retrieval_results
            else (memory_documents + documents)
        )
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
        retrieval_intents=current_intents or planned_intents,
        exhaustive_booking_requested=exhaustive_booking_requested,
        catalog_query=f"{effective_user_message(state)}\n{state.get('rag_query', '')}",
        preferred_output_currency=preferred_output_currency,
    )
    if int(enrichment.get("structured_price_document_count") or 0) > 0:
        retrieval_mode = f"{retrieval_mode}+structured_price"

    # Structured price rows are added after semantic task retrieval. Attach them to
    # the relevant atomic price task(s) so downstream context/assessment cannot treat
    # the price evidence as an unowned global document.
    price_task_ids = [
        task_id for task_id, result in task_retrieval_results.items()
        if result.get("price_requested")
    ]
    if price_task_ids:
        for item in documents:
            if not text_has_price_evidence(item.get("text", "")):
                continue
            task_ids = [
                str(value or "").strip()
                for value in (item.get("matched_task_ids") or [item.get("matched_task_id")])
                if str(value or "").strip()
            ]
            for task_id in price_task_ids:
                if task_id not in task_ids:
                    task_ids.append(task_id)
            item["matched_task_ids"] = task_ids
            if not item.get("matched_task_id") and task_ids:
                item["matched_task_id"] = task_ids[0]
        for task_id in price_task_ids:
            result = task_retrieval_results[task_id]
            has_price = any(
                task_id in (item.get("matched_task_ids") or [])
                and text_has_price_evidence(item.get("text", ""))
                for item in documents
            )
            result["has_numeric_price_evidence"] = has_price
            if has_price and result.get("status") == "not_found":
                result["status"] = "found"
            elif not has_price:
                # An atomic price task is not answered by a semantically related
                # package/property row that contains no actual numeric price.
                result["status"] = "not_found"

    primary_intent = current_intents[0] if current_intents else diagnostics.get("intent")

    exhaustive_retrieval_complete = bool(
        exhaustive_retrieval_requested
        and diagnostics.get("exhaustive_retrieval_complete", False)
    )
    exhaustive_retrieval_packet = _build_exhaustive_retrieval_packet(
        documents,
        current_intents or planned_intents,
        complete=exhaustive_retrieval_complete,
        entity_scope=diagnostics.get("named_entity_scope") or {},
    ) if exhaustive_retrieval_requested else {}
    if task_retrieval_results:
        context, context_diagnostics = rag.build_context_with_diagnostics(
            documents,
            exhaustive=exhaustive_retrieval_requested,
            task_aware=True,
        )
    else:
        context, context_diagnostics = rag.build_context_with_diagnostics(
            documents,
            exhaustive=exhaustive_retrieval_requested,
        )
    context_task_counts = dict(context_diagnostics.get("task_counts") or {})
    for task_id, result in task_retrieval_results.items():
        serialized_count = int(context_task_counts.get(task_id) or 0)
        result["serialized_document_count"] = serialized_count
        result["context_available"] = bool(serialized_count)
        if (
            result.get("status") in {"found", "partial"}
            and not serialized_count
            and not (
                result.get("price_requested")
                and result.get("has_numeric_price_evidence")
            )
        ):
            result["status"] = "not_found"

    return {
        "retrieved_documents": documents,
        "context": context,
        "context_document_count": int(context_diagnostics.get("document_count") or 0),
        "context_branch_counts": dict(context_diagnostics.get("branch_counts") or {}),
        "context_intents": list(context_diagnostics.get("intents") or []),
        "context_entity_keys": list(context_diagnostics.get("entity_keys") or []),
        "context_task_ids": list(context_diagnostics.get("task_ids") or []),
        "exhaustive_retrieval_requested": exhaustive_retrieval_requested,
        "exhaustive_retrieval_complete": exhaustive_retrieval_complete,
        "exhaustive_retrieval_packet": exhaustive_retrieval_packet,
        "retrieval_mode": retrieval_mode,
        "detected_destination": diagnostics.get("destination_id"),
        "detected_destination_name": diagnostics.get("destination_name"),
        "detected_destinations": diagnostics.get("destinations", []),
        "detected_destination_ids": diagnostics.get("destination_ids", []),
        "detected_destination_names": diagnostics.get("destination_names", []),
        "retrieval_entity_scope": dict(diagnostics.get("named_entity_scope") or {}),
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
        "task_retrieval_results": task_retrieval_results,
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
    task_results = state.get("task_retrieval_results", {}) or {}

    # Atomic task evidence is more precise than intent-level evidence. Two separate
    # questions can share one intent and must still be judged independently.  For an
    # informational compound turn, useful evidence for any task is enough to generate
    # a grounded partial answer; unsupported tasks will receive a task-local caveat.
    if len(task_results) > 1:
        supported: list[str] = []
        missing_tasks: list[str] = []
        for task_id, result in task_results.items():
            status = str(result.get("status") or "not_found")
            context_available = bool(
                int(result.get("serialized_document_count") or 0) > 0
                or result.get("has_numeric_price_evidence")
            )
            if status in {"found", "partial"} and context_available:
                supported.append(str(task_id))
            else:
                missing_tasks.append(str(task_id))

        best_task_score = max(
            (float(result.get("best_score") or 0.0) for result in task_results.values()),
            default=0.0,
        )
        request_mode = str(state.get("request_mode") or "information")
        resolution_mode = str(state.get("resolution_mode") or "information_only")

        if supported and (not missing_tasks or request_mode == "information"):
            reason = (
                f"Atomic task retrieval found answer evidence for {', '.join(supported)}"
                + (
                    f"; task-local evidence is unavailable for {', '.join(missing_tasks)}, so a partial informational answer is required."
                    if missing_tasks else "."
                )
            )
            print("\n===== ATOMIC TASK ASSESSMENT =====")
            print(f"Supported tasks: {supported}")
            print(f"Missing tasks: {missing_tasks}")
            print("Enough: True")
            print(f"Reason: {reason}")
            print("==================================\n")
            return {
                "enough_information": True,
                "assessment_reason": reason,
                "best_relevance_score": best_task_score,
                "insufficiency_action": "no_data",
            }

        if supported and resolution_mode == "self_serve":
            return _insufficient(
                state,
                (
                    f"Self-service compound request has evidence for {', '.join(supported)} "
                    f"but lacks grounded guidance for {', '.join(missing_tasks)}."
                ),
                best_task_score,
            )
        return _insufficient(
            state,
            "No atomic customer task has grounded evidence available in the serialized answer context.",
            best_task_score,
        )

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

    faq_documents = [
        item for item in documents
        if str((item.get("metadata", {}) or {}).get("entity_type") or "").lower() == "faq"
    ]
    accepted_faq_supplement = any(
        bool((result or {}).get("faq_match"))
        for result in intent_results.values()
        if isinstance(result, dict)
    )
    try:
        request_task_count = int(state.get("request_task_count") or 0)
    except (TypeError, ValueError):
        request_task_count = 0
    if request_task_count <= 0:
        request_task_count = len(task_results) if task_results else 1
    safe_faq_clear_pass = bool(
        faq_documents
        and request_task_count == 1
        and (retrieval_mode.startswith("faq_") or accepted_faq_supplement)
        and not state.get("price_requested")
        and not state.get("cost_estimate_requested")
        and not state.get("exhaustive_retrieval_requested")
        and input_task_type not in {
            "property_detail", "brand_detail", "place_structure_clarification"
        }
    )

    if safe_faq_clear_pass:
        scores = [float(item.get("score", 0.0) or 0.0) for item in faq_documents]
        best_score = max(scores, default=0.0)
        if best_score >= settings.min_relevance_score:
            reason = (
                "Verified FAQ clear-pass: canonical FAQ retrieval returned authoritative "
                "evidence above the configured relevance threshold for the single non-price task."
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
            expected_entity_names = {
                normalize_text(value)
                for value in (state.get("resolved_entity_names") or [])
                if normalize_text(value)
            }
            packet_entity_names = {
                normalize_text(value)
                for value in ((packet.get("entity_scope") or {}).get("names") or [])
                if normalize_text(value)
            }
            entity_scope_matches = bool(
                not expected_entity_names
                or expected_entity_names.issubset(packet_entity_names)
            )
            if not entity_scope_matches:
                return _insufficient(
                    state,
                    "Exhaustive evidence is not scoped to every resolved entity target for the current follow-up.",
                    0.0,
                )
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
                print(f"Exhaustive entity scope: {packet.get('entity_scope') or {}}")
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
