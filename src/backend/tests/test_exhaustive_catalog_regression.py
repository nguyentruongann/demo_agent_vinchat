from __future__ import annotations

from types import MethodType, SimpleNamespace

from src.backend.agents.nodes import retrieval as retrieval_node
from src.backend.services.rag import RAGService
from src.backend.services.retrieval_enrichment import _catalog_scope_score


def test_shared_catalog_prefix_is_not_treated_as_many_named_products():
    service = RAGService.__new__(RAGService)
    metadatas = [
        {
            "entity_type": "booking_product",
            "entity_name": f"[VinWonders Nha Trang] - Package {index}",
        }
        for index in range(1, 8)
    ]
    service._load_corpus_cache = MethodType(
        lambda self: {"metadatas": metadatas}, service
    )

    result = service._find_named_entity_mentions("vinwonders nha trang")

    assert result == []


def test_full_booking_product_name_remains_matchable():
    service = RAGService.__new__(RAGService)
    metadatas = [
        {
            "entity_type": "booking_product",
            "entity_name": "[VinWonders Nha Trang] - Sunset Combo",
        },
        {
            "entity_type": "booking_product",
            "entity_name": "[VinWonders Nha Trang] - Happy Hour Combo",
        },
    ]
    service._load_corpus_cache = MethodType(
        lambda self: {"metadatas": metadatas}, service
    )

    result = service._find_named_entity_mentions(
        "cho mình giá [VinWonders Nha Trang] - Sunset Combo"
    )

    assert len(result) == 1
    assert result[0]["name"] == "[VinWonders Nha Trang] - Sunset Combo"


def test_unique_short_property_alias_still_works():
    service = RAGService.__new__(RAGService)
    metadatas = [
        {
            "entity_type": "property",
            "entity_name": "Vinpearl Cua Hoi Resort, Affiliated by Meliá",
        },
        {
            "entity_type": "property",
            "entity_name": "Vinpearl Resort Nha Trang, Affiliated by Meliá",
        },
    ]
    service._load_corpus_cache = MethodType(
        lambda self: {"metadatas": metadatas}, service
    )

    result = service._find_named_entity_mentions("review Vinpearl Cua Hoi Resort")

    assert len(result) == 1
    assert result[0]["name"].startswith("Vinpearl Cua Hoi Resort")


def test_named_property_scope_keeps_its_rooms_and_excludes_peer_properties():
    service = RAGService.__new__(RAGService)
    metadatas = [
        {
            "entity_type": "property",
            "entity_id": "id=vinpearl-resort-nha-trang",
            "entity_name": "Vinpearl Resort Nha Trang",
            "destination_id": "nha-trang",
        }
    ]
    service._load_corpus_cache = MethodType(
        lambda self: {"metadatas": metadatas}, service
    )
    scope = service._named_entity_scope([
        {
            "name": "Vinpearl Resort Nha Trang",
            "type": "property",
            "indices": [0],
        }
    ])

    target_room = {
        "metadata": {
            "entity_type": "room",
            "entity_id": "id=vinpearl-resort-nha-trang--room-1",
            "entity_name": "Grand Deluxe Twin Bed",
            "property_id": "vinpearl-resort-nha-trang",
        }
    }
    peer_property = {
        "metadata": {
            "entity_type": "property",
            "entity_id": "id=vinpearl-resort-spa-nha-trang-bay",
            "entity_name": "Vinpearl Resort & Spa Nha Trang Bay",
        }
    }

    assert service._document_matches_named_entity_scope(target_room, scope) is True
    assert service._document_matches_named_entity_scope(peer_property, scope) is False
    assert service._is_room_catalog_query(
        "What types of rooms are available at Vinpearl Resort Nha Trang?"
    ) is True


def test_catalog_scope_score_is_semantic_and_typo_tolerant():
    query = "cho mình trọn bộ vé và giá ở vinwonder nha trang"

    target = _catalog_scope_score(query, "VINWONDERS NHA TRANG")
    harbour = _catalog_scope_score(query, "VINPEARL HARBOUR NHA TRANG")
    aquafield = _catalog_scope_score(query, "AQUAFIELD NHA TRANG")

    assert target >= 0.74
    assert target > harbour + 0.10
    assert target > aquafield + 0.10


