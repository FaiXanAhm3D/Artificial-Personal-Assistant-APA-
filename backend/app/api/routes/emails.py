"""
emails.py

FastAPI route handlers for email retrieval and local AI triage.

Endpoints:
    - GET  /emails                -> list recent emails (metadata summary only)
    - GET  /emails/{email_id}     -> get single email details (including bodies)
    - POST /emails/{email_id}/analyze -> triage and summarize email via local AI

Security and Privacy:
    - Strictly read-only operations.
    - Full email bodies are omitted from collection views.
    - Never communicates with cloud AI services.
    - Sanitizes error responses to prevent secret or filepath leakage.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from backend.app.api.deps import (
    get_ai_service,
    get_current_settings,
    get_gmail_service,
)
from backend.app.api.schemas import (
    AnalyzeRequest,
    EmailAnalysisResponse,
    EmailDetailResponse,
    EmailSummaryResponse,
)
from backend.app.core.config import Settings
from backend.app.domain.models import EmailMessage
from backend.app.services.ai.factory import get_ai_provider
from backend.app.services.ai_service import AIService
from backend.app.services.gmail_service import GmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["Emails"])

# Allowed AI providers for request overrides
ALLOWED_PROVIDERS = {"offline", "local", "ollama"}


@router.get(
    "",
    response_model=List[EmailSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List recent emails",
)
def list_emails(
    limit: int = Query(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of emails to retrieve (1-50)",
    ),
    query: str = Query(
        default="",
        description="Gmail search filter syntax (e.g., 'is:unread', 'from:alice@example.com')",
    ),
    gmail_service: GmailService = Depends(get_gmail_service),
) -> List[EmailSummaryResponse]:
    """
    Retrieves recent emails matching the search query.
    Returns structured metadata summaries without full message bodies.
    """
    try:
        messages: List[EmailMessage] = gmail_service.get_emails(
            query=query,
            max_results=limit,
        )
    except FileNotFoundError:
        logger.warning("Gmail credentials file missing during list_emails request.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Gmail credentials not configured or not found.",
        )
    except Exception as exc:
        err_msg = str(exc).lower()
        if "auth" in err_msg or "token" in err_msg or "credential" in err_msg:
            logger.warning("Gmail authentication error during list_emails.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Gmail authentication failed or token expired.",
            )
        logger.error("Upstream error during list_emails: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve emails from Gmail API.",
        )

    return [
        EmailSummaryResponse(
            id=msg.id,
            thread_id=msg.thread_id,
            message_id=msg.message_id,
            sender=msg.sender,
            recipient=msg.recipient,
            subject=msg.subject,
            date=msg.date,
            snippet=msg.snippet,
        )
        for msg in messages
    ]


@router.get(
    "/{email_id}",
    response_model=EmailDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single email details",
)
def get_email_detail(
    email_id: str = Path(
        ...,
        min_length=1,
        description="Unique Gmail message identifier",
    ),
    gmail_service: GmailService = Depends(get_gmail_service),
) -> EmailDetailResponse:
    """
    Retrieves full content for a single email by its unique ID.
    Includes extracted plain-text and HTML bodies.
    """
    clean_id = email_id.strip()
    if not clean_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email ID provided.",
        )

    try:
        msg: Optional[EmailMessage] = gmail_service.get_email(clean_id)
    except FileNotFoundError:
        logger.warning("Gmail credentials file missing during get_email_detail.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Gmail credentials not configured or not found.",
        )
    except Exception as exc:
        err_msg = str(exc).lower()
        if "auth" in err_msg or "token" in err_msg or "credential" in err_msg:
            logger.warning("Gmail authentication error during get_email_detail.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Gmail authentication failed or token expired.",
            )
        logger.error("Upstream error during get_email_detail: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve email from Gmail API.",
        )

    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email with ID '{clean_id}' not found.",
        )

    return EmailDetailResponse(
        id=msg.id,
        thread_id=msg.thread_id,
        message_id=msg.message_id,
        sender=msg.sender,
        recipient=msg.recipient,
        subject=msg.subject,
        date=msg.date,
        snippet=msg.snippet,
        body_text=msg.body_text,
        body_html=msg.body_html,
    )


@router.post(
    "/{email_id}/analyze",
    response_model=EmailAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze email importance and summary",
)
def analyze_email_endpoint(
    email_id: str = Path(
        ...,
        min_length=1,
        description="Unique Gmail message identifier",
    ),
    provider: Optional[str] = Query(
        default=None,
        description="Optional provider override ('offline' or 'local'/'ollama')",
    ),
    request_body: Optional[AnalyzeRequest] = None,
    gmail_service: GmailService = Depends(get_gmail_service),
    ai_service: AIService = Depends(get_ai_service),
    settings: Settings = Depends(get_current_settings),
) -> EmailAnalysisResponse:
    """
    Retrieves the specified email and generates an intelligence analysis
    (importance classification, factual summary, proposed action).
    Operates strictly offline or via loopback-only local LLM.
    """
    clean_id = email_id.strip()
    if not clean_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email ID provided.",
        )

    # 1. Determine and validate provider selection
    selected_provider_raw = (
        request_body.provider
        if request_body and request_body.provider
        else provider
    )

    active_provider_name: str
    target_ai_service: AIService

    if selected_provider_raw:
        cleaned_provider = selected_provider_raw.strip().lower()
        if cleaned_provider not in ALLOWED_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported AI provider '{selected_provider_raw}'. "
                    f"Supported providers: 'offline', 'local', 'ollama'."
                ),
            )
        # Normalize 'ollama' alias to 'local'
        normalized_provider = "local" if cleaned_provider == "ollama" else cleaned_provider
        active_provider_name = normalized_provider
        try:
            custom_provider = get_ai_provider(
                settings=settings,
                provider_override=normalized_provider,
            )
            target_ai_service = AIService(
                provider=custom_provider,
                settings=settings,
            )
        except Exception as exc:
            logger.error("Failed to initialize AI provider '%s': %s", normalized_provider, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to initialize requested AI provider '{normalized_provider}'.",
            )
    else:
        active_provider_name = settings.ai_provider
        target_ai_service = ai_service

    # 2. Fetch the target message
    try:
        msg: Optional[EmailMessage] = gmail_service.get_email(clean_id)
    except FileNotFoundError:
        logger.warning("Gmail credentials file missing during analyze_email.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Gmail credentials not configured or not found.",
        )
    except Exception as exc:
        err_msg = str(exc).lower()
        if "auth" in err_msg or "token" in err_msg or "credential" in err_msg:
            logger.warning("Gmail authentication error during analyze_email.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Gmail authentication failed or token expired.",
            )
        logger.error("Upstream error fetching email for analysis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve email from Gmail API.",
        )

    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email with ID '{clean_id}' not found.",
        )

    # 3. Perform AI analysis
    try:
        analysis = target_ai_service.analyze(msg)
    except Exception as exc:
        logger.error("AI provider failure during analysis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI analysis provider failed or timed out.",
        )

    return EmailAnalysisResponse(
        email_id=msg.id,
        importance=analysis.importance,
        summary=analysis.summary,
        suggested_action=analysis.suggested_action,
        confidence_score=analysis.confidence_score,
        reasoning=analysis.reasoning,
        provider_used=active_provider_name,
    )
