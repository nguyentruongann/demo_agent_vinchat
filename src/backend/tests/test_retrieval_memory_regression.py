from types import SimpleNamespace

from src.backend.agents.nodes import retrieval as retrieval_node
from src.backend.services import query_parser
from src.backend.services.memory import MemoryService


def test_rewrite_intents_are_marked_as_inferred_not_explicit(monkeypatch) -> None:
    # Keep this unit test independent from PostgreSQL destination catalog loading.
    monkeypatch.setattr(query_parser, "load_destination_catalog", lambda: {})

    parsed = query_parser.parse_retrieval_query(
        "thế có nơi nào cảnh quan thiên nhiên, nhiều cây không bạn",
        "Vinpearl resorts or VinWonders locations with natural landscapes and lots of trees",
    )

    assert parsed["explicit_intents"] == []
    assert parsed["intent_origin"] == "generic_discovery"
    assert parsed["intents"] == list(query_parser.GENERIC_DISCOVERY_INTENTS)


def test_current_explicit_intent_keeps_authoritative_origin(monkeypatch) -> None:
    monkeypatch.setattr(query_parser, "load_destination_catalog", lambda: {})

    parsed = query_parser.parse_retrieval_query(
        "khách sạn nào phù hợp gia đình?",
        "Which Vinpearl hotel is suitable for a family?",
    )

    assert parsed["explicit_intents"] == ["hotel"]
    assert parsed["intents"] == ["hotel"]
    assert parsed["intent_origin"] == "current_explicit"


def test_memory_retrieval_does_not_leak_old_intents_into_current_turn(monkeypatch) -> None:
    class FakeRag:
        def hybrid_search(self, *, query, user_message, resolved_destinations=None, top_k=None, **kwargs):
            if query == "current query":
                return (
                    [{"id": "current", "text": "current evidence", "score": 0.9, "metadata": {"entity_type": "attraction"}}],
                    {
                        "mode": "semantic_fallback",
                        "intent": "attraction",
                        "intents": ["attraction"],
                        "explicit_intents": [],
                        "intent_origin": "rewrite_inferred",
                        "intent_results": {"attraction": {"status": "found", "document_count": 1}},
                        "destinations": [],
                        "destination_ids": [],
                        "destination_names": [],
                        "keyword_candidate_count": 0,
                        "missing_destination_ids": [],
                    },
                )
            return (
                [{"id": "old", "text": "old hotel evidence", "score": 0.8, "metadata": {"entity_type": "property"}}],
                {
                    "mode": "semantic_fallback",
                    "intent": "hotel",
                    "intents": ["hotel"],
                    "intent_results": {"hotel": {"status": "found", "document_count": 1}},
                    "destinations": [],
                    "destination_ids": [],
                    "destination_names": [],
                    "keyword_candidate_count": 0,
                    "missing_destination_ids": [],
                },
            )

        @staticmethod
        def build_context(documents):
            return "\n".join(item["text"] for item in documents)

        @staticmethod
        def build_context_with_diagnostics(documents, **_kwargs):
            context = "\n".join(item["text"] for item in documents)
            intents = sorted({
                str((item.get("metadata") or {}).get("entity_type") or "")
                for item in documents
                if str((item.get("metadata") or {}).get("entity_type") or "")
            })
            return context, {
                "document_count": len(documents),
                "branch_counts": {},
                "intents": intents,
                "task_counts": {},
            }

    monkeypatch.setattr(retrieval_node, "get_rag_service", lambda: FakeRag())
    monkeypatch.setattr(retrieval_node, "get_settings", lambda: SimpleNamespace(top_k=5))

    state = {
        "rag_query": "current query",
        "user_message": "tư vấn kỹ hơn về các nơi này",
        "selected_memory_turn_refs": ["turn:1"],
        "conversation_turns": [
            {
                "memory_ref": "turn:1",
                "route": "rag",
                "rag_query": "old query",
                "user_message": "old hotel question",
                "resolved_destinations": [],
            }
        ],
    }

    result = retrieval_node.retrieve_context(state)

    assert result["memory_augmented"] is True
    assert result["detected_intents"] == ["attraction"]
    assert "hotel" not in result["intent_results"]
    assert {item["id"] for item in result["retrieved_documents"]} == {"current", "old"}


def test_old_turn_documents_are_filtered_to_current_property_scope() -> None:
    documents = [
        {
            "id": "target-room",
            "metadata": {
                "entity_type": "room",
                "entity_name": "Grand Deluxe Twin Bed",
                "property_id": "vinpearl-resort-nha-trang",
            },
        },
        {
            "id": "peer-property",
            "metadata": {
                "entity_type": "property",
                "entity_name": "Vinpearl Resort & Spa Nha Trang Bay",
                "entity_id": "id=vinpearl-resort-spa-nha-trang-bay",
            },
        },
        {
            "id": "unrelated-attraction",
            "metadata": {
                "entity_type": "attraction",
                "entity_name": "VinWonders Nha Trang",
            },
        },
    ]
    scope = {
        "names": ["Vinpearl Resort Nha Trang"],
        "normalized_names": ["vinpearl resort nha trang"],
        "entity_ids": ["vinpearl-resort-nha-trang", "id=vinpearl-resort-nha-trang"],
    }

    filtered, discarded = retrieval_node._filter_memory_documents_to_entity_scope(
        documents, scope
    )

    assert [item["id"] for item in filtered] == ["target-room"]
    assert discarded == 2


