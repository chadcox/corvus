from collections.abc import Generator

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_migrations() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


def current_db_revision() -> str | None:
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
            if not row:
                return None
            return str(row[0])
    except Exception:
        return None


def init_db() -> None:
    from app.auth.bootstrap import ensure_bootstrap_admin

    _run_migrations()
    with SessionLocal() as db:
        ensure_bootstrap_admin(db)
