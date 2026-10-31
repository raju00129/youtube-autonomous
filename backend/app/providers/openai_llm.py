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
) -> str:
    vocal_label = "female" if vocal == "f" else "male"
    regen = ""
    if regenerate or previous_lyrics:
        regen = f"""
REGENERATE — write a NEW draft (new Pallavi, Slokam, Charanams; new style_prompt tempo/colour).
Do NOT copy previous Pallavi or style.
Previous style (do not copy): {(previous_style or "(none)")[:500]}
Previous lyrics (do not copy):
{(previous_lyrics or "(none)")[:1800]}
"""
    return f"""You are a senior Telugu keerthana / bhajan lyricist for YouTube channel "Ragam Spiritual".
Write ORIGINAL temple-grade lyrics in Telugu script for Suno custom mode — deep traditional bhakti poetry, NOT everyday speech.

LANGUAGE REGISTER (critical)
- Sung lines MUST be Telugu script (తెలుగు). No transliteration-only; no Hindi Devanagari for sung lines.
- CLASSICAL / granthika-leaning BHAKTI Telugu — sacred poetic tongue of old keerthanas.
- Deep spiritual vocabulary (nama, guna, leela, karuna, sharanagati, jyothi, amrutham, hrudayam, divya…).
- FORBIDDEN: colloquial chat Telugu, newspaper prose, film slang, English mix-ins in sung lines, shallow common words when a traditional synonym exists.
- Only Hindu deities/avataras (Shiva, Parvati, Sri Vishnu, Sri Rama, Krishna, Narasimha, Lakshmi, Saraswati, Durga, Hanuman, Ganesha, Subrahmanya, Venkateswara, Surya, Ayyappa, Annapurna…). Never Sai Baba / Shirdi.

BRIEF
- Language: {language or "te"}
- Title hint: {title or "(invent a melodic traditional Telugu title)"}
- Deity / theme: {deity or "general Hindu devotion"}
- Topic / mood: {topic or "peaceful traditional temple devotion"}
- Lead vocal: {vocal_label}
- Music direction: {music_genre or "traditional Telugu Carnatic-devotional bhajan"}
{regen}

FORM (exact tags, Pallavi repeats unchanged):
[Pallavi] 2–4 nama-rich melodic lines
[Anupallavi] 2–4 lines
[Pallavi] SAME text
[Slokam] 2–4 original Sanskrit or Sanskritised-Telugu lines
[Pallavi] SAME text
[Charanam 1] 4–6 deep poetic lines
[Pallavi] SAME text
[Charanam 2] 4–6 deep poetic lines
[Pallavi] SAME text (final)

Also write English style_prompt for Suno (comma tags, ~450 chars): traditional Telugu Carnatic/temple only; tanpura; percussion matching energy; {vocal_label} Telugu vocalist; EXPLICIT tempo e.g. "slow 68 BPM" or "medium 96 BPM"; temple reverb; Pallavi repeats; brief sloka break. Tempo MUST fit these lyrics.

Respond with ONLY valid JSON (no markdown):
{{"title":"...","style_prompt":"...","lyrics":"...","tempo":"slow|slow_medium|medium|medium_brisk","bpm_hint":90,"energy":"..."}}"""


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
    )

    payload = {
        "model": settings.openai_llm_model,
        "temperature": 0.9 if regenerate else 0.75,
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
