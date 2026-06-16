from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.readiness import readiness_payload

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "version": settings.api_version,
        "admin_api": settings.enable_admin_api,
        "validation_api": settings.enable_validation_api,
    }


@router.get("/health/ready", response_model=None)
def readiness() -> JSONResponse:
    """Check dependencies for orchestration (Docker Compose, k8s probes)."""
    body = readiness_payload()
    code = 200 if body["status"] == "ready" else 503
    return JSONResponse(status_code=code, content=body)
