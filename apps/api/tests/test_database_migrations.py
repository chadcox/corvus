from __future__ import annotations

import app.database as database


class DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


def test_run_migrations_invokes_alembic_upgrade(monkeypatch):
    seen: dict[str, object] = {}

    def fake_upgrade(cfg, revision):
        seen["config"] = cfg
        seen["revision"] = revision

    monkeypatch.setattr(database.command, "upgrade", fake_upgrade)

    database._run_migrations()

    assert seen["revision"] == "head"
    assert getattr(seen["config"], "config_file_name", None).endswith("alembic.ini")


def test_init_db_runs_migrations_then_bootstrap_admin(monkeypatch):
    calls: list[str] = []

    def fake_run_migrations():
        calls.append("migrations")

    def fake_bootstrap_admin(_db):
        calls.append("bootstrap")

    monkeypatch.setattr(database, "_run_migrations", fake_run_migrations)
    monkeypatch.setattr(database, "SessionLocal", lambda: DummySession())

    import app.auth.bootstrap as bootstrap

    monkeypatch.setattr(bootstrap, "ensure_bootstrap_admin", fake_bootstrap_admin)

    database.init_db()

    assert calls == ["migrations", "bootstrap"]
