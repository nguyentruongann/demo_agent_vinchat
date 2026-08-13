from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.backend.config import get_settings
from src.backend.models.auth import UserPublic
from src.backend.services.db import open_session
from src.data_postgre.db.app import AppUser, AuthSession


_PHONE_DIGITS = re.compile(r"\D+")


def normalize_email(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value or None


def normalize_phone(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    digits = _PHONE_DIGITS.sub("", raw)
    if not digits:
        return None
    # Normalize common Vietnam formats so 090... and +8490... resolve to the same account.
    if digits.startswith("84") and len(digits) in {11, 12}:
        digits = "0" + digits[2:]
    return digits


def hash_password(password: str) -> str:
    settings = get_settings()
    iterations = max(200_000, int(settings.password_pbkdf2_iterations))
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_raw.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_raw.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def user_public(user: AppUser) -> UserPublic:
    return UserPublic(
        id=str(user.id),
        name=user.display_name or "User",
        email=user.email,
        phone=user.phone,
        role=user.role,
        locale=user.locale or "vi",
        is_active=user.is_active,
    )


def create_user(
    db: Session,
    *,
    name: str,
    email: str | None,
    phone: str | None,
    password: str,
    role: str = "customer",
    locale: str = "vi",
) -> AppUser:
    email = normalize_email(email)
    phone = normalize_phone(phone)
    name = name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tên không được để trống.")
    if not email and not phone:
        raise HTTPException(status_code=422, detail="Cần ít nhất email hoặc số điện thoại.")

    conditions = []
    if email:
        conditions.append(func.lower(AppUser.email) == email)
    if phone:
        conditions.append(AppUser.phone == phone)
    if conditions and db.scalar(select(AppUser.id).where(or_(*conditions)).limit(1)):
        raise HTTPException(status_code=409, detail="Email hoặc số điện thoại đã được sử dụng.")

    user = AppUser(
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        display_name=name,
        locale=locale or "vi",
        role=role,
        is_staff=role in {"staff", "admin"},
        is_active=True,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email hoặc số điện thoại đã được sử dụng.") from exc
    return user


def authenticate(db: Session, identifier: str, password: str) -> AppUser:
    identifier_raw = identifier.strip()
    email = normalize_email(identifier_raw) if "@" in identifier_raw else None
    phone = normalize_phone(identifier_raw)

    conditions = []
    if email:
        conditions.append(func.lower(AppUser.email) == email)
    if phone:
        conditions.append(AppUser.phone == phone)
    if not conditions:
        raise HTTPException(status_code=401, detail="Thông tin đăng nhập không hợp lệ.")

    user = db.scalar(select(AppUser).where(or_(*conditions)).limit(1))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email/số điện thoại hoặc mật khẩu không đúng.")

    user.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return user


def issue_session(db: Session, user: AppUser) -> str:
    settings = get_settings()
    raw_token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=_token_hash(raw_token),
        expires_at=now + timedelta(days=max(1, int(settings.auth_session_days))),
        last_used_at=now,
    )
    db.add(auth_session)
    db.commit()
    return raw_token


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bạn chưa đăng nhập.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token đăng nhập không hợp lệ.")
    return token.strip()


def resolve_user_from_token(db: Session, raw_token: str) -> tuple[AppUser, AuthSession]:
    now = datetime.now(timezone.utc)
    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == _token_hash(raw_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        ).limit(1)
    )
    if not auth_session:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập đã hết hạn hoặc không hợp lệ.")
    user = db.get(AppUser, auth_session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Tài khoản không còn hoạt động.")
    auth_session.last_used_at = now
    db.commit()
    return user, auth_session


def get_current_user(authorization: str | None = Header(default=None)) -> AppUser:
    token = _extract_bearer(authorization)
    with open_session() as db:
        user, _ = resolve_user_from_token(db, token)
        db.expunge(user)
        return user


def get_optional_user(authorization: str | None = Header(default=None)) -> AppUser | None:
    if not authorization:
        return None
    return get_current_user(authorization)


def require_staff(user: AppUser = Depends(get_current_user)) -> AppUser:
    if user.role not in {"staff", "admin"}:
        raise HTTPException(status_code=403, detail="Chỉ nhân viên tư vấn hoặc admin được phép truy cập.")
    return user


def require_admin(user: AppUser = Depends(get_current_user)) -> AppUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Chỉ admin được phép thực hiện thao tác này.")
    return user


def revoke_current_session(db: Session, raw_token: str) -> None:
    auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(raw_token)).limit(1))
    if auth_session and auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(timezone.utc)
        db.commit()
