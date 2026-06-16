import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { api, Entity, TimelineEvent, TimelineHistogram } from "../api/client";
import { SigmaEventBadges } from "./SigmaFindingsPanel";
import TimelineChart from "./TimelineChart";
import { formatEventTypeLabel } from "../utils/eventCodes";

const PAGE_SIZE = 10000;
type RowDensity = "compact" | "analyst";
const PIVOT_FIELDS = [
  "UserName",
  "TargetUserName",
  "SubjectUserName",
  "Computer",
  "Hostname",
  "EventId",
  "EventID",
  "Channel",
  "Provider",
  "Image",
  "NewProcessName",
  "CommandLine",
  "ParentImage",
  "ParentCommandLine",
  "SourceIp",
  "IpAddress",
  "DestinationIp",
  "TargetFilename",
  "ObjectName",
  "FullPath",
  "SourceFile",
  "DestinationFile",
  "url",
  "host",
  "domain",
  "title",
] as const;

type Props = {
  caseId: string;
  sourceId: string;
  focusEvent?: TimelineEvent | null;
  eventTypes?: string[];
  sigmaOnly?: boolean;
  onSigmaOnlyChange?: (value: boolean) => void;
  mftOnly?: boolean;
  viewTitle?: string;
  viewDescription?: string;
  onEntityClick?: (entity: Entity) => void;
};

function valueText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function copyText(value: string): void {
  if (!value) return;
  navigator.clipboard?.writeText(value).catch(() => undefined);
}

function firstText(data: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = data[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" || typeof value === "boolean") return String(value);
  }
  return "";
}

function rowPreview(ev: TimelineEvent): {
  title: string;
  subtitle: string;
  pivots: string[];
} {
  const d = ev.data;
  const eventId = firstText(d, ["EventID", "EventId"]);
  const provider = firstText(d, ["Provider"]);
  const channel = firstText(d, ["Channel"]);
  const user = firstText(d, ["UserName", "TargetUserName", "SubjectUserName"]);
  const host = firstText(d, ["Computer", "Hostname", "host"]);
  const proc = firstText(d, ["Image", "NewProcessName"]);
  const path = firstText(d, ["TargetFilename", "FullPath", "ObjectName", "SourceFile"]);
  const ip = firstText(d, ["IpAddress", "SourceIp", "DestinationIp"]);

  const titleParts = [
    eventId ? `EventId:${eventId}` : "",
    provider || channel || ev.summary,
  ].filter(Boolean);

  const subtitle = [channel, provider].filter(Boolean).join(" · ") || ev.summary;
  const pivots = [
    host ? `host:${host}` : "",
    user ? `user:${user}` : "",
    proc ? `proc:${proc}` : "",
    path ? `path:${path}` : "",
    ip ? `ip:${ip}` : "",
  ].filter(Boolean);

  return {
    title: titleParts.join(" · "),
    subtitle,
    pivots: pivots.slice(0, 3),
  };
}

