"""
Integration tests for the Project APA End-to-End Gmail Demonstration workflow.

Verifies:
    - Complete retrieval -> domain mapping -> AI triage -> terminal output pipeline.
    - Deterministic offline baseline execution (100% offline, zero Ollama requirement).
    - Local LLM provider execution with mocked HTTP responses.
    - Handling missing OAuth credentials with clear user instructions.
    - Handling Gmail API failures and empty search results.
    - Read-only scope enforcement (no send/modify access requested).
    - Correct terminal card rendering and batch summary calculations.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.app.core.config import Settings
from backend.app.domain.models import EmailAnalysis, EmailMessage, ImportanceLevel
from backend.app.services.ai.offline_provider import OfflineRuleBasedProvider
from backend.app.services.ai.ollama_provider import LocalLLMProvider
from backend.app.services.ai_service import AIService
from backend.app.services.gmail_service import GmailService
from main import GMAIL_READONLY_SCOPE, render_email_card, run_demonstration


def create_synthetic_emails(count: int = 5) -> list[EmailMessage]:
    """Generates synthetic EmailMessage fixtures covering diverse priorities."""
    messages = [
        EmailMessage(
            id="msg_001",
            sender="security@service.org",
            subject="Security Alert: Unusual sign-in activity detected",
            date="Mon, 13 Oct 2026 10:00:00 +0000",
            body_text="Action required: We noticed a login from an unrecognized device. Review immediately.",
        ),
        EmailMessage(
            id="msg_002",
            sender="boss@corp.com",
            subject="Urgent: Q3 Budget Deadline Today",
            date="Mon, 13 Oct 2026 10:15:00 +0000",
            body_text="Please submit your team budget before 5 PM today without delay.",
        ),
        EmailMessage(
            id="msg_003",
            sender="colleague@corp.com",
            subject="Project roadmap sync notes",
            date="Mon, 13 Oct 2026 11:30:00 +0000",
            body_text="Hi team, here are the meeting notes from our architecture review session.",
        ),
        EmailMessage(
            id="msg_004",
            sender="newsletter@techdaily.com",
            subject="Weekly Developer Digest #102",
            date="Mon, 13 Oct 2026 12:00:00 +0000",
            body_text="Check out the latest tools in Python. Click here to unsubscribe.",
        ),
        EmailMessage(
            id="msg_005",
            sender="store@shopping.com",
            subject="Exclusive Sale: 40% off electronics",
            date="Mon, 13 Oct 2026 12:45:00 +0000",
            body_text="Big seasonal discount available this weekend only. Promotional offer.",
        ),
    ]
    return messages[:count]


# ----------------------------------------------------------------------
# 1. End-to-End Workflow Tests (Offline & Local Providers)
# ----------------------------------------------------------------------


def test_e2e_demonstration_offline_provider_success(capsys):
    """Verify complete end-to-end flow with offline provider renders all cards and summary."""
    synthetic_emails = create_synthetic_emails(5)

    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.return_value = synthetic_emails

    settings = Settings(ai_provider="offline")
    ai_service = AIService(provider=OfflineRuleBasedProvider())

    exit_code = run_demonstration(
        limit=5,
        provider_override="offline",
        settings=settings,
        gmail_service=mock_gmail,
        ai_service=ai_service,
    )

    assert exit_code == 0
    captured = capsys.readouterr().out

    # Verify banner and read-only scope display
    assert GMAIL_READONLY_SCOPE in captured
    assert "STRICTLY READ-ONLY" in captured

    # Verify each email rendered with required fields
    for email in synthetic_emails:
        assert email.sender in captured
        assert email.subject in captured

    # Verify triage badges rendered
    assert "[HIGH PRIORITY]" in captured
    assert "[MEDIUM PRIORITY]" in captured
    assert "[LOW PRIORITY]" in captured

    # Verify summary fields rendered
    assert "Summary:" in captured
    assert "Suggested Action:" in captured

    # Verify Batch Summary Dashboard
    assert "BATCH TRIAGE SUMMARY" in captured
    assert "Total Emails Processed:  5" in captured
    assert "High Importance:         2" in captured
    assert "Medium Importance:       1" in captured
    assert "Low Importance:          2" in captured
    assert "Zero emails modified or sent" in captured


def test_e2e_demonstration_local_llm_provider_success(capsys):
    """Verify complete flow with local LLM provider when model returns valid JSON."""
    synthetic_emails = create_synthetic_emails(2)

    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.return_value = synthetic_emails

    mock_llm_provider = MagicMock(spec=LocalLLMProvider)
    mock_llm_provider.analyze.side_effect = [
        EmailAnalysis(
            importance=ImportanceLevel.HIGH,
            summary="Security alert regarding new login device.",
            suggested_action="Review login history and reset password.",
            confidence_score=0.98,
            reasoning="Direct security implication.",
        ),
        EmailAnalysis(
            importance=ImportanceLevel.HIGH,
            summary="Urgent budget submission due today.",
            suggested_action="Finalize budget spreadsheet immediately.",
            confidence_score=0.95,
            reasoning="Explicit deadline stated by manager.",
        ),
    ]

    settings = Settings(ai_provider="local")
    ai_service = AIService(provider=mock_llm_provider)

    exit_code = run_demonstration(
        limit=2,
        provider_override="local",
        settings=settings,
        gmail_service=mock_gmail,
        ai_service=ai_service,
    )

    assert exit_code == 0
    captured = capsys.readouterr().out

    assert "Total Emails Processed:  2" in captured
    assert "High Importance:         2" in captured
    assert "Security alert regarding new login device." in captured
    assert "Finalize budget spreadsheet immediately." in captured


# ----------------------------------------------------------------------
# 2. Safety, Error Handling & Boundary Condition Tests
# ----------------------------------------------------------------------


def test_e2e_demonstration_missing_credentials_graceful_exit(capsys, tmp_path):
    """Verify missing credentials.json produces clear setup guidance and exits with code 1."""
    settings = Settings(
        project_root=tmp_path,
        gmail_credentials_file="nonexistent_creds.json",
        gmail_token_file="nonexistent_token.json",
    )

    exit_code = run_demonstration(settings=settings)

    assert exit_code == 1
    captured = capsys.readouterr().out

    assert "ACTION REQUIRED: Gmail OAuth Credentials Not Found" in captured
    assert "https://console.cloud.google.com/" in captured
    assert "credentials.json" in captured
    assert "Desktop app" in captured


def test_e2e_demonstration_empty_mailbox_returns_zero(capsys):
    """Verify empty search results print an informative message and exit cleanly."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.return_value = []

    exit_code = run_demonstration(
        query="label:nonexistent",
        provider_override="offline",
        gmail_service=mock_gmail,
    )

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "No emails found in mailbox" in captured


