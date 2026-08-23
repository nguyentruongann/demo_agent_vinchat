from __future__ import annotations

import random
import time
from dataclasses import dataclass

import numpy as np
from google import genai
from google.genai import types


@dataclass(frozen=True)
class GeminiEmbeddingConfig:
    api_key: str
    model: str = "gemini-embedding-001"
    batch_size: int = 16
    dimension: int = 3072
    max_retries: int = 4
    retry_base_seconds: float = 1.0
    retry_max_seconds: float = 20.0


class GeminiEmbedding:
    """Gemini API embedding client.

    Chunking stays local. Only vector generation is moved to Gemini API so the
    service container does not need to load ONNX embedding models into RAM.
    """

    def __init__(self, config: GeminiEmbeddingConfig) -> None:
        self.config = config
        self.client = genai.Client(api_key=config.api_key)

        print(
            f"[EMBEDDING] Gemini API ready: model={config.model}"
        )

    def _embed(
        self,
        texts: list[str],
        task_type: str,
    ) -> np.ndarray:

        if not texts:
            return np.empty((0, self.config.dimension), dtype=np.float32)

        all_vectors: list[list[float]] = []

        # Gemini limit:
        # BatchEmbedContentsRequest.requests <= 100
        # Use 50 for safety.
        batch_size = min(
            self.config.batch_size,
            50,
        )

        total_batches = (
            len(texts) + batch_size - 1
        ) // batch_size

        for batch_index in range(total_batches):

            start = batch_index * batch_size
            end = start + batch_size

            batch_texts = texts[start:end]

            batch_succeeded = False
            for attempt in range(1, self.config.max_retries + 2):
                try:

                    result = self.client.models.embed_content(
                        model=self.config.model,
                        contents=batch_texts,
                        config=types.EmbedContentConfig(
                            task_type=task_type
                        ),
                    )

                    vectors = [list(item.values) for item in (result.embeddings or [])]
                    if len(vectors) != len(batch_texts):
                        raise RuntimeError(
                            "Gemini returned an unexpected embedding count: "
                            f"expected={len(batch_texts)} actual={len(vectors)}"
                        )
                    invalid_dimensions = {
                        len(vector) for vector in vectors if len(vector) != self.config.dimension
                    }
                    if invalid_dimensions:
                        raise RuntimeError(
                            "Gemini embedding dimension mismatch: "
                            f"expected={self.config.dimension} actual={sorted(invalid_dimensions)}"
                        )

                    all_vectors.extend(vectors)

                    print(
                        f"[EMBEDDING] batch "
                        f"{batch_index + 1}/{total_batches} "
                        f"completed "
                        f"({len(batch_texts)} texts)"
                    )

                    batch_succeeded = True
                    break


                except Exception as exc:
                    error_text = str(exc)
                    upper_error = error_text.upper()

                    print(
                        f"[EMBEDDING] Gemini API failed "
                        f"(batch={batch_index + 1}/"
                        f"{total_batches}, "
                        f"attempt={attempt}/{self.config.max_retries + 1})"
                    )

                    print(
                        f"[EMBEDDING] Error: {exc}"
                    )

                    # Invalid request will never succeed by retrying.
                    permanent_markers = (
                        "INVALID_ARGUMENT", "API_KEY_INVALID", "PERMISSION_DENIED",
                        "UNAUTHENTICATED", "NOT_FOUND",
                    )
                    if any(marker in upper_error for marker in permanent_markers):
                        raise RuntimeError("Gemini embedding request is not retryable") from exc
                    if attempt > self.config.max_retries:
                        raise RuntimeError(
                            "Gemini embedding request exhausted bounded retries"
                        ) from exc
                    base = min(
                        self.config.retry_max_seconds,
                        self.config.retry_base_seconds * (2 ** (attempt - 1)),
                    )
                    delay = min(
                        self.config.retry_max_seconds,
                        base + random.uniform(0.0, max(0.1, base * 0.25)),
                    )
                    print(f"[EMBEDDING] Retry after {delay:.2f} seconds...")
                    time.sleep(delay)

            if not batch_succeeded:
                raise RuntimeError("Gemini embedding batch did not complete")


        return np.asarray(
            all_vectors,
            dtype=np.float32
        )


    def encode(
        self,
        texts: list[str],
    ) -> np.ndarray:

        return self._embed(
            texts,
            "RETRIEVAL_DOCUMENT",
        )


    def encode_query(
        self,
        texts: list[str],
    ) -> np.ndarray:

        return self._embed(
            texts,
            "RETRIEVAL_QUERY",
        )
