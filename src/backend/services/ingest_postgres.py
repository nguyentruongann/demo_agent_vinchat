"""Ingest normalized PostgreSQL data into the existing Chroma collection.

Run from repository root:
    python -m src.backend.services.ingest_postgres

Optional:
    python -m src.backend.services.ingest_postgres --reset
    python -m src.backend.services.ingest_postgres --types room faq promotion
"""

from __future__ import annotations

import argparse

import chromadb

from src.backend.services.postgres_loader import load_postgres_documents
from src.backend.services.rag import RAGService
from src.backend.services.knowledge_manifest import write_manifest
from src.backend.config import get_settings


def _batches(items: list[dict], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _reset_chroma_collection() -> None:
    """
    Delete old Chroma collection before RAGService initialization.

    Required when embedding contract changes:
    - backend
    - model
    - dimension
    - schema version
    """

    settings = get_settings()

    chroma = chromadb.PersistentClient(
        path=settings.chroma_path
    )

    try:
        chroma.delete_collection(
            name=settings.chroma_collection
        )

        print(
            f"[Chroma] deleted old collection: "
            f"{settings.chroma_collection}"
        )

    except Exception as exc:
        print(
            f"[Chroma] no existing collection or delete skipped: {exc}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing Chroma collection before ingest",
    )

    parser.add_argument(
        "--types",
        nargs="*",
        help="property room faq attraction promotion policy",
    )

    args = parser.parse_args()


    # IMPORTANT:
    # Reset MUST happen before RAGService()
    # because RAGService validates existing collection contract.
    if args.reset:
        _reset_chroma_collection()


    # Create RAG after old collection is removed
    rag = RAGService()


    documents = load_postgres_documents(args.types)

    if not documents:
        print(
            "No PostgreSQL documents found; nothing to ingest."
        )
        return


    batch_size = min(
        max(rag.settings.embedding_batch_size, 1),
        256,
    )

    written = 0


    for batch in _batches(documents, batch_size):

        texts = [
            item["text"]
            for item in batch
        ]

        embeddings = rag.embed_documents(texts)


        rag.collection.upsert(
            ids=[
                item["id"]
                for item in batch
            ],

            documents=texts,

            metadatas=[
                item["metadata"]
                for item in batch
            ],

            embeddings=embeddings,
        )


        written += len(batch)

        print(
            f"[Chroma] upserted "
            f"{written}/{len(documents)}"
        )


    manifest = write_manifest(
        rag,
        rag.settings,
    )


    print(
        f"Done. Collection "
        f"'{rag.settings.chroma_collection}' "
        f"now has "
        f"{rag.collection.count()} documents. "
        f"Manifest: {manifest}"
    )


if __name__ == "__main__":
    main()