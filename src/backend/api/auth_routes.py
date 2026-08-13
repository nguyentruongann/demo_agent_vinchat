from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.backend.config import get_settings
from src.backend.models.auth import (
    AuthResponse,
    BootstrapAdminRequest,
    LoginRequest,
    RegisterRequest,
    StaffCreateRequest,
    StaffUpdateRequest,
    UserPublic,
)
from src.backend.services.auth import (
    _extract_bearer,
    authenticate,
    create_user,
    ensure_unique_contacts,
    get_current_user,
    issue_session,
    normalize_email,
    normalize_phone,
    require_admin,
    revoke_current_session,
    user_public,
)
from src.backend.services.db import open_session
from src.data_postgre.db.app import AppUser

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest) -> AuthResponse:
    with open_session() as db:
        user = create_user(
            db,
            name=payload.name,
            email=str(payload.email) if payload.email else None,
            phone=payload.phone,
            password=payload.password,
            role="customer",
            locale=payload.locale,
        )
        token = issue_session(db, user)
        return AuthResponse(access_token=token, user=user_public(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    with open_session() as db:
        user = authenticate(db, payload.identifier, payload.password)
        token = issue_session(db, user)
        return AuthResponse(access_token=token, user=user_public(user))


@router.get("/me", response_model=UserPublic)
def me(user: AppUser = Depends(get_current_user)) -> UserPublic:
    return user_public(user)


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    token = _extract_bearer(authorization)
    with open_session() as db:
        revoke_current_session(db, token)
    return {"ok": True}


@router.post("/bootstrap-admin", response_model=AuthResponse, status_code=201)
def bootstrap_admin(payload: BootstrapAdminRequest) -> AuthResponse:
    settings = get_settings()
    if not settings.admin_bootstrap_key or payload.bootstrap_key != settings.admin_bootstrap_key:
        raise HTTPException(status_code=403, detail="Bootstrap key không hợp lệ.")
    with open_session() as db:
        existing_admin = db.scalar(select(AppUser.id).where(AppUser.role == "admin").limit(1))
        if existing_admin:
            raise HTTPException(status_code=409, detail="Admin đã tồn tại. Hãy dùng tài khoản admin để tạo nhân viên.")
        user = create_user(
            db,
            name=payload.name,
            email=str(payload.email) if payload.email else None,
            phone=payload.phone,
            password=payload.password,
            role="admin",
            locale=payload.locale,
        )
        token = issue_session(db, user)
        return AuthResponse(access_token=token, user=user_public(user))


@router.get("/staff", response_model=list[UserPublic])
def list_staff(_: AppUser = Depends(require_admin)) -> list[UserPublic]:
    with open_session() as db:
        users = db.scalars(select(AppUser).where(AppUser.role.in_(["staff", "admin"])).order_by(AppUser.created_at)).all()
        return [user_public(item) for item in users]


@router.post("/staff", response_model=UserPublic, status_code=201)
def create_staff(payload: StaffCreateRequest, _: AppUser = Depends(require_admin)) -> UserPublic:
    with open_session() as db:
        user = create_user(
            db,
            name=payload.name,
            email=str(payload.email) if payload.email else None,
            phone=payload.phone,
            password=payload.password,
            role=payload.role,
            locale=payload.locale,
        )
        return user_public(user)


@router.patch("/staff/{user_id}", response_model=UserPublic)
def update_staff(user_id: str, payload: StaffUpdateRequest, current: AppUser = Depends(require_admin)) -> UserPublic:
    with open_session() as db:
        from uuid import UUID
        try:
            parsed_user_id = UUID(user_id)
            user = db.get(AppUser, parsed_user_id)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.") from exc
        if not user or user.role not in {"staff", "admin"}:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản nhân viên.")
        if str(user.id) == str(current.id) and payload.is_active is False:
            raise HTTPException(status_code=400, detail="Admin không thể tự vô hiệu hóa tài khoản đang đăng nhập.")
        if payload.name is not None:
            user.display_name = payload.name.strip()
        if payload.email is not None:
            user.email = normalize_email(str(payload.email))
        if payload.phone is not None:
            user.phone = normalize_phone(payload.phone)
        if payload.role is not None:
            user.role = payload.role
            user.is_staff = True
        if payload.is_active is not None:
            user.is_active = payload.is_active
        if not user.email and not user.phone:
            raise HTTPException(status_code=422, detail="Tài khoản phải có email hoặc số điện thoại.")

        ensure_unique_contacts(
            db,
            email=user.email,
            phone=user.phone,
            exclude_user_id=user.id,
        )
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Email hoặc số điện thoại đã được sử dụng.",
            ) from exc
        return user_public(user)
