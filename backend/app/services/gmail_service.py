"""
gmail_service.py

Single-responsibility connector and service wrapper around the Gmail API.

Responsibilities:
    - authenticate()     -> handles OAuth2 login and token refresh
    - parse_message()    -> decodes raw Gmail API payload into EmailMessage domain model
    - get_email()        -> fetches single email by ID and converts to EmailMessage
    - get_emails()       -> lists/fetches emails by query and converts to List[EmailMessage]
    - send_email()       -> sends outbound email message via Gmail API

Decoupled from AI inference and CLI presentation. Anchored to central settings.
"""

import base64
import binascii
import html
import os
from email.mime.text import MIMEText
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from backend.app.core.config import Settings, get_settings
from backend.app.domain.models import EmailMessage


class HTMLTextExtractor(HTMLParser):
    """
    Parses and strips HTML markup into clean, normalized plain text.
    Ignores non-content elements (script, style, head, meta) and translates
    block-level tags to appropriate line breaks.
    """

    def __init__(self):
        super().__init__()
        self.text_parts: List[str] = []
        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list):
        tag_lower = tag.lower()
        if tag_lower in ("script", "style", "head", "meta", "title"):
            self._ignore_depth += 1
        elif tag_lower in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote"):
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in ("script", "style", "head", "meta", "title"):
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
        elif tag_lower in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote"):
            self.text_parts.append("\n")

    def handle_data(self, data: str):
        if self._ignore_depth == 0:
            self.text_parts.append(data)

    def get_text(self) -> str:
        """Returns decoded and whitespace-normalized plain text."""
        raw_text = "".join(self.text_parts)
        unescaped = html.unescape(raw_text)
        lines = [line.strip() for line in unescaped.splitlines()]
        cleaned_lines: List[str] = []
        prev_blank = False
        for line in lines:
            if line:
                cleaned_lines.append(line)
                prev_blank = False
            elif not prev_blank:
                cleaned_lines.append("")
                prev_blank = True
        return "\n".join(cleaned_lines).strip()


def decode_base64_url_safe(data: Optional[str]) -> str:
    """
    Decodes URL-safe Base64 encoded strings, with resilience against missing
    padding characters ('=') and character set substitutions.
    """
    if not data:
        return ""

    cleaned = data.strip().replace("-", "+").replace("_", "/")
    pad_needed = 4 - (len(cleaned) % 4)
    if pad_needed < 4:
        cleaned += "=" * pad_needed

    try:
        decoded_bytes = base64.b64decode(cleaned, validate=True)
        return decoded_bytes.decode("utf-8", errors="replace")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return ""


