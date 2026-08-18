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


def _parse_current_destination_bindings(
    result: dict[str, Any],
    explicit: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Bind destinations mentioned in the CURRENT message only.

    Every explicit destination must end up in exactly one bucket: positive target or
    current-message exclusion. This prevents a memory classifier from accidentally
    dropping a destination that the user just named.
    """
    explicit_by_id = {
        str(item.get("id") or "").strip(): item
        for item in explicit
        if str(item.get("id") or "").strip()
    }
    valid_ids = set(explicit_by_id)
    invalid: list[str] = []

    def parse_ids(field: str) -> list[str]:
        raw_values = result.get(field, [])
        if not isinstance(raw_values, list):
            invalid.append(f"malformed:{field}")
            return []
        output: list[str] = []
        seen: set[str] = set()
        for raw in raw_values:
            destination_id = str(raw or "").strip()
            if not destination_id or destination_id in seen:
                continue
            if destination_id not in valid_ids:
                invalid.append(destination_id)
                continue
            output.append(destination_id)
            seen.add(destination_id)
        return output

    target_ids = parse_ids("current_target_destination_ids")
    excluded_ids = parse_ids("current_excluded_destination_ids")

    overlap = set(target_ids) & set(excluded_ids)
    if overlap:
        invalid.extend(f"overlap:{item}" for item in sorted(overlap))

    # A current explicit destination may never silently disappear. If the semantic
    # binder omitted an otherwise valid explicit mention, default it to a positive
    # current target. The model is specifically prompted to place negated/corrected
    # mentions in current_excluded_destination_ids, so this default is fail-safe for
    # the common standalone case and fixes stale-memory destination loss.
    assigned = set(target_ids) | set(excluded_ids)
    for destination_id in explicit_by_id:
        if destination_id not in assigned:
            target_ids.append(destination_id)

    targets = [explicit_by_id[item] for item in target_ids if item in explicit_by_id]
    exclusions = [explicit_by_id[item] for item in excluded_ids if item in explicit_by_id]
    return targets, exclusions, invalid


def _memory_refs_used(
    selected_memory_destinations: list[dict[str, Any]],
    selected_memory_entities: list[dict[str, Any]],
    selected_turn_refs: list[str],
    excluded_memory_destinations: list[dict[str, Any]],
    excluded_memory_entities: list[dict[str, Any]],
) -> bool:
    """Return whether prior conversational state is materially consumed."""
    return bool(
        selected_memory_destinations
        or selected_memory_entities
        or selected_turn_refs
        or excluded_memory_destinations
        or excluded_memory_entities
    )


def _dedupe_destinations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        destination_id = str(item.get("id") or "").strip()
        if not destination_id or destination_id in seen:
            continue
        seen.add(destination_id)
        output.append(item)
    return output


def _resolution_result(
    *,
    explicit: list[dict[str, Any]],
    selected_destinations: list[dict[str, Any]],
    selected_entities: list[dict[str, Any]],
    selected_turn_refs: list[str],
    excluded_destinations: list[dict[str, Any]],
    excluded_entities: list[dict[str, Any]],
    uses_memory: bool,
    request_kind: str,
    reason: str,
    confidence: float,
    source: str,
    rag_query: str,
) -> AgentState:
    selected_destinations = _dedupe_destinations(selected_destinations)
    excluded_destinations = _dedupe_destinations(excluded_destinations)
    excluded_ids = {
        str(item.get("id") or "").strip()
        for item in excluded_destinations
        if str(item.get("id") or "").strip()
    }
    # An explicit/current exclusion must win over a positive selection.
    selected_destinations = [
        item
        for item in selected_destinations
        if str(item.get("id") or "").strip() not in excluded_ids
    ]

    destination_names = [_destination_name(item) for item in selected_destinations]
    entity_names = [
        str(item.get("name") or "").strip()
        for item in selected_entities
        if str(item.get("name") or "").strip()
    ]
    excluded_destination_ids = [
        str(item.get("id") or "").strip()
        for item in excluded_destinations
        if str(item.get("id") or "").strip()
    ]
    excluded_entity_names = [
        str(item.get("name") or "").strip()
        for item in excluded_entities
        if str(item.get("name") or "").strip()
    ]

    return {
        "explicit_destinations": explicit,
        "resolved_destinations": selected_destinations,
        "resolved_destination_ids": [
            str(item.get("id") or "") for item in selected_destinations
        ],
        "resolved_destination_names": destination_names,
        "resolved_entities": selected_entities,
        "resolved_entity_names": entity_names,
        "selected_memory_turn_refs": selected_turn_refs,
        "excluded_destination_ids": excluded_destination_ids,
        "excluded_entity_names": excluded_entity_names,
        "context_uses_memory": uses_memory,
        "context_request_kind": request_kind,
        "context_resolution_reason": reason[:500],
        "context_resolution_confidence": _bounded_confidence(confidence),
        "context_resolution_source": source,
        "rag_query": rag_query,
    }


def resolve_conversation_context(state: AgentState) -> AgentState:
    """Resolve current context first; consult memory only when the turn depends on it.

    The resolver intentionally has two semantic stages:

    1. MEMORY DEPENDENCY GATE: decide whether the current request is standalone,
       a factual continuation that truly needs prior context, or a conversation-meta
       request. At the same time, bind/exclude only destinations explicitly present in
       the current message.
    2. MEMORY SELECTION: runs *only* for factual continuations and may select the
       minimal closed memory refs needed to resolve an omitted subject, comparison,
       correction, alternative, exclusion, ordinal, or similar discourse relation.

    This prevents stale session state from influencing independent questions while
    still supporting natural follow-ups such as "giá bao nhiêu?", "còn chỗ khác?",
    "ở Hà Nội thì sao?", and clarification/correction turns.
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

    current_explicit_payload = [
        {
            "id": item.get("id"),
            "name": _destination_name(item),
        }
        for item in explicit
    ]
    memory_destination_candidates = [
        item for item in destination_candidates if item.get("source") == "recent_user_focus"
    ]
    memory_destination_payload = [
        {
            "id": item.get("id"),
            "name": _destination_name(item),
            "recency_rank": item.get("recency_rank"),
        }
        for item in memory_destination_candidates
    ]

    llm = LLMService()

    # Stage 1: decide if memory is required. Do NOT allow this call to select old
    # entities/turns, which keeps stale memory out of independent requests by design.
    dependency_prompt = (
        "You are the memory-dependency gate for a Vinpearl/VinWonders assistant. "
        "Decide whether the CURRENT request actually requires prior conversation. Same session or topic similarity is NOT enough. "
        "Classify request_kind as exactly one of independent, factual_continuation, conversation_meta. "
        "independent: the current message plus any entities/destinations explicitly named IN THAT MESSAGE are sufficient to understand "
        "what new factual request to retrieve. Do not use memory merely because a previous destination/entity is related. "
        "factual_continuation: prior context is materially required to resolve an omitted subject/pronoun, 'this/that/it/there', ordinal, "
        "comparison, correction, clarification, 'another/additional/different' option, exclusion of a previous recommendation, or an equivalent "
        "discourse relation. If the same request could be answered correctly without knowing prior turns, it is independent. "
        "conversation_meta: the requested output itself is about the stored conversation and no new KB fact is requested. "
        "\n\nAlso bind destinations explicitly present in the CURRENT message only. Put each explicit destination in either "
        "current_target_destination_ids or current_excluded_destination_ids. A destination named as the desired/new target is a target. "
        "A destination named only as wrong, negated, replaced, or explicitly excluded is an exclusion. Never use a memory destination in these "
        "two current_* fields. If a current destination is positively named, it must never disappear merely because old memory exists. "
        "Return JSON only."
    )
    dependency_payload = {
        "current_route_hint": route,
        "current_message": current_message,
        "guarded_current_only_rag_query": guarded_query,
        "current_explicit_destinations": current_explicit_payload,
        "available_prior_destination_focus": memory_destination_payload,
        "available_prior_entities": entity_candidates,
        "recent_structured_focus_turns": focus_turns,
    }
    dependency_schema = '''{
  "request_kind": "independent|factual_continuation|conversation_meta",
  "needs_memory": false,
  "current_target_destination_ids": ["current-explicit-id"],
  "current_excluded_destination_ids": ["current-explicit-id"],
  "reason": "brief semantic dependency reason",
  "confidence": 0.0
}'''

    try:
        dependency = llm.json(
            system_prompt=dependency_prompt,
            user_prompt=(
                "UNTRUSTED_CONTEXT_JSON:\n"
                + json.dumps(dependency_payload, ensure_ascii=False)
                + "\n\nReturn exactly:\n"
                + dependency_schema
            ),
        )
    except Exception as exc:
        return _fallback_resolution(
            explicit,
            guarded_query,
            f"Memory dependency gate failed; memory disabled safely: {exc}",
            request_kind="conversation_meta" if route == "conversation_context" else "independent",
        )

    request_kind = str(dependency.get("request_kind") or "").strip().lower()
    if request_kind not in {"independent", "factual_continuation", "conversation_meta"}:
        request_kind = "conversation_meta" if route == "conversation_context" else "independent"

    current_targets, current_exclusions, current_binding_invalid = _parse_current_destination_bindings(
        dependency,
        explicit,
    )
    if current_binding_invalid:
        # Invalid IDs are a control-output integrity problem. Fail closed to current
        # explicit positive context, with all prior memory disabled.
        return _fallback_resolution(
            explicit,
            guarded_query,
            "Memory dependency gate returned unsupported current destination bindings; memory disabled safely.",
            request_kind="independent",
        )

    dependency_reason = str(
        dependency.get("reason") or "Memory dependency gate completed."
    ).strip()[:500]
    dependency_confidence = _bounded_confidence(dependency.get("confidence"))
    declared_needs_memory = bool(dependency.get("needs_memory", False))

    # Semantic invariant: independent requests never consume prior memory. Conversely,
    # a factual continuation must actually need memory; a contradictory gate output is
    # downgraded to independent instead of allowing stale context to leak in.
    if request_kind == "independent" or (
        request_kind == "factual_continuation" and not declared_needs_memory
    ):
        request_kind = "independent"
        source = "current_explicit" if current_targets else "none"
        result = _resolution_result(
            explicit=explicit,
            selected_destinations=current_targets,
            selected_entities=[],
            selected_turn_refs=[],
            excluded_destinations=current_exclusions,
            excluded_entities=[],
            uses_memory=False,
            request_kind=request_kind,
            reason=dependency_reason,
            confidence=dependency_confidence,
            source=source,
            rag_query=guarded_query,
        )
        _print_resolution(current_message, destination_candidates, entity_candidates, result)
        return result

    if request_kind == "conversation_meta":
        # conversation_context_response reads the closed stored conversation directly.
        # No factual retrieval target or RAG query should be carried into that route.
        result = _resolution_result(
            explicit=explicit,
            selected_destinations=[],
            selected_entities=[],
            selected_turn_refs=[],
            excluded_destinations=current_exclusions,
            excluded_entities=[],
            uses_memory=True,
            request_kind="conversation_meta",
            reason=dependency_reason,
            confidence=dependency_confidence,
            source="memory",
            rag_query="",
        )
        _print_resolution(current_message, destination_candidates, entity_candidates, result)
        return result

    # Stage 2: this turn has been semantically proven to need prior context. Select
    # only the minimal CLOSED memory refs required. Current explicit bindings are
    # supplied separately and cannot be overwritten by memory selection.
    memory_destination_by_id = {
        str(item.get("id") or ""): item for item in memory_destination_candidates
    }
    entity_by_ref = {str(item.get("ref") or ""): item for item in entity_candidates}
    turn_refs = {
        str(item.get("turn_ref") or "")
        for item in focus_turns
        if str(item.get("turn_ref") or "")
    }

    selector_prompt = (
        "You are the CLOSED memory selector for a Vinpearl/VinWonders factual continuation. The dependency gate has already established "
        "that prior context is required. Select the MINIMUM prior refs needed to resolve the current request. "
        "selected_memory_destination_ids/entities are positive prior targets the current request is still about. excluded_memory_* are prior "
        "recommendations/entities that must not be returned (for example 'another option'). Select a prior turn only when its grounded retrieval "
        "focus materially supplies the omitted relation/subject; recency alone is not enough. Never invent refs. Old assistant prose is not fresh "
        "factual evidence. Return a standalone faithful English rag_query that combines the CURRENT request with only the selected memory meaning, "
        "preserving constraints, comparisons, corrections, exclusions, quantities, dates, and requested relation. Current explicit targets/exclusions "
        "are authoritative and must not be replaced by stale memory. Return JSON only."
    )
    selector_payload = {
        "current_message": current_message,
        "guarded_current_only_rag_query": guarded_query,
        "current_target_destinations": [
            {"id": item.get("id"), "name": _destination_name(item)}
            for item in current_targets
        ],
        "current_excluded_destinations": [
            {"id": item.get("id"), "name": _destination_name(item)}
            for item in current_exclusions
        ],
        "memory_destination_candidates": memory_destination_payload,
        "memory_entity_candidates": entity_candidates,
        "recent_structured_focus_turns": focus_turns,
    }
    selector_schema = '''{
  "selected_memory_destination_ids": ["prior-destination-id"],
  "selected_memory_entity_refs": ["entity:1"],
  "selected_turn_refs": ["turn:5"],
  "excluded_memory_destination_ids": ["prior-destination-id"],
  "excluded_memory_entity_refs": ["entity:1"],
  "rag_query": "standalone faithful English retrieval query",
  "reason": "brief memory-selection reason",
  "confidence": 0.0
}'''

    try:
        selection = llm.json(
            system_prompt=selector_prompt,
            user_prompt=(
                "UNTRUSTED_CONTEXT_JSON:\n"
                + json.dumps(selector_payload, ensure_ascii=False)
                + "\n\nReturn exactly:\n"
                + selector_schema
            ),
        )
    except Exception as exc:
        result = _resolution_result(
            explicit=explicit,
            selected_destinations=current_targets,
            selected_entities=[],
            selected_turn_refs=[],
            excluded_destinations=current_exclusions,
            excluded_entities=[],
            uses_memory=False,
            request_kind="independent",
            reason=f"Memory selection failed; prior context disabled safely: {exc}",
            confidence=0.0,
            source="current_explicit" if current_targets else "none",
            rag_query=guarded_query,
        )
        _print_resolution(current_message, destination_candidates, entity_candidates, result)
        return result

    # Reuse the closed-reference parser by adapting Stage-2 field names to its
    # legacy closed schema. The destination map intentionally contains memory-only
    # destinations, so Stage 2 cannot reclassify current explicit destinations.
    adapted_selection = {
        "selected_destination_ids": selection.get("selected_memory_destination_ids", []),
        "selected_entity_refs": selection.get("selected_memory_entity_refs", []),
        "selected_turn_refs": selection.get("selected_turn_refs", []),
        "excluded_destination_ids": selection.get("excluded_memory_destination_ids", []),
        "excluded_entity_refs": selection.get("excluded_memory_entity_refs", []),
    }
    (
        selected_memory_destinations,
        selected_memory_entities,
        selected_turn_refs,
        excluded_memory_destinations,
        excluded_memory_entities,
        invalid_refs,
    ) = _parse_closed_selection(
        adapted_selection,
        destination_by_id=memory_destination_by_id,
        entity_by_ref=entity_by_ref,
        turn_refs=turn_refs,
    )

    if invalid_refs:
        result = _resolution_result(
            explicit=explicit,
            selected_destinations=current_targets,
            selected_entities=[],
            selected_turn_refs=[],
            excluded_destinations=current_exclusions,
            excluded_entities=[],
            uses_memory=False,
            request_kind="independent",
            reason="Memory selector returned unsupported refs; prior context disabled safely.",
            confidence=0.0,
            source="current_explicit" if current_targets else "none",
            rag_query=guarded_query,
        )
        _print_resolution(current_message, destination_candidates, entity_candidates, result)
        return result

    uses_memory = _memory_refs_used(
        selected_memory_destinations,
        selected_memory_entities,
        selected_turn_refs,
        excluded_memory_destinations,
        excluded_memory_entities,
    )
    if not uses_memory:
        # The second-stage selector found no concrete dependency. Treat the turn as
        # standalone rather than preserving a nominal continuation label.
        result = _resolution_result(
            explicit=explicit,
            selected_destinations=current_targets,
            selected_entities=[],
            selected_turn_refs=[],
            excluded_destinations=current_exclusions,
            excluded_entities=[],
            uses_memory=False,
            request_kind="independent",
            reason="Continuation gate found no usable memory ref; current request treated as independent.",
            confidence=_bounded_confidence(selection.get("confidence")),
            source="current_explicit" if current_targets else "none",
            rag_query=guarded_query,
        )
        _print_resolution(current_message, destination_candidates, entity_candidates, result)
        return result

    resolved_query = str(selection.get("rag_query") or "").strip() or guarded_query
    final_destinations = _dedupe_destinations(current_targets + selected_memory_destinations)
    final_exclusions = _dedupe_destinations(current_exclusions + excluded_memory_destinations)
    source = "memory"
    if current_targets:
        source = "current_plus_memory"

    selection_reason = str(selection.get("reason") or dependency_reason).strip()[:500]
    selection_confidence = _bounded_confidence(selection.get("confidence"))
    confidence = min(
        dependency_confidence if dependency_confidence > 0 else 1.0,
        selection_confidence if selection_confidence > 0 else 1.0,
    )

    result = _resolution_result(
        explicit=explicit,
        selected_destinations=final_destinations,
        selected_entities=selected_memory_entities,
        selected_turn_refs=selected_turn_refs,
        excluded_destinations=final_exclusions,
        excluded_entities=excluded_memory_entities,
        uses_memory=True,
        request_kind="factual_continuation",
        reason=selection_reason,
        confidence=confidence,
        source=source,
        rag_query=resolved_query,
    )
    _print_resolution(current_message, destination_candidates, entity_candidates, result)
    return result


def _print_resolution(
    current_message: str,
    destination_candidates: list[dict[str, Any]],
    entity_candidates: list[dict[str, Any]],
    result: AgentState,
) -> None:
    """Centralized diagnostics so all resolver exits are comparable in Railway logs."""
    print("\n===== CONTEXT RESOLUTION =====")
    print(f"Question: {current_message}")
    print(f"Request kind: {result.get('context_request_kind')}")
    print(
        "Destination candidates: "
        f"{[(item.get('id'), item.get('source')) for item in destination_candidates]}"
    )
    print(
        "Entity candidates: "
        f"{[(item.get('ref'), item.get('name')) for item in entity_candidates]}"
    )
    print(f"Resolved destinations: {result.get('resolved_destination_ids', [])}")
    print(f"Resolved entities: {result.get('resolved_entity_names', [])}")
    print(f"Excluded destinations: {result.get('excluded_destination_ids', [])}")
    print(f"Excluded entities: {result.get('excluded_entity_names', [])}")
    print(f"Selected memory turns: {result.get('selected_memory_turn_refs', [])}")
    print(f"Uses memory: {result.get('context_uses_memory', False)}")
    print(f"Resolution source: {result.get('context_resolution_source', 'none')}")
    print(f"Confidence: {float(result.get('context_resolution_confidence', 0.0) or 0.0):.2f}")
    print(f"Reason: {result.get('context_resolution_reason', '')}")
    print(f"RAG query: {result.get('rag_query', '')}")
    print("==============================\n")
