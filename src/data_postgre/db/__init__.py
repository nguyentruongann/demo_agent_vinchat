"""Tầng cơ sở dữ liệu: ORM model cho lược đồ CORE + ứng dụng.

Import ``Base`` (schema core) và ``AppBase`` (schema app) từ đây để Alembic
thấy đủ 41 bảng khi autogenerate.
Đặc tả đầy đủ: docs/DATABASE.md
"""

from src.data_postgre.db.app import (
    AppUser,
    AuthSession,
    ChatSession,
    EventLog,
    Message,
    MessageCitation,
    MessageFeedback,
    Ticket,
)
from src.data_postgre.db.base import AppBase, Base, Sourced, Timestamped, by_bare_name
from src.data_postgre.db.core import (
    Amenity,
    Attraction,
    Brand,
    Complex,
    DataQualityIssue,
    Destination,
    DestinationAlias,
    DestinationHighlight,
    DiningService,
    EntitySource,
    Faq,
    GolfCourse,
    GolfFeature,
    IngestRun,
    Media,
    MiceRoom,
    MiceRoomCapacity,
    MiceVenue,
    OrgHighlight,
    OrgInfo,
    PageLink,
    PolicyBlock,
    PolicyDocument,
    PolicySection,
    Promotion,
    PromotionBenefit,
    PromotionBlock,
    PromotionCode,
    PromotionDestination,
    PromotionPropertyRaw,
    PromotionRelation,
    PromotionSection,
    PromotionTerm,
    Property,
    Room,
    Source,
)

# Dung SAU khi core.py va app.py da import xong: luc base.py chay thi metadata
# con rong. Khoa la ten tran ('room'), khong phai 'core.room'.
CORE_TABLES = by_bare_name(Base.metadata)
APP_TABLES = by_bare_name(AppBase.metadata)

__all__ = [
    "Base",
    "AppBase",
    "CORE_TABLES",
    "APP_TABLES",
    "Sourced",
    "Timestamped",
    # vận hành
    "IngestRun",
    "DataQualityIssue",
    # trục dùng chung
    "Brand",
    "Source",
    "Destination",
    "DestinationAlias",
    "Complex",
    "Media",
    "EntitySource",
    "PageLink",
    # lưu trú
    "Property",
    "Room",
    "Amenity",
    "DiningService",
    # trải nghiệm
    "Attraction",
    "DestinationHighlight",
    # golf & mice
    "GolfCourse",
    "GolfFeature",
    "MiceVenue",
    "MiceRoom",
    "MiceRoomCapacity",
    # ưu đãi
    "Promotion",
    "PromotionBenefit",
    "PromotionSection",
    "PromotionBlock",
    "PromotionDestination",
    "PromotionCode",
    "PromotionPropertyRaw",
    "PromotionTerm",
    "PromotionRelation",
    # tri thức
    "Faq",
    "PolicyDocument",
    "PolicySection",
    "PolicyBlock",
    "OrgInfo",
    "OrgHighlight",
    # ứng dụng
    "AuthSession",
    "AppUser",
    "ChatSession",
    "Message",
    "MessageCitation",
    "MessageFeedback",
    "Ticket",
    "EventLog",
]