import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Entity, TimelineEvent } from "../api/client";
import ResizableSplit from "./ResizableSplit";

type Props = {
  caseId: string;
  sourceId: string;
  focusEntity?: Entity | null;
  onTimelineClick?: (event: TimelineEvent) => void;
};

const TYPES = ["", "User", "Process", "File", "Host", "IpAddress"];
/** One server page. Load-more appends a page at a time; nothing auto-loads. */
const ENTITY_PAGE_SIZE = 200;
const EVENT_PAGE_SIZE = 100;

function loadedOfTotal(loaded: number, total: number | null, noun: string): string {
  if (total == null) return `${loaded.toLocaleString()} ${noun} loaded (total unavailable)`;
  return `${loaded.toLocaleString()} of ${total.toLocaleString()} ${noun} loaded`;
}

type LoadError = {
  message: string;
  retry: "first-page" | "next-page";
};

export default function ObjectView({
  caseId,
  sourceId,
  focusEntity,
  onTimelineClick,
}: Props) {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [entityTotal, setEntityTotal] = useState<number | null>(null);
  const [entityPageFull, setEntityPageFull] = useState(false);
  const [entityError, setEntityError] = useState<LoadError | null>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Entity | null>(null);
  const [relatedEvents, setRelatedEvents] = useState<TimelineEvent[]>([]);
  const [relatedTotal, setRelatedTotal] = useState<number | null>(null);
  const [relatedPageFull, setRelatedPageFull] = useState(false);
  const [relatedError, setRelatedError] = useState<LoadError | null>(null);
  const [loading, setLoading] = useState(true);
  const [relatedLoading, setRelatedLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadingMoreEvents, setLoadingMoreEvents] = useState(false);
  const [entityReload, setEntityReload] = useState(0);
  const [relatedReload, setRelatedReload] = useState(0);

  // Every response is tagged with the request generation that asked for it; a
  // slow reply from a superseded filter must never overwrite fresher rows.
  const entityRequest = useRef(0);
  const relatedRequest = useRef(0);
  const displayedEntityQuery = useRef<string | null>(null);
  const displayedRelatedEntity = useRef<string | null>(null);

  const filterOpts = useMemo(
    () => ({ entityType: typeFilter || undefined, q: search.trim() || undefined }),
    [typeFilter, search]
  );
  const hasFilters = Boolean(typeFilter || search.trim());
  const entityQueryKey = `${caseId}:${sourceId}:${typeFilter}:${search.trim()}`;

  useEffect(() => {
    if (focusEntity) {
      setSelected(focusEntity);
      setTypeFilter(focusEntity.entity_type);
    }
  }, [focusEntity]);

  useEffect(() => {
    const generation = ++entityRequest.current;
    const queryChanged = displayedEntityQuery.current !== entityQueryKey;
    displayedEntityQuery.current = entityQueryKey;
    if (queryChanged) {
      // Rows from the preceding filter/source are not partial results for the
      // new query. Clear them rather than labelling them with the new total.
      setEntities([]);
      setEntityTotal(null);
      setEntityPageFull(false);
    }
    setLoading(true);
    setLoadingMore(false);
    setEntityError(null);
    Promise.allSettled([
      api.listEntities(caseId, sourceId, { ...filterOpts, limit: ENTITY_PAGE_SIZE, offset: 0 }),
      api.countEntities(caseId, sourceId, filterOpts),
    ])
      .then(([listed, counted]) => {
        if (generation !== entityRequest.current) return;
        if (listed.status === "fulfilled") {
          setEntities(listed.value);
          setEntityPageFull(listed.value.length === ENTITY_PAGE_SIZE);
          setEntityError(null);
          if (focusEntity) {
            const hit = listed.value.find((e) => e.id === focusEntity.id);
            setSelected(hit ?? focusEntity);
          }
        } else {
          // Keep whatever is already on screen rather than blanking the panel.
          setEntityTotal(null);
          setEntityPageFull(false);
          setEntityError({
            message: !queryChanged && entities.length > 0
              ? "Could not load entities. Showing the last results loaded."
              : "Could not load entities. No results for this query were loaded.",
            retry: "first-page",
          });
        }
        if (listed.status === "fulfilled") {
          setEntityTotal(counted.status === "fulfilled" ? counted.value.count : null);
        }
      })
      .finally(() => {
        if (generation === entityRequest.current) setLoading(false);
      });
  }, [caseId, sourceId, filterOpts, focusEntity, entityReload, entityQueryKey]);

  const loadMoreEntities = useCallback(() => {
    const generation = entityRequest.current;
    const offset = entities.length;
    setLoadingMore(true);
    setEntityError(null);
    api
      .listEntities(caseId, sourceId, { ...filterOpts, limit: ENTITY_PAGE_SIZE, offset })
      .then((page) => {
        if (generation !== entityRequest.current) return;
        setEntities((prev) => [...prev, ...page]);
        setEntityPageFull(page.length === ENTITY_PAGE_SIZE);
        setEntityError(null);
      })
      .catch(() => {
        if (generation !== entityRequest.current) return;
        setEntityError({
          message: "Could not load more entities. The loaded rows are unchanged.",
          retry: "next-page",
        });
      })
      .finally(() => {
        if (generation === entityRequest.current) setLoadingMore(false);
      });
  }, [caseId, sourceId, filterOpts, entities.length]);

  useEffect(() => {
    const generation = ++relatedRequest.current;
    if (!selected) {
      displayedRelatedEntity.current = null;
      setRelatedEvents([]);
      setRelatedTotal(null);
      setRelatedPageFull(false);
      setRelatedError(null);
      setRelatedLoading(false);
      return;
    }
    const relatedQueryKey = `${caseId}:${sourceId}:${selected.id}`;
    const selectionChanged = displayedRelatedEntity.current !== relatedQueryKey;
    displayedRelatedEntity.current = relatedQueryKey;
    if (selectionChanged) {
      // Related rows from another entity must never appear under this entity's
      // heading, even briefly or after a failed first page.
      setRelatedEvents([]);
      setRelatedTotal(null);
      setRelatedPageFull(false);
    }
    setRelatedLoading(true);
    setLoadingMoreEvents(false);
    setRelatedError(null);
    Promise.allSettled([
      api.listEntityTimeline(caseId, sourceId, selected.id, { limit: EVENT_PAGE_SIZE, offset: 0 }),
      api.countEntityTimeline(caseId, sourceId, selected.id),
    ]).then(([listed, counted]) => {
      if (generation !== relatedRequest.current) return;
      if (listed.status === "fulfilled") {
        setRelatedEvents(listed.value);
        setRelatedPageFull(listed.value.length === EVENT_PAGE_SIZE);
        setRelatedError(null);
      } else {
        setRelatedTotal(null);
        setRelatedPageFull(false);
        setRelatedError({
          message: !selectionChanged && relatedEvents.length > 0
            ? "Could not load related events. Showing the last results loaded."
            : "Could not load related events. No events for this entity were loaded.",
          retry: "first-page",
        });
      }
      if (listed.status === "fulfilled") {
        setRelatedTotal(counted.status === "fulfilled" ? counted.value.count : null);
      }
    }).finally(() => {
      if (generation === relatedRequest.current) setRelatedLoading(false);
    });
  }, [caseId, sourceId, selected, relatedReload]);

  const loadMoreEvents = useCallback(() => {
    if (!selected) return;
    const generation = relatedRequest.current;
    const offset = relatedEvents.length;
    setLoadingMoreEvents(true);
    setRelatedError(null);
    api
      .listEntityTimeline(caseId, sourceId, selected.id, { limit: EVENT_PAGE_SIZE, offset })
      .then((page) => {
        if (generation !== relatedRequest.current) return;
        setRelatedEvents((prev) => [...prev, ...page]);
        setRelatedPageFull(page.length === EVENT_PAGE_SIZE);
        setRelatedError(null);
      })
      .catch(() => {
        if (generation !== relatedRequest.current) return;
        setRelatedError({
          message: "Could not load more related events. The loaded rows are unchanged.",
          retry: "next-page",
        });
      })
      .finally(() => {
        if (generation === relatedRequest.current) setLoadingMoreEvents(false);
      });
  }, [caseId, sourceId, selected, relatedEvents.length]);

  // With no total we can only infer more rows from a full last page.
  const hasMoreEntities =
    entityTotal != null ? entities.length < entityTotal : entityPageFull;
  const hasMoreEvents =
    relatedTotal != null ? relatedEvents.length < relatedTotal : relatedPageFull;

  return (
    <div className="animate-in animate-in-delay-3">
      <ResizableSplit
        left={<div className="panel">
        <h2>Entities</h2>
        <p className="panel-desc">Users, processes, files, hosts, and IPs from ingested artifacts.</p>
        <div className="filters-stack">
          <input
            placeholder="Search by name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search entities"
          />
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            aria-label="Entity type filter"
          >
            {TYPES.map((t) => (
              <option key={t || "all"} value={t}>{t || "All types"}</option>
            ))}
          </select>
          {hasFilters && (
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setSearch("");
                setTypeFilter("");
              }}
            >
              Reset filters
            </button>
          )}
        </div>

        {entityError && (
          <div className="alert alert-error" style={{ marginTop: "0.5rem" }}>
            {entityError.message}{" "}
            <button
              type="button"
              className="secondary"
              onClick={entityError.retry === "next-page"
                ? loadMoreEntities
                : () => setEntityReload((n) => n + 1)}
            >
              Retry
            </button>
          </div>
        )}

        {loading && <p className="loading-text">Loading entities…</p>}
        {!loading && entities.length === 0 && !entityError && (
          <div className="detail-empty">No entities match your filters.</div>
        )}
        {entities.length > 0 && (
          <>
            <p className="mft-count entity-load-state">
              {loadedOfTotal(entities.length, entityTotal, "entities")}
              {hasFilters && entityTotal != null && " (filtered)"}
            </p>
            <ul className="item-list">
              {entities.map((ent) => (
                <li
                  key={ent.id}
                  className={`item-list-row${selected?.id === ent.id ? " selected" : ""}`}
                  onClick={() => setSelected(ent)}
                >
                  <div className="item-list-meta mono">{ent.entity_type}</div>
                  <div className="item-list-title">{ent.display_name}</div>
                </li>
              ))}
            </ul>
            {hasMoreEntities && (
              <button
                type="button"
                className="secondary load-more-btn"
                disabled={loadingMore}
                onClick={loadMoreEntities}
              >
                {loadingMore ? "Loading…" : `Load ${ENTITY_PAGE_SIZE} more entities`}
              </button>
            )}
          </>
        )}
      </div>}
        right={<div className="panel">
        <h2>Entity detail</h2>
        {!selected && <div className="detail-empty">Select an entity to view related events.</div>}
        {selected && (
          <>
            <div className="detail-header">
              <p className="detail-summary">
                <span className="entity-type-badge">{selected.entity_type}</span>
                {selected.display_name}
              </p>
            </div>

            {relatedError && (
              <div className="alert alert-error" style={{ marginBottom: "0.5rem" }}>
                {relatedError.message}{" "}
                <button
                  type="button"
                  className="secondary"
                  onClick={relatedError.retry === "next-page"
                    ? loadMoreEvents
                    : () => setRelatedReload((n) => n + 1)}
                >
                  Retry
                </button>
              </div>
            )}

            {relatedEvents.length > 0 && (
              <div>
                <p className="detail-section-label related-load-state">
                  Related timeline — {loadedOfTotal(relatedEvents.length, relatedTotal, "events")}
                </p>
                <ul className="item-list" style={{ maxHeight: "220px" }}>
                  {relatedEvents.map((ev) => (
                    <li
                      key={ev.id}
                      className="item-list-row"
                      onClick={() => onTimelineClick?.(ev)}
                      style={{ cursor: onTimelineClick ? "pointer" : "default" }}
                    >
                      <div className="item-list-time mono">
                        {new Date(ev.timestamp_utc).toISOString()}
                      </div>
                      <div className="item-list-title">{ev.summary}</div>
                    </li>
                  ))}
                </ul>
                {hasMoreEvents && (
                  <button
                    type="button"
                    className="secondary load-more-btn"
                    disabled={loadingMoreEvents}
                    onClick={loadMoreEvents}
                  >
                    {loadingMoreEvents ? "Loading…" : `Load ${EVENT_PAGE_SIZE} more events`}
                  </button>
                )}
              </div>
            )}

            {relatedLoading && relatedEvents.length === 0 && (
              <p className="loading-text">Loading related events…</p>
            )}

            {!relatedLoading && relatedEvents.length === 0 && !relatedError && (
              <p className="panel-desc">No linked timeline events. Re-ingest to populate entity links.</p>
            )}

            <p className="detail-section-label">Attributes</p>
            <pre className="code-block mono">{JSON.stringify(selected.attributes, null, 2)}</pre>
          </>
        )}
      </div>}
      />
    </div>
  );
}
