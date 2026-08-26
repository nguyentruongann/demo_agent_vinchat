import asyncio
import json

from src.backend.agents.nodes import answer as answer_node
from src.backend.agents.nodes import language_guard
from src.backend.api import routes
from src.backend.models.chat import ChatRequest, ChatResponse


def _decode_sse(chunks: list[str]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for chunk in chunks:
        event_name = "message"
        data = None
        for line in chunk.strip().splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = json.loads(line.split(":", 1)[1].strip())
        if data is not None:
            events.append((event_name, data))
    return events


def test_language_guard_streams_only_its_final_output(monkeypatch):
    emitted: list[str] = []

    monkeypatch.setattr(
        language_guard.LLMService,
        "text_stream",
        lambda *_args, **_kwargs: iter(["Xin ", "chào", " bạn"]),
    )

    result = language_guard.enforce_response_language({
        "answer": "Draft already grounded",
        "original_language": "vi",
        "original_language_name": "Vietnamese",
        "stream_writer": emitted.append,
    })

    assert emitted == ["Xin ", "chào", " bạn"]
    assert result["answer"] == "Xin chào bạn"


def test_answer_node_streams_the_primary_rag_draft(monkeypatch):
    emitted: list[str] = []

    monkeypatch.setattr(
        answer_node.LLMService,
        "text_stream",
        lambda *_args, **_kwargs: iter(["Tư vấn ", "Hà Nội"]),
    )

    result = answer_node.generate_answer({
        "user_message": "Tư vấn Hà Nội",
        "sanitized_user_request": "Tư vấn Hà Nội",
        "original_language": "vi",
        "original_language_name": "Vietnamese",
        "request_task_count": 0,
        "price_requested": False,
        "stream_writer": emitted.append,
    })

    assert emitted == ["Tư vấn ", "Hà Nội"]
    assert result == {
        "answer": "Tư vấn Hà Nội",
        "answer_streamed": True,
    }


def test_language_guard_does_not_duplicate_an_answer_stream(monkeypatch):
    monkeypatch.setattr(
        language_guard.LLMService,
        "text",
        lambda *_args, **_kwargs: "Bản cuối đã kiểm tra",
    )
    monkeypatch.setattr(
        language_guard.LLMService,
        "text_stream",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not stream twice")),
    )

    result = language_guard.enforce_response_language({
        "answer": "Bản nháp đang hiển thị",
        "answer_streamed": True,
        "original_language": "vi",
        "original_language_name": "Vietnamese",
        "stream_writer": lambda _chunk: None,
    })

    assert result["answer"] == "Bản cuối đã kiểm tra"


def test_chat_event_stream_emits_progress_tokens_and_complete(monkeypatch):
    class FakeGraph:
        def stream(self, state, stream_mode):
            assert stream_mode == "updates"
            yield {"guardrail": {"scope_action": "allow"}}
            yield {"classify": {"route": "rag"}}
            yield {"retrieve": {"retrieved_documents": []}}
            state["stream_writer"]("Xin ")
            state["stream_writer"]("chào")
            yield {"answer": {"answer": "Xin chào", "answer_streamed": True}}
            yield {"grounding": {"answer": "Xin chào"}}
            yield {
                "language_guard": {
                    "answer": "Xin chào bạn",
                    "session_id": state["session_id"],
                    "original_language": "vi",
                    "route": "rag",
                }
            }
            yield {"save_memory": {}}

    monkeypatch.setattr(routes, "agent_graph", FakeGraph())
    monkeypatch.setattr(
        routes,
        "_build_chat_response",
        lambda state, session_id: ChatResponse(
            answer=state["answer"],
            session_id=session_id,
            language=state["original_language"],
            route=state["route"],
            sources=[],
        ),
    )

    async def collect() -> list[str]:
        return [
            chunk
            async for chunk in routes._chat_event_stream(
                payload=ChatRequest(message="Xin chào", session_id="test-session"),
                session_id="test-session",
                user_id=None,
            )
        ]

    events = _decode_sse(asyncio.run(collect()))
    event_names = [name for name, _data in events]
    stages = [data["stage"] for name, data in events if name == "status"]
    answer = "".join(data["content"] for name, data in events if name == "delta")
    replacements = [data["content"] for name, data in events if name == "replace"]
    completed = [data for name, data in events if name == "complete"]

    assert event_names[0] == "status"
    assert stages == [
        "understanding",
        "searching",
        "evaluating",
        "verifying",
        "finalizing",
    ]
    assert answer == "Xin chào"
    assert replacements == ["Xin chào bạn"]
    assert len(completed) == 1
    assert completed[0]["answer"] == "Xin chào bạn"
    assert completed[0]["session_id"] == "test-session"
    assert event_names[-1] == "complete"
