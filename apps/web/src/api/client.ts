const API_BASE = (() => {
  const configured = import.meta.env.VITE_API_URL?.trim();
  if (!configured) {
    return "";
  }
  try {
    const parsed = new URL(configured);
    if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
      // In containerized/remote browser sessions, localhost often points to the wrong machine.
      return "";
    }
  } catch {
    // Keep non-URL values (for example empty-relative paths).
  }
  return configured.replace(/\/$/, "");
})();
const AUTH_TOKEN_KEY = "ff_auth_token";

export class ApiAuthError extends Error {}

export function getAuthToken(): string | null {
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string | null): void {
  if (!token) {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
    return;
  }
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export type Case = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  evidence_source_count: number;
};

export type EvidenceSource = {
  id: string;
  case_id: string;
  hostname: string;
  collector: string;
  collector_version: string | null;
  source_type: string;
  platform: string;
  os_version: string | null;
  architecture: string | null;
  timezone: string | null;
  collected_at: string | null;
  package_path: string;
  uploaded_filename: string | null;
  status: string;
  manifest: Record<string, unknown> | null;
  created_at: string;
  processing_started_at: string | null;
  processing_finished_at: string | null;
  total_processing_seconds: number | null;
  latest_job_id: string | null;
};

export type IngestJob = {
  id: string;
  evidence_source_id: string;
  status: string;
  progress: number;
  message: string | null;
  error_code?: string | null;
  error_stage?: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type SigmaHit = {
  rule_id: string;
  title: string;
  level: string;
  engine?: string;
};

export type TimelineEvent = {
  id: string;
  evidence_source_id: string;
  timestamp_utc: string;
  event_type: string;
  summary: string;
  artifact_type: string | null;
  original_source: string | null;
  data: Record<string, unknown>;
  entity_refs: string[];
  sigma_hits: SigmaHit[];
};

export type SigmaRulesStatus = {
  state: string;
  rule_count: number;
  ref: string;
  updated_at: string | null;
  message: string | null;
  task_id: string | null;
  refresh_interval_hours: number;
};

export type SigmaDetection = {
  id: string;
  evidence_source_id: string;
  engine?: string;
  rule_id: string;
  title: string;
  level: string;
  description: string | null;
  rule_definition?: string | null;
  tags: string[];
  match_count: number;
  sample_event_ids: string[];
  created_at: string;
};

export type FilesystemNode = {
  id: string;
  evidence_source_id: string;
  full_path: string;
  name: string;
  is_directory: boolean;
  size: number | null;
  is_deleted: boolean;
  parent_path: string | null;
};

export type FilePreview = {
  node_id: string;
  name: string;
  full_path: string;
  offset: number;
  length: number;
  file_size: number;
  truncated: boolean;
  hex: string;
  ascii: string;
};

export type FileHashes = {
  node_id: string;
  relative_path: string;
  sha256: string | null;
  sha1: string | null;
  md5: string | null;
  available: boolean;
};

export type EvidenceHashes = {
  sha256: string | null;
  sha1: string | null;
  md5: string | null;
  hash_status: string | null;
  hash_file_count: number | null;
  hashed_files_in_db: number;
  yara_status: string | null;
  yara_match_count: number | null;
  yara_file_count: number | null;
};

export type Entity = {
  id: string;
  evidence_source_id: string;
  entity_type: string;
  display_name: string;
  attributes: Record<string, unknown>;
};

export type GlobalSearchResult = {
  query: string;
  timeline: TimelineEvent[];
  filesystem: FilesystemNode[];
  entities: Entity[];
  total: number;
};

export type SourceStats = {
  timeline_count: number;
  filesystem_count: number;
  entity_count: number;
  sigma_detection_count: number;
  mft_count: number;
  browser_count: number;
  event_types: string[];
};

export type TimelineHistogram = {
  buckets: { ts: string; count: number }[];
  total: number;
  granularity: string;
};

export type SystemStatus = {
  hostname: string;
  cpu_usage_percent: number | null;
  memory_used_bytes: number | null;
  memory_total_bytes: number | null;
  disk_used_bytes: number | null;
  disk_total_bytes: number | null;
  jobs: {
    running: number;
    queued: number;
    completed: number;
    failed: number;
  };
};

export type AdminOverview = {
  readiness: Record<string, unknown>;
  table_counts: {
    cases: number;
    evidence_sources: number;
    ingest_jobs: number;
    timeline_events: number;
    filesystem_nodes: number;
    entities: number;
    relations: number;
    sigma_detections: number;
  };
  jobs_by_status: Record<string, number>;
  evidence_by_status: Record<string, number>;
  disk: {
    path: string;
    total_bytes: number | null;
    used_bytes: number | null;
    free_bytes: number | null;
    error: string | null;
  };
  sigma_rules: SigmaRulesStatus;
  feature_flags: {
    enable_validation_api: boolean;
    enable_admin_api: boolean;
  };
};

export type ChainsawRulesStatus = {
  state: string;
  rule_count: number;
  mapping_count: number;
  binary_available: boolean;
  chainsaw_version: string | null;
  ref: string;
  updated_at: string | null;
  message: string | null;
  task_id: string | null;
  include_sigma_in_hunt: boolean;
};

export type DetectionRulesStatus = {
  sigma: SigmaRulesStatus;
  chainsaw: ChainsawRulesStatus;
};

export type YaraRulesStatus = {
  state: string;
  rule_count: number;
  updated_at: string | null;
  message: string | null;
  task_id: string | null;
};

export type AdminJob = {
  id: string;
  evidence_source_id: string;
  case_id: string;
  case_name: string;
  hostname: string;
  status: string;
  progress: number;
  message: string | null;
  error_code?: string | null;
  error_stage?: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ProjectContainer = {
  id: string;
  name: string;
  service: string | null;
  image: string;
  state: string;
  status: string;
  health: string | null;
};

export type AuthUser = {
  id: string;
  username: string;
  role: "administrator" | "analyst";
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

function parseApiError(body: string, statusText: string): string {
  try {
    const data = JSON.parse(body) as { detail?: string | { msg: string }[] };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail) && data.detail[0]?.msg) return data.detail[0].msg;
  } catch {
    /* not JSON */
  }
  return body || statusText;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  const token = getAuthToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(
      msg === "Failed to fetch"
        ? `Cannot reach API at ${API_BASE}. Is the stack running?`
        : msg
    );
  }
  if (!res.ok) {
    const text = await res.text();
    if (res.status === 401) throw new ApiAuthError(parseApiError(text, res.statusText));
    throw new Error(parseApiError(text, res.statusText));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; token_type: string; user: AuthUser }>("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<AuthUser>("/api/v1/auth/me"),
  logout: () => request<{ message: string }>("/api/v1/auth/logout", { method: "POST" }),
  listUsers: () => request<AuthUser[]>("/api/v1/auth/users"),
  createUser: (payload: { username: string; password: string; role: "administrator" | "analyst"; is_active?: boolean }) =>
    request<AuthUser>("/api/v1/auth/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateUserRole: (id: string, role: "administrator" | "analyst") =>
    request<AuthUser>(`/api/v1/auth/users/${id}/role`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    }),
  updateUserActive: (id: string, is_active: boolean) =>
    request<AuthUser>(`/api/v1/auth/users/${id}/active`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active }),
    }),
  resetUserPassword: (id: string, password: string) =>
    request<AuthUser>(`/api/v1/auth/users/${id}/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    }),
  listCases: () => request<Case[]>("/api/v1/cases"),
  createCase: (name: string, description?: string) =>
    request<Case>("/api/v1/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    }),
  getCase: (id: string) => request<Case>(`/api/v1/cases/${id}`),
  renameCase: (id: string, name: string) =>
    request<Case>(`/api/v1/cases/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  deleteCase: (id: string) =>
    request<void>(`/api/v1/cases/${id}`, { method: "DELETE" }),
  listEvidence: (caseId: string) =>
    request<EvidenceSource[]>(`/api/v1/cases/${caseId}/evidence`),
  uploadEvidence: (caseId: string, file: File, hostname?: string, platform?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (hostname) form.append("hostname", hostname);
    if (platform && platform !== "unknown") form.append("platform", platform);
    return request<IngestJob>(`/api/v1/cases/${caseId}/evidence/upload`, {
      method: "POST",
      body: form,
    });
  },
  getJob: (jobId: string) => request<IngestJob>(`/api/v1/jobs/${jobId}`),
  cancelJob: (jobId: string) =>
    request<IngestJob>(`/api/v1/jobs/${jobId}/cancel`, { method: "POST" }),
  listSourceJobs: (caseId: string, sourceId: string) =>
    request<IngestJob[]>(`/api/v1/cases/${caseId}/evidence/${sourceId}/jobs`),
  getTimelineEvent: (caseId: string, sourceId: string, eventId: string) =>
    request<TimelineEvent>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/timeline/events/${eventId}`
    ),
  listSigmaDetections: (caseId: string, sourceId: string) =>
    request<SigmaDetection[]>(`/api/v1/cases/${caseId}/sources/${sourceId}/sigma`),
  getSigmaRulesStatus: () => request<SigmaRulesStatus>("/api/v1/sigma/rules"),
  getChainsawRulesStatus: () => request<ChainsawRulesStatus>("/api/v1/chainsaw/rules"),
  getYaraRulesStatus: () => request<YaraRulesStatus>("/api/v1/yara/rules"),
  getDetectionRulesStatus: () => request<DetectionRulesStatus>("/api/v1/detection-rules"),
  getSystemStatus: () => request<SystemStatus>("/api/v1/system/status"),
  getAdminOverview: () => request<AdminOverview>("/api/v1/admin/overview"),
  refreshSigmaRules: (ref?: string) =>
    request<{ task_id: string; message: string }>(
      `/api/v1/sigma/rules/refresh${ref ? `?ref=${encodeURIComponent(ref)}` : ""}`,
      { method: "POST" }
    ),
  refreshChainsawRules: (ref?: string) =>
    request<{ task_id: string; message: string }>(
      `/api/v1/chainsaw/rules/refresh${ref ? `?ref=${encodeURIComponent(ref)}` : ""}`,
      { method: "POST" }
    ),
  refreshYaraRules: () =>
    request<{ task_id: string; message: string }>(`/api/v1/yara/rules/refresh`, { method: "POST" }),
  listAdminJobs: (opts?: { status?: string; errorCode?: string; errorStage?: string; caseId?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.errorCode) params.set("error_code", opts.errorCode);
    if (opts?.errorStage) params.set("error_stage", opts.errorStage);
    if (opts?.caseId) params.set("case_id", opts.caseId);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<AdminJob[]>(`/api/v1/admin/jobs${qs ? `?${qs}` : ""}`);
  },
  reingestEvidence: (caseId: string, sourceId: string) =>
    request<IngestJob>(`/api/v1/cases/${caseId}/evidence/${sourceId}/reingest`, { method: "POST" }),
  listContainers: () => request<ProjectContainer[]>("/api/v1/admin/containers"),
  startContainer: (name: string) =>
    request<ProjectContainer>(`/api/v1/admin/containers/${encodeURIComponent(name)}/start`, {
      method: "POST",
    }),
  getContainerLogs: (name: string, tail = 400) =>
    request<{ name: string; logs: string }>(
      `/api/v1/admin/containers/${encodeURIComponent(name)}/logs?tail=${tail}`
    ),
  bulkDeleteCases: (caseIds: string[]) =>
    request<{ deleted_cases: number; case_ids: string[]; evidence_dirs_removed: number; orphan_evidence_dirs_removed: number; dry_run: boolean }>(
      "/api/v1/admin/cases/bulk-delete",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_ids: caseIds, confirm: true }),
      }
    ),
  reindexSearch: (opts?: { caseId?: string; sourceId?: string }) => {
    const params = new URLSearchParams();
    if (opts?.caseId) params.set("case_id", opts.caseId);
    if (opts?.sourceId) params.set("source_id", opts.sourceId);
    const qs = params.toString();
    return request<{ sources: number; timeline: number; filesystem: number; entities: number }>(
      `/api/v1/admin/search/reindex${qs ? `?${qs}` : ""}`,
      { method: "POST" }
    );
  },
  listTimeline: (
    caseId: string,
    sourceId: string,
    opts?: {
      q?: string;
      start?: string;
      end?: string;
      eventType?: string;
      artifactType?: string;
      sigmaOnly?: boolean;
      mftOnly?: boolean;
      browserOnly?: boolean;
      browserCategory?: string;
      limit?: number;
      offset?: number;
    }
  ) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.start) params.set("start", opts.start);
    if (opts?.end) params.set("end", opts.end);
    if (opts?.eventType) params.set("event_type", opts.eventType);
    if (opts?.artifactType) params.set("artifact_type", opts.artifactType);
    if (opts?.sigmaOnly) params.set("sigma_only", "true");
    if (opts?.mftOnly) params.set("mft_only", "true");
    if (opts?.browserOnly) params.set("browser_only", "true");
    if (opts?.browserCategory) params.set("browser_category", opts.browserCategory);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    if (opts?.offset != null) params.set("offset", String(opts.offset));
    const qs = params.toString();
    return request<TimelineEvent[]>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/timeline${qs ? `?${qs}` : ""}`
    );
  },
  countTimeline: (
    caseId: string,
    sourceId: string,
    opts?: {
      q?: string;
      start?: string;
      end?: string;
      eventType?: string;
      artifactType?: string;
      sigmaOnly?: boolean;
      mftOnly?: boolean;
      browserOnly?: boolean;
      browserCategory?: string;
    }
  ) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.start) params.set("start", opts.start);
    if (opts?.end) params.set("end", opts.end);
    if (opts?.eventType) params.set("event_type", opts.eventType);
    if (opts?.artifactType) params.set("artifact_type", opts.artifactType);
    if (opts?.sigmaOnly) params.set("sigma_only", "true");
    if (opts?.mftOnly) params.set("mft_only", "true");
    if (opts?.browserOnly) params.set("browser_only", "true");
    if (opts?.browserCategory) params.set("browser_category", opts.browserCategory);
    const qs = params.toString();
    return request<{ count: number }>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/timeline/count${qs ? `?${qs}` : ""}`
    );
  },
  timelineExportUrl: (
    caseId: string,
    sourceId: string,
    opts?: {
      q?: string;
      start?: string;
      end?: string;
      eventType?: string;
      artifactType?: string;
      sigmaOnly?: boolean;
      mftOnly?: boolean;
      browserOnly?: boolean;
      browserCategory?: string;
    }
  ) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.start) params.set("start", opts.start);
    if (opts?.end) params.set("end", opts.end);
    if (opts?.eventType) params.set("event_type", opts.eventType);
    if (opts?.artifactType) params.set("artifact_type", opts.artifactType);
    if (opts?.sigmaOnly) params.set("sigma_only", "true");
    if (opts?.mftOnly) params.set("mft_only", "true");
    if (opts?.browserOnly) params.set("browser_only", "true");
    if (opts?.browserCategory) params.set("browser_category", opts.browserCategory);
    const qs = params.toString();
    return `${API_BASE}/api/v1/cases/${caseId}/sources/${sourceId}/timeline/export${qs ? `?${qs}` : ""}`;
  },
  listFilesystem: (caseId: string, sourceId: string, parentPath?: string | null) => {
    const params = new URLSearchParams();
    if (parentPath != null && parentPath !== "") {
      params.set("parent_path", parentPath);
    }
    const qs = params.toString();
    return request<FilesystemNode[]>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/filesystem${qs ? `?${qs}` : ""}`
    );
  },
  searchFilesystem: (caseId: string, sourceId: string, q: string) =>
    request<FilesystemNode[]>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/filesystem/search?q=${encodeURIComponent(q)}`
    ),
  getFilesystemFilePreview: (
    caseId: string,
    sourceId: string,
    nodeId: string,
    opts?: { offset?: number; length?: number }
  ) => {
    const params = new URLSearchParams();
    if (opts?.offset != null) params.set("offset", String(opts.offset));
    if (opts?.length != null) params.set("length", String(opts.length));
    const qs = params.toString();
    return request<FilePreview>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/filesystem/${nodeId}/preview${qs ? `?${qs}` : ""}`
    );
  },
  getFilesystemFileHashes: (caseId: string, sourceId: string, nodeId: string) =>
    request<FileHashes>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/filesystem/${nodeId}/hashes`
    ),
  filesystemFileDownloadUrl: (caseId: string, sourceId: string, nodeId: string) =>
    `${API_BASE}/api/v1/cases/${caseId}/sources/${sourceId}/filesystem/${nodeId}/download`,
  listEntities: (
    caseId: string,
    sourceId: string,
    opts?: { entityType?: string; q?: string; ids?: string[] }
  ) => {
    const params = new URLSearchParams();
    if (opts?.entityType) params.set("entity_type", opts.entityType);
    if (opts?.q) params.set("q", opts.q);
    opts?.ids?.forEach((id) => params.append("ids", id));
    const qs = params.toString();
    return request<Entity[]>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/entities${qs ? `?${qs}` : ""}`
    );
  },
  listEntityTimeline: (caseId: string, sourceId: string, entityId: string) =>
    request<TimelineEvent[]>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/entities/${entityId}/timeline`
    ),
  globalSearch: (caseId: string, sourceId: string, q: string, limit = 25) =>
    request<GlobalSearchResult>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/search?q=${encodeURIComponent(q)}&limit=${limit}`
    ),
  getSourceStats: (caseId: string, sourceId: string) =>
    request<SourceStats>(`/api/v1/cases/${caseId}/sources/${sourceId}/stats`),
  getEvidenceHashes: (caseId: string, sourceId: string) =>
    request<EvidenceHashes>(
      `/api/v1/cases/${caseId}/evidence/${sourceId}/hashes`
    ),
  computeFileHashes: (caseId: string, sourceId: string) =>
    request<{message: string}>(`/api/v1/cases/${caseId}/evidence/${sourceId}/hashes/compute`, { method: "POST" }),
  computeYaraScan: (caseId: string, sourceId: string) =>
    request<{message: string}>(`/api/v1/cases/${caseId}/evidence/${sourceId}/yara/scan`, { method: "POST" }),
  evidenceHashExportUrl: (caseId: string, sourceId: string) =>
    `${API_BASE}/api/v1/cases/${caseId}/evidence/${sourceId}/hashes/export`,
  getTimelineHistogram: (
    caseId: string,
    sourceId: string,
    opts?: {
      q?: string;
      start?: string;
      end?: string;
      eventType?: string;
      artifactType?: string;
      sigmaOnly?: boolean;
      mftOnly?: boolean;
      browserOnly?: boolean;
      browserCategory?: string;
    }
  ) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.start) params.set("start", opts.start);
    if (opts?.end) params.set("end", opts.end);
    if (opts?.eventType) params.set("event_type", opts.eventType);
    if (opts?.artifactType) params.set("artifact_type", opts.artifactType);
    if (opts?.sigmaOnly) params.set("sigma_only", "true");
    if (opts?.mftOnly) params.set("mft_only", "true");
    if (opts?.browserOnly) params.set("browser_only", "true");
    if (opts?.browserCategory) params.set("browser_category", opts.browserCategory);
    const qs = params.toString();
    return request<TimelineHistogram>(
      `/api/v1/cases/${caseId}/sources/${sourceId}/stats/histogram${qs ? `?${qs}` : ""}`
    );
  },
};
