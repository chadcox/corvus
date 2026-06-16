"""Build human-readable Sigma ingest notes for analysts."""

from __future__ import annotations

from worker.sigma.diagnostics import summarize_sigma_inputs


def sigma_ingest_note(events: list[dict], detection_count: int) -> str | None:
    stats = summarize_sigma_inputs(events)
    if detection_count > 0:
        return (
            f"Detections: {detection_count} rule(s) matched "
            f"({stats['sigma_eligible']:,} Windows log events in timeline)"
        )

    if stats["sigma_eligible"] == 0:
        if stats["copylog"] > 0 and stats["copylog"] == stats["total"]:
            return (
                "Sigma: no matches — package has only KAPE CopyLog/SkipLog rows, not parsed "
                "Windows event logs (EvtxECmd/!EZParser). Re-collect with Event Logs or "
                "include !EZParser output, then re-ingest."
            )
        if stats["total"] == 0:
            return "Sigma: no matches — no timeline events ingested."
        return (
            "Sigma: no matches — no Windows log fields (EventID/Channel/Image) on timeline "
            "events. Include EvtxECmd CSV or raw .evtx under the collection."
        )

    return (
        f"Sigma: no rules matched {stats['sigma_eligible']:,} Windows log event(s) "
        "(rules need specific field values; sparse CSV rows often match nothing)."
    )