def test_planned_exhaustive_scope_does_not_change_normal_price_lookup():
    exhaustive = {
        "request_tasks": [
            {
                "task_type": "price_lookup",
                "result_scope": "exhaustive",
                "retrieval_intents": ["booking_product"],
            }
        ]
    }
    normal = {
        "request_tasks": [
            {
                "task_type": "price_lookup",
                "result_scope": "normal",
                "retrieval_intents": ["booking_product"],
            }
        ]
    }

    assert retrieval_node._planned_retrieval_requirements(exhaustive) == (
        ["booking_product"], True, False, True
    )
    assert retrieval_node._planned_retrieval_requirements(normal) == (
        ["booking_product"], True, False, False
    )


def test_complete_exhaustive_catalog_clear_passes_without_llm_judge(monkeypatch):
    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(min_relevance_score=0.35),
    )

    class ExplodingLLM:
        def __init__(self):
            raise AssertionError("LLM sufficiency judge must not run for a complete structured catalog")

    monkeypatch.setattr(retrieval_node, "LLMService", ExplodingLLM)

    state = {
        "user_message": "liệt kê trọn bộ vé và giá tại vinwonders nha trang",
        "sanitized_user_request": "liệt kê trọn bộ vé và giá tại vinwonders nha trang",
        "rag_query": "complete VinWonders Nha Trang ticket catalog and prices",
        "price_requested": True,
        "retrieved_documents": [
            {
                "id": "p1",
                "text": "Product A - 30 USD",
                "score": 0.99,
                "metadata": {"entity_type": "booking_product"},
            }
        ],
        "retrieval_mode": "keyword_multi_intent+structured_price",
        "detected_intents": ["booking_product"],
        "intent_results": {
            "booking_product": {"status": "found", "best_score": 0.93}
        },
        "exhaustive_catalog_requested": True,
        "exhaustive_catalog_complete": True,
        "exhaustive_catalog_count": 20,
        "exhaustive_catalog_scope": {
            "scope_type": "booking_venue",
            "venue_name": "VINWONDERS NHA TRANG",
        },
        "request_mode": "information",
        "resolution_mode": "information_only",
    }

    result = retrieval_node.assess_information(state)

    assert result["enough_information"] is True
    assert "20 records" in result["assessment_reason"]


def test_generic_exhaustive_packet_dedupes_entities_across_intent_branches():
    documents = [
        {
            "id": "p1-hotel",
            "text": "Hotel A description",
            "matched_intent": "hotel",
            "metadata": {
                "entity_type": "property",
                "entity_id": "p1",
                "entity_name": "Hotel A",
                "destination_id": "phu-quoc",
            },
        },
        {
            "id": "p1-service",
            "text": "Hotel A service description",
            "matched_intent": "service",
            "metadata": {
                "entity_type": "property",
                "entity_id": "p1",
                "entity_name": "Hotel A",
                "destination_id": "phu-quoc",
            },
        },
        {
            "id": "b1",
            "text": "Water Taxi details",
            "matched_intent": "service",
            "metadata": {
                "entity_type": "booking_product",
                "entity_id": "b1",
                "entity_name": "Water Taxi",
                "destination_id": "phu-quoc",
            },
        },
    ]

    packet = retrieval_node._build_exhaustive_retrieval_packet(
        documents, ["hotel", "service"], complete=True
    )

    assert packet["complete"] is True
    assert packet["entity_count"] == 2
    hotel = next(item for item in packet["entities"] if item["name"] == "Hotel A")
    assert set(hotel["matched_intents"]) == {"hotel", "service"}
    assert packet["branches"]["service"]["entity_count"] == 2


def test_exhaustive_context_round_robin_preserves_multiple_branches():
    service = RAGService.__new__(RAGService)
    service.settings = SimpleNamespace(max_context_chars=4200)
    long_text = "x" * 2200
    documents = [
        {"id": "s1", "text": long_text, "matched_intent": "service", "metadata": {"entity_type": "booking_product", "entity_name": "Service 1"}},
        {"id": "s2", "text": long_text, "matched_intent": "service", "metadata": {"entity_type": "booking_product", "entity_name": "Service 2"}},
        {"id": "h1", "text": long_text, "matched_intent": "hotel", "metadata": {"entity_type": "property", "entity_name": "Hotel 1"}},
        {"id": "a1", "text": long_text, "matched_intent": "attraction", "metadata": {"entity_type": "attraction", "entity_name": "Attraction 1"}},
    ]

    _, diagnostics = service.build_context_with_diagnostics(documents, exhaustive=True)

    assert set(diagnostics["intents"]) >= {"service", "hotel", "attraction"}
    assert diagnostics["document_count"] >= 3


