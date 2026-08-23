from src.backend.agents.nodes import context_resolver
from src.backend.services.memory import MemoryService
from src.backend.services.query_parser import detect_retrieval_facets


def _catalog_destination(destination_id):
    names = {
        "ho-chi-minh": ("Ho Chi Minh City", "Thành phố Hồ Chí Minh"),
        "phu-quoc": ("Phu Quoc", "Phú Quốc"),
    }
    if destination_id not in names:
        return None
    name_en, name_vi = names[destination_id]
    return {"id": destination_id, "name_en": name_en, "name_vi": name_vi, "aliases": []}


def _region_turn():
    return {
        "turn_ref": "turn:1",
        "route": "rag",
        "focus_destinations": [
            {"id": "ho-chi-minh", "source": "current_explicit_region", "confirmed": True},
            {"id": "phu-quoc", "source": "current_explicit_region", "confirmed": True},
        ],
        "request_tasks": [{"task_type": "destination_recommendation"}],
    }


def test_budget_refinement_inherits_immediately_active_user_region(monkeypatch):
    monkeypatch.setattr(context_resolver, "_catalog_destination", _catalog_destination)
    state = {"request_tasks": [{"task_type": "destination_recommendation"}]}
    selected, refs = context_resolver._active_scope_refinement(
        state,
        "tài chính 5tr thì nên đi nơi nào",
        [],
        [_region_turn()],
    )
    assert [item["id"] for item in selected] == ["ho-chi-minh", "phu-quoc"]
    assert all(item["source"] == "active_user_scope" for item in selected)
    assert refs == ["turn:1"]


def test_scope_refinement_supports_dates_guests_preferences_and_itinerary(monkeypatch):
    monkeypatch.setattr(context_resolver, "_catalog_destination", _catalog_destination)
    for task_type, message in (
        ("itinerary", "đi 3 ngày 2 đêm thì lịch trình thế nào"),
        ("hotel_recommendation", "gia đình 4 người nên ở khách sạn nào"),
        ("destination_recommendation", "tôi thích nơi yên tĩnh và có biển"),
        ("availability_check", "cuối tuần sau còn phòng không"),
    ):
        selected, _ = context_resolver._active_scope_refinement(
            {"request_tasks": [{"task_type": task_type}]}, message, [], [_region_turn()]
        )
        assert {item["id"] for item in selected} == {"ho-chi-minh", "phu-quoc"}


def test_new_region_or_explicit_reset_does_not_inherit_old_scope(monkeypatch):
    monkeypatch.setattr(context_resolver, "_catalog_destination", _catalog_destination)
    state = {"request_tasks": [{"task_type": "destination_recommendation"}]}
    assert context_resolver._active_scope_refinement(
        state, "miền Bắc có những nơi nào", [], [_region_turn()]
    ) == ([], [])
    assert context_resolver._active_scope_refinement(
        state, "bỏ qua địa điểm, tìm trên toàn quốc", [], [_region_turn()]
    ) == ([], [])


def test_assistant_only_proposals_never_become_implicit_hard_scope(monkeypatch):
    monkeypatch.setattr(context_resolver, "_catalog_destination", _catalog_destination)
    turn = _region_turn()
    turn["focus_destinations"] = [
        {"id": "phu-quoc", "source": "assistant_suggestion", "confirmed": True}
    ]
    selected, refs = context_resolver._active_scope_refinement(
        {"request_tasks": [{"task_type": "destination_recommendation"}]},
        "5 triệu thì nên đi đâu",
        [],
        [turn],
    )
    assert selected == []
    assert refs == []


def test_region_scope_is_persisted_as_user_owned_focus():
    service = MemoryService.__new__(MemoryService)
    turns = [{
        "sanitized_user_request": "tôi muốn du lịch tại miền Nam",
        "resolved_destinations": [
            {"id": "ho-chi-minh", "name": "Thành phố Hồ Chí Minh", "source": "current_explicit_region"},
            {"id": "phu-quoc", "name": "Phú Quốc", "source": "current_explicit_region"},
        ],
    }]
    assert [item["id"] for item in service.extract_recent_destinations(turns)] == [
        "ho-chi-minh", "phu-quoc"
    ]


def test_budget_destination_choice_is_an_aggregate_cost_estimate():
    facets = detect_retrieval_facets(
        "tài chính 5tr thì nên đi nơi nào",
        "where should I go with a budget of 5 million VND",
    )
    assert facets["cost_estimate_requested"] is True
    assert facets["price_requested"] is True
    assert facets["booking_evidence_preferred"] is True
