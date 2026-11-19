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


def _song_channel_key(song: SongProject) -> str:
    return (getattr(song, "channel_key", None) or "te").strip().lower() or "te"


def _daypart_from_when(when: datetime) -> str:
    local = when.astimezone(IST) if when.tzinfo else when.replace(tzinfo=IST)
    return "morning" if local.hour < 12 else "evening"


def daypart_for_song(song: SongProject) -> str:
    """Morning or evening slot for this song (both publish long video + Short)."""
    for slot in song.schedule_slots or []:
        part = (getattr(slot, "daypart", None) or "").strip().lower()
        if part in {"morning", "evening"}:
            return part
    if song.publish_at:
        return _daypart_from_when(song.publish_at)
    return "morning"


def publish_targets_for_daypart(daypart: str) -> dict[str, bool]:
    """Both morning and evening publish a long video + Short together."""
    _ = daypart
    return {"longform": True, "shorts": True}


def evening_short_at(day: datetime) -> datetime:
    """Evening Short release time on the same IST calendar day as `day`."""
    from app.calendar_rules import DAYPART_FLAVOR

    local = day.astimezone(IST) if day.tzinfo else day.replace(tzinfo=IST)
    flavor = DAYPART_FLAVOR.get("evening") or {}
    hour = int(flavor.get("default_hour", 19))
    minute = int(flavor.get("default_minute", 0))
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0)


def same_day_morning_song(
    db: Session,
    *,
    on_day: datetime | None = None,
    exclude_id=None,
    require_youtube: bool = False,
) -> SongProject | None:
    """Morning song for this IST calendar day (evening Short reuses its A/V)."""
    if on_day is None:
        return None
    local = on_day.astimezone(IST) if on_day.tzinfo else on_day.replace(tzinfo=IST)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    q = (
        select(SongProject)
        .options(
            selectinload(SongProject.schedule_slots),
            selectinload(SongProject.shorts),
        )
        .where(SongProject.publish_at.is_not(None))
        .where(SongProject.publish_at >= day_start)
        .where(SongProject.publish_at < day_end)
        .order_by(SongProject.publish_at.asc())
    )
    if exclude_id is not None:
        q = q.where(SongProject.id != exclude_id)
    if require_youtube:
        q = q.where(SongProject.youtube_video_id.is_not(None))
    candidates = db.scalars(q).all()
    for other in candidates:
        if daypart_for_song(other) == "morning":
            return other
    for other in candidates:
        pa = other.publish_at
        if pa is None:
            continue
        local_pa = pa.astimezone(IST) if pa.tzinfo else pa.replace(tzinfo=IST)
        if local_pa.hour < 12:
            return other
    return None


def same_day_morning_longform(
    db: Session, song: SongProject
) -> tuple[str | None, str | None]:
    """YouTube id/url for today's morning long-form (related link for Short)."""
    other = same_day_morning_song(
        db, on_day=song.publish_at, exclude_id=song.id, require_youtube=True
    )
    if other and other.youtube_video_id:
        vid = other.youtube_video_id
        return vid, other.youtube_url or f"https://www.youtube.com/watch?v={vid}"
    # Same song is the morning long-form
    if song.youtube_video_id and daypart_for_song(song) == "morning":
        vid = song.youtube_video_id
        return vid, song.youtube_url or f"https://www.youtube.com/watch?v={vid}"
    return None, None


def short_stagger_hours_for(when: datetime) -> int:
    """Legacy Short 2 stagger (unused when SHORTS_COUNT=1)."""
    from app.calendar_rules import DAYPART_FLAVOR

    part = _daypart_from_when(when)
    flavor = DAYPART_FLAVOR.get(part) or {}
    configured = flavor.get("short2_stagger_hours")
    if configured is not None:
        return int(configured)
    return int(getattr(get_settings(), "short_stagger_hours", 5) or 5)


