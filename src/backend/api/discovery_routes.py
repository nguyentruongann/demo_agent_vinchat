from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import exists, func, literal, select, union_all

from src.backend.models.discovery import (
    AttractionDetail,
    AttractionListResponse,
    AttractionSummary,
    DiscoveryDestination,
    GolfDetail,
    GolfFeatureSummary,
    GolfListResponse,
    GolfSummary,
    MiceCapacitySummary,
    MiceRoomSummary,
    MiceVenueDetail,
    MiceVenueListResponse,
    MiceVenueSummary,
)
from src.backend.services.db import open_session
from src.data_postgre.db.core import (
    Attraction,
    Destination,
    GolfCourse,
    GolfFeature,
    Media,
    MiceRoom,
    MiceRoomCapacity,
    MiceVenue,
    Room,
    Source,
)

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])

Language = Literal["en", "vi", "ko", "ja", "zh"]
AttractionKind = Literal[
    "park", "show", "game", "event", "experience", "journey", "itinerary"
]
MiceLayout = Literal[
    "theater", "classroom", "u_shape", "boardroom", "banquet", "cocktail"
]


def _destination_name(destination: Destination, language: str) -> str:
    return destination.name_vi if language == "vi" else destination.name_en


def _load_media_first(
    db, entity_type: str, entity_ids: list[str]
) -> dict[str, str]:
    """First media URL per entity, used as an image fallback."""
    if not entity_ids:
        return {}
    rows = db.execute(
        select(Media.entity_id, Media.url)
        .where(Media.entity_type == entity_type, Media.entity_id.in_(entity_ids))
        .order_by(Media.entity_id, Media.sort_order.nullslast(), Media.id)
    ).all()
    first: dict[str, str] = {}
    for entity_id, url in rows:
        first.setdefault(entity_id, url)
    return first


def _destination_options(db, entity, language: str) -> list[DiscoveryDestination]:
    rows = db.execute(
        select(Destination)
        .join(entity, entity.destination_id == Destination.id)
        .where(entity.is_active.is_(True))
        .distinct()
        .order_by(Destination.sort_order.nullslast(), Destination.name_en)
    ).scalars()
    return [
        DiscoveryDestination(id=item.id, name=_destination_name(item, language))
        for item in rows
    ]


def _load_mice_images(db, venue_ids: list[str]) -> dict[str, str]:
    """Load preferred media/room fallback images for all venues in one query."""
    if not venue_ids:
        return {}

    media_candidates = select(
        Media.entity_id.label("venue_id"),
        Media.url.label("url"),
        literal(0).label("priority"),
        Media.sort_order.label("sort_order"),
        Media.id.label("candidate_id"),
    ).where(
        Media.entity_type == "mice_venue",
        Media.entity_id.in_(venue_ids),
    )
    room_candidates = select(
        Room.property_id.label("venue_id"),
        Room.image_url.label("url"),
        literal(1).label("priority"),
        Room.room_index.label("sort_order"),
        Room.id.label("candidate_id"),
    ).where(
        Room.property_id.in_(venue_ids),
        Room.is_active.is_(True),
        Room.image_url.is_not(None),
    )
    candidates = union_all(media_candidates, room_candidates).subquery(
        "mice_image_candidates"
    )
    rows = db.execute(
        select(candidates.c.venue_id, candidates.c.url).order_by(
            candidates.c.venue_id,
            candidates.c.priority,
            candidates.c.sort_order.nullslast(),
            candidates.c.candidate_id,
        )
    ).all()
    first: dict[str, str] = {}
    for venue_id, url in rows:
        first.setdefault(venue_id, url)
    return first


def _attraction_summary(
    item: Attraction,
    destination: Destination,
    source: Source | None,
    language: str,
) -> AttractionSummary:
    return AttractionSummary(
        id=item.id,
        title=item.title,
        kind=item.kind,
        destination_id=item.destination_id,
        destination_name=_destination_name(destination, language),
        summary=item.summary or item.description,
        image_url=item.image_url,
        duration_label=item.duration_label,
        detail_url=item.detail_url,
        source_url=source.url if source else None,
    )


