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
        # Keep the accented single-token form. The accentless token ``phong`` is
        # ambiguous in Vietnamese (e.g. ``phong cảnh`` = scenery), so treating
        # it as an authoritative room signal creates false hotel intents.
        # Accentless room requests are still covered by unambiguous phrases and
        # can fall back to the standalone rewrite when phrased differently.
        "phòng", "dat phong", "book phong", "gia phong", "loai phong",
        "con phong", "het phong", "phong nghi",
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
        # Booking/refund lifecycle is policy even when the user does not literally
        # say "policy". Keeping these here lets mixed questions such as
        # "payment + refund" create separate payment/policy retrieval branches.
        "refund", "refunds", "refundable", "non-refundable", "nonrefundable",
        "cancellation", "cancel booking", "cancel reservation", "booking cancellation",
        "amendment", "reschedule", "change booking", "change reservation",
        "hoan tien", "hoàn tiền", "hoan ve", "hoàn vé",
        "huy dat phong", "hủy đặt phòng", "huỷ đặt phòng",
        "huy booking", "hủy booking", "huỷ booking",
        "huy dat cho", "hủy đặt chỗ", "huỷ đặt chỗ",
        "doi dat cho", "đổi đặt chỗ", "thay doi dat cho", "thay đổi đặt chỗ",
    ),
    "payment": (
        "payment", "payments", "pay", "bank", "account", "swift",
        "thanh toan", "thanh toán", "tai khoan", "tài khoản", "ngan hang", "ngân hàng",
    ),
}

INTENT_ENTITY_TYPES: dict[str, set[str]] = {
    # Keep branch evidence semantically strict. Generic destination/highlight/complex
    # documents are useful for attraction discovery, but should not make a hotel or
    # service branch look "found" when there is no actual hotel/service record.
    "hotel": {
        "property", "room",
    },
    "service": {
        "booking_product", "amenity", "dining_service", "golf_feature",
        "mice_venue", "mice_room",
    },
    "dining": {"booking_product", "dining_service", "property", "amenity"},
    "promotion": {
        "booking_product", "promotion", "promotion_benefit", "promotion_block", "promotion_code",
        "promotion_destination", "promotion_property_raw", "promotion_relation",
        "promotion_section", "promotion_term",
    },
    "attraction": {
        "booking_product", "destination", "attraction", "destination_highlight", "complex",
    },
    "event": {"booking_product", "attraction", "destination_highlight", "complex"},
    "golf": {"golf_course", "golf_feature"},
    "mice": {"mice_venue", "mice_room", "mice_room_capacity"},
    "policy": {"booking_product", "policy_document", "policy_section", "policy_block", "faq"},
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
    # Open-ended recommendation wording. These describe the *shape* of the
    # request rather than a domain attribute such as forest/beach/greenery, so
    # unseen preference wording is handled the same way.
    "noi nao",
    "cho nao",
    "dia diem nao",
    "travel",
    "tourism",
    "travel guide",
    "travel advice",
    "trip",
    "things to do",
    "what to do",
    "what is there",
    "what s there",
    "recommend",
    "recommendation",
    "where should i go",
    "where can i go",
    "where to go",
    "go where",
    "di dau",
    "nen di dau",
    "which place",
    "which destination",
    "any place",
    "anywhere",
    "explore",
    "itinerary",
    "vacation",
    "holiday",
)

# Weak navigation wording is useful only when a concrete destination is already
# resolved.  Keeping it separate prevents specific requests such as "can I visit
# with a wheelchair/pet?" from being reclassified as broad discovery merely
# because the rewrite happens to contain the verb "visit".
_GENERIC_DISCOVERY_DESTINATION_SCOPED_MARKERS: tuple[str, ...] = (
    "visit",
    "visiting",
)

# Scope is decided once, upstream, by the authoritative semantic guardrail.
# This parser deliberately does not maintain an external-topic keyword deny-list:
# terms such as flight, shuttle, transfer, rain, passport, or payment can be valid
# Vinpearl FAQ/service content and must not suppress retrieval after scope was allowed.


