from __future__ import annotations

from datetime import UTC, datetime, timedelta
from collections import deque
from typing import Annotated
from uuid import uuid4

import jwt
import redis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)
_REVOCATION_FAILURE_WINDOW_SECONDS = 300
_REVOCATION_FAILURES: deque[float] = deque()
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


class TokenPayload(BaseModel):
    sub: str
    role: str
    exp: int
    jti: str


def create_access_token(*, user_id: str, role: str) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.auth_token_exp_minutes)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int(exp.timestamp()),
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_jwt_algorithm)


def _revocation_key(jti: str) -> str:
    return f"{settings.auth_revocation_prefix}:{jti}"


def revoke_access_token(token: str) -> None:
    payload = decode_access_token(token)
    ttl_seconds = max(payload.exp - int(datetime.now(UTC).timestamp()), 1)
    try:
        _get_redis().set(
            _revocation_key(payload.jti),
            "1",
            ex=ttl_seconds,
        )
    except redis.RedisError as exc:
        _record_revocation_failure()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Logout unavailable",
        ) from exc


def is_token_revoked(jti: str) -> bool:
    try:
        return bool(_get_redis().exists(_revocation_key(jti)))
    except redis.RedisError:
        return bool(settings.auth_revocation_fail_closed)


def _record_revocation_failure() -> None:
    now = datetime.now(UTC).timestamp()
    _REVOCATION_FAILURES.append(now)
    cutoff = now - _REVOCATION_FAILURE_WINDOW_SECONDS
    while _REVOCATION_FAILURES and _REVOCATION_FAILURES[0] < cutoff:
        _REVOCATION_FAILURES.popleft()


def recent_revocation_failures() -> int:
    now = datetime.now(UTC).timestamp()
    cutoff = now - _REVOCATION_FAILURE_WINDOW_SECONDS
    while _REVOCATION_FAILURES and _REVOCATION_FAILURES[0] < cutoff:
        _REVOCATION_FAILURES.popleft()
    return len(_REVOCATION_FAILURES)


def decode_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=[settings.auth_jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    return TokenPayload.model_validate(payload)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> User:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    token_payload = decode_access_token(creds.credentials)
    if is_token_revoked(token_payload.jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = db.get(User, token_payload.sub)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "administrator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return user
