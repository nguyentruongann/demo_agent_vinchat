from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from src.backend.agents.nodes import request_understanding
from src.backend.agents.nodes import retrieval as retrieval_node
from src.backend.services.faq_matcher import FAQEntry, FAQMatcher
from src.backend.services.retrieval_enrichment import _structured_price_lanes


def _planner_task(message: str, task_type: str) -> dict:
    return request_understanding._normalize_task(
        {
            "task_type": task_type,
            "result_scope": "normal",
            "goal": "Explain how to start buying VinWonders tickets.",
            "source_text": message,
            "retrieval_intents": ["booking_product", "attraction"],
            "retrieval_queries": ["VinWonders ticket purchase guide"],
            "needs_retrieval": True,
        },
        1,
    )


def test_how_to_buy_tickets_is_not_numeric_price_lookup() -> None:
    task = _planner_task(
        "Tôi định đưa vợ và con 6 tuổi đi Phú Quốc chơi VinWonders, "
        "không biết bắt đầu nên mua vé thế nào?",
        "price_lookup",
    )

    assert task is not None
    assert task["task_type"] == "general_qa"
    assert task["task_type_repaired_from"] == "price_lookup"
    assert task["price_requested"] is False
    assert "booking_product" in task["retrieval_intents"]
    assert retrieval_node._planned_retrieval_requirements({"request_tasks": [task]})[1] is False


def test_explicit_ticket_price_remains_price_lookup() -> None:
    task = _planner_task(
        "Giá vé VinWonders Phú Quốc cho người lớn và trẻ em bao nhiêu?",
        "price_lookup",
    )

    assert task is not None
    assert task["task_type"] == "price_lookup"
    assert "task_type_repaired_from" not in task
    assert retrieval_node._planned_retrieval_requirements({"request_tasks": [task]})[1] is True


def test_ticket_price_lane_excludes_unrelated_room_prices() -> None:
    assert _structured_price_lanes(
        ["booking_product", "attraction"],
        cost_estimate_requested=False,
    ) == (False, True)
    assert _structured_price_lanes(
        ["hotel"],
        cost_estimate_requested=False,
    ) == (True, False)
    assert _structured_price_lanes(
        ["hotel", "booking_product"],
        cost_estimate_requested=True,
    ) == (True, True)


def test_verified_faq_supplement_clear_passes_single_non_price_task(monkeypatch) -> None:
    class ExplodingLLM:
        def __init__(self):
            raise AssertionError("generic sufficiency judge must not reject a verified FAQ")

    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(min_relevance_score=0.35),
    )
    monkeypatch.setattr(retrieval_node, "LLMService", ExplodingLLM)

    state = {
        "user_message": "Không biết bắt đầu nên mua vé thế nào?",
        "rag_query": "How to buy VinWonders tickets",
        "request_task_count": 1,
        "price_requested": False,
        "retrieval_mode": "keyword_multi_intent+booking_focus+faq_supplement",
        "retrieved_documents": [
            {
                "id": "faq-ticket-purchase",
                "text": "Official FAQ purchase guidance.",
                "score": 0.61,
                "metadata": {
                    "entity_type": "faq",
                    "entity_name": "Can I purchase a ticket package for VinWonders?",
                },
            }
        ],
        "intent_results": {
            "attraction": {
                "status": "found",
                "best_score": 0.61,
                "faq_match": True,
            },
            "booking_product": {
                "status": "found",
                "best_score": 0.60,
            },
        },
        "detected_intents": ["attraction", "booking_product"],
        "request_mode": "information",
        "resolution_mode": "information_only",
    }

    result = retrieval_node.assess_information(state)

    assert result["enough_information"] is True
    assert "FAQ clear-pass" in result["assessment_reason"]


def test_faq_vector_cache_round_trip(tmp_path) -> None:
    matcher = FAQMatcher(embed_passages=lambda values: [], embed_queries=lambda values: [])
    matcher.settings = SimpleNamespace(
        chroma_dir=tmp_path,
        embedding_backend="gemini_api",
        gemini_embedding_model="gemini-embedding-001",
    )
    entries = [
        FAQEntry(
            index=0,
            question="How do I buy a ticket?",
            answer="Use the official website or ticket counter.",
            category="Tickets",
            subcategory="Purchase",
            source_url="https://example.test/faq",
            language="en",
            source_path="test",
        )
    ]
    question_vectors = np.asarray([[0.1, 0.2, 0.3]], dtype=np.float32)
    enriched_vectors = np.asarray([[0.4, 0.5, 0.6]], dtype=np.float32)

    matcher._save_vector_cache(entries, question_vectors, enriched_vectors)
    matcher._question_vectors = None
    matcher._enriched_vectors = None

    assert matcher._load_vector_cache(entries) is True
    np.testing.assert_allclose(matcher._question_vectors, question_vectors)
    np.testing.assert_allclose(matcher._enriched_vectors, enriched_vectors)