def test_generic_exhaustive_packet_clear_passes_without_llm_judge(monkeypatch):
    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(min_relevance_score=0.35),
    )

    class ExplodingLLM:
        def __init__(self):
            raise AssertionError("LLM sufficiency judge must not run for a complete exhaustive entity packet")

    monkeypatch.setattr(retrieval_node, "LLMService", ExplodingLLM)
    packet = {
        "complete": True,
        "entity_count": 4,
        "requested_intents": ["service", "hotel", "attraction"],
        "branches": {
            "service": {"entity_count": 2, "entity_keys": ["a", "b"]},
            "hotel": {"entity_count": 1, "entity_keys": ["c"]},
            "attraction": {"entity_count": 1, "entity_keys": ["d"]},
        },
        "entities": [
            {"entity_key": "a", "name": "Service A", "entity_type": "booking_product"},
            {"entity_key": "b", "name": "Service B", "entity_type": "amenity"},
            {"entity_key": "c", "name": "Hotel C", "entity_type": "property"},
            {"entity_key": "d", "name": "Attraction D", "entity_type": "attraction"},
        ],
    }
    state = {
        "user_message": "tư vấn toàn bộ dịch vụ tại phú quốc mà bạn có thông tin",
        "sanitized_user_request": "tư vấn toàn bộ dịch vụ tại phú quốc mà bạn có thông tin",
        "retrieved_documents": [
            {"id": "a", "text": "Service A", "score": 1.0, "metadata": {"entity_type": "booking_product"}}
        ],
        "context": "service evidence",
        "context_branch_counts": {"service": 1, "hotel": 1, "attraction": 1},
        "exhaustive_retrieval_requested": True,
        "exhaustive_retrieval_complete": True,
        "exhaustive_retrieval_packet": packet,
        "detected_intents": ["service", "hotel", "attraction"],
        "intent_results": {
            "service": {"status": "found", "best_score": 1.0},
            "hotel": {"status": "found", "best_score": 1.0},
            "attraction": {"status": "found", "best_score": 1.0},
        },
        "request_mode": "information",
        "resolution_mode": "information_only",
    }

    result = retrieval_node.assess_information(state)

    assert result["enough_information"] is True
    assert "4 unique entities" in result["assessment_reason"]


def test_global_destination_count_uses_complete_canonical_catalog(monkeypatch):
    catalog = {
        "ha-noi": {
            "id": "ha-noi", "name_vi": "Hà Nội", "name_en": "Hanoi",
            "province": "Hà Nội", "region": "north", "country": "Vietnam",
            "has_content": True,
        },
        "phu-quoc": {
            "id": "phu-quoc", "name_vi": "Phú Quốc", "name_en": "Phu Quoc",
            "province": "An Giang", "region": "south", "country": "Vietnam",
            "has_content": True,
        },
        "hue": {
            "id": "hue", "name_vi": "Huế", "name_en": "Hue",
            "province": "Huế", "region": "central", "country": "Vietnam",
            "has_content": False,
        },
        "tasmania": {
            "id": "tasmania", "name_vi": "Tasmania", "name_en": "Tasmania",
            "province": "Tasmania", "region": None, "country": "Australia",
            "has_content": True,
        },
    }
    monkeypatch.setattr(retrieval_node, "load_destination_catalog", lambda: catalog)
    state = {
        "resolved_destinations": [],
        "request_tasks": [{
            "task_type": "brand_detail",
            "result_scope": "exhaustive",
            "goal": "List all Vinpearl tourism areas and destinations",
            "source_text": "bạn có tất cả bao nhiêu khu du lịch",
        }],
    }
    packet = retrieval_node._complete_destination_catalog_packet(state, exhaustive=True)
    assert packet["complete"] is True
    assert packet["entity_count"] == 2
    assert [item["destination_id"] for item in packet["entities"]] == ["ha-noi", "phu-quoc"]


def test_global_destination_packet_is_not_built_for_non_exhaustive_request(monkeypatch):
    monkeypatch.setattr(retrieval_node, "load_destination_catalog", lambda: {})
    state = {
        "resolved_destinations": [],
        "request_tasks": [{
            "task_type": "destination_recommendation",
            "result_scope": "normal",
            "goal": "Recommend a destination",
        }],
    }
    assert retrieval_node._complete_destination_catalog_packet(state, exhaustive=False) == {}
