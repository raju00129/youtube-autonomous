"""OpenAI Chat Completions — Telugu keerthana lyrics + Suno style."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import get_settings


class OpenAILlmError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(get_settings().openai_api_key.strip())


def _build_prompt(
    *,
    title: str | None,
    deity: str | None,
    topic: str | None,
    vocal: str | None,
    language: str,
    music_genre: str | None,
    regenerate: bool,
    previous_lyrics: str | None,
    previous_style: str | None,
    avoid_echo: str | None = None,
    variation_seed: str | None = None,
) -> str:
    from app.lyrics_prompt import build_lyrics_prompt

    return build_lyrics_prompt(
        title=title,
        deity=deity,
        topic=topic,
        vocal=vocal,
        language=language,
        music_genre=music_genre,
        regenerate=regenerate,
        previous_lyrics=previous_lyrics,
        previous_style=previous_style,
        avoid_echo=avoid_echo,
        variation_seed=variation_seed,
    )

def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    candidate = fence.group(1).strip() if fence else raw
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end < 0:
        raise OpenAILlmError("OpenAI returned no JSON object")
    return json.loads(candidate[start : end + 1])


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
    avoid_echo: str | None = None,
    variation_seed: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key.strip():
        raise OpenAILlmError("OPENAI_API_KEY missing")

    genre = music_genre or ""
    if energy_hint and energy_hint.lower() not in genre.lower():
        genre = f"{genre}, target energy: {energy_hint}".strip(", ")

    prompt = _build_prompt(
        title=title,
        deity=deity,
        topic=topic,
        vocal=vocal,
        language=language,
        music_genre=genre or None,
        regenerate=regenerate,
        previous_lyrics=previous_lyrics,
        previous_style=previous_style,
        avoid_echo=avoid_echo,
        variation_seed=variation_seed,
    )

    payload = {
        "model": settings.openai_llm_model,
        "temperature": 0.95 if regenerate else 0.88,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write original Telugu temple keerthana lyrics as strict JSON. "
                    "Deep traditional bhakti diction only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.RequestError as exc:
        raise OpenAILlmError(f"OpenAI unreachable: {exc}") from exc

    if response.status_code >= 400:
        raise OpenAILlmError(f"OpenAI HTTP {response.status_code}: {response.text[:800]}")

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAILlmError(f"Unexpected OpenAI payload: {body}") from exc

    data = _extract_json(content)
    if not str(data.get("lyrics") or "").strip():
        raise OpenAILlmError("OpenAI returned empty lyrics")

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
        data["style_prompt"] = style[:1000]

    data["provider"] = "openai"
    data["model"] = settings.openai_llm_model
    return data
