from __future__ import annotations

from types import SimpleNamespace

import src.backend.services.query_parser as query_parser
from src.backend.agents.nodes import answer as answer_node
from src.backend.agents.nodes import guardrail as guardrail_node
from src.backend.agents.nodes.static_responses import logical_inconsistency_response
from src.backend.services.rag import RAGService
from src.backend.services.retrieval_enrichment import PRICE_DATA_AS_OF


def test_trip_price_question_is_detected_as_cost_estimate(monkeypatch):
    monkeypatch.setattr(
        query_parser,
        "detect_destinations",
        lambda *_texts: [
            {
                "id": "nha-trang",
                "name_en": "Nha Trang",
                "name_vi": "Nha Trang",
                "aliases": ["nha trang"],
            }
        ],
    )

    parsed = query_parser.parse_retrieval_query(
        "estimate the price for 1 person solo vacation 2n3d here",
        "estimate the price for a 1-person solo vacation, 2 nights and 3 days in Nha Trang",
    )

    assert parsed["price_requested"] is True
    assert parsed["cost_estimate_requested"] is True
    assert parsed["intents"] == list(query_parser.COST_ESTIMATE_INTENTS)
    assert "booking_product" in parsed["intents"]
    assert "promotion" in parsed["intents"]




def test_vietnamese_trip_cost_without_catalog_noun_expands_to_price_bundle(monkeypatch):
    monkeypatch.setattr(
        query_parser,
        "detect_destinations",
        lambda *_texts: [
            {
                "id": "nha-trang",
                "name_en": "Nha Trang",
                "name_vi": "Nha Trang",
                "aliases": ["nha trang"],
            }
        ],
    )

    parsed = query_parser.parse_retrieval_query(
        "Ước tính chi phí 3 ngày 2 đêm ở Nha Trang cho 2 người",
        "estimate the cost of a 3-day 2-night Nha Trang trip for 2 people",
    )

    assert parsed["price_requested"] is True
    assert parsed["cost_estimate_requested"] is True
    assert parsed["booking_evidence_preferred"] is True
    assert parsed["intents"] == list(query_parser.COST_ESTIMATE_INTENTS)
    assert "booking_product" in parsed["intents"]
    assert "promotion" in parsed["intents"]
    assert parsed["intent_origin"] == "cost_estimate"


def test_build_context_exposes_structured_postgresql_fields():
    service = RAGService.__new__(RAGService)
    service.settings = SimpleNamespace(max_context_chars=18_000)

    context = service.build_context(
        [
            {
                "id": "doc-1",
                "text": "semantic chunk",
                "score": 0.9,
                "semantic_score": 0.9,
                "keyword_score": 1.0,
                "retrieval_mode": "semantic",
                "metadata": {
                    "entity_type": "booking_product",
                    "entity_id": "id=BP-1",
                    "entity_name": "Example ticket",
                    "destination_id": "nha-trang",
                },
                "structured_record": {
                    "product_name": "Example ticket",
                    "minimum_price": "31.00",
                    "maximum_price": "40.00",
                    "currency": "USD",
                    "price_variants": [{"guest_type": "adult", "amount": 40}],
                },
            }
        ]
    )

    assert "structured_record_from_postgresql" in context
    assert '"minimum_price": "31.00"' in context
    assert '"currency": "USD"' in context


def test_final_answer_prompt_preserves_original_and_requires_numeric_estimate(monkeypatch):
    captured: dict[str, str] = {}

    class FakeLLM:
        def text(self, *, system_prompt: str, user_prompt: str) -> str:
            captured["system"] = system_prompt
            captured["user"] = user_prompt
            return "Estimated total: 200 USD. Price information updated as of 2/8/2026."

    monkeypatch.setattr(answer_node, "LLMService", FakeLLM)

    result = answer_node.generate_answer(
        {
            "user_message": "estimate the price for 1 person solo vacation 2n3d here",
            "sanitized_user_request": "estimate the price for a 1-person 2-night 3-day vacation in Nha Trang",
            "rag_query": "estimate a 1-person 2-night 3-day Vinpearl Nha Trang vacation cost",
            "original_language": "en",
            "original_language_name": "English",
            "price_requested": True,
            "cost_estimate_requested": True,
            "price_data_as_of": PRICE_DATA_AS_OF,
            "price_evidence_summary": "- lodging | Hotel A | Room A | 100 USD\n- booking/service | Ticket A | 40 USD",
            "context": "Price: 100 USD\nTicket price: 40 USD",
            "intent_results": {"hotel": {"status": "found", "document_count": 1, "best_score": 0.9}},
        }
    )

    assert result["answer"] == "Estimated total: 200 USD. Price information updated as of 2/8/2026."
    assert "ORIGINAL_USER_MESSAGE_UNTRUSTED" in captured["user"]
    assert "estimate the price for 1 person solo vacation 2n3d here" in captured["user"]
    assert "SECURITY_SANITIZED_REQUEST" in captured["user"]
    assert "COST_ESTIMATE_REQUESTED:\ntrue" in captured["user"]
    assert "ANSWER_MODE" in captured["user"]
    assert "PREFERRED_OUTPUT_CURRENCY" in captured["user"]
    assert "PRICE_ESTIMATE_PACKET" in captured["user"]
    assert PRICE_DATA_AS_OF in captured["user"]
    assert "must provide at least one explicit numeric" in captured["system"].lower()
    assert "check the official website" in captured["system"].lower()