# Budget/affordability is a cross-cutting constraint rather than a standalone
# catalog noun. When a user asks for Vinpearl experiences/services/hotels within
# a concrete budget, promotion/offer evidence is directly relevant even if the
# literal words "promotion" or "ưu đãi" are absent. Keep this deliberately
# conservative so arbitrary monetary amounts (for example a refund amount) do
# not silently become promotion intent.
_BUDGET_CONSTRAINT_MARKERS: tuple[str, ...] = (
    "ngan sach", "tai chinh", "budget", "financial limit", "spending limit",
    "afford", "affordable", "within budget", "under budget", "price range",
)

_BUDGET_AMOUNT_RE = re.compile(
    r"(?:^|\s)\d+(?:[.,]\d+)?\s*(?:tr|trieu|million|k|nghin|ngan|vnd|dong)(?:$|\s)"
)

def _has_budget_constraint(user_message: str, rag_query: str = "") -> bool:
    """Detect an affordability constraint without treating every price as a deal.

    Strong affordability wording is sufficient on its own. Generic comparative
    wording such as ``duoi``/``under`` is accepted only when a currency-like
    amount is also present. Both the current message and faithful rewrite are
    checked to support arbitrary input languages.
    """
    combined = normalize_text(f"{user_message} {rag_query}")
    if not combined:
        return False
    if any(marker in combined for marker in _BUDGET_CONSTRAINT_MARKERS):
        return True
    has_amount = bool(_BUDGET_AMOUNT_RE.search(f" {combined} "))
    if not has_amount:
        return False
    comparative_markers = (
        "chi co", "toi da", "khong qua", "tam gia", "muc gia",
        "duoi", "tren duoi", "tam", "khoang", "under", "within",
        "up to", "maximum",
    )
    if any(marker in combined for marker in comparative_markers):
        return True

    # Natural Vietnamese recommendation requests often express affordability as
    # "tôi/mình/em có 3 triệu" without saying the literal word "ngân sách".
    # Treat that possession wording as a budget only when the same turn is clearly
    # about travel/leisure discovery. This avoids misreading unrelated amounts
    # such as "tôi có 3 triệu tiền cọc, muốn hoàn tiền" as a travel budget.
    possession_markers = ("toi co", "minh co", "em co", "co tam", "co khoang")
    travel_context_markers = (
        "du lich", "di choi", "muon di", "di dau", "nen di dau",
        "nghi duong", "xa stress", "thu gian", "vui choi",
        "vinpearl", "vinwonders", "hotel", "resort", "spa",
        "travel", "trip", "vacation", "holiday", "relax", "where should i go",
    )
    return (
        any(marker in combined for marker in possession_markers)
        and any(marker in combined for marker in travel_context_markers)
    )


def extract_budget_vnd(user_message: str, rag_query: str = "") -> int | None:
    """Return the user's affordability ceiling in VND when one is explicit.

    Budget is modeled as a constraint, not a catalog intent. We intentionally
    parse it only after :func:`_has_budget_constraint` succeeds so unrelated
    monetary values (refund amount, deposit, invoice value, etc.) do not become
    travel-budget constraints. The current user wording is preferred over the
    LLM rewrite; the rewrite is only a multilingual fallback.
    """
    if not _has_budget_constraint(user_message, rag_query):
        return None

    def parse_one(text_value: str) -> list[int]:
        text = str(text_value or "")
        values: list[int] = []

        # Compact human forms: 2tr, 2 trieu, 2 million, 500k, 500 nghin.
        compact = re.compile(
            r"(?<![\w])(?P<num>\d+(?:[.,]\d+)?)\s*"
            r"(?P<unit>tr|tri[eệ]u|million|k|ngh[iì]n|ng[aà]n)\b",
            flags=re.IGNORECASE,
        )
        for match in compact.finditer(text):
            raw_num = match.group("num").replace(",", ".")
            try:
                number = float(raw_num)
            except ValueError:
                continue
            unit = normalize_text(match.group("unit"))
            multiplier = 1_000_000 if unit in {"tr", "trieu", "million"} else 1_000
            value = int(round(number * multiplier))
            if value > 0:
                values.append(value)

        # Fully written currency forms: 2.000.000 VND / 2,000,000 VNĐ / 2000000 đồng.
        full = re.compile(
            r"(?<!\d)(?P<num>\d{1,3}(?:[.,]\d{3}){1,3}|\d{4,10})\s*"
            r"(?:vnd|vnđ|đ|đồng|dong)\b",
            flags=re.IGNORECASE,
        )
        for match in full.finditer(text):
            digits = re.sub(r"[^0-9]", "", match.group("num"))
            if not digits:
                continue
            value = int(digits)
            if value > 0:
                values.append(value)
        return values

    # User text is authoritative. Only fall back to the standalone rewrite when
    # the current message's budget wording could not be numerically parsed.
    values = parse_one(user_message)
    if not values:
        values = parse_one(rag_query)
    if not values:
        return None

    # If the same ceiling is repeated in the rewrite this stays stable; for a
    # genuine range such as 1-2 million, the upper bound is the useful ceiling.
    return max(values)

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

