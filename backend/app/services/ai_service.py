"""
ai_service.py

High-level application service facade for email analysis.
Connects callers to the configured AI provider while ensuring domain model
validation and privacy safeguards.
"""

from typing import Optional

from backend.app.core.config import Settings, get_settings
from backend.app.domain.models import EmailAnalysis, EmailMessage
from backend.app.services.ai.base import AIBaseProvider
from backend.app.services.ai.factory import get_ai_provider


class AIService:
    """Service facade managing email summarization, importance classification, and analysis."""

    def __init__(
        self,
        provider: Optional[AIBaseProvider] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.provider = provider or get_ai_provider(settings=self.settings)

    def summarize(self, message: EmailMessage) -> str:
        """Generates a concise factual summary of the email message."""
        return self.provider.summarize(message)

    def classify_importance(self, message: EmailMessage) -> EmailAnalysis:
        """Classifies the importance level of the email message."""
        return self.provider.classify_importance(message)

    def analyze(self, message: EmailMessage) -> EmailAnalysis:
        """Performs full analysis (classification, summary, suggested action) on the message."""
        return self.provider.analyze(message)


# Convenience module-level functions
def analyze_email(
    message: EmailMessage,
    provider: Optional[AIBaseProvider] = None,
    settings: Optional[Settings] = None,
) -> EmailAnalysis:
    service = AIService(provider=provider, settings=settings)
    return service.analyze(message)


def summarize_email(
    message: EmailMessage,
    provider: Optional[AIBaseProvider] = None,
    settings: Optional[Settings] = None,
) -> str:
    service = AIService(provider=provider, settings=settings)
    return service.summarize(message)
