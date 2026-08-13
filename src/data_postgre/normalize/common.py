"""Hàm phân tích dùng chung cho mọi adapter.

Mỗi hàm trả về cả **giá trị đã parse** lẫn **lý do thất bại**, để adapter ghi được
một dòng ``data_quality_issue`` thay vì nuốt lỗi. Xem docs/DATABASE.md Luật 3 và 9.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

from src.data_postgre.normalize.text import clean_text

# --------------------------------------------------------------------------
# Khoá chính tất định
# --------------------------------------------------------------------------


def stable_id(entity_type: str, *parts: object) -> str:
    """Sinh khoá chính tất định.

    Chạy lại pipeline phải ra đúng id cũ, nếu không ``message_citation`` và
    ``chunk`` trỏ tới sẽ mồ côi.
    """
    payload = "|".join([entity_type, *(str(p) for p in parts)])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# Tiền
# --------------------------------------------------------------------------

_CURRENCY = {"USD": "USD", "VND": "VND", "VNĐ": "VND", "Đ": "VND", "D": "VND"}
_MONEY = re.compile(
    r"(?P<approx>~)?\s*(?P<num>\d[\d.,]*)\s*(?P<cur>USD|VND|VNĐ|đ|Đ)", re.IGNORECASE
)


@dataclass(frozen=True)
class Money:
    amount: Decimal | None
    currency: str | None
    is_approximate: bool
    failure: str | None


def _to_decimal(num: str) -> Decimal | None:
    """Xử lý dấu phân tách nghìn kiểu châu Âu lẫn kiểu Anh–Mỹ.

    '1.944' và '1,944' đều là **một nghìn chín trăm bốn tư**, không phải 1,944.
    Quy tắc: dấu phân tách theo sau đúng 3 chữ số thì là phân tách nghìn;
    ít hơn thì là dấu thập phân.
    """
    num = num.strip()
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", num):
        return Decimal(re.sub(r"[.,]", "", num))
    if re.fullmatch(r"\d+[.,]\d{1,2}", num):
        return Decimal(num.replace(",", "."))
    if re.fullmatch(r"\d+", num):
        return Decimal(num)
    try:
        return Decimal(re.sub(r"[.,]", "", num))
    except InvalidOperation:
        return None


def parse_money(raw: str | None) -> Money:
    """Đọc giá tiền từ chuỗi thô.

    Ca thật trong data:

        >>> parse_money("~ 131USD").amount
        Decimal('131')
        >>> parse_money("~ 1.944USD").amount     # dấu chấm = phân tách nghìn
        Decimal('1944')
        >>> parse_money("tel:1900232389").failure
        'no_currency_pattern'

    69/116 phòng có ``standard_rate.raw = "tel:1900232389"`` — crawler bắt nhầm
    link hotline thành giá. Chúng rơi vào nhánh ``no_currency_pattern``.
    """
    text = clean_text(raw)
    if not text:
        return Money(None, None, False, "empty")

    match = _MONEY.search(text)
    if not match:
        return Money(None, None, False, "no_currency_pattern")

    amount = _to_decimal(match.group("num"))
    if amount is None:
        return Money(None, None, False, "unparseable_number")

    currency = _CURRENCY.get(match.group("cur").upper())
    return Money(amount, currency, "~" in text, None)


# --------------------------------------------------------------------------
# Diện tích, kích thước
# --------------------------------------------------------------------------

_NUMBER = re.compile(r"\d[\d.,]*")


def parse_area(raw: str | None) -> Decimal | None:
    """Diện tích tính bằng m².

        >>> parse_area("42 m²")
        Decimal('42')
        >>> parse_area("1250m 2")      # ký tự ² bị tách thành ' 2'
        Decimal('1250')

    Số '2' cuối chuỗi ``'1250m 2'`` là ký tự mũ bị hỏng chứ không phải giá trị,
    nên chỉ lấy số ĐẦU TIÊN.
    """
    text = clean_text(raw)
    if not text:
        return None
    match = _NUMBER.search(text)
    return _to_decimal(match.group()) if match else None


_DIMENSIONS = re.compile(r"(\d[\d.,]*)\s*m\s*[x×]\s*(\d[\d.,]*)\s*m", re.IGNORECASE)
_CEILING = re.compile(r"ceiling\s+height[^0-9]*(\d[\d.,]*)", re.IGNORECASE)


def _to_decimal_metric(num: str) -> Decimal | None:
    """Số đo bằng mét: dấu phẩy và dấu chấm LUÔN là dấu thập phân.

    Ngược hẳn với tiền. ``'1,944USD'`` là một nghìn chín trăm bốn tư, nhưng
    ``'Dimensions: 22,839m x 12,938m'`` là 22,8 m × 12,9 m — không phòng hội nghị
    nào rộng 22 km. Cùng một khuôn mẫu, hai ngữ nghĩa trái ngược; chỉ ngữ cảnh
    mới phân biệt được, nên không dùng chung hàm với parse_money.
    """
    try:
        return Decimal(num.strip().replace(",", "."))
    except InvalidOperation:
        return None


def parse_specifications(specs: list[str] | None) -> dict[str, Decimal | None]:
    """Đọc mảng specifications của phòng hội nghị.

        >>> parse_specifications(["Dimensions: 50m x 25m", "Ceiling height: 7m"])
        {'length_m': Decimal('50'), 'width_m': Decimal('25'), 'ceiling_height_m': Decimal('7')}
    """
    out: dict[str, Decimal | None] = {
        "length_m": None,
        "width_m": None,
        "ceiling_height_m": None,
    }
    for spec in specs or []:
        text = clean_text(spec) or ""
        if dim := _DIMENSIONS.search(text):
            out["length_m"] = _to_decimal_metric(dim.group(1))
            out["width_m"] = _to_decimal_metric(dim.group(2))
        if ceil := _CEILING.search(text):
            out["ceiling_height_m"] = _to_decimal_metric(ceil.group(1))
    return out


def normalize_language(raw: str | None) -> str | None:
    """Rút mã ngôn ngữ về đúng 2 ký tự.

    Nguồn dùng lẫn ``'en'`` và ``'en-US'``; cột ``content_language`` là CHAR(2)
    nên ``'en-US'`` làm Postgres từ chối cả dòng với SQLSTATE 22001.
    """
    text = clean_text(raw)
    if not text:
        return None
    primary = re.split(r"[-_]", text)[0].lower()
    return primary if primary in {"vi", "en"} else None


def parse_int(raw: object) -> int | None:
    """Ép số nguyên từ chuỗi. ``capacities`` trong data lưu số dưới dạng string."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    text = clean_text(str(raw))
    if not text:
        return None
    match = _NUMBER.search(text)
    if not match:
        return None
    value = _to_decimal(match.group())
    return int(value) if value is not None else None