def test_e2e_demonstration_api_error_returns_nonzero(capsys):
    """Verify Gmail API failure displays friendly diagnostic and exits with code 1."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.side_effect = RuntimeError("Gmail API rate limit exceeded")

    exit_code = run_demonstration(
        provider_override="offline",
        gmail_service=mock_gmail,
    )

    assert exit_code == 1
    captured = capsys.readouterr().out
    assert "Failed to fetch emails from Gmail API" in captured


def test_e2e_demonstration_respects_custom_limit(capsys):
    """Verify that the requested limit parameter is passed directly to get_emails."""
    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.return_value = create_synthetic_emails(3)

    ai_service = AIService(provider=OfflineRuleBasedProvider())

    run_demonstration(
        limit=3,
        query="is:unread",
        provider_override="offline",
        gmail_service=mock_gmail,
        ai_service=ai_service,
    )

    mock_gmail.get_emails.assert_called_once_with(query="is:unread", max_results=3)


def test_e2e_demonstration_readonly_scope_constant():
    """Verify that GMAIL_READONLY_SCOPE is strictly the read-only scope string."""
    assert GMAIL_READONLY_SCOPE == "https://www.googleapis.com/auth/gmail.readonly"


def test_render_email_card_long_reasoning_no_truncation(capsys):
    """Verify that long reasoning text is word-wrapped without truncation or ellipsis."""
    long_reason = (
        "Rule-based heuristic match: High priority keyword 'unusual sign-in activity' "
        "detected in subject line, cross-referenced with security alert header classification. "
        "Immediate user password verification and security audit advised without delay."
    )
    email = EmailMessage(
        id="msg_test_001",
        sender="security@service.org",
        subject="Security Alert: Unusual sign-in activity detected",
        date="Mon, 13 Oct 2026 10:00:00 +0000",
        body_text="Action required: We noticed a login from an unrecognized device.",
    )
    analysis = EmailAnalysis(
        importance=ImportanceLevel.HIGH,
        summary="Urgent security notification regarding sign-in.",
        suggested_action="Review login history and reset credentials immediately.",
        confidence_score=0.98,
        reasoning=long_reason,
    )

    render_email_card(1, 1, email, analysis)

    captured = capsys.readouterr().out
    lines = [line for line in captured.splitlines() if line.strip()]

    # Verify no line truncation of the reasoning content
    for word in [
        "Rule-based", "heuristic", "unusual", "sign-in", "activity",
        "cross-referenced", "classification", "Immediate", "verification",
        "security", "audit", "advised", "without", "delay."
    ]:
        assert word in captured

    # Verify reasoning lines start with Reason: or proper indent
    reason_lines = [l for l in lines if "Reason:" in l or "cross-referenced" in l or "without delay" in l]
    assert len(reason_lines) >= 2  # Must be wrapped across multiple lines

    # Verify terminal box borders and consistent width
    for line in lines:
        assert len(line) == 80, f"Line length {len(line)} != 80: {line}"
        assert line.startswith("┌") or line.startswith("├") or line.startswith("└") or line.startswith("│")
        assert line.endswith("┐") or line.endswith("┤") or line.endswith("┘") or line.endswith("│")


def test_render_email_card_does_not_print_full_body_or_secrets(capsys):
    """Verify that full email body text and sensitive tokens are never exposed in terminal cards."""
    secret_body = "TOP_SECRET_PRIVATE_EMAIL_BODY_12345_NEVER_PRINT"
    email = EmailMessage(
        id="msg_secret_002",
        sender="confidential@corp.com",
        subject="Quarterly Strategy",
        date="Mon, 13 Oct 2026 10:00:00 +0000",
        body_text=secret_body,
    )
    analysis = EmailAnalysis(
        importance=ImportanceLevel.MEDIUM,
        summary="Quarterly strategic overview.",
        suggested_action="Review slide deck before meeting.",
        confidence_score=0.85,
        reasoning="Standard corporate update.",
    )

    render_email_card(1, 1, email, analysis)

    captured = capsys.readouterr().out
    assert secret_body not in captured
    assert "token" not in captured.lower()
    assert "credential" not in captured.lower()


def test_e2e_demonstration_preserves_full_reasoning_in_pipeline(capsys):
    """Verify that the end-to-end pipeline preserves and displays full reasoning text."""
    long_reason = (
        "Ollama local model deep analysis: sender is direct supervisor, "
        "topic requires urgent budget confirmation, and deadline is today at 5 PM."
    )
    email = EmailMessage(
        id="msg_e2e_reason",
        sender="manager@corp.com",
        subject="Urgent: Q3 Budget Deadline Today",
        date="Mon, 13 Oct 2026 10:15:00 +0000",
        body_text="Please submit your team budget before 5 PM today.",
    )

    mock_gmail = MagicMock(spec=GmailService)
    mock_gmail.get_emails.return_value = [email]

    mock_llm_provider = MagicMock(spec=LocalLLMProvider)
    mock_llm_provider.analyze.return_value = EmailAnalysis(
        importance=ImportanceLevel.HIGH,
        summary="Urgent budget submission due today.",
        suggested_action="Submit budget spreadsheet before 5 PM.",
        confidence_score=0.99,
        reasoning=long_reason,
    )

    settings = Settings(ai_provider="local")
    ai_service = AIService(provider=mock_llm_provider)

    exit_code = run_demonstration(
        limit=1,
        provider_override="local",
        settings=settings,
        gmail_service=mock_gmail,
        ai_service=ai_service,
    )

    assert exit_code == 0
    captured = capsys.readouterr().out

    # Complete reasoning must be intact across wrapped lines
    assert "Ollama local model deep analysis" in captured
    assert "direct supervisor" in captured
    assert "urgent budget confirmation" in captured
    assert "deadline is today" in captured
    assert "at 5 PM." in captured

