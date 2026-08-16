from __future__ import annotations

"""Lightweight knowledge-base evidence for the input scope guardrail.

This module deliberately performs only *exact phrase* matching against canonical
entity names already present in the Chroma knowledge base. It is not a retriever
and it never decides scope on its own. The guardrail remains authoritative and
uses these matches only as evidence that an otherwise unfamiliar named entity is
actually documented by the Vinpearl knowledge base.

Why this exists:
A legitimate Vinpearl-managed entity can have a name that does not contain the
words "Vinpearl" or "VinWonders" (for example, Cape Wickham Golf Links). Without
KB evidence, an LLM-only scope gate may incorrectly reject such a request before
RAG gets a chance to retrieve the supporting document.
"""

import re
import unicodedata
from typing import Any


# Restrict the probe to entity/table types whose labels can reasonably identify a
# concrete Vinpearl-supported object or an official KB item. Exact phrase matching
# plus the guardrail's mixed-scope policy prevents these matches from becoming a
# blanket allow rule.
_SCOPE_ENTITY_TYPES = {
    "destination",
    "complex",
    "property",
    "room",
    "amenity",
    "dining_service",
    "attraction",
    "destination_highlight",
    "golf_course",
    "golf_feature",
    "mice_venue",
    "mice_room",
    "promotion",
    "faq",
    "policy_document",
    "org_info",
}

# Names that are too generic to be useful as affiliation evidence when they appear
# alone. Multi-word canonical names such as "Vinpearl Safari Phu Quoc" are still
# eligible because the full entity_name is matched, not individual tokens.
_GENERIC_SINGLE_NAMES = {
    "vinpearl",
    "vinwonders",
    "vinclub",
    "hotel",
    "resort",
    "room",
    "safari",
    "golf",
    "restaurant",
    "promotion",
    "policy",
    "payment",
    "faq",
    "service",
    "destination",
    "attraction",
}

_INDEX_CACHE: list[dict[str, str]] | None = None
_INDEX_COLLECTION_NAME: str | None = None
_INDEX_COLLECTION_COUNT: int = -1


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFD", str(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower().replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_strong_entity_name(name: str) -> bool:
    normalized = _normalize_text(name)
    if not normalized:
        return False

    tokens = normalized.split()
    if len(tokens) == 1:
        return len(normalized) >= 8 and normalized not in _GENERIC_SINGLE_NAMES

    # Avoid tiny/noisy labels while keeping normal proper names and official FAQ
    # questions. The full phrase still has to appear in the user's message.
    return len(normalized) >= 7 and any(len(token) >= 3 for token in tokens)


def _match_entities(
    message: str,
    entities: list[dict[str, str]],
    *,
    limit: int = 5,
) -> list[dict[str, str]]:
    """Return strong exact-phrase entity matches, longest names first."""
    normalized_message = _normalize_text(message)
    if not normalized_message:
        return []

    padded_message = f" {normalized_message} "
    matches: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    # Longest canonical names first so a specific entity beats a shorter parent.
    ordered = sorted(
        entities,
        key=lambda item: len(_normalize_text(item.get("entity_name", ""))),
        reverse=True,
    )

    for item in ordered:
        entity_name = str(item.get("entity_name") or "").strip()
        entity_type = str(item.get("entity_type") or "").strip()
        if entity_type not in _SCOPE_ENTITY_TYPES or not _is_strong_entity_name(entity_name):
            continue

        normalized_name = _normalize_text(entity_name)
        if f" {normalized_name} " not in padded_message:
            continue

        key = (normalized_name, entity_type)
        if key in seen:
            continue
        seen.add(key)

        match = {
            "entity_name": entity_name[:300],
            "entity_type": entity_type[:80],
        }
        destination_id = str(item.get("destination_id") or "").strip()
        if destination_id:
            match["destination_id"] = destination_id[:120]
        matches.append(match)
        if len(matches) >= limit:
            break

    return matches


