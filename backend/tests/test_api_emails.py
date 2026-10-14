"""
test_api_emails.py

Focused automated tests for Project APA's FastAPI read-only service.
Uses FastAPI TestClient and isolated mock services.

Guarantees:
    - 100% offline execution.
    - Zero live Gmail access or OAuth credentials required.
    - Zero live Ollama server or network calls required.
    - Full dependency override cleanup after each test.
"""

from typing import List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import (
    get_ai_service,
    get_current_settings,
    get_gmail_service,
)
from backend.app.core.config import Settings
from backend.app.domain.models import EmailAnalysis, EmailMessage, ImportanceLevel
from backend.app.main import app, run
from backend.app.services.ai_service import AIService
from backend.app.services.gmail_service import GmailService


@pytest.fixture
def mock_settings() -> Settings:
    """Fixture providing isolated Settings for API tests."""
    return Settings(
        app_name="Artificial Personal Assistant (APA)",
        app_version="0.2.0",
        environment="testing",
        ai_provider="offline",
        local_llm_url="http://127.0.0.1:11434",
    )


@pytest.fixture
def sample_email_message() -> EmailMessage:
    """Fixture returning a standard valid EmailMessage."""
    return EmailMessage(
        id="msg_101",
        thread_id="thread_202",
        message_id="<rfc_msg_101@example.com>",
        sender="alice@example.com",
        recipient="bob@example.com",
        subject="Urgent: Q4 Strategy Update",
        date="Wed, 14 Oct 2026 10:00:00 +0000",
        body_text="Please review the attached Q4 strategy document. This is urgent.",
        body_html="<p>Please review the attached Q4 strategy document. This is urgent.</p>",
        snippet="Please review the attached Q4 strategy...",
    )



@pytest.fixture
def sample_analysis() -> EmailAnalysis:
    """Fixture returning a standard valid EmailAnalysis."""
    return EmailAnalysis(
        importance=ImportanceLevel.HIGH,
        summary="Urgent Q4 strategy document review requested.",
        suggested_action="REPLY",
        confidence_score=0.95,
        reasoning="Contains urgency keywords and direct action request.",
    )


@pytest.fixture
def client(mock_settings: Settings) -> TestClient:
    """
    TestClient fixture with automatic dependency override cleanup.
    Ensures no state leaks between test runs.
    """
    app.dependency_overrides[get_current_settings] = lambda: mock_settings
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()



# ====================================================================== #
# 1. Health Endpoint Tests
# ====================================================================== #


def test_health_endpoint_success(client: TestClient):
    """GET /health returns 200 with service metadata and read-only mode."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "0.2.0"
    assert data["ai_provider"] == "offline"
    assert data["read_only"] is True


def test_health_endpoint_excludes_sensitive_fields(client: TestClient):
    """GET /health must never leak filesystem paths, tokens, or credential state."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    prohibited_keys = {
        "credentials_path",
        "token_path",
        "credentials_file",
        "token_file",
        "credentials_present",
        "token_present",
        "api_key",
        "groq_api_key",
        "gemini_api_key",
        "openai_api_key",
        "project_root",
        "secrets",
    }
    assert prohibited_keys.isdisjoint(data.keys())


# ====================================================================== #
# 2. Email Listing Endpoint Tests (GET /emails)
# ====================================================================== #


def test_list_emails_success(client: TestClient, sample_email_message: EmailMessage):
    """GET /emails returns a list of email metadata summaries."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.return_value = [sample_email_message]
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1

    item = data[0]
    assert item["id"] == "msg_101"
    assert item["thread_id"] == "thread_202"
    assert item["sender"] == "alice@example.com"
    assert item["subject"] == "Urgent: Q4 Strategy Update"
    assert item["snippet"] == "Please review the attached Q4 strategy..."


    # Crucial privacy requirement: collection endpoint omits full bodies
    assert "body_text" not in item
    assert "body_html" not in item


def test_list_emails_supports_query_and_limit(
    client: TestClient, sample_email_message: EmailMessage
):
    """GET /emails correctly forwards search query and limit to the connector."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.return_value = [sample_email_message]
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails?limit=10&query=is:unread")
    assert response.status_code == 200
    mock_gmail.get_emails.assert_called_once_with(query="is:unread", max_results=10)