@router.get("/attractions", response_model=AttractionListResponse)
def list_attractions(
    destination: str | None = None,
    kind: AttractionKind | None = None,
    lang: Language = "en",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
) -> AttractionListResponse:
    with open_session() as db:
        filters = [Attraction.is_active.is_(True)]
        if destination and destination != "all":
            filters.append(Attraction.destination_id == destination)
        if kind:
            filters.append(Attraction.kind == kind)

        total = int(
            db.scalar(select(func.count(Attraction.id)).where(*filters)) or 0
        )
        rows = db.execute(
            select(Attraction, Destination, Source)
            .join(Destination, Destination.id == Attraction.destination_id)
            .outerjoin(Source, Source.id == Attraction.source_id)
            .where(*filters)
            .order_by(
                Destination.sort_order.nullslast(),
                Attraction.sort_order.nullslast(),
                Attraction.title,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        kinds = list(
            db.scalars(
                select(Attraction.kind)
                .where(Attraction.is_active.is_(True))
                .distinct()
                .order_by(Attraction.kind)
            )
        )
        return AttractionListResponse(
            items=[
                _attraction_summary(item, destination_row, source, lang)
                for item, destination_row, source in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
            kinds=kinds,
            destinations=_destination_options(db, Attraction, lang),
        )


@router.get("/attractions/{attraction_id}", response_model=AttractionDetail)
def attraction_detail(
    attraction_id: str,
    lang: Language = "en",
) -> AttractionDetail:
    with open_session() as db:
        row = db.execute(
            select(Attraction, Destination, Source)
            .join(Destination, Destination.id == Attraction.destination_id)
            .outerjoin(Source, Source.id == Attraction.source_id)
            .where(
                Attraction.id == attraction_id,
                Attraction.is_active.is_(True),
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Attraction not found")
        item, destination, source = row
        summary = _attraction_summary(item, destination, source, lang)
        return AttractionDetail(
            **summary.model_dump(),
            description=item.description,
            full_text=item.full_text,
            location_text=item.location_text,
            section_title=item.section_title,
            topic_group=item.topic_group,
            detail_status=item.detail_status,
            duration_days=item.duration_days,
            duration_nights=item.duration_nights,
            itinerary=item.itinerary or [],
        )


def _golf_feature_summary(item: GolfFeature) -> GolfFeatureSummary:
    return GolfFeatureSummary(
        id=item.id,
        kind=item.kind,
        title=item.title,
        description=item.description,
        image_url=item.image_url,
        detail_url=item.detail_url,
        variant=item.variant,
    )


def _golf_summary(
    item: GolfCourse,
    destination: Destination,
    source: Source | None,
    features: list[GolfFeature],
    language: str,
    media_url: str | None = None,
) -> GolfSummary:
    return GolfSummary(
        id=item.id,
        name=item.name,
        destination_id=item.destination_id,
        destination_name=_destination_name(destination, language),
        summary=item.summary,
        image_url=next(
            (feature.image_url for feature in features if feature.image_url),
            media_url,
        ),
        designer=item.designer,
        holes=item.holes,
        par=item.par,
        page_url=item.page_url or (source.url if source else None),
        feature_count=len(features),
    )


def _load_golf_features(db, course_ids: list[str]) -> dict[str, list[GolfFeature]]:
    grouped: dict[str, list[GolfFeature]] = defaultdict(list)
    if not course_ids:
        return grouped
    features = db.scalars(
        select(GolfFeature)
        .where(
            GolfFeature.course_id.in_(course_ids),
            GolfFeature.is_active.is_(True),
        )
        .order_by(
            GolfFeature.course_id,
            GolfFeature.sort_order.nullslast(),
            GolfFeature.title,
        )
    ).all()
    for feature in features:
        grouped[feature.course_id].append(feature)
    return grouped


@router.get("/golf", response_model=GolfListResponse)
def list_golf_courses(
    destination: str | None = None,
    lang: Language = "en",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
) -> GolfListResponse:
    with open_session() as db:
        filters = [GolfCourse.is_active.is_(True)]
        if destination and destination != "all":
            filters.append(GolfCourse.destination_id == destination)
        total = int(db.scalar(select(func.count(GolfCourse.id)).where(*filters)) or 0)
        rows = db.execute(
            select(GolfCourse, Destination, Source)
            .join(Destination, Destination.id == GolfCourse.destination_id)
            .outerjoin(Source, Source.id == GolfCourse.source_id)
            .where(*filters)
            .order_by(Destination.sort_order.nullslast(), GolfCourse.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        features_by_course = _load_golf_features(
            db, [course.id for course, _destination, _source in rows]
        )
        media_by_course = _load_media_first(
            db, "golf_course", [course.id for course, _destination, _source in rows]
        )
        return GolfListResponse(
            items=[
                _golf_summary(
                    course,
                    destination_row,
                    source,
                    features_by_course.get(course.id, []),
                    lang,
                    media_url=media_by_course.get(course.id),
                )
                for course, destination_row, source in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
            destinations=_destination_options(db, GolfCourse, lang),
        )


@router.get("/golf/{course_id}", response_model=GolfDetail)
def golf_course_detail(course_id: str, lang: Language = "en") -> GolfDetail:
    with open_session() as db:
        row = db.execute(
            select(GolfCourse, Destination, Source)
            .join(Destination, Destination.id == GolfCourse.destination_id)
            .outerjoin(Source, Source.id == GolfCourse.source_id)
            .where(GolfCourse.id == course_id, GolfCourse.is_active.is_(True))
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Golf course not found")
        course, destination, source = row
        features = _load_golf_features(db, [course.id]).get(course.id, [])
        media_url = _load_media_first(db, "golf_course", [course.id]).get(course.id)
        summary = _golf_summary(course, destination, source, features, lang, media_url)
        return GolfDetail(
            **summary.model_dump(),
            course_length=course.course_length_raw,
            total_area=course.total_area,
            terrain=course.terrain,
            full_address=course.full_address,
            city=course.city,
            district=course.district,
            island=course.island,
            features=[_golf_feature_summary(item) for item in features],
        )


def _load_mice_rooms(
    db,
    venue_ids: list[str],
) -> tuple[dict[str, list[MiceRoom]], dict[str, list[MiceRoomCapacity]]]:
    rooms_by_venue: dict[str, list[MiceRoom]] = defaultdict(list)
    capacities_by_room: dict[str, list[MiceRoomCapacity]] = defaultdict(list)
    if not venue_ids:
        return rooms_by_venue, capacities_by_room
    rows = db.execute(
        select(MiceRoom, MiceRoomCapacity)
        .outerjoin(MiceRoomCapacity, MiceRoomCapacity.room_id == MiceRoom.id)
        .where(MiceRoom.venue_id.in_(venue_ids), MiceRoom.is_active.is_(True))
        .order_by(
            MiceRoom.venue_id,
            MiceRoom.sort_order.nullslast(),
            MiceRoom.name,
            MiceRoomCapacity.layout,
        )
    ).all()
    seen_rooms: set[str] = set()
    for room, capacity in rows:
        if room.id not in seen_rooms:
            rooms_by_venue[room.venue_id].append(room)
            seen_rooms.add(room.id)
        if capacity is not None:
            capacities_by_room[capacity.room_id].append(capacity)
    return rooms_by_venue, capacities_by_room


def _mice_summary(
    venue: MiceVenue,
    destination: Destination,
    source: Source | None,
    rooms: list[MiceRoom],
    capacities_by_room: dict[str, list[MiceRoomCapacity]],
    language: str,
    media_url: str | None = None,
) -> MiceVenueSummary:
    capacities = [
        capacity.pax
        for room in rooms
        for capacity in capacities_by_room.get(room.id, [])
    ]
    return MiceVenueSummary(
        id=venue.id,
        name=venue.name,
        destination_id=venue.destination_id,
        destination_name=_destination_name(destination, language),
        subtitle=venue.subtitle,
        summary=venue.summary,
        address=venue.address,
        phone=venue.phone,
        source_url=venue.url or (source.url if source else None),
        image_url=next(
            (room.image_url for room in rooms if room.image_url),
            media_url,
        ),
        room_count=len(rooms),
        max_capacity=max(capacities, default=None),
    )


def _mice_room_summary(
    room: MiceRoom,
    capacities: list[MiceRoomCapacity],
) -> MiceRoomSummary:
    return MiceRoomSummary(
        id=room.id,
        name=room.name,
        description=room.description,
        area_sqm=float(room.area_sqm) if room.area_sqm is not None else None,
        area_raw=room.area_raw,
        length_m=float(room.length_m) if room.length_m is not None else None,
        width_m=float(room.width_m) if room.width_m is not None else None,
        ceiling_height_m=(
            float(room.ceiling_height_m) if room.ceiling_height_m is not None else None
        ),
        specifications=room.specifications_raw or [],
        image_url=room.image_url,
        capacities=[
            MiceCapacitySummary(layout=item.layout, pax=item.pax)
            for item in capacities
        ],
    )


@router.get("/mice", response_model=MiceVenueListResponse)
def list_mice_venues(
    destination: str | None = None,
    layout: MiceLayout | None = None,
    min_capacity: int | None = Query(default=None, ge=1, le=10000),
    lang: Language = "en",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
) -> MiceVenueListResponse:
    with open_session() as db:
        filters = [MiceVenue.is_active.is_(True)]
        if destination and destination != "all":
            filters.append(MiceVenue.destination_id == destination)
        if layout or min_capacity:
            capacity_filters = [
                MiceRoom.venue_id == MiceVenue.id,
                MiceRoom.is_active.is_(True),
            ]
            if layout:
                capacity_filters.append(MiceRoomCapacity.layout == layout)
            if min_capacity:
                capacity_filters.append(MiceRoomCapacity.pax >= min_capacity)
            filters.append(
                exists(
                    select(MiceRoomCapacity.room_id)
                    .join(MiceRoom, MiceRoom.id == MiceRoomCapacity.room_id)
                    .where(*capacity_filters)
                )
            )
        total = int(db.scalar(select(func.count(MiceVenue.id)).where(*filters)) or 0)
        rows = db.execute(
            select(MiceVenue, Destination, Source)
            .join(Destination, Destination.id == MiceVenue.destination_id)
            .outerjoin(Source, Source.id == MiceVenue.source_id)
            .where(*filters)
            .order_by(Destination.sort_order.nullslast(), MiceVenue.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        venue_ids = [venue.id for venue, _destination, _source in rows]
        rooms_by_venue, capacities_by_room = _load_mice_rooms(db, venue_ids)
        images_by_venue = _load_mice_images(db, venue_ids)
        return MiceVenueListResponse(
            items=[
                _mice_summary(
                    venue,
                    destination_row,
                    source,
                    rooms_by_venue.get(venue.id, []),
                    capacities_by_room,
                    lang,
                    media_url=images_by_venue.get(venue.id),
                )
                for venue, destination_row, source in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
            destinations=_destination_options(db, MiceVenue, lang),
        )


@router.get("/mice/{venue_id}", response_model=MiceVenueDetail)
def mice_venue_detail(venue_id: str, lang: Language = "en") -> MiceVenueDetail:
    with open_session() as db:
        row = db.execute(
            select(MiceVenue, Destination, Source)
            .join(Destination, Destination.id == MiceVenue.destination_id)
            .outerjoin(Source, Source.id == MiceVenue.source_id)
            .where(MiceVenue.id == venue_id, MiceVenue.is_active.is_(True))
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="MICE venue not found")
        venue, destination, source = row
        rooms_by_venue, capacities_by_room = _load_mice_rooms(db, [venue.id])
        rooms = rooms_by_venue.get(venue.id, [])
        media_url = _load_mice_images(db, [venue.id]).get(venue.id)
        summary = _mice_summary(
            venue,
            destination,
            source,
            rooms,
            capacities_by_room,
            lang,
            media_url,
        )
        return MiceVenueDetail(
            **summary.model_dump(),
            overview=venue.overview,
            rooms=[
                _mice_room_summary(room, capacities_by_room.get(room.id, []))
                for room in rooms
            ],
        )
