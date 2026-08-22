from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select

from src.backend.services.db import open_session
from src.data_postgre.db.core import (
    Destination,
    Media,
    Promotion,
    PromotionBenefit,
    PromotionBlock,
    PromotionCode,
    PromotionDestination,
    PromotionSection,
    PromotionTerm,
    Source,
)

router = APIRouter(prefix="/api/v1/promotions", tags=["promotions"])


def _promotion_status(promotion: Promotion, today: date) -> str:
    """Calculate a current UI status from structured date fields.

    We intentionally do not trust status_at_crawl as the primary value because
    it was computed at crawl time. When structured dates are unavailable, that
    field is used only as a fallback.
    """
    starts = [
        value
        for value in (
            promotion.booking_from,
            promotion.stay_from,
            promotion.validity_from,
            promotion.purchase_from,
            promotion.redemption_from,
        )
        if value is not None
    ]
    ends = [
        value
        for value in (
            promotion.booking_to,
            promotion.stay_to,
            promotion.validity_to,
            promotion.purchase_to,
            promotion.redemption_to,
        )
        if value is not None
    ]

    if starts and min(starts) > today:
        return "upcoming"
    if ends and max(ends) < today:
        return "expired"
    if starts or ends:
        return "active"

    fallback = (promotion.status_at_crawl or "unknown").lower()
    return fallback if fallback in {"active", "upcoming", "expired"} else "unknown"


def _date_text(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


@router.get("")
def list_promotions(
    destination: str | None = Query(default=None),
    status: str = Query(default="active"),
    search: str | None = Query(default=None),
    page_size: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    """Return PostgreSQL-backed promotions in the shape expected by the Vite UI."""
    destination = (destination or "").strip() or None
    status = (status or "all").strip().lower()
    search = (search or "").strip() or None

    if status not in {"all", "active", "upcoming", "expired", "unknown"}:
        status = "all"

    with open_session() as session:
        stmt = select(Promotion).where(Promotion.is_active.is_(True))

        if destination and destination != "all":
            stmt = (
                stmt.outerjoin(
                    PromotionDestination,
                    PromotionDestination.promotion_id == Promotion.id,
                )
                .where(
                    or_(
                        Promotion.is_nationwide.is_(True),
                        PromotionDestination.destination_id == destination,
                    )
                )
                .distinct()
            )

        if search:
            term = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Promotion.title.ilike(term),
                    Promotion.summary.ilike(term),
                    Promotion.discount_text.ilike(term),
                    Promotion.full_text.ilike(term),
                )
            )

        promotions = session.execute(stmt.order_by(Promotion.title.asc())).scalars().all()
        if not promotions:
            return {"items": [], "total": 0}

        today = date.today()
        rows: list[tuple[Promotion, str]] = []
        for promotion in promotions:
            current_status = _promotion_status(promotion, today)
            if status != "all" and current_status != status:
                continue
            rows.append((promotion, current_status))

        promotion_ids = [promotion.id for promotion, _ in rows]
        if not promotion_ids:
            return {"items": [], "total": 0}

        destination_rows = session.execute(
            select(
                PromotionDestination.promotion_id,
                Destination.id,
                Destination.name_vi,
                Destination.name_en,
            )
            .join(Destination, Destination.id == PromotionDestination.destination_id)
            .where(PromotionDestination.promotion_id.in_(promotion_ids))
        ).all()
        destinations_by_promotion: dict[str, list[dict[str, str]]] = {}
        for promotion_id, destination_id, name_vi, name_en in destination_rows:
            destinations_by_promotion.setdefault(promotion_id, []).append(
                {
                    "id": destination_id,
                    "name": name_vi or name_en or destination_id,
                    "name_vi": name_vi,
                    "name_en": name_en,
                }
            )

        media_rows = session.execute(
            select(Media.entity_id, Media.url, Media.role, Media.sort_order)
            .where(
                Media.entity_type == "promotion",
                Media.entity_id.in_(promotion_ids),
            )
            .order_by(Media.entity_id, Media.sort_order.asc().nullslast())
        ).all()
        images_by_promotion: dict[str, str] = {}
        for entity_id, url, role, _sort_order in media_rows:
            if not url:
                continue
            if entity_id not in images_by_promotion or role in {"hero", "thumbnail"}:
                images_by_promotion[entity_id] = url

        source_ids = [promotion.source_id for promotion, _ in rows if promotion.source_id]
        source_by_id: dict[str, str] = {}
        if source_ids:
            source_rows = session.execute(
                select(Source.id, Source.canonical_url, Source.url).where(Source.id.in_(source_ids))
            ).all()
            source_by_id = {
                source_id: (canonical_url or url)
                for source_id, canonical_url, url in source_rows
                if canonical_url or url
            }

        items: list[dict[str, Any]] = []
        for promotion, current_status in rows[:page_size]:
            items.append(
                {
                    "id": promotion.id,
                    "slug": promotion.slug,
                    "title": promotion.title,
                    "summary": promotion.summary,
                    "discount_text": promotion.discount_text,
                    "is_nationwide": bool(promotion.is_nationwide),
                    "destinations": destinations_by_promotion.get(promotion.id, []),
                    "status": current_status,
                    "validity_from": _date_text(promotion.validity_from),
                    "validity_to": _date_text(promotion.validity_to),
                    "booking_from": _date_text(promotion.booking_from),
                    "booking_to": _date_text(promotion.booking_to),
                    "stay_from": _date_text(promotion.stay_from),
                    "stay_to": _date_text(promotion.stay_to),
                    "booking_url": promotion.booking_url
                    or (source_by_id.get(promotion.source_id) if promotion.source_id else None),
                    "terms_url": promotion.terms_url,
                    "app_url": promotion.app_url,
                    "image_url": images_by_promotion.get(promotion.id),
                    "content_language": promotion.content_language,
                }
            )

        return {"items": items, "total": len(rows)}


