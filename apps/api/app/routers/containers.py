from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.docker_ops import (
    docker_available,
    get_project_container_logs,
    list_project_containers,
    start_project_container,
)

router = APIRouter(prefix="/admin/containers", tags=["admin"])


class ContainerRead(BaseModel):
    id: str
    name: str
    service: str | None
    image: str
    state: str
    status: str
    health: str | None

    model_config = {"from_attributes": True}


class ContainerLogsRead(BaseModel):
    name: str
    logs: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ContainerRead])
def list_containers() -> list[ContainerRead]:
    ok, err = docker_available()
    if not ok:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {err}")
    try:
        return [ContainerRead.model_validate(c) for c in list_project_containers()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list containers: {exc}") from exc


@router.post("/{container_name}/start", response_model=ContainerRead)
def start_container(container_name: str) -> ContainerRead:
    ok, err = docker_available()
    if not ok:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {err}")
    try:
        c = start_project_container(container_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start container: {exc}") from exc
    return ContainerRead.model_validate(c)


@router.get("/{container_name}/logs", response_model=ContainerLogsRead)
def get_container_logs(container_name: str, tail: int = Query(400, ge=1, le=5000)) -> ContainerLogsRead:
    ok, err = docker_available()
    if not ok:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {err}")
    try:
        logs = get_project_container_logs(container_name, tail=tail)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {exc}") from exc
    return ContainerLogsRead(name=container_name, logs=logs)