def _load_entity_index() -> list[dict[str, str]]:
    """Load a small entity-name index from the already-ingested Chroma corpus.

    Any storage/import failure returns an empty index. This is intentionally
    fail-neutral: when the probe is unavailable, the existing guardrail behavior
    is preserved rather than weakening scope controls.
    """
    global _INDEX_CACHE, _INDEX_COLLECTION_NAME, _INDEX_COLLECTION_COUNT

    try:
        # Lazy imports keep this helper harmless in unit-test/dev environments that
        # do not have the production vector-store dependency installed.
        import chromadb  # type: ignore

        from src.backend.config import get_settings

        settings = get_settings()
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        chroma = chromadb.PersistentClient(path=str(settings.chroma_dir))
        collection = chroma.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        count = collection.count()

        if (
            _INDEX_CACHE is not None
            and _INDEX_COLLECTION_NAME == collection.name
            and _INDEX_COLLECTION_COUNT == count
        ):
            return _INDEX_CACHE

        entities: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        batch_size = 500
        for offset in range(0, count, batch_size):
            batch = collection.get(
                limit=min(batch_size, count - offset),
                offset=offset,
                include=["metadatas"],
            )
            for metadata in batch.get("metadatas", []) or []:
                metadata = metadata or {}
                entity_type = str(metadata.get("entity_type") or "").strip()
                entity_name = str(metadata.get("entity_name") or "").strip()
                destination_id = str(metadata.get("destination_id") or "").strip()
                if entity_type not in _SCOPE_ENTITY_TYPES or not _is_strong_entity_name(entity_name):
                    continue

                key = (_normalize_text(entity_name), entity_type, destination_id)
                if key in seen:
                    continue
                seen.add(key)
                entities.append(
                    {
                        "entity_name": entity_name,
                        "entity_type": entity_type,
                        "destination_id": destination_id,
                    }
                )

        _INDEX_CACHE = entities
        _INDEX_COLLECTION_NAME = collection.name
        _INDEX_COLLECTION_COUNT = count
        print(f"[KB SCOPE PROBE] Indexed {len(entities)} canonical KB entity names")
        return entities
    except Exception as exc:
        # Do not turn an optional scope hint into a new failure mode.
        print(f"[KB SCOPE PROBE] unavailable; preserving existing guardrail behavior: {exc}")
        return []


def probe_kb_scope_evidence(message: str, *, limit: int = 5) -> list[dict[str, str]]:
    """Find exact canonical KB entities explicitly named in ``message``.

    The returned value is evidence only. Callers MUST NOT use it as a standalone
    authorization/scope decision.
    """
    return _match_entities(message, _load_entity_index(), limit=limit)


def probe_recent_kb_entities(
    recent_entities: list[dict[str, Any]] | None,
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Re-validate grounded conversation entities against the current KB index.

    ``recent_entities`` comes from structured conversation memory, but memory alone
    must never become scope authority.  This helper therefore keeps only names that
    exactly equal a canonical entity currently present in the indexed Vinpearl KB.
    The result is still *evidence only*: the guardrail must semantically decide
    whether the CURRENT message actually refers back to any returned entity.

    This closes the pre-RAG anaphora gap for turns such as ``tell me more about it``
    after a grounded answer about a KB entity whose name does not itself contain the
    Vinpearl brand.  No pronoun/topic keyword rules are introduced here.
    """
    if not recent_entities:
        return []

    index = _load_entity_index()
    if not index:
        return []

    by_name: dict[str, list[dict[str, str]]] = {}
    for item in index:
        normalized_name = _normalize_text(item.get("entity_name", ""))
        if not normalized_name:
            continue
        by_name.setdefault(normalized_name, []).append(item)

    matches: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for memory_item in recent_entities:
        memory_name = str(memory_item.get("name") or "").strip()
        memory_type = str(
            memory_item.get("type") or memory_item.get("entity_type") or ""
        ).strip()
        normalized_memory_name = _normalize_text(memory_name)
        if not normalized_memory_name:
            continue

        canonical_candidates = by_name.get(normalized_memory_name, [])
        if memory_type:
            typed_candidates = [
                item
                for item in canonical_candidates
                if str(item.get("entity_type") or "").casefold() == memory_type.casefold()
            ]
            if typed_candidates:
                canonical_candidates = typed_candidates

        for item in canonical_candidates:
            entity_name = str(item.get("entity_name") or "").strip()
            entity_type = str(item.get("entity_type") or "").strip()
            destination_id = str(item.get("destination_id") or "").strip()
            key = (_normalize_text(entity_name), entity_type.casefold(), destination_id)
            if not entity_name or key in seen:
                continue
            seen.add(key)

            match = {
                "entity_name": entity_name[:300],
                "entity_type": entity_type[:80],
                "memory_source": str(
                    memory_item.get("source") or "recent_grounded_focus"
                )[:80],
            }
            if destination_id:
                match["destination_id"] = destination_id[:120]
            matches.append(match)
            if len(matches) >= max(1, limit):
                return matches

    return matches


def clear_kb_scope_probe_cache() -> None:
    """Clear process-local cache (primarily for tests/maintenance)."""
    global _INDEX_CACHE, _INDEX_COLLECTION_NAME, _INDEX_COLLECTION_COUNT
    _INDEX_CACHE = None
    _INDEX_COLLECTION_NAME = None
    _INDEX_COLLECTION_COUNT = -1
