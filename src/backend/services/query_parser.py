from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text

from src.backend.config import get_settings


# Keep intents semantic and non-overlapping where practical. Generic "event/su kien"
# is treated as leisure/event content, while conference/meeting terminology remains MICE.
INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hotel": (
        "hotel", "hotels", "resort", "resorts", "property", "properties",
        "khach san", "khách sạn", "khu nghi duong", "khu nghỉ dưỡng",
        "villa", "villas", "biet thu", "biệt thự", "room", "rooms",
        "phong", "phòng",
    ),
    "service": (
        "service", "services", "amenity", "amenities", "facility", "facilities",
        "dich vu", "dịch vụ", "tien ich", "tiện ích", "spa", "pool",
        "ho boi", "hồ bơi",
    ),
    "dining": (
        "dining", "restaurant", "restaurants", "nha hang", "nhà hàng",
        "bar", "food", "foods", "am thuc", "ẩm thực", "an uong", "ăn uống",
    ),
    "promotion": (
        "promotion", "promotions", "offer", "offers", "deal", "deals",
        "khuyen mai", "khuyến mãi", "uu dai", "ưu đãi", "voucher", "code",
    ),
    "attraction": (
        "attraction", "attractions", "vinwonders", "theme park", "water park",
        "khu vui choi", "khu vui chơi", "diem tham quan", "điểm tham quan",
        "hoat dong", "hoạt động", "entertainment", "giai tri", "giải trí",
        "grand world", "aquafield",
    ),
    "event": (
        "event", "events", "su kien", "sự kiện", "show", "shows",
        "festival", "festivals", "le hoi", "lễ hội", "parade",
    ),
    "golf": ("golf", "golf course", "san golf", "sân golf"),
    "mice": (
        "mice", "meeting", "meetings", "conference", "conferences",
        "hoi nghi", "hội nghị", "phong hop", "phòng họp", "wedding", "weddings",
        "tiec cuoi", "tiệc cưới",
    ),
    "policy": (
        "policy", "policies", "regulation", "regulations", "terms", "term",
        "chinh sach", "chính sách", "quy dinh", "quy định", "dieu khoan", "điều khoản",
        "check-in", "check-out", "check in", "check out",
    ),
    "payment": (
        "payment", "payments", "pay", "bank", "account", "swift",
        "thanh toan", "thanh toán", "tai khoan", "tài khoản", "ngan hang", "ngân hàng",
    ),
}

INTENT_ENTITY_TYPES: dict[str, set[str]] = {
    "hotel": {
        "property", "room", "amenity", "dining_service",
        "destination", "destination_highlight", "complex",
    },
    "service": {
        "property", "room", "amenity", "dining_service",
        "destination_highlight", "golf_feature", "mice_venue", "mice_room",
        "attraction", "complex",
    },
    "dining": {"dining_service", "property", "amenity"},
    "promotion": {
        "promotion", "promotion_benefit", "promotion_block", "promotion_code",
        "promotion_destination", "promotion_property_raw", "promotion_relation",
        "promotion_section", "promotion_term",
    },
    "attraction": {
        "attraction", "destination_highlight", "complex",
    },
    "event": {"attraction", "destination_highlight", "complex"},
    "golf": {"golf_course", "golf_feature"},
    "mice": {"mice_venue", "mice_room", "mice_room_capacity"},
    "policy": {"policy_document", "policy_section", "policy_block", "faq"},
    "payment": {"policy_document", "policy_section", "policy_block", "faq"},
}



# Generic destination discovery is intentionally mapped to several existing
# catalog intents instead of adding a synthetic entity type. This keeps
# retrieval branch-specific and gives the answerer a balanced set of grounded
# evidence for broad requests such as "tôi muốn đi du lịch Hà Nội" or
# "what can I do in Phu Quoc?".
GENERIC_DISCOVERY_INTENTS: tuple[str, ...] = (
    "attraction",
    "hotel",
    "dining",
    "service",
)

# These markers are evaluated only when no explicit supported intent was found.
# Current-message wording is checked first; the standalone RAG query is also
# checked so non-Latin languages can benefit from the LLM's English rewrite.
_GENERIC_DISCOVERY_MARKERS: tuple[str, ...] = (
    "du lich",
    "di choi",
    "choi gi",
    "co gi",
    "goi y",
    "kham pha",
    "tham quan",
    "lich trinh",
    "muon di",
    "travel",
    "tourism",
    "travel guide",
    "travel advice",
    "trip",
    "visit",
    "visiting",
    "things to do",
    "what to do",
    "what is there",
    "what s there",
    "recommend",
    "recommendation",
    "explore",
    "itinerary",
    "vacation",
    "holiday",
)

