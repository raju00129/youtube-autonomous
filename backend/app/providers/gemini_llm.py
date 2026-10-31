"""Gemini generateContent — Telugu keerthana lyrics + Suno style."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.lyrics_prompt import build_lyrics_prompt
from app.style_prompt import enrich_style_prompt


class GeminiLlmError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(get_settings().gemini_api_key.strip())


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    candidate = fence.group(1).strip() if fence else raw
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end < 0:
        raise GeminiLlmError("Gemini returned no JSON object")
    return json.loads(candidate[start : end + 1])


def _response_text(body: dict[str, Any]) -> str:
    try:
        parts = body["candidates"][0]["content"]["parts"]
        chunks = [p.get("text", "") for p in parts if isinstance(p, dict)]
        text = "".join(chunks).strip()
        if text:
            return text
    except (KeyError, IndexError, TypeError):
        pass
    raise GeminiLlmError(f"Unexpected Gemini payload: {str(body)[:600]}")


LYRICS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "style_prompt": {"type": "string"},
        "lyrics": {"type": "string"},
        "tempo": {"type": "string"},
        "bpm_hint": {"type": "integer"},
        "energy": {"type": "string"},
    },
    "required": ["title", "style_prompt", "lyrics"],
}


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
    if not settings.gemini_api_key.strip():
        raise GeminiLlmError("GEMINI_API_KEY missing")

    genre = music_genre or ""
    if energy_hint and energy_hint.lower() not in genre.lower():
        genre = f"{genre}, target energy: {energy_hint}".strip(", ")

    prompt = build_lyrics_prompt(
        title=title,
        deity=deity,
        topic=topic,
        vocal=vocal,
        language=language,
        music_genre=genre or None,
        regenerate=regenerate,
        previous_lyrics=previous_lyrics,
        previous_style=previous_style,
        variation_seed=f"{int(time.time())}-{regenerate}",
    )

    primary = (settings.gemini_llm_model or "gemini-3.8-flash").strip()
    model_fallbacks = [
        primary,
        "gemini-3.8-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ]
    models = [m for i, m in enumerate(model_fallbacks) if m and m not in model_fallbacks[:i]]

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "You write original Telugu temple keerthana lyrics as strict JSON. "
                        "Deep traditional bhakti diction, crystal-clear Telugu singability, "
                        "native pronunciation-friendly lines only."
                    )
                }
            ]
        },
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.95 if regenerate else 0.8,
            "responseMimeType": "application/json",
            "responseSchema": LYRICS_SCHEMA,
        },
    }

    body: dict[str, Any] | None = None
    used_model = primary
    last_err = ""
    try:
        with httpx.Client(timeout=180.0) as client:
            for model in models:
                used_model = model
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent"
                )
                try:
                    response = client.post(
                        url,
                        headers={
                            "Content-Type": "application/json",
                            "x-goog-api-key": settings.gemini_api_key,
                        },
                        json=payload,
                    )
                except httpx.RequestError as exc:
                    last_err = f"{model}: unreachable {exc}"
                    continue
                if response.status_code >= 400:
                    last_err = f"{model}: HTTP {response.status_code} {response.text[:400]}"
                    continue
                body = response.json()
                if body.get("candidates"):
                    break
                last_err = f"{model}: no candidates {str(body)[:400]}"
                body = None
    except httpx.RequestError as exc:
        raise GeminiLlmError(f"Gemini lyrics unreachable: {exc}") from exc

    if not body:
        raise GeminiLlmError(f"Gemini lyrics failed. {last_err}")

    content = _response_text(body)
    data = _extract_json(content)
    if not str(data.get("lyrics") or "").strip():
        raise GeminiLlmError("Gemini returned empty lyrics")

    style = str(data.get("style_prompt") or "").strip()
    extras = []
    if data.get("tempo"):
        extras.append(str(data["tempo"]).replace("_", " "))
    if isinstance(data.get("bpm_hint"), (int, float)):
        extras.append(f"{int(data['bpm_hint'])} BPM")
    if data.get("energy"):
        extras.append(str(data["energy"]))
    if extras and style:
        lower = style.lower()
        for bit in extras:
            if bit.lower() not in lower:
                style = f"{style}, {bit}"
    data["style_prompt"] = enrich_style_prompt(style, vocal=vocal)[:1000]
    data["provider"] = "gemini"
    data["model"] = used_model
    return data
