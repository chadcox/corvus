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
