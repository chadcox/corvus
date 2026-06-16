from __future__ import annotations

from datetime import datetime
import hashlib
import ipaddress
import logging
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.auth.providers import LocalAuthProvider
from app.auth.service import (
    bearer_scheme,
    create_access_token,
    get_current_user,
    require_admin,
    revoke_access_token,
)
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
provider = LocalAuthProvider()
logger = logging.getLogger(__name__)

LOGIN_ATTEMPT_WINDOW_SECONDS = 300
LOGIN_LOCKOUT_SECONDS = 600
MAX_LOGIN_ATTEMPTS = 5


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class AuthUserRead(BaseModel):
    id: UUID
    username: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserRead


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=512)
    role: str = Field(pattern="^(administrator|analyst)$")
    is_active: bool = True


class UserUpdateRoleRequest(BaseModel):
    role: str = Field(pattern="^(administrator|analyst)$")


class UserPasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=512)


class UserStatusUpdateRequest(BaseModel):
    is_active: bool


def _active_admin_count(db: Session) -> int:
    return (
        db.query(User)
        .filter(User.role == "administrator", User.is_active.is_(True))
        .count()
    )


def _client_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    client_host = request.client.host if request.client and request.client.host else ""
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for and _is_trusted_proxy(client_host):
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    if client_host:
        return client_host
    return "unknown"


def _is_trusted_proxy(host: str) -> bool:
    if not host:
        return False
    trusted = settings.auth_trusted_proxy_list
    if not trusted:
        return False
    if "*" in trusted:
        return True
    try:
        host_ip = ipaddress.ip_address(host)
    except ValueError:
        return host in trusted

    for candidate in trusted:
        try:
            if host_ip in ipaddress.ip_network(candidate, strict=False):
                return True
        except ValueError:
            if host == candidate:
                return True
    return False


def _username_hash(username: str) -> str:
    return hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _lock_key(ip: str, username: str) -> str:
    return f"auth:lock:{ip}:{_username_hash(username)}"


def _attempt_keys(ip: str, username: str) -> list[str]:
    username_h = _username_hash(username)
    return [f"auth:attempts:ip-user:{ip}:{username_h}", f"auth:attempts:user:{username_h}"]


def _is_locked_out(ip: str, username: str) -> bool:
    try:
        return bool(_redis_client().exists(_lock_key(ip, username)))
    except redis.RedisError:
        logger.warning("Redis unavailable while checking login lockout", exc_info=True)
        return False


def _record_failed_login(ip: str, username: str) -> None:
    try:
        client = _redis_client()
        max_seen = 0
        for key in _attempt_keys(ip, username):
            attempts = int(client.incr(key))
            max_seen = max(max_seen, attempts)
            if attempts == 1:
                client.expire(key, LOGIN_ATTEMPT_WINDOW_SECONDS)

        if max_seen >= MAX_LOGIN_ATTEMPTS:
            lock_key = _lock_key(ip, username)
            client.set(lock_key, "1", ex=LOGIN_LOCKOUT_SECONDS)
            logger.warning(
                "Login lockout activated",
                extra={"client_ip": ip, "username_hash": _username_hash(username)},
            )
    except redis.RedisError:
        logger.warning("Redis unavailable while recording failed login", exc_info=True)


def _clear_failed_login_state(ip: str, username: str) -> None:
    try:
        _redis_client().delete(*_attempt_keys(ip, username), _lock_key(ip, username))
    except redis.RedisError:
        logger.warning("Redis unavailable while clearing login counters", exc_info=True)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    username = payload.username.strip()
    client_ip = _client_ip(request)

    if _is_locked_out(client_ip, username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please retry later.",
        )

    auth_user = provider.authenticate(db, username, payload.password)
    if not auth_user:
        _record_failed_login(client_ip, username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    user = db.get(User, auth_user.id)
    assert user is not None
    _clear_failed_login_state(client_ip, username)
    token = create_access_token(user_id=str(user.id), role=user.role)
    return LoginResponse(access_token=token, user=AuthUserRead.model_validate(user, from_attributes=True))


@router.post("/logout")
def logout(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, str]:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    revoke_access_token(creds.credentials)
    return {"message": "Logged out"}


@router.get("/me", response_model=AuthUserRead)
def me(user: User = Depends(get_current_user)) -> AuthUserRead:
    return AuthUserRead.model_validate(user, from_attributes=True)


@router.get("/users", response_model=list[AuthUserRead])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[AuthUserRead]:
    users = db.query(User).order_by(User.created_at.asc()).all()
    return [AuthUserRead.model_validate(u, from_attributes=True) for u in users]


@router.post("/users", response_model=AuthUserRead, status_code=201)
def create_user(
    payload: UserCreateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuthUserRead:
    username = payload.username.strip()
    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=409, detail=f'User "{username}" already exists')

    user = User(
        username=username,
        password_hash=provider.hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthUserRead.model_validate(user, from_attributes=True)


@router.patch("/users/{user_id}/role", response_model=AuthUserRead)
def update_user_role(
    user_id: UUID,
    payload: UserUpdateRoleRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuthUserRead:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if (
        user.role == "administrator"
        and payload.role != "administrator"
        and user.is_active
        and _active_admin_count(db) <= 1
    ):
        raise HTTPException(
            status_code=400,
            detail="Cannot demote the last active administrator",
        )
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return AuthUserRead.model_validate(user, from_attributes=True)


@router.patch("/users/{user_id}/active", response_model=AuthUserRead)
def update_user_active(
    user_id: UUID,
    payload: UserStatusUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuthUserRead:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if (
        user.role == "administrator"
        and user.is_active
        and not payload.is_active
        and _active_admin_count(db) <= 1
    ):
        raise HTTPException(
            status_code=400,
            detail="Cannot disable the last active administrator",
        )
    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return AuthUserRead.model_validate(user, from_attributes=True)


@router.post("/users/{user_id}/password", response_model=AuthUserRead)
def reset_user_password(
    user_id: UUID,
    payload: UserPasswordResetRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuthUserRead:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = provider.hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return AuthUserRead.model_validate(user, from_attributes=True)
