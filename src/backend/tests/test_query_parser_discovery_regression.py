from __future__ import annotations

import src.backend.services.query_parser as query_parser


def _parse_without_catalog(monkeypatch, user_message: str, rag_query: str):
    monkeypatch.setattr(query_parser, "detect_destinations", lambda _text: [])
    return query_parser.parse_retrieval_query(user_message, rag_query)


def test_open_ended_travel_discovery_does_not_become_rewrite_hotel(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "có nơi nào có cảnh rừng núi thiên nhiên để đi du lịch không ạ",
        "Vinpearl destinations and resorts with natural mountain and forest landscapes",
    )

    assert parsed["intent_origin"] == "generic_discovery"
    assert parsed["explicit_intents"] == []
    assert parsed["intents"] == list(query_parser.GENERIC_DISCOVERY_INTENTS)


def test_open_ended_where_request_is_discovery_even_without_destination(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "có nơi nào có rừng núi thiên nhiên đẹp không bạn",
        "Vinpearl destinations with beautiful natural forests and mountains",
    )

    assert parsed["intent_origin"] == "generic_discovery"
    assert "hotel" in parsed["intents"]
    assert "attraction" in parsed["intents"]


def test_specific_explicit_intent_still_wins(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "Giới thiệu ngắn về sân golf Cape Wickham Golf Links",
        "Short introduction to Cape Wickham Golf Links golf course",
    )

    assert parsed["intent_origin"] == "current_explicit"
    assert parsed["intents"] == ["golf"]


def test_weak_visit_word_does_not_force_generic_discovery_without_destination(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "Can I visit with a pet?",
        "Can I visit Grand World Phu Quoc with a pet?",
    )

    assert parsed["intent_origin"] != "generic_discovery"


def test_vietnamese_scenery_word_does_not_become_hotel_intent(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "chào bạn, có nơi nào có rừng núi phong cảnh thiên nhiên để du lịch thư giản k",
        "Vinpearl resorts and destinations with mountain forests and natural scenery for relaxation",
    )

    assert parsed["explicit_intents"] == []
    assert parsed["intent_origin"] == "generic_discovery"
    assert parsed["intents"] == list(query_parser.GENERIC_DISCOVERY_INTENTS)


def test_accented_room_word_still_detects_hotel(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "ở Phú Quốc còn phòng không?",
        "Are there rooms available in Phu Quoc?",
    )

    assert parsed["explicit_intents"] == ["hotel"]
    assert parsed["intent_origin"] == "current_explicit"


def test_unaccented_room_phrase_still_detects_hotel(monkeypatch):
    parsed = _parse_without_catalog(
        monkeypatch,
        "minh muon dat phong o Phu Quoc",
        "I want to book a room in Phu Quoc",
    )

    assert parsed["explicit_intents"] == ["hotel"]
    assert parsed["intent_origin"] == "current_explicit"


def test_equivalent_nature_discovery_phrasings_share_same_intent_route(monkeypatch):
    first = _parse_without_catalog(
        monkeypatch,
        "chào bạn, có nơi nào có rừng núi phong cảnh thiên nhiên để du lịch thư giản k",
        "Vinpearl resorts and destinations with mountain forests and natural scenery for relaxation",
    )
    second = _parse_without_catalog(
        monkeypatch,
        "có nơi nào có rừng, núi, phong cảnh thiên nhiên không bạn",
        "Vinpearl resorts or destinations with forests, mountains, and natural landscapes",
    )

    assert first["intent_origin"] == second["intent_origin"] == "generic_discovery"
    assert first["explicit_intents"] == second["explicit_intents"] == []
    assert first["intents"] == second["intents"] == list(query_parser.GENERIC_DISCOVERY_INTENTS)
