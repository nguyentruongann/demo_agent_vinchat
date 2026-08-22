from __future__ import annotations

from pathlib import Path

from src.backend.agents.nodes import grounding, request_understanding
from src.backend.services.faq_matcher import FAQMatcher
from src.backend.services.llm import LLMService
from src.backend.services.text_chunker import chunk_text


def test_relative_zone_price_contract_removes_hotel_and_exhaustive_scope() -> None:
    task = request_understanding._normalize_task(
        {
            "task_type": "price_lookup",
            "result_scope": "exhaustive",
            "goal": "Provide prices for those areas.",
            "source_text": "giá những khu đó như thế nào",
            "needs_memory": False,
            "retrieval_intents": ["hotel", "booking_product"],
            "retrieval_queries": ["prices for previously discussed hotels"],
            "needs_retrieval": True,
        },
        1,
    )

    assert task is not None
    assert task["needs_memory"] is True
    assert task["result_scope"] == "normal"
    assert "hotel" not in task["retrieval_intents"]
    assert "attraction" in task["retrieval_intents"]
    assert "booking_product" in task["retrieval_intents"]
    assert "immediately preceding turn" in task["retrieval_queries"][0]


def test_faq_matcher_loads_only_injected_postgres_rows() -> None:
    matcher = FAQMatcher(
        embed_passages=lambda values: [],
        embed_queries=lambda values: [],
        rows_loader=lambda: [
            {
                "index": 7,
                "question": "PostgreSQL question?",
                "answer": "PostgreSQL answer.",
                "category": "General",
                "source_path": "postgresql:core.faq",
            }
        ],
    )

    entries = matcher._load_entries()

    assert len(entries) == 1
    assert entries[0].question == "PostgreSQL question?"
    assert entries[0].source_path == "postgresql:core.faq"


def test_backend_has_no_json_knowledge_loader_or_onnx_embedding() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    python_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in backend_root.rglob("*.py")
        if "tests" not in path.parts
    )
    assert "load_json_documents" not in python_source
    assert "vinpearl_faqs.json" not in python_source
    assert "onnxruntime" not in python_source
    assert not (backend_root / "services" / "onnx_embeddings.py").exists()


def test_postgres_chunker_is_deterministic_and_overlapping() -> None:
    source = "First sentence. " + ("middle " * 20) + "Last sentence."
    first = chunk_text(source, max_chars=60, overlap=10)
    second = chunk_text(source, max_chars=60, overlap=10)
    assert first == second
    assert len(first) > 1
    assert all(chunk.strip() == chunk and chunk for chunk in first)


def _llm_with_text_responses(*responses: str) -> LLMService:
    service = object.__new__(LLMService)
    service.max_tokens = 1500
    queue = list(responses)

    def fake_text(*_args, **_kwargs):
        return queue.pop(0)

    service.text = fake_text  # type: ignore[method-assign]
    return service


def test_invalid_json_gets_one_bounded_repair() -> None:
    service = _llm_with_text_responses(
        '{"grounded": true, "reason": "ok", "unsupported_claims": [',
        '{"grounded":true,"reason":"repaired","unsupported_claims":[]}',
    )
    result = service.json("system", "user")
    assert result["grounded"] is True
    assert result["reason"] == "repaired"


def test_grounding_validator_failure_never_raises_http_500(monkeypatch) -> None:
    class FailingLLM:
        max_tokens = 1500

        def json(self, **_kwargs):
            raise ValueError("truncated control JSON")

    monkeypatch.setattr(grounding, "LLMService", FailingLLM)
    result = grounding.validate_grounding(
        {
            "answer": "draft answer",
            "context": "grounded context",
            "user_message": "câu hỏi",
            "original_language": "vi",
        }
    )
    assert result["grounding_passed"] is False
    assert result["answer"]
    assert "ValueError" in result["grounding_reason"]


def test_unsupported_answer_is_corrected_outside_json(monkeypatch) -> None:
    class CorrectionLLM:
        max_tokens = 1500

        def __init__(self):
            self.text_called = False

        def json(self, **_kwargs):
            return {
                "grounded": False,
                "reason": "one unsupported claim",
                "unsupported_claims": ["invented price"],
            }

        def text(self, **kwargs):
            self.text_called = True
            assert kwargs["max_tokens"] >= 2500
            return "Câu trả lời đã bỏ giá không có nguồn."

    fake = CorrectionLLM()
    monkeypatch.setattr(grounding, "LLMService", lambda: fake)
    result = grounding.validate_grounding(
        {
            "answer": "Bản nháp có giá bịa.",
            "context": "Nguồn không có giá.",
            "user_message": "Giá bao nhiêu?",
            "original_language": "vi",
        }
    )
    assert fake.text_called is True
    assert result["answer"] == "Câu trả lời đã bỏ giá không có nguồn."
    assert result["grounding_passed"] is False
