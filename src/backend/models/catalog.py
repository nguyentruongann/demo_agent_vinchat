from typing import Literal

from pydantic import BaseModel, Field


class DestinationSummary(BaseModel):
    id: str
    name: str
    name_en: str
    name_vi: str
    province: str | None = None
    region: str | None = None
    country: str
    image_url: str | None = None
    highlight: str | None = None
    description: str | None = None
    property_count: int = 0


class RoomSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    guest_count: int | None = None
    area_sqm: float | None = None
    price: float | None = None
    currency: str | None = None
    price_is_approximate: bool = False
    image_url: str | None = None
    amenities: list[str] = Field(default_factory=list)
    bed_types: list[str] = Field(default_factory=list)
    has_wifi: bool | None = None
    booking_url: str | None = None


class DiningSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    hours: str | None = None
    contact: str | None = None
    image_url: str | None = None


class PropertySummary(BaseModel):
    id: str
    name: str
    kind: str | None = None
    destination_id: str
    destination_name: str
    address: str | None = None
    source_url: str | None = None
    images: list[str] = Field(default_factory=list)
    room_count: int = 0
    max_guests: int | None = None
    price_from: float | None = None
    currency: str | None = None
    amenities: list[str] = Field(default_factory=list)
    summary: str | None = None


class PropertyDetail(PropertySummary):
    room_page_url: str | None = None
    dining_page_url: str | None = None
    rooms: list[RoomSummary] = Field(default_factory=list)
    dining: list[DiningSummary] = Field(default_factory=list)


class PropertyListResponse(BaseModel):
    items: list[PropertySummary]
    page: int
    page_size: int
    total: int
    currency: Literal["USD"] = "USD"
