from __future__ import annotations

import json
from typing import Any

from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.agents.state import AgentState
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import detect_destinations, load_destination_catalog


def _bounded_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _catalog_destination(destination_id: str) -> dict[str, Any] | None:
    item = load_destination_catalog().get(str(destination_id or "").strip())
    if not item:
        return None
    return {
        "id": str(item.get("id") or destination_id),
        "name_en": item.get("name_en"),
        "name_vi": item.get("name_vi"),
        "aliases": list(item.get("normalized_aliases") or item.get("aliases") or []),
    }


def _destination_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("name_vi")
        or item.get("name_en")
        or item.get("id")
        or ""
    ).strip()


def _build_destination_candidates(
    state: AgentState,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build a closed destination set from explicit mentions + structured memory."""
    current_message = effective_user_message(state)
    explicit_raw = detect_destinations(current_message)

    candidates: list[dict[str, Any]] = []
    explicit: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in explicit_raw:
        destination_id = str(raw.get("id") or "").strip()
        if not destination_id or destination_id in seen:
            continue
        item = _catalog_destination(destination_id) or dict(raw)
        item = dict(item)
        item["source"] = "current_explicit"
        item["recency_rank"] = None
        explicit.append(item)
        candidates.append(item)
        seen.add(destination_id)

    for rank, raw in enumerate(state.get("recent_destinations", []) or [], start=1):
        destination_id = str(raw.get("id") or "").strip()
        if not destination_id or destination_id in seen:
            continue
        item = _catalog_destination(destination_id)
        if item is None:
            continue
        item = dict(item)
        item["source"] = "recent_user_focus"
        item["recency_rank"] = rank
        candidates.append(item)
        seen.add(destination_id)

    return explicit, candidates


def _build_entity_candidates(state: AgentState) -> list[dict[str, Any]]:
    """Expose recent grounded entities using opaque refs, not product-name rules.

    The entity memory is populated from actual retrieved-document metadata. This
    lets packages, properties, attractions, services, promotions, FAQs and future
    entity types participate without adding one-off keyword keys to the resolver.
    """
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for rank, raw in enumerate(state.get("recent_entities", []) or [], start=1):
        name = str(raw.get("name") or "").strip()
        entity_type = str(raw.get("type") or raw.get("entity_type") or "entity").strip() or "entity"
        if not name:
            continue
        key = (entity_type.lower(), name.casefold())
        if key in seen:
            continue
        seen.add(key)
        candidate = {
            "ref": f"entity:{rank}",
            "name": name,
            "type": entity_type,
            "source": str(raw.get("source") or "recent_grounded_focus"),
            "recency_rank": rank,
        }
        destination_id = str(raw.get("destination_id") or "").strip()
        if destination_id:
            candidate["destination_id"] = destination_id
        output.append(candidate)
    return output


def _compact_focus_turns(state: AgentState, limit: int = 8) -> list[dict[str, Any]]:
    """Return recent user-grounded turns with stable opaque refs for semantic reuse."""
    turns = list(state.get("conversation_turns", []) or [])[-limit:]
    output: list[dict[str, Any]] = []
    for turn in turns:
        focus = turn.get("resolved_destinations") or turn.get("detected_destinations") or []
        focus_ids = [
            str(item.get("id") or "").strip()
            for item in focus
            if str(item.get("id") or "").strip()
        ]
        focus_entities = []
        for item in (turn.get("focus_entities") or [])[:12]:
            if not str(item.get("name") or "").strip():
                continue
            compact_entity = {
                "name": str(item.get("name") or "")[:180],
                "type": str(item.get("type") or item.get("entity_type") or "entity")[:80],
            }
            destination_id = str(item.get("destination_id") or "").strip()
            if destination_id:
                compact_entity["destination_id"] = destination_id[:120]
            focus_entities.append(compact_entity)
        output.append(
            {
                "turn_ref": str(turn.get("memory_ref") or ""),
                "user_message": str(turn.get("user_message") or "")[:500],
                "rag_query": str(turn.get("rag_query") or "")[:700],
                "focus_destination_ids": focus_ids,
                "focus_entities": focus_entities,
                "detected_intents": list(turn.get("detected_intents") or []),
            }
        )
    return output


def _fallback_resolution(
    explicit: list[dict[str, Any]],
    rag_query: str,
    reason: str,
    *,
    request_kind: str = "independent",
) -> AgentState:
    """Fail safely to current explicit context with memory fully disabled."""
    names = [_destination_name(item) for item in explicit]
    return {
        "explicit_destinations": explicit,
        "resolved_destinations": explicit,
        "resolved_destination_ids": [str(item.get("id") or "") for item in explicit],
        "resolved_destination_names": names,
        "resolved_entities": [],
        "resolved_entity_names": [],
        "selected_memory_turn_refs": [],
        "excluded_destination_ids": [],
        "excluded_entity_names": [],
        "context_uses_memory": False,
        "context_request_kind": request_kind,
        "context_resolution_reason": reason,
        "context_resolution_confidence": 0.0,
        "context_resolution_source": "explicit_fallback" if explicit else "none",
        "rag_query": rag_query,
    }


def _closed_refs_used(
    selected_destinations: list[dict[str, Any]],
    selected_entities: list[dict[str, Any]],
    selected_turn_refs: list[str],
    excluded_destinations: list[dict[str, Any]],
    excluded_entities: list[dict[str, Any]],
) -> bool:
    return bool(
        any(item.get("source") == "recent_user_focus" for item in selected_destinations)
        or selected_entities
        or selected_turn_refs
        or excluded_destinations
        or excluded_entities
    )


def _parse_closed_selection(
    result: dict[str, Any],
    *,
    destination_by_id: dict[str, dict[str, Any]],
    entity_by_ref: dict[str, dict[str, Any]],
    turn_refs: set[str],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
]:
    """Parse target and exclusion refs without allowing invented memory IDs."""
    fields = (
        "selected_destination_ids",
        "selected_entity_refs",
        "selected_turn_refs",
        "excluded_destination_ids",
        "excluded_entity_refs",
    )
    if any(not isinstance(result.get(field, []), list) for field in fields):
        return [], [], [], [], [], ["malformed-reference-list"]

    invalid: list[str] = []

    def destinations(field: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in result.get(field, []) or []:
            ref = str(raw or "").strip()
            if not ref or ref in seen:
                continue
            item = destination_by_id.get(ref)
            if item is None:
                invalid.append(ref)
                continue
            output.append(item)
            seen.add(ref)
        return output

    def entities(field: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in result.get(field, []) or []:
            ref = str(raw or "").strip()
            if not ref or ref in seen:
                continue
            item = entity_by_ref.get(ref)
            if item is None:
                invalid.append(ref)
                continue
            output.append(item)
            seen.add(ref)
        return output

    selected_turns: list[str] = []
    seen_turns: set[str] = set()
    for raw in result.get("selected_turn_refs", []) or []:
        ref = str(raw or "").strip()
        if not ref or ref in seen_turns:
            continue
        if ref not in turn_refs:
            invalid.append(ref)
            continue
        selected_turns.append(ref)
        seen_turns.add(ref)

    return (
        destinations("selected_destination_ids"),
        entities("selected_entity_refs"),
        selected_turns,
        destinations("excluded_destination_ids"),
        entities("excluded_entity_refs"),
        invalid,
    )


def resolve_conversation_context(state: AgentState) -> AgentState:
    """Decide whether the current turn needs memory, then resolve only that memory.

    Memory is a conditional dependency, not a session-wide constraint. The resolver
    distinguishes independent factual requests, factual continuations, and questions
    about the stored conversation itself. Positive targets and exclusions are kept
    separate so "another place" cannot turn the previous place into a retrieval target.
    """
    current_message = effective_user_message(state)
    guarded_query = str(state.get("rag_query") or current_message).strip()
    explicit, destination_candidates = _build_destination_candidates(state)
    entity_candidates = _build_entity_candidates(state)
    focus_turns = _compact_focus_turns(state)

    route = str(state.get("route") or "").strip()
    if route not in {"rag", "conversation_context"}:
        return _fallback_resolution(
            explicit,
            guarded_query,
            "Context resolver skipped because this route cannot consume conversation memory.",
        )

    has_memory = bool(
        any(item.get("source") == "recent_user_focus" for item in destination_candidates)
        or entity_candidates
        or focus_turns
    )
    if not has_memory:
        request_kind = "conversation_meta" if route == "conversation_context" else "independent"
        return {
            **_fallback_resolution(
                explicit,
                guarded_query,
                "No prior structured memory is available; only current explicit context was used.",
                request_kind=request_kind,
            ),
            "context_resolution_confidence": 1.0 if explicit else 0.0,
            "context_resolution_source": "current_explicit" if explicit else "none",
        }

    destination_payload = [
        {
            "id": item.get("id"),
            "name": _destination_name(item),
            "source": item.get("source"),
            "recency_rank": item.get("recency_rank"),
        }
        for item in destination_candidates
    ]

    llm = LLMService()
    system_prompt = (
        "You are the semantic memory-dependency resolver for a Vinpearl/VinWonders assistant. "
        "First decide whether the CURRENT request actually needs prior conversation. Memory is optional: being in the same "
        "session is never enough. Classify request_kind as exactly one of: independent, factual_continuation, conversation_meta. "
        "independent means the request is fully understandable and answerable as a new factual request without prior turns. "
        "factual_continuation means the user wants a NEW factual Vinpearl answer but a prior turn is required to resolve an omitted "
        "subject, pronoun, correction/clarification, comparison, ordinal, continuation, alternative, exclusion, or equivalent discourse "
        "relation. A clarification that narrows or corrects a previous factual question is factual_continuation, NOT conversation_meta. "
        "A request for another/additional/different option after a prior recommendation is factual_continuation because the previous "
        "option must be known in order not to repeat it. conversation_meta is only when the requested OUTPUT itself is about the chat "
        "record and no new KB lookup is requested. "
        "\n\nYou receive CLOSED candidate sets. Select only supplied IDs/refs; never invent one. Separate POSITIVE TARGETS from EXCLUSIONS. "
        "selected_* identifies prior destinations/entities that the current factual request is ABOUT. excluded_* identifies prior "
        "destinations/entities that must NOT be returned. Prefer excluding the concrete prior entity rather than its entire destination "
        "unless the user explicitly excludes the destination. Select prior turn refs only when re-retrieving that turn's grounded evidence "
        "materially helps the current factual continuation; do not select a turn merely because it is recent. Old assistant prose is never "
        "factual evidence. "
        "\n\nINVARIANT: if request_kind=independent, select no memory targets, exclusions, or turn refs and keep the standalone query faithful "
        "to the current request only. If request_kind=factual_continuation, select at least one required memory target, exclusion, or turn "
        "ref. Every memory-only name inserted into rag_query must be backed by one of those selected/excluded refs. For factual requests, "
        "return a standalone faithful English rag_query preserving the user's relation, constraints, preferences, and exclusions. Return JSON only."
    )
    payload = {
        "current_route_hint": route,
        "current_message": current_message,
        "guarded_rag_query": guarded_query,
        "destination_candidates": destination_payload,
        "memory_entity_candidates": entity_candidates,
        "recent_structured_focus_turns": focus_turns,
    }

    schema = '''{
  "request_kind": "independent|factual_continuation|conversation_meta",
  "selected_destination_ids": ["candidate-id"],
  "selected_entity_refs": ["entity:1"],
  "selected_turn_refs": ["turn:5"],
  "excluded_destination_ids": ["candidate-id"],
  "excluded_entity_refs": ["entity:1"],
  "uses_memory": false,
  "rag_query": "standalone faithful English retrieval query; empty only for conversation_meta",
  "reason": "brief semantic memory-dependency reason",
  "confidence": 0.0
}'''

    try:
        result = llm.json(
            system_prompt=system_prompt,
            user_prompt=(
                "UNTRUSTED_CONTEXT_JSON:\n"
                + json.dumps(payload, ensure_ascii=False)
                + "\n\nReturn exactly:\n"
                + schema
            ),
        )
    except Exception as exc:
        request_kind = "conversation_meta" if route == "conversation_context" else "independent"
        return _fallback_resolution(
            explicit,
            guarded_query,
            f"Semantic context resolver failed; memory disabled safely: {exc}",
            request_kind=request_kind,
        )

    destination_by_id = {str(item.get("id") or ""): item for item in destination_candidates}
    entity_by_ref = {str(item.get("ref") or ""): item for item in entity_candidates}
    turn_refs = {str(item.get("turn_ref") or "") for item in focus_turns if str(item.get("turn_ref") or "")}

    request_kind = str(result.get("request_kind") or "").strip().lower()
    if request_kind not in {"independent", "factual_continuation", "conversation_meta"}:
        request_kind = "conversation_meta" if route == "conversation_context" else "independent"

    def parse(value: dict[str, Any]):
        return _parse_closed_selection(
            value,
            destination_by_id=destination_by_id,
            entity_by_ref=entity_by_ref,
            turn_refs=turn_refs,
        )

    (
        selected_destinations,
        selected_entities,
        selected_turn_refs,
        excluded_destinations,
        excluded_entities,
        invalid_refs,
    ) = parse(result)
    if invalid_refs:
        return _fallback_resolution(
            explicit,
            guarded_query,
            "Semantic context resolver selected unsupported memory references; memory disabled safely.",
            request_kind="conversation_meta" if request_kind == "conversation_meta" else "independent",
        )

    if request_kind == "independent":
        selected_destinations = [item for item in selected_destinations if item.get("source") == "current_explicit"]
        selected_entities = []
        selected_turn_refs = []
        excluded_destinations = []
        excluded_entities = []
        resolved_query = guarded_query
    elif request_kind == "conversation_meta":
        resolved_query = ""
    else:
        resolved_query = str(result.get("rag_query") or "").strip() or guarded_query
        if not _closed_refs_used(
            selected_destinations,
            selected_entities,
            selected_turn_refs,
            excluded_destinations,
            excluded_entities,
        ):
            try:
                repair = llm.json(
                    system_prompt=(
                        system_prompt
                        + "\n\nREPAIR: You classified this as factual_continuation but selected no memory ref. "
                          "That is invalid. Select the minimal CLOSED target/exclusion/turn refs needed, or change "
                          "request_kind to independent if no prior context is actually needed."
                    ),
                    user_prompt=(
                        "UNTRUSTED_CONTEXT_JSON:\n"
                        + json.dumps(payload, ensure_ascii=False)
                        + "\n\nReturn exactly:\n"
                        + schema
                    ),
                )
                repaired_kind = str(repair.get("request_kind") or "").strip().lower()
                if repaired_kind in {"independent", "factual_continuation", "conversation_meta"}:
                    request_kind = repaired_kind
                (
                    selected_destinations,
                    selected_entities,
                    selected_turn_refs,
                    excluded_destinations,
                    excluded_entities,
                    invalid_refs,
                ) = parse(repair)
                if invalid_refs:
                    raise ValueError("repair selected unsupported refs")
                if request_kind == "independent":
                    selected_destinations = [item for item in selected_destinations if item.get("source") == "current_explicit"]
                    selected_entities = []
                    selected_turn_refs = []
                    excluded_destinations = []
                    excluded_entities = []
                    resolved_query = guarded_query
                elif request_kind == "conversation_meta":
                    resolved_query = ""
                else:
                    resolved_query = str(repair.get("rag_query") or "").strip() or guarded_query
                    result = repair
            except Exception as exc:
                return _fallback_resolution(
                    explicit,
                    guarded_query,
                    f"Continuation memory selection was inconsistent and repair failed; memory disabled safely: {exc}",
                    request_kind="independent",
                )

    uses_memory = _closed_refs_used(
        selected_destinations,
        selected_entities,
        selected_turn_refs,
        excluded_destinations,
        excluded_entities,
    )

    if request_kind == "factual_continuation" and not uses_memory:
        request_kind = "independent"
        selected_destinations = [item for item in selected_destinations if item.get("source") == "current_explicit"]
        selected_entities = []
        selected_turn_refs = []
        excluded_destinations = []
        excluded_entities = []
        resolved_query = guarded_query

    excluded_destination_ids = [str(item.get("id") or "") for item in excluded_destinations if str(item.get("id") or "")]
    excluded_entity_names = [str(item.get("name") or "").strip() for item in excluded_entities if str(item.get("name") or "").strip()]

    reason = str(result.get("reason") or "Semantic context resolution completed.").strip()[:500]
    confidence = _bounded_confidence(result.get("confidence"))

    source = "none"
    if uses_memory:
        source = "memory"
        if any(item.get("source") == "current_explicit" for item in selected_destinations):
            source = "current_plus_memory"
    elif selected_destinations:
        source = "current_explicit"

    destination_names = [_destination_name(item) for item in selected_destinations]
    entity_names = [str(item.get("name") or "").strip() for item in selected_entities]

    print("\n===== CONTEXT RESOLUTION =====")
    print(f"Question: {current_message}")
    print(f"Request kind: {request_kind}")
    print(f"Destination candidates: {[(item.get('id'), item.get('source')) for item in destination_candidates]}")
    print(f"Entity candidates: {[(item.get('ref'), item.get('name')) for item in entity_candidates]}")
    print(f"Resolved destinations: {[item.get('id') for item in selected_destinations]}")
    print(f"Resolved entities: {entity_names}")
    print(f"Excluded destinations: {excluded_destination_ids}")
    print(f"Excluded entities: {excluded_entity_names}")
    print(f"Selected memory turns: {selected_turn_refs}")
    print(f"Uses memory: {uses_memory}")
    print(f"Confidence: {confidence:.2f}")
    print(f"Reason: {reason}")
    print(f"RAG query: {resolved_query}")
    print("==============================\n")

    return {
        "explicit_destinations": explicit,
        "resolved_destinations": selected_destinations,
        "resolved_destination_ids": [str(item.get("id") or "") for item in selected_destinations],
        "resolved_destination_names": destination_names,
        "resolved_entities": selected_entities,
        "resolved_entity_names": entity_names,
        "selected_memory_turn_refs": selected_turn_refs,
        "excluded_destination_ids": excluded_destination_ids,
        "excluded_entity_names": excluded_entity_names,
        "context_uses_memory": uses_memory,
        "context_request_kind": request_kind,
        "context_resolution_reason": reason,
        "context_resolution_confidence": confidence,
        "context_resolution_source": source,
        "rag_query": resolved_query,
    }
