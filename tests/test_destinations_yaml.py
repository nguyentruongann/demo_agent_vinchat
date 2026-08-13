"""Kiểm thử tính toàn vẹn của master data địa danh.

Chạy được mà không cần database — chỉ đọc YAML và data/*.json.
"""

from __future__ import annotations

import pytest

from scripts.seed_destinations import (
    build_alias_index,
    collect_source_strings,
    load_yaml,
)
from src.data_postgre.normalize.text import normalize_alias

SPEC = load_yaml()


def test_every_destination_string_in_data_resolves() -> None:
    """Chuỗi địa danh mới trong data mà chưa có bí danh phải làm test đỏ.

    Đây là lưới an toàn quan trọng nhất của bước này: thiếu một bí danh thì cả
    nhánh dữ liệu đó âm thầm thành NULL chứ không báo lỗi gì.
    """
    index = build_alias_index(SPEC)
    skip = {normalize_alias(x) for x in SPEC["not_destinations"]}

    unresolved = {
        value: sorted(where)
        for value, where in collect_source_strings().items()
        if normalize_alias(value) not in index and normalize_alias(value) not in skip
    }
    assert not unresolved, (
        f"{len(unresolved)} chuỗi địa danh chưa có bí danh: {unresolved}. "
        "Thêm vào src/normalize/destinations.yaml."
    )


def test_no_alias_points_to_two_destinations() -> None:
    """build_alias_index tự nổ nếu mơ hồ; gọi ra đây cho rõ ý định."""
    assert build_alias_index(SPEC)


def test_complex_destinations_exist() -> None:
    ids = {d["id"] for d in SPEC["destinations"]}
    for c in SPEC["complexes"]:
        assert c["destination"] in ids, f"complex {c['id']} trỏ tới địa danh lạ"


def test_ids_are_unique() -> None:
    dest_ids = [d["id"] for d in SPEC["destinations"]]
    complex_ids = [c["id"] for c in SPEC["complexes"]]
    assert len(dest_ids) == len(set(dest_ids))
    assert len(complex_ids) == len(set(complex_ids))


def test_ids_are_valid_slugs() -> None:
    for item in SPEC["destinations"] + SPEC["complexes"]:
        assert item["id"] == normalize_alias(item["id"]).replace(" ", "-"), item["id"]


@pytest.mark.parametrize("field", ["name_en", "name_vi"])
def test_destinations_have_both_names(field: str) -> None:
    for d in SPEC["destinations"]:
        assert d.get(field), f"{d['id']} thiếu {field}"


def test_nationwide_is_not_a_destination() -> None:
    """'Nationwide' và 'Toàn quốc' phải nằm ngoài bảng destination."""
    index = build_alias_index(SPEC)
    for value in SPEC["not_destinations"]:
        assert normalize_alias(value) not in index


def test_non_vietnam_destination_declares_country() -> None:
    """Cape Wickham Golf Links ở Tasmania — country không được mặc định Vietnam."""
    tasmania = next(d for d in SPEC["destinations"] if d["id"] == "tasmania")
    assert tasmania["country"] == "Australia"
    assert tasmania["region"] is None


def test_nam_hoi_an_resolves_to_hoi_an() -> None:
    """Quyết định §15.1: Nam Hoi An là khu phức hợp nằm trong địa danh Hoi An.

    Thiếu bí danh này thì dữ liệu hotel/golf/mice không nối được vào hoi-an,
    vì chuỗi 'Hoi An' chỉ xuất hiện trong promotion.
    """
    index = build_alias_index(SPEC)
    assert index[normalize_alias("Nam Hoi An")] == "hoi-an"

    complex_ids = {c["id"] for c in SPEC["complexes"]}
    assert "nam-hoi-an" in complex_ids
