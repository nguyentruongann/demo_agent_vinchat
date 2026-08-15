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
        output.append(
            {
                "ref": f"entity:{rank}",
                "name": name,
                "type": entity_type,
                "source": str(raw.get("source") or "recent_grounded_focus"),
                "recency_rank": rank,
            }
        )
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
        focus_entities = [
            {
                "name": str(item.get("name") or "")[:180],
                "type": str(item.get("type") or item.get("entity_type") or "entity")[:80],
            }
            for item in (turn.get("focus_entities") or [])[:6]
            if str(item.get("name") or "").strip()
        ]
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
) -> AgentState:
    """Fail safely to explicit current destinations and no inherited entities."""
    names = [_destination_name(item) for item in explicit]
    return {
        "explicit_destinations": explicit,
        "resolved_destinations": explicit,
        "resolved_destination_ids": [str(item.get("id") or "") for item in explicit],
        "resolved_destination_names": names,
        "resolved_entities": [],
        "resolved_entity_names": [],
        "selected_memory_turn_refs": [],
        "context_uses_memory": False,
        "context_resolution_reason": reason,
        "context_resolution_confidence": 0.0,
        "context_resolution_source": "explicit_fallback" if explicit else "none",
        "rag_query": rag_query,
    }


def resolve_conversation_context(state: AgentState) -> AgentState:
    """Resolve references and factual-memory dependencies semantically.

    There are deliberately no product/topic keyword tables here. The model receives
    closed candidate sets derived from current destination detection, grounded entity
    metadata from prior turns, and recent turn refs. It may select none, one or many.
    This supports unseen packages/entities and follow-ups such as comparisons without
    teaching the resolver every future product name.
    """
    current_message = effective_user_message(state)
    guarded_query = str(state.get("rag_query") or current_message).strip()
    explicit, destination_candidates = _build_destination_candidates(state)
    entity_candidates = _build_entity_candidates(state)
    focus_turns = _compact_focus_turns(state)

    if str(state.get("route") or "") != "rag":
        return _fallback_resolution(
            explicit,
            guarded_query,
            "Context resolver skipped because the current route is not RAG.",
        )

    has_memory = bool(
        any(item.get("source") == "recent_user_focus" for item in destination_candidates)
        or entity_candidates
        or focus_turns
    )
    if not has_memory:
        return {
            **_fallback_resolution(
                explicit,
                guarded_query,
                "No prior structured memory is available; only current explicit context was used.",
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
    try:
        result = llm.json(
            system_prompt=(
                "You are a semantic conversation-reference resolver for a Vinpearl/VinWonders RAG assistant. "
                "Resolve the CURRENT request from meaning and discourse context, never from keyword rules. You receive "
                "three CLOSED memory surfaces: supported destination candidates, grounded entity candidates from prior "
                "retrieval, and prior RAG turn refs. Select only refs/IDs supplied to you. You may select zero, one, or "
                "multiple items from each surface. Current-explicit destinations are authoritative literal mentions. "
                "Recent destinations/entities are only inherited when the current request truly refers back through an "
                "omitted subject, pronoun, comparison, continuation, correction, ordinal/reference, or equivalent semantic "
                "relation. Do not blindly carry the previous topic into an independent new question. A named entity that "
                "appears only in the current request does not need to be in memory; preserve it faithfully in the query. "
                "Select prior turn refs when the CURRENT factual request depends on, summarizes, compares with, or continues "
                "facts/topics from those turns and re-retrieving their evidence would materially help. Do not select turns "
                "merely because they are recent. Never treat old assistant prose itself as factual evidence. Return a "
                "standalone faithful English RAG query for the CURRENT request, inserting selected destination/entity names "
                "only when needed to resolve references. Preserve all requested facts, quantities, preferences, exclusions, "
                "and comparison intent. Never invent an entity, destination, or missing detail. Return JSON only."
            ),
            user_prompt=(
                "UNTRUSTED_CONTEXT_JSON:\n"
                + json.dumps(
                    {
                        "current_message": current_message,
                        "guarded_rag_query": guarded_query,
                        "destination_candidates": destination_payload,
                        "memory_entity_candidates": entity_candidates,
                        "recent_structured_focus_turns": focus_turns,
                    },
                    ensure_ascii=False,
                )
                + "\n\nReturn exactly:\n"
                + '''{
  "selected_destination_ids": ["candidate-id"],
  "selected_entity_refs": ["entity:1"],
  "selected_turn_refs": ["turn:5"],
  "uses_memory": false,
  "rag_query": "standalone faithful English retrieval query",
  "reason": "brief semantic reference-resolution reason",
  "confidence": 0.0
}'''
            ),
        )
    except Exception as exc:
        return _fallback_resolution(
            explicit,
            guarded_query,
            f"Semantic context resolver failed; used explicit current context only: {exc}",
        )

    destination_by_id = {str(item.get("id") or ""): item for item in destination_candidates}
    entity_by_ref = {str(item.get("ref") or ""): item for item in entity_candidates}
    turn_refs = {str(item.get("turn_ref") or "") for item in focus_turns if str(item.get("turn_ref") or "")}

    raw_destination_ids = result.get("selected_destination_ids")
    raw_entity_refs = result.get("selected_entity_refs")
    raw_turn_refs = result.get("selected_turn_refs")
    if not isinstance(raw_destination_ids, list) or not isinstance(raw_entity_refs, list) or not isinstance(raw_turn_refs, list):
        return _fallback_resolution(
            explicit,
            guarded_query,
            "Semantic context resolver returned malformed reference lists; used explicit current context only.",
        )

    selected_destinations: list[dict[str, Any]] = []
    invalid_refs: list[str] = []
    seen_destinations: set[str] = set()
    for raw_id in raw_destination_ids:
        destination_id = str(raw_id or "").strip()
        if not destination_id or destination_id in seen_destinations:
            continue
        item = destination_by_id.get(destination_id)
        if item is None:
            invalid_refs.append(destination_id)
            continue
        selected_destinations.append(item)
        seen_destinations.add(destination_id)

    selected_entities: list[dict[str, Any]] = []
    seen_entity_refs: set[str] = set()
    for raw_ref in raw_entity_refs:
        ref = str(raw_ref or "").strip()
        if not ref or ref in seen_entity_refs:
            continue
        item = entity_by_ref.get(ref)
        if item is None:
            invalid_refs.append(ref)
            continue
        selected_entities.append(item)
        seen_entity_refs.add(ref)

    selected_turn_refs: list[str] = []
    seen_turn_refs: set[str] = set()
    for raw_ref in raw_turn_refs:
        ref = str(raw_ref or "").strip()
        if not ref or ref in seen_turn_refs:
            continue
        if ref not in turn_refs:
            invalid_refs.append(ref)
            continue
        selected_turn_refs.append(ref)
        seen_turn_refs.add(ref)

    if invalid_refs:
        return _fallback_resolution(
            explicit,
            guarded_query,
            "Semantic context resolver selected unsupported memory references; used explicit current context only.",
        )

    uses_memory = bool(
        any(item.get("source") == "recent_user_focus" for item in selected_destinations)
        or selected_entities
        or selected_turn_refs
    )
    resolved_query = str(result.get("rag_query") or "").strip() or guarded_query
    reason = str(result.get("reason") or "Semantic context resolution completed.").strip()[:500]
    confidence = _bounded_confidence(result.get("confidence"))

    source = "none"
    if selected_destinations or selected_entities or selected_turn_refs:
        has_explicit = any(item.get("source") == "current_explicit" for item in selected_destinations)
        if has_explicit and uses_memory:
            source = "current_plus_memory"
        elif uses_memory:
            source = "memory"
        elif has_explicit:
            source = "current_explicit"

    destination_names = [_destination_name(item) for item in selected_destinations]
    entity_names = [str(item.get("name") or "").strip() for item in selected_entities]

    print("\n===== CONTEXT RESOLUTION =====")
    print(f"Question: {current_message}")
    print(f"Destination candidates: {[(item.get('id'), item.get('source')) for item in destination_candidates]}")
    print(f"Entity candidates: {[(item.get('ref'), item.get('name')) for item in entity_candidates]}")
    print(f"Resolved destinations: {[item.get('id') for item in selected_destinations]}")
    print(f"Resolved entities: {entity_names}")
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
        "context_uses_memory": uses_memory,
        "context_resolution_reason": reason,
        "context_resolution_confidence": confidence,
        "context_resolution_source": source,
        "rag_query": resolved_query,
    }
