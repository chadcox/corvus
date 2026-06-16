from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, validate_security_settings
from app.database import init_db
from app.auth.service import get_current_user, require_admin
from app.routers import (
    auth,
    admin,
    cases,
    chainsaw_rules,
    containers,
    detection_rules,
    entities,
    evidence,
    filesystem,
    health,
    ingest_outcome,
    jobs,
    root,
    search,
    sigma,
    sigma_rules,
    yara_rules,
    stats,
    system_status,
    timeline,
    validation,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_security_settings(settings)
    init_db()
    yield


app = FastAPI(
    title="ForensicFlow API",
    version=settings.api_version,
    description="Offline endpoint evidence ingest and forensic triage review",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "meta", "description": "API discovery"},
        {"name": "auth", "description": "Local development authentication and user management"},
        {"name": "admin", "description": "Operator / development (ENABLE_ADMIN_API)"},
        {"name": "validation", "description": "Automated ingest tests (ENABLE_VALIDATION_API)"},
        {"name": "ingest-outcome", "description": "Structured ingest success checks for CI"},
        {"name": "sigma-rules", "description": "Sigma rule bundle sync from GitHub"},
        {"name": "chainsaw-rules", "description": "Chainsaw native rules from WithSecureLabs/chainsaw"},
        {"name": "yara-rules", "description": "YARA signature bundle refresh from Neo23x0/signature-base"},
        {"name": "detection-rules", "description": "Combined Sigma + Chainsaw rule status"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(root.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1", dependencies=[Depends(require_admin)])
app.include_router(containers.router, prefix="/api/v1", dependencies=[Depends(require_admin)])
app.include_router(cases.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(evidence.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(jobs.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(ingest_outcome.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(validation.router, prefix="/api/v1", dependencies=[Depends(require_admin)])
app.include_router(timeline.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(filesystem.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(entities.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(search.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(stats.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(sigma.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(sigma_rules.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(chainsaw_rules.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(yara_rules.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(detection_rules.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(system_status.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(health.router)
