from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.auth.providers import LocalAuthProvider


def ensure_bootstrap_admin(db: Session) -> None:
    username = settings.auth_bootstrap_admin_username.strip()
    password = settings.auth_bootstrap_admin_password
    if not username or not password:
        return

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return

    provider = LocalAuthProvider()
    user = User(
        username=username,
        password_hash=provider.hash_password(password),
        role="administrator",
        is_active=True,
    )
    db.add(user)
    db.commit()
