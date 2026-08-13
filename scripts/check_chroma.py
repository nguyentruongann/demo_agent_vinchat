from src.backend.services.rag import RAGService


def main() -> None:
    rag = RAGService()
    print("Collection:", rag.collection.name)
    print("Documents:", rag.collection.count())


if __name__ == "__main__":
    main()
