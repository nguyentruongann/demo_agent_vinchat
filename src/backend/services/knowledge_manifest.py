from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import chromadb
from sqlalchemy import create_engine, select, text

from src.backend.config import Settings, get_settings
from src.backend.services.postgres_loader import EXCLUDED_TABLES
from src.data_postgre.db import CORE_TABLES

REQUIRED_ENTITY_TYPES = ("faq", "property", "booking_product", "policy_document")
REQUIRED_DB_TABLES = ("faq", "property", "booking_product", "policy_document")
ACTIVE_FILTER_BY_TABLE = {
    "faq": " WHERE is_active IS TRUE",
    "property": " WHERE is_active IS TRUE",
    "booking_product": "",
    "policy_document": " WHERE is_active IS TRUE",
}


def expected_contract(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    return {
        "embedding_backend": "gemini_api",
        "embedding_model": settings.gemini_embedding_model,
        "embedding_dimension": int(settings.embedding_dimension),
        "knowledge_schema_version": int(settings.knowledge_schema_version),
    }


def manifest_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.chroma_dir / settings.knowledge_manifest_name


def data_fingerprint(settings: Settings | None = None) -> str:
    """Fingerprint active normalized PostgreSQL knowledge; never inspect source files."""
    settings = settings or get_settings()
    digest = hashlib.sha256()
    digest.update(f"knowledge-schema:{settings.knowledge_schema_version}\n".encode())

    def encode_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return str(value)

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            for table_name in sorted(CORE_TABLES):
                if table_name in EXCLUDED_TABLES:
                    continue
                table = CORE_TABLES[table_name]
                primary_keys = list(table.primary_key.columns)
                columns = list(primary_keys)
                present = {column.name for column in columns}
                for name in ("content_hash", "updated_at", "ingest_run_id", "is_active"):
                    if name in table.c and name not in present:
                        columns.append(table.c[name])
                        present.add(name)
                statement = select(*columns)
                if primary_keys:
                    statement = statement.order_by(*primary_keys)
                rows = connection.execute(statement).all()
                digest.update(f"table:{table_name}:rows:{len(rows)}\n".encode())
                for row in rows:
                    digest.update("\x1f".join(encode_value(value) for value in row).encode("utf-8"))
                    digest.update(b"\n")
    finally:
        engine.dispose()
    return digest.hexdigest()


def read_manifest(settings: Settings | None = None) -> dict[str, Any] | None:
    path = manifest_path(settings)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def database_counts(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    counts: dict[str, int] = {}
    try:
        with engine.connect() as connection:
            for table_name in REQUIRED_DB_TABLES:
                counts[table_name] = int(
                    connection.execute(
                        text(
                            f'SELECT COUNT(*) FROM core."{table_name}"'
                            + ACTIVE_FILTER_BY_TABLE[table_name]
                        )
                    ).scalar_one()
                )
            counts["successful_ingest_runs"] = int(
                connection.execute(
                    text("SELECT COUNT(*) FROM core.ingest_run WHERE status = 'success'")
                ).scalar_one()
            )
    finally:
        engine.dispose()
    return counts


def collection_snapshot(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    collection = client.get_collection(settings.chroma_collection)
    return {
        "name": collection.name,
        "document_count": int(collection.count()),
        "metadata": dict(collection.metadata or {}),
    }


def build_manifest(rag: Any, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    entity_counts: Counter[str] = Counter()
    total = int(rag.collection.count())
    for offset in range(0, total, 500):
        batch = rag.collection.get(
            limit=min(500, total - offset),
            offset=offset,
            include=["metadatas"],
        )
        for metadata in batch.get("metadatas") or []:
            entity_type = str((metadata or {}).get("entity_type") or "").strip()
            if entity_type:
                entity_counts[entity_type] += 1

    payload = {
        "manifest_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_sha256": data_fingerprint(settings),
        "collection": settings.chroma_collection,
        **expected_contract(settings),
        "document_count": total,
        "entity_type_counts": dict(sorted(entity_counts.items())),
        "database_counts": database_counts(settings),
    }
    missing = [name for name in REQUIRED_ENTITY_TYPES if entity_counts.get(name, 0) <= 0]
    if missing:
        raise RuntimeError(f"Rebuilt Chroma collection is missing required entity types: {missing}")
    return payload


def write_manifest(rag: Any, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    path = manifest_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_manifest(rag, settings)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def readiness_issues(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    issues: list[str] = []
    if settings.embedding_backend != "gemini_api":
        issues.append("embedding backend is not gemini_api")
    if not settings.gemini_api_key:
        issues.append("GEMINI_API_KEY is not configured")

    manifest = read_manifest(settings)
    if manifest is None:
        issues.append("knowledge manifest is missing")
        return issues

    try:
        current_fingerprint = data_fingerprint(settings)
    except Exception:
        current_fingerprint = None
        issues.append("PostgreSQL knowledge tables are unavailable for fingerprinting")
    if current_fingerprint and manifest.get("data_sha256") != current_fingerprint:
        issues.append("PostgreSQL knowledge fingerprint differs from the built knowledge index")
    if manifest.get("collection") != settings.chroma_collection:
        issues.append("knowledge manifest collection name mismatch")
    for key, expected in expected_contract(settings).items():
        if manifest.get(key) != expected:
            issues.append(f"knowledge manifest {key} mismatch")
    if int(manifest.get("document_count") or 0) <= 0:
        issues.append("knowledge manifest reports an empty collection")
    entity_counts = manifest.get("entity_type_counts") or {}
    for entity_type in REQUIRED_ENTITY_TYPES:
        if int(entity_counts.get(entity_type) or 0) <= 0:
            issues.append(f"knowledge manifest has no {entity_type} documents")

    try:
        snapshot = collection_snapshot(settings)
        if snapshot["document_count"] != int(manifest.get("document_count") or 0):
            issues.append("Chroma document count differs from knowledge manifest")
        metadata = snapshot["metadata"]
        for key, expected in expected_contract(settings).items():
            if metadata.get(key) != expected:
                issues.append(f"Chroma {key} mismatch")
    except Exception:
        issues.append("configured Chroma collection is unavailable")

    try:
        counts = database_counts(settings)
        for table_name in REQUIRED_DB_TABLES:
            if int(counts.get(table_name) or 0) <= 0:
                issues.append(f"PostgreSQL core.{table_name} is empty")
        if int(counts.get("successful_ingest_runs") or 0) <= 0:
            issues.append("PostgreSQL has no successful core ingest run")
    except Exception:
        issues.append("PostgreSQL knowledge tables are unavailable")
    return issues
