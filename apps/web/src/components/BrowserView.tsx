import { useEffect, useMemo, useState } from "react";
import { api, TimelineEvent } from "../api/client";
import ResizableSplit from "./ResizableSplit";

const PAGE_SIZE = 200;

export type BrowserCategory =
  | ""
  | "visits"
  | "downloads"
  | "cookies"
  | "bookmarks"
  | "sessions"
  | "credentials"
  | "storage"
  | "autofill"
  | "extensions"
  | "cache"
  | "preferences";

const CATEGORIES: { id: BrowserCategory; label: string }[] = [
  { id: "", label: "All" },
  { id: "visits", label: "Visits" },
  { id: "downloads", label: "Downloads" },
  { id: "cookies", label: "Cookies" },
  { id: "bookmarks", label: "Bookmarks" },
  { id: "sessions", label: "Sessions" },
  { id: "credentials", label: "Credentials" },
  { id: "storage", label: "Storage" },
  { id: "autofill", label: "Autofill" },
  { id: "extensions", label: "Extensions" },
  { id: "cache", label: "Cache" },
  { id: "preferences", label: "Preferences" },
];

type Props = {
  caseId: string;
  sourceId: string;
};

function eventUrl(ev: TimelineEvent): string {
  const d = ev.data;
  if (typeof d.url === "string" && d.url) return d.url;
  if (typeof d.value === "string" && d.value.startsWith("http")) return d.value;
  return "";
}

function eventTitle(ev: TimelineEvent): string {
  const d = ev.data;
  if (typeof d.title === "string" && d.title) return d.title;
  if (typeof d.name === "string" && d.name) return d.name;
  return "";
}

function categoryLabel(eventType: string): string {
  const suffix = eventType.replace(/^browser\./, "");
  return suffix.charAt(0).toUpperCase() + suffix.slice(1);
}

