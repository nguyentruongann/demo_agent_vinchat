"""Repository đọc FAQ từ PostgreSQL.

Hỗ trợ search text, filter theo category/destination, pagination,
và trả category count phản ánh filter hiện tại.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select

from src.backend.services.db import open_session
from src.data_postgre.db.core import Faq


def _base_filter(
    *,
    q: str | None,
    category: str | None,
    destination: str | None,
):
    """Trả danh sách SQLAlchemy filter conditions dùng chung cho items và count."""
    conditions = []

    if q:
        term = f"%{q}%"
        conditions.append(
            or_(
                Faq.question.ilike(term),
                Faq.answer.ilike(term),
            )
        )

    if category:
        conditions.append(Faq.category == category)

    if destination:
        conditions.append(Faq.destination_id == destination)

    return conditions


def _deduplicated_faq_rows(conditions, *, name: str):
    """Return one FAQ id/category per question after applying filters."""
    ranked = (
        select(
            Faq.id.label("id"),
            Faq.category.label("category"),
            func.row_number()
            .over(partition_by=Faq.question, order_by=Faq.id)
            .label("question_rank"),
        )
        .where(*conditions)
        .subquery(f"{name}_ranked")
    )
    return (
        select(ranked.c.id, ranked.c.category)
        .where(ranked.c.question_rank == 1)
        .subquery(name)
    )


def list_faqs(
    *,
    q: str | None = None,
    category: str | None = None,
    destination: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Trả FAQ với search/filter/pagination và category counts.

    Lọc trước rồi xếp hạng theo question để chọn một bản ghi ổn định.
    """
    with open_session() as session:
        filters = _base_filter(q=q, category=category, destination=destination)

        # ── Distinct subquery để loại duplicate question ──────────────
        deduplicated = _deduplicated_faq_rows(filters, name="deduplicated_faq")

        # ── Base query join distinct ────────────────────────────────
        base = select(Faq).join(deduplicated, Faq.id == deduplicated.c.id)

        # ── Total count ─────────────────────────────────────────────
        count_stmt = select(func.count()).select_from(deduplicated)
        total = session.execute(count_stmt).scalar() or 0

        # ── Category counts (phản ánh search + destination, KHÔNG filter category) ──
        cat_filters = _base_filter(q=q, category=None, destination=destination)
        category_rows = _deduplicated_faq_rows(
            cat_filters,
            name="deduplicated_faq_categories",
        )
        cat_base = (
            select(category_rows.c.category, func.count().label("cnt"))
            .group_by(category_rows.c.category)
            .order_by(category_rows.c.category)
        )

        cat_rows = session.execute(cat_base).all()
        categories = [{"name": name, "count": cnt} for name, cnt in cat_rows]

        # ── Items với pagination ────────────────────────────────────
        items_stmt = (
            base
            .order_by(
                Faq.sort_order.asc().nullslast(),
                Faq.question.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = session.execute(items_stmt).scalars().all()

        items = [
            {
                "id": row.id,
                "category": row.category,
                "subcategory": row.subcategory,
                "question": row.question,
                "answer": row.answer,
                "destination_id": row.destination_id,
                "content_language": row.content_language,
                "sort_order": row.sort_order,
            }
            for row in rows
        ]

        return {
            "items": items,
            "categories": categories,
            "total": total,
        }
