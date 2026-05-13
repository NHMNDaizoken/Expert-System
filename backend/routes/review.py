from fastapi import APIRouter, Depends

from backend.core.dependencies import require_admin_api_key
from backend.schemas import RuleDecisionRequest
from backend.services.review_service import ReviewService


router = APIRouter(
    prefix="/api",
    tags=["review"],
    dependencies=[Depends(require_admin_api_key)],
)


@router.get("/pending-rules")
def pending_rules():
    service = ReviewService()
    try:
        return {"rules": service.list_pending()}
    finally:
        service.close()


@router.post("/rules/{rule_id}/approve")
def approve_rule(rule_id: str, payload: RuleDecisionRequest):
    service = ReviewService()
    try:
        return service.set_rule_status(
            rule_id,
            "approved",
            cf=payload.cf,
            note=payload.note,
        )
    finally:
        service.close()


@router.post("/rules/{rule_id}/reject")
def reject_rule(rule_id: str, payload: RuleDecisionRequest):
    service = ReviewService()
    try:
        return service.set_rule_status(
            rule_id,
            "rejected",
            cf=payload.cf,
            note=payload.note,
        )
    finally:
        service.close()
