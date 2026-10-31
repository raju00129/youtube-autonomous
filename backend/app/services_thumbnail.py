"""Ultra-premium YouTube thumbs: Gemini cinematic scene + local 3D Telugu + logo.

Gemini (Nano Banana / Flash Image) is used for the still — same class as ChatGPT image
quality for marketing posters. Kling Omni is fallback only.
Telugu title is ALWAYS local (AI invents fake Indic letters).
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChannelBrand, SongProject
from app.providers import gemini_images, kling_images
from app.thumbnail_compose import (
    compose_thumbnail,
    extract_pallavi_line,
    infer_mood,
    sanitize_overlay_text,
    thumbnail_hook_title,
)

logger = logging.getLogger(__name__)


def _latest_lyrics(song: SongProject) -> str | None:
    if not song.lyrics_versions:
        return None
    return song.lyrics_versions[-1].body


def overlay_title_from_song(song: SongProject, lyrics: str | None) -> str:
    """Telugu title for thumb — prefer latest Pallavi, then song.title (strip SEO English)."""
    from app.content_templates import _telugu_hook_title

    candidates = [
        extract_pallavi_line(lyrics),
        _telugu_hook_title(song.title, max_chars=42),
        _telugu_hook_title(getattr(song, "youtube_title", None), max_chars=42),
    ]
    for raw in candidates:
        clean = sanitize_overlay_text((raw or "").strip(), max_len=80)
        if clean and clean.lower() not in {"ragam spiritual", "untitled", "untitled devotional"}:
            return thumbnail_hook_title(clean, max_words=3, max_chars=22)
    return thumbnail_hook_title(song.title or "Ragam Spiritual", max_words=3, max_chars=22)


def _telugu_subtitle(lyrics: str | None, title: str | None) -> str:
    if not lyrics:
        return ""
    m = re.search(
        r"\[Pallavi\]\s*(.+?)(?=\n\s*\[|\Z)",
        lyrics,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    plines = [
        sanitize_overlay_text(ln.strip(), max_len=40)
        for ln in m.group(1).splitlines()
        if ln.strip() and not ln.strip().startswith("[")
    ]
    plines = [p for p in plines if p]
    hook_plain = (title or "").rstrip("!")
    for cand in plines[1:3]:
        if cand and cand not in hook_plain and hook_plain not in cand:
            return cand[:36]
    if len(plines) >= 2:
        return plines[1][:36]
    return ""


def ensure_song_thumbnail(
    db: Session,
    song: SongProject,
    *,
    daypart: str | None = None,
    use_ai: bool = False,
    force_ai: bool = False,
) -> tuple[Path, str] | None:
    """Gemini ultra-premium scene + local 3D Telugu title + logo (Kling fallback)."""
    settings = get_settings()
    brand = db.scalar(select(ChannelBrand).limit(1))
    logo = brand.logo_path if brand else None
    lyrics = _latest_lyrics(song)
    title = overlay_title_from_song(song, lyrics)
    if not title and not lyrics:
        return None

    out_dir = Path(settings.media_root) / "thumbnails" / str(song.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"thumb_{uuid.uuid4().hex[:10]}.jpg"
    bg_path: str | None = None
    engine = "local_pillow"

    want_ai = force_ai or use_ai
    ai_cache = out_dir / "ai_scene_premium.png"
    provider = (getattr(settings, "thumbnail_image_provider", None) or "gemini").strip().lower()

    if want_ai:
        mood = infer_mood(
            lyrics=lyrics,
            style_prompt=song.style_prompt,
            deity=song.deity,
            daypart=daypart,
        )
        fresh = out_dir / f"ai_scene_{uuid.uuid4().hex[:10]}.png"
        scene_kwargs = dict(
            deity=song.deity,
            mood=mood,
            lyrics=lyrics,
            title=title or song.title,
            visual_style=getattr(song, "visual_style", None),
            style_prompt=song.style_prompt,
            notes=getattr(song, "notes", None),
            out_path=fresh,
        )

        last_err: Exception | None = None
        # Prefer Gemini (ChatGPT-class stills); Kling Omni only as fallback
        order = ["gemini", "kling"] if provider != "kling" else ["kling", "gemini"]
        for name in order:
            try:
                if name == "gemini":
                    if not gemini_images.is_configured():
                        continue
                    gemini_images.generate_rich_deity_scene(**scene_kwargs)
                    engine = "gemini_premium"
                else:
                    if not kling_images.is_configured():
                        continue
                    kling_images.generate_rich_deity_scene(**scene_kwargs)
                    engine = "kling_v3_omni_4k"
                ai_cache.write_bytes(fresh.read_bytes())
                bg_path = str(fresh)
                last_err = None
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s thumbnail scene failed: %s", name, exc)
                last_err = exc

        if bg_path is None:
            if force_ai and last_err:
                raise last_err
            if ai_cache.exists():
                bg_path = str(ai_cache)
                engine = "ai_scene_cached"

    if bg_path is None and not force_ai:
        if ai_cache.exists():
            bg_path = str(ai_cache)
            engine = "ai_scene_cached"
        elif song.deity_image_path and Path(song.deity_image_path).exists():
            bg_path = song.deity_image_path
            engine = "user_upload"

    compose_thumbnail(
        title=title or "Ragam Spiritual",
        deity=song.deity,
        logo_path=logo,
        deity_image_path=bg_path,
        out_path=out,
        lyrics=lyrics,
        style_prompt=song.style_prompt,
        daypart=daypart,
        subtitle=_telugu_subtitle(lyrics, title) or None,
        prefer_photo=bool(bg_path),
    )
    song.thumbnail_path = str(out)
    return out, engine
