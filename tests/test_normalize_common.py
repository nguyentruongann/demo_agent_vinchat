"""Kiểm thử src/normalize/common.py.

Mọi ca đầu vào ở đây đều là chuỗi có thật lấy từ data/, không phải ví dụ bịa.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from src.data_postgre.normalize.common import (
    domain_of,
    html_filename,
    language_from_url,
    parse_area,
    parse_int,
    parse_iso_date,
    parse_money,
    parse_specifications,
    parse_time_range,
    stable_id,
)

# --------------------------------------------------------------------------
# Tiền — ba ca nhọn
# --------------------------------------------------------------------------


def test_money_simple() -> None:
    m = parse_money("~ 131USD")
    assert m.amount == Decimal("131")
    assert m.currency == "USD"
    assert m.is_approximate is True
    assert m.failure is None


def test_money_thousand_separator_is_not_decimal_point() -> None:
    """'~ 1.944USD' là 1944 USD, không phải 1,944 USD. Sai chỗ này là lệch 1000 lần."""
    assert parse_money("~ 1.944USD").amount == Decimal("1944")
    assert parse_money("1,944USD").amount == Decimal("1944")


def test_money_rejects_hotline_mistaken_for_price() -> None:
    """69/116 phòng có standard_rate.raw = 'tel:1900232389'."""
    m = parse_money("tel:1900232389")
    assert m.amount is None
    assert m.currency is None
    assert m.failure == "no_currency_pattern"


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_money_empty(raw: str | None) -> None:
    assert parse_money(raw).failure == "empty"


def test_money_currency_from_raw_when_field_is_null() -> None:
    """Nguồn để currency = null ở 100% dòng nhưng raw luôn ghi rõ đơn vị."""
    assert parse_money("~ 126USD").currency == "USD"
    assert parse_money("1.500.000 VND").currency == "VND"
    assert parse_money("1.500.000 VND").amount == Decimal("1500000")


def test_money_decimal_point_still_works() -> None:
    """Chỉ 3 chữ số sau dấu mới là phân tách nghìn."""
    assert parse_money("12.5USD").amount == Decimal("12.5")


# --------------------------------------------------------------------------
# Diện tích và kích thước
# --------------------------------------------------------------------------


def test_area_hotel_room() -> None:
    assert parse_area("37 m²") == Decimal("37")


def test_area_mice_room_with_broken_superscript() -> None:
    """'1250m 2' — số 2 là ký tự mũ bị tách, không phải giá trị."""
    assert parse_area("1250m 2") == Decimal("1250")
    assert parse_area("209m 2") == Decimal("209")


def test_area_empty() -> None:
    assert parse_area(None) is None
    assert parse_area("") is None


def test_specifications() -> None:
    out = parse_specifications(["Dimensions: 50m x 25m", "Ceiling height: 7m"])
    assert out == {
        "length_m": Decimal("50"),
        "width_m": Decimal("25"),
        "ceiling_height_m": Decimal("7"),
    }


def test_specifications_missing_fields() -> None:
    assert parse_specifications([]) == {
        "length_m": None,
        "width_m": None,
        "ceiling_height_m": None,
    }
    assert parse_specifications(None)["length_m"] is None


def test_parse_int_from_string_capacity() -> None:
    """capacities lưu số dưới dạng chuỗi: {'Theater': '1065'}."""
    assert parse_int("1065") == 1065
    assert parse_int(600) == 600
    assert parse_int("") is None
    assert parse_int(None) is None
    assert parse_int("khong phai so") is None


# --------------------------------------------------------------------------
# Ngày giờ
# --------------------------------------------------------------------------


def test_iso_date() -> None:
    assert parse_iso_date("2026-10-10") == date(2026, 10, 10)
    assert parse_iso_date(None) is None
    assert parse_iso_date("khong co ngay") is None


def test_iso_date_rejects_impossible_day() -> None:
    assert parse_iso_date("2026-02-31") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("17:30 - 22:00 (Last order 21:30)", (time(17, 30), time(22, 0))),
        ("6:00 - 22:00", (time(6, 0), time(22, 0))),
        ("16:00 - 23:00", (time(16, 0), time(23, 0))),
        ("Breakfast: 6:00AM - 10:30AM Lunch: 12:00PM", (time(6, 0), time(10, 30))),
    ],
)
def test_time_range(raw: str, expected: tuple[time, time]) -> None:
    assert parse_time_range(raw) == expected


def test_time_range_empty() -> None:
    assert parse_time_range("") == (None, None)
    assert parse_time_range(None) == (None, None)


# --------------------------------------------------------------------------
# URL
# --------------------------------------------------------------------------


def test_language_from_url() -> None:
    assert language_from_url("https://vinpearl.com/vi/combo-vinpearl") == "vi"
    assert language_from_url("https://vinpearl.com/en/hotels/x") == "en"
    assert language_from_url("https://booking.vinpearl.com/") is None
    assert language_from_url(None) is None


def test_domain_of() -> None:
    assert domain_of("https://www.vinwonders.com/en/tata-show/") == "vinwonders.com"
    assert domain_of("https://vinpearl.com/vi/x") == "vinpearl.com"
    assert domain_of(None) is None


def test_html_filename_strips_other_peoples_paths() -> None:
    """32 chỗ trong data lộ đường dẫn máy người khác — không được để lọt ra ngoài."""
    assert html_filename(r"D:\vinuni\T013\data_crawl\html\ha-noi.html") == "ha-noi.html"
    assert html_filename("/mnt/data/grand_park.html") == "grand_park.html"
    assert html_filename(None) is None


# --------------------------------------------------------------------------
# Khoá chính
# --------------------------------------------------------------------------


def test_stable_id_is_deterministic() -> None:
    a = stable_id("room", "https://x", 1)
    b = stable_id("room", "https://x", 1)
    assert a == b and len(a) == 16


def test_stable_id_differs_by_entity_type() -> None:
    assert stable_id("room", "x") != stable_id("attraction", "x")
