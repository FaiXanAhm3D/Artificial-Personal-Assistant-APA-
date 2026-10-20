"""
deps.py

Dependency injection providers for FastAPI routes.
Enables clean substitution of GmailService and AIService in automated tests
without network calls or real credentials.
"""

from fastapi import Depends
from backend.app.core.config import Settings, get_settings
from backend.app.services.ai_service import AIService
from backend.app.services.gmail_service import GmailService

# Read-only Gmail scope strictly enforced for API interactions
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def get_current_settings() -> Settings:
    """Dependency provider for application settings."""
    return get_settings()


def get_gmail_service(
    settings: Settings = Depends(get_current_settings),
) -> GmailService:
    """
    Dependency provider for GmailService.
    Always enforces read-only scope and non-interactive authentication for API routes.
    """
    return GmailService(
        settings=settings,
        scopes=[GMAIL_READONLY_SCOPE],
        interactive=False,
    )


def get_ai_service(
    settings: Settings = Depends(get_current_settings),
) -> AIService:
    """
    Dependency provider for AIService.
    Initializes using central settings (defaulting to local/offline providers).
    """
    return AIService(settings=settings)
