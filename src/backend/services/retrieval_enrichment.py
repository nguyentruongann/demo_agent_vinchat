from __future__ import annotations

"""Structured post-retrieval enrichment for grounded RAG answers.

The vector index is intentionally optimized for semantic matching, so a selected
chunk may not contain every useful field from the underlying PostgreSQL row.
This module performs a *second, deterministic* lookup after vector/keyword
retrieval:

1. Re-hydrate matched CORE entities from PostgreSQL and attach selected non-null
   fields to each retrieved document.
2. For money/price questions, add destination-scoped price evidence from valid
   room rows and booking products so the answerer can produce an actual estimate
   instead of redirecting the customer to the website.

PostgreSQL remains the source of truth; Chroma only decides which entities are
semantically relevant.
"""

import json
import re
from difflib import SequenceMatcher
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select

from src.backend.config import get_settings
from src.backend.services.db import get_engine
from src.backend.services.query_parser import normalize_text
from src.data_postgre.db import CORE_TABLES


PRICE_DATA_AS_OF = "31/7/2026"
DEFAULT_OUTPUT_CURRENCY_BY_LANGUAGE = {"vi": "VND", "en": "USD"}


def preferred_currency_for_language(language_code: str | None, language_name: str | None = None) -> str:
    """Choose the customer-facing money currency from the input language.

    Vietnamese customers should normally see VND even when source crawler rows are
    in USD. English answers keep USD unless the evidence is only in another
    currency. This function is deliberately small and deterministic; it is a
    presentation rule, not a live FX service.
    """
    code = str(language_code or "").strip().lower()
    name = str(language_name or "").strip().lower()
    if code.startswith("vi") or "vietnamese" in name or "tiếng việt" in name:
        return "VND"
    return "USD"


def currency_conversion_guidance(target_currency: str | None = None) -> str:
    target = _normalize_currency(target_currency) or "USD"
    try:
        rate = Decimal(str(get_settings().usd_to_vnd_rate))
    except Exception:
        rate = Decimal("26000")
    if target == "VND":
        return f"Preferred output currency: VND. Use system conversion basis 1 USD ≈ {int(rate):,} VND for USD evidence. Customer-facing money MUST be shown in VND only; do not show USD amounts or USD parentheses in the final answer."
    if target == "USD":
        return f"Preferred output currency: USD. Use system conversion basis 1 USD ≈ {int(rate):,} VND for VND evidence. Customer-facing money MUST be shown in USD only; do not show VND amounts or VND parentheses in the final answer."
    return f"Preferred output currency: {target}. No system conversion basis is available except USD↔VND at 1 USD ≈ {int(rate):,} VND."

# Large crawler/audit blobs are valuable for debugging but are poor final-LLM
# context. Their curated/normalized siblings are kept instead.
_NOISY_FIELDS = {
    "raw_payload",
    "source_data",
    "validation",
    "html_filename",
    "content_hash",
}

# Price estimation benefits from a few more booking fields than a generic row
# hydration. Keep this ordered so the most decision-useful fields appear first.
_BOOKING_PRIORITY_FIELDS = (
    "id",
    "product_name",
    "destination_id",
    "destination_name",
    "venue_name",
    "service_group",
    "product_type",
    "category",
    "short_description",
    "currency",
    "pricing_status",
    "price_type",
    "is_dynamic_price",
    "is_from_price",
    "is_approximate_price",
    "display_price",
    "display_original_price",
    "display_discount_text",
    "minimum_price",
    "maximum_price",
    "price_variants",
    "is_promotional",
    "promotion_name",
    "promotion_code",
    "discount_percent",
    "valid_from",
    "valid_until",
    "duration",
    "duration_minutes",
    "duration_hours",
    "duration_days",
    "availability_status",
    "availability_text",
    "sold_out",
    "booking_open",
    "inclusions",
    "exclusions",
    "food_and_beverage",
    "spa_and_wellness",
    "policies",
    "source_url",
    "detail_url",
    "booking_url",
    "booking_search_url",
)


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        # Keep exact decimal text instead of silently rounding to float.
        return format(value, "f")
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value



def _normalize_currency(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"VNĐ", "VND", "Đ", "DONG", "ĐỒNG"}:
        return "VND"
    if raw in {"US$", "$", "USD"}:
        return "USD"
    return raw


def _decimal_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Prefer normalized numeric fields. display_price may contain labels; extract
    # the first price-like number only as a fallback.
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except Exception:
        return None


def _money_display(amount: Any, currency: str | None) -> str:
    value = _decimal_amount(amount)
    cur = _normalize_currency(currency)
    if value is None:
        raw = str(amount or "").strip()
        return f"{raw} {cur}".strip()
    if cur == "VND":
        return f"{int(value):,} VND"
    # Keep non-VND values compact but not over-rounded.
    normalized = value.quantize(Decimal("0.01")) if value != value.to_integral() else value.quantize(Decimal("1"))
    return f"{normalized:,} {cur}".strip()


def _converted_money_display(amount: Any, source_currency: str | None, target_currency: str | None) -> str | None:
    value = _decimal_amount(amount)
    source = _normalize_currency(source_currency)
    target = _normalize_currency(target_currency)
    if value is None or not source or not target or source == target:
        return None
    try:
        rate = Decimal(str(get_settings().usd_to_vnd_rate))
    except Exception:
        rate = Decimal("26000")
    if source == "USD" and target == "VND":
        return _money_display((value * rate).quantize(Decimal("1")), "VND")
    if source == "VND" and target == "USD" and rate > 0:
        return _money_display((value / rate).quantize(Decimal("0.01")), "USD")
    return None


