from src.backend.agents.nodes import classify as classify_module


def _supported_hanoi(*_args, **_kwargs):
    return [{"id": "ha-noi", "name_vi": "Hà Nội"}]


def test_generic_hanoi_travel_advice_is_rag(monkeypatch):
    monkeypatch.setattr(
        classify_module, "detect_supported_destination_discovery", _supported_hanoi
    )

    state = {
        "user_message": "mình muốn bạn tư vấn du lịch Hà Nội",
        "rag_query": "Vinpearl VinWonders tourism and hotel services in Hanoi",
        "conversation_history": "",
        "scope_action": "allow",
    }

    assert classify_module.classify_input(state)["route"] == "rag"


def test_origin_to_hanoi_generic_travel_advice_is_rag(monkeypatch):
    monkeypatch.setattr(
        classify_module, "detect_supported_destination_discovery", _supported_hanoi
    )

    state = {
        "user_message": "mình từ hồ chí minh ra hà nội du lịch á",
        "rag_query": "travel guide and tips for traveling from Ho Chi Minh City to Hanoi",
        "conversation_history": "",
        "scope_action": "allow",
    }

    assert classify_module.classify_input(state)["route"] == "rag"


def test_explicit_flight_request_is_not_force_rag():
    assert not classify_module._is_supported_destination_travel_request(
        "tư vấn vé máy bay đi Hà Nội",
        "flight tickets to Hanoi",
    )


def test_explicit_weather_request_is_not_force_rag():
    assert not classify_module._is_supported_destination_travel_request(
        "thời tiết Hà Nội hôm nay thế nào",
        "weather in Hanoi today",
    )
