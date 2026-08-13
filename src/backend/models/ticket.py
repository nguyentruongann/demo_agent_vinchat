from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TicketStatus = Literal["open", "in_progress", "resolved", "closed"]
TicketPriority = Literal["low", "normal", "high"]


class ManualTicketCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    subject: str = Field(default="General inquiry", max_length=250)
    content: str = Field(min_length=3, max_length=10000)
    language: str = Field(default="vi", max_length=10)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if value is None or not value.strip():
            return None
        value = value.strip().lower()
        if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
            raise ValueError("Email không hợp lệ.")
        return value

    @model_validator(mode="after")
    def validate_contact(self):
        if not self.email and not (self.phone or "").strip():
            raise ValueError("Ticket cần ít nhất email hoặc số điện thoại.")
        return self


class TicketPublic(BaseModel):
    id: str
    customer_name: str | None = None
    email: str | None = None
    phone: str | None = None
    subject: str | None = None
    content: str | None = None
    language: str | None = None
    status: TicketStatus
    priority: TicketPriority | None = None
    reason: str | None = None
    assigned_to: str | None = None
    assigned_to_name: str | None = None
    created_at: str
    updated_at: str
    resolved_at: str | None = None


class TicketUpdateRequest(BaseModel):
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assigned_to: str | None = None
