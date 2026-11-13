"""Publish final mix + Shorts to YouTube (upload, thumbnail, playlists)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import SongProject
from app.providers import youtube as yt
from app.providers.youtube import YouTubeUploadError
from app.progress import ProgressFn, report

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

ProgressCB = ProgressFn | None


class PublishError(RuntimeError):
    pass


def _daypart_from_when(when: datetime) -> str:
    local = when.astimezone(IST) if when.tzinfo else when.replace(tzinfo=IST)
    return "morning" if local.hour < 12 else "evening"


def short_stagger_hours_for(when: datetime) -> int:
    """Short 2 offset: morning → mid-morning; evening → Shorts peak (~9 PM)."""
    from app.calendar_rules import DAYPART_FLAVOR

    part = _daypart_from_when(when)
    flavor = DAYPART_FLAVOR.get(part) or {}
    configured = flavor.get("short2_stagger_hours")
    if configured is not None:
        return int(configured)
    return int(getattr(get_settings(), "short_stagger_hours", 5) or 5)


def short_release_at(main_when: datetime, slot_index: int) -> datetime:
    """Short 1 with the long-form; Short 2+ staggered by daypart peak."""
    when = main_when
    if when.tzinfo is None:
        when = when.replace(tzinfo=IST)
    hours = short_stagger_hours_for(when)
    if int(slot_index) >= 2 and hours > 0:
        return when + timedelta(hours=hours)
    return when


def apply_short_publish_times(song: SongProject, main_when: datetime) -> None:
    """Stamp each Short's publish_at from the main video time."""
    for short in song.shorts or []:
        short.publish_at = short_release_at(main_when, int(short.slot_index))


def _youtube_schedule_fields(when: datetime) -> tuple[str, str | None]:
    """Return (privacy_status, publish_at_iso) for YouTube upload."""
    aware = when if when.tzinfo else when.replace(tzinfo=IST)
    now = datetime.now(tz=timezone.utc)
    if aware.astimezone(timezone.utc) > now:
        return "private", aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "public", None


def _require_file(path: str | None, label: str) -> Path:
    if not path:
        raise PublishError(f"Missing {label}")
    p = Path(path)
    if not p.exists():
        raise PublishError(f"{label} file missing on disk: {p}")
    return p


