import { IngestJob } from "../api/client";

type Props = {
  phase: "uploading" | "ingesting";
  job: IngestJob | null;
  fileName?: string | null;
};

function phaseLabel(phase: Props["phase"], job: IngestJob | null): string {
  if (phase === "uploading") return "Uploading package";
  if (!job) return "Processing evidence";
  if (job.status === "pending") return "Queued for ingest";
  if (job.status === "running") return "Ingesting evidence";
  if (job.status === "failed") return "Ingest failed";
  if (job.status === "completed") return "Ingest complete";
  return "Processing evidence";
}

function splitJobMessage(message: string | null | undefined): {
  summary: string | null;
  notes: string[];
} {
  if (!message) return { summary: null, notes: [] };
  // Split at the first separator only — notes may embed it themselves, and
  // `split(sep, 2)` would silently drop everything past the second one.
  const sep = " — ";
  const cut = message.indexOf(sep);
  if (cut === -1) return { summary: message, notes: [] };
  const summary = message.slice(0, cut);
  const noteText = message.slice(cut + sep.length);
  if (!noteText) return { summary, notes: [] };
  return {
    summary,
    notes: noteText
      .split(";")
      .map((n) => n.trim())
      .filter(Boolean),
  };
}

// Worker prefix for any note meaning "an input was not read in full" — a
// completed job carrying one of these covered only part of the evidence.
const PARTIAL_PARSE_PREFIX = "Partial parse:";

function isPartialNote(note: string): boolean {
  return note.startsWith(PARTIAL_PARSE_PREFIX);
}

export default function IngestStatusPanel({ phase, job, fileName }: Props) {
  const progress =
    phase === "uploading" ? undefined : job?.progress ?? (job?.status === "pending" ? 0 : undefined);
  const indeterminate =
    phase === "uploading" ||
    (job?.status === "running" && (job.progress ?? 0) < 10);
  const diagnostics = splitJobMessage(job?.message);
  const detailMessage = diagnostics.summary ?? job?.message;

  return (
    <div className="panel ingest-status-panel" role="status" aria-live="polite">
      <div className="ingest-status-header">
        <span className="ingest-status-spinner" aria-hidden="true" />
        <div>
          <h2 style={{ margin: 0 }}>{phaseLabel(phase, job)}</h2>
          {fileName && (
            <p className="panel-desc" style={{ margin: "0.25rem 0 0" }}>
              {fileName}
            </p>
          )}
        </div>
        {job && phase === "ingesting" && (
          <span className={`status-badge ${job.status}`}>{job.status}</span>
        )}
      </div>

      <div className="progress-track ingest-status-progress">
        <div
          className={`progress-fill${indeterminate ? " indeterminate" : ""}`}
          style={
            indeterminate || progress == null
              ? undefined
              : { width: `${Math.max(progress, job?.status === "completed" ? 100 : 2)}%` }
          }
        />
      </div>

      <p className="ingest-status-detail">
        {phase === "uploading" &&
          "Sending evidence package to the server. Large uploads may take a minute."}
        {phase === "ingesting" && job?.status === "pending" &&
          "Waiting for the worker to pick up this job…"}
        {phase === "ingesting" && job?.status === "running" && (detailMessage ?? "Parsing artifacts…")}
        {phase === "ingesting" && job?.status === "failed" && (detailMessage ?? "Ingest failed.")}
        {phase === "ingesting" && job?.status === "completed" && (detailMessage ?? "Ready to investigate.")}
      </p>

      {phase === "ingesting" && diagnostics.notes.length > 0 && (
        <div
          className={`ingest-diagnostics${
            diagnostics.notes.some(isPartialNote) ? " partial" : ""
          }`}
        >
          <p className="detail-section-label">Ingest diagnostics</p>
          {diagnostics.notes.some(isPartialNote) && (
            <p className="ingest-diagnostics-partial">
              Incomplete ingest — at least one input was parsed only in part, so this
              source does not cover all collected evidence.
            </p>
          )}
          <ul>
            {diagnostics.notes.map((note) => (
              <li key={note} className={isPartialNote(note) ? "partial" : undefined}>
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}

      {phase === "ingesting" && job && job.status !== "pending" && (
        <p className="mono ingest-status-pct">{job.progress}%</p>
      )}
    </div>
  );
}
