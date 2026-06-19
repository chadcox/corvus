from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from pydantic import BaseModel, Field

from app.database import get_db
from app.models import Case, EvidenceSource
from app.util.evidence_storage import delete_case_evidence_dir
from corvus_core.schemas import CaseCreate, CaseRead


class CaseRename(BaseModel):
    name: str = Field(min_length=1, max_length=255)

router = APIRouter(prefix="/cases", tags=["cases"])


def _case_to_read(case: Case, evidence_count: int) -> CaseRead:
    return CaseRead(
        id=case.id,
        name=case.name,
        description=case.description,
        created_at=case.created_at,
        updated_at=case.updated_at,
        evidence_source_count=evidence_count,
    )


@router.get("", response_model=list[CaseRead])
def list_cases(db: Session = Depends(get_db)) -> list[CaseRead]:
    rows = (
        db.query(Case, func.count(EvidenceSource.id).label("evidence_count"))
        .outerjoin(EvidenceSource, EvidenceSource.case_id == Case.id)
        .group_by(Case.id)
        .order_by(Case.created_at.desc())
        .all()
    )
    return [_case_to_read(case, count) for case, count in rows]


@router.post("", response_model=CaseRead, status_code=201)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> CaseRead:
    existing = (
        db.query(Case)
        .filter(func.lower(Case.name) == payload.name.strip().lower())
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f'A case named "{payload.name.strip()}" already exists.',
        )
    case = Case(name=payload.name.strip(), description=payload.description)
    db.add(case)
    db.commit()
    db.refresh(case)
    return _case_to_read(case, 0)


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: UUID, db: Session = Depends(get_db)) -> CaseRead:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    count = db.query(EvidenceSource).filter(EvidenceSource.case_id == case_id).count()
    return _case_to_read(case, count)


@router.patch("/{case_id}", response_model=CaseRead)
def rename_case(case_id: UUID, payload: CaseRename, db: Session = Depends(get_db)) -> CaseRead:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    name = payload.name.strip()
    existing = (
        db.query(Case)
        .filter(func.lower(Case.name) == name.lower(), Case.id != case_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f'A case named "{name}" already exists.')
    case.name = name
    db.commit()
    db.refresh(case)
    count = db.query(EvidenceSource).filter(EvidenceSource.case_id == case_id).count()
    return _case_to_read(case, count)


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: UUID, db: Session = Depends(get_db)) -> None:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    db.delete(case)
    db.commit()
    delete_case_evidence_dir(case_id)
