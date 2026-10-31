"""OpenAI Images — deity/temple backgrounds (no text; Telugu overlay is local)."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx

from app.core.config import get_settings


class OpenAIImageError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(get_settings().openai_api_key.strip())


def generate_deity_background(
    *,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None,
    out_path: str | Path,
) -> Path:
    """Generate a cinematic temple still WITHOUT text/logos/watermark."""
    settings = get_settings()
    if not settings.openai_api_key.strip():
        raise OpenAIImageError("OPENAI_API_KEY missing")

    deity_bit = deity or "Hindu deity"
    mood_bit = mood or "serene temple devotion"
    hint = (lyrics_hint or "")[:280]
    prompt = (
        f"Cinematic South Indian temple devotional photograph for {deity_bit}. "
        f"Mood: {mood_bit}. Atmosphere: sacred mandapam, oil lamps, soft incense haze, "
        f"stone pillars, warm golden hour light, reverent Hindu temple aesthetic. "
        f"Lyric mood hint: {hint or 'peaceful bhakti'}. "
        "Photorealistic, vertical-friendly 16:9 composition, rich colour, "
        "NO text, NO letters, NO watermark, NO logo, NO modern people selfies, "
        "NO Sai Baba. Suitable as YouTube thumbnail background under title overlay."
    )

    # dall-e-3: size 1792x1024; gpt-image-1 may use different sizes — stick to dall-e-3 for compatibility
    model = settings.openai_image_model
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1792x1024",
        "quality": "standard",
        "response_format": "b64_json",
    }
    if model.startswith("gpt-image"):
        # Newer image models: omit response_format quirks; still request b64 if supported
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": "1536x1024",
        }

    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(
                f"{settings.openai_base_url.rstrip('/')}/images/generations",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.RequestError as exc:
        raise OpenAIImageError(f"OpenAI images unreachable: {exc}") from exc

    if response.status_code >= 400:
        raise OpenAIImageError(f"OpenAI images HTTP {response.status_code}: {response.text[:800]}")

    body = response.json()
    data = (body.get("data") or [None])[0] or {}
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if data.get("b64_json"):
        out.write_bytes(base64.b64decode(data["b64_json"]))
        return out
    if data.get("url"):
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            img = client.get(data["url"])
            img.raise_for_status()
            out.write_bytes(img.content)
        return out
    raise OpenAIImageError(f"OpenAI images returned no image data: {body}")
