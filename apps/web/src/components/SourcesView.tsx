import { ChangeEvent, useRef, useState } from "react";
import { api, EvidenceHashes, EvidenceSource, IngestJob, SourceStats } from "../api/client";
import {
  formatCompactStat,
  isActiveJob,
  jobDisplayStatus,
  sourceCollectorLabel,
  sourcePlatformLabel,
} from "../lib/caseFormat";

/**
 * Sources view (plan §6.8): the evidence inventory. A real table of sources —
 * hostname, platform, collector, status, counts, ingested at, row actions —
 * with the ingest dropzone parked in a fixed right rail so uploading never
 * competes with reviewing what is already in the case.
 *
 * Pure extraction from CaseDetailPage plus the §6.8 restyle: no ingest,
 * hashing, YARA or selection logic changed. Manifest reference data moved to
 * the source Info drawer (it was duplicated there already); the row keeps the
 * accessible name `<hostname> <platform> <status>` that the drawer opener and
 * the e2e suite rely on.
 */

type Props = {
  caseId: string;
  sources: EvidenceSource[];
  selectedSource: string;
  stats: SourceStats | null;
  job: IngestJob | null;
  uploading: boolean;
  uploadError: string | null;
  loadError: string | null;
  hostname: string;
  platform: string;
  hashInfo: EvidenceHashes | null;
  hashingSourceIds: Set<string>;
  yaraSourceIds: Set<string>;
  onHostnameChange: (value: string) => void;
  onPlatformChange: (value: string) => void;
  onDismissUploadError: () => void;
  onUploadFile: (file: File) => Promise<void>;
  onOpenSource: (source: EvidenceSource) => void;
  onOpenIngestHistory: () => void;
  onCancelProcessing: () => void;
  onHash: (sourceId: string) => void;
  onYara: (sourceId: string) => void;
};

function formatIngestedAt(source: EvidenceSource): string {
  const raw = source.processing_finished_at ?? source.created_at;
  if (!raw) return "—";
  const at = new Date(raw);
  if (Number.isNaN(at.getTime())) return "—";
  return at.toLocaleString();
}

