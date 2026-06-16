import { useEffect, useMemo, useState } from "react";
import { api, SigmaDetection, TimelineEvent } from "../api/client";

type Props = {
  caseId: string;
  sourceId: string;
  detections?: SigmaDetection[];
  onViewEvent?: (eventId: string) => void;
  onOpenPath?: (path: string) => void;
};

const LEVEL_CLASS: Record<string, string> = {
  critical: "sigma-level-critical",
  high: "sigma-level-high",
  medium: "sigma-level-medium",
  low: "sigma-level-low",
  informational: "sigma-level-info",
};

const PAGE_SIZE = 5;

export default function SigmaFindingsPanel({ caseId, sourceId, detections: externalDetections, onViewEvent, onOpenPath }: Props) {
  const [detections, setDetections] = useState<SigmaDetection[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [selectedDetection, setSelectedDetection] = useState<SigmaDetection | null>(null);

  useEffect(() => {
    if (externalDetections) {
      setDetections(externalDetections);
      setLoading(false);
      return;
    }
    setLoading(true);
    setSearch("");
    setPage(0);
    api
      .listSigmaDetections(caseId, sourceId)
      .then(setDetections)
      .catch(() => setDetections([]))
      .finally(() => setLoading(false));
  }, [caseId, sourceId, externalDetections]);

  // Reset to page 0 when search changes
  useEffect(() => {
    setPage(0);
  }, [search]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedDetection(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return detections;
    return detections.filter(
      (d) =>
        d.title.toLowerCase().includes(q) ||
        (d.description ?? "").toLowerCase().includes(q) ||
        d.level.toLowerCase().includes(q)
    );
  }, [detections, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageDetections = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  if (loading) return null;
  if (detections.length === 0) return null;

  const top = detections[0];

  return (
    <div className="sigma-alert-banner" role="alert">
      <div className="sigma-alert-header">
        <span className="sigma-alert-icon" aria-hidden="true">⚠</span>
        <div>
          <h2>Detections</h2>
          <p className="panel-desc" style={{ margin: 0 }}>
            {detections.length} rule{detections.length === 1 ? "" : "s"} matched this evidence
            source.{" "}
            {top && (
              <span className="mono" style={{ opacity: 0.7 }}>
                Highest: <span className={`status-badge ${LEVEL_CLASS[top.level] ?? "sigma-level-medium"}`}>{top.level}</span> {top.title}
              </span>
            )}
          </p>
        </div>
      </div>

      <div className="sigma-search-bar">
        <input
          type="search"
          placeholder="Search detections…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search detections"
        />
        {search && (
          <span className="sigma-search-count">
            {filtered.length} match{filtered.length === 1 ? "" : "es"}
          </span>
        )}
      </div>

      {filtered.length === 0 ? (
        <p className="panel-desc" style={{ margin: "0.5rem 0" }}>No detections match "{search}".</p>
      ) : (
        <ul className="sigma-detection-list">
          {pageDetections.map((d) => (
            <li key={d.id} className="sigma-detection-item">
              <div className="sigma-detection-row1">
                <span className={`status-badge ${LEVEL_CLASS[d.level] ?? "sigma-level-medium"}`}>
                  {d.level}
                </span>
                {d.engine !== "yara" && d.sample_event_ids.length > 0 && onViewEvent ? (
                  <button
                    type="button"
                    className="ghost sigma-detection-title sigma-detection-title--link"
                    title={d.title}
                    onClick={() => onViewEvent(d.sample_event_ids[0])}
                  >
                    {d.title}
                  </button>
                ) : (
                  <strong className="sigma-detection-title" title={d.title}>{d.title}</strong>
                )}
                <span className="sigma-detection-meta">
                  {d.engine && <span className="detection-engine-tag">{d.engine}</span>}
                  {d.match_count.toLocaleString()} event{d.match_count === 1 ? "" : "s"}
                </span>
                <button
                  type="button"
                  className="ghost sigma-view-event-compact"
                  onClick={() => setSelectedDetection(d)}
                  title="View detection details"
                >
                  Details
                </button>
                {d.engine !== "yara" && d.sample_event_ids.length > 0 && onViewEvent && (
                  <button
                    type="button"
                    className="ghost sigma-view-event-compact"
                    onClick={() => onViewEvent(d.sample_event_ids[0])}
                    title="Jump to sample event"
                  >
                    →
                  </button>
                )}
              </div>
              {d.description && (
                <p className="sigma-detection-desc" title={d.description}>{d.description}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {totalPages > 1 && (
        <div className="sigma-pagination">
          <button
            type="button"
            className="secondary"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
            aria-label="Previous page"
          >
            ← Prev
          </button>
          <span className="sigma-pagination-info">
            Page {page + 1} of {totalPages}
            {search ? ` (${filtered.length} of ${detections.length})` : ` · ${detections.length} total`}
          </span>
          <button
            type="button"
            className="secondary"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
            aria-label="Next page"
          >
            Next →
          </button>
        </div>
      )}

      {selectedDetection && (
        <div className="modal-backdrop" onClick={() => setSelectedDetection(null)}>
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-label="Detection details"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2>Detection details</h2>
              <button type="button" className="ghost" onClick={() => setSelectedDetection(null)}>
                Close
              </button>
            </div>
            <dl className="manifest-meta modal-meta">
              <dt>Title</dt>
              <dd>{selectedDetection.title}</dd>
              <dt>Rule ID</dt>
              <dd className="mono">{selectedDetection.rule_id}</dd>
              <dt>Engine</dt>
              <dd>{selectedDetection.engine ?? "sigma"}</dd>
              <dt>Severity</dt>
              <dd>
                <span className={`status-badge ${LEVEL_CLASS[selectedDetection.level] ?? "sigma-level-medium"}`}>
                  {selectedDetection.level}
                </span>
              </dd>
              <dt>Definition</dt>
              <dd>{selectedDetection.description ?? "No description available."}</dd>
              {selectedDetection.engine === "yara" && selectedDetection.rule_definition && (
                <>
                  <dt>YARA rule</dt>
                  <dd>
                    <pre
                      className="mono"
                      style={{
                        margin: 0,
                        whiteSpace: "pre-wrap",
                        maxHeight: "20rem",
                        overflow: "auto",
                        padding: "0.6rem",
                        border: "1px solid var(--line)",
                        borderRadius: "0.4rem",
                        background: "rgba(0,0,0,0.2)",
                      }}
                    >
                      {selectedDetection.rule_definition}
                    </pre>
                  </dd>
                </>
              )}
              <dt>Matches</dt>
              <dd>{selectedDetection.match_count.toLocaleString()}</dd>
              {selectedDetection.tags.length > 0 && (
                <>
                  <dt>Tags</dt>
                  <dd>{selectedDetection.tags.join(", ")}</dd>
                </>
              )}
              {selectedDetection.sample_event_ids.length > 0 && (
                <>
                  <dt>{selectedDetection.engine === "yara" ? "Matched paths" : "Sample events"}</dt>
                  <dd>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                      {selectedDetection.sample_event_ids.slice(0, 10).map((idOrPath) =>
                        selectedDetection.engine === "yara" ? (
                          <button
                            key={idOrPath}
                            type="button"
                            className="secondary"
                            style={{ textAlign: "left" }}
                            onClick={() => {
                              if (!onOpenPath) return;
                              onOpenPath(idOrPath.startsWith("/") ? idOrPath : `/${idOrPath}`);
                              setSelectedDetection(null);
                            }}
                          >
                            <span className="mono">{idOrPath}</span>
                          </button>
                        ) : (
                          <button
                            key={idOrPath}
                            type="button"
                            className="secondary"
                            style={{ textAlign: "left" }}
                            onClick={() => {
                              if (!onViewEvent) return;
                              onViewEvent(idOrPath);
                              setSelectedDetection(null);
                            }}
                          >
                            <span className="mono">{idOrPath}</span>
                          </button>
                        )
                      )}
                    </div>
                  </dd>
                </>
              )}
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}

export function SigmaEventBadges({ hits }: { hits: TimelineEvent["sigma_hits"] }) {
  if (!hits?.length) return null;
  const top = hits[0];
  return (
    <span
      className={`sigma-event-badge ${LEVEL_CLASS[top.level] ?? "sigma-level-medium"}`}
      title={hits.map((h) => h.title).join(", ")}
    >
      {hits.length > 1 ? `${hits.length} detections` : top.level}
    </span>
  );
}
