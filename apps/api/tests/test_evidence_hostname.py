from pathlib import Path

from app.routers.evidence import _hostname_from_artifacts, _infer_hostname, _platform_for_source
from ff_core.schemas import EvidenceManifest


def test_hostname_from_single_evtx(tmp_path: Path):
    evtx = tmp_path / "Security.evtx"
    evtx.write_bytes(b"fake")
    assert _hostname_from_artifacts(tmp_path) == "Security"


def test_infer_hostname_evtx_upload(tmp_path: Path):
    evtx = tmp_path / "Application.evtx"
    evtx.write_bytes(b"fake")
    assert _infer_hostname(tmp_path, None) == "Application"


def test_platform_from_manifest_alias(tmp_path: Path):
    manifest = EvidenceManifest(platform="darwin")
    assert _platform_for_source(tmp_path, manifest) == "macos"


def test_platform_from_linux_artifact_tree(tmp_path: Path):
    log_dir = tmp_path / "var" / "log"
    log_dir.mkdir(parents=True)
    (log_dir / "auth.log").write_text("session opened", encoding="utf-8")
    assert _platform_for_source(tmp_path, None) == "linux"


def test_platform_from_wrapped_windows_collection(tmp_path: Path):
    wrapped = tmp_path / "WKS-042" / "C" / "Windows" / "System32" / "winevt" / "Logs"
    wrapped.mkdir(parents=True)
    (wrapped / "Security.evtx").write_bytes(b"fake")
    assert _platform_for_source(tmp_path, None) == "windows"


def test_platform_from_uac_wrapped_root(tmp_path: Path):
    (tmp_path / "uac.log").write_text("collector run", encoding="utf-8")
    wrapped = tmp_path / "[root]" / "var" / "log"
    wrapped.mkdir(parents=True)
    (wrapped / "syslog").write_text("line", encoding="utf-8")
    assert _platform_for_source(tmp_path, None) == "linux"


def test_platform_from_memory_artifact(tmp_path: Path):
    (tmp_path / "memdump.raw").write_bytes(b"fake")
    assert _platform_for_source(tmp_path, None) == "memory"


def test_platform_from_manifest_memory_alias(tmp_path: Path):
    manifest = EvidenceManifest(platform="mem")
    assert _platform_for_source(tmp_path, manifest) == "memory"
