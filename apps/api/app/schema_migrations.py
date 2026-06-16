"""Apply idempotent PostgreSQL FK updates for ON DELETE CASCADE."""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

logger = logging.getLogger(__name__)

# (table, column, ref_table, ref_column)
_CASCADE_FKS: list[tuple[str, str, str, str]] = [
    ("evidence_sources", "case_id", "cases", "id"),
    ("ingest_jobs", "evidence_source_id", "evidence_sources", "id"),
    ("timeline_events", "evidence_source_id", "evidence_sources", "id"),
    ("filesystem_nodes", "evidence_source_id", "evidence_sources", "id"),
    ("entities", "evidence_source_id", "evidence_sources", "id"),
    ("relations", "evidence_source_id", "evidence_sources", "id"),
    ("relations", "source_entity_id", "entities", "id"),
    ("relations", "target_entity_id", "entities", "id"),
]


def _constraint_name(table: str, column: str) -> str:
    return f"{table}_{column}_fkey"


def ensure_cascade_deletes(engine: Engine) -> None:
    """Recreate FK constraints with ON DELETE CASCADE (safe for existing dev DBs)."""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        for table, column, ref_table, ref_col in _CASCADE_FKS:
            cname = _constraint_name(table, column)
            try:
                with conn.begin_nested():
                    conn.execute(
                        text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{cname}"')
                    )
                    conn.execute(
                        text(
                            f'ALTER TABLE "{table}" ADD CONSTRAINT "{cname}" '
                            f'FOREIGN KEY ("{column}") REFERENCES "{ref_table}" ("{ref_col}") '
                            f"ON DELETE CASCADE"
                        )
                    )
            except DBAPIError as exc:
                # Timescale compressed hypertables can reject FK DDL changes.
                # Keep startup resilient for existing dev databases.
                msg = str(getattr(exc, "orig", exc)).lower()
                if table == "timeline_events" and "hypertable" in msg and "compression" in msg:
                    logger.warning(
                        "Skipping cascade FK migration for %s.%s due to Timescale compression: %s",
                        table,
                        column,
                        exc,
                    )
                    continue
                raise


