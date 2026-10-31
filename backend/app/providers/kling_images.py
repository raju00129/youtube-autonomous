"""Kling Image 3.0 Omni — ultra-premium cinematic scenes (style-matched to channel thumbs).

Telugu title is NEVER painted by Kling. services_thumbnail stamps 3D gold Telugu + logo.
Style reference images teach Omni the Ragam Spiritual premium look.
"""

from __future__ import annotations

import base64
import io
import re
import time
from pathlib import Path

import httpx
from PIL import Image

from app.core.config import get_settings
from app.progress import ProgressFn, kling_poll_percent, report


class KlingImageError(RuntimeError):
    pass


_OMNI_MODELS = frozenset({"kling-v3-omni", "kling-image-o1", "kling-image-v3-omni"})
_STYLE_DIR = Path(__file__).resolve().parent.parent / "assets" / "thumb_style_refs"


def is_configured() -> bool:
    return bool(get_settings().kling_api_key.strip())


def _base_url() -> str:
    return (get_settings().kling_base_url or "https://api-singapore.klingai.com").rstrip("/")


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().kling_api_key.strip()}",
        "Content-Type": "application/json",
    }


def _normalize_model(raw: str) -> str:
    m = (raw or "kling-v3-omni").strip()
    if m in {"kling-image-v3-omni", "kling-v3-omni"}:
        return "kling-v3-omni"
    if m == "kling-image-o1":
        return "kling-image-o1"
    return "kling-v3-omni"


def _normalize_resolution(raw: str, *, model: str) -> str:
    r = (raw or "4k").strip().lower()
    if r not in {"1k", "2k", "4k"}:
        r = "4k"
    if model == "kling-image-o1" and r == "4k":
        return "2k"
    return r


def _output_size(resolution: str) -> tuple[int, int]:
    if resolution == "4k":
        return (2560, 1440)
    if resolution == "2k":
        return (1920, 1080)
    return (1280, 720)


