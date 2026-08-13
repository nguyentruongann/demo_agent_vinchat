from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from src.backend.services.db import open_session
from src.data_postgre.db.core import (
    Destination,
    Media,
    Promotion,
    PromotionDestination,
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
    return fallback if fallback in {"active", "upcoming", "expired"} else "active"


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

    if status not in {"all", "active", "upcoming", "expired"}:
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
