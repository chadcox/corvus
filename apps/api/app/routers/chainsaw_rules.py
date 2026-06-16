"""Chainsaw rule bundle — status and refresh from WithSecureLabs/chainsaw."""

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.celery_client import celery_app
from app.chainsaw_rules_status import get_chainsaw_rules_status
from ff_core.schemas import ChainsawRulesStatusRead

router = APIRouter(prefix="/chainsaw/rules", tags=["chainsaw-rules"])


class ChainsawRulesRefreshResponse(BaseModel):
    task_id: str
    state: str = "queued"
    message: str = "Chainsaw rule refresh queued"


@router.get("", response_model=ChainsawRulesStatusRead)
def chainsaw_rules_status() -> ChainsawRulesStatusRead:
    return ChainsawRulesStatusRead.model_validate(get_chainsaw_rules_status())


@router.post("/refresh", response_model=ChainsawRulesRefreshResponse, status_code=202)
def refresh_chainsaw_rules(
    ref: str | None = Query(
        None,
        description="Git branch on WithSecureLabs/chainsaw (default: CHAINSAW_REF env)",
    ),
) -> ChainsawRulesRefreshResponse:
    status = get_chainsaw_rules_status()
    if status.get("state") == "running":
        task_id = status.get("task_id")
        if task_id:
            result = AsyncResult(task_id, app=celery_app)
            if not result.ready():
                raise HTTPException(
                    status_code=409,
                    detail="A Chainsaw rule refresh is already in progress",
                )

    result = celery_app.send_task(
        "worker.tasks.chainsaw_rules.refresh_chainsaw_rules",
        kwargs={"ref": ref} if ref else {},
        queue="ingest",
    )
    return ChainsawRulesRefreshResponse(
        task_id=result.id,
        message="Chainsaw rules refresh queued — native rules and mappings will update from GitHub.",
    )
