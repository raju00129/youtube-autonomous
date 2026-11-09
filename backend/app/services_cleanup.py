"""Delete heavy media for published songs after the publish day (disk hygiene)."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import SongProject

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


def _unlink(path: str | None) -> bool:
    if not path:
        return False
    p = Path(path)
    try:
        if p.is_file():
            p.unlink(missing_ok=True)
            return True
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            return True
    except OSError as exc:
        logger.warning("cleanup unlink failed %s: %s", p, exc)
    return False


def _clear_song_dirs(media_root: Path, song_id: str) -> int:
    removed = 0
    for sub in ("music", "thumbnails", "visuals", "finals", "temp"):
        d = media_root / sub / song_id
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed


def cleanup_published_media(db: Session, *, as_of: datetime | None = None) -> dict:
    """Remove audio/video/thumbnail files for songs published before today (IST).

    Keeps YouTube IDs, titles, lyrics text, and schedule metadata.
    Safe to run daily — already-cleaned songs are skipped via notes stamp.
    """
    now = as_of or datetime.now(tz=IST)
    today = now.astimezone(IST).date()
    settings = get_settings()
    media_root = Path(settings.media_root)

    songs = db.scalars(
        select(SongProject)
        .options(
            selectinload(SongProject.music_generations),
            selectinload(SongProject.shorts),
        )
        .where(
            or_(
                SongProject.stage == "published",
                SongProject.youtube_video_id.is_not(None),
            )
        )
    ).all()

    cleaned_songs: list[str] = []
    files_removed = 0
    skipped = 0

    for song in songs:
        notes = song.notes or ""
        if "[media_cleaned" in notes:
            skipped += 1
            continue

        pub = song.publish_at
        if pub is not None:
            pub_day = pub.astimezone(IST).date() if pub.tzinfo else pub.date()
        else:
            # Fall back to updated_at if publish_at missing but YouTube id exists
            u = song.updated_at
            pub_day = u.astimezone(IST).date() if u and u.tzinfo else (u.date() if u else None)

        if pub_day is None or pub_day >= today:
            # Still publish day (or future) — keep media for retries / Short 2 stagger
            skipped += 1
            continue

        # Clear file paths
        for attr in (
            "thumbnail_path",
            "deity_image_path",
            "video_clip_path",
            "final_video_path",
        ):
            path = getattr(song, attr, None)
            if _unlink(path):
                files_removed += 1
            setattr(song, attr, None)

        for music in song.music_generations or []:
            if _unlink(music.file_path):
                files_removed += 1
            music.file_path = None

        for short in song.shorts or []:
            for attr in ("clip_path", "final_clip_path"):
                path = getattr(short, attr, None)
                if _unlink(path):
                    files_removed += 1
                setattr(short, attr, None)

        files_removed += _clear_song_dirs(media_root, str(song.id))

        stamp = f"[media_cleaned {today.isoformat()}]"
        song.notes = f"{notes.strip()}\n{stamp}".strip() if notes.strip() else stamp
        cleaned_songs.append(str(song.id))

    db.commit()
    return {
        "as_of": today.isoformat(),
        "cleaned_count": len(cleaned_songs),
        "cleaned_song_ids": cleaned_songs,
        "files_or_dirs_removed": files_removed,
        "skipped": skipped,
    }
