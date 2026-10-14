"""
main.py — Project APA (Artificial Personal Assistant)
Unified entry point for end-to-end Gmail triage demonstration.

Connects:
    1. Read-only Gmail API connector (OAuth2 Desktop App flow)
    2. Strongly-typed EmailMessage domain model conversion
    3. Modular local AI triage (Local Ollama / Deterministic Offline Heuristic)
    4. Structured, readable terminal demonstration output

Privacy and Safety Guarantees:
    - Scope is strictly read-only: https://www.googleapis.com/auth/gmail.readonly
    - Never modifies, deletes, archives, sends, or labels any email.
    - Never transmits email content to hosted or cloud AI APIs.
    - Never prints full raw bodies, tokens, or client credentials to logs.
"""

import argparse
import os
import sys
import textwrap
from typing import List, Optional

if sys.platform == "win32":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.app.core.config import Settings, get_settings
from backend.app.domain.models import EmailAnalysis, EmailMessage, ImportanceLevel
from backend.app.services.ai_service import AIService
from backend.app.services.gmail_service import GmailService

# Read-only Gmail scope required for demonstration
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def print_banner(settings: Settings, scope: str) -> None:
    """Displays the application security and configuration banner."""
    print("=" * 80)
    print("  PROJECT APA — Artificial Personal Assistant")
    print("  End-to-End Gmail Demonstration & Local Triage Pipeline")
    print("=" * 80)
    print(f"  • Gmail Scope:     {scope} (STRICTLY READ-ONLY)")
    print(f"  • AI Provider:     {settings.ai_provider.upper()} ", end="")
    if settings.ai_provider == "local":
        print(f"({settings.local_model_name} @ {settings.local_llm_url})")
    else:
        print("(Deterministic Rule-Based Heuristic Baseline)")
    print(f"  • Privacy:         Localhost only — zero cloud AI calls — zero data exfiltration")
    print("=" * 80)
    print()


def print_credentials_help(credentials_path: str) -> None:
    """Prints friendly, actionable instructions when credentials.json is missing."""
    print()
    print("[!] ACTION REQUIRED: Gmail OAuth Credentials Not Found")
    print("-" * 80)
    print("Project APA requires OAuth 2.0 Client credentials to connect to Gmail.")
    print()
    print("Follow these 7 quick steps to set up your free Google Cloud credentials:")
    print("  1. Visit Google Cloud Console: https://console.cloud.google.com/")
    print("  2. Create a new project (e.g., 'Project APA').")
    print("  3. Navigate to 'APIs & Services' -> 'Library' and enable 'Gmail API'.")
    print("  4. Go to 'OAuth consent screen':")
    print("       - Select User Type: 'External'")
    print("       - Fill in app name ('Project APA') and your email")
    print("       - Add your Gmail address under 'Test users'")
    print("  5. Go to 'Credentials' -> 'Create Credentials' -> 'OAuth client ID':")
    print("       - Application type: 'Desktop app'")
    print("       - Name: 'APA Desktop Client'")
    print("  6. Click 'Download JSON' and rename the downloaded file to:")
    print("       credentials.json")
    print(f"  7. Place 'credentials.json' at:")
    print(f"       {credentials_path}")
    print()
    print("After placing 'credentials.json', re-run: python main.py")
    print("-" * 80)
    print()


