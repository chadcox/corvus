import csv
import hashlib
import io
import json
import re
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.celery_client import celery_app
from app.config import settings
from app.database import get_db
from app.models import (
    Case,
    Entity,
    EvidenceFileHash,
    EvidenceSource,
    FilesystemNode,
    IngestJob,
    Relation,
    SigmaDetection,
    TimelineEvent,
)
from app.package_extract import PackageExtractError, extract_archive, is_supported_archive
from app.services.opensearch_service import delete_source_docs
from ff_core.constants import EvidencePlatform, JobStatus
from ff_core.schemas import EvidenceManifest, EvidenceSourceRead, IngestJobRead

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["evidence"])

_COPY_CHUNK_SIZE = 1024 * 1024
_MEMORY_EXTS = {".raw", ".mem", ".vmem", ".dmp", ".img", ".bin"}


def _copy_upload_with_hashes(upload: UploadFile, dest: Path) -> tuple[str, str, str]:
    h_sha256 = hashlib.sha256()
    h_sha1 = hashlib.sha1()
    h_md5 = hashlib.md5()
    total = 0
    with dest.open("wb") as f:
        while chunk := upload.file.read(_COPY_CHUNK_SIZE):
            total += len(chunk)
            if total > settings.upload_max_bytes:
                raise PackageExtractError(
                    f"Upload exceeds the configured limit of {settings.upload_max_bytes:,} bytes"
                )
            h_sha256.update(chunk)
            h_sha1.update(chunk)
            h_md5.update(chunk)
            f.write(chunk)
    return h_sha256.hexdigest(), h_sha1.hexdigest(), h_md5.hexdigest()


def _extract_upload(dest: Path, upload: UploadFile) -> tuple[str, str, str] | None:
    """Extract upload and return hashes of the primary uploaded file."""
    dest.mkdir(parents=True, exist_ok=True)
    filename = upload.filename or "upload.bin"
    if is_supported_archive(filename):
        archive_path = dest / filename
        hashes = _copy_upload_with_hashes(upload, archive_path)
        extract_archive(
            archive_path,
            dest,
            max_files=settings.extracted_max_files,
            max_uncompressed_bytes=settings.extracted_max_bytes,
        )
        archive_path.unlink(missing_ok=True)
        return hashes
    else:
        out = dest / filename
        return _copy_upload_with_hashes(upload, out)


def _resolve_package_root(package_dir: Path) -> Path:
    """Find package root when upload ZIP wraps a single folder."""
    if (package_dir / "manifest.json").is_file():
        return package_dir
    children = [
        p for p in package_dir.iterdir() if p.is_dir() and p.name not in (".git", "__MACOSX")
    ]
    if len(children) == 1 and (children[0] / "manifest.json").is_file():
        return children[0]
    return package_dir


