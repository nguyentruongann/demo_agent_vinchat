"""Kiểm thử cấu trúc đồ thị agent.

File cũ là mã mẫu của template: nó import ``agent`` và gọi
``agent.ainvoke({"query": ...})`` rồi kiểm tra khoá ``response``. Không cái nào
tồn tại — graph thật export ``agent_graph``, còn AgentState dùng ``user_message``
và ``answer``. Vì vậy test này chưa từng chạy được kể từ commit đầu.

Bản mới kiểm tra những gì xác minh được mà không cần gọi LLM hay Chroma:
đồ thị biên dịch được, đủ node, và hai hàm định tuyến trả về đúng nhánh.
"""

import pytest

from src.backend.agents.graph import (
    agent_graph,
    route_after_assessment,
    route_after_classification,
)

EXPECTED_NODES = {
    "language",
    "classify",
    "greeting",
    "out_of_scope",
    "retrieve",
    "assess",
    "answer",
    "language_guard",
    "ticket",
}


def test_graph_compiles() -> None:
    assert agent_graph is not None


def test_graph_has_expected_nodes() -> None:
    nodes = set(agent_graph.get_graph().nodes)
    assert EXPECTED_NODES <= nodes, f"thiếu node: {EXPECTED_NODES - nodes}"


@pytest.mark.parametrize("route", ["greeting", "out_of_scope", "rag"])
def test_route_after_classification(route: str) -> None:
    assert route_after_classification({"route": route}) == route


def test_route_after_assessment_enough_info() -> None:
    assert route_after_assessment({"enough_information": True}) == "answer"


@pytest.mark.parametrize("state", [{"enough_information": False}, {}])
def test_route_after_assessment_falls_back_to_ticket(state: dict) -> None:
    """Thiếu thông tin, hoặc thiếu luôn cả khoá, đều phải mở ticket."""
    assert route_after_assessment(state) == "ticket"
