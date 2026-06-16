import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AdminJob, AdminOverview, api, AuthUser, Case, DetectionRulesStatus, EvidenceSource, ProjectContainer, SystemStatus, YaraRulesStatus } from "../api/client";
import AdminUsersPage from "./AdminUsersPage";

type Props = {
  me: AuthUser;
};

export default function ControlPanelPage({ me }: Props) {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [adminOverview, setAdminOverview] = useState<AdminOverview | null>(null);
  const [rulesStatus, setRulesStatus] = useState<DetectionRulesStatus | null>(null);
  const [yaraStatus, setYaraStatus] = useState<YaraRulesStatus | null>(null);
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [jobStatusFilter, setJobStatusFilter] = useState("failed");
  const [jobErrorCodeFilter, setJobErrorCodeFilter] = useState("");
  const [jobErrorStageFilter, setJobErrorStageFilter] = useState("");
  const [containers, setContainers] = useState<ProjectContainer[]>([]);
  const [containersError, setContainersError] = useState<string | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [bulkDeleteCaseIds, setBulkDeleteCaseIds] = useState<string[]>([]);
  const [sourcesByCase, setSourcesByCase] = useState<Record<string, EvidenceSource[]>>({});
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [opsError, setOpsError] = useState<string | null>(null);
  const [opsMessage, setOpsMessage] = useState<string | null>(null);
  const [runningOp, setRunningOp] = useState<string | null>(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logsTitle, setLogsTitle] = useState("");
  const [logsText, setLogsText] = useState("");

  if (me.role !== "administrator") {
    return <div className="alert alert-error">Forbidden (403): administrator role required.</div>;
  }

  const selectedSources = useMemo(
    () => (selectedCaseId ? sourcesByCase[selectedCaseId] ?? [] : []),
    [selectedCaseId, sourcesByCase]
  );
  const allCasesSelected = cases.length > 0 && bulkDeleteCaseIds.length === cases.length;

  const refreshOverview = () => {
    api.getSystemStatus().then(setSystemStatus).catch(() => setSystemStatus(null));
    api.getAdminOverview().then(setAdminOverview).catch(() => setAdminOverview(null));
    api.getDetectionRulesStatus().then(setRulesStatus).catch(() => setRulesStatus(null));
    api.getYaraRulesStatus().then(setYaraStatus).catch(() => setYaraStatus(null));
    api
      .listContainers()
      .then((rows) => {
        setContainers(rows);
        setContainersError(null);
      })
      .catch((e) => {
        setContainers([]);
        setContainersError(String(e));
      });
  };
  const refreshJobs = () => {
    api
      .listAdminJobs({
        status: jobStatusFilter || undefined,
        errorCode: jobErrorCodeFilter.trim() || undefined,
        errorStage: jobErrorStageFilter.trim() || undefined,
        limit: 25,
      })
      .then(setJobs)
      .catch(() => setJobs([]));
  };

  const refreshCases = async () => {
    const rows = await api.listCases();
    setCases(rows);
    setBulkDeleteCaseIds((prev) => prev.filter((id) => rows.some((c) => c.id === id)));
  };

  useEffect(() => {
    refreshOverview();
    refreshJobs();
    refreshCases().catch((e) => setOpsError(String(e)));
    const t = window.setInterval(() => {
      refreshOverview();
      refreshJobs();
    }, 15000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    refreshJobs();
  }, [jobStatusFilter, jobErrorCodeFilter, jobErrorStageFilter]);

  useEffect(() => {
    if (!selectedCaseId) {
      setSelectedSourceId("");
      return;
    }
    api
      .listEvidence(selectedCaseId)
      .then((rows) => {
        setSourcesByCase((prev) => ({ ...prev, [selectedCaseId]: rows }));
        if (!rows.find((s) => s.id === selectedSourceId)) {
          setSelectedSourceId("");
        }
      })
      .catch((e) => setOpsError(String(e)));
  }, [selectedCaseId]);

  const doOp = async (opId: string, fn: () => Promise<unknown>) => {
    setRunningOp(opId);
    setOpsError(null);
    setOpsMessage(null);
    try {
      const result = await fn();
      const msg = typeof result === "object" && result !== null ? JSON.stringify(result) : String(result);
      setOpsMessage(msg);
      refreshOverview();
    } catch (e) {
      setOpsError(String(e));
    } finally {
      setRunningOp(null);
    }
  };

  const toggleBulkCase = (caseId: string) => {
    setBulkDeleteCaseIds((prev) =>
      prev.includes(caseId) ? prev.filter((id) => id !== caseId) : [...prev, caseId]
    );
  };

  const totalDisk = adminOverview?.disk.total_bytes ?? null;
  const usedDisk = adminOverview?.disk.used_bytes ?? null;
  const freeDisk = adminOverview?.disk.free_bytes ?? null;
  const diskPct = totalDisk && freeDisk != null && totalDisk > 0 ? ((totalDisk - freeDisk) / totalDisk) * 100 : null;

  return (
    <div className="animate-in">
      <div className="cases-top-row animate-in animate-in-delay-1">
        <div className="cases-hero">
          <p className="section-label">Administration</p>
          <h1 className="page-title">Control Panel</h1>
          <p className="page-subtitle">
            Centralized admin workspace for user access, operations, and platform controls.
          </p>
          <div style={{ marginTop: "0.5rem" }}>
            <Link to="/" className="mono">Return to cases</Link>
          </div>
        </div>
      </div>

      <div className="panel animate-in animate-in-delay-2" style={{ marginBottom: "1rem" }}>
        <h2>System overview</h2>
        {!systemStatus && <p className="panel-desc">Loading system metrics…</p>}
        {systemStatus && (
          <div className="status-grid status-grid-compact">
            <div className="status-item"><div className="status-label">Host</div><div className="status-value mono">{systemStatus.hostname}</div></div>
            <div className="status-item"><div className="status-label">CPU %</div><div className="status-value">{systemStatus.cpu_usage_percent ?? "N/A"}</div></div>
            <div className="status-item"><div className="status-label">Running jobs</div><div className="status-value">{systemStatus.jobs.running}</div></div>
            <div className="status-item"><div className="status-label">Queued jobs</div><div className="status-value">{systemStatus.jobs.queued}</div></div>
          </div>
        )}
        {adminOverview && (
          <div className="status-grid status-grid-compact" style={{ marginTop: "0.75rem" }}>
            <div className="status-item"><div className="status-label">Cases</div><div className="status-value">{adminOverview.table_counts.cases}</div></div>
            <div className="status-item"><div className="status-label">Evidence sources</div><div className="status-value">{adminOverview.table_counts.evidence_sources}</div></div>
            <div className="status-item"><div className="status-label">Case data used</div><div className="status-value">{usedDisk != null ? (usedDisk / (1024 ** 3)).toFixed(1) : "N/A"} GB</div></div>
            <div className="status-item"><div className="status-label">Disk total</div><div className="status-value">{totalDisk != null ? (totalDisk / (1024 ** 3)).toFixed(1) : "N/A"} GB</div></div>
            <div className="status-item"><div className="status-label">Disk used %</div><div className="status-value">{diskPct != null ? `${diskPct.toFixed(1)}%` : "N/A"}</div></div>
          </div>
        )}
        {!adminOverview && (
          <p className="panel-desc" style={{ marginTop: "0.75rem" }}>
            Admin overview unavailable. Ensure <code>ENABLE_ADMIN_API=true</code>.
          </p>
        )}
      </div>

      <div className="panel animate-in animate-in-delay-2" style={{ marginBottom: "1rem" }}>
        <h2>Detection rules operations</h2>
        {!rulesStatus && <p className="panel-desc">Loading detection rule status…</p>}
        {rulesStatus && (
          <div className="status-grid status-grid-compact" style={{ marginBottom: "0.75rem" }}>
            <div className="status-item"><div className="status-label">Sigma</div><div className="status-value">{rulesStatus.sigma.state} ({rulesStatus.sigma.rule_count})</div></div>
            <div className="status-item"><div className="status-label">Chainsaw</div><div className="status-value">{rulesStatus.chainsaw.state} ({rulesStatus.chainsaw.rule_count})</div></div>
            <div className="status-item"><div className="status-label">YARA</div><div className="status-value">{yaraStatus ? `${yaraStatus.state} (${yaraStatus.rule_count})` : "N/A"}</div></div>
          </div>
        )}
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button disabled={runningOp !== null} onClick={() => doOp("refresh-sigma", () => api.refreshSigmaRules())}>
            {runningOp === "refresh-sigma" ? "Refreshing…" : "Refresh Sigma"}
          </button>
          <button disabled={runningOp !== null} onClick={() => doOp("refresh-chainsaw", () => api.refreshChainsawRules())}>
            {runningOp === "refresh-chainsaw" ? "Refreshing…" : "Refresh Chainsaw"}
          </button>
          <button disabled={runningOp !== null} onClick={() => doOp("refresh-yara", () => api.refreshYaraRules())}>
            {runningOp === "refresh-yara" ? "Refreshing…" : "Refresh YARA"}
          </button>
          <button
            disabled={runningOp !== null}
            onClick={() =>
              doOp("refresh-all", async () => ({
                sigma: await api.refreshSigmaRules(),
                chainsaw: await api.refreshChainsawRules(),
                yara: await api.refreshYaraRules(),
              }))
            }
          >
            {runningOp === "refresh-all" ? "Refreshing…" : "Refresh all"}
          </button>
        </div>
      </div>

      <div className="panel animate-in animate-in-delay-2" style={{ marginBottom: "1rem" }}>
        <h2>Job operations</h2>
        <div style={{ display: "grid", gap: "0.5rem", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", marginBottom: "0.75rem" }}>
          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span className="status-label">Status filter</span>
            <select aria-label="Job status filter" value={jobStatusFilter} onChange={(e) => setJobStatusFilter(e.target.value)}>
              <option value="">all</option>
              <option value="failed">failed</option>
              <option value="pending">pending</option>
              <option value="running">running</option>
              <option value="completed">completed</option>
            </select>
          </label>
          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span className="status-label">Error code filter</span>
            <input
              aria-label="Job error code filter"
              value={jobErrorCodeFilter}
              onChange={(e) => setJobErrorCodeFilter(e.target.value)}
              placeholder="manifest_invalid"
            />
          </label>
          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span className="status-label">Error stage filter</span>
            <input
              aria-label="Job error stage filter"
              value={jobErrorStageFilter}
              onChange={(e) => setJobErrorStageFilter(e.target.value)}
              placeholder="parse"
            />
          </label>
        </div>
        {jobs.length === 0 && <p className="panel-desc">No recent jobs.</p>}
        {jobs.length > 0 && (
          <div className="stack">
            {jobs.map((j) => (
              <div key={j.id} className="status-item" style={{ display: "grid", gap: "0.45rem" }}>
                <div>
                  <strong>{j.case_name}</strong> · {j.hostname} · <span className="mono">{j.status}</span> ({j.progress}%)
                </div>
                {(j.error_code || j.error_stage) && (
                  <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                    {j.error_code && <span className="status-badge failed">code: {j.error_code}</span>}
                    {j.error_stage && <span className="status-badge pending">stage: {j.error_stage}</span>}
                  </div>
                )}
                <div className="mono">{j.message ?? "No message"}</div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button
                    className="secondary"
                    disabled={runningOp !== null || (j.status !== "pending" && j.status !== "running")}
                    onClick={() => doOp(`job-cancel-${j.id}`, () => api.cancelJob(j.id))}
                  >
                    Cancel
                  </button>
                  <button
                    className="secondary"
                    disabled={runningOp !== null || j.status !== "failed"}
                    onClick={() => doOp(`job-retry-${j.id}`, () => api.reingestEvidence(j.case_id, j.evidence_source_id))}
                  >
                    Retry ingest
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel animate-in animate-in-delay-2" style={{ marginBottom: "1rem" }}>
        <h2>Container status</h2>
        {containersError && <p className="panel-desc">Container status unavailable: {containersError}</p>}
        {!containersError && containers.length === 0 && <p className="panel-desc">No project containers found.</p>}
        {containers.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "0.75rem" }}>
            {containers.map((c) => (
              <div key={c.id} className="status-item" style={{ display: "grid", gap: "0.45rem", alignContent: "start" }}>
                <div>
                  <strong>{c.service ?? c.name}</strong> · <span className="mono">{c.name}</span>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                  <span className={`status-badge ${c.state === "running" ? "completed" : c.state === "exited" ? "failed" : "pending"}`}>{c.state}</span>
                  <span className={`status-badge ${c.health === "healthy" ? "completed" : c.health === "unhealthy" ? "failed" : "pending"}`}>
                    {c.health ?? "no-healthcheck"}
                  </span>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button
                    className="secondary"
                    disabled={runningOp !== null || c.state === "running"}
                    onClick={() => doOp(`container-start-${c.name}`, () => api.startContainer(c.name))}
                  >
                    Start
                  </button>
                  <button
                    className="secondary"
                    disabled={runningOp !== null}
                    onClick={() =>
                      doOp(`container-logs-${c.name}`, async () => {
                        const res = await api.getContainerLogs(c.name, 500);
                        setLogsTitle(c.name);
                        setLogsText(res.logs || "(no logs)");
                        setLogsOpen(true);
                        return { opened: c.name };
                      })
                    }
                  >
                    Logs
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel animate-in animate-in-delay-2" style={{ marginBottom: "1rem" }}>
        <h2>Bulk case delete</h2>
        <p className="panel-desc">Select one or more cases to remove permanently.</p>
        <div style={{ marginBottom: "0.6rem" }}>
          <button
            className="secondary"
            disabled={cases.length === 0 || runningOp !== null}
            onClick={() =>
              setBulkDeleteCaseIds(allCasesSelected ? [] : cases.map((c) => c.id))
            }
          >
            {allCasesSelected ? "Clear all" : "Select all"}
          </button>
        </div>
        <div className="stack" style={{ maxHeight: "220px", overflow: "auto", marginBottom: "0.75rem" }}>
          {cases.map((c) => (
            <label key={c.id} className="status-item" style={{ display: "flex", gap: "0.55rem", alignItems: "center" }}>
              <input
                type="checkbox"
                checked={bulkDeleteCaseIds.includes(c.id)}
                onChange={() => toggleBulkCase(c.id)}
              />
              <span>{c.name}</span>
              <span className="mono" style={{ marginLeft: "auto" }}>{c.evidence_source_count} src</span>
            </label>
          ))}
        </div>
        <button
          disabled={runningOp !== null || bulkDeleteCaseIds.length === 0}
          onClick={() => {
            if (!window.confirm(`Delete ${bulkDeleteCaseIds.length} selected case(s)? This cannot be undone.`)) return;
            void doOp("bulk-delete-cases", async () => {
              const result = await api.bulkDeleteCases(bulkDeleteCaseIds);
              setBulkDeleteCaseIds([]);
              await refreshCases();
              return result;
            });
          }}
        >
          {runningOp === "bulk-delete-cases" ? "Deleting…" : `Delete Selected Cases (${bulkDeleteCaseIds.length})`}
        </button>
      </div>

      <div className="panel animate-in animate-in-delay-2" style={{ marginBottom: "1rem" }}>
        <h2>Search index maintenance</h2>
        <p className="panel-desc">Rebuild search documents from canonical PostgreSQL/Timescale data.</p>
        <div style={{ display: "grid", gap: "0.6rem", maxWidth: "620px" }}>
          <select value={selectedCaseId} onChange={(e) => setSelectedCaseId(e.target.value)}>
            <option value="">All cases</option>
            {cases.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <select
            value={selectedSourceId}
            onChange={(e) => setSelectedSourceId(e.target.value)}
            disabled={!selectedCaseId}
          >
            <option value="">All sources in selected scope</option>
            {selectedSources.map((s) => (
              <option key={s.id} value={s.id}>{s.hostname} ({s.platform})</option>
            ))}
          </select>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button
              className="secondary"
              disabled={runningOp !== null}
              onClick={() =>
                doOp("reindex-scoped", () =>
                  api.reindexSearch({
                    caseId: selectedCaseId || undefined,
                    sourceId: selectedSourceId || undefined,
                  })
                )
              }
            >
              {runningOp === "reindex-scoped" ? "Reindexing…" : "Run Scoped Reindex"}
            </button>
            <button
              disabled={runningOp !== null}
              onClick={() => {
                if (!window.confirm("Reindex all sources? This can take time.")) return;
                void doOp("reindex-all", () => api.reindexSearch());
              }}
            >
              {runningOp === "reindex-all" ? "Reindexing…" : "Full Reindex"}
            </button>
          </div>
        </div>
      </div>

      {(opsError || opsMessage) && (
        <div className={`alert ${opsError ? "alert-error" : "alert-success"}`} style={{ marginBottom: "1rem" }}>
          {opsError ?? opsMessage}
        </div>
      )}

      <AdminUsersPage me={me} />

      {logsOpen && (
        <div className="modal-backdrop" onClick={() => setLogsOpen(false)}>
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-label="Container logs"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2>Container logs: {logsTitle}</h2>
              <button className="secondary" onClick={() => setLogsOpen(false)}>Close</button>
            </div>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.78rem" }}>
              {logsText}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