def extract_payload_bodies(payload: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """
    Recursively extracts plain text and HTML bodies from a Gmail message payload.

    Handles:
        - Single-part plain text or HTML
        - Nested multipart/alternative, multipart/mixed, multipart/related
        - Payloads with missing or default mimeType
        - HTML fallback conversion when plain text is absent
    """
    text_parts: List[str] = []
    html_parts: List[str] = []

    def _walk_parts(part: Dict[str, Any]):
        mime = str(part.get("mimeType", "")).lower()
        body_dict = part.get("body", {})
        body_data = body_dict.get("data") if isinstance(body_dict, dict) else None

        if body_data:
            if mime == "text/html":
                decoded = decode_base64_url_safe(body_data)
                if decoded:
                    html_parts.append(decoded)
            elif mime == "text/plain" or not mime or mime.startswith("text/"):
                decoded = decode_base64_url_safe(body_data)
                if decoded:
                    text_parts.append(decoded)

        # Recursively process child parts if present
        subparts = part.get("parts")
        if isinstance(subparts, list):
            for subpart in subparts:
                if isinstance(subpart, dict):
                    _walk_parts(subpart)

    _walk_parts(payload)

    combined_text = "\n\n".join(tp.strip() for tp in text_parts if tp.strip())
    combined_html = "\n".join(hp.strip() for hp in html_parts if hp.strip()) or None

    # HTML fallback if no plain text part was discovered
    if not combined_text and combined_html:
        extractor = HTMLTextExtractor()
        extractor.feed(combined_html)
        combined_text = extractor.get_text()

    return combined_text, combined_html


def parse_gmail_message(message: Dict[str, Any]) -> EmailMessage:
    """
    Converts a raw Gmail API message dictionary into a validated EmailMessage domain object.

    Extracts:
        - id: Provider unique message ID
        - thread_id: Conversation thread ID
        - message_id: RFC 2822 Message-ID header
        - sender: From header (with fallback to 'Unknown Sender' for malformed inputs)
        - recipient: To header
        - subject: Subject header (defaults to empty string)
        - date: Date header
        - snippet: Message snippet preview
        - body_text: Plain-text body (or HTML-fallback extracted text)
        - body_html: HTML body if present
    """
    if not isinstance(message, dict):
        raise ValueError("Gmail message payload must be a dictionary.")

    raw_id = message.get("id")
    if not raw_id or not str(raw_id).strip():
        raise ValueError("Gmail message payload missing required non-empty 'id'.")
    msg_id = str(raw_id).strip()

    raw_thread_id = message.get("threadId")
    thread_id = str(raw_thread_id).strip() if raw_thread_id else None

    raw_snippet = message.get("snippet")
    snippet = str(raw_snippet) if raw_snippet is not None else None

    payload = message.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    headers_list = payload.get("headers")
    headers: Dict[str, str] = {}
    if isinstance(headers_list, list):
        for h in headers_list:
            if isinstance(h, dict) and "name" in h:
                name_key = str(h["name"]).strip().lower()
                val = str(h.get("value", "")).strip()
                headers[name_key] = val

    message_id = headers.get("message-id") or None
    subject = headers.get("subject", "")
    date = headers.get("date") or None
    recipient = headers.get("to") or None

    sender = headers.get("from")
    if not sender or not sender.strip():
        sender = "Unknown Sender"
    else:
        sender = sender.strip()

    body_text, body_html = extract_payload_bodies(payload)

    return EmailMessage(
        id=msg_id,
        thread_id=thread_id,
        message_id=message_id,
        sender=sender,
        recipient=recipient,
        subject=subject,
        date=date,
        body_text=body_text,
        body_html=body_html,
        snippet=snippet,
    )


class GmailService:
    """
    Handles all interactions with the Gmail API, abstracting network operations
    and returning typed domain models.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        credentials_path: Optional[str | Path] = None,
        token_path: Optional[str | Path] = None,
        scopes: Optional[List[str]] = None,
        service: Optional[Any] = None,
    ):
        self.settings = settings or get_settings()
        self.credentials_path = str(
            credentials_path or self.settings.credentials_path
        )
        self.token_path = str(
            token_path or self.settings.token_path
        )
        self.scopes = scopes or self.settings.gmail_scopes
        self._service: Optional[Resource] = service

    def authenticate(self) -> None:
        """
        Authenticates with Gmail using OAuth2.

        Loads cached credentials from token_path if present and valid,
        refreshes them if expired, or runs the interactive OAuth flow
        if no valid credentials exist. Builds the underlying Gmail API
        client and stores it on self._service.
        """
        creds: Optional[Credentials] = None

        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, self.scopes)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"OAuth client credentials file not found at: '{self.credentials_path}'. "
                        f"Please place your 'credentials.json' from Google Cloud Console at this location."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, self.scopes
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        self._service = build("gmail", "v1", credentials=creds)

    def _ensure_authenticated(self) -> None:
        if self._service is None:
            self.authenticate()

    @staticmethod
    def parse_message(message: Dict[str, Any]) -> EmailMessage:
        """Convenience method to parse a raw Gmail message dict into an EmailMessage."""
        return parse_gmail_message(message)

    # ------------------------------------------------------------------ #
    # Fetching emails
    # ------------------------------------------------------------------ #
    def get_emails(
        self,
        query: str = "",
        max_results: int = 10,
        user_id: str = "me",
    ) -> List[EmailMessage]:
        """
        Fetches a list of emails matching a Gmail search query.

        Args:
            query: Gmail search syntax, e.g. "is:unread", "from:someone@example.com".
                   Empty string returns the most recent emails.
            max_results: Maximum number of emails to return.
            user_id: Gmail user id ("me" refers to the authenticated user).

        Returns:
            A list of EmailMessage domain model instances.
        """
        self._ensure_authenticated()

        try:
            response = (
                self._service.users()
                .messages()
                .list(userId=user_id, q=query, maxResults=max_results)
                .execute()
            )
        except HttpError as error:
            raise RuntimeError(f"Failed to list emails: {error}") from error

        message_refs = response.get("messages", [])
        if not message_refs:
            return []

        emails: List[EmailMessage] = []
        for ref in message_refs:
            msg_id = ref.get("id")
            if msg_id:
                email = self.get_email(msg_id, user_id=user_id)
                if email:
                    emails.append(email)
        return emails

    def get_email(self, email_id: str, user_id: str = "me") -> Optional[EmailMessage]:
        """
        Retrieves the full content of a single email by its id and converts it
        into an EmailMessage domain model.

        Args:
            email_id: The Gmail message id.
            user_id: Gmail user id ("me" refers to the authenticated user).

        Returns:
            An EmailMessage instance, or None if not found (404).
        """
        self._ensure_authenticated()

        try:
            message = (
                self._service.users()
                .messages()
                .get(userId=user_id, id=email_id, format="full")
                .execute()
            )
        except HttpError as error:
            if getattr(error, "resp", None) and getattr(error.resp, "status", None) == 404:
                return None
            raise RuntimeError(f"Failed to fetch email {email_id}: {error}") from error
        except Exception as error:
            if "404" in str(error):
                return None
            raise RuntimeError(f"Failed to fetch email {email_id}: {error}") from error

        if not message:
            return None

        return parse_gmail_message(message)

    # ------------------------------------------------------------------ #
    # Sending emails (preserves existing implementation)
    # ------------------------------------------------------------------ #
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        user_id: str = "me",
    ) -> Dict[str, Any]:
        """
        Sends an email via Gmail API.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Plain text email body.
            user_id: Gmail user id ("me" refers to the authenticated user).

        Returns:
            The Gmail API response dict for the sent message (contains id, threadId).
        """
        self._ensure_authenticated()

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("UTF-8")

        try:
            sent = (
                self._service.users()
                .messages()
                .send(userId=user_id, body={"raw": raw_message})
                .execute()
            )
        except HttpError as error:
            raise RuntimeError(f"Failed to send email: {error}") from error

        return sent
