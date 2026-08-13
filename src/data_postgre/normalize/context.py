"""Ngữ cảnh dùng chung khi nạp dữ liệu: gom dòng, tra địa danh, ghi nhận lỗi."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.data_postgre.db import CORE_TABLES
from src.data_postgre.normalize.common import domain_of, html_filename, language_from_url, stable_id
from src.data_postgre.normalize.text import clean_text, normalize_alias

# Thương hiệu trong hệ sinh thái, lấy từ source_brand và related_brands của promotion.
BRANDS: dict[str, str] = {
    "vinpearl": "Vinpearl",
    "vinwonders": "VinWonders",
    "vinpearl_safari": "Vinpearl Safari",
    "vinpearl_golf": "Vinpearl Golf",
    "grand_world": "Grand World",
    "vinclub": "VinClub",
    "myvinpearl": "MyVinpearl",
}

_DOMAIN_BRAND = {"vinpearl.com": "vinpearl", "vinwonders.com": "vinwonders"}


@dataclass
class Issue:
    severity: str
    rule: str
    entity_type: str | None = None
    entity_id: str | None = None
    source_file: str | None = None
    json_path: str | None = None
    field: str | None = None
    raw_value: str | None = None
    message: str | None = None


class Rows:
    """Gom dòng theo bảng, tự gộp khi trùng khoá chính.

    Gộp là bắt buộc chứ không phải tiện tay: cùng một ``amenity`` xuất hiện ở 100+
    phòng, cùng một ``source`` ở hàng chục bản ghi. Nếu để trùng, Postgres từ chối
    cả câu lệnh với lỗi *"ON CONFLICT DO UPDATE command cannot affect row a second
    time"*.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[tuple, dict[str, Any]]] = {}
        self._pk_cache: dict[str, list[str]] = {}

    def _pk(self, table: str) -> list[str]:
        if table not in self._pk_cache:
            self._pk_cache[table] = [
                c.name for c in CORE_TABLES[table].primary_key.columns
            ]
        return self._pk_cache[table]

    def add(self, table: str, row: dict[str, Any]) -> None:
        key = tuple(row[c] for c in self._pk(table))
        bucket = self._data.setdefault(table, {})
        if key in bucket:
            # Giá trị mới chỉ ghi đè khi có nội dung — cho phép hai adapter cùng
            # bồi vào một dòng (org_info nhận thông tin công ty từ about, nhận
            # đoạn giới thiệu MICE từ event).
            for field_name, value in row.items():
                if value is not None:
                    bucket[key][field_name] = value
        else:
            bucket[key] = dict(row)

    def get(self, table: str) -> list[dict[str, Any]]:
        return list(self._data.get(table, {}).values())

    def tables(self) -> list[str]:
        return list(self._data)

    def counts(self) -> dict[str, int]:
        return {t: len(v) for t, v in sorted(self._data.items())}


@dataclass
class Context:
    """Trạng thái dùng chung cho tất cả adapter."""

    alias_to_destination: dict[str, str]
    alias_to_complex: dict[str, str]
    nationwide: set[str]
    rows: Rows = field(default_factory=Rows)
    issues: list[Issue] = field(default_factory=list)
    source_file: str = ""

    # -- ghi nhận lỗi -----------------------------------------------------

    def issue(self, severity: str, rule: str, **kwargs: Any) -> None:
        raw = kwargs.pop("raw_value", None)
        self.issues.append(
            Issue(
                severity=severity,
                rule=rule,
                source_file=kwargs.pop("source_file", self.source_file),
                raw_value=None if raw is None else str(raw)[:500],
                **kwargs,
            )
        )

    # -- tra địa danh -----------------------------------------------------

    def destination(
        self, raw: str | None, *, json_path: str, entity_type: str | None = None
    ) -> str | None:
        """Tra địa danh qua bảng bí danh.

        Chuỗi không khớp phải nổi lên thành issue — nếu để nó âm thầm thành NULL
        thì mất cả nhánh dữ liệu mà không ai biết.
        """
        text = clean_text(raw)
        if not text:
            return None
        key = normalize_alias(text)
        if key in self.nationwide:
            return None
        found = self.alias_to_destination.get(key)
        if found is None:
            self.issue(
                "error",
                "destination.unknown_alias",
                entity_type=entity_type,
                json_path=json_path,
                raw_value=text,
                message="Thêm bí danh vào src/normalize/destinations.yaml",
            )
        return found

    def is_nationwide(self, raw: str | None) -> bool:
        text = clean_text(raw)
        return bool(text) and normalize_alias(text) in self.nationwide

    def complex(self, raw: str | None) -> str | None:
        text = clean_text(raw)
        return self.alias_to_complex.get(normalize_alias(text)) if text else None

    # -- nguồn ------------------------------------------------------------

    def source(
        self,
        url: str | None,
        *,
        canonical: str | None = None,
        crawled_at: Any = None,
        http_status: int | None = None,
        is_404: bool = False,
        html_file: str | None = None,
        content_hash: str | None = None,
    ) -> str | None:
        """Đăng ký một URL và trả về ``source.id``. Gọi lại cùng URL thì gộp."""
        clean_url = clean_text(url)
        if not clean_url or not clean_url.startswith("http"):
            return None
        source_id = stable_id("source", clean_text(canonical) or clean_url)
        domain = domain_of(clean_url)
        self.rows.add(
            "source",
            {
                "id": source_id,
                "url": clean_url,
                "canonical_url": clean_text(canonical) or clean_url,
                "domain": domain,
                "brand_id": _DOMAIN_BRAND.get(domain or ""),
                "source_language": language_from_url(clean_url),
                "http_status": http_status,
                "is_404": is_404,
                "crawled_at": crawled_at,
                "content_hash": content_hash,
                "html_filename": html_filename(html_file),
            },
        )
        return source_id

    # -- ảnh --------------------------------------------------------------

    def media(
        self,
        entity_type: str,
        entity_id: str,
        url: str | None,
        *,
        role: str = "gallery",
        alt: str | None = None,
        sort_order: int | None = None,
    ) -> None:
        clean_url = clean_text(url)
        if not clean_url or not clean_url.startswith("http"):
            return
        self.rows.add(
            "media",
            {
                "id": stable_id("media", entity_type, entity_id, clean_url),
                "entity_type": entity_type,
                "entity_id": entity_id,
                "url": clean_url,
                "role": role,
                "alt": clean_text(alt),
                "sort_order": sort_order,
            },
        )

    def link(
        self,
        from_source_id: str | None,
        to_url: str | None,
        *,
        anchor: str | None = None,
        is_internal: bool | None = None,
        context: str | None = None,
    ) -> None:
        clean_url = clean_text(to_url)
        if not from_source_id or not clean_url or not clean_url.startswith("http"):
            return
        self.rows.add(
            "page_link",
            {
                "id": stable_id("page_link", from_source_id, clean_url, context or ""),
                "from_source_id": from_source_id,
                "to_url": clean_url,
                "to_source_id": None,
                "anchor_text": clean_text(anchor),
                "is_internal": is_internal,
                "context": context,
            },
        )