def _load_manifest(package_dir: Path) -> EvidenceManifest | None:
    root = _resolve_package_root(package_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return EvidenceManifest.model_validate(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json is not valid JSON: {exc}") from exc
    except ValidationError as exc:
        raise ValueError(f"manifest.json failed validation: {exc}") from exc


def _normalize_platform(value: str | None) -> str:
    if not value:
        return EvidencePlatform.UNKNOWN
    normalized = value.strip().lower()
    aliases = {
        "win": EvidencePlatform.WINDOWS,
        "windows": EvidencePlatform.WINDOWS,
        "windows_nt": EvidencePlatform.WINDOWS,
        "mac": EvidencePlatform.MACOS,
        "macos": EvidencePlatform.MACOS,
        "darwin": EvidencePlatform.MACOS,
        "osx": EvidencePlatform.MACOS,
        "linux": EvidencePlatform.LINUX,
        "gnu/linux": EvidencePlatform.LINUX,
        "memory": EvidencePlatform.MEMORY,
        "mem": EvidencePlatform.MEMORY,
        "ram": EvidencePlatform.MEMORY,
    }
    return aliases.get(normalized, EvidencePlatform.UNKNOWN)


def _infer_platform_from_artifacts(package_dir: Path) -> str:
    root = _resolve_package_root(package_dir)
    if any((root / marker).exists() for marker in ("uac.log", "uac.log.gz", "uac.conf", "uac.yml", "uac.yaml")):
        return EvidencePlatform.LINUX
    children = [
        p for p in root.iterdir() if p.is_dir() and p.name not in (".git", "__MACOSX")
    ]
    if len(children) == 1 and not (root / "manifest.json").is_file():
        root = children[0]
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        name = path.name.lower()
        if name in ("etc", "var", "home", "usr"):
            return EvidencePlatform.LINUX
        if name in ("windows", "program files", "programdata"):
            return EvidencePlatform.WINDOWS
    names = {p.name.lower() for p in root.iterdir()} if root.is_dir() else set()
    if {"windows", "program files", "programdata"} & names or (root / "C").is_dir() or (root / "c").is_dir():
        return EvidencePlatform.WINDOWS
    if {"applications", "library", "system", "users"} <= names:
        return EvidencePlatform.MACOS
    if {"etc", "var", "home", "usr"} & names:
        return EvidencePlatform.LINUX

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if path.suffix.lower() in _MEMORY_EXTS or lower.endswith(
            (".memdump", ".memory", ".hiberfil.sys")
        ):
            return EvidencePlatform.MEMORY
        if lower.endswith((".evtx", ".pf")) or lower in ("$mft", "mft"):
            return EvidencePlatform.WINDOWS
        if lower in ("system.log", "install.log") or lower.endswith(".plist"):
            return EvidencePlatform.MACOS
        if lower in ("auth.log", "secure", "syslog") or lower.endswith((".journal", ".service")):
            return EvidencePlatform.LINUX
    return EvidencePlatform.UNKNOWN


def _platform_for_source(
    package_dir: Path,
    manifest: EvidenceManifest | None,
    explicit_platform: str | None = None,
) -> str:
    explicit = _normalize_platform(explicit_platform)
    if explicit != EvidencePlatform.UNKNOWN:
        return explicit
    manifest_platform = _normalize_platform(manifest.platform if manifest else None)
    if manifest_platform != EvidencePlatform.UNKNOWN:
        return manifest_platform
    return _infer_platform_from_artifacts(package_dir)


def _apply_manifest_metadata(
    source: EvidenceSource,
    package_dir: Path,
    manifest: EvidenceManifest | None,
    *,
    explicit_platform: str | None = None,
) -> None:
    detected_platform = _platform_for_source(package_dir, manifest, explicit_platform)
    if detected_platform != EvidencePlatform.UNKNOWN or not source.platform:
        source.platform = detected_platform
    if manifest:
        source.collector = manifest.collector or source.collector or "import"
        source.collector_version = manifest.collector_version or manifest.kape_version
        source.source_type = manifest.source_type or "endpoint"
        source.os_version = manifest.os_version
        source.architecture = manifest.architecture
        source.timezone = manifest.timezone
        source.collected_at = manifest.collected_at
        source.manifest = manifest.model_dump(mode="json")
    else:
        source.collector = source.collector or "import"
        source.source_type = source.source_type or "endpoint"


def _hostname_from_copylog(package_dir: Path) -> str | None:
    """Infer host from KAPE CopyLog destination path (e.g. ...PC-RACHEL\\c\\)."""
    root = _resolve_package_root(package_dir)
    for log in sorted(root.glob("*CopyLog.csv")):
        try:
            import csv

            with log.open(newline="", encoding="utf-8", errors="replace") as f:
                row = next(csv.DictReader(f), None)
            if not row:
                continue
            dest = row.get("DestinationFile") or row.get("SourceFile") or ""
            folder_match = re.search(r"[\\/]([^\\/]+)[\\/][cC][\\/]", dest)
            if not folder_match:
                continue
            folder = folder_match.group(1)
            host_match = re.search(r"(PC-[A-Z0-9_-]+)$", folder, re.IGNORECASE)
            if host_match:
                return host_match.group(1).upper()
            if "_" in folder:
                return folder.split("_")[-1]
            return folder
        except OSError:
            continue
    return None


def _hostname_from_artifacts(package_dir: Path) -> str | None:
    """Use a single uploaded artifact name when there is no manifest."""
    root = _resolve_package_root(package_dir)
    artifact_exts = {".evtx", ".pf", ".mft", ".csv", ".json", ".hve", ".dat", ".txt"}
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in artifact_exts and p.name != "manifest.json"
    ]
    if len(files) == 1:
        stem = files[0].stem.replace("$", "") or "artifact"
        return stem[:64]
    if files and all(p.suffix.lower() == ".evtx" for p in files):
        return "windows-logs"
    return None


def _infer_hostname(package_dir: Path, manifest: EvidenceManifest | None) -> str:
    if manifest and manifest.hostname:
        return manifest.hostname
    from_copylog = _hostname_from_copylog(package_dir)
    if from_copylog:
        return from_copylog
    from_artifacts = _hostname_from_artifacts(package_dir)
    if from_artifacts:
        return from_artifacts
    root = _resolve_package_root(package_dir)
    name = root.name.split("_")[0]
    if name and len(name) < 64 and not re.fullmatch(r"[0-9a-f-]{36}", name, re.I):
        return name
    return "unknown-host"


@router.get("", response_model=list[EvidenceSourceRead])
def list_evidence(case_id: UUID, db: Session = Depends(get_db)) -> list[EvidenceSourceRead]:
    if not db.get(Case, case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    sources = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.case_id == case_id)
        .order_by(EvidenceSource.created_at.desc())
        .all()
    )
    if not sources:
        return []

    source_ids = [source.id for source in sources]
    jobs = (
        db.query(IngestJob)
        .filter(IngestJob.evidence_source_id.in_(source_ids))
        .order_by(IngestJob.evidence_source_id, IngestJob.created_at.desc())
        .all()
    )
    latest_jobs: dict[UUID, IngestJob] = {}
    for job in jobs:
        latest_jobs.setdefault(job.evidence_source_id, job)

    out: list[EvidenceSourceRead] = []
    for source in sources:
        latest = latest_jobs.get(source.id)
        duration = None
        if latest and latest.started_at and latest.finished_at:
            duration = max(0.0, (latest.finished_at - latest.started_at).total_seconds())
        out.append(
            EvidenceSourceRead.model_validate(source).model_copy(
                update={
                    "processing_started_at": latest.started_at if latest else None,
                    "processing_finished_at": latest.finished_at if latest else None,
                    "total_processing_seconds": duration,
                    "latest_job_id": latest.id if latest else None,
                }
            )
        )
    return out


