"""
backend/app/main.py

FastAPI application entry point and factory for Project APA.
Provides read-only local REST endpoints for health checks, email retrieval,
and local AI triage.

Security Guarantees:
    - Strictly bound to loopback interface (127.0.0.1) by default.
    - Explicitly rejects external/public bind addresses (0.0.0.0).
    - No permissive CORS by default (locked down for local process safety).
    - Read-only operations only.
"""

import argparse
import sys
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import emails, health
from backend.app.core.config import Settings, get_settings

# Permitted bind addresses for local-only privacy compliance
PERMITTED_HOSTS = {"127.0.0.1", "localhost"}


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """
    Application factory for Project APA FastAPI service.
    Configures route handlers, metadata, and security boundaries.
    """
    s = settings or get_settings()

    application = FastAPI(
        title=s.app_name,
        version=s.app_version,
        description=(
            "Artificial Personal Assistant (APA) Local REST API.\n"
            "Provides strictly read-only email retrieval and local-first AI triage."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Note: Permissive CORS ('*') is deliberately omitted.
    # Future desktop/browser frontends on localhost should be added with explicit origins.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Register API route handlers
    application.include_router(health.router)
    application.include_router(emails.router)

    return application


app = create_app()


def run(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """
    Starts the Uvicorn ASGI server with loopback binding validation.
    Refuses execution if configured for external interfaces (e.g. 0.0.0.0).
    """
    clean_host = host.strip().lower()
    if clean_host not in PERMITTED_HOSTS:
        raise ValueError(
            f"Security violation: Host '{host}' is prohibited. "
            f"Project APA handles private email content and strictly requires loopback binding: {PERMITTED_HOSTS}"
        )

    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=clean_host,
        port=port,
        reload=reload,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Project APA Local Read-Only REST API service."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server bind address (strictly limited to 127.0.0.1 or localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port number (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for local development",
    )

    args = parser.parse_args()

    try:
        run(host=args.host, port=args.port, reload=args.reload)
    except ValueError as err:
        sys.stderr.write(f"\n[ERROR] {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
