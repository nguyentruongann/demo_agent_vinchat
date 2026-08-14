from __future__ import annotations

from functools import lru_cache
from math import ceil
from typing import Any

import chromadb
import numpy as np
from src.backend.config import get_settings
from src.backend.services.onnx_embeddings import OnnxE5Embedder, OnnxEmbeddingConfig
from src.backend.services.query_parser import (
    build_intent_query,
    load_destination_catalog,
    normalize_text,
    parse_retrieval_query,
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

    def __init__(self) -> None:
        settings = get_settings()
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        if settings.embedding_backend != "onnx_int8":
            raise RuntimeError(
                "This deployment build supports EMBEDDING_BACKEND=onnx_int8 only. "
                "Use the ONNX INT8 backend to keep Railway memory usage low."
            )
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

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        passages = [f"passage: {text}" for text in texts]
        embeddings = self.model.encode(passages)
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        embedding = self.model.encode([f"query: {query}"])[0]
        return embedding.tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    def _ensure_not_empty(self) -> None:
        if self.collection.count() == 0:
            raise RuntimeError(
                "Vector database is empty. Run: "
                "python -m src.backend.services.ingest_postgres --reset"
            )

    def semantic_search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        self._ensure_not_empty()
        query_embedding = self.embed_query(query)
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k or self.settings.top_k,
            include=["documents", "metadatas", "distances"],
        )

        output: list[dict[str, Any]] = []
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

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
        return output

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
                "complex": 0.18,
                "destination_highlight": 0.15,
                "destination": 0.14,
                "attraction": 0.10,
                "attraction_itinerary_day": 0.04,
            }.get(entity_type, 0.0)
        if intent == "service":
            return {
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
            "attraction", "dining_service", "amenity",
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
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Run destination-aware retrieval with native multi-intent support.

        A multi-clause request such as "services + golf + events" is split into
        independent intent retrieval branches. One missing branch does not erase the
        evidence found for the others. The merged document set is still bounded by
        the normal context budget downstream.
        """
        k = top_k or self.settings.top_k
        parsed = parse_retrieval_query(user_message=user_message, rag_query=query)

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
        primary_intent = parsed.get("intent")

        # Keep legacy behavior for a query where no explicit intent can be detected.
        retrieval_intents: list[str | None] = intents or [primary_intent]
        is_multi_intent = len([item for item in retrieval_intents if item]) > 1

        all_candidates = 0
        missing_destination_ids: list[str] = []
        documents: list[dict[str, Any]] = []
        intent_results: dict[str, dict[str, Any]] = {}

        if destinations:
            # Allocate a useful minimum to each intent. The final merged context is
            # bounded by max_context_chars, so 3-4 docs per intent is a good balance.
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
                    candidates = self.keyword_candidates(
                        destination=destination,
                        intent=intent,
                        preferred_entity_types=preferred_entity_types,
                        strict_entity_types=is_multi_intent and bool(preferred_entity_types),
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

                    ranked = self._rerank_candidates(
                        query=focused_query,
                        candidates=candidates,
                        top_k=per_destination_k,
                        preferred_entity_types=preferred_entity_types,
                        intent=intent,
                    )
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
                branch_docs = self._dedupe_documents(branch_docs)[:per_intent_k]

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
            if any(result.get("status") == "not_found" for result in intent_results.values()):
                mode += "_partial"
        else:
            # No destination was resolved. Preserve the user's original wording as
            # retrieval evidence instead of relying only on the LLM-rewritten query.
            # This specifically protects exact FAQ questions from rewrite drift while
            # keeping the rewritten query for multilingual/follow-up understanding.
            original_query = str(user_message or "").strip()
            rewritten_query = str(query or "").strip()

            exact_faq = self._exact_faq_matches(original_query, top_k=k)

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

            semantic_groups = self.semantic_search_many(
                [item[1] for item in semantic_queries],
                top_k=k,
            ) if semantic_queries else []

            merged_by_key: dict[tuple[str, str], dict[str, Any]] = {}

            def add_result(item: dict[str, Any], query_source: str) -> None:
                candidate = dict(item)
                candidate["query_source"] = query_source
                metadata = candidate.get("metadata", {}) or {}
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
            )[:k]

            if exact_faq:
                mode = "semantic_fallback_exact_faq"
            elif len(semantic_queries) > 1:
                mode = "semantic_dual_query"
            else:
                mode = "semantic_fallback"

            if intents:
                best_score = max(
                    (float(item.get("score", 0.0) or 0.0) for item in documents),
                    default=0.0,
                )
                for intent in intents:
                    intent_results[intent] = {
                        "status": "found" if documents else "not_found",
                        "document_count": len(documents),
                        "candidate_count": len(merged_by_key),
                        "best_score": round(best_score, 4),
                        "query": query,
                        "missing_destination_ids": [],
                    }

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
            "intent_results": intent_results,
            "keyword_candidate_count": all_candidates,
            "missing_destination_ids": missing_destination_ids,
        }

        print(
            "[RAG RETRIEVAL] "
            f"mode={mode} destinations={destination_ids or 'none'} "
            f"intents={intents or [primary_intent]} candidates={all_candidates} "
            f"intent_results={intent_results}"
        )
        return documents, diagnostics

    def search(
        self,
        query: str,
        top_k: int | None = None,
        user_message: str = "",
    ) -> list[dict[str, Any]]:
        documents, _ = self.hybrid_search(
            query=query,
            user_message=user_message,
            top_k=top_k,
        )
        return documents

    def build_context(self, documents: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        total = 0

        for index, item in enumerate(documents, start=1):
            metadata = item.get("metadata", {}) or {}
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
                f"content:\n{item.get('text', '')}\n"
            )
            if total + len(block) > self.settings.max_context_chars:
                break
            blocks.append(block)
            total += len(block)

        return "\n---\n".join(blocks)


@lru_cache(maxsize=1)
def get_rag_service() -> RAGService:
    """Return one process-wide RAG/model instance for API traffic."""
    return RAGService()
