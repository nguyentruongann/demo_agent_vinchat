from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from src.backend.config import get_settings
from src.backend.services.query_parser import normalize_intent_text, normalize_text


# The FAQ matcher is intentionally independent from destination/intent routing.
# A documented FAQ is authoritative evidence even when its wording mentions a
# cross-domain concept such as flights, passports, pets, shuttle buses, weather,
# baggage, pregnancy, or payment.

_STOPWORDS = {
    "a", "an", "the", "i", "me", "my", "we", "our", "you", "your", "it",
    "to", "for", "of", "in", "on", "at", "and", "or", "with", "from", "by",
    "be", "is", "are", "am", "was", "were", "do", "does", "did", "can", "may",
    "could", "should", "would", "what", "where", "when", "why", "how", "which",
    "who", "this", "that", "these", "those", "there", "any", "please", "tell",
    "toi", "minh", "ban", "co", "la", "duoc", "khong", "cho", "cua", "va",
    "voi", "tu", "tai", "o", "ve", "nay", "do", "mot", "nhung", "cac", "the",
    "nao", "gi", "nhieu", "lam", "sao", "xin", "hay",
}

# Generic conversational/support words are poor discriminators between FAQ rows.
# They are excluded from the "anchor" check used to prevent a semantically nearby
# but topically wrong FAQ from hijacking retrieval (for example, a cancellation
# question matching a bank-transfer FAQ merely because both say "who do I contact").
_GENERIC_ANCHOR_TOKENS = _STOPWORDS | {
    "vinpearl", "vinwonders", "customer", "customers", "guest", "guests",
    "booking", "bookings", "reservation", "reservations", "service", "services",
    "request", "requests", "information", "details", "detail", "support",
    "contact", "contacts", "help", "assistance", "website", "online",
}

_SYNTHESIS_MARKERS = (
    "summarize", "summary", "recap", "overview", "synthesize",
    "tom tat", "tong hop", "nhac lai", "noi dung vua trao doi",
)


@dataclass(frozen=True)
class FAQEntry:
    index: int
    question: str
    answer: str
    category: str
    subcategory: str
    source_url: str
    language: str
    source_path: str

    @property
    def normalized_question(self) -> str:
        return normalize_text(self.question)

    @property
    def enriched_search_text(self) -> str:
        # Include the answer because many user paraphrases describe the policy result
        # rather than echoing the source question wording. Keep it bounded so one long
        # FAQ cannot dominate the small canonical index.
        answer = self.answer[:1400]
        return (
            f"Vinpearl official FAQ. Category: {self.category}. "
            f"Subcategory: {self.subcategory}. Question: {self.question}. "
            f"Answer: {answer}"
        )

    @property
    def document_text(self) -> str:
        return (
            "Bảng dữ liệu: faq\n"
            f"Bản ghi: {self.question}\n"
            f"Category: {self.category}\n"
            f"Subcategory: {self.subcategory}\n"
            f"Question: {self.question}\n"
            f"Answer: {self.answer}\n"
            f"Content language: {self.language}\n"
            f"Nguồn/URL liên quan: {self.source_url}"
        )

    def as_retrieval_document(
        self,
        *,
        score: float,
        semantic_score: float,
        lexical_score: float,
        mode: str,
        matched_query_source: str,
    ) -> dict[str, Any]:
        return {
            "id": f"faq:raw:{self.index}",
            "text": self.document_text,
            "metadata": {
                "entity_type": "faq",
                "entity_id": f"raw:{self.index}",
                "entity_name": self.question,
                "source_table": "faq",
                "source_url": self.source_url,
                "category": self.category,
                "subcategory": self.subcategory,
                "content_language": self.language,
                "faq_index": self.index,
                "source_file": self.source_path,
            },
            "score": round(float(score), 4),
            "semantic_score": round(float(semantic_score), 4),
            "keyword_score": round(float(lexical_score), 4),
            "retrieval_mode": mode,
            "query_source": matched_query_source,
        }


