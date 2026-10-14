"""
Unit tests for Project APA central configuration and path resolution.
Verifies defaults, missing setting validation, and working-directory independence.
"""

import os
from pathlib import Path
import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings, get_settings, DEFAULT_PROJECT_ROOT


def test_default_configuration():
    """Verify default settings are local-first and secure without requiring secrets."""
    settings = Settings()

    assert settings.ai_provider == "local"
    assert settings.local_llm_url == "http://localhost:11434"
    assert settings.local_model_name == "llama3.2:3b"
    assert settings.groq_api_key is None
    assert settings.gemini_api_key is None
    assert settings.environment == "development"
    assert len(settings.gmail_scopes) == 2


def test_path_resolution_independent_of_cwd(tmp_path):
    """Verify relative paths resolve to project root regardless of the current working directory."""
    settings = Settings(project_root=tmp_path)

    # Relative paths
    resolved_cred = settings.resolve_path("credentials.json")
    resolved_tok = settings.resolve_path("token.json")
    resolved_sub = settings.resolve_path("subdir/nested.txt")

    assert resolved_cred == (tmp_path / "credentials.json").resolve()
    assert resolved_tok == (tmp_path / "token.json").resolve()
    assert resolved_sub == (tmp_path / "subdir" / "nested.txt").resolve()

    # Properties
    assert settings.credentials_path == (tmp_path / "credentials.json").resolve()
    assert settings.token_path == (tmp_path / "token.json").resolve()


def test_path_resolution_absolute_path():
    """Verify absolute paths are preserved without prepending project root."""
    settings = Settings()
    abs_path = Path("C:/arbitrary/absolute/path.json")

    assert settings.resolve_path(abs_path) == abs_path.resolve()


def test_invalid_ai_provider_raises_validation_error():
    """Verify setting an unsupported AI provider raises an understandable ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(ai_provider="unsupported_vendor")

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("ai_provider",) for e in errors)


def test_cloud_provider_requires_key_when_selected():
    """Verify that selecting a cloud AI provider without a key fails validation with clear messaging."""
    # Groq without key
    with pytest.raises(ValidationError) as exc_groq:
        Settings(ai_provider="groq", groq_api_key=None)
    assert "GROQ_API_KEY is required" in str(exc_groq.value)

    # Gemini without key
    with pytest.raises(ValidationError) as exc_gemini:
        Settings(ai_provider="gemini", gemini_api_key=None)
    assert "GEMINI_API_KEY is required" in str(exc_gemini.value)


def test_cloud_provider_succeeds_when_key_provided():
    """Verify cloud provider succeeds when API key is explicitly supplied."""
    groq_settings = Settings(ai_provider="groq", groq_api_key="gsk-dummy-test-key")
    assert groq_settings.ai_provider == "groq"
    assert groq_settings.groq_api_key == "gsk-dummy-test-key"

    gemini_settings = Settings(ai_provider="gemini", gemini_api_key="gem-dummy-test-key")
    assert gemini_settings.ai_provider == "gemini"
    assert gemini_settings.gemini_api_key == "gem-dummy-test-key"


def test_get_settings_env_override(tmp_path):
    """Verify get_settings reads from a custom .env file correctly."""
    custom_env = tmp_path / ".env.test"
    custom_env.write_text(
        "AI_PROVIDER=local\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n"
        "LOCAL_MODEL_NAME=qwen2.5:3b\n"
        "GMAIL_CREDENTIALS_PATH=custom_creds.json\n",
        encoding="utf-8"
    )

    settings = get_settings(env_file=custom_env, force_reload=True)
    assert settings.ai_provider == "local"
    assert settings.local_llm_url == "http://127.0.0.1:11434"
    assert settings.local_model_name == "qwen2.5:3b"
    assert settings.gmail_credentials_file == "custom_creds.json"
