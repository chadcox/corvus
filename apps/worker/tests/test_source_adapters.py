from pathlib import Path
from uuid import uuid4

from worker.sources.registry import select_source_adapter
from worker.sources.generic import GenericDirectoryAdapter
from worker.sources.uac import UacImportAdapter


def test_kape_compat_adapter_selected_for_collector(tmp_path: Path):
    adapter = select_source_adapter(tmp_path, platform="windows", collector="kape")
    assert adapter.name == "kape_compat"


def test_generic_adapter_selected_for_plain_directory(tmp_path: Path):
    adapter = select_source_adapter(tmp_path, platform="linux", collector="import")
    assert adapter.name == "generic_directory"


def test_uac_adapter_selected_for_collector(tmp_path: Path):
    adapter = select_source_adapter(tmp_path, platform="linux", collector="uac")
    assert adapter.name == "uac_import"


def test_uac_adapter_selected_for_wrapped_uac_package(tmp_path: Path):
    wrapped = tmp_path / "host-uac-output"
    wrapped.mkdir()
    (wrapped / "uac.log").write_text("started", encoding="utf-8")

    adapter = select_source_adapter(tmp_path, platform="linux", collector="import")
    assert adapter.name == "uac_import"


def test_uac_adapter_selected_for_deep_wrapped_uac_package(tmp_path: Path):
    wrapped = tmp_path / "[root]" / "host-uac-output"
    wrapped.mkdir(parents=True)
    (wrapped / "uac.log").write_text("started", encoding="utf-8")

    adapter = select_source_adapter(tmp_path, platform="linux", collector="import")
    assert adapter.name == "uac_import"


def test_uac_adapter_preferred_over_kape_when_uac_markers_present(tmp_path: Path):
    (tmp_path / "C").mkdir()
    (tmp_path / "uac.log").write_text("started", encoding="utf-8")

    adapter = select_source_adapter(tmp_path, platform="linux", collector="import")
    assert adapter.name == "uac_import"


def test_uac_ingest_overrides_windows_platform_for_filesystem(tmp_path: Path):
    (tmp_path / "uac.log").write_text("started", encoding="utf-8")
    (tmp_path / "var" / "log").mkdir(parents=True)
    (tmp_path / "var" / "log" / "syslog").write_text("line", encoding="utf-8")

    result = UacImportAdapter().ingest(
        tmp_path,
        uuid4(),
        platform="windows",
        collector="import",
        manifest=None,
    )

    paths = {node["full_path"] for node in result["filesystem_nodes"]}
    assert "/var/log/syslog" in paths


def test_generic_linux_directory_indexes_package_tree(tmp_path: Path):
    log_dir = tmp_path / "var" / "log"
    log_dir.mkdir(parents=True)
    (log_dir / "auth.log").write_text("session opened", encoding="utf-8")

    result = GenericDirectoryAdapter().ingest(
        tmp_path,
        uuid4(),
        platform="linux",
        collector="import",
        manifest=None,
    )

    paths = {node["full_path"] for node in result["filesystem_nodes"]}
    assert "/var/log/auth.log" in paths


def test_velociraptor_adapter_selected_for_collector(tmp_path: Path):
    adapter = select_source_adapter(tmp_path, platform="linux", collector="velociraptor")
    assert adapter.name == "velociraptor_import"


def test_unknown_collector_falls_back_to_generic_adapter(tmp_path: Path):
    adapter = select_source_adapter(tmp_path, platform="linux", collector="custom")
    assert adapter.name == "generic_directory"


def test_mac_apt_adapter_selected_for_macos(tmp_path: Path):
    adapter = select_source_adapter(tmp_path, platform="macos", collector="import")
    assert adapter.name == "mac_apt"


def test_volatility3_adapter_selected_for_collector(tmp_path: Path):
    adapter = select_source_adapter(tmp_path, platform="windows", collector="volatility3")
    assert adapter.name == "volatility3"


def test_volatility3_adapter_selected_for_windows_memory_image(tmp_path: Path):
    (tmp_path / "memory.vmem").write_bytes(b"fake")
    adapter = select_source_adapter(tmp_path, platform="windows", collector="import")
    assert adapter.name == "volatility3"


def test_volatility3_adapter_selected_for_memory_platform(tmp_path: Path):
    (tmp_path / "capture.raw").write_bytes(b"fake")
    adapter = select_source_adapter(tmp_path, platform="memory", collector="import")
    assert adapter.name == "volatility3"
