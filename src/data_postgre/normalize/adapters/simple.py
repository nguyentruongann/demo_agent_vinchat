"""Bốn nguồn có cấu trúc rõ ràng: golf, MICE, FAQ, quy định, giới thiệu.

Gộp chung một file vì mỗi cái chỉ vài chục dòng và hình dạng đã sạch sẵn.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.data_postgre.normalize.common import (
    normalize_language,
    parse_area,
    parse_int,
    parse_specifications,
    stable_id,
)
from src.data_postgre.normalize.context import Context
from src.data_postgre.normalize.text import clean_text, slugify

GOLF = "data/golf/golf.json"
MICE = "data/event/vinpearl_mice_rag_en.json"
FAQS = "data/faqs/vinpearl_faqs.json"
REGULATIONS = "data/regulations/vinpearl_regulations.json"
ABOUT = "data/about/vinpearl_about.json"

CAPACITY_LAYOUTS = {
    "theater": "theater",
    "classroom": "classroom",
    "u-shape": "u_shape",
    "u shape": "u_shape",
    "boardroom": "boardroom",
    "banquet": "banquet",
    "cocktail": "cocktail",
}


# --------------------------------------------------------------------------
# Golf
# --------------------------------------------------------------------------


def parse_golf(ctx: Context) -> None:
    ctx.source_file = GOLF
    payload = json.loads(Path(GOLF).read_text(encoding="utf-8"))

    for index, course in enumerate(payload.get("golf_courses") or []):
        name = clean_text(course.get("name"))
        if not name:
            continue
        course_id = slugify(name)
        location = course.get("location") or {}
        path = f"golf_courses[{index}]"

        destination_id = ctx.destination(
            location.get("destination"), json_path=f"{path}.location.destination",
            entity_type="golf_course",
        )
        if not destination_id:
            continue

        info = course.get("general_information") or {}
        source_id = ctx.source(course.get("page_url"))
        ctx.rows.add("golf_course", {
            "id": course_id,
            "destination_id": destination_id,
            "complex_id": ctx.complex(location.get("destination")),
            "name": name,
            "page_url": clean_text(course.get("page_url")),
            "summary": clean_text(info.get("summary")),
            "designer": clean_text(info.get("designer")),
            "holes": parse_int(info.get("number_of_holes")),
            "par": parse_int(info.get("par")),
            "course_length_raw": clean_text(info.get("course_length")),
            "total_area": clean_text(info.get("total_area")),
            "terrain": clean_text(info.get("terrain_and_landscape")),
            "full_address": clean_text(location.get("full_address")),
            "city": clean_text(location.get("city")),
            "district": clean_text(location.get("district")),
            "island": clean_text(location.get("island")),
            "source_id": source_id,
        })

        # source_urls[] co 2 URL moi san -> quan he N-N.
        for url in course.get("source_urls") or []:
            extra = ctx.source(url)
            if extra and extra != source_id:
                ctx.rows.add("entity_source", {
                    "entity_type": "golf_course", "entity_id": course_id,
                    "source_id": extra, "role": "secondary",
                })

        _golf_features(ctx, course, course_id, info)

        # Ban do san cung chi la {ten, anh} gan voi mot san, giong het tien ich
        # va trai nghiem -> vao chung golf_feature voi kind='map'.
        base = len(ctx.rows.get("golf_feature"))
        for order, gmap in enumerate(course.get("golf_course_maps") or []):
            title = clean_text(gmap.get("map_name")) or clean_text(gmap.get("course_type"))
            if not title:
                continue
            ctx.rows.add("golf_feature", {
                "id": stable_id("golf_feature", course_id, "map", order),
                "course_id": course_id,
                "kind": "map",
                "title": title,
                "description": None,
                "image_url": clean_text(gmap.get("map_url")),
                "detail_url": None,
                "variant": clean_text(gmap.get("course_type")),
                "sort_order": base + order,
                "source_id": ctx.source(gmap.get("source_url")),
            })
            ctx.media("golf_course", course_id, gmap.get("map_url"), role="map",
                      sort_order=order)


def _golf_features(ctx: Context, course: dict, course_id: str, info: dict) -> None:
    """Bốn mảng khác tên nhưng cùng hình dạng {title, description}."""
    order = 0
    for text in info.get("distinctive_features") or []:
        title = clean_text(text)
        if title:
            ctx.rows.add("golf_feature", {
                "id": stable_id("golf_feature", course_id, order), "course_id": course_id,
                "kind": "feature", "title": title, "description": None,
                "image_url": None, "detail_url": None, "sort_order": order,
            })
            order += 1
    for text in info.get("awards_and_recognitions") or []:
        title = clean_text(text)
        if title:
            ctx.rows.add("golf_feature", {
                "id": stable_id("golf_feature", course_id, order), "course_id": course_id,
                "kind": "award", "title": title, "description": None,
                "image_url": None, "detail_url": None, "sort_order": order,
            })
            order += 1
    for item in course.get("amenities") or []:
        title = clean_text(item.get("name"))
        if title:
            ctx.rows.add("golf_feature", {
                "id": stable_id("golf_feature", course_id, order), "course_id": course_id,
                "kind": "amenity", "title": title,
                "description": clean_text(item.get("description")),
                "image_url": None, "detail_url": None, "sort_order": order,
                "source_id": ctx.source(item.get("source_url")),
            })
            order += 1
    for item in course.get("experiences") or []:
        title = clean_text(item.get("title"))
        if title:
            ctx.rows.add("golf_feature", {
                "id": stable_id("golf_feature", course_id, order), "course_id": course_id,
                "kind": "experience", "title": title,
                "description": clean_text(item.get("description")),
                "image_url": clean_text(item.get("image_url")),
                "detail_url": clean_text(item.get("detail_url")),
                "sort_order": order,
                "source_id": ctx.source(item.get("source_url")),
            })
            order += 1


# --------------------------------------------------------------------------
# MICE
# --------------------------------------------------------------------------


def parse_mice(ctx: Context) -> None:
    ctx.source_file = MICE
    payload = json.loads(Path(MICE).read_text(encoding="utf-8"))

    intro = payload.get("page_intro") or {}
    if intro:
        # Quyet dinh §15.6: doan gioi thieu trang MICE vao org_info.
        ctx.rows.add("org_info", {
            "id": 1,
            "mice_intro_title": clean_text(intro.get("title")),
            "mice_intro_description": clean_text(intro.get("description")),
            "mice_intro_cta": clean_text(intro.get("booking_button_text")),
        })

    hotel_names = {r["name"]: r["id"] for r in ctx.rows.get("property")}

    for index, venue in enumerate(payload.get("venues") or []):
        name = clean_text(venue.get("name"))
        if not name:
            continue
        venue_id = slugify(name)
        path = f"venues[{index}]"
        destination_id = ctx.destination(
            venue.get("destination"), json_path=f"{path}.destination",
            entity_type="mice_venue",
        )
        if not destination_id:
            continue

        detail = venue.get("detail") or {}
        ctx.rows.add("mice_venue", {
            "id": venue_id,
            "destination_id": destination_id,
            "complex_id": ctx.complex(venue.get("destination")),
            # 5/10 khop chinh xac ten khach san; 5 dong NULL la Convention Center /
            # Theater / Almaz / VinPalace — cong trinh doc lap, NULL la dung nghia.
            "property_id": hotel_names.get(name),
            "name": name,
            "url": clean_text(venue.get("url")),
            "address": clean_text(venue.get("address")),
            "phone": clean_text(venue.get("phone")),
            "subtitle": clean_text(detail.get("subtitle")),
            "summary": clean_text(venue.get("summary")),
            "overview": clean_text(detail.get("overview")),
            "source_id": ctx.source(venue.get("url"),
                                    canonical=detail.get("source_url")),
        })

        for order, url in enumerate(detail.get("overview_image_urls") or []):
            ctx.media("mice_venue", venue_id, url, sort_order=order)

        for r_index, room in enumerate(detail.get("rooms") or []):
            _mice_room(ctx, venue_id, r_index, room, path)


def _mice_room(ctx: Context, venue_id: str, index: int, room: dict, path: str) -> None:
    name = clean_text(room.get("name"))
    if not name:
        return
    room_id = stable_id("mice_room", venue_id, index)
    dims = parse_specifications(room.get("specifications"))

    ctx.rows.add("mice_room", {
        "id": room_id,
        "venue_id": venue_id,
        "name": name,
        "description": clean_text(room.get("description")),
        # Nguon ban: gia tri that la chuoi '1250m 2' — ky tu mu bi tach.
        "area_sqm": parse_area(room.get("area")),
        "area_raw": clean_text(room.get("area")),
        "length_m": dims["length_m"],
        "width_m": dims["width_m"],
        "ceiling_height_m": dims["ceiling_height_m"],
        "specifications_raw": room.get("specifications") or None,
        "image_url": clean_text(room.get("image_url")),
        "sort_order": index,
    })
    ctx.media("mice_room", room_id, room.get("image_url"), role="hero")

    for label, value in (room.get("capacities") or {}).items():
        layout = CAPACITY_LAYOUTS.get(clean_text(label).lower() if label else "")
        if not layout:
            ctx.issue("warning", "mice.unknown_layout", entity_type="mice_room",
                      entity_id=room_id, json_path=f"{path}.capacities",
                      raw_value=label)
            continue
        pax = parse_int(value)
        if pax and pax > 0:
            ctx.rows.add("mice_room_capacity",
                         {"room_id": room_id, "layout": layout, "pax": pax})


# --------------------------------------------------------------------------
# FAQ
# --------------------------------------------------------------------------


def parse_faqs(ctx: Context) -> None:
    ctx.source_file = FAQS
    payload = json.loads(Path(FAQS).read_text(encoding="utf-8"))
    source_id = ctx.source(payload.get("source_url"))
    language = normalize_language(payload.get("language"))

    # Chi dung items[]; items_by_category{} chua y het cung 174 muc.
    seen: set[str] = set()
    for order, item in enumerate(payload.get("items") or []):
        question = clean_text(item.get("question"))
        answer = clean_text(item.get("answer"))
        if not question or not answer:
            ctx.issue("error", "faq.incomplete", entity_type="faq",
                      json_path=f"items[{order}]", raw_value=question)
            continue
        if question in seen:
            # 3/174 cau hoi bi lap y het trong nguon. Khoa chinh la hash cau hoi
            # nen chung tu gop; ghi lai de khong ai tuong pipeline lam mat dong.
            ctx.issue("info", "faq.duplicate_question", entity_type="faq",
                      json_path=f"items[{order}]", raw_value=question)
            continue
        seen.add(question)
        subcategory = clean_text(item.get("subcategory"))
        # 72/174 dong suy duoc dia danh tu subcategory ('VinWonders Nha Trang'...).
        destination_id = _destination_in_text(ctx, subcategory)
        ctx.rows.add("faq", {
            "id": stable_id("faq", question),
            "category": clean_text(item.get("category")) or "General",
            "subcategory": subcategory,
            "question": question,
            "answer": answer,
            "destination_id": destination_id,
            "content_language": language,
            "sort_order": order,
            "source_id": source_id,
        })


def _destination_in_text(ctx: Context, text: str | None) -> str | None:
    """Tìm tên địa danh nằm bên trong một chuỗi dài hơn."""
    if not text:
        return None
    from src.data_postgre.normalize.text import normalize_alias

    haystack = normalize_alias(text)
    best: tuple[int, str] | None = None
    for alias, dest_id in ctx.alias_to_destination.items():
        if len(alias) >= 4 and alias in haystack and (best is None or len(alias) > best[0]):
            best = (len(alias), dest_id)
    return best[1] if best else None


# --------------------------------------------------------------------------
# Quy định
# --------------------------------------------------------------------------


def parse_regulations(ctx: Context) -> None:
    ctx.source_file = REGULATIONS
    payload = json.loads(Path(REGULATIONS).read_text(encoding="utf-8"))

    for doc in payload.get("documents") or []:
        doc_id = doc.get("id") or stable_id("policy_document", doc.get("source_url"))
        ctx.rows.add("policy_document", {
            "id": doc_id,
            "title": clean_text(doc.get("title")),
            "h1": clean_text(doc.get("h1")),
            "category": clean_text(doc.get("category")),
            "plain_text": clean_text(doc.get("plain_text")),
            "word_count": parse_int(doc.get("word_count")),
            "effective_from": None,
            "content_hash": clean_text(doc.get("content_hash")),
            "source_id": ctx.source(
                doc.get("source_url"), canonical=doc.get("canonical_url"),
                crawled_at=doc.get("crawled_at"),
                http_status=parse_int(doc.get("status_code")),
                content_hash=doc.get("content_hash"),
            ),
        })

        for order, section in enumerate(doc.get("sections") or []):
            body = " ".join(clean_text(x) or "" for x in section.get("content") or [])
            ctx.rows.add("policy_section", {
                "id": stable_id("policy_section", doc_id, order),
                "document_id": doc_id, "ord": order,
                "heading": clean_text(section.get("heading")),
                "content": clean_text(body),
            })

        order = 0
        for table in doc.get("tables") or []:
            ctx.rows.add("policy_block", {
                "id": stable_id("policy_block", doc_id, order),
                "document_id": doc_id, "ord": order, "block_type": "table",
                "caption": None,
                "payload": {"headers": table.get("headers") or [],
                            "rows": table.get("rows") or []},
            })
            order += 1
        for lst in doc.get("lists") or []:
            ctx.rows.add("policy_block", {
                "id": stable_id("policy_block", doc_id, order),
                "document_id": doc_id, "ord": order, "block_type": "list",
                "caption": None,
                "payload": {"type": lst.get("type"),
                            "items": lst.get("items") or []},
            })
            order += 1

    for err in payload.get("errors") or []:
        ctx.issue("warning", "crawl.empty_content", entity_type="policy_document",
                  raw_value=err.get("url"), message=clean_text(err.get("message")))


# --------------------------------------------------------------------------
# Giới thiệu công ty
# --------------------------------------------------------------------------

HIGHLIGHT_FIELDS = {
    "hotels_and_resorts": "hotel_resort",
    "signature_product_packages": "package",
    "mice": "mice",
    "meeting_and_events": "meeting_event",
}


def parse_about(ctx: Context) -> None:
    ctx.source_file = ABOUT
    payload = json.loads(Path(ABOUT).read_text(encoding="utf-8"))
    info = payload.get("company_info") or {}
    source_id = ctx.source(payload.get("source_url"))

    ctx.rows.add("org_info", {
        "id": 1,
        "headline": clean_text(payload.get("headline")),
        "introduction": clean_text(payload.get("introduction")),
        "address": clean_text(info.get("address")),
        "hotline": clean_text(info.get("hotline")),
        "account_holder": clean_text(info.get("account_holder")),
        "bank_account": clean_text(info.get("bank_account")),
        "bank": clean_text(info.get("bank")),
        "business_registration": clean_text(info.get("business_registration")),
        "issued_by": clean_text(info.get("issued_by")),
        "source_id": source_id,
    })

    # 9/9 muc hotels_and_resorts khop chinh xac tuyet doi hotel_name.
    hotel_names = {r["name"]: r["id"] for r in ctx.rows.get("property")}
    hotel_dest = {r["name"]: r["destination_id"] for r in ctx.rows.get("property")}

    order = 0
    for field_name, kind in HIGHLIGHT_FIELDS.items():
        for item in payload.get(field_name) or []:
            name = clean_text(item.get("name"))
            if not name:
                continue
            ctx.rows.add("org_highlight", {
                "id": stable_id("org_highlight", kind, name),
                "kind": kind,
                "name": name,
                "description": clean_text(item.get("description")),
                "destination_id": hotel_dest.get(name),
                "property_id": hotel_names.get(name),
                "sort_order": order,
                "source_id": source_id,
            })
            order += 1


def parse(ctx: Context) -> None:
    """Chạy cả năm nguồn. MICE và about phụ thuộc property nên gọi sau hotels."""
    parse_golf(ctx)
    parse_mice(ctx)
    parse_faqs(ctx)
    parse_regulations(ctx)
    parse_about(ctx)


__all__: list[str] = [
    "parse",
    "parse_about",
    "parse_faqs",
    "parse_golf",
    "parse_mice",
    "parse_regulations",
]
