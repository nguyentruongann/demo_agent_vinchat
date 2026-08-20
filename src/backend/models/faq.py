"""Pydantic response models cho FAQ API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FaqItem(BaseModel):
    id: str
    category: str
    subcategory: str | None = None
    question: str
    answer: str
    destination_id: str | None = None
    content_language: str | None = None
    sort_order: int | None = None


class CategoryCount(BaseModel):
    name: str
    count: int


class FaqListResponse(BaseModel):
    items: list[FaqItem] = Field(default_factory=list)
    categories: list[CategoryCount] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0
    content_language: str = "en"
    requested_language: str = "en"
    translation_fallback: bool = False
