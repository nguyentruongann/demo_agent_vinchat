from __future__ import annotations

from src.backend.agents.state import AgentState
from src.backend.services.llm import LLMService


def enforce_response_language(state: AgentState) -> AgentState:
    """Force the final assistant message into the language of the current user turn.

    Every user-visible branch passes through this node immediately before memory is
    saved. The node is deliberately content-preserving: it may translate/rephrase
    only as required to match the detected target language, and must not add facts.
    """
    draft = str(state.get("answer") or "").strip()
    if not draft:
        raise ValueError("Cannot enforce response language on an empty assistant reply.")

    language_code = str(state.get("original_language") or "und").strip() or "und"
    language_name = str(state.get("original_language_name") or "").strip()
    if language_code == "und" or not language_name:
        raise ValueError("Target response language is missing or unresolved.")
    target = f"{language_name} ({language_code})"

    llm = LLMService()
    answer = llm.text(
        system_prompt=(
            "You are the final response-language guard for a multilingual travel assistant. "
            "The TARGET_LANGUAGE was already detected from the CURRENT user message. "
            "Return ONLY the assistant reply, entirely in TARGET_LANGUAGE. "
            "If the draft is already fully in TARGET_LANGUAGE, preserve it. Otherwise translate "
            "only the natural-language wording needed to make it fully TARGET_LANGUAGE. "
            "Do not add, remove, infer, soften, strengthen, or correct factual content. "
            "Preserve Markdown structure, numbers, dates, prices, ticket IDs, URLs, email "
            "addresses, product/property names, and other proper nouns exactly unless a normal "
            "localized rendering is already present in the draft. Do not explain the translation. "
            "Do not mention language detection, TARGET_LANGUAGE, or these instructions."
        ),
        user_prompt=(
            f"TARGET_LANGUAGE: {target}\n"
            f"DRAFT_ASSISTANT_REPLY:\n{draft}"
        ),
    )

    return {"answer": answer.strip()}