def short_release_at(main_when: datetime, slot_index: int) -> datetime:
    """Short publishes with the long video; Short 2+ can stagger later if enabled."""
    when = main_when
    if when.tzinfo is None:
        when = when.replace(tzinfo=IST)
    # Only Short 1 is used by default; keep stagger for a paused Short 2
    if int(slot_index) >= 2:
        hours = short_stagger_hours_for(when)
        if hours > 0:
            return when + timedelta(hours=hours)
    return when


def apply_short_publish_times(song: SongProject, main_when: datetime) -> None:
    """Stamp each Short's publish_at with the long-form release time."""
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


def _upload_shorts_from_song(
    db: Session,
    song: SongProject,
    *,
    when: datetime,
    video_id: str | None,
    url: str | None,
    on_progress: ProgressCB = None,
) -> list[dict[str, Any]]:
    """Upload Short clips cut from this song's existing A/V (evening release)."""
    title = (song.youtube_title or song.title or "Ragam Spiritual Telugu").strip()[:100]
    tags = song.youtube_tags
    n_shorts = max(1, min(2, int(getattr(get_settings(), "shorts_count", 1) or 1)))
    shorts = [
        s
        for s in sorted(song.shorts or [], key=lambda s: s.slot_index)
        if int(s.slot_index) <= n_shorts
    ]
    if not shorts:
        raise PublishError("No Short clip on morning song — run Mix first")
    results: list[dict[str, Any]] = []
    n = max(len(shorts), 1)
    for i, short in enumerate(shorts):
        pct = 55 + int(35 * (i / n))
        if short.youtube_video_id:
            report(on_progress, pct, f"Short {short.slot_index} already uploaded — reusing…")
            results.append(
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
            results.append({"slot_index": short.slot_index, "error": "no final short clip"})
            continue
        report(on_progress, pct, f"Uploading Short {short.slot_index} from morning video…")
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
        short_when = short.publish_at or short_release_at(when, int(short.slot_index))
        if short_when.tzinfo is None:
            short_when = short_when.replace(tzinfo=IST)
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
                channel_key=_song_channel_key(song),
                language=getattr(song, "language", None),
            )
        except YouTubeUploadError as exc:
            results.append({"slot_index": short.slot_index, "error": str(exc)})
            continue
        short.youtube_video_id = up["video_id"]
        short.youtube_url = up["url"]
        short.stage = "published" if short_privacy == "public" else "scheduled"
        db.commit()
        results.append(
            {
                "slot_index": short.slot_index,
                "video_id": up["video_id"],
                "url": up["url"],
                "related_video_id": video_id,
                "related_video_url": url,
                "publish_at": short_when.isoformat(),
                "privacy": short_privacy,
                "reused": False,
            }
        )
        pl = song.shorts_playlist_id or song.youtube_playlist_id
        if pl:
            try:
                yt.add_to_playlist(
                    playlist_id=pl,
                    video_id=up["video_id"],
                    channel_key=_song_channel_key(song),
                )
            except YouTubeUploadError as exc:
                logger.warning("shorts playlist add failed: %s", exc)

    if video_id:
        report(on_progress, 92, "Pinning Short → morning long-form related link…")
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
                    channel_key=_song_channel_key(song),
                    language=getattr(song, "language", None),
                )
                for row in results:
                    if row.get("slot_index") == short.slot_index:
                        row["related_video_id"] = video_id
                        row["related_video_url"] = url
                        row["description_pinned"] = True
            except YouTubeUploadError as exc:
                logger.warning("short related-link update failed: %s", exc)
    return results


