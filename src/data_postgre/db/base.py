"""Lớp nền cho toàn bộ ORM model.

Quy ước (xem docs/DATABASE.md §1):
- Khoá chính CORE là TEXT sinh tất định, không dùng autoincrement.
- Không dùng CREATE TYPE ... AS ENUM; dùng TEXT + CheckConstraint.
- Tiền dùng Numeric, không dùng float.
- Không DELETE dòng CORE; dòng biến mất khỏi website thì is_active = false.
- Bảng nằm trong schema ``core`` hoặc ``app``, không nằm trong ``public``.

Hai điểm cần biết trước khi viết script nạp dữ liệu (chi tiết ở docs/DATABASE.md §16.1):

1. Model cố ý KHÔNG khai báo relationship(), vì đường ghi chính là bulk upsert chứ không
   phải unit-of-work. Hệ quả: Session.flush() không tự sắp thứ tự INSERT theo khoá ngoại —
   phải chèn theo thứ tự bảng tường minh. Lược đồ không có vòng phụ thuộc nên có thể lấy
   thứ tự từ Base.metadata.sorted_tables.

2. Driver pg8000 ném ProgrammingError (không phải IntegrityError) cho vi phạm CHECK và
   FOREIGN KEY. Bắt sqlalchemy.exc.DBAPIError rồi phân nhánh theo SQLSTATE.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, MetaData, Table, Text, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Đặt tên ràng buộc theo khuôn mẫu để Alembic sinh migration ổn định.
# Thiếu phần này, ràng buộc do Postgres tự đặt tên và autogenerate sẽ tạo ra
# diff giả mỗi lần chạy.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Hai schema thay vì 41 bảng nằm phẳng trong public.
#
# core = dữ liệu nghiệp vụ + vận hành nạp;  app = hội thoại, ticket, nhật ký.
# Hai bên KHÔNG có khoá ngoại sang nhau: message_citation trỏ vào lớp CORE bằng
# (entity_type, entity_id) dạng text, cố ý không ràng buộc. Nhờ vậy tách được
# thành hai MetaData độc lập mà không sinh phụ thuộc vòng.
#
# Đặt schema ở MetaData chứ không ở từng bảng: mọi ForeignKey("source.id") viết
# không kèm schema vẫn tự phân giải về đúng schema mặc định của MetaData đó.
CORE_SCHEMA = "core"
APP_SCHEMA = "app"


class Base(DeclarativeBase):
    """Bảng lớp CORE — schema ``core``."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=CORE_SCHEMA)


class AppBase(DeclarativeBase):
    """Bảng lớp ứng dụng — schema ``app``."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=APP_SCHEMA)


class Timestamped:
    """created_at / updated_at cho mọi bảng."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Sourced(Timestamped):
    """Cột kiểm toán cho thực thể CORE.

    ``source_id`` là *nguồn chính*; thực thể có nhiều nguồn thì phần còn lại
    nằm ở bảng ``entity_source`` (Luật 10).

    ``ingest_run_id`` cho phép quét dòng đã biến mất: sau khi nạp xong, mọi dòng
    còn mang run_id cũ nghĩa là lần crawl này không thấy nó nữa.
    """

    @declared_attr
    def source_id(cls) -> Mapped[str | None]:  # noqa: N805
        return mapped_column(Text, ForeignKey("source.id", ondelete="SET NULL"))

    @declared_attr
    def ingest_run_id(cls) -> Mapped[int | None]:  # noqa: N805
        return mapped_column(ForeignKey("ingest_run.id", ondelete="SET NULL"))

    content_hash: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), nullable=False
    )


def pk_text() -> Mapped[str]:
    """Khoá chính TEXT sinh tất định."""
    return mapped_column(Text, primary_key=True)


def by_bare_name(metadata: MetaData) -> dict[str, Table]:
    """Tra bảng theo tên trần, ví dụ ``"room"`` thay vì ``"core.room"``.

    Từ khi MetaData mang schema, khoá của ``metadata.tables`` có tiền tố schema.
    Nhưng tên trần là *định danh nghiệp vụ* dùng khắp nơi ngoài lược đồ: khoá của
    ``Context.rows``, ``entity_type`` trong media/entity_source/message_citation,
    và INTENT_ENTITY_TYPES của query_parser. Đổi chúng theo schema sẽ làm hỏng
    trích dẫn đã lưu, nên lớp tra này giữ tên trần ở đúng một chỗ.

    Gọi SAU khi mọi model đã import xong — trong file này metadata còn rỗng.
    src/data_postgre/db/__init__.py dựng CORE_TABLES và APP_TABLES từ đây.
    """
    return {t.name: t for t in metadata.sorted_tables}
