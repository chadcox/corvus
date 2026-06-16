import { type ReactNode, useEffect, useRef, useState } from "react";
import { api, Entity, GlobalSearchResult, TimelineEvent } from "../api/client";

type Tab = "timeline" | "object" | "disk";

type Props = {
  caseId: string;
  sourceId: string;
  sourceStatus: string;
  onNavigate: (target: {
    tab: Tab;
    timelineEvent?: TimelineEvent;
    filesystemPath?: string;
    entity?: Entity;
  }) => void;
};

export default function GlobalSearch({ caseId, sourceId, sourceStatus, onNavigate }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GlobalSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const canSearch = sourceStatus === "completed" || sourceStatus === "failed";

  useEffect(() => {
    if (!canSearch) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if ((e.target as HTMLElement | null)?.isContentEditable) return;
      e.preventDefault();
      inputRef.current?.focus();
      inputRef.current?.select();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [canSearch]);

  useEffect(() => {
    if (!canSearch || query.trim().length < 2) {
      setResults(null);
      setError(null);
      return;
    }

    const t = setTimeout(() => {
      setLoading(true);
      setError(null);
      api
        .globalSearch(caseId, sourceId, query.trim())
        .then((r) => {
          setResults(r);
          setOpen(true);
        })
        .catch((e) => {
          setResults(null);
          setError(String(e));
        })
        .finally(() => setLoading(false));
    }, 300);

    return () => clearTimeout(t);
  }, [caseId, sourceId, query, canSearch]);

  if (!canSearch) {
    return (
      <div className="panel global-search">
        <h2>Investigate</h2>
        <p className="panel-desc" style={{ margin: 0 }}>
          Global search unlocks after evidence processing completes.
        </p>
      </div>
    );
  }

  return (
    <div className="panel global-search">
      <h2>Investigate</h2>
      <div className="search-bar">
        <span className="search-bar-icon" aria-hidden="true">⌕</span>
        <input
          ref={inputRef}
          type="search"
          placeholder="Search users, paths, hashes, event IDs, registry keys..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results && setOpen(true)}
          aria-label="Global search"
          aria-keyshortcuts="/"
        />
        <span className="search-kbd" title="Press / to focus">/</span>
      </div>

      {loading && <p className="loading-text" style={{ marginTop: "0.5rem" }}>Searching…</p>}
      {error && <div className="alert alert-error" style={{ marginTop: "0.5rem" }}>{error}</div>}

      {open && results && query.trim().length >= 2 && (
        <div className="global-search-results">
          <p className="panel-desc" style={{ margin: "0 0 0.5rem" }}>
            {results.total} result{results.total === 1 ? "" : "s"} for &quot;{results.query}&quot;
          </p>
          {results.total === 0 && <p className="loading-text">No matches found.</p>}

          {results.timeline.length > 0 && (
            <SearchSection title={`Timeline · ${results.timeline.length}`}>
              {results.timeline.map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  className="search-hit"
                  onClick={() => {
                    onNavigate({ tab: "timeline", timelineEvent: ev });
                    setOpen(false);
                  }}
                >
                  <span className="mono search-hit-time">
                    {new Date(ev.timestamp_utc).toISOString()}
                  </span>
                  <span>{ev.summary}</span>
                  <span className="mono search-hit-meta">{ev.event_type}</span>
                </button>
              ))}
            </SearchSection>
          )}

          {results.filesystem.length > 0 && (
            <SearchSection title={`Disk · ${results.filesystem.length}`}>
              {results.filesystem.map((node) => (
                <button
                  key={node.id}
                  type="button"
                  className="search-hit"
                  onClick={() => {
                    onNavigate({ tab: "disk", filesystemPath: node.full_path });
                    setOpen(false);
                  }}
                >
                  <span className="mono">{node.full_path}</span>
                  {!node.is_directory && node.size != null && (
                    <span className="search-hit-meta">{node.size.toLocaleString()} bytes</span>
                  )}
                </button>
              ))}
            </SearchSection>
          )}

          {results.entities.length > 0 && (
            <SearchSection title={`Objects · ${results.entities.length}`}>
              {results.entities.map((ent) => (
                <button
                  key={ent.id}
                  type="button"
                  className="search-hit"
                  onClick={() => {
                    onNavigate({ tab: "object", entity: ent });
                    setOpen(false);
                  }}
                >
                  <span className="mono search-hit-meta">{ent.entity_type}</span>
                  <span>{ent.display_name}</span>
                </button>
              ))}
            </SearchSection>
          )}
        </div>
      )}
    </div>
  );
}

function SearchSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="search-section">
      <h3>{title}</h3>
      <div className="search-section-list">{children}</div>
    </div>
  );
}
