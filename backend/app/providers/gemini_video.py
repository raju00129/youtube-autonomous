"""Gemini Omni Flash video via Interactions API (one clip @ 720p)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


class GeminiVideoError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(get_settings().gemini_api_key.strip())


def _extract_video_b64(body: dict[str, Any]) -> bytes:
    """Pull MP4 bytes from Interactions API response (SDK or REST shape)."""
    # SDK convenience field when proxied
    out = body.get("output_video") or {}
    if isinstance(out, dict) and out.get("data"):
        return base64.b64decode(out["data"])

    for step in body.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for part in step.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "video" and part.get("data"):
                return base64.b64decode(part["data"])
            # nested content arrays
            for nested in part.get("content") or []:
                if isinstance(nested, dict) and nested.get("type") == "video" and nested.get("data"):
                    return base64.b64decode(nested["data"])

    raise GeminiVideoError(f"No video bytes in Gemini response: {str(body)[:600]}")


def generate_clip(
    *,
    prompt: str,
    out_path: str | Path,
    resolution: str | None = None,
    aspect_ratio: str | None = None,
    duration_sec: int | None = None,
) -> Path:
    """Generate ONE temple visual clip. Shorts must be cut from this file — never re-call for Shorts."""
    settings = get_settings()
    if not settings.gemini_api_key.strip():
        raise GeminiVideoError("GEMINI_API_KEY missing")

    res = (resolution or settings.gemini_video_resolution or "720p").strip()
    if res not in {"360p", "720p", "1080p", "4k"}:
        res = "720p"
    # Product rule: prefer 720p (not low 360p, not upscaled high)
    if res in {"1080p", "4k"}:
        res = "720p"

    ar = (aspect_ratio or settings.gemini_video_aspect_ratio or "16:9").strip()
    if ar not in {"16:9", "9:16"}:
        ar = "16:9"

    dur = int(duration_sec or settings.gemini_video_duration or 10)
    dur = max(3, min(10, dur))

    payload = {
        "model": settings.gemini_video_model,
        "input": prompt,
        "response_format": {
            "type": "video",
            "resolution": res,
            "aspect_ratio": ar,
            "duration": str(dur),
            "delivery": "inline",
        },
        "video_config": {"task": "text_to_video"},
        "background": False,
        "store": False,
        "stream": False,
    }

    url = "https://generativelanguage.googleapis.com/v1/interactions"
    try:
        with httpx.Client(timeout=600.0) as client:
            response = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": settings.gemini_api_key,
                },
                json=payload,
            )
    except httpx.RequestError as exc:
        raise GeminiVideoError(f"Gemini video unreachable: {exc}") from exc

    if response.status_code >= 400:
        raise GeminiVideoError(f"Gemini video HTTP {response.status_code}: {response.text[:800]}")

    body = response.json()
    status = str(body.get("status") or "").lower()
    if status and status not in {"completed", "complete", "succeeded", "success", ""}:
        raise GeminiVideoError(f"Gemini video status={status}: {str(body)[:600]}")

    data = _extract_video_b64(body)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out