def _extract_destination_ids_from_documents(documents: list[dict[str, Any]], limit: int = 3) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in documents:
        metadata = item.get("metadata", {}) or {}
        record = item.get("structured_record", {}) or {}
        candidates = (
            item.get("matched_destination_id"),
            metadata.get("matched_destination_id"),
            metadata.get("destination_id"),
            record.get("destination_id"),
        )
        for raw in candidates:
            destination_id = str(raw or "").strip()
            if destination_id and destination_id not in seen:
                seen.add(destination_id)
                output.append(destination_id)
                if len(output) >= max(1, limit):
                    return output
    return output


def _destination_names(connection, destination_ids: list[str]) -> dict[str, str]:
    destination = CORE_TABLES.get("destination")
    if destination is None or not destination_ids:
        return {}
    columns = destination.c
    name_fields = [name for name in ("name_vi", "name_en", "name", "province") if hasattr(columns, name)]
    select_columns = [columns.id]
    for field in name_fields:
        select_columns.append(getattr(columns, field))
    try:
        rows = connection.execute(
            select(*select_columns).where(columns.id.in_(destination_ids))
        ).mappings().all()
    except Exception:
        return {}
    names: dict[str, str] = {}
    for row in rows:
        destination_id = str(row.get("id") or "")
        for field in ("name_vi", "name_en", "name", "province"):
            value = str(row.get(field) or "").strip()
            if value:
                names[destination_id] = value
                break
    return names


def _candidate_destination_ids_for_cost_estimate(connection, documents: list[dict[str, Any]], limit: int = 3) -> list[str]:
    from_docs = _extract_destination_ids_from_documents(documents, limit=limit)
    if from_docs:
        return from_docs

    room = CORE_TABLES.get("room")
    prop = CORE_TABLES.get("property")
    booking = CORE_TABLES.get("booking_product")
    ordered: list[str] = []
    scores: dict[str, int] = defaultdict(int)

    def add(destination_id: Any, weight: int) -> None:
        value = str(destination_id or "").strip()
        if not value:
            return
        if value not in scores:
            ordered.append(value)
        scores[value] += weight

    if room is not None and prop is not None:
        try:
            rows = connection.execute(
                select(prop.c.destination_id)
                .select_from(room.join(prop, room.c.property_id == prop.c.id))
                .where(
                    or_(
                        room.c.price_from_amount.is_not(None),
                        and_(room.c.rate_amount.is_not(None), room.c.is_rate_suspect.is_(False)),
                    )
                )
                .distinct()
                .limit(25)
            ).mappings().all()
            for row in rows:
                add(row.get("destination_id"), 3)
        except Exception:
            pass

    if booking is not None:
        try:
            rows = connection.execute(
                select(booking.c.destination_id)
                .where(booking.c.destination_id.is_not(None))
                .where(
                    or_(
                        booking.c.minimum_price.is_not(None),
                        booking.c.maximum_price.is_not(None),
                        booking.c.display_price.is_not(None),
                    )
                )
                .distinct()
                .limit(50)
            ).mappings().all()
            for row in rows:
                add(row.get("destination_id"), 2)
        except Exception:
            pass

    ranked = sorted(ordered, key=lambda item: (-scores.get(item, 0), ordered.index(item)))
    return ranked[: max(1, limit)]


def _parse_pk_text(table, value: object) -> dict[str, str]:
    """Parse postgres_loader's metadata entity_id back into PK columns."""
    raw = str(value or "").strip()
    if not raw:
        return {}
    parsed: dict[str, str] = {}
    for part in raw.split("|"):
        if "=" not in part:
            continue
        key, item = part.split("=", 1)
        key = key.strip()
        if key:
            parsed[key] = item.strip()

    pk_names = {column.name for column in table.primary_key.columns}
    if pk_names and pk_names.issubset(parsed):
        return {name: parsed[name] for name in pk_names}

    # Defensive compatibility for older/hand-built metadata where a single PK
    # may have been stored as the bare value rather than ``id=value``.
    if len(pk_names) == 1 and "=" not in raw:
        return {next(iter(pk_names)): raw}
    return {}


def _coerce_pk_value(column, value: str) -> Any:
    """Coerce metadata PK text back to the SQLAlchemy column's Python type."""
    try:
        python_type = column.type.python_type
    except (AttributeError, NotImplementedError):
        return value
    try:
        if python_type is int:
            return int(value)
        if python_type is float:
            return float(value)
        if python_type is Decimal:
            return Decimal(value)
        if python_type is str:
            return str(value)
        return python_type(value)
    except (TypeError, ValueError, ArithmeticError):
        return value


