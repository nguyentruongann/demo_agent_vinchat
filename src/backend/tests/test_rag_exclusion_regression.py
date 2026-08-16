from __future__ import annotations

from types import MethodType, SimpleNamespace

from src.backend.services import rag as rag_module


class _FaqMatcher:
    @staticmethod
    def match(**_kwargs):
        return [], {"accepted": False, "mode": "faq_semantic_rejected"}


def test_excluded_previous_entity_is_not_named_target_or_returned(monkeypatch):
    service = rag_module.RAGService.__new__(rag_module.RAGService)
    service.settings = SimpleNamespace(top_k=5)
    service.faq_matcher = _FaqMatcher()

    monkeypatch.setattr(rag_module, "load_destination_catalog", lambda: {})
    monkeypatch.setattr(
        rag_module,
        "parse_retrieval_query",
        lambda **_kwargs: {
            "destinations": [],
            "intents": ["attraction"],
            "intent": "attraction",
            "explicit_intents": [],
            "intent_origin": "generic_discovery",
            "preferred_entity_types": [],
            "preferred_entity_types_by_intent": {},
        },
    )

    service._find_named_entity_mentions = MethodType(
        lambda self, *_texts: [
            {
                "name": "Vinpearl Wonderworld Phu Quoc",
                "normalized_name": "vinpearl wonderworld phu quoc",
                "type": "property",
                "indices": [0],
            }
        ],
        service,
    )
    service._load_corpus_cache = MethodType(
        lambda self: {
            "metadatas": [
                {
                    "entity_name": "Vinpearl Wonderworld Phu Quoc",
                    "entity_type": "property",
                    "destination_id": "phu-quoc",
                }
            ]
        },
        service,
    )

    captured_named = []

    def retrieve_named(self, entities, *, query, per_entity_k=2):
        captured_named.extend(item["name"] for item in entities)
        return [
            {
                "id": "excluded-named",
                "text": "old recommendation",
                "score": 0.99,
                "metadata": {
                    "entity_name": "Vinpearl Wonderworld Phu Quoc",
                    "entity_type": "property",
                    "destination_id": "phu-quoc",
                },
            }
        ] if entities else []

    service._retrieve_named_entity_branches = MethodType(retrieve_named, service)
    service._exact_faq_matches = MethodType(lambda self, *_args, **_kwargs: [], service)
    service.semantic_search_many = MethodType(
        lambda self, queries, top_k: [[
            {
                "id": "excluded-semantic",
                "text": "old recommendation",
                "score": 0.97,
                "metadata": {
                    "entity_name": "Vinpearl Wonderworld Phu Quoc",
                    "entity_type": "property",
                    "destination_id": "phu-quoc",
                },
            },
            {
                "id": "alternative",
                "text": "another nature destination",
                "score": 0.91,
                "metadata": {
                    "entity_name": "Vinpearl Nam Hoi An",
                    "entity_type": "attraction",
                    "destination_id": "hoi-an",
                },
            },
        ] for _ in queries],
        service,
    )

    documents, diagnostics = service.hybrid_search(
        query=(
            "Which other Vinpearl locations have forests and natural scenery, "
            "excluding Vinpearl Wonderworld Phu Quoc?"
        ),
        user_message="ở vinpearl có nơi nào khác có rừng núi, cây cối, thiên nhiên không?",
        resolved_destinations=[],
        excluded_entity_names=["Vinpearl Wonderworld Phu Quoc"],
    )

    assert captured_named == []
    assert [item["id"] for item in documents] == ["alternative"]
    assert diagnostics["named_entities"] == []
    assert "vinpearl wonderworld phu quoc" in diagnostics["excluded_entity_names"]
