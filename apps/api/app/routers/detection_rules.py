"""Unified detection rule status (Sigma + Chainsaw)."""

from fastapi import APIRouter

from app.chainsaw_rules_status import get_chainsaw_rules_status
from app.sigma_rules_status import get_sigma_rules_status
from ff_core.schemas import (
    ChainsawRulesStatusRead,
    DetectionRulesStatusRead,
    SigmaRulesStatusRead,
)

router = APIRouter(prefix="/detection-rules", tags=["detection-rules"])


@router.get("", response_model=DetectionRulesStatusRead)
def detection_rules_status() -> DetectionRulesStatusRead:
    return DetectionRulesStatusRead(
        sigma=SigmaRulesStatusRead.model_validate(get_sigma_rules_status()),
        chainsaw=ChainsawRulesStatusRead.model_validate(get_chainsaw_rules_status()),
    )