export default function SourcesView({
  caseId,
  sources,
  selectedSource,
  stats,
  job,
  uploading,
  uploadError,
  loadError,
  hostname,
  platform,
  hashInfo,
  hashingSourceIds,
  yaraSourceIds,
  onHostnameChange,
  onPlatformChange,
  onDismissUploadError,
  onUploadFile,
  onOpenSource,
  onOpenIngestHistory,
  onCancelProcessing,
  onHash,
  onYara,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const uploadBusy = uploading || isActiveJob(job);

  const onUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await onUploadFile(file);
    e.target.value = "";
  };

  return (
    <section className="sources-view" aria-label="Evidence sources">
      <div className="sources-view-main">
        <div className="panel">
          <div className="sources-panel-head">
            <h2>Evidence sources</h2>
            {sources.length > 0 && (
              <button type="button" className="secondary" onClick={onOpenIngestHistory}>
                View ingest history
              </button>
            )}
          </div>

          {sources.length === 0 ? (
            <p className="panel-desc" style={{ margin: 0 }}>No evidence uploaded yet.</p>
          ) : (
            <div className="data-table-wrap sources-table-wrap">
              <table className="data-table sources-table">
                <thead>
                  <tr>
                    <th scope="col">Host</th>
                    <th scope="col">Platform</th>
                    <th scope="col">Collector</th>
                    <th scope="col">Status</th>
                    <th scope="col" className="num-col">Events</th>
                    <th scope="col">Ingested</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((s) => {
                    const selected = selectedSource === s.id;
                    return (
                      <tr
                        key={s.id}
                        className={`clickable${selected ? " selected" : ""}`}
                        onClick={() => onOpenSource(s)}
                      >
                        <td>
                          <button
                            type="button"
                            className="link-button source-row-open"
                            aria-label={`${s.hostname} ${sourcePlatformLabel(s.platform)} ${s.status}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              onOpenSource(s);
                            }}
                          >
                            {s.hostname}
                          </button>
                        </td>
                        <td>{sourcePlatformLabel(s.platform)}</td>
                        <td className="mono" title={sourceCollectorLabel(s.collector)}>
                          {sourceCollectorLabel(s.collector)}
                        </td>
                        <td>
                          <span className={`status-badge ${s.status}`}>{s.status}</span>
                        </td>
                        <td className="num-col mono">
                          {selected && stats ? formatCompactStat(stats.timeline_count) : "—"}
                        </td>
                        <td className="mono" title={formatIngestedAt(s)}>{formatIngestedAt(s)}</td>
                        <td>
                          <div
                            className="source-row-actions"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              type="button"
                              className="secondary"
                              onClick={() => onOpenSource(s)}
                            >
                              Details
                            </button>
                            {selected && s.status === "completed" && hashInfo && (
                              <>
                                {hashInfo.hash_status === "complete" ? (
                                  <>
                                    <span className="mono source-row-note">
                                      {hashInfo.hashed_files_in_db.toLocaleString()} files hashed
                                    </span>
                                    <a
                                      href={api.evidenceHashExportUrl(caseId, s.id)}
                                      className="secondary"
                                      download
                                    >
                                      Export hashes
                                    </a>
                                  </>
                                ) : hashInfo.hash_status === "running" ? (
                                  <span className="mono source-row-note">Hashing files…</span>
                                ) : (
                                  <button
                                    type="button"
                                    className="secondary"
                                    disabled={hashingSourceIds.has(s.id)}
                                    onClick={() => onHash(s.id)}
                                  >
                                    {hashingSourceIds.has(s.id) ? "Starting…" : "Hash all evidence files"}
                                  </button>
                                )}
                                {hashInfo.yara_status === "running" ? (
                                  <span className="mono source-row-note">YARA scanning…</span>
                                ) : hashInfo.yara_status === "complete" ? (
                                  <span className="mono source-row-note">
                                    {(hashInfo.yara_match_count ?? 0).toLocaleString()} YARA rules matched across{" "}
                                    {(hashInfo.yara_file_count ?? 0).toLocaleString()} files
                                  </span>
                                ) : (
                                  <button
                                    type="button"
                                    className="secondary"
                                    disabled={yaraSourceIds.has(s.id)}
                                    onClick={() => onYara(s.id)}
                                  >
                                    {yaraSourceIds.has(s.id) ? "Starting…" : "Scan evidence with YARA"}
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <aside className="sources-view-rail" aria-label="Ingest evidence">
        <div className="panel">
          <h2>Ingest evidence</h2>
          <p className="panel-desc">
            Upload a ZIP archive or individual files — EVTX logs, $MFT, registry hives, Chromium profiles, CSV exports, and more.
          </p>
          {loadError && (
            <p className="panel-desc">Evidence controls are unavailable until case data loads.</p>
          )}
          {uploadError && (
            <div className="alert alert-error">
              {uploadError}
              <button type="button" className="secondary" onClick={onDismissUploadError}>
                Try another file
              </button>
            </div>
          )}
          {!loadError && !uploadError && (
            <div className="upload-zone">
              <div
                className={`upload-drop-hint${dragActive ? " is-dragover" : ""}${uploadBusy ? " is-disabled" : ""}`}
                role="button"
                tabIndex={uploadBusy ? -1 : 0}
                aria-label="Drop evidence files or click to select"
                onClick={() => {
                  if (uploadBusy) return;
                  fileInputRef.current?.click();
                }}
                onKeyDown={(e) => {
                  if (uploadBusy) return;
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                onDragEnter={(e) => {
                  e.preventDefault();
                  if (uploadBusy) return;
                  setDragActive(true);
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (uploadBusy) return;
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
                  if (uploadBusy) return;
                  const file = e.dataTransfer.files?.[0];
                  if (!file) return;
                  await onUploadFile(file);
                }}
              >
                {uploading ? "Uploading…" : "Select files or a ZIP archive"}
              </div>
              <div className="upload-actions">
                <input
                  placeholder="Hostname override"
                  value={hostname}
                  onChange={(e) => onHostnameChange(e.target.value)}
                  aria-label="Hostname override"
                  disabled={uploadBusy}
                />
                <select
                  value={platform}
                  onChange={(e) => onPlatformChange(e.target.value)}
                  aria-label="Evidence platform"
                  disabled={uploadBusy}
                >
                  <option value="unknown">Auto platform</option>
                  <option value="windows">Windows</option>
                  <option value="macos">macOS</option>
                  <option value="linux">Linux</option>
                  <option value="memory">Memory</option>
                  <option value="disk">Disk image (E01/RAW)</option>
                </select>
                <input
                  ref={fileInputRef}
                  type="file"
                  style={{ display: "none" }}
                  onChange={onUpload}
                  disabled={uploadBusy}
                />
              </div>
            </div>
          )}
          {job && !uploading && (
            <div className="ingest-status-compact">
              <div className="job-status-line">
                <span className={`status-badge ${jobDisplayStatus(job).status}`}>
                  {jobDisplayStatus(job).label}
                </span>
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
                  onClick={onCancelProcessing}
                >
                  Cancel processing
                </button>
              )}
            </div>
          )}
        </div>
      </aside>
    </section>
  );
}
