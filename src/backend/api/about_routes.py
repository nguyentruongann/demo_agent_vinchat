from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from src.backend.services.db import open_session
from src.data_postgre.db.core import OrgHighlight, OrgInfo, Source

router = APIRouter(prefix="/api/v1", tags=["about"])


def _highlight_payload(item: OrgHighlight) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "destination_id": item.destination_id,
        "property_id": item.property_id,
        "sort_order": item.sort_order,
    }


@router.get("/about")
def get_about_info(lang: str = Query(default="en")) -> dict[str, Any]:
    """Return organization and about-page highlight data for the frontend."""
    _lang = (lang or "en").lower()

    with open_session() as session:
        org = session.execute(select(OrgInfo).limit(1)).scalar_one_or_none()
        source_url = None
        if org and org.source_id:
            source_row = session.execute(
                select(Source.canonical_url, Source.url).where(Source.id == org.source_id)
            ).first()
            if source_row:
                source_url = source_row[0] or source_row[1]

        highlights = session.execute(
            select(OrgHighlight).order_by(
                OrgHighlight.kind.asc(),
                OrgHighlight.sort_order.asc().nullslast(),
                OrgHighlight.name.asc(),
            )
        ).scalars().all()

        grouped: dict[str, list[dict[str, Any]]] = {
            "hotels_and_resorts": [],
            "packages": [],
            "mice": [],
            "meeting_events": [],
        }
        kind_map = {
            "hotel_resort": "hotels_and_resorts",
            "package": "packages",
            "mice": "mice",
            "meeting_event": "meeting_events",
        }
        for item in highlights:
            grouped.setdefault(kind_map.get(item.kind, item.kind), []).append(
                _highlight_payload(item)
            )

        return {
            "source_url": source_url,
            "language": _lang,
            "org": {
                "headline": org.headline if org else None,
                "introduction": org.introduction if org else None,
                "address": org.address if org else None,
                "hotline": org.hotline if org else None,
                "account_holder": org.account_holder if org else None,
                "bank_account": org.bank_account if org else None,
                "bank": org.bank if org else None,
                "business_registration": org.business_registration if org else None,
                "issued_by": org.issued_by if org else None,
                "mice_intro_title": org.mice_intro_title if org else None,
                "mice_intro_description": org.mice_intro_description if org else None,
                "mice_intro_cta": org.mice_intro_cta if org else None,
            },
            "highlights": grouped,
        }
