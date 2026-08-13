"""Đọc mã lỗi PostgreSQL độc lập với driver.

Vì sao cần: driver ``pg8000`` không ném đúng lớp ngoại lệ theo DB-API. Đã đo
trên chính lược đồ này:

===========================  ========  =========================
Vi phạm                      SQLSTATE  Lớp ngoại lệ SQLAlchemy
===========================  ========  =========================
UNIQUE / khoá chính trùng    23505     IntegrityError
CHECK                        23514     ProgrammingError
FOREIGN KEY                  23503     ProgrammingError
===========================  ========  =========================

Nghĩa là ``except IntegrityError`` sẽ **để lọt** mọi vi phạm CHECK và khoá ngoại —
đúng hai thứ mà lược đồ này dựa vào để chặn dữ liệu bẩn. Luôn bắt ``DBAPIError``
rồi phân nhánh bằng :func:`sqlstate`.

Các hàm ở đây đọc được mã lỗi từ cả pg8000, psycopg3 và psycopg2, nên nếu sau
này đổi driver thì script nạp dữ liệu không phải sửa.
"""

from __future__ import annotations

from typing import Any

# Mã SQLSTATE lớp 23 — vi phạm toàn vẹn dữ liệu.
NOT_NULL_VIOLATION = "23502"
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"


def _error_payload(exc: BaseException) -> Any:
    """Lấy ngoại lệ gốc của driver từ lớp bọc của SQLAlchemy."""
    return getattr(exc, "orig", exc)


def sqlstate(exc: BaseException) -> str | None:
    """Trả về mã SQLSTATE 5 ký tự, hoặc None nếu không phải lỗi database."""
    orig = _error_payload(exc)

    # psycopg3
    code = getattr(orig, "sqlstate", None)
    if code:
        return str(code)

    # psycopg2
    code = getattr(orig, "pgcode", None)
    if code:
        return str(code)

    # pg8000: args[0] là dict thông điệp lỗi của server, khoá 'C' là SQLSTATE
    args = getattr(orig, "args", None)
    if args and isinstance(args[0], dict):
        code = args[0].get("C")
        if code:
            return str(code)

    return None


def constraint_name(exc: BaseException) -> str | None:
    """Tên ràng buộc bị vi phạm — dùng để ghi vào data_quality_issue."""
    orig = _error_payload(exc)

    diag = getattr(orig, "diag", None)  # psycopg
    if diag is not None:
        name = getattr(diag, "constraint_name", None)
        if name:
            return str(name)

    args = getattr(orig, "args", None)  # pg8000: khoá 'n'
    if args and isinstance(args[0], dict):
        name = args[0].get("n")
        if name:
            return str(name)

    return None


def is_integrity_violation(exc: BaseException) -> bool:
    """True nếu là vi phạm toàn vẹn (SQLSTATE lớp 23).

    Dùng cái này thay cho ``isinstance(exc, IntegrityError)``.
    """
    code = sqlstate(exc)
    return bool(code) and code.startswith("23")


def describe(exc: BaseException) -> str:
    """Mô tả ngắn gọn để ghi log và data_quality_issue."""
    code = sqlstate(exc) or "?"
    name = constraint_name(exc)
    label = {
        NOT_NULL_VIOLATION: "thiếu giá trị bắt buộc",
        FOREIGN_KEY_VIOLATION: "khoá ngoại không tồn tại",
        UNIQUE_VIOLATION: "trùng khoá",
        CHECK_VIOLATION: "vi phạm CHECK",
    }.get(code, "lỗi database")
    return f"{label} [{code}]" + (f" trên {name}" if name else "")