@router.get("/{promotion_id}")
def promotion_detail(
    promotion_id: str,
    lang: str = Query(default="en"),
) -> dict[str, Any]:
    """Return the structured promotion payload consumed by FE ver_02.

    The current P-013 backend does not yet have the translation repository from
    the FE team's branch, so ``lang`` is accepted for API compatibility while
    stored promotion content is returned as-is. Destination names use Vietnamese
    when requested and available.
    """
    language = (lang or "en").lower()

    with open_session() as session:
        promotion = session.execute(
            select(Promotion).where(
                or_(Promotion.id == promotion_id, Promotion.slug == promotion_id)
            )
        ).scalar_one_or_none()
        if promotion is None or not promotion.is_active:
            raise HTTPException(status_code=404, detail="Promotion not found")

        destination_rows = session.execute(
            select(
                Destination.id,
                Destination.name_vi,
                Destination.name_en,
            )
            .join(
                PromotionDestination,
                PromotionDestination.destination_id == Destination.id,
            )
            .where(PromotionDestination.promotion_id == promotion.id)
            .order_by(Destination.sort_order.asc().nullslast(), Destination.name_en.asc())
        ).all()
        destinations = [
            {
                "id": destination_id,
                "name": (
                    name_vi
                    if language == "vi" and name_vi
                    else name_en or name_vi or destination_id
                ),
                "name_vi": name_vi,
                "name_en": name_en,
            }
            for destination_id, name_vi, name_en in destination_rows
        ]

        media_row = session.execute(
            select(Media.url)
            .where(
                Media.entity_type == "promotion",
                Media.entity_id == promotion.id,
                Media.url.is_not(None),
            )
            .order_by(Media.sort_order.asc().nullslast())
        ).first()
        image_url = media_row[0] if media_row else None

        source_url = None
        if promotion.source_id:
            source_row = session.execute(
                select(Source.canonical_url, Source.url).where(Source.id == promotion.source_id)
            ).first()
            if source_row:
                source_url = source_row[0] or source_row[1]

        benefits = session.execute(
            select(PromotionBenefit)
            .where(PromotionBenefit.promotion_id == promotion.id)
            .order_by(PromotionBenefit.sort_order.asc().nullslast(), PromotionBenefit.id.asc())
        ).scalars().all()
        codes = session.execute(
            select(PromotionCode)
            .where(PromotionCode.promotion_id == promotion.id)
            .order_by(PromotionCode.id.asc())
        ).scalars().all()
        sections = session.execute(
            select(PromotionSection)
            .where(PromotionSection.promotion_id == promotion.id)
            .order_by(PromotionSection.ord.asc())
        ).scalars().all()
        blocks = session.execute(
            select(PromotionBlock)
            .where(PromotionBlock.promotion_id == promotion.id)
            .order_by(PromotionBlock.ord.asc())
        ).scalars().all()
        terms = session.execute(
            select(PromotionTerm)
            .where(PromotionTerm.promotion_id == promotion.id)
            .order_by(PromotionTerm.kind.asc(), PromotionTerm.ord.asc())
        ).scalars().all()

        term_groups: dict[str, list[dict[str, str]]] = {
            "term": [],
            "combination": [],
            "contact": [],
            "step": [],
        }
        for item in terms:
            term_groups.setdefault(item.kind, []).append(
                {"id": item.id, "text": item.text_content}
            )

        return {
            "id": promotion.id,
            "slug": promotion.slug,
            "title": promotion.title,
            "summary": promotion.summary,
            "content": promotion.full_text,
            "discount_text": promotion.discount_text,
            "is_nationwide": bool(promotion.is_nationwide),
            "destinations": destinations,
            "status": _promotion_status(promotion, date.today()),
            "validity_from": _date_text(promotion.validity_from),
            "validity_to": _date_text(promotion.validity_to),
            "booking_from": _date_text(promotion.booking_from),
            "booking_to": _date_text(promotion.booking_to),
            "stay_from": _date_text(promotion.stay_from),
            "stay_to": _date_text(promotion.stay_to),
            "booking_url": promotion.booking_url or source_url,
            "terms_url": promotion.terms_url,
            "app_url": promotion.app_url,
            "image_url": image_url,
            "content_language": promotion.content_language,
            "benefits": [
                {
                    "id": item.id,
                    "benefit_type": item.benefit_type,
                    "value": float(item.value) if item.value is not None else None,
                    "unit": item.unit,
                    "is_maximum": item.is_maximum,
                    "description": item.description,
                    "source_text": item.source_text,
                }
                for item in benefits
            ],
            "codes": [
                {
                    "id": item.id,
                    "code": item.code,
                    "description": item.description,
                    "validity": item.validity,
                    "conditions": item.conditions or [],
                }
                for item in codes
                if not item.is_suspect
            ],
            "sections": [
                {
                    "id": item.id,
                    "heading": item.heading,
                    "level": item.level,
                    "content": item.content,
                }
                for item in sections
            ],
            "blocks": [
                {
                    "id": item.id,
                    "block_type": item.block_type,
                    "caption": item.caption,
                    "payload": item.payload or {},
                }
                for item in blocks
            ],
            "terms": term_groups.get("term", []),
            "combination_rules": term_groups.get("combination", []),
            "contacts": term_groups.get("contact", []),
            "steps": term_groups.get("step", []),
        }
