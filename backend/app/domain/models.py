"""
Core domain models for Project APA.

Contains pure data representations of retrieved email messages, AI analysis
results, and proposed outbound drafts.
Separated from connector implementations, HTTP transport, and AI inference.
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class ImportanceLevel(str, Enum):
    """Constrained priority levels for email triage."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EmailMessage(BaseModel):
    """
    Represents an email message retrieved from a provider.

    Encapsulates raw provider identifiers, message headers, and extracted content.
    Does not execute provider calls, parsing, or inference.
    """

    id: str = Field(..., min_length=1, description="Unique provider message identifier")
    thread_id: Optional[str] = Field(default=None, description="Conversation or thread identifier")
    message_id: Optional[str] = Field(default=None, description="RFC 2822 Message-ID header")
    sender: str = Field(..., min_length=1, description="Sender email address or header string")
    recipient: Optional[str] = Field(default=None, description="Recipient email address or header string")
    subject: str = Field(default="", description="Subject line; permits empty string")
    date: Optional[str] = Field(default=None, description="Timestamp or date header representation")
    body_text: str = Field(default="", description="Extracted plain-text body; permits empty string")
    body_html: Optional[str] = Field(default=None, description="Optional raw or sanitized HTML body")
    snippet: Optional[str] = Field(default=None, description="Optional short message preview")

    @field_validator("id", "sender")
    @classmethod
    def validate_non_whitespace(cls, v: str) -> str:
        """Ensure required identifiers are non-empty and not purely whitespace."""
        if not v or not v.strip():
            raise ValueError("Field must not be empty or whitespace only.")
        return v.strip()


class EmailAnalysis(BaseModel):
    """
    Represents APA's intelligence analysis of an email.

    Contains classification, summary, and non-executing suggested action.
    Independent of specific model architectures or inference providers.
    """

    importance: ImportanceLevel = Field(..., description="Constrained importance level (HIGH, MEDIUM, LOW)")
    summary: str = Field(default="", description="Concise summary; empty when unavailable")
    suggested_action: str = Field(
        default="",
        description="Description of next proposed action; informational only, never executed",
    )
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence score between 0.0 and 1.0",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Optional brief explanation for the importance assessment",
    )

    @field_validator("importance", mode="before")
    @classmethod
    def normalize_importance(cls, v: Any) -> Any:
        """Allow case-insensitive string values to map to ImportanceLevel."""
        if isinstance(v, str):
            v_cleaned = v.strip().upper()
            return v_cleaned
        return v


class EmailDraft(BaseModel):
    """
    Represents a proposed outbound email or reply draft.

    Maintains reply-thread metadata separately from ordinary message content.
    Does not send messages or invent message identifiers.
    """

    to: str = Field(..., min_length=1, description="Recipient email address")
    subject: str = Field(default="", description="Proposed subject line")
    body: str = Field(default="", description="Proposed email body text")
    thread_id: Optional[str] = Field(default=None, description="Provider thread ID for in-thread replies")
    in_reply_to: Optional[str] = Field(default=None, description="RFC 2822 Message-ID of the parent message")
    references: Optional[str] = Field(default=None, description="RFC 2822 References header value")

    @field_validator("to")
    @classmethod
    def validate_recipient(cls, v: str) -> str:
        """Ensure recipient address is non-empty and not purely whitespace."""
        if not v or not v.strip():
            raise ValueError("Recipient 'to' must not be empty or whitespace only.")
        return v.strip()

    @property
    def is_reply(self) -> bool:
        """Indicates whether this draft targets an existing thread or reply chain."""
        return bool(self.thread_id or self.in_reply_to)
