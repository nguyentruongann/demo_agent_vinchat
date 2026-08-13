"""data/promotion/*.json (9 file) → promotion và 10 bảng con.

Khử trùng theo ``promotion_id``: 124 dòng trong 9 file gộp lại còn 38 thực thể.
Đã so từng cặp bản sao — 49 cặp lệch nhau và **lệch duy nhất ở trường
``destinations``** — nên quy tắc là lấy bản đầu tiên, hợp danh sách địa danh.

KHÔNG parse ``status_reason``: data đã có sẵn 5 object khoảng thời gian đã tách.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

from src.data_postgre.normalize.common import (
    normalize_language,
    parse_int,
    parse_iso_date,
    stable_id,
)
from src.data_postgre.normalize.context import BRANDS, Context
from src.data_postgre.normalize.text import clean_text

GLOB = "data/promotion/*.json"

# Nam cap cot ngay, anh xa thang tu 5 object co san trong nguon.
PERIODS = {
    "booking": "booking_period",
    "stay": "stay_period",
    "validity": "general_validity",
    "purchase": "purchase_period",
    "redemption": "redemption_period",
}

TAG_FIELDS = {
    "promotion_type": "promotion_type",
    "applicable_services": "service",
    "channels": "channel",
    "customer_groups": "customer_group",
    "member_tiers": "member_tier",
}

TERM_FIELDS = {
    "terms_and_conditions": "term",
    "combination_rules": "combination",
    "contact_information": "contact",
    "redemption_steps": "step",
}


def _date_confidence(promo: dict[str, Any]) -> str:
    found = sum(
        1
        for source_key in PERIODS.values()
        if (promo.get(source_key) or {}).get("start_date")
        or (promo.get(source_key) or {}).get("end_date")
    )
    if found == 0:
        return "unknown"
    return "parsed" if found >= 2 else "partial"


def parse(ctx: Context) -> None:
    merged: dict[str, dict[str, Any]] = {}
    destinations: dict[str, set[str]] = {}

    for file_path in sorted(glob.glob(GLOB)):
        ctx.source_file = file_path
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        for promo in payload.get("promotions") or []:
            pid = promo["promotion_id"]
            merged.setdefault(pid, promo)
            destinations.setdefault(pid, set()).update(promo.get("destinations") or [])

    ctx.source_file = GLOB
    for pid, promo in merged.items():
        _one(ctx, pid, promo, destinations[pid])


def _one(ctx: Context, pid: str, promo: dict[str, Any], dests: set[str]) -> None:
    source_id = ctx.source(
        promo.get("primary_source_url"),
        canonical=promo.get("canonical_url"),
        crawled_at=promo.get("crawled_at"),
        content_hash=promo.get("content_hash"),
    )

    row: dict[str, Any] = {
        "id": pid,
        "slug": clean_text(promo.get("slug")),
        "title": clean_text(promo.get("title")) or pid,
        "summary": clean_text(promo.get("summary")),
        "is_nationwide": any(ctx.is_nationwide(d) for d in dests),
        "excluded_dates": promo.get("excluded_dates") or None,
        "recurring_schedule": clean_text(promo.get("recurring_schedule")),
        "date_confidence": _date_confidence(promo),
        "status_at_crawl": clean_text(promo.get("promotion_status")),
        "status_reason_raw": clean_text(promo.get("status_reason")),
        "status_calculated_at": promo.get("status_calculated_at"),
        "quality_score": promo.get("quality_score"),
        "needs_review": promo.get("needs_review"),
        "brand_id": promo.get("source_brand") if promo.get("source_brand") in BRANDS else None,
        "booking_url": clean_text(promo.get("booking_url")),
        "app_url": clean_text(promo.get("app_url")),
        "terms_url": clean_text(promo.get("terms_url")),
        "content_language": normalize_language(promo.get("language")),
        "discount_text": clean_text(promo.get("discount_text")),
        "full_text": clean_text(promo.get("full_text")),
        "word_count": parse_int(promo.get("word_count")),
        "crawl_method": clean_text(promo.get("crawl_method")),
        "published_at": promo.get("published_at"),
        "source_updated_at": promo.get("updated_at"),
        "tags": build_tags(promo),
        "source_id": source_id,
    }
    for prefix, source_key in PERIODS.items():
        period = promo.get(source_key) or {}
        row[f"{prefix}_from"] = parse_iso_date(period.get("start_date"))
        row[f"{prefix}_to"] = parse_iso_date(period.get("end_date"))
        row[f"{prefix}_raw"] = clean_text(period.get("raw_text"))
    ctx.rows.add("promotion", row)

    _destinations(ctx, pid, dests)
    _benefits(ctx, pid, promo)
    _codes(ctx, pid, promo)
    _sections(ctx, pid, promo)
    _blocks(ctx, pid, promo)
    _steps_and_terms(ctx, pid, promo)
    _relations(ctx, pid, promo)
    _applicable_properties(ctx, pid, promo)

    for order, url in enumerate(promo.get("image_urls") or []):
        ctx.media("promotion", pid, url, sort_order=order)
    for url in promo.get("source_urls") or []:
        extra = ctx.source(url)
        if extra and extra != source_id:
            ctx.rows.add("entity_source", {
                "entity_type": "promotion", "entity_id": pid,
                "source_id": extra, "role": "secondary",
            })
    for note in promo.get("review_notes") or []:
        ctx.issue("info", "promotion.review_note", entity_type="promotion",
                  entity_id=pid, raw_value=note)


def _destinations(ctx: Context, pid: str, dests: set[str]) -> None:
    for raw in sorted(dests):
        if ctx.is_nationwide(raw):
            continue
        dest_id = ctx.destination(raw, json_path="promotions[].destinations[]",
                                  entity_type="promotion")
        if dest_id:
            ctx.rows.add("promotion_destination",
                         {"promotion_id": pid, "destination_id": dest_id})


def _benefits(ctx: Context, pid: str, promo: dict[str, Any]) -> None:
    valid_units = {"percent", "VND", "times"}
    for order, benefit in enumerate(promo.get("benefits") or []):
        kind = clean_text(benefit.get("benefit_type"))
        if not kind:
            continue
        unit = clean_text(benefit.get("unit"))
        if unit and unit not in valid_units:
            ctx.issue("warning", "benefit.unknown_unit", entity_type="promotion_benefit",
                      entity_id=pid, raw_value=unit)
            unit = None
        if unit is None and benefit.get("value") is not None:
            # 20/310 dong thieu don vi. KHONG duoc mac dinh thanh 'percent'.
            ctx.issue("info", "benefit.missing_unit", entity_type="promotion_benefit",
                      entity_id=pid, raw_value=benefit.get("source_text"))
        ctx.rows.add("promotion_benefit", {
            "id": stable_id("promotion_benefit", pid, order),
            "promotion_id": pid,
            "benefit_type": kind,
            "value": benefit.get("value"),
            "unit": unit,
            "is_maximum": benefit.get("maximum"),
            "description": clean_text(benefit.get("description")),
            "source_text": clean_text(benefit.get("source_text")),
            "sort_order": order,
        })


def build_tags(promo: dict[str, Any]) -> dict[str, list[str]] | None:
    """Gộp 5 chiều phân loại thành một JSONB {chiều: [giá trị]}.

    Khoá chỉ lấy từ TAG_FIELDS — đây là chốt chặn thay cho CHECK constraint đã
    mất khi bảng promotion_tag gộp vào cột. Chiều nào rỗng thì không có khoá,
    để ``tags ? 'member_tier'`` phân biệt được "không có" với "rỗng".
    """
    tags: dict[str, list[str]] = {}
    for field_name, tag_type in TAG_FIELDS.items():
        values = [
            v for v in (clean_text(x) for x in promo.get(field_name) or []) if v
        ]
        if values:
            tags.setdefault(tag_type, []).extend(values)
    return {k: list(dict.fromkeys(v)) for k, v in tags.items()} or None


def _codes(ctx: Context, pid: str, promo: dict[str, Any]) -> None:
    for order, code in enumerate(promo.get("promo_codes") or []):
        value = clean_text(code.get("code"))
        if not value:
            continue
        ctx.rows.add("promotion_code", {
            "id": stable_id("promotion_code", pid, value, order),
            "promotion_id": pid,
            "code": value,
            "description": clean_text(code.get("description")),
            "validity": clean_text(code.get("validity")),
            "source_text": clean_text(code.get("source_text")),
            "conditions": code.get("conditions") or None,
            "is_suspect": value.upper() == "NONE",
        })


def _sections(ctx: Context, pid: str, promo: dict[str, Any]) -> None:
    for order, section in enumerate(promo.get("sections") or []):
        body = " ".join(clean_text(x) or "" for x in section.get("content") or [])
        ctx.rows.add("promotion_section", {
            "id": stable_id("promotion_section", pid, order),
            "promotion_id": pid,
            "ord": order,
            "heading": clean_text(section.get("heading")),
            "level": parse_int(section.get("level")),
            "content": clean_text(body),
        })


def _blocks(ctx: Context, pid: str, promo: dict[str, Any]) -> None:
    order = 0
    def block(block_type: str, ord_: int, **kw) -> None:
        ctx.rows.add("promotion_block", {
            "id": stable_id("promotion_block", pid, ord_),
            "promotion_id": pid, "ord": ord_, "block_type": block_type, **kw,
        })

    for table in promo.get("tables") or []:
        block("table", order, caption=clean_text(table.get("caption")),
              payload={"headers": table.get("headers") or [],
                       "rows": table.get("rows") or []})
        order += 1
    for bullet in promo.get("bullet_lists") or []:
        # 'list' chứ không phải 'bullet_list' như bản đầu: cùng từ vựng với
        # policy_block để hai bảng đọc như nhau dù không gộp.
        block("list", order, caption=None,
              payload={"type": bullet.get("type"),
                       "items": bullet.get("items") or []})
        order += 1
    for heading in promo.get("headings") or []:
        block("heading", order, caption=None,
              payload={"level": heading.get("level"),
                       "text": heading.get("text")})
        order += 1


def _steps_and_terms(ctx: Context, pid: str, promo: dict[str, Any]) -> None:
    """Bốn mảng văn bản có thứ tự, cùng vào promotion_term.

    ``ord`` đếm riêng trong từng ``kind`` — "bước 3 của quy trình đổi thưởng"
    độc lập với "điều khoản thứ 3".
    """
    for field_name, kind in TERM_FIELDS.items():
        for order, value in enumerate(promo.get(field_name) or []):
            text = clean_text(value)
            if text:
                ctx.rows.add("promotion_term", {
                    "id": stable_id("promotion_term", pid, kind, order),
                    "promotion_id": pid, "kind": kind, "ord": order, "text": text,
                })


def _relations(ctx: Context, pid: str, promo: dict[str, Any]) -> None:
    pairs = [
        ("related_promotions", "related_promotion"),
        ("related_articles", "related_article"),
    ]
    for field_name, kind in pairs:
        for url in promo.get(field_name) or []:
            text = clean_text(url)
            if not text:
                continue
            ctx.rows.add("promotion_relation", {
                "id": stable_id("promotion_relation", pid, kind, text),
                "promotion_id": pid, "kind": kind, "target_url": text,
                "target_promotion_id": None, "target_brand_id": None,
            })
    for brand in promo.get("related_brands") or []:
        text = clean_text(brand)
        if text in BRANDS:
            ctx.rows.add("promotion_relation", {
                "id": stable_id("promotion_relation", pid, "brand", text),
                "promotion_id": pid, "kind": "related_brand", "target_url": None,
                "target_promotion_id": None, "target_brand_id": text,
            })


def _applicable_properties(ctx: Context, pid: str, promo: dict[str, Any]) -> None:
    """327 giá trị nguồn, phần lớn là chuỗi cụt do lỗi parse.

    Cố ý KHÔNG ép khoá ngoại vào ``property``; để riêng bảng kiểm dịch rồi khớp
    mờ bằng pg_trgm sau.
    """
    for value in promo.get("applicable_properties") or []:
        text = clean_text(value)
        if text:
            ctx.rows.add("promotion_property_raw", {
                "id": stable_id("promotion_property_raw", pid, text),
                "promotion_id": pid, "raw_value": text,
                "matched_property_id": None, "match_score": None,
            })