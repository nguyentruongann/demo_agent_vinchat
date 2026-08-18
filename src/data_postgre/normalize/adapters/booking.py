"""data/booking/*.json -> core.booking_product.

Nhánh booking cố ý denormalized: MỘT dòng PostgreSQL chứa đủ thông tin cần cho
agent/RAG, không tạo bảng con cho price variant/policy/condition và cũng không
phụ thuộc destination/source. Các object/list giàu cấu trúc giữ bằng JSONB;
``rag_content`` là bản text dễ chunk ở bước ingest vector sau này.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

from src.data_postgre.normalize.common import parse_int, stable_id
from src.data_postgre.normalize.context import Context
from src.data_postgre.normalize.text import clean_text

GLOB = "data/booking/*.json"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact_json(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        items = [clean_text(item) for item in value]
        return " | ".join(item for item in items if item) or None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _variant_text(variants: list[Any]) -> str | None:
    """Đổi price variants thành text giàu ngữ nghĩa cho chunk/RAG."""
    lines: list[str] = []
    for raw in variants:
        variant = _dict(raw)
        if not variant:
            continue
        eligibility = _dict(variant.get("eligibility"))
        price = _dict(variant.get("price"))
        discount = _dict(variant.get("discount"))
        availability = _dict(variant.get("availability"))

        parts = [
            clean_text(variant.get("variant_name")) or clean_text(variant.get("guest_label")),
            f"guest_type={variant.get('guest_type')}" if variant.get("guest_type") else None,
            f"eligibility={_compact_json(eligibility)}" if eligibility else None,
            f"price={price.get('display_price') or price.get('amount')}"
            if price.get("display_price") is not None or price.get("amount") is not None
            else None,
            f"currency={price.get('currency')}" if price.get("currency") else None,
            f"original_price={price.get('original_price')}"
            if price.get("original_price") is not None
            else None,
            f"discount={discount.get('discount_text') or discount.get('discount_percent')}"
            if discount.get("discount_text") or discount.get("discount_percent") is not None
            else None,
            f"availability={availability.get('status')}" if availability.get("status") else None,
            f"available_quantity={availability.get('available_quantity')}"
            if availability.get("available_quantity") is not None
            else None,
        ]
        text = "; ".join(str(part) for part in parts if part not in (None, ""))
        if text:
            lines.append(text)
    return "\n".join(f"- {line}" for line in lines) or None


def _rag_content(site: dict[str, Any], product: dict[str, Any]) -> str:
    source = _dict(site.get("source"))
    destination = _dict(site.get("destination"))
    card = _dict(product.get("card"))
    details = _dict(product.get("details"))
    pricing = _dict(product.get("pricing"))
    promotion = _dict(product.get("promotion"))
    conditions = _dict(product.get("customer_conditions"))
    usage = _dict(product.get("usage"))
    availability = _dict(product.get("availability"))
    booking = _dict(product.get("booking"))
    policies = _dict(product.get("policies"))

    sections: list[tuple[str, Any]] = [
        ("Product name", product.get("product_name")),
        ("Normalized product name", product.get("normalized_product_name")),
        ("Ticket code", product.get("ticket_code") or booking.get("ticket_code")),
        ("Booking code", booking.get("booking_code") or source.get("booking_code")),
        ("Provider", source.get("provider")),
        ("Destination", destination.get("destination_name")),
        ("City", destination.get("city")),
        ("Province", destination.get("province")),
        ("Country", destination.get("country")),
        ("Venue", destination.get("venue_name")),
        ("Service group", destination.get("service_group")),
        ("Product type", product.get("product_type")),
        ("Category", product.get("category")),
        ("Sub category", product.get("sub_category")),
        ("Status", product.get("status")),
        ("Short description", card.get("short_description")),
        ("Overview", details.get("overview")),
        ("Highlights", card.get("highlights")),
        ("Experience", details.get("experience_description")),
        ("Currency", pricing.get("currency")),
        ("Display price", pricing.get("display_price") or card.get("display_price_text")),
        ("Minimum price", pricing.get("minimum_price")),
        ("Maximum price", pricing.get("maximum_price")),
        ("Price type", pricing.get("price_type")),
        ("Pricing status", pricing.get("pricing_status")),
        ("Price variants", _variant_text(_list(pricing.get("variants")))),
        ("Promotion", promotion),
        ("Inclusions", product.get("inclusions") or details.get("included")),
        ("Exclusions", product.get("exclusions") or details.get("excluded")),
        ("Benefits", details.get("benefits")),
        ("Customer conditions", conditions),
        ("Quantity rules", product.get("quantity_rules")),
        ("Validity", usage.get("validity_text")),
        ("Duration", usage.get("duration")),
        ("Usage type", usage.get("usage_type")),
        ("Time slot", usage.get("time_slot") or usage.get("entry_time")),
        ("Usage instructions", details.get("usage_instructions")),
        ("Availability", availability),
        ("Important notes", details.get("important_notes")),
        ("Restrictions", details.get("restrictions")),
        ("Terms and conditions", details.get("terms_and_conditions")),
        ("Policies", policies),
        ("Surcharges", product.get("surcharges") or details.get("surcharge_conditions")),
        ("Transportation", product.get("transportation")),
        ("Food and beverage", product.get("food_and_beverage")),
        ("Spa and wellness", product.get("spa_and_wellness")),
        ("Service locations", details.get("service_locations")),
        ("Operating information", details.get("operating_information")),
        ("Booking URL", booking.get("booking_url") or booking.get("search_url")),
    ]

    lines: list[str] = []
    for label, value in sections:
        rendered = _compact_json(value)
        if rendered:
            lines.append(f"{label}: {rendered}")
    return "\n".join(lines)


def parse(ctx: Context) -> None:
    for file_path in sorted(glob.glob(GLOB)):
        ctx.source_file = file_path
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        sites = payload.get("sites") or []

        for site_index, raw_site in enumerate(sites):
            site = _dict(raw_site)
            source = _dict(site.get("source"))
            destination = _dict(site.get("destination"))
            provider = clean_text(source.get("provider")) or "VinWonders"

            # Resolve canonical destination từ city của TỪNG site. Điều này quan
            # trọng với others.json vì file đó chứa nhiều site/địa điểm khác nhau.
            # Không hard-code theo tên file/venue: aliases trong destinations.yaml
            # là source of truth (Ha Noi -> ha-noi, Nha Trang -> nha-trang, ...).
            city = clean_text(destination.get("city"))
            destination_id = ctx.destination(
                city,
                json_path=f"sites[{site_index}].destination.city",
                entity_type="booking_product",
            )

            for product_index, raw_product in enumerate(site.get("products") or []):
                product = _dict(raw_product)
                product_id = clean_text(product.get("product_id"))
                product_name = clean_text(product.get("product_name"))
                json_path = f"sites[{site_index}].products[{product_index}]"

                if not product_id:
                    ctx.issue(
                        "error",
                        "booking.missing_product_id",
                        entity_type="booking_product",
                        json_path=json_path,
                        raw_value=product.get("product_name"),
                    )
                    continue
                if not product_name:
                    ctx.issue(
                        "error",
                        "booking.missing_product_name",
                        entity_type="booking_product",
                        entity_id=product_id,
                        json_path=json_path,
                    )
                    continue

                card = _dict(product.get("card"))
                media = _dict(product.get("media"))
                details = _dict(product.get("details"))
                usage = _dict(product.get("usage"))
                pricing = _dict(product.get("pricing"))
                promotion = _dict(product.get("promotion"))
                booking = _dict(product.get("booking"))
                availability = _dict(product.get("availability"))

                entity_id = stable_id("booking_product", provider, product_id)
                ctx.rows.add(
                    "booking_product",
                    {
                        "id": entity_id,
                        "provider": provider,
                        "product_id": product_id,
                        "ticket_code": clean_text(product.get("ticket_code") or booking.get("ticket_code")),
                        "booking_code": clean_text(booking.get("booking_code") or source.get("booking_code")),
                        "source_url": clean_text(source.get("source_url")),
                        "source_language": clean_text(source.get("language")),
                        "source_currency": clean_text(source.get("currency")),
                        "source_style": clean_text(source.get("style")),
                        "source_tab": clean_text(source.get("tab")),
                        "source_domain": clean_text(source.get("domain")),
                        "source_page_type": clean_text(source.get("page_type")),
                        "destination_id": destination_id,
                        "destination_name": clean_text(destination.get("destination_name")),
                        "city": city,
                        "province": clean_text(destination.get("province")),
                        "country": clean_text(destination.get("country")),
                        "venue_name": clean_text(destination.get("venue_name")),
                        "service_group": clean_text(destination.get("service_group")),
                        "product_name": product_name,
                        "normalized_product_name": clean_text(product.get("normalized_product_name")),
                        "product_type": clean_text(product.get("product_type")),
                        "category": clean_text(product.get("category")),
                        "sub_category": clean_text(product.get("sub_category")),
                        "status": clean_text(product.get("status")),
                        "card_title": clean_text(card.get("title")),
                        "short_description": clean_text(card.get("short_description")),
                        "badges": _list(card.get("badges")) or None,
                        "highlights": _list(card.get("highlights")) or None,
                        "view_detail_available": card.get("view_detail_available"),
                        "select_available": card.get("select_available"),
                        "thumbnail_url": clean_text(media.get("thumbnail_url")),
                        "images": _list(media.get("images")) or None,
                        "overview": clean_text(details.get("overview")),
                        "detail_included": _list(details.get("included")) or None,
                        "detail_excluded": _list(details.get("excluded")) or None,
                        "benefits": _list(details.get("benefits")) or None,
                        "experience_description": _list(details.get("experience_description")) or None,
                        "usage_instructions": _list(details.get("usage_instructions")) or None,
                        "important_notes": _list(details.get("important_notes")) or None,
                        "detail_terms_and_conditions": _list(details.get("terms_and_conditions")) or None,
                        "surcharge_conditions": _list(details.get("surcharge_conditions")) or None,
                        "restrictions": _list(details.get("restrictions")) or None,
                        "service_locations": _list(details.get("service_locations")) or None,
                        "operating_information": _dict(details.get("operating_information")) or None,
                        "currency": clean_text(pricing.get("currency")),
                        "pricing_status": clean_text(pricing.get("pricing_status")),
                        "price_type": clean_text(pricing.get("price_type")),
                        "is_dynamic_price": pricing.get("is_dynamic_price"),
                        "is_from_price": pricing.get("is_from_price"),
                        "is_approximate_price": pricing.get("is_approximate_price"),
                        "display_price": clean_text(pricing.get("display_price") or card.get("display_price_text")),
                        "display_original_price": clean_text(card.get("display_original_price_text")),
                        "display_discount_text": clean_text(card.get("display_discount_text")),
                        "minimum_price": pricing.get("minimum_price"),
                        "maximum_price": pricing.get("maximum_price"),
                        "price_variants": _list(pricing.get("variants")) or None,
                        "is_promotional": promotion.get("is_promotional"),
                        "promotion_badges": _list(promotion.get("badges")) or None,
                        "promotion_name": clean_text(promotion.get("promotion_name")),
                        "promotion_code": clean_text(promotion.get("promotion_code")),
                        "promotion_description": clean_text(promotion.get("promotion_description")),
                        "discount_percent": promotion.get("discount_percent"),
                        "promotion_start_date": clean_text(promotion.get("promotion_start_date")),
                        "promotion_end_date": clean_text(promotion.get("promotion_end_date")),
                        "customer_conditions": _dict(product.get("customer_conditions")) or None,
                        "quantity_rules": _dict(product.get("quantity_rules")) or None,
                        "valid_from": clean_text(usage.get("valid_from")),
                        "valid_until": clean_text(usage.get("valid_until")),
                        "validity_text": clean_text(usage.get("validity_text")),
                        "duration": clean_text(usage.get("duration")),
                        "duration_minutes": parse_int(usage.get("duration_minutes")),
                        "duration_hours": parse_int(usage.get("duration_hours")),
                        "duration_days": parse_int(usage.get("duration_days")),
                        "number_of_uses": parse_int(usage.get("number_of_uses")),
                        "usage_type": clean_text(usage.get("usage_type")),
                        "same_day_use": usage.get("same_day_use"),
                        "time_slot_required": usage.get("time_slot_required"),
                        "time_slot": clean_text(usage.get("time_slot")),
                        "entry_time": clean_text(usage.get("entry_time")),
                        "availability_status": clean_text(availability.get("status")),
                        "availability_text": clean_text(availability.get("availability_text")),
                        "sold_out": availability.get("sold_out"),
                        "booking_open": availability.get("booking_open"),
                        "booking_search_url": clean_text(booking.get("search_url")),
                        "detail_url": clean_text(booking.get("detail_url")),
                        "booking_url": clean_text(booking.get("booking_url")),
                        "cart_url": clean_text(booking.get("cart_url")),
                        "booking_type": clean_text(booking.get("booking_type")),
                        "button_text": clean_text(booking.get("button_text")),
                        "select_button_available": booking.get("select_button_available"),
                        "inclusions": _list(product.get("inclusions")) or None,
                        "exclusions": _list(product.get("exclusions")) or None,
                        "policies": _dict(product.get("policies")) or None,
                        "surcharges": _list(product.get("surcharges")) or None,
                        "transportation": _list(product.get("transportation")) or None,
                        "food_and_beverage": _list(product.get("food_and_beverage")) or None,
                        "spa_and_wellness": _list(product.get("spa_and_wellness")) or None,
                        "source_data": _dict(product.get("source_data")) or None,
                        "validation": _dict(product.get("validation")) or None,
                        "rag_content": _rag_content(site, product),
                        "raw_payload": product,
                    },
                )
