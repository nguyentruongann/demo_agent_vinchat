from __future__ import annotations

from src.backend.agents.nodes import language as language_node
from src.backend.agents.nodes import language_guard


class _FakeJsonLLM:
    def json(self, *, system_prompt: str, user_prompt: str):
        assert "สวัสดี" in user_prompt
        if "safety classifier" in system_prompt:
            return {"safety_action": "allow", "safety_reason": "benign greeting"}
        assert "current message" in system_prompt.lower()
        return {
            "language": "th_TH",
            "language_name": "Thai",
            "rag_query": "Vinpearl greeting",
            "route": "greeting",
        }


class _FakeTextLLM:
    def __init__(self):
        self.system_prompt = ""
        self.user_prompt = ""

    def text(self, *, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return "คำตอบภาษาไทย"


def test_normalize_language_code_supports_bcp47() -> None:
    assert language_node._normalize_language_code("pt_br") == "pt-BR"
    assert language_node._normalize_language_code("zh_hant") == "zh-Hant"
    assert language_node._normalize_language_code("TH") == "th"
    assert language_node._normalize_language_code("not a language code") == "und"


def test_language_node_uses_current_message_and_returns_language_name(monkeypatch) -> None:
    monkeypatch.setattr(language_node, "LLMService", lambda: _FakeJsonLLM())
    result = language_node.detect_language_and_translate(
        {
            "user_message": "สวัสดี",
            "conversation_history": "User: Bonjour",
            "recent_destination_summary": "(none yet)",
        }
    )
    assert result["original_language"] == "th-TH"
    assert result["original_language_name"] == "Thai"
    assert result["route"] == "greeting"


def test_final_language_guard_forces_target_language(monkeypatch) -> None:
    fake = _FakeTextLLM()
    monkeypatch.setattr(language_guard, "LLMService", lambda: fake)

    result = language_guard.enforce_response_language(
        {
            "user_message": "ช่วยแนะนำโรงแรม Vinpearl",
            "original_language": "th",
            "original_language_name": "Thai",
            "answer": "Here is the grounded answer.",
        }
    )

    assert result["answer"] == "คำตอบภาษาไทย"
    assert "TARGET_LANGUAGE: Thai (th)" in fake.user_prompt
    assert "Do not add, remove" in fake.system_prompt