class FAQMatcher:
    """High-recall FAQ-first matcher over the canonical 174-row FAQ JSON.

    Why this exists:
    - destination-scoped retrieval can legally exclude FAQ rows when the detected
      intent prefers catalog entities such as ``attraction``;
    - exact FAQ matching only after the destination branch is too late;
    - the FAQ file itself is the authoritative source for FAQ answers, so it should
      have a dedicated retrieval lane that does not depend on generic catalog filters.

    The matcher uses three signals, in order:
    1) exact normalized question equality;
    2) lexical overlap against the English standalone query;
    3) multilingual E5 semantic similarity against both question-only and
       category/subcategory-enriched FAQ passages.

    The embedding callbacks are provided by ``RAGService`` so the ONNX model is
    instantiated only once for the whole process.
    """

    def __init__(
        self,
        *,
        embed_passages: Callable[[list[str]], list[list[float]]],
        embed_queries: Callable[[list[str]], np.ndarray],
        fallback_rows: Callable[[], list[dict[str, Any]]] | None = None,
        semantic_verifier: Callable[
            [list[tuple[str, str]], list[dict[str, Any]]],
            dict[str, Any] | None,
        ] | None = None,
    ) -> None:
        self.settings = get_settings()
        self._embed_passages = embed_passages
        self._embed_queries = embed_queries
        self._fallback_rows = fallback_rows
        self._semantic_verifier = semantic_verifier
        self._entries: list[FAQEntry] | None = None
        self._question_vectors: np.ndarray | None = None
        self._enriched_vectors: np.ndarray | None = None
        self._loaded_path: Path | None = None
        self._question_idf: dict[str, float] | None = None

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _candidate_paths(self) -> list[Path]:
        service_path = Path(__file__).resolve()
        src_dir = service_path.parents[2]
        cwd = Path.cwd()

        candidates = [
            src_dir / "data_crawl" / "Faqs" / "vinpearl_faqs.json",
            src_dir / "data_crawl" / "faqs" / "vinpearl_faqs.json",
            cwd / "src" / "data_crawl" / "Faqs" / "vinpearl_faqs.json",
            cwd / "src" / "data_crawl" / "faqs" / "vinpearl_faqs.json",
            cwd / "data" / "faqs" / "vinpearl_faqs.json",
            cwd / "data_crawl" / "Faqs" / "vinpearl_faqs.json",
            Path(self.settings.data_dir) / "faqs" / "vinpearl_faqs.json",
        ]

        output: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path.resolve()) if path.exists() else str(path.absolute())
            if key in seen:
                continue
            seen.add(key)
            output.append(path)
        return output

    def _load_entries(self) -> list[FAQEntry]:
        if self._entries is not None:
            return self._entries

        faq_path = next((path for path in self._candidate_paths() if path.is_file()), None)
        payload: dict[str, Any] = {}
        source_label = ""
        rows: list[dict[str, Any]] = []

        if faq_path is not None:
            try:
                payload = json.loads(faq_path.read_text(encoding="utf-8"))
                rows = [item for item in (payload.get("items") or []) if isinstance(item, dict)]
                source_label = str(faq_path)
            except Exception as exc:
                print(f"[FAQ MATCHER] failed to load {faq_path}: {exc}")
                rows = []

        # Deployment fallback: some Docker images copy only backend code + Chroma and
        # omit data_crawl. The normalized FAQ rows are already present in Chroma, so
        # reuse them instead of silently disabling FAQ-first retrieval.
        if not rows and self._fallback_rows is not None:
            try:
                rows = [item for item in self._fallback_rows() if isinstance(item, dict)]
                source_label = "chroma:faq"
                payload = {
                    "source_url": "https://vinpearl.com/en/faqs",
                    "language": "en",
                    "item_count": len(rows),
                }
                print(f"[FAQ MATCHER] raw FAQ JSON unavailable; loaded {len(rows)} FAQ rows from Chroma fallback")
            except Exception as exc:
                print(f"[FAQ MATCHER] Chroma FAQ fallback failed: {exc}")
                rows = []

        if not rows:
            print("[FAQ MATCHER] no FAQ source available; FAQ-first lane disabled")
            self._entries = []
            return self._entries

        source_url = str(payload.get("source_url") or "https://vinpearl.com/en/faqs").strip()
        language = str(payload.get("language") or "en").strip() or "en"

        entries: list[FAQEntry] = []
        for index, item in enumerate(rows):
            question = str(item.get("question") or item.get("entity_name") or "").strip()
            answer = str(item.get("answer") or item.get("text") or "").strip()
            if not question or not answer:
                continue
            entries.append(
                FAQEntry(
                    index=int(item.get("index", index) if str(item.get("index", index)).isdigit() else index),
                    question=question,
                    answer=answer,
                    category=str(item.get("category") or "General").strip() or "General",
                    subcategory=str(item.get("subcategory") or "").strip(),
                    source_url=str(item.get("source_url") or source_url).strip() or source_url,
                    language=str(item.get("language") or language).strip() or language,
                    source_path=str(item.get("source_path") or source_label),
                )
            )

        self._loaded_path = faq_path
        self._entries = entries
        print(
            f"[FAQ MATCHER] loaded {len(entries)} FAQ rows from {source_label} "
            f"(declared item_count={payload.get('item_count')})"
        )
        return entries

    # ------------------------------------------------------------------
    # Similarity helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _canonical_token(token: str) -> str:
        """Apply a tiny language-agnostic-enough English morphology normalizer.

        The canonical FAQ is English while the control layer rewrites multilingual
        questions to English. Normalizing ordinary plural inflections lets lexical
        evidence align ``stroller`` with ``strollers`` and similar pairs without
        maintaining any product/topic keyword dictionary.
        """
        value = str(token or "").strip().lower()
        if len(value) <= 4:
            return value
        if value.endswith("ies") and len(value) > 5:
            return value[:-3] + "y"
        if value.endswith("sses"):
            return value[:-2]
        if value.endswith(("xes", "zes", "ches", "shes")):
            return value[:-2]
        if value.endswith("s") and not value.endswith(("ss", "us", "is")):
            return value[:-1]
        return value

    @staticmethod
    def _normalized_lexical_text(value: str) -> str:
        """Normalize FAQ lexical text without erasing Vietnamese ``báo``.

        ``normalize_text`` intentionally strips accents, so both the verb ``báo``
        (notify/report) and the price phrase ``bao nhiêu`` become ``bao``. Treating
        the single token as a stopword removed a meaningful predicate from FAQ
        confidence checks. Remove only the actual question phrase before using the
        accent-insensitive representation; keep standalone ``báo``/``bao`` tokens.
        """
        raw = normalize_intent_text(value)
        normalized = normalize_text(value)
        if re.search(r"\bbao\s+nhiêu\b", raw) or re.search(r"\bbao\s+nhieu\b", raw):
            normalized = re.sub(r"\bbao\s+nhieu\b", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _tokens(cls, value: str) -> set[str]:
        normalized = cls._normalized_lexical_text(value)
        return {
            cls._canonical_token(token)
            for token in normalized.split()
            if len(token) >= 2 and token not in _STOPWORDS
        }

    @classmethod
    def _anchor_tokens(cls, value: str) -> set[str]:
        return {
            cls._canonical_token(token)
            for token in cls._normalized_lexical_text(value).split()
            if len(token) >= 3 and token not in _GENERIC_ANCHOR_TOKENS
        }

    @classmethod
    def _anchor_overlap(cls, query: str, entry: FAQEntry) -> tuple[int, float]:
        query_tokens = cls._anchor_tokens(query)
        if not query_tokens:
            return 0, 0.0
        evidence_tokens = cls._anchor_tokens(
            f"{entry.category} {entry.subcategory} {entry.question} {entry.answer}"
        )
        overlap = query_tokens & evidence_tokens
        return len(overlap), len(overlap) / max(1, min(len(query_tokens), 8))

    @classmethod
    def _predicate_overlap(
        cls,
        query: str,
        entry: FAQEntry,
        routing_context: str = "",
    ) -> tuple[int, float]:
        """Measure overlap on the requested fact, not merely routing/location words.

        FAQ rows often share a category/subcategory or venue name. Those tokens are
        useful for retrieval, but they are unsafe as proof that two questions ask the
        same thing.  For example, a golf question and a ticket-purchase FAQ can both
        contain ``Nam Hoi An`` while asking completely different predicates.

        The candidate's own category/subcategory plus caller-supplied resolved
        destination context are therefore treated as routing context and removed
        from both sides before measuring overlap. This stays
        data-driven: no product, destination, or topic keyword list is encoded here.
        Answer text remains available so faithful paraphrases such as ``baggage
        allowance`` can align with a source question phrased as ``pieces/kilos of
        luggage``.
        """
        routing_tokens = cls._anchor_tokens(
            f"{entry.category} {entry.subcategory} {routing_context}"
        )
        query_tokens = cls._anchor_tokens(query) - routing_tokens
        if not query_tokens:
            return 0, 0.0

        evidence_tokens = cls._anchor_tokens(
            f"{entry.question} {entry.answer}"
        ) - routing_tokens
        overlap = query_tokens & evidence_tokens
        return len(overlap), len(overlap) / max(1, min(len(query_tokens), 8))

    @staticmethod
    def _confidence_gate(
        *,
        semantic: float,
        lexical: float,
        weighted_f1: float,
        query_coverage: float,
        predicate_count: int,
        predicate_ratio: float,
        margin: float,
    ) -> tuple[bool, str]:
        """Conservative cross-signal gate for deterministic FAQ clear-pass.

        The main failure mode this gate prevents is a same-venue FAQ winning only
        because the venue/destination words are very similar.  A semantic score is
        therefore never enough by itself.  We accept either:

        * very strong direct question overlap;
        * strong candidate-specific predicate/object overlap; or
        * a balanced paraphrase where semantic, lexical and predicate evidence all
          agree.

        This is intentionally topic-agnostic: there are no Safari/tram/hotel keys.
        """
        semantic_alignment = semantic >= 0.70

        # Keep high-confidence direct paraphrases even when predicate extraction is
        # sparse, but require substantially more than the old single >=0.50 signal.
        # This prevents a nearby FAQ such as "operating hours at <same venue>" from
        # clear-passing on venue overlap alone.
        strong_direct_alignment = (
            semantic >= 0.72
            and lexical >= 0.76
            and weighted_f1 >= 0.58
            and query_coverage >= 0.55
        )

        predicate_alignment = predicate_count >= 2 and predicate_ratio >= 0.30

        # Translation/rewrite drift often changes a concrete noun (e.g. tram ->
        # electric vehicle) while preserving most of the rest of the request.  This
        # balanced path lets such paraphrases through only when *all* independent
        # signals are reasonably strong and at least one predicate token is shared.
        balanced_paraphrase_alignment = (
            margin >= 0.020
            and semantic >= 0.84
            and lexical >= 0.52
            and weighted_f1 >= 0.42
            and query_coverage >= 0.35
            and predicate_count >= 1
            and predicate_ratio >= 0.30
        )

        separated_short_alignment = (
            margin >= 0.045
            and semantic >= 0.78
            and predicate_count >= 1
            and predicate_ratio >= 0.50
        )

        accepted = semantic_alignment and (
            strong_direct_alignment
            or predicate_alignment
            or balanced_paraphrase_alignment
            or separated_short_alignment
        )

        # A near tie needs unusually strong evidence. This keeps ambiguous FAQ rows
        # on normal RAG, while still allowing translated/paraphrased questions whose
        # distinctive predicate is well covered by the selected FAQ answer.
        if accepted and margin < 0.018:
            strong_near_tie_alignment = strong_direct_alignment or (
                predicate_count >= 3 and predicate_ratio >= 0.45
            )
            if not strong_near_tie_alignment:
                accepted = False

        if strong_direct_alignment:
            reason = "strong direct question alignment"
        elif predicate_alignment:
            reason = "candidate-specific predicate alignment"
        elif balanced_paraphrase_alignment:
            reason = "balanced semantic/lexical/predicate paraphrase alignment"
        elif separated_short_alignment:
            reason = "short predicate alignment with clear candidate separation"
        else:
            reason = "insufficient cross-signal alignment"
        return accepted, reason

    def _ensure_question_idf(self) -> dict[str, float]:
        """Build corpus-derived token importance over canonical FAQ questions.

        This is deliberately data-driven. Terms repeated across a destination
        cluster (for example the destination name itself) receive less weight than
        the distinctive predicate/object of a question. That prevents a query from
        matching a nearby FAQ merely because both mention the same venue.
        """
        if self._question_idf is not None:
            return self._question_idf
        entries = self._load_entries()
        counts: Counter[str] = Counter()
        for entry in entries:
            counts.update(self._tokens(entry.question))
        total = max(1, len(entries))
        self._question_idf = {
            token: math.log((total + 1.0) / (count + 1.0)) + 1.0
            for token, count in counts.items()
        }
        return self._question_idf

    def _weighted_question_overlap(self, query: str, entry: FAQEntry) -> tuple[float, float, float]:
        """Return query coverage, candidate precision and weighted F1.

        IDF comes from the FAQ corpus itself; there are no domain-specific keys.
        The query-coverage component is especially useful for guarding against
        false positives where only a shared destination name overlaps.
        """
        query_tokens = self._tokens(query)
        entry_tokens = self._tokens(entry.question)
        if not query_tokens or not entry_tokens:
            return 0.0, 0.0, 0.0
        idf = self._ensure_question_idf()
        unseen = math.log(len(self._load_entries()) + 1.0) + 1.0

        def weight(token: str) -> float:
            return float(idf.get(token, unseen))

        overlap = query_tokens & entry_tokens
        overlap_weight = sum(weight(token) for token in overlap)
        query_weight = sum(weight(token) for token in query_tokens)
        entry_weight = sum(weight(token) for token in entry_tokens)
        coverage = overlap_weight / max(query_weight, 1e-9)
        precision = overlap_weight / max(entry_weight, 1e-9)
        f1 = (2.0 * overlap_weight / max(query_weight + entry_weight, 1e-9))
        return coverage, precision, f1

    @staticmethod
    def _is_synthesis_request(*queries: str) -> bool:
        combined = " ".join(normalize_text(value) for value in queries if str(value or "").strip())
        return any(marker in combined for marker in _SYNTHESIS_MARKERS)

    @classmethod
    def _lexical_similarity(cls, query: str, entry: FAQEntry) -> float:
        qnorm = normalize_text(query)
        question_norm = entry.normalized_question
        if not qnorm or not question_norm:
            return 0.0
        if qnorm == question_norm:
            return 1.0

        q_tokens = cls._tokens(query)
        question_tokens = cls._tokens(entry.question)
        context_tokens = cls._tokens(f"{entry.subcategory} {entry.category} {entry.question}")
        if not q_tokens or not question_tokens:
            return 0.0

        question_overlap = len(q_tokens & question_tokens)
        context_overlap = len(q_tokens & context_tokens)
        recall = question_overlap / max(1, len(question_tokens))
        precision = question_overlap / max(1, len(q_tokens))
        context_recall = context_overlap / max(1, min(len(context_tokens), 12))

        containment_bonus = 0.0
        if len(question_tokens) >= 3 and (
            f" {question_norm} " in f" {qnorm} "
            or f" {qnorm} " in f" {question_norm} "
        ):
            containment_bonus = 0.20

        score = 0.52 * recall + 0.28 * precision + 0.20 * context_recall + containment_bonus
        return max(0.0, min(1.0, score))

    def _ensure_vectors(self) -> None:
        if self._question_vectors is not None and self._enriched_vectors is not None:
            return

        entries = self._load_entries()
        if not entries:
            self._question_vectors = np.empty((0, 384), dtype=np.float32)
            self._enriched_vectors = np.empty((0, 384), dtype=np.float32)
            return

        question_vectors = np.asarray(
            self._embed_passages([entry.question for entry in entries]),
            dtype=np.float32,
        )
        enriched_vectors = np.asarray(
            self._embed_passages([entry.enriched_search_text for entry in entries]),
            dtype=np.float32,
        )
        self._question_vectors = question_vectors
        self._enriched_vectors = enriched_vectors
        print(
            f"[FAQ MATCHER] built question index: rows={len(entries)} "
            f"vectors={question_vectors.shape}/{enriched_vectors.shape}"
        )

    @staticmethod
    def _dedupe_query_variants(
        original_query: str,
        rewritten_query: str,
        additional_queries: list[tuple[str, str]] | None = None,
    ) -> list[tuple[str, str]]:
        output: list[tuple[str, str]] = []
        seen: set[str] = set()
        candidates = [
            ("original", original_query),
            ("rewritten", rewritten_query),
            *(additional_queries or []),
        ]
        for source, value in candidates:
            text = str(value or "").strip()
            normalized = normalize_text(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            output.append((source, text))
        return output

    # ------------------------------------------------------------------
    # Public match API
    # ------------------------------------------------------------------
    def match(
        self,
        *,
        original_query: str,
        rewritten_query: str,
        top_k: int = 3,
        skip_semantic: bool = False,
        routing_context: str = "",
        additional_queries: list[tuple[str, str]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        entries = self._load_entries()
        if not entries:
            return [], {"accepted": False, "reason": "FAQ JSON unavailable"}

        variants = self._dedupe_query_variants(
            original_query,
            rewritten_query,
            additional_queries,
        )
        if not variants:
            return [], {"accepted": False, "reason": "Empty FAQ query"}

        # 1) Exact normalized equality: authoritative and threshold-free.
        exact_indices: list[int] = []
        exact_source = "original"
        for source, query in variants:
            target = normalize_text(query)
            matches = [i for i, entry in enumerate(entries) if entry.normalized_question == target]
            if matches:
                exact_indices = matches
                exact_source = source
                break

        if exact_indices:
            # Duplicate question texts exist in the source under multiple categories.
            # Use the first canonical occurrence only so the answerer receives one
            # authoritative answer instead of duplicate context.
            docs = [
                entries[exact_indices[0]].as_retrieval_document(
                    score=1.0,
                    semantic_score=1.0,
                    lexical_score=1.0,
                    mode="faq_exact",
                    matched_query_source=exact_source,
                )
            ]
            return docs, {
                "accepted": True,
                "mode": "faq_exact",
                "best_score": 1.0,
                "best_semantic_score": 1.0,
                "best_lexical_score": 1.0,
                "margin": 1.0,
                "matched_question": entries[exact_indices[0]].question,
                "matched_query_source": exact_source,
                "candidate_count": len(entries),
                "reason": "Exact normalized FAQ question match.",
            }

        # Synthesis/recap requests need evidence from several rows/documents. A
        # single semantic FAQ candidate must never hijack a request such as
        # "summarize payment and refund". Exact FAQ equality above remains allowed.
        if self._is_synthesis_request(*(value for _, value in variants)):
            return [], {
                "accepted": False,
                "mode": "faq_synthesis_skipped",
                "candidate_count": len(entries),
                "reason": "Synthesis/recap request requires multi-document retrieval.",
            }

        # Broad discovery/planning requests are intentionally kept on the normal
        # catalog path by the caller.  For every other factual RAG request we run the
        # FAQ lane even when the surface form is not an interrogative.  Users often
        # ask the same fact as "tư vấn giúp mình X", "cho mình thông tin về X",
        # or an imperative fragment; requiring a question mark/"what/how" made
        # semantically identical requests take different retrieval paths.
        #
        # Safety is preserved by the conservative cross-signal confidence gate
        # below: merely running semantic retrieval does not make an FAQ authoritative.
        if skip_semantic:
            return [], {
                "accepted": False,
                "mode": "faq_skipped",
                "candidate_count": len(entries),
                "reason": "Broad discovery/planning request keeps normal catalog retrieval.",
            }

        # 2) Semantic + lexical matching. Both original multilingual wording and the
        # English standalone rewrite participate; the best signal wins per FAQ row.
        self._ensure_vectors()
        if self._question_vectors is None or self._question_vectors.size == 0:
            return [], {"accepted": False, "reason": "FAQ embedding index unavailable"}

        query_vectors = np.asarray(
            self._embed_queries([value for _, value in variants]),
            dtype=np.float32,
        )
        if query_vectors.size == 0:
            return [], {"accepted": False, "reason": "FAQ query embedding unavailable"}

        question_scores = query_vectors @ self._question_vectors.T
        enriched_scores = query_vectors @ self._enriched_vectors.T

        ranked: list[dict[str, Any]] = []
        for entry_index, entry in enumerate(entries):
            question_by_variant = question_scores[:, entry_index]
            enriched_by_variant = enriched_scores[:, entry_index]
            best_question_variant = int(np.argmax(question_by_variant))
            best_enriched_variant = int(np.argmax(enriched_by_variant))
            question_semantic = float(question_by_variant[best_question_variant])
            enriched_semantic = float(enriched_by_variant[best_enriched_variant])

            lexical_scores = [self._lexical_similarity(value, entry) for _, value in variants]
            lexical_score = max(lexical_scores, default=0.0)
            lexical_variant_index = int(np.argmax(lexical_scores)) if lexical_scores else best_question_variant

            weighted_scores = [self._weighted_question_overlap(value, entry) for _, value in variants]
            weighted_variant_index = int(
                np.argmax([item[2] for item in weighted_scores])
            ) if weighted_scores else best_question_variant
            query_coverage, candidate_precision, weighted_f1 = (
                weighted_scores[weighted_variant_index] if weighted_scores else (0.0, 0.0, 0.0)
            )

            # Use the query variant whose direct question alignment is strongest.
            # An English rewrite with high weighted lexical coverage is more reliable
            # than an enriched-answer embedding that shares only destination words.
            query_source = variants[best_question_variant][0]
            if weighted_f1 >= 0.45 or lexical_score >= 0.70:
                query_source = variants[weighted_variant_index][0]
            elif enriched_semantic > question_semantic + 0.08:
                query_source = variants[best_enriched_variant][0]

            anchor_scores = [self._anchor_overlap(value, entry) for _, value in variants]
            best_anchor_count, best_anchor_ratio = max(
                anchor_scores,
                key=lambda item: (item[0], item[1]),
                default=(0, 0.0),
            )
            predicate_scores = [
                self._predicate_overlap(value, entry, routing_context=routing_context)
                for _, value in variants
            ]
            best_predicate_count, best_predicate_ratio = max(
                predicate_scores,
                key=lambda item: (item[0], item[1]),
                default=(0, 0.0),
            )

            # Question semantics and corpus-weighted lexical coverage must agree.
            # The answer embedding is intentionally a small auxiliary signal; it may
            # contain broad venue/location vocabulary that is not the requested fact.
            combined_score = min(
                1.0,
                0.56 * max(0.0, question_semantic)
                + 0.08 * max(0.0, enriched_semantic)
                + 0.20 * weighted_f1
                + 0.10 * lexical_score
                + 0.06 * query_coverage,
            )
            ranked.append(
                {
                    "entry_index": entry_index,
                    "score": combined_score,
                    "semantic_score": question_semantic,
                    "enriched_semantic_score": enriched_semantic,
                    "lexical_score": lexical_score,
                    "weighted_f1": weighted_f1,
                    "query_coverage": query_coverage,
                    "candidate_precision": candidate_precision,
                    "anchor_count": best_anchor_count,
                    "anchor_ratio": best_anchor_ratio,
                    "predicate_count": best_predicate_count,
                    "predicate_ratio": best_predicate_ratio,
                    "query_source": query_source,
                }
            )

        ranked.sort(key=lambda item: float(item["score"]), reverse=True)

        # Validate candidates in score order instead of validating only rank #1.
        # Same-venue FAQ rows can score very close semantically; the top row may ask
        # for a different predicate (e.g. operating hours) while rank #2 is the
        # correct service/policy question.  We therefore reject invalid rows and
        # continue to the next candidate.  The scan is bounded so a weak tail row can
        # never become authoritative merely because everything above it failed.
        max_validation_candidates = min(8, len(ranked))
        selected_rank: int | None = None
        selected_signal = "insufficient cross-signal alignment"
        rejection_details: list[dict[str, Any]] = []

        def candidate_margin(rank_index: int) -> float:
            current = ranked[rank_index]
            current_question_norm = entries[int(current["entry_index"])].normalized_question
            second_different = next(
                (
                    item for item in ranked[rank_index + 1:]
                    if entries[int(item["entry_index"])].normalized_question != current_question_norm
                ),
                None,
            )
            second_score = float(second_different["score"]) if second_different else 0.0
            return max(0.0, float(current["score"]) - second_score)

        for rank_index in range(max_validation_candidates):
            candidate = ranked[rank_index]
            margin = candidate_margin(rank_index)
            accepted, signal = self._confidence_gate(
                semantic=float(candidate.get("semantic_score") or 0.0),
                lexical=float(candidate.get("lexical_score") or 0.0),
                weighted_f1=float(candidate.get("weighted_f1") or 0.0),
                query_coverage=float(candidate.get("query_coverage") or 0.0),
                predicate_count=int(candidate.get("predicate_count") or 0),
                predicate_ratio=float(candidate.get("predicate_ratio") or 0.0),
                margin=margin,
            )
            if accepted:
                selected_rank = rank_index
                selected_signal = signal
                break
            rejection_details.append({
                "rank": rank_index + 1,
                "question": entries[int(candidate["entry_index"])].question,
                "score": round(float(candidate.get("score") or 0.0), 4),
                "predicate_count": int(candidate.get("predicate_count") or 0),
                "predicate_ratio": round(float(candidate.get("predicate_ratio") or 0.0), 4),
                "reason": signal,
            })

        verifier_result: dict[str, Any] | None = None
        if selected_rank is None and self._semantic_verifier is not None:
            verifier_candidates: list[dict[str, Any]] = []
            for rank_index, candidate in enumerate(
                ranked[:max_validation_candidates],
                start=1,
            ):
                entry = entries[int(candidate["entry_index"])]
                verifier_candidates.append({
                    "position": rank_index,
                    "question": entry.question,
                    "answer": entry.answer[:1400],
                    "category": entry.category,
                    "subcategory": entry.subcategory,
                    "semantic_score": round(float(candidate.get("semantic_score") or 0.0), 4),
                    "lexical_score": round(float(candidate.get("lexical_score") or 0.0), 4),
                    "predicate_count": int(candidate.get("predicate_count") or 0),
                    "predicate_ratio": round(float(candidate.get("predicate_ratio") or 0.0), 4),
                })
            try:
                raw_verifier_result = self._semantic_verifier(
                    variants,
                    verifier_candidates,
                )
                verifier_result = (
                    dict(raw_verifier_result)
                    if isinstance(raw_verifier_result, dict)
                    else None
                )
                selected_position = int(
                    (verifier_result or {}).get("selected_candidate_position") or 0
                )
                verifier_confidence = float(
                    (verifier_result or {}).get("confidence") or 0.0
                )
                if (
                    1 <= selected_position <= max_validation_candidates
                    and verifier_confidence >= 0.82
                ):
                    selected_rank = selected_position - 1
                    selected_signal = "semantic equivalence verifier"
            except Exception as exc:
                verifier_result = {
                    "selected_candidate_position": 0,
                    "confidence": 0.0,
                    "reason": f"Verifier unavailable: {type(exc).__name__}",
                }
                print(f"[FAQ VERIFIER] skipped after error: {type(exc).__name__}: {exc}")

        # Diagnostics still expose the highest-scoring raw candidate when nothing
        # passes, but when rank #2/#3 is the first valid candidate we report that row
        # as the actual match.
        best = ranked[selected_rank] if selected_rank is not None else ranked[0]
        best_rank_index = selected_rank if selected_rank is not None else 0
        margin = candidate_margin(best_rank_index)

        best_semantic = float(best["semantic_score"])
        best_enriched_semantic = float(best.get("enriched_semantic_score") or 0.0)
        best_lexical = float(best["lexical_score"])
        best_weighted_f1 = float(best.get("weighted_f1") or 0.0)
        best_query_coverage = float(best.get("query_coverage") or 0.0)
        best_candidate_precision = float(best.get("candidate_precision") or 0.0)
        best_anchor_count = int(best.get("anchor_count") or 0)
        best_anchor_ratio = float(best.get("anchor_ratio") or 0.0)
        best_predicate_count = int(best.get("predicate_count") or 0)
        best_predicate_ratio = float(best.get("predicate_ratio") or 0.0)

        if selected_rank is None:
            return [], {
                "accepted": False,
                "mode": "faq_semantic_rejected",
                "best_score": round(float(best["score"]), 4),
                "best_semantic_score": round(best_semantic, 4),
                "best_lexical_score": round(best_lexical, 4),
                "best_enriched_semantic_score": round(best_enriched_semantic, 4),
                "best_weighted_f1": round(best_weighted_f1, 4),
                "best_query_coverage": round(best_query_coverage, 4),
                "best_candidate_precision": round(best_candidate_precision, 4),
                "best_anchor_count": best_anchor_count,
                "best_anchor_ratio": round(best_anchor_ratio, 4),
                "best_predicate_count": best_predicate_count,
                "best_predicate_ratio": round(best_predicate_ratio, 4),
                "margin": round(margin, 4),
                "matched_question": entries[int(best["entry_index"])].question,
                "matched_query_source": best["query_source"],
                "candidate_count": len(entries),
                "validated_candidate_count": max_validation_candidates,
                "rejected_candidates": rejection_details,
                "semantic_verifier": verifier_result,
                "reason": "No top FAQ candidate passed the conservative cross-signal confidence gate.",
            }

        acceptance_signal = selected_signal
        # Once the confidence gate passes, use only the single best FAQ row. Feeding
        # several merely-similar FAQ answers to the generator creates unnecessary
        # ambiguity. Exact duplicate wording is already handled by the exact branch.
        matched_entry = entries[int(best["entry_index"])]
        selected = [
            matched_entry.as_retrieval_document(
                score=float(best["score"]),
                semantic_score=float(best["semantic_score"]),
                lexical_score=float(best["lexical_score"]),
                mode="faq_semantic",
                matched_query_source=str(best["query_source"]),
            )
        ]

        return selected, {
            "accepted": True,
            "mode": "faq_semantic",
            "best_score": round(float(best["score"]), 4),
            "best_semantic_score": round(best_semantic, 4),
            "best_lexical_score": round(best_lexical, 4),
            "best_enriched_semantic_score": round(best_enriched_semantic, 4),
            "best_weighted_f1": round(best_weighted_f1, 4),
            "best_query_coverage": round(best_query_coverage, 4),
            "best_candidate_precision": round(best_candidate_precision, 4),
            "best_anchor_count": best_anchor_count,
            "best_anchor_ratio": round(best_anchor_ratio, 4),
            "best_predicate_count": best_predicate_count,
            "best_predicate_ratio": round(best_predicate_ratio, 4),
            "margin": round(margin, 4),
            "matched_question": matched_entry.question,
            "matched_query_source": best["query_source"],
            "candidate_count": len(entries),
            "selected_candidate_rank": int(best_rank_index) + 1,
            "rejected_higher_ranked_candidates": rejection_details[:best_rank_index],
            "semantic_verifier": verifier_result,
            "reason": (
                "High-confidence cross-signal match to canonical Vinpearl FAQ "
                f"({acceptance_signal})."
            ),
        }
