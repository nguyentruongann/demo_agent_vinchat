"""7 bảng ứng dụng — người dùng, hội thoại, ticket.

Nhóm này KHÔNG có nguồn trong data/; nó suy từ code hiện có:
src/api/routes.py, src/agents/state.py, src/services/ticket.py.

Thay thế storage/tickets.jsonl và storage/chat_history.jsonl.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    func,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

# AppBase mang schema 'app'; lớp CORE dùng Base mang schema 'core'. Đặt bí danh
# để 7 khai báo bảng bên dưới không phải đổi.
from src.data_postgre.db.base import AppBase as Base
from src.data_postgre.db.base import Timestamped

# none_as_null: Python None phải thành SQL NULL, không phải JSON 'null'.
# Mặc định của SQLAlchemy biến None thành JSON null (một scalar), khiến
# jsonb_array_length() báo 'cannot get array length of a scalar'.
JSONB_NULL = JSONB(none_as_null=True)


class AppUser(Base, Timestamped):
    """Anonymous-first: người dùng chưa đăng nhập vẫn có một dòng.

    Khi cần tài khoản thật thì điền email + password_hash vào đúng dòng đó,
    lịch sử chat không mất. Bảng tên app_user vì "user" là từ khoá của Postgres.
    """

    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    anon_id: Mapped[str | None] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    phone: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, server_default=text("'customer'"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    locale: Mapped[str] = mapped_column(
        Text, server_default=text("'vi'"), nullable=False
    )
    is_staff: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("role IN ('customer','staff','admin')", name="app_user_role_valid"),
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL OR anon_id IS NOT NULL", name="app_user_contact_or_anon"),
        # email is normalized by the API, and this functional UNIQUE index also
        # protects direct DB writes from case/whitespace variants.
        Index(
            "uq_app_user_email_normalized",
            func.lower(func.btrim(email)),
            unique=True,
            postgresql_where=text("email IS NOT NULL AND btrim(email) <> ''"),
        ),
        Index("ix_app_user_role", "role"),
    )


class AuthSession(Base, Timestamped):
    """Opaque bearer sessions. Only a SHA-256 hash of the token is stored."""

    __tablename__ = "auth_session"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_auth_session_user", "user_id"),
        Index("ix_auth_session_expires", "expires_at"),
    )


class ChatSession(Base, Timestamped):
    """Bảng "session".

    Tên class là ChatSession chứ không phải Session để không đụng
    sqlalchemy.orm.Session khi import.

    ``id`` do client sinh — khớp đúng ChatRequest.session_id đang có.
    """

    __tablename__ = "session"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    channel: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # UA + platform. Đừng lưu đủ chi tiết để fingerprint thiết bị.
    client_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB_NULL)

    __table_args__ = (
        CheckConstraint(
            "channel IS NULL OR channel IN ('web','api')", name="channel_valid"
        ),
    )


class Message(Base, Timestamped):
    """Nơi DUY NHẤT lưu nội dung thô.

    Chứa PII (khách sẽ gõ số điện thoại, mã đặt phòng), nên chính sách xoá và
    lưu trữ chỉ phải áp một chỗ. event_log không được lưu content.
    """

    __tablename__ = "message"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(Text)
    # Khớp RouteName trong src/agents/state.py
    route: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    finish_reason: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_message_session_seq"),
        CheckConstraint(
            "role IN ('user','assistant','system','tool')", name="role_valid"
        ),
        CheckConstraint(
            "route IS NULL OR route IN ('greeting','out_of_scope','rag')",
            name="route_valid",
        ),
        Index("ix_message_session_seq", "session_id", "seq"),
    )


class MessageCitation(Base):
    """Nguồn đã dùng để sinh câu trả lời.

    Hiện routes.py dựng SourceItem rồi vứt đi. Bảng này giữ lại — nền cho eval/.

    Trỏ entity_type + entity_id TRƯỚC, chunk_id sau: dùng được ngay khi chưa có
    lớp RAG, và không phải migrate khi có.
    """

    __tablename__ = "message_citation"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    chunk_id: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class MessageFeedback(Base, Timestamped):
    __tablename__ = "message_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("rating IN (-1, 1)", name="rating_valid"),
    )


class Ticket(Base, Timestamped):
    """Thay storage/tickets.jsonl. Giữ nguyên format id VP-XXXXXXXXXX."""

    __tablename__ = "ticket"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("session.id", ondelete="SET NULL")
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("message.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        Text, server_default=text("'open'"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    conversation_turns: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    assignee: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','in_progress','resolved','closed')", name="status_valid"
        ),
        CheckConstraint(
            "priority IS NULL OR priority IN ('low','normal','high')",
            name="priority_valid",
        ),
        Index("ix_ticket_status", "status"),
        Index("ix_ticket_assigned_to", "assigned_to"),
    )


class EventLog(Base):
    """Nhật ký vận hành.

    KHÔNG lưu content thô ở đây — chỉ độ dài và hash. Bảng này phình nhanh nhất
    và có giá trị lâu dài thấp nhất; cần script purge theo ts.
    """

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("session.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB_NULL)

    __table_args__ = (Index("ix_event_log_ts", "ts"),)