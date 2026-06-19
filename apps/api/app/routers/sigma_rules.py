"""Sigma rule bundle sync — status and on-demand refresh from GitHub."""

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.celery_client import celery_app
from app.sigma_rules_status import get_sigma_rules_status
from corvus_core.schemas import SigmaRulesStatusRead

router = APIRouter(prefix="/sigma/rules", tags=["sigma-rules"])


class SigmaRulesRefreshResponse(BaseModel):
    task_id: str
    state: str = "queued"
    message: str = "Sigma rule refresh queued"


@router.get("", response_model=SigmaRulesStatusRead)
def sigma_rules_status() -> SigmaRulesStatusRead:
    return SigmaRulesStatusRead.model_validate(get_sigma_rules_status())


@router.post("/refresh", response_model=SigmaRulesRefreshResponse, status_code=202)
def refresh_sigma_rules(
    ref: str | None = Query(
        None,
        description="Git branch or tag on SigmaHQ/sigma (default: SIGMA_REF env, usually master)",
    ),
) -> SigmaRulesRefreshResponse:
    status = get_sigma_rules_status()
    if status.get("state") == "running":
        task_id = status.get("task_id")
        if task_id:
            result = AsyncResult(task_id, app=celery_app)
            if not result.ready():
                raise HTTPException(
                    status_code=409,
                    detail="A Sigma rule refresh is already in progress",
                )
        else:
            raise HTTPException(
                status_code=409,
                detail="A Sigma rule refresh is already in progress",
            )

    result = celery_app.send_task(
        "worker.tasks.sigma_rules.refresh_sigma_rules",
        kwargs={"ref": ref} if ref else {},
        queue="ingest",
    )
    return SigmaRulesRefreshResponse(
        task_id=result.id,
        message="Sigma rule refresh queued — rules will update from GitHub shortly.",
    )
