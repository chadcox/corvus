import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  Case,
  EvidenceHashes,
  Entity,
  EvidenceSource,
  IngestJob,
  SigmaDetection,
  SourceStats,
  TimelineEvent,
} from "../api/client";
import BrowserView from "../components/BrowserView";
import MftView from "../components/MftView";
import DiskView from "../components/DiskView";
import GlobalSearch from "../components/GlobalSearch";
import IngestStatusPanel from "../components/IngestStatusPanel";
import SigmaFindingsPanel from "../components/SigmaFindingsPanel";
import ObjectView from "../components/ObjectView";
import TimelineView from "../components/TimelineView";

type Tab = "timeline" | "object" | "disk" | "mft" | "browser";
type StatPivot = "events" | "objects" | "paths" | "sigma" | "mft" | "browser";

const BASE_TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "timeline", label: "Timeline", icon: "◷" },
  { id: "object", label: "Entities", icon: "◉" },
  { id: "disk", label: "Disk", icon: "▣" },
];

function sourceCollectorLabel(collector: string): string {
  if (collector === "kape" || collector === "import") return "Imported";
  return collector;
}

function sourcePlatformLabel(platform: string): string {
  if (platform === "macos") return "macOS";
  if (platform === "windows") return "Windows";
  if (platform === "linux") return "Linux";
  if (platform === "memory") return "Memory";
  return "Unknown platform";
}

function formatDuration(seconds: number | null | undefined): string | null {
  if (seconds == null) return null;
  if (seconds < 1) return `${Math.max(0, seconds).toFixed(2)}s`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins < 60) return secs ? `${mins}m ${secs}s` : `${mins}m`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins ? `${hours}h ${remMins}m` : `${hours}h`;
}

const ACTIVE_JOB_STATUSES = new Set(["pending", "running"]);

/** Compact counts for narrow sidebar stat cards (full value in title tooltip). */
function formatCompactStat(n: number): string {
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    return m >= 10 ? `${Math.round(m)}M` : `${m.toFixed(1).replace(/\.0$/, "")}M`;
  }
  if (n >= 10_000) return `${Math.round(n / 1000)}K`;
  if (n >= 1_000) {
    const k = n / 1000;
    return k >= 10 ? `${Math.round(k)}K` : `${k.toFixed(1).replace(/\.0$/, "")}K`;
  }
  return n.toLocaleString();
}

const SEVERITY_RANK: Record<string, number> = {
  critical: 5,
  high: 4,
  medium: 3,
  low: 2,
  informational: 1,
};

function topSeverity(detections: SigmaDetection[]): string {
  return detections.reduce(
    (top, detection) =>
      (SEVERITY_RANK[detection.level] ?? 0) > (SEVERITY_RANK[top] ?? 0)
        ? detection.level
        : top,
    "informational"
  );
}

function isActiveJob(job: IngestJob | null): boolean {
  return !!job && ACTIVE_JOB_STATUSES.has(job.status);
}

function packageFileName(packagePath: string): string {
  const clean = (packagePath || "").replace(/\\/g, "/").replace(/\/+$/, "");
  if (!clean) return "n/a";
  const parts = clean.split("/");
  return parts[parts.length - 1] || "n/a";
}

