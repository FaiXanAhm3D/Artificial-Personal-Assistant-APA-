"""
schemas.py

Pydantic request and response schemas for Project APA's REST API.
Enforces strict response shapes without exposing sensitive tokens, credentials,
or unnecessary full email bodies in listing endpoints.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.models import ImportanceLevel


class HealthResponse(BaseModel):
    """
    Health check status response.
    Explicitly omits credential paths, machine info, or secrets.
    """

    status: str = Field(default="healthy", description="Service operational status")
    version: Optional[str] = Field(default=None, description="Application semantic version")
    ai_provider: str = Field(..., description="Currently configured AI provider name")
    read_only: bool = Field(default=True, description="Strict read-only operational mode flag")

    model_config = ConfigDict(extra="forbid")


class EmailSummaryResponse(BaseModel):
    """
    Structured email metadata for collection/listing views.
    Omits full email bodies to minimize overhead and privacy exposure.
    """

    id: str = Field(..., description="Provider unique message identifier")
    thread_id: Optional[str] = Field(default=None, description="Conversation or thread identifier")
    message_id: Optional[str] = Field(default=None, description="RFC 2822 Message-ID header")
    sender: str = Field(..., description="Sender address or header string")
    recipient: Optional[str] = Field(default=None, description="Recipient address or header string")
    subject: str = Field(default="", description="Email subject line")
    date: Optional[str] = Field(default=None, description="Timestamp or date header")
    snippet: Optional[str] = Field(default=None, description="Short preview snippet")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class EmailDetailResponse(BaseModel):
    """
    Detailed email view including extracted plain-text and HTML bodies.
    Returned only when specifically querying an individual message by ID.
    """

    id: str = Field(..., description="Provider unique message identifier")
    thread_id: Optional[str] = Field(default=None, description="Conversation or thread identifier")
    message_id: Optional[str] = Field(default=None, description="RFC 2822 Message-ID header")
    sender: str = Field(..., description="Sender address or header string")
    recipient: Optional[str] = Field(default=None, description="Recipient address or header string")
    subject: str = Field(default="", description="Email subject line")
    date: Optional[str] = Field(default=None, description="Timestamp or date header")
    snippet: Optional[str] = Field(default=None, description="Short preview snippet")
    body_text: str = Field(default="", description="Extracted plain-text body content")
    body_html: Optional[str] = Field(default=None, description="Optional raw or sanitized HTML body")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class AnalyzeRequest(BaseModel):
    """
    Optional request body for triggering email analysis.
    Permits selecting between approved local inference providers ('offline', 'local'/'ollama').
    """

    provider: Optional[str] = Field(
        default=None,
        description="Optional provider override ('offline' or 'local'/'ollama').",
    )

    model_config = ConfigDict(extra="forbid")


class EmailAnalysisResponse(BaseModel):
    """
    Structured outcome of local AI email triage and summarization.
    """

    email_id: str = Field(..., description="Target email message identifier")
    importance: ImportanceLevel = Field(..., description="Assessed importance level (HIGH, MEDIUM, LOW)")
    summary: str = Field(default="", description="Concise summary of email content")
    suggested_action: str = Field(
        default="",
        description="Proposed non-executing next step or recommended action",
    )
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Brief explanation of the importance assessment",
    )
    provider_used: Optional[str] = Field(
        default=None,
        description="Name of the AI provider that generated this analysis",
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid")
