from src.backend.agents.state import AgentState
from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.services.llm import LLMService
from src.backend.services.retrieval_enrichment import PRICE_DATA_AS_OF


def validate_grounding(state: AgentState) -> AgentState:
    """Validate positive claims against context while allowing KB-absence statements."""
    draft = str(state.get("answer") or "").strip()
    context = str(state.get("context") or "").strip()
    intent_results = state.get("intent_results", {}) or {}

    if not draft:
        return {
            "grounding_passed": False,
            "grounding_reason": "Answer is empty.",
        }

    # A pure no-data response can legitimately have no retrieved context.
    if not context and not intent_results:
        return {
            "grounding_passed": False,
            "grounding_reason": "Answer and retrieval metadata cannot be grounded.",
        }

    llm = LLMService()
    result = llm.json(
        system_prompt=(
            "You are a strict grounding validator for a RAG system. Positive factual claims and "
            "named entities are supported ONLY by RETRIEVED_CONTEXT. INTENT_RETRIEVAL_STATUS is "
            "trusted system retrieval metadata and may support only a narrow statement such as "
            "'the current knowledge base did not retrieve/record enough information for golf'. "
            "It NEVER supports the stronger claim that golf or any entity does not exist in reality. "
            "For multi-intent answers, validate each section independently. A missing branch may be "
            "reported as KB-not-found while found branches must remain grounded in context. "
            "When RETRIEVED_CONTEXT contains a matching type=faq source, a faithful translation or concise "
            "paraphrase of that FAQ's Answer field is grounded even if it does not repeat the English wording verbatim. "
            "For price/cost answers, transparent arithmetic derived solely from numeric RETRIEVED_CONTEXT values is grounded. "
            "A clearly labeled estimation assumption that a hotel room price_from/standard-rate is used as an approximate nightly "
            "rate is also permitted when the user explicitly requested a trip/lodging cost estimate. Do not allow invented exchange "
            "rates or unsupported prices. PRICE_DATA_AS_OF is trusted system provenance metadata, so a statement that price information "
            "is updated as of that date is grounded even when the date is not repeated inside a source row. "
            "When PRICE_REQUESTED=true and RETRIEVED_CONTEXT contains numeric money evidence, any corrected_answer must preserve at least "
            "one supported numeric price/range/estimate and the PRICE_DATA_AS_OF statement; grounding correction must not collapse a useful "
            "price answer into a generic website referral. "
            "If unsupported content exists, return a corrected answer removing only unsupported claims "
            "and preserving grounded partial sections. Introduce no new facts. corrected_answer MUST be "
            "entirely in TARGET_RESPONSE_LANGUAGE. Do not fall back to English just because the context is English. "
            "Return JSON with exactly: grounded, reason, unsupported_claims, corrected_answer."
        ),
        user_prompt=f"""
TARGET_RESPONSE_LANGUAGE: {state.get("original_language_name") or state.get("original_language", "en")} ({state.get("original_language", "en")})

USER_QUESTION:
{effective_user_message(state)}

PRICE_REQUESTED: {str(bool(state.get('price_requested', False))).lower()}
COST_ESTIMATE_REQUESTED: {str(bool(state.get('cost_estimate_requested', False))).lower()}
PRICE_DATA_AS_OF: {state.get('price_data_as_of') or PRICE_DATA_AS_OF}
STRUCTURED_PRICE_EVIDENCE:
{state.get('price_evidence_summary') or '(none)'}

INTENT_RETRIEVAL_STATUS:
{intent_results}

RETRIEVED_CONTEXT:
{context}

DRAFT_ANSWER:
{draft}

Return exactly this JSON shape:
{{
  "grounded": true,
  "reason": "brief reason",
  "unsupported_claims": [],
  "corrected_answer": ""
}}
""",
    )

    grounded = bool(result.get("grounded", False))
    reason = str(result.get("reason") or "No grounding reason returned.").strip()
    unsupported = result.get("unsupported_claims") or []
    if not isinstance(unsupported, list):
        unsupported = [str(unsupported)]

    if grounded:
        final_answer = draft
    else:
        corrected = str(result.get("corrected_answer") or "").strip()
        final_answer = corrected or (
            "The current knowledge base does not contain enough grounded information "
            "to answer this request safely."
        )

    print("\n===== GROUNDING VALIDATION =====")
    print(f"Grounded: {grounded}")
    print(f"Reason: {reason}")
    if unsupported:
        print("Unsupported claims:")
        for claim in unsupported:
            print(f"- {claim}")
    print("================================\n")

    return {
        "answer": final_answer,
        "grounding_passed": grounded,
        "grounding_reason": reason,
        "unsupported_claims": [str(item) for item in unsupported],
    }