# Price/package/ticket wording is a cross-cutting retrieval facet, not a catalog
# intent.  Keep it separate from INTENT_KEYWORDS so a request such as
# "Aquafield service prices" still has the user's semantic intents (service +
# attraction), while retrieval may additionally prefer price-bearing booking
# products without replacing either branch.
_PRICE_REQUEST_MARKERS: tuple[str, ...] = (
    "price", "prices", "pricing", "ticket price", "service price", "cost",
    "costs", "fare", "fares", "how much", "giá", "muc gia",
    "mức giá", "gia ve", "giá vé", "gia bao nhieu", "gia ra sao",
    "gia ca", "bao nhieu tien", "bao nhiêu tiền",
)

_BOOKING_EVIDENCE_MARKERS: tuple[str, ...] = (
    "ticket", "tickets", "package", "packages", "combo", "membership",
    "pass", "voucher", "booking", "book", "vé", "gói",
    "goi dich vu", "goi ve", "the hoi vien", "thẻ",
)

def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFD", str(value))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.lower().replace("đ", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def normalize_intent_text(value: str | None) -> str:
    """Normalize text for intent matching without collapsing Vietnamese homographs.

    Destination/entity matching intentionally uses :func:`normalize_text` so
    accented and accentless place names can resolve to the same canonical item.
    Intent matching is different: stripping diacritics can change meaning
    (``phòng`` = room, while ``phong cảnh`` = scenery). Keep Unicode letters and
    diacritics here, while still normalizing case, punctuation and whitespace.
    """
    if not value:
        return ""
    value = unicodedata.normalize("NFC", str(value)).lower()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).replace("_", " ")
    return re.sub(r"\s+", " ", value).strip()

def _contains_intent_phrase(text_value: str | None, markers: tuple[str, ...]) -> bool:
    normalized = normalize_intent_text(text_value)
    if not normalized:
        return False
    padded = f" {normalized} "
    for marker in markers:
        token = normalize_intent_text(marker)
        if token and f" {token} " in padded:
            return True
    return False

def detect_retrieval_facets(user_message: str, rag_query: str) -> dict[str, bool]:
    """Detect cross-cutting facts that should shape evidence selection.

    The current user message is authoritative.  The standalone rewrite is used
    only as a multilingual fallback so these flags cannot become a replacement
    for the user's intents or destination constraints.
    """
    price_requested = _contains_intent_phrase(user_message, _PRICE_REQUEST_MARKERS)
    if not price_requested:
        price_requested = _contains_intent_phrase(rag_query, _PRICE_REQUEST_MARKERS)

    booking_evidence_preferred = price_requested or _contains_intent_phrase(
        user_message, _BOOKING_EVIDENCE_MARKERS
    )
    if not booking_evidence_preferred:
        booking_evidence_preferred = _contains_intent_phrase(
            rag_query, _BOOKING_EVIDENCE_MARKERS
        )

    return {
        "price_requested": bool(price_requested),
        "booking_evidence_preferred": bool(booking_evidence_preferred),
    }

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

