import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, TimelineEvent, TimelineHistogram } from "../api/client";
import ResizableSplit from "./ResizableSplit";
import TimelineChart from "./TimelineChart";

type Props = {
  caseId: string;
  sourceId: string;
  mftTotal?: number;
};

type SortCol = "path" | "b" | "m" | "a" | "c" | "size";
type SortDir = "asc" | "desc";

const MACB_FIELDS: Record<string, string> = {
  b: "Created0x10",
  m: "LastModified0x10",
  a: "LastAccess0x10",
  c: "LastRecordChange0x10",
};

const SERVER_PAGE_SIZE = 500;

type ColWidths = { path: number; b: number; m: number; a: number; c: number; size: number; del: number };
const DEFAULT_WIDTHS: ColWidths = { path: 38, b: 13, m: 13, a: 13, c: 13, size: 7, del: 3 };

function mftPath(ev: TimelineEvent): string {
  const d = ev.data;
  const parent = String(d.ParentPath ?? "")
    .replace(/^\.[\\/]/, "")
    .replace(/\\/g, "/");
  const name = String(d.FileName ?? ev.summary ?? "");
  return parent ? `${parent}/${name}` : name;
}

function mftTs(ev: TimelineEvent, field: string): Date | null {
  const val = ev.data[field];
  if (!val || typeof val !== "string") return null;
  const d = new Date(val.trim().replace(" ", "T") + (val.includes("Z") || val.includes("+") ? "" : "Z"));
  return isNaN(d.getTime()) ? null : d;
}

function mftTsStr(ev: TimelineEvent, field: string): string {
  const d = mftTs(ev, field);
  return d ? d.toISOString().slice(0, 16).replace("T", " ") : "—";
}

function sortValue(ev: TimelineEvent, col: SortCol): number | string {
  switch (col) {
    case "path": return mftPath(ev).toLowerCase();
    case "size": return parseInt(String(ev.data.FileSize ?? "0"), 10) || 0;
    default: return mftTs(ev, MACB_FIELDS[col])?.getTime() ?? 0;
  }
}

