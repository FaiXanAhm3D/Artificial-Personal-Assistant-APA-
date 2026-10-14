"""
Central Configuration Module for Project APA.

Resolves paths relative to the project root, enforces local-first AI defaults,
and provides strongly typed validation for all environment settings.
"""

from pathlib import Path
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
from dotenv import dotenv_values

# Compute canonical Project APA root anchor:
# .../Project APA/backend/app/core/config.py -> core -> app -> backend -> Project APA
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseModel):
    """Application settings with deterministic defaults and path resolution."""

    # Application metadata
    app_name: str = "Artificial Personal Assistant (APA)"
    app_version: str = "0.2.0"
    environment: Literal["development", "testing", "production"] = "development"

    # Filesystem & Path Management
    project_root: Path = Field(default_factory=lambda: DEFAULT_PROJECT_ROOT)

    # AI Configuration (Local-first by design)
    ai_provider: Literal["local", "offline", "groq", "gemini"] = "local"
    local_llm_url: str = "http://localhost:11434"
    local_model_name: str = "llama3.2:3b"
    local_llm_timeout: float = 30.0
    local_llm_fallback_to_offline: bool = False

    # Cloud AI Credentials (Optional; strictly prohibited on private email by default)
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Gmail Connector File Paths (Relative to project root or absolute paths)
    gmail_credentials_file: str = "credentials.json"
    gmail_token_file: str = "token.json"
    gmail_scopes: List[str] = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    def resolve_path(self, path: str | Path) -> Path:
        """
        Resolves a path reliably.
        Absolute paths are preserved as-is.
        Relative paths are anchored to the project root, independent of current working directory.
        """
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        return (self.project_root / p).resolve()

    @property
    def credentials_path(self) -> Path:
        """Fully resolved path to the Gmail credentials file."""
        return self.resolve_path(self.gmail_credentials_file)

    @property
    def token_path(self) -> Path:
        """Fully resolved path to the Gmail OAuth token file."""
        return self.resolve_path(self.gmail_token_file)

    @model_validator(mode="after")
    def validate_cloud_keys_if_selected(self) -> "Settings":
        """Ensure cloud API keys are provided only if explicitly chosen."""
        if self.ai_provider == "groq" and not self.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is required when AI_PROVIDER is explicitly set to 'groq'."
            )
        if self.ai_provider == "gemini" and not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when AI_PROVIDER is explicitly set to 'gemini'."
            )
        return self


_settings_instance: Optional[Settings] = None


def get_settings(
    env_file: Optional[Path] = None,
    force_reload: bool = False,
    **overrides,
) -> Settings:
    """
    Factory to retrieve or construct the application settings.
    Reads values from OS environment and optional .env file, merging overrides.
    """
    global _settings_instance

    if _settings_instance is not None and not force_reload and not overrides and env_file is None:
        return _settings_instance

    # Load potential .env file
    project_env = env_file or (DEFAULT_PROJECT_ROOT / ".env")
    env_vars = {}
    if project_env.exists():
        env_vars = {k.lower(): v for k, v in dotenv_values(project_env).items() if v is not None}

    # Overlay with os.environ (case-insensitive keys mapping to settings fields)
    import os
    for k, v in os.environ.items():
        env_vars[k.lower()] = v

    # Map standard environment variables to Settings fields
    mapped = {}
    if "ai_provider" in env_vars:
        mapped["ai_provider"] = env_vars["ai_provider"].lower()
    if "ollama_base_url" in env_vars:
        mapped["local_llm_url"] = env_vars["ollama_base_url"]
    elif "local_llm_url" in env_vars:
        mapped["local_llm_url"] = env_vars["local_llm_url"]
    if "local_model_name" in env_vars:
        mapped["local_model_name"] = env_vars["local_model_name"]
    if "local_llm_timeout" in env_vars:
        mapped["local_llm_timeout"] = float(env_vars["local_llm_timeout"])
    if "local_llm_fallback_to_offline" in env_vars:
        mapped["local_llm_fallback_to_offline"] = str(env_vars["local_llm_fallback_to_offline"]).lower() in ("true", "1", "yes")
    if "groq_api_key" in env_vars:
        mapped["groq_api_key"] = env_vars["groq_api_key"]
    if "gemini_api_key" in env_vars:
        mapped["gemini_api_key"] = env_vars["gemini_api_key"]
    if "openai_api_key" in env_vars:
        mapped["openai_api_key"] = env_vars["openai_api_key"]
    if "gmail_credentials_path" in env_vars:
        mapped["gmail_credentials_file"] = env_vars["gmail_credentials_path"]
    if "gmail_token_path" in env_vars:
        mapped["gmail_token_file"] = env_vars["gmail_token_path"]
    if "environment" in env_vars:
        mapped["environment"] = env_vars["environment"].lower()

    # Apply programmatic overrides
    mapped.update(overrides)

    settings = Settings(**mapped)
    if not overrides and env_file is None:
        _settings_instance = settings
    return settings
