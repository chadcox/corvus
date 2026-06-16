from pathlib import Path
from unittest.mock import patch

from worker.chainsaw.sigma_rules import resolve_sigma_rules_root


def test_resolve_sigma_off_when_include_sigma_false(tmp_path: Path):
    with patch("worker.chainsaw.sigma_rules.settings") as mock_settings:
        mock_settings.chainsaw_include_sigma = False
        mock_settings.chainsaw_sigma_profile = "dfir"
        mock_settings.sigma_rules_root = str(tmp_path)
        assert resolve_sigma_rules_root() is None


def test_resolve_sigma_full_returns_source(tmp_path: Path):
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "test.yml").write_text("title: t\nlevel: high\n", encoding="utf-8")

    with patch("worker.chainsaw.sigma_rules.settings") as mock_settings:
        mock_settings.chainsaw_include_sigma = True
        mock_settings.chainsaw_sigma_profile = "full"
        mock_settings.sigma_rules_root = str(rules)
        assert resolve_sigma_rules_root("full") == rules
