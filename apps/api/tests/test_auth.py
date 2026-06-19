from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.auth.providers import LocalAuthProvider
import app.auth.service as auth_service
from app.auth.service import create_access_token, get_current_user, require_admin
from app.config import Settings, validate_security_settings
from app.models import User
from app.routers import auth


@pytest.fixture(autouse=True)
def _reset_pooled_redis():
    # Service now reuses a module-level Redis client; clear it so each test's
    # monkeypatched redis.Redis.from_url is honored.
    auth_service._redis_client = None
    yield
    auth_service._redis_client = None


@dataclass
class FakeUser:
    id: uuid.UUID
    username: str
    password_hash: str
    role: str
    is_active: bool = True
    created_at: str = "2026-01-01T00:00:00Z"
    updated_at: str = "2026-01-01T00:00:00Z"


class FakeQuery:
    def __init__(self, db: "FakeDb"):
        self.db = db
        self._username = None

    def filter(self, expr):
        rhs = getattr(expr, "right", None)
        self._username = getattr(rhs, "value", None)
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        if self._username is None:
            return None
        return self.db.users_by_name.get(self._username)

    def all(self):
        return list(self.db.users.values())


class FakeDb:
    def __init__(self, users: list[FakeUser]):
        self.users = {str(u.id): u for u in users}
        self.users_by_name = {u.username: u for u in users}

    def query(self, _model):
        return FakeQuery(self)

    def get(self, _model, key):
        return self.users.get(str(key))

    def add(self, user):
        self.users[str(user.id)] = user
        self.users_by_name[user.username] = user

    def commit(self):
        return None

    def refresh(self, _user):
        return None


class FakeRedis:
    def __init__(self):
        self._values: dict[str, int] = {}

    def exists(self, key: str) -> int:
        return 1 if key in self._values else 0

    def incr(self, key: str) -> int:
        value = int(self._values.get(key, 0)) + 1
        self._values[key] = value
        return value

    def expire(self, _key: str, _seconds: int) -> bool:
        return True

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        _ = (value, ex)
        self._values[key] = 1
        return True

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._values:
                removed += 1
                self._values.pop(key, None)
        return removed


class FailingRedis:
    def exists(self, *args, **kwargs):
        _ = (args, kwargs)
        raise auth_service.redis.RedisError("down")

    def set(self, *args, **kwargs):
        _ = (args, kwargs)
        raise auth_service.redis.RedisError("down")


def _make_request(ip: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [],
        "client": (ip, 12345),
    }
    return Request(scope)


def test_password_hashing_and_verify():
    provider = LocalAuthProvider()
    password = "Sup3r-Secret!"
    password_hash = provider.hash_password(password)
    assert password_hash != password
    assert provider.verify_password(password, password_hash)
    assert not provider.verify_password("wrong", password_hash)


def test_login_success_and_failure():
    provider = LocalAuthProvider()
    user = FakeUser(
        id=uuid.uuid4(),
        username="alice",
        password_hash=provider.hash_password("correct-password"),
        role="analyst",
    )
    db = FakeDb([user])

    ok = auth.login(auth.LoginRequest(username="alice", password="correct-password"), request=_make_request(), db=db)
    assert ok.access_token
    assert ok.user.username == "alice"

    with pytest.raises(HTTPException) as exc:
        auth.login(auth.LoginRequest(username="alice", password="nope"), request=_make_request(), db=db)
    assert exc.value.status_code == 401


def test_login_lockout_after_repeated_failures(monkeypatch):
    provider = LocalAuthProvider()
    user = FakeUser(
        id=uuid.uuid4(),
        username="alice",
        password_hash=provider.hash_password("correct-password"),
        role="analyst",
    )
    db = FakeDb([user])

    state = {"locked": False, "failures": 0}

    monkeypatch.setattr(auth, "_client_ip", lambda _request: "127.0.0.1")
    monkeypatch.setattr(auth, "_is_locked_out", lambda _ip, _username: state["locked"])

    def _record(_ip, _username):
        state["failures"] += 1
        if state["failures"] >= auth.MAX_LOGIN_ATTEMPTS:
            state["locked"] = True

    monkeypatch.setattr(auth, "_record_failed_login", _record)
    monkeypatch.setattr(auth, "_clear_failed_login_state", lambda _ip, _username: None)

    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        with pytest.raises(HTTPException) as exc:
            auth.login(auth.LoginRequest(username="alice", password="wrong"), request=_make_request(), db=db)
        assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        auth.login(auth.LoginRequest(username="alice", password="correct-password"), request=_make_request(), db=db)
    assert exc.value.status_code == 429


def test_login_success_clears_failed_state(monkeypatch):
    provider = LocalAuthProvider()
    user = FakeUser(
        id=uuid.uuid4(),
        username="alice",
        password_hash=provider.hash_password("correct-password"),
        role="analyst",
    )
    db = FakeDb([user])

    cleared: list[tuple[str, str]] = []
    monkeypatch.setattr(auth, "_client_ip", lambda _request: "127.0.0.1")
    monkeypatch.setattr(auth, "_is_locked_out", lambda _ip, _username: False)
    monkeypatch.setattr(auth, "_record_failed_login", lambda _ip, _username: None)
    monkeypatch.setattr(auth, "_clear_failed_login_state", lambda ip, username: cleared.append((ip, username)))

    auth.login(auth.LoginRequest(username="alice", password="correct-password"), request=_make_request(), db=db)
    assert cleared == [("127.0.0.1", "alice")]


