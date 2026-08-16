from __future__ import annotations

from src.backend.agents.nodes import context_resolver, classify


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def json(self, **_kwargs):
        self.calls += 1
        return dict(self.response)


def _memory_state(*, route: str, current_message: str):
    return {
        "route": route,
        "scope_action": "allow",
        "sanitized_user_request": current_message,
        "user_message": current_message,
        "rag_query": "" if route == "conversation_context" else "guarded current query",
        "recent_destinations": [
            {"id": "phu-quoc", "name": "Phú Quốc", "source": "recent_user_focus"}
        ],
        "recent_entities": [
            {
                "name": "Vinpearl Wonderworld Phu Quoc",
                "type": "property",
                "destination_id": "phu-quoc",
                "source": "grounded_answer_kb",
            }
        ],
        "conversation_turns": [
            {
                "memory_ref": "turn:5",
                "route": "rag",
                "user_message": "ở vinpearl có nơi nào có rừng núi, cây cối, thiên nhiên không?",
                "rag_query": "Which Vinpearl locations feature natural landscapes with forests, mountains, and trees?",
                "resolved_destinations": [],
                "focus_entities": [
                    {
                        "name": "Vinpearl Wonderworld Phu Quoc",
                        "type": "property",
                        "destination_id": "phu-quoc",
                    }
                ],
            }
        ],
    }


def _patch_catalog(monkeypatch):
    monkeypatch.setattr(context_resolver, "detect_destinations", lambda _text: [])
    monkeypatch.setattr(
        context_resolver,
        "load_destination_catalog",
        lambda: {
            "phu-quoc": {
                "id": "phu-quoc",
                "name_vi": "Phú Quốc",
                "name_en": "Phu Quoc",
                "normalized_aliases": ["phu quoc"],
            }
        },
    )


def test_factual_clarification_can_recover_from_conversation_context_route(monkeypatch):
    _patch_catalog(monkeypatch)
    fake = _FakeLLM(
        {
            "request_kind": "factual_continuation",
            "selected_destination_ids": [],
            "selected_entity_refs": [],
            "selected_turn_refs": ["turn:5"],
            "excluded_destination_ids": [],
            "excluded_entity_refs": [],
            "uses_memory": True,
            "rag_query": "Which Vinpearl locations have natural forests, mountains, and greenery?",
            "reason": "The user is clarifying the scope of the previous factual request.",
            "confidence": 0.98,
        }
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="conversation_context", current_message="ý mình là ở Vinpearl á")
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_request_kind"] == "factual_continuation"
    assert resolved["context_uses_memory"] is True
    assert resolved["selected_memory_turn_refs"] == ["turn:5"]
    assert resolved["rag_query"].startswith("Which Vinpearl locations")

    routed = classify.classify_input({**state, **resolved})
    assert routed["route"] == "rag"


def test_other_option_uses_memory_as_exclusion_not_positive_target(monkeypatch):
    _patch_catalog(monkeypatch)
    fake = _FakeLLM(
        {
            "request_kind": "factual_continuation",
            "selected_destination_ids": [],
            "selected_entity_refs": [],
            "selected_turn_refs": [],
            "excluded_destination_ids": [],
            "excluded_entity_refs": ["entity:1"],
            "uses_memory": True,
            "rag_query": "Which other Vinpearl locations have forests, mountains, trees, and natural scenery, excluding Vinpearl Wonderworld Phu Quoc?",
            "reason": "The user asks for another option, so the prior recommendation must be excluded.",
            "confidence": 0.99,
        }
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(
        route="rag",
        current_message="ở vinpearl có nơi nào khác có rừng núi, cây cối, thiên nhiên không?",
    )
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_request_kind"] == "factual_continuation"
    assert resolved["context_uses_memory"] is True
    assert resolved["resolved_destination_ids"] == []
    assert resolved["resolved_entity_names"] == []
    assert resolved["excluded_destination_ids"] == []
    assert resolved["excluded_entity_names"] == ["Vinpearl Wonderworld Phu Quoc"]


def test_independent_turn_discards_stale_memory_refs(monkeypatch):
    _patch_catalog(monkeypatch)
    fake = _FakeLLM(
        {
            "request_kind": "independent",
            "selected_destination_ids": ["phu-quoc"],
            "selected_entity_refs": ["entity:1"],
            "selected_turn_refs": ["turn:5"],
            "excluded_destination_ids": [],
            "excluded_entity_refs": [],
            "uses_memory": True,
            "rag_query": "stale memory contaminated query",
            "reason": "The current question is independent.",
            "confidence": 0.99,
        }
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="rag", current_message="chính sách hoàn vé là gì?")
    state["rag_query"] = "What is the Vinpearl refund policy?"
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_request_kind"] == "independent"
    assert resolved["context_uses_memory"] is False
    assert resolved["selected_memory_turn_refs"] == []
    assert resolved["resolved_entity_names"] == []
    assert resolved["excluded_entity_names"] == []
    assert resolved["rag_query"] == "What is the Vinpearl refund policy?"
