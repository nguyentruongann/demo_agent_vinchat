from __future__ import annotations

from types import MethodType, SimpleNamespace

import src.backend.services.query_parser as query_parser
from src.backend.agents.nodes import retrieval as retrieval_node
from src.backend.services import rag as rag_module
from src.backend.services.llm import LLMService


def _parse_without_catalog(monkeypatch, user_message: str, rag_query: str):
    monkeypatch.setattr(query_parser, "detect_destinations", lambda *_texts: [])
    return query_parser.parse_retrieval_query(user_message, rag_query)


def test_budget_constraint_adds_promotion_without_replacing_service(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "mình muốn trải nghiệm dịch vụ của vinpearl nhưng tài chính chỉ có 2 tr",
        "budget travel options for experiencing Vinpearl services with a 2 million VND budget",
    )

    assert parsed["explicit_intents"] == ["service"]
    assert parsed["intents"] == ["service", "promotion"]
    assert parsed["constraint_derived_intents"] == ["promotion"]
    assert parsed["intent_origin"] == "current_explicit"


def test_monetary_refund_question_does_not_silently_become_promotion(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "tôi cần hoàn tiền 2 triệu cho booking này",
        "I need a 2 million VND refund for this booking",
    )

    assert "policy" in parsed["intents"]
    assert "promotion" not in parsed["intents"]
    assert parsed["constraint_derived_intents"] == []


class _FaqMatcher:
    @staticmethod
    def match(**_kwargs):
        return [], {"accepted": False, "mode": "faq_semantic_rejected"}


def test_corpus_wide_rag_returns_only_intent_evidence_and_preserves_promotion(monkeypatch):
    service = rag_module.RAGService.__new__(rag_module.RAGService)
    service.settings = SimpleNamespace(top_k=5)
    service.faq_matcher = _FaqMatcher()

    monkeypatch.setattr(rag_module, "load_destination_catalog", lambda: {})
    monkeypatch.setattr(
        rag_module,
        "parse_retrieval_query",
        lambda **_kwargs: {
            "destinations": [],
            "intents": ["service", "promotion"],
            "intent": "service",
            "explicit_intents": ["service"],
            "constraint_derived_intents": ["promotion"],
            "intent_origin": "current_explicit",
            "preferred_entity_types": [],
            "preferred_entity_types_by_intent": {},
        },
    )
    service._find_named_entity_mentions = MethodType(lambda self, *_texts: [], service)
    service._retrieve_named_entity_branches = MethodType(lambda self, *_args, **_kwargs: [], service)
    service._exact_faq_matches = MethodType(lambda self, *_args, **_kwargs: [], service)

    irrelevant = {
        "id": "destination-highlight",
        "text": "generic destination article",
        "score": 0.99,
        "metadata": {"entity_type": "destination_highlight", "entity_name": "Generic"},
    }
    service_doc = {
        "id": "amenity",
        "text": "spa amenity evidence",
        "score": 0.89,
        "metadata": {"entity_type": "amenity", "entity_name": "Spa"},
    }
    promotion_doc = {
        "id": "promotion",
        "text": "ticket package 1,150,000 VND",
        "score": 0.88,
        "metadata": {"entity_type": "promotion", "entity_name": "Budget ticket deal"},
    }

    def semantic_many(self, queries, top_k):
        # Every batched query sees the same pool; the strict branch filter must
        # discard the stronger irrelevant destination article.
        return [[irrelevant, service_doc, promotion_doc] for _ in queries]

    service.semantic_search_many = MethodType(semantic_many, service)

    documents, diagnostics = service.hybrid_search(
        query="budget travel options for Vinpearl services with 2 million VND",
        user_message="mình muốn trải nghiệm dịch vụ vinpearl nhưng tài chính chỉ có 2tr",
    )

    assert {item["id"] for item in documents} == {"amenity", "promotion"}
    assert all(item["id"] != "destination-highlight" for item in documents)
    assert diagnostics["intent_results"]["service"]["status"] == "found"
    assert diagnostics["intent_results"]["promotion"]["status"] == "found"
    assert diagnostics["intent_results"]["service"]["best_score"] == 0.89
    assert diagnostics["intent_results"]["promotion"]["best_score"] == 0.88
    assert "intent_filtered" in diagnostics["mode"]


