from worker.parsers.filesystem_paths import build_filesystem_from_paths


def test_builds_nodes_from_windows_paths():
    events = [
        {"data": {"FullPath": "C:\\Windows\\System32\\cmd.exe"}},
        {"data": {"TargetFilename": "C:\\Users\\jsmith\\Downloads\\mal.exe"}},
    ]
    nodes = build_filesystem_from_paths(events, "src-1")
    paths = {n["full_path"] for n in nodes}
    assert "/C:/Windows/System32/cmd.exe" in paths
    assert "/C:/Users/jsmith/Downloads/mal.exe" in paths


def test_deduplicates_paths():
    events = [
        {"data": {"FullPath": "C:\\Windows\\cmd.exe"}},
        {"data": {"Image": "C:\\Windows\\cmd.exe"}},
    ]
    nodes = build_filesystem_from_paths(events, "src-1")
    assert len(nodes) == 1
    assert nodes[0]["full_path"] == "/C:/Windows/cmd.exe"


def test_scratch_dirs_are_excluded_from_filesystem_nodes(tmp_path):
    """Corvus writes parser output into _ff_parsed/_ff_mounted inside the
    package; those are tool artifacts and must not appear as evidence."""
    from worker.parsers.filesystem import build_filesystem_nodes

    (tmp_path / "Windows" / "System32").mkdir(parents=True)
    (tmp_path / "Windows" / "System32" / "cmd.exe").write_text("x")
    (tmp_path / "_ff_parsed" / "disk_image").mkdir(parents=True)
    (tmp_path / "_ff_parsed" / "disk_image" / "plaso.jsonl").write_text("{}")
    (tmp_path / "_ff_mounted").mkdir()
    (tmp_path / "_ff_mounted" / "etc").mkdir()

    paths = {n["full_path"] for n in build_filesystem_nodes(tmp_path, "src-1")}

    assert paths == {"/Windows", "/Windows/System32", "/Windows/System32/cmd.exe"}
