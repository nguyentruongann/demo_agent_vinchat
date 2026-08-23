"""data/entertainment/*.json (8 file, 3 thế hệ schema) → attraction và bảng liên quan.

Ba thế hệ, ba cách đọc — nhưng cùng quy về một bảng:

* **Dạng A** (ha_noi, ha_tinh, hai_phong, ho_chi_minh, nghe_an): ``sections{}``
  là dict với key là slug do parser tự đặt, tiếng Việt lẫn tiếng Anh. Phải duyệt
  ``.values()``, TUYỆT ĐỐI không hardcode key.
* **Dạng B** (phu_quoc, nam_hoi_an): thêm ``detail`` lồng và ``detail_status``.
* **Dạng C** (nha-trang, schema_version 1.1): ``destination_overview.sections``
  cho thẻ giới thiệu, ``all_topics[]`` cho trang chi tiết, nối nhau bằng ``topic_id``.

Section quảng cáo đi vào ``destination_highlight``, không vào ``attraction``
(quyết định §15.2).
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

from src.data_postgre.normalize.common import normalize_language, parse_int, stable_id
from src.data_postgre.normalize.context import Context
from src.data_postgre.normalize.text import clean_text

GLOB = "data/entertainment/*.json"

# Bay section quang cao, dem duoc dung 28 muc. Doi chieu bang ten section that
# chu khong doan bang tu khoa.
MARKETING_SECTIONS = {
    "reasons_to_visit_grand_world",
    "top_reasons_to_visit",
    "reasons_you_must_visit",
    "welcome_to_vu_yen_royal_island",
    "welcome_to_the_land_of_heritage",
    "welcome_to_phu_quoc_united_center",
    "welcome_experiences",
}

# Suy kind tu ten section. Khong khop thi mac dinh 'experience'.
SECTION_KIND = {
    "must_see_events": "event",
    "must_see_shows": "show",
    "must_play_games": "game",
    "suggested_itinerary": "itinerary",
    "journey_of_experiences": "journey",
    "experience_journeys": "journey",
}


def _title_of(item: dict[str, Any]) -> str | None:
    """Item dùng ``title`` hoặc ``name`` tuỳ thế hệ schema."""
    return clean_text(item.get("title")) or clean_text(item.get("name"))


def _fallback_title(description: str | None) -> str | None:
    """Một số mục quảng cáo không có tiêu đề, chỉ có mô tả."""
    text = clean_text(description)
    if not text:
        return None
    head = text.split(". ")[0]
    return head if len(head) <= 120 else head[:117] + "…"


def parse(ctx: Context) -> None:
    for file_path in sorted(glob.glob(GLOB)):
        ctx.source_file = file_path
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        _one_file(ctx, file_path, payload)


def _one_file(ctx: Context, file_path: str, payload: dict[str, Any]) -> None:
    dest_block = payload.get("destination") or {}
    page = payload.get("page_information") or {}

    # destination.name la TEN KHU, con city/province moi la dia danh.
    geo = dest_block.get("city") or dest_block.get("province") or dest_block.get("name")
    destination_id = ctx.destination(
        geo, json_path="destination.city|province", entity_type="attraction"
    )
    if not destination_id:
        ctx.issue("error", "entertainment.no_destination", json_path="destination",
                  raw_value=geo)
        return

    complex_id = ctx.complex(dest_block.get("name")) or ctx.complex(geo)

    source_url = (
        page.get("source_url")
        or (dest_block.get("source_page") or {}).get("canonical_url")
        or dest_block.get("source_url")
    )
    source_id = ctx.source(
        source_url,
        canonical=(dest_block.get("source_page") or {}).get("canonical_url"),
        html_file=page.get("source_file")
        or (dest_block.get("source_page") or {}).get("source_file"),
        is_404=bool((dest_block.get("source_page") or {}).get("is_404")),
    )
    language = normalize_language(page.get("language") or dest_block.get("language"))
    key = Path(file_path).stem

    scope = _Scope(ctx, key, destination_id, complex_id, source_id, language)

    # Dang A va B: sections{} o goc.
    for name, section in (payload.get("sections") or {}).items():
        scope.section(name, section)

    # Dang C: the gioi thieu nam trong destination_overview.
    overview = (payload.get("destination_overview") or {}).get("sections") or {}
    for name, section in overview.items():
        scope.section(name, section, title_field="section_title")

    # Dang C: trang chi tiet, noi vao the bang topic_id.
    for topic in payload.get("all_topics") or []:
        scope.topic(topic)


class _Scope:
    """Giữ ngữ cảnh của một file để khỏi truyền lặp sáu tham số."""

    def __init__(
        self,
        ctx: Context,
        key: str,
        destination_id: str,
        complex_id: str | None,
        source_id: str | None,
        language: str | None,
    ) -> None:
        self.ctx = ctx
        self.key = key
        self.destination_id = destination_id
        self.complex_id = complex_id
        self.source_id = source_id
        self.language = language

    # -- section ----------------------------------------------------------

    def section(
        self, name: str, section: dict[str, Any], *, title_field: str = "title"
    ) -> None:
        section_title = clean_text(section.get(title_field) or section.get("title"))
        items = section.get("items") or []
        if name in MARKETING_SECTIONS:
            for order, item in enumerate(items):
                self._highlight(name, section_title, order, item)
            return
        kind = SECTION_KIND.get(name, "experience")
        for order, item in enumerate(items):
            self._attraction(name, section_title, kind, order, item)

    def _highlight(
        self, name: str, section_title: str | None, order: int, item: dict[str, Any]
    ) -> None:
        description = clean_text(item.get("description"))
        title = _title_of(item) or _fallback_title(description)
        if not title:
            self.ctx.issue("warning", "highlight.no_title", json_path=f"sections.{name}",
                           raw_value=str(item)[:200])
            return
        highlight_id = stable_id("destination_highlight", self.key, name, order)
        self.ctx.rows.add("destination_highlight", {
            "id": highlight_id,
            "destination_id": self.destination_id,
            "complex_id": self.complex_id,
            "section_title": section_title,
            "title": title,
            "description": description,
            "image_url": clean_text(item.get("image_url")),
            "sort_order": order,
            "source_id": self.source_id,
        })
        self.ctx.media("destination_highlight", highlight_id, item.get("image_url"),
                       role="hero", alt=clean_text(item.get("image_alt")))

    def _attraction(
        self,
        name: str,
        section_title: str | None,
        kind: str,
        order: int,
        item: dict[str, Any],
    ) -> None:
        # Ba muc trong ha_tinh_data.json chi co description + image_url, khong co
        # title. Lay cau dau cua mo ta lam tieu de con hon bo ca dong.
        title = _title_of(item) or _fallback_title(item.get("description"))
        if not title:
            self.ctx.issue("warning", "attraction.no_title",
                           json_path=f"sections.{name}[{order}]",
                           raw_value=str(item)[:200])
            return
        if not _title_of(item):
            self.ctx.issue("info", "attraction.title_from_description",
                           json_path=f"sections.{name}[{order}]", raw_value=title)

        topic_id = item.get("topic_id")
        attraction_id = (
            stable_id("attraction", self.key, topic_id)
            if topic_id is not None
            else stable_id("attraction", self.key, name, order)
        )

        detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
        detail_url = clean_text(item.get("detail_url") or item.get("topic_url")
                                or item.get("option_url"))

        self.ctx.rows.add("attraction", {
            "id": attraction_id,
            "destination_id": self.destination_id,
            "complex_id": self.complex_id,
            "parent_id": None,
            "kind": kind,
            "title": title,
            "summary": clean_text(item.get("description")),
            "description": clean_text(detail.get("meta_description")),
            "full_text": clean_text(detail.get("full_text")),
            "location_text": clean_text(item.get("location") or item.get("address")),
            "section_title": section_title,
            "topic_group": clean_text(item.get("topic_group")) or name,
            "detail_url": detail_url,
            "detail_status": self._detail_status(item),
            "image_url": clean_text(item.get("image_url")),
            "content_language": normalize_language(detail.get("language")) or self.language,
            "sort_order": order,
            "source_id": self.source_id,
        })

        self.ctx.media("attraction", attraction_id, item.get("image_url"), role="hero",
                       alt=clean_text(item.get("image_alt")))
        if detail_url:
            self.ctx.link(self.source_id, detail_url, anchor=title,
                          context="option" if item.get("option_url") else "card")
        for link in detail.get("links") or []:
            self.ctx.link(self.source_id, link.get("url"), anchor=link.get("text"),
                          is_internal=link.get("is_internal"), context="detail")

    @staticmethod
    def _detail_status(item: dict[str, Any]) -> str | None:
        raw = clean_text(item.get("detail_status"))
        allowed = {"available", "missing_url", "not_found", "not_provided"}
        if raw in allowed:
            return raw
        if raw == "missing_detail_url":
            return "missing_url"
        if raw == "page_not_found":
            return "not_found"
        return "available" if item.get("detail") else None

    # -- all_topics (dạng C) ----------------------------------------------

    def topic(self, topic: dict[str, Any]) -> None:
        card = topic.get("card_data") or {}
        page = topic.get("page_data") or {}
        source = topic.get("source") or {}
        topic_id = card.get("topic_id")
        title = clean_text(card.get("title")) or clean_text(page.get("title"))
        if topic_id is None or not title:
            return

        attraction_id = stable_id("attraction", self.key, topic_id)
        group = clean_text(topic.get("topic_group")) or ""
        kind = "journey" if "journey" in group else SECTION_KIND.get(group, "experience")

        detail_source = self.ctx.source(
            source.get("url"),
            canonical=source.get("canonical_url"),
            html_file=source.get("html_file"),
        )

        # Gop vao dung dong da tao tu the: Rows.add merge theo khoa chinh.
        self.ctx.rows.add("attraction", {
            "id": attraction_id,
            "destination_id": self.destination_id,
            "complex_id": self.complex_id,
            "parent_id": None,
            "kind": kind,
            "title": title,
            "summary": clean_text(card.get("description")),
            "description": clean_text((page.get("metadata") or {}).get("meta_description")),
            "full_text": clean_text(page.get("full_text")),
            "location_text": clean_text(card.get("location")),
            "section_title": clean_text(card.get("section_title")),
            "topic_group": group or None,
            "detail_url": clean_text(card.get("topic_url") or source.get("canonical_url")),
            "detail_status": "available",
            "image_url": clean_text(card.get("image_url")),
            "content_language": normalize_language((page.get("metadata") or {}).get("language"))
            or self.language,
            "sort_order": parse_int(topic_id),
            "source_id": detail_source or self.source_id,
        })

        self._journey(topic, attraction_id)

        for link in page.get("links") or []:
            self.ctx.link(detail_source, link.get("url"), anchor=link.get("text"),
                          is_internal=link.get("is_internal"), context="body")
        for order, image in enumerate(page.get("images") or []):
            self.ctx.media("attraction", attraction_id, image.get("url"),
                           alt=image.get("alt"), sort_order=order)

    def _journey(self, topic: dict[str, Any], attraction_id: str) -> None:
        journey = topic.get("journey_data")
        if not isinstance(journey, dict):
            return
        duration = journey.get("duration") or {}

        # Lich trinh theo ngay di thang vao cot JSONB attraction.itinerary.
        # Khong tach bang con: chi 7 ngay thuoc 3 hanh trinh, va khong ai truy
        # van rieng mot ngay — ban than activities cung la van ban tuong thuat.
        days: list[dict[str, Any]] = []
        for day in journey.get("itinerary") or []:
            number = parse_int(day.get("day_number"))
            if number is None:
                continue
            days.append({
                "day_number": number,
                "heading": clean_text(day.get("heading")),
                "text": clean_text(day.get("text")),
                "activities": day.get("activities") or None,
            })

        self.ctx.rows.add("attraction", {
            "id": attraction_id,
            "duration_days": parse_int(duration.get("days")),
            "duration_nights": parse_int(duration.get("nights")),
            "duration_label": clean_text(duration.get("label")),
            "itinerary": days or None,
        })
