from typing import Any

from pydantic import BaseModel, Field


class DiscoveryDestination(BaseModel):
    id: str
    name: str


class AttractionSummary(BaseModel):
    id: str
    title: str
    kind: str
    destination_id: str
    destination_name: str
    summary: str | None = None
    image_url: str | None = None
    duration_label: str | None = None
    detail_url: str | None = None
    source_url: str | None = None


class AttractionDetail(AttractionSummary):
    description: str | None = None
    full_text: str | None = None
    location_text: str | None = None
    section_title: str | None = None
    topic_group: str | None = None
    detail_status: str | None = None
    duration_days: int | None = None
    duration_nights: int | None = None
    itinerary: list[dict[str, Any]] = Field(default_factory=list)


class AttractionListResponse(BaseModel):
    items: list[AttractionSummary]
    page: int
    page_size: int
    total: int
    kinds: list[str] = Field(default_factory=list)
    destinations: list[DiscoveryDestination] = Field(default_factory=list)


class GolfFeatureSummary(BaseModel):
    id: str
    kind: str
    title: str
    description: str | None = None
    image_url: str | None = None
    detail_url: str | None = None
    variant: str | None = None


class GolfSummary(BaseModel):
    id: str
    name: str
    destination_id: str
    destination_name: str
    summary: str | None = None
    image_url: str | None = None
    designer: str | None = None
    holes: int | None = None
    par: int | None = None
    page_url: str | None = None
    feature_count: int = 0


class GolfDetail(GolfSummary):
    course_length: str | None = None
    total_area: str | None = None
    terrain: str | None = None
    full_address: str | None = None
    city: str | None = None
    district: str | None = None
    island: str | None = None
    features: list[GolfFeatureSummary] = Field(default_factory=list)


class GolfListResponse(BaseModel):
    items: list[GolfSummary]
    page: int
    page_size: int
    total: int
    destinations: list[DiscoveryDestination] = Field(default_factory=list)


class MiceCapacitySummary(BaseModel):
    layout: str
    pax: int


class MiceRoomSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    area_sqm: float | None = None
    area_raw: str | None = None
    length_m: float | None = None
    width_m: float | None = None
    ceiling_height_m: float | None = None
    specifications: list[str] = Field(default_factory=list)
    image_url: str | None = None
    capacities: list[MiceCapacitySummary] = Field(default_factory=list)


class MiceVenueSummary(BaseModel):
    id: str
    name: str
    destination_id: str
    destination_name: str
    subtitle: str | None = None
    summary: str | None = None
    address: str | None = None
    phone: str | None = None
    source_url: str | None = None
    image_url: str | None = None
    room_count: int = 0
    max_capacity: int | None = None


class MiceVenueDetail(MiceVenueSummary):
    overview: str | None = None
    rooms: list[MiceRoomSummary] = Field(default_factory=list)


class MiceVenueListResponse(BaseModel):
    items: list[MiceVenueSummary]
    page: int
    page_size: int
    total: int
    destinations: list[DiscoveryDestination] = Field(default_factory=list)
