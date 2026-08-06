from pathlib import Path
from uuid import uuid4

from worker.config import settings
from worker.sources import disk_image as disk_image_module
from worker.sources import external_tools
from worker.sources.disk_image import (
    DiskImageAdapter,
    find_disk_image_in_package,
    looks_like_disk_image,
)
from worker.sources.registry import select_source_adapter

EWF_HEADER = b"EVF\x09\x0d\x0a\xff\x00"


def write_ewf(path: Path) -> Path:
    path.write_bytes(EWF_HEADER + b"\x01\x00\x00\x00" + b"\x00" * 512)
    return path


def write_mbr_raw(path: Path) -> Path:
    data = bytearray(b"\x00" * 1024)
    data[510:512] = b"\x55\xaa"
    path.write_bytes(bytes(data))
    return path


def write_gpt_raw(path: Path) -> Path:
    data = bytearray(b"\x00" * 1024)
    data[512:520] = b"EFI PART"
    path.write_bytes(bytes(data))
    return path


def write_memory_dump(path: Path) -> Path:
    """A memory capture: .raw extension, but no MBR/GPT structures."""
    path.write_bytes(b"\x00" * 2048)
    return path


# --- content detection -------------------------------------------------


def test_ewf_image_detected_by_magic(tmp_path: Path):
    assert looks_like_disk_image(write_ewf(tmp_path / "disk.E01"))


def test_e01_extension_without_ewf_magic_rejected(tmp_path: Path):
    (tmp_path / "notreally.E01").write_bytes(b"fake" * 100)
    assert not looks_like_disk_image(tmp_path / "notreally.E01")


def test_raw_image_detected_by_mbr_signature(tmp_path: Path):
    assert looks_like_disk_image(write_mbr_raw(tmp_path / "disk.raw"))


def test_raw_image_detected_by_gpt_signature(tmp_path: Path):
    assert looks_like_disk_image(write_gpt_raw(tmp_path / "disk.dd"))


def test_memory_capture_not_treated_as_disk_image(tmp_path: Path):
    assert not looks_like_disk_image(write_memory_dump(tmp_path / "memdump.raw"))


def test_unrelated_extension_ignored(tmp_path: Path):
    write_mbr_raw(tmp_path / "notes.txt")
    assert not looks_like_disk_image(tmp_path / "notes.txt")


def test_empty_file_ignored(tmp_path: Path):
    (tmp_path / "empty.raw").write_bytes(b"")
    assert not looks_like_disk_image(tmp_path / "empty.raw")


# --- package scanning --------------------------------------------------


def test_find_image_prefers_ewf_over_raw(tmp_path: Path):
    write_mbr_raw(tmp_path / "a-disk.raw")
    write_ewf(tmp_path / "z-disk.E01")
    found = find_disk_image_in_package(tmp_path)
    assert found is not None and found.name == "z-disk.E01"


def test_find_image_returns_none_for_triage_package(tmp_path: Path):
    (tmp_path / "C" / "Windows").mkdir(parents=True)
    (tmp_path / "C" / "Windows" / "SYSTEM").write_bytes(b"regf" + b"\x00" * 100)
    assert find_disk_image_in_package(tmp_path) is None


def test_manifest_declaration_wins_over_scan(tmp_path: Path):
    write_ewf(tmp_path / "auto.E01")
    declared = tmp_path / "nested" / "declared.vhdx"
    declared.parent.mkdir()
    declared.write_bytes(b"custom-format")
    found = find_disk_image_in_package(tmp_path, {"disk_image_path": "nested/declared.vhdx"})
    assert found == declared.resolve()


def test_manifest_path_traversal_rejected(tmp_path: Path):
    outside = tmp_path.parent / "outside-secret.E01"
    write_ewf(outside)
    package = tmp_path / "pkg"
    package.mkdir()
    found = find_disk_image_in_package(package, {"disk_image_path": "../outside-secret.E01"})
    assert found is None


def test_missing_manifest_image_falls_back_to_scan(tmp_path: Path):
    write_ewf(tmp_path / "real.E01")
    found = find_disk_image_in_package(tmp_path, {"disk_image_path": "gone.E01"})
    assert found is not None and found.name == "real.E01"


# --- adapter selection -------------------------------------------------


def test_disk_image_adapter_selected_for_real_image(tmp_path: Path):
    write_ewf(tmp_path / "disk.E01")
    adapter = select_source_adapter(tmp_path, platform="windows", collector="import")
    assert adapter.name == "disk_image"


