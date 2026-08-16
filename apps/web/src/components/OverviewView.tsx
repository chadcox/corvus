import { useMemo } from "react";
import { EvidenceSource, SigmaDetection, SourceStats } from "../api/client";
import SeverityBadge, { severityAbbrev } from "./SeverityBadge";
import {
  formatCompactStat,
  sourceCollectorLabel,
  sourcePlatformLabel,
  topSeverity,
} from "../lib/caseFormat";

/**
 * Case Overview (plan §6.2): 30-second orientation — what evidence is here,
 * what is hot, where to start.
 *
 * Everything rendered here is already fetched by CaseDetailPage; this view owns
 * no fetching and no tab state. The counts strip lives in `CountsStrip` because
 * the shell renders it above every investigation view (Timeline, Disk, MFT,
 * Browser pivot back through it), while the rest of the overview is only shown
 * on `tab === "overview"`.
 *
 * Scope note: `stats` and `detections` are per evidence source and only the
 * selected source is loaded, so the "Top hosts" list can only show counts for
 * the active source. Other sources are listed with `—` rather than a guessed
 * number.
 */

export type StatPivot = "events" | "objects" | "paths" | "sigma" | "mft" | "browser";

export type TimelineLoadState = "loading" | "error" | "empty" | "ready";

/** Severity order used for ranking rows and colouring the distribution bar. */
const SEVERITY_ORDER = ["critical", "high", "medium", "low", "informational"] as const;

type SeverityKey = (typeof SEVERITY_ORDER)[number];

function severityKey(level: string | null | undefined): SeverityKey {
  const key = (level ?? "").toLowerCase();
  return (SEVERITY_ORDER as readonly string[]).includes(key)
    ? (key as SeverityKey)
    : "medium";
}

function severityRank(level: string | null | undefined): number {
  return SEVERITY_ORDER.indexOf(severityKey(level));
}

function formatIngestedAt(source: EvidenceSource): string {
  const raw = source.processing_finished_at ?? source.created_at;
  if (!raw) return "—";
  const at = new Date(raw);
  if (Number.isNaN(at.getTime())) return "—";
  return at.toLocaleDateString();
}

/* ── Counts strip ────────────────────────────────────────────────────────── */

type CountsStripProps = {
  stats: SourceStats;
  timelineState: TimelineLoadState;
  isActive: (target: StatPivot) => boolean;
  onPivot: (target: StatPivot) => void;
};

/**
 * The pivot strip. Keeps `.stat-card--action` (e2e locates
 * `button.stat-card--action`) and drops the Events pivot while the timeline
 * request is failing so a broken count never becomes a navigation target.
 */
export function CountsStrip({ stats, timelineState, isActive, onPivot }: CountsStripProps) {
  const items = (
    [
      ["events", stats.timeline_count, "Events", "Open timeline"],
      ["objects", stats.entity_count, "Entities", "Open entities"],
      ["paths", stats.filesystem_count, "Disk", "Open disk view"],
      [
        "sigma",
        stats.sigma_detection_count ?? 0,
        "Detections",
        "Open timeline (detections only)",
      ],
      ...(stats.mft_count > 0
        ? ([["mft", stats.mft_count, "MFT", "Open MFT view"]] satisfies readonly [
            StatPivot,
            number,
            string,
            string,
          ][])
        : []),
      ...(stats.browser_count > 0
        ? ([
            ["browser", stats.browser_count, "Browser", "Open browser forensics"],
          ] satisfies readonly [StatPivot, number, string, string][])
        : []),
    ] satisfies readonly [StatPivot, number, string, string][]
  ).filter(([target]) => timelineState !== "error" || target !== "events");

  return (
    <div className="stats-strip" role="group" aria-label="Jump to view">
      {items.map(([target, count, label, hint]) => (
        <button
          key={target}
          type="button"
          className={`stat-card stat-card--action${isActive(target) ? " active" : ""}`}
          title={`${count.toLocaleString()} ${label.toLowerCase()} — ${hint}`}
          aria-current={isActive(target) ? "true" : undefined}
          onClick={() => onPivot(target)}
        >
          <div className="stat-label">{label}</div>
          <div className="stat-value">{formatCompactStat(count)}</div>
        </button>
      ))}
    </div>
  );
}

