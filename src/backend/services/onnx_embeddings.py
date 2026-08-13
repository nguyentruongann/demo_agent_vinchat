from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer


@dataclass(frozen=True)
class OnnxEmbeddingConfig:
    model_name: str
    onnx_file: str
    provider: str = "CPUExecutionProvider"
    batch_size: int = 16
    max_length: int = 512
    intra_op_threads: int = 1


class OnnxE5Embedder:
    """Low-memory E5 inference using ONNX Runtime instead of PyTorch.

    The implementation intentionally mirrors the official multilingual-e5-small
    recipe: add ``query:`` / ``passage:`` prefixes, mean-pool token embeddings
    with the attention mask, then L2-normalize the sentence vector.
    """

    def __init__(self, config: OnnxEmbeddingConfig) -> None:
        self.config = config

        self.tokenizer = AutoTokenizer.from_pretrained(
            config.model_name,
            use_fast=True,
        )

        model_path = hf_hub_download(
            repo_id=config.model_name,
            filename=config.onnx_file,
        )

        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )

        session_options.intra_op_num_threads = max(
            1,
            int(config.intra_op_threads),
        )
        session_options.inter_op_num_threads = 1

        # Railway / low-memory optimization:
        # avoid retaining a large CPU memory arena and static memory pattern
        # after inference. This does not change the INT8 model or embedding math.
        session_options.enable_cpu_mem_arena = False
        session_options.enable_mem_pattern = False

        # Sequential execution avoids extra parallel execution resources.
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        self.session = ort.InferenceSession(
            model_path,
            sess_options=session_options,
            providers=[config.provider],
        )

        self.input_names = {
            item.name for item in self.session.get_inputs()
        }

        print(
            "[EMBEDDING] ONNX INT8 ready: "
            f"model={config.model_name} "
            f"file={config.onnx_file} "
            f"provider={config.provider} "
            "cpu_mem_arena=off mem_pattern=off"
        )

    @staticmethod
    def _mean_pool(
        last_hidden_state: np.ndarray,
        attention_mask: np.ndarray,
    ) -> np.ndarray:
        mask = attention_mask.astype(np.float32)[..., None]
        summed = (
            last_hidden_state.astype(np.float32) * mask
        ).sum(axis=1)
        counts = np.clip(
            mask.sum(axis=1),
            a_min=1e-9,
            a_max=None,
        )
        return summed / counts

    @staticmethod
    def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(
            vectors,
            axis=1,
            keepdims=True,
        )
        return vectors / np.clip(
            norms,
            a_min=1e-12,
            a_max=None,
        )

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        encoded = self.tokenizer(
            texts,
            max_length=self.config.max_length,
            padding=True,
            truncation=True,
            return_tensors="np",
        )

        ort_inputs: dict[str, np.ndarray] = {}

        for name in self.input_names:
            if name in encoded:
                ort_inputs[name] = np.asarray(
                    encoded[name],
                    dtype=np.int64,
                )

            elif name == "token_type_ids":
                ort_inputs[name] = np.zeros_like(
                    np.asarray(
                        encoded["input_ids"],
                        dtype=np.int64,
                    )
                )

            else:
                raise RuntimeError(
                    f"ONNX model requires unsupported input '{name}'. "
                    f"Available tokenizer fields: {sorted(encoded.keys())}"
                )

        outputs = self.session.run(
            None,
            ort_inputs,
        )

        if not outputs:
            raise RuntimeError(
                "ONNX embedding model returned no outputs."
            )

        last_hidden_state = np.asarray(
            outputs[0],
            dtype=np.float32,
        )

        attention_mask = np.asarray(
            encoded["attention_mask"],
            dtype=np.int64,
        )

        pooled = self._mean_pool(
            last_hidden_state,
            attention_mask,
        )

        return self._l2_normalize(
            pooled
        ).astype(
            np.float32,
            copy=False,
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty(
                (0, 384),
                dtype=np.float32,
            )

        batch_size = max(
            1,
            int(self.config.batch_size),
        )

        chunks: list[np.ndarray] = []

        for start in range(
            0,
            len(texts),
            batch_size,
        ):
            chunks.append(
                self._encode_batch(
                    texts[start : start + batch_size]
                )
            )

        return np.concatenate(
            chunks,
            axis=0,
        )
