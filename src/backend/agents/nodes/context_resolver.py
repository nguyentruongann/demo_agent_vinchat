from __future__ import annotations

import json
from typing import Any

from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.agents.state import AgentState
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import detect_destinations, load_destination_catalog, normalize_text


_USER_FOCUS_DESTINATION_SOURCES = {
    "current_explicit",
    "user_explicit",
    "user_explicit_kb",
    "user_explicit_legacy_detection",
    "user_explicit_logic_subject",
    "user_confirmed",
    "user_confirmed_via_memory",
    "recent_user_focus",
    "user_focus_from_selected_turn",
    "current_page_context",
}
_ASSISTANT_PROPOSAL_DESTINATION_SOURCES = {
    "assistant_suggestion",
    "assistant_suggestion_kb",
    "grounded_answer",
    "grounded_answer_kb",
    "recent_assistant_proposal",
}
_RETRIEVAL_ONLY_DESTINATION_SOURCES = {
    "retrieval_detection",
    "retrieval_evidence",
    "grounded_retrieval",
    "recent_retrieval_evidence",
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


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


def _message_uses_page_context(message: str) -> bool:
    text = normalize_text(message)
    if not text:
        return False
    markers = (
        "here", "this place", "this destination", "this hotel", "this resort",
        "current page", "on this page", "o day", "ở đây", "cho nay", "chỗ này",
        "noi nay", "nơi này", "trang nay", "trang này", "tai day", "tại đây",
    )
    return any(normalize_text(marker) in text for marker in markers)


def _infer_current_input_task(message: str) -> dict[str, Any]:
    """Classify the *current* customer task before memory selection.

    This is intentionally lightweight and runs after the raw guardrail has passed.
    It does not answer the question; it gives downstream memory/retrieval nodes a
    stable reading of what the customer is trying to do now.  The important UX
    distinction is that customers may phrase an assumption incorrectly ("ở đây có
    2 nơi hả?") when the UI or prior answer confused them.  That wording should
    trigger clarification/grouping against memory, not force a fake comparison.
    """
    text = normalize_text(message)
    if not text:
        return {
            "input_task_type": "general",
            "current_user_intent": "general Vinpearl information request",
            "memory_resolution_strategy": "current_message_first",
            "place_grouping_hint": {},
        }

    place_count_markers = (
        "2 noi", "hai noi", "may noi", "mấy nơi", "tung noi", "từng nơi",
        "co 2 noi", "co hai noi", "có 2 nơi", "có hai nơi",
        "2 cho", "hai cho", "may cho", "mấy chỗ", "tung cho", "từng chỗ",
        "co 2 cho", "co hai cho", "có 2 chỗ", "có hai chỗ",
        "hai dia diem", "2 dia diem", "mấy địa điểm", "co phai 2", "có phải 2",
    )
    if any(marker in text for marker in place_count_markers):
        return {
            "input_task_type": "place_structure_clarification",
            "current_user_intent": (
                "clarify whether the previously mentioned items are separate places "
                "or components/names of the same place, then review the supported components"
            ),
            "memory_resolution_strategy": "use_recent_answer_entities_to_group_places_do_not_assume_count",
            "place_grouping_hint": {
                "customer_count_may_be_wrong": True,
                "group_by": ["destination_id", "complex_id", "property_id", "area_alias"],
                "same_destination_components_are_not_separate_places": True,
                "brand_suffix_is_not_a_place": True,
            },
        }

    brand_markers = ("affiliated by melia", "affiliated by meliá")
    if any(marker in text for marker in brand_markers):
        # If the user names a full Vinpearl property, treat it as a property detail
        # query; otherwise they are asking about the brand/suffix concept itself.
        property_context_markers = ("vinpearl", "resort", "hotel", "khach san", "khách sạn")
        if not any(marker in text for marker in property_context_markers):
            return {
                "input_task_type": "brand_detail",
                "current_user_intent": "explain the Affiliated by Meliá label/relationship without turning one property into a destination",
                "memory_resolution_strategy": "current_message_first_memory_only_for_examples",
                "place_grouping_hint": {"brand_suffix_is_not_a_place": True},
            }

    detail_markers = (
        "chi tiet", "chi tiết", "thong tin", "thông tin", "review", "danh gia", "đánh giá",
        "gioi thieu", "giới thiệu", "tell me about", "details about", "detail about",
    )
    property_markers = ("vinpearl", "resort", "hotel", "khach san", "khách sạn")
    if any(marker in text for marker in detail_markers) and any(marker in text for marker in property_markers):
        return {
            "input_task_type": "property_detail",
            "current_user_intent": "provide details about the explicitly named Vinpearl property/entity",
            "memory_resolution_strategy": "current_explicit_entity_first",
            "place_grouping_hint": {"entity_detail_not_generic_faq": True},
        }

    comparison_markers = ("so sanh", "so sánh", "khac nhau", "khác nhau", "nen chon", "nên chọn", "compare")
    if any(marker in text for marker in comparison_markers):
        return {
            "input_task_type": "comparison",
            "current_user_intent": "compare the explicitly named or memory-resolved supported entities",
            "memory_resolution_strategy": "use_memory_only_when_compared_entities_are_omitted",
            "place_grouping_hint": {"require_distinct_entities_before_comparing": True},
        }

    return {
        "input_task_type": "general",
        "current_user_intent": "answer the current Vinpearl/VinWonders request",
        "memory_resolution_strategy": "current_message_first_memory_only_if_dependency_gate_requires_it",
        "place_grouping_hint": {},
    }


def _input_task_from_request_plan(state: AgentState, message: str) -> dict[str, Any]:
    """Bridge the N-task request plan into legacy single-task fields.

    Downstream code still reads input_task_type/current_user_intent, but those
    fields must no longer collapse a compound request. The full request_tasks list
    remains authoritative; this helper exposes a compatible summary only.
    """
    tasks = [item for item in (state.get("request_tasks") or []) if isinstance(item, dict)]
    if not tasks:
        return _infer_current_input_task(message)

    if len(tasks) == 1:
        task = tasks[0]
        task_type = str(task.get("task_type") or "general_qa")
        legacy_map = {
            "place_structure_clarification": "place_structure_clarification",
            "property_detail": "property_detail",
            "brand_detail": "brand_detail",
            "comparison": "comparison",
        }
        return {
            "input_task_type": legacy_map.get(task_type, "general"),
            "current_user_intent": str(task.get("goal") or state.get("request_understanding_summary") or "answer the current request"),
            "memory_resolution_strategy": (
                "resolve_only_task_references_from_memory" if task.get("needs_memory")
                else "current_message_first"
            ),
            "place_grouping_hint": (
                {
                    "customer_count_may_be_wrong": True,
                    "group_by": ["destination_id", "complex_id", "property_id", "area_alias"],
                    "same_destination_components_are_not_separate_places": True,
                    "brand_suffix_is_not_a_place": True,
                }
                if task_type == "place_structure_clarification" else {}
            ),
        }

    has_place_clarification = any(str(item.get("task_type")) == "place_structure_clarification" for item in tasks)
    return {
        "input_task_type": "multi_intent",
        "current_user_intent": str(state.get("request_understanding_summary") or " | ".join(str(item.get("goal") or "") for item in tasks)),
        "memory_resolution_strategy": "resolve_memory_per_task_then_preserve_all_tasks",
        "place_grouping_hint": (
            {
                "customer_count_may_be_wrong": True,
                "group_by": ["destination_id", "complex_id", "property_id", "area_alias"],
                "same_destination_components_are_not_separate_places": True,
                "brand_suffix_is_not_a_place": True,
            }
            if has_place_clarification else {}
        ),
    }


def _input_task_fields(input_task: dict[str, Any] | None) -> dict[str, Any]:
    input_task = input_task or {}
    return {
        "input_task_type": str(input_task.get("input_task_type") or "general"),
        "current_user_intent": str(input_task.get("current_user_intent") or "answer the current request"),
        "memory_resolution_strategy": str(input_task.get("memory_resolution_strategy") or "current_message_first"),
        "place_grouping_hint": dict(input_task.get("place_grouping_hint") or {}),
    }


def _page_context_destination(state: AgentState) -> dict[str, Any] | None:
    page_context = state.get("page_context") or {}
    if not isinstance(page_context, dict):
        return None
    destination_id = str(page_context.get("destination_id") or "").strip()
    if not destination_id:
        return None
    item = _catalog_destination(destination_id) or {"id": destination_id}
    item = dict(item)
    if page_context.get("destination_name"):
        item["name"] = str(page_context.get("destination_name"))
    item["source"] = "current_page_context"
    item["confirmed"] = True
    item["recency_rank"] = None
    return item


def _build_destination_candidates(
    state: AgentState,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build a closed destination set with explicit provenance.

    ``recent_destinations`` is user-owned focus. ``recent_discussed_destinations``
    is answer/retrieval/proposal memory for recall and follow-up only.  Both are
    exposed to the resolver, but their ``source`` values decide whether they may
    become hard filters or merely contextual references.
    """
    current_message = effective_user_message(state)
    explicit_raw = detect_destinations(current_message)

    candidates: list[dict[str, Any]] = []
    explicit: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_candidate(
        raw: dict[str, Any],
        *,
        source: str,
        recency_rank: int | None,
        confirmed: bool = False,
    ) -> dict[str, Any] | None:
        destination_id = str(raw.get("id") or "").strip()
        if not destination_id or destination_id in seen:
            return None
        item = _catalog_destination(destination_id) or dict(raw)
        item = dict(item)
        item["source"] = source
        item["recency_rank"] = recency_rank
        item["confirmed"] = bool(confirmed or source in _USER_FOCUS_DESTINATION_SOURCES)
        candidates.append(item)
        seen.add(destination_id)
        return item

    for raw in explicit_raw:
        item = append_candidate(
            raw,
            source="current_explicit",
            recency_rank=None,
            confirmed=True,
        )
        if item is not None:
            explicit.append(item)

    page_destination = _page_context_destination(state)
    if page_destination and (not explicit or _message_uses_page_context(current_message)):
        item = append_candidate(
            page_destination,
            source="current_page_context",
            recency_rank=None,
            confirmed=True,
        )
        if item is not None:
            explicit.append(item)

    for rank, raw in enumerate(state.get("recent_destinations", []) or [], start=1):
        raw_source = str(raw.get("source") or "recent_user_focus").strip()
        source = raw_source if raw_source in _USER_FOCUS_DESTINATION_SOURCES else "recent_user_focus"
        append_candidate(
            raw,
            source=source,
            recency_rank=rank,
            confirmed=True,
        )

    for rank, raw in enumerate(state.get("recent_discussed_destinations", []) or [], start=1):
        raw_source = str(raw.get("source") or "assistant_suggestion").strip()
        if raw_source in _USER_FOCUS_DESTINATION_SOURCES:
            source = raw_source
        elif raw_source in _ASSISTANT_PROPOSAL_DESTINATION_SOURCES:
            source = "recent_assistant_proposal"
        else:
            source = "recent_retrieval_evidence"
        append_candidate(
            raw,
            source=source,
            recency_rank=rank,
            confirmed=_truthy(raw.get("confirmed")) and source in _USER_FOCUS_DESTINATION_SOURCES,
        )

    return explicit, candidates


def _build_entity_candidates(state: AgentState) -> list[dict[str, Any]]:
    """Expose recent grounded entities using opaque refs, not product-name rules.

    The entity memory is populated from actual retrieved-document metadata. This
    lets packages, properties, attractions, services, promotions, FAQs and future
    entity types participate without adding one-off keyword keys to the resolver.
    """
    # One real-world entity may be indexed under several evidence tables (for
    # example the same resort as property, MICE venue and organisation highlight).
    # Memory must expose one discourse target, not three same-name choices for the
    # selector to accidentally select together.
    type_priority = {
        "property": 100,
        "booking_product": 95,
        "attraction": 90,
        "complex": 85,
        "dining_service": 80,
        "golf_course": 75,
        "mice_venue": 70,
    }
    best_by_name: dict[str, tuple[tuple[int, int, int, int], dict[str, Any]]] = {}
    for rank, raw in enumerate(state.get("recent_entities", []) or [], start=1):
        name = str(raw.get("name") or "").strip()
        entity_type = str(raw.get("type") or raw.get("entity_type") or "entity").strip() or "entity"
        if not name:
            continue
        normalized_name = normalize_text(name)
        if not normalized_name:
            continue
        source = str(raw.get("source") or "recent_grounded_focus")
        confirmed = _truthy(raw.get("confirmed")) or source in _USER_FOCUS_DESTINATION_SOURCES
        candidate = {
            "name": name,
            "type": entity_type,
            "source": source,
            "confirmed": confirmed,
            "recency_rank": rank,
        }
        destination_id = str(raw.get("destination_id") or "").strip()
        if destination_id:
            candidate["destination_id"] = destination_id
        score = (
            1 if confirmed else 0,
            1 if source in _USER_FOCUS_DESTINATION_SOURCES else 0,
            type_priority.get(entity_type.lower(), 0),
            -rank,
        )
        current = best_by_name.get(normalized_name)
        if current is None or score > current[0]:
            best_by_name[normalized_name] = (score, candidate)

    ordered = sorted(
        (item for _score, item in best_by_name.values()),
        key=lambda item: int(item.get("recency_rank") or 9999),
    )
    output: list[dict[str, Any]] = []
    for index, item in enumerate(ordered, start=1):
        copied = dict(item)
        copied["ref"] = f"entity:{index}"
        output.append(copied)
    return output


def _dedupe_selected_entities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse same-name evidence-table aliases after CLOSED ref selection."""
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items or []:
        key = normalize_text(item.get("name"))
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _compact_focus_turns(state: AgentState, limit: int = 8) -> list[dict[str, Any]]:
    """Return recent turns with user/proposal provenance for semantic reuse."""
    turns = list(state.get("conversation_turns", []) or [])[-limit:]
    output: list[dict[str, Any]] = []
    for turn in turns:
        focus_destinations: list[dict[str, Any]] = []
        seen_destinations: set[str] = set()

        def add_focus_destination(destination_id: str, *, source: str, confirmed: bool = False) -> None:
            destination_id = str(destination_id or "").strip()
            if not destination_id or destination_id in seen_destinations:
                return
            focus_destinations.append(
                {
                    "id": destination_id,
                    "source": source,
                    "confirmed": bool(confirmed or source in _USER_FOCUS_DESTINATION_SOURCES),
                }
            )
            seen_destinations.add(destination_id)

        for item in turn.get("resolved_destinations") or []:
            source = str(item.get("source") or "retrieval_evidence").strip()
            add_focus_destination(
                str(item.get("id") or ""),
                source=source,
                confirmed=_truthy(item.get("confirmed")),
            )
        for item in turn.get("detected_destinations") or []:
            add_focus_destination(
                str(item.get("id") or ""),
                source=str(item.get("source") or "retrieval_detection").strip(),
            )

        # Recovery for pre-v3 memory: invalid timing/quantity/etc. can prevent
        # normal context resolution, but a single explicitly named destination
        # remains a valid user-owned subject.  Never promote raw text from
        # safety/scope blocked or conversation-meta turns.
        route = str(turn.get("route") or "").strip()
        logic_action = str(turn.get("logic_action") or "").strip().lower()
        scope_action = str(turn.get("scope_action") or "allow").strip().lower()
        safety_action = str(turn.get("safety_action") or "allow").strip().lower()
        recover_logic_subject = (
            route == "invalid_request" or logic_action == "reject"
        ) and scope_action != "block" and safety_action != "block"
        if recover_logic_subject:
            safe_previous_request = str(
                turn.get("sanitized_user_request")
                or turn.get("user_message")
                or turn.get("rag_query")
                or ""
            )
            raw_explicit = detect_destinations(safe_previous_request)
            raw_ids = {str(item.get("id") or "").strip() for item in raw_explicit if str(item.get("id") or "").strip()}
            if len(raw_ids) == 1:
                add_focus_destination(
                    next(iter(raw_ids)),
                    source="user_explicit_logic_subject",
                    confirmed=True,
                )

        focus_entities = []
        for item in (turn.get("focus_entities") or [])[:12]:
            if not str(item.get("name") or "").strip():
                continue
            entity_source = str(item.get("source") or "grounded_answer").strip()
            compact_entity = {
                "name": str(item.get("name") or "")[:180],
                "type": str(item.get("type") or item.get("entity_type") or "entity")[:80],
                "source": entity_source[:80],
                "confirmed": _truthy(item.get("confirmed")) or entity_source in _USER_FOCUS_DESTINATION_SOURCES,
            }
            destination_id = str(item.get("destination_id") or "").strip()
            if destination_id:
                compact_entity["destination_id"] = destination_id[:120]
                if entity_source in _USER_FOCUS_DESTINATION_SOURCES:
                    dest_source = entity_source
                    confirmed = True
                elif entity_source in _ASSISTANT_PROPOSAL_DESTINATION_SOURCES:
                    dest_source = "assistant_suggestion"
                    confirmed = False
                else:
                    dest_source = "retrieval_evidence"
                    confirmed = False
                add_focus_destination(destination_id, source=dest_source, confirmed=confirmed)
            focus_entities.append(compact_entity)

        output.append(
            {
                "turn_ref": str(turn.get("memory_ref") or ""),
                "user_message": str(
                    turn.get("sanitized_user_request") or turn.get("rag_query") or ""
                )[:500],
                "assistant_answer_excerpt": str(turn.get("assistant_answer") or "")[:800],
                "rag_query": str(turn.get("rag_query") or "")[:700],
                "focus_destination_ids": [item["id"] for item in focus_destinations],
                "focus_destinations": focus_destinations,
                "focus_entities": focus_entities,
                "detected_intents": list(turn.get("detected_intents") or []),
                "request_tasks": list(turn.get("request_tasks") or []),
            }
        )
    return output


def _fallback_resolution(
    explicit: list[dict[str, Any]],
    rag_query: str,
    reason: str,
    *,
    request_kind: str = "independent",
    input_task: dict[str, Any] | None = None,
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
        "context_destination_provenance": [
            {
                "id": str(item.get("id") or ""),
                "name": _destination_name(item),
                "source": str(item.get("source") or "current_explicit"),
                "confirmed": str(bool(item.get("confirmed", True))).lower(),
            }
            for item in explicit
        ],
        "context_resolution_reason": reason,
        "context_resolution_confidence": 0.0,
        "context_resolution_source": "explicit_fallback" if explicit else "none",
        "rag_query": rag_query,
        **_input_task_fields(input_task),
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
    input_task: dict[str, Any] | None = None,
) -> AgentState:
    selected_destinations = _dedupe_destinations(selected_destinations)
    selected_entities = _dedupe_selected_entities(selected_entities)
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
        "context_destination_provenance": [
            {
                "id": str(item.get("id") or ""),
                "name": _destination_name(item),
                "source": str(item.get("source") or "unknown"),
                "confirmed": str(bool(item.get("confirmed", False))).lower(),
            }
            for item in selected_destinations
        ],
        "context_resolution_reason": reason[:500],
        "context_resolution_confidence": _bounded_confidence(confidence),
        "context_resolution_source": source,
        "rag_query": rag_query,
        **_input_task_fields(input_task),
    }


def _message_confirms_prior_option(message: str) -> bool:
    """Heuristic guard for turning an assistant proposal into user-confirmed focus."""
    text = normalize_text(message)
    if not text:
        return False
    reference_terms = (
        "cho do", "noi do", "goi do", "phuong an do", "lua chon do",
        "option do", "cai do", "chuyen do", "noi nay", "goi nay", "phuong an nay",
    )
    confirmation_terms = (
        "chon", "lay", "dat", "book", "quyet", "dong y", "ok", "duoc", "di",
    )
    return any(term in text for term in reference_terms) and any(term in text for term in confirmation_terms)


def _confirmed_selection_destinations(
    selected_destinations: list[dict[str, Any]],
    *,
    selection: dict[str, Any],
    current_message: str,
) -> list[dict[str, Any]]:
    """Promote selected assistant proposals only when the user confirms them."""
    model_confirms = bool(selection.get("user_confirms_selected_memory_destination", False))
    heuristic_confirms = _message_confirms_prior_option(current_message)
    if not (model_confirms or heuristic_confirms):
        return selected_destinations
    promoted: list[dict[str, Any]] = []
    for item in selected_destinations:
        copied = dict(item)
        if str(copied.get("source") or "") in _ASSISTANT_PROPOSAL_DESTINATION_SOURCES | {"recent_assistant_proposal"}:
            copied["source"] = "user_confirmed_via_memory"
            copied["confirmed"] = True
        promoted.append(copied)
    return promoted


def _single_confirmed_destination_from_selected_turns(
    selected_turn_refs: list[str],
    focus_turns: list[dict[str, Any]],
    destination_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recover one authoritative destination carried by selected prior turns.

    A continuation selector may correctly choose the prior turn that supplies an
    omitted subject while omitting the parallel destination ID.  If those selected
    turns point to exactly one *confirmed/user-owned* destination, materialize it as
    the factual continuation scope.  Assistant proposals/retrieval evidence are
    intentionally excluded so the discussed-memory stream can never silently
    become user focus.
    """
    selected = set(selected_turn_refs or [])
    ids: list[str] = []
    seen: set[str] = set()
    for turn in focus_turns or []:
        if str(turn.get("turn_ref") or "") not in selected:
            continue
        for item in turn.get("focus_destinations") or []:
            destination_id = str(item.get("id") or "").strip()
            source = str(item.get("source") or "").strip()
            confirmed = _truthy(item.get("confirmed")) or source in _USER_FOCUS_DESTINATION_SOURCES
            if not destination_id or not confirmed or destination_id in seen:
                continue
            seen.add(destination_id)
            ids.append(destination_id)
    if len(ids) != 1:
        return []
    destination_id = ids[0]
    item = destination_by_id.get(destination_id)
    if item is not None:
        return [item]
    catalog_item = _catalog_destination(destination_id)
    if not catalog_item:
        return []
    catalog_item = dict(catalog_item)
    catalog_item["source"] = "user_focus_from_selected_turn"
    catalog_item["confirmed"] = True
    return [catalog_item]



def _single_confirmed_user_focus_destination(
    memory_destination_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return one unambiguous user-owned destination from structured memory.

    This is a deterministic fail-safe for factual follow-ups when the CLOSED LLM
    selector emits malformed/unsupported refs.  It intentionally ignores assistant
    proposals and retrieval-only destinations: only a destination previously owned
    by the user may become the fallback hard scope.  If more than one user-focus
    destination is present, return nothing rather than guessing.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for item in memory_destination_candidates or []:
        destination_id = str(item.get("id") or "").strip()
        source = str(item.get("source") or "").strip()
        confirmed = _truthy(item.get("confirmed")) or source in _USER_FOCUS_DESTINATION_SOURCES
        if not destination_id or not confirmed or source not in _USER_FOCUS_DESTINATION_SOURCES:
            continue
        by_id.setdefault(destination_id, item)

    if len(by_id) != 1:
        return []

    item = dict(next(iter(by_id.values())))
    item["confirmed"] = True
    return [item]


def _fallback_scoped_rag_query(
    guarded_query: str,
    destinations: list[dict[str, Any]],
) -> str:
    """Attach only deterministic destination memory to a current-only query.

    The guarded query remains authoritative for the current task.  This helper adds
    the single recovered destination subject without asking another LLM to rewrite
    the request, preventing a failed memory selector from broadening a follow-up to
    the entire KB.
    """
    query = str(guarded_query or "").strip()
    names = [_destination_name(item) for item in destinations if _destination_name(item)]
    if not names:
        return query
    normalized_query = normalize_text(query)
    missing_names = [name for name in names if normalize_text(name) not in normalized_query]
    if not missing_names:
        return query
    suffix = ", ".join(missing_names)
    return f"{query} for {suffix}".strip() if query else suffix


_RELATIVE_AREA_REFERENCES = (
    "nhung khu do", "cac khu do", "may khu do", "nhung khu nay", "cac khu nay",
    "nhung khu vua noi", "cac khu vua noi", "those zones", "those areas",
    "these zones", "these areas", "the zones above", "the areas above",
)


def _is_relative_area_followup(message: str) -> bool:
    normalized = normalize_text(message)
    return any(marker in normalized for marker in _RELATIVE_AREA_REFERENCES)


def _repair_relative_area_selection(
    *,
    message: str,
    selected_entities: list[dict[str, Any]],
    selected_turn_refs: list[str],
    focus_turns: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """Bind plural ``those zones/areas`` to the immediately preceding answer."""
    if not _is_relative_area_followup(message) or not focus_turns:
        return selected_entities, selected_turn_refs, False
    latest_turn = focus_turns[-1]
    latest_ref = str(latest_turn.get("turn_ref") or "").strip()
    answer_text = normalize_text(latest_turn.get("assistant_answer_excerpt") or "")
    kept_entities: list[dict[str, Any]] = []
    if answer_text:
        for item in selected_entities:
            entity_name = normalize_text(item.get("name") or "")
            entity_type = normalize_text(item.get("type") or "")
            if entity_name and entity_name in answer_text and entity_type not in {"property", "room", "mice venue"}:
                kept_entities.append(item)
    repaired_turn_refs = [latest_ref] if latest_ref else selected_turn_refs
    return kept_entities, repaired_turn_refs, (
        kept_entities != selected_entities or repaired_turn_refs != selected_turn_refs
    )


def _relative_area_rag_query(destinations: list[dict[str, Any]]) -> str:
    names = [_destination_name(item) for item in destinations if _destination_name(item)]
    base = (
        "VinWonders admission ticket prices and whether the entertainment zones "
        "mentioned in the immediately preceding answer are separately priced or included in admission"
    )
    return f"{base} for {', '.join(names)}" if names else base

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
    input_task = _input_task_from_request_plan(state, current_message)
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
            input_task=input_task,
        )

    prior_destination_candidates = [
        item for item in destination_candidates if item.get("source") != "current_explicit"
    ]
    has_memory = bool(prior_destination_candidates or entity_candidates or focus_turns)
    if not has_memory:
        request_kind = "conversation_meta" if route == "conversation_context" else "independent"
        return {
            **_fallback_resolution(
                explicit,
                guarded_query,
                "No prior structured memory is available; only current explicit context was used.",
                request_kind=request_kind,
                input_task=input_task,
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
    memory_destination_candidates = prior_destination_candidates
    memory_destination_payload = [
        {
            "id": item.get("id"),
            "name": _destination_name(item),
            "recency_rank": item.get("recency_rank"),
            "source": item.get("source"),
            "confirmed": _truthy(item.get("confirmed")),
            "memory_role": (
                "user_focus" if item.get("source") in _USER_FOCUS_DESTINATION_SOURCES
                else "assistant_proposal" if item.get("source") in _ASSISTANT_PROPOSAL_DESTINATION_SOURCES | {"recent_assistant_proposal"}
                else "retrieval_evidence"
            ),
        }
        for item in memory_destination_candidates
    ]

    llm = LLMService()

    # Stage 1: decide if memory is required. Do NOT allow this call to select old
    # entities/turns, which keeps stale memory out of independent requests by design.
    dependency_prompt = (
        "You are the memory-dependency gate for a Vinpearl/VinWonders assistant. "
        "Decide whether the CURRENT request actually requires prior conversation. Same session or topic similarity is NOT enough. "
        "Prior destinations/entities include a provenance role: user_focus means the user chose/named it; assistant_proposal means the assistant previously suggested or mentioned it; retrieval_evidence is only a KB/search hit. "
        "Classify request_kind as exactly one of independent, factual_continuation, conversation_meta. "
        "independent: the current message plus any entities/destinations explicitly named IN THAT MESSAGE are sufficient to understand "
        "what new factual request to retrieve. Do not use memory merely because a previous destination/entity is related. "
        "factual_continuation: prior context is materially required to resolve an omitted subject/pronoun, 'this/that/it/there', ordinal, "
        "comparison, correction, clarification, 'another/additional/different' option, exclusion of a previous recommendation, or an equivalent "
        "discourse relation, or a request to reuse/adjust/recalculate information already provided. If the same request could be answered correctly without knowing prior turns, it is independent. "
        "conversation_meta: the requested output itself is about the stored conversation and no new KB fact is requested, for example recap/repeat what was said. "
        "The field current_input_task is system-derived from the raw current message. If it is place_structure_clarification, the customer may be asking because a prior answer/UI made one property/area look like multiple places; classify it as factual_continuation when prior context is available, and do NOT turn the user's assumed count into a requirement to compare two places. "
        "\n\nAlso bind destinations explicitly present in the CURRENT message only. Put each explicit destination in either "
        "current_target_destination_ids or current_excluded_destination_ids. A destination named as the desired/new target is a target. "
        "A destination named only as wrong, negated, replaced, or explicitly excluded is an exclusion. Never use a memory destination in these "
        "two current_* fields. If a current destination is positively named, it must never disappear merely because old memory exists. "
        "Never treat an assistant_proposal or retrieval_evidence destination as a user-confirmed choice in this gate. "
        "REFERENCE INTEGRITY IS STRICT: current_target_destination_ids and current_excluded_destination_ids may contain ONLY exact IDs copied from current_explicit_destinations. If the current message contains no explicit destination for a field, return an empty array. Never output placeholders or guessed IDs. "
        "Return JSON only."
    )
    dependency_payload = {
        "current_route_hint": route,
        "current_message": current_message,
        "current_input_task": input_task,
        "request_task_plan": state.get("request_tasks") or [],
        "guarded_current_only_rag_query": guarded_query,
        "current_explicit_destinations": current_explicit_payload,
        "available_prior_destination_focus": [item for item in memory_destination_payload if item.get("memory_role") == "user_focus"],
        "available_prior_discussed_destinations": memory_destination_payload,
        "available_prior_entities": entity_candidates,
        "recent_structured_focus_turns": focus_turns,
    }
    dependency_schema = '''{
  "request_kind": "independent|factual_continuation|conversation_meta",
  "needs_memory": false,
  "current_target_destination_ids": [],
  "current_excluded_destination_ids": [],
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
            input_task=input_task,
        )

    request_kind = str(dependency.get("request_kind") or "").strip().lower()
    if request_kind not in {"independent", "factual_continuation", "conversation_meta"}:
        request_kind = "conversation_meta" if route == "conversation_context" else "independent"

    current_targets, current_exclusions, current_binding_invalid = _parse_current_destination_bindings(
        dependency,
        explicit,
    )
    if current_binding_invalid:
        fatal_binding_errors = [
            item for item in current_binding_invalid
            if str(item).startswith("malformed:") or str(item).startswith("overlap:")
        ]
        if fatal_binding_errors:
            # Structural/contradictory binding output cannot be interpreted safely.
            return _fallback_resolution(
                explicit,
                guarded_query,
                "Memory dependency gate returned malformed/contradictory current destination bindings; memory disabled safely.",
                request_kind="independent",
                input_task=input_task,
            )
        # Unsupported IDs are already rejected by the CLOSED parser. Keeping valid
        # current bindings prevents a single hallucinated placeholder from erasing
        # otherwise sound continuation memory.
        print(
            "[CONTEXT RESOLUTION] ignored unsupported current destination bindings: "
            f"{current_binding_invalid}"
        )

    dependency_reason = str(
        dependency.get("reason") or "Memory dependency gate completed."
    ).strip()[:500]
    dependency_confidence = _bounded_confidence(dependency.get("confidence"))
    declared_needs_memory = bool(dependency.get("needs_memory", False))

    if (
        request_kind != "conversation_meta"
        and bool(state.get("request_requires_memory"))
        and has_memory
    ):
        request_kind = "factual_continuation"
        declared_needs_memory = True
        dependency_reason = (
            "At least one atomic task in the current factual request explicitly requires prior conversation; "
            "resolve only the references needed by those tasks while preserving every other current task."
        )

    if input_task.get("input_task_type") == "place_structure_clarification" and has_memory:
        # Customer wording such as "có 2 nơi hả?" is usually an assumption to be
        # checked against the previous answer, not a standalone comparison request.
        request_kind = "factual_continuation"
        declared_needs_memory = True
        dependency_reason = (
            "Current turn asks to clarify the structure/count of items mentioned earlier; "
            "use memory to group prior entities instead of assuming there are multiple places."
        )

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
            input_task=input_task,
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
            input_task=input_task,
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
        "selected_memory_destination_ids/entities are positive prior targets the current request is still about. A selected prior destination may be user_focus or assistant_proposal; preserve that distinction. For near-deictic plural references such as 'những khu đó/các khu đó/those zones', the immediately preceding turn is authoritative: do not substitute older hotels or properties merely because they share the destination. excluded_memory_* are prior "
        "recommendations/entities that must not be returned (for example 'another option'). Select a prior turn only when its grounded retrieval "
        "focus materially supplies the omitted relation/subject; recency alone is not enough. Never invent refs. If current_input_task is place_structure_clarification, select the most recent turn/entities that caused the customer's confusion and write the rag_query to clarify whether they are one place with multiple components/names, not to review room types unless rooms were explicitly requested. If several assistant_proposal destinations were offered and the current request does not identify one, prefer selecting the prior turn and/or all relevant entities over guessing one destination. Old assistant prose is not fresh "
        "factual evidence. REQUEST_TASK_PLAN is authoritative for customer-visible coverage: preserve EVERY atomic task in the standalone rag_query, in order when practical; never drop a later clause just because an earlier clause resolved the reference. "
        "Return a standalone faithful English rag_query that combines the CURRENT request with only the selected memory meaning, preserving all task goals, constraints, comparisons, corrections, exclusions, quantities, dates, and requested relations. Current explicit targets/exclusions "
        "are authoritative and must not be replaced by stale memory. Set user_confirms_selected_memory_destination=true only when the CURRENT message clearly accepts/chooses a prior assistant proposal (for example 'chọn phương án đó', 'đi chỗ đó', 'book gói đó'). "
        "REFERENCE INTEGRITY IS STRICT: every destination ID, entity ref, and turn ref in your output MUST be copied verbatim from the corresponding candidate list in UNTRUSTED_CONTEXT_JSON. Never output schema examples, placeholders, guessed refs, or IDs that are not present. If no exact ref is needed, return an empty array for that field. Return JSON only."
    )
    selector_payload = {
        "current_message": current_message,
        "current_input_task": input_task,
        "request_task_plan": state.get("request_tasks") or [],
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
  "selected_memory_destination_ids": [],
  "selected_memory_entity_refs": [],
  "selected_turn_refs": [],
  "excluded_memory_destination_ids": [],
  "excluded_memory_entity_refs": [],
  "user_confirms_selected_memory_destination": false,
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
        recovered_user_focus = (
            _single_confirmed_user_focus_destination(memory_destination_candidates)
            if not current_targets else []
        )
        if recovered_user_focus:
            result = _resolution_result(
                explicit=explicit,
                selected_destinations=recovered_user_focus,
                selected_entities=[],
                selected_turn_refs=[],
                excluded_destinations=current_exclusions,
                excluded_entities=[],
                uses_memory=True,
                request_kind="factual_continuation",
                reason=(
                    "Memory selector call failed; recovered the single confirmed user-focus destination "
                    f"deterministically to preserve continuation scope: {exc}"
                ),
                confidence=min(dependency_confidence if dependency_confidence > 0 else 0.95, 0.95),
                source="memory",
                rag_query=_fallback_scoped_rag_query(guarded_query, recovered_user_focus),
                input_task=input_task,
            )
            _print_resolution(current_message, destination_candidates, entity_candidates, result)
            return result

        result = _resolution_result(
            explicit=explicit,
            selected_destinations=current_targets,
            selected_entities=[],
            selected_turn_refs=[],
            excluded_destinations=current_exclusions,
            excluded_entities=[],
            uses_memory=False,
            request_kind="independent",
            reason=f"Memory selection failed and no unambiguous confirmed user-focus fallback exists: {exc}",
            confidence=0.0,
            source="current_explicit" if current_targets else "none",
            rag_query=guarded_query,
            input_task=input_task,
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

    (
        selected_memory_entities,
        selected_turn_refs,
        relative_area_selection_repaired,
    ) = _repair_relative_area_selection(
        message=current_message,
        selected_entities=selected_memory_entities,
        selected_turn_refs=selected_turn_refs,
        focus_turns=focus_turns,
    )

    selector_had_invalid_refs = bool(invalid_refs)
    if selector_had_invalid_refs:
        # Invalid model refs are rejected individually, but valid CLOSED refs must
        # survive.  Discarding the entire memory selection here used to erase a
        # confirmed destination (e.g. Phu Quoc) and broaden short follow-ups such as
        # "chi phí ra sao" to the whole KB.
        print(f"[CONTEXT RESOLUTION] ignored unsupported memory refs: {invalid_refs}")

    valid_memory_refs_used = _memory_refs_used(
        selected_memory_destinations,
        selected_memory_entities,
        selected_turn_refs,
        excluded_memory_destinations,
        excluded_memory_entities,
    )

    deterministic_fallback_used = False
    if not valid_memory_refs_used and not current_targets:
        # Stage 1/planner has already proven this turn needs prior context. If the
        # Stage-2 selector fails to provide a usable ref, recover ONLY an
        # unambiguous confirmed user-focus destination. Never guess among multiple
        # destinations and never promote assistant proposals/retrieval evidence.
        recovered_user_focus = _single_confirmed_user_focus_destination(
            memory_destination_candidates
        )
        if recovered_user_focus:
            selected_memory_destinations = recovered_user_focus
            deterministic_fallback_used = True

    selected_memory_destinations = _confirmed_selection_destinations(
        selected_memory_destinations,
        selection=selection,
        current_message=current_message,
    )

    if not selected_memory_destinations and selected_turn_refs and not current_targets:
        recovered_from_turn = _single_confirmed_destination_from_selected_turns(
            selected_turn_refs,
            focus_turns,
            memory_destination_by_id,
        )
        if recovered_from_turn:
            selected_memory_destinations = recovered_from_turn

    uses_memory = _memory_refs_used(
        selected_memory_destinations,
        selected_memory_entities,
        selected_turn_refs,
        excluded_memory_destinations,
        excluded_memory_entities,
    )
    if not uses_memory:
        # If the current message already has an explicit target, it can safely stand
        # alone when Stage 2 selects nothing. Without a current target we still fail
        # closed rather than guessing among ambiguous prior subjects.
        result = _resolution_result(
            explicit=explicit,
            selected_destinations=current_targets,
            selected_entities=[],
            selected_turn_refs=[],
            excluded_destinations=current_exclusions,
            excluded_entities=[],
            uses_memory=False,
            request_kind="independent",
            reason=(
                "Continuation gate found no usable memory ref and no unambiguous confirmed user-focus fallback; "
                "current request treated as independent without importing stale memory."
            ),
            confidence=_bounded_confidence(selection.get("confidence")),
            source="current_explicit" if current_targets else "none",
            rag_query=guarded_query,
            input_task=input_task,
        )
        _print_resolution(current_message, destination_candidates, entity_candidates, result)
        return result

    if _is_relative_area_followup(current_message):
        resolved_query = _relative_area_rag_query(current_targets + selected_memory_destinations)
    elif deterministic_fallback_used:
        resolved_query = _fallback_scoped_rag_query(
            guarded_query,
            selected_memory_destinations,
        )
    else:
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
    if deterministic_fallback_used:
        selection_reason = (
            "Memory selector produced no usable closed ref; recovered the single confirmed user-focus destination "
            "deterministically to preserve factual follow-up scope."
        )
        confidence = min(confidence, 0.95)
    elif relative_area_selection_repaired:
        selection_reason = (
            "Near-deictic area reference was bound to the immediately preceding turn; "
            "stale entities not present in that answer were removed."
        )
        confidence = min(confidence, 0.95)
    elif selector_had_invalid_refs:
        selection_reason = (
            f"{selection_reason} Unsupported refs were ignored individually: {invalid_refs}."
        )[:500]
        confidence = min(confidence, 0.90)

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
        input_task=input_task,
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
    print(f"Input task: {result.get('input_task_type', 'general')}")
    print(f"Current intent: {result.get('current_user_intent', '')}")
    print(f"Request tasks: {[(item.get('task_id'), item.get('task_type')) for item in (result.get('request_tasks') or [])] if result.get('request_tasks') else 'see state planner'}")
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
