import { useCallback, useEffect, useState } from "react";
import { api, SigmaRulesStatus } from "../api/client";

export default function SigmaRulesSync() {
  const [status, setStatus] = useState<SigmaRulesStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .getSigmaRulesStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (status?.state !== "running") return;
    const id = window.setInterval(load, 3000);
    return () => window.clearInterval(id);
  }, [status?.state, load]);

  const onRefresh = async () => {
    setError(null);
    setRefreshing(true);
    try {
      await api.refreshSigmaRules();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not queue rule refresh");
    } finally {
      setRefreshing(false);
    }
  };

  const busy = refreshing || status?.state === "running";
  const updatedLabel =
    status?.updated_at != null
      ? new Date(status.updated_at).toLocaleString()
      : "not yet synced from GitHub";

  return (
    <div className="sigma-rules-sync panel-compact">
      <div className="sigma-rules-sync-main">
        <span className="sigma-rules-sync-label">Detection rules</span>
        <span className="sigma-rules-sync-meta mono">
          {(status?.rule_count ?? 0).toLocaleString()} rules · profile dfir · ref {status?.ref ?? "master"} ·{" "}
          {updatedLabel}
          {status?.refresh_interval_hours
            ? ` · auto every ${status.refresh_interval_hours}h`
            : ""}
        </span>
        {status?.state === "running" && (
          <span className="sigma-rules-sync-running">Updating from GitHub…</span>
        )}
        {status?.state === "error" && status.message && (
          <span className="sigma-rules-sync-error">{status.message}</span>
        )}
        {error && <span className="sigma-rules-sync-error">{error}</span>}
      </div>
      <button
        type="button"
        className="secondary sigma-rules-sync-btn"
        disabled={busy}
        onClick={onRefresh}
      >
        {busy ? "Updating…" : "Update rules"}
      </button>
    </div>
  );
}
