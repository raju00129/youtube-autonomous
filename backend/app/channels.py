"""Multi-channel registry: Telugu (te) + Hindi (hi) under one Google OAuth app."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import Header, HTTPException, Query

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ChannelKey = Literal["te", "hi"]
VALID_CHANNEL_KEYS: frozenset[str] = frozenset({"te", "hi"})
DEFAULT_CHANNEL_KEY: ChannelKey = "te"


@dataclass(frozen=True)
class ChannelProfile:
    key: ChannelKey
    language: str
    display_name: str
    short_name: str
    youtube_channel_id: str
    youtube_channel_handle: str
    youtube_channel_url: str
    token_filename: str

    @property
    def youtube_language(self) -> str:
        return self.language


def normalize_channel_key(raw: str | None) -> ChannelKey:
    key = (raw or DEFAULT_CHANNEL_KEY).strip().lower()
    if key not in VALID_CHANNEL_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel_key '{raw}'. Use 'te' or 'hi'.",
        )
    return key  # type: ignore[return-value]


def get_channel(key: str | None = None) -> ChannelProfile:
    settings = get_settings()
    ck = normalize_channel_key(key)
    if ck == "hi":
        return ChannelProfile(
            key="hi",
            language="hi",
            display_name="Devotional Songs Hindi",
            short_name="Devotional Songs Hindi",
            youtube_channel_id=(settings.youtube_channel_id_hi or "").strip(),
            youtube_channel_handle=(
                settings.youtube_channel_handle_hi or "DevotionalSongsHindi-o9"
            ).strip().lstrip("@"),
            youtube_channel_url=(
                settings.youtube_channel_url_hi
                or "https://www.youtube.com/@DevotionalSongsHindi-o9"
            ).strip(),
            token_filename="youtube_oauth_token_hi.json",
        )
    return ChannelProfile(
        key="te",
        language="te",
        display_name="Ragam Spiritual Telugu",
        short_name="Ragam Spiritual",
        youtube_channel_id=(settings.youtube_channel_id or "").strip(),
        youtube_channel_handle=(settings.youtube_channel_handle or "").strip().lstrip("@"),
        youtube_channel_url=(settings.youtube_channel_url or "").strip(),
        token_filename="youtube_oauth_token_te.json",
    )


def default_language(key: str | None = None) -> str:
    return get_channel(key).language


def token_path_for(key: str | None = None) -> Path:
    settings = get_settings()
    channel = get_channel(key)
    path = Path(settings.media_root) / "cache" / channel.token_filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def migrate_legacy_token() -> None:
    """Copy legacy youtube_oauth_token.json → te token if te missing."""
    settings = get_settings()
    cache = Path(settings.media_root) / "cache"
    legacy = cache / "youtube_oauth_token.json"
    te_path = cache / "youtube_oauth_token_te.json"
    if te_path.exists() or not legacy.exists():
        return
    try:
        cache.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, te_path)
        logger.info("Migrated legacy YouTube OAuth token → %s", te_path.name)
    except OSError as exc:
        logger.warning("Could not migrate legacy YouTube token: %s", exc)


def list_channels() -> list[dict]:
    out: list[dict] = []
    for key in ("te", "hi"):
        ch = get_channel(key)
        out.append(
            {
                "key": ch.key,
                "language": ch.language,
                "display_name": ch.display_name,
                "short_name": ch.short_name,
                "youtube_channel_id": ch.youtube_channel_id,
                "youtube_channel_handle": ch.youtube_channel_handle,
                "youtube_channel_url": ch.youtube_channel_url,
                "youtube_language": ch.youtube_language,
            }
        )
    return out


def channel_key_dependency(
    x_channel_key: str | None = Header(default=None, alias="X-Channel-Key"),
    channel_key: str | None = Query(
        default=None,
        description="Fallback for media tags (img/audio/video) that cannot send headers",
    ),
) -> ChannelKey:
    # Header wins; query supports <img>/<video> URLs via withPortalKey.
    return normalize_channel_key(x_channel_key or channel_key)
