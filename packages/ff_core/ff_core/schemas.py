from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class CaseRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    evidence_source_count: int = 0

    model_config = {"from_attributes": True}


class EvidenceManifest(BaseModel):
    package_version: str = "1"
    hostname: str | None = None
    collected_at: datetime | None = None
    collector: str = "import"
    collector_version: str | None = None
    source_type: str = "endpoint"
    platform: str = "unknown"
    os_version: str | None = None
    architecture: str | None = None
    kape_version: str | None = None
    modules_run: list[str] = Field(default_factory=list)
    timezone: str | None = None

    model_config = {"extra": "allow"}


class EvidenceSourceRead(BaseModel):
    id: UUID
    case_id: UUID
    hostname: str
    collector: str
    collector_version: str | None = None
    source_type: str
    platform: str
    os_version: str | None = None
    architecture: str | None = None
    timezone: str | None = None
    collected_at: datetime | None = None
    package_path: str
    uploaded_filename: str | None = None
    status: str
    manifest: dict[str, Any] | None = None
    created_at: datetime
    processing_started_at: datetime | None = None
    processing_finished_at: datetime | None = None
    total_processing_seconds: float | None = None
    latest_job_id: UUID | None = None

    model_config = {"from_attributes": True}


class IngestJobRead(BaseModel):
    id: UUID
    evidence_source_id: UUID
    status: str
    progress: int
    message: str | None
    error_code: str | None = None
    error_stage: str | None = None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SigmaHitRead(BaseModel):
    rule_id: str
    title: str
    level: str
    engine: str = "sigma"


