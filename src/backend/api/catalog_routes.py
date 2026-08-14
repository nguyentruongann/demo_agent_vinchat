from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from src.backend.models.catalog import (
    DestinationSummary,
    DiningSummary,
    PropertyDetail,
    PropertyListResponse,
    PropertySummary,
    RoomSummary,
)
from src.backend.services.db import open_session
from src.data_postgre.db.core import (
    Amenity,
    Destination,
    DestinationHighlight,
    DiningService,
    Media,
    Property,
    Room,
)

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


def _destination_name(destination: Destination, language: str) -> str:
    return destination.name_vi if language == "vi" else destination.name_en


def _valid_room_price(room: Room) -> tuple[float | None, str | None]:
    if room.is_rate_suspect:
        return None, None
    amount = room.price_from_amount if room.price_from_amount is not None else room.rate_amount
    currency = room.price_from_currency or room.rate_currency
    return (float(amount), currency) if amount is not None else (None, currency)


def _load_catalog_parts(db, property_ids: list[str]):
    if not property_ids:
        return {}, {}, {}

    rooms = db.scalars(
        select(Room)
        .where(Room.property_id.in_(property_ids), Room.is_active.is_(True))
        .order_by(Room.property_id, Room.room_index)
    ).all()
    rooms_by_property: dict[str, list[Room]] = defaultdict(list)
    amenity_ids: set[str] = set()
    for room in rooms:
        rooms_by_property[room.property_id].append(room)
        amenity_ids.update(room.amenity_ids or [])

    amenities = {}
    if amenity_ids:
        amenities = {
            item.id: item
            for item in db.scalars(select(Amenity).where(Amenity.id.in_(amenity_ids))).all()
        }

    dining = db.scalars(
        select(DiningService)
        .where(
            DiningService.property_id.in_(property_ids),
            DiningService.is_active.is_(True),
        )
        .order_by(DiningService.property_id, DiningService.service_index)
    ).all()
    dining_by_property: dict[str, list[DiningService]] = defaultdict(list)
    for item in dining:
        dining_by_property[item.property_id].append(item)
    return rooms_by_property, amenities, dining_by_property


