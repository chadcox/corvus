from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EvidenceFileHash, EvidenceSource, FilesystemNode
from ff_core.schemas import FilesystemNodeRead

router = APIRouter(prefix="/cases/{case_id}/sources/{source_id}/filesystem", tags=["filesystem"])

_PREVIEW_MAX_BYTES = 4096


def _strip_root_prefix(path: str) -> str:
    lower = path.lower()
    if lower.startswith("/[root]/"):
        return path[8:]
    if lower.startswith("[root]/"):
        return path[7:]
    return path


def _resolve_node_file(source: EvidenceSource, node: FilesystemNode) -> Path:
    package_dir = Path(source.package_path).resolve()
    if not package_dir.is_dir():
        raise HTTPException(status_code=404, detail="Evidence package files are not available on disk")
    raw = (node.full_path or "").replace("\\", "/").strip()
    if not raw:
        raise HTTPException(status_code=404, detail="File path is empty")
    normalized = _strip_root_prefix(raw).lstrip("/")
    candidates: list[Path] = []
    seen: set[str] = set()

    def add_candidate(rel_path: str) -> None:
        rel = rel_path.strip("/")
        if not rel:
            return
        candidate = (package_dir / rel).resolve()
        key = str(candidate)
        if key in seen:
            return
        seen.add(key)
        candidates.append(candidate)

    if normalized:
        add_candidate(normalized)

        # Windows-style logical paths like "C:/Users/..." can exist in package as
        # "c/Users/..." depending on collector layout.
        parts = normalized.split("/")
        if parts and len(parts[0]) == 2 and parts[0][1] == ":" and parts[0][0].isalpha():
            drive = parts[0][0]
            tail = "/".join(parts[1:])
            if tail:
                add_candidate(f"{drive.lower()}/{tail}")
                add_candidate(f"{drive.upper()}/{tail}")
                add_candidate(tail)
        elif parts and parts[0].lower() in ("users", "windows", "programdata", "program files", "program files (x86)"):
            # Some parsed Windows paths lose their drive letter and are stored
            # as "/Users/..." while extracted package trees are rooted at "c/".
            add_candidate(f"c/{normalized}")
            add_candidate(f"C/{normalized}")

    package_str = str(package_dir).replace("\\", "/")
    if package_str in raw:
        tail = raw.split(package_str, 1)[1].lstrip("/")
        if tail:
            add_candidate(tail)

    # Some rows may carry host/container absolute prefixes. Try progressively
    # shorter suffixes to recover package-relative path safely.
    if normalized:
        parts = [p for p in normalized.split("/") if p]
        for idx in range(1, len(parts) - 1):
            add_candidate("/".join(parts[idx:]))

    for candidate in candidates:
        try:
            candidate.relative_to(package_dir)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    raise HTTPException(status_code=404, detail="Selected file is not available in evidence package")


def _read_preview(path: Path, *, offset: int, length: int) -> dict:
    with path.open("rb") as fh:
        fh.seek(offset)
        chunk = fh.read(length)
    hex_dump = " ".join(f"{b:02x}" for b in chunk)
    ascii_dump = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
    file_size = path.stat().st_size
    return {
        "offset": offset,
        "length": len(chunk),
        "file_size": file_size,
        "truncated": offset + len(chunk) < file_size,
        "hex": hex_dump,
        "ascii": ascii_dump,
    }


def _get_source_and_node(db: Session, case_id: UUID, source_id: UUID, node_id: UUID) -> tuple[EvidenceSource, FilesystemNode]:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")
    node = (
        db.query(FilesystemNode)
        .filter(FilesystemNode.id == node_id, FilesystemNode.evidence_source_id == source_id)
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="Filesystem node not found")
    if node.is_directory:
        raise HTTPException(status_code=400, detail="Selected node is a directory")
    return source, node


@router.get("", response_model=list[FilesystemNodeRead])
def list_filesystem_nodes(
    case_id: UUID,
    source_id: UUID,
    parent_path: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[FilesystemNode]:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")

    query = db.query(FilesystemNode).filter(FilesystemNode.evidence_source_id == source_id)
    if parent_path is not None:
        query = query.filter(FilesystemNode.parent_path == parent_path)
    else:
        query = query.filter(
            (FilesystemNode.parent_path == None) | (FilesystemNode.parent_path == "")  # noqa: E711
        )

    return query.order_by(FilesystemNode.is_directory.desc(), FilesystemNode.name.asc()).all()


@router.get("/search", response_model=list[FilesystemNodeRead])
def search_paths(
    case_id: UUID,
    source_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
) -> list[FilesystemNode]:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")

    return (
        db.query(FilesystemNode)
        .filter(
            FilesystemNode.evidence_source_id == source_id,
            FilesystemNode.full_path.ilike(f"%{q}%"),
        )
        .limit(limit)
        .all()
    )


@router.get("/{node_id}/preview")
def preview_file(
    case_id: UUID,
    source_id: UUID,
    node_id: UUID,
    offset: int = Query(0, ge=0),
    length: int = Query(512, ge=1, le=_PREVIEW_MAX_BYTES),
    db: Session = Depends(get_db),
) -> dict:
    source, node = _get_source_and_node(db, case_id, source_id, node_id)
    file_path = _resolve_node_file(source, node)
    preview = _read_preview(file_path, offset=offset, length=length)
    return {
        "node_id": str(node.id),
        "name": node.name,
        "full_path": node.full_path,
        **preview,
    }


@router.get("/{node_id}/download")
def download_file(
    case_id: UUID,
    source_id: UUID,
    node_id: UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    source, node = _get_source_and_node(db, case_id, source_id, node_id)
    file_path = _resolve_node_file(source, node)
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=node.name or file_path.name,
    )


@router.get("/{node_id}/hashes")
def file_hashes(
    case_id: UUID,
    source_id: UUID,
    node_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    source, node = _get_source_and_node(db, case_id, source_id, node_id)
    file_path = _resolve_node_file(source, node)
    package_dir = Path(source.package_path).resolve()
    relative_path = str(file_path.relative_to(package_dir)).replace("\\", "/")
    row = (
        db.query(EvidenceFileHash)
        .filter(
            EvidenceFileHash.evidence_source_id == source_id,
            EvidenceFileHash.relative_path == relative_path,
        )
        .first()
    )
    return {
        "node_id": str(node.id),
        "relative_path": relative_path,
        "sha256": row.sha256 if row else None,
        "sha1": row.sha1 if row else None,
        "md5": row.md5 if row else None,
        "available": row is not None,
    }
