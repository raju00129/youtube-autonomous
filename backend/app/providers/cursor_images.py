"""Cursor GenerateImage via lyrics-agent sidecar (premium stills / thumbs)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
from PIL import Image
import io

from app.core.config import get_settings
from app.progress import ProgressFn, report


class CursorImageError(RuntimeError):
    pass


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.cursor_api_key.strip())


def _normalize_still(out_path: Path, data: bytes) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        if img.size != (1920, 1080):
            img = img.resize((1920, 1080), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        # Keep PNG for thumbs; JPEG also fine for scenes — match extension
        if out_path.suffix.lower() in {".jpg", ".jpeg"}:
            img.save(buf, format="JPEG", quality=92, optimize=True)
        else:
            img.save(buf, format="PNG", optimize=True)
        out_path.write_bytes(buf.getvalue())
    except Exception:  # noqa: BLE001
        out_path.write_bytes(data)
    return out_path


def _call_lyrics_agent(
    *,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None,
    prompt: str | None = None,
) -> bytes:
    settings = get_settings()
    if not settings.cursor_api_key.strip():
        raise CursorImageError("CURSOR_API_KEY missing")

    url = settings.lyrics_agent_url.rstrip("/") + "/generate-image"
    payload: dict[str, Any] = {
        "deity": deity,
        "mood": mood,
        "lyrics_hint": (lyrics_hint or "")[:280] or None,
    }
    if prompt and prompt.strip():
        payload["prompt"] = prompt.strip()[:1800]
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
    return base64.b64decode(data["b64"])


def generate_deity_background(
    *,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None,
    out_path: str | Path,
) -> Path:
    """Ask lyrics-agent to run Cursor GenerateImage (no text in frame)."""
    raw = _call_lyrics_agent(deity=deity, mood=mood, lyrics_hint=lyrics_hint)
    return _normalize_still(Path(out_path), raw)


def generate_rich_deity_scene(
    *,
    deity: str | None,
    mood: str | None,
    out_path: str | Path,
    lyrics: str | None = None,
    title: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Scene / thumb still via Cursor GenerateImage (god-ideal, text-free)."""
    report(on_progress, 10, "Cursor generating cinematic still…")
    hint_parts = [
        (title or "").strip(),
        (style_prompt or "").strip()[:400],
        (notes or "").strip()[:200],
        (lyrics or "").strip()[:200],
        (visual_style or "").strip(),
    ]
    lyrics_hint = " | ".join(p for p in hint_parts if p)[:280] or None
    prompt = (style_prompt or "").strip() or None
    if prompt:
        prompt = (
            f"{prompt} Classical murti ideal, temple sanctum, ultra-premium cinematic still, "
            "NO text, NO watermark, NO logo, NO drama actor face."
        )[:1800]
    raw = _call_lyrics_agent(
        deity=deity,
        mood=mood,
        lyrics_hint=lyrics_hint,
        prompt=prompt,
    )
    report(on_progress, 90, "Cursor still ready…")
    return _normalize_still(Path(out_path), raw)