def _section(lyrics: str, name: str) -> str:
    m = re.search(
        rf"\[{name}\]\s*(.+?)(?=\n\s*\[|\Z)",
        lyrics,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    lines = [
        ln.strip()
        for ln in m.group(1).splitlines()
        if ln.strip() and not ln.strip().startswith("[")
    ]
    return " ".join(lines[:6])


def _deity_visual(deity: str | None) -> str:
    key = (deity or "").lower()
    table = {
        "narasimha": (
            "Ugra Narasimha — fierce lion-headed Vishnu avatar, roaring mouth, glowing eyes, "
            "muscular golden body, smashing stone pillars, cinematic mythological movie energy"
        ),
        "hanuman": (
            "Veera Hanuman — powerful flying vanara warrior, golden crown, orange dhoti, "
            "gada trailing energy, ocean or sky leap, Adipurush / Hanuman film CGI quality"
        ),
        "lakshmi": (
            "Goddess Lakshmi — four arms, seated on blooming pink lotus, gold coins cascading, "
            "green-red silk saree, ornate crown, temple diyas, prosperity radiance"
        ),
        "shiva": (
            "Lord Shiva — serene powerful yogic form, Tripundra, crescent moon, rudraksha, "
            "optional lingam abhishekam, Himalayan or Mandapam aura"
        ),
        "vishnu": (
            "Lord Vishnu — calm royal kiritam, shankha chakra, Vaikuntha gold aura"
        ),
        "rama": (
            "Lord Rama — noble warrior-prince with bow, blue-toned dignified skin"
        ),
        "krishna": (
            "Lord Krishna — peacock feather, flute, pitambara, Vrindavan golden light"
        ),
        "durga": (
            "Goddess Durga — fierce-graceful, lion mount, red-gold shakti energy"
        ),
        "ganesha": (
            "Lord Ganesha — elephant head, modaka, festive red-gold temple lamps"
        ),
    }
    for name, desc in table.items():
        if name in key:
            return desc
    return f"sacred Hindu deity for {deity or 'bhakti'} — South Indian classical iconography, cinematic CGI"


def pick_style_reference(deity: str | None) -> Path | None:
    """Pick a channel-style reference thumb closest to the deity."""
    if not _STYLE_DIR.exists():
        return None
    key = (deity or "").lower()
    prefer: list[str] = []
    if "narasimha" in key:
        prefer = ["Narasimha"]
    elif "hanuman" in key or "anjaneya" in key:
        prefer = ["Hanuman"]
    elif "lakshmi" in key or "kamala" in key:
        prefer = ["Lakshmi", "Goddess"]
    else:
        prefer = ["Lakshmi", "Narasimha", "Hanuman"]
    files = sorted(_STYLE_DIR.glob("*.jpg")) + sorted(_STYLE_DIR.glob("*.png"))
    for needle in prefer:
        for f in files:
            if needle.lower() in f.name.lower():
                return f
    return files[0] if files else None


def build_lyrics_scene_brief(
    *,
    deity: str | None,
    mood: str | None,
    lyrics: str | None,
    title: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    has_style_ref: bool = False,
) -> str:
    body = (lyrics or "").strip()
    pallavi = _section(body, "Pallavi")
    anu = _section(body, "Anupallavi")
    char1 = _section(body, "Charanam 1") or _section(body, "Charanam")
    char2 = _section(body, "Charanam 2")
    sloka = _section(body, "Slokam") or _section(body, "Sloka")
    lyric_bits = [b for b in (pallavi, anu, char1, char2, sloka) if b]
    lyric_story = " | ".join(lyric_bits)[:800] if lyric_bits else (title or "Telugu bhakti")

    blob = f"{body} {visual_style or ''} {style_prompt or ''} {notes or ''}".lower()
    setting_cues: list[str] = []
    if any(k in blob for k in ("లింగ", "linga", "lingam", "అభిషేక", "abhishek")):
        setting_cues.append("Shiva lingam abhishekam, bilva, sacred ash")
    if any(k in blob for k in ("సంధ్య", "sandhya", "evening", "aarti", "ఆరతి")):
        setting_cues.append("sandhya aarti lamps and incense dusk")
    if any(k in blob for k in ("నవరాత్రి", "navaratri", "దీపావళి", "deepavali", "diwali")):
        setting_cues.append("festival lamps, marigold, red-gold celebration")
    if any(k in blob for k in ("సముద్ర", "ocean", "sea", "సుందర", "sundara")):
        setting_cues.append("cinematic ocean / sundarakanda sea leap energy")
    if any(k in blob for k in ("కమల", "lotus", "పద్మ", "స్వర్ణ", "gold coin")):
        setting_cues.append("lotus throne, cascading gold coins, temple diyas")
    if not setting_cues:
        setting_cues.append("setting invented from the lyric story — cinematic, not generic stock")

    hero = _deity_visual(deity)
    mood_bit = mood or "devotional power"
    style_bit = (visual_style or "").strip()[:160]
    notes_bit = (notes or "").strip()[:160]

    ref_line = (
        "Match the ULTRA-PREMIUM cinematic lighting, CGI polish, color grade, and YouTube-thumbnail "
        "composition quality of <<<image_1>>> (Ragam Spiritual channel style). "
        "Do NOT copy the same deity or text from the reference — invent a NEW scene for THIS song. "
        if has_style_ref
        else ""
    )

    return (
        f"{ref_line}"
        f"Ultra-premium 16:9 Telugu YouTube thumbnail BACKGROUND — mythological movie poster CGI, "
        f"8K detail, volumetric god rays, jewel sparkle, particle dust, rim light, film still. "
        f"FULL-BLEED single scene (no collage, no split panels, no black text box). "
        f"SUBJECT: {hero}. Energy: {mood_bit}. "
        f"LYRIC STORY TO ILLUSTRATE: {lyric_story}. "
        f"SETTING: {'; '.join(setting_cues[:3])}. "
        f"{('Visual style: ' + style_bit + '. ') if style_bit else ''}"
        f"{('Notes: ' + notes_bit + '. ') if notes_bit else ''}"
        f"Composition: powerful deity hero filling LEFT–CENTER ~55–60%; RIGHT side softer/emptier "
        f"for later title graphics, still continuous atmosphere. High CTR gold-orange-crimson punch. "
        f"CRITICAL — ZERO TEXT: no Telugu, no Hindi, no Devanagari, no English, no letters, "
        f"no captions, no watermarks, no logos, no Sai Baba, no selfies."
    )[:2400]


def _poll_omni_task(
    client: httpx.Client,
    task_id: str,
    *,
    timeout_sec: float,
    on_progress: ProgressFn | None = None,
) -> str:
    started = time.monotonic()
    deadline = started + timeout_sec
    url = f"{_base_url()}/v1/images/omni-image/{task_id}"
    last = ""
    while time.monotonic() < deadline:
        response = client.get(url, headers=_auth_headers())
        if response.status_code >= 400:
            raise KlingImageError(
                f"Kling Omni poll HTTP {response.status_code}: {response.text[:400]}"
            )
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise KlingImageError(f"Unexpected Kling Omni poll payload: {str(body)[:400]}")
        status = str(data.get("task_status") or "").lower()
        last = status
        pct = kling_poll_percent(
            elapsed=time.monotonic() - started,
            timeout=timeout_sec,
            status=status,
        )
        report(on_progress, pct, f"Kling Omni image: {status or 'waiting'}…")
        if status in {"succeed", "succeeded", "success"}:
            result = data.get("task_result") or {}
            images = result.get("images") or result.get("series_images") or []
            if not images:
                raise KlingImageError(f"Kling Omni succeed but empty: {str(data)[:400]}")
            img_url = images[0].get("url")
            if not img_url:
                raise KlingImageError(f"Kling Omni missing url: {str(images[0])[:300]}")
            return str(img_url)
        if status in {"failed", "fail", "error"}:
            msg = data.get("task_status_msg") or body.get("message") or status
            raise KlingImageError(f"Kling Omni failed: {msg}")
        time.sleep(2.5)
    raise KlingImageError(f"Kling Omni timed out (last status={last or 'unknown'})")


def generate_rich_deity_scene(
    *,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None = None,
    out_path: str | Path,
    lyrics: str | None = None,
    title: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Kling Omni @ 4K — ultra-premium lyrics-driven plate, zero text."""
    settings = get_settings()
    if not settings.kling_api_key.strip():
        raise KlingImageError("KLING_API_KEY missing")

    report(on_progress, 3, "Building ultra-premium scene prompt…")
    model = _normalize_model(settings.kling_image_model)
    resolution = _normalize_resolution(
        getattr(settings, "kling_image_resolution", None) or "4k",
        model=model,
    )

    style_ref = pick_style_reference(deity)
    image_list: list[dict] = []
    if style_ref and style_ref.exists() and style_ref.stat().st_size < 9_000_000:
        # Resize ref so payload stays light
        ref_img = Image.open(style_ref).convert("RGB")
        ref_img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        ref_img.save(buf, format="JPEG", quality=88)
        image_list.append({"image": base64.b64encode(buf.getvalue()).decode("ascii")})
        report(on_progress, 5, f"Style ref: {style_ref.name}")

    full_lyrics = (lyrics or lyrics_hint or "").strip()
    prompt = build_lyrics_scene_brief(
        deity=deity,
        mood=mood,
        lyrics=full_lyrics,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        has_style_ref=bool(image_list),
    )

    timeout = float(settings.kling_image_timeout_sec or 240)
    payload: dict = {
        "model_name": model if model in _OMNI_MODELS else "kling-v3-omni",
        "prompt": prompt,
        "resolution": resolution,
        "result_type": "single",
        "n": 1,
        "aspect_ratio": "16:9",
        "watermark_info": {"enabled": False},
    }
    if image_list:
        payload["image_list"] = image_list

    try:
        with httpx.Client(timeout=timeout) as client:
            report(on_progress, 6, f"Submitting Kling Omni {resolution}…")
            create = client.post(
                f"{_base_url()}/v1/images/omni-image",
                headers=_auth_headers(),
                json=payload,
            )
            try:
                body = create.json()
            except Exception:  # noqa: BLE001
                body = {}
            api_code = body.get("code")
            if create.status_code >= 400 or api_code not in (0, "0", None):
                msg = str(body.get("message") or create.text[:400])
                if api_code in (1101, 1102, "1101", "1102") or "balance" in msg.lower():
                    raise KlingImageError(
                        "Kling API has no usable credits (code 1102). "
                        "Buy an Image pack at https://kling.ai/dev/pricing?scrollTo=image "
                        f"then retry. Detail: {msg}"
                    )
                raise KlingImageError(
                    f"Kling Omni create HTTP {create.status_code} code={api_code}: {msg}"
                )

            data = body.get("data") or {}
            task_id = data.get("task_id")
            if not task_id:
                raise KlingImageError(f"Kling Omni missing task_id: {str(body)[:400]}")

            report(on_progress, 10, "Kling Omni rendering ultra-premium scene…")
            image_url = _poll_omni_task(
                client, str(task_id), timeout_sec=timeout, on_progress=on_progress
            )
            report(on_progress, 90, "Downloading Omni image…")
            dl = client.get(image_url)
            if dl.status_code >= 400:
                raise KlingImageError(f"Kling Omni download HTTP {dl.status_code}")

            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            img = Image.open(io.BytesIO(dl.content)).convert("RGB")
            tw, th = _output_size(resolution)
            if img.width != tw or img.height != th:
                img = img.resize((tw, th), Image.Resampling.LANCZOS)
            if out.suffix.lower() in {".jpg", ".jpeg"}:
                img.save(out, format="JPEG", quality=95, optimize=True, subsampling=0)
            else:
                img.save(out, format="PNG", optimize=True)
            report(on_progress, 96, "Scene ready — composing 3D Telugu title + logo…")
            return out
    except httpx.RequestError as exc:
        raise KlingImageError(f"Kling images unreachable: {exc}") from exc


def generate_premium_thumbnail(
    *,
    title: str,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None,
    out_path: str | Path,
    logo_path: str | Path | None = None,
    channel_name: str = "Ragam Spiritual",
    lyrics: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    del logo_path, channel_name
    return generate_rich_deity_scene(
        deity=deity,
        mood=mood,
        lyrics_hint=lyrics_hint,
        lyrics=lyrics or lyrics_hint,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        out_path=out_path,
        on_progress=on_progress,
    )


def generate_deity_background(
    *,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None,
    out_path: str | Path,
    title: str | None = None,
    logo_path: str | Path | None = None,
    lyrics: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    del logo_path
    return generate_rich_deity_scene(
        deity=deity,
        mood=mood,
        lyrics_hint=lyrics_hint,
        lyrics=lyrics or lyrics_hint,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        out_path=out_path,
        on_progress=on_progress,
    )
