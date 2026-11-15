"""Publish final mix + Shorts to YouTube (upload, thumbnail, playlists)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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


def daypart_for_song(song: SongProject) -> str:
    """Morning = long video only; evening = Short only (channel strategy)."""
    for slot in song.schedule_slots or []:
        part = (getattr(slot, "daypart", None) or "").strip().lower()
        if part in {"morning", "evening"}:
            return part
    if song.publish_at:
        return _daypart_from_when(song.publish_at)
    return "morning"


def publish_targets_for_daypart(daypart: str) -> dict[str, bool]:
    """What to upload for this daypart."""
    part = (daypart or "morning").strip().lower()
    if part == "evening":
        return {"longform": False, "shorts": True}
    return {"longform": True, "shorts": False}


def same_day_morning_longform(
    db: Session, song: SongProject
) -> tuple[str | None, str | None]:
    """Find today's morning long-form video so evening Shorts can link to it."""
    when = song.publish_at
    if when is None:
        return None, None
    local = when.astimezone(IST) if when.tzinfo else when.replace(tzinfo=IST)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    candidates = db.scalars(
        select(SongProject)
        .options(selectinload(SongProject.schedule_slots))
        .where(SongProject.id != song.id)
        .where(SongProject.youtube_video_id.is_not(None))
        .where(SongProject.publish_at.is_not(None))
        .where(SongProject.publish_at >= day_start)
        .where(SongProject.publish_at < day_end)
        .order_by(SongProject.publish_at.asc())
    ).all()
    for other in candidates:
        if daypart_for_song(other) != "morning":
            continue
        vid = other.youtube_video_id
        if vid:
            return vid, other.youtube_url or f"https://www.youtube.com/watch?v={vid}"
    for other in candidates:
        pa = other.publish_at
        if pa is None or not other.youtube_video_id:
            continue
        local_pa = pa.astimezone(IST) if pa.tzinfo else pa.replace(tzinfo=IST)
        if local_pa.hour < 12:
            vid = other.youtube_video_id
            return vid, other.youtube_url or f"https://www.youtube.com/watch?v={vid}"
    return None, None


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
    """Upload by daypart: morning = long video only; evening = Short only."""
    if not yt.is_connected():
        raise PublishError("YouTube not connected — open /api/v1/youtube/auth first")
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
    if song.publish_at is None:
        song.publish_at = when

    daypart = daypart_for_song(song)
    targets = publish_targets_for_daypart(daypart)
    privacy, publish_at_iso = _youtube_schedule_fields(when)
    apply_short_publish_times(song, when)
    stagger_h = short_stagger_hours_for(when)

    results: dict[str, Any] = {
        "longform": None,
        "shorts": [],
        "playlist": None,
        "daypart": daypart,
        "targets": targets,
    }
    video_id: str | None = song.youtube_video_id
    url: str | None = song.youtube_url

    # --- Long-form (morning only) ---
    if targets["longform"]:
        final = _require_file(song.final_video_path, "final mix")
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
            db.commit()
            results["longform"] = {"video_id": video_id, "url": url, "reused": False}

        if song.thumbnail_path and Path(song.thumbnail_path).exists() and video_id:
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
    else:
        report(on_progress, 10, f"{daypart.title()}: skipping long-form (Short-only slot)…")
        related_id, related_url = same_day_morning_longform(db, song)
        if related_id:
            video_id, url = related_id, related_url
            results["related_morning"] = {"video_id": related_id, "url": related_url}

    # --- Shorts (evening only) ---
    n_shorts = max(1, min(2, int(getattr(get_settings(), "shorts_count", 1) or 1)))
    shorts = [
        s
        for s in sorted(song.shorts or [], key=lambda s: s.slot_index)
        if int(s.slot_index) <= n_shorts
    ]
    if targets["shorts"]:
        if not shorts:
            raise PublishError("Evening Short slot has no Short clip — run Mix first")
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
                suffix = " #Shorts"
                short_title = (short_title[: 100 - len(suffix)] + suffix)[:100]
            short_desc = yt.short_related_description(
                base_description=(short.description or "").strip(),
                main_video_id=video_id or "",
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

        if video_id:
            report(on_progress, 92, "Pinning Shorts → morning long-form related link…")
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
    else:
        report(on_progress, 70, f"{daypart.title()}: skipping Shorts (long-form-only slot)…")

    song.publish_at = when
    song.stage = "published"
    db.flush()
    report(on_progress, 100, "Published to YouTube")

    if targets["longform"] and song.youtube_url:
        note = f"Published morning long-form: {song.youtube_url}"
    elif results["shorts"]:
        short_bits = [
            f"Short {s['slot_index']}: {s['url']}"
            + (f" → related {s['related_video_url']}" if s.get("related_video_url") else "")
            for s in results["shorts"]
            if s.get("url")
        ]
        note = "Published evening Short · " + " · ".join(short_bits)
    else:
        note = "Publish finished with nothing uploaded — check daypart targets / clips"
    return {
        "song_id": str(song.id),
        "stage": song.stage,
        "publish_at": when.isoformat() if when else None,
        "youtube_url": song.youtube_url,
        "youtube_video_id": song.youtube_video_id,
        "results": results,
        "note": note,
    }
