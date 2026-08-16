import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useParams } from "react-router-dom";
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
import CaseNav, { CaseTab, SeverityLevel } from "../components/CaseNav";
import MftView from "../components/MftView";
import DiskView from "../components/DiskView";
import GlobalSearch from "../components/GlobalSearch";
import IngestStatusPanel from "../components/IngestStatusPanel";
import SigmaFindingsPanel from "../components/SigmaFindingsPanel";
import SourcesView from "../components/SourcesView";
import ObjectView from "../components/ObjectView";
import OverviewView, { CountsStrip, StatPivot } from "../components/OverviewView";
import TimelineView from "../components/TimelineView";
import ConfirmDialog from "../components/ConfirmDialog";
import Drawer from "../components/Drawer";
import {
  ACTIVE_JOB_STATUSES,
  formatCompactStat,
  formatDuration,
  formatIngestHistoryMessage,
  isActiveJob,
  jobDisplayStatus,
  packageFileName,
  sourceCollectorLabel,
  sourcePlatformLabel,
  topSeverity,
} from "../lib/caseFormat";

type Tab = CaseTab;
type ConfirmAction =
  | { kind: "cancel"; jobId: string }
  | { kind: "hash"; sourceId: string }
  | { kind: "yara"; sourceId: string };

/** Views that require a completed evidence source to render anything useful. */
const INVESTIGATION_TABS: ReadonlySet<Tab> = new Set([
  "overview",
  "timeline",
  "object",
  "disk",
  "mft",
  "browser",
  "detections",
]);

