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


def test_grounded_entity_destination_is_available_for_plural_followup() -> None:
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
                    "source": "grounded_answer_kb",
                    "destination_id": "ho-chi-minh",
                }
            ],
        }
    ]

    destinations = memory.extract_recent_destinations(turns)

    assert destinations[0]["id"] == "ho-chi-minh"
