from pathlib import Path

from worker.parsers.external_events import parse_tool_outputs


def test_parse_jsonl_tool_output(tmp_path: Path):
    out = tmp_path / "events.jsonl"
    out.write_text(
        '{"datetime":"2026-01-02T03:04:05Z","message":"user login","parser":"auth"}\n',
        encoding="utf-8",
    )
    events = parse_tool_outputs(tmp_path, "source-1", tool="plaso")
    assert len(events) == 1
    assert events[0]["event_type"] == "auth"
    assert events[0]["summary"] == "user login"
    assert events[0]["data"]["_ff_tool"] == "plaso"


def test_parse_json_array_tool_output(tmp_path: Path):
    out = tmp_path / "velociraptor.json"
    out.write_text(
        '[{"timestamp":"2026-01-02T03:04:05+00:00","path":"/etc/passwd","artifact":"file"}]',
        encoding="utf-8",
    )
    events = parse_tool_outputs(tmp_path, "source-1", tool="velociraptor")
    assert len(events) == 1
    assert events[0]["artifact_type"] == "file"
    assert events[0]["summary"] == "/etc/passwd"