def ensure_sigma_schema(engine: Engine) -> None:
    """Sigma rule hits on timeline events and per-source detection summaries."""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        with conn.begin_nested():
            conn.execute(
                text(
                    """
                    ALTER TABLE timeline_events
                    ADD COLUMN IF NOT EXISTS sigma_hits JSONB
                    """
                )
            )
        with conn.begin_nested():
            conn.execute(
                text(
                    """
                    UPDATE timeline_events
                    SET sigma_hits = '[]'::jsonb
                    WHERE sigma_hits IS NULL
                    """
                )
            )
        try:
            with conn.begin_nested():
                conn.execute(
                    text(
                        """
                        ALTER TABLE timeline_events
                        ALTER COLUMN sigma_hits SET NOT NULL
                        """
                    )
                )
        except DBAPIError as exc:
            msg = str(getattr(exc, "orig", exc)).lower()
            if "hypertable" in msg and "compression" in msg:
                logger.warning(
                    "Skipping timeline_events.sigma_hits NOT NULL migration due to Timescale compression: %s",
                    exc,
                )
            else:
                raise
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sigma_detections (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    evidence_source_id UUID NOT NULL
                        REFERENCES evidence_sources(id) ON DELETE CASCADE,
                    rule_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'medium',
                    description TEXT,
                    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                    match_count INTEGER NOT NULL DEFAULT 0,
                    sample_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (evidence_source_id, rule_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_sigma_detections_source
                ON sigma_detections (evidence_source_id)
                """
            )
        )
        # Table may predate UNIQUE (evidence_source_id, rule_id) — required for ingest upsert.
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sigma_detections_source_rule
                ON sigma_detections (evidence_source_id, rule_id)
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE sigma_detections
                ADD COLUMN IF NOT EXISTS engine TEXT NOT NULL DEFAULT 'sigma'
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE sigma_detections
                ADD COLUMN IF NOT EXISTS rule_definition TEXT
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE sigma_detections SET engine = 'sigma' WHERE engine IS NULL OR engine = ''
                """
            )
        )
        conn.execute(
            text("DROP INDEX IF EXISTS uq_sigma_detections_source_rule")
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sigma_detections_source_engine_rule
                ON sigma_detections (evidence_source_id, engine, rule_id)
                """
            )
        )


def ensure_performance_indexes(engine: Engine) -> None:
    """Add btree/trigram/GIN indexes for common query filters and pagination.

    Idempotent: uses IF NOT EXISTS so repeated init_db() calls are safe.
    """
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        # Timeline events — heaviest-queried table
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_timeline_source
                ON timeline_events (evidence_source_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_timeline_ts
                ON timeline_events (timestamp_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_timeline_source_ts
                ON timeline_events (evidence_source_id, timestamp_utc, id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_timeline_artifact_type
                ON timeline_events (evidence_source_id, artifact_type, timestamp_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_timeline_event_type
                ON timeline_events (evidence_source_id, event_type, timestamp_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_timeline_summary_trgm
                ON timeline_events USING gin (summary gin_trgm_ops)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_timeline_original_source_trgm
                ON timeline_events USING gin (original_source gin_trgm_ops)
                """
            )
        )
        # GIN on JSONB list of entity UUIDs enables .contains([eid]) fast path
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_timeline_entity_refs
                ON timeline_events USING gin (entity_refs)
                """
            )
        )

        # Filesystem nodes — browsing is exact parent_path equality, search is substring
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_fs_source
                ON filesystem_nodes (evidence_source_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_fs_parent_path
                ON filesystem_nodes (parent_path)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_fs_source_parent_name
                ON filesystem_nodes (evidence_source_id, parent_path, is_directory DESC, name)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_fs_source_full_path
                ON filesystem_nodes (evidence_source_id, full_path)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_fs_full_path_trgm
                ON filesystem_nodes USING gin (full_path gin_trgm_ops)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_fs_name
                ON filesystem_nodes (name)
                """
            )
        )

        # Entities — filtered by type, ordered by (type, name) in list endpoint
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_entities_source
                ON entities (evidence_source_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_entities_type
                ON entities (entity_type)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_entities_type_name
                ON entities (entity_type, display_name)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_entities_source_type_name
                ON entities (evidence_source_id, entity_type, display_name)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_entities_display_name_trgm
                ON entities USING gin (display_name gin_trgm_ops)
                """
            )
        )

        # Relations — navigated from entities in both directions
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_relations_source
                ON relations (evidence_source_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_evidence_sources_case_created
                ON evidence_sources (case_id, created_at DESC)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_ingest_jobs_source_status_created
                ON ingest_jobs (evidence_source_id, status, created_at DESC)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_relations_source_entity
                ON relations (source_entity_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_relations_target_entity
                ON relations (target_entity_id)
                """
            )
        )


