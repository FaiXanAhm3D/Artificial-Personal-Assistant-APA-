"""
Automated unit tests for Project APA domain models.
Verifies EmailMessage, EmailAnalysis, and EmailDraft using synthetic test fixtures.
"""

import pytest
from pydantic import ValidationError

from backend.app.domain.models import (
    EmailAnalysis,
    EmailDraft,
    EmailMessage,
    ImportanceLevel,
)


# ====================================================================
# EmailMessage Tests
# ====================================================================

def test_email_message_valid_full():
    """Verify construction of EmailMessage with all fields populated."""
    msg = EmailMessage(
        id="msg_abc123",
        thread_id="thread_xyz789",
        message_id="<cad123@mail.example.com>",
        sender="prof.smith@university.edu",
        recipient="student@university.edu",
        subject="Midterm Exam Schedule",
        date="2026-10-12T10:30:00Z",
        body_text="Midterm exams will be held next Tuesday in Room 402.",
        body_html="<p>Midterm exams will be held next Tuesday in Room 402.</p>",
        snippet="Midterm exams will be held next Tuesday...",
    )

    assert msg.id == "msg_abc123"
    assert msg.thread_id == "thread_xyz789"
    assert msg.message_id == "<cad123@mail.example.com>"
    assert msg.sender == "prof.smith@university.edu"
    assert msg.recipient == "student@university.edu"
    assert msg.subject == "Midterm Exam Schedule"
    assert msg.date == "2026-10-12T10:30:00Z"
    assert msg.body_text.startswith("Midterm exams")
    assert msg.body_html.startswith("<p>")
    assert msg.snippet.startswith("Midterm")


def test_email_message_missing_optional_metadata():
    """Verify construction with only required fields (id and sender)."""
    msg = EmailMessage(
        id="msg_minimal",
        sender="notifications@service.com",
    )

    assert msg.id == "msg_minimal"
    assert msg.sender == "notifications@service.com"
    assert msg.thread_id is None
    assert msg.message_id is None
    assert msg.recipient is None
    assert msg.subject == ""
    assert msg.date is None
    assert msg.body_text == ""
    assert msg.body_html is None
    assert msg.snippet is None


def test_email_message_empty_subject_and_body():
    """Verify that an email with empty subject and empty body does not crash."""
    msg = EmailMessage(
        id="msg_empty_content",
        sender="automated@system.net",
        subject="",
        body_text="",
    )

    assert msg.subject == ""
    assert msg.body_text == ""


@pytest.mark.parametrize(
    "invalid_kwargs, expected_field",
    [
        ({"sender": "user@example.com"}, "id"),  # missing id
        ({"id": "msg_001"}, "sender"),  # missing sender
        ({"id": "", "sender": "user@example.com"}, "id"),  # empty id
        ({"id": "   ", "sender": "user@example.com"}, "id"),  # whitespace id
        ({"id": "msg_001", "sender": ""}, "sender"),  # empty sender
        ({"id": "msg_001", "sender": "   "}, "sender"),  # whitespace sender
    ],
)
def test_email_message_rejection_of_malformed_required_fields(invalid_kwargs, expected_field):
    """Verify rejection when required fields are missing or whitespace-only."""
    with pytest.raises(ValidationError) as exc_info:
        EmailMessage(**invalid_kwargs)

    errors = exc_info.value.errors()
    assert any(expected_field in e["loc"] for e in errors)


# ====================================================================
# EmailAnalysis Tests
# ====================================================================

@pytest.mark.parametrize(
    "importance_input, expected_enum",
    [
        (ImportanceLevel.HIGH, ImportanceLevel.HIGH),
        (ImportanceLevel.MEDIUM, ImportanceLevel.MEDIUM),
        (ImportanceLevel.LOW, ImportanceLevel.LOW),
        ("HIGH", ImportanceLevel.HIGH),
        ("MEDIUM", ImportanceLevel.MEDIUM),
        ("LOW", ImportanceLevel.LOW),
        ("high", ImportanceLevel.HIGH),  # case-insensitive normalization
        ("medium", ImportanceLevel.MEDIUM),
        ("low", ImportanceLevel.LOW),
    ],
)
def test_email_analysis_valid_importance_levels(importance_input, expected_enum):
    """Verify valid construction for all three supported importance levels."""
    analysis = EmailAnalysis(
        importance=importance_input,
        summary="Automated status alert.",
        suggested_action="Review and archive",
        confidence_score=0.95,
        reasoning="Routine notification detected.",
    )

    assert analysis.importance == expected_enum
    assert analysis.summary == "Automated status alert."
    assert analysis.suggested_action == "Review and archive"
    assert analysis.confidence_score == 0.95
    assert analysis.reasoning == "Routine notification detected."


