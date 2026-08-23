from src.backend.services.faq_matcher import FAQMatcher

# Self-contained rows emulate the active ``core.faq`` repository result.
_POSTGRES_FAQ_ROWS = [
    {"index": 0, "question": "How many pieces/kilos of luggage can I check in?", "answer": "The baggage allowance lists permitted pieces and checked baggage weight.", "category": "Transportation", "subcategory": "Baggage", "source_path": "postgresql:core.faq"},
    {"index": 1, "question": "How to buy an entrance ticket to VinWonders Nam Hoi An?", "answer": "Purchase through official sales channels.", "category": "VinWonders Nam Hoi An", "subcategory": "Tickets", "source_path": "postgresql:core.faq"},
    {"index": 2, "question": "Where are Vinpearl's properties?", "answer": "Properties are available at multiple destinations.", "category": "Properties", "subcategory": "Locations", "source_path": "postgresql:core.faq"},
]


def _matcher() -> FAQMatcher:
    return FAQMatcher(
        embed_passages=lambda values: [],
        embed_queries=lambda values: [],
        rows_loader=lambda: list(_POSTGRES_FAQ_ROWS),
    )


def test_translated_baggage_query_keeps_predicate_alignment() -> None:
    matcher = _matcher()
    entry = next(
        item
        for item in matcher._load_entries()
        if item.question == "How many pieces/kilos of luggage can I check in?"
    )

    count, ratio = matcher._predicate_overlap(
        "Vinpearl flight ticket baggage allowance checked baggage weight limit pieces",
        entry,
    )

    assert count >= 3
    assert ratio >= 0.45

    accepted, _ = matcher._confidence_gate(
        semantic=0.8472,
        lexical=0.2208,
        weighted_f1=0.1557,
        query_coverage=0.1183,
        predicate_count=count,
        predicate_ratio=ratio,
        margin=0.0087,
    )
    assert accepted is True


def test_same_destination_wrong_faq_cannot_clear_pass_on_margin_alone() -> None:
    matcher = _matcher()
    entry = next(
        item
        for item in matcher._load_entries()
        if item.question == "How to buy an entrance ticket to VinWonders Nam Hoi An?"
    )

    count, ratio = matcher._predicate_overlap(
        "Vinpearl Golf Nam Hoi An number of holes and par",
        entry,
    )

    # Shared venue tokens are removed; a coincidental word such as "number" in a
    # phone number is not enough to prove the FAQ asks for holes/par.
    assert count <= 1
    assert ratio < 0.50

    accepted, _ = matcher._confidence_gate(
        semantic=0.8012,
        lexical=0.3105,
        weighted_f1=0.3481,
        query_coverage=0.2974,
        predicate_count=count,
        predicate_ratio=ratio,
        margin=0.0576,
    )
    assert accepted is False


def test_existing_strong_direct_faq_match_stays_accepted() -> None:
    matcher = _matcher()
    accepted, _ = matcher._confidence_gate(
        semantic=0.76,
        lexical=0.78,
        weighted_f1=0.61,
        query_coverage=0.66,
        predicate_count=0,
        predicate_ratio=0.0,
        margin=0.01,
    )
    assert accepted is True


def test_exact_english_faq_path_remains_threshold_free() -> None:
    matcher = _matcher()
    documents, diagnostics = matcher.match(
        original_query="How many pieces/kilos of luggage can I check in?",
        rewritten_query="How many pieces/kilos of luggage can I check in?",
    )
    assert diagnostics["accepted"] is True
    assert diagnostics["mode"] == "faq_exact"
    assert documents[0]["metadata"]["entity_name"] == "How many pieces/kilos of luggage can I check in?"
    assert documents[0]["metadata"]["source_file"] == "postgresql:core.faq"


def test_resolved_destination_words_do_not_count_as_predicate_evidence() -> None:
    matcher = _matcher()
    entry = next(
        item for item in matcher._load_entries()
        if item.question == "Where are Vinpearl's properties?"
    )

    count, ratio = matcher._predicate_overlap(
        "Vinpearl Golf Hai Phong number of holes and par",
        entry,
        routing_context="Hai Phong hai-phong",
    )

    assert count == 0
    assert ratio == 0.0
