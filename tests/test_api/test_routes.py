"""Kiểm thử API.

``test_agent_status`` cũ gọi ``GET /api/v1/status`` — endpoint mã mẫu của
template, chưa từng tồn tại trong src/api/routes.py. Thay bằng các phép kiểm
validate đầu vào của /api/v1/chat: chúng chạy trước khi handler gọi LLM nên
không cần API key hay Chroma.
"""

import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_empty_message(client):
    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_missing_message(client):
    response = await client.post("/api/v1/chat", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_message_too_long(client):
    """ChatRequest giới hạn 10.000 ký tự."""
    response = await client.post("/api/v1/chat", json={"message": "x" * 10_001})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_route_returns_404(client):
    response = await client.get("/api/v1/khong-ton-tai")
    assert response.status_code == 404