@router.post("/upload", response_model=IngestJobRead, status_code=202)
async def upload_evidence(
    case_id: UUID,
    file: UploadFile = File(...),
    hostname: str | None = Form(None),
    platform: str | None = Form(None),
    db: Session = Depends(get_db),
) -> IngestJob:
    return await _create_ingest_source(
        case_id=case_id,
        file=file,
        hostname=hostname,
        platform=platform,
        db=db,
    )


async def _create_ingest_source(
    *,
    case_id: UUID,
    file: UploadFile,
    hostname: str | None,
    platform: str | None,
    db: Session,
    manifest_overrides: dict | None = None,
) -> IngestJob:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    evidence_root = Path(settings.evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True)

    source = EvidenceSource(
        case_id=case_id,
        hostname=hostname or "pending",
        collector="import",
        source_type="endpoint",
        platform=_normalize_platform(platform),
        package_path="",
        uploaded_filename=file.filename or "upload.bin",
        status=JobStatus.PENDING,
    )
    db.add(source)
    db.flush()

    package_dir = evidence_root / str(case_id) / str(source.id)
    try:
        upload_hashes = _extract_upload(package_dir, file)
    except PackageExtractError as exc:
        db.rollback()
        if package_dir.exists():
            shutil.rmtree(package_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        manifest = _load_manifest(package_dir)
    except ValueError as exc:
        db.rollback()
        shutil.rmtree(package_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if manifest_overrides:
        if manifest is None:
            manifest = EvidenceManifest.model_validate(manifest_overrides)
        else:
            manifest = manifest.model_copy(update=manifest_overrides)

    source.hostname = hostname or _infer_hostname(package_dir, manifest)
    source.package_path = str(package_dir)
    _apply_manifest_metadata(source, package_dir, manifest, explicit_platform=platform)
    if upload_hashes:
        source.sha256, source.sha1, source.md5 = upload_hashes

    job = IngestJob(
        evidence_source_id=source.id,
        status=JobStatus.PENDING,
        progress=0,
        message="Queued for ingest",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        celery_app.send_task(
            "worker.tasks.ingest.process_evidence_package",
            args=[str(job.id), str(source.id)],
            queue="ingest",
            task_id=str(job.id),
        )
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.message = f"Failed to queue ingest: {exc.__class__.__name__}"
        source.status = JobStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="Ingest queue unavailable; job marked failed",
        ) from exc

    return job


def _clear_source_data(db: Session, source_id: UUID) -> None:
    try:
        delete_source_docs(source_id)
    except Exception:
        pass
    db.query(TimelineEvent).filter(TimelineEvent.evidence_source_id == source_id).delete(
        synchronize_session=False
    )
    db.query(Relation).filter(Relation.evidence_source_id == source_id).delete(
        synchronize_session=False
    )
    db.query(Entity).filter(Entity.evidence_source_id == source_id).delete(
        synchronize_session=False
    )
    db.query(FilesystemNode).filter(FilesystemNode.evidence_source_id == source_id).delete(
        synchronize_session=False
    )
    db.query(SigmaDetection).filter(SigmaDetection.evidence_source_id == source_id).delete(
        synchronize_session=False
    )


def _active_ingest_job(db: Session, source_id: UUID) -> IngestJob | None:
    return (
        db.query(IngestJob)
        .filter(
            IngestJob.evidence_source_id == source_id,
            IngestJob.status.in_((JobStatus.PENDING, JobStatus.RUNNING)),
        )
        .order_by(IngestJob.created_at.desc())
        .first()
    )


def _queue_ingest(source: EvidenceSource, db: Session) -> IngestJob:
    if _active_ingest_job(db, source.id):
        raise HTTPException(status_code=409, detail="Ingest already in progress for this source")

    job = IngestJob(
        evidence_source_id=source.id,
        status=JobStatus.PENDING,
        progress=0,
        message="Queued for ingest",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        celery_app.send_task(
            "worker.tasks.ingest.process_evidence_package",
            args=[str(job.id), str(source.id)],
            queue="ingest",
            task_id=str(job.id),
        )
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.message = f"Failed to queue ingest: {exc.__class__.__name__}"
        source.status = JobStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="Ingest queue unavailable; job marked failed",
        ) from exc
    return job


@router.post("/{source_id}/reingest", response_model=IngestJobRead, status_code=202)
def reingest_evidence(
    case_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
) -> IngestJob:
    """Re-run ingest on an existing package (e.g. after parser improvements)."""
    if settings.delete_evidence_after_ingest:
        raise HTTPException(
            status_code=409,
            detail="Re-ingest is disabled when delete_evidence_after_ingest is enabled",
        )

    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")
    package_dir = Path(source.package_path)
    if not package_dir.is_dir():
        raise HTTPException(status_code=400, detail="Package files no longer on disk")

    if _active_ingest_job(db, source_id):
        raise HTTPException(status_code=409, detail="Ingest already in progress for this source")

    _clear_source_data(db, source_id)
    try:
        manifest = _load_manifest(package_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    source.hostname = _infer_hostname(package_dir, manifest)
    _apply_manifest_metadata(source, package_dir, manifest)
    source.status = JobStatus.PENDING
    db.commit()

    return _queue_ingest(source, db)


@router.get("/{source_id}/jobs", response_model=list[IngestJobRead])
def list_jobs(
    case_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
) -> list[IngestJob]:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")
    return (
        db.query(IngestJob)
        .filter(IngestJob.evidence_source_id == source_id)
        .order_by(IngestJob.created_at.desc())
        .all()
    )


@router.post("/{source_id}/hashes/compute", status_code=202)
def trigger_hash_files(
    case_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Trigger asynchronous SHA256 hashing of all files in the evidence package."""
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")
    if source.status != "completed":
        raise HTTPException(status_code=400, detail="Ingest must be complete before hashing files")
    package_dir = Path(source.package_path)
    if not package_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Evidence files are no longer on disk for this source",
        )
    source.hash_status = "running"
    db.commit()
    celery_app.send_task(
        "worker.tasks.hash_evidence.hash_evidence_files",
        args=[str(source_id)],
        queue="ingest",
    )
    return {"message": "Hash job started"}


@router.post("/{source_id}/yara/scan", status_code=202)
def trigger_yara_scan(
    case_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")
    if source.status != "completed":
        raise HTTPException(status_code=400, detail="Ingest must be complete before YARA scan")
    package_dir = Path(source.package_path)
    if not package_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Evidence files are no longer on disk for this source",
        )
    source.yara_status = "running"
    db.commit()
    celery_app.send_task(
        "worker.tasks.yara_scan.scan_evidence_with_yara",
        args=[str(source_id)],
        queue="ingest",
    )
    return {"message": "YARA scan started"}


@router.get("/{source_id}/hashes")
def get_hash_status(
    case_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Return package hashes and file-hash job status."""
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")
    file_count = (
        db.query(EvidenceFileHash)
        .filter(EvidenceFileHash.evidence_source_id == source_id)
        .count()
    )
    return {
        "sha256": source.sha256,
        "sha1": source.sha1,
        "md5": source.md5,
        "hash_status": source.hash_status,
        "hash_file_count": source.hash_file_count,
        "hashed_files_in_db": file_count,
        "yara_status": source.yara_status,
        "yara_match_count": source.yara_match_count,
        "yara_file_count": source.yara_file_count,
    }


@router.get("/{source_id}/hashes/export")
def export_file_hashes(
    case_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download all file hashes as a CSV report."""
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")
    query = (
        db.query(
            EvidenceFileHash.relative_path,
            EvidenceFileHash.sha256,
            EvidenceFileHash.sha1,
            EvidenceFileHash.md5,
            EvidenceFileHash.file_size,
            EvidenceFileHash.computed_at,
        )
        .filter(EvidenceFileHash.evidence_source_id == source_id)
        .order_by(EvidenceFileHash.relative_path)
    )

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["path", "sha256", "sha1", "md5", "size_bytes", "computed_at"])
        yield buf.getvalue()
        for row in query.yield_per(2000):
            buf.seek(0)
            buf.truncate(0)
            writer.writerow([
                row.relative_path,
                row.sha256,
                row.sha1,
                row.md5,
                row.file_size or "",
                row.computed_at.isoformat(),
            ])
            yield buf.getvalue()

    name = f"file-hashes-{source.hostname}.csv".replace(" ", "_")
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