const NAV_COLLAPSED_KEY = "corvus.navCollapsed";

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [sources, setSources] = useState<EvidenceSource[]>([]);
  const [selectedSource, setSelectedSource] = useState<string>("");
  const selectedSourceRef = useRef(selectedSource);
  selectedSourceRef.current = selectedSource;
  const [tab, setTab] = useState<Tab>("overview");
  const [navCollapsed, setNavCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(NAV_COLLAPSED_KEY) === "1";
    } catch {
      return false;
    }
  });
  // The top bar lives in App.tsx; the global search trigger is owned here and is
  // portaled into the slot the shell reserves. The case name deliberately stays
  // an h1 in the workspace (one instance only — the e2e suite matches it by text).
  const [searchSlot, setSearchSlot] = useState<HTMLElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadFileName, setUploadFileName] = useState<string | null>(null);
  const [job, setJob] = useState<IngestJob | null>(null);
  const [hostname, setHostname] = useState("");
  const [platform, setPlatform] = useState("unknown");
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [focusTimeline, setFocusTimeline] = useState<TimelineEvent | null>(null);
  const [focusPath, setFocusPath] = useState<string | null>(null);
  const [focusEntity, setFocusEntity] = useState<Entity | null>(null);
  const [stats, setStats] = useState<SourceStats | null>(null);
  const [timelineSigmaOnly, setTimelineSigmaOnly] = useState(false);
  const [timelineState, setTimelineState] = useState<"loading" | "error" | "empty" | "ready">("loading");
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [hashInfo, setHashInfo] = useState<EvidenceHashes | null>(null);
  const [hashingSourceIds, setHashingSourceIds] = useState<Set<string>>(() => new Set());
  const [yaraSourceIds, setYaraSourceIds] = useState<Set<string>>(() => new Set());
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [detections, setDetections] = useState<SigmaDetection[]>([]);
  /** Rule id handed from the Overview top-detections table to the Detections view. */
  const [detectionFocus, setDetectionFocus] = useState<string | null>(null);
  const [sourceInfoOpen, setSourceInfoOpen] = useState(false);
  const [sourceInfo, setSourceInfo] = useState<EvidenceSource | null>(null);
  const [sourceInfoHash, setSourceInfoHash] = useState<EvidenceHashes | null>(null);
  const [ingestHistoryOpen, setIngestHistoryOpen] = useState(false);
  const [ingestHistoryLoading, setIngestHistoryLoading] = useState(false);
  const [ingestHistoryBySource, setIngestHistoryBySource] = useState<Record<string, IngestJob[]>>({});
  const closeSourceInfo = useCallback(() => setSourceInfoOpen(false), []);
  const closeIngestHistory = useCallback(() => setIngestHistoryOpen(false), []);

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
          setLoadError(null);
          setCaseData(c);
          setSources(s);
          if (opts?.selectSourceId) {
            setSelectedSource(opts.selectSourceId);
          } else if (s.length && !selectedSource) {
            setSelectedSource(s[0].id);
          }
        })
        .catch((e) => setLoadError(String(e)));
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
    setTimelineState("loading");
    // Switching the active source invalidates every investigation view, so send
    // them back to Overview. Sources is the one view that is about the sources
    // themselves: switching cards there must not eject the analyst mid-action.
    setTab((current) => (current === "sources" ? current : "overview"));
  }, [selectedSource]);

  // MFT/Browser are only meaningful when the source produced those artifacts.
  // If the counts land as zero while the view is open, fall back to Overview.
  useEffect(() => {
    if (tab === "mft" && stats && stats.mft_count === 0) {
      setTab("overview");
    }
    if (tab === "browser" && stats && stats.browser_count === 0) {
      setTab("overview");
    }
  }, [tab, stats]);

  // Investigation views need a completed source; bounce back to Sources while
  // the case is still ingesting (or has no evidence at all yet), then return to
  // Overview once the evidence is ready so the wait ends on the right screen.
  const parkedOnSourcesRef = useRef(false);
  useEffect(() => {
    if (!canInvestigate) {
      if (INVESTIGATION_TABS.has(tab)) {
        parkedOnSourcesRef.current = true;
        setTab("sources");
      }
      return;
    }
    if (parkedOnSourcesRef.current) {
      parkedOnSourcesRef.current = false;
      if (tab === "sources") setTab("overview");
    }
  }, [canInvestigate, tab]);

  useEffect(() => {
    try {
      window.localStorage.setItem(NAV_COLLAPSED_KEY, navCollapsed ? "1" : "0");
    } catch {
      // storage unavailable (private mode); collapse stays session-only
    }
  }, [navCollapsed]);

  useEffect(() => {
    setSearchSlot(document.getElementById("header-search-slot"));
  }, [caseId]);

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
    setUploadError(null);
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
      setUploadError(String(err));
      setUploadFileName(null);
    } finally {
      setUploading(false);
    }
  };

  const cancelProcessing = async () => {
    if (!job || !isActiveJob(job)) return;
    setConfirmAction({ kind: "cancel", jobId: job.id });
  };

  const doCancelProcessing = async (jobId: string) => {
    try {
      const updated = await api.cancelJob(jobId);
      setJob(updated);
      if (caseId) {
        load({ selectSourceId: updated.evidence_source_id });
      }
    } catch (err) {
      setError(String(err));
    }
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

  // Source details are reachable from two places (context-bar ⓘ and the Sources
  // cards); both go through here so the dialog always gets fresh hash state.
  const openSourceDetails = (s: EvidenceSource) => {
    setSelectedSource(s.id);
    setSourceInfo(s);
    setSourceInfoOpen(true);
    setSourceInfoHash(null);
    if (!caseId) return;
    api
      .getEvidenceHashes(caseId, s.id)
      .then(setSourceInfoHash)
      .catch(() => setSourceInfoHash(null));
  };

  if (!caseId) return null;

  return (
    <div className={`case-workspace${navCollapsed ? " nav-collapsed" : ""}`}>
      <CaseNav
        active={tab}
        onSelect={(next) => {
          if (next !== "timeline") setTimelineSigmaOnly(false);
          setTab(next);
        }}
        detectionCount={detections.length}
        topSeverity={detections.length ? (topSeverity(detections) as SeverityLevel) : null}
        sourceCount={sources.length}
        hasActiveJob={isActiveJob(job)}
        mftCount={stats?.mft_count ?? 0}
        browserCount={stats?.browser_count ?? 0}
        collapsed={navCollapsed}
        onToggleCollapsed={() => setNavCollapsed((v) => !v)}
      />

      <div className="case-main">
        <div className="context-bar">
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

          {sources.length > 0 ? (
            <div className="context-source">
              <select
                className="context-source-select"
                aria-label="Active evidence source"
                value={selectedSource}
                onChange={(e) => setSelectedSource(e.target.value)}
              >
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.hostname} ({sourcePlatformLabel(s.platform)})
                  </option>
                ))}
              </select>
              {selectedSourceData && (
                <>
                  <span className={`status-badge ${selectedSourceData.status}`}>
                    {selectedSourceData.status}
                  </span>
                  <button
                    type="button"
                    className="ghost context-source-info"
                    aria-label="Source details"
                    title="Source details"
                    onClick={() => openSourceDetails(selectedSourceData)}
                  >
                    ⓘ
                  </button>
                </>
              )}
              {stats && (
                <span className="context-stat mono">
                  {formatCompactStat(stats.timeline_count)} events
                </span>
              )}
            </div>
          ) : (
            <div className="context-source">
              <span className="context-stat">
                No evidence —{" "}
                <button type="button" className="link-button" onClick={() => setTab("sources")}>
                  upload in Sources
                </button>
              </span>
            </div>
          )}
        </div>

        {(loadError || error) && <div className="alert alert-error">{loadError || error}</div>}

        {showIngestStatus && (
          <IngestStatusPanel
            phase={uploading ? "uploading" : "ingesting"}
            job={uploading ? null : job}
            fileName={uploadFileName}
          />
        )}

        {tab === "sources" && (
          <SourcesView
            caseId={caseId}
            sources={sources}
            selectedSource={selectedSource}
            stats={stats}
            job={job}
            uploading={uploading}
            uploadError={uploadError}
            loadError={loadError}
            hostname={hostname}
            platform={platform}
            hashInfo={hashInfo}
            hashingSourceIds={hashingSourceIds}
            yaraSourceIds={yaraSourceIds}
            onHostnameChange={setHostname}
            onPlatformChange={setPlatform}
            onDismissUploadError={() => setUploadError(null)}
            onUploadFile={handleUploadFile}
            onOpenSource={openSourceDetails}
            onOpenIngestHistory={openIngestHistory}
            onCancelProcessing={cancelProcessing}
            onHash={(sourceId) => setConfirmAction({ kind: "hash", sourceId })}
            onYara={(sourceId) => setConfirmAction({ kind: "yara", sourceId })}
          />
        )}

        {tab !== "sources" && canInvestigate ? (
          <>
            {stats && selectedSourceData?.status === "completed" && !showIngestStatus && (
              <div className="panel">
                <h2>Findings</h2>
                <CountsStrip
                  stats={stats}
                  timelineState={timelineState}
                  isActive={statCardActive}
                  onPivot={pivotToStat}
                />
              </div>
            )}

            {tab === "overview" && stats && selectedSourceData && (
              <OverviewView
                source={selectedSourceData}
                sources={sources}
                selectedSource={selectedSource}
                stats={stats}
                detections={detections}
                timelineState={timelineState}
                onSelectSource={(s) => {
                  setSelectedSource(s.id);
                  setTab("timeline");
                }}
                onOpenDetection={(d) => {
                  setDetectionFocus(d.rule_id);
                  setTab("detections");
                }}
              />
            )}

            {tab === "detections" && (
              <SigmaFindingsPanel
                caseId={caseId}
                sourceId={selectedSource}
                detections={detections}
                focusRuleId={detectionFocus}
                onFocusConsumed={() => setDetectionFocus(null)}
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
            )}

            {/* Search is a shell-level affordance (plan §2): it renders into the
                top bar slot when the shell is mounted, and falls back to inline
                so the view still works if the slot is missing. */}
            {(() => {
              const search = (
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
              );
              return searchSlot ? createPortal(search, searchSlot) : search;
            })()}


            {tab === "timeline" && (
              <TimelineView
                caseId={caseId}
                sourceId={selectedSource}
                focusEvent={focusTimeline}
                eventTypes={stats?.event_types ?? []}
                sigmaOnly={timelineSigmaOnly}
                onSigmaOnlyChange={setTimelineSigmaOnly}
                onLoadStateChange={setTimelineState}
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
        ) : tab !== "sources" && !showIngestStatus ? (
          <div className="empty-state">
            <div className="empty-state-icon">↑</div>
            <p>Add evidence in the Sources view to begin investigation.</p>
            <button type="button" className="secondary" onClick={() => setTab("sources")}>
              Go to Sources
            </button>
          </div>
        ) : null}
      </div>
      <Drawer
        open={sourceInfoOpen && sourceInfo !== null}
        onClose={closeSourceInfo}
        title="Evidence source details"
      >
        {sourceInfo && (
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
        )}
      </Drawer>
      <Drawer
        open={ingestHistoryOpen}
        onClose={closeIngestHistory}
        title="Ingest history"
        width="min(46rem, 92vw)"
      >
        {ingestHistoryLoading ? (
          <p className="panel-desc" style={{ marginTop: 0 }}>Loading history…</p>
        ) : (
          <div style={{ display: "grid", gap: "0.75rem" }}>
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
                      {jobs.slice(0, 20).map((j) => {
                        const displayStatus = jobDisplayStatus(j);
                        return <li key={j.id} className="job-history-item">
                          <span className={`status-badge ${displayStatus.status}`}>{displayStatus.label}</span>
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
                        </li>;
                      })}
                    </ul>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </Drawer>

            <ConfirmDialog
              open={confirmAction !== null}
              title={
                confirmAction?.kind === "cancel"
                  ? "Cancel processing"
                  : confirmAction?.kind === "hash"
                  ? "Hash all evidence files"
                  : "Scan evidence with YARA"
              }
              message={
                confirmAction?.kind === "cancel"
                  ? "Cancel current evidence processing?"
                  : confirmAction?.kind === "hash"
                  ? "This will hash all files in the evidence package using SHA256, SHA1, and MD5. It can take a while on large collections and will use worker resources. Continue?"
                  : "This runs YARA across evidence files using the signature-base default ruleset. It can take time on large collections. Continue?"
              }
              confirmLabel="Continue"
              onCancel={() => setConfirmAction(null)}
              onConfirm={() => {
                const action = confirmAction;
                setConfirmAction(null);
                if (action?.kind === "cancel") {
                  void doCancelProcessing(action.jobId);
                } else if (action?.kind === "hash") {
                  setHashingSourceIds((ids) => new Set(ids).add(action.sourceId));
                  api
                    .computeFileHashes(caseId, action.sourceId)
                    .then(() => {
                      if (selectedSourceRef.current === action.sourceId) {
                        setHashInfo((h) => (h ? { ...h, hash_status: "running" } : h));
                      }
                    })
                    .catch((e) => setError(String(e)))
                    .finally(() =>
                      setHashingSourceIds((ids) => {
                        const next = new Set(ids);
                        next.delete(action.sourceId);
                        return next;
                      })
                    );
                } else if (action?.kind === "yara") {
                  setYaraSourceIds((ids) => new Set(ids).add(action.sourceId));
                  api
                    .computeYaraScan(caseId, action.sourceId)
                    .then(() => {
                      if (selectedSourceRef.current === action.sourceId) {
                        setHashInfo((h) => (h ? { ...h, yara_status: "running" } : h));
                      }
                    })
                    .catch((e) => setError(String(e)))
                    .finally(() =>
                      setYaraSourceIds((ids) => {
                        const next = new Set(ids);
                        next.delete(action.sourceId);
                        return next;
                      })
                    );
                }
              }}
            />
    </div>
  );
}
