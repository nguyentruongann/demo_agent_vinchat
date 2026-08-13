"""Ingest normalized PostgreSQL data into the existing Chroma collection.

Run from repository root:
    python -m src.backend.services.ingest_postgres

Optional:
    python -m src.backend.services.ingest_postgres --reset
    python -m src.backend.services.ingest_postgres --types room faq promotion
"""
from __future__ import annotations

import argparse

from src.backend.services.postgres_loader import load_postgres_documents
from src.backend.services.rag import RAGService


def _batches(items: list[dict], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete existing Chroma documents before ingest")
    parser.add_argument("--types", nargs="*", help="property room faq attraction promotion policy")
    args = parser.parse_args()

    rag = RAGService()
    if args.reset:
        collection_name = rag.collection.name

        rag.chroma.delete_collection(collection_name)

        rag.collection = rag.chroma.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        print(f"[Chroma] reset collection: {collection_name}")

    documents = load_postgres_documents(args.types)
    if not documents:
        print("No PostgreSQL documents found; nothing to ingest.")
        return

    batch_size = min(max(rag.settings.embedding_batch_size, 1), 256)
    written = 0
    for batch in _batches(documents, batch_size):
        texts = [item["text"] for item in batch]
        embeddings = rag.embed_documents(texts)
        rag.collection.upsert(
            ids=[item["id"] for item in batch],
            documents=texts,
            metadatas=[item["metadata"] for item in batch],
            embeddings=embeddings,
        )
        written += len(batch)
        print(f"[Chroma] upserted {written}/{len(documents)}")

    print(f"Done. Collection '{rag.settings.chroma_collection}' now has {rag.collection.count()} documents.")


if __name__ == "__main__":
    main()
