from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np
from google import genai
from google.genai import types


@dataclass(frozen=True)
class GeminiEmbeddingConfig:
    api_key: str
    model: str = "gemini-embedding-001"
    batch_size: int = 50


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
            return np.empty(
                (0, 3072),
                dtype=np.float32
            )

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

            retry_count = 0

            while True:
                try:

                    result = self.client.models.embed_content(
                        model=self.config.model,
                        contents=batch_texts,
                        config=types.EmbedContentConfig(
                            task_type=task_type
                        ),
                    )

                    vectors = [
                        item.values
                        for item in result.embeddings
                    ]

                    all_vectors.extend(vectors)

                    print(
                        f"[EMBEDDING] batch "
                        f"{batch_index + 1}/{total_batches} "
                        f"completed "
                        f"({len(batch_texts)} texts)"
                    )

                    break


                except Exception as e:
                    retry_count += 1

                    error_text = str(e)

                    print(
                        f"[EMBEDDING] Gemini API failed "
                        f"(batch={batch_index + 1}/"
                        f"{total_batches}, "
                        f"attempt={retry_count})"
                    )

                    print(
                        f"[EMBEDDING] Error: {e}"
                    )

                    # Invalid request will never succeed by retrying.
                    if (
                        "INVALID_ARGUMENT" in error_text
                        and "at most 100" in error_text
                    ):
                        raise


                    print(
                        "[EMBEDDING] Retry after 30 seconds..."
                    )

                    time.sleep(30)


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