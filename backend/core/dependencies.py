from fastapi import Header, HTTPException, status
from backend.core.config import settings
from backend.core.container import container
from src.expert_system.inference.engine import ExpertSystemEngine

def require_admin_api_key(x_admin_api_key: str | None = Header(default=None)):
    if not x_admin_api_key or x_admin_api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key.",
        )

def get_engine() -> ExpertSystemEngine:
    return container.get_engine()
