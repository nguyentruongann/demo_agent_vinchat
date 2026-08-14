from __future__ import annotations

import json
from typing import Any

from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.agents.state import AgentState
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import detect_destinations, load_destination_catalog


def _bounded_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _catalog_destination(destination_id: str) -> dict[str, Any] | None:
    item = load_destination_catalog().get(str(destination_id or "").strip())
    if not item:
        return None
    return {
        "id": str(item.get("id") or destination_id),
        "name_en": item.get("name_en"),
        "name_vi": item.get("name_vi"),
        "aliases": list(item.get("normalized_aliases") or item.get("aliases") or []),
    }


def _destination_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("name_vi")
        or item.get("name_en")
        or item.get("id")
        or ""
    ).strip()


def _build_candidates(state: AgentState) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build a closed candidate set from current explicit mentions + user focus memory.

    Assistant-answer entities are intentionally absent. ``recent_destinations`` is
    built from structured turn metadata (or, for old rows, user_message/rag_query),
    so a broad assistant reply cannot silently become future conversation focus.
    """
    current_message = effective_user_message(state)
    explicit_raw = detect_destinations(current_message)

    candidates: list[dict[str, Any]] = []
    explicit: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in explicit_raw:
        destination_id = str(raw.get("id") or "").strip()
        if not destination_id or destination_id in seen:
            continue
        item = _catalog_destination(destination_id) or dict(raw)
        item = dict(item)
        item["source"] = "current_explicit"
        item["recency_rank"] = None
        explicit.append(item)
        candidates.append(item)
        seen.add(destination_id)

    for rank, raw in enumerate(state.get("recent_destinations", []) or [], start=1):
        destination_id = str(raw.get("id") or "").strip()
        if not destination_id or destination_id in seen:
            continue
        item = _catalog_destination(destination_id)
        if item is None:
            # Recent focus should normally be catalog-backed. Ignore stale/invalid
            # IDs instead of exposing them as selectable model output.
            continue
        item = dict(item)
        item["source"] = "recent_user_focus"
        item["recency_rank"] = rank
        candidates.append(item)
        seen.add(destination_id)

    return explicit, candidates


def _compact_focus_turns(state: AgentState, limit: int = 8) -> list[dict[str, Any]]:
    """Expose structured user focus to the resolver without assistant-answer noise."""
    output: list[dict[str, Any]] = []
    turns = list(state.get("conversation_turns", []) or [])[-limit:]
    for turn in turns:
        focus = turn.get("resolved_destinations") or turn.get("detected_destinations") or []
        focus_ids = [
            str(item.get("id") or "").strip()
            for item in focus
            if str(item.get("id") or "").strip()
        ]
        output.append(
            {
                "user_message": str(turn.get("user_message") or "")[:500],
                "rag_query": str(turn.get("rag_query") or "")[:700],
                "focus_destination_ids": focus_ids,
                "detected_intents": list(turn.get("detected_intents") or []),
            }
        )
    return output


def _fallback_resolution(
    explicit: list[dict[str, Any]],
    rag_query: str,
    reason: str,
) -> AgentState:
    """Fail safely to current explicit entities; never guess from memory on errors."""
    names = [_destination_name(item) for item in explicit]
    return {
        "explicit_destinations": explicit,
        "resolved_destinations": explicit,
        "resolved_destination_ids": [str(item.get("id") or "") for item in explicit],
        "resolved_destination_names": names,
        "context_uses_memory": False,
        "context_resolution_reason": reason,
        "context_resolution_confidence": 0.0,
        "context_resolution_source": "explicit_fallback" if explicit else "none",
        "rag_query": rag_query,
    }


def resolve_conversation_context(state: AgentState) -> AgentState:
    """Semantically bind CURRENT-turn destination references to structured memory.

    This is intentionally NOT a phrase/regex resolver. The model receives a closed
    set of supported destination candidates and decides, from the meaning of the
    current request, which of them are actually in focus. It may select zero, one,
    or several. A generic request such as "where are the golf courses?" is allowed
    to select zero even when old destinations exist; a follow-up such as "what about
    there?" may select recent user focus. The selected IDs are validated before they
    can reach retrieval.
    """
    current_message = effective_user_message(state)
    guarded_query = str(state.get("rag_query") or current_message).strip()
    explicit, candidates = _build_candidates(state)

    # Non-RAG turns do not need reference binding. Preserve explicit detection only
    # for diagnostics and never allow memory to change their route.
    if str(state.get("route") or "") != "rag":
        return _fallback_resolution(
            explicit,
            guarded_query,
            "Context resolver skipped because the current route is not RAG.",
        )

    if not candidates:
        return _fallback_resolution(
            explicit,
            guarded_query,
            "No supported destination candidates are available for this turn.",
        )

    # With no prior focus there is nothing to resolve semantically: current explicit
    # mentions are already authoritative and can pass straight through.
    has_memory_candidates = any(item.get("source") == "recent_user_focus" for item in candidates)
    if not has_memory_candidates:
        return {
            **_fallback_resolution(
                explicit,
                guarded_query,
                "Only current-message destinations are available; no memory binding was needed.",
            ),
            "context_resolution_confidence": 1.0 if explicit else 0.0,
            "context_resolution_source": "current_explicit" if explicit else "none",
        }

    candidate_payload = [
        {
            "id": item.get("id"),
            "name": _destination_name(item),
            "source": item.get("source"),
            "recency_rank": item.get("recency_rank"),
        }
        for item in candidates
    ]

    llm = LLMService()
    try:
        result = llm.json(
            system_prompt=(
                "You are a semantic conversation-reference resolver for a Vinpearl/VinWonders RAG assistant. "
                "Resolve which SUPPORTED DESTINATIONS the CURRENT user request is actually about. Do not use "
                "keyword-pattern rules and do not blindly inherit the last destination. You may select ZERO, ONE, "
                "or MULTIPLE destination IDs, but ONLY from the supplied candidate list. Current-explicit candidates "
                "come from destination names literally present in the current message. recent_user_focus candidates "
                "come from destinations the user previously asked about or that were previously resolved for the "
                "user's request; assistant-only locations are deliberately not candidates. Use recent focus only when "
                "the current request semantically refers back to it through an omitted subject, pronoun/reference, "
                "ordinal/choice reference, comparison, continuation, or equivalent discourse relation. A broad/global "
                "question that does not refer back to prior focus must select no old destination even if memory exists. "
                "Handle corrections and negations by meaning: a destination named only as the wrong/negated option is "
                "not necessarily the target. Never invent a destination or infer one from world knowledge. Do not carry "
                "an old intent into the current turn. Also return a standalone faithful English RAG query for the CURRENT "
                "request. Insert resolved destination names when they are necessary to make a follow-up standalone; if "
                "no destination is resolved, keep the query destination-neutral. Preserve requested facts, quantities, "
                "preferences, exclusions, and comparison intent. Return JSON only."
            ),
            user_prompt=(
                "UNTRUSTED_CONTEXT_JSON:\n"
                + json.dumps(
                    {
                        "current_message": current_message,
                        "guarded_rag_query": guarded_query,
                        "destination_candidates": candidate_payload,
                        "recent_structured_focus_turns": _compact_focus_turns(state),
                    },
                    ensure_ascii=False,
                )
                + "\n\nReturn exactly:\n"
                + '''{
  "selected_destination_ids": ["candidate-id"],
  "uses_memory": false,
  "rag_query": "standalone faithful English retrieval query",
  "reason": "brief semantic reference-resolution reason",
  "confidence": 0.0
}'''
            ),
        )
    except Exception as exc:
        return _fallback_resolution(
            explicit,
            guarded_query,
            f"Semantic context resolver failed; used explicit current destinations only: {exc}",
        )

    candidate_by_id = {str(item.get("id") or ""): item for item in candidates}
    raw_ids = result.get("selected_destination_ids")
    if not isinstance(raw_ids, list):
        return _fallback_resolution(
            explicit,
            guarded_query,
            "Semantic context resolver returned malformed destination IDs; used explicit current destinations only.",
        )

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    invalid_ids: list[str] = []
    for raw_id in raw_ids:
        destination_id = str(raw_id or "").strip()
        if not destination_id or destination_id in seen:
            continue
        item = candidate_by_id.get(destination_id)
        if item is None:
            invalid_ids.append(destination_id)
            continue
        selected.append(item)
        seen.add(destination_id)

    # A resolver that tries to escape the closed candidate set is not trusted.
    if invalid_ids:
        return _fallback_resolution(
            explicit,
            guarded_query,
            "Semantic context resolver selected unsupported destination IDs; used explicit current destinations only.",
        )

    uses_memory = any(item.get("source") == "recent_user_focus" for item in selected)
    resolved_query = str(result.get("rag_query") or "").strip() or guarded_query
    reason = str(result.get("reason") or "Semantic context resolution completed.").strip()[:500]
    confidence = _bounded_confidence(result.get("confidence"))

    source = "none"
    if selected:
        has_explicit = any(item.get("source") == "current_explicit" for item in selected)
        if has_explicit and uses_memory:
            source = "current_plus_memory"
        elif uses_memory:
            source = "memory"
        else:
            source = "current_explicit"

    names = [_destination_name(item) for item in selected]
    print("\n===== CONTEXT RESOLUTION =====")
    print(f"Question: {current_message}")
    print(f"Candidates: {[(item.get('id'), item.get('source')) for item in candidates]}")
    print(f"Resolved: {[item.get('id') for item in selected]}")
    print(f"Uses memory: {uses_memory}")
    print(f"Confidence: {confidence:.2f}")
    print(f"Reason: {reason}")
    print(f"RAG query: {resolved_query}")
    print("==============================\n")

    return {
        "explicit_destinations": explicit,
        "resolved_destinations": selected,
        "resolved_destination_ids": [str(item.get("id") or "") for item in selected],
        "resolved_destination_names": names,
        "context_uses_memory": uses_memory,
        "context_resolution_reason": reason,
        "context_resolution_confidence": confidence,
        "context_resolution_source": source,
        "rag_query": resolved_query,
    }
