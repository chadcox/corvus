import { useEffect, useState } from "react";
import { api, Entity, TimelineEvent } from "../api/client";
import ResizableSplit from "./ResizableSplit";

type Props = {
  caseId: string;
  sourceId: string;
  focusEntity?: Entity | null;
  onTimelineClick?: (event: TimelineEvent) => void;
};

const TYPES = ["", "User", "Process", "File", "Host", "IpAddress"];

export default function ObjectView({
  caseId,
  sourceId,
  focusEntity,
  onTimelineClick,
}: Props) {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Entity | null>(null);
  const [relatedEvents, setRelatedEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (focusEntity) {
      setSelected(focusEntity);
      setTypeFilter(focusEntity.entity_type);
    }
  }, [focusEntity]);

  useEffect(() => {
    setLoading(true);
    api
      .listEntities(caseId, sourceId, {
        entityType: typeFilter || undefined,
        q: search.trim() || undefined,
      })
      .then((list) => {
        setEntities(list);
        if (focusEntity) {
          const hit = list.find((e) => e.id === focusEntity.id);
          setSelected(hit ?? focusEntity);
        }
      })
      .catch(() => setEntities([]))
      .finally(() => setLoading(false));
  }, [caseId, sourceId, typeFilter, search, focusEntity]);

  useEffect(() => {
    if (!selected) {
      setRelatedEvents([]);
      return;
    }
    api
      .listEntityTimeline(caseId, sourceId, selected.id)
      .then(setRelatedEvents)
      .catch(() => setRelatedEvents([]));
  }, [caseId, sourceId, selected]);

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
        </div>

        {loading && <p className="loading-text">Loading entities…</p>}
        {!loading && entities.length === 0 && (
          <div className="detail-empty">No entities match your filters.</div>
        )}
        {!loading && entities.length > 0 && (
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

            {relatedEvents.length > 0 && (
              <div>
                <p className="detail-section-label">Related timeline ({relatedEvents.length})</p>
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
              </div>
            )}

            {relatedEvents.length === 0 && (
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
