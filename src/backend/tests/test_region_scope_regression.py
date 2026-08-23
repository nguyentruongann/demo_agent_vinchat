from src.backend.agents.nodes import retrieval as retrieval_node
from src.backend.agents.nodes.context_resolver import _parse_current_destination_bindings
from src.backend.services import query_parser


def _catalog():
    return {
        "phu-quoc": {
            "id": "phu-quoc", "name_vi": "Phú Quốc", "name_en": "Phu Quoc",
            "region": "south", "has_content": True,
        },
        "ho-chi-minh": {
            "id": "ho-chi-minh", "name_vi": "Thành phố Hồ Chí Minh",
            "name_en": "Ho Chi Minh City", "region": "south", "has_content": True,
        },
        "hoi-an": {
            "id": "hoi-an", "name_vi": "Hội An", "name_en": "Hoi An",
            "region": "central", "has_content": True,
        },
        "hue": {
            "id": "hue", "name_vi": "Huế", "name_en": "Hue",
            "region": "central", "has_content": False,
        },
    }


def test_region_detection_does_not_treat_nam_hoi_an_as_south():
    assert query_parser.detect_destination_regions("Vinpearl Nam Hội An") == []
    assert query_parser.detect_destination_regions("miền Nam có khu du lịch gì") == ["south"]
    assert query_parser.detect_destination_regions("Southern Vietnam resorts") == ["south"]


def test_region_catalog_expansion_is_complete_and_content_backed():
    items = query_parser.destinations_for_regions(["south"], catalog=_catalog())
    assert [item["id"] for item in items] == ["phu-quoc", "ho-chi-minh"]
    assert all(item["source"] == "current_explicit_region" for item in items)


def test_retrieval_region_scope_overrides_unbounded_empty_resolution(monkeypatch):
    monkeypatch.setattr(retrieval_node, "destinations_for_regions", lambda regions: [
        _catalog()["phu-quoc"], _catalog()["ho-chi-minh"]
    ])
    state = {
        "user_message": "cho tôi tất cả khu du lịch tại miền Nam",
        "sanitized_user_request": "cho tôi tất cả khu du lịch tại miền Nam",
        "rag_query": "all Vinpearl tourist destinations in Southern Vietnam",
        "request_tasks": [],
        "resolved_destinations": [],
        "excluded_destination_ids": [],
    }
    scoped, regions = retrieval_node._apply_deterministic_region_scope(state)
    assert regions == ["south"]
    assert scoped["resolved_destination_ids"] == ["phu-quoc", "ho-chi-minh"]
    assert {item["region"] for item in scoped["resolved_destinations"]} == {"south"}


def test_region_scope_respects_explicit_exclusion(monkeypatch):
    monkeypatch.setattr(retrieval_node, "destinations_for_regions", lambda regions: [
        _catalog()["phu-quoc"], _catalog()["ho-chi-minh"]
    ])
    state = {
        "user_message": "ngoài Phú Quốc, miền Nam còn khu nào?",
        "sanitized_user_request": "ngoài Phú Quốc, miền Nam còn khu nào?",
        "rag_query": "southern destinations other than Phu Quoc",
        "request_tasks": [],
        "resolved_destinations": [],
        "excluded_destination_ids": ["phu-quoc"],
    }
    scoped, _ = retrieval_node._apply_deterministic_region_scope(state)
    assert scoped["resolved_destination_ids"] == ["ho-chi-minh"]


def test_other_than_phrase_repairs_wrong_positive_binding():
    explicit = [{
        "id": "phu-quoc", "name_vi": "Phú Quốc", "name_en": "Phu Quoc",
        "matched_alias": "phu quoc", "aliases": ["phu quoc"],
    }]
    targets, exclusions, invalid = _parse_current_destination_bindings(
        {
            "current_target_destination_ids": ["phu-quoc"],
            "current_excluded_destination_ids": [],
        },
        explicit,
        "ngoài Phú Quốc ra thì hết rồi à?",
    )
    assert targets == []
    assert [item["id"] for item in exclusions] == ["phu-quoc"]
    assert invalid == []