def test_budget_partial_evidence_clear_passes_without_llm_flip(monkeypatch):
    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(min_relevance_score=0.35),
    )

    class ExplodingLLM:
        def __init__(self):
            raise AssertionError("LLM sufficiency judge must not run for authoritative partial evidence")

    monkeypatch.setattr(retrieval_node, "LLMService", ExplodingLLM)

    state = {
        "user_message": "mình muốn trải nghiệm dịch vụ vinpearl nhưng tài chính chỉ có 2tr",
        "sanitized_user_request": "mình muốn trải nghiệm dịch vụ vinpearl nhưng tài chính chỉ có 2tr",
        "rag_query": "budget travel options for Vinpearl services with a 2 million VND budget",
        "retrieved_documents": [
            {
                "id": "promo",
                "text": "Combo ticket 1,150,000 VND",
                "score": 0.8912,
                "metadata": {"entity_type": "promotion"},
            }
        ],
        "context": "Combo ticket 1,150,000 VND",
        "detected_intents": ["service", "promotion"],
        "intent_origin": "current_explicit",
        "intent_results": {
            "service": {"status": "not_found", "document_count": 0, "best_score": 0.0},
            "promotion": {"status": "found", "document_count": 1, "best_score": 0.8912},
        },
        "request_mode": "information",
        "resolution_mode": "information_only",
    }

    result = retrieval_node.assess_information(state)

    assert result["enough_information"] is True
    assert result["best_relevance_score"] == 0.8912
    assert "promotion" in result["assessment_reason"]
    assert "service" in result["assessment_reason"]


def test_authoritative_missing_intent_cannot_be_rescued_by_unrelated_document(monkeypatch):
    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(min_relevance_score=0.35),
    )

    class ExplodingLLM:
        def __init__(self):
            raise AssertionError("LLM sufficiency judge must not run for deterministic missing branch")

    monkeypatch.setattr(retrieval_node, "LLMService", ExplodingLLM)

    state = {
        "user_message": "mình muốn trải nghiệm dịch vụ vinpearl",
        "sanitized_user_request": "mình muốn trải nghiệm dịch vụ vinpearl",
        "rag_query": "Vinpearl services",
        "retrieved_documents": [
            {
                "id": "unrelated",
                "text": "unrelated but high-scoring promotion",
                "score": 0.99,
                "metadata": {"entity_type": "promotion"},
            }
        ],
        "context": "unrelated but high-scoring promotion",
        "detected_intents": ["service"],
        "intent_origin": "current_explicit",
        "intent_results": {
            "service": {
                "status": "not_found",
                "document_count": 0,
                "best_score": 0.0,
            }
        },
        "request_mode": "information",
        "resolution_mode": "information_only",
    }

    result = retrieval_node.assess_information(state)

    assert result["enough_information"] is False
    assert result["best_relevance_score"] == 0.0
    assert "No requested intent branch" in result["assessment_reason"]


def test_json_control_calls_default_to_zero_temperature(monkeypatch):
    captured = {}

    class _Message:
        content = '{"ok": true}'

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _Response()

    import src.backend.services.llm as llm_module

    monkeypatch.setattr(llm_module, "completion", fake_completion)
    service = LLMService.__new__(LLMService)
    service.model = "gemini/test"
    service.api_key = "test-key"
    service.api_key_backup = None
    service.base_url = None
    service.temperature = 0.2
    service.max_tokens = 100
    service.timeout = 1.0
    service.max_retries = 1

    assert service.json(system_prompt="control", user_prompt="input") == {"ok": True}
    assert captured["temperature"] == 0.0

    service.text(system_prompt="answer", user_prompt="input")
    assert captured["temperature"] == 0.2


def test_budget_where_to_go_remains_discovery_plus_constraint(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "mình muốn xõa stress, tài chính 2 tr nên đi đâu",
        "Vinpearl destinations and experiences options under 2 million VND budget",
    )

    assert parsed["intent_origin"] == "generic_discovery"
    assert parsed["intents"][:4] == list(query_parser.GENERIC_DISCOVERY_INTENTS)
    assert parsed["intents"][-1] == "promotion"
    assert parsed["constraint_derived_intents"] == ["promotion"]
    assert parsed["has_budget_constraint"] is True
    assert parsed["budget_vnd"] == 2_000_000