def ensure_hash_schema(engine: Engine) -> None:
    """Hash fields for evidence packages and individual files."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS sha256 TEXT"))
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS sha1 TEXT"))
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS md5 TEXT"))
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS hash_status TEXT"))
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS hash_file_count INTEGER"))
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS yara_status TEXT"))
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS yara_match_count INTEGER"))
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS yara_file_count INTEGER"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS evidence_file_hashes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                evidence_source_id UUID NOT NULL
                    REFERENCES evidence_sources(id) ON DELETE CASCADE,
                relative_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                sha1 TEXT,
                md5 TEXT,
                file_size BIGINT,
                computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("ALTER TABLE evidence_file_hashes ADD COLUMN IF NOT EXISTS sha1 TEXT"))
        conn.execute(text("ALTER TABLE evidence_file_hashes ADD COLUMN IF NOT EXISTS md5 TEXT"))
        conn.execute(text("UPDATE evidence_file_hashes SET sha1 = '' WHERE sha1 IS NULL"))
        conn.execute(text("UPDATE evidence_file_hashes SET md5 = '' WHERE md5 IS NULL"))
        conn.execute(text("ALTER TABLE evidence_file_hashes ALTER COLUMN sha1 SET NOT NULL"))
        conn.execute(text("ALTER TABLE evidence_file_hashes ALTER COLUMN md5 SET NOT NULL"))
        conn.execute(text("""
            ALTER TABLE evidence_file_hashes
            ALTER COLUMN id SET DEFAULT gen_random_uuid()
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_file_hashes_source
            ON evidence_file_hashes (evidence_source_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_file_hashes_source_path
            ON evidence_file_hashes (evidence_source_id, relative_path)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_file_hashes_sha256
            ON evidence_file_hashes (sha256)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_file_hashes_sha1
            ON evidence_file_hashes (sha1)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_file_hashes_md5
            ON evidence_file_hashes (md5)
        """))


def ensure_evidence_source_metadata_schema(engine: Engine) -> None:
    """Cross-platform source metadata for adapter selection and UI context."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS collector_version TEXT")
        )
        conn.execute(
            text(
                """
                ALTER TABLE evidence_sources
                ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'endpoint'
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE evidence_sources
                ADD COLUMN IF NOT EXISTS platform TEXT NOT NULL DEFAULT 'unknown'
                """
            )
        )
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS os_version TEXT"))
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS architecture TEXT"))
        conn.execute(text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS timezone TEXT"))
        conn.execute(
            text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS collected_at TIMESTAMPTZ")
        )
        conn.execute(
            text(
                """
                UPDATE evidence_sources
                SET collector = 'import'
                WHERE collector IS NULL OR collector = ''
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_evidence_sources_platform
                ON evidence_sources (platform)
                """
            )
        )
        conn.execute(
            text("ALTER TABLE evidence_sources ADD COLUMN IF NOT EXISTS uploaded_filename TEXT")
        )



def ensure_timescale_schema(engine: Engine) -> None:
    """Convert timeline_events to a TimescaleDB hypertable when available."""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        available = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'
                )
                """
            )
        ).scalar()
        if not available:
            return
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))

        table_exists = conn.execute(
            text("SELECT to_regclass('public.timeline_events') IS NOT NULL")
        ).scalar()
        if not table_exists:
            return

        is_hypertable = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM timescaledb_information.hypertables
                    WHERE hypertable_schema = 'public'
                      AND hypertable_name = 'timeline_events'
                )
                """
            )
        ).scalar()
        if is_hypertable:
            return

        row_count = conn.execute(text("SELECT count(*) FROM timeline_events")).scalar() or 0
        if row_count:
            return

        conn.execute(text("ALTER TABLE timeline_events ALTER COLUMN id SET NOT NULL"))
        conn.execute(text("ALTER TABLE timeline_events ALTER COLUMN timestamp_utc SET NOT NULL"))
        conn.execute(text("ALTER TABLE timeline_events DROP CONSTRAINT IF EXISTS timeline_events_pkey"))
        conn.execute(
            text(
                """
                ALTER TABLE timeline_events
                ADD CONSTRAINT timeline_events_pkey PRIMARY KEY (timestamp_utc, id)
                """
            )
        )
        conn.execute(
            text(
                """
                SELECT create_hypertable(
                    'timeline_events',
                    'timestamp_utc',
                    chunk_time_interval => INTERVAL '7 days',
                    if_not_exists => TRUE,
                    migrate_data => TRUE
                )
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE timeline_events SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'evidence_source_id,artifact_type',
                    timescaledb.compress_orderby = 'timestamp_utc DESC'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                SELECT add_compression_policy(
                    'timeline_events',
                    INTERVAL '7 days',
                    if_not_exists => TRUE
                )
                """
            )
        )


def ensure_auth_schema(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'analyst',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_users_username
                ON users (username)
                """
            )
        )


def ensure_large_size_columns(engine: Engine) -> None:
    """Use BIGINT for size columns to prevent integer overflows."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE filesystem_nodes
                ALTER COLUMN size TYPE BIGINT
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE evidence_file_hashes
                ALTER COLUMN file_size TYPE BIGINT
                """
            )
        )