def _intent_matches(text_value: str | None) -> list[tuple[int, int, str]]:
    """Return intent matches ordered by where the user mentioned them.

    Tuple = (first_position, -specificity_score, intent). This keeps multi-clause
    questions in roughly the same order as the user's wording.
    """
    normalized = normalize_intent_text(text_value)
    if not normalized:
        return []

    found: list[tuple[int, int, str]] = []
    for intent, keywords in INTENT_KEYWORDS.items():
        positions: list[int] = []
        specificity = 0
        for keyword in keywords:
            nk = normalize_intent_text(keyword)
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
    intents (hotel, golf, policy, payment, ...) have failed to match. Open-ended
    discovery may happen before a destination exists (for example "where should
    I go?"), so strong recommendation/travel wording is sufficient by itself.
    Weak navigation verbs such as ``visit`` remain destination-scoped.
    """
    normalized_message = normalize_text(user_message)
    normalized_rag = normalize_text(rag_query)
    combined = f"{normalized_message} {normalized_rag}".strip()
    if not combined:
        return False

    # A discovery/recommendation request does not require the user to have
    # already named a destination.  In fact, "where should I go?" is exactly the
    # turn where destination discovery is needed.  The previous destination
    # requirement made these requests fall through to model-rewrite intents; a
    # rewrite containing "resorts" could then incorrectly turn the whole request
    # into a hotel lookup.
    if any(marker in combined for marker in _GENERIC_DISCOVERY_MARKERS):
        return True

    # Very weak navigation wording is considered discovery only after a concrete
    # destination has been resolved.
    if destinations and any(
        marker in combined for marker in _GENERIC_DISCOVERY_DESTINATION_SCOPED_MARKERS
    ):
        return True

    return False

def detect_supported_destination_discovery(
    user_message: str,
    rag_query: str = "",
) -> list[dict[str, Any]]:
    """Return catalog destinations for broad travel/discovery requests.

    This helper is intentionally narrow: a destination must resolve against the
    official destination catalog AND the current request must have broad
    discovery/planning shape (for example ``có gì chơi ở Hà Nội`` or
    ``tư vấn du lịch Hà Nội``).  It is used upstream as deterministic evidence
    that the request may be answered as *Vinpearl-KB-bounded* destination
    discovery even when the user does not repeat the Vinpearl brand name.

    It does not authorize unrelated deliverables and it does not bypass safety or
    prompt-injection checks.
    """
    destinations = detect_destinations(user_message, rag_query)
    if not destinations:
        return []
    if not _is_generic_destination_discovery(
        user_message=user_message,
        rag_query=rag_query,
        destinations=destinations,
    ):
        return []
    return destinations

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
    explicit_intents = detect_intents(user_message)
    intents = list(explicit_intents)
    intent_origin = "current_explicit" if intents else "none"

    if not intents and _is_generic_destination_discovery(
        user_message=user_message,
        rag_query=rag_query,
        destinations=destinations,
    ):
        intents = list(GENERIC_DISCOVERY_INTENTS)
        intent_origin = "generic_discovery"
    elif not intents:
        # The standalone English rewrite is useful as a multilingual retrieval
        # hint, but its wording is model-generated.  Keep that provenance so a
        # phrase introduced by the rewrite (for example ``resorts`` or
        # ``VinWonders``) cannot silently become an authoritative user intent in
        # downstream sufficiency fast-paths.
        intents = detect_intents(rag_query)
        if intents:
            intent_origin = "rewrite_inferred"

    # A concrete affordability constraint means promotion/offer evidence can
    # materially answer the request even when the user says only "service" or
    # "travel". Add it as a deterministic secondary branch instead of relying on
    # the LLM rewrite to happen to include words such as "deal" or "promotion".
    constraint_derived_intents: list[str] = []
    if _has_budget_constraint(user_message, rag_query) and "promotion" not in intents:
        budget_compatible_intents = {"hotel", "service", "attraction"}
        if not intents or any(intent in budget_compatible_intents for intent in intents):
            intents.append("promotion")
            constraint_derived_intents.append("promotion")
            if intent_origin == "none":
                intent_origin = "constraint_derived"

    budget_vnd = extract_budget_vnd(user_message, rag_query)
    facets = detect_retrieval_facets(user_message, rag_query)
    primary_intent = intents[0] if intents else None
    return {
        "destination": destinations[0] if destinations else None,
        "destinations": destinations,
        "intent": primary_intent,  # backward-compatible field
        "intents": intents,
        "explicit_intents": explicit_intents,
        "constraint_derived_intents": constraint_derived_intents,
        "has_budget_constraint": budget_vnd is not None,
        "budget_vnd": budget_vnd,
        "price_requested": bool(facets.get("price_requested")),
        "booking_evidence_preferred": bool(facets.get("booking_evidence_preferred")),
        "intent_origin": intent_origin,
        "preferred_entity_types": sorted(INTENT_ENTITY_TYPES.get(primary_intent or "", set())),
        "preferred_entity_types_by_intent": {
            intent: sorted(INTENT_ENTITY_TYPES.get(intent, set())) for intent in intents
        },
    }