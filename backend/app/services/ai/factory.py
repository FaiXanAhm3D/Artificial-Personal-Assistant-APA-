"""
Factory for creating AI and rule-based providers based on central configuration.
"""

from typing import Optional

from backend.app.core.config import Settings, get_settings
from backend.app.services.ai.base import AIBaseProvider
from backend.app.services.ai.offline_provider import OfflineRuleBasedProvider
from backend.app.services.ai.ollama_provider import LocalLLMProvider


def get_ai_provider(
    settings: Optional[Settings] = None,
    provider_override: Optional[str] = None,
    enable_fallback: Optional[bool] = None,
) -> AIBaseProvider:
    """
    Constructs and returns an AI provider adhering to central Settings.

    Args:
        settings: Application settings (defaults to get_settings()).
        provider_override: Optional explicit provider selection ('local', 'offline').
        enable_fallback: Optional override for falling back to offline provider on local LLM errors.

    Returns:
        An instance implementing AIBaseProvider.
    """
    s = settings or get_settings()
    provider_type = (provider_override or s.ai_provider).lower().strip()

    if provider_type == "offline":
        return OfflineRuleBasedProvider()

    elif provider_type == "local":
        fallback_enabled = (
            enable_fallback
            if enable_fallback is not None
            else s.local_llm_fallback_to_offline
        )
        return LocalLLMProvider(
            base_url=s.local_llm_url,
            model_name=s.local_model_name,
            timeout=s.local_llm_timeout,
            enable_fallback=fallback_enabled,
        )

    elif provider_type in ("groq", "gemini"):
        # Cloud providers are strictly prohibited on private email by default
        raise NotImplementedError(
            f"Cloud provider '{provider_type}' is prohibited on local personal data in this baseline. "
            f"Use 'local' or 'offline' provider."
        )

    else:
        raise ValueError(
            f"Unknown AI provider '{provider_type}'. Supported providers: 'local', 'offline'."
        )