function fmtSize(ev: TimelineEvent): string {
  const n = parseInt(String(ev.data.FileSize ?? ""), 10);
  if (isNaN(n)) return "—";
  if (n === 0) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function MftView({ caseId, sourceId, mftTotal = 0 }: Props) {
  const [pageEvents, setPageEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<TimelineEvent | null>(null);
  const [q, setQ] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [sortCol, setSortCol] = useState<SortCol>("b");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [serverPage, setServerPage] = useState(0);
  const [filteredTotal, setFilteredTotal] = useState<number | null>(null);
  const [histogram, setHistogram] = useState<TimelineHistogram | null>(null);
  const [startFilter, setStartFilter] = useState("");
  const [endFilter, setEndFilter] = useState("");

  const [colWidths, setColWidths] = useState<ColWidths>(DEFAULT_WIDTHS);
  const tableRef = useRef<HTMLTableElement | null>(null);

  const startResize = useCallback((col: keyof ColWidths, e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = colWidths[col];
    const totalW = tableRef.current?.offsetWidth ?? 800;
    const onMove = (me: MouseEvent) => {
      const delta = me.clientX - startX;
      const newW = Math.max(4, startW + (delta / totalW) * 100);
      setColWidths((prev) => ({ ...prev, [col]: newW }));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [colWidths]);

  // Search runs server-side over every MFT record in the source, so debounce
  // keystrokes (same 300ms as global search) before issuing the query.
  useEffect(() => {
    const next = q.trim();
    if (next === appliedQ) return;
    const t = setTimeout(() => {
      setAppliedQ(next);
      setServerPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [q, appliedQ]);

  const startIso = startFilter ? new Date(startFilter).toISOString() : undefined;
  const endIso = endFilter ? new Date(endFilter).toISOString() : undefined;

  // Fetch when source, page, search, or time filters change. A superseded
  // request must not paint its rows: a slow response for an earlier term would
  // otherwise be shown under the newer one.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPageEvents([]);
    setSelected(null);
    api
      .listTimeline(caseId, sourceId, {
        mftOnly: true,
        q: appliedQ || undefined,
        limit: SERVER_PAGE_SIZE,
        offset: serverPage * SERVER_PAGE_SIZE,
        start: startIso,
        end: endIso,
      })
      .then((rows) => { if (!cancelled) setPageEvents(rows); })
      .catch(() => { if (!cancelled) setPageEvents([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [caseId, sourceId, serverPage, appliedQ, startIso, endIso]);

  // Count uses the same filters as the list so paging reflects every match,
  // not just the loaded page.
  useEffect(() => {
    let cancelled = false;
    setFilteredTotal(null);
    api
      .countTimeline(caseId, sourceId, {
        mftOnly: true,
        q: appliedQ || undefined,
        start: startIso,
        end: endIso,
      })
      .then((r) => { if (!cancelled) setFilteredTotal(r.count); })
      .catch(() => { if (!cancelled) setFilteredTotal(null); });
    return () => { cancelled = true; };
  }, [caseId, sourceId, appliedQ, startIso, endIso]);

  // Fetch histogram once per source
  useEffect(() => {
    setQ("");
    setAppliedQ("");
    setServerPage(0);
    api.getTimelineHistogram(caseId, sourceId, { artifactType: "mft" }).then(setHistogram).catch(() => setHistogram(null));
  }, [caseId, sourceId]);

  const toggleSort = (col: SortCol) => {
    if (col === sortCol) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  };

  const sortIndicator = (col: SortCol) =>
    sortCol !== col ? " ↕" : sortDir === "asc" ? " ↑" : " ↓";

  // Sort is client-side and therefore only orders the loaded page; searching and
  // paging are server-side across the whole source.
  const sorted = useMemo(() => {
    return [...pageEvents].sort((a, b) => {
      const av = sortValue(a, sortCol);
      const bv = sortValue(b, sortCol);
      const cmp = typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv));
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [pageEvents, sortCol, sortDir]);

  const handleBucketClick = (start: string, end: string) => {
    setStartFilter(start.slice(0, 16));
    setEndFilter(end.slice(0, 16));
    setServerPage(0);
  };

  const hasFilters = Boolean(q || startFilter || endFilter);
  const isFiltered = Boolean(appliedQ || startFilter || endFilter);
  // Fall back to the unfiltered source total only when nothing is filtered; an
  // unavailable count is shown as unknown rather than as a wrong number.
  const total = filteredTotal ?? (isFiltered ? null : mftTotal || null);
  const totalServerPages = total != null ? Math.max(1, Math.ceil(total / SERVER_PAGE_SIZE)) : null;
  const hasNextPage = totalServerPages != null
    ? serverPage < totalServerPages - 1
    : pageEvents.length === SERVER_PAGE_SIZE;

  const SortTh = ({ col, rCol, children }: { col: SortCol; rCol: keyof ColWidths; children: string }) => (
    <th style={{ position: "relative" }}>
      <button
        type="button"
        className="sort-header"
        title="Sorts the records loaded on this page, not the full result set"
        onClick={() => toggleSort(col)}
      >
        {children}{sortIndicator(col)}
      </button>
      <div className="col-resize-handle" onMouseDown={(e) => startResize(rCol, e)} />
    </th>
  );

  return (
    <div className="mft-workspace animate-in animate-in-delay-3">
      {histogram && histogram.buckets.length > 0 && (
        <TimelineChart histogram={histogram} onBucketClick={handleBucketClick} />
      )}

      <ResizableSplit
        className="mft-grid"
        left={<div className="panel mft-table-panel">
          <div className="panel-header">
            <h2>MFT Records</h2>
            <span className="mft-count mono">
              {total != null
                ? `${total.toLocaleString()} ${appliedQ ? "matching" : "total"}`
                : `${sorted.length} loaded`}
            </span>
          </div>

          <div className="filters-stack">
            <input
              placeholder="Search all file paths…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Search MFT paths"
            />
            {hasFilters && (
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setQ("");
                  setAppliedQ("");
                  setStartFilter("");
                  setEndFilter("");
                  setServerPage(0);
                }}
              >
                Clear filters
              </button>
            )}
          </div>

          {loading && <p className="loading-text">Loading MFT records…</p>}

          {!loading && pageEvents.length === 0 && (
            <div className="detail-empty">
              {isFiltered
                ? "No MFT records match the current filters."
                : "No MFT records — upload a package with $MFT or MFTECmd output."}
            </div>
          )}

          {!loading && pageEvents.length > 0 && (
            <>
              <p className="mft-count mft-scope-note">
                Search covers every MFT record in this source. Column sort orders only the{" "}
                {sorted.length.toLocaleString()} records loaded on this page.
              </p>
              <div className="mft-table-scroll">
                <table className="mft-table" ref={tableRef} style={{ tableLayout: "fixed" }}>
                  <colgroup>
                    {(Object.keys(DEFAULT_WIDTHS) as (keyof ColWidths)[]).map((c) => (
                      <col key={c} style={{ width: `${colWidths[c]}%` }} />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      <SortTh col="path" rCol="path">Path</SortTh>
                      <SortTh col="b" rCol="b">B (Born)</SortTh>
                      <SortTh col="m" rCol="m">M (Mod)</SortTh>
                      <SortTh col="a" rCol="a">A (Access)</SortTh>
                      <SortTh col="c" rCol="c">C (Change)</SortTh>
                      <SortTh col="size" rCol="size">Size</SortTh>
                      <th title="Deleted" style={{ position: "relative" }}>Del
                        <div className="col-resize-handle" onMouseDown={(e) => startResize("del", e)} />
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((ev) => {
                      const deleted = String(ev.data.InUse ?? "true").toLowerCase() !== "true";
                      return (
                        <tr
                          key={ev.id}
                          className={`mft-row${selected?.id === ev.id ? " selected" : ""}${deleted ? " mft-row-deleted" : ""}`}
                          onClick={() => setSelected(ev)}
                        >
                          <td className="mft-path-cell" title={mftPath(ev)}>
                            {String(ev.data.IsDirectory ?? "").toLowerCase() === "true" && (
                              <span className="mft-dir-icon" aria-hidden="true">▣ </span>
                            )}
                            {mftPath(ev)}
                          </td>
                          <td className="mft-ts-cell mono">{mftTsStr(ev, "Created0x10")}</td>
                          <td className="mft-ts-cell mono">{mftTsStr(ev, "LastModified0x10")}</td>
                          <td className="mft-ts-cell mono">{mftTsStr(ev, "LastAccess0x10")}</td>
                          <td className="mft-ts-cell mono">{mftTsStr(ev, "LastRecordChange0x10")}</td>
                          <td className="mft-ts-cell mono">{fmtSize(ev)}</td>
                          <td className="mft-del-cell">{deleted ? "✕" : ""}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="mft-pagination">
                <button
                  type="button"
                  className="secondary"
                  disabled={serverPage === 0}
                  onClick={() => setServerPage((p) => p - 1)}
                >
                  ← Prev
                </button>
                <span className="mft-page-info mono">
                  Page {serverPage + 1} of {totalServerPages ?? "?"}
                  {total != null && ` · ${total.toLocaleString()} ${appliedQ ? "matching records" : "records"}`}
                </span>
                <button
                  type="button"
                  className="secondary"
                  disabled={!hasNextPage}
                  onClick={() => setServerPage((p) => p + 1)}
                >
                  Next →
                </button>
              </div>
            </>
          )}
        </div>}
        right={<div className="panel mft-detail-panel">
          <h2>File details</h2>
          <div className="mft-detail-inner">
          {!selected && (
            <div className="detail-empty">Select a row to inspect timestamps and attributes.</div>
          )}
          {selected && (
            <>
              <div className="mft-detail-path mono">{mftPath(selected)}</div>

              <table className="mft-detail-macb">
                <thead>
                  <tr>
                    <th></th>
                    <th>$STANDARD_INFO</th>
                    <th>$FILE_NAME</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { label: "B — Born", si: "Created0x10", fn: "Created0x30" },
                    { label: "M — Modified", si: "LastModified0x10", fn: "LastModified0x30" },
                    { label: "A — Accessed", si: "LastAccess0x10", fn: "LastAccess0x30" },
                    { label: "C — Changed", si: "LastRecordChange0x10", fn: "LastRecordChange0x30" },
                  ].map(({ label, si, fn }) => (
                    <tr key={label}>
                      <td className="mft-macb-label">{label}</td>
                      <td className="mono mft-macb-ts">{mftTsStr(selected, si)}</td>
                      <td className="mono mft-macb-ts mft-macb-fn">{mftTsStr(selected, fn)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <dl className="mft-detail-attrs">
                <dt>Size</dt><dd className="mono">{fmtSize(selected)}</dd>
                <dt>Status</dt>
                <dd>{String(selected.data.InUse ?? "").toLowerCase() === "true" ? "In use" : "Deleted / unlinked"}</dd>
                <dt>Type</dt>
                <dd>{String(selected.data.IsDirectory ?? "").toLowerCase() === "true" ? "Directory" : "File"}</dd>
                {selected.data.IsAds === "True" && <><dt>ADS</dt><dd>Alternate data stream</dd></>}
                {Boolean(selected.data.Extension) && <><dt>Extension</dt><dd className="mono">{String(selected.data.Extension)}</dd></>}
                {Boolean(selected.data.SiFlags) && <><dt>Attributes</dt><dd className="mono">{String(selected.data.SiFlags)}</dd></>}
                {Boolean(selected.data.EntryNumber) && <><dt>MFT entry</dt><dd className="mono">{String(selected.data.EntryNumber)}</dd></>}
                {Boolean(selected.data.ReparseTarget) && <><dt>Reparse target</dt><dd className="mono">{String(selected.data.ReparseTarget)}</dd></>}
                {selected.data["SI<FN"] === "True" && (
                  <><dt className="mft-flag-warn">⚠ SI &lt; FN</dt><dd>Timestamps may be timestomped</dd></>
                )}
              </dl>
            </>
          )}
          </div>{/* mft-detail-inner */}
        </div>}
      />
    </div>
  );
}