def _amenity_names(rooms: list[Room], amenities: dict, language: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for room in rooms:
        for amenity_id in room.amenity_ids or []:
            amenity = amenities.get(amenity_id)
            if not amenity:
                continue
            name = amenity.name_vi if language == "vi" and amenity.name_vi else amenity.name_en
            if name not in seen:
                names.append(name)
                seen.add(name)
    return names


def _property_summary(
    item: Property,
    destination: Destination,
    rooms: list[Room],
    amenities: dict,
    language: str,
) -> PropertySummary:
    prices = [_valid_room_price(room) for room in rooms]
    known_prices = [(amount, currency) for amount, currency in prices if amount is not None]
    price_from, currency = min(known_prices, default=(None, None), key=lambda value: value[0] or 0)
    images = list(dict.fromkeys(room.image_url for room in rooms if room.image_url))
    summary = next((room.description for room in rooms if room.description), None)
    return PropertySummary(
        id=item.id,
        name=item.name,
        kind=item.kind,
        destination_id=item.destination_id,
        destination_name=_destination_name(destination, language),
        address=item.address,
        source_url=item.url,
        images=images[:6],
        room_count=len(rooms),
        max_guests=max((room.guest_count or 0 for room in rooms), default=0) or None,
        price_from=price_from,
        currency=currency,
        amenities=_amenity_names(rooms, amenities, language),
        summary=summary,
    )


@router.get("/destinations", response_model=list[DestinationSummary])
def list_destinations(
    lang: Literal["en", "vi", "ko", "ja", "zh"] = "en",
) -> list[DestinationSummary]:
    with open_session() as db:
        destinations = db.scalars(
            select(Destination).order_by(Destination.sort_order.nullslast(), Destination.name_en)
        ).all()
        property_counts = dict(
            db.execute(
                select(Property.destination_id, func.count(Property.id))
                .where(Property.is_active.is_(True))
                .group_by(Property.destination_id)
            ).all()
        )
        highlights = db.scalars(
            select(DestinationHighlight)
            .where(DestinationHighlight.is_active.is_(True))
            .order_by(DestinationHighlight.destination_id, DestinationHighlight.sort_order.nullslast())
        ).all()
        highlight_by_destination = {}
        for highlight in highlights:
            current = highlight_by_destination.get(highlight.destination_id)
            if current is None or (not current.image_url and highlight.image_url):
                highlight_by_destination[highlight.destination_id] = highlight

        destination_ids = [item.id for item in destinations]
        media_rows = db.execute(
            select(Media.entity_id, Media.url)
            .where(
                Media.entity_type == "destination",
                Media.entity_id.in_(destination_ids),
                Media.url.is_not(None),
            )
            .order_by(Media.entity_id, Media.sort_order.asc().nullslast())
        ).all()
        media_image_by_destination = {}
        for destination_id, image_url in media_rows:
            if image_url and destination_id not in media_image_by_destination:
                media_image_by_destination[destination_id] = image_url

        property_image_rows = db.execute(
            select(Property.destination_id, Room.image_url)
            .join(Room, Room.property_id == Property.id)
            .where(
                Property.is_active.is_(True),
                Room.is_active.is_(True),
                Room.image_url.is_not(None),
            )
            .order_by(Property.destination_id, Property.name, Room.room_index)
        ).all()
        room_image_by_destination = {}
        for destination_id, image_url in property_image_rows:
            if image_url and destination_id not in room_image_by_destination:
                room_image_by_destination[destination_id] = image_url

        return [
            DestinationSummary(
                id=item.id,
                name=_destination_name(item, lang),
                name_en=item.name_en,
                name_vi=item.name_vi,
                province=item.province,
                region=item.region,
                country=item.country,
                image_url=getattr(highlight_by_destination.get(item.id), "image_url", None)
                or media_image_by_destination.get(item.id)
                or room_image_by_destination.get(item.id),
                highlight=getattr(highlight_by_destination.get(item.id), "title", None),
                description=getattr(highlight_by_destination.get(item.id), "description", None),
                property_count=int(property_counts.get(item.id, 0)),
            )
            for item in destinations
            if property_counts.get(item.id, 0) > 0
        ]


@router.get("/properties", response_model=PropertyListResponse)
def list_properties(
    destination: str | None = None,
    kind: Literal["hotel", "resort"] | None = None,
    min_guests: int | None = Query(default=None, ge=1, le=30),
    max_price: float | None = Query(default=None, gt=0),
    lang: Literal["en", "vi", "ko", "ja", "zh"] = "en",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
) -> PropertyListResponse:
    with open_session() as db:
        stmt = select(Property).where(Property.is_active.is_(True))
        if destination and destination != "all":
            stmt = stmt.where(Property.destination_id == destination)
        if kind:
            stmt = stmt.where(Property.kind == kind)
        properties = db.scalars(stmt.order_by(Property.name)).all()
        destination_ids = {item.destination_id for item in properties}
        destinations = {
            item.id: item
            for item in db.scalars(select(Destination).where(Destination.id.in_(destination_ids))).all()
        }
        rooms_by_property, amenities, _ = _load_catalog_parts(
            db, [item.id for item in properties]
        )
        summaries = [
            _property_summary(
                item,
                destinations[item.destination_id],
                rooms_by_property.get(item.id, []),
                amenities,
                lang,
            )
            for item in properties
        ]
        if min_guests:
            summaries = [item for item in summaries if (item.max_guests or 0) >= min_guests]
        if max_price:
            summaries = [
                item
                for item in summaries
                if item.price_from is not None and item.currency == "USD" and item.price_from <= max_price
            ]
        total = len(summaries)
        start = (page - 1) * page_size
        return PropertyListResponse(
            items=summaries[start : start + page_size],
            page=page,
            page_size=page_size,
            total=total,
        )


@router.get("/properties/{property_id}", response_model=PropertyDetail)
def property_detail(
    property_id: str,
    lang: Literal["en", "vi", "ko", "ja", "zh"] = "en",
) -> PropertyDetail:
    with open_session() as db:
        item = db.get(Property, property_id)
        if item is None or not item.is_active:
            raise HTTPException(status_code=404, detail="Property not found")
        destination = db.get(Destination, item.destination_id)
        rooms_by_property, amenities, dining_by_property = _load_catalog_parts(db, [item.id])
        rooms = rooms_by_property.get(item.id, [])
        summary = _property_summary(item, destination, rooms, amenities, lang)
        room_items = []
        for room in rooms:
            price, currency = _valid_room_price(room)
            room_items.append(
                RoomSummary(
                    id=room.id,
                    name=room.name,
                    description=room.description,
                    guest_count=room.guest_count,
                    area_sqm=float(room.area_sqm) if room.area_sqm is not None else None,
                    price=price,
                    currency=currency,
                    price_is_approximate=room.price_is_approximate,
                    image_url=room.image_url,
                    amenities=_amenity_names([room], amenities, lang),
                    bed_types=room.bed_types or [],
                    has_wifi=room.has_wifi,
                    booking_url=room.page_url or item.room_page_url or item.url,
                )
            )
        dining_items = [
            DiningSummary(
                id=dining.id,
                name=dining.name,
                description=dining.description,
                hours=dining.hours_display or dining.hours_raw,
                contact=dining.contact_display or dining.contact_raw,
                image_url=dining.image_url,
            )
            for dining in dining_by_property.get(item.id, [])
        ]
        return PropertyDetail(
            **summary.model_dump(),
            room_page_url=item.room_page_url,
            dining_page_url=item.dining_page_url,
            rooms=room_items,
            dining=dining_items,
        )
