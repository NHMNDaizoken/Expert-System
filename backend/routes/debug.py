import os
from fastapi import APIRouter, HTTPException, status
from backend.services.session_service import SessionService
from backend.core.config import settings

router = APIRouter(tags=["debug"])

def _is_debug_enabled():
    debug_env = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    app_env = os.getenv("APP_ENV", "production").lower() == "development"
    return debug_env or app_env

@router.get("/debug/diagnosis/{session_id}/trace")
def get_diagnosis_trace(session_id: str):
    if not _is_debug_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debug endpoints are disabled in production.",
        )
    
    session = SessionService().get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        )
    
    trace = session.get("reasoning_trace")
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No reasoning trace found for this session.",
        )
    
    return {"session_id": session_id, "trace": trace}
