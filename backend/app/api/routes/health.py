"""
health.py

Health check endpoint for Project APA REST API.
Verifies service liveness, application version, active AI provider, and read-only mode.
Does not expose sensitive system paths, credentials existence, or tokens.
"""

from fastapi import APIRouter, Depends
from backend.app.api.deps import get_current_settings
from backend.app.api.schemas import HealthResponse
from backend.app.core.config import Settings

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def get_health(settings: Settings = Depends(get_current_settings)) -> HealthResponse:
    """
    Returns API health status, application version, and read-only mode flag.
    Excludes local paths, secrets, or credential state to avoid privacy leaks.
    """
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        ai_provider=settings.ai_provider,
        read_only=True,
    )
