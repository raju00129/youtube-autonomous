"""Cursor GenerateImage via lyrics-agent sidecar (premium thumb backgrounds)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


class CursorImageError(RuntimeError):
    pass


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.cursor_api_key.strip())


def generate_deity_background(
    *,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None,
    out_path: str | Path,
) -> Path:
    """Ask lyrics-agent to run Cursor GenerateImage (no text in frame)."""
    settings = get_settings()
    if not settings.cursor_api_key.strip():
        raise CursorImageError("CURSOR_API_KEY missing")

    url = settings.lyrics_agent_url.rstrip("/") + "/generate-image"
    payload: dict[str, Any] = {
        "deity": deity,
        "mood": mood,
        "lyrics_hint": (lyrics_hint or "")[:280] or None,
    }
    timeout = float(getattr(settings, "cursor_image_timeout_sec", None) or 300)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
    except httpx.RequestError as exc:
        raise CursorImageError(
            f"lyrics-agent image unreachable at {url}: {exc}. "
            "Is the lyrics-agent container running?"
        ) from exc

    if response.status_code >= 400:
        detail = response.text[:800]
        raise CursorImageError(f"lyrics-agent image HTTP {response.status_code}: {detail}")

    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not data.get("b64"):
        raise CursorImageError(f"lyrics-agent image returned unexpected payload: {body}")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(data["b64"]))
    return out
