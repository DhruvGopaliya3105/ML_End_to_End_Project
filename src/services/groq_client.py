"""Shared Groq client that connects lazily and never crashes the app on import.

Why this module exists
----------------------
``groq.Groq(api_key=None)`` raises ``GroqError`` immediately, and
``src/services/llm_service.py`` used to raise ``ValueError`` when
``GROQ_API_KEY`` was missing. Because both happened at *import* time, a missing
key took down the entire application: FastAPI could not even start, so pages
that need no AI at all (login, dashboard, doctors, booking, appointments)
were unusable too.

This module defers client construction until an AI function is actually
called, and raises a clear, actionable error at that point instead.
"""

import os

from dotenv import load_dotenv

load_dotenv()


GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()

MISSING_KEY_MESSAGE = (
    "AI features are unavailable because GROQ_API_KEY is not set. "
    "Create a file named .env in the project root containing "
    "GROQ_API_KEY=your_key_here and restart the app. "
    "Free keys: https://console.groq.com/keys"
)


class GroqNotConfigured(RuntimeError):
    """Raised when an AI feature runs without a configured GROQ_API_KEY."""


class LazyGroqClient:
    """Drop-in stand-in for ``groq.Groq`` that connects on first use.

    Any attribute access (``client.chat``, ``client.audio`` ...) is forwarded to
    a real client created on demand. If no API key is configured, a
    ``GroqNotConfigured`` error is raised with a human-readable explanation.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (
            GROQ_API_KEY if api_key is None else (api_key or "").strip()
        )
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _connect(self):
        if not self._api_key:
            raise GroqNotConfigured(MISSING_KEY_MESSAGE)

        if self._client is None:
            from groq import Groq  # imported here so a missing SDK is not fatal

            self._client = Groq(api_key=self._api_key)

        return self._client

    def __getattr__(self, name: str):
        return getattr(self._connect(), name)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "configured" if self.configured else "NOT configured"
        return f"<LazyGroqClient ({state})>"


def get_groq_client(api_key: str | None = None) -> LazyGroqClient:
    """Return a lazily-connecting Groq client."""
    return LazyGroqClient(api_key=api_key)


def ai_is_configured() -> bool:
    """True when a Groq API key is present."""
    return bool(GROQ_API_KEY)