def _compact_record(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    """Return useful normalized fields without crawler-sized raw blobs."""
    if table_name == "booking_product":
        ordered = []
        seen: set[str] = set()
        for field in _BOOKING_PRIORITY_FIELDS:
            if field in row and row.get(field) is not None:
                ordered.append(field)
                seen.add(field)
        # Include additional normalized scalar fields after the priority set.
        for field, value in row.items():
            if field in seen or field in _NOISY_FIELDS or value is None:
                continue
            if isinstance(value, (dict, list, tuple)):
                continue
            ordered.append(field)
    else:
        ordered = [
            field
            for field, value in row.items()
            if field not in _NOISY_FIELDS and value is not None
        ]

    result: dict[str, Any] = {}
    for field in ordered:
        value = _json_safe(row.get(field))
        # Avoid duplicating giant curated text when the original chunk already
        # contains it. The important structured price/action fields remain.
        if field == "rag_content":
            continue
        result[field] = value
    return result


def _fetch_matched_rows(connection, documents: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Rehydrate every unique matched CORE row, grouped by table."""
    refs_by_table: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)
    for item in documents:
        metadata = item.get("metadata", {}) or {}
        table_name = str(metadata.get("entity_type") or metadata.get("source_table") or "").strip()
        table = CORE_TABLES.get(table_name)
        if table is None:
            continue
        entity_id = str(metadata.get("entity_id") or "").strip()
        pk = _parse_pk_text(table, entity_id)
        if not pk:
            continue
        refs_by_table[table_name].append((entity_id, pk))

    output: dict[tuple[str, str], dict[str, Any]] = {}
    for table_name, refs in refs_by_table.items():
        table = CORE_TABLES[table_name]
        # Small top-k means a few deterministic PK lookups are simpler and less
        # error-prone than building tuple-IN expressions across mixed PK types.
        seen_ids: set[str] = set()
        for entity_id, pk in refs:
            if entity_id in seen_ids:
                continue
            seen_ids.add(entity_id)
            conditions = [
                table.c[name] == _coerce_pk_value(table.c[name], value)
                for name, value in pk.items()
            ]
            row = connection.execute(
                select(table).where(and_(*conditions)).limit(1)
            ).mappings().first()
            if row:
                output[(table_name, entity_id)] = _compact_record(table_name, dict(row))
    return output


def _price_amount_from_room(row: dict[str, Any]) -> tuple[Decimal | None, str | None, str]:
    price = row.get("price_from_amount")
    currency = row.get("price_from_currency")
    source = "price_from"
    if price is None and not bool(row.get("is_rate_suspect")):
        price = row.get("rate_amount")
        currency = row.get("rate_currency")
        source = "standard_rate"
    return price, currency, source


def _room_price_rows(connection, destination_ids: list[str], per_destination: int = 3) -> list[dict[str, Any]]:
    room = CORE_TABLES.get("room")
    prop = CORE_TABLES.get("property")
    destination = CORE_TABLES.get("destination")
    if room is None or prop is None or not destination_ids:
        return []

    select_columns = [
        room.c.id.label("room_id"),
        room.c.name.label("room_name"),
        room.c.guest_count,
        room.c.price_from_amount,
        room.c.price_from_currency,
        room.c.price_is_approximate,
        room.c.price_observed_at,
        room.c.rate_amount,
        room.c.rate_currency,
        room.c.rate_raw,
        room.c.is_rate_suspect,
        room.c.page_url,
        prop.c.id.label("property_id"),
        prop.c.name.label("property_name"),
        prop.c.destination_id,
        prop.c.url.label("property_url"),
    ]
    from_clause = room.join(prop, room.c.property_id == prop.c.id)
    if destination is not None and hasattr(destination.c, "id"):
        from_clause = from_clause.join(destination, prop.c.destination_id == destination.c.id)
        if hasattr(destination.c, "name_vi"):
            select_columns.append(destination.c.name_vi.label("destination_name_vi"))
        if hasattr(destination.c, "name_en"):
            select_columns.append(destination.c.name_en.label("destination_name_en"))

    stmt = (
        select(*select_columns)
        .select_from(from_clause)
        .where(prop.c.destination_id.in_(destination_ids))
        .where(
            or_(
                room.c.price_from_amount.is_not(None),
                and_(room.c.rate_amount.is_not(None), room.c.is_rate_suspect.is_(False)),
            )
        )
    )
    rows = [dict(row) for row in connection.execute(stmt).mappings().all()]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        amount, currency, source = _price_amount_from_room(row)
        if amount is None:
            continue
        row["effective_price"] = amount
        row["effective_currency"] = currency
        row["effective_price_source"] = source
        grouped[str(row.get("destination_id") or "")].append(row)

    selected: list[dict[str, Any]] = []
    for destination_id in destination_ids:
        candidates = grouped.get(destination_id, [])
        candidates.sort(
            key=lambda item: (
                str(item.get("effective_currency") or ""),
                Decimal(str(item.get("effective_price") or 0)),
                str(item.get("property_name") or ""),
            )
        )
        selected.extend(candidates[: max(1, per_destination)])
    return selected


def _booking_price_rows(
    connection,
    destination_ids: list[str],
    per_destination: int = 5,
    *,
    catalog_query: str = "",
    hydrated_documents: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    booking = CORE_TABLES.get("booking_product")
    if booking is None or not destination_ids:
        return []

    scope = _resolve_booking_catalog_scope(
        connection,
        destination_ids,
        catalog_query,
        hydrated_documents or [],
    )

    stmt = (
        select(booking)
        .where(booking.c.destination_id.in_(destination_ids))
        .where(
            or_(
                booking.c.minimum_price.is_not(None),
                booking.c.maximum_price.is_not(None),
                booking.c.display_price.is_not(None),
            )
        )
    )
    booking_code = str(scope.get("booking_code") or "").strip()
    venue_name = str(scope.get("venue_name") or "").strip()
    if booking_code:
        stmt = stmt.where(booking.c.booking_code == booking_code)
    elif venue_name:
        stmt = stmt.where(booking.c.venue_name == venue_name)
    rows = [dict(row) for row in connection.execute(stmt).mappings().all()]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        # Sold-out rows can still be historically informative, but they are poor
        # defaults for an estimate when available rows exist. Rank them last.
        grouped[str(row.get("destination_id") or "")].append(row)

    selected: list[dict[str, Any]] = []
    for destination_id in destination_ids:
        candidates = grouped.get(destination_id, [])
        for item in candidates:
            labels = [
                item.get("product_name"), item.get("venue_name"),
                item.get("service_group"), item.get("product_type"),
                item.get("category"), item.get("booking_code"),
                item.get("ticket_code"),
            ]
            item["_catalog_scope_score"] = max(
                (_catalog_scope_score(catalog_query, str(value or "")) for value in labels),
                default=0.0,
            )
        candidates.sort(
            key=lambda item: (
                -float(item.get("_catalog_scope_score") or 0.0),
                bool(item.get("sold_out")),
                0 if item.get("minimum_price") is not None else 1,
                Decimal(str(item.get("minimum_price") or item.get("maximum_price") or 10**18)),
                str(item.get("product_name") or ""),
            )
        )

        # Keep price examples diverse so an aggregate-trip question sees more than
        # five nearly identical variants from one product family.
        limit = max(1, per_destination)
        picked: list[dict[str, Any]] = []
        seen_groups: set[str] = set()
        for row in candidates:
            group = str(row.get("service_group") or row.get("product_type") or row.get("category") or "").strip().casefold()
            if group and group in seen_groups:
                continue
            picked.append(row)
            if group:
                seen_groups.add(group)
            if len(picked) >= limit:
                break
        if len(picked) < limit:
            picked_ids = {id(row) for row in picked}
            for row in candidates:
                if id(row) in picked_ids:
                    continue
                picked.append(row)
                if len(picked) >= limit:
                    break
        for row in picked:
            row.pop("_catalog_scope_score", None)
        selected.extend(picked)
    return selected


def _structured_price_lanes(
    retrieval_intents: list[str] | None,
    *,
    cost_estimate_requested: bool,
) -> tuple[bool, bool]:
    """Return (include_rooms, include_booking_products) for a price request."""
    if cost_estimate_requested:
        return True, True
    intents = {
        str(value or "").strip().lower()
        for value in (retrieval_intents or [])
        if str(value or "").strip()
    }
    if not intents:
        return True, True
    return "hotel" in intents, bool(intents & {"booking_product", "attraction"})


def _token_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def _catalog_scope_score(query_text: str, label: str) -> float:
    """Generic fuzzy score for a user-described catalog scope.

    This intentionally scores semantic entity labels from PostgreSQL rather than
    relying on a hard-coded VinWonders/venue dictionary. Token coverage handles
    natural surrounding wording, while fuzzy token matching tolerates small
    spelling/plural differences such as ``vinwonder`` vs ``vinwonders``.
    """
    query = normalize_text(query_text)
    candidate = normalize_text(label)
    if not query or not candidate:
        return 0.0
    if candidate == query:
        return 1.0
    if re.search(rf"(?:^|\s){re.escape(candidate)}(?:$|\s)", query):
        return 0.98

    query_tokens = query.split()
    candidate_tokens = candidate.split()
    if not candidate_tokens:
        return 0.0

    best_matches: list[float] = []
    for token in candidate_tokens:
        best_matches.append(max((_token_similarity(token, other) for other in query_tokens), default=0.0))
    strong = [score for score in best_matches if score >= 0.82]
    candidate_coverage = len(strong) / len(candidate_tokens)
    fuzzy_coverage = sum(best_matches) / len(candidate_tokens)
    sequence = SequenceMatcher(None, candidate, query).ratio()
    return min(1.0, 0.62 * candidate_coverage + 0.23 * fuzzy_coverage + 0.15 * sequence)


def _resolve_booking_catalog_scope(
    connection,
    destination_ids: list[str],
    query_text: str,
    hydrated_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve an optional booking venue/site scope without hard-coded keys.

    The destination remains the safe outer boundary. Within it, canonical venue
    labels/booking codes are read from PostgreSQL and matched against the user's
    semantic query. Retrieved booking rows provide only a small evidence boost;
    they never invent a scope that does not exist in the canonical table.
    """
    booking = CORE_TABLES.get("booking_product")
    if booking is None or not destination_ids:
        return {"destination_ids": list(destination_ids), "scope_type": "destination"}

    try:
        rows = connection.execute(
            select(
                booking.c.booking_code,
                booking.c.destination_id,
                booking.c.destination_name,
                booking.c.venue_name,
            )
            .where(booking.c.destination_id.in_(destination_ids))
            .distinct()
        ).mappings().all()
    except Exception:
        rows = []

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in rows:
        destination_id = str(raw.get("destination_id") or "").strip()
        venue_name = str(raw.get("venue_name") or "").strip()
        destination_name = str(raw.get("destination_name") or "").strip()
        booking_code = str(raw.get("booking_code") or "").strip()
        key = (destination_id, venue_name.casefold(), booking_code.casefold())
        if key in seen:
            continue
        seen.add(key)
        labels = [value for value in (venue_name, destination_name) if value]
        score = max((_catalog_scope_score(query_text, value) for value in labels), default=0.0)
        candidates.append({
            "destination_id": destination_id,
            "venue_name": venue_name,
            "destination_name": destination_name,
            "booking_code": booking_code,
            "score": score,
        })

    # A canonical venue repeatedly present in already-retrieved booking evidence is
    # a useful tie-breaker, not an authoritative selector.
    evidence_counts: dict[tuple[str, str], int] = defaultdict(int)
    for item in hydrated_documents:
        metadata = item.get("metadata", {}) or {}
        if str(metadata.get("entity_type") or "") != "booking_product":
            continue
        record = item.get("structured_record", {}) or {}
        venue = str(record.get("venue_name") or "").strip().casefold()
        code = str(record.get("booking_code") or "").strip().casefold()
        if venue or code:
            evidence_counts[(venue, code)] += 1
    for item in candidates:
        key = (str(item.get("venue_name") or "").casefold(), str(item.get("booking_code") or "").casefold())
        item["score"] = min(1.0, float(item.get("score") or 0.0) + min(0.08, evidence_counts.get(key, 0) * 0.02))

    candidates.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    if not candidates:
        return {"destination_ids": list(destination_ids), "scope_type": "destination"}

    best = candidates[0]
    runner_up = float(candidates[1].get("score") or 0.0) if len(candidates) > 1 else 0.0
    best_score = float(best.get("score") or 0.0)
    # Require high canonical-label coverage and a useful margin. If the user only
    # named the city/destination, keep the broader destination scope instead of
    # guessing a venue.
    if best_score >= 0.74 and (best_score - runner_up >= 0.10 or best_score >= 0.94):
        return {
            "destination_ids": list(destination_ids),
            "scope_type": "booking_venue",
            "venue_name": best.get("venue_name"),
            "destination_name": best.get("destination_name"),
            "booking_code": best.get("booking_code"),
            "match_score": round(best_score, 4),
        }
    return {
        "destination_ids": list(destination_ids),
        "scope_type": "destination",
        "match_score": round(best_score, 4),
    }


def _booking_catalog_rows(connection, scope: dict[str, Any]) -> list[dict[str, Any]]:
    booking = CORE_TABLES.get("booking_product")
    destination_ids = [str(value).strip() for value in scope.get("destination_ids", []) if str(value).strip()]
    if booking is None or not destination_ids:
        return []

    stmt = select(booking).where(booking.c.destination_id.in_(destination_ids))
    booking_code = str(scope.get("booking_code") or "").strip()
    venue_name = str(scope.get("venue_name") or "").strip()
    if booking_code:
        stmt = stmt.where(booking.c.booking_code == booking_code)
    elif venue_name:
        stmt = stmt.where(booking.c.venue_name == venue_name)

    rows = [dict(row) for row in connection.execute(stmt).mappings().all()]
    rows.sort(key=lambda item: (
        bool(item.get("sold_out")),
        str(item.get("product_name") or "").casefold(),
        str(item.get("ticket_code") or "").casefold(),
    ))
    return rows


def _compact_catalog_variant(variant: dict[str, Any], target_currency: str) -> dict[str, Any]:
    price = variant.get("price") if isinstance(variant.get("price"), dict) else {}
    eligibility = variant.get("eligibility") if isinstance(variant.get("eligibility"), dict) else {}
    discount = variant.get("discount") if isinstance(variant.get("discount"), dict) else {}
    availability = variant.get("availability") if isinstance(variant.get("availability"), dict) else {}
    source_currency = _normalize_currency(price.get("currency"))
    amount = price.get("sale_price") if price.get("sale_price") is not None else price.get("amount")
    customer_display = _converted_money_display(amount, source_currency, target_currency) or _money_display(amount, source_currency)
    output = {
        "variant_name": variant.get("variant_name"),
        "guest_type": variant.get("guest_type"),
        "guest_label": variant.get("guest_label"),
        "source_amount": _json_safe(amount),
        "source_currency": source_currency,
        "customer_display": customer_display,
        "price_basis": price.get("price_basis"),
        "is_approximate": price.get("is_approximate"),
        "original_price": _json_safe(price.get("original_price")),
        "discount_percent": discount.get("discount_percent"),
        "discount_text": discount.get("discount_text"),
        "availability_status": availability.get("status"),
        "sold_out": availability.get("sold_out"),
    }
    eligibility_compact = {
        key: _json_safe(eligibility.get(key))
        for key in (
            "height_min_cm", "height_max_cm", "height_text",
            "age_min", "age_max", "age_text", "gender", "nationality",
            "membership_required", "membership_type",
        )
        if eligibility.get(key) is not None
    }
    if eligibility_compact:
        output["eligibility"] = eligibility_compact
    return {key: value for key, value in output.items() if value not in (None, "")}


def _compact_catalog_product(
    row: dict[str, Any],
    preferred_output_currency: str | None = None,
) -> dict[str, Any]:
    target_currency = _normalize_currency(preferred_output_currency) or "USD"
    raw_variants = row.get("price_variants")
    variants: list[dict[str, Any]] = []
    if isinstance(raw_variants, list):
        variants = [
            _compact_catalog_variant(item, target_currency)
            for item in raw_variants[:8]
            if isinstance(item, dict)
        ]

    source_currency = _normalize_currency(row.get("currency") or row.get("source_currency"))
    primary_amount = (
        row.get("minimum_price")
        if row.get("minimum_price") is not None
        else row.get("maximum_price")
    )
    customer_display = (
        _converted_money_display(primary_amount, source_currency, target_currency)
        or _money_display(primary_amount, source_currency)
        if primary_amount is not None
        else ""
    )
    minimum_display = (
        _converted_money_display(row.get("minimum_price"), source_currency, target_currency)
        or _money_display(row.get("minimum_price"), source_currency)
        if row.get("minimum_price") is not None
        else ""
    )
    maximum_display = (
        _converted_money_display(row.get("maximum_price"), source_currency, target_currency)
        or _money_display(row.get("maximum_price"), source_currency)
        if row.get("maximum_price") is not None
        else ""
    )

    output = {
        key: _json_safe(row.get(key))
        for key in (
            "id", "product_name", "ticket_code", "booking_code", "destination_id",
            "destination_name", "venue_name", "service_group", "product_type", "category",
            "currency", "pricing_status", "price_type", "is_from_price", "is_approximate_price",
            "display_price", "display_original_price", "display_discount_text",
            "minimum_price", "maximum_price", "availability_status", "availability_text",
            "sold_out", "booking_open", "source_url", "detail_url", "booking_url",
        )
        if row.get(key) is not None
    }
    output["preferred_output_currency"] = target_currency
    if customer_display:
        output["customer_display"] = customer_display
    if minimum_display:
        output["customer_minimum_display"] = minimum_display
    if maximum_display:
        output["customer_maximum_display"] = maximum_display
    if variants:
        output["price_variants"] = variants
    return output


def _build_booking_catalog_packet(
    rows: list[dict[str, Any]],
    scope: dict[str, Any],
    *,
    preferred_output_currency: str | None = None,
) -> dict[str, Any]:
    target_currency = _normalize_currency(preferred_output_currency) or "USD"
    products = [
        _compact_catalog_product(row, target_currency)
        for row in rows
    ]
    return {
        "task": "exhaustive_booking_catalog",
        "complete": bool(rows),
        "record_count": len(products),
        "scope": {key: value for key, value in scope.items() if value not in (None, "", [])},
        "price_data_as_of": PRICE_DATA_AS_OF,
        "preferred_output_currency": target_currency,
        "currency_conversion_guidance": currency_conversion_guidance(target_currency),
        "products": products,
    }


def _price_doc_from_room(row: dict[str, Any]) -> dict[str, Any]:
    amount = _json_safe(row.get("effective_price"))
    currency = str(row.get("effective_currency") or "").strip() or "unknown currency"
    destination_name = row.get("destination_name_vi") or row.get("destination_name_en") or row.get("destination_id")
    approximate = bool(row.get("price_is_approximate"))
    observed = _json_safe(row.get("price_observed_at"))
    text = (
        "Structured room price evidence\n"
        f"Property: {row.get('property_name')}\n"
        f"Room: {row.get('room_name')}\n"
        f"Destination: {destination_name}\n"
        f"Destination id: {row.get('destination_id')}\n"
        f"Price: {amount} {currency}\n"
        f"Price basis: per room/stay unit as stored by the source; use trip nights only when the user explicitly asks for a lodging estimate.\n"
        f"Approximate: {str(approximate).lower()}\n"
        f"Observed at: {observed or 'not recorded'}\n"
        f"Rate source: {row.get('effective_price_source')}\n"
        f"Rate suspect: {str(bool(row.get('is_rate_suspect'))).lower()}\n"
    )
    source_url = row.get("page_url") or row.get("property_url")
    row["destination_name"] = destination_name
    return {
        "id": f"structured-price:room:{row.get('room_id')}",
        "text": text,
        "score": 0.99,
        "semantic_score": 0.0,
        "keyword_score": 1.0,
        "retrieval_mode": "post_retrieval_structured_price",
        "matched_intent": "hotel",
        "matched_destination_id": row.get("destination_id"),
        "metadata": {
            "entity_type": "room",
            "entity_id": f"id={row.get('room_id')}",
            "entity_name": f"{row.get('property_name')} — {row.get('room_name')}",
            "destination_id": row.get("destination_id"),
            "destination_name": destination_name,
            "property_id": row.get("property_id"),
            "source_url": source_url,
            "currency": currency,
            "structured_price_support": True,
        },
        "structured_record": {
            key: _json_safe(value)
            for key, value in row.items()
            if value is not None
        },
    }


def _price_doc_from_booking(row: dict[str, Any]) -> dict[str, Any]:
    variants = _json_safe(row.get("price_variants"))
    if isinstance(variants, list):
        variants = variants[:6]
    variants_text = json.dumps(variants, ensure_ascii=False, default=str)
    if len(variants_text) > 1800:
        variants_text = variants_text[:1800] + "…"
    compact = {
        key: _json_safe(row.get(key))
        for key in (
            "id", "product_name", "ticket_code", "booking_code", "destination_id", "destination_name",
            "venue_name", "service_group", "product_type", "category",
            "currency", "pricing_status", "price_type", "is_from_price",
            "is_approximate_price", "display_price", "display_original_price",
            "display_discount_text", "minimum_price", "maximum_price",
            "is_promotional", "promotion_name", "promotion_code",
            "discount_percent", "availability_status", "availability_text",
            "sold_out", "booking_open", "source_url", "detail_url", "booking_url",
        )
        if row.get(key) is not None
    }
    if variants is not None:
        compact["price_variants"] = variants
    text = (
        "Structured booking-product price evidence\n"
        f"Product: {row.get('product_name')}\n"
        f"Destination: {row.get('destination_name') or row.get('destination_id')}\n"
        f"Venue/service group: {row.get('venue_name') or row.get('service_group')}\n"
        f"Currency: {row.get('currency') or row.get('source_currency')}\n"
        f"Display price: {row.get('display_price')}\n"
        f"Minimum price: {_json_safe(row.get('minimum_price'))}\n"
        f"Maximum price: {_json_safe(row.get('maximum_price'))}\n"
        f"Price type: {row.get('price_type')}\n"
        f"Approximate/from price: {str(bool(row.get('is_approximate_price') or row.get('is_from_price'))).lower()}\n"
        f"Availability: {row.get('availability_status') or row.get('availability_text')}\n"
        f"Price variants: {variants_text}\n"
    )
    return {
        "id": f"structured-price:booking_product:{row.get('id')}",
        "text": text,
        "score": 0.99,
        "semantic_score": 0.0,
        "keyword_score": 1.0,
        "retrieval_mode": "post_retrieval_structured_price",
        "matched_intent": "service",
        "matched_destination_id": row.get("destination_id"),
        "metadata": {
            "entity_type": "booking_product",
            "entity_id": f"id={row.get('id')}",
            "entity_name": row.get("product_name"),
            "destination_id": row.get("destination_id"),
            "source_url": row.get("source_url") or row.get("detail_url") or row.get("booking_url"),
            "currency": row.get("currency") or row.get("source_currency"),
            "product_type": row.get("product_type"),
            "structured_price_support": True,
        },
        "structured_record": compact,
    }


def _dedupe_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in documents:
        metadata = item.get("metadata", {}) or {}
        key = (
            str(metadata.get("entity_type") or ""),
            str(metadata.get("entity_id") or metadata.get("entity_name") or item.get("id") or ""),
        )
        if key in seen:
            # If the semantic chunk already exists, retain it but merge the richer
            # structured record from the deterministic lookup when available.
            if item.get("structured_record"):
                for existing in output:
                    existing_meta = existing.get("metadata", {}) or {}
                    existing_key = (
                        str(existing_meta.get("entity_type") or ""),
                        str(existing_meta.get("entity_id") or existing_meta.get("entity_name") or existing.get("id") or ""),
                    )
                    if existing_key == key and not existing.get("structured_record"):
                        existing["structured_record"] = item.get("structured_record")
                        break
            continue
        seen.add(key)
        output.append(item)
    return output



def _destination_name_from_record(metadata: dict[str, Any], record: dict[str, Any]) -> str:
    return str(
        record.get("destination_name")
        or record.get("destination_name_vi")
        or record.get("destination_name_en")
        or metadata.get("destination_name")
        or record.get("destination_name")
        or metadata.get("destination_id")
        or record.get("destination_id")
        or "unknown destination"
    ).strip()


def _price_value_for_record(entity_type: str, record: dict[str, Any]) -> tuple[Any, str | None]:
    if entity_type == "room":
        return record.get("effective_price"), record.get("effective_currency")
    return (
        record.get("minimum_price")
        or record.get("display_price")
        or record.get("maximum_price"),
        record.get("currency") or record.get("source_currency"),
    )


def _build_price_estimate_packet(
    documents: list[dict[str, Any]],
    *,
    preferred_output_currency: str | None = None,
    max_destinations: int = 3,
) -> dict[str, Any]:
    """Group deterministic price rows by destination for the final answer LLM.

    The answerer should reason from this packet instead of scanning long raw
    chunks. We keep both source currency and converted presentation amounts so
    the LLM does not need to invent exchange rates.
    """
    target_currency = _normalize_currency(preferred_output_currency) or "USD"
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for item in documents:
        metadata = item.get("metadata", {}) or {}
        if not metadata.get("structured_price_support"):
            continue
        record = item.get("structured_record", {}) or {}
        entity_type = str(metadata.get("entity_type") or "")
        destination_id = str(
            metadata.get("destination_id")
            or record.get("destination_id")
            or item.get("matched_destination_id")
            or ""
        ).strip()
        if not destination_id:
            continue
        if destination_id not in grouped:
            grouped[destination_id] = {
                "destination_id": destination_id,
                "destination_name": _destination_name_from_record(metadata, record),
                "lodging_options": [],
                "booking_service_options": [],
            }
            order.append(destination_id)
        amount, currency = _price_value_for_record(entity_type, record)
        source_currency = _normalize_currency(currency)
        converted_display = _converted_money_display(amount, source_currency, target_currency)
        customer_display = converted_display or _money_display(amount, source_currency)
        common = {
            "source_amount": _json_safe(amount),
            "source_currency": source_currency,
            "preferred_output_currency": target_currency,
            "customer_display": customer_display,
            "converted_display": converted_display,
            "price_basis_note": "Use source basis exactly; for room evidence, multiply by requested nights only as an estimate assumption. In the customer-facing answer, show money in preferred_output_currency only.",
        }
        if entity_type == "room":
            grouped[destination_id]["lodging_options"].append(
                {
                    **common,
                    "property_name": record.get("property_name"),
                    "room_name": record.get("room_name"),
                    "guest_count": record.get("guest_count"),
                    "approximate": bool(record.get("price_is_approximate")),
                    "observed_at": record.get("price_observed_at"),
                    "source_url": metadata.get("source_url") or record.get("page_url") or record.get("property_url"),
                }
            )
        elif entity_type == "booking_product":
            grouped[destination_id]["booking_service_options"].append(
                {
                    **common,
                    "product_name": record.get("product_name"),
                    "service_group": record.get("service_group") or record.get("product_type") or record.get("category"),
                    "display_price": record.get("display_price"),
                    "minimum_price": record.get("minimum_price"),
                    "maximum_price": record.get("maximum_price"),
                    "price_type": record.get("price_type"),
                    "availability_status": record.get("availability_status") or record.get("availability_text"),
                    "source_url": metadata.get("source_url") or record.get("source_url") or record.get("booking_url"),
                }
            )

    destinations = []
    for destination_id in order:
        item = grouped[destination_id]
        if not item["lodging_options"] and not item["booking_service_options"]:
            continue
        item["lodging_options"] = item["lodging_options"][:3]
        item["booking_service_options"] = item["booking_service_options"][:5]
        destinations.append(item)
        if len(destinations) >= max(1, max_destinations):
            break

    return {
        "task": "cost_estimate" if destinations else "price_lookup",
        "price_data_as_of": PRICE_DATA_AS_OF,
        "preferred_output_currency": target_currency,
        "currency_conversion_guidance": currency_conversion_guidance(target_currency),
        "destination_count": len(destinations),
        "destinations": destinations,
    }


def _price_summary(documents: list[dict[str, Any]], max_lines: int = 10, preferred_output_currency: str | None = None) -> str:
    lines: list[str] = []
    target = _normalize_currency(preferred_output_currency) or "USD"
    for item in documents:
        metadata = item.get("metadata", {}) or {}
        if not metadata.get("structured_price_support"):
            continue
        record = item.get("structured_record", {}) or {}
        entity_type = str(metadata.get("entity_type") or "")
        destination_name = _destination_name_from_record(metadata, record)
        amount, currency = _price_value_for_record(entity_type, record)
        source_currency = _normalize_currency(currency)
        converted = _converted_money_display(amount, source_currency, target)
        display = converted or _money_display(amount, source_currency)
        if entity_type == "room":
            lines.append(
                f"- lodging | {destination_name} | {record.get('property_name')} | {record.get('room_name')} | {display}"
            )
        elif entity_type == "booking_product":
            lines.append(
                f"- booking/service | {destination_name} | {record.get('product_name')} | {display}".rstrip()
            )
        if len(lines) >= max_lines:
            break
    return "\n".join(lines)


def enrich_retrieved_documents(
    documents: list[dict[str, Any]],
    *,
    destination_ids: list[str] | None = None,
    price_requested: bool = False,
    cost_estimate_requested: bool = False,
    retrieval_intents: list[str] | None = None,
    exhaustive_booking_requested: bool = False,
    catalog_query: str = "",
    preferred_output_currency: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Hydrate matched rows and optionally supplement structured price evidence.

    Failure is deliberately non-fatal: semantic retrieval already produced a valid
    evidence set, so a transient PostgreSQL enrichment problem must not erase it.
    """
    base_documents = [dict(item) for item in (documents or [])]
    destination_ids = [str(value).strip() for value in (destination_ids or []) if str(value).strip()]
    preferred_output_currency = _normalize_currency(preferred_output_currency) or "USD"
    diagnostics: dict[str, Any] = {
        "structured_enrichment_count": 0,
        "structured_price_document_count": 0,
        "price_data_as_of": PRICE_DATA_AS_OF if price_requested else None,
        "price_evidence_summary": "",
        "price_estimate_packet": {},
        "price_estimate_destination_ids": [],
        "exhaustive_catalog_requested": bool(exhaustive_booking_requested),
        "exhaustive_catalog_complete": False,
        "exhaustive_catalog_count": 0,
        "exhaustive_catalog_scope": {},
        "exhaustive_catalog_packet": {},
        "preferred_output_currency": preferred_output_currency,
        "currency_conversion_guidance": currency_conversion_guidance(preferred_output_currency),
    }
    if not base_documents and not price_requested:
        return base_documents, diagnostics

    engine = get_engine()
    try:
        with engine.connect() as connection:
            hydrated = _fetch_matched_rows(connection, base_documents)
            for item in base_documents:
                metadata = item.get("metadata", {}) or {}
                key = (
                    str(metadata.get("entity_type") or metadata.get("source_table") or "").strip(),
                    str(metadata.get("entity_id") or "").strip(),
                )
                record = hydrated.get(key)
                if record:
                    item["structured_record"] = record
                    diagnostics["structured_enrichment_count"] += 1

            price_documents: list[dict[str, Any]] = []
            price_destination_ids = list(destination_ids)
            if price_requested and cost_estimate_requested and not price_destination_ids:
                # Open-ended estimates ("a Vinpearl destination", "here" without
                # page context, etc.) still need places. Prefer destinations already
                # present in semantic results; otherwise ask PostgreSQL for a few
                # destinations that have both lodging/booking price evidence.
                price_destination_ids = _candidate_destination_ids_for_cost_estimate(
                    connection, base_documents, limit=3
                )
            elif price_requested and not price_destination_ids:
                price_destination_ids = _extract_destination_ids_from_documents(base_documents, limit=3)

            if price_requested and price_destination_ids:
                if exhaustive_booking_requested:
                    # Exhaustive listing is a structured enumeration contract, not
                    # a top-k sampling problem. Resolve the narrowest canonical
                    # booking scope that the user's wording supports, then return
                    # every row in that scope. Do not mix unrelated room samples
                    # into a ticket/package catalog request.
                    catalog_scope = _resolve_booking_catalog_scope(
                        connection,
                        price_destination_ids,
                        catalog_query,
                        base_documents,
                    )
                    catalog_rows = _booking_catalog_rows(connection, catalog_scope)
                    catalog_packet = _build_booking_catalog_packet(
                        catalog_rows,
                        catalog_scope,
                        preferred_output_currency=preferred_output_currency,
                    )
                    diagnostics["exhaustive_catalog_scope"] = catalog_scope
                    diagnostics["exhaustive_catalog_packet"] = catalog_packet
                    diagnostics["exhaustive_catalog_count"] = len(catalog_rows)
                    diagnostics["exhaustive_catalog_complete"] = bool(catalog_rows)
                    for row in catalog_rows:
                        doc = _price_doc_from_booking(row)
                        doc["retrieval_mode"] = "post_retrieval_exhaustive_catalog"
                        doc["metadata"]["exhaustive_catalog_support"] = True
                        price_documents.append(doc)
                else:
                    # Cost-estimate questions need enough examples to construct a
                    # practical breakdown. Single-item price questions still receive a
                    # small grounded price lane, but with fewer rows.
                    room_limit = 3 if cost_estimate_requested else 2
                    booking_limit = 5 if cost_estimate_requested else 3
                    include_rooms, include_booking = _structured_price_lanes(
                        retrieval_intents,
                        cost_estimate_requested=cost_estimate_requested,
                    )
                    if include_rooms:
                        for row in _room_price_rows(connection, price_destination_ids, per_destination=room_limit):
                            price_documents.append(_price_doc_from_room(row))
                    if include_booking:
                        for row in _booking_price_rows(
                            connection,
                            price_destination_ids,
                            per_destination=booking_limit,
                            catalog_query=catalog_query,
                            hydrated_documents=base_documents,
                        ):
                            price_documents.append(_price_doc_from_booking(row))

            # If the requested output language/currency is VND, enrich summaries
            # with deterministic converted display values so the final LLM never has
            # to invent an exchange rate from memory.
            names = _destination_names(connection, price_destination_ids)
            for item in price_documents:
                metadata = item.get("metadata", {}) or {}
                record = item.get("structured_record", {}) or {}
                destination_id = str(metadata.get("destination_id") or record.get("destination_id") or "").strip()
                if destination_id and names.get(destination_id):
                    metadata.setdefault("destination_name", names[destination_id])
                    record.setdefault("destination_name", names[destination_id])
                    item["metadata"] = metadata
                    item["structured_record"] = record

            merged = _dedupe_documents(price_documents + base_documents)
            diagnostics["structured_price_document_count"] = sum(
                1
                for item in merged
                if (item.get("metadata", {}) or {}).get("structured_price_support")
            )
            diagnostics["price_evidence_summary"] = _price_summary(
                merged, preferred_output_currency=preferred_output_currency
            )
            packet = _build_price_estimate_packet(
                merged, preferred_output_currency=preferred_output_currency
            )
            diagnostics["price_estimate_packet"] = packet
            diagnostics["price_estimate_destination_ids"] = [
                str(item.get("destination_id") or "")
                for item in packet.get("destinations", [])
                if str(item.get("destination_id") or "").strip()
            ]
            return merged, diagnostics
    except Exception as exc:
        print(
            "[POST-RETRIEVAL ENRICHMENT] fallback to semantic chunks because of "
            f"{type(exc).__name__}: {exc}"
        )
        return base_documents, diagnostics
