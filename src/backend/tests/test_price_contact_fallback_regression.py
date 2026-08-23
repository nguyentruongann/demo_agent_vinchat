from src.backend.agents.graph import route_after_assessment
from src.backend.agents.nodes.answer import _answer_mode_specific_system
from src.backend.agents.nodes.retrieval import _price_contact_fallback, assess_information
from src.backend.agents.nodes.static_responses import no_data_response


def _price_state(documents: list[dict]) -> dict:
    return {
        "price_requested": True,
        "retrieved_documents": documents,
        "intent_results": {},
        "detected_intents": ["hotel"],
        "task_retrieval_results": {},
        "resolution_mode": "information_only",
        "answer_mode": "PRICE_LOOKUP",
        "original_language": "vi",
        "detected_destination_names": ["Nha Trang"],
    }


def test_price_without_amount_uses_grounded_phone_instead_of_no_data() -> None:
    state = _price_state([
        {
            "id": "room-deluxe-double",
            "score": 0.91,
            "text": "Deluxe Double Room. Giá phòng: tel:1900232389",
            "metadata": {"entity_name": "Vinpearl Empire Nha Trang"},
        }
    ])

    result = assess_information(state)

    assert result["enough_information"] is True
    assert result["price_resolution"] == "contact_fallback"
    assert result["price_contact_fallback"]["channels"] == [
        {
            "type": "phone",
            "value": "1900232389",
            "source": "Vinpearl Empire Nha Trang",
        }
    ]
    assert route_after_assessment({**state, **result}) == "answer"
    prompt = _answer_mode_specific_system({**state, **result})
    assert "PRICE_CONTACT_FALLBACK" in prompt
    assert "generic refusal" in prompt


def test_contact_extractor_accepts_explicit_metadata_and_rejects_generic_source_url() -> None:
    packet = _price_contact_fallback([
        {
            "id": "room-1",
            "text": "No listed rate.",
            "metadata": {
                "entity_name": "Example room",
                "contact_email": "rates@example.test",
                "booking_url": "https://booking.example.test/room-1",
                "url": "https://example.test/article/room-1",
            },
        }
    ])

    values = {(item["type"], item["value"]) for item in packet["channels"]}
    assert ("email", "rates@example.test") in values
    assert ("url", "https://booking.example.test/room-1") in values
    assert ("url", "https://example.test/article/room-1") not in values


def test_price_without_amount_or_contact_offers_ticket_without_creating_one() -> None:
    state = _price_state([
        {
            "id": "room-deluxe-twin",
            "score": 0.88,
            "text": "Deluxe Twin Room with two beds and city view.",
            "metadata": {"entity_name": "Vinpearl Empire Nha Trang"},
        }
    ])

    result = assess_information(state)
    merged = {**state, **result}
    response = no_data_response(merged)

    assert result["enough_information"] is False
    assert result["price_resolution"] == "ticket_offer"
    assert route_after_assessment(merged) == "no_data"
    assert response["ticket_id"] is None
    assert "họ tên" in response["answer"]
    assert "email hoặc số điện thoại" in response["answer"]
    assert "chưa có đủ thông tin" not in response["answer"]


def test_unlabelled_digits_are_not_mistaken_for_a_contact_channel() -> None:
    packet = _price_contact_fallback([
        {
            "id": "room-1",
            "text": "Room size 32 m2, capacity 2 adults, internal code 1900232389.",
            "metadata": {},
        }
    ])
    assert packet == {"available": False, "channels": []}