# A generic travel word must not broaden a clearly external request into a
# Vinpearl discovery query. Scope/guardrail already handles these topics, but
# this parser-level deny list makes retrieval fail-safe as well.
_GENERIC_DISCOVERY_EXCLUSIONS: tuple[str, ...] = (
    "ve may bay",
    "may bay",
    "flight",
    "airline",
    "thoi tiet",
    "weather",
    "visa",
    "thi thuc",
    "ho chieu",
    "passport",
    "taxi",
    "grab",
    "xe buyt",
    "bus route",
    "tau hoa",
    "train ticket",
)

INTENT_QUERY_LABELS: dict[str, str] = {
    "hotel": "hotels resorts rooms accommodation",
    "service": "services amenities facilities",
    "dining": "restaurants dining food and beverage",
    "promotion": "promotions offers deals",
    "attraction": "attractions entertainment things to do",
    "event": "events shows festivals entertainment",
    "golf": "golf courses and golf services",
    "mice": "meetings conferences weddings MICE venues",
    "policy": "policies regulations terms",
    "payment": "payment guidance policies",
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFD", str(value))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.lower().replace("đ", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


@lru_cache(maxsize=1)
def load_destination_catalog() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    catalog: dict[str, dict[str, Any]] = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, name_en, name_vi, province FROM core.destination")
            ).mappings()
            for row in rows:
                destination_id = str(row["id"])
                aliases = {
                    destination_id,
                    str(row.get("name_en") or ""),
                    str(row.get("name_vi") or ""),
                    str(row.get("province") or ""),
                }
                catalog[destination_id] = {
                    "id": destination_id,
                    "name_en": row.get("name_en"),
                    "name_vi": row.get("name_vi"),
                    "aliases": {a for a in aliases if a.strip()},
                }

            alias_rows = conn.execute(
                text("SELECT destination_id, alias, alias_normalized FROM core.destination_alias")
            ).mappings()
            for row in alias_rows:
                destination_id = str(row["destination_id"])
                if destination_id not in catalog:
                    catalog[destination_id] = {
                        "id": destination_id,
                        "name_en": destination_id,
                        "name_vi": destination_id,
                        "aliases": {destination_id},
                    }
                for field in ("alias", "alias_normalized"):
                    value = str(row.get(field) or "").strip()
                    if value:
                        catalog[destination_id]["aliases"].add(value)
    except Exception as exc:
        print(f"[QueryParser] Could not load destination aliases: {exc}")
        return {}
    finally:
        engine.dispose()

    for item in catalog.values():
        normalized_aliases = {
            normalize_text(alias) for alias in item["aliases"] if normalize_text(alias)
        }
        normalized_aliases.add(normalize_text(item["id"]))
        item["normalized_aliases"] = sorted(
            normalized_aliases,
            key=lambda value: (-len(value), value),
        )

    return catalog


def _contains_phrase(haystack: str, needle: str) -> bool:
    if not haystack or not needle:
        return False
    return re.search(rf"(?:^|\s){re.escape(needle)}(?:$|\s)", haystack) is not None


def detect_destinations(*texts: str | None) -> list[dict[str, Any]]:
    """Detect every distinct destination mentioned, in textual order."""
    combined = normalize_text(" ".join(str(t or "") for t in texts))
    if not combined:
        return []

    matches: list[tuple[int, int, dict[str, Any], str]] = []
    for item in load_destination_catalog().values():
        best_for_item: tuple[int, int, dict[str, Any], str] | None = None
        for alias in item.get("normalized_aliases", []):
            pattern = re.compile(rf"(?:^|\s)({re.escape(alias)})(?:$|\s)")
            match = pattern.search(combined)
            if not match:
                continue
            start = match.start(1)
            candidate = (start, -len(alias), item, alias)
            if best_for_item is None or candidate[:2] < best_for_item[:2]:
                best_for_item = candidate
        if best_for_item is not None:
            matches.append(best_for_item)

    matches.sort(key=lambda value: (value[0], value[1]))
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, _, item, matched_alias in matches:
        destination_id = str(item["id"])
        if destination_id in seen:
            continue
        seen.add(destination_id)
        output.append(
            {
                "id": destination_id,
                "name_en": item.get("name_en"),
                "name_vi": item.get("name_vi"),
                "matched_alias": matched_alias,
                "aliases": list(item.get("normalized_aliases", [])),
            }
        )
    return output


def detect_destination(*texts: str | None) -> dict[str, Any] | None:
    destinations = detect_destinations(*texts)
    return destinations[0] if destinations else None


