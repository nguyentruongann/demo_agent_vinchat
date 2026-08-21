from __future__ import annotations

from functools import lru_cache
from math import ceil
import json
import re
from typing import Any

import chromadb
import numpy as np
from src.backend.config import get_settings
from src.backend.services.onnx_embeddings import OnnxE5Embedder, OnnxEmbeddingConfig
from src.backend.services.gemini_embeddings import GeminiEmbedding, GeminiEmbeddingConfig
from src.backend.services.faq_matcher import FAQMatcher
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import (
    INTENT_ENTITY_TYPES,
    build_intent_query,
    load_destination_catalog,
    normalize_text,
    parse_retrieval_query,
)

_PRICE_FULL_VND_RE = re.compile(
    r"(?<!\d)(?P<num>\d{1,3}(?:[.,]\d{3}){1,3}|\d{4,10})\s*"
    r"(?:vnd|vnđ|đ|đồng|dong)(?!\w)",
    flags=re.IGNORECASE,
)
_PRICE_COMPACT_VND_RE = re.compile(
    r"(?<![\w])(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>tr|tri[eệ]u|million|k|ngh[iì]n|ng[aà]n)(?!\w)",
    flags=re.IGNORECASE,
)
_PRICE_IGNORE_BEFORE_MARKERS = (
    "tri gia", "qua tang", "gift value", "gift worth", "merchandise worth",
    "cashback", "hoan tien", "deposit", "dat coc",
)

def _vnd_price_mentions(text_value: str) -> list[tuple[int, int, int]]:
    """Extract explicit VND-like prices as ``(amount, start, end)`` tuples."""
    text = str(text_value or "")
    mentions: list[tuple[int, int, int]] = []

    for match in _PRICE_FULL_VND_RE.finditer(text):
        digits = re.sub(r"[^0-9]", "", match.group("num"))
        if not digits:
            continue
        amount = int(digits)
        if amount > 0:
            mentions.append((amount, match.start(), match.end()))

    for match in _PRICE_COMPACT_VND_RE.finditer(text):
        raw_num = match.group("num").replace(",", ".")
        try:
            number = float(raw_num)
        except ValueError:
            continue
        unit = normalize_text(match.group("unit"))
        multiplier = 1_000_000 if unit in {"tr", "trieu", "million"} else 1_000
        amount = int(round(number * multiplier))
        if amount > 0:
            mentions.append((amount, match.start(), match.end()))

    # Same printed price may be caught by more than one regex in edge cases.
    output: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for item in sorted(mentions, key=lambda value: (value[1], value[0])):
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output

def _affordable_prices(text_value: str, budget_vnd: int | None) -> list[int]:
    """Return offer/ticket prices in the evidence that are within the ceiling.

    We ignore obvious gift/deposit/refund monetary values so an expensive package
    is not declared affordable merely because its copy mentions a small gift value.
    """
    if not budget_vnd or budget_vnd <= 0:
        return []
    text = str(text_value or "")
    output: list[int] = []
    for amount, start, _end in _vnd_price_mentions(text):
        before = normalize_text(text[max(0, start - 90):start])
        if any(marker in before for marker in _PRICE_IGNORE_BEFORE_MARKERS):
            continue
        if amount <= budget_vnd:
            output.append(amount)
    return sorted(set(output))


def text_has_price_evidence(text_value: str) -> bool:
    """Return True only when a retrieved chunk contains an explicit numeric price.

    Product-level metadata such as ``currency`` is intentionally insufficient:
    one booking product can be split into several chunks and only some of them
    actually carry the numeric price variants.
    """
    text = str(text_value or "")
    if not text.strip():
        return False

    price_labels = (
        "price", "prices", "pricing", "cost", "fare", "amount",
        "sale price", "original price", "minimum price", "maximum price",
        "display price", "price variants",
    )
    for raw_line in text.splitlines():
        normalized_line = normalize_text(raw_line)
        if not normalized_line or not any(label in normalized_line for label in price_labels):
            continue
        if re.search(r"\d", raw_line) and (
            re.search(r"[$€£₫]", raw_line)
            or re.search(r"\b(?:usd|vnd|vnđ|dong|đồng)\b", raw_line, re.IGNORECASE)
            or ":" in raw_line
        ):
            return True

    return bool(
        re.search(r"[$€£₫]\s*~?\s*\d", text)
        or re.search(r"\d[\d.,]*\s*(?:usd|vnd|vnđ|dong|đồng)\b", text, re.IGNORECASE)
    )


