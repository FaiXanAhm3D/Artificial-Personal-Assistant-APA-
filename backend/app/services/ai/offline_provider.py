"""
Deterministic offline rule-based email analysis provider.

Implements explicit, documented keyword and pattern matching heuristics
for triage and extractive summarization. Does not execute model inference,
does not contact external networks, does not alter messages, and does not
claim heuristic outputs are machine-learning predictions.
"""

import re
from typing import List, Optional, Set, Tuple

from backend.app.domain.models import EmailAnalysis, EmailMessage, ImportanceLevel
from backend.app.services.ai.base import AIBaseProvider

# Documented heuristic keyword dictionaries
HIGH_PRIORITY_KEYWORDS: Set[str] = {
    "urgent",
    "asap",
    "deadline",
    "emergency",
    "action required",
    "security alert",
    "critical",
    "important notice",
    "due date",
    "immediate attention",
    "high priority",
    "account suspended",
    "verification required",
    "exam schedule",
}

LOW_PRIORITY_KEYWORDS: Set[str] = {
    "unsubscribe",
    "newsletter",
    "sale",
    "discount",
    "promotional",
    "special offer",
    "digest",
    "weekly update",
    "advertisement",
    "no-reply",
    "noreply",
    "marketing",
    "webinar",
    "order confirmation",
    "receipt",
}


class OfflineRuleBasedProvider(AIBaseProvider):
    """
    Deterministic rule-based baseline provider.

    Rules:
        1. Empty content: If both subject and body_text are empty, classifies as LOW,
           produces an empty summary, and descriptive verification action.
        2. High priority: If subject or body contains any HIGH_PRIORITY_KEYWORDS,
           classifies as HIGH with immediate review action.
        3. Low priority: If subject or body contains any LOW_PRIORITY_KEYWORDS,
           classifies as LOW with archiving/read-at-convenience action.
        4. Medium priority (default): Regular correspondence without high or low triggers
           classifies as MEDIUM with standard read/respond action.

    Note on confidence_score:
        confidence_score is intentionally left as None to explicitly document that
        classifications are deterministic heuristics, not probabilistic model predictions.
    """

    def __init__(
        self,
        high_keywords: Optional[Set[str]] = None,
        low_keywords: Optional[Set[str]] = None,
    ):
        self.high_keywords = high_keywords or HIGH_PRIORITY_KEYWORDS
        self.low_keywords = low_keywords or LOW_PRIORITY_KEYWORDS

    def summarize(self, message: EmailMessage) -> str:
        """
        Produces an extractive summary of the email message.
        Extracts up to the first 2 informative sentences or 200 characters.
        Returns empty string if no content exists.
        """
        body = (message.body_text or "").strip()
        subject = (message.subject or "").strip()

        if not body:
            if subject:
                return f"Subject: {subject}"
            return ""

        # Normalize whitespace
        cleaned = re.sub(r"\s+", " ", body)

        # Extract first 1 or 2 sentences
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        if sentences and sentences[0]:
            candidate = sentences[0]
            if len(candidate) < 100 and len(sentences) > 1:
                candidate = f"{candidate} {sentences[1]}"
            if len(candidate) > 200:
                candidate = candidate[:197] + "..."
            return candidate.strip()

        return cleaned[:200].strip()

    def _match_keywords(self, text: str, keywords: Set[str]) -> List[str]:
        text_lower = text.lower()
        matched = []
        for kw in sorted(keywords):
            # Check word boundary matching for keywords
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, text_lower):
                matched.append(kw)
        return matched

    def classify_importance(self, message: EmailMessage) -> EmailAnalysis:
        """Evaluates importance level using explicit rules."""
        subject = (message.subject or "").strip()
        body = (message.body_text or "").strip()
        full_text = f"{subject} {body}".strip()

        # Rule 1: Empty or minimal message
        if not full_text:
            return EmailAnalysis(
                importance=ImportanceLevel.LOW,
                summary="",
                suggested_action="Verify sender authenticity if unexpected.",
                confidence_score=None,
                reasoning="Rule-based heuristic: Message contains neither subject nor body content.",
            )

        # Rule 2: High priority keywords
        high_matches = self._match_keywords(full_text, self.high_keywords)
        if high_matches:
            matched_str = ", ".join(high_matches)
            return EmailAnalysis(
                importance=ImportanceLevel.HIGH,
                summary=self.summarize(message),
                suggested_action="Review immediately and address time-sensitive items.",
                confidence_score=None,
                reasoning=f"Rule-based heuristic: High-priority trigger detected ({matched_str}).",
            )

        # Rule 3: Low priority keywords
        low_matches = self._match_keywords(full_text, self.low_keywords)
        if low_matches:
            matched_str = ", ".join(low_matches)
            return EmailAnalysis(
                importance=ImportanceLevel.LOW,
                summary=self.summarize(message),
                suggested_action="Archive or review at convenience.",
                confidence_score=None,
                reasoning=f"Rule-based heuristic: Promotional or informational trigger detected ({matched_str}).",
            )

        # Rule 4: Default Medium priority
        return EmailAnalysis(
            importance=ImportanceLevel.MEDIUM,
            summary=self.summarize(message),
            suggested_action="Read and respond as appropriate.",
            confidence_score=None,
            reasoning="Rule-based heuristic: Standard correspondence (no high-priority or promotional triggers).",
        )

    def analyze(self, message: EmailMessage) -> EmailAnalysis:
        """Full deterministic analysis delegating to classify_importance."""
        return self.classify_importance(message)