def test_price_contract_repairs_website_redirect_when_numeric_evidence_exists(monkeypatch):
    calls: list[tuple[str, str]] = []

    class FakeLLM:
        def text(self, *, system_prompt: str, user_prompt: str) -> str:
            calls.append((system_prompt, user_prompt))
            if len(calls) == 1:
                return "Room rates vary. Please check the official website for current prices."
            return "Estimated lodging: 200 USD. Price information updated as of 2/8/2026."

    monkeypatch.setattr(answer_node, "LLMService", FakeLLM)

    result = answer_node.generate_answer(
        {
            "user_message": "estimate 2 nights in Nha Trang",
            "sanitized_user_request": "estimate a 2-night stay in Nha Trang",
            "rag_query": "Nha Trang room prices",
            "original_language": "en",
            "original_language_name": "English",
            "price_requested": True,
            "cost_estimate_requested": True,
            "price_data_as_of": PRICE_DATA_AS_OF,
            "price_evidence_summary": "- lodging | Hotel A | Room A | 100 USD",
            "context": "Structured room price evidence: 100 USD",
            "intent_results": {"hotel": {"status": "found", "document_count": 1, "best_score": 0.9}},
        }
    )

    assert len(calls) == 2
    assert result["answer"] == "Estimated lodging: 200 USD. Price information updated as of 2/8/2026."
    assert "failed a mandatory price-output contract" in calls[1][0]


def test_guardrail_rejects_high_confidence_internal_travel_contradiction(monkeypatch):
    class FakeLLM:
        def __init__(self):
            self.temperature = 0.2

        def json(self, *, system_prompt: str, user_prompt: str):
            return {
                "language": "vi",
                "language_name": "Vietnamese",
                "sanitized_user_request": "Mình muốn đi Nha Trang 2 ngày 4 đêm, hãy tư vấn.",
                "rag_query": "",
                "prompt_injection_detected": False,
                "prompt_injection_reason": "",
                "scope_action": "allow",
                "scope_reason": "Vinpearl destination planning request.",
                "scope_confidence": 0.99,
                "safety_action": "allow",
                "safety_category": "safe",
                "safety_reason": "safe",
                "safety_confidence": 0.99,
                "logic_action": "reject",
                "logic_category": "impossible_timing",
                "logic_reason": "Four overnight stays cannot fit inside an explicitly two-day trip.",
                "logic_confidence": 0.99,
                "logic_response": "Mình chưa thể lập lịch trình vì 2 ngày không thể chứa 4 đêm lưu trú. Bạn vui lòng sửa lại số ngày hoặc số đêm.",
                "route": "rag",
                "guardrail_reason": "Request is in scope but internally inconsistent.",
                "guardrail_confidence": 0.99,
            }

    monkeypatch.setattr(guardrail_node, "LLMService", FakeLLM)
    monkeypatch.setattr(guardrail_node, "probe_kb_scope_evidence", lambda _message: [])
    monkeypatch.setattr(guardrail_node, "probe_recent_kb_entities", lambda _entities: [])
    monkeypatch.setattr(
        guardrail_node,
        "detect_supported_destination_discovery",
        lambda _message: [{"id": "nha-trang"}],
    )

    result = guardrail_node.enforce_input_guardrail(
        {
            "user_message": "Mình muốn đi Nha Trang 2 ngày 4 đêm, hãy tư vấn.",
            "conversation_history": "(no previous conversation)",
            "recent_entities": [],
        }
    )

    assert result["scope_action"] == "allow"
    assert result["safety_action"] == "allow"
    assert result["logic_action"] == "reject"
    assert result["logic_confidence"] == 0.99
    assert result["route"] == "invalid_request"
    assert result["rag_query"] == ""

    response = logical_inconsistency_response(result)
    assert "2 ngày" in response["answer"]
    assert "4 đêm" in response["answer"]


