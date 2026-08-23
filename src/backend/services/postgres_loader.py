"""FULL PostgreSQL -> RAG loader for P-013.

Goal
----
Use 100% of normalized PostgreSQL BUSINESS/CORE data as the RAG corpus.

This loader intentionally does NOT cherry-pick only a few entity tables.
It walks every SQLAlchemy CORE table, every row and every non-null column,
adds FK labels/source URLs when possible, then turns the row into one or
more deterministic Chroma documents.

Excluded on purpose:
- Alembic internal table (not in SQLAlchemy Base.metadata anyway)
- ingest_run, data_quality_issue: ETL/quality-control metadata
- app_user, session, message, message_citation, message_feedback,
  ticket, event_log: application/runtime/user data, not Vinpearl knowledge

All other normalized CORE tables are included.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, select

from src.backend.config import get_settings
from src.backend.services.text_chunker import chunk_text
from src.data_postgre.db import CORE_TABLES

# ---------------------------------------------------------------------------
# Coverage policy
# ---------------------------------------------------------------------------

TECHNICAL_TABLES = {
    "ingest_run",
    "data_quality_issue",
}

APP_RUNTIME_TABLES = {
    "app_user",
    "session",
    "message",
    "message_citation",
    "message_feedback",
    "ticket",
    "event_log",
}

EXCLUDED_TABLES = TECHNICAL_TABLES | APP_RUNTIME_TABLES

# Prefer human-readable fields in this order when naming a row/reference.
LABEL_COLUMNS = (
    "product_name",
    "name",
    "title",
    "question",
    "headline",
    "heading",
    "alias",
    "code",
    "url",
    "name_vi",
    "name_en",
    "text",
    "description",
)

# URL-like fields are useful as citation metadata.
URL_COLUMNS = (
    "source_url",
    "url",
    "canonical_url",
    "page_url",
    "detail_url",
    "booking_url",
    "booking_search_url",
    "cart_url",
    "terms_url",
    "room_page_url",
    "dining_page_url",
    "map_url",
    "target_url",
    "to_url",
)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_value(value: Any) -> str:
    """Serialize every non-null SQL value without silently dropping data."""
    if value is None:
        return ""

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return format(value, "f")

    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)

    return str(value).strip()


def _humanize(column_name: str) -> str:
    return column_name.replace("_", " ").strip().capitalize()


def _row_label(row: dict[str, Any]) -> str:
    for column in LABEL_COLUMNS:
        value = row.get(column)
        if value not in (None, ""):
            return _format_value(value)

    # destination is more useful as VN/EN name than an opaque id.
    vi = row.get("name_vi")
    en = row.get("name_en")
    if vi or en:
        return _format_value(vi or en)

    return ""


def _primary_key_text(table, row: dict[str, Any]) -> str:
    parts: list[str] = []
    for column in table.primary_key.columns:
        parts.append(f"{column.name}={_format_value(row.get(column.name))}")

    if parts:
        return "|".join(parts)

    # Defensive fallback; CORE models should all have PKs.
    raw = json.dumps(row, ensure_ascii=False, default=str, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _document_id(table_name: str, pk_text: str, chunk_index: int) -> str:
    stable = hashlib.sha1(f"{table_name}|{pk_text}".encode()).hexdigest()
    return f"pg:{table_name}:{stable}:{chunk_index}"


def _direct_urls(row: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for column in URL_COLUMNS:
        value = row.get(column)
        if value:
            text_value = _format_value(value)
            if text_value and text_value not in urls:
                urls.append(text_value)
    return urls


def _get_rows(connection, table) -> list[dict[str, Any]]:
    return [dict(r) for r in connection.execute(select(table)).mappings().all()]


# ---------------------------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------------------------

def _build_indexes(all_rows: dict[str, list[dict[str, Any]]]):
    """Build labels and source URLs so FK-only rows become meaningful text."""
    labels: dict[str, dict[str, str]] = defaultdict(dict)
    source_urls: dict[str, str] = {}

    for table_name, rows in all_rows.items():
        table = CORE_TABLES[table_name]
        pk_columns = list(table.primary_key.columns)

        # Single-column PK tables are enough for normal FK resolution.
        if len(pk_columns) == 1:
            pk_name = pk_columns[0].name
            for row in rows:
                pk = row.get(pk_name)
                if pk is None:
                    continue
                label = _row_label(row)
                if label:
                    labels[table_name][str(pk)] = label

        if table_name == "source":
            for row in rows:
                sid = row.get("id")
                url = row.get("canonical_url") or row.get("url")
                if sid is not None and url:
                    source_urls[str(sid)] = _format_value(url)

    return labels, source_urls


def _entity_sources(
    all_rows: dict[str, list[dict[str, Any]]],
    source_urls: dict[str, str],
) -> dict[tuple[str, str], list[str]]:
    """Resolve polymorphic entity_source -> source URLs."""
    result: dict[tuple[str, str], list[str]] = defaultdict(list)

    for row in all_rows.get("entity_source", []):
        key = (_format_value(row.get("entity_type")), _format_value(row.get("entity_id")))
        url = source_urls.get(_format_value(row.get("source_id")))
        if url and url not in result[key]:
            result[key].append(url)

    return result


def _resolve_fk_label(column, value: Any, labels: dict[str, dict[str, str]]) -> str | None:
    if value is None or not column.foreign_keys:
        return None

    # Normal SQL FK: use target table's human label.
    fk = next(iter(column.foreign_keys))
    target_table = fk.column.table.name
    return labels.get(target_table, {}).get(str(value))


def _polymorphic_label(
    table_name: str,
    row: dict[str, Any],
    labels: dict[str, dict[str, str]],
) -> str | None:
    """Resolve media/entity_source polymorphic entity_type + entity_id."""
    if table_name not in {"media", "entity_source"}:
        return None

    entity_type = row.get("entity_type")
    entity_id = row.get("entity_id")
    if not entity_type or entity_id is None:
        return None

    return labels.get(str(entity_type), {}).get(str(entity_id))


# ---------------------------------------------------------------------------
# Row -> semantic document
# ---------------------------------------------------------------------------

def _row_to_documents(
    *,
    table_name: str,
    table,
    row: dict[str, Any],
    labels: dict[str, dict[str, str]],
    source_urls: dict[str, str],
    entity_source_urls: dict[tuple[str, str], list[str]],
) -> list[dict[str, Any]]:
    pk_text = _primary_key_text(table, row)
    entity_name = _row_label(row) or pk_text

    lines = [
        f"Bảng dữ liệu: {table_name}",
        f"Bản ghi: {entity_name}",
    ]

    # booking_product is intentionally denormalized and already contains a
    # curated semantic representation in rag_content.  Do NOT stringify every
    # column for this table: that would duplicate the same facts through
    # raw_payload/source_data/validation and produce noisy, oversized chunks.
    if table_name == "booking_product" and row.get("rag_content"):
        lines.append(_format_value(row["rag_content"]))
    else:
        # Every non-null column is emitted for the normal normalized CORE tables.
        for column in table.columns:
            value = row.get(column.name)
            if value is None:
                continue

            rendered = _format_value(value)
            if rendered == "":
                continue

            ref_label = _resolve_fk_label(column, value, labels)
            if ref_label:
                rendered = f"{rendered} ({ref_label})"

            lines.append(f"{_humanize(column.name)}: {rendered}")

    # Polymorphic tables don't have a normal FK for entity_id.
    poly_label = _polymorphic_label(table_name, row, labels)
    if poly_label:
        lines.append(f"Thực thể tham chiếu: {poly_label}")

    urls = _direct_urls(row)

    # Direct source_id FK.
    source_id = row.get("source_id")
    if source_id is not None:
        source_url = source_urls.get(str(source_id))
        if source_url and source_url not in urls:
            urls.append(source_url)

    # Generic entity_source mapping for normal entity rows.
    simple_id = row.get("id")
    if simple_id is not None:
        for url in entity_source_urls.get((table_name, str(simple_id)), []):
            if url not in urls:
                urls.append(url)

    if urls:
        lines.append("Nguồn/URL liên quan: " + " | ".join(urls))

    full_text = "\n".join(lines)

    # Long normalized rows (policy/promotion/attraction etc.) may exceed one chunk.
    chunks = chunk_text(full_text, max_chars=2200, overlap=180)
    if not chunks:
        chunks = [full_text]

    output: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        # Repeat core identity if the generic chunker cuts it away.
        if idx > 0:
            chunk = (
                f"Bảng dữ liệu: {table_name}\n"
                f"Bản ghi: {entity_name}\n"
                f"{chunk}"
            )

        metadata: dict[str, Any] = {
            "entity_type": table_name,
            "entity_id": pk_text,
            "entity_name": entity_name[:1000],
            "source_table": table_name,
            "chunk_index": idx,
        }
        if urls:
            metadata["source_url"] = urls[0]

        # Helpful common filters, while keeping Chroma metadata scalar-only.
        for field in (
            "destination_id", "destination_name", "property_id", "promotion_id",
            "content_language", "category", "kind", "product_type",
            "availability_status", "currency", "ticket_code", "booking_code",
        ):
            value = row.get(field)
            if value is not None:
                metadata[field] = _format_value(value)
                if field == "property_id" and field in table.c:
                    property_name = _resolve_fk_label(table.c[field], value, labels)
                    if property_name:
                        metadata["property_name"] = property_name[:1000]

        output.append(
            {
                "id": _document_id(table_name, pk_text, idx),
                "text": chunk,
                "metadata": metadata,
            }
        )

    return output


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_postgres_documents(entity_types: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Load ALL normalized CORE business data into semantic RAG documents.

    Parameters
    ----------
    entity_types:
        Optional set/list of exact SQL table names to ingest.
        If omitted, every CORE business table is included.

    Coverage guarantee
    ------------------
    For every included table:
      * every row is read;
      * every non-null column is rendered into text;
      * every row must produce >= 1 document/chunk.

    The function raises RuntimeError if any included row fails to produce a
    document, so missing coverage cannot silently pass.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    available_tables = {
        name
        for name in CORE_TABLES
        if name not in EXCLUDED_TABLES
    }

    if entity_types is None:
        requested = available_tables
    else:
        requested = set(entity_types)
        unknown = requested - available_tables
        if unknown:
            raise ValueError(
                "Unknown/non-knowledge table(s): "
                + ", ".join(sorted(unknown))
            )

    # Deterministic order helps reproducible logs and debugging.
    requested = set(sorted(requested))

    documents: list[dict[str, Any]] = []
    total_rows = 0
    total_chunks = 0

    with engine.connect() as connection:
        # Load all included tables first so FK labels can be resolved both ways.
        all_rows: dict[str, list[dict[str, Any]]] = {}
        for table_name in sorted(requested):
            table = CORE_TABLES[table_name]
            all_rows[table_name] = _get_rows(connection, table)

        # Reference targets may sit outside a limited --types request.
        # Load lightweight rows for ALL knowledge tables for label resolution.
        reference_rows = dict(all_rows)
        for table_name in sorted(available_tables - set(reference_rows)):
            table = CORE_TABLES[table_name]
            reference_rows[table_name] = _get_rows(connection, table)

        labels, source_urls = _build_indexes(reference_rows)
        entity_source_urls = _entity_sources(reference_rows, source_urls)

        coverage_errors: list[str] = []

        for table_name in sorted(requested):
            table = CORE_TABLES[table_name]
            rows = all_rows[table_name]
            table_docs: list[dict[str, Any]] = []

            for row in rows:
                row_docs = _row_to_documents(
                    table_name=table_name,
                    table=table,
                    row=row,
                    labels=labels,
                    source_urls=source_urls,
                    entity_source_urls=entity_source_urls,
                )
                if not row_docs:
                    coverage_errors.append(
                        f"{table_name}: {_primary_key_text(table, row)}"
                    )
                    continue
                table_docs.extend(row_docs)

            total_rows += len(rows)
            total_chunks += len(table_docs)
            documents.extend(table_docs)

            print(
                f"[PostgreSQL] {table_name:<28} "
                f"{len(rows):>5} rows -> {len(table_docs):>5} chunks"
            )

        if coverage_errors:
            sample = "\n".join(coverage_errors[:20])
            raise RuntimeError(
                "FULL DATA coverage failed. Rows without documents:\n" + sample
            )

    print("-" * 72)
    print(
        f"[Coverage] FULL CORE BUSINESS DATA: "
        f"{len(requested)} tables · {total_rows} rows · {total_chunks} chunks"
    )
    print(
        "[Excluded intentionally] "
        + ", ".join(sorted(EXCLUDED_TABLES))
    )

    return documents