def test_budget_price_filter_prefers_actual_affordable_offer(monkeypatch):
    service = rag_module.RAGService.__new__(rag_module.RAGService)
    service.settings = SimpleNamespace(top_k=5)
    service.faq_matcher = _FaqMatcher()

    monkeypatch.setattr(rag_module, "load_destination_catalog", lambda: {})
    monkeypatch.setattr(
        rag_module,
        "parse_retrieval_query",
        lambda **_kwargs: {
            "destinations": [],
            "intents": ["promotion"],
            "intent": "promotion",
            "explicit_intents": [],
            "constraint_derived_intents": ["promotion"],
            "has_budget_constraint": True,
            "budget_vnd": 2_000_000,
            "intent_origin": "constraint_derived",
            "preferred_entity_types": ["promotion"],
            "preferred_entity_types_by_intent": {"promotion": ["promotion"]},
        },
    )
    service._find_named_entity_mentions = MethodType(lambda self, *_texts: [], service)
    service._retrieve_named_entity_branches = MethodType(lambda self, *_args, **_kwargs: [], service)
    service._exact_faq_matches = MethodType(lambda self, *_args, **_kwargs: [], service)

    expensive = {
        "id": "expensive",
        "text": "Luxury package 6,700,000 VND; complimentary gift worth 100,000 VND",
        "score": 0.95,
        "metadata": {"entity_type": "promotion", "entity_name": "Luxury package"},
    }
    affordable = {
        "id": "affordable",
        "text": "VinWonders Nha Trang 2-day unlimited ticket | 1,350,000 VND",
        "score": 0.80,
        "metadata": {"entity_type": "promotion", "entity_name": "Nha Trang 2-day ticket"},
    }

    service.semantic_search_many = MethodType(
        lambda self, queries, top_k: [[expensive, affordable] for _ in queries],
        service,
    )

    documents, diagnostics = service.hybrid_search(
        query="Vinpearl destinations under 2 million VND budget",
        user_message="tài chính 2 tr nên đi đâu",
    )

    assert [item["id"] for item in documents] == ["affordable"]
    assert documents[0]["budget_matched_prices"] == [1_350_000]
    assert diagnostics["intent_results"]["promotion"]["status"] == "found"
    assert diagnostics["intent_results"]["promotion"]["constraint_satisfied"] is True
    assert diagnostics["intent_results"]["promotion"]["budget_matched_prices"] == [1_350_000]


def test_budget_constraint_cannot_be_rescued_by_generic_discovery(monkeypatch):
    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(min_relevance_score=0.35),
    )

    class ExplodingLLM:
        def __init__(self):
            raise AssertionError("budget constraint failure must be deterministic")

    monkeypatch.setattr(retrieval_node, "LLMService", ExplodingLLM)

    state = {
        "user_message": "mình muốn xõa stress, tài chính 2 tr nên đi đâu",
        "sanitized_user_request": "mình muốn xõa stress, tài chính 2 tr nên đi đâu",
        "rag_query": "Vinpearl destinations and experiences under 2 million VND",
        "retrieved_documents": [
            {
                "id": "destination",
                "text": "A great Vinpearl destination for relaxation",
                "score": 0.90,
                "metadata": {"entity_type": "destination"},
            }
        ],
        "context": "A great Vinpearl destination for relaxation",
        "detected_intents": ["attraction", "hotel", "dining", "service", "promotion"],
        "constraint_derived_intents": ["promotion"],
        "has_budget_constraint": True,
        "budget_vnd": 2_000_000,
        "intent_origin": "generic_discovery",
        "intent_results": {
            "attraction": {"status": "found", "document_count": 1, "best_score": 0.90},
            "hotel": {"status": "not_found", "document_count": 0, "best_score": 0.0},
            "dining": {"status": "not_found", "document_count": 0, "best_score": 0.0},
            "service": {"status": "not_found", "document_count": 0, "best_score": 0.0},
            "promotion": {
                "status": "not_found",
                "document_count": 0,
                "best_score": 0.0,
                "constraint_satisfied": False,
            },
        },
        "request_mode": "information",
        "resolution_mode": "information_only",
    }

    result = retrieval_node.assess_information(state)

    assert result["enough_information"] is False
    assert "Budget constraint is not grounded" in result["assessment_reason"]
