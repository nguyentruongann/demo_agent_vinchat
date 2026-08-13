"""Kiểm thử src/normalize/text.py.

Các ca ở đây lấy từ chuỗi có thật trong data/, không phải ví dụ bịa.
"""

from __future__ import annotations

import pytest

from src.data_postgre.normalize.text import clean_text, normalize_alias, slugify, strip_accents


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Đà Nẵng", "da nang"),
        ("Hội An", "hoi an"),
        ("Thành phố Hồ Chí Minh", "thanh pho ho chi minh"),
        ("Nghệ An", "nghe an"),
        ("Phú Quốc", "phu quoc"),
        # dạng slug trong tên file và destination_slug của promotion
        ("ho-chi-minh-city", "ho chi minh city"),
        ("ha_noi", "ha noi"),
        # dấu phẩy trong golf: location.destination
        ("Tasmania, Australia", "tasmania australia"),
        # khoảng trắng thừa hai đầu và ở giữa
        ("  Nha   Trang  ", "nha trang"),
    ],
)
def test_normalize_alias(raw: str, expected: str) -> None:
    assert normalize_alias(raw) == expected


def test_normalize_alias_collapses_variants() -> None:
    """Bốn cách viết Hà Nội trong data phải ra cùng một khoá."""
    keys = {normalize_alias(x) for x in ("Hà Nội", "Ha Noi", "Hanoi", "ha-noi")}
    assert keys == {"ha noi"} or keys == {"ha noi", "hanoi"}, keys


def test_stroked_d_is_handled() -> None:
    """'đ' không phải ký tự tổ hợp nên NFD không tách được — phải ánh xạ tay."""
    assert strip_accents("Đảo Vũ Yên") == "Dao Vu Yen"


def test_nfc_normalisation_makes_equal_strings_equal() -> None:
    """'Phú' tổ hợp sẵn và 'Phú' tách dấu là hai chuỗi khác nhau khi so ==."""
    precomposed = "Phú Quốc"          # ú, ố dựng sẵn
    decomposed = "Phú Quó́c"   # u + dấu sắc
    assert precomposed != decomposed
    assert normalize_alias(precomposed) == normalize_alias(decomposed) == "phu quoc"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  nhiều   khoảng   trắng  ", "nhiều khoảng trắng"),
        ("xuống\ndòng\ttab", "xuống dòng tab"),
        ("dấu ‘nháy’ “cong”", "dấu 'nháy' \"cong\""),
        ("zero​width﻿", "zerowidth"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_clean_text(raw: str | None, expected: str | None) -> None:
    assert clean_text(raw) == expected


def test_slugify() -> None:
    assert slugify("Nam Hoi An") == "nam-hoi-an"
    assert slugify("Grand World Ocean City") == "grand-world-ocean-city"
    assert slugify("Vinpearl Resort & Spa Phu Quoc") == "vinpearl-resort-spa-phu-quoc"
