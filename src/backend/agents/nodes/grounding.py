from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.agents.state import AgentState
from src.backend.services.llm import LLMService
from src.backend.services.retrieval_enrichment import PRICE_DATA_AS_OF


def _safe_grounding_answer(state: AgentState) -> str:
    if str(state.get("original_language") or "").lower().startswith("vi"):
        return (
            "Mình chưa thể kiểm chứng an toàn câu trả lời từ dữ liệu hiện có. "
            "Bạn vui lòng hỏi cụ thể hơn một ý để mình kiểm tra lại."
        )
    return (
        "I could not safely verify the answer against the available data. "
        "Please ask a narrower question so I can check it again."
    )


def _validation_payload(
    state: AgentState,
    *,
    draft: str,
    context: str,
    intent_results: dict,
    task_results: dict,
) -> str:
    return f"""
TARGET_RESPONSE_LANGUAGE: {state.get("original_language_name") or state.get("original_language", "en")} ({state.get("original_language", "en")})

USER_QUESTION:
{effective_user_message(state)}

PRICE_REQUESTED: {str(bool(state.get('price_requested', False))).lower()}
COST_ESTIMATE_REQUESTED: {str(bool(state.get('cost_estimate_requested', False))).lower()}
PRICE_DATA_AS_OF: {state.get('price_data_as_of') or PRICE_DATA_AS_OF}
STRUCTURED_PRICE_EVIDENCE:
{state.get('price_evidence_summary') or '(none)'}
PRICE_RESOLUTION: {state.get('price_resolution') or '(none)'}
PRICE_CONTACT_FALLBACK:
{state.get('price_contact_fallback') or {}}
PRICE_ENTITY_RESOLUTION:
{state.get('price_entity_resolution') or []}
ROOM_CATALOG_PRICE_REQUESTED: {str(bool(state.get('room_catalog_price_requested', False))).lower()}

EXHAUSTIVE_RETRIEVAL_REQUESTED: {str(bool(state.get('exhaustive_retrieval_requested', False))).lower()}
EXHAUSTIVE_RETRIEVAL_COMPLETE: {str(bool(state.get('exhaustive_retrieval_complete', False))).lower()}
EXHAUSTIVE_RETRIEVAL_PACKET:
{state.get('exhaustive_retrieval_packet') or {}}

EXHAUSTIVE_CATALOG_REQUESTED: {str(bool(state.get('exhaustive_catalog_requested', False))).lower()}
EXHAUSTIVE_CATALOG_COMPLETE: {str(bool(state.get('exhaustive_catalog_complete', False))).lower()}
EXHAUSTIVE_CATALOG_PACKET:
{state.get('exhaustive_catalog_packet') or {}}

INTENT_RETRIEVAL_STATUS:
{intent_results}

TASK_RETRIEVAL_STATUS:
{task_results}

REQUEST_TASK_PLAN:
{state.get('request_tasks') or []}

CURRENT_INPUT_TASK_TYPE:
{state.get('input_task_type') or 'general'}

RESOLVED_ENTITY_TARGETS:
{state.get('resolved_entity_names') or (state.get('retrieval_entity_scope') or {}).get('names') or []}

RETRIEVED_CONTEXT:
{context}

DRAFT_ANSWER:
{draft}
"""


def validate_grounding(state: AgentState) -> AgentState:
    """Validate claims without allowing malformed control JSON to crash chat."""
    draft = str(state.get("answer") or "").strip()
    context = str(state.get("context") or "").strip()
    intent_results = state.get("intent_results", {}) or {}
    task_results = state.get("task_retrieval_results", {}) or {}

    if not draft:
        return {"grounding_passed": False, "grounding_reason": "Answer is empty."}

    if (
        not context
        and not intent_results
        and not task_results
        and not state.get("exhaustive_catalog_packet")
        and not state.get("exhaustive_retrieval_packet")
    ):
        return {
            "grounding_passed": False,
            "grounding_reason": "Answer and retrieval metadata cannot be grounded.",
        }

    llm = LLMService()
    payload = _validation_payload(
        state,
        draft=draft,
        context=context,
        intent_results=intent_results,
        task_results=task_results,
    )
    try:
        result = llm.json(
            system_prompt=(
                "You are a strict grounding validator for a RAG system. Positive factual claims and named entities "
                "must be supported by RETRIEVED_CONTEXT, PRICE_CONTACT_FALLBACK, PRICE_ENTITY_RESOLUTION, or an explicitly complete trusted packet. "
                "For named-entity price requests, reject any price/contact borrowed from a different entity even when it shares the same destination. Retrieval status may "
                "Also reject a draft that presents a sold-out, booking-closed, unavailable, or unselectable product as currently purchasable. "
                "support only a narrow statement that the current knowledge base did not retrieve enough information; "
                "it never proves non-existence in reality. Validate every atomic task independently and preserve grounded "
                "partial sections. Enforce resolved entity target alignment unless comparison/alternatives were requested. "
                "A faithful translation or concise paraphrase of a matching FAQ answer is grounded. Transparent arithmetic "
                "from retrieved numeric values is grounded, as is the trusted PRICE_DATA_AS_OF provenance. Complete packets "
                "must retain their complete unique entity/product set. Judge only; do not rewrite in this call. Keep reason "
                "and unsupported_claims concise. Never copy DRAFT_ANSWER or RETRIEVED_CONTEXT into a JSON string. "
                "Return JSON with exactly: grounded, reason, unsupported_claims."
            ),
            user_prompt=(
                payload
                + "\nReturn exactly this JSON shape:\n"
                + '{"grounded":true,"reason":"brief reason","unsupported_claims":[]}'
            ),
        )
    except Exception as exc:
        return {
            "answer": _safe_grounding_answer(state),
            "grounding_passed": False,
            "grounding_reason": "Grounding validator failed safely: " + type(exc).__name__,
            "unsupported_claims": [],
        }

    grounded = bool(result.get("grounded", False))
    reason = str(result.get("reason") or "No grounding reason returned.").strip()
    unsupported = result.get("unsupported_claims") or []
    if not isinstance(unsupported, list):
        unsupported = [str(unsupported)]

    if grounded:
        final_answer = draft
    else:
        try:
            corrected = llm.text(
                system_prompt=(
                    "You correct a RAG answer after a separate grounding judgement. Return only the corrected "
                    "customer-facing answer, not JSON. Remove only unsupported claims, preserve every grounded task/section "
                    "and supported numeric price, introduce no new facts, and write entirely in the requested target language."
                ),
                user_prompt=(
                    payload
                    + "\n\nGROUNDING_REASON:\n" + reason
                    + "\n\nUNSUPPORTED_CLAIMS:\n" + str(unsupported)
                    + "\n\nReturn only the corrected answer."
                ),
                temperature=0.0,
                max_tokens=max(llm.max_tokens, 2500),
            ).strip()
        except Exception as exc:
            reason = f"{reason} Correction failed safely: {type(exc).__name__}."[:500]
            corrected = ""
        final_answer = corrected or _safe_grounding_answer(state)

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
