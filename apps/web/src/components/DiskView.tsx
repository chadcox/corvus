import { useEffect, useState } from "react";
import { api, FileHashes, FilePreview, FilesystemNode } from "../api/client";
import ResizableSplit from "./ResizableSplit";

type Props = { caseId: string; sourceId: string; focusPath?: string | null };

function fmtSize(n: number | null): string {
  if (n == null) return "—";
  if (n === 0) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function DiskView({ caseId, sourceId, focusPath }: Props) {
  const [path, setPath] = useState<string | null>(null);
  const [nodes, setNodes] = useState<FilesystemNode[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<FilesystemNode | null>(null);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [fileHashes, setFileHashes] = useState<FileHashes | null>(null);
  const [fileHashesLoading, setFileHashesLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewOffset, setPreviewOffset] = useState(0);

  useEffect(() => {
    if (focusPath) {
      setSearch(focusPath);
      setPath(null);
      setSelected(null);
      setPreview(null);
      setFileHashes(null);
      setPreviewError(null);
      setPreviewOffset(0);
    }
  }, [focusPath]);

  useEffect(() => {
    setLoading(true);
    setSelected(null);
    setPreview(null);
    setFileHashes(null);
    setPreviewError(null);
    setPreviewOffset(0);
    const req = search.trim()
      ? api.searchFilesystem(caseId, sourceId, search.trim())
      : api.listFilesystem(caseId, sourceId, path);
    req
      .then(setNodes)
      .catch(() => setNodes([]))
      .finally(() => setLoading(false));
  }, [caseId, sourceId, path, search]);

  const breadcrumbs = path ? path.split("/").filter(Boolean) : [];

  useEffect(() => {
    if (!selected || selected.is_directory) {
      setPreview(null);
      setFileHashes(null);
      setPreviewError(null);
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    api
      .getFilesystemFilePreview(caseId, sourceId, selected.id, { offset: previewOffset, length: 512 })
      .then(setPreview)
      .catch((e) => {
        setPreview(null);
        setPreviewError(String(e));
      })
      .finally(() => setPreviewLoading(false));

    setFileHashesLoading(true);
    api
      .getFilesystemFileHashes(caseId, sourceId, selected.id)
      .then(setFileHashes)
      .catch(() => setFileHashes(null))
      .finally(() => setFileHashesLoading(false));
  }, [caseId, sourceId, selected, previewOffset]);

  const handleRowClick = (n: FilesystemNode) => {
    setSelected(n);
    setPreview(null);
    setFileHashes(null);
    setPreviewError(null);
    setPreviewOffset(0);
    if (n.is_directory) {
      setPath(n.full_path);
      setSearch("");
    }
  };

  return (
    <div className="animate-in animate-in-delay-3">
      <ResizableSplit
        className="disk-workspace"
        left={<div className="panel disk-browser-panel">
        <h2>Disk</h2>
        <p className="panel-desc">Logical filesystem from collected directory trees and artifact file paths.</p>

        <div className="disk-toolbar">
          <div className="breadcrumb-trail">
            <button type="button" className="secondary" onClick={() => { setPath(null); setSearch(""); setSelected(null); }}>
              /
            </button>
            {breadcrumbs.map((part, i) => {
              const sub = "/" + breadcrumbs.slice(0, i + 1).join("/");
              return (
                <button
                  key={sub}
                  type="button"
                  className="secondary"
                  onClick={() => { setPath(sub); setSearch(""); setSelected(null); }}
                >
                  {part}
                </button>
              );
            })}
          </div>
          <input
            placeholder="Search paths…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search filesystem paths"
          />
        </div>

        {loading && <p className="loading-text">Loading filesystem…</p>}
        {!loading && nodes.length === 0 && !search.trim() && (
          <div className="detail-empty">
            No entries at this path. Navigate from root (/) or search for a file path.
          </div>
        )}
        {!loading && nodes.length === 0 && search.trim() && (
          <div className="detail-empty">No paths matching &quot;{search.trim()}&quot;.</div>
        )}

        {!loading && nodes.length > 0 && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Size</th>
                  <th>Path</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((n) => (
                  <tr
                    key={n.id}
                    className={`clickable${selected?.id === n.id ? " disk-row-selected" : ""}`}
                    onClick={() => handleRowClick(n)}
                  >
                    <td>
                      <span className="data-table-name" title={n.name}>
                        <span className="file-icon">{n.is_directory ? "▸" : "·"}</span>
                        {n.name}
                      </span>
                    </td>
                    <td className="mono">{n.is_directory ? "—" : fmtSize(n.size)}</td>
                    <td className="mono path-col" title={n.full_path}>{n.full_path}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>}
        right={<div className="panel disk-detail-panel">
        <h2>Details</h2>
        {!selected ? (
          <div className="detail-empty">Click a file or directory to inspect its properties.</div>
        ) : (
          <div className="disk-detail-inner">
            <div className="disk-detail-name">
              <span className="file-icon" style={{ fontSize: "1.2rem" }}>{selected.is_directory ? "▸" : "·"}</span>
              {selected.name}
            </div>

            <dl className="disk-detail-attrs">
              <dt>Type</dt>
              <dd>{selected.is_directory ? "Directory" : "File"}</dd>

              <dt>Full path</dt>
              <dd className="mono disk-detail-path">{selected.full_path}</dd>

              {selected.parent_path && (
                <>
                  <dt>Parent</dt>
                  <dd className="mono">{selected.parent_path}</dd>
                </>
              )}

              {!selected.is_directory && (
                <>
                  <dt>Size</dt>
                  <dd className="mono">{fmtSize(selected.size)}{selected.size != null ? ` (${selected.size.toLocaleString()} bytes)` : ""}</dd>
                </>
              )}

              {!selected.is_directory && (
                <>
                  <dt>SHA256</dt>
                  <dd className="mono">
                    {fileHashesLoading ? "Loading…" : (fileHashes?.sha256 ?? "n/a")}
                  </dd>
                  <dt>SHA1</dt>
                  <dd className="mono">
                    {fileHashesLoading ? "Loading…" : (fileHashes?.sha1 ?? "n/a")}
                  </dd>
                  <dt>MD5</dt>
                  <dd className="mono">
                    {fileHashesLoading ? "Loading…" : (fileHashes?.md5 ?? "n/a")}
                  </dd>
                </>
              )}

              <dt>Status</dt>
              <dd className={selected.is_deleted ? "disk-deleted" : ""}>
                {selected.is_deleted ? "Deleted / unlinked" : "Present"}
              </dd>
            </dl>

            {!selected.is_directory && selected.parent_path && (
              <button
                type="button"
                className="secondary"
                style={{ marginTop: "0.75rem", width: "100%", fontSize: "0.75rem" }}
                onClick={() => { setPath(selected.parent_path!); setSearch(""); }}
              >
                Navigate to parent directory
              </button>
            )}

            {!selected.is_directory && (
              <button
                type="button"
                className="secondary"
                style={{ marginTop: "0.45rem", width: "100%", fontSize: "0.75rem", textAlign: "center", padding: "0.36rem 0.5rem" }}
                onClick={() => {
                  const ok = window.confirm(
                    `Warning: This file may contain malware or other harmful content.\n\n` +
                    `Only download to a controlled forensic analysis environment.\n\n` +
                    `Do you want to continue downloading "${selected.name}"?`
                  );
                  if (!ok) return;
                  window.location.href = api.filesystemFileDownloadUrl(caseId, sourceId, selected.id);
                }}
              >
                Download file
              </button>
            )}

            {!selected.is_directory && (
              <div className="disk-preview-panel">
                <div className="disk-preview-head">
                  <strong>Hex / ASCII preview</strong>
                  <div className="disk-preview-nav">
                    <button
                      type="button"
                      className="secondary"
                      disabled={previewLoading || previewOffset <= 0}
                      onClick={() => setPreviewOffset((v) => Math.max(0, v - 512))}
                    >
                      Prev
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={previewLoading || !preview?.truncated}
                      onClick={() => setPreviewOffset((v) => v + 512)}
                    >
                      Next
                    </button>
                  </div>
                </div>
                {previewLoading && <p className="loading-text" style={{ margin: "0.35rem 0 0" }}>Loading preview…</p>}
                {previewError && !previewLoading && (
                  <p className="panel-desc" style={{ margin: "0.35rem 0 0", color: "var(--danger)" }}>{previewError}</p>
                )}
                {preview && !previewLoading && (
                  <>
                    <p className="mono" style={{ margin: "0.35rem 0 0.5rem", color: "var(--muted)" }}>
                      Offset {preview.offset.toLocaleString()} · Showing {preview.length.toLocaleString()} of {preview.file_size.toLocaleString()} bytes
                    </p>
                    <div className="disk-preview-grid">
                      <pre className="disk-preview-block mono">{preview.hex || "(empty)"}</pre>
                      <pre className="disk-preview-block mono">{preview.ascii || "(empty)"}</pre>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>}
      />
    </div>
  );
}