def test_memory_package_not_hijacked_by_disk_adapter(tmp_path: Path):
    """Regression: a .raw memory capture must not be claimed as a disk image."""
    write_memory_dump(tmp_path / "memdump.raw")
    assert not DiskImageAdapter().supports(tmp_path, platform="memory", collector="import")
    adapter = select_source_adapter(tmp_path, platform="memory", collector="import")
    assert adapter.name == "volatility3"


def test_windows_triage_package_not_hijacked(tmp_path: Path):
    (tmp_path / "C").mkdir()
    (tmp_path / "C" / "$MFT").write_bytes(b"FILE0" + b"\x00" * 100)
    adapter = select_source_adapter(tmp_path, platform="windows", collector="import")
    assert adapter.name != "disk_image"


def test_disk_platform_selects_adapter_without_image(tmp_path: Path):
    adapter = select_source_adapter(tmp_path, platform="disk", collector="import")
    assert adapter.name == "disk_image"


# --- ingest behaviour --------------------------------------------------


def test_ingest_without_plaso_degrades_and_still_indexes(tmp_path: Path, monkeypatch):
    write_ewf(tmp_path / "disk.E01")
    monkeypatch.setattr(disk_image_module, "plaso_available", lambda: False)

    result = DiskImageAdapter().ingest(
        tmp_path,
        uuid4(),
        platform="disk",
        collector="import",
        manifest=None,
    )

    notes = " ".join(result["ingest_notes"])
    assert "Plaso is not installed" in notes
    assert "disk.E01" in notes
    # Falls through to the generic adapter rather than returning nothing.
    assert result["filesystem_nodes"]


def test_ingest_reports_missing_image(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(disk_image_module, "plaso_available", lambda: False)
    result = DiskImageAdapter().ingest(
        tmp_path,
        uuid4(),
        platform="disk",
        collector="import",
        manifest=None,
    )
    assert any("no EWF/E01 or raw disk image" in note for note in result["ingest_notes"])


def test_ingest_runs_plaso_on_image_file_with_partitions(tmp_path: Path, monkeypatch):
    image = write_ewf(tmp_path / "disk.E01")
    captured: dict = {}

    def fake_run_plaso(source, output_dir, *, platform, source_args=None):
        captured["source"] = source
        captured["platform"] = platform
        captured["source_args"] = source_args
        return output_dir / "plaso.jsonl", None

    monkeypatch.setattr(disk_image_module, "plaso_available", lambda: True)
    monkeypatch.setattr(settings, "plaso_enabled", True)
    monkeypatch.setattr(disk_image_module, "run_plaso", fake_run_plaso)
    monkeypatch.setattr(disk_image_module, "parse_tool_outputs", lambda *_a, **_k: [])

    DiskImageAdapter().ingest(
        tmp_path,
        uuid4(),
        platform="disk",
        collector="import",
        manifest=None,
    )

    # Plaso reads the image directly; it is never handed a mount point.
    assert captured["source"] == image
    assert captured["source_args"] == ["--partitions", "all"]


def test_run_plaso_passes_source_args_to_log2timeline(tmp_path: Path, monkeypatch):
    commands: list[list[str]] = []

    def fake_run_command(args, *, timeout, cwd=None):
        assert timeout > 0 and cwd is None
        commands.append(args)
        # Stand in for log2timeline/psort by creating the artifacts they emit.
        for arg in args:
            if arg.endswith((".plaso", ".jsonl")):
                path = Path(arg)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
        return True, None

    monkeypatch.setattr(settings, "plaso_parallel_enabled", False)
    monkeypatch.setattr(external_tools, "run_command", fake_run_command)

    external_tools.run_plaso(
        tmp_path / "disk.E01",
        tmp_path / "out",
        platform="disk",
        source_args=["--partitions", "all"],
    )

    log2timeline_cmd = commands[0]
    assert "--partitions" in log2timeline_cmd
    assert log2timeline_cmd.index("--partitions") == log2timeline_cmd.index("all") - 1
    # Source path stays last.
    assert log2timeline_cmd[-1] == str(tmp_path / "disk.E01")


def test_run_plaso_leaves_only_merged_jsonl_in_output_dir(tmp_path: Path, monkeypatch):
    """Intermediate parts must not survive: the caller rglobs output_dir and
    would ingest every event a second time."""
    commands: list[list[str]] = []

    def fake_run_command(args, *, timeout, cwd=None):
        assert timeout > 0 and cwd is None
        commands.append(args)
        for arg in args:
            if arg.endswith((".plaso", ".jsonl", ".log.gz")):
                path = Path(arg)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"datetime": "2024-01-01T00:00:00Z"}\n', encoding="utf-8")
        return True, None

    monkeypatch.setattr(settings, "plaso_parallel_enabled", True)
    monkeypatch.setattr(settings, "plaso_parallel_jobs", 2)
    monkeypatch.setattr(external_tools, "run_command", fake_run_command)

    out_dir = tmp_path / "_ff_parsed" / "plaso"
    result, err = external_tools.run_plaso(
        tmp_path / "disk.E01", out_dir, platform="windows"
    )

    assert err is None
    assert result == out_dir / "plaso.jsonl"
    # Only the merged output remains anywhere under output_dir.
    leftovers = sorted(p.name for p in out_dir.rglob("*") if p.is_file())
    assert leftovers == ["plaso.jsonl"]
    # Scratch dir is cleaned up rather than left next to the parsed output.
    assert sorted(p.name for p in out_dir.parent.iterdir()) == ["plaso"]
    # Plaso is told where to write its log, since CWD is read-only in the image.
    assert all("--logfile" in cmd for cmd in commands)


