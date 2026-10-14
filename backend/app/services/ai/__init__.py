"""
AI services package for Project APA.
Provides modular, provider-independent email analysis and triage.
"""

from backend.app.services.ai.base import AIBaseProvider
from backend.app.services.ai.factory import get_ai_provider
from backend.app.services.ai.offline_provider import OfflineRuleBasedProvider
from backend.app.services.ai.ollama_provider import (
    LocalAIProviderError,
    LocalLLMProvider,
    validate_loopback_endpoint,
)

__all__ = [
    "AIBaseProvider",
    "OfflineRuleBasedProvider",
    "LocalLLMProvider",
    "LocalAIProviderError",
    "get_ai_provider",
    "validate_loopback_endpoint",
]
