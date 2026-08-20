from __future__ import annotations

from src.backend.agents.nodes import context_resolver, classify


class _FakeLLM:
    def __init__(self, *responses):
        self.responses = [dict(item) for item in responses]
        self.calls = 0

    def json(self, **_kwargs):
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return dict(self.responses[index])


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


def _patch_catalog(monkeypatch, *, explicit_ids=None):
    explicit_ids = list(explicit_ids or [])
    catalog = {
        "phu-quoc": {
            "id": "phu-quoc",
            "name_vi": "Phú Quốc",
            "name_en": "Phu Quoc",
            "normalized_aliases": ["phu quoc"],
        },
        "ha-noi": {
            "id": "ha-noi",
            "name_vi": "Hà Nội",
            "name_en": "Hanoi",
            "normalized_aliases": ["ha noi", "hanoi"],
        },
        "nha-trang": {
            "id": "nha-trang",
            "name_vi": "Nha Trang",
            "name_en": "Nha Trang",
            "normalized_aliases": ["nha trang"],
        },
    }
    monkeypatch.setattr(
        context_resolver,
        "detect_destinations",
        lambda _text: [catalog[item] for item in explicit_ids],
    )
    monkeypatch.setattr(context_resolver, "load_destination_catalog", lambda: catalog)


def _dependency(
    kind: str,
    *,
    needs_memory: bool,
    targets=None,
    exclusions=None,
    reason="test dependency",
):
    return {
        "request_kind": kind,
        "needs_memory": needs_memory,
        "current_target_destination_ids": list(targets or []),
        "current_excluded_destination_ids": list(exclusions or []),
        "reason": reason,
        "confidence": 0.99,
    }


def _selection(
    *,
    destinations=None,
    entities=None,
    turns=None,
    excluded_destinations=None,
    excluded_entities=None,
    rag_query="resolved continuation query",
):
    return {
        "selected_memory_destination_ids": list(destinations or []),
        "selected_memory_entity_refs": list(entities or []),
        "selected_turn_refs": list(turns or []),
        "excluded_memory_destination_ids": list(excluded_destinations or []),
        "excluded_memory_entity_refs": list(excluded_entities or []),
        "rag_query": rag_query,
        "reason": "minimal prior context selected",
        "confidence": 0.98,
    }


