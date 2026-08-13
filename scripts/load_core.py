"""Nạp toàn bộ data/*.json đã làm sạch vào lớp CORE.

    python -m scripts.load_core                 # nạp thật
    python -m scripts.load_core --dry-run       # chỉ đếm, không ghi DB
    python -m scripts.load_core --dump build/   # xuất JSONL để soi bằng mắt

Idempotent: khoá chính sinh tất định + ``INSERT ... ON CONFLICT DO UPDATE``,
nên chạy bao nhiêu lần cũng ra một kết quả.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from src.backend.config import get_settings
from src.data_postgre.db import Base, CORE_TABLES, DataQualityIssue, IngestRun
from src.data_postgre.db.errors import describe, sqlstate
from src.data_postgre.normalize.adapters import entertainment, hotels, promotions, simple
from src.data_postgre.normalize.context import BRANDS, Context, Issue
from src.data_postgre.normalize.text import normalize_alias
YAML_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "data_postgre"
    / "normalize"
    / "destinations.yaml"
)


def build_context() -> Context:
    spec = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    ctx = Context(
        alias_to_destination={
            normalize_alias(a): d["id"] for d in spec["destinations"] for a in d["aliases"]
        },
        alias_to_complex={
            normalize_alias(a): c["id"] for c in spec["complexes"] for a in c["aliases"]
        },
        nationwide={normalize_alias(x) for x in spec["not_destinations"]},
    )
    for brand_id, name in BRANDS.items():
        ctx.rows.add("brand", {"id": brand_id, "name": name, "website": None})
    return ctx


def run_adapters(ctx: Context) -> None:
    # Thu tu quan trong: mice va about doi chieu ten khach san nen phai chay sau hotels.
    hotels.parse(ctx)
    promotions.parse(ctx)
    entertainment.parse(ctx)
    simple.parse(ctx)


def load_order(tables: list[str]) -> list[str]:
    """Sắp bảng theo phụ thuộc khoá ngoại.

    Model cố ý không khai ``relationship()`` nên ``Session.flush`` KHÔNG tự sắp
    thứ tự INSERT — phải lấy từ metadata (docs/DATABASE.md §16.1).
    """
    ordered = [t.name for t in Base.metadata.sorted_tables]
    return [t for t in ordered if t in set(tables)]


def upsert(session: Session, table_name: str, rows: list[dict[str, Any]],
           run_id: int, issues: list[Issue]) -> int:
    """Upsert theo lô; lô nào lỗi thì thử lại từng dòng để khoanh đúng dòng hỏng."""
    if not rows:
        return 0
    table = CORE_TABLES[table_name]
    columns = {c.name for c in table.columns}
    pk = [c.name for c in table.primary_key.columns]
    if "ingest_run_id" in columns:
        for row in rows:
            row["ingest_run_id"] = run_id
    payload = [{k: v for k, v in row.items() if k in columns} for row in rows]

    # Bọc lô trong SAVEPOINT: lô hỏng chỉ huỷ tới điểm lưu, không giết giao dịch
    # ngoài. Dùng session.rollback() ở đây sẽ đóng luôn transaction và mọi bảng
    # sau đó chết theo với "Can't operate on closed transaction".
    batch = session.begin_nested()
    try:
        _execute(session, table, payload, pk)
        batch.commit()
        return len(payload)
    except DBAPIError:
        batch.rollback()

    written = 0
    for row in payload:
        savepoint = session.begin_nested()
        try:
            _execute(session, table, [row], pk)
            savepoint.commit()
            written += 1
        except DBAPIError as exc:
            savepoint.rollback()
            issues.append(Issue(
                severity="error",
                rule=f"db.{sqlstate(exc) or 'unknown'}",
                entity_type=table_name,
                entity_id=str(row.get(pk[0])) if pk else None,
                message=describe(exc),
                raw_value=json.dumps(row, default=str, ensure_ascii=False)[:500],
            ))
    return written


def sweep_stale(session: Session, table_names: list[str], run_id: int) -> dict[str, int]:
    """Đánh dấu dòng lần crawl này không còn thấy nữa.

    Không DELETE: ``message_citation`` và ``chunk`` có thể đang trỏ tới. Dòng biến
    mất khỏi website chỉ chuyển ``is_active = false`` (docs/DATABASE.md §1).

    Chỉ quét bảng mà lần chạy này thực sự có ghi, để một lần nạp thiếu nguồn không
    vô tình vô hiệu hoá cả bảng khác.
    """
    swept: dict[str, int] = {}
    for name in table_names:
        table = CORE_TABLES[name]
        columns = {c.name for c in table.columns}
        if not {"ingest_run_id", "is_active", "updated_at"} <= columns:
            continue

        stale_predicate = table.c.is_active.is_(True) & (
            table.c.ingest_run_id.is_(None) | (table.c.ingest_run_id != run_id)
        )
        result = session.execute(
            table.update()
            .where(stale_predicate)
            .values(is_active=False, updated_at=datetime.now(UTC))
        )
        if result.rowcount:
            swept[name] = result.rowcount
    return swept


def _execute(session: Session, table: Any, payload: list[dict[str, Any]],
             pk: list[str]) -> None:
    stmt = insert(table).values(payload)
    updatable = {
        c.name: stmt.excluded[c.name]
        for c in table.columns
        if c.name not in pk and c.name != "created_at"
    }
    if updatable:
        stmt = stmt.on_conflict_do_update(index_elements=pk, set_=updatable)
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=pk)
    session.execute(stmt)


def git_sha() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001 - khong co git thi bo qua
        return None


def dump(ctx: Context, folder: str) -> None:
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    for table_name in sorted(ctx.rows.tables()):
        path = target / f"{table_name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in ctx.rows.get(table_name):
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    print(f"Đã xuất {len(ctx.rows.tables())} file vào {target}/")


def report(ctx: Context) -> None:
    counts = ctx.rows.counts()
    width = max(len(t) for t in counts) if counts else 20
    print(f"\n{'BẢNG':<{width}}  SỐ DÒNG")
    for table_name, n in counts.items():
        print(f"  {table_name:<{width}} {n:>7}")
    print(f"  {'TỔNG':<{width}} {sum(counts.values()):>7}")

    if ctx.issues:
        by_rule: dict[str, int] = {}
        for issue in ctx.issues:
            by_rule[f"{issue.severity}/{issue.rule}"] = by_rule.get(
                f"{issue.severity}/{issue.rule}", 0) + 1
        print(f"\nVẤN ĐỀ CHẤT LƯỢNG ({len(ctx.issues)})")
        for rule, n in sorted(by_rule.items(), key=lambda kv: -kv[1]):
            print(f"  {rule:<40} {n:>5}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="không ghi vào database")
    parser.add_argument("--dump", metavar="THƯ_MỤC", help="xuất JSONL để soi bằng mắt")
    args = parser.parse_args()

    ctx = build_context()
    run_adapters(ctx)
    report(ctx)

    if args.dump:
        dump(ctx, args.dump)
    if args.dry_run:
        print("\n--dry-run: không ghi gì vào database.")
        return 0

    engine = create_engine(get_settings().database_url)

    # Ket noi rieng cho nhat ky: issue phai song sot ke ca khi lan nap bi rollback.
    with Session(engine) as log_session:
        run = IngestRun(status="running", started_at=datetime.now(UTC),
                        git_sha=git_sha())
        log_session.add(run)
        log_session.commit()
        run_id = run.id

    issues = list(ctx.issues)
    written: dict[str, int] = {}
    status = "success"
    note: str | None = None

    swept: dict[str, int] = {}
    try:
        with Session(engine) as session, session.begin():
            tables = load_order(ctx.rows.tables())
            for table_name in tables:
                written[table_name] = upsert(
                    session, table_name, ctx.rows.get(table_name), run_id, issues
                )
            swept = sweep_stale(session, tables, run_id)
    except Exception as exc:  # noqa: BLE001 - ghi lai roi nem tiep
        status, note = "failed", str(exc)[:2000]

    with Session(engine) as log_session:
        log_session.add_all([
            DataQualityIssue(ingest_run_id=run_id, severity=i.severity, rule=i.rule,
                             entity_type=i.entity_type, entity_id=i.entity_id,
                             source_file=i.source_file, json_path=i.json_path,
                             field=i.field, raw_value=i.raw_value, message=i.message)
            for i in issues
        ])
        run = log_session.get(IngestRun, run_id)
        if run is None:
            raise RuntimeError(f"Không tìm thấy core.ingest_run id={run_id}")
        run.status = status
        run.finished_at = datetime.now(UTC)
        run.stats = written
        run.notes = note
        log_session.commit()

    if swept:
        print("\nDÒNG KHÔNG CÒN THẤY (đánh dấu is_active = false)")
        for table_name, n in sorted(swept.items()):
            print(f"  {table_name:<28} {n:>5}")

    print(f"\nLần nạp #{run_id}: {status} · {sum(written.values())} dòng "
          f"· {len(issues)} vấn đề đã ghi")
    if note:
        print(f"  {note}")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