def _intent_matches(text_value: str | None) -> list[tuple[int, int, str]]:
    """Return intent matches ordered by where the user mentioned them.

    Tuple = (first_position, -specificity_score, intent). This keeps multi-clause
    questions in roughly the same order as the user's wording.
    """
    normalized = normalize_text(text_value)
    if not normalized:
        return []

    found: list[tuple[int, int, str]] = []
    for intent, keywords in INTENT_KEYWORDS.items():
        positions: list[int] = []
        specificity = 0
        for keyword in keywords:
            nk = normalize_text(keyword)
            if not nk:
                continue
            pattern = re.compile(rf"(?:^|\s)({re.escape(nk)})(?:$|\s)")
            match = pattern.search(normalized)
            if match:
                positions.append(match.start(1))
                specificity += max(1, len(nk.split()))
        if positions:
            found.append((min(positions), -specificity, intent))
    found.sort(key=lambda item: (item[0], item[1], item[2]))
    return found


def detect_intents(*texts: str | None, max_intents: int = 8) -> list[str]:
    """Detect every distinct intent instead of collapsing a multi-clause query to one.

    Current user wording should be passed first. Callers can fall back to a rewritten
    RAG query only when the current message has no explicit intent.
    """
    output: list[str] = []
    seen: set[str] = set()
    for text_value in texts:
        for _, _, intent in _intent_matches(text_value):
            if intent in seen:
                continue
            seen.add(intent)
            output.append(intent)
            if len(output) >= max_intents:
                return output
    return output


def detect_intent(*texts: str | None) -> str | None:
    intents = detect_intents(*texts, max_intents=1)
    return intents[0] if intents else None


def build_intent_query(
    intent: str,
    destinations: list[dict[str, Any]],
    fallback_query: str,
) -> str:
    """Create a focused semantic query for one intent in a multi-intent turn."""
    destination_names = [
        str(item.get("name_en") or item.get("name_vi") or item.get("id") or "").strip()
        for item in destinations
    ]
    destination_part = " ".join(name for name in destination_names if name)
    intent_part = INTENT_QUERY_LABELS.get(intent, intent)
    if destination_part:
        return f"Vinpearl VinWonders {destination_part} {intent_part}".strip()
    return f"{fallback_query} {intent_part}".strip()



def _is_generic_destination_discovery(
    user_message: str,
    rag_query: str,
    destinations: list[dict[str, Any]],
) -> bool:
    """Return True only for broad destination exploration/planning requests.

    This is deliberately a fallback: callers invoke it only after explicit
    intents (hotel, golf, policy, payment, ...) have failed to match. The
    destination requirement prevents generic phrases such as "gợi ý cho tôi"
    from turning into a broad corpus search.
    """
    if not destinations:
        return False

    normalized_message = normalize_text(user_message)
    normalized_rag = normalize_text(rag_query)
    combined = f"{normalized_message} {normalized_rag}".strip()
    if not combined:
        return False

    if any(marker in combined for marker in _GENERIC_DISCOVERY_EXCLUSIONS):
        return False

    return any(marker in combined for marker in _GENERIC_DISCOVERY_MARKERS)

def parse_retrieval_query(user_message: str, rag_query: str) -> dict[str, Any]:
    # The LLM-created RAG query remains the canonical destination target because it
    # resolves references/complaints from memory. Current-message intents, however,
    # must take priority so an earlier topic cannot leak into a new turn.
    destinations = detect_destinations(rag_query)
    if not destinations:
        destinations = detect_destinations(user_message)

    # Explicit intent words in the CURRENT user message always win. If the
    # current wording is broad discovery/planning, do not let the LLM rewrite
    # accidentally narrow it to only one or two categories (e.g. "hotel services").
    # Only use rewritten-query intents when the current message is neither explicit
    # nor a generic discovery request. This keeps multilingual specific requests
    # working while making broad travel consultation deterministic.
    intents = detect_intents(user_message)
    if not intents and _is_generic_destination_discovery(
        user_message=user_message,
        rag_query=rag_query,
        destinations=destinations,
    ):
        intents = list(GENERIC_DISCOVERY_INTENTS)
    elif not intents:
        intents = detect_intents(rag_query)

    primary_intent = intents[0] if intents else None
    return {
        "destination": destinations[0] if destinations else None,
        "destinations": destinations,
        "intent": primary_intent,  # backward-compatible field
        "intents": intents,
        "preferred_entity_types": sorted(INTENT_ENTITY_TYPES.get(primary_intent or "", set())),
        "preferred_entity_types_by_intent": {
            intent: sorted(INTENT_ENTITY_TYPES.get(intent, set())) for intent in intents
        },
    }