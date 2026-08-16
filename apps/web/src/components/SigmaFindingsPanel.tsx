import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, SigmaDetection, TimelineEvent } from "../api/client";
import SeverityBadge, { severityClass, severityRowClass } from "./SeverityBadge";
import { SEVERITY_RANK } from "../lib/caseFormat";

/**
 * Detections view (plan §6.7): a full-width triage surface, not a banner.
 *
 * Layout: toolbar (search — the pre-existing search state — plus severity and
 * engine filters and relocated pagination) over a table grouped by rule. A
 * group row expands into its individual hits; the 360px right inspector shows
 * the selected rule's definition, tags, rule id and hit list.
 *
 * Pivots are unchanged from the old panel: `onViewEvent` focuses the event in
 * Timeline, `onOpenPath` opens a YARA match in Disk. The component still owns
 * no tab state and fetches detections only when the parent does not pass them.
 *
 * Hit rows need timestamps and summaries, which the detections payload does not
 * carry (it only has `sample_event_ids`). Expanding a group lazily resolves up
 * to `HIT_LIMIT` of those ids through the existing per-event endpoint; anything
 * that fails to resolve degrades to the raw id, still pivotable.
 */

type Props = {
  caseId: string;
  sourceId: string;
  detections?: SigmaDetection[];
  /** Rule id to open on arrival (Overview -> Detections pivot). */
  focusRuleId?: string | null;
  onFocusConsumed?: () => void;
  onViewEvent?: (eventId: string) => void;
  onOpenPath?: (path: string) => void;
};

const PAGE_SIZE = 25;
/** Sample events resolved per expanded group (the API caps the id list anyway). */
const HIT_LIMIT = 10;

const SEVERITY_OPTIONS = ["critical", "high", "medium", "low", "informational"] as const;

type HitState = { loading: boolean; events: Record<string, TimelineEvent> };

/** The per-event endpoint returns one object; anything else is treated as a miss. */
function isTimelineEvent(value: unknown): value is TimelineEvent {
  return (
    !!value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    typeof (value as TimelineEvent).id === "string"
  );
}

function severityRank(level: string | null | undefined): number {
  return SEVERITY_RANK[(level ?? "").toLowerCase()] ?? 0;
}

/** Full ISO UTC (plan §14: timestamps stay full ISO UTC, never localised). */
function isoUtc(raw: string | null | undefined): string {
  if (!raw) return "—";
  const at = new Date(raw);
  return Number.isNaN(at.getTime()) ? "—" : at.toISOString();
}

function engineLabel(detection: SigmaDetection): string {
  return detection.engine ?? "sigma";
}

function yaraPath(idOrPath: string): string {
  return idOrPath.startsWith("/") ? idOrPath : `/${idOrPath}`;
}

/* ── Hit list (shared by expanded rows and the inspector) ────────────────── */