def publish_song_to_youtube(
    db: Session,
    song: SongProject,
    *,
    publish_now: bool = True,
    publish_at: datetime | None = None,
    on_progress: ProgressCB = None,
) -> dict[str, Any]:
    """Upload long-form + 2 Shorts, set thumbnail, add to playlists."""
    if not yt.is_connected():
        raise PublishError("YouTube not connected — open /api/v1/youtube/auth first")

    final = _require_file(song.final_video_path, "final mix")
    if not song.youtube_playlist_id:
        raise PublishError("Select a YouTube playlist before publishing")

    title = (song.youtube_title or song.title or "Ragam Spiritual Telugu").strip()[:100]
    description = (song.youtube_description or "").strip()
    tags = song.youtube_tags

    when = publish_at
    if publish_now:
        when = datetime.now(tz=IST)
    else:
        if when is None:
            raise PublishError("publish_at required when not publishing immediately")
        if when.tzinfo is None:
            when = when.replace(tzinfo=IST)
    privacy, publish_at_iso = _youtube_schedule_fields(when)
    apply_short_publish_times(song, when)
    stagger_h = short_stagger_hours_for(when)

    results: dict[str, Any] = {"longform": None, "shorts": [], "playlist": None}

    # --- Long-form ---
    if song.youtube_video_id:
        report(on_progress, 15, "Long-form already on YouTube — reusing…")
        video_id = song.youtube_video_id
        url = song.youtube_url or f"https://www.youtube.com/watch?v={video_id}"
        results["longform"] = {"video_id": video_id, "url": url, "reused": True}
    else:
        report(on_progress, 8, "Uploading long-form to YouTube…")
        try:
            uploaded = yt.upload_video(
                file_path=final,
                title=title,
                description=description,
                tags=tags,
                privacy_status=privacy,
                publish_at=publish_at_iso,
            )
        except YouTubeUploadError as exc:
            raise PublishError(str(exc)) from exc
        video_id = uploaded["video_id"]
        url = uploaded["url"]
        song.youtube_video_id = video_id
        song.youtube_url = url
        # Commit now: if a later step fails, a retry must reuse this upload.
        db.commit()
        results["longform"] = {"video_id": video_id, "url": url, "reused": False}

    # Thumbnail (best-effort — channel may need verification for custom thumbs)
    if song.thumbnail_path and Path(song.thumbnail_path).exists():
        report(on_progress, 40, "Setting YouTube thumbnail…")
        try:
            yt.set_thumbnail(video_id=video_id, image_path=song.thumbnail_path)
            results["thumbnail"] = "set"
        except YouTubeUploadError as exc:
            logger.warning("thumbnail set failed: %s", exc)
            results["thumbnail"] = f"skipped: {exc}"

    report(on_progress, 48, "Adding long-form to playlist…")
    try:
        yt.add_to_playlist(playlist_id=song.youtube_playlist_id, video_id=video_id)
        results["playlist"] = song.youtube_playlist_id
    except YouTubeUploadError as exc:
        logger.warning("playlist add failed: %s", exc)
        results["playlist_error"] = str(exc)

    # --- Shorts (respect SHORTS_COUNT; Short 2 paused when count=1) ---
    n_shorts = max(1, min(2, int(getattr(get_settings(), "shorts_count", 1) or 1)))
    shorts = [
        s
        for s in sorted(song.shorts or [], key=lambda s: s.slot_index)
        if int(s.slot_index) <= n_shorts
    ]
    n = max(len(shorts), 1)
    for i, short in enumerate(shorts):
        pct = 55 + int(35 * (i / n))
        if short.youtube_video_id:
            report(on_progress, pct, f"Short {short.slot_index} already uploaded — reusing…")
            results["shorts"].append(
                {
                    "slot_index": short.slot_index,
                    "video_id": short.youtube_video_id,
                    "url": short.youtube_url,
                    "related_video_id": video_id,
                    "related_video_url": url,
                    "reused": True,
                }
            )
            continue
        clip = short.final_clip_path or short.clip_path
        if not clip or not Path(clip).exists():
            results["shorts"].append(
                {"slot_index": short.slot_index, "error": "no final short clip"}
            )
            continue
        report(on_progress, pct, f"Uploading Short {short.slot_index}…")
        short_title = (short.title or f"{title} | Short {short.slot_index}")[:100]
        if "#Shorts" not in short_title and "#shorts" not in short_title.lower():
            # Keep under 100 chars
            suffix = " #Shorts"
            short_title = (short_title[: 100 - len(suffix)] + suffix)[:100]
        short_desc = yt.short_related_description(
            base_description=(short.description or "").strip(),
            main_video_id=video_id,
            main_url=url,
        )
        short.description = short_desc
        short_when = short_release_at(when, int(short.slot_index))
        short.publish_at = short_when
        short_privacy, short_publish_at_iso = _youtube_schedule_fields(short_when)
        try:
            up = yt.upload_video(
                file_path=clip,
                title=short_title,
                description=short_desc,
                tags=tags,
                privacy_status=short_privacy,
                publish_at=short_publish_at_iso,
            )
        except YouTubeUploadError as exc:
            results["shorts"].append(
                {"slot_index": short.slot_index, "error": str(exc)}
            )
            continue
        short.youtube_video_id = up["video_id"]
        short.youtube_url = up["url"]
        short.stage = "published" if short_privacy == "public" else "scheduled"
        db.commit()
        results["shorts"].append(
            {
                "slot_index": short.slot_index,
                "video_id": up["video_id"],
                "url": up["url"],
                "related_video_id": video_id,
                "related_video_url": url,
                "publish_at": short_when.isoformat(),
                "privacy": short_privacy,
                "stagger_hours": 0 if int(short.slot_index) < 2 else stagger_h,
                "reused": False,
            }
        )
        pl = song.shorts_playlist_id or song.youtube_playlist_id
        if pl:
            try:
                yt.add_to_playlist(playlist_id=pl, video_id=up["video_id"])
            except YouTubeUploadError as exc:
                logger.warning("shorts playlist add failed: %s", exc)

    # Always re-pin Short descriptions to the long-form (covers reused Shorts too)
    report(on_progress, 92, "Pinning Shorts → long-form related link…")
    for short in shorts:
        if not short.youtube_video_id:
            continue
        short_title = (short.title or f"{title} | Short {short.slot_index}")[:100]
        if "#Shorts" not in short_title and "#shorts" not in short_title.lower():
            suffix = " #Shorts"
            short_title = (short_title[: 100 - len(suffix)] + suffix)[:100]
        pinned = yt.short_related_description(
            base_description=(short.description or "").strip(),
            main_video_id=video_id,
            main_url=url,
        )
        short.description = pinned
        try:
            yt.update_video_snippet(
                video_id=short.youtube_video_id,
                title=short_title,
                description=pinned,
                tags=tags,
            )
            for row in results["shorts"]:
                if row.get("slot_index") == short.slot_index:
                    row["related_video_id"] = video_id
                    row["related_video_url"] = url
                    row["description_pinned"] = True
        except YouTubeUploadError as exc:
            logger.warning("short related-link update failed: %s", exc)

    song.publish_at = when
    song.stage = "published"
    db.flush()
    report(on_progress, 100, "Published to YouTube")
    short_bits = []
    for s in results["shorts"]:
        if not s.get("url"):
            continue
        delay = s.get("stagger_hours") or 0
        when_note = f" (+{delay}h)" if delay else " (with video)"
        short_bits.append(
            f"Short {s['slot_index']}{when_note}: {s['url']} → related {s.get('related_video_url') or url}"
        )
    note = f"Published long-form: {song.youtube_url}"
    if short_bits:
        note += " · " + " · ".join(short_bits)
    else:
        note += " · Shorts: none uploaded (check final Short clips)"
    note += (
        f" · Short 1 with main video; Short 2 scheduled +{stagger_h}h later. "
        "Description link points to full song."
    )
    return {
        "song_id": str(song.id),
        "stage": song.stage,
        "publish_at": when.isoformat() if when else None,
        "youtube_url": song.youtube_url,
        "youtube_video_id": song.youtube_video_id,
        "results": results,
        "note": note,
    }
