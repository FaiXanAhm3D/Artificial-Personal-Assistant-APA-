# Project APA (Artificial Personal Assistant)

A privacy-first personal email assistant built with a modular backend, strictly read-only Gmail access, and local AI triage.

---

## Architecture Overview

Project APA follows a clean, decoupled architecture:

- **Central Configuration** ([`backend/app/core/config.py`](backend/app/core/config.py)): Pydantic Settings class managing environment settings and resolving all filesystem paths (project root, credentials, tokens) independently of the current working directory.
- **Domain Models** ([`backend/app/domain/models.py`](backend/app/domain/models.py)): Strongly-typed Pydantic v2 models representing application entities:
  - `EmailMessage`: Normalized email with RFC Message-ID, sender, recipients, subject, date, snippet, and plain text.
  - `EmailAnalysis`: Validated triage classification (`HIGH`, `MEDIUM`, `LOW`), concise summary, suggested action, confidence score, and reasoning.
  - `EmailDraft`: Structured draft model with thread metadata and recipient validation.
- **Gmail Connector** ([`backend/app/services/gmail_service.py`](backend/app/services/gmail_service.py)): Read-only Gmail API service featuring recursive multipart MIME traversal, URL-safe and unpadded base64 decoding, HTML-only fallback extraction via `HTMLTextExtractor`, and conversion into domain models.
- **Local AI Service** ([`backend/app/services/ai/`](backend/app/services/ai/)): Provider-independent AI interface (`AIBaseProvider`) supporting:
  - `OfflineRuleBasedProvider`: Deterministic, zero-dependency offline heuristic baseline.
  - `LocalLLMProvider`: Local Ollama integration with strict loopback endpoint validation (`http://localhost:11434`), structured JSON output parsing, and defensive anti-prompt injection framing.
  - `AIService` facade ([`backend/app/services/ai_service.py`](backend/app/services/ai_service.py)): High-level service coordinating classification, summarization, and action recommendations.
- **Unified Entry Point** ([`main.py`](main.py)): CLI application connecting read-only OAuth, email retrieval, local AI triage, non-truncating multiline terminal cards, and batch summary dashboard.
- **Automated Test Suite** ([`backend/tests/`](backend/tests/)): Comprehensive unit and integration tests covering all layers.

---

## Privacy & Security Guarantees

1. **Strictly Read-Only Access:** Project APA requests only `https://www.googleapis.com/auth/gmail.readonly`. The application cannot send, delete, archive, or modify emails.
2. **Zero Cloud AI Exfiltration:** Email contents and metadata are **never** transmitted to hosted or cloud AI APIs (Gemini, OpenAI, Groq). All inference runs strictly on `localhost` via Ollama or the offline rule-based heuristic.
3. **Loopback Endpoint Enforcement:** Local LLM connections are restricted to `127.0.0.1` and `localhost` to prevent server-side request forgery (SSRF).
4. **Anti-Prompt Injection Framing:** Untrusted email text is isolated in strict data boundaries to ensure adversarial email contents cannot hijack assistant instructions.
5. **Secret Protection:** `credentials.json`, `token.json`, and `.env` files are excluded from version control via comprehensive `.gitignore` rules. Full email bodies and tokens are never printed to console logs.

---

## Prerequisites

- **Python:** 3.10 or higher (tested on Python 3.13)
- **Google Cloud Console:** OAuth 2.0 Client ID (Desktop Application) with Gmail API enabled
- **Optional (for Local LLM mode):** [Ollama](https://ollama.com/) running locally (`http://localhost:11434`) with `llama3.2:3b` or preferred model

---

## Installation & Setup

1. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Gmail OAuth Credentials:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
   - Navigate to **APIs & Services > Library** and enable **Gmail API**.
   - Configure the **OAuth consent screen** (User Type: External; add your Gmail as a Test user).
   - Go to **Credentials > Create Credentials > OAuth client ID**:
     - Application type: **Desktop app**
     - Name: `APA Desktop Client`
   - Download the client configuration file, rename it to `credentials.json`, and place it at the project root:
     ```
     Project APA/credentials.json
     ```

---

## Usage

### 1. Offline Baseline (Deterministic Heuristic)
Runs 100% locally with zero external network calls and no Ollama dependency:
```bash
python main.py --offline
```

### 2. Local LLM Mode (Ollama)
Connects to your local Ollama instance for deep triage:
```bash
python main.py --provider local
```

### 3. Configurable Limits and Search Queries
Fetch a specific number of recent emails (default: 5) or apply Gmail query syntax:
```bash
# Fetch 10 most recent unread emails:
python main.py -n 10 -q "is:unread"

# Fetch emails from a specific sender:
python main.py -n 5 -q "from:boss@corp.com"
```

---

## Running the Automated Test Suite

Project APA includes a comprehensive automated test suite with synthetic fixtures and zero live network dependency:

```bash
pytest backend/tests -v
```
