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
    recent_destinations = memory.extract_recent_destinations(turns)
    return {
        "conversation_turns": turns,
        "conversation_history": memory.format_for_prompt(turns),
        "recent_destinations": recent_destinations,
        "recent_destination_summary": memory.format_destination_summary(recent_destinations),
    }


def save_conversation_memory(state: AgentState) -> AgentState:
    MemoryService().append_turn(
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
        user_message=state.get("user_message", ""),
        assistant_answer=state.get("answer", ""),
        language=state.get("original_language", "unknown"),
        route=state.get("route", "unknown"),
        rag_query=state.get("rag_query"),
        ticket_id=state.get("ticket_id"),
        detected_destinations=state.get("detected_destinations", []),
        detected_intent=state.get("detected_intent"),
        detected_intents=state.get("detected_intents", []),
        request_mode=state.get("request_mode"),
        resolution_mode=state.get("resolution_mode"),
    )
    return {}
