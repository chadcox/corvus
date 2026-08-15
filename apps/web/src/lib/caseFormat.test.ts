import { describe, expect, it } from "vitest";
import type { IngestJob, SigmaDetection } from "../api/client";
import {
  ACTIVE_JOB_STATUSES,
  formatCompactStat,
  formatDuration,
  formatIngestHistoryMessage,
  isActiveJob,
  jobDisplayStatus,
  packageFileName,
  SEVERITY_RANK,
  sourceCollectorLabel,
  sourcePlatformLabel,
  topSeverity,
} from "./caseFormat";

/**
 * Gate tests for the helpers extracted out of CaseDetailPage during the Phase 2
 * re-composition. These ran only through the Playwright suite before, which
 * meant a boundary bug (0.5s durations, 999_999 counts, a whitespace-only ingest
 * message) could only surface as a wrong pixel in a screenshot.
 *
 * Deterministic, node-only, no network: this is the <2s lane.
 */

function job(overrides: Partial<IngestJob> = {}): IngestJob {
  return {
    id: "job-1",
    evidence_source_id: "src-1",
    status: "completed",
    progress: 100,
    message: null,
    started_at: null,
    finished_at: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function detection(level: string): SigmaDetection {
  return {
    id: `det-${level}`,
    evidence_source_id: "src-1",
    rule_id: `rule-${level}`,
    title: `Rule ${level}`,
    level,
    description: null,
    tags: [],
    match_count: 1,
    sample_event_ids: [],
    created_at: "2026-01-01T00:00:00Z",
  };
}

describe("sourceCollectorLabel", () => {
  it("collapses the two ingest paths that mean 'the analyst uploaded it'", () => {
    expect(sourceCollectorLabel("kape")).toBe("Imported");
    expect(sourceCollectorLabel("import")).toBe("Imported");
  });

  it("passes other collectors through verbatim", () => {
    expect(sourceCollectorLabel("velociraptor")).toBe("velociraptor");
    expect(sourceCollectorLabel("uac")).toBe("uac");
    expect(sourceCollectorLabel("")).toBe("");
  });
});

describe("sourcePlatformLabel", () => {
  it("maps every platform the ingest pipeline can emit", () => {
    expect(sourcePlatformLabel("macos")).toBe("macOS");
    expect(sourcePlatformLabel("windows")).toBe("Windows");
    expect(sourcePlatformLabel("linux")).toBe("Linux");
    expect(sourcePlatformLabel("memory")).toBe("Memory");
    expect(sourcePlatformLabel("disk")).toBe("Disk image (E01/RAW)");
  });

  it("labels anything unrecognized instead of rendering a raw enum", () => {
    expect(sourcePlatformLabel("solaris")).toBe("Unknown platform");
    expect(sourcePlatformLabel("")).toBe("Unknown platform");
  });

  it("is case-sensitive by design - the API only ever sends lowercase", () => {
    expect(sourcePlatformLabel("Windows")).toBe("Unknown platform");
  });
});

describe("formatDuration", () => {
  it("returns null for a missing duration so callers can hide the field", () => {
    expect(formatDuration(null)).toBeNull();
    expect(formatDuration(undefined)).toBeNull();
  });

  it("shows sub-second work at centisecond precision", () => {
    expect(formatDuration(0)).toBe("0.00s");
    expect(formatDuration(0.456)).toBe("0.46s");
    expect(formatDuration(0.999)).toBe("1.00s");
  });

  it("clamps a negative duration to zero rather than printing '-3.00s'", () => {
    expect(formatDuration(-3)).toBe("0.00s");
  });

  it("drops to whole seconds once the number gets wide", () => {
    expect(formatDuration(1)).toBe("1.0s");
    expect(formatDuration(9.94)).toBe("9.9s");
    expect(formatDuration(10)).toBe("10s");
    expect(formatDuration(59.4)).toBe("59s");
  });

  it("switches to minutes at 60s and hides a zero seconds remainder", () => {
    expect(formatDuration(60)).toBe("1m");
    expect(formatDuration(90)).toBe("1m 30s");
    expect(formatDuration(3599)).toBe("59m 59s");
  });

  it("switches to hours at 3600s and hides a zero minutes remainder", () => {
    expect(formatDuration(3600)).toBe("1h");
    expect(formatDuration(3660)).toBe("1h 1m");
    expect(formatDuration(7200)).toBe("2h");
    expect(formatDuration(45296)).toBe("12h 34m");
  });

  it("known quirk: rounding the seconds remainder can print 60s", () => {
    // 119.6s -> 1m + round(59.6)s. Cosmetic only, and pinned here so a future
    // change to the rounding is a deliberate decision, not an accident.
    expect(formatDuration(119.6)).toBe("1m 60s");
  });
});

describe("formatCompactStat", () => {
  it("prints small counts in full", () => {
    expect(formatCompactStat(0)).toBe("0");
    expect(formatCompactStat(7)).toBe("7");
    expect(formatCompactStat(999)).toBe("999");
  });

  it("abbreviates thousands, dropping a trailing .0", () => {
    expect(formatCompactStat(1_000)).toBe("1K");
    expect(formatCompactStat(1_500)).toBe("1.5K");
    expect(formatCompactStat(9_949)).toBe("9.9K");
    expect(formatCompactStat(10_000)).toBe("10K");
    expect(formatCompactStat(99_999)).toBe("100K");
  });

  it("abbreviates millions the same way", () => {
    expect(formatCompactStat(1_000_000)).toBe("1M");
    expect(formatCompactStat(1_250_000)).toBe("1.3M");
    expect(formatCompactStat(10_000_000)).toBe("10M");
  });

  it("known quirk: just under a million stays in K", () => {
    // 999_999 -> "1000K". Four characters, still fits the stat card, so the
    // extra branch is not worth it - but pin it so a regression is visible.
    expect(formatCompactStat(999_999)).toBe("1000K");
  });

  it("never exceeds 6 characters for any realistic event count", () => {
    for (const n of [0, 1, 999, 1_000, 12_345, 999_999, 1_000_000, 87_654_321]) {
      expect(formatCompactStat(n).length).toBeLessThanOrEqual(6);
    }
  });
});

describe("topSeverity", () => {
  it("floors at informational for a source with no detections", () => {
    expect(topSeverity([])).toBe("informational");
  });

  it("picks the highest ranked level regardless of order", () => {
    expect(topSeverity([detection("low"), detection("critical"), detection("medium")])).toBe(
      "critical"
    );
    expect(topSeverity([detection("high"), detection("low")])).toBe("high");
  });

  it("ignores levels outside the rank table instead of surfacing them", () => {
    expect(topSeverity([detection("bogus")])).toBe("informational");
    expect(topSeverity([detection("bogus"), detection("medium")])).toBe("medium");
  });

  it("ranks the five levels in the documented order", () => {
    expect(SEVERITY_RANK.critical).toBeGreaterThan(SEVERITY_RANK.high);
    expect(SEVERITY_RANK.high).toBeGreaterThan(SEVERITY_RANK.medium);
    expect(SEVERITY_RANK.medium).toBeGreaterThan(SEVERITY_RANK.low);
    expect(SEVERITY_RANK.low).toBeGreaterThan(SEVERITY_RANK.informational);
  });
});

describe("isActiveJob", () => {
  it("treats only pending and running as active", () => {
    expect(ACTIVE_JOB_STATUSES).toEqual(new Set(["pending", "running"]));
    expect(isActiveJob(job({ status: "pending" }))).toBe(true);
    expect(isActiveJob(job({ status: "running" }))).toBe(true);
  });

  it("stops the poll loop for terminal states", () => {
    expect(isActiveJob(job({ status: "completed" }))).toBe(false);
    expect(isActiveJob(job({ status: "failed" }))).toBe(false);
    expect(isActiveJob(job({ status: "cancelled" }))).toBe(false);
    expect(isActiveJob(null)).toBe(false);
  });
});

describe("jobDisplayStatus", () => {
  it("passes non-completed statuses straight through", () => {
    expect(jobDisplayStatus(job({ status: "running" }))).toEqual({
      status: "running",
      label: "running",
    });
    expect(jobDisplayStatus(job({ status: "failed" }))).toEqual({
      status: "failed",
      label: "failed",
    });
  });

  it("reports a clean completion as completed", () => {
    expect(jobDisplayStatus(job({ message: "Ingested 20 events, 4 entities" }))).toEqual({
      status: "completed",
      label: "completed",
    });
  });

  it("demotes a completion carrying an error code or stage to partial", () => {
    expect(jobDisplayStatus(job({ error_code: "PARSER_TIMEOUT" })).status).toBe("partial");
    expect(jobDisplayStatus(job({ error_stage: "chainsaw" })).status).toBe("partial");
  });

  it("demotes a completion whose message admits partial work", () => {
    const partials = [
      "Ingested 0 events",
      "Sigma skipped: no rules",
      "EvtxECmd failed on 2 files",
      "Unable to parse $MFT",
      "INGESTED 0 EVENTS",
    ];
    for (const message of partials) {
      expect(jobDisplayStatus(job({ message })).label).toBe("completed with errors");
    }
  });

  it("does not fire the partial markers on substring lookalikes", () => {
    // \b guards mean "Ingested 20 events" and "unfailed" must stay clean.
    expect(jobDisplayStatus(job({ message: "Ingested 20 events" })).status).toBe("completed");
    expect(jobDisplayStatus(job({ message: null })).status).toBe("completed");
  });
});

describe("packageFileName", () => {
  it("takes the last segment of a posix path", () => {
    expect(packageFileName("/data/evidence/kape-minimal.zip")).toBe("kape-minimal.zip");
  });

  it("handles windows separators from a Windows-hosted worker", () => {
    expect(packageFileName("C:\\evidence\\WKS-042.zip")).toBe("WKS-042.zip");
  });

  it("ignores trailing slashes on directory-style packages", () => {
    expect(packageFileName("/data/evidence/WKS-042/")).toBe("WKS-042");
    expect(packageFileName("/data/evidence/WKS-042///")).toBe("WKS-042");
  });

  it("falls back to n/a rather than rendering an empty cell", () => {
    expect(packageFileName("")).toBe("n/a");
    expect(packageFileName("/")).toBe("n/a");
  });
});

describe("formatIngestHistoryMessage", () => {
  it("explains an absent message instead of rendering nothing", () => {
    expect(formatIngestHistoryMessage(null)).toEqual(["No details available."]);
    expect(formatIngestHistoryMessage("")).toEqual(["No details available."]);
  });

  it("treats a whitespace-only message as absent", () => {
    // Regression: this used to fall through to [""] and paint a blank line in
    // the ingest history drawer.
    expect(formatIngestHistoryMessage("   \n\t ")).toEqual(["No details available."]);
  });

  it("splits on em-dash and semicolon section separators", () => {
    expect(
      formatIngestHistoryMessage("Ingested 20 events — Sigma skipped; Chainsaw disabled")
    ).toEqual(["Ingested 20 events", "Sigma skipped", "Chainsaw disabled"]);
  });

  it("collapses newlines and runs of spaces from worker logs", () => {
    expect(formatIngestHistoryMessage("Ingested   20 events\n  —  done")).toEqual([
      "Ingested 20 events",
      "done",
    ]);
  });

  it("returns a single section unchanged", () => {
    expect(formatIngestHistoryMessage("Ingested 20 events")).toEqual(["Ingested 20 events"]);
  });

  it("drops trailing separators instead of leaving a dangling ';'", () => {
    // Regression: the split needs "; " exactly, so a message ending in "; "
    // used to render as "Ingested 20 events;".
    expect(formatIngestHistoryMessage("Ingested 20 events; ")).toEqual(["Ingested 20 events"]);
    expect(formatIngestHistoryMessage("Ingested 20 events;")).toEqual(["Ingested 20 events"]);
    expect(formatIngestHistoryMessage("Ingested 20 events — ")).toEqual(["Ingested 20 events"]);
  });

  it("never returns an empty section, whatever the separators", () => {
    const messages = ["; ; ;", " — ", "a;b", "a; b; ", "  x  "];
    for (const message of messages) {
      const sections = formatIngestHistoryMessage(message);
      expect(sections.length).toBeGreaterThan(0);
      for (const section of sections) expect(section).not.toBe("");
    }
  });
});