class TimelineEventRead(BaseModel):
    id: UUID
    evidence_source_id: UUID
    timestamp_utc: datetime
    event_type: str
    summary: str
    artifact_type: str | None
    original_source: str | None
    data: dict[str, Any]
    entity_refs: list[str]
    sigma_hits: list[SigmaHitRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SigmaRulesStatusRead(BaseModel):
    state: str = "idle"
    rule_count: int = 0
    ref: str = "master"
    updated_at: datetime | None = None
    message: str | None = None
    task_id: str | None = None
    refresh_interval_hours: float = 0.0


class ChainsawRulesStatusRead(BaseModel):
    state: str = "idle"
    rule_count: int = 0
    mapping_count: int = 0
    binary_available: bool = False
    chainsaw_version: str | None = None
    ref: str = "master"
    updated_at: datetime | None = None
    message: str | None = None
    task_id: str | None = None
    include_sigma_in_hunt: bool = False


class DetectionRulesStatusRead(BaseModel):
    sigma: SigmaRulesStatusRead
    chainsaw: ChainsawRulesStatusRead


class SigmaDetectionRead(BaseModel):
    id: UUID
    evidence_source_id: UUID
    engine: str = "sigma"
    rule_id: str
    title: str
    level: str
    description: str | None
    rule_definition: str | None = None
    tags: list[str] = Field(default_factory=list)
    match_count: int
    sample_event_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class FilesystemNodeRead(BaseModel):
    id: UUID
    evidence_source_id: UUID
    full_path: str
    name: str
    is_directory: bool
    size: int | None
    is_deleted: bool
    parent_path: str | None

    model_config = {"from_attributes": True}


class EntityRead(BaseModel):
    id: UUID
    evidence_source_id: UUID
    entity_type: str
    display_name: str
    attributes: dict[str, Any]

    model_config = {"from_attributes": True}


class GlobalSearchResult(BaseModel):
    query: str
    timeline: list[TimelineEventRead] = Field(default_factory=list)
    filesystem: list[FilesystemNodeRead] = Field(default_factory=list)
    entities: list[EntityRead] = Field(default_factory=list)
    total: int = 0


class SourceStats(BaseModel):
    timeline_count: int = 0
    filesystem_count: int = 0
    entity_count: int = 0
    sigma_detection_count: int = 0
    mft_count: int = 0
    browser_count: int = 0
    event_types: list[str] = Field(default_factory=list)


class IngestCheck(BaseModel):
    name: str
    passed: bool
    detail: str | None = None


class IngestOutcomeRead(BaseModel):
    """Machine-readable ingest validation — use instead of parsing job message strings."""

    success: bool
    case_id: UUID
    job_id: UUID
    evidence_source_id: UUID
    job_status: str
    source_status: str | None = None
    progress: int = 0
    message: str | None = None
    stats: SourceStats | None = None
    checks: list[IngestCheck] = Field(default_factory=list)


class IngestSampleStartRead(BaseModel):
    """Response from POST /validation/ingest-sample — poll outcome_url until success."""

    case_id: UUID
    job_id: UUID
    evidence_source_id: UUID
    sample: str
    outcome_path: str
    job_path: str
    stats_path: str


class ApiLink(BaseModel):
    rel: str
    href: str
    description: str | None = None


class ApiIndexRead(BaseModel):
    name: str
    version: str
    links: list[ApiLink]


class AdminTableCounts(BaseModel):
    cases: int
    evidence_sources: int
    ingest_jobs: int
    timeline_events: int
    filesystem_nodes: int
    entities: int
    relations: int
    sigma_detections: int


class AdminDiskUsage(BaseModel):
    path: str
    total_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    error: str | None = None


class AdminFeatureFlags(BaseModel):
    enable_validation_api: bool
    enable_admin_api: bool


class AdminAuthSecurityRead(BaseModel):
    failed_logins_5m: int = 0
    active_lockouts: int = 0
    redis_available: bool = True
    revocation_redis_available: bool = True
    revocation_failures_5m: int = 0
    error: str | None = None


class AdminSearchObservabilityRead(BaseModel):
    window_seconds: int = 300
    total_queries: int = 0
    opensearch_hits: int = 0
    fallback_hits: int = 0
    fallback_short_queries: int = 0
    fallback_avg_ms: float = 0.0


class AdminOverviewRead(BaseModel):
    readiness: dict
    table_counts: AdminTableCounts
    jobs_by_status: dict[str, int]
    evidence_by_status: dict[str, int]
    disk: AdminDiskUsage
    sigma_rules: SigmaRulesStatusRead
    feature_flags: AdminFeatureFlags
    auth_security: AdminAuthSecurityRead = Field(default_factory=AdminAuthSecurityRead)
    search_observability: AdminSearchObservabilityRead = Field(
        default_factory=AdminSearchObservabilityRead
    )


class AdminJobSummary(BaseModel):
    id: UUID
    evidence_source_id: UUID
    case_id: UUID
    case_name: str
    hostname: str
    status: str
    progress: int
    message: str | None
    error_code: str | None = None
    error_stage: str | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AdminEvidenceSourceSummary(BaseModel):
    id: UUID
    case_id: UUID
    case_name: str
    hostname: str
    status: str
    collector: str
    platform: str
    source_type: str
    created_at: datetime
    latest_job_id: UUID | None
    latest_job_status: str | None


class AdminRouteEntry(BaseModel):
    methods: list[str]
    path: str
    name: str | None
    tags: list[str]


class AdminConfigRead(BaseModel):
    api_version: str
    evidence_root: str
    samples_root: str
    sigma_rules_root: str
    sigma_ref: str
    sigma_refresh_interval_hours: float
    cors_origins: str
    database_url_host: str


class AdminPurgeResult(BaseModel):
    deleted_cases: int
    case_ids: list[UUID]


class CasePurgeResult(BaseModel):
    """Result of deleting one or more cases (projects) and evidence on disk."""

    deleted_cases: int
    case_ids: list[UUID]
    evidence_dirs_removed: int = 0
    orphan_evidence_dirs_removed: int = 0
    dry_run: bool = False


class CaseBulkDeleteRequest(BaseModel):
    case_ids: list[UUID] = Field(min_length=1, max_length=500)
    confirm: bool = Field(
        False,
        description="Must be true to perform deletion",
    )