function formatIngestHistoryMessage(message: string | null): string[] {
  if (!message) return ["No details available."];
  const compact = message.replace(/\s+/g, " ").trim();
  const sections = compact
    .split(" — ")
    .flatMap((part) => part.split("; "))
    .map((part) => part.trim())
    .filter(Boolean);
  if (sections.length === 0) return [compact];
  return sections;
}

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [sources, setSources] = useState<EvidenceSource[]>([]);
  const [selectedSource, setSelectedSource] = useState<string>("");
  const [tab, setTab] = useState<Tab>("timeline");
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [uploadFileName, setUploadFileName] = useState<string | null>(null);
  const [job, setJob] = useState<IngestJob | null>(null);
  const [hostname, setHostname] = useState("");
  const [platform, setPlatform] = useState("unknown");
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [focusTimeline, setFocusTimeline] = useState<TimelineEvent | null>(null);
  const [focusPath, setFocusPath] = useState<string | null>(null);
  const [focusEntity, setFocusEntity] = useState<Entity | null>(null);
  const [stats, setStats] = useState<SourceStats | null>(null);
  const [timelineSigmaOnly, setTimelineSigmaOnly] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [hashInfo, setHashInfo] = useState<EvidenceHashes | null>(null);
  const [hashingFiles, setHashingFiles] = useState(false);
  const [scanningYara, setScanningYara] = useState(false);
  const [detections, setDetections] = useState<SigmaDetection[]>([]);
  const [sourceInfoOpen, setSourceInfoOpen] = useState(false);
  const [sourceInfo, setSourceInfo] = useState<EvidenceSource | null>(null);
  const [sourceInfoHash, setSourceInfoHash] = useState<EvidenceHashes | null>(null);
  const [ingestHistoryOpen, setIngestHistoryOpen] = useState(false);
  const [ingestHistoryLoading, setIngestHistoryLoading] = useState(false);
  const [ingestHistoryBySource, setIngestHistoryBySource] = useState<Record<string, IngestJob[]>>({});

  const selectedSourceData = sources.find((s) => s.id === selectedSource);
  const sourceIngesting =
    selectedSourceData?.status === "pending" || selectedSourceData?.status === "running";
  const showIngestStatus =
    uploading || isActiveJob(job) || sourceIngesting || job?.status === "failed";
  const canInvestigate =
    selectedSource &&
    selectedSourceData &&
    selectedSourceData.status === "completed" &&
    !showIngestStatus;

  const load = useCallback(
    (opts?: { selectSourceId?: string }) => {
      if (!caseId) return;
      Promise.all([api.getCase(caseId), api.listEvidence(caseId)])
        .then(([c, s]) => {
          setCaseData(c);
          setSources(s);
          if (opts?.selectSourceId) {
            setSelectedSource(opts.selectSourceId);
          } else if (s.length && !selectedSource) {
            setSelectedSource(s[0].id);
          }
        })
        .catch((e) => setError(String(e)));
    },
    [caseId, selectedSource]
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setFocusTimeline(null);
    setFocusPath(null);
    setFocusEntity(null);
    setStats(null);
    setHashInfo(null);
    setDetections([]);
    setTimelineSigmaOnly(false);
    setTab("timeline");
  }, [selectedSource]);

  useEffect(() => {
    if (tab === "mft" && stats && stats.mft_count === 0) {
      setTab("timeline");
    }
    if (tab === "browser" && stats && stats.browser_count === 0) {
      setTab("timeline");
    }
  }, [tab, stats]);

  const pivotToStat = (target: StatPivot) => {
    setFocusTimeline(null);
    setFocusPath(null);
    setFocusEntity(null);
    switch (target) {
      case "events":
        setTimelineSigmaOnly(false);
        setTab("timeline");
        break;
      case "objects":
        setTab("object");
        break;
      case "paths":
        setTab("disk");
        break;
      case "sigma":
        setTimelineSigmaOnly(true);
        setTab("timeline");
        break;
      case "mft":
        setTimelineSigmaOnly(false);
        setTab("mft");
        break;
      case "browser":
        setTimelineSigmaOnly(false);
        setTab("browser");
        break;
    }
  };

  const statCardActive = (target: StatPivot): boolean => {
    if (target === "events") return tab === "timeline" && !timelineSigmaOnly;
    if (target === "sigma") return tab === "timeline" && timelineSigmaOnly;
    if (target === "objects") return tab === "object";
    if (target === "paths") return tab === "disk";
    if (target === "mft") return tab === "mft";
    if (target === "browser") return tab === "browser";
    return false;
  };

  const viewTabs: { id: Tab; label: string; icon: string }[] = [
    ...BASE_TABS,
    ...(stats && stats.mft_count > 0 ? [{ id: "mft" as const, label: "MFT", icon: "▦" }] : []),
    ...(stats && stats.browser_count > 0
      ? [{ id: "browser" as const, label: "Browser", icon: "◈" }]
      : []),
  ];

  useEffect(() => {
    if (!caseId || sources.length === 0) return;
    const busy = sources.find((s) => s.status === "pending" || s.status === "running");
    if (!busy || isActiveJob(job)) return;

    setSelectedSource(busy.id);
    api
      .listSourceJobs(caseId, busy.id)
      .then((jobs) => {
        const active =
          jobs.find((j) => ACTIVE_JOB_STATUSES.has(j.status)) ?? jobs[0] ?? null;
        if (active) setJob(active);
      })
      .catch(() => {});
  }, [caseId, sources, job]);

  useEffect(() => {
    if (!caseId || !selectedSource) return;
    const source = sources.find((s) => s.id === selectedSource);
    if (!source || source.status !== "completed") {
      setStats(null);
      return;
    }
    api
      .getSourceStats(caseId, selectedSource)
      .then(setStats)
      .catch(() => setStats(null));
    api
      .getEvidenceHashes(caseId, selectedSource)
      .then(setHashInfo)
      .catch(() => setHashInfo(null));
    api
      .listSigmaDetections(caseId, selectedSource)
      .then(setDetections)
      .catch(() => setDetections([]));
  }, [caseId, selectedSource, sources]);

  useEffect(() => {
    if (!caseId || !selectedSource || !hashInfo) return;
    const hashRunning = hashInfo.hash_status === "running";
    const yaraRunning = hashInfo.yara_status === "running";
    if (!hashRunning && !yaraRunning) return;

    const t = setInterval(() => {
      api
        .getEvidenceHashes(caseId, selectedSource)
        .then((latest) => {
          setHashInfo(latest);
          if (sourceInfoOpen && sourceInfo?.id === selectedSource) {
            setSourceInfoHash(latest);
          }
          const stillRunning =
            latest.hash_status === "running" || latest.yara_status === "running";
          if (!stillRunning) {
            api
              .listSigmaDetections(caseId, selectedSource)
              .then(setDetections)
              .catch(() => {});
            api
              .getSourceStats(caseId, selectedSource)
              .then(setStats)
              .catch(() => {});
          }
        })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(t);
  }, [caseId, selectedSource, hashInfo, sourceInfoOpen, sourceInfo]);

  const summaryCategories = useMemo(() => {
    const counts = new Map<string, number>();
    detections.forEach((d) => {
      const tag = d.tags.find((t) => t.startsWith("attack.")) ?? d.tags[0] ?? d.level;
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    });
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([tag]) => tag.replace(/^attack\./, ""));
  }, [detections]);

  useEffect(() => {
    if (!job || (job.status !== "pending" && job.status !== "running")) return;
    const t = setInterval(() => {
      api.getJob(job.id).then((j) => {
        setJob(j);
        if (j.status === "completed" || j.status === "failed") {
          load({ selectSourceId: j.evidence_source_id });
        }
      });
    }, 2000);
    return () => clearInterval(t);
  }, [job, load]);

  useEffect(() => {
    if (!sourceInfoOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSourceInfoOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sourceInfoOpen]);

  useEffect(() => {
    if (!ingestHistoryOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIngestHistoryOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ingestHistoryOpen]);

  const openIngestHistory = async () => {
    if (!caseId) return;
    setIngestHistoryOpen(true);
    setIngestHistoryLoading(true);
    try {
      const entries = await Promise.all(
        sources.map(async (s) => [s.id, await api.listSourceJobs(caseId, s.id)] as const)
      );
      setIngestHistoryBySource(Object.fromEntries(entries));
    } catch {
      setIngestHistoryBySource({});
    } finally {
      setIngestHistoryLoading(false);
    }
  };

  const handleUploadFile = async (file: File) => {
    if (!file || !caseId) return;
    setUploading(true);
    setUploadFileName(file.name);
    setError(null);
    try {
      const j = await api.uploadEvidence(
        caseId,
        file,
        hostname || undefined,
        platform
      );
      setJob(j);
      setSelectedSource(j.evidence_source_id);
      load({ selectSourceId: j.evidence_source_id });
    } catch (err) {
      setError(String(err));
      setUploadFileName(null);
    } finally {
      setUploading(false);
    }
  };

  const cancelProcessing = async () => {
    if (!job || !isActiveJob(job)) return;
    const proceed = window.confirm("Cancel current evidence processing?");
    if (!proceed) return;
    try {
      const updated = await api.cancelJob(job.id);
      setJob(updated);
      if (caseId) {
        load({ selectSourceId: updated.evidence_source_id });
      }
    } catch (err) {
      setError(String(err));
    }
  };

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await handleUploadFile(file);
    e.target.value = "";
  };

  const startRename = () => {
    setNameInput(caseData?.name ?? "");
    setEditingName(true);
  };

  const commitRename = async () => {
    const trimmed = nameInput.trim();
    if (!caseId || !trimmed || trimmed === caseData?.name) {
      setEditingName(false);
      return;
    }
    try {
      const updated = await api.renameCase(caseId, trimmed);
      setCaseData(updated);
      setEditingName(false);
    } catch (err) {
      setError(String(err));
      setEditingName(false);
    }
  };

  if (!caseId) return null;

  return (
    <div className="case-workspace animate-in">
      <aside className="case-sidebar animate-in animate-in-delay-1">
        <Link to="/" className="back-link">
          ← All cases
        </Link>

        <div>
          <p className="section-label">Case</p>
          {editingName ? (
            <form
              onSubmit={(e) => { e.preventDefault(); commitRename(); }}
              className="case-rename-form"
            >
              <input
                className="case-rename-input"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                autoFocus
                onBlur={commitRename}
                onKeyDown={(e) => e.key === "Escape" && setEditingName(false)}
                aria-label="Case name"
              />
            </form>
          ) : (
            <h1
              className="case-name case-name-editable"
              title="Click to rename"
              onClick={startRename}
            >
              {caseData?.name ?? "…"}
              <span className="case-name-edit-icon" aria-hidden="true">✎</span>
            </h1>
          )}
        </div>

        <div className="panel">
          <h2>Ingest evidence</h2>
          <p className="panel-desc">
            Upload a ZIP archive or individual files — EVTX logs, $MFT, registry hives, Chromium profiles, CSV exports, and more.
          </p>
          <div className="upload-zone">
            <div
              className={`upload-drop-hint${dragActive ? " is-dragover" : ""}${(uploading || isActiveJob(job)) ? " is-disabled" : ""}`}
              role="button"
              tabIndex={uploading || isActiveJob(job) ? -1 : 0}
              aria-label="Drop evidence files or click to select"
              onClick={() => {
                if (uploading || isActiveJob(job)) return;
                fileInputRef.current?.click();
              }}
              onKeyDown={(e) => {
                if (uploading || isActiveJob(job)) return;
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              onDragEnter={(e) => {
                e.preventDefault();
                if (uploading || isActiveJob(job)) return;
                setDragActive(true);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                if (uploading || isActiveJob(job)) return;
                setDragActive(true);
              }}
              onDragLeave={(e) => {
                e.preventDefault();
                const next = e.relatedTarget as Node | null;
                if (!next || !e.currentTarget.contains(next)) {
                  setDragActive(false);
                }
              }}
              onDrop={async (e) => {
                e.preventDefault();
                setDragActive(false);
                if (uploading || isActiveJob(job)) return;
                const file = e.dataTransfer.files?.[0];
                if (!file) return;
                await handleUploadFile(file);
              }}
            >
              {uploading ? "Uploading…" : "Select files or a ZIP archive"}
            </div>
            <div className="upload-actions">
              <input
                placeholder="Hostname override"
                value={hostname}
                onChange={(e) => setHostname(e.target.value)}
                aria-label="Hostname override"
                disabled={uploading || isActiveJob(job)}
              />
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                aria-label="Evidence platform"
                disabled={uploading || isActiveJob(job)}
              >
                <option value="unknown">Auto platform</option>
                <option value="windows">Windows</option>
                <option value="macos">macOS</option>
                <option value="linux">Linux</option>
                <option value="memory">Memory</option>
              </select>
              <input
                ref={fileInputRef}
                type="file"
                style={{ display: "none" }}
                onChange={onUpload}
                disabled={uploading || isActiveJob(job)}
              />
            </div>
          </div>
          {job && !uploading && (
            <div className="ingest-status-compact">
              <div className="job-status-line">
                <span className={`status-badge ${job.status}`}>{job.status}</span>
                <span>{job.progress}%</span>
              </div>
              {job.message && (
                <p className="mono ingest-status-compact-msg">{job.message}</p>
              )}
              {isActiveJob(job) && (
                <button
                  type="button"
                  className="secondary"
                  style={{ width: "100%", marginTop: "0.5rem" }}
                  onClick={cancelProcessing}
                >
                  Cancel processing
                </button>
              )}
            </div>
          )}
        </div>

        <div className="panel">
          <h2>Evidence sources</h2>
          {sources.length === 0 && (
            <p className="panel-desc" style={{ margin: 0 }}>No evidence uploaded yet.</p>
          )}
          {sources.length > 0 && (
            <ul className="source-card-list">
              {sources.map((s) => (
                <li
                  key={s.id}
                  className={`source-card${selectedSource === s.id ? " selected" : ""}`}
                  onClick={() => {
                    setSelectedSource(s.id);
                    setSourceInfo(s);
                    setSourceInfoOpen(true);
                    setSourceInfoHash(null);
                    api
                      .getEvidenceHashes(caseId, s.id)
                      .then(setSourceInfoHash)
                      .catch(() => setSourceInfoHash(null));
                  }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter") return;
                    setSelectedSource(s.id);
                    setSourceInfo(s);
                    setSourceInfoOpen(true);
                    setSourceInfoHash(null);
                    api
                      .getEvidenceHashes(caseId, s.id)
                      .then(setSourceInfoHash)
                      .catch(() => setSourceInfoHash(null));
                  }}
                >
                  <div>
                    <div className="source-card-name">{s.hostname}</div>
                    <div className="source-card-host">
                      {[
                        sourcePlatformLabel(s.platform),
                      ].filter(Boolean).join(" · ")}
                    </div>
                  </div>
                  <span className={`status-badge ${s.status}`}>{s.status}</span>
                </li>
              ))}
            </ul>
          )}
          {selectedSourceData?.manifest && (
            <dl className="manifest-meta">
              <dt>Platform</dt>
              <dd>{sourcePlatformLabel(selectedSourceData.platform)}</dd>
              <dt>Source</dt>
              <dd>{selectedSourceData.source_type}</dd>
              {selectedSourceData.os_version && (
                <>
                  <dt>OS</dt>
                  <dd>{selectedSourceData.os_version}</dd>
                </>
              )}
              {selectedSourceData.architecture && (
                <>
                  <dt>Architecture</dt>
                  <dd>{selectedSourceData.architecture}</dd>
                </>
              )}
              {typeof selectedSourceData.manifest.collected_at === "string" && (
                <>
                  <dt>Collected</dt>
                  <dd className="mono">{selectedSourceData.manifest.collected_at as string}</dd>
                </>
              )}
              {typeof selectedSourceData.manifest.timezone === "string" && (
                <>
                  <dt>Timezone</dt>
                  <dd>{selectedSourceData.manifest.timezone as string}</dd>
                </>
              )}
              {Array.isArray(selectedSourceData.manifest.modules_run) &&
                selectedSourceData.manifest.modules_run.length > 0 && (
                  <>
                    <dt>Modules</dt>
                    <dd>{(selectedSourceData.manifest.modules_run as string[]).join(", ")}</dd>
                  </>
                )}
            </dl>
          )}
        </div>

        {selectedSourceData?.status === "completed" && hashInfo && (
          <div className="panel">
            <h2>Actions</h2>
            <div className="evidence-hash-panel" style={{ marginTop: "0.65rem" }}>
              <div className="evidence-hash-actions">
                {hashInfo.hash_status === "complete" ? (
                  <>
                    <span className="mono" style={{ fontSize: "0.7rem", color: "var(--muted)" }}>
                      {(hashInfo.hashed_files_in_db).toLocaleString()} files hashed
                    </span>
                    <a
                      href={api.evidenceHashExportUrl(caseId, selectedSource)}
                      className="secondary"
                      style={{ fontSize: "0.72rem", padding: "0.2rem 0.5rem" }}
                      download
                    >
                      Export hashes
                    </a>
                  </>
                ) : hashInfo.hash_status === "running" ? (
                  <span className="mono" style={{ fontSize: "0.7rem", color: "var(--muted)" }}>Hashing files…</span>
                ) : (
                  <button
                    type="button"
                    className="secondary"
                    style={{ fontSize: "0.72rem", width: "100%", padding: "0.25rem" }}
                    disabled={hashingFiles}
                    onClick={async () => {
                      const proceed = window.confirm(
                        "This will hash all files in the evidence package using SHA256, SHA1, and MD5. " +
                        "It can take a while on large collections and will use worker resources. Continue?"
                      );
                      if (!proceed) return;
                      setHashingFiles(true);
                      try { await api.computeFileHashes(caseId, selectedSource); setHashInfo((h) => h ? { ...h, hash_status: "running" } : h); }
                      finally { setHashingFiles(false); }
                    }}
                  >
                    {hashingFiles ? "Starting…" : "Hash all evidence files"}
                  </button>
                )}
              </div>
              <div className="evidence-hash-actions" style={{ marginTop: "0.5rem" }}>
                {hashInfo.yara_status === "running" ? (
                  <span className="mono" style={{ fontSize: "0.7rem", color: "var(--muted)" }}>YARA scanning…</span>
                ) : hashInfo.yara_status === "complete" ? (
                  <span className="mono" style={{ fontSize: "0.7rem", color: "var(--muted)" }}>
                    {(hashInfo.yara_match_count ?? 0).toLocaleString()} YARA rules matched across {(hashInfo.yara_file_count ?? 0).toLocaleString()} files
                  </span>
                ) : (
                  <button
                    type="button"
                    className="secondary"
                    style={{ fontSize: "0.72rem", width: "100%", padding: "0.25rem" }}
                    disabled={scanningYara}
                    onClick={async () => {
                      const proceed = window.confirm(
                        "This runs YARA across evidence files using the signature-base default ruleset. " +
                        "It can take time on large collections. Continue?"
                      );
                      if (!proceed) return;
                      setScanningYara(true);
                      try { await api.computeYaraScan(caseId, selectedSource); setHashInfo((h) => h ? { ...h, yara_status: "running" } : h); }
                      finally { setScanningYara(false); }
                    }}
                  >
                    {scanningYara ? "Starting…" : "Scan evidence with YARA"}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {stats && selectedSourceData?.status === "completed" && !showIngestStatus && (
          <div className="panel">
            <h2>Findings</h2>
            <div className="stats-strip" style={{ marginTop: "0.65rem" }} role="group" aria-label="Jump to view">
              {(
                [
                  ["events", stats.timeline_count, "Events", "Open timeline"] as const,
                  ["objects", stats.entity_count, "Entities", "Open entities"] as const,
                  ["paths", stats.filesystem_count, "Disk", "Open disk view"] as const,
                  [
                    "sigma",
                    stats.sigma_detection_count ?? 0,
                    "Detections",
                    "Open timeline (detections only)",
                  ] as const,
                  ...(stats.mft_count > 0
                    ? ([
                        ["mft", stats.mft_count, "MFT", "Open MFT view"] as const,
                      ] satisfies readonly [StatPivot, number, string, string][])
                    : []),
                  ...(stats.browser_count > 0
                    ? ([
                        ["browser", stats.browser_count, "Browser", "Open browser forensics"] as const,
                      ] satisfies readonly [StatPivot, number, string, string][])
                    : []),
                ] satisfies readonly [StatPivot, number, string, string][]
              ).map(([target, count, label, hint]) => (
                <button
                  key={target}
                  type="button"
                  className={`stat-card stat-card--action${statCardActive(target) ? " active" : ""}`}
                  title={`${count.toLocaleString()} ${label.toLowerCase()} — ${hint}`}
                  aria-current={statCardActive(target) ? "true" : undefined}
                  onClick={() => pivotToStat(target)}
                >
                  <div className="stat-value">{formatCompactStat(count)}</div>
                  <div className="stat-label">{label}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {sources.length > 0 && (
          <div className="panel">
            <button type="button" className="secondary" style={{ width: "100%" }} onClick={openIngestHistory}>
              View ingest history
            </button>
          </div>
        )}
      </aside>

      <div className="case-main animate-in animate-in-delay-2">
        {error && <div className="alert alert-error">{error}</div>}

        {showIngestStatus && (
          <IngestStatusPanel
            phase={uploading ? "uploading" : "ingesting"}
            job={uploading ? null : job}
            fileName={uploadFileName}
          />
        )}

        {canInvestigate ? (
          <>
            {stats && selectedSourceData && (
              <section className="case-summary-panel" aria-label="Case summary">
                <div className="case-summary-head">
                  <div>
                    <p className="section-label">Case Summary</p>
                    <h2>{selectedSourceData.hostname}</h2>
                    <p>
                      {sourcePlatformLabel(selectedSourceData.platform)} endpoint evidence ready for triage.
                    </p>
                  </div>
                  <span className={`summary-severity summary-severity-${topSeverity(detections)}`}>
                    {detections.length ? topSeverity(detections) : "clear"}
                  </span>
                </div>
                <div className="summary-kpis">
                  <div><strong>{formatCompactStat(stats.timeline_count)}</strong><span>Events Processed</span></div>
                  <div><strong>{detections.length.toLocaleString()}</strong><span>Detection Rules</span></div>
                  <div><strong>{detections.filter((d) => d.level === "critical").length.toLocaleString()}</strong><span>Critical Findings</span></div>
                </div>
                <div className="summary-insights">
                  <div>
                    <span>Top Hosts</span>
                    <strong>{selectedSourceData.hostname}</strong>
                  </div>
                  <div>
                    <span>Top Categories</span>
                    <strong>{summaryCategories.length ? summaryCategories.join(", ") : "No detection categories"}</strong>
                  </div>
                </div>
              </section>
            )}

            <SigmaFindingsPanel
              caseId={caseId}
              sourceId={selectedSource}
              detections={detections}
              onViewEvent={(eventId) => {
                setTimelineSigmaOnly(false);
                setTab("timeline");
                api
                  .getTimelineEvent(caseId, selectedSource, eventId)
                  .then((ev) => setFocusTimeline(ev))
                  .catch(() => setError("Could not load timeline event"));
              }}
              onOpenPath={(path) => {
                setTimelineSigmaOnly(false);
                setTab("disk");
                setFocusTimeline(null);
                setFocusEntity(null);
                setFocusPath(path);
              }}
            />

            <GlobalSearch
              caseId={caseId}
              sourceId={selectedSource}
              sourceStatus={selectedSourceData.status}
              onNavigate={({ tab: t, timelineEvent, filesystemPath, entity }) => {
                if (t !== "timeline") setTimelineSigmaOnly(false);
                setTab(t);
                setFocusTimeline(timelineEvent ?? null);
                setFocusPath(filesystemPath ?? null);
                setFocusEntity(entity ?? null);
              }}
            />

            <nav className="view-tabs" aria-label="Investigation views">
              {viewTabs.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`view-tab${tab === t.id ? " active" : ""}`}
                  onClick={() => {
                    if (t.id !== "timeline") setTimelineSigmaOnly(false);
                    setTab(t.id);
                  }}
                  aria-current={tab === t.id ? "page" : undefined}
                >
                  <span className="view-tab-icon" aria-hidden="true">{t.icon}</span>
                  {t.label}
                </button>
              ))}
            </nav>

            {tab === "timeline" && (
              <TimelineView
                caseId={caseId}
                sourceId={selectedSource}
                focusEvent={focusTimeline}
                eventTypes={stats?.event_types ?? []}
                sigmaOnly={timelineSigmaOnly}
                onSigmaOnlyChange={setTimelineSigmaOnly}
                onEntityClick={(entity) => {
                  setTimelineSigmaOnly(false);
                  setTab("object");
                  setFocusEntity(entity);
                }}
              />
            )}
            {tab === "object" && (
              <ObjectView
                caseId={caseId}
                sourceId={selectedSource}
                focusEntity={focusEntity}
                onTimelineClick={(ev) => {
                  setTab("timeline");
                  setFocusTimeline(ev);
                }}
              />
            )}
            {tab === "disk" && (
              <DiskView caseId={caseId} sourceId={selectedSource} focusPath={focusPath} />
            )}
            {tab === "mft" && (
              <MftView caseId={caseId} sourceId={selectedSource} mftTotal={stats?.mft_count ?? 0} />
            )}
            {tab === "browser" && (
              <BrowserView caseId={caseId} sourceId={selectedSource} />
            )}
          </>
        ) : !showIngestStatus ? (
          <div className="empty-state">
            <div className="empty-state-icon">↑</div>
            <p>Upload evidence in the sidebar to begin investigation.</p>
          </div>
        ) : null}
      </div>
      {sourceInfoOpen && sourceInfo && (
        <div className="modal-backdrop" onClick={() => setSourceInfoOpen(false)}>
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-label="Evidence source details"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2>Evidence source details</h2>
              <button type="button" className="ghost" onClick={() => setSourceInfoOpen(false)}>Close</button>
            </div>
            <dl className="manifest-meta modal-meta">
              <dt>Hostname</dt>
              <dd>{sourceInfo.hostname}</dd>
              <dt>Status</dt>
              <dd><span className={`status-badge ${sourceInfo.status}`}>{sourceInfo.status}</span></dd>
              {formatDuration(sourceInfo.total_processing_seconds) && (
                <>
                  <dt>Total processing time</dt>
                  <dd className="mono">{formatDuration(sourceInfo.total_processing_seconds)}</dd>
                </>
              )}
              <dt>Platform</dt>
              <dd>{sourcePlatformLabel(sourceInfo.platform)}</dd>
              <dt>Collector</dt>
              <dd>{sourceCollectorLabel(sourceInfo.collector)}</dd>
              <dt>Collected at</dt>
              <dd>{sourceInfo.collected_at ? new Date(sourceInfo.collected_at).toLocaleString() : "n/a"}</dd>
              <dt>Uploaded at</dt>
              <dd>{new Date(sourceInfo.created_at).toLocaleString()}</dd>
              <dt>Uploaded filename</dt>
              <dd className="mono">{sourceInfo.uploaded_filename || packageFileName(sourceInfo.package_path)}</dd>
              <dt>Package folder</dt>
              <dd className="mono">{packageFileName(sourceInfo.package_path)}</dd>
              <dt>Package path</dt>
              <dd className="mono">{sourceInfo.package_path}</dd>
              <dt>Package SHA256</dt>
              <dd className="mono">{sourceInfoHash?.sha256 ?? "n/a"}</dd>
              <dt>Package SHA1</dt>
              <dd className="mono">{sourceInfoHash?.sha1 ?? "n/a"}</dd>
              <dt>Package MD5</dt>
              <dd className="mono">{sourceInfoHash?.md5 ?? "n/a"}</dd>
              <dt>Hash status</dt>
              <dd>{sourceInfoHash?.hash_status ?? "n/a"}</dd>
              <dt>Hashed files</dt>
              <dd>{sourceInfoHash ? sourceInfoHash.hashed_files_in_db.toLocaleString() : "n/a"}</dd>
            </dl>
          </div>
        </div>
      )}
      {ingestHistoryOpen && (
        <div className="modal-backdrop" onClick={() => setIngestHistoryOpen(false)}>
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-label="Ingest history"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: "64rem" }}
          >
            <div className="modal-head">
              <h2>Ingest history</h2>
              <button type="button" className="ghost" onClick={() => setIngestHistoryOpen(false)}>Close</button>
            </div>
            {ingestHistoryLoading ? (
              <p className="panel-desc" style={{ marginTop: 0 }}>Loading history…</p>
            ) : (
              <div style={{ display: "grid", gap: "0.75rem", maxHeight: "70vh", overflow: "auto", paddingRight: "0.25rem" }}>
                {sources.map((s) => {
                  const jobs = ingestHistoryBySource[s.id] ?? [];
                  return (
                    <section key={s.id} className="panel" style={{ margin: 0 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem", alignItems: "center" }}>
                        <div>
                          <h3 style={{ margin: 0 }}>{s.hostname}</h3>
                          <p className="panel-desc" style={{ margin: "0.2rem 0 0" }}>
                            {sourcePlatformLabel(s.platform)} · {sourceCollectorLabel(s.collector)}
                          </p>
                        </div>
                        <span className={`status-badge ${s.status}`}>{s.status}</span>
                      </div>
                      {jobs.length === 0 ? (
                        <p className="panel-desc" style={{ margin: "0.75rem 0 0" }}>No ingest jobs recorded.</p>
                      ) : (
                        <ul className="job-history-list" style={{ marginTop: "0.75rem" }}>
                          {jobs.slice(0, 20).map((j) => (
                            <li key={j.id} className="job-history-item">
                              <span className={`status-badge ${j.status}`}>{j.status}</span>
                              <span className="mono job-history-msg">
                                <ul style={{ margin: 0, paddingLeft: "1rem" }}>
                                  {formatIngestHistoryMessage(j.message).map((line) => (
                                    <li key={`${j.id}-${line}`}>{line}</li>
                                  ))}
                                </ul>
                              </span>
                              <span className="mono job-history-time">
                                {j.finished_at
                                  ? new Date(j.finished_at).toLocaleString()
                                  : new Date(j.created_at).toLocaleString()}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
