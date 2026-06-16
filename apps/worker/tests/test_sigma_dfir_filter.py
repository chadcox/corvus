from pathlib import Path

from worker.sigma.dfir_filter import is_dfir_relevant
from worker.sigma.loader import load_sigma_rules


def test_excludes_system_and_application():
    assert not is_dfir_relevant(
        rel_path="rules/windows/builtin/system/win_system_something.yml",
        level="high",
        status="stable",
    )
    assert not is_dfir_relevant(
        rel_path="rules/windows/builtin/application/win_app_something.yml",
        level="high",
        status="stable",
    )


def test_keeps_security_medium():
    assert is_dfir_relevant(
        rel_path="rules/windows/builtin/security/win_security_logon.yml",
        level="medium",
        status="stable",
    )


def test_process_creation_requires_high_or_critical():
    assert is_dfir_relevant(
        rel_path="rules/windows/process_creation/proc_high.yml",
        level="high",
        status="stable",
    )
    assert not is_dfir_relevant(
        rel_path="rules/windows/process_creation/proc_medium.yml",
        level="medium",
        status="stable",
    )


def test_load_sigma_rules_dfir_profile_filters(tmp_path: Path, monkeypatch):
    sec = tmp_path / "rules/windows/builtin/security"
    sys_dir = tmp_path / "rules/windows/builtin/system"
    proc = tmp_path / "rules/windows/process_creation"
    for d in (sec, sys_dir, proc):
        d.mkdir(parents=True)

    (sec / "good.yml").write_text(
        "title: Good\nlogsource:\n  product: windows\n  service: security\ndetection:\n  selection:\n    EventID: 4624\n  condition: selection\nlevel: high\n",
        encoding="utf-8",
    )
    (sys_dir / "noise.yml").write_text(
        "title: Noise\nlogsource:\n  product: windows\n  service: system\ndetection:\n  selection:\n    EventID: 1\n  condition: selection\nlevel: high\n",
        encoding="utf-8",
    )
    (proc / "med.yml").write_text(
        "title: Med Proc\nlogsource:\n  product: windows\n  category: process_creation\ndetection:\n  selection:\n    Image: cmd.exe\n  condition: selection\nlevel: medium\n",
        encoding="utf-8",
    )
    (proc / "hi.yml").write_text(
        "title: Hi Proc\nlogsource:\n  product: windows\n  category: process_creation\ndetection:\n  selection:\n    Image: powershell.exe\n  condition: selection\nlevel: high\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("worker.sigma.loader.settings.sigma_profile", "dfir")
    rules = load_sigma_rules(tmp_path)
    titles = {r.title for r in rules}
    assert titles == {"Good", "Hi Proc"}
