"""
Unit tests for GmailService connector and Gmail message parsing baseline.

Tests verify:
    - Decoding single-part and multipart payloads into EmailMessage
    - URL-safe base64 decoding with padding tolerances
    - Header extraction (Message-ID, From, To, Subject, Date, snippet)
    - Handling missing, whitespace, or malformed headers
    - HTML-to-text fallback when plain text is absent
    - Attachment-only and empty payloads
    - Central configuration integration
    - Mocked Gmail API get_email and get_emails execution (zero network calls)
"""

import base64
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from backend.app.core.config import Settings
from backend.app.domain.models import EmailMessage
from backend.app.services.gmail_service import (
    GmailService,
    HTMLTextExtractor,
    decode_base64_url_safe,
    extract_payload_bodies,
    parse_gmail_message,
)


def encode_b64(text: str) -> str:
    """Helper to encode text into URL-safe base64 string."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8")


# ----------------------------------------------------------------------
# 1. Payload Parsing and Domain Model Mapping Tests
# ----------------------------------------------------------------------


def test_parse_single_part_plain_text():
    """Verify single-part text/plain Gmail payload is correctly mapped to EmailMessage."""
    body_content = "Hello team,\nThis is a plain-text status update."
    b64_body = encode_b64(body_content)

    raw_message: Dict[str, Any] = {
        "id": "msg_001",
        "threadId": "thread_100",
        "snippet": "Hello team, This is a plain-text...",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "To", "value": "bob@example.com"},
                {"name": "Subject", "value": "Weekly Status Update"},
                {"name": "Date", "value": "Mon, 13 Oct 2026 09:30:00 +0000"},
                {"name": "Message-ID", "value": "<status-001@example.com>"},
            ],
            "body": {
                "size": len(body_content),
                "data": b64_body,
            },
        },
    }

    email = parse_gmail_message(raw_message)

    assert isinstance(email, EmailMessage)
    assert email.id == "msg_001"
    assert email.thread_id == "thread_100"
    assert email.message_id == "<status-001@example.com>"
    assert email.sender == "Alice <alice@example.com>"
    assert email.recipient == "bob@example.com"
    assert email.subject == "Weekly Status Update"
    assert email.date == "Mon, 13 Oct 2026 09:30:00 +0000"
    assert email.snippet == "Hello team, This is a plain-text..."
    assert email.body_text == body_content
    assert email.body_html is None


def test_parse_multipart_alternative_both_text_and_html():
    """Verify multipart/alternative payloads preserve both plain text and HTML bodies."""
    plain_text = "Please review the attached quarterly summary."
    html_text = "<p>Please review the <b>attached quarterly summary</b>.</p>"

    raw_message: Dict[str, Any] = {
        "id": "msg_002",
        "threadId": "thread_101",
        "snippet": "Please review the attached...",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "from", "value": "carol@example.com"},
                {"name": "to", "value": "dave@example.com"},
                {"name": "subject", "value": "Quarterly Summary"},
                {"name": "message-id", "value": "<summary-101@example.com>"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encode_b64(plain_text)},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": encode_b64(html_text)},
                },
            ],
        },
    }

    email = parse_gmail_message(raw_message)

    assert email.id == "msg_002"
    assert email.body_text == plain_text
    assert email.body_html == html_text
    assert email.sender == "carol@example.com"
    assert email.recipient == "dave@example.com"


def test_parse_html_only_fallback_extraction():
    """Verify that HTML-only messages populate body_html and extract clean body_text."""
    html_markup = """
    <html>
        <head><title>Notification</title></head>
        <style>body { font-family: sans-serif; }</style>
        <body>
            <h1>Project Milestone Reached</h1>
            <p>Phase 1 has successfully completed &amp; passed all checks.</p>
            <script>alert('unwanted');</script>
        </body>
    </html>
    """

    raw_message: Dict[str, Any] = {
        "id": "msg_003",
        "threadId": "thread_102",
        "payload": {
            "mimeType": "text/html",
            "headers": [
                {"name": "From", "value": "bot@automated.service"},
                {"name": "Subject", "value": "Milestone Reached"},
            ],
            "body": {"data": encode_b64(html_markup)},
        },
    }

    email = parse_gmail_message(raw_message)

    assert email.id == "msg_003"
    assert email.body_html == html_markup.strip()
    assert "Project Milestone Reached" in email.body_text
    assert "Phase 1 has successfully completed & passed all checks." in email.body_text
    # Script, style and head tags must be stripped from plain text fallback
    assert "unwanted" not in email.body_text
    assert "sans-serif" not in email.body_text
    assert "Notification" not in email.body_text


def test_parse_nested_multipart_mixed_with_attachment():
    """Verify recursive traversal across multipart/mixed and child multipart/alternative."""
    text_content = "Here is the report you requested."
    html_content = "<p>Here is the report you requested.</p>"

    raw_message: Dict[str, Any] = {
        "id": "msg_004",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "analyst@example.com"},
                {"name": "Subject", "value": "Report"},
            ],
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": encode_b64(text_content)},
                        },
                        {
                            "mimeType": "text/html",
                            "body": {"data": encode_b64(html_content)},
                        },
                    ],
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "quarterly_report.pdf",
                    "body": {"attachmentId": "att_999", "size": 1048576},
                },
            ],
        },
    }

    email = parse_gmail_message(raw_message)

    assert email.id == "msg_004"
    assert email.body_text == text_content
    assert email.body_html == html_content
    assert email.sender == "analyst@example.com"


def test_base64_urlsafe_and_unpadded_decoding():
    """Verify tolerance for unpadded base64 and standard URL-safe characters."""
    special_text = "Query test: ?param=value&flag=true"
    # Create urlsafe base64 with stripped '=' padding
    unpadded_b64 = base64.urlsafe_b64encode(special_text.encode("utf-8")).decode("utf-8").rstrip("=")

    decoded = decode_base64_url_safe(unpadded_b64)
    assert decoded == special_text

    raw_message: Dict[str, Any] = {
        "id": "msg_005",
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "From", "value": "tester@example.com"}],
            "body": {"data": unpadded_b64},
        },
    }
    email = parse_gmail_message(raw_message)
    assert email.body_text == special_text


def test_corrupted_base64_graceful_handling():
    """Verify corrupted or invalid base64 does not crash parsing."""
    corrupted_data = "!!!NOT_VALID_BASE64!!!"
    decoded = decode_base64_url_safe(corrupted_data)
    assert decoded == ""

    raw_message: Dict[str, Any] = {
        "id": "msg_006",
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "From", "value": "tester@example.com"}],
            "body": {"data": corrupted_data},
        },
    }
    email = parse_gmail_message(raw_message)
    assert email.body_text == ""


def test_missing_optional_headers():
    """Verify graceful defaults when optional headers (Subject, Date, To, Message-ID) are missing."""
    raw_message: Dict[str, Any] = {
        "id": "msg_007",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "known@example.com"},
            ],
            "body": {"data": encode_b64("Brief note")},
        },
    }

    email = parse_gmail_message(raw_message)

    assert email.id == "msg_007"
    assert email.sender == "known@example.com"
    assert email.subject == ""
    assert email.recipient is None
    assert email.date is None
    assert email.message_id is None
    assert email.thread_id is None
    assert email.snippet is None
    assert email.body_text == "Brief note"


def test_missing_or_empty_from_header_fallback():
    """Verify fallback to 'Unknown Sender' when From header is completely missing or whitespace."""
    raw_message_no_from: Dict[str, Any] = {
        "id": "msg_008_a",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Subject with no sender"},
            ],
        },
    }
    email_a = parse_gmail_message(raw_message_no_from)
    assert email_a.sender == "Unknown Sender"

    raw_message_whitespace_from: Dict[str, Any] = {
        "id": "msg_008_b",
        "payload": {
            "headers": [
                {"name": "From", "value": "   "},
            ],
        },
    }
    email_b = parse_gmail_message(raw_message_whitespace_from)
    assert email_b.sender == "Unknown Sender"


def test_empty_payload_and_missing_body():
    """Verify that messages with empty payload or missing body data return empty strings."""
    raw_message: Dict[str, Any] = {
        "id": "msg_009",
        "payload": {
            "headers": [{"name": "From", "value": "sender@example.com"}],
            "body": {},
        },
    }
    email = parse_gmail_message(raw_message)
    assert email.body_text == ""
    assert email.body_html is None


def test_attachment_only_message():
    """Verify that messages containing only binary attachments result in empty body text."""
    raw_message: Dict[str, Any] = {
        "id": "msg_010",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [{"name": "From", "value": "scanner@office.local"}],
            "parts": [
                {
                    "mimeType": "application/pdf",
                    "filename": "scan_doc.pdf",
                    "body": {"attachmentId": "att_001", "size": 54321},
                }
            ],
        },
    }
    email = parse_gmail_message(raw_message)
    assert email.body_text == ""
    assert email.body_html is None


def test_invalid_payload_raises_value_error():
    """Verify validation errors when payload is not a dict or lacks an ID."""
    with pytest.raises(ValueError, match="must be a dictionary"):
        parse_gmail_message(["not", "a", "dict"])  # type: ignore

    with pytest.raises(ValueError, match="missing required non-empty 'id'"):
        parse_gmail_message({"snippet": "no id present"})

    with pytest.raises(ValueError, match="missing required non-empty 'id'"):
        parse_gmail_message({"id": "   ", "snippet": "whitespace id"})


# ----------------------------------------------------------------------
# 2. GmailService Configuration Integration Tests
# ----------------------------------------------------------------------


def test_gmail_service_uses_central_settings():
    """Verify that GmailService anchors paths and scopes to central Settings."""
    custom_settings = Settings(
        gmail_credentials_file="custom_creds.json",
        gmail_token_file="custom_token.json",
        gmail_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )

    service = GmailService(settings=custom_settings)

    assert service.credentials_path == str(custom_settings.credentials_path)
    assert service.token_path == str(custom_settings.token_path)
    assert service.scopes == ["https://www.googleapis.com/auth/gmail.readonly"]


def test_gmail_service_explicit_path_overrides():
    """Verify that explicit arguments override settings defaults."""
    service = GmailService(
        credentials_path="explicit_creds.json",
        token_path="explicit_token.json",
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )

    assert service.credentials_path == "explicit_creds.json"
    assert service.token_path == "explicit_token.json"
    assert service.scopes == ["https://www.googleapis.com/auth/gmail.send"]


# ----------------------------------------------------------------------
# 3. GmailService API Method Tests (Mocked - Zero Network Calls)
# ----------------------------------------------------------------------


def test_get_email_successful_retrieval():
    """Verify GmailService.get_email fetches and parses a message via mocked API."""
    mock_api = MagicMock()
    mock_messages = mock_api.users.return_value.messages.return_value

    synthetic_payload = {
        "id": "remote_msg_100",
        "threadId": "th_100",
        "snippet": "Test email snippet",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "boss@company.com"},
                {"name": "Subject", "value": "Urgent Review"},
            ],
            "body": {"data": encode_b64("Please check this ASAP.")},
        },
    }
    mock_messages.get.return_value.execute.return_value = synthetic_payload

    service = GmailService(service=mock_api)
    result = service.get_email("remote_msg_100")

    assert result is not None
    assert isinstance(result, EmailMessage)
    assert result.id == "remote_msg_100"
    assert result.sender == "boss@company.com"
    assert result.subject == "Urgent Review"
    assert result.body_text == "Please check this ASAP."

    mock_messages.get.assert_called_once_with(
        userId="me", id="remote_msg_100", format="full"
    )


def test_get_email_not_found_returns_none():
    """Verify GmailService.get_email returns None on 404 HttpError."""
    mock_api = MagicMock()
    mock_messages = mock_api.users.return_value.messages.return_value

    # Simulate Google 404 response
    response_mock = MagicMock()
    response_mock.status = 404
    mock_messages.get.return_value.execute.side_effect = HttpError(
        resp=response_mock, content=b"Message not found"
    )

    service = GmailService(service=mock_api)
    result = service.get_email("nonexistent_id")

    assert result is None


def test_get_email_server_error_raises_runtime_error():
    """Verify GmailService.get_email raises RuntimeError on non-404 API error."""
    mock_api = MagicMock()
    mock_messages = mock_api.users.return_value.messages.return_value

    response_mock = MagicMock()
    response_mock.status = 500
    mock_messages.get.return_value.execute.side_effect = HttpError(
        resp=response_mock, content=b"Internal Server Error"
    )

    service = GmailService(service=mock_api)
    with pytest.raises(RuntimeError, match="Failed to fetch email"):
        service.get_email("error_id")


def test_get_emails_multiple_results():
    """Verify GmailService.get_emails lists and fetches multiple messages."""
    mock_api = MagicMock()
    mock_messages = mock_api.users.return_value.messages.return_value

    mock_messages.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}, {"id": "m2"}]
    }

    payload_1 = {
        "id": "m1",
        "payload": {
            "headers": [{"name": "From", "value": "user1@example.com"}],
            "body": {"data": encode_b64("Body 1")},
        },
    }
    payload_2 = {
        "id": "m2",
        "payload": {
            "headers": [{"name": "From", "value": "user2@example.com"}],
            "body": {"data": encode_b64("Body 2")},
        },
    }

    mock_messages.get.return_value.execute.side_effect = [payload_1, payload_2]

    service = GmailService(service=mock_api)
    emails = service.get_emails(query="is:unread", max_results=5)

    assert len(emails) == 2
    assert emails[0].id == "m1"
    assert emails[0].sender == "user1@example.com"
    assert emails[0].body_text == "Body 1"
    assert emails[1].id == "m2"
    assert emails[1].sender == "user2@example.com"
    assert emails[1].body_text == "Body 2"

    mock_messages.list.assert_called_once_with(
        userId="me", q="is:unread", maxResults=5
    )


def test_get_emails_empty_result():
    """Verify GmailService.get_emails returns empty list when no messages match query."""
    mock_api = MagicMock()
    mock_messages = mock_api.users.return_value.messages.return_value
    mock_messages.list.return_value.execute.return_value = {"messages": []}

    service = GmailService(service=mock_api)
    emails = service.get_emails(query="label:nonexistent")

    assert emails == []


def test_parse_message_convenience_static_method():
    """Verify GmailService.parse_message static method delegates to parse_gmail_message."""
    sample = {
        "id": "static_01",
        "payload": {
            "headers": [{"name": "From", "value": "static@example.com"}],
            "body": {"data": encode_b64("Testing static parse")},
        },
    }

    result = GmailService.parse_message(sample)
    assert isinstance(result, EmailMessage)
    assert result.id == "static_01"
    assert result.body_text == "Testing static parse"