class RAGService:
    """Hybrid retriever: destination/entity keywords first, embeddings second.

    Important guarantees:
    - A detected destination is a hard constraint. We never fall back to the full
      corpus when an explicit destination has no lexical candidates.
    - Multi-destination comparison queries retrieve evidence for every detected
      destination instead of collapsing to only the first one.
    """

    _corpus_cache: dict[str, Any] | None = None
    _corpus_cache_collection: str | None = None
    _corpus_cache_count: int = -1

    @staticmethod
    def _verify_faq_candidates(
        query_variants: list[tuple[str, str]],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Semantically verify near-miss FAQ candidates after deterministic gates.

        Dense similarity alone is intentionally not authoritative, but multilingual
        paraphrases can miss the lexical/predicate thresholds by a small amount. A
        bounded verifier sees only the top candidates and may select one when its
        documented answer directly supports a requested task. It cannot create new
        evidence or search outside the supplied FAQ rows.
        """
        if not candidates:
            return None
        llm = LLMService()
        result = llm.json(
            system_prompt=(
                "You are a strict semantic equivalence verifier for official Vinpearl FAQ retrieval. "
                "The deterministic vector/lexical gate rejected all candidates, so independently inspect meaning rather than shared words. "
                "Select exactly one candidate only when its QUESTION and documented ANSWER directly support at least one factual or procedural outcome requested by the customer. "
                "For a compound request, a candidate may support one atomic part (for example the requested contact channel) because other evidence will be merged later. "
                "Prefer the most specific applicable candidate. Do not select a merely adjacent policy, and do not assume that deadlines or conditions for changing an existing package apply to a new preference unless the request says so. "
                "Treat faithful multilingual synonyms and paraphrases as equivalent. If no candidate is safely applicable, select 0. Return JSON only."
            ),
            user_prompt=(
                "QUERY_VARIANTS_JSON:\n"
                + json.dumps(
                    [
                        {"source": source, "query": value}
                        for source, value in query_variants
                    ],
                    ensure_ascii=False,
                )
                + "\n\nFAQ_CANDIDATES_JSON:\n"
                + json.dumps(candidates, ensure_ascii=False)
                + "\n\nReturn exactly:\n"
                + '{"selected_candidate_position":0,"confidence":0.0,"reason":"brief evidence-based reason"}'
            ),
        )
        try:
            position = int(result.get("selected_candidate_position") or 0)
        except (TypeError, ValueError):
            position = 0
        try:
            confidence = max(0.0, min(1.0, float(result.get("confidence") or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        if position < 0 or position > len(candidates):
            position = 0
        verified = {
            "selected_candidate_position": position,
            "confidence": confidence,
            "reason": str(result.get("reason") or "").strip()[:500],
        }
        print(
            "[FAQ VERIFIER] "
            f"selected={position} confidence={confidence:.4f} "
            f"reason={verified['reason']}"
        )
        return verified

    def __init__(self) -> None:
        settings = get_settings()
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        if settings.embedding_backend == "gemini_api":
            if not settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is required when EMBEDDING_BACKEND=gemini_api")
            self.model = GeminiEmbedding(
                GeminiEmbeddingConfig(
                    api_key=settings.gemini_api_key,
                    model=settings.gemini_embedding_model,
                    batch_size=settings.embedding_batch_size,
                )
            )
        else:
            self.model = OnnxE5Embedder(
                OnnxEmbeddingConfig(
                    model_name=settings.local_embedding_model,
                    onnx_file=settings.embedding_onnx_file,
                    provider=settings.embedding_onnx_provider,
                    batch_size=settings.embedding_batch_size,
                    max_length=settings.embedding_max_length,
                    intra_op_threads=settings.embedding_onnx_threads,
                )
            )
        self.chroma = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self.collection = self.chroma.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        # Canonical FAQ retrieval is intentionally separate from generic catalog
        # retrieval. It reuses this same ONNX model instance and the raw 174-row
        # FAQ JSON, so no second embedding model is loaded into memory.
        self.faq_matcher = FAQMatcher(
            embed_passages=self.embed_documents,
            embed_queries=self.embed_queries,
            fallback_rows=self._load_faq_fallback_rows,
            semantic_verifier=self._verify_faq_candidates,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        passages = [f"passage: {text}" for text in texts]
        if self.settings.embedding_backend == "gemini_api":
            embeddings = self.model.encode(passages)
        else:
            embeddings = self.model.encode(passages)
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        if self.settings.embedding_backend == "gemini_api":
            embedding = self.model.encode_query([query])[0]
        else:
            embedding = self.model.encode([f"query: {query}"])[0]
        return embedding.tolist()

    def embed_queries(self, queries: list[str]) -> np.ndarray:
        """Embed several query strings in one ONNX batch.

        FAQ-first retrieval compares both the user's original multilingual wording
        and the English standalone rewrite. Batching them avoids duplicate inference.
        """
        cleaned = [str(query or "").strip() for query in queries if str(query or "").strip()]
        if not cleaned:
            return np.empty((0, 3072), dtype=np.float32)
        if self.settings.embedding_backend == "gemini_api":
            return self.model.encode_query(cleaned)
        return self.model.encode([f"query: {query}" for query in cleaned])

    def _ensure_not_empty(self) -> None:
        if self.collection.count() == 0:
            raise RuntimeError(
                "Vector database is empty. Run: "
                "python -m src.backend.services.ingest_postgres --reset"
            )

    def semantic_search_many(
        self,
        queries: list[str],
        top_k: int | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Run multiple semantic queries in one ONNX batch and one Chroma call.

        This is used by the semantic fallback to preserve both the user's exact
        wording and the LLM-rewritten standalone RAG query without paying the
        overhead of two independent model invocations.
        """
        self._ensure_not_empty()
        cleaned = [str(query or "").strip() for query in queries]
        if not cleaned:
            return []

        if self.settings.embedding_backend == "gemini_api":
            embeddings = self.model.encode_query(cleaned).tolist()
        else:
            embeddings = self.model.encode([f"query: {query}" for query in cleaned]).tolist()
        result = self.collection.query(
            query_embeddings=embeddings,
            n_results=top_k or self.settings.top_k,
            include=["documents", "metadatas", "distances"],
        )

        all_documents = result.get("documents", []) or []
        all_metadatas = result.get("metadatas", []) or []
        all_distances = result.get("distances", []) or []
        outputs: list[list[dict[str, Any]]] = []

        for query_index in range(len(cleaned)):
            documents = all_documents[query_index] if query_index < len(all_documents) else []
            metadatas = all_metadatas[query_index] if query_index < len(all_metadatas) else []
            distances = all_distances[query_index] if query_index < len(all_distances) else []
            output: list[dict[str, Any]] = []

            for text, metadata, distance in zip(documents, metadatas, distances):
                score = max(0.0, 1.0 - float(distance))
                output.append(
                    {
                        "text": text,
                        "metadata": metadata or {},
                        "score": round(score, 4),
                        "semantic_score": round(score, 4),
                        "keyword_score": 0.0,
                        "retrieval_mode": "semantic",
                    }
                )
            outputs.append(output)

        return outputs

    def _exact_faq_matches(
        self,
        user_message: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Return exact FAQ-question matches from the lightweight lexical cache.

        FAQ rows store the question in ``entity_name``. If the user asks that
        exact normalized question, the matching FAQ is authoritative evidence and
        should not be lost because an LLM rewrite generalized the wording.
        """
        target = normalize_text(user_message)
        if not target:
            return []

        cache = self._load_corpus_cache()
        matches: list[dict[str, Any]] = []

        for index, metadata in enumerate(cache["metadatas"]):
            entity_type = normalize_text(
                str(metadata.get("entity_type") or metadata.get("category") or "")
            )
            if entity_type != "faq":
                continue

            entity_name = normalize_text(str(metadata.get("entity_name") or ""))
            if entity_name != target:
                continue

            matches.append(
                {
                    "text": cache["documents"][index],
                    "metadata": metadata,
                    "score": 1.0,
                    "semantic_score": 0.0,
                    "keyword_score": 1.0,
                    "retrieval_mode": "exact_faq",
                    "query_source": "original_exact",
                }
            )
            if len(matches) >= top_k:
                break

        return matches

    def _load_corpus_cache(self) -> dict[str, Any]:
        self._ensure_not_empty()
        count = self.collection.count()
        collection_name = self.collection.name

        if (
            RAGService._corpus_cache is not None
            and RAGService._corpus_cache_collection == collection_name
            and RAGService._corpus_cache_count == count
        ):
            return RAGService._corpus_cache

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        normalized: list[str] = []

        # Keep only the lightweight lexical fields in process memory.
        # Document embeddings stay persisted in Chroma and are fetched only for the
        # small candidate set that survives keyword filtering. This avoids loading
        # the full vector corpus into the long-lived FastAPI process.
        batch_size = 500
        for offset in range(0, count, batch_size):
            batch = self.collection.get(
                limit=min(batch_size, count - offset),
                offset=offset,
                include=["documents", "metadatas"],
            )
            batch_ids = batch.get("ids", []) or []
            batch_docs = batch.get("documents", []) or []
            batch_meta = batch.get("metadatas", []) or []

            for doc_id, text, metadata in zip(batch_ids, batch_docs, batch_meta):
                text = text or ""
                metadata = metadata or {}
                searchable = " ".join(
                    [
                        text,
                        str(metadata.get("entity_name") or ""),
                        str(metadata.get("entity_type") or ""),
                        str(metadata.get("destination_id") or ""),
                        str(metadata.get("category") or ""),
                    ]
                )
                ids.append(doc_id)
                documents.append(text)
                metadatas.append(metadata)
                normalized.append(normalize_text(searchable))

        cache = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
            "normalized": normalized,
        }
        RAGService._corpus_cache = cache
        RAGService._corpus_cache_collection = collection_name
        RAGService._corpus_cache_count = count
        print(f"[RAG] Built lexical cache: {count} Chroma documents")
        return cache

    def _load_faq_fallback_rows(self) -> list[dict[str, Any]]:
        """Recover FAQ rows from Chroma when raw JSON is absent in the image.

        ``postgres_loader`` writes FAQ columns into labeled text lines and keeps the
        question in ``entity_name``. Reconstructing these lightweight rows makes the
        FAQ-first path deployment-safe without requiring a database migration or
        Chroma rebuild.
        """
        cache = self._load_corpus_cache()
        rows: list[dict[str, Any]] = []

        def field(text: str, label: str) -> str:
            prefix = f"{label}:"
            for line in str(text or "").splitlines():
                if line.startswith(prefix):
                    return line[len(prefix):].strip()
            return ""

        for index, metadata in enumerate(cache["metadatas"]):
            entity_type = normalize_text(
                str(metadata.get("entity_type") or metadata.get("category") or "")
            )
            if entity_type != "faq":
                continue

            document_text = str(cache["documents"][index] or "")
            question = str(metadata.get("entity_name") or field(document_text, "Question")).strip()
            answer = field(document_text, "Answer") or document_text
            if not question or not answer:
                continue
            rows.append({
                "index": len(rows),
                "question": question,
                "answer": answer,
                "category": str(metadata.get("category") or field(document_text, "Category") or "General"),
                "subcategory": field(document_text, "Subcategory"),
                "source_url": str(metadata.get("source_url") or "https://vinpearl.com/en/faqs"),
                "language": str(metadata.get("content_language") or "en"),
                "source_path": "chroma:faq",
            })

        return rows

    @staticmethod
    def _phrase_in_text(text: str, phrase: str) -> bool:
        if not text or not phrase:
            return False
        return f" {phrase} " in f" {text} "

    def keyword_candidates(
        self,
        destination: dict[str, Any] | None,
        intent: str | None,
        preferred_entity_types: set[str],
        max_candidates: int = 300,
        strict_entity_types: bool = False,
        require_destination_id_match: bool = False,
    ) -> list[dict[str, Any]]:
        if not destination:
            return []

        aliases = [normalize_text(a) for a in destination.get("aliases", [])]
        aliases = [a for a in aliases if a]
        destination_id = str(destination.get("id") or "")
        normalized_destination_id = normalize_text(destination_id)

        cache = self._load_corpus_cache()
        candidates: list[dict[str, Any]] = []

        for index, searchable in enumerate(cache["normalized"]):
            metadata = cache["metadatas"][index]
            entity_type = str(metadata.get("entity_type") or metadata.get("category") or "")
            metadata_destination = normalize_text(str(metadata.get("destination_id") or ""))

            matched_aliases = [
                alias for alias in aliases if self._phrase_in_text(searchable, alias)
            ]
            destination_id_match = bool(
                normalized_destination_id
                and metadata_destination
                and metadata_destination == normalized_destination_id
            )
            if require_destination_id_match and not destination_id_match:
                continue
            if not matched_aliases and not destination_id_match:
                continue
            if strict_entity_types and preferred_entity_types and entity_type not in preferred_entity_types:
                continue

            keyword_score = 1.0 if destination_id_match else 0.75
            if matched_aliases:
                longest = max(len(alias.split()) for alias in matched_aliases)
                keyword_score += min(0.15, longest * 0.05)
            if preferred_entity_types and entity_type in preferred_entity_types:
                keyword_score += 0.20

            candidates.append(
                {
                    "id": cache["ids"][index],
                    "text": cache["documents"][index],
                    "metadata": metadata,
                    "keyword_score": round(keyword_score, 4),
                    "matched_aliases": matched_aliases[:5],
                    "matched_destination_id": destination_id,
                    "matched_destination_name": (
                        destination.get("name_vi")
                        or destination.get("name_en")
                        or destination_id
                    ),
                    "intent": intent,
                }
            )

        candidates.sort(
            key=lambda item: (
                float(item.get("keyword_score", 0.0)),
                str(item.get("metadata", {}).get("entity_type") or ""),
            ),
            reverse=True,
        )
        return candidates[:max_candidates]

    @staticmethod
    def _is_broad_discovery_query(query: str, intent: str | None) -> bool:
        normalized = normalize_text(query)
        if intent not in {"attraction", "service", "hotel"}:
            return False
        broad_hints = (
            "what is there", "what else", "things to do", "travel information",
            "tourism information", "attractions and entertainment",
            "attractions experiences", "services and attractions",
            "co gi", "con gi", "du lich",
        )
        return any(hint in normalized for hint in broad_hints) or len(normalized.split()) <= 8

    @staticmethod
    def _entity_type_bonus(entity_type: str, intent: str | None, broad: bool) -> float:
        if not broad:
            return 0.0
        if intent == "attraction":
            return {
                "booking_product": 0.19,
                "complex": 0.18,
                "destination_highlight": 0.15,
                "destination": 0.14,
                "attraction": 0.10,
                "attraction_itinerary_day": 0.04,
            }.get(entity_type, 0.0)
        if intent == "service":
            return {
                "booking_product": 0.18,
                "property": 0.16,
                "complex": 0.15,
                "destination_highlight": 0.14,
                "dining_service": 0.10,
                "amenity": 0.08,
                "attraction": 0.08,
            }.get(entity_type, 0.0)
        if intent == "hotel":
            return {
                "property": 0.18,
                "destination": 0.14,
                "complex": 0.12,
                "room": 0.08,
                "dining_service": 0.06,
            }.get(entity_type, 0.0)
        return 0.0

    @staticmethod
    def _is_child_show_entity(entity_name: str) -> bool:
        normalized = normalize_text(entity_name)
        hints = (
            "show", "performance", "street performance", "song",
            "little mermaid", "once", "charm of venice", "quintessence",
            "rhythm of ocean",
        )
        return any(hint in normalized for hint in hints)

    @classmethod
    def _select_diverse_ranked(
        cls,
        ranked: list[dict[str, Any]],
        top_k: int,
        intent: str | None,
        broad: bool,
    ) -> list[dict[str, Any]]:
        if not broad:
            return ranked[:top_k]

        selected: list[dict[str, Any]] = []
        seen_entities: set[str] = set()
        seen_types: dict[str, int] = {}

        # First pass: favor broad/parent entities and keep entity/type coverage.
        broad_types = {
            "destination", "complex", "destination_highlight", "property",
            "booking_product", "attraction", "dining_service", "amenity",
        }
        for item in ranked:
            metadata = item.get("metadata", {}) or {}
            entity_type = str(metadata.get("entity_type") or metadata.get("category") or "")
            entity_name = normalize_text(str(metadata.get("entity_name") or ""))
            if entity_name and entity_name in seen_entities:
                continue
            if entity_type not in broad_types:
                continue
            # Do not let many child-show pages consume the context for a generic
            # destination discovery question. One such page is enough as evidence.
            if cls._is_child_show_entity(str(metadata.get("entity_name") or "")):
                if seen_types.get("child_show", 0) >= 1:
                    continue
                seen_types["child_show"] = seen_types.get("child_show", 0) + 1
            if seen_types.get(entity_type, 0) >= 3:
                continue
            selected.append(item)
            if entity_name:
                seen_entities.add(entity_name)
            seen_types[entity_type] = seen_types.get(entity_type, 0) + 1
            if len(selected) >= top_k:
                return selected

        # Second pass: fill remaining slots with the best distinct entities.
        for item in ranked:
            metadata = item.get("metadata", {}) or {}
            entity_name = normalize_text(str(metadata.get("entity_name") or ""))
            if entity_name and entity_name in seen_entities:
                continue
            selected.append(item)
            if entity_name:
                seen_entities.add(entity_name)
            if len(selected) >= top_k:
                break
        return selected

    def _find_named_entity_mentions(
        self,
        *texts: str,
        max_entities: int = 6,
    ) -> list[dict[str, Any]]:
        """Find corpus entity names literally/faithfully present in the request.

        Long-name prefixes are accepted only when that shortened alias identifies a
        single canonical entity in the corpus. This keeps useful aliases such as a
        hotel name without a brand suffix, while preventing a shared catalog prefix
        (for example ``[Venue] - Product A/B/C``) from making one venue mention look
        like many explicitly named products.
        """
        combined = normalize_text(" ".join(str(value or "") for value in texts))
        if not combined:
            return []

        cache = self._load_corpus_cache()

        def literal_aliases(name: str, normalized_name: str) -> list[str]:
            aliases = [normalized_name]
            for delimiter in (",", " - ", " – ", " — "):
                if delimiter in name:
                    prefix = normalize_text(name.split(delimiter, 1)[0])
                    if prefix and prefix not in aliases:
                        aliases.append(prefix)
            for suffix in ("affiliated by melia", "affiliated by meliá"):
                if suffix in normalized_name:
                    prefix = normalize_text(normalized_name.replace(suffix, ""))
                    prefix = prefix.strip(" ,:-–—")
                    if prefix and prefix not in aliases:
                        aliases.append(prefix)
            return aliases

        entries: list[dict[str, Any]] = []
        alias_owners: dict[str, set[tuple[str, str]]] = {}
        for index, metadata in enumerate(cache["metadatas"]):
            entity_type = str(metadata.get("entity_type") or metadata.get("category") or "entity").strip() or "entity"
            if normalize_text(entity_type) == "faq":
                continue
            name = str(metadata.get("entity_name") or "").strip()
            normalized_name = normalize_text(name)
            if not normalized_name:
                continue
            key = (entity_type, normalized_name)
            aliases = literal_aliases(name, normalized_name)
            entries.append({
                "index": index,
                "key": key,
                "name": name,
                "normalized_name": normalized_name,
                "entity_type": entity_type,
                "aliases": aliases,
            })
            # Full canonical names remain matchable even when duplicated in metadata.
            # Only shortened aliases need uniqueness protection.
            for alias in aliases[1:]:
                alias_owners.setdefault(alias, set()).add(key)

        by_name: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in entries:
            aliases = [entry["normalized_name"]]
            aliases.extend(
                alias
                for alias in entry["aliases"][1:]
                if len(alias_owners.get(alias, set())) == 1
            )

            matched_alias = ""
            for alias in aliases:
                tokens = alias.split()
                # Single-token names are too broad for substring matching unless the
                # entire current request is that entity name.
                if len(tokens) == 1 and combined != alias:
                    continue
                if len(tokens) >= 2 and self._phrase_in_text(combined, alias):
                    matched_alias = alias
                    break
            if not matched_alias:
                continue

            key = entry["key"]
            bucket = by_name.setdefault(
                key,
                {
                    "name": entry["name"],
                    "normalized_name": entry["normalized_name"],
                    "type": entry["entity_type"],
                    "indices": [],
                },
            )
            bucket["indices"].append(entry["index"])

        # Prefer the most specific/longest named mentions and suppress a shorter
        # candidate fully contained in an already selected longer name.
        ranked = sorted(
            by_name.values(),
            key=lambda item: (
                len(str(item["normalized_name"]).split()),
                len(str(item["normalized_name"])),
            ),
            reverse=True,
        )
        selected: list[dict[str, Any]] = []
        selected_names: list[str] = []
        for item in ranked:
            name_norm = str(item["normalized_name"])
            if any(
                name_norm != longer and self._phrase_in_text(longer, name_norm)
                for longer in selected_names
            ):
                continue
            selected.append(item)
            selected_names.append(name_norm)
            if len(selected) >= max_entities:
                break
        return selected

    def _retrieve_named_entity_branches(
        self,
        entities: list[dict[str, Any]],
        query: str,
        per_entity_k: int = 2,
    ) -> list[dict[str, Any]]:
        """Retrieve evidence independently for every named entity mention.

        Comparison/synthesis requests therefore cannot lose one side merely because
        a single embedding query spends all top-k slots on the other side.
        """
        if not entities:
            return []
        cache = self._load_corpus_cache()
        groups: list[list[dict[str, Any]]] = []
        for entity in entities:
            candidates: list[dict[str, Any]] = []
            for index in entity.get("indices") or []:
                metadata = cache["metadatas"][index]
                candidates.append(
                    {
                        "id": cache["ids"][index],
                        "text": cache["documents"][index],
                        "metadata": metadata,
                        "keyword_score": 1.0,
                        "matched_aliases": [entity.get("normalized_name")],
                    }
                )
            branch_query = f"{entity.get('name')}. {query}".strip()
            ranked = self._rerank_candidates(
                query=branch_query,
                candidates=candidates,
                top_k=max(1, per_entity_k),
                preferred_entity_types={str(entity.get("type") or "")},
                intent=None,
            )
            for item in ranked:
                item["matched_named_entity"] = str(entity.get("name") or "")
                item["retrieval_mode"] = "named_entity_branch"
            groups.append(ranked)

        # Round-robin guarantees at least the best source for each entity before a
        # second source from any one branch can consume context budget.
        merged: list[dict[str, Any]] = []
        max_len = max((len(group) for group in groups), default=0)
        for offset in range(max_len):
            for group in groups:
                if offset < len(group):
                    merged.append(group[offset])
        return self._dedupe_documents(merged)

    def _rerank_candidates(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
        preferred_entity_types: set[str],
        intent: str | None = None,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        # Documents were already embedded during ingestion. Fetch vectors only for
        # the keyword-filtered candidate IDs instead of retaining all corpus vectors
        # in process memory. The ONNX INT8 model is still used for the query vector.
        candidate_ids = [str(item.get("id") or "") for item in candidates]
        candidate_ids = [doc_id for doc_id in candidate_ids if doc_id]
        if not candidate_ids:
            return []

        stored = self.collection.get(
            ids=candidate_ids,
            include=["embeddings"],
        )
        stored_ids = stored.get("ids", []) or []
        stored_embeddings = stored.get("embeddings")

        embedding_map: dict[str, np.ndarray] = {}
        if stored_embeddings is not None:
            for doc_id, embedding in zip(stored_ids, stored_embeddings):
                if embedding is not None:
                    embedding_map[str(doc_id)] = np.asarray(
                        embedding,
                        dtype=np.float32,
                    )

        candidates_with_vectors: list[dict[str, Any]] = []
        for item in candidates:
            vector = embedding_map.get(str(item.get("id") or ""))
            if vector is None:
                continue
            item_with_vector = dict(item)
            item_with_vector["embedding"] = vector
            candidates_with_vectors.append(item_with_vector)

        candidates = candidates_with_vectors
        if not candidates:
            return []

        query_vector = np.asarray(self.embed_query(query), dtype=np.float32)
        candidate_vectors = np.asarray(
            [item["embedding"] for item in candidates],
            dtype=np.float32,
        )
        semantic_scores = candidate_vectors @ query_vector
        broad = self._is_broad_discovery_query(query, intent)

        ranked: list[dict[str, Any]] = []
        for item, semantic_score in zip(candidates, semantic_scores.tolist()):
            metadata = item.get("metadata", {}) or {}
            entity_type = str(metadata.get("entity_type") or metadata.get("category") or "")
            entity_name = str(metadata.get("entity_name") or "")
            preferred_bonus = 0.08 if preferred_entity_types and entity_type in preferred_entity_types else 0.0
            coverage_bonus = self._entity_type_bonus(entity_type, intent, broad)
            child_penalty = 0.0
            if broad and self._is_child_show_entity(entity_name):
                child_penalty = 0.08

            keyword_score = float(item.get("keyword_score", 0.0))
            final_score = (
                0.67 * float(semantic_score)
                + 0.25 * min(keyword_score, 1.0)
                + preferred_bonus
                + coverage_bonus
                - child_penalty
            )
            ranked.append(
                {
                    "text": item["text"],
                    "metadata": metadata,
                    "score": round(max(0.0, min(1.0, final_score)), 4),
                    "semantic_score": round(max(0.0, min(1.0, float(semantic_score))), 4),
                    "keyword_score": round(keyword_score, 4),
                    "retrieval_mode": "keyword_then_embedding",
                    "matched_aliases": item.get("matched_aliases", []),
                    "matched_destination_id": item.get("matched_destination_id"),
                    "matched_destination_name": item.get("matched_destination_name"),
                }
            )

        ranked.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return self._select_diverse_ranked(ranked, top_k=top_k, intent=intent, broad=broad)

    @staticmethod
    def _dedupe_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        output: list[dict[str, Any]] = []
        for item in documents:
            metadata = item.get("metadata", {}) or {}
            key = (
                str(metadata.get("entity_type") or ""),
                str(metadata.get("entity_id") or metadata.get("entity_name") or item.get("text", "")[:120]),
            )
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    def hybrid_search(
        self,
        query: str,
        user_message: str = "",
        top_k: int | None = None,
        resolved_destinations: list[dict[str, Any]] | None = None,
        excluded_destination_ids: list[str] | None = None,
        excluded_entity_names: list[str] | None = None,
        planned_intents: list[str] | None = None,
        planned_queries: list[dict[str, Any]] | None = None,
        force_price_requested: bool = False,
        force_cost_estimate_requested: bool = False,
        exhaustive_requested: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Run destination-aware retrieval with native multi-intent support.

        A multi-clause request such as "services + golf + events" is split into
        independent intent retrieval branches. One missing branch does not erase the
        evidence found for the others. The merged document set is still bounded by
        the normal context budget downstream.
        """
        k = top_k or self.settings.top_k
        excluded_destination_norms = {
            normalize_text(str(value or ""))
            for value in (excluded_destination_ids or [])
            if normalize_text(str(value or ""))
        }
        excluded_entity_norms = {
            normalize_text(str(value or ""))
            for value in (excluded_entity_names or [])
            if normalize_text(str(value or ""))
        }
        has_exclusions = bool(excluded_destination_norms or excluded_entity_norms)
        # Retrieve a slightly wider pool when exclusions are active so filtering one
        # previously recommended entity does not leave the answer with no alternatives.
        search_k = max(k * 2, k + 4) if has_exclusions else k

        def document_is_excluded(item: dict[str, Any]) -> bool:
            metadata = item.get("metadata", {}) or {}
            destination_norm = normalize_text(str(metadata.get("destination_id") or ""))
            entity_norm = normalize_text(str(metadata.get("entity_name") or ""))
            return bool(
                (destination_norm and destination_norm in excluded_destination_norms)
                or (entity_norm and entity_norm in excluded_entity_norms)
            )

        parsed = parse_retrieval_query(user_message=user_message, rag_query=query)
        budget_vnd = parsed.get("budget_vnd")
        try:
            budget_vnd = int(budget_vnd) if budget_vnd is not None else None
        except (TypeError, ValueError):
            budget_vnd = None
        has_budget_constraint = bool(parsed.get("has_budget_constraint") and budget_vnd)
        price_requested = bool(parsed.get("price_requested")) or bool(force_price_requested) or bool(force_cost_estimate_requested)
        booking_evidence_preferred = bool(parsed.get("booking_evidence_preferred")) or bool(force_price_requested) or bool(force_cost_estimate_requested)
        cost_estimate_requested = bool(parsed.get("cost_estimate_requested")) or bool(force_cost_estimate_requested)

        # When the semantic context resolver has run, its closed/validated
        # destination set is authoritative. This prevents a later text parser from
        # re-guessing destinations from an LLM rewrite and losing conversation
        # references (or adding locations that were merely mentioned elsewhere).
        if resolved_destinations is not None:
            catalog = load_destination_catalog()
            destinations: list[dict[str, Any]] = []
            seen_destination_ids: set[str] = set()
            for raw in resolved_destinations:
                destination_id = str(raw.get("id") or "").strip()
                if not destination_id or destination_id in seen_destination_ids:
                    continue
                canonical = catalog.get(destination_id)
                if not canonical:
                    continue
                destinations.append(dict(canonical))
                seen_destination_ids.add(destination_id)
        else:
            destinations = list(parsed.get("destinations") or [])

        intents = list(parsed.get("intents") or [])
        planned_added: list[str] = []
        for planned in planned_intents or []:
            planned_name = str(planned or "").strip().lower()
            if planned_name in INTENT_ENTITY_TYPES and planned_name not in intents:
                intents.append(planned_name)
                planned_added.append(planned_name)
        task_query_variants: list[tuple[str, str, list[str]]] = []
        seen_task_queries: set[str] = set()
        for index, raw in enumerate(planned_queries or [], start=1):
            if not isinstance(raw, dict):
                continue
            task_query = str(raw.get("query") or "").strip()
            normalized_task_query = normalize_text(task_query)
            if not normalized_task_query or normalized_task_query in seen_task_queries:
                continue
            seen_task_queries.add(normalized_task_query)
            task_id = str(raw.get("task_id") or f"t{index}").strip() or f"t{index}"
            task_intents = [
                str(value or "").strip().lower()
                for value in (raw.get("intents") or [])
                if str(value or "").strip().lower() in INTENT_ENTITY_TYPES
            ]
            task_query_variants.append((f"task:{task_id}", task_query, task_intents))
        primary_intent = intents[0] if intents else parsed.get("intent")
        named_entities = self._find_named_entity_mentions(user_message, query)
        named_entity_types = {str(item.get("type") or "").strip().lower() for item in named_entities}

        # Keep legacy behavior for a query where no explicit intent can be detected.
        retrieval_intents: list[str | None] = intents or [primary_intent]
        is_multi_intent = len([item for item in retrieval_intents if item]) > 1

        all_candidates = 0
        missing_destination_ids: list[str] = []
        documents: list[dict[str, Any]] = []
        intent_results: dict[str, dict[str, Any]] = {}

        # ------------------------------------------------------------------
        # FAQ-FIRST RETRIEVAL
        # ------------------------------------------------------------------
        # FAQ questions must be checked BEFORE destination/entity filtering. The old
        # ordering could detect ``Phu Quoc`` + ``attraction`` and then restrict the
        # candidate set to attraction/complex rows, making the exact FAQ invisible.
        # That is precisely why "Can I bring my pet into Grand World Phu Quoc?"
        # previously retrieved two unrelated attraction articles even though the FAQ
        # JSON contained the authoritative answer.
        #
        # Exact FAQ equality is always allowed. Semantic FAQ matching is skipped only
        # for broad multi-category discovery queries, where a narrow FAQ answer should
        # not replace normal destination consultation.
        generic_discovery_intents = {"attraction", "hotel", "dining", "service"}
        combined_query_for_faq_gate = normalize_text(f"{user_message} {query}")
        policy_or_faq_intent = bool({"policy", "payment"} & set(intents))
        entity_detail_markers = (
            "chi tiet", "chi tiết", "thong tin", "thông tin", "review", "danh gia", "đánh giá",
            "details", "detail", "tell me about", "gioi thieu", "giới thiệu",
        )
        has_specific_catalog_entity = bool(
            named_entities
            and named_entity_types & {"property", "room", "complex", "attraction", "booking_product", "dining_service", "golf_course", "mice_venue"}
        )
        entity_detail_request = has_specific_catalog_entity and any(
            marker in combined_query_for_faq_gate for marker in entity_detail_markers
        )
        # Broad discovery/planning and specific entity-detail requests stay on the
        # catalog/property retrieval path. Exact FAQ equality is still allowed inside
        # FAQMatcher; this only disables semantic FAQ hijacking such as matching
        # "Where are Vinpearl's properties?" for "chi tiết về Vinpearl Cua Hoi Resort".
        broad_discovery_request = (
            len(intents) >= 3
            and generic_discovery_intents.issubset(set(intents))
        )
        skip_faq_semantic = (
            broad_discovery_request
            or (entity_detail_request and not policy_or_faq_intent)
        )
        faq_routing_context = " ".join(
            str(value or "").strip()
            for destination in destinations
            for value in (
                destination.get("id"),
                destination.get("name_en"),
                destination.get("name_vi"),
                destination.get("matched_alias"),
            )
            if str(value or "").strip()
        )
        faq_documents, faq_diagnostics = self.faq_matcher.match(
            original_query=str(user_message or "").strip(),
            rewritten_query=str(query or "").strip(),
            top_k=min(3, max(1, k)),
            skip_semantic=skip_faq_semantic,
            routing_context=faq_routing_context,
            additional_queries=[
                (source, task_query)
                for source, task_query, _task_intents in task_query_variants
            ],
        )

        supplemental_faq_documents: list[dict[str, Any]] = []
        supplemental_faq_intent: str | None = None

        if faq_diagnostics.get("accepted") and faq_documents and not is_multi_intent:
            primary_destination = destinations[0] if destinations else None
            destination_ids = [str(item.get("id") or "") for item in destinations]
            destination_names = [
                str(item.get("name_vi") or item.get("name_en") or item.get("id") or "")
                for item in destinations
            ]

            # Carry resolved destination identity into the FAQ evidence. This keeps
            # downstream source filtering/citation selection consistent even though
            # the raw FAQ row itself does not store a normalized destination_id.
            if primary_destination:
                for item in faq_documents:
                    item["matched_destination_id"] = str(primary_destination.get("id") or "")
                    item["matched_destination_name"] = str(
                        primary_destination.get("name_vi")
                        or primary_destination.get("name_en")
                        or primary_destination.get("id")
                        or ""
                    )
                    metadata = item.get("metadata", {}) or {}
                    if not metadata.get("destination_id"):
                        metadata["destination_id"] = str(primary_destination.get("id") or "")
                    item["metadata"] = metadata

            matched_intent_names = intents or ([primary_intent] if primary_intent else ["faq"])
            for item in faq_documents:
                item["matched_intent"] = primary_intent or "faq"
            for intent_name in matched_intent_names:
                if not intent_name:
                    continue
                intent_results[str(intent_name)] = {
                    "status": "found",
                    "document_count": len(faq_documents),
                    "candidate_count": int(faq_diagnostics.get("candidate_count") or 0),
                    "best_score": round(float(faq_diagnostics.get("best_score") or 0.0), 4),
                    "query": query,
                    "missing_destination_ids": [],
                    "faq_match": True,
                    "matched_question": faq_diagnostics.get("matched_question"),
                }

            faq_mode = str(faq_diagnostics.get("mode") or "faq_semantic")
            diagnostics = {
                "mode": faq_mode,
                "destination_id": primary_destination.get("id") if primary_destination else None,
                "destination_name": (
                    primary_destination.get("name_vi") or primary_destination.get("name_en")
                    if primary_destination else None
                ),
                "destinations": destinations,
                "destination_ids": destination_ids,
                "destination_names": destination_names,
                "intent": primary_intent or "faq",
                "intents": intents or ["faq"],
                "explicit_intents": list(parsed.get("explicit_intents") or []),
                "constraint_derived_intents": list(parsed.get("constraint_derived_intents") or []),
                "planned_intents": planned_added,
                "has_budget_constraint": has_budget_constraint,
                "budget_vnd": budget_vnd,
                "price_requested": price_requested,
                "booking_evidence_preferred": booking_evidence_preferred,
                "cost_estimate_requested": cost_estimate_requested,
                "booking_focus_document_count": 0,
                "intent_origin": ("request_plan" if planned_added else str(parsed.get("intent_origin") or "none")),
                "intent_results": intent_results,
                "keyword_candidate_count": int(faq_diagnostics.get("candidate_count") or 0),
                "missing_destination_ids": [],
                "faq_match": faq_diagnostics,
            }
            print(
                "[FAQ RETRIEVAL] "
                f"mode={faq_mode} accepted=true "
                f"question={faq_diagnostics.get('matched_question')!r} "
                f"score={faq_diagnostics.get('best_score')} "
                f"semantic={faq_diagnostics.get('best_semantic_score')} "
                f"lexical={faq_diagnostics.get('best_lexical_score')} "
                f"weighted_f1={faq_diagnostics.get('best_weighted_f1')} "
                f"query_coverage={faq_diagnostics.get('best_query_coverage')} "
                f"predicate_count={faq_diagnostics.get('best_predicate_count')} "
                f"predicate_ratio={faq_diagnostics.get('best_predicate_ratio')} "
                f"margin={faq_diagnostics.get('margin')} "
                f"selected_rank={faq_diagnostics.get('selected_candidate_rank', 1)}"
            )
            return faq_documents, diagnostics

        if faq_diagnostics.get("accepted") and faq_documents and is_multi_intent:
            supplemental_faq_intent = next(
                (value for value in ("policy", "payment") if value in intents),
                primary_intent or "faq",
            )
            primary_destination = destinations[0] if destinations else None
            for item in faq_documents:
                copied = dict(item)
                copied["matched_intent"] = supplemental_faq_intent
                if primary_destination:
                    copied["matched_destination_id"] = str(primary_destination.get("id") or "")
                    copied["matched_destination_name"] = str(
                        primary_destination.get("name_vi")
                        or primary_destination.get("name_en")
                        or primary_destination.get("id")
                        or ""
                    )
                    metadata = dict(copied.get("metadata", {}) or {})
                    if not metadata.get("destination_id"):
                        metadata["destination_id"] = str(primary_destination.get("id") or "")
                    copied["metadata"] = metadata
                supplemental_faq_documents.append(copied)
            print(
                "[FAQ RETRIEVAL] "
                f"mode={faq_diagnostics.get('mode')} accepted=true supplemental=true "
                f"intent={supplemental_faq_intent} "
                f"question={faq_diagnostics.get('matched_question')!r} "
                f"score={faq_diagnostics.get('best_score')} "
                f"semantic={faq_diagnostics.get('best_semantic_score')} "
                f"lexical={faq_diagnostics.get('best_lexical_score')} "
                f"predicate_count={faq_diagnostics.get('best_predicate_count')} "
                f"predicate_ratio={faq_diagnostics.get('best_predicate_ratio')}"
            )

        if (
            not faq_diagnostics.get("accepted")
            and faq_diagnostics.get("mode") not in {None, "faq_skipped"}
        ):
            print(
                "[FAQ RETRIEVAL] "
                f"mode={faq_diagnostics.get('mode')} accepted=false "
                f"candidate={faq_diagnostics.get('matched_question')!r} "
                f"score={faq_diagnostics.get('best_score')} "
                f"semantic={faq_diagnostics.get('best_semantic_score')} "
                f"lexical={faq_diagnostics.get('best_lexical_score')} "
                f"weighted_f1={faq_diagnostics.get('best_weighted_f1')} "
                f"query_coverage={faq_diagnostics.get('best_query_coverage')} "
                f"predicate_count={faq_diagnostics.get('best_predicate_count')} "
                f"predicate_ratio={faq_diagnostics.get('best_predicate_ratio')} "
                f"margin={faq_diagnostics.get('margin')}"
            )

        if named_entities and has_exclusions:
            cache = self._load_corpus_cache()
            filtered_named_entities: list[dict[str, Any]] = []
            for item in named_entities:
                entity_norm = normalize_text(str(item.get("normalized_name") or item.get("name") or ""))
                if entity_norm and entity_norm in excluded_entity_norms:
                    continue
                excluded_by_destination = False
                for index in item.get("indices", []) or []:
                    try:
                        metadata = cache["metadatas"][int(index)] or {}
                    except (TypeError, ValueError, IndexError):
                        continue
                    destination_norm = normalize_text(str(metadata.get("destination_id") or ""))
                    if destination_norm and destination_norm in excluded_destination_norms:
                        excluded_by_destination = True
                        break
                if not excluded_by_destination:
                    filtered_named_entities.append(item)
            named_entities = filtered_named_entities

        # Destination-aware retrieval already owns resolved destinations. Avoid
        # retrieving the same destination/destination_alias again as a named entity:
        # those duplicate generic chunks can consume context ahead of a specific
        # booking product. Other named entities (property/product/promotion/...)
        # keep the existing independent branch behavior unchanged.
        if destinations and named_entities:
            destination_aliases: set[str] = set()
            for destination in destinations:
                values = [
                    destination.get("id"),
                    destination.get("name_en"),
                    destination.get("name_vi"),
                    *(destination.get("aliases") or []),
                ]
                for value in values:
                    normalized_value = normalize_text(str(value or ""))
                    if normalized_value:
                        destination_aliases.add(normalized_value)
            named_entities = [
                item
                for item in named_entities
                if not (
                    normalize_text(str(item.get("type") or ""))
                    in {"destination", "destination alias", "destination_alias"}
                    and normalize_text(str(item.get("normalized_name") or item.get("name") or ""))
                    in destination_aliases
                )
            ]

        named_entity_documents = self._retrieve_named_entity_branches(
            named_entities,
            query=query,
            per_entity_k=2,
        )
        if named_entities:
            print(
                "[NAMED ENTITY RETRIEVAL] "
                f"entities={[item.get('name') for item in named_entities]} "
                f"documents={len(named_entity_documents)}"
            )

        booking_focus_documents: list[dict[str, Any]] = []
        if destinations and booking_evidence_preferred:
            # Keep the existing destination+intent focused branches exactly as they
            # are, and add a supplemental booking-only lane that uses the faithful
            # standalone query. This preserves specific entity/price/package/ticket
            # terms without removing the generic branch isolation that broad
            # destination discovery relies on.
            per_destination_groups: list[list[dict[str, Any]]] = []
            booking_focus_k = max(1, min(3, k))
            for destination in destinations:
                candidates = self.keyword_candidates(
                    destination=destination,
                    intent=None,
                    preferred_entity_types={"booking_product"},
                    max_candidates=300,
                    strict_entity_types=True,
                )
                if not candidates:
                    per_destination_groups.append([])
                    continue
                booking_rerank_k = (
                    min(20, len(candidates))
                    if price_requested
                    else max(booking_focus_k, 3)
                )
                ranked = self._rerank_candidates(
                    query=str(query or user_message or ""),
                    candidates=candidates,
                    top_k=booking_rerank_k,
                    preferred_entity_types={"booking_product"},
                    intent=None,
                )
                if price_requested:
                    price_ranked = [
                        item for item in ranked if text_has_price_evidence(item.get("text", ""))
                    ]
                    if price_ranked:
                        ranked = price_ranked
                for item in ranked[:booking_focus_k]:
                    item["booking_focus"] = True
                    item["intent_query"] = str(query or user_message or "")
                per_destination_groups.append(ranked[:booking_focus_k])

            max_booking_len = max((len(group) for group in per_destination_groups), default=0)
            for index in range(max_booking_len):
                for group in per_destination_groups:
                    if index < len(group):
                        booking_focus_documents.append(group[index])
            booking_focus_documents = self._dedupe_documents(booking_focus_documents)[:booking_focus_k]

        if destinations:
            # Normal requests stay top-k bounded. Exhaustive requests are a different
            # coverage contract: enumerate every canonical indexed entity that falls
            # inside the resolved destination + intent entity-type scope. This avoids
            # pretending a top-k sample is a complete catalog while leaving ordinary
            # RAG latency/noise unchanged.
            per_intent_k = max(2, ceil(k / max(1, len(retrieval_intents))))
            per_intent_k = min(max(per_intent_k, 3 if is_multi_intent else 2), 5)

            for raw_intent in retrieval_intents:
                intent = raw_intent or primary_intent
                preferred_entity_types = set(
                    (parsed.get("preferred_entity_types_by_intent") or {}).get(intent or "", [])
                )
                if not preferred_entity_types:
                    preferred_entity_types = set(parsed.get("preferred_entity_types") or [])

                focused_query = (
                    build_intent_query(intent, destinations, query)
                    if intent and is_multi_intent
                    else query
                )
                branch_docs: list[dict[str, Any]] = []
                branch_candidates = 0
                branch_missing: list[str] = []

                per_destination_k = max(2, ceil(per_intent_k / max(1, len(destinations))))
                per_destination_docs: list[list[dict[str, Any]]] = []
                for destination in destinations:
                    exhaustive_types = set(INTENT_ENTITY_TYPES.get(intent or "", set()))
                    effective_types = preferred_entity_types or exhaustive_types
                    candidates = self.keyword_candidates(
                        destination=destination,
                        intent=intent,
                        preferred_entity_types=effective_types,
                        # An exhaustive branch is meaningful only inside its typed
                        # catalog lane. Normal multi-intent behavior is unchanged.
                        strict_entity_types=(bool(effective_types) if exhaustive_requested else (is_multi_intent and bool(preferred_entity_types))),
                        # Exhaustive enumeration must not silently inherit the normal
                        # 300-candidate ceiling. The corpus cache itself is finite, so
                        # this safely means "all indexed candidates in scope".
                        max_candidates=1000000 if exhaustive_requested else 300,
                        require_destination_id_match=bool(exhaustive_requested),
                    )
                    branch_candidates += len(candidates)
                    all_candidates += len(candidates)
                    if not candidates:
                        destination_id = str(destination.get("id") or "")
                        branch_missing.append(destination_id)
                        if destination_id not in missing_destination_ids:
                            missing_destination_ids.append(destination_id)
                        per_destination_docs.append([])
                        continue

                    if exhaustive_requested:
                        # Destination metadata + strict entity type already provide a
                        # deterministic scope. Dedupe all chunks to one representative
                        # source per canonical entity instead of semantically cutting
                        # the branch back down to top-k.
                        ranked: list[dict[str, Any]] = []
                        seen_entities: set[tuple[str, str]] = set()
                        for candidate in candidates:
                            metadata = candidate.get("metadata", {}) or {}
                            entity_type = str(metadata.get("entity_type") or metadata.get("category") or "")
                            entity_key = str(
                                metadata.get("entity_id")
                                or metadata.get("entity_name")
                                or candidate.get("id")
                                or candidate.get("text", "")[:120]
                            )
                            dedupe_key = (entity_type, entity_key)
                            if dedupe_key in seen_entities:
                                continue
                            seen_entities.add(dedupe_key)
                            copied = dict(candidate)
                            keyword_score = float(candidate.get("keyword_score", 0.0) or 0.0)
                            copied["score"] = round(max(0.0, min(1.0, keyword_score)), 4)
                            copied["semantic_score"] = 0.0
                            copied["retrieval_mode"] = "keyword_exhaustive_catalog"
                            copied["matched_intent"] = intent
                            copied["intent_query"] = focused_query
                            ranked.append(copied)
                        ranked.sort(
                            key=lambda item: (
                                str((item.get("metadata", {}) or {}).get("entity_type") or ""),
                                str((item.get("metadata", {}) or {}).get("entity_name") or "").casefold(),
                            )
                        )
                    else:
                        rerank_k = per_destination_k
                        if has_budget_constraint and intent == "promotion":
                            # Price-fit is a hard constraint, so inspect a wider semantic
                            # shortlist before cutting to the normal per-destination top-k.
                            rerank_k = max(per_destination_k, min(20, len(candidates)))
                        ranked = self._rerank_candidates(
                            query=focused_query,
                            candidates=candidates,
                            top_k=rerank_k,
                            preferred_entity_types=preferred_entity_types,
                            intent=intent,
                        )
                        if has_budget_constraint and intent == "promotion":
                            affordable_ranked: list[dict[str, Any]] = []
                            for item in ranked:
                                prices = _affordable_prices(item.get("text", ""), budget_vnd)
                                if not prices:
                                    continue
                                copied = dict(item)
                                copied["budget_constraint_vnd"] = budget_vnd
                                copied["budget_matched_prices"] = prices
                                affordable_ranked.append(copied)
                            ranked = affordable_ranked[:per_destination_k]
                        else:
                            ranked = ranked[:per_destination_k]
                        for item in ranked:
                            item["matched_intent"] = intent
                            item["intent_query"] = focused_query
                    per_destination_docs.append(ranked)

                # Round-robin across destinations inside each intent branch.
                max_len = max((len(group) for group in per_destination_docs), default=0)
                for index in range(max_len):
                    for group in per_destination_docs:
                        if index < len(group):
                            branch_docs.append(group[index])
                branch_docs = self._dedupe_documents(branch_docs)
                if not exhaustive_requested:
                    branch_docs = branch_docs[:per_intent_k]

                intent_key = intent or "general"
                best_score = max(
                    (float(item.get("score", 0.0) or 0.0) for item in branch_docs),
                    default=0.0,
                )
                intent_results[intent_key] = {
                    "status": "found" if branch_docs else "not_found",
                    "document_count": len(branch_docs),
                    "candidate_count": branch_candidates,
                    "best_score": round(best_score, 4),
                    "query": focused_query,
                    "missing_destination_ids": branch_missing,
                    "budget_constraint_vnd": budget_vnd if intent == "promotion" else None,
                    "budget_matched_prices": sorted({
                        price
                        for item in branch_docs
                        for price in (item.get("budget_matched_prices") or [])
                    }) if intent == "promotion" else [],
                    "constraint_satisfied": (
                        bool(branch_docs) if has_budget_constraint and intent == "promotion" else None
                    ),
                }
                documents.extend(branch_docs)

            # Preserve one branch's evidence from being deduped by another intent.
            seen: set[tuple[str, str, str]] = set()
            merged: list[dict[str, Any]] = []
            for item in documents:
                metadata = item.get("metadata", {}) or {}
                key = (
                    str(item.get("matched_intent") or ""),
                    str(metadata.get("entity_type") or ""),
                    str(metadata.get("entity_id") or metadata.get("entity_name") or item.get("text", "")[:120]),
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
            documents = merged

            mode = "keyword_multi_intent" if is_multi_intent else (
                "keyword_multi_destination" if len(destinations) > 1 else "keyword_then_embedding"
            )
            if exhaustive_requested:
                mode += "+exhaustive"
            if any(result.get("status") == "not_found" for result in intent_results.values()):
                mode += "_partial"
            if booking_focus_documents:
                documents = self._dedupe_documents(booking_focus_documents + documents)
                mode += "+booking_focus"
        else:
            # No destination was resolved. Preserve the user's original wording as
            # retrieval evidence instead of relying only on the LLM-rewritten query.
            # This specifically protects exact FAQ questions from rewrite drift while
            # keeping the rewritten query for multilingual/follow-up understanding.
            original_query = str(user_message or "").strip()
            rewritten_query = str(query or "").strip()

            exact_faq = self._exact_faq_matches(original_query, top_k=search_k)

            semantic_queries: list[tuple[str, str]] = []
            seen_queries: set[str] = set()

            # If an exact FAQ is already found, re-embedding the same original wording
            # adds no value. Keep the rewritten semantic branch only as supplemental
            # evidence, so this common FAQ case is not slower than the old path.
            if original_query and not exact_faq:
                normalized_original = normalize_text(original_query)
                if normalized_original:
                    semantic_queries.append(("original", original_query))
                    seen_queries.add(normalized_original)

            normalized_rewritten = normalize_text(rewritten_query)
            if rewritten_query and normalized_rewritten not in seen_queries:
                semantic_queries.append(("rewritten", rewritten_query))
                seen_queries.add(normalized_rewritten)

            # Atomic task goals are independent retrieval evidence. They are batched
            # with the original/rewritten queries, so a short contact-guidance task
            # can retrieve its FAQ even when the combined query is dominated by a
            # room, dining, price, or policy constraint.
            for task_source, task_query, _task_intents in task_query_variants:
                normalized_task_query = normalize_text(task_query)
                if normalized_task_query and normalized_task_query not in seen_queries:
                    semantic_queries.append((task_source, task_query))
                    seen_queries.add(normalized_task_query)

            # For corpus-wide retrieval, add one focused query per detected intent
            # in the SAME embedding/Chroma batch. This prevents a strong but wrong
            # entity type in the global top-k from crowding out valid evidence for
            # another requested branch (for example budget/service requests where
            # promotion rows are the useful evidence).
            focused_base_query = rewritten_query or original_query
            if intents and focused_base_query:
                for intent in intents:
                    focused_query = build_intent_query(intent, [], focused_base_query)
                    normalized_focused = normalize_text(focused_query)
                    if normalized_focused and normalized_focused not in seen_queries:
                        semantic_queries.append((f"intent:{intent}", focused_query))
                        seen_queries.add(normalized_focused)

            if booking_evidence_preferred and focused_base_query:
                booking_query = (
                    f"{focused_base_query} booking tickets packages prices"
                    if price_requested
                    else f"{focused_base_query} booking tickets packages"
                ).strip()
                normalized_booking = normalize_text(booking_query)
                if normalized_booking and normalized_booking not in seen_queries:
                    semantic_queries.append(("booking_focus", booking_query))
                    seen_queries.add(normalized_booking)

            # Pull a wider candidate pool only for intent-aware corpus search. The
            # final returned evidence is still capped to the configured top-k after
            # strict entity-type branch filtering below.
            semantic_pool_k = (
                max(search_k, min(30, search_k * 6)) if intents else search_k
            )
            semantic_groups = self.semantic_search_many(
                [item[1] for item in semantic_queries],
                top_k=semantic_pool_k,
            ) if semantic_queries else []

            merged_by_key: dict[tuple[str, str], dict[str, Any]] = {}

            def add_result(item: dict[str, Any], query_source: str) -> None:
                candidate = dict(item)
                candidate["query_source"] = query_source
                metadata = candidate.get("metadata", {}) or {}
                if query_source == "booking_focus":
                    entity_type = str(
                        metadata.get("entity_type") or metadata.get("source_table") or ""
                    ).strip()
                    if entity_type != "booking_product":
                        return
                    if price_requested and not text_has_price_evidence(candidate.get("text", "")):
                        return
                key = (
                    str(metadata.get("entity_type") or ""),
                    str(
                        metadata.get("entity_id")
                        or metadata.get("entity_name")
                        or candidate.get("text", "")[:120]
                    ),
                )
                existing = merged_by_key.get(key)
                if existing is None or float(candidate.get("score", 0.0) or 0.0) > float(
                    existing.get("score", 0.0) or 0.0
                ):
                    merged_by_key[key] = candidate

            for item in exact_faq:
                add_result(item, "original_exact")

            for (query_source, _semantic_query), group in zip(semantic_queries, semantic_groups):
                for item in group:
                    add_result(item, query_source)

            documents = sorted(
                merged_by_key.values(),
                key=lambda item: float(item.get("score", 0.0) or 0.0),
                reverse=True,
            )
            if not intents:
                documents = documents[:semantic_pool_k]

            if exact_faq:
                mode = "semantic_fallback_exact_faq"
            elif len(semantic_queries) > 2:
                mode = "semantic_multi_query"
            elif len(semantic_queries) > 1:
                mode = "semantic_dual_query"
            else:
                mode = "semantic_fallback"

        if has_exclusions:
            documents = [item for item in documents if not document_is_excluded(item)]
            named_entity_documents = [
                item for item in named_entity_documents if not document_is_excluded(item)
            ]

        if named_entity_documents:
            documents = self._dedupe_documents(named_entity_documents + documents)
            prefix = "named_entity_multi" if len(named_entities) > 1 else "named_entity"
            mode = f"{prefix}:{mode}"

        if has_exclusions:
            documents = [item for item in documents if not document_is_excluded(item)]
            # No-destination intent filtering below needs the widened semantic
            # pool; cap immediately only on paths that will not run that filter.
            if destinations or not intents:
                documents = documents[:k]

        # With no resolved destination the semantic search is corpus-wide. A raw
        # global top-k is not evidence for a detected intent. Build strict branch
        # evidence from the allowed entity types, then return ONLY the union of
        # those branch documents. This keeps retrieval diagnostics, the assessor,
        # answer context, and source citations on the same evidence set.
        if not destinations and intents:
            candidate_pool = list(documents)
            candidate_count = len(candidate_pool)
            intent_results = {}
            evidence_groups: list[list[dict[str, Any]]] = []
            per_intent_k = max(1, ceil(k / max(1, len(intents))))

            for intent in intents:
                allowed_types = set(INTENT_ENTITY_TYPES.get(intent, set()))
                branch_docs: list[dict[str, Any]] = []
                for item in candidate_pool:
                    metadata = item.get("metadata", {}) or {}
                    entity_type = str(
                        metadata.get("entity_type")
                        or metadata.get("source_table")
                        or ""
                    ).strip()
                    if allowed_types and entity_type not in allowed_types:
                        continue
                    copied = dict(item)
                    copied["matched_intent"] = intent
                    copied["intent_query"] = build_intent_query(
                        intent, [], str(query or user_message or "")
                    )
                    if has_budget_constraint and intent == "promotion":
                        prices = _affordable_prices(copied.get("text", ""), budget_vnd)
                        if not prices:
                            continue
                        copied["budget_constraint_vnd"] = budget_vnd
                        copied["budget_matched_prices"] = prices
                    branch_docs.append(copied)

                branch_docs.sort(
                    key=lambda item: float(item.get("score", 0.0) or 0.0),
                    reverse=True,
                )
                branch_docs = self._dedupe_documents(branch_docs)[:per_intent_k]
                evidence_groups.append(branch_docs)

                best_score = max(
                    (float(item.get("score", 0.0) or 0.0) for item in branch_docs),
                    default=0.0,
                )
                intent_results[intent] = {
                    "status": "found" if branch_docs else "not_found",
                    "document_count": len(branch_docs),
                    "candidate_count": candidate_count,
                    "best_score": round(best_score, 4),
                    "query": build_intent_query(intent, [], str(query or user_message or "")),
                    "missing_destination_ids": [],
                    "budget_constraint_vnd": budget_vnd if intent == "promotion" else None,
                    "budget_matched_prices": sorted({
                        price
                        for item in branch_docs
                        for price in (item.get("budget_matched_prices") or [])
                    }) if intent == "promotion" else [],
                    "constraint_satisfied": (
                        bool(branch_docs) if has_budget_constraint and intent == "promotion" else None
                    ),
                    "evidence_entity_types": sorted(
                        {
                            str((item.get("metadata", {}) or {}).get("entity_type") or "")
                            for item in branch_docs
                            if str((item.get("metadata", {}) or {}).get("entity_type") or "").strip()
                        }
                    ),
                }

            # Round-robin prevents the strongest branch from consuming the entire
            # final top-k and preserves useful partial-answer evidence for every
            # found intent. Keep branch identity in the dedupe key.
            selected: list[dict[str, Any]] = []
            seen_evidence: set[tuple[str, str, str]] = set()
            max_group_len = max((len(group) for group in evidence_groups), default=0)
            for index in range(max_group_len):
                for group in evidence_groups:
                    if index >= len(group):
                        continue
                    item = group[index]
                    metadata = item.get("metadata", {}) or {}
                    key = (
                        str(item.get("matched_intent") or ""),
                        str(metadata.get("entity_type") or ""),
                        str(
                            metadata.get("entity_id")
                            or metadata.get("entity_name")
                            or item.get("text", "")[:120]
                        ),
                    )
                    if key in seen_evidence:
                        continue
                    seen_evidence.add(key)
                    selected.append(item)
                    if len(selected) >= k:
                        break
                if len(selected) >= k:
                    break

            documents = selected
            mode += "_intent_filtered"
            if any(result.get("status") == "not_found" for result in intent_results.values()):
                mode += "_partial"

        # A high-confidence FAQ for a compound request supplements the normal
        # branch evidence instead of replacing it. The previous early return marked
        # every intent as found from one FAQ and could hide independently requested
        # policies/services. Prepending the authoritative row also prevents a lower
        # scoring generic policy chunk from crowding it out of the final context.
        if supplemental_faq_documents:
            documents = self._dedupe_documents(supplemental_faq_documents + documents)
            documents = documents[: max(k, len(supplemental_faq_documents))]
            faq_intent_key = str(supplemental_faq_intent or primary_intent or "faq")
            branch_document_count = sum(
                1 for item in documents
                if str(item.get("matched_intent") or "") == faq_intent_key
            )
            existing_result = dict(intent_results.get(faq_intent_key, {}) or {})
            existing_result.update({
                "status": "found",
                "document_count": max(1, branch_document_count),
                "candidate_count": max(
                    int(existing_result.get("candidate_count") or 0),
                    int(faq_diagnostics.get("candidate_count") or 0),
                ),
                "best_score": round(max(
                    float(existing_result.get("best_score") or 0.0),
                    float(faq_diagnostics.get("best_score") or 0.0),
                ), 4),
                "query": str(query or user_message or ""),
                "missing_destination_ids": list(existing_result.get("missing_destination_ids") or []),
                "faq_match": True,
                "matched_question": faq_diagnostics.get("matched_question"),
            })
            intent_results[faq_intent_key] = existing_result
            mode += "+faq_supplement"

        primary = destinations[0] if destinations else None
        destination_names = [
            str(item.get("name_vi") or item.get("name_en") or item.get("id") or "")
            for item in destinations
        ]
        destination_ids = [str(item.get("id") or "") for item in destinations]

        diagnostics = {
            "mode": mode,
            "destination_id": primary.get("id") if primary else None,
            "destination_name": (
                primary.get("name_vi") or primary.get("name_en") if primary else None
            ),
            "destinations": destinations,
            "destination_ids": destination_ids,
            "destination_names": destination_names,
            "intent": primary_intent,
            "intents": intents,
            "explicit_intents": list(parsed.get("explicit_intents") or []),
            "constraint_derived_intents": list(parsed.get("constraint_derived_intents") or []),
            "planned_intents": planned_added,
            "has_budget_constraint": has_budget_constraint,
            "budget_vnd": budget_vnd,
            "price_requested": price_requested,
            "booking_evidence_preferred": booking_evidence_preferred,
            "cost_estimate_requested": cost_estimate_requested,
            "exhaustive_requested": bool(exhaustive_requested),
            "exhaustive_retrieval_complete": bool(exhaustive_requested and destinations),
            "booking_focus_document_count": len(booking_focus_documents),
            "intent_origin": ("request_plan" if planned_added else str(parsed.get("intent_origin") or "none")),
            "intent_results": intent_results,
            "faq_match": faq_diagnostics,
            "keyword_candidate_count": all_candidates,
            "missing_destination_ids": missing_destination_ids,
            "named_entities": [
                {"name": item.get("name"), "type": item.get("type")}
                for item in named_entities
            ],
            "excluded_destination_ids": sorted(excluded_destination_norms),
            "excluded_entity_names": sorted(excluded_entity_norms),
        }

        print(
            "[RAG RETRIEVAL] "
            f"mode={mode} destinations={destination_ids or 'none'} "
            f"intents={intents or [primary_intent]} candidates={all_candidates} "
            f"named_entities={[item.get('name') for item in named_entities]} "
            f"excluded_destinations={sorted(excluded_destination_norms)} "
            f"excluded_entities={sorted(excluded_entity_norms)} "
            f"intent_results={intent_results}"
        )
        return documents, diagnostics

    @staticmethod
    def _context_round_robin(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Interleave intent branches so one long branch cannot hide the rest."""
        groups: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        for item in documents:
            key = str(item.get("matched_intent") or "general")
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(item)
        output: list[dict[str, Any]] = []
        max_len = max((len(group) for group in groups.values()), default=0)
        for offset in range(max_len):
            for key in order:
                group = groups[key]
                if offset < len(group):
                    output.append(group[offset])
        return output

    def build_context_with_diagnostics(
        self,
        documents: list[dict[str, Any]],
        *,
        exhaustive: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        """Serialize evidence and report what actually reached the answer LLM.

        Normal requests preserve the historical ordering/budget behavior. Exhaustive
        requests use branch round-robin + compact blocks so a large first document
        cannot consume the entire context before other requested branches are seen.
        The complete exhaustive entity set is also supplied separately by the agent
        packet; this context is the detailed supporting sample used for richer prose.
        """
        blocks: list[str] = []
        total = 0
        selected_intents: dict[str, int] = {}
        selected_entities: list[str] = []
        ordered = self._context_round_robin(documents) if exhaustive else list(documents)

        for index, item in enumerate(ordered, start=1):
            metadata = item.get("metadata", {}) or {}
            structured_record = item.get("structured_record") or {}
            structured_text = ""
            if structured_record:
                try:
                    structured_text = json.dumps(
                        structured_record,
                        ensure_ascii=False,
                        default=str,
                        sort_keys=True,
                    )
                except Exception:
                    structured_text = str(structured_record)
                structured_cap = 1200 if exhaustive else 5000
                if len(structured_text) > structured_cap:
                    structured_text = structured_text[:structured_cap] + "…"

            raw_content = str(item.get("text", "") or "")
            if exhaustive and len(raw_content) > 1100:
                raw_content = raw_content[:1100] + "…"

            block = (
                f"[SOURCE {index}]\n"
                f"type: {metadata.get('entity_type') or metadata.get('category')}\n"
                f"name: {metadata.get('entity_name') or metadata.get('source_file')}\n"
                f"destination: {item.get('matched_destination_name') or metadata.get('destination_id') or metadata.get('destination')}\n"
                f"intent: {item.get('matched_intent') or 'general'}\n"
                f"url: {metadata.get('source_url')}\n"
                f"retrieval_mode: {item.get('retrieval_mode')}\n"
                f"relevance_score: {item.get('score')}\n"
                f"semantic_score: {item.get('semantic_score')}\n"
                f"keyword_score: {item.get('keyword_score')}\n"
                f"content:\n{raw_content}\n"
                + (
                    f"structured_record_from_postgresql:\n{structured_text}\n"
                    if structured_text
                    else ""
                )
            )
            # Exhaustive discovery queries need wider context, but they still need
            # a hard ceiling. Without this limit, the exhaustive catalog retrieval
            # can serialize an entire destination catalog into the LLM prompt.
            # Keep normal RAG behavior unchanged and only expand the budget for
            # explicit exhaustive requests.
            context_limit = (
                getattr(
                    self.settings,
                    "exhaustive_max_context_chars",
                    self.settings.max_context_chars,
                )
                if exhaustive
                else self.settings.max_context_chars
            )

            if total + len(block) > context_limit:
                break
            blocks.append(block)
            total += len(block)
            intent = str(item.get("matched_intent") or "general")
            selected_intents[intent] = selected_intents.get(intent, 0) + 1
            entity_key = str(
                metadata.get("entity_id")
                or metadata.get("entity_name")
                or item.get("id")
                or ""
            ).strip()
            if entity_key:
                selected_entities.append(entity_key)

        return "\n---\n".join(blocks), {
            "document_count": len(blocks),
            "branch_counts": selected_intents,
            "intents": list(selected_intents),
            "entity_keys": selected_entities,
            "character_count": total,
            "exhaustive_serialization": bool(exhaustive),
        }

    def build_context(self, documents: list[dict[str, Any]], *, exhaustive: bool = False) -> str:
        context, _ = self.build_context_with_diagnostics(documents, exhaustive=exhaustive)
        return context

@lru_cache(maxsize=1)
def get_rag_service() -> RAGService:
    """Return one process-wide RAG/model instance for API traffic."""
    return RAGService()
