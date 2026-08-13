"""Nạp master data địa danh vào database.

    python -m scripts.seed_destinations           # nạp (upsert, chạy lại vô hại)
    python -m scripts.seed_destinations --check   # chỉ đối chiếu, không ghi

``--check`` quét mọi chuỗi địa danh có thật trong data/*.json rồi báo chuỗi nào
chưa có bí danh. Chạy nó mỗi lần crawler cập nhật: một chuỗi mới không khớp sẽ
âm thầm thành NULL nếu không ai để ý.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.backend.config import get_settings
from src.data_postgre.db import Complex, Destination, DestinationAlias
from src.data_postgre.normalize.text import normalize_alias

YAML_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "data_postgre"
    / "normalize"
    / "destinations.yaml"
)

def load_yaml() -> dict[str, Any]:
    with YAML_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_alias_index(spec: dict[str, Any]) -> dict[str, str]:
    """alias đã chuẩn hoá -> destination_id. Nổ ngay nếu có bí danh mơ hồ."""
    index: dict[str, str] = {}
    for dest in spec["destinations"]:
        for alias in dest["aliases"]:
            key = normalize_alias(alias)
            if key in index and index[key] != dest["id"]:
                raise SystemExit(
                    f"Bí danh mơ hồ: {alias!r} -> {key!r} trỏ về cả "
                    f"{index[key]!r} lẫn {dest['id']!r}"
                )
            index[key] = dest["id"]
    return index


def collect_source_strings() -> dict[str, set[str]]:
    """Mọi chuỗi địa danh có thật trong data/, kèm nơi nó xuất hiện."""
    hits: dict[str, set[str]] = defaultdict(set)

    for path in glob.glob("data/promotion/*.json"):
        for promo in json.load(open(path, encoding="utf-8"))["promotions"]:
            for value in promo.get("destinations") or []:
                hits[value].add("promotion")

    hotels = json.load(
        open("data/hotel/vinpearl_hotel_room_dining_rag.json", encoding="utf-8")
    )
    for hotel in hotels["hotels"]:
        hits[hotel["location_name"]].add("hotel")

    for course in json.load(open("data/golf/golf.json", encoding="utf-8"))["golf_courses"]:
        hits[course["location"]["destination"]].add("golf")

    for venue in json.load(
        open("data/event/vinpearl_mice_rag_en.json", encoding="utf-8")
    )["venues"]:
        hits[venue["destination"]].add("mice")

    for path in glob.glob("data/entertainment/*.json"):
        dest = json.load(open(path, encoding="utf-8")).get("destination") or {}
        for key in ("city", "province"):
            if dest.get(key):
                hits[dest[key]].add("entertainment")

    return hits


def check(spec: dict[str, Any]) -> int:
    index = build_alias_index(spec)
    skip = {normalize_alias(x) for x in spec["not_destinations"]}
    hits = collect_source_strings()

    matched = {v for v in hits if normalize_alias(v) in index}
    skipped = {v for v in hits if normalize_alias(v) in skip}
    missing = {v: w for v, w in hits.items() if v not in matched and v not in skipped}

    print(f"Chuỗi địa danh trong data/  : {len(hits)}")
    print(f"  khớp được bí danh         : {len(matched)}")
    print(f"  cố ý bỏ qua (toàn quốc)   : {len(skipped)}")
    print(f"  chưa có bí danh           : {len(missing)}")

    if missing:
        print(f"\nTHIẾU BÍ DANH ({len(missing)}):")
        for value, where in sorted(missing.items()):
            print(f"  {value!r}  (xuất hiện ở: {', '.join(sorted(where))})")
        print("\nThêm chúng vào src/normalize/destinations.yaml rồi chạy lại.")
        return 1

    print("\nMọi chuỗi địa danh trong data/ đều khớp được.")
    return 0


def seed(spec: dict[str, Any]) -> int:
    engine = create_engine(get_settings().database_url)

    dest_rows = [
        {
            "id": d["id"],
            "name_en": d["name_en"],
            "name_vi": d["name_vi"],
            "province": d.get("province"),
            "region": d.get("region"),
            "country": d.get("country", "Vietnam"),
            "has_content": d.get("has_content", False),
            "sort_order": i,
        }
        for i, d in enumerate(spec["destinations"])
    ]

    # Nhiều biến thể của cùng một địa danh chuẩn hoá ra y hệt nhau — 'Hà Nội',
    # 'Ha Noi', 'ha_noi', 'ha-noi' đều thành 'ha noi'. YAML cố ý liệt kê đủ để
    # người review thấy biến thể nào đã được phủ, nên phải khử trùng ở đây;
    # nếu không, Postgres từ chối cả câu lệnh với lỗi
    # "ON CONFLICT DO UPDATE command cannot affect row a second time".
    alias_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    collapsed = 0
    for d in spec["destinations"]:
        for alias in d["aliases"]:
            key = (d["id"], normalize_alias(alias))
            if key in seen:
                collapsed += 1
                continue
            seen.add(key)
            alias_rows.append(
                {
                    "destination_id": d["id"],
                    "alias": alias,
                    "alias_normalized": key[1],
                    "origin": "manual",
                }
            )

    complex_rows = [
        {
            "id": c["id"],
            "name": c["name"],
            "destination_id": c["destination"],
            "kind": c["kind"],
            "summary": c.get("summary"),
        }
        for c in spec["complexes"]
    ]

    def upsert(session: Session, model, rows: list[dict[str, Any]], keys: list[str]) -> None:
        if not rows:
            return
        stmt = insert(model).values(rows)
        updatable = {
            c.name: stmt.excluded[c.name]
            for c in model.__table__.columns
            if c.name not in keys and c.name != "created_at"
        }
        session.execute(stmt.on_conflict_do_update(index_elements=keys, set_=updatable))

    # Thu tu bat buoc: destination -> alias + complex. Model khong khai
    # relationship() nen flush KHONG tu sap xep (docs/DATABASE.md §16.1).
    with Session(engine) as session, session.begin():
        upsert(session, Destination, dest_rows, ["id"])
        upsert(session, DestinationAlias, alias_rows, ["destination_id", "alias_normalized"])
        upsert(session, Complex, complex_rows, ["id"])

    with Session(engine) as session:
        counts = {
            "destination": session.scalar(select(func.count()).select_from(Destination)),
            "destination_alias": session.scalar(
                select(func.count()).select_from(DestinationAlias)
            ),
            "complex": session.scalar(select(func.count()).select_from(Complex)),
        }
    total_aliases = sum(len(d["aliases"]) for d in spec["destinations"])
    print(f"  bí danh khai trong YAML  {total_aliases}")
    print(f"  gộp trùng sau chuẩn hoá  {collapsed}")
    for name, n in counts.items():
        print(f"  {name:<24} {n}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="chỉ đối chiếu với data/, không ghi DB"
    )
    args = parser.parse_args()

    spec = load_yaml()
    build_alias_index(spec)  # phát hiện bí danh mơ hồ dù chạy chế độ nào

    if args.check:
        return check(spec)
    return seed(spec)


if __name__ == "__main__":
    sys.exit(main())