def test_list_emails_validates_limit_boundaries(client: TestClient):
    """GET /emails validates that limit is between 1 and 50."""
    # Under lower limit (0)
    res_under = client.get("/emails?limit=0")
    assert res_under.status_code == 422

    # Over upper limit (51)
    res_over = client.get("/emails?limit=51")
    assert res_over.status_code == 422

    # Invalid non-integer limit
    res_nan = client.get("/emails?limit=abc")
    assert res_nan.status_code == 422


def test_list_emails_empty_result(client: TestClient):
    """GET /emails returns an empty list when no messages match."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.return_value = []
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails")
    assert response.status_code == 200
    assert response.json() == []


def test_list_emails_missing_credentials_handling(client: TestClient):
    """GET /emails returns 401 Unauthorized when credentials are not configured."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.side_effect = FileNotFoundError("credentials.json not found")
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails")
    assert response.status_code == 401
    assert "credentials" in response.json()["detail"].lower()


def test_list_emails_auth_error_handling(client: TestClient):
    """GET /emails returns 401 Unauthorized on authentication / token expiration."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.side_effect = RuntimeError("Invalid Grant: token has expired")
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails")
    assert response.status_code == 401
    assert "authentication failed" in response.json()["detail"].lower()


def test_list_emails_upstream_service_error_handling(client: TestClient):
    """GET /emails returns 502 Bad Gateway on upstream Gmail API errors."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.side_effect = RuntimeError("Upstream 503 Backend Error")
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails")
    assert response.status_code == 502
    assert "failed to retrieve emails" in response.json()["detail"].lower()


# ====================================================================== #
# 3. Email Detail Endpoint Tests (GET /emails/{email_id})
# ====================================================================== #


def test_get_email_detail_success(
    client: TestClient, sample_email_message: EmailMessage
):
    """GET /emails/{email_id} returns complete message details including bodies."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_email.return_value = sample_email_message
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails/msg_101")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "msg_101"
    assert data["body_text"] == "Please review the attached Q4 strategy document. This is urgent."
    assert "<p>" in data["body_html"]

    assert data["sender"] == "alice@example.com"
    mock_gmail.get_email.assert_called_once_with("msg_101")


def test_get_email_detail_not_found(client: TestClient):
    """GET /emails/{email_id} returns 404 when the message does not exist."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_email.return_value = None
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails/non_existent_id")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_email_detail_missing_credentials(client: TestClient):
    """GET /emails/{email_id} returns 401 when credentials file is missing."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_email.side_effect = FileNotFoundError("credentials.json not found")
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails/msg_101")
    assert response.status_code == 401


def test_get_email_detail_upstream_error(client: TestClient):
    """GET /emails/{email_id} returns 502 on upstream connector failure."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_email.side_effect = RuntimeError("Network timeout")
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.get("/emails/msg_101")
    assert response.status_code == 502


# ====================================================================== #
# 4. Email Analysis Endpoint Tests (POST /emails/{email_id}/analyze)
# ====================================================================== #


def test_analyze_email_success_default_provider(
    client: TestClient,
    sample_email_message: EmailMessage,
    sample_analysis: EmailAnalysis,
):
    """POST /emails/{email_id}/analyze performs analysis with the configured provider."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_email.return_value = sample_email_message
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    mock_ai = MagicMock(spec=AIService)
    mock_ai.analyze.return_value = sample_analysis
    app.dependency_overrides[get_ai_service] = lambda: mock_ai

    response = client.post("/emails/msg_101/analyze")
    assert response.status_code == 200
    data = response.json()
    assert data["email_id"] == "msg_101"
    assert data["importance"] == "HIGH"
    assert data["summary"] == "Urgent Q4 strategy document review requested."
    assert data["suggested_action"] == "REPLY"
    assert data["provider_used"] == "offline"


def test_analyze_email_with_offline_override_query(
    client: TestClient,
    sample_email_message: EmailMessage,
):
    """POST /emails/{email_id}/analyze?provider=offline executes offline heuristic."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_email.return_value = sample_email_message
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.post("/emails/msg_101/analyze?provider=offline")
    assert response.status_code == 200
    data = response.json()
    assert data["email_id"] == "msg_101"
    assert data["importance"] == "HIGH"
    assert data["provider_used"] == "offline"