/* ── Overview ────────────────────────────────────────────────────────────── */

type Props = {
  /** The selected (completed) source the stats and detections belong to. */
  source: EvidenceSource;
  sources: EvidenceSource[];
  selectedSource: string;
  stats: SourceStats;
  detections: SigmaDetection[];
  timelineState: TimelineLoadState;
  /** Row click: select that source and open Timeline. */
  onSelectSource: (source: EvidenceSource) => void;
  /** "Open" on a detection row: jump to the Detections view filtered to it. */
  onOpenDetection: (detection: SigmaDetection) => void;
};

export default function OverviewView({
  source,
  sources,
  selectedSource,
  stats,
  detections,
  timelineState,
  onSelectSource,
  onOpenDetection,
}: Props) {
  const criticalCount = useMemo(
    () => detections.filter((d) => severityKey(d.level) === "critical").length,
    [detections]
  );

  /** Rule counts per severity — the segmented bar and its legend. */
  const distribution = useMemo(() => {
    const counts = new Map<SeverityKey, number>();
    detections.forEach((d) => {
      const key = severityKey(d.level);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    });
    return SEVERITY_ORDER.map((level) => ({ level, count: counts.get(level) ?? 0 })).filter(
      (seg) => seg.count > 0
    );
  }, [detections]);

  const distributionLabel = useMemo(() => {
    if (!detections.length) return "No detections";
    return distribution.map((seg) => `${seg.count} ${seg.level}`).join(" · ");
  }, [detections, distribution]);

  /** Highest severity first, then noisiest rule. */
  const topDetections = useMemo(
    () =>
      [...detections]
        .sort(
          (a, b) => severityRank(a.level) - severityRank(b.level) || b.match_count - a.match_count
        )
        .slice(0, 5),
    [detections]
  );

  const topCategories = useMemo(() => {
    const counts = new Map<string, number>();
    detections.forEach((d) => {
      const tag = d.tags.find((t) => t.startsWith("attack.")) ?? d.tags[0] ?? d.level;
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    });
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([tag, count]) => ({ label: tag.replace(/^attack\./, ""), count }));
  }, [detections]);

  const topHosts = useMemo(
    () =>
      [...sources]
        .sort((a, b) => Number(b.id === selectedSource) - Number(a.id === selectedSource))
        .slice(0, 5)
        .map((s) => ({
          label: s.hostname,
          /** Only the selected source has stats loaded — see scope note above. */
          count: s.id === selectedSource && timelineState !== "error" ? stats.timeline_count : null,
        })),
    [sources, selectedSource, stats, timelineState]
  );

  return (
    <section className="overview-view" aria-label="Case overview">
      <section className="case-summary-panel" aria-label="Case summary">
        <div className="case-summary-head">
          <div>
            <p className="section-label">Case Summary</p>
            <h2>{source.hostname}</h2>
            <p>{sourcePlatformLabel(source.platform)} endpoint evidence ready for triage.</p>
          </div>
          {detections.length ? (
            <SeverityBadge
              level={topSeverity(detections)}
              variant="full"
              title={`highest of ${detections.length.toLocaleString()} detections`}
              className="summary-severity"
            />
          ) : (
            <span className="summary-severity summary-severity-none">No detections</span>
          )}
        </div>
        <div className="summary-kpis">
          <div>
            <strong>
              {timelineState === "error" ? "—" : formatCompactStat(stats.timeline_count)}
            </strong>
            <span>Timeline events</span>
          </div>
          <div>
            <strong>{detections.length.toLocaleString()}</strong>
            <span>Detections</span>
          </div>
          <div>
            <strong>{criticalCount.toLocaleString()}</strong>
            <span>Critical detections</span>
          </div>
        </div>
      </section>

      <div className="overview-grid">
        <div className="panel overview-panel">
          <h2>Detections</h2>
          {detections.length === 0 ? (
            <p className="panel-desc" style={{ margin: "0.5rem 0 0" }}>
              No detections on this source.
            </p>
          ) : (
            <>
              <div
                className="sev-bar"
                role="img"
                aria-label={`Detection severity distribution: ${distributionLabel}`}
              >
                {distribution.map((seg) => (
                  <span
                    key={seg.level}
                    className={`sev-bar-seg sev-bar-seg--${seg.level}`}
                    style={{ flexGrow: seg.count }}
                  />
                ))}
              </div>
              <p className="sev-bar-legend mono">{distributionLabel}</p>
              <div className="data-table-wrap">
                <table className="data-table overview-detections-table">
                  <thead>
                    <tr>
                      <th scope="col">Sev</th>
                      <th scope="col">Rule</th>
                      <th scope="col" className="num-col">
                        Hits
                      </th>
                      <th scope="col" />
                    </tr>
                  </thead>
                  <tbody>
                    {topDetections.map((d) => (
                      <tr key={d.id} className="clickable" onClick={() => onOpenDetection(d)}>
                        <td>
                          <SeverityBadge level={d.level} title={d.title} />
                        </td>
                        <td title={d.title}>{d.title}</td>
                        <td className="num-col mono">{d.match_count.toLocaleString()}</td>
                        <td>
                          <button
                            type="button"
                            className="link-button"
                            aria-label={`Open ${severityAbbrev(d.level)} detection ${d.title}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              onOpenDetection(d);
                            }}
                          >
                            open
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <div className="panel overview-panel">
          <h2>Evidence sources</h2>
          <div className="data-table-wrap">
            <table className="data-table overview-sources-table">
              <thead>
                <tr>
                  <th scope="col">Host</th>
                  <th scope="col">Platform</th>
                  <th scope="col">Collector</th>
                  <th scope="col">Status</th>
                  <th scope="col" className="num-col">
                    Events
                  </th>
                  <th scope="col">Ingested</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => {
                  const selected = s.id === selectedSource;
                  return (
                    <tr
                      key={s.id}
                      className={`clickable${selected ? " selected" : ""}`}
                      onClick={() => onSelectSource(s)}
                    >
                      <td>
                        <button
                          type="button"
                          className="link-button"
                          aria-label={`Open ${s.hostname} in Timeline`}
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectSource(s);
                          }}
                        >
                          {s.hostname}
                        </button>
                      </td>
                      <td>{sourcePlatformLabel(s.platform)}</td>
                      <td className="mono" title={sourceCollectorLabel(s.collector)}>
                        {sourceCollectorLabel(s.collector)}
                      </td>
                      <td>
                        <span className={`status-badge ${s.status}`}>{s.status}</span>
                      </td>
                      <td className="num-col mono">
                        {selected && timelineState !== "error"
                          ? formatCompactStat(stats.timeline_count)
                          : "—"}
                      </td>
                      <td className="mono">{formatIngestedAt(s)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="overview-grid overview-grid--lists">
        <div className="panel overview-panel">
          <h2>Top categories</h2>
          {topCategories.length === 0 ? (
            <p className="panel-desc" style={{ margin: "0.5rem 0 0" }}>
              No detection categories.
            </p>
          ) : (
            <ul className="overview-list">
              {topCategories.map((row) => (
                <li key={row.label}>
                  <span title={row.label}>{row.label}</span>
                  <strong className="mono">{row.count.toLocaleString()}</strong>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel overview-panel">
          <h2>Top hosts</h2>
          <ul className="overview-list">
            {topHosts.map((row) => (
              <li key={row.label}>
                <span title={row.label}>{row.label}</span>
                <strong className="mono">
                  {row.count === null ? "—" : formatCompactStat(row.count)}
                </strong>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
