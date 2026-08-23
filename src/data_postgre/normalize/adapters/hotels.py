"""data/hotel/vinpearl_hotel_room_dining_rag.json → property, room, amenity, dining_service.

Nhóm sạch nhất trong toàn bộ data. Hai quan hệ cha–con ở đây có hai lớp bằng
chứng: mảng lồng trong JSON, cộng với tiền tố id (116/116 và 68/68).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.data_postgre.normalize.common import (
    parse_area,
    parse_int,
    parse_money,
    parse_time_range,
    stable_id,
)
from src.data_postgre.normalize.context import Context
from src.data_postgre.normalize.text import clean_text, slugify

SOURCE = "data/hotel/vinpearl_hotel_room_dining_rag.json"

# 'Bathtub' nằm lẫn trong bed_types của nguồn — nó là tiện nghi, không phải giường.
_NOT_A_BED = {"bathtub"}


def _kind(name: str) -> str:
    return "resort" if "resort" in name.lower() else "hotel"


def _amenity(ctx: Context, label: str) -> str | None:
    text = clean_text(label)
    if not text:
        return None
    amenity_id = slugify(text)
    if not amenity_id:
        return None
    ctx.rows.add("amenity", {"id": amenity_id, "name_en": text, "name_vi": None,
                             "category": None})
    return amenity_id


def parse(ctx: Context) -> None:
    ctx.source_file = SOURCE
    payload = json.loads(Path(SOURCE).read_text(encoding="utf-8"))

    for h_index, hotel in enumerate(payload["hotels"]):
        hotel_id = hotel["hotel_id"]
        name = clean_text(hotel["hotel_name"]) or hotel_id
        path = f"hotels[{h_index}]"

        destination_id = ctx.destination(
            hotel.get("location_name"), json_path=f"{path}.location_name",
            entity_type="property",
        )
        if not destination_id:
            # Thiếu địa danh thì cả khách sạn vô dụng — loại hẳn, không nạp nửa vời.
            ctx.issue("error", "property.no_destination", entity_type="property",
                      entity_id=hotel_id, json_path=path,
                      raw_value=hotel.get("location_name"))
            continue

        source_id = ctx.source(hotel.get("hotel_url"))
        ctx.rows.add("property", {
            "id": hotel_id,
            "name": name,
            "kind": _kind(name),
            "destination_id": destination_id,
            "complex_id": ctx.complex(hotel.get("location_name")),
            "brand_id": "vinpearl",
            "address": clean_text(hotel.get("hotel_address")),
            "url": clean_text(hotel.get("hotel_url")),
            "room_page_url": clean_text(hotel.get("room_page_url")),
            "dining_page_url": clean_text(hotel.get("dining_page_url")),
            "source_id": source_id,
        })

        _rooms(ctx, hotel, hotel_id, path)
        _dining(ctx, hotel, hotel_id, path)


def _rooms(ctx: Context, hotel: dict, hotel_id: str, path: str) -> None:
    room_source = ctx.source(hotel.get("room_page_url"))

    for r_index, room in enumerate(hotel.get("rooms") or []):
        room_id = room["room_id"]
        json_path = f"{path}.rooms[{r_index}]"

        price = parse_money((room.get("price_from") or {}).get("raw"))
        if price.failure and price.failure != "empty":
            ctx.issue("warning", "price.unparseable", entity_type="room",
                      entity_id=room_id, json_path=f"{json_path}.price_from",
                      field="price_from", raw_value=(room.get("price_from") or {}).get("raw"),
                      message=price.failure)

        rate = parse_money((room.get("standard_rate") or {}).get("raw"))
        if rate.failure == "no_currency_pattern":
            # 69/116 dòng: crawler bắt nhầm link hotline 'tel:1900232389' thành giá.
            ctx.issue("warning", "rate.not_a_price", entity_type="room",
                      entity_id=room_id, json_path=f"{json_path}.standard_rate",
                      field="standard_rate",
                      raw_value=(room.get("standard_rate") or {}).get("raw"))

        beds = [
            b for b in (clean_text(x) for x in room.get("bed_types") or [])
            if b and b.lower() not in _NOT_A_BED
        ]

        # _amenity() vừa ghi vào bảng từ điển ``amenity`` vừa trả về id, nên phải
        # chạy TRƯỚC khi dựng dòng room — amenity_ids giờ là cột của chính nó.
        # dict.fromkeys giữ thứ tự xuất hiện và loại trùng: một phòng có thể liệt
        # kê 'Bathtub' và 'bathtub' cùng lúc, cả hai quy về một id.
        amenity_ids = list(dict.fromkeys(
            aid for aid in (_amenity(ctx, label) for label in room.get("amenities") or [])
            if aid
        ))

        ctx.rows.add("room", {
            "id": room_id,
            "property_id": hotel_id,
            "room_index": parse_int(room.get("room_index")) or r_index + 1,
            "name": clean_text(room.get("room_name")) or room_id,
            "description": clean_text(room.get("room_description")),
            "guest_count": parse_int(room.get("guest_count")),
            "area_sqm": parse_area((room.get("room_area") or {}).get("raw")),
            "area_raw": clean_text((room.get("room_area") or {}).get("raw")),
            "price_from_amount": price.amount,
            "price_from_currency": price.currency,
            "price_is_approximate": price.is_approximate,
            "price_observed_at": None,
            "rate_amount": rate.amount,
            "rate_currency": rate.currency,
            "rate_raw": clean_text((room.get("standard_rate") or {}).get("raw")),
            "is_rate_suspect": rate.failure == "no_currency_pattern",
            "bed_types": beds or None,
            "has_wifi": room.get("wifi"),
            "image_url": clean_text(room.get("room_image_url")),
            "page_url": clean_text(room.get("room_page_url")),
            "amenity_ids": amenity_ids or None,
            "source_id": room_source,
        })

        ctx.media("room", room_id, room.get("room_image_url"), role="hero")


def _dining(ctx: Context, hotel: dict, hotel_id: str, path: str) -> None:
    dining_source = ctx.source(hotel.get("dining_page_url"))

    for d_index, service in enumerate(hotel.get("dining_services") or []):
        service_id = service["service_id"]
        hours = service.get("opening_hours") or {}
        contact = service.get("contact") or {}
        opens_at, closes_at = parse_time_range(hours.get("raw"))

        ctx.rows.add("dining_service", {
            "id": service_id,
            "property_id": hotel_id,
            "service_index": parse_int(service.get("service_index")) or d_index + 1,
            "name": clean_text(service.get("service_name")) or service_id,
            "description": clean_text(service.get("description")),
            "opens_at": opens_at,
            "closes_at": closes_at,
            "hours_raw": clean_text(hours.get("raw")),
            "hours_display": clean_text(hours.get("display")),
            "contact_raw": clean_text(contact.get("raw")),
            "contact_display": clean_text(contact.get("display")),
            "image_url": clean_text(service.get("service_image_url")),
            "source_id": dining_source,
        })
        ctx.media("dining_service", service_id, service.get("service_image_url"),
                  role="hero")


__all__ = ["parse", "stable_id"]
