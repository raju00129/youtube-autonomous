"""Ready queue + anytime publish controls (review before going live)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import ScheduleSlot, ShortProject, SongProject
from app.providers import youtube as yt

router = APIRouter(prefix="/publish", tags=["publish"])
IST = ZoneInfo("Asia/Kolkata")


def readiness(song: SongProject) -> dict:
    approved_lyrics = any(l.approved for l in song.lyrics_versions) or (
        bool(song.lyrics_versions) and song.stage in {"music_ready", "ready_to_publish", "queued_publish", "published"}
    )
    has_lyrics = bool(song.lyrics_versions)
    has_music = bool(song.music_generations)
    has_thumbnail = bool(getattr(song, "thumbnail_path", None))
    has_video_clip = bool(getattr(song, "video_clip_path", None))
    has_video = has_video_clip or song.stage in {
        "video_ready",
        "final_ready",
        "ready_to_publish",
        "queued_publish",
        "published",
    }
    has_final = bool(getattr(song, "final_video_path", None))
    shorts_cut = sum(1 for s in (song.shorts or []) if getattr(s, "clip_path", None)) >= 2
    shorts_final = sum(1 for s in (song.shorts or []) if getattr(s, "final_clip_path", None)) >= 2
    reviewable = has_lyrics and has_music
    publishable = reviewable and has_final and bool(getattr(song, "youtube_playlist_id", None))
    can_set_time = reviewable

    checks = [
        {"key": "lyrics", "label": "Lyrics ready", "ok": has_lyrics},
        {"key": "lyrics_approved", "label": "Lyrics approved", "ok": approved_lyrics},
        {"key": "audio", "label": "Song audio uploaded", "ok": has_music},
        {"key": "video", "label": "Kling visual clip (720p 16:9)", "ok": has_video},
        {
            "key": "shorts_clips",
            "label": "2 Shorts cut from same clip",
            "ok": shorts_cut,
        },
        {
            "key": "final_mix",
            "label": "Final A/V mix (audio+video preview)",
            "ok": has_final,
        },
        {
            "key": "shorts_final",
            "label": "2 Short finals mixed with audio",
            "ok": shorts_final,
        },
        {"key": "thumbnail", "label": "Thumbnail (logo + deity + title)", "ok": has_thumbnail},
        {
            "key": "shorts",
            "label": "2 Shorts planned",
            "ok": len(song.shorts or []) >= 2,
        },
        {
            "key": "playlist",
            "label": "YouTube playlist selected",
            "ok": bool(getattr(song, "youtube_playlist_id", None)),
        },
    ]
    missing = [c["label"] for c in checks if not c["ok"]]
    return {
        "checks": checks,
        "reviewable": reviewable,
        "publishable": publishable,
        "can_set_time": can_set_time,
        "missing": missing,
        "queue_bucket": (
            "published"
            if song.stage == "published"
            else "queued"
            if song.stage in {"queued_publish", "ready_to_publish"}
            else "ready_for_review"
            if reviewable
            else "in_progress"
        ),
    }


def _item(song: SongProject) -> dict:
    ready = readiness(song)
    music = song.music_generations[-1] if song.music_generations else None
    return {
        "id": str(song.id),
        "title": song.title,
        "deity": song.deity,
        "stage": song.stage,
        "publish_at": song.publish_at.isoformat() if song.publish_at else None,
        "youtube_title": song.youtube_title,
        "youtube_url": song.youtube_url,
        "youtube_video_id": song.youtube_video_id,
        "youtube_playlist_id": getattr(song, "youtube_playlist_id", None),
        "youtube_playlist_title": getattr(song, "youtube_playlist_title", None),
        "shorts_playlist_id": getattr(song, "shorts_playlist_id", None),
        "shorts_playlist_title": getattr(song, "shorts_playlist_title", None),
        "music_file": music.original_filename if music else None,
        "shorts_count": len(song.shorts or []),
        "shorts": [
            {
                "slot_index": s.slot_index,
                "youtube_video_id": getattr(s, "youtube_video_id", None),
                "youtube_url": getattr(s, "youtube_url", None),
                "stage": s.stage,
            }
            for s in (song.shorts or [])
        ],
        "readiness": ready,
        "pipeline": _pipeline_for(song),
        "studio_path": f"/songs/{song.id}",
    }


def _pipeline_for(song: SongProject) -> dict:
    from app.services_pipeline import pipeline_status

    return pipeline_status(song)


@router.get("/queue")
def publish_queue(db: Session = Depends(get_db)) -> dict:
    """List songs grouped so you can review and publish anytime (including mid-week)."""
    rows = db.scalars(
        select(SongProject)
        .options(
            selectinload(SongProject.lyrics_versions),
            selectinload(SongProject.music_generations),
            selectinload(SongProject.shorts),
        )
        .order_by(SongProject.updated_at.desc())
    ).all()

    buckets: dict[str, list] = {
        "ready_for_review": [],
        "queued": [],
        "in_progress": [],
        "published": [],
    }
    for song in rows:
        item = _item(song)
        buckets[item["readiness"]["queue_bucket"]].append(item)

    return {
        "data": {
            "youtube_connected": yt.is_connected(),
            "buckets": buckets,
            "counts": {k: len(v) for k, v in buckets.items()},
            "note": (
                "Ready for review = lyrics + audio + thumbnail. Set publish_at: auto video+mix "
                "(Gemini→Kling) ~1h before, then auto YouTube at the scheduled time. "
                "Publish now still uploads immediately when the final mix is ready."
            ),
        }
    }


class SchedulePublishBody(BaseModel):
    publish_at: datetime | None = Field(
        default=None,
        description="Any IST/UTC datetime. Omit with publish_now=true to go ASAP.",
    )
    publish_now: bool = False
    sync_shorts: bool = True


@router.post("/songs/{song_id}/schedule")
def schedule_or_publish_now(
    song_id: uuid.UUID,
    body: SchedulePublishBody,
    db: Session = Depends(get_db),
) -> dict:
    song = db.scalar(
        select(SongProject)
        .where(SongProject.id == song_id)
        .options(
            selectinload(SongProject.lyrics_versions),
            selectinload(SongProject.music_generations),
            selectinload(SongProject.shorts),
        )
    )
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    ready = readiness(song)
    if not ready["can_set_time"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Need lyrics + uploaded audio before setting publish time",
                "missing": ready["missing"],
            },
        )

    if body.publish_now:
        if not ready["publishable"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": (
                        "Preview the final A/V mix and select a playlist before Publish now"
                    ),
                    "missing": ready["missing"],
                },
            )
        if not yt.is_connected():
            raise HTTPException(
                status_code=400,
                detail="YouTube not connected — open /api/v1/youtube/auth first",
            )
        from app.services_publish import PublishError, publish_song_to_youtube

        try:
            published = publish_song_to_youtube(db, song, publish_now=True)
        except PublishError as exc:
            db.rollback()
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        when = song.publish_at or datetime.now(tz=IST)
        if body.sync_shorts:
            for short in song.shorts:
                short.publish_at = when

        slots = db.scalars(select(ScheduleSlot).where(ScheduleSlot.song_id == song.id)).all()
        for slot in slots:
            slot.publish_at = when
            slot.status = "published"

        db.commit()
        song = db.scalar(
            select(SongProject)
            .where(SongProject.id == song_id)
            .options(
                selectinload(SongProject.lyrics_versions),
                selectinload(SongProject.music_generations),
                selectinload(SongProject.shorts),
            )
        )
        assert song is not None
        return {
            "data": {
                **_item(song),
                "action": "published",
                "youtube_url": published.get("youtube_url"),
                "youtube_video_id": published.get("youtube_video_id"),
                "upload": published.get("results"),
                "message": published.get("note")
                or f"Published to YouTube: {published.get('youtube_url')}",
            }
        }

    if not body.publish_at:
        raise HTTPException(status_code=400, detail="provide publish_at or publish_now=true")
    when = body.publish_at
    if when.tzinfo is None:
        when = when.replace(tzinfo=IST)
    song.stage = "ready_to_publish"
    song.publish_at = when

    if body.sync_shorts:
        for short in song.shorts:
            short.publish_at = when

    # Keep linked schedule slots in sync
    slots = db.scalars(select(ScheduleSlot).where(ScheduleSlot.song_id == song.id)).all()
    for slot in slots:
        slot.publish_at = when
        slot.status = "ready_to_publish"

    db.commit()
    db.refresh(song)
    song = db.scalar(
        select(SongProject)
        .where(SongProject.id == song_id)
        .options(
            selectinload(SongProject.lyrics_versions),
            selectinload(SongProject.music_generations),
            selectinload(SongProject.shorts),
        )
    )
    assert song is not None
    return {
        "data": {
            **_item(song),
            "action": "scheduled",
            "message": f"Scheduled for {when.isoformat()} — change anytime from Ready queue.",
        }
    }