export default function BrowserView({ caseId, sourceId }: Props) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [category, setCategory] = useState<BrowserCategory>("");
  const [q, setQ] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [selected, setSelected] = useState<TimelineEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [sortCol, setSortCol] = useState<"time" | "type" | "url">("time");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const filterOpts = useMemo(
    () => ({
      q: q || undefined,
      start: start ? new Date(start).toISOString() : undefined,
      end: end ? new Date(end).toISOString() : undefined,
      browserOnly: true as const,
      browserCategory: category || undefined,
    }),
    [q, start, end, category]
  );

  useEffect(() => {
    setLoading(true);
    api
      .listTimeline(caseId, sourceId, { ...filterOpts, limit: PAGE_SIZE, offset: 0 })
      .then((list) => {
        setEvents(list);
        setHasMore(list.length === PAGE_SIZE);
        setSelected((prev) => {
          if (prev && list.some((e) => e.id === prev.id)) return prev;
          return list[0] ?? null;
        });
      })
      .catch(() => {
        setEvents([]);
        setHasMore(false);
        setSelected(null);
      })
      .finally(() => setLoading(false));
  }, [caseId, sourceId, filterOpts]);

  const loadMore = () => {
    setLoadingMore(true);
    api
      .listTimeline(caseId, sourceId, { ...filterOpts, limit: PAGE_SIZE, offset: events.length })
      .then((list) => {
        setEvents((prev) => [...prev, ...list]);
        setHasMore(list.length === PAGE_SIZE);
      })
      .finally(() => setLoadingMore(false));
  };

  const hasFilters = Boolean(q || start || end || category);

  const toggleSort = (col: typeof sortCol) => {
    if (col === sortCol) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  };

  const sortIndicator = (col: typeof sortCol) =>
    sortCol !== col ? " ↕" : sortDir === "asc" ? " ↑" : " ↓";

  const sortedEvents = useMemo(() => {
    const cmp = (a: TimelineEvent, b: TimelineEvent): number => {
      let av = "";
      let bv = "";
      if (sortCol === "time") {
        av = a.timestamp_utc;
        bv = b.timestamp_utc;
      } else if (sortCol === "type") {
        av = a.event_type;
        bv = b.event_type;
      } else {
        av = eventUrl(a) || a.summary;
        bv = eventUrl(b) || b.summary;
      }
      return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    };
    return [...events].sort(cmp);
  }, [events, sortCol, sortDir]);

  return (
    <div className="animate-in animate-in-delay-3">
      <ResizableSplit
        left={<div className="panel">
        <div className="panel-header">
          <h2>Browser</h2>
        </div>
        <p className="panel-desc" style={{ marginTop: 0 }}>
          Chromium history, downloads, cookies, and related artifacts parsed with{" "}
          <a href="https://github.com/RyanDFIR/hindsight" target="_blank" rel="noreferrer">
            Hindsight
          </a>
          .
        </p>

        <div className="browser-category-tabs" role="tablist" aria-label="Browser artifact type">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id || "all"}
              type="button"
              role="tab"
              aria-selected={category === cat.id}
              className={`browser-category-tab${category === cat.id ? " active" : ""}`}
              onClick={() => setCategory(cat.id)}
            >
              {cat.label}
            </button>
          ))}
        </div>

        <div className="filters-stack">
          <input
            placeholder="Search URL, title, domain…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search browser artifacts"
          />
          <div className="filters-row">
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
            {hasFilters && (
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setQ("");
                  setStart("");
                  setEnd("");
                  setCategory("");
                }}
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {loading && <p className="loading-text">Loading browser artifacts…</p>}
        {!loading && events.length === 0 && (
          <div className="detail-empty">
            {hasFilters
              ? "No browser records match filters."
              : "No Chromium browser data for this source — include Chrome/Edge User Data in the upload."}
          </div>
        )}

        {!loading && events.length > 0 && (
          <>
            <div className="browser-table-wrap">
              <table className="browser-table">
                <thead>
                  <tr>
                    <th>
                      <button type="button" className="sort-header" onClick={() => toggleSort("time")}>
                        Time (UTC){sortIndicator("time")}
                      </button>
                    </th>
                    <th>
                      <button type="button" className="sort-header" onClick={() => toggleSort("type")}>
                        Type{sortIndicator("type")}
                      </button>
                    </th>
                    <th>
                      <button type="button" className="sort-header" onClick={() => toggleSort("url")}>
                        URL / summary{sortIndicator("url")}
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedEvents.map((ev) => {
                    const url = eventUrl(ev);
                    const title = eventTitle(ev);
                    return (
                      <tr
                        key={ev.id}
                        className={selected?.id === ev.id ? "selected" : undefined}
                        onClick={() => setSelected(ev)}
                      >
                        <td className="mono browser-time">
                          {new Date(ev.timestamp_utc).toLocaleString()}
                        </td>
                        <td>
                          <span className="browser-type-pill">{categoryLabel(ev.event_type)}</span>
                        </td>
                        <td className="browser-url-cell">
                          {url ? (
                            <>
                              <div className="browser-url mono">{url}</div>
                              {title && <div className="browser-title">{title}</div>}
                            </>
                          ) : (
                            <div className="browser-summary">{ev.summary}</div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {hasMore && (
              <button
                type="button"
                className="secondary load-more-btn"
                disabled={loadingMore}
                onClick={loadMore}
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </>
        )}
      </div>}
        right={<div className="panel detail-panel">
        <h2>Details</h2>
        {!selected && <p className="detail-empty">Select a row to inspect fields.</p>}
        {selected && (
          <>
            <dl className="detail-dl">
              <dt>Time</dt>
              <dd className="mono">{new Date(selected.timestamp_utc).toISOString()}</dd>
              <dt>Type</dt>
              <dd>{selected.event_type}</dd>
              {eventUrl(selected) && (
                <>
                  <dt>URL</dt>
                  <dd className="mono break-all">{eventUrl(selected)}</dd>
                </>
              )}
              {eventTitle(selected) && (
                <>
                  <dt>Title</dt>
                  <dd>{eventTitle(selected)}</dd>
                </>
              )}
              <dt>Summary</dt>
              <dd>{selected.summary}</dd>
              {typeof selected.data.browser_profile === "string" && (
                <>
                  <dt>Profile</dt>
                  <dd className="mono break-all">{selected.data.browser_profile}</dd>
                </>
              )}
              {typeof selected.data.hindsight_data_type === "string" && (
                <>
                  <dt>Hindsight type</dt>
                  <dd className="mono">{selected.data.hindsight_data_type}</dd>
                </>
              )}
            </dl>
            <details className="raw-json-details">
              <summary>Raw JSON</summary>
              <pre className="mono">{JSON.stringify(selected.data, null, 2)}</pre>
            </details>
          </>
        )}
      </div>}
      />
    </div>
  );
}
