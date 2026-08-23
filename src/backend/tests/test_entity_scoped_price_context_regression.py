from types import SimpleNamespace

from src.backend.agents.nodes import retrieval as retrieval_node
from src.backend.agents.nodes.answer import _answer_mode_specific_system
from src.backend.services import retrieval_enrichment


def _doc(doc_id, name, text, *, matched_name="", record=None):
    return {
        "id": doc_id,
        "text": text,
        "score": 0.99,
        "matched_named_entity": matched_name,
        "metadata": {"entity_type": "room", "entity_name": name},
        "structured_record": record or {},
    }


def test_unrelated_destination_price_cannot_satisfy_named_rooms(monkeypatch):
    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(min_relevance_score=0.35),
    )
    target_a = _doc(
        "a", "Grand Deluxe Twin Bed", "Rate: tel:1900232389",
        matched_name="Grand Deluxe Twin Bed",
    )
    target_b = _doc(
        "b", "Grand Deluxe Queen Bed", "Rate: tel:1900232389",
        matched_name="Grand Deluxe Queen Bed",
    )
    unrelated = _doc(
        "wrong", "One-bedroom Suite", "Price: 149 USD",
        record={"room_name": "One-bedroom Suite"},
    )
    state = {
        "price_requested": True,
        "retrieved_documents": [unrelated, target_a, target_b],
        "retrieval_entity_scope": {
            "names": ["Grand Deluxe Twin Bed", "Grand Deluxe Queen Bed"],
            "entity_types": ["room"],
        },
        "intent_results": {},
        "detected_intents": ["hotel"],
        "task_retrieval_results": {},
        "resolution_mode": "information_only",
    }

    result = retrieval_node.assess_information(state)

    assert result["enough_information"] is True
    assert result["price_resolution"] == "entity_mixed"
    assert [item["status"] for item in result["price_entity_resolution"]] == [
        "contact_fallback", "contact_fallback"
    ]
    assert all(
        channel["value"] == "1900232389"
        for item in result["price_entity_resolution"]
        for channel in item["channels"]
    )


def test_one_named_room_price_never_satisfies_the_other_room():
    docs = [
        _doc(
            "a-price", "Hotel — Grand Deluxe Twin Bed", "Price: 200 USD",
            record={"room_name": "Grand Deluxe Twin Bed"},
        ),
        _doc(
            "b-info", "Grand Deluxe Queen Bed", "Queen room information only",
            matched_name="Grand Deluxe Queen Bed",
        ),
    ]
    resolution = retrieval_node._price_entity_resolution(
        docs,
        {"names": ["Grand Deluxe Twin Bed", "Grand Deluxe Queen Bed"]},
    )
    assert resolution[0]["status"] == "numeric_price"
    assert resolution[1]["status"] == "ticket_offer"


def test_price_followup_to_room_catalog_restores_complete_room_scope():
    state = {
        "context_uses_memory": True,
        "resolved_entity_names": [],
        "rag_query": "price rates for the room categories at Vinpearl properties in Nha Trang",
        "current_user_intent": "Provide prices for the previously listed room categories",
    }
    assert retrieval_node._memory_room_catalog_price_request(state, True) is True
    assert retrieval_node._memory_room_catalog_price_request(state, False) is False


def test_named_room_enrichment_filters_out_other_room_prices(monkeypatch):
    rows = [
        {"room_id": "twin", "room_name": "Grand Deluxe Twin Bed"},
        {"room_id": "queen", "room_name": "Grand Deluxe Queen Bed"},
        {"room_id": "suite", "room_name": "One-bedroom Suite"},
    ]
    monkeypatch.setattr(
        retrieval_enrichment,
        "_room_price_rows",
        lambda connection, destination_ids, per_destination=3: rows,
    )
    matched = retrieval_enrichment._room_price_rows_for_entity_scope(
        object(),
        ["nha-trang"],
        {"names": ["Grand Deluxe Twin Bed", "Grand Deluxe Queen Bed"]},
    )
    assert [item["room_id"] for item in matched] == ["twin", "queen"]


def test_room_catalog_price_prompt_forbids_ticket_price_substitution():
    prompt = _answer_mode_specific_system({
        "answer_mode": "ROOM_PRICE_CATALOG",
        "preferred_output_currency": "VND",
    })
    assert "Cover every room exactly once" in prompt
    assert "Never insert ticket" in prompt


def test_contact_only_room_amount_is_never_treated_as_price():
    amount, currency, source = retrieval_enrichment._price_amount_from_room({
        "price_from_amount": 1900232389,
        "price_from_currency": None,
        "rate_amount": 1900232389,
        "rate_currency": None,
        "rate_raw": "tel:1900232389",
        "is_rate_suspect": True,
    })
    assert amount is None
    assert currency is None
    assert source == "contact_only"


def test_duplicate_room_name_is_resolved_per_property():
    docs = [
        {
            **_doc("a", "Deluxe Twin Bed", "Rate: tel:1900232389", matched_name="Deluxe Twin Bed"),
            "metadata": {
                "entity_type": "room", "entity_id": "id=room-a",
                "entity_name": "Deluxe Twin Bed", "property_id": "hotel-a",
                "property_name": "Hotel A",
            },
        },
        {
            **_doc("b", "Hotel B — Deluxe Twin Bed", "Price: 200 USD", record={
                "room_name": "Deluxe Twin Bed", "property_id": "hotel-b", "property_name": "Hotel B",
            }),
            "metadata": {
                "entity_type": "room", "entity_id": "id=room-b",
                "entity_name": "Hotel B — Deluxe Twin Bed", "property_id": "hotel-b",
                "property_name": "Hotel B",
            },
        },
    ]
    resolution = retrieval_node._price_entity_resolution(
        docs, {"names": ["Deluxe Twin Bed"]}
    )
    assert len(resolution) == 2
    assert {item["entity_name"] for item in resolution} == {
        "Hotel A — Deluxe Twin Bed", "Hotel B — Deluxe Twin Bed"
    }
    assert {item["status"] for item in resolution} == {
        "contact_fallback", "numeric_price"
    }


def test_unknown_booking_price_uses_search_url_as_guidance():
    packet = retrieval_node._price_contact_fallback([{
        "id": "haven-standard",
        "text": "Pricing status: unknown",
        "metadata": {"entity_type": "booking_product", "entity_name": "Haven Sunset Standard"},
        "structured_record": {
            "booking_search_url": "https://booking.vinwonders.com/en-USD/search?code=HVSST",
        },
    }])
    assert packet["available"] is True
    assert packet["channels"][0]["type"] == "url"
    assert "code=HVSST" in packet["channels"][0]["value"]
