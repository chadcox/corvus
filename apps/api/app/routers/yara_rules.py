"""YARA rule bundle status and refresh."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from celery.result import AsyncResult

from app.celery_client import celery_app
from app.yara_rules_status import get_yara_rules_status

router = APIRouter(prefix="/yara/rules", tags=["yara-rules"])


class YaraRulesStatusRead(BaseModel):
    state: str = "idle"
    rule_count: int = 0
    updated_at: str | None = None
    message: str | None = None
    task_id: str | None = None


class YaraRulesRefreshResponse(BaseModel):
    task_id: str
    state: str = "queued"
    message: str = "YARA rule refresh queued"


@router.get("", response_model=YaraRulesStatusRead)
def yara_rules_status() -> YaraRulesStatusRead:
    return YaraRulesStatusRead.model_validate(get_yara_rules_status())


@router.post("/refresh", response_model=YaraRulesRefreshResponse, status_code=202)
def refresh_yara_rules() -> YaraRulesRefreshResponse:
    status = get_yara_rules_status()
    if status.get("state") == "running":
        task_id = status.get("task_id")
        if task_id:
            result = AsyncResult(task_id, app=celery_app)
            if not result.ready():
                raise HTTPException(status_code=409, detail="A YARA rule refresh is already in progress")

    result = celery_app.send_task(
        "worker.tasks.yara_rules.refresh_yara_rules",
        queue="ingest",
    )
    return YaraRulesRefreshResponse(task_id=result.id)
