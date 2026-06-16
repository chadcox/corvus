from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory


EXPECTED_CHAIN = [
    "20260601_0001",
    "20260601_0002",
    "20260601_0003",
    "20260601_0004",
    "20260601_0005",
    "20260601_0006",
]


def _script_dir() -> ScriptDirectory:
    cfg = Config("alembic.ini")
    return ScriptDirectory.from_config(cfg)


def test_alembic_has_single_head() -> None:
    script = _script_dir()
    heads = script.get_heads()
    assert heads == [EXPECTED_CHAIN[-1]]


def test_alembic_linear_chain_matches_expected() -> None:
    script = _script_dir()
    rev = script.get_revision(EXPECTED_CHAIN[-1])
    assert rev is not None

    chain: list[str] = []
    while rev is not None:
        chain.append(rev.revision)
        rev = script.get_revision(rev.down_revision) if rev.down_revision else None

    assert list(reversed(chain)) == EXPECTED_CHAIN