def render_email_card(index: int, total: int, email: EmailMessage, analysis: EmailAnalysis) -> None:
    """Renders a structured, visually appealing terminal card for an analyzed email."""
    # Priority badge formatting
    priority_badges = {
        ImportanceLevel.HIGH: "[HIGH PRIORITY]",
        ImportanceLevel.MEDIUM: "[MEDIUM PRIORITY]",
        ImportanceLevel.LOW: "[LOW PRIORITY]",
    }
    badge = priority_badges.get(analysis.importance, f"[{analysis.importance}]")

    border = "─" * 78
    print(f"┌{border}┐")
    header_info = f"Email {index} of {total}"
    id_info = f"ID: {email.id}"
    if len(id_info) > 55:
        id_info = id_info[:52] + "..."
    header_line = f"{header_info:<18}│  {id_info}"
    print(f"│ {header_line:<76} │")
    print(f"├{border}┤")

    from_text = f"From:     {email.sender}"
    if len(from_text) > 76:
        from_text = from_text[:73] + "..."
    print(f"│ {from_text:<76} │")

    subj_text = f"Subject:  {email.subject or '(No Subject)'}"
    if len(subj_text) > 76:
        subj_text = subj_text[:73] + "..."
    print(f"│ {subj_text:<76} │")

    date_text = f"Date:     {email.date or 'Unknown Date'}"
    if len(date_text) > 76:
        date_text = date_text[:73] + "..."
    print(f"│ {date_text:<76} │")

    triage_text = f"Triage:   {badge}"
    print(f"│ {triage_text:<76} │")

    if analysis.reasoning:
        # Wrap reasoning across multiple lines without truncating content
        wrapped_reason = textwrap.wrap(
            analysis.reasoning.strip(),
            width=76,
            initial_indent="Reason:   ",
            subsequent_indent="          ",
            break_long_words=True,
        )
        for r_line in wrapped_reason:
            print(f"│ {r_line:<76} │")

    print(f"├{border}┤")
    print(f"│ Summary:                                                                     │")
    summary_text = analysis.summary or "(No summary available)"
    wrapped_summary = textwrap.wrap(
        summary_text.strip(),
        width=76,
        initial_indent="  ",
        subsequent_indent="  ",
        break_long_words=True,
    )
    for s_line in wrapped_summary:
        print(f"│ {s_line:<76} │")

    print(f"│                                                                              │")
    print(f"│ Suggested Action:                                                            │")
    action_text = analysis.suggested_action or "None"
    wrapped_action = textwrap.wrap(
        action_text.strip(),
        width=76,
        initial_indent="  → ",
        subsequent_indent="    ",
        break_long_words=True,
    )
    for a_line in wrapped_action:
        print(f"│ {a_line:<76} │")
    print(f"└{border}┘")
    print()


def render_batch_summary(total: int, analyses: List[EmailAnalysis], provider_name: str) -> None:
    """Renders the summary dashboard for the analyzed batch."""
    high_count = sum(1 for a in analyses if a.importance == ImportanceLevel.HIGH)
    med_count = sum(1 for a in analyses if a.importance == ImportanceLevel.MEDIUM)
    low_count = sum(1 for a in analyses if a.importance == ImportanceLevel.LOW)

    print("=" * 80)
    print("  BATCH TRIAGE SUMMARY")
    print("=" * 80)
    print(f"  • Total Emails Processed:  {total}")
    print(f"  • High Importance:         {high_count} (Immediate attention required)")
    print(f"  • Medium Importance:       {med_count} (Standard correspondence)")
    print(f"  • Low Importance:          {low_count} (Promotions, digests, or informational)")
    print(f"  • Triage Provider:         {provider_name}")
    print(f"  • Mailbox Protection:      Zero emails modified or sent. Scope was strictly read-only.")
    print("=" * 80)
    print()