def test_analyze_email_with_provider_override_body(
    client: TestClient,
    sample_email_message: EmailMessage,
):
    """POST /emails/{email_id}/analyze accepts provider override in JSON body."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_email.return_value = sample_email_message
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.post("/emails/msg_101/analyze", json={"provider": "offline"})
    assert response.status_code == 200
    data = response.json()
    assert data["provider_used"] == "offline"


def test_analyze_email_rejects_unsupported_provider(client: TestClient):
    """POST /emails/{email_id}/analyze rejects unknown or prohibited providers."""
    # Cloud providers are strictly prohibited
    res_cloud = client.post("/emails/msg_101/analyze?provider=groq")
    assert res_cloud.status_code == 400
    assert "unsupported ai provider" in res_cloud.json()["detail"].lower()

    # Arbitrary strings are rejected
    res_invalid = client.post("/emails/msg_101/analyze?provider=openai")
    assert res_invalid.status_code == 400


def test_analyze_email_not_found(client: TestClient):
    """POST /emails/{email_id}/analyze returns 404 when target email does not exist."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_email.return_value = None
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    response = client.post("/emails/missing_id/analyze")
    assert response.status_code == 404


def test_analyze_email_ai_provider_failure(
    client: TestClient,
    sample_email_message: EmailMessage,
):
    """POST /emails/{email_id}/analyze returns 502 without leaking tracebacks on AI failure."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_email.return_value = sample_email_message
    app.dependency_overrides[get_gmail_service] = lambda: mock_gmail

    mock_ai = MagicMock(spec=AIService)
    mock_ai.analyze.side_effect = RuntimeError("Local LLM socket connection refused")
    app.dependency_overrides[get_ai_service] = lambda: mock_ai

    response = client.post("/emails/msg_101/analyze")
    assert response.status_code == 502
    data = response.json()
    assert "ai analysis provider failed" in data["detail"].lower()
    # Ensure sensitive system details or raw tracebacks are not in detail
    assert "traceback" not in data["detail"].lower()


# ====================================================================== #
# 5. Security & Loopback Binding Tests
# ====================================================================== #


def test_loopback_validation_rejects_external_hosts():
    """Server runner must strictly refuse to bind to non-loopback addresses."""
    with pytest.raises(ValueError, match="Security violation"):
        run(host="0.0.0.0", port=8000)

    with pytest.raises(ValueError, match="Security violation"):
        run(host="192.168.1.50", port=8000)


def test_get_gmail_service_enforces_readonly_scope(mock_settings: Settings):
    """Dependency provider get_gmail_service must strictly enforce read-only OAuth scope."""
    broad_settings = mock_settings.model_copy(
        update={
            "gmail_scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
            ]
        }
    )
    service = get_gmail_service(settings=broad_settings)
    assert service.scopes == ["https://www.googleapis.com/auth/gmail.readonly"]


def test_cors_preflight_permitted_and_untrusted_origins(client: TestClient):
    """CORS preflight requests must allow configured local origins and reject untrusted origins."""
    # Permitted origin 1: 127.0.0.1:3000
    res_local_ip = client.options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_local_ip.status_code == 200
    assert res_local_ip.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
    assert res_local_ip.headers.get("access-control-allow-credentials") == "true"

    # Permitted origin 2: localhost:3000
    res_localhost = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_localhost.status_code == 200
    assert res_localhost.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Untrusted origin: malicious.com
    res_untrusted = client.options(
        "/health",
        headers={
            "Origin": "http://malicious.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in res_untrusted.headers


def test_whitespace_email_id_rejected_with_bad_request(client: TestClient):
    """Whitespace-only email IDs must be rejected with 400 Bad Request."""
    res_get = client.get("/emails/%20%20")
    assert res_get.status_code == 400
    assert "invalid email id" in res_get.json()["detail"].lower()

    res_post = client.post("/emails/%20%20/analyze")
    assert res_post.status_code == 400
    assert "invalid email id" in res_post.json()["detail"].lower()
