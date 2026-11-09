"""LLM facade — Gemini lyrics by default; optional Cursor/OpenAI fallbacks."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.providers import cursor_llm, gemini_llm, openai_llm
from app.providers.cursor_llm import CursorLlmError
from app.providers.gemini_llm import GeminiLlmError
from app.providers.openai_llm import OpenAILlmError

logger = logging.getLogger(__name__)

LlmError = GeminiLlmError


def _sanitize_generated(data: dict[str, Any]) -> dict[str, Any]:
    from app.lyrics_sections import sanitize_suno_lyrics

    if isinstance(data.get("lyrics"), str):
        data["lyrics"] = sanitize_suno_lyrics(data["lyrics"])
    return data


def is_configured() -> bool:
    return (
        gemini_llm.is_configured()
        or cursor_llm.is_configured()
        or openai_llm.is_configured()
    )


def generate_lyrics(**kwargs: Any) -> dict[str, Any]:
    """
    LLM_PROVIDER:
      gemini (default) — Gemini generateContent for Telugu lyrics
      cursor — Cursor lyrics-agent only
      openai — OpenAI only
      auto — Gemini → Cursor → OpenAI
    """
    settings = get_settings()
    provider = (settings.llm_provider or "gemini").lower()
    errors: list[str] = []

    try_gemini = provider in {"gemini", "auto"} and gemini_llm.is_configured()
    try_cursor = provider in {"cursor", "auto"} and cursor_llm.is_configured()
    try_openai = provider in {"openai", "auto"} and openai_llm.is_configured()

    if provider == "gemini" and not gemini_llm.is_configured():
        raise GeminiLlmError("GEMINI_API_KEY missing (LLM_PROVIDER=gemini)")
    if provider == "cursor" and not cursor_llm.is_configured():
        raise CursorLlmError("CURSOR_API_KEY missing (LLM_PROVIDER=cursor)")
    if provider == "openai" and not openai_llm.is_configured():
        raise OpenAILlmError("OPENAI_API_KEY missing (LLM_PROVIDER=openai)")

    if try_gemini:
        try:
            data = gemini_llm.generate_lyrics(**kwargs)
            data.setdefault("provider", "gemini")
            return _sanitize_generated(data)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            logger.warning("Gemini lyrics failed, fallback=%s: %s", try_cursor or try_openai, msg[:300])
            errors.append(f"gemini: {msg[:240]}")
            if provider == "gemini":
                raise GeminiLlmError(msg) from exc

    if try_cursor:
        try:
            data = cursor_llm.generate_lyrics(**kwargs)
            data.setdefault("provider", "cursor")
            data.setdefault("model", settings.cursor_llm_model)
            if errors:
                data["fallback_from"] = errors
            return _sanitize_generated(data)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            logger.warning("Cursor lyrics failed, fallback=%s: %s", try_openai, msg[:300])
            errors.append(f"cursor: {msg[:240]}")
            if provider == "cursor":
                raise CursorLlmError(msg) from exc

    if try_openai:
        try:
            data = openai_llm.generate_lyrics(**kwargs)
            data.setdefault("provider", "openai")
            if errors:
                data["fallback_from"] = errors
            return _sanitize_generated(data)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"openai: {str(exc)[:240]}")
            raise OpenAILlmError(" | ".join(errors)) from exc

    raise GeminiLlmError(
        "No LLM available. Set GEMINI_API_KEY (preferred) and/or CURSOR_API_KEY. "
        + (" | ".join(errors) if errors else "")
    )
