from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RoleName = Literal["customer", "staff", "admin"]


class UserPublic(BaseModel):
    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    role: RoleName
    locale: str = "vi"
    is_active: bool = True


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    locale: str = Field(default="vi", max_length=10)

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
            raise ValueError("Cần ít nhất email hoặc số điện thoại.")
        return self


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class StaffCreateRequest(RegisterRequest):
    role: Literal["staff", "admin"] = "staff"


class StaffUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    role: Literal["staff", "admin"] | None = None
    is_active: bool | None = None


class BootstrapAdminRequest(RegisterRequest):
    bootstrap_key: str = Field(min_length=1, max_length=512)
