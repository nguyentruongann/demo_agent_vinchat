from typing import Any, Literal, TypedDict


RouteName = Literal["greeting", "out_of_scope", "conversation_context", "rag"]
InsufficiencyAction = Literal["no_data", "ticket"]
RequestMode = Literal["information", "support_action"]
ResolutionMode = Literal["information_only", "self_serve", "human_required"]
SafetyAction = Literal["allow", "block"]
ScopeAction = Literal["allow", "block"]


class AgentState(TypedDict, total=False):
    user_message: str
    session_id: str | None
    user_id: str | None

    conversation_turns: list[dict[str, Any]]
    conversation_history: str
    recent_destinations: list[dict[str, str]]
    recent_destination_summary: str

    original_language: str
    original_language_name: str
    rag_query: str
    route: RouteName

    # Semantic safety guard. This is intentionally model-classified rather than
    # keyword-matched so paraphrases, euphemisms and multilingual requests are
    # handled consistently.
    safety_action: SafetyAction
    safety_category: str
    safety_reason: str
    safety_confidence: float

    # Authoritative semantic scope + prompt-injection guard. Downstream nodes
    # consume sanitized_user_request instead of the raw user_message.
    scope_action: ScopeAction
    scope_reason: str
    scope_confidence: float
    prompt_injection_detected: bool
    prompt_injection_reason: str
    sanitized_user_request: str
    guardrail_reason: str
    guardrail_confidence: float

    retrieved_documents: list[dict[str, Any]]
    context: str

    # Hybrid retrieval diagnostics.
    retrieval_mode: str
    detected_destination: str | None
    detected_destination_name: str | None
    detected_destinations: list[dict[str, Any]]
    detected_destination_ids: list[str]
    detected_destination_names: list[str]
    detected_intent: str | None          # backward-compatible primary intent
    detected_intents: list[str]          # all intents in the current turn
    intent_results: dict[str, dict[str, Any]]
    keyword_candidate_count: int
    missing_destination_ids: list[str]

    enough_information: bool
    assessment_reason: str
    best_relevance_score: float
    insufficiency_action: InsufficiencyAction

    # Support triage: semantic intent for escalation, independent of topic keywords.
    request_mode: RequestMode
    resolution_mode: ResolutionMode
    support_triage_reason: str
    support_triage_confidence: float

    answer: str

    # Post-generation grounding diagnostics.
    grounding_passed: bool
    grounding_reason: str
    unsupported_claims: list[str]

    ticket_id: str | None
