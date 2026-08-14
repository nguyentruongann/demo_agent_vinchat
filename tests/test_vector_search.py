from __future__ import annotations

r"""Pure embedding/vector-search test for P-013.

This script intentionally bypasses the agent graph, guardrail, intent routing,
destination filtering, reranking and Gemini calls. It tests only:

    question -> current E5 ONNX embedder -> current Chroma collection -> Top-K

Run from the repository root:
    python .\scripts\test_vector_model.py

You can also pass another question:
    python .\scripts\test_vector_model.py --question "your question"
"""

import argparse
import sys
from pathlib import Path

import numpy as np


# Make `src` importable when this file is placed under <repo>/scripts/.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backend.services.query_parser import normalize_text
from src.backend.services.rag import RAGService


DEFAULT_QUESTION = "Can we bring outside food into the safari park?"
DEFAULT_TOP_K = 20


def cosine_similarity(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def find_exact_faq_in_chroma(rag: RAGService, question: str) -> list[dict]:
    """Find Chroma documents that literally contain the FAQ question."""
    target = normalize_text(question)
    matches: list[dict] = []

    count = rag.collection.count()
    batch_size = 500

    for offset in range(0, count, batch_size):
        batch = rag.collection.get(
            limit=min(batch_size, count - offset),
            offset=offset,
            include=["documents", "metadatas"],
        )

        ids = batch.get("ids") or []
        documents = batch.get("documents") or []
        metadatas = batch.get("metadatas") or []

        for doc_id, text, metadata in zip(ids, documents, metadatas):
            text = text or ""
            if target and target in normalize_text(text):
                matches.append(
                    {
                        "id": doc_id,
                        "text": text,
                        "metadata": metadata or {},
                    }
                )

    return matches


def print_result(rank: int, item: dict) -> None:
    metadata = item.get("metadata") or {}
    text = (item.get("text") or "").replace("\n", " | ")

    print("-" * 100)
    print(f"TOP {rank:02d} | score={item.get('score')}")
    print(f"entity_type   : {metadata.get('entity_type')}")
    print(f"entity_name   : {metadata.get('entity_name')}")
    print(f"destination_id: {metadata.get('destination_id')}")
    print(f"source_table  : {metadata.get('source_table')}")
    print(f"text          : {text[:1000]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test current P-013 embedding + Chroma only")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    args = parser.parse_args()

    question = args.question.strip()
    if not question:
        raise SystemExit("Question must not be empty.")

    print("\n=== PURE VECTOR MODEL TEST ===")
    print(f"Question   : {question}")
    print("Agent/LLM  : BYPASSED")
    print("Testing    : E5 ONNX -> Chroma only\n")

    rag = RAGService()

    print(f"Embedding model : {rag.settings.local_embedding_model}")
    print(f"Backend         : {rag.settings.embedding_backend}")
    print(f"ONNX file       : {rag.settings.embedding_onnx_file}")
    print(f"Collection      : {rag.collection.name}")
    print(f"Document count  : {rag.collection.count()}")

    # 1) Verify the model can produce a query vector.
    query_vector = rag.embed_query(question)
    print(f"Query dimension : {len(query_vector)}")

    # 2) Verify that the exact FAQ actually exists in the CURRENT Chroma collection.
    exact_matches = find_exact_faq_in_chroma(rag, question)
    print(f"\nExact FAQ documents found in Chroma: {len(exact_matches)}")

    for idx, match in enumerate(exact_matches[:5], start=1):
        metadata = match.get("metadata") or {}
        print(f"  exact #{idx}: id={match['id']}")
        print(f"             entity_type={metadata.get('entity_type')}")
        print(f"             entity_name={metadata.get('entity_name')}")

    # 3) Direct semantic search. No filters/rerank/agent logic.
    results = rag.semantic_search(question, top_k=args.top_k)

    print(f"\n=== TOP {len(results)} PURE SEMANTIC RESULTS ===")
    for rank, item in enumerate(results, start=1):
        print_result(rank, item)

    # 4) Find rank of the literal FAQ document in Top-K.
    target = normalize_text(question)
    exact_rank = None
    exact_rank_score = None

    for rank, item in enumerate(results, start=1):
        if target in normalize_text(item.get("text") or ""):
            exact_rank = rank
            exact_rank_score = item.get("score")
            break

    # 5) Optional direct cosine against stored embedding of the exact FAQ document.
    direct_cosines: list[tuple[str, float]] = []
    for match in exact_matches[:5]:
        fetched = rag.collection.get(
            ids=[match["id"]],
            include=["embeddings"],
        )
        embeddings = fetched.get("embeddings")
        if embeddings is not None and len(embeddings) > 0:
            direct_cosines.append(
                (match["id"], cosine_similarity(query_vector, embeddings[0]))
            )

    print("\n=== VERDICT ===")

    if not exact_matches:
        print("FAIL: The exact FAQ is NOT present in the current Chroma collection.")
        print("This points to ingest/index data, not the embedding model itself.")
    elif exact_rank == 1:
        print(f"PASS: Exact FAQ is TOP 1 (score={exact_rank_score}).")
        print("The current E5 ONNX vector search works for this failing FAQ.")
        print("If the real agent still says 'no data', the failure is AFTER vector search.")
    elif exact_rank is not None:
        print(f"WARNING: Exact FAQ exists but ranks TOP {exact_rank} (score={exact_rank_score}).")
        print("The current embedding/retrieval quality should be compared with the old model.")
    else:
        print(f"FAIL: Exact FAQ exists in Chroma but is NOT in TOP {args.top_k}.")
        print("This is strong evidence that the current embedding/vector retrieval is missing it.")

    if direct_cosines:
        print("\nDirect cosine(query, exact FAQ stored vector):")
        for doc_id, score in direct_cosines:
            print(f"  {score:.6f}  {doc_id}")

    print("\nDone.")


if __name__ == "__main__":
    main()