def publish_evening_short_from_morning(
    db: Session,
    song: SongProject,
    *,
    publish_now: bool = True,
    on_progress: ProgressCB = None,
) -> dict[str, Any]:
    """Evening: upload Short cut from this morning song (no new A/V)."""
    ck = _song_channel_key(song)
    if not yt.is_connected(ck):
        raise PublishError(
            f"YouTube not connected for '{ck}' — open /api/v1/youtube/auth?channel_key={ck}"
        )
    if not song.youtube_video_id:
        raise PublishError("Morning long video must be live before evening Short")
    if not song.youtube_playlist_id:
        raise PublishError("Select a YouTube playlist before publishing")

    when = datetime.now(tz=IST) if publish_now else (song.publish_at or datetime.now(tz=IST))
    if when.tzinfo is None:
        when = when.replace(tzinfo=IST)
    apply_short_publish_times(song, song.publish_at or when)
    video_id = song.youtube_video_id
    url = song.youtube_url or f"https://www.youtube.com/watch?v={video_id}"
    report(on_progress, 10, "Evening Short from morning video…")
    shorts = _upload_shorts_from_song(
        db,
        song,
        when=when,
        video_id=video_id,
        url=url,
        on_progress=on_progress,
    )
    db.flush()
    report(on_progress, 100, "Evening Short published")
    short_bits = [
        f"Short {s['slot_index']}: {s['url']}"
        + (f" → related {s['related_video_url']}" if s.get("related_video_url") else "")
        for s in shorts
        if s.get("url")
    ]
    note = "Published evening Short from morning video · " + (
        " · ".join(short_bits) if short_bits else "no Short uploaded"
    )
    return {
        "song_id": str(song.id),
        "stage": song.stage,
        "publish_at": when.isoformat(),
        "youtube_url": song.youtube_url,
        "youtube_video_id": song.youtube_video_id,
        "results": {"longform": None, "shorts": shorts, "daypart": "evening", "from_morning": True},
        "note": note,
    }


def publish_song_to_youtube(
    db: Session,
    song: SongProject,
    *,
    publish_now: bool = True,
    publish_at: datetime | None = None,
    on_progress: ProgressCB = None,
) -> dict[str, Any]:
    """Publish long video + Short together for morning or evening songs."""
    from app.channels import get_channel

    ck = _song_channel_key(song)
    if not yt.is_connected(ck):
        raise PublishError(
            f"YouTube not connected for '{ck}' — open /api/v1/youtube/auth?channel_key={ck}"
        )
    if not song.youtube_playlist_id:
        raise PublishError("Select a YouTube playlist before publishing")

    title = (
        song.youtube_title or song.title or get_channel(ck).display_name
    ).strip()[:100]
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

    results: dict[str, Any] = {
        "longform": None,
        "shorts": [],
        "playlist": None,
        "daypart": daypart,
        "targets": targets,
    }
    video_id: str | None = song.youtube_video_id
    url: str | None = song.youtube_url

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
                channel_key=ck,
                language=getattr(song, "language", None),
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
            yt.set_thumbnail(
                video_id=video_id,
                image_path=song.thumbnail_path,
                channel_key=ck,
            )
            results["thumbnail"] = "set"
        except YouTubeUploadError as exc:
            logger.warning("thumbnail set failed: %s", exc)
            results["thumbnail"] = f"skipped: {exc}"

    report(on_progress, 48, "Adding long-form to playlist…")
    try:
        yt.add_to_playlist(
            playlist_id=song.youtube_playlist_id,
            video_id=video_id,
            channel_key=ck,
        )
        results["playlist"] = song.youtube_playlist_id
    except YouTubeUploadError as exc:
        logger.warning("playlist add failed: %s", exc)
        results["playlist_error"] = str(exc)

    if targets.get("shorts"):
        report(on_progress, 70, "Uploading Short with the long video…")
        results["shorts"] = _upload_shorts_from_song(
            db,
            song,
            when=when,
            video_id=video_id,
            url=url,
            on_progress=on_progress,
        )

    song.publish_at = when
    song.stage = "published"
    db.flush()
    short_bits = [
        f"Short {s['slot_index']}: {s['url']}"
        for s in (results.get("shorts") or [])
        if s.get("url")
    ]
    report(on_progress, 100, f"Published {daypart} long video + Short")
    note = f"Published {daypart} long-form: {song.youtube_url}"
    if short_bits:
        note += " · " + " · ".join(short_bits)
    return {
        "song_id": str(song.id),
        "stage": song.stage,
        "publish_at": when.isoformat() if when else None,
        "youtube_url": song.youtube_url,
        "youtube_video_id": song.youtube_video_id,
        "results": results,
        "note": note,
    }