function HitList({
  detection,
  state,
  onViewEvent,
  onOpenPath,
}: {
  detection: SigmaDetection;
  state?: HitState;
  onViewEvent?: (eventId: string) => void;
  onOpenPath?: (path: string) => void;
}) {
  const ids = detection.sample_event_ids.slice(0, HIT_LIMIT);
  const isYara = engineLabel(detection) === "yara";

  if (ids.length === 0) {
    return (
      <p className="panel-desc detection-hit-empty">
        No sample {isYara ? "paths" : "events"} recorded for this rule.
      </p>
    );
  }

  return (
    <>
      <ul className="detection-hit-list">
        {ids.map((idOrPath) => {
          const event = state?.events[idOrPath];
          if (isYara) {
            return (
              <li key={idOrPath} className="detection-hit">
                <span className="detection-hit-time mono">path</span>
                <span className="detection-hit-summary mono" title={idOrPath}>
                  {idOrPath}
                </span>
                {onOpenPath && (
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => onOpenPath(yaraPath(idOrPath))}
                  >
                    Open in Disk
                  </button>
                )}
              </li>
            );
          }
          return (
            <li key={idOrPath} className="detection-hit">
              <span className="detection-hit-time mono" title={event?.timestamp_utc ?? ""}>
                {event ? isoUtc(event.timestamp_utc) : state?.loading ? "loading…" : "—"}
              </span>
              <span
                className={`detection-hit-summary${event ? "" : " mono"}`}
                title={event?.summary ?? idOrPath}
              >
                {event?.summary ?? idOrPath}
              </span>
              {onViewEvent && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => onViewEvent(idOrPath)}
                >
                  View event
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {detection.match_count > ids.length && (
        <p className="detection-hit-more mono">
          Showing {ids.length} of {detection.match_count.toLocaleString()} hits
        </p>
      )}
    </>
  );
}

/* ── Detections view ─────────────────────────────────────────────────────── */

export default function SigmaFindingsPanel({
  caseId,
  sourceId,
  detections: externalDetections,
  focusRuleId,
  onFocusConsumed,
  onViewEvent,
  onOpenPath,
}: Props) {
  const [detections, setDetections] = useState<SigmaDetection[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("all");
  const [engine, setEngine] = useState("all");
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [hits, setHits] = useState<Record<string, HitState>>({});
  /** Ids whose sample events were already requested, so expand/collapse is free. */
  const requested = useRef<Set<string>>(new Set());

  // Evidence source switch: drop everything derived from the old source.
  useEffect(() => {
    setSearch("");
    setSeverity("all");
    setEngine("all");
    setPage(0);
    setSelectedId(null);
    setExpanded(new Set());
    setHits({});
    requested.current = new Set();
  }, [caseId, sourceId]);

  useEffect(() => {
    if (externalDetections) {
      setDetections(externalDetections);
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .listSigmaDetections(caseId, sourceId)
      .then(setDetections)
      .catch(() => setDetections([]))
      .finally(() => setLoading(false));
  }, [caseId, sourceId, externalDetections]);

  const loadHits = useCallback(
    async (detection: SigmaDetection) => {
      if (engineLabel(detection) === "yara") return; // sample ids are paths
      if (requested.current.has(detection.id)) return;
      const ids = detection.sample_event_ids.slice(0, HIT_LIMIT);
      if (ids.length === 0) return;
      requested.current.add(detection.id);
      setHits((prev) => ({ ...prev, [detection.id]: { loading: true, events: {} } }));
      const settled = await Promise.allSettled(
        ids.map((id) => api.getTimelineEvent(caseId, sourceId, id))
      );
      const events: Record<string, TimelineEvent> = {};
      settled.forEach((result, index) => {
        if (result.status === "fulfilled" && isTimelineEvent(result.value)) {
          events[ids[index]] = result.value;
        }
      });
      setHits((prev) => ({ ...prev, [detection.id]: { loading: false, events } }));
    },
    [caseId, sourceId]
  );

  const toggleExpanded = useCallback(
    (detection: SigmaDetection) => {
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(detection.id)) next.delete(detection.id);
        else next.add(detection.id);
        return next;
      });
      void loadHits(detection);
    },
    [loadHits]
  );

  const selectDetection = useCallback(
    (detection: SigmaDetection) => {
      setSelectedId(detection.id);
      void loadHits(detection);
    },
    [loadHits]
  );

  // A pivot from the Overview table opens that rule straight away; the parent
  // clears the request so re-entering the view does not reopen it. Wait for the
  // list to settle first: consuming the request against an empty list would
  // clear it before the matching rule ever arrives.
  useEffect(() => {
    if (!focusRuleId || loading) return;
    const match = detections.find((d) => d.rule_id === focusRuleId);
    if (match) {
      setSelectedId(match.id);
      setExpanded((prev) => new Set(prev).add(match.id));
      void loadHits(match);
    }
    onFocusConsumed?.();
  }, [focusRuleId, detections, loading, onFocusConsumed, loadHits]);

  // Any filter change invalidates the current page offset.
  useEffect(() => {
    setPage(0);
  }, [search, severity, engine]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const severityChoices = useMemo(() => {
    const present = new Set(detections.map((d) => d.level.toLowerCase()));
    return SEVERITY_OPTIONS.filter((level) => present.has(level));
  }, [detections]);

  const engineChoices = useMemo(
    () => Array.from(new Set(detections.map(engineLabel))).sort(),
    [detections]
  );

  const criticalCount = useMemo(
    () => detections.filter((d) => d.level.toLowerCase() === "critical").length,
    [detections]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = detections.filter((d) => {
      if (severity !== "all" && d.level.toLowerCase() !== severity) return false;
      if (engine !== "all" && engineLabel(d) !== engine) return false;
      if (!q) return true;
      return (
        d.title.toLowerCase().includes(q) ||
        d.rule_id.toLowerCase().includes(q) ||
        (d.description ?? "").toLowerCase().includes(q) ||
        d.tags.some((tag) => tag.toLowerCase().includes(q)) ||
        d.level.toLowerCase().includes(q)
      );
    });
    // Worst first, then loudest: the triage order an analyst actually works in.
    return rows.sort(
      (a, b) =>
        severityRank(b.level) - severityRank(a.level) ||
        b.match_count - a.match_count ||
        a.title.localeCompare(b.title)
    );
  }, [detections, search, severity, engine]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageDetections = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);
  const selected = useMemo(
    () => detections.find((d) => d.id === selectedId) ?? null,
    [detections, selectedId]
  );
  const totalHits = useMemo(
    () => detections.reduce((sum, d) => sum + d.match_count, 0),
    [detections]
  );

  const clearFilters = () => {
    setSearch("");
    setSeverity("all");
    setEngine("all");
  };

  return (
    <section className="detections-view">
      <div className="panel detections-main">
        <div className="sources-panel-head">
          <h2>Detections</h2>
          {!loading && detections.length > 0 && (
            <span className="panel-desc mono">
              {detections.length.toLocaleString()} rule{detections.length === 1 ? "" : "s"} ·{" "}
              {totalHits.toLocaleString()} hit{totalHits === 1 ? "" : "s"}
            </span>
          )}
        </div>

        {loading ? (
          <div className="data-table-wrap detections-table-wrap">
            <table className="data-table--spec detections-table">
              <tbody>
                {[0, 1, 2, 3, 4].map((row) => (
                  <tr key={row} className="table-skeleton-row" aria-hidden="true">
                    <td>
                      <span className="skeleton-cell" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="panel-desc" role="status">
              Loading detections…
            </p>
          </div>
        ) : detections.length === 0 ? (
          <p className="detail-empty-guided">
            <strong>No detections for this source.</strong>
            Detection rules are synced on a schedule — check rule status and last sync in the{" "}
            <Link to="/admin/control-panel">Control Panel</Link> (admin).
          </p>
        ) : (
          <>
            <div className="detections-toolbar">
              <input
                type="search"
                className="detections-search"
                placeholder="Search detections…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Search detections"
              />
              <label className="detections-filter">
                <span className="sr-only">Severity</span>
                <select
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                  aria-label="Filter by severity"
                >
                  <option value="all">All severities</option>
                  {severityChoices.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </label>
              <label className="detections-filter">
                <span className="sr-only">Engine</span>
                <select
                  value={engine}
                  onChange={(e) => setEngine(e.target.value)}
                  aria-label="Filter by engine"
                >
                  <option value="all">All engines</option>
                  {engineChoices.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <span className="detections-toolbar-spacer" />
              <span className="sigma-search-count mono">
                {filtered.length.toLocaleString()} of {detections.length.toLocaleString()}
              </span>
              {totalPages > 1 && (
                <span className="table-pagination detections-pagination">
                  <button
                    type="button"
                    className="secondary"
                    disabled={safePage === 0}
                    onClick={() => setPage(safePage - 1)}
                    aria-label="Previous page"
                  >
                    ← Prev
                  </button>
                  <span className="sigma-pagination-info">
                    Page {safePage + 1} of {totalPages}
                  </span>
                  <button
                    type="button"
                    className="secondary"
                    disabled={safePage >= totalPages - 1}
                    onClick={() => setPage(safePage + 1)}
                    aria-label="Next page"
                  >
                    Next →
                  </button>
                </span>
              )}
            </div>

            {criticalCount > 0 && (
              <div className="sigma-alert-banner detections-critical-line" role="status">
                <span aria-hidden="true">▍</span>
                <span>
                  {criticalCount.toLocaleString()} critical finding
                  {criticalCount === 1 ? "" : "s"}
                </span>
                {severity !== "critical" && (
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => setSeverity("critical")}
                  >
                    Show only critical
                  </button>
                )}
              </div>
            )}

            <div className="data-table-wrap detections-table-wrap">
              <table className="data-table--spec detections-table">
                <thead>
                  <tr>
                    <th scope="col" className="col-expand">
                      <span className="sr-only">Expand hits</span>
                    </th>
                    <th scope="col" className="col-sev">
                      Sev
                    </th>
                    <th scope="col">Rule</th>
                    <th scope="col" className="col-engine">
                      Engine
                    </th>
                    <th scope="col" className="col-num">
                      Hits
                    </th>
                    <th scope="col" className="col-tags">
                      Tags
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {pageDetections.length === 0 ? (
                    <tr className="table-empty">
                      <td colSpan={6}>
                        No detections match these filters.{" "}
                        <button type="button" className="link-button" onClick={clearFilters}>
                          Clear filters
                        </button>
                      </td>
                    </tr>
                  ) : (
                    pageDetections.map((d) => {
                      const isOpen = expanded.has(d.id);
                      const tags = d.tags.join(" ");
                      return (
                        <Fragment key={d.id}>
                          <tr
                            className={`clickable ${severityRowClass(d.level)}${
                              selectedId === d.id ? " is-selected" : ""
                            }`}
                            onClick={() => selectDetection(d)}
                          >
                            <td className="col-expand">
                              <button
                                type="button"
                                className="ghost detection-expander"
                                aria-expanded={isOpen}
                                aria-label={`${isOpen ? "Collapse" : "Expand"} hits for ${d.title}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleExpanded(d);
                                }}
                              >
                                {isOpen ? "▾" : "▸"}
                              </button>
                            </td>
                            <td className="col-sev">
                              <SeverityBadge level={d.level} title={d.title} />
                            </td>
                            <td className="detection-rule-cell" title={d.title}>
                              {d.title}
                            </td>
                            <td className="col-engine">
                              <span className="detection-engine-tag">{engineLabel(d)}</span>
                            </td>
                            <td className="col-num mono">{d.match_count.toLocaleString()}</td>
                            <td className="col-tags mono" title={tags}>
                              {tags || "—"}
                            </td>
                          </tr>
                          {isOpen && (
                            <tr className="detection-hits-row">
                              <td colSpan={6}>
                                <HitList
                                  detection={d}
                                  state={hits[d.id]}
                                  onViewEvent={onViewEvent}
                                  onOpenPath={onOpenPath}
                                />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      <aside className="panel detections-inspector" aria-label="Detection details">
        <div className="sources-panel-head">
          <h2>Detection details</h2>
          {selected && (
            <button type="button" className="ghost" onClick={() => setSelectedId(null)}>
              Clear selection
            </button>
          )}
        </div>

        {!selected ? (
          <p className="detail-empty-guided">
            <strong>Select a detection.</strong>
            The inspector shows its definition, tags, rule id and the events it matched.
          </p>
        ) : (
          <>
            <div className="detection-inspector-head">
              <SeverityBadge level={selected.level} variant="full" title={selected.title} />
              <strong className={`detection-inspector-title ${severityClass(selected.level)}`}>
                {selected.title}
              </strong>
            </div>

            <p className="sigma-detection-desc">
              {selected.description ?? "No description available."}
            </p>

            <dl className="manifest-meta">
              <dt>Rule ID</dt>
              <dd className="mono">{selected.rule_id}</dd>
              <dt>Engine</dt>
              <dd>{engineLabel(selected)}</dd>
              <dt>Matches</dt>
              <dd className="mono">{selected.match_count.toLocaleString()}</dd>
              {selected.tags.length > 0 && (
                <>
                  <dt>Tags</dt>
                  <dd className="mono">{selected.tags.join(", ")}</dd>
                </>
              )}
            </dl>

            {engineLabel(selected) === "yara" && selected.rule_definition && (
              <>
                <h3 className="section-label">Rule definition</h3>
                <pre className="mono detection-rule-definition">{selected.rule_definition}</pre>
              </>
            )}

            <h3 className="section-label">
              {engineLabel(selected) === "yara" ? "Matched paths" : "Hits"}
            </h3>
            <HitList
              detection={selected}
              state={hits[selected.id]}
              onViewEvent={onViewEvent}
              onOpenPath={onOpenPath}
            />
          </>
        )}
      </aside>
    </section>
  );
}

export function SigmaEventBadges({ hits }: { hits: TimelineEvent["sigma_hits"] }) {
  if (!hits?.length) return null;
  const top = hits[0];
  return (
    <span
      className={`sigma-event-badge ${severityClass(top.level)}`}
      title={hits.map((h) => h.title).join(", ")}
    >
      {hits.length > 1 ? `${hits.length} detections` : top.level}
    </span>
  );
}
