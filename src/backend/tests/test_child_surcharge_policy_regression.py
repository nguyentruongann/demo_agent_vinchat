from src.backend.services.faq_matcher import FAQEntry, FAQMatcher
from src.backend.agents.nodes.request_understanding import _atomic_clause_candidates


def _entry(question: str, answer: str) -> FAQEntry:
    return FAQEntry(0, question, answer, "Hotels", "Accommodation", "https://vinpearl.com/en/faqs", "en", "test")


def test_age_specific_surcharge_policy_beats_generic_extra_bed_policy():
    query = "child surcharge policy for a 5 year old child sharing the same bed"
    surcharge = _entry(
        "What is the child surcharge rate for a hotel/villa room?",
        "For hotel rooms, additional charges apply for children from 4 years old to under 12 years old. "
        "For villas, child surcharge applies from 4 years old to under 12 years old.",
    )
    extra_bed = _entry(
        "Can I have an extra bed in the hotel room?",
        "Only one extra bed is allowed. The extra-bed fee depends on the room package.",
    )
    assert FAQMatcher._age_policy_alignment(query, surcharge) == (True, 1.0)
    assert FAQMatcher._age_policy_alignment(query, extra_bed) == (False, 0.0)


def test_non_age_policy_query_does_not_trigger_age_preference():
    entry = _entry(
        "What is the child surcharge rate?",
        "A surcharge applies to children from 4 years old to under 12 years old.",
    )
    assert FAQMatcher._age_policy_alignment("Can I request an extra bed?", entry) == (False, 0.0)


def test_trailing_surcharge_clarification_stays_one_atomic_task():
    message = "Thế còn con 5 tuổi ngủ chung giường thì sao, có phụ thu không?"
    assert _atomic_clause_candidates(message) == [message]
