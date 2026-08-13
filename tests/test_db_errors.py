"""Kiểm chứng src/data_postgre/db/errors.py trên database thật.

Bỏ qua nếu Postgres chưa chạy, để pytest vẫn xanh trên máy chưa dựng database.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from src.backend.config import get_settings
from src.data_postgre.db import Complex, Destination, DestinationAlias, Property, Room
from src.data_postgre.db.errors import (
    CHECK_VIOLATION,
    FOREIGN_KEY_VIOLATION,
    UNIQUE_VIOLATION,
    constraint_name,
    describe,
    is_integrity_violation,
    sqlstate,
)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(get_settings().database_url)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - muốn skip với mọi lỗi kết nối
        pytest.skip(f"Postgres chưa chạy, bỏ qua: {exc}")
    return eng


def _purge(session: Session) -> None:
    """Xoá đúng dữ liệu test theo thứ tự ngược khoá ngoại trong schema core."""
    session.execute(text("DELETE FROM core.room WHERE id LIKE 't-%'"))
    session.execute(text("DELETE FROM core.property WHERE id LIKE 't-%'"))
    session.execute(text("DELETE FROM core.complex WHERE id LIKE 't-%'"))
    session.execute(
        text("DELETE FROM core.destination_alias WHERE destination_id LIKE 't-%'")
    )
    session.execute(text("DELETE FROM core.destination WHERE id LIKE 't-%'"))


@pytest.fixture
def seeded(engine):
    """Dựng chuỗi destination -> complex -> property -> room rồi dọn sạch sau."""
    with Session(engine) as s:
        _purge(s)
        for obj in (
            Destination(id="t-hoi-an", name_en="Hoi An", name_vi="Hội An"),
            DestinationAlias(
                destination_id="t-hoi-an", alias="Hội An", alias_normalized="t hoi an"
            ),
            Complex(
                id="t-nam-hoi-an",
                name="Nam Hoi An",
                destination_id="t-hoi-an",
                kind="united_center",
            ),
            Property(
                id="t-p1", name="Test Resort", kind="resort", destination_id="t-hoi-an"
            ),
            Room(id="t-p1--room-1", property_id="t-p1", room_index=1, name="Deluxe"),
        ):
            s.add(obj)
            s.flush()
        s.commit()
    yield engine
    with Session(engine) as s:
        _purge(s)
        s.commit()


def _capture(engine, obj) -> DBAPIError:
    with Session(engine) as s:
        s.add(obj)
        with pytest.raises(DBAPIError) as info:
            s.commit()
    return info.value


def test_check_violation_readable(seeded) -> None:
    exc = _capture(
        seeded, Room(id="t-bad", property_id="t-p1", room_index=9, name="X", guest_count=0)
    )
    assert sqlstate(exc) == CHECK_VIOLATION
    assert is_integrity_violation(exc)
    assert constraint_name(exc) == "ck_room_guest_count_positive"
    assert "CHECK" in describe(exc)


def test_foreign_key_violation_readable(seeded) -> None:
    exc = _capture(
        seeded, Room(id="t-bad2", property_id="khong-ton-tai", room_index=8, name="X")
    )
    assert sqlstate(exc) == FOREIGN_KEY_VIOLATION
    assert is_integrity_violation(exc)


def test_unique_violation_readable(seeded) -> None:
    exc = _capture(
        seeded,
        DestinationAlias(
            destination_id="t-hoi-an", alias="Hoi An", alias_normalized="t hoi an"
        ),
    )
    assert sqlstate(exc) == UNIQUE_VIOLATION
    assert is_integrity_violation(exc)


def test_sqlstate_returns_none_for_plain_exception() -> None:
    assert sqlstate(ValueError("khong phai loi database")) is None
    assert not is_integrity_violation(ValueError("x"))