def test_exhaustive_entity_followup_does_not_replay_old_broad_query(monkeypatch) -> None:
    calls: list[str] = []

    class FakeRag:
        def hybrid_search(self, **kwargs):
            query = kwargs["query"]
            calls.append(query)
            if query == "old broad Nha Trang hotels":
                raise AssertionError("old broad memory evidence must not be replayed")
            return (
                [
                    {
                        "id": "room-1",
                        "text": "Grand Deluxe Twin Bed",
                        "score": 1.0,
                        "matched_intent": "hotel",
                        "metadata": {
                            "entity_type": "room",
                            "entity_id": "id=room-1",
                            "entity_name": "Grand Deluxe Twin Bed",
                            "property_id": "vinpearl-resort-nha-trang",
                        },
                    }
                ],
                {
                    "mode": "named_entity:keyword_then_embedding+exhaustive",
                    "intent": "hotel",
                    "intents": ["hotel"],
                    "explicit_intents": ["hotel"],
                    "intent_results": {
                        "hotel": {
                            "status": "found",
                            "document_count": 1,
                            "candidate_count": 1,
                            "best_score": 1.0,
                            "missing_destination_ids": [],
                        }
                    },
                    "destinations": [{"id": "nha-trang", "name_vi": "Nha Trang"}],
                    "destination_ids": ["nha-trang"],
                    "destination_names": ["Nha Trang"],
                    "keyword_candidate_count": 1,
                    "missing_destination_ids": [],
                    "exhaustive_retrieval_complete": True,
                    "named_entity_scope": {
                        "names": ["Vinpearl Resort Nha Trang"],
                        "normalized_names": ["vinpearl resort nha trang"],
                        "entity_ids": ["vinpearl-resort-nha-trang"],
                    },
                },
            )

        @staticmethod
        def build_context_with_diagnostics(documents, exhaustive=False, task_aware=False):
            return (
                "\n".join(item["text"] for item in documents),
                {
                    "document_count": len(documents),
                    "branch_counts": {"hotel": len(documents)},
                    "intents": ["hotel"],
                    "entity_keys": [item["id"] for item in documents],
                    "task_counts": {},
                    "task_ids": [],
                },
            )

    def fake_enrich(documents, **_kwargs):
        return documents, {
            "structured_price_document_count": 0,
            "structured_enrichment_count": 0,
            "price_estimate_packet": {},
            "price_estimate_destination_ids": [],
            "preferred_output_currency": "VND",
            "currency_conversion_guidance": "",
        }

    monkeypatch.setattr(retrieval_node, "get_rag_service", lambda: FakeRag())
    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(top_k=5, min_relevance_score=0.35),
    )
    monkeypatch.setattr(retrieval_node, "enrich_retrieved_documents", fake_enrich)

    state = {
        "rag_query": "room types at Vinpearl Resort Nha Trang",
        "user_message": "Chỗ đó có những loại phòng nào?",
        "resolved_destinations": [{"id": "nha-trang", "name_vi": "Nha Trang"}],
        "resolved_entity_names": ["Vinpearl Resort Nha Trang"],
        "selected_memory_turn_refs": ["turn:1"],
        "conversation_turns": [
            {
                "memory_ref": "turn:1",
                "route": "rag",
                "rag_query": "old broad Nha Trang hotels",
                "user_message": "khách sạn Nha Trang",
            }
        ],
        "request_tasks": [
            {
                "task_id": "t1",
                "task_type": "property_detail",
                "result_scope": "exhaustive",
                "retrieval_intents": ["hotel"],
                "needs_retrieval": True,
            }
        ],
    }

    result = retrieval_node.retrieve_context(state)

    assert calls == ["room types at Vinpearl Resort Nha Trang"]
    assert result["memory_augmented"] is False
    assert [item["id"] for item in result["retrieved_documents"]] == ["room-1"]
    assert result["exhaustive_retrieval_packet"]["entity_count"] == 1
    assert result["exhaustive_retrieval_packet"]["entity_scope"]["names"] == [
        "Vinpearl Resort Nha Trang"
    ]


def test_assistant_suggested_destination_is_recallable_but_not_user_focus() -> None:
    memory = MemoryService.__new__(MemoryService)
    turns = [
        {
            "route": "rag",
            "detected_destinations": [],
            "resolved_destinations": [],
            "focus_entities": [
                {
                    "name": "VinWonders Grand Park",
                    "type": "attraction",
                    "source": "assistant_suggestion_kb",
                    "destination_id": "ho-chi-minh",
                }
            ],
        }
    ]

    assert memory.extract_recent_destinations(turns) == []

    discussed = memory.extract_recent_discussed_destinations(turns)
    assert discussed[0]["id"] == "ho-chi-minh"
    assert discussed[0]["source"] == "assistant_suggestion"
    assert discussed[0]["confirmed"] == "false"