@pytest.mark.parametrize(
    "invalid_importance",
    [
        "CRITICAL",
        "URGENT",
        "SPAM",
        "NONE",
        "",
        123,
        None,
    ],
)
def test_email_analysis_rejection_of_unsupported_importance(invalid_importance):
    """Verify that unsupported or invalid importance values raise a ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        EmailAnalysis(importance=invalid_importance, summary="Test summary")

    errors = exc_info.value.errors()
    assert any("importance" in e["loc"] for e in errors)


def test_email_analysis_empty_summary_and_action():
    """Verify that empty summary and suggested action are permitted when unavailable."""
    analysis = EmailAnalysis(importance="LOW")

    assert analysis.importance == ImportanceLevel.LOW
    assert analysis.summary == ""
    assert analysis.suggested_action == ""
    assert analysis.confidence_score is None


# ====================================================================
# EmailDraft Tests
# ====================================================================

def test_email_draft_with_threading_metadata():
    """Verify valid EmailDraft targeted as an in-thread reply."""
    draft = EmailDraft(
        to="prof.smith@university.edu",
        subject="Re: Midterm Exam Schedule",
        body="Thank you, I will be attending Room 402.",
        thread_id="thread_xyz789",
        in_reply_to="<cad123@mail.example.com>",
        references="<cad123@mail.example.com>",
    )

    assert draft.to == "prof.smith@university.edu"
    assert draft.subject == "Re: Midterm Exam Schedule"
    assert draft.body.startswith("Thank you")
    assert draft.thread_id == "thread_xyz789"
    assert draft.in_reply_to == "<cad123@mail.example.com>"
    assert draft.references == "<cad123@mail.example.com>"
    assert draft.is_reply is True


def test_email_draft_without_threading_metadata():
    """Verify valid standalone EmailDraft with no thread references."""
    draft = EmailDraft(
        to="advisor@university.edu",
        subject="Inquiry regarding course selection",
        body="Dear Advisor, I would like to schedule a meeting.",
    )

    assert draft.to == "advisor@university.edu"
    assert draft.subject == "Inquiry regarding course selection"
    assert draft.thread_id is None
    assert draft.in_reply_to is None
    assert draft.references is None
    assert draft.is_reply is False


@pytest.mark.parametrize(
    "invalid_to",
    [
        "",
        "   ",
        None,
    ],
)
def test_email_draft_rejection_of_invalid_recipient(invalid_to):
    """Verify that draft construction fails when recipient is empty or whitespace."""
    with pytest.raises(ValidationError) as exc_info:
        EmailDraft(to=invalid_to, subject="Test", body="Body text")

    errors = exc_info.value.errors()
    assert any("to" in e["loc"] for e in errors)


# ====================================================================
# Serialization and Round-Trip Tests
# ====================================================================

def test_models_serialization_and_round_trip():
    """Verify that models serialize to dict/JSON and reconstruct accurately."""
    # 1. EmailMessage round-trip
    original_msg = EmailMessage(
        id="round_1",
        thread_id="t_1",
        sender="sender@test.com",
        recipient="receiver@test.com",
        subject="Round-trip Test",
        body_text="Checking serialization fidelity.",
    )
    dumped_dict = original_msg.model_dump()
    reconstructed_msg = EmailMessage.model_validate(dumped_dict)
    assert reconstructed_msg == original_msg

    json_str = original_msg.model_dump_json()
    reconstructed_from_json = EmailMessage.model_validate_json(json_str)
    assert reconstructed_from_json == original_msg

    # 2. EmailAnalysis round-trip
    original_analysis = EmailAnalysis(
        importance="HIGH",
        summary="High-priority alert",
        suggested_action="Review immediately",
        confidence_score=0.98,
    )
    analysis_dict = original_analysis.model_dump()
    reconstructed_analysis = EmailAnalysis.model_validate(analysis_dict)
    assert reconstructed_analysis == original_analysis

    # 3. EmailDraft round-trip
    original_draft = EmailDraft(
        to="contact@service.com",
        subject="Draft Round-trip",
        body="Draft content.",
        thread_id="thread_99",
    )
    draft_dict = original_draft.model_dump()
    reconstructed_draft = EmailDraft.model_validate(draft_dict)
    assert reconstructed_draft == original_draft
