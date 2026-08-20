from typing import Any, Literal, TypedDict


RouteName = Literal[
    "greeting",
    "out_of_scope",
    "conversation_context",
    "rag",
    "invalid_request",
]
InsufficiencyAction = Literal["no_data", "ticket"]
RequestMode = Literal["information", "support_action"]
ResolutionMode = Literal["information_only", "self_serve", "human_required"]
SafetyAction = Literal["allow", "block"]
ScopeAction = Literal["allow", "block"]


class AgentState(TypedDict, total=False):
    user_message: str
    session_id: str | None
    user_id: str | None
    page_context: dict[str, Any] | None  # optional frontend page/location context for deictic "here/this" requests

    conversation_turns: list[dict[str, Any]]
    conversation_history: str
    recent_destinations: list[dict[str, str]]
    recent_destination_summary: str
    recent_discussed_destinations: list[dict[str, str]]
    recent_discussed_destination_summary: str
    recent_entities: list[dict[str, str]]
    recent_entity_summary: str

    # Semantic reference resolution. These fields describe the destination focus
    # of the CURRENT user request before retrieval runs. They are deliberately
    # separate from ``detected_*`` below, which are retrieval diagnostics.
    explicit_destinations: list[dict[str, Any]]
    resolved_destinations: list[dict[str, Any]]
    resolved_destination_ids: list[str]
    resolved_destination_names: list[str]
    resolved_entities: list[dict[str, Any]]
    resolved_entity_names: list[str]
    selected_memory_turn_refs: list[str]
    context_uses_memory: bool
    context_resolution_reason: str
    context_resolution_confidence: float
    context_resolution_source: str
    context_request_kind: str  # independent|factual_continuation|conversation_meta
    # Current-turn semantic intent identified after raw guardrail pass and before retrieval.
    # These fields help downstream nodes distinguish a customer's actual task from
    # wording assumptions/errors such as "there are two places, right?".
    input_task_type: str  # property_detail|place_structure_clarification|brand_detail|comparison|general
    current_user_intent: str
    memory_resolution_strategy: str
    place_grouping_hint: dict[str, Any]

    # Current-request task plan. A single user turn may contain any number of
    # customer-visible clauses; each clause becomes an atomic task that must be
    # resolved/answered rather than being collapsed into one primary intent.
    request_tasks: list[dict[str, Any]]
    request_task_count: int
    request_requires_memory: bool
    request_understanding_summary: str
    request_understanding_confidence: float
    request_understanding_source: str
    exhaustive_catalog_requested: bool
    exhaustive_catalog_complete: bool
    exhaustive_catalog_count: int
    exhaustive_catalog_scope: dict[str, Any]
    exhaustive_catalog_packet: dict[str, Any]
    context_destination_provenance: list[dict[str, str]]
    excluded_destination_ids: list[str]
    excluded_entity_names: list[str]

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
    supported_destination_discovery_ids: list[str]

    # Semantic/logical coherence gate. Unlike safety/scope, this rejects requests
    # whose own constraints cannot reasonably be true at the same time (for
    # example a 2-day trip containing 4 overnight stays). The input LLM owns this
    # classification so it can generalize beyond hard-coded examples.
    logic_action: Literal["allow", "reject"]
    logic_category: str
    logic_reason: str
    logic_confidence: float
    logic_response: str

    retrieved_documents: list[dict[str, Any]]
    context: str
    context_document_count: int
    context_branch_counts: dict[str, int]
    context_intents: list[str]
    context_entity_keys: list[str]

    # Generic semantic exhaustive-retrieval contract. This is separate from the
    # specialised structured booking-price catalog below and applies to any typed
    # destination intent (hotel/service/attraction/dining/...).
    exhaustive_retrieval_requested: bool
    exhaustive_retrieval_complete: bool
    exhaustive_retrieval_packet: dict[str, Any]

    # Hybrid retrieval diagnostics.
    retrieval_mode: str
    detected_destination: str | None
    detected_destination_name: str | None
    detected_destinations: list[dict[str, Any]]
    detected_destination_ids: list[str]
    detected_destination_names: list[str]
    detected_intent: str | None          # backward-compatible primary intent
    detected_intents: list[str]          # all intents in the current turn
    explicit_intents: list[str]          # intent words grounded in current user wording
    constraint_derived_intents: list[str]  # deterministic evidence branches added from constraints (e.g. budget -> promotion)
    has_budget_constraint: bool          # current turn contains an explicit affordability ceiling
    budget_vnd: int | None               # parsed affordability ceiling in VND
    price_requested: bool                # user explicitly asks for a numeric price/cost/fare
    booking_evidence_preferred: bool     # ticket/package/price wording should prefer booking_product evidence
    cost_estimate_requested: bool        # aggregate trip/service budgeting rather than a single item lookup
    price_data_as_of: str | None          # provenance label for customer-facing money answers
    price_evidence_summary: str           # compact structured price evidence for the final answerer
    price_estimate_packet: dict[str, Any]  # deterministic grouped price/estimate evidence for final LLM
    price_estimate_destination_ids: list[str]
    preferred_output_currency: str         # derived from input language; e.g. VND for Vietnamese, USD for English
    currency_conversion_guidance: str      # system-provided conversion rule when evidence currency differs
    answer_mode: str                       # PRICE_ESTIMATE|PRICE_LOOKUP|POLICY_QA|...
    structured_enrichment_count: int
    structured_price_document_count: int
    intent_origin: str                   # current_explicit|generic_discovery|rewrite_inferred|constraint_derived|none
    intent_results: dict[str, dict[str, Any]]
    keyword_candidate_count: int
    missing_destination_ids: list[str]

    # Conversation-memory retrieval augmentation used for recap/summary follow-ups.
    memory_retrieval_queries: list[str]
    memory_augmented: bool

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
