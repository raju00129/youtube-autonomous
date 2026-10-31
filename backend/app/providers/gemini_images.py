"""Gemini image generation — ChatGPT-class stills for ultra-premium YouTube thumbs.

Gemini Nano Banana / Flash Image is stronger than Kling Omni for polished marketing
stills. Telugu title stays local (AI still invents fake Indic letters).
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image

from app.core.config import get_settings
from app.progress import ProgressFn, report


class GeminiImageError(RuntimeError):
    pass


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.gemini_api_key.strip() or settings.aimlapi_api_key.strip())


def _write_bytes(out_path: str | Path, data: bytes) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Normalize to high-quality PNG for compose
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = img.resize((1920, 1080), Image.Resampling.LANCZOS) if img.size != (1920, 1080) else img
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        out.write_bytes(buf.getvalue())
    except Exception:  # noqa: BLE001
        out.write_bytes(data)
    return out


def _extract_image_bytes(body: dict) -> bytes:
    try:
        parts = body["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiImageError(f"Unexpected Gemini image payload: {str(body)[:600]}") from exc

    for part in parts:
        if not isinstance(part, dict):
            continue
        inline = part.get("inlineData") or part.get("inline_data")
        if not isinstance(inline, dict):
            continue
        data = inline.get("data")
        if data:
            return base64.b64decode(data)
    raise GeminiImageError(f"Gemini returned no image bytes: {str(body)[:600]}")


def _style_ref_part(deity: str | None) -> dict | None:
    """Attach one Ragam Spiritual premium style ref for Gemini multimodal."""
    try:
        from app.providers.kling_images import pick_style_reference
    except Exception:  # noqa: BLE001
        return None
    ref = pick_style_reference(deity)
    if not ref or not ref.exists():
        return None
    img = Image.open(ref).convert("RGB")
    img.thumbnail((1024, 576), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return {
        "inline_data": {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(buf.getvalue()).decode("ascii"),
        }
    }


def _build_prompt(
    *,
    deity: str | None,
    mood: str | None,
    lyrics: str | None,
    title: str | None,
    visual_style: str | None,
    style_prompt: str | None,
    notes: str | None,
    has_style_ref: bool,
) -> str:
    from app.providers.kling_images import build_lyrics_scene_brief

    brief = build_lyrics_scene_brief(
        deity=deity,
        mood=mood,
        lyrics=lyrics,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        has_style_ref=has_style_ref,
    )
    # Gemini responds better to explicit "ChatGPT / Midjourney poster" quality cues
    return (
        f"{brief} "
        "Quality bar: same league as ChatGPT / GPT Image ultra-premium Telugu YouTube "
        "mythological movie posters — hyper-detailed CGI, jewel micro-contrast, cinematic "
        "rim light, floating petals, festival CTR punch. "
        "Leave RIGHT side soft for title graphics. ZERO text/letters/logos."
    )[:2400]


def _try_google_gemini(
    prompt: str,
    out_path: Path,
    client: httpx.Client,
    *,
    style_part: dict | None,
) -> Path | None:
    settings = get_settings()
    if not settings.gemini_api_key.strip():
        return None

    primary = (settings.gemini_image_model or "gemini-3.1-flash-image").strip()
    seen: set[str] = set()
    models: list[str] = []
    for m in (
        primary,
        "gemini-3.1-flash-image",
        "gemini-3-pro-image",
        "gemini-nano-banana-2.1",
        "nano-banana-pro-preview",
        "gemini-2.5-flash-image",
        "gemini-3.1-flash-lite-image",
    ):
        if m and m not in seen:
            seen.add(m)
            models.append(m)

    parts: list[dict] = [{"text": prompt}]
    if style_part:
        parts.insert(0, style_part)
        parts[1] = {
            "text": (
                "Use the attached image ONLY as a QUALITY / STYLE / LIGHTING reference for a "
                "Ragam Spiritual Telugu YouTube thumbnail. Do NOT copy its deity or any text. "
                "Create a NEW scene from the prompt below.\n\n" + prompt
            )
        }

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "16:9"},
        },
    }

    errors: list[str] = []
    for model in models:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        response = client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": settings.gemini_api_key,
            },
            json=payload,
        )
        if response.status_code >= 400:
            errors.append(f"{model}: HTTP {response.status_code} {response.text[:220]}")
            continue
        body = response.json()
        if not body.get("candidates"):
            errors.append(f"{model}: no candidates {str(body)[:220]}")
            continue
        try:
            data = _extract_image_bytes(body)
        except GeminiImageError as exc:
            errors.append(f"{model}: {exc}")
            continue
        return _write_bytes(out_path, data)

    _try_google_gemini.last_errors = errors  # type: ignore[attr-defined]
    return None


def _download_image(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    if response.status_code >= 400:
        raise GeminiImageError(f"AIMLAPI image download HTTP {response.status_code}")
    return response.content


def _try_aimlapi(prompt: str, out_path: Path, client: httpx.Client) -> Path | None:
    settings = get_settings()
    if not settings.aimlapi_api_key.strip():
        return None

    base = (settings.aimlapi_base_url or "https://api.aimlapi.com").rstrip("/")
    primary = (settings.gemini_image_model or "gemini-nano-banana-2.1").strip()
    model_map = {
        "gemini-nano-banana-2.1": "google/gemini-nano-banana-2.1",
        "gemini-3.1-flash-image": "google/nano-banana-2",
        "gemini-3.1-flash-image-preview": "google/gemini-3-1-flash-image-preview",
        "gemini-2.5-flash-image": "google/nano-banana-2",
        "gemini-3.1-flash-lite-image": "google/nano-banana-2",
    }
    models: list[str] = []
    seen: set[str] = set()
    for raw in (primary, "gemini-3.1-flash-image", "gemini-nano-banana-2.1"):
        mapped = model_map.get(raw, raw if raw.startswith("google/") else f"google/{raw}")
        if mapped not in seen:
            seen.add(mapped)
            models.append(mapped)

    errors: list[str] = []
    for model in models:
        for resolution in ("2K", "1K"):
            response = client.post(
                f"{base}/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {settings.aimlapi_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "prompt": prompt,
                    "aspect_ratio": "16:9",
                    "resolution": resolution,
                },
            )
            if response.status_code >= 400:
                errors.append(
                    f"aiml:{model}:{resolution}: HTTP {response.status_code} {response.text[:180]}"
                )
                continue
            body = response.json()
            items = body.get("data") if isinstance(body, dict) else None
            if not isinstance(items, list) or not items:
                errors.append(f"aiml:{model}:{resolution}: empty")
                continue
            first = items[0] if isinstance(items[0], dict) else {}
            b64 = first.get("b64_json")
            if b64:
                return _write_bytes(out_path, base64.b64decode(b64))
            url = first.get("url")
            if url and isinstance(url, str) and urlparse(url).scheme in {"http", "https"}:
                return _write_bytes(out_path, _download_image(client, url))
            errors.append(f"aiml:{model}:{resolution}: no url/b64")

    _try_aimlapi.last_errors = errors  # type: ignore[attr-defined]
    return None


def generate_rich_deity_scene(
    *,
    deity: str | None,
    mood: str | None,
    out_path: str | Path,
    lyrics: str | None = None,
    lyrics_hint: str | None = None,
    title: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Ultra-premium 16:9 still via Gemini (ChatGPT-class), no text in frame."""
    settings = get_settings()
    if not is_configured():
        raise GeminiImageError("GEMINI_API_KEY or AIMLAPI_API_KEY required for thumbnails")

    report(on_progress, 5, "Building Gemini ultra-premium prompt…")
    style_part = _style_ref_part(deity)
    prompt = _build_prompt(
        deity=deity,
        mood=mood,
        lyrics=lyrics or lyrics_hint,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        has_style_ref=bool(style_part),
    )
    out = Path(out_path)
    timeout = float(getattr(settings, "gemini_image_timeout_sec", None) or 180)
    google_errors: list[str] = []
    aiml_errors: list[str] = []

    try:
        with httpx.Client(timeout=timeout) as client:
            report(on_progress, 15, "Gemini generating cinematic still…")
            result = _try_google_gemini(prompt, out, client, style_part=style_part)
            google_errors = list(getattr(_try_google_gemini, "last_errors", []) or [])
            if result is not None:
                report(on_progress, 92, "Gemini scene ready…")
                return result
            report(on_progress, 40, "Gemini direct failed — trying AIMLAPI…")
            result = _try_aimlapi(prompt, out, client)
            aiml_errors = list(getattr(_try_aimlapi, "last_errors", []) or [])
            if result is not None:
                report(on_progress, 92, "AIMLAPI Gemini scene ready…")
                return result
    except httpx.RequestError as exc:
        raise GeminiImageError(f"Gemini images unreachable: {exc}") from exc

    detail = "; ".join((google_errors + aiml_errors)[-4:]) or "no provider succeeded"
    raise GeminiImageError(f"Gemini image generation failed. {detail}")


def generate_deity_background(
    *,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None,
    out_path: str | Path,
    lyrics: str | None = None,
    title: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    return generate_rich_deity_scene(
        deity=deity,
        mood=mood,
        lyrics=lyrics or lyrics_hint,
        lyrics_hint=lyrics_hint,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        out_path=out_path,
        on_progress=on_progress,
    )
