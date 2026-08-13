from src.backend.config import get_settings
from src.backend.services.data_loader import load_json_documents
from src.backend.services.rag import RAGService

# Number of records written to Chroma per upsert. The model itself uses
# EMBEDDING_BATCH_SIZE from .env for local inference.
UPSERT_BATCH_SIZE = 512


def main() -> None:
    settings = get_settings()
    documents = load_json_documents(settings.data_dir)

    if not documents:
        raise RuntimeError(f"No JSON documents found in {settings.data_dir}")

    rag = RAGService()

    existing_result = rag.collection.get(include=[])
    existing_ids = set(existing_result.get("ids", []))
    remaining_documents = [
        document for document in documents if document["id"] not in existing_ids
    ]

    print(f"Embedding model: {settings.local_embedding_model}")
    print(f"Device: {settings.embedding_device}")
    print(f"Loaded total: {len(documents)} documents")
    print(f"Already ingested: {len(existing_ids)} documents")
    print(f"Remaining: {len(remaining_documents)} documents")

    if not remaining_documents:
        print(f"Done. Collection contains {rag.collection.count()} documents.")
        return

    try:
        for start in range(0, len(remaining_documents), UPSERT_BATCH_SIZE):
            batch = remaining_documents[start : start + UPSERT_BATCH_SIZE]
            texts = [item["text"] for item in batch]
            embeddings = rag.embed_documents(texts)

            rag.collection.upsert(
                ids=[item["id"] for item in batch],
                documents=texts,
                metadatas=[item["metadata"] for item in batch],
                embeddings=embeddings,
            )

            completed = min(start + UPSERT_BATCH_SIZE, len(remaining_documents))
            print(
                f"Ingested this run: {completed}/{len(remaining_documents)} "
                f"| Collection: {rag.collection.count()}/{len(documents)}"
            )

    except KeyboardInterrupt:
        print("\nStopped safely.")
        print(f"Collection currently contains {rag.collection.count()} documents.")
        print("Run the same command later to continue:")
        print("python -m scripts.ingest_data")
        return

    print(f"Done. Collection contains {rag.collection.count()} documents.")


if __name__ == "__main__":
    main()
