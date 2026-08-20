"""FAQ API routes.

GET /api/v1/faqs — danh sách FAQ với search, filter category/destination, pagination.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.backend.models.faq import CategoryCount, FaqItem, FaqListResponse
from src.backend.repositories.faq_repository import list_faqs

router = APIRouter(prefix="/api/v1", tags=["faq"])


@router.get("/faqs", response_model=FaqListResponse)
def get_faqs(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None),
    destination: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    lang: str = Query(default="en"),
) -> FaqListResponse:
    """Trả danh sách FAQ.

    - ``q``: tìm trong question và answer (trim, giới hạn 200 ký tự).
    - ``category``: lọc theo category.
    - ``destination``: lọc theo destination_id.
    - ``page``: trang hiện tại (1-indexed).
    - ``page_size``: mặc định 20, tối đa 50.
    - ``lang``: ngôn ngữ yêu cầu.
    """
    q_trimmed = q.strip() if q else None

    result = list_faqs(
        q=q_trimmed,
        category=category,
        destination=destination,
        page=page,
        page_size=page_size,
    )

    items = [FaqItem(**item) for item in result["items"]]
    categories = [CategoryCount(**cat) for cat in result["categories"]]

    # FAQ data hiện tại chỉ có tiếng Anh; nếu lang != en, đánh dấu fallback.
    content_lang = items[0].content_language if items else "en"
    fallback = lang != "en" and lang != content_lang

    return FaqListResponse(
        items=items,
        categories=categories,
        page=page,
        page_size=page_size,
        total=result["total"],
        content_language=content_lang or "en",
        requested_language=lang,
        translation_fallback=fallback,
    )