def run_demonstration(
    limit: int = 5,
    query: str = "",
    provider_override: Optional[str] = None,
    settings: Optional[Settings] = None,
    gmail_service: Optional[GmailService] = None,
    ai_service: Optional[AIService] = None,
) -> int:
    """
    Executes the end-to-end demonstration workflow.

    Args:
        limit: Maximum number of emails to fetch (default 5).
        query: Gmail search query syntax (default empty for recent emails).
        provider_override: Optional AI provider override ('local' or 'offline').
        settings: Application settings instance.
        gmail_service: Optional pre-configured GmailService (e.g. for testing with mocks).
        ai_service: Optional pre-configured AIService (e.g. for testing with mocks).

    Returns:
        0 on success, non-zero on failure.
    """
    # 1. Resolve Settings
    current_settings = settings or get_settings()
    if provider_override:
        current_settings = current_settings.model_copy(update={"ai_provider": provider_override})

    print_banner(current_settings, GMAIL_READONLY_SCOPE)

    # 2. Check credentials existence before attempting flow
    credentials_file = str(current_settings.credentials_path)
    token_file = str(current_settings.token_path)

    if not gmail_service:
        has_token = os.path.exists(token_file)
        has_creds = os.path.exists(credentials_file)

        if not has_token and not has_creds:
            print_credentials_help(credentials_file)
            return 1

        # 3. Initialize Gmail Connector with STRICTLY READ-ONLY scope
        gmail_service = GmailService(
            settings=current_settings,
            credentials_path=credentials_file,
            token_path=token_file,
            scopes=[GMAIL_READONLY_SCOPE],
        )

    # 4. Authenticate
    try:
        if not os.path.exists(token_file) and getattr(gmail_service, "_service", None) is None:
            print("[*] No cached authorization found. Starting browser OAuth sign-in flow...")
            print("[*] A browser window should open shortly. Please grant READ-ONLY Gmail permission.")
        gmail_service._ensure_authenticated()
        print("[✓] Gmail authentication confirmed (read-only mode active).")
    except FileNotFoundError as fnf_err:
        print_credentials_help(credentials_file)
        return 1
    except Exception as auth_err:
        print(f"[!] Authentication error: {auth_err}")
        print("    Tip: If token.json is invalid or expired, delete 'token.json' and re-run.")
        return 1

    # 5. Fetch recent emails
    print(f"[*] Fetching up to {limit} recent emails from your mailbox...")
    try:
        emails = gmail_service.get_emails(query=query, max_results=limit)
    except Exception as fetch_err:
        print(f"[!] Failed to fetch emails from Gmail API: {fetch_err}")
        return 1

    if not emails:
        query_desc = f" matching '{query}'" if query else ""
        print(f"[i] No emails found in mailbox{query_desc}.")
        return 0

    print(f"[✓] Retrieved {len(emails)} email(s). Starting local AI analysis...")
    print()

    # 6. Initialize AI Service
    if not ai_service:
        ai_service = AIService(settings=current_settings)

    provider_name = (
        f"Local LLM ({current_settings.local_model_name})"
        if current_settings.ai_provider == "local"
        else "Offline Rule-Based Heuristic Baseline"
    )

    # 7. Analyze & Display each email
    analyses: List[EmailAnalysis] = []
    for idx, msg in enumerate(emails, start=1):
        try:
            analysis = ai_service.analyze(msg)
        except Exception as ai_err:
            print(f"[!] Error analyzing email {msg.id}: {ai_err}")
            analysis = EmailAnalysis(
                importance=ImportanceLevel.MEDIUM,
                summary=f"Analysis failed: {str(ai_err)[:60]}",
                suggested_action="Inspect email manually",
                reasoning=f"Provider error occurred during triage.",
            )
        analyses.append(analysis)
        render_email_card(idx, len(emails), msg, analysis)

    # 8. Render Batch Summary
    render_batch_summary(len(emails), analyses, provider_name)
    return 0


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Project APA — Gmail Triage Demonstration",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=5,
        help="Maximum number of recent emails to fetch (1-50)",
    )
    parser.add_argument(
        "-q", "--query",
        type=str,
        default="",
        help="Optional Gmail search query (e.g. 'is:unread', 'label:inbox')",
    )
    parser.add_argument(
        "-p", "--provider",
        choices=["local", "offline"],
        default=None,
        help="Override AI provider ('local' for Ollama, 'offline' for rule-based)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Shorthand for --provider offline (runs 100%% offline without Ollama)",
    )

    args = parser.parse_args()

    # Determine provider override
    provider_override = "offline" if args.offline else args.provider

    # Bound limit
    limit = max(1, min(args.limit, 50))

    exit_code = run_demonstration(
        limit=limit,
        query=args.query,
        provider_override=provider_override,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
