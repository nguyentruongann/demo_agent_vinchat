from langgraph.graph import END, START, StateGraph

from src.backend.agents.nodes.answer import generate_answer
from src.backend.agents.nodes.classify import classify_input
from src.backend.agents.nodes.language import detect_language_and_translate
from src.backend.agents.nodes.guardrail import enforce_input_guardrail
from src.backend.agents.nodes.language_guard import enforce_response_language
from src.backend.agents.nodes.grounding import validate_grounding
from src.backend.agents.nodes.memory import (
    load_conversation_memory,
    save_conversation_memory,
)
from src.backend.agents.nodes.retrieval import assess_information, retrieve_context
from src.backend.agents.nodes.support_triage import analyze_support_request
from src.backend.agents.nodes.static_responses import (
    conversation_context_response,
    greeting_response,
    no_data_response,
    out_of_scope_response,
    sensitive_content_response,
)
from src.backend.agents.nodes.ticket import create_ticket
from src.backend.agents.state import AgentState


def route_after_classification(state: AgentState) -> str:
    return state["route"]


def route_after_safety(state: AgentState) -> str:
    """Backward-compatible helper for tests/callers using the old safety split."""
    return "sensitive" if state.get("safety_action") == "block" else "classify"


def route_after_guardrail(state: AgentState) -> str:
    """Authoritative fail-closed routing before classification/retrieval."""
    if state.get("safety_action") == "block":
        return "sensitive"
    if state.get("scope_action") != "allow":
        return "out_of_scope"
    return "classify"


def route_after_support_triage(state: AgentState) -> str:
    # Once triage establishes that a personal record/action is required, evidence
    # sufficiency cannot change the routing decision. Skip the assessment node.
    if state.get("resolution_mode") == "human_required":
        return "ticket"
    return "assess"


def route_after_assessment(state: AgentState) -> str:
    # A case-specific operational request needs a human even when RAG contains
    # general policy/guidance. The chatbot cannot inspect or mutate personal records.
    if state.get("resolution_mode") == "human_required":
        return "ticket"
    if state.get("enough_information"):
        return "answer"
    return state.get("insufficiency_action", "ticket")


def route_after_answer(state: AgentState) -> str:
    """Fail closed when generation produced only an intro/empty body."""
    if state.get("answer_substantive") is False:
        return "no_data"
    return "grounding"


builder = StateGraph(AgentState)

builder.add_node("load_memory", load_conversation_memory)
builder.add_node("language", detect_language_and_translate)
builder.add_node("guardrail", enforce_input_guardrail)
builder.add_node("classify", classify_input)
builder.add_node("sensitive", sensitive_content_response)
builder.add_node("conversation_context", conversation_context_response)
builder.add_node("greeting", greeting_response)
builder.add_node("out_of_scope", out_of_scope_response)
builder.add_node("retrieve", retrieve_context)
builder.add_node("support_triage", analyze_support_request)
builder.add_node("assess", assess_information)
builder.add_node("answer", generate_answer)
builder.add_node("grounding", validate_grounding)
builder.add_node("language_guard", enforce_response_language)
builder.add_node("no_data", no_data_response)
builder.add_node("ticket", create_ticket)
builder.add_node("save_memory", save_conversation_memory)

builder.add_edge(START, "load_memory")
builder.add_edge("load_memory", "guardrail")
builder.add_conditional_edges(
    "guardrail",
    route_after_guardrail,
    {
        "sensitive": "sensitive",
        "out_of_scope": "out_of_scope",
        "classify": "language",
    },
)
builder.add_conditional_edges(
    "language",
    route_after_safety,
    {
        "sensitive": "sensitive",
        "classify": "classify",
    },
)

builder.add_conditional_edges(
    "classify",
    route_after_classification,
    {
        "greeting": "greeting",
        "out_of_scope": "out_of_scope",
        "conversation_context": "conversation_context",
        "rag": "retrieve",
    },
)

builder.add_edge("retrieve", "support_triage")
builder.add_conditional_edges(
    "support_triage",
    route_after_support_triage,
    {
        "assess": "assess",
        "ticket": "ticket",
    },
)
builder.add_conditional_edges(
    "assess",
    route_after_assessment,
    {
        "answer": "answer",
        "no_data": "no_data",
        "ticket": "ticket",
    },
)

builder.add_edge("conversation_context", "language_guard")
builder.add_edge("greeting", "language_guard")
builder.add_edge("out_of_scope", "language_guard")
builder.add_edge("sensitive", "language_guard")
builder.add_conditional_edges(
    "answer",
    route_after_answer,
    {
        "grounding": "grounding",
        "no_data": "no_data",
    },
)
builder.add_edge("grounding", "language_guard")
builder.add_edge("no_data", "language_guard")
builder.add_edge("ticket", "language_guard")
builder.add_edge("language_guard", "save_memory")
builder.add_edge("save_memory", END)

agent_graph = builder.compile()
