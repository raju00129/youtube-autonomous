"""Cursor agent via lyrics-agent sidecar (Node @cursor/sdk)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class CursorLlmError(RuntimeError):
    pass


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.cursor_api_key.strip())


def generate_lyrics(
    *,
    title: str | None = None,
    deity: str | None = None,
    topic: str | None = None,
    vocal: str | None = "m",
    language: str = "te",
    music_genre: str | None = None,
    energy_hint: str | None = None,
    regenerate: bool = False,
    previous_lyrics: str | None = None,
    previous_style: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.cursor_api_key.strip():
        raise CursorLlmError("CURSOR_API_KEY missing")

    url = settings.lyrics_agent_url.rstrip("/") + "/generate"
    genre = music_genre or ""
    if energy_hint and energy_hint.lower() not in genre.lower():
        genre = f"{genre}, target energy: {energy_hint}".strip(", ")
    payload = {
        "title": title,
        "deity": deity,
        "topic": topic,
        "vocal": vocal,
        "language": language,
        "musicGenre": genre or None,
        "regenerate": regenerate,
        "previousLyrics": (previous_lyrics or "")[:2500] or None,
        "previousStyle": (previous_style or "")[:500] or None,
    }
    try:
        with httpx.Client(timeout=float(settings.lyrics_agent_timeout_sec)) as client:
            response = client.post(url, json=payload)
    except httpx.RequestError as exc:
        raise CursorLlmError(
            f"lyrics-agent unreachable at {url}: {exc}. Is the lyrics-agent container running?"
        ) from exc

    if response.status_code >= 400:
        detail = response.text[:800]
        raise CursorLlmError(f"lyrics-agent HTTP {response.status_code}: {detail}")

    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not data.get("lyrics"):
        raise CursorLlmError(f"lyrics-agent returned unexpected payload: {body}")
    # Prefer lyric-fitted style; append tempo/energy + Telugu pronunciation quality tags
    from app.style_prompt import enrich_style_prompt

    style = str(data.get("style_prompt") or "").strip()
    extras = []
    if data.get("tempo"):
        extras.append(str(data["tempo"]).replace("_", " "))
    if data.get("bpm_hint"):
        extras.append(f"{data['bpm_hint']} BPM")
    if data.get("energy"):
        extras.append(str(data["energy"]))
    if extras and style:
        lower = style.lower()
        for bit in extras:
            if bit.lower() not in lower:
                style = f"{style}, {bit}"
    data["style_prompt"] = enrich_style_prompt(style, vocal=vocal)[:1000]
    return data
