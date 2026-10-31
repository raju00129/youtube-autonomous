"""Publish final mix + Shorts to YouTube (upload, thumbnail, playlists)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import SongProject
from app.providers import youtube as yt
from app.providers.youtube import YouTubeUploadError
from app.progress import ProgressFn, report

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

ProgressCB = ProgressFn | None


class PublishError(RuntimeError):
    pass


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

    privacy = "public"
    publish_at_iso: str | None = None
    when = publish_at
    if publish_now:
        when = datetime.now(tz=IST)
        privacy = "public"
    else:
        if when is None:
            raise PublishError("publish_at required when not publishing immediately")
        if when.tzinfo is None:
            when = when.replace(tzinfo=IST)
        # Future schedule → private until publishAt
        if when > datetime.now(tz=timezone.utc):
            privacy = "private"
            publish_at_iso = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            privacy = "public"

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
        db.flush()
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

    # --- Shorts ---
    shorts = sorted(song.shorts or [], key=lambda s: s.slot_index)
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
        try:
            up = yt.upload_video(
                file_path=clip,
                title=short_title,
                description=short_desc,
                tags=tags,
                privacy_status=privacy,
                publish_at=publish_at_iso,
            )
        except YouTubeUploadError as exc:
            results["shorts"].append(
                {"slot_index": short.slot_index, "error": str(exc)}
            )
            continue
        short.youtube_video_id = up["video_id"]
        short.youtube_url = up["url"]
        short.stage = "published"
        db.flush()
        results["shorts"].append(
            {
                "slot_index": short.slot_index,
                "video_id": up["video_id"],
                "url": up["url"],
                "related_video_id": video_id,
                "related_video_url": url,
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
    short_bits = [
        f"Short {s['slot_index']}: {s['url']} → related {s.get('related_video_url') or url}"
        for s in results["shorts"]
        if s.get("url")
    ]
    note = f"Published long-form: {song.youtube_url}"
    if short_bits:
        note += " · " + " · ".join(short_bits)
    else:
        note += " · Shorts: none uploaded (check final Short clips)"
    note += (
        " (Description link points to full song. YouTube Studio “Related video” pill "
        "is not available via API — set once in Studio if you want the in-player chip.)"
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