def test_explicit_user_destination_still_becomes_user_focus(monkeypatch) -> None:
    memory = MemoryService.__new__(MemoryService)
    monkeypatch.setattr(
        "src.backend.services.query_parser.detect_destinations",
        lambda _text: [{"id": "nha-trang", "name_vi": "Nha Trang"}],
    )
    turns = [
        {
            "route": "rag",
            "user_message": "mình muốn đi Nha Trang",
            "detected_destinations": [
                {"id": "nha-trang", "name": "Nha Trang", "source": "retrieval_detection"}
            ],
            "resolved_destinations": [],
            "focus_entities": [],
        }
    ]

    destinations = memory.extract_recent_destinations(turns)
    assert destinations[0]["id"] == "nha-trang"


def test_logic_rejected_turn_recovers_single_explicit_destination_as_user_focus(monkeypatch) -> None:
    memory = MemoryService.__new__(MemoryService)
    monkeypatch.setattr(
        "src.backend.services.query_parser.detect_destinations",
        lambda _text: [{"id": "phu-quoc", "name_vi": "Phú Quốc"}],
    )
    turns = [
        {
            "route": "invalid_request",
            "logic_action": "reject",
            "scope_action": "allow",
            "safety_action": "allow",
            "user_message": "mình muốn đi Phú Quốc 2 ngày 3 đêm",
            "detected_destinations": [],
            "resolved_destinations": [],
            "focus_entities": [],
        }
    ]

    destinations = memory.extract_recent_destinations(turns)
    assert [item["id"] for item in destinations] == ["phu-quoc"]
    assert destinations[0]["source"] == "user_explicit_logic_subject"
    assert destinations[0]["confirmed"] == "true"


def test_logic_rejected_turn_does_not_promote_ambiguous_multiple_destinations(monkeypatch) -> None:
    memory = MemoryService.__new__(MemoryService)
    monkeypatch.setattr(
        "src.backend.services.query_parser.detect_destinations",
        lambda _text: [
            {"id": "phu-quoc", "name_vi": "Phú Quốc"},
            {"id": "nha-trang", "name_vi": "Nha Trang"},
        ],
    )
    turns = [
        {
            "route": "invalid_request",
            "logic_action": "reject",
            "scope_action": "allow",
            "safety_action": "allow",
            "user_message": "Phú Quốc hay Nha Trang 2 ngày 3 đêm",
            "detected_destinations": [],
            "resolved_destinations": [],
            "focus_entities": [],
        }
    ]

    assert memory.extract_recent_destinations(turns) == []


def test_structured_price_enrichment_prefers_resolved_hard_destination_scope(monkeypatch) -> None:
    captured = {}

    class FakeRag:
        def hybrid_search(self, **_kwargs):
            return (
                [{"id": "doc", "text": "price evidence", "score": 0.9, "metadata": {"entity_type": "booking_product"}}],
                {
                    "mode": "semantic_fallback",
                    "intent": "booking_product",
                    "intents": ["booking_product"],
                    "explicit_intents": [],
                    "intent_origin": "cost_estimate",
                    "intent_results": {"booking_product": {"status": "found", "document_count": 1}},
                    # Simulate noisy semantic evidence mentioning another destination.
                    "destinations": [],
                    "destination_ids": ["phu-quoc", "nha-trang"],
                    "destination_names": ["Phú Quốc", "Nha Trang"],
                    "keyword_candidate_count": 1,
                    "missing_destination_ids": [],
                    "price_requested": True,
                    "cost_estimate_requested": True,
                },
            )

        @staticmethod
        def build_context_with_diagnostics(documents, exhaustive=False):
            return (
                "\n".join(item.get("text", "") for item in documents),
                {"document_count": len(documents), "branch_counts": {}, "intents": ["booking_product"], "entity_keys": []},
            )

    def fake_enrich(documents, *, destination_ids=None, **_kwargs):
        captured["destination_ids"] = list(destination_ids or [])
        return documents, {
            "structured_price_document_count": 0,
            "structured_enrichment_count": 0,
            "price_estimate_packet": {},
            "price_estimate_destination_ids": list(destination_ids or []),
            "preferred_output_currency": "VND",
            "currency_conversion_guidance": "",
        }

    monkeypatch.setattr(retrieval_node, "get_rag_service", lambda: FakeRag())
    monkeypatch.setattr(retrieval_node, "enrich_retrieved_documents", fake_enrich)

    state = {
        "rag_query": "Plan a 3-day 2-night Phu Quoc trip with estimated cost",
        "user_message": "mình nhầm 3 ngày 2 đêm mới đúng tư vấn cho mình đi ạ",
        "resolved_destinations": [
            {"id": "phu-quoc", "name": "Phú Quốc", "source": "user_explicit_logic_subject", "confirmed": True}
        ],
        "request_tasks": [
            {"task_id": "t1", "task_type": "itinerary", "retrieval_intents": ["hotel", "booking_product"], "needs_price": True, "needs_cost_estimate": True}
        ],
    }

    retrieval_node.retrieve_context(state)
    assert captured["destination_ids"] == ["phu-quoc"]
