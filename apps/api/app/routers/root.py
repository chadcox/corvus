"""API discovery — entry points for operators and automation."""

from fastapi import APIRouter

from app.config import settings
from corvus_core.schemas import ApiIndexRead, ApiLink

router = APIRouter(tags=["meta"])


@router.get("/api/v1", response_model=ApiIndexRead)
def api_index() -> ApiIndexRead:
    """Curated links for docs, health, admin, and validation."""
    links = [
        ApiLink(rel="openapi", href="/docs", description="Swagger UI"),
        ApiLink(rel="openapi-json", href="/openapi.json"),
        ApiLink(rel="health", href="/health"),
        ApiLink(rel="readiness", href="/health/ready"),
        ApiLink(rel="auth-login", href="/api/v1/auth/login"),
        ApiLink(rel="auth-me", href="/api/v1/auth/me"),
        ApiLink(rel="cases", href="/api/v1/cases"),
        ApiLink(rel="sigma-rules", href="/api/v1/sigma/rules"),
        ApiLink(rel="chainsaw-rules", href="/api/v1/chainsaw/rules"),
        ApiLink(rel="detection-rules", href="/api/v1/detection-rules"),
    ]
    if settings.enable_admin_api:
        links.append(
            ApiLink(
                rel="admin-overview",
                href="/api/v1/admin/overview",
                description="DB counts, disk, sigma, job breakdown",
            )
        )
        links.append(ApiLink(rel="admin-routes", href="/api/v1/admin/routes"))
        links.append(
            ApiLink(
                rel="admin-delete-all-cases",
                href="/api/v1/admin/cases?confirm=true",
                description="DELETE — remove all cases/projects and evidence",
            )
        )
        links.append(
            ApiLink(
                rel="admin-purge-preview",
                href="/api/v1/admin/cases/purge-preview",
                description="GET — preview case count before purge",
            )
        )
    if settings.enable_validation_api:
        links.append(
            ApiLink(
                rel="validation-ingest-sample",
                href="/api/v1/validation/ingest-sample",
                description="POST — queue bundled sample ingest",
            )
        )
    return ApiIndexRead(name="Corvus API", version=settings.api_version, links=links)