def test_validate_security_settings_rejects_default_secret_in_production():
    cfg = Settings(environment="production", auth_secret_key="change-me-dev-auth-secret")
    with pytest.raises(RuntimeError):
        validate_security_settings(cfg)


def test_validate_security_settings_allows_default_secret_in_development():
    cfg = Settings(environment="development", auth_secret_key="change-me-dev-auth-secret")
    validate_security_settings(cfg)


def test_login_route_lockout_integration(monkeypatch):
    provider = LocalAuthProvider()
    user = FakeUser(
        id=uuid.uuid4(),
        username="alice",
        password_hash=provider.hash_password("correct-password"),
        role="analyst",
    )
    db = FakeDb([user])
    fake_redis = FakeRedis()

    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1")

    def _override_get_db():
        yield db

    app.dependency_overrides[auth.get_db] = _override_get_db
    monkeypatch.setattr(auth, "_redis_client", lambda: fake_redis)

    client = TestClient(app)
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        resp = client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong"})
        assert resp.status_code == 401

    lockout_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "correct-password"},
    )
    assert lockout_resp.status_code == 429

    fake_redis.delete(*auth._attempt_keys("testclient", "alice"), auth._lock_key("testclient", "alice"))
    success_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "correct-password"},
    )
    assert success_resp.status_code == 200
    assert success_resp.json().get("access_token")


def test_logout_revokes_token_and_blocks_future_access(monkeypatch):
    provider = LocalAuthProvider()
    user = FakeUser(
        id=uuid.uuid4(),
        username="alice",
        password_hash=provider.hash_password("correct-password"),
        role="analyst",
    )
    db = FakeDb([user])
    fake_redis = FakeRedis()

    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1")

    def _override_get_db():
        yield db

    app.dependency_overrides[auth.get_db] = _override_get_db
    monkeypatch.setattr(auth, "_redis_client", lambda: fake_redis)
    monkeypatch.setattr("app.auth.service.redis.Redis.from_url", lambda *_args, **_kwargs: fake_redis)

    client = TestClient(app)
    login_resp = client.post("/api/v1/auth/login", json={"username": "alice", "password": "correct-password"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200

    logout_resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200

    blocked_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert blocked_resp.status_code == 401


def test_client_ip_ignores_forwarded_header_from_untrusted_proxy(monkeypatch):
    monkeypatch.setattr(auth.settings, "auth_trusted_proxies", "")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [(b"x-forwarded-for", b"198.51.100.9")],
        "client": ("10.0.0.10", 12345),
    }
    assert auth._client_ip(Request(scope)) == "10.0.0.10"


def test_client_ip_honors_forwarded_header_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(auth.settings, "auth_trusted_proxies", "10.0.0.0/8")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [(b"x-forwarded-for", b"198.51.100.9, 10.0.0.10")],
        "client": ("10.0.0.10", 12345),
    }
    assert auth._client_ip(Request(scope)) == "198.51.100.9"


def test_revoke_access_token_records_failure_count(monkeypatch):
    auth_service._REVOCATION_FAILURES.clear()
    monkeypatch.setattr(
        auth_service.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: FailingRedis(),
    )
    token = create_access_token(user_id=str(uuid.uuid4()), role="analyst")
    with pytest.raises(HTTPException) as exc:
        auth_service.revoke_access_token(token)
    assert exc.value.status_code == 503
    assert auth_service.recent_revocation_failures() == 1


def test_is_token_revoked_fail_open_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(auth_service.settings, "auth_revocation_fail_closed", False)
    monkeypatch.setattr(
        auth_service.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: FailingRedis(),
    )
    assert auth_service.is_token_revoked("jti-123") is False


def test_is_token_revoked_fail_closed_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(auth_service.settings, "auth_revocation_fail_closed", True)
    monkeypatch.setattr(
        auth_service.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: FailingRedis(),
    )
    assert auth_service.is_token_revoked("jti-123") is True


def test_protected_api_access_requires_authentication():
    db = FakeDb([])
    with pytest.raises(HTTPException) as exc:
        get_current_user(None, db=db)
    assert exc.value.status_code == 401


def test_analyst_blocked_from_admin_and_admin_allowed():
    analyst = User(
        id=uuid.uuid4(),
        username="analyst1",
        password_hash=LocalAuthProvider().hash_password("analyst-pass"),
        role="analyst",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    admin = User(
        id=uuid.uuid4(),
        username="admin1",
        password_hash=LocalAuthProvider().hash_password("admin-pass"),
        role="administrator",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    analyst.created_at = datetime.now(UTC)
    analyst.updated_at = datetime.now(UTC)
    admin.created_at = datetime.now(UTC)
    admin.updated_at = datetime.now(UTC)
    fake_db = FakeDb([analyst, admin])

    analyst_token = create_access_token(user_id=str(analyst.id), role=analyst.role)
    admin_token = create_access_token(user_id=str(admin.id), role=admin.role)

    analyst_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=analyst_token)
    admin_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=admin_token)

    analyst_user = get_current_user(analyst_creds, db=fake_db)
    with pytest.raises(HTTPException) as exc:
        require_admin(analyst_user)
    assert exc.value.status_code == 403

    admin_user = get_current_user(admin_creds, db=fake_db)
    require_admin(admin_user)
    users = auth.list_users(admin_user, db=fake_db)
    assert {u.username for u in users} == {"analyst1", "admin1"}
