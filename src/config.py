"""Runtime configuration helpers."""

from __future__ import annotations

import os

DEFAULT_GOOGLE_GENAI_MODEL = "gemini-3.5-flash"


def get_google_genai_model() -> str:
    return os.getenv("GOOGLE_GENAI_MODEL", os.getenv("GEMINI_MODEL", DEFAULT_GOOGLE_GENAI_MODEL))
