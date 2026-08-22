from src.backend.agents.state import AgentState
from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.services.memory import MemoryService
from src.backend.services.query_parser import detect_destinations


def load_conversation_memory(state: AgentState) -> AgentState:
    memory = MemoryService()
    # Create app.session before the graph continues so ticket creation on the
    # first turn can keep a valid session_id foreign key.
    memory.ensure_session(
        state.get("session_id"),
        state.get("user_id"),
        channel="web",
    )
    turns = memory.load_recent(
        state.get("session_id"),
        user_id=state.get("user_id"),
    )
    for index, turn in enumerate(turns):
        turn["memory_ref"] = f"turn:{index + 1}"

    recent_destinations = memory.extract_recent_destinations(turns)
    recent_discussed_destinations = memory.extract_recent_discussed_destinations(turns)
    recent_entities = memory.extract_recent_entities(turns)

    # Keep this log concise but explicit: it makes reference-resolution bugs
    # visible before retrieval. Most importantly, assistant-only destination
    # mentions should never suddenly appear in Recent focus.
    print("\n===== CONVERSATION MEMORY =====")
    print(f"Session: {state.get('session_id')}")
    print(f"Loaded turns: {len(turns)}")
    print(f"Recent user-focus destinations: {[item.get('id') for item in recent_destinations]}")
    print(f"User-focus summary: {memory.format_destination_summary(recent_destinations)}")
    print(f"Recent discussed destinations: {[item.get('id') for item in recent_discussed_destinations]}")
    print(f"Discussed summary: {memory.format_destination_summary(recent_discussed_destinations)}")
    print(f"Recent entities: {[item.get('name') for item in recent_entities]}")
    print(f"Entity summary: {memory.format_entity_summary(recent_entities)}")
    print("===============================\n")

    return {
        "conversation_turns": turns,
        "conversation_history": memory.format_for_prompt(turns),
        "recent_destinations": recent_destinations,
        "recent_destination_summary": memory.format_destination_summary(recent_destinations),
        "recent_discussed_destinations": recent_discussed_destinations,
        "recent_discussed_destination_summary": memory.format_destination_summary(recent_discussed_destinations),
        "recent_entities": recent_entities,
        "recent_entity_summary": memory.format_entity_summary(recent_entities),
    }


def _logic_reject_subject_destinations(state: AgentState) -> list[dict]:
    """Preserve a safe, explicit destination even when another constraint is invalid.

    The guardrail can reject a turn such as "Phú Quốc, 2 days 3 nights" for
    impossible timing before the normal resolver runs.  That must not erase the
    valid user-owned subject from memory.  This recovery is deliberately narrow:
    only safety/scope-allowed, non-injection turns with exactly one canonical
    destination are promoted.  Ambiguous multi-destination rejected turns remain
    unpromoted rather than guessing target/exclusion semantics.
    """
    if str(state.get("logic_action") or "").strip().lower() != "reject":
        return []
    if str(state.get("scope_action") or "allow").strip().lower() == "block":
        return []
    if str(state.get("safety_action") or "allow").strip().lower() == "block":
        return []
    if bool(state.get("prompt_injection_detected", False)):
        return []

    matches = detect_destinations(effective_user_message(state))
    unique: dict[str, dict] = {}
    for raw in matches or []:
        destination_id = str(raw.get("id") or "").strip()
        if destination_id and destination_id not in unique:
            unique[destination_id] = raw
    if len(unique) != 1:
        return []

    raw = next(iter(unique.values()))
    return [{
        "id": str(raw.get("id") or "").strip(),
        "name": str(raw.get("name") or raw.get("name_vi") or raw.get("name_en") or raw.get("id") or "").strip(),
        "source": "user_explicit_logic_subject",
        "confirmed": True,
    }]


def save_conversation_memory(state: AgentState) -> AgentState:
    # Never persist a blocked/sensitive turn as a RAG turn. Otherwise the raw
    # adversarial message could later be mined as trusted destination memory.
    persisted_route = state.get("route", "unknown")
    if state.get("safety_action") == "block" or state.get("scope_action") == "block":
        persisted_route = "out_of_scope"

    memory = MemoryService()
    focus_entities = memory.derive_focus_entities(state)

    detected_destinations = list(state.get("detected_destinations", []) or [])
    resolved_destinations = list(state.get("resolved_destinations", []) or [])
    recovered_logic_subjects = _logic_reject_subject_destinations(state)
    if recovered_logic_subjects:
        existing_detected = {str(item.get("id") or "") for item in detected_destinations}
        existing_resolved = {str(item.get("id") or "") for item in resolved_destinations}
        for item in recovered_logic_subjects:
            if item["id"] not in existing_detected:
                detected_destinations.append(dict(item))
            if item["id"] not in existing_resolved:
                resolved_destinations.append(dict(item))
        print(
            "[MEMORY] preserved valid subject from logic-rejected turn: "
            f"{[item['id'] for item in recovered_logic_subjects]}"
        )

    memory.append_turn(
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
        user_message=state.get("user_message", ""),
        sanitized_user_request=effective_user_message(state),
        assistant_answer=state.get("answer", ""),
        language=state.get("original_language", "unknown"),
        route=persisted_route,
        rag_query=state.get("rag_query"),
        ticket_id=state.get("ticket_id"),
        detected_destinations=detected_destinations,
        resolved_destinations=resolved_destinations,
        focus_entities=focus_entities,
        context_uses_memory=bool(state.get("context_uses_memory", False)),
        context_resolution_reason=state.get("context_resolution_reason"),
        context_resolution_confidence=state.get("context_resolution_confidence"),
        context_resolution_source=state.get("context_resolution_source"),
        detected_intent=state.get("detected_intent"),
        detected_intents=state.get("detected_intents", []),
        request_tasks=state.get("request_tasks", []),
        request_mode=state.get("request_mode"),
        resolution_mode=state.get("resolution_mode"),
        logic_action=state.get("logic_action"),
        logic_category=state.get("logic_category"),
        scope_action=state.get("scope_action"),
        safety_action=state.get("safety_action"),
    )
    return {}