export default function TimelineView({
  caseId,
  sourceId,
  focusEvent,
  eventTypes = [],
  sigmaOnly: sigmaOnlyProp = false,
  onSigmaOnlyChange,
  mftOnly = false,
  viewTitle,
  viewDescription,
  onEntityClick,
}: Props) {
  const [splitPct, setSplitPct] = useState(62);
  const [eventsByIndex, setEventsByIndex] = useState<Record<number, TimelineEvent>>({});
  const [q, setQ] = useState("");
  const [eventType, setEventType] = useState("");
  const [artifactType, setArtifactType] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [selected, setSelected] = useState<TimelineEvent | null>(null);
  const [rowDensity, setRowDensity] = useState<RowDensity>("analyst");
  const [linkedEntities, setLinkedEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingPageCount, setLoadingPageCount] = useState(0);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [pagingError, setPagingError] = useState<string | null>(null);
  const [sigmaOnly, setSigmaOnly] = useState(sigmaOnlyProp);
  const [histogram, setHistogram] = useState<TimelineHistogram | null>(null);
  const [detectionHistogram, setDetectionHistogram] = useState<TimelineHistogram | null>(null);
  const parentRef = useRef<HTMLDivElement | null>(null);
  const loadedPagesRef = useRef<Set<number>>(new Set());
  const loadingPagesRef = useRef<Set<number>>(new Set());
  const queryVersionRef = useRef(0);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);
  const loadedCount = useMemo(() => Object.keys(eventsByIndex).length, [eventsByIndex]);
  const eventTypeProviderHints = useMemo(() => {
    const hints = new Map<string, { provider?: string; channel?: string; mixed: boolean }>();
    Object.values(eventsByIndex).forEach((ev) => {
      const provider = firstText(ev.data, ["Provider"]);
      const channel = firstText(ev.data, ["Channel"]);
      const current = hints.get(ev.event_type);
      if (!current) {
        hints.set(ev.event_type, { provider, channel, mixed: false });
        return;
      }
      if (current.provider !== provider || current.channel !== channel) {
        current.mixed = true;
      }
    });
    return hints;
  }, [eventsByIndex]);
  const rowCount = totalCount ?? loadedCount;
  const loadingMore = loadingPageCount > 0;

  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => (rowDensity === "compact" ? 84 : 144),
    overscan: 12,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const lastPageOffset = useMemo(() => {
    if (totalCount == null || totalCount <= 0) return null;
    return Math.floor((totalCount - 1) / PAGE_SIZE) * PAGE_SIZE;
  }, [totalCount]);

  useEffect(() => {
    setSigmaOnly(sigmaOnlyProp);
  }, [sigmaOnlyProp, sourceId]);

  const setSigmaOnlyFiltered = (value: boolean) => {
    setSigmaOnly(value);
    onSigmaOnlyChange?.(value);
  };

  const filterOpts = useMemo(
    () => ({
      q: q || undefined,
      start: start ? new Date(start).toISOString() : undefined,
      end: end ? new Date(end).toISOString() : undefined,
      eventType: eventType || undefined,
      artifactType: artifactType || undefined,
      sigmaOnly: sigmaOnly && !mftOnly ? true : undefined,
      mftOnly: mftOnly || undefined,
    }),
    [q, start, end, eventType, artifactType, sigmaOnly, mftOnly]
  );

  useEffect(() => {
    if (mftOnly) return; // MftView has its own chart
    const histogramFilters = {
      q: filterOpts.q,
      start: filterOpts.start,
      end: filterOpts.end,
      eventType: filterOpts.eventType,
      artifactType: filterOpts.artifactType,
      mftOnly: filterOpts.mftOnly,
      sigmaOnly: filterOpts.sigmaOnly,
    };
    const detectionFilters = { ...histogramFilters, sigmaOnly: true };
    Promise.all([
      api.getTimelineHistogram(caseId, sourceId, histogramFilters),
      api.getTimelineHistogram(caseId, sourceId, detectionFilters).catch(() => null),
    ])
      .then(([allEvents, detectionEvents]) => {
        setHistogram(allEvents);
        setDetectionHistogram(detectionEvents);
      })
      .catch(() => {
        setHistogram(null);
        setDetectionHistogram(null);
      });
  }, [caseId, sourceId, mftOnly, filterOpts]);

  useEffect(() => {
    if (focusEvent) {
      setSelected(focusEvent);
      setQ("");
    }
  }, [focusEvent]);

  // Fetch first page + count when filters/source changes. Additional pages are
  // requested by visible virtual row indexes below.
  useEffect(() => {
    const version = queryVersionRef.current + 1;
    queryVersionRef.current = version;
    loadedPagesRef.current = new Set();
    loadingPagesRef.current = new Set();
    setLoading(true);
    setEventsByIndex({});
    setTotalCount(null);
    setLoadingPageCount(0);
    setPagingError(null);
    parentRef.current?.scrollTo({ top: 0 });
    const listReq = api.listTimeline(caseId, sourceId, {
      ...filterOpts,
      limit: PAGE_SIZE,
      offset: 0,
    });
    const countReq = api
      .countTimeline(caseId, sourceId, filterOpts)
      .then((r) => r.count)
      .catch(() => null);
    Promise.all([listReq, countReq])
      .then(([list, count]) => {
        if (version !== queryVersionRef.current) return;
        loadedPagesRef.current.add(0);
        setEventsByIndex(
          Object.fromEntries(list.map((event, index) => [index, event]))
        );
        setTotalCount(count ?? list.length);
        setPagingError(null);
        if (focusEvent && !q && !eventType && !artifactType && !start && !end) {
          const hit = list.find((e) => e.id === focusEvent.id);
          setSelected(hit ?? focusEvent);
        }
      })
      .catch(() => {
        if (version !== queryVersionRef.current) return;
        setEventsByIndex({});
        setTotalCount(0);
        setPagingError("Failed to load timeline events.");
      })
      .finally(() => {
        if (version === queryVersionRef.current) setLoading(false);
      });
  }, [caseId, sourceId, filterOpts, focusEvent, q, eventType, artifactType, start, end]);

  const fetchPage = useCallback((offset: number) => {
    if (offset < 0) return;
    if (totalCount != null && offset >= totalCount) return;
    if (loadedPagesRef.current.has(offset) || loadingPagesRef.current.has(offset)) return;

    const version = queryVersionRef.current;
    loadingPagesRef.current.add(offset);
    setLoadingPageCount((count) => count + 1);
    setPagingError(null);
    api
      .listTimeline(caseId, sourceId, {
        ...filterOpts,
        limit: PAGE_SIZE,
        offset,
      })
      .then((list) => {
        if (version !== queryVersionRef.current) return;
        loadedPagesRef.current.add(offset);
        if (list.length === 0) {
          return;
        }
        setEventsByIndex((prev) => {
          const next = { ...prev };
          list.forEach((event, index) => {
            next[offset + index] = event;
          });
          return next;
        });
      })
      .catch(() => {
        setPagingError("Pagination failed while loading additional events.");
      })
      .finally(() => {
        if (version === queryVersionRef.current) {
          loadingPagesRef.current.delete(offset);
          setLoadingPageCount((count) => Math.max(0, count - 1));
        }
      });
  }, [caseId, sourceId, filterOpts, totalCount]);

  useEffect(() => {
    if (loading || totalCount == null || totalCount === 0) return;
    const pageOffsets = new Set(
      virtualItems
        .map((item) => Math.floor(item.index / PAGE_SIZE) * PAGE_SIZE)
        .filter((offset) => offset < totalCount)
    );
    pageOffsets.forEach(fetchPage);
  }, [fetchPage, loading, totalCount, virtualItems]);

  // Dragging the scrollbar thumb directly to the physical bottom can skip
  // intermediate virtual ranges; explicitly request the final page.
  useEffect(() => {
    const el = parentRef.current;
    if (!el || loading || totalCount == null || totalCount <= 0 || lastPageOffset == null) return;
    const onScroll = () => {
      const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
      if (maxScroll <= 0) return;
      const ratio = el.scrollTop / maxScroll;
      if (ratio >= 0.995) {
        fetchPage(lastPageOffset);
      }
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", onScroll);
    };
  }, [fetchPage, lastPageOffset, loading, totalCount]);

  // Scroll both the panel into viewport and the focused virtual row into
  // view when cross-pane navigation drives selection. scrollToIndex is a
  // no-op if the item doesn't exist yet; the next effect tick retries after
  // the list has been loaded.
  useEffect(() => {
    if (!focusEvent) return;
    const hit = Object.entries(eventsByIndex).find(([, event]) => event.id === focusEvent.id);
    const idx = hit ? Number(hit[0]) : -1;
    const frame = requestAnimationFrame(() => {
      panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      if (idx >= 0) {
        virtualizer.scrollToIndex(idx, { align: "center", behavior: "smooth" });
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [focusEvent?.id, eventsByIndex, virtualizer]);

  useEffect(() => {
    if (!selected?.entity_refs?.length) {
      setLinkedEntities([]);
      return;
    }
    api
      .listEntities(caseId, sourceId, { ids: selected.entity_refs })
      .then(setLinkedEntities)
      .catch(() => setLinkedEntities([]));
  }, [caseId, sourceId, selected]);

  const hasFilters = Boolean(q || eventType || artifactType || start || end);
  const pivotValues = selected
    ? PIVOT_FIELDS.map((field) => [field, valueText(selected.data[field])] as const)
        .filter(([, value]) => value)
        .slice(0, 10)
    : [];

  const setTimelineWindow = (hours: number | "all") => {
    if (hours === "all") {
      setStart("");
      setEnd("");
      return;
    }
    const anchorTs = histogram?.buckets.at(-1)?.ts;
    const anchor = anchorTs ? new Date(anchorTs) : new Date();
    const from = new Date(anchor.getTime() - hours * 60 * 60 * 1000);
    setStart(from.toISOString().slice(0, 16));
    setEnd(anchor.toISOString().slice(0, 16));
  };

  const updateSplitFromClientX = (clientX: number) => {
    const host = panelRef.current;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    if (rect.width <= 0) return;
    const raw = ((clientX - rect.left) / rect.width) * 100;
    const clamped = Math.max(35, Math.min(75, raw));
    setSplitPct(clamped);
  };

  const onSplitMouseDown = (e: ReactMouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    draggingRef.current = true;
    const onMove = (ev: MouseEvent) => {
      if (!draggingRef.current) return;
      updateSplitFromClientX(ev.clientX);
    };
    const onUp = () => {
      draggingRef.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return (
    <div
      ref={panelRef}
      className="timeline-resizable-grid animate-in animate-in-delay-3"
      style={{ ["--timeline-left" as string]: `${splitPct}%` }}
    >
      <div className="panel">
        <div className="panel-header">
          <h2>{viewTitle ?? (mftOnly ? "MFT" : "Timeline")}</h2>
          <div style={{ display: "flex", gap: "0.45rem", alignItems: "center" }}>
            <select
              value={rowDensity}
              onChange={(e) => setRowDensity(e.target.value as RowDensity)}
              aria-label="Timeline row density"
              style={{ minWidth: "9rem" }}
            >
              <option value="compact">Compact rows</option>
              <option value="analyst">Analyst rows</option>
            </select>
            <a
              href={api.timelineExportUrl(caseId, sourceId, filterOpts)}
              className="export-link"
              download
            >
              Export CSV
            </a>
          </div>
        </div>
        {viewDescription && (
          <p className="panel-desc" style={{ marginTop: 0 }}>{viewDescription}</p>
        )}
        <div className="filters-stack">
          <input
            placeholder={mftOnly ? "Search paths and file names…" : "Search summaries…"}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search timeline"
          />
          <div className="filters-row">
            <select
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              aria-label="Event type filter"
            >
              <option value="">All event types</option>
              {eventTypes.map((t) => {
                const hint = eventTypeProviderHints.get(t);
                return (
                  <option key={t} value={t}>
                    {formatEventTypeLabel(t, hint?.mixed ? undefined : hint?.provider, hint?.mixed ? undefined : hint?.channel)}
                  </option>
                );
              })}
            </select>
            <select
              value={artifactType}
              onChange={(e) => setArtifactType(e.target.value)}
              aria-label="Artifact type filter"
            >
              <option value="">All artifact types</option>
              <option value="evtx">EVTX</option>
              <option value="mft">MFT</option>
              <option value="browser">Browser</option>
            </select>
            <input
              type="datetime-local"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              title="Start time (UTC)"
              aria-label="Start time"
            />
            <input
              type="datetime-local"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              title="End time (UTC)"
              aria-label="End time"
            />
            {!mftOnly && (
              <label className="sigma-only-toggle">
                <input
                  type="checkbox"
                  checked={sigmaOnly}
                  onChange={(e) => setSigmaOnlyFiltered(e.target.checked)}
                />
                Detections only
              </label>
            )}
            {hasFilters && (
              <button
                type="button"
                className="secondary"
                onClick={() => { setQ(""); setEventType(""); setArtifactType(""); setStart(""); setEnd(""); }}
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {histogram && histogram.buckets.length > 0 && (
          <div className="timeline-distribution">
            <div className="timeline-zoom-controls" aria-label="Timeline zoom">
              <span className="timeline-zoom-label">Zoom</span>
              <button type="button" className="secondary" onClick={() => setTimelineWindow(1)}>1h</button>
              <button type="button" className="secondary" onClick={() => setTimelineWindow(24)}>24h</button>
              <button type="button" className="secondary" onClick={() => setTimelineWindow(24 * 7)}>7d</button>
              <button type="button" className="secondary" onClick={() => setTimelineWindow("all")}>Entire case</button>
            </div>
            <TimelineChart
              histogram={histogram}
              detectionHistogram={detectionHistogram}
              onBucketClick={(s, e) => {
                setStart(s.slice(0, 16));
                setEnd(e ? e.slice(0, 16) : "");
              }}
            />
          </div>
        )}

        {loading && <p className="loading-text">Loading events…</p>}
        {!loading && rowCount === 0 && (
          <div className="detail-empty">
            {mftOnly
              ? "No MFT records for this source — upload an $MFT export or a package that includes one."
              : sigmaOnly
                ? "No detection matches for this source — rules may not apply to your log types."
                : hasFilters
                  ? "No events match filters."
                  : "No events yet — ingest may still be running."}
          </div>
        )}
        {!loading && rowCount > 0 && (
          <div ref={parentRef} className="virtual-list-container">
            <ul
              className="item-list virtual-list"
              style={{ height: `${virtualizer.getTotalSize()}px` }}
            >
              {virtualItems.map((virtualItem) => {
                const ev = eventsByIndex[virtualItem.index];
                if (!ev) {
                  return (
                    <li
                      key={`timeline-placeholder-${virtualItem.index}`}
                      ref={virtualizer.measureElement}
                      data-index={virtualItem.index}
                      className="item-list-row timeline-placeholder-row"
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        transform: `translateY(${virtualItem.start}px)`,
                      }}
                    >
                      <div className="item-list-time mono">Row {virtualItem.index + 1}</div>
                      <div className="item-list-title">Loading timeline event…</div>
                      <div className="item-list-meta mono">server-paged timeline</div>
                    </li>
                  );
                }
                const isSelected = selected?.id === ev.id;
                return (
                  <li
                    key={ev.id}
                    ref={virtualizer.measureElement}
                    data-index={virtualItem.index}
                    className={`item-list-row${isSelected ? " selected" : ""}${ev.sigma_hits?.length ? " sigma-hit-row" : ""}`}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      transform: `translateY(${virtualItem.start}px)`,
                    }}
                    onClick={() => setSelected(ev)}
                  >
                    <div className="item-list-time mono">
                      {new Date(ev.timestamp_utc).toISOString()}
                      <SigmaEventBadges hits={ev.sigma_hits} />
                    </div>
                    {(() => {
                      const preview = rowPreview(ev);
                      return (
                        <>
                          <div className="item-list-title">{preview.title}</div>
                          {rowDensity === "analyst" && (
                            <>
                              <div className="item-list-subtitle">{preview.subtitle}</div>
                              {preview.pivots.length > 0 && (
                                <div className="item-list-pivots">
                                  {preview.pivots.map((pivot) => (
                                    <span key={`${ev.id}-${pivot}`} className="item-list-pivot mono">{pivot}</span>
                                  ))}
                                </div>
                              )}
                            </>
                          )}
                          <div className="item-list-meta mono">
                            {formatEventTypeLabel(ev.event_type, firstText(ev.data, ["Provider"]), firstText(ev.data, ["Channel"]))}
                            {ev.artifact_type ? ` · ${ev.artifact_type}` : ""}
                          </div>
                        </>
                      );
                    })()}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {!loading && rowCount > 0 && (
          <div style={{ marginTop: "0.65rem", textAlign: "center", color: "var(--muted)", fontSize: "0.78rem" }}>
            {loadingMore
              ? "Loading timeline page…"
              : `Loaded ${loadedCount} of ${rowCount} events`}
          </div>
        )}
        {pagingError && (
          <p className="panel-desc" style={{ marginTop: "0.5rem", color: "var(--danger)" }}>{pagingError}</p>
        )}
      </div>

      <div
        className="timeline-splitter"
        role="separator"
        aria-label="Resize timeline and event detail panels"
        aria-orientation="vertical"
        aria-valuemin={35}
        aria-valuemax={75}
        aria-valuenow={Math.round(splitPct)}
        tabIndex={0}
        onMouseDown={onSplitMouseDown}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setSplitPct((p) => Math.max(35, p - 2));
          if (e.key === "ArrowRight") setSplitPct((p) => Math.min(75, p + 2));
        }}
      />

      <div className="panel">
        <h2>Event detail</h2>
        {!selected && (
          <div className="detail-empty detail-empty-guided">
            <strong>No event selected</strong>
            <span>Select an event to view raw artifact data, detection context, timeline placement, and related artifacts.</span>
          </div>
        )}
        {selected && (
          <>
            <div className="detail-header">
              <div className="detail-timestamp mono">
                {selected.timestamp_utc}
                <SigmaEventBadges hits={selected.sigma_hits} />
              </div>
              {selected.sigma_hits?.length > 0 && (
                <ul className="sigma-hit-detail-list">
                  {selected.sigma_hits.map((h) => (
                    <li key={h.rule_id}>
                      <span className={`status-badge sigma-level-${h.level}`}>{h.level}</span>
                      {h.engine && (
                        <>
                          <span className="detection-engine-tag">{h.engine}</span>
                          {" · "}
                        </>
                      )}
                      {h.title}
                    </li>
                  ))}
                </ul>
              )}
              <p className="detail-summary">{selected.summary}</p>
              {selected.original_source && (
                <div className="detail-source mono">{selected.original_source}</div>
              )}
            </div>

            {linkedEntities.length > 0 && (
              <div>
                <p className="detail-section-label">Linked objects</p>
                <div className="entity-chips">
                  {linkedEntities.map((ent) => (
                    <button
                      key={ent.id}
                      type="button"
                      className="entity-chip"
                      onClick={() => onEntityClick?.(ent)}
                    >
                      <span className="mono">{ent.entity_type}</span>
                      {ent.display_name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="event-action-group">
              <p className="detail-section-label">Actions</p>
              <div className="event-action-buttons">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => copyText(selected.summary)}
                >
                  Copy summary
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setEventType(selected.event_type)}
                >
                  Filter event type
                </button>
                {selected.original_source && (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => copyText(selected.original_source ?? "")}
                  >
                    Copy source
                  </button>
                )}
              </div>
            </div>

            {pivotValues.length > 0 && (
              <div className="event-pivot-group">
                <p className="detail-section-label">Pivot values</p>
                <div className="event-pivot-list">
                  {pivotValues.map(([field, value]) => (
                    <div key={`${field}:${value}`} className="event-pivot-row">
                      <span className="mono event-pivot-field">{field}</span>
                      <span className="mono event-pivot-value" title={value}>{value}</span>
                      <button
                        type="button"
                        className="ghost event-pivot-btn"
                        onClick={() => copyText(value)}
                      >
                        Copy
                      </button>
                      <button
                        type="button"
                        className="ghost event-pivot-btn"
                        onClick={() => setQ(value)}
                      >
                        Search
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="detail-section-label">Raw artifact data</p>
            <pre className="code-block mono">{JSON.stringify(selected.data, null, 2)}</pre>
          </>
        )}
      </div>
    </div>
  );
}
