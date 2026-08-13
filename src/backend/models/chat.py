from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    session_id: str | None = None
    user_id: str | None = None


class SourceItem(BaseModel):
    source_file: str
    category: str | None = None
    path: str | None = None
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    language: str
    route: str
    ticket_id: str | None = None
    sources: list[SourceItem] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class ChatSessionSummary(BaseModel):
    id: str
    title: str
    language: str | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    message_count: int = 0


class ChatHistoryMessage(BaseModel):
    id: str
    seq: int
    role: str
    content: str
    language: str | None = None
    route: str | None = None
    ticket_id: str | None = None
    created_at: datetime | None = None


class ChatSessionHistory(BaseModel):
    session_id: str
    messages: list[ChatHistoryMessage] = Field(default_factory=list)