def _fs_stat(filename: str, *, entry_type: str = "file", size: int = 0, allocated: bool = True):
    return {
        "data": {
            "data_type": "fs:stat",
            "filename": filename,
            "display_name": f"NTFS:{filename}",
            "file_entry_type": entry_type,
            "file_size": size,
            "is_allocated": allocated,
        }
    }


def test_filesystem_nodes_from_events_builds_tree_from_fs_stat():
    events = [
        _fs_stat("\\Windows\\System32\\cmd.exe", size=289792),
        # Plaso emits one event per timestamp for the same entry.
        _fs_stat("\\Windows\\System32\\cmd.exe", size=289792),
        _fs_stat("\\Windows\\System32", entry_type="directory"),
        _fs_stat("\\$MFT", size=262144),
        {"data": {"data_type": "windows:registry:key_value", "filename": "\\ignored"}},
    ]

    nodes = disk_image_module.filesystem_nodes_from_events(events, "src-1")
    by_path = {n["full_path"]: n for n in nodes}

    assert set(by_path) == {"/Windows", "/Windows/System32", "/Windows/System32/cmd.exe", "/$MFT"}
    cmd = by_path["/Windows/System32/cmd.exe"]
    assert cmd["is_directory"] is False
    assert cmd["size"] == 289792
    assert cmd["parent_path"] == "/Windows/System32"
    assert cmd["name"] == "cmd.exe"
    # Directory entries carry no size, and missing parents are synthesised.
    assert by_path["/Windows/System32"]["is_directory"] is True
    assert by_path["/Windows/System32"]["size"] is None
    assert by_path["/Windows"]["is_directory"] is True
    assert by_path["/Windows"]["parent_path"] is None
    assert by_path["/$MFT"]["parent_path"] is None


def test_filesystem_nodes_from_events_marks_unallocated_as_deleted():
    nodes = disk_image_module.filesystem_nodes_from_events(
        [_fs_stat("\\Users\\jsmith\\mal.exe", size=10, allocated=False)], "src-1"
    )
    deleted = {n["full_path"]: n["is_deleted"] for n in nodes}
    assert deleted["/Users/jsmith/mal.exe"] is True
    # Synthesised parents are not claimed to be deleted.
    assert deleted["/Users"] is False


def test_filesystem_nodes_from_events_keeps_ads_paths_intact():
    """A ':' in a filename is an NTFS alternate data stream, not a URI prefix."""
    nodes = disk_image_module.filesystem_nodes_from_events(
        [_fs_stat("\\$Extend\\$UsnJrnl:$J", size=5)], "src-1"
    )
    assert "/$Extend/$UsnJrnl:$J" in {n["full_path"] for n in nodes}


def test_filesystem_nodes_from_events_respects_limit():
    events = [_fs_stat(f"\\dir\\file{i}") for i in range(50)]
    nodes = disk_image_module.filesystem_nodes_from_events(events, "src-1", limit=10)
    assert len(nodes) <= 10


def test_disk_image_plaso_uses_single_pass_disk_parser_profile():
    """A disk image must be read once, with parsers for every OS."""
    spec = external_tools._plaso_family_spec_for_platform("disk")
    assert external_tools._parse_plaso_families(spec) == []

    parsers = external_tools._plaso_parsers_for_platform("disk").split(",")
    for required in ("winreg", "winevtx", "prefetch", "mft", "usnjrnl", "filestat", "sqlite"):
        assert required in parsers


def test_windows_platform_gets_windows_parsers():
    parsers = external_tools._plaso_parsers_for_platform("windows").split(",")
    assert "winevtx" in parsers and "winreg" in parsers
    families = dict(
        external_tools._parse_plaso_families(
            external_tools._plaso_family_spec_for_platform("windows")
        )
    )
    assert "winevtx" in families["win"]
