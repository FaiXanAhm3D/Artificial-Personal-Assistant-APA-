"""
Abstract base interface for AI and rule-based email analysis providers.

Defines the contract for summarizing emails, classifying importance, and
performing full structured analysis returning an EmailAnalysis domain model.
"""

from abc import ABC, abstractmethod
from backend.app.domain.models import EmailAnalysis, EmailMessage


class AIBaseProvider(ABC):
    """
    Abstract interface for email analysis providers.
    All providers (rule-based, local LLM, or mock) must adhere to this contract.
    """

    @abstractmethod
    def summarize(self, message: EmailMessage) -> str:
        """
        Generates a concise factual summary of the email message.

        Args:
            message: The validated EmailMessage domain object.

        Returns:
            A string summary (may be empty if message is empty).
        """
        pass

    @abstractmethod
    def classify_importance(self, message: EmailMessage) -> EmailAnalysis:
        """
        Evaluates the importance level of the email message.

        Args:
            message: The validated EmailMessage domain object.

        Returns:
            An EmailAnalysis instance containing the importance level and reasoning.
        """
        pass

    @abstractmethod
    def analyze(self, message: EmailMessage) -> EmailAnalysis:
        """
        Performs complete analysis of the email message, populating importance,
        summary, suggested action, and optional metadata.

        Args:
            message: The validated EmailMessage domain object.

        Returns:
            A validated EmailAnalysis domain model instance.
        """
        pass
