from types import MethodType

from src.backend.agents.nodes import retrieval as retrieval_node
from src.backend.agents.nodes.answer import _answer_mode_specific_system
from src.backend.services.query_parser import normalize_text
from src.backend.services.rag import RAGService


def test_destination_room_catalog_inherits_destination_from_parent_property() -> None:
    service = RAGService.__new__(RAGService)
    room_metadata = {
        "entity_type": "room",
        "entity_id": "id=room-deluxe-double",
        "entity_name": "Deluxe Double Room",
        "property_id": "vinpearl-empire-nha-trang",
    }
    service._load_corpus_cache = MethodType(
        lambda self: {
            "ids": ["room-1"],
            "documents": ["Deluxe Double Room, 32 m2"],
            "metadatas": [room_metadata],
            "normalized": [normalize_text("Deluxe Double Room room")],
            "entity_destination_map": {
                "vinpearl-empire-nha-trang": {"nha-trang"},
            },
        },
        service,
    )

    candidates = service.keyword_candidates(
        destination={
            "id": "nha-trang",
            "name_vi": "Nha Trang",
            "aliases": ["Nha Trang"],
        },
        intent="hotel",
        preferred_entity_types={"room"},
        strict_entity_types=True,
        require_destination_id_match=True,
        max_candidates=100,
    )

    assert len(candidates) == 1
    assert candidates[0]["metadata"]["entity_name"] == "Deluxe Double Room"
    assert candidates[0]["matched_destination_id"] == "nha-trang"


def test_destination_wide_room_request_does_not_use_single_property_answer_mode() -> None:
    state = {
        "user_message": "cho mình thông tin các hạng phòng tại nha trang đi ạ",
        "rag_query": "all room categories at Vinpearl Nha Trang properties",
        "request_task_count": 1,
        "input_task_type": "property_detail",
        "request_tasks": [{
            "task_type": "property_detail",
            "result_scope": "exhaustive",
            "source_text": "các hạng phòng tại nha trang",
            "goal": "Provide all room categories across Nha Trang properties",
        }],
    }
    diagnostics = {
        "intents": ["hotel"],
        "exhaustive_requested": True,
        "named_entity_scope": {"names": [], "entity_ids": []},
    }

    mode = retrieval_node._answer_mode(state, diagnostics)

    assert mode == "DESTINATION_ROOM_CATALOG"
    prompt = _answer_mode_specific_system({"answer_mode": mode})
    assert "all indexed room categories across the resolved destination" in prompt
    assert "group rooms by property_name or property_id" in prompt


def test_exhaustive_packet_preserves_room_parent_for_grouping() -> None:
    packet = retrieval_node._build_exhaustive_retrieval_packet(
        [{
            "id": "room-1",
            "text": "Deluxe Double Room, 32 m2",
            "matched_intent": "hotel",
            "matched_destination_id": "nha-trang",
            "metadata": {
                "entity_type": "room",
                "entity_id": "room-1",
                "entity_name": "Deluxe Double Room",
                "property_id": "vinpearl-empire-nha-trang",
                "property_name": "Vinpearl Empire Nha Trang",
            },
        }],
        ["hotel"],
        complete=True,
    )

    room = packet["entities"][0]
    assert room["destination_id"] == "nha-trang"
    assert room["property_id"] == "vinpearl-empire-nha-trang"
    assert room["property_name"] == "Vinpearl Empire Nha Trang"
