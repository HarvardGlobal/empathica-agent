from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent
_SYSTEM_PROMPTS_DIR = _PACKAGE_ROOT / "system_prompts" / "active"


class PromptNotFoundError(FileNotFoundError):
    pass


def load_prompt(filename: str) -> str:
    """Load a prompt from the active system_prompts registry."""
    path = _SYSTEM_PROMPTS_DIR / filename
    if not path.exists():
        raise PromptNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")
