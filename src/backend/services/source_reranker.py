from __future__ import annotations

import re
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import chromadb

from src.backend.config import get_settings
from src.backend.services.query_parser import load_destination_catalog, normalize_text


URL_KEYS = (
    "source_url",
    "canonical_url",
    "page_url",
    "detail_url",
    "booking_url",
    "terms_url",
    "room_page_url",
    "dining_page_url",
    "map_url",
    "target_url",
    "to_url",
    "path",
)

PRIMARY_ENTITY_TYPES = {
    "destination",
    "complex",
    "property",
    "attraction",
    "golf_course",
    "mice_venue",
    "dining_service",
}

SECONDARY_ENTITY_TYPES = {
    "destination_highlight",
    "room",
    "amenity",
    "golf_feature",
    "mice_room",
}

# Pages about a child show/article can be useful evidence, but should not outrank
# the canonical page of the place/entity that the assistant actually named.
CHILD_PAGE_HINTS = {
    "show",
    "performance",
    "street performance",
    "song",
    "little mermaid",
    "once show",
    "charm of venice",
    "quintessence",
}


class SourceReranker:
    """Choose citations *after* answer generation.

    Retrieval optimizes answer context. Citation selection has a different goal:
    the URL shown to the user should directly support an entity that appears in
    the final answer and should not contradict the active destination.
    """

    _cache_collection: str | None = None
    _cache_count: int = -1
    _cache: list[dict[str, Any]] | None = None

    def __init__(self) -> None:
        settings = get_settings()
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self.chroma = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self.collection = self.chroma.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _phrase_in_text(text: str, phrase: str) -> bool:
        if not text or not phrase:
            return False
        return f" {phrase} " in f" {text} "

    def _load_cache(self) -> list[dict[str, Any]]:
        count = self.collection.count()
        if (
            SourceReranker._cache is not None
            and SourceReranker._cache_collection == self.collection.name
            and SourceReranker._cache_count == count
        ):
            return SourceReranker._cache

        rows: list[dict[str, Any]] = []
        batch_size = 500
        for offset in range(0, count, batch_size):
            batch = self.collection.get(
                limit=min(batch_size, count - offset),
                offset=offset,
                include=["documents", "metadatas"],
            )
            ids = batch.get("ids", []) or []
            docs = batch.get("documents", []) or []
            metas = batch.get("metadatas", []) or []
            for doc_id, text, metadata in zip(ids, docs, metas):
                text = text or ""
                metadata = metadata or {}
                searchable = normalize_text(
                    " ".join(
                        [
                            str(metadata.get("entity_name") or ""),
                            str(metadata.get("entity_type") or ""),
                            str(metadata.get("destination_id") or ""),
                            text,
                        ]
                    )
                )
                rows.append(
                    {
                        "id": doc_id,
                        "text": text,
                        "metadata": metadata,
                        "searchable": searchable,
                    }
                )

        SourceReranker._cache = rows
        SourceReranker._cache_collection = self.collection.name
        SourceReranker._cache_count = count
        print(f"[SOURCE RERANK] Built citation cache: {count} documents")
        return rows

    @staticmethod
    def _extract_answer_entities(answer: str) -> list[str]:
        """Extract entity-like phrases explicitly named in the final answer."""
        values: list[str] = []

        # Markdown bold is the most reliable signal in current answer formatting.
        values.extend(re.findall(r"\*\*([^*\n]{2,120})\*\*", answer or ""))

        # Bullets often use "Entity: description" even if markdown styling changes.
        for line in (answer or "").splitlines():
            match = re.match(r"^\s*[-*•]\s*(?:\*\*)?([^:\n]{2,100})(?:\*\*)?\s*:", line)
            if match:
                values.append(match.group(1))

        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            value = re.sub(r"\s+", " ", value).strip(" -–—:*`[]()")
            normalized = normalize_text(value)
            # Avoid treating generic section labels as entities.
            if not normalized or normalized in {
                "noi luu tru cao cap",
                "trai nghiem noi bat",
                "dich vu",
                "tien ich",
                "hoat dong",
                "luu y",
            }:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(value)
        return cleaned[:20]

    @staticmethod
    def _candidate_urls(item: dict[str, Any]) -> list[str]:
        metadata = item.get("metadata", {}) or {}
        urls: list[str] = []
        for key in URL_KEYS:
            value = str(metadata.get(key) or "").strip()
            if value.startswith(("http://", "https://")) and value not in urls:
                urls.append(value)

        for value in re.findall(r"https?://[^\s<>\]\)\}]+", str(item.get("text") or "")):
            cleaned = value.rstrip(".,;:'\"")
            if cleaned and cleaned not in urls:
                urls.append(cleaned)
        return urls

    @staticmethod
    def _url_destination_ids(url: str) -> set[str]:
        normalized = normalize_text(url)
        found: set[str] = set()
        if not normalized:
            return found
        for destination_id, destination in load_destination_catalog().items():
            for alias in destination.get("normalized_aliases", []):
                if len(alias) < 4:
                    continue
                if SourceReranker._phrase_in_text(normalized, alias):
                    found.add(str(destination_id))
                    break
        return found

    @classmethod
    def _url_conflicts(cls, url: str, target_destination_ids: set[str]) -> bool:
        if not target_destination_ids:
            return False
        encoded = cls._url_destination_ids(url)
        # Generic canonical pages such as /grand-world/ encode no city and are valid.
        return bool(encoded and encoded.isdisjoint(target_destination_ids))

    @staticmethod
    def _destination_aliases(destination_ids: set[str]) -> list[str]:
        catalog = load_destination_catalog()
        aliases: list[str] = []
        for destination_id in destination_ids:
            item = catalog.get(destination_id) or {}
            aliases.extend(item.get("normalized_aliases", []))
        return sorted(set(a for a in aliases if a), key=lambda x: (-len(x), x))

    @classmethod
    def _matches_destination(
        cls,
        item: dict[str, Any],
        destination_ids: set[str],
        destination_aliases: list[str],
    ) -> bool:
        if not destination_ids:
            return True
        metadata = item.get("metadata", {}) or {}
        metadata_destination = str(metadata.get("destination_id") or "").strip()
        if metadata_destination and metadata_destination in destination_ids:
            return True
        searchable = item.get("searchable") or normalize_text(
            " ".join(
                [
                    str(metadata.get("entity_name") or ""),
                    str(item.get("text") or ""),
                ]
            )
        )
        return any(cls._phrase_in_text(searchable, alias) for alias in destination_aliases)

    @staticmethod
    def _entity_terms(entity: str) -> list[str]:
        normalized = normalize_text(entity)
        stop = {
            "vinpearl",
            "vinwonders",
            "hanoi",
            "ha",
            "noi",
            "ocean",
            "city",
            "the",
            "and",
            "at",
            "park",
        }
        return [token for token in normalized.split() if len(token) >= 3 and token not in stop]

    @classmethod
    def _url_score(
        cls,
        url: str,
        *,
        entity_name: str,
        answer_entities: list[str],
        target_destination_ids: set[str],
    ) -> float:
        if cls._url_conflicts(url, target_destination_ids):
            return -10_000.0

        parsed = urlparse(url)
        normalized_url = normalize_text(f"{parsed.netloc} {parsed.path}")
        score = 0.0

        entity_norm = normalize_text(entity_name)
        entity_terms = cls._entity_terms(entity_name)
        if entity_norm and cls._phrase_in_text(normalized_url, entity_norm):
            score += 80.0
        if entity_terms:
            matched = sum(1 for token in entity_terms if cls._phrase_in_text(normalized_url, token))
            score += min(50.0, matched * 15.0)

        for answer_entity in answer_entities:
            answer_terms = cls._entity_terms(answer_entity)
            if answer_terms:
                matched = sum(1 for token in answer_terms if cls._phrase_in_text(normalized_url, token))
                score += min(35.0, matched * 10.0)

        # Prefer a concise canonical/detail page over deep article URLs when entity
        # relevance is otherwise similar.
        depth = len([part for part in parsed.path.split("/") if part])
        score += max(0.0, 12.0 - depth * 2.0)
        return score

    @classmethod
    def _best_url(
        cls,
        item: dict[str, Any],
        *,
        answer_entities: list[str],
        target_destination_ids: set[str],
    ) -> str | None:
        metadata = item.get("metadata", {}) or {}
        entity_name = str(metadata.get("entity_name") or "")
        urls = cls._candidate_urls(item)
        if not urls:
            return None
        ranked = sorted(
            urls,
            key=lambda url: cls._url_score(
                url,
                entity_name=entity_name,
                answer_entities=answer_entities,
                target_destination_ids=target_destination_ids,
            ),
            reverse=True,
        )
        best = ranked[0]
        if cls._url_score(
            best,
            entity_name=entity_name,
            answer_entities=answer_entities,
            target_destination_ids=target_destination_ids,
        ) <= -9_000:
            return None
        return best

    @classmethod
    def _citation_score(
        cls,
        item: dict[str, Any],
        *,
        answer_norm: str,
        answer_entities: list[str],
        destination_ids: set[str],
        destination_aliases: list[str],
        original_retrieved_ids: set[str],
    ) -> float:
        metadata = item.get("metadata", {}) or {}
        entity_name = str(metadata.get("entity_name") or "")
        entity_norm = normalize_text(entity_name)
        entity_type = str(metadata.get("entity_type") or metadata.get("category") or "")
        searchable = item.get("searchable") or normalize_text(
            f"{entity_name} {item.get('text') or ''}"
        )

        score = 0.0
        if item.get("id") in original_retrieved_ids:
            score += 12.0

        # Strongest signal: this source's entity is actually named in the answer.
        if entity_norm and len(entity_norm) >= 4:
            if cls._phrase_in_text(answer_norm, entity_norm):
                score += 120.0
            elif entity_norm in answer_norm:
                score += 90.0

        for answer_entity in answer_entities:
            answer_entity_norm = normalize_text(answer_entity)
            if not answer_entity_norm:
                continue
            if entity_norm == answer_entity_norm:
                score += 140.0
            elif entity_norm and (
                entity_norm in answer_entity_norm or answer_entity_norm in entity_norm
            ):
                score += 90.0
            elif cls._phrase_in_text(searchable, answer_entity_norm):
                score += 55.0
            else:
                terms = cls._entity_terms(answer_entity)
                if terms:
                    overlap = sum(1 for token in terms if cls._phrase_in_text(searchable, token))
                    score += min(35.0, overlap * 9.0)

        metadata_destination = str(metadata.get("destination_id") or "").strip()
        if destination_ids and metadata_destination in destination_ids:
            score += 55.0
        elif destination_ids and any(
            cls._phrase_in_text(searchable, alias) for alias in destination_aliases
        ):
            score += 30.0

        if entity_type in PRIMARY_ENTITY_TYPES:
            score += 28.0
        elif entity_type in SECONDARY_ENTITY_TYPES:
            score += 12.0

        urls = cls._candidate_urls(item)
        if urls:
            score += 18.0
        if urls and all(cls._url_conflicts(url, destination_ids) for url in urls):
            score -= 300.0

        # Penalize child show/article pages unless that child itself is named in answer.
        entity_lower = normalize_text(entity_name)
        is_child_page = any(hint in entity_lower for hint in CHILD_PAGE_HINTS)
        if is_child_page and not cls._phrase_in_text(answer_norm, entity_lower):
            score -= 55.0

        return score

    def rerank(
        self,
        *,
        answer: str,
        retrieved_documents: list[dict[str, Any]],
        destination_ids: set[str] | None = None,
        max_sources: int = 5,
    ) -> list[dict[str, Any]]:
        destination_ids = set(destination_ids or set())
        destination_aliases = self._destination_aliases(destination_ids)
        answer_norm = normalize_text(answer)
        answer_entities = self._extract_answer_entities(answer)

        original_retrieved_ids: set[str] = set()
        seed_items: list[dict[str, Any]] = []
        for item in retrieved_documents or []:
            copied = dict(item)
            metadata = copied.get("metadata", {}) or {}
            copied["searchable"] = normalize_text(
                f"{metadata.get('entity_name') or ''} {copied.get('text') or ''}"
            )
            # The runtime retrieved dict may not carry the Chroma id. Keep a stable
            # pseudo-id only for seed bonus/dedup.
            pseudo_id = str(
                copied.get("id")
                or metadata.get("entity_id")
                or f"seed:{metadata.get('entity_type')}:{metadata.get('entity_name')}"
            )
            copied["id"] = pseudo_id
            original_retrieved_ids.add(pseudo_id)
            seed_items.append(copied)

        # Search the entire indexed knowledge base lexically, but only for entities
        # that survived into the final answer. This is the key difference from using
        # retrieved_documents[:5].
        corpus_candidates: list[dict[str, Any]] = []
        entity_norms = [normalize_text(value) for value in answer_entities]
        entity_norms = [value for value in entity_norms if len(value) >= 4]

        for item in self._load_cache():
            if destination_ids and not self._matches_destination(
                item, destination_ids, destination_aliases
            ):
                continue
            searchable = item["searchable"]
            entity_name_norm = normalize_text(
                str((item.get("metadata", {}) or {}).get("entity_name") or "")
            )
            matched = False
            for entity_norm in entity_norms:
                if (
                    cls_phrase := self._phrase_in_text(searchable, entity_norm)
                ) or (entity_name_norm and (
                    entity_name_norm in entity_norm or entity_norm in entity_name_norm
                )):
                    matched = bool(cls_phrase or entity_name_norm)
                    if matched:
                        break
                # Token overlap helps when answer says "Hanoi Grand World" while
                # source metadata says "Grand World".
                terms = self._entity_terms(entity_norm)
                if terms:
                    overlap = sum(1 for token in terms if self._phrase_in_text(searchable, token))
                    if overlap >= min(2, len(terms)):
                        matched = True
                        break
            if matched:
                corpus_candidates.append(item)

        merged: dict[str, dict[str, Any]] = {}
        for item in seed_items + corpus_candidates:
            metadata = item.get("metadata", {}) or {}
            key = str(
                item.get("id")
                or metadata.get("entity_id")
                or f"{metadata.get('entity_type')}:{metadata.get('entity_name')}:{item.get('text','')[:80]}"
            )
            merged[key] = item

        ranked: list[dict[str, Any]] = []
        for item in merged.values():
            score = self._citation_score(
                item,
                answer_norm=answer_norm,
                answer_entities=answer_entities,
                destination_ids=destination_ids,
                destination_aliases=destination_aliases,
                original_retrieved_ids=original_retrieved_ids,
            )
            best_url = self._best_url(
                item,
                answer_entities=answer_entities,
                target_destination_ids=destination_ids,
            )
            # URL is optional citation metadata. A source can still directly
            # support the answer even when the crawl/database has no canonical URL.
            # Keep strong no-URL evidence instead of pretending the knowledge is absent.
            minimum_score = 65.0 if best_url else 85.0
            if score < minimum_score:
                continue
            ranked.append(
                {
                    **item,
                    "citation_score": round(score, 2),
                    "best_source_url": best_url,
                }
            )

        ranked.sort(key=lambda item: float(item.get("citation_score", 0.0)), reverse=True)

        # Deduplicate by canonical URL first; then by entity name. Do not force five
        # citations when only two or three direct sources are good enough.
        output: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        seen_entities: set[str] = set()
        for item in ranked:
            metadata = item.get("metadata", {}) or {}
            url = str(item.get("best_source_url") or "").strip()
            entity = normalize_text(str(metadata.get("entity_name") or ""))
            if url and url in seen_urls:
                continue
            if entity and entity in seen_entities:
                continue
            if url:
                seen_urls.add(url)
            if entity:
                seen_entities.add(entity)
            output.append(item)
            if len(output) >= max_sources:
                break

        print(
            "[SOURCE RERANK] "
            f"entities={answer_entities[:8]} destination_ids={sorted(destination_ids)} "
            f"candidates={len(merged)} selected={len(output)}"
        )
        for index, item in enumerate(output, start=1):
            metadata = item.get("metadata", {}) or {}
            print(
                f"  {index}. citation_score={item.get('citation_score')} "
                f"name={metadata.get('entity_name')} url={item.get('best_source_url')}"
            )
        return output


@lru_cache(maxsize=1)
def get_source_reranker() -> SourceReranker:
    return SourceReranker()