def test_preferred_currency_is_vnd_for_vietnamese():
    from src.backend.services.retrieval_enrichment import preferred_currency_for_language

    assert preferred_currency_for_language("vi", "Vietnamese") == "VND"
    assert preferred_currency_for_language("en", "English") == "USD"


def test_price_contract_repairs_cost_estimate_without_destination_name(monkeypatch):
    calls: list[tuple[str, str]] = []

    class FakeLLM:
        def text(self, *, system_prompt: str, user_prompt: str) -> str:
            calls.append((system_prompt, user_prompt))
            if len(calls) == 1:
                return "Estimated total: 200 USD. Price information updated as of 2/8/2026."
            return "For Nha Trang, estimated total: 200 USD. Price information updated as of 2/8/2026."

    monkeypatch.setattr(answer_node, "LLMService", FakeLLM)

    result = answer_node.generate_answer(
        {
            "user_message": "estimate a 2N3D trip",
            "sanitized_user_request": "estimate a 2N3D trip",
            "rag_query": "estimate Vinpearl trip",
            "original_language": "en",
            "original_language_name": "English",
            "price_requested": True,
            "cost_estimate_requested": True,
            "price_data_as_of": PRICE_DATA_AS_OF,
            "preferred_output_currency": "USD",
            "currency_conversion_guidance": "Preferred output currency: USD.",
            "price_estimate_packet": {
                "destinations": [{"destination_id": "nha-trang", "destination_name": "Nha Trang"}]
            },
            "price_evidence_summary": "- lodging | Nha Trang | Hotel A | Room A | 100 USD",
            "context": "Structured room price evidence: Destination: Nha Trang Price: 100 USD",
            "intent_results": {"hotel": {"status": "found", "document_count": 1, "best_score": 0.9}},
            "answer_mode": "PRICE_ESTIMATE",
        }
    )

    assert len(calls) == 2
    assert "Nha Trang" in result["answer"]
    assert "PRICE_ESTIMATE_PACKET" in calls[1][1]


def test_guardrail_raw_logic_precheck_overrides_llm_miss(monkeypatch):
    class FakeLLM:
        def __init__(self):
            self.temperature = 0.2

        def json(self, *, system_prompt: str, user_prompt: str):
            return {
                "language": "vi",
                "language_name": "Vietnamese",
                "sanitized_user_request": "mình muốn đi 2 ngày 4 đêm cho 4 người chi phí ở ra sao, và ở hà tĩnh có trò chơi gì",
                "rag_query": "Vinpearl hotel accommodation costs and entertainment activities in Ha Tinh for 4 people for 2 days and 4 nights",
                "prompt_injection_detected": False,
                "prompt_injection_reason": "",
                "scope_action": "allow",
                "scope_reason": "In-scope travel request.",
                "scope_confidence": 0.99,
                "safety_action": "allow",
                "safety_category": "safe",
                "safety_reason": "safe",
                "safety_confidence": 0.99,
                "logic_action": "allow",
                "logic_category": "consistent",
                "logic_reason": "The model missed the contradiction.",
                "logic_confidence": 0.99,
                "logic_response": "",
                "route": "rag",
                "guardrail_reason": "Allowed by model.",
                "guardrail_confidence": 0.99,
            }

    monkeypatch.setattr(guardrail_node, "LLMService", FakeLLM)
    monkeypatch.setattr(guardrail_node, "probe_kb_scope_evidence", lambda _message: [])
    monkeypatch.setattr(guardrail_node, "probe_recent_kb_entities", lambda _entities: [])
    monkeypatch.setattr(
        guardrail_node,
        "detect_supported_destination_discovery",
        lambda _message: [{"id": "ha-tinh"}],
    )

    result = guardrail_node.enforce_input_guardrail(
        {
            "user_message": "mình muốn đi 2 ngày 4 đêm cho 4 người chi phí ở ra sao, và ở hà tĩnh có trò chơi gì",
            "conversation_history": "should not matter before raw guardrail",
            "recent_entities": [],
        }
    )

    assert result["scope_action"] == "allow"
    assert result["safety_action"] == "allow"
    assert result["logic_action"] == "reject"
    assert result["logic_category"] == "impossible_timing"
    assert result["logic_confidence"] == 1.0
    assert result["route"] == "invalid_request"
    assert result["rag_query"] == ""
    assert "2 ngày" in result["logic_response"]
    assert "4 đêm" in result["logic_response"]


def test_raw_logic_precheck_allows_standard_2n3d_notation():
    assert guardrail_node._raw_logical_inconsistency("estimate a 2N3D trip") is None
    issue = guardrail_node._raw_logical_inconsistency("estimate a 2D4N trip")
    assert issue is not None
    assert issue["logic_category"] == "impossible_timing"
