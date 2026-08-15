import { IngestJob, SigmaDetection } from "../api/client";

/**
 * Formatting + status helpers shared by CaseDetailPage and the views extracted
 * out of it (OverviewView, SourcesView). Pure functions only - no React, no API
 * calls - so every consumer can import them without a cycle.
 *
 * Moved verbatim from CaseDetailPage.tsx:47-142 during the Phase 2 re-composition.
 * Behavior is byte-identical on purpose; do not "improve" these here.
 */

export function sourceCollectorLabel(collector: string): string {
  if (collector === "kape" || collector === "import") return "Imported";
  return collector;
}

export function sourcePlatformLabel(platform: string): string {
  if (platform === "macos") return "macOS";
  if (platform === "windows") return "Windows";
  if (platform === "linux") return "Linux";
  if (platform === "memory") return "Memory";
  if (platform === "disk") return "Disk image (E01/RAW)";
  return "Unknown platform";
}

export function formatDuration(seconds: number | null | undefined): string | null {
  if (seconds == null) return null;
  if (seconds < 1) return `${Math.max(0, seconds).toFixed(2)}s`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins < 60) return secs ? `${mins}m ${secs}s` : `${mins}m`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins ? `${hours}h ${remMins}m` : `${hours}h`;
}

export const ACTIVE_JOB_STATUSES = new Set(["pending", "running"]);

/** Compact counts for narrow sidebar stat cards (full value in title tooltip). */
export function formatCompactStat(n: number): string {
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    return m >= 10 ? `${Math.round(m)}M` : `${m.toFixed(1).replace(/\.0$/, "")}M`;
  }
  if (n >= 10_000) return `${Math.round(n / 1000)}K`;
  if (n >= 1_000) {
    const k = n / 1000;
    return k >= 10 ? `${Math.round(k)}K` : `${k.toFixed(1).replace(/\.0$/, "")}K`;
  }
  return n.toLocaleString();
}

export const SEVERITY_RANK: Record<string, number> = {
  critical: 5,
  high: 4,
  medium: 3,
  low: 2,
  informational: 1,
};

export function topSeverity(detections: SigmaDetection[]): string {
  return detections.reduce(
    (top, detection) =>
      (SEVERITY_RANK[detection.level] ?? 0) > (SEVERITY_RANK[top] ?? 0)
        ? detection.level
        : top,
    "informational"
  );
}

export function isActiveJob(job: IngestJob | null): boolean {
  return !!job && ACTIVE_JOB_STATUSES.has(job.status);
}

export const PARTIAL_MARKERS = [/\bIngested 0 events\b/i, /\bfailed\b/i, /\bunable to\b/i, /\bskipped\b/i];

export function jobDisplayStatus(job: IngestJob): { status: string; label: string } {
  if (job.status !== "completed") return { status: job.status, label: job.status };
  const partial =
    !!job.error_code ||
    !!job.error_stage ||
    PARTIAL_MARKERS.some((pattern) => pattern.test(job.message ?? ""));
  return partial
    ? { status: "partial", label: "completed with errors" }
    : { status: "completed", label: "completed" };
}

export function packageFileName(packagePath: string): string {
  const clean = (packagePath || "").replace(/\\/g, "/").replace(/\/+$/, "");
  if (!clean) return "n/a";
  const parts = clean.split("/");
  return parts[parts.length - 1] || "n/a";
}

export function formatIngestHistoryMessage(message: string | null): string[] {
  // Collapse worker-log whitespace, then drop trailing separators: a message
  // ending in "; " would keep the dangling ";" glued to the last section (the
  // split needs "; " exactly), and a whitespace-only message used to fall
  // through to [""] and paint a blank line in the ingest history drawer.
  const compact = (message ?? "").replace(/\s+/g, " ").replace(/[;—\s]+$/, "").trim();
  if (!compact) return ["No details available."];
  // compact is non-empty and cannot end in a separator, so the final segment
  // always survives filter(Boolean) - sections is never empty here.
  return compact
    .split(" — ")
    .flatMap((part) => part.split("; "))
    .map((part) => part.trim())
    .filter(Boolean);
}

