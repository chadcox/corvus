import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Case, EvidenceSource, SystemStatus } from "../api/client";

function formatBytes(bytes: number | null): string {
  if (bytes == null || Number.isNaN(bytes)) return "N/A";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

function formatPercent(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "N/A";
  return `${value.toFixed(1)}%`;
}

export default function CasesPage() {
  const navigate = useNavigate();
  const [cases, setCases] = useState<Case[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [caseEvidence, setCaseEvidence] = useState<Record<string, EvidenceSource[]>>({});

  const summarizePlatforms = (sources: EvidenceSource[]): string[] => {
    const preferred = ["windows", "linux", "macos", "memory"];
    const seen = new Set<string>();
    for (const src of sources) {
      const platform = (src.platform || "unknown").toLowerCase();
      if (platform !== "unknown") seen.add(platform);
    }
    if (seen.size === 0 && sources.length > 0) return ["unknown"];
    return preferred.filter((p) => seen.has(p));
  };

  const load = () => {
    setLoading(true);
    api
      .listCases()
      .then(async (listedCases) => {
        setCases(listedCases);
        const sourceRows = await Promise.all(
          listedCases.map(async (c) => {
            try {
              const sources = await api.listEvidence(c.id);
              return [c.id, sources] as const;
            } catch {
              return [c.id, [] as EvidenceSource[]] as const;
            }
          })
        );
        setCaseEvidence(Object.fromEntries(sourceRows));
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadSystemStatus = () => {
      api
        .getSystemStatus()
        .then((status) => {
          if (!cancelled) setSystemStatus(status);
        })
        .catch(() => {
          if (!cancelled) setSystemStatus(null);
        });
    };
    loadSystemStatus();
    const timer = window.setInterval(loadSystemStatus, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      const created = await api.createCase(name.trim());
      setName("");
      navigate(`/cases/${created.id}`);
    } catch (err) {
      setError(String(err));
      setCreating(false);
    }
  };

  const onDelete = async (caseId: string, caseName: string) => {
    if (!window.confirm(`Delete case "${caseName}" and all evidence? This cannot be undone.`)) {
      return;
    }
    setDeleting(caseId);
    setError(null);
    try {
      await api.deleteCase(caseId);
      load();
    } catch (err) {
      setError(String(err));
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="animate-in">
      <div className="cases-top-row animate-in animate-in-delay-1">
        <div className="cases-hero">
          <p className="section-label">Digital forensics</p>
          <h1 className="page-title">Cases</h1>
          <p className="page-subtitle">
            Ingest forensic artifacts and investigate across timeline, object, disk, and MFT views — fully offline.
          </p>
        </div>
      </div>

      <div className="panel animate-in animate-in-delay-2" style={{ marginBottom: "1.25rem" }}>
        <h2>Open new case</h2>
        <p className="panel-desc">Name your investigation, then upload evidence on the case workspace.</p>
        <form onSubmit={onCreate} className="create-case-form">
          <input
            placeholder="Case name — e.g. WKS-042 IR-2025"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Case name"
          />
          <button type="submit" disabled={creating || !name.trim()}>
            {creating ? "Creating…" : "Create case"}
          </button>
        </form>
      </div>

      {error && <div className="alert alert-error animate-in">{error}</div>}

      <div className="animate-in animate-in-delay-3">
        <p className="section-label">Active investigations</p>
        {loading && <p className="loading-text">Loading cases…</p>}
        {!loading && cases.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">◎</div>
            <p>No cases yet. Create one above to begin your investigation.</p>
          </div>
        )}
        {!loading && cases.length > 0 && (
          <ul className="cases-grid">
            {cases.map((c) => (
              <li key={c.id} className="case-card">
                <Link to={`/cases/${c.id}`} className="case-card-link">
                  {c.name}
                </Link>
                <div className="case-card-tags">
                  {caseEvidence[c.id]?.some((s) => s.status === "pending" || s.status === "running") && (
                    <span className="status-badge running">Processing</span>
                  )}
                  {summarizePlatforms(caseEvidence[c.id] ?? []).map((platform) => (
                    <span key={`${c.id}-${platform}`} className={`os-badge os-${platform}`}>
                      {platform === "macos" ? "macOS" : platform === "memory" ? "Memory" : platform}
                    </span>
                  ))}
                </div>
                <div className="case-card-meta">
                  Created {new Date(c.created_at).toLocaleString()}
                </div>
                <div className="case-card-id mono">{c.id}</div>
                <div className="case-card-footer">
                  <span className="evidence-count-pill">
                    {c.evidence_source_count} source{c.evidence_source_count === 1 ? "" : "s"}
                  </span>
                  <button
                    type="button"
                    className="ghost"
                    disabled={deleting === c.id}
                    onClick={() => onDelete(c.id, c.name)}
                  >
                    {deleting === c.id ? "…" : "Delete"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="cases-bottom-row animate-in animate-in-delay-3">
        <div className="panel system-status-panel">
          <h2>System status</h2>
          {!systemStatus && <p className="loading-text">Loading…</p>}
          {systemStatus && (
            <div className="status-grid status-grid-compact">
              <div className="status-item">
                <div className="status-label">Host</div>
                <div className="status-value mono">{systemStatus.hostname}</div>
              </div>
              <div className="status-item">
                <div className="status-label">CPU</div>
                <div className="status-value">{formatPercent(systemStatus.cpu_usage_percent)}</div>
              </div>
              <div className="status-item">
                <div className="status-label">Memory</div>
                <div className="status-value">
                  {formatBytes(systemStatus.memory_used_bytes)} / {formatBytes(systemStatus.memory_total_bytes)}
                </div>
              </div>
              <div className="status-item">
                <div className="status-label">Disk</div>
                <div className="status-value">
                  {formatBytes(systemStatus.disk_used_bytes)} / {formatBytes(systemStatus.disk_total_bytes)}
                </div>
              </div>
              <div className="status-item">
                <div className="status-label">Running</div>
                <div className="status-value">{systemStatus.jobs.running}</div>
              </div>
              <div className="status-item">
                <div className="status-label">Queued</div>
                <div className="status-value">{systemStatus.jobs.queued}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
