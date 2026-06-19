from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import bcrypt
from sqlalchemy.orm import Session

from app.models import User

# Compared against when the user is missing/inactive so login timing stays
# constant regardless of whether the username exists (avoids enumeration).
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"corvus-dummy-password", bcrypt.gensalt()).decode("utf-8")


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str
    role: str
    is_active: bool


class AuthProvider(Protocol):
    """Authentication backend abstraction for local auth and future OIDC."""

    def authenticate(self, db: Session, username: str, password: str) -> AuthenticatedUser | None:
        ...


class LocalAuthProvider:
    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False

    def authenticate(self, db: Session, username: str, password: str) -> AuthenticatedUser | None:
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            self.verify_password(password, _DUMMY_PASSWORD_HASH)
            return None
        if not self.verify_password(password, user.password_hash):
            return None
        return AuthenticatedUser(
            id=str(user.id),
            username=user.username,
            role=user.role,
            is_active=user.is_active,
        )


class OidcAuthProvider:
    """Placeholder provider for future Entra ID / OIDC integration."""

    def authenticate(self, db: Session, username: str, password: str) -> AuthenticatedUser | None:
        raise NotImplementedError("OIDC provider is not implemented yet")
