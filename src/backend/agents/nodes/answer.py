from src.backend.agents.state import AgentState
from src.backend.services.llm import LLMService


def _allowed_entities(state: AgentState) -> str:
    names: list[str] = []
    seen: set[str] = set()

    for item in state.get("retrieved_documents", []):
        metadata = item.get("metadata", {}) or {}
        for key in ("entity_name", "source_file", "title", "name"):
            value = str(metadata.get(key) or "").strip()
            if value and value.lower() not in seen:
                seen.add(value.lower())
                names.append(value)

    return "\n".join(f"- {name}" for name in names[:80]) or "(none)"


def _intent_status_text(state: AgentState) -> str:
    results = state.get("intent_results", {}) or {}
    if not results:
        return "(single-intent/legacy retrieval; no per-intent status)"
    lines: list[str] = []
    for intent, result in results.items():
        lines.append(
            f"- {intent}: {result.get('status', 'unknown')} "
            f"(documents={result.get('document_count', 0)}, best_score={result.get('best_score', 0)})"
        )
    return "\n".join(lines)


def generate_answer(state: AgentState) -> AgentState:
    """Generate a grounded answer; multi-intent branches may be partially available."""
    llm = LLMService()

    answer = llm.text(
        system_prompt=(
            "You are a strictly grounded Vinpearl/VinWonders RAG assistant. "
            "RETRIEVED_CONTEXT is the ONLY source for positive factual claims. "
            "Do not use pretrained knowledge, general knowledge, web knowledge, assumptions, "
            "or facts remembered from previous assistant answers. Every named entity and factual "
            "claim must be explicitly supported by RETRIEVED_CONTEXT. Never fabricate URLs. "
            "INTENT_RETRIEVAL_STATUS is system-generated retrieval metadata, not world knowledge. "
            "For an intent marked found, answer that part only from RETRIEVED_CONTEXT. "
            "For an intent marked not_found, do NOT say the service/entity does not exist in reality; "
            "say only that the current knowledge base does not record or does not contain enough "
            "information to confirm that requested category for the destination. "
            "For multi-intent questions, answer EACH requested intent separately. One missing intent "
            "must never cause you to suppress other intents that have grounded evidence. "
            "Preserve the order of the user's requested topics when practical. Missing URL metadata "
            "must never cause supported content to be omitted. The response language is mandatory: "
            "write the ENTIRE natural-language answer in TARGET_RESPONSE_LANGUAGE. Do not switch to "
            "English merely because RETRIEVED_CONTEXT or the retrieval query is English."
        ),
        user_prompt=f"""
TARGET_RESPONSE_LANGUAGE: {state.get("original_language_name") or state.get("original_language", "en")} ({state.get("original_language", "en")})

Current user question:
{state["user_message"]}

Standalone retrieval query:
{state.get("rag_query", "")}

Detected destinations:
{', '.join(state.get("detected_destination_names", [])) or 'none'}

Detected intents (in current-message order):
{', '.join(state.get('detected_intents', [])) or state.get('detected_intent') or 'none'}

REQUEST_MODE: {state.get('request_mode', 'information')}
RESOLUTION_MODE: {state.get('resolution_mode', 'information_only')}

INTENT_RETRIEVAL_STATUS:
{_intent_status_text(state)}

Entities explicitly identified in retrieved metadata:
{_allowed_entities(state)}

RETRIEVED_CONTEXT — sole evidence for positive factual claims:
{state.get("context", "")}

Rules for this answer:
- Cover every requested intent.
- found => answer from context.
- not_found => state only that the CURRENT KNOWLEDGE BASE lacks enough evidence for that intent.
- Never turn not_found into a real-world non-existence claim.
- Never use previous assistant answers as evidence.
- Use TARGET_RESPONSE_LANGUAGE for every explanatory sentence, heading, caveat, and KB-not-found statement.
- Keep proper nouns, IDs, URLs, emails, numbers, and official names as needed; those do not count as a language switch.
- For self_serve support, give only grounded steps; do not pretend to perform account-specific actions.
""",
    )

    return {"answer": answer}
