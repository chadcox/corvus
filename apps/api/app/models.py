import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    evidence_sources: Mapped[list["EvidenceSource"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True
    )


class EvidenceSource(Base):
    __tablename__ = "evidence_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    collector: Mapped[str] = mapped_column(String(64), default="import")
    collector_version: Mapped[str | None] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(64), default="endpoint")
    platform: Mapped[str] = mapped_column(String(32), default="unknown")
    os_version: Mapped[str | None] = mapped_column(String(255))
    architecture: Mapped[str | None] = mapped_column(String(64))
    timezone: Mapped[str | None] = mapped_column(String(128))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    package_path: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_filename: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    manifest: Mapped[dict | None] = mapped_column(JSONB)
    sha256: Mapped[str | None] = mapped_column(Text)
    sha1: Mapped[str | None] = mapped_column(Text)
    md5: Mapped[str | None] = mapped_column(Text)
    hash_status: Mapped[str | None] = mapped_column(String(32))
    hash_file_count: Mapped[int | None] = mapped_column(Integer)
    yara_status: Mapped[str | None] = mapped_column(String(32))
    yara_match_count: Mapped[int | None] = mapped_column(Integer)
    yara_file_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped["Case"] = relationship(back_populates="evidence_sources")
    jobs: Mapped[list["IngestJob"]] = relationship(
        back_populates="evidence_source", cascade="all, delete-orphan", passive_deletes=True
    )


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_sources.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_stage: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    evidence_source: Mapped["EvidenceSource"] = relationship(back_populates="jobs")


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_sources.id", ondelete="CASCADE"), nullable=False
    )
    timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_type: Mapped[str | None] = mapped_column(String(64))
    original_source: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    entity_refs: Mapped[list] = mapped_column(JSONB, default=list)
    sigma_hits: Mapped[list] = mapped_column(JSONB, default=list)


class SigmaDetection(Base):
    __tablename__ = "sigma_detections"
    __table_args__ = (
        UniqueConstraint(
            "evidence_source_id",
            "engine",
            "rule_id",
            name="uq_sigma_detections_source_engine_rule",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_sources.id", ondelete="CASCADE"), nullable=False
    )
    engine: Mapped[str] = mapped_column(String(32), nullable=False, default="sigma")
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    description: Mapped[str | None] = mapped_column(Text)
    rule_definition: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    sample_event_ids: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FilesystemNode(Base):
    __tablename__ = "filesystem_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_sources.id", ondelete="CASCADE"), nullable=False
    )
    full_path: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    is_directory: Mapped[bool] = mapped_column(default=False)
    size: Mapped[int | None] = mapped_column(BigInteger)
    is_deleted: Mapped[bool] = mapped_column(default=False)
    parent_path: Mapped[str | None] = mapped_column(Text)


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_sources.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)


class Relation(Base):
    __tablename__ = "relations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_sources.id", ondelete="CASCADE"), nullable=False
    )
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE")
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE")
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)


class EvidenceFileHash(Base):
    __tablename__ = "evidence_file_hashes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_sources.id", ondelete="CASCADE"), nullable=False
    )
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sha1: Mapped[str] = mapped_column(String(40), nullable=False)
    md5: Mapped[str] = mapped_column(String(32), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="analyst")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