def test_factual_clarification_can_recover_from_conversation_context_route(monkeypatch):
    _patch_catalog(monkeypatch)
    fake = _FakeLLM(
        _dependency("factual_continuation", needs_memory=True),
        _selection(
            turns=["turn:5"],
            rag_query="Which Vinpearl locations have natural forests, mountains, and greenery?",
        ),
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
        _dependency("factual_continuation", needs_memory=True),
        _selection(
            excluded_entities=["entity:1"],
            rag_query="Which other Vinpearl locations have forests, mountains, trees, and natural scenery, excluding Vinpearl Wonderworld Phu Quoc?",
        ),
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


def test_independent_turn_never_calls_memory_selector_or_keeps_stale_refs(monkeypatch):
    _patch_catalog(monkeypatch)
    fake = _FakeLLM(
        _dependency("independent", needs_memory=False),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="rag", current_message="chính sách hoàn vé là gì?")
    state["rag_query"] = "What is the Vinpearl refund policy?"
    resolved = context_resolver.resolve_conversation_context(state)

    assert fake.calls == 1
    assert resolved["context_request_kind"] == "independent"
    assert resolved["context_uses_memory"] is False
    assert resolved["selected_memory_turn_refs"] == []
    assert resolved["resolved_entity_names"] == []
    assert resolved["excluded_entity_names"] == []
    assert resolved["rag_query"] == "What is the Vinpearl refund policy?"


def test_current_explicit_destination_is_never_dropped_on_independent_turn(monkeypatch):
    _patch_catalog(monkeypatch, explicit_ids=["ha-noi"])
    fake = _FakeLLM(
        # Deliberately omit the current target to reproduce the Railway failure:
        # the invariant must restore current explicit Hanoi instead of returning [].
        _dependency("independent", needs_memory=False, targets=[]),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="rag", current_message="ở hà nội có gì chơi không")
    state["rag_query"] = "What attractions and entertainment options are available in Hanoi?"
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_request_kind"] == "independent"
    assert resolved["context_uses_memory"] is False
    assert resolved["resolved_destination_ids"] == ["ha-noi"]
    assert resolved["context_resolution_source"] == "current_explicit"
    assert resolved["rag_query"] == state["rag_query"]


def test_new_explicit_destination_overrides_old_destination_without_memory(monkeypatch):
    _patch_catalog(monkeypatch, explicit_ids=["ha-noi"])
    fake = _FakeLLM(
        _dependency("independent", needs_memory=False, targets=["ha-noi"]),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="rag", current_message="ở hà nội có gì chơi không")
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["resolved_destination_ids"] == ["ha-noi"]
    assert "phu-quoc" not in resolved["resolved_destination_ids"]
    assert resolved["context_uses_memory"] is False


def test_current_explicit_exclusion_is_respected_without_using_memory(monkeypatch):
    _patch_catalog(monkeypatch, explicit_ids=["phu-quoc", "nha-trang"])
    fake = _FakeLLM(
        _dependency(
            "independent",
            needs_memory=False,
            targets=["nha-trang"],
            exclusions=["phu-quoc"],
        ),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="rag", current_message="không phải Phú Quốc, Nha Trang cơ")
    state["rag_query"] = "Vinpearl options in Nha Trang, not Phu Quoc"
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_uses_memory"] is False
    assert resolved["resolved_destination_ids"] == ["nha-trang"]
    assert resolved["excluded_destination_ids"] == ["phu-quoc"]


def test_followup_with_new_explicit_destination_keeps_current_target_and_uses_only_needed_turn(monkeypatch):
    _patch_catalog(monkeypatch, explicit_ids=["ha-noi"])
    fake = _FakeLLM(
        _dependency(
            "factual_continuation",
            needs_memory=True,
            targets=["ha-noi"],
        ),
        _selection(
            turns=["turn:5"],
            rag_query="What Vinpearl locations in Hanoi have natural landscapes with forests, mountains, and trees?",
        ),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="rag", current_message="ở Hà Nội thì sao?")
    state["rag_query"] = "What about Hanoi?"
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_request_kind"] == "factual_continuation"
    assert resolved["context_uses_memory"] is True
    assert resolved["resolved_destination_ids"] == ["ha-noi"]
    assert resolved["selected_memory_turn_refs"] == ["turn:5"]
    assert "phu-quoc" not in resolved["resolved_destination_ids"]


def test_nominal_continuation_without_selected_memory_downgrades_to_independent(monkeypatch):
    _patch_catalog(monkeypatch, explicit_ids=["ha-noi"])
    fake = _FakeLLM(
        _dependency("factual_continuation", needs_memory=True, targets=["ha-noi"]),
        _selection(),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="rag", current_message="ở hà nội có gì chơi không")
    state["rag_query"] = "What attractions are available in Hanoi?"
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_request_kind"] == "independent"
    assert resolved["context_uses_memory"] is False
    assert resolved["resolved_destination_ids"] == ["ha-noi"]
    assert resolved["selected_memory_turn_refs"] == []
    assert resolved["rag_query"] == state["rag_query"]


def test_conversation_meta_uses_memory_but_does_not_produce_rag_query(monkeypatch):
    _patch_catalog(monkeypatch)
    fake = _FakeLLM(
        _dependency("conversation_meta", needs_memory=True),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="conversation_context", current_message="câu trước mình hỏi gì?")
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_request_kind"] == "conversation_meta"
    assert resolved["context_uses_memory"] is True
    assert resolved["rag_query"] == ""
    assert fake.calls == 1


def test_assistant_proposal_memory_can_be_used_without_becoming_user_focus(monkeypatch):
    _patch_catalog(monkeypatch)
    fake = _FakeLLM(
        _dependency("factual_continuation", needs_memory=True),
        _selection(
            destinations=["phu-quoc"],
            turns=["turn:5"],
            rag_query="Is 5 million VND enough for two people for the previously suggested Phu Quoc option?",
        ),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="rag", current_message="mình có bạn gái đi cùng nữa thì 5tr có đủ không")
    state["recent_destinations"] = []
    state["recent_discussed_destinations"] = [
        {"id": "phu-quoc", "name": "Phú Quốc", "source": "assistant_suggestion", "confirmed": "false"}
    ]
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_uses_memory"] is True
    assert resolved["resolved_destination_ids"] == ["phu-quoc"]
    assert resolved["context_destination_provenance"][0]["source"] == "recent_assistant_proposal"
    assert resolved["context_destination_provenance"][0]["confirmed"] == "false"


def test_user_confirmation_promotes_prior_assistant_proposal(monkeypatch):
    _patch_catalog(monkeypatch)
    fake = _FakeLLM(
        _dependency("factual_continuation", needs_memory=True),
        {
            **_selection(
                destinations=["phu-quoc"],
                turns=["turn:5"],
                rag_query="Plan the previously suggested Phu Quoc option.",
            ),
            "user_confirms_selected_memory_destination": True,
        },
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(route="rag", current_message="ok chọn phương án đó đi")
    state["recent_destinations"] = []
    state["recent_discussed_destinations"] = [
        {"id": "phu-quoc", "name": "Phú Quốc", "source": "assistant_suggestion", "confirmed": "false"}
    ]
    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["resolved_destination_ids"] == ["phu-quoc"]
    assert resolved["context_destination_provenance"][0]["source"] == "user_confirmed_via_memory"
    assert resolved["context_destination_provenance"][0]["confirmed"] == "true"


def test_conversation_meta_named_destination_is_reference_not_rag_target(monkeypatch):
    _patch_catalog(monkeypatch, explicit_ids=["nha-trang"])
    fake = _FakeLLM(
        _dependency(
            "conversation_meta",
            needs_memory=True,
            targets=["nha-trang"],
            reason="User asks why Nha Trang appeared in the previous answer.",
        ),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = _memory_state(
        route="conversation_context",
        current_message="tại sao bạn lại tư vấn cả Nha Trang cho mình vậy?",
    )
    state["request_requires_memory"] = True
    resolved = context_resolver.resolve_conversation_context(state)

    assert fake.calls == 1
    assert resolved["context_request_kind"] == "conversation_meta"
    assert resolved["context_uses_memory"] is True
    assert resolved["resolved_destination_ids"] == []
    assert resolved["rag_query"] == ""


def test_correction_selected_invalid_turn_recovers_its_single_user_destination(monkeypatch):
    _patch_catalog(monkeypatch)
    fake = _FakeLLM(
        _dependency(
            "factual_continuation",
            needs_memory=True,
            reason="User corrects the duration of the previous Phu Quoc request.",
        ),
        _selection(
            turns=["turn:1"],
            rag_query="Plan the corrected 3-day 2-night Phu Quoc trip with a cost estimate.",
        ),
    )
    monkeypatch.setattr(context_resolver, "LLMService", lambda: fake)

    state = {
        "route": "rag",
        "scope_action": "allow",
        "sanitized_user_request": "mình nhầm 3 ngày 2 đêm mới đúng tư vấn cho mình đi ạ",
        "user_message": "mình nhầm 3 ngày 2 đêm mới đúng tư vấn cho mình đi ạ",
        "rag_query": "Plan the corrected 3-day 2-night trip.",
        "request_requires_memory": True,
        "recent_destinations": [
            {"id": "phu-quoc", "name": "Phú Quốc", "source": "user_explicit_logic_subject", "confirmed": "true"}
        ],
        "recent_discussed_destinations": [],
        "recent_entities": [],
        "conversation_turns": [
            {
                "memory_ref": "turn:1",
                "route": "invalid_request",
                "logic_action": "reject",
                "scope_action": "allow",
                "safety_action": "allow",
                "user_message": "mình muốn đi Phú Quốc 2 ngày 3 đêm",
                "rag_query": "",
                "resolved_destinations": [],
                "detected_destinations": [],
                "focus_entities": [],
            }
        ],
    }

    # Current correction contains no destination; only the selected prior turn does.
    monkeypatch.setattr(
        context_resolver,
        "detect_destinations",
        lambda text: (
            [{"id": "phu-quoc", "name_vi": "Phú Quốc"}]
            if "phú quốc" in text.lower() else []
        ),
    )

    resolved = context_resolver.resolve_conversation_context(state)

    assert resolved["context_request_kind"] == "factual_continuation"
    assert resolved["context_uses_memory"] is True
    assert resolved["selected_memory_turn_refs"] == ["turn:1"]
    assert resolved["resolved_destination_ids"] == ["phu-quoc"]
    assert resolved["context_destination_provenance"][0]["confirmed"] == "true"
    assert "nha-trang" not in resolved["resolved_destination_ids"]
