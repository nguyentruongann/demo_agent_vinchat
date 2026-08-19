from src.backend.agents.state import AgentState
from src.backend.services.memory import MemoryService


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


def save_conversation_memory(state: AgentState) -> AgentState:
    # Never persist a blocked/sensitive turn as a RAG turn. Otherwise the raw
    # adversarial message could later be mined as trusted destination memory.
    persisted_route = state.get("route", "unknown")
    if state.get("safety_action") == "block" or state.get("scope_action") == "block":
        persisted_route = "out_of_scope"

    memory = MemoryService()
    focus_entities = memory.derive_focus_entities(state)
    memory.append_turn(
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
        user_message=state.get("user_message", ""),
        assistant_answer=state.get("answer", ""),
        language=state.get("original_language", "unknown"),
        route=persisted_route,
        rag_query=state.get("rag_query"),
        ticket_id=state.get("ticket_id"),
        detected_destinations=state.get("detected_destinations", []),
        resolved_destinations=state.get("resolved_destinations", []),
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
    )
    return {}