# --------------------------------------------------------------------------
# Ngày giờ
# --------------------------------------------------------------------------

_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_iso_date(raw: object) -> date | None:
    """Đọc ngày ISO. Toàn bộ 96 giá trị ngày trong data đều đúng khuôn YYYY-MM-DD."""
    if isinstance(raw, date):
        return raw
    text = clean_text(str(raw)) if raw is not None else None
    if not text:
        return None
    match = _ISO_DATE.search(text)
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


_TIME = re.compile(r"(\d{1,2})[:h](\d{2})\s*(AM|PM)?", re.IGNORECASE)


def parse_time_range(raw: str | None) -> tuple[time | None, time | None]:
    """Lấy cặp giờ mở – đóng đầu tiên trong chuỗi.

        >>> parse_time_range("17:30 - 22:00 (Last order 21:30)")
        (datetime.time(17, 30), datetime.time(22, 0))

    Nhiều nhà hàng ghi nhiều khung giờ ('Breakfast: … Lunch: …'); ta chỉ lấy cặp
    đầu và luôn giữ nguyên chuỗi gốc ở ``hours_raw``.
    """
    text = clean_text(raw)
    if not text:
        return None, None

    found: list[time] = []
    for match in _TIME.finditer(text):
        hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3)
        if meridiem:
            upper = meridiem.upper()
            if upper == "PM" and hour != 12:
                hour += 12
            elif upper == "AM" and hour == 12:
                hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            found.append(time(hour, minute))
        if len(found) == 2:
            break
    if len(found) == 2:
        return found[0], found[1]
    return (found[0], None) if found else (None, None)


# --------------------------------------------------------------------------
# URL và đường dẫn
# --------------------------------------------------------------------------


def language_from_url(url: str | None) -> str | None:
    """Suy ngôn ngữ từ path, KHÔNG lấy từ field ``language`` của file.

    nha-trang.json khai ``language: "en"`` nhưng chứa 945 URL ``/vi/`` so với
    127 URL ``/en/``: nội dung đã dịch, còn link thì vẫn trỏ trang tiếng Việt.
    """
    if not url:
        return None
    parts = urlparse(url).path.strip("/").split("/")
    return parts[0] if parts and parts[0] in {"vi", "en"} else None


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def html_filename(path: str | None) -> str | None:
    """Chỉ giữ tên file, bỏ đường dẫn máy người khác.

    32 chỗ trong data chứa ``D:\\vinuni\\T013\\data_crawl\\...`` hoặc ``/mnt/data/...``.
    Chúng không được lộ ra ngoài trong bất kỳ trích dẫn nào.
    """
    text = clean_text(path)
    if not text:
        return None
    name = PureWindowsPath(text).name if "\\" in text else PurePosixPath(text).name
    return name or None


def first_url(*candidates: str | None) -> str | None:
    for value in candidates:
        text = clean_text(value)
        if text and text.startswith("http"):
            return text
    return None
