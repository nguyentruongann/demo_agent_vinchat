"""Chuẩn hoá chuỗi dùng chung cho toàn bộ pipeline nạp dữ liệu."""

from __future__ import annotations

import re
import unicodedata

# 'đ' không phải ký tự tổ hợp nên NFD không tách được dấu gạch ngang của nó.
# Phải ánh xạ tay, đúng như extension unaccent của Postgres đang làm:
# unaccent('Đà Nẵng') -> 'Da Nang'
_STROKED = str.maketrans({"đ": "d", "Đ": "D", "ð": "d", "Ð": "D"})

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))

_SMART_QUOTES = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"'}
)


def clean_text(value: str | None) -> str | None:
    """Làm sạch mọi chuỗi lấy từ file crawl.

    Đo được trên data/: 123.158 cụm nhiều khoảng trắng, 123.191 ký tự xuống dòng
    nằm trong chuỗi, 4.348 dấu nháy cong, 18 ký tự zero-width.

    NFC quan trọng với tiếng Việt: 'Phú' tổ hợp sẵn và 'Phú' tách dấu là hai
    chuỗi khác nhau khi so bằng ``==``, đủ để làm hỏng khử trùng và JOIN.
    """
    if value is None:
        return None
    s = unicodedata.normalize("NFC", value)
    s = s.translate(_ZERO_WIDTH).translate(_SMART_QUOTES)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def strip_accents(value: str) -> str:
    """Bỏ dấu tiếng Việt, cho kết quả giống ``unaccent()`` của Postgres."""
    s = value.translate(_STROKED)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", s)


def normalize_alias(value: str) -> str:
    """Khoá tra cứu địa danh: bỏ dấu, thường hoá, bỏ dấu câu.

    Đây là **hàm chuẩn duy nhất** cho ``destination_alias.alias_normalized``.
    Mọi phép tra địa danh — lúc nạp dữ liệu lẫn lúc agent tool nhận chuỗi từ
    người dùng — đều phải đi qua hàm này.

    KHÔNG tra bằng ``lower(unaccent(...))`` trong SQL: hàm này còn bỏ cả dấu câu
    và gạch nối nên kết quả sẽ lệch với Postgres.

        >>> normalize_alias("Thành phố Hồ Chí Minh")
        'thanh pho ho chi minh'
        >>> normalize_alias("ho-chi-minh-city")
        'ho chi minh city'
        >>> normalize_alias("Đà Nẵng")
        'da nang'
    """
    s = strip_accents(value).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def slugify(value: str) -> str:
    """Sinh slug ổn định cho khoá chính: 'Nam Hoi An' -> 'nam-hoi-an'."""
    return normalize_alias(value).replace(" ", "-")
