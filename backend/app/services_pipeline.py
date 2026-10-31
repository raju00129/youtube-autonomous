"""Schedule-driven auto prep (video+mix) and publish eligibility."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import SongProject
from app.progress import ProgressFn, report
from app.services_final import FinalMixError, mix_final_preview
from app.services_video import generate_visual_and_shorts

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

LOCKED_STAGES = frozenset({"prep_running", "publish_running", "published"})


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt


def _now() -> datetime:
    return datetime.now(tz=IST)


def _has_lyrics(song: SongProject) -> bool:
    return bool(song.lyrics_versions)


def _has_audio(song: SongProject) -> bool:
    music = song.music_generations[-1] if song.music_generations else None
    return bool(music and music.file_path and Path(music.file_path).exists())


def _has_thumbnail(song: SongProject) -> bool:
    path = getattr(song, "thumbnail_path", None)
    return bool(path and Path(path).exists())


def _has_visual(song: SongProject) -> bool:
    path = getattr(song, "video_clip_path", None)
    return bool(path and Path(path).exists())


def _has_final(song: SongProject) -> bool:
    path = getattr(song, "final_video_path", None)
    return bool(path and Path(path).exists())


def _shorts_final_ready(song: SongProject) -> bool:
    ready = sum(
        1
        for s in (song.shorts or [])
        if getattr(s, "final_clip_path", None) and Path(s.final_clip_path).exists()
    )
    return ready >= 2


def pipeline_status(song: SongProject) -> dict:
    """UI-facing auto pipeline status for a song."""
    settings = get_settings()
    lead = timedelta(minutes=int(settings.prep_lead_minutes or 60))
    publish_at = _aware(song.publish_at)
    now = _now()
    has_final = _has_final(song)
    published = song.stage == "published" or bool(song.youtube_video_id)

    prep_at = publish_at - lead if publish_at else None
    next_step = "idle"
    detail = ""
    if published:
        next_step = "done"
        detail = "Already published to YouTube"
    elif song.stage == "prep_running":
        next_step = "prep_running"
        detail = "Video + mix in progress…"
    elif song.stage == "publish_running":
        next_step = "publish_running"
        detail = "Uploading to YouTube…"
    elif not publish_at:
        next_step = "needs_schedule"
        detail = "Set publish_at to enable auto video/mix/publish"
    elif not (_has_lyrics(song) and _has_audio(song) and _has_thumbnail(song)):
        next_step = "needs_manual"
        missing = []
        if not _has_lyrics(song):
            missing.append("lyrics")
        if not _has_audio(song):
            missing.append("Suno audio")
        if not _has_thumbnail(song):
            missing.append("thumbnail")
        detail = "Need: " + ", ".join(missing)
    elif not has_final:
        if prep_at and now < prep_at:
            next_step = "wait_prep"
            detail = f"Auto video+mix ~{prep_at.strftime('%d %b %H:%M IST')} (1h before publish)"
        else:
            next_step = "due_prep"
            detail = "Due for auto video+mix (Gemini→Kling) then final mix"
    elif publish_at and now < publish_at:
        next_step = "wait_publish"
        detail = f"Will auto-publish at {publish_at.strftime('%d %b %H:%M IST')} unless you Publish now"
    else:
        next_step = "due_publish"
        detail = "Due for auto YouTube publish"

    return {
        "next_step": next_step,
        "detail": detail,
        "publish_at": publish_at.isoformat() if publish_at else None,
        "prep_at": prep_at.isoformat() if prep_at else None,
        "prep_lead_minutes": int(settings.prep_lead_minutes or 60),
        "video_provider": settings.video_provider,
        "has_lyrics": _has_lyrics(song),
        "has_audio": _has_audio(song),
        "has_thumbnail": _has_thumbnail(song),
        "has_visual": _has_visual(song),
        "has_final": has_final,
        "published": published,
    }


def load_songs_for_pipeline(db: Session) -> list[SongProject]:
    return list(
        db.scalars(
            select(SongProject)
            .options(
                selectinload(SongProject.lyrics_versions),
                selectinload(SongProject.music_generations),
                selectinload(SongProject.shorts),
            )
            .where(SongProject.publish_at.is_not(None))
            .where(SongProject.stage.notin_(["published"]))
            .order_by(SongProject.publish_at.asc())
        ).all()
    )


def songs_due_for_prep(db: Session) -> list[SongProject]:
    settings = get_settings()
    lead = timedelta(minutes=int(settings.prep_lead_minutes or 60))
    grace = timedelta(minutes=int(settings.prep_grace_minutes or 15))
    now = _now()
    due: list[SongProject] = []
    for song in load_songs_for_pipeline(db):
        if song.stage in LOCKED_STAGES:
            continue
        if _has_final(song) and _shorts_final_ready(song):
            continue
        if not (_has_lyrics(song) and _has_audio(song) and _has_thumbnail(song)):
            continue
        publish_at = _aware(song.publish_at)
        if not publish_at:
            continue
        window_open = publish_at - lead
        window_close = publish_at + grace
        if window_open <= now <= window_close:
            due.append(song)
    return due


def songs_due_for_publish(db: Session) -> list[SongProject]:
    now = _now()
    due: list[SongProject] = []
    for song in load_songs_for_pipeline(db):
        if song.stage in {"publish_running", "published"} or song.youtube_video_id:
            continue
        if song.stage == "prep_running":
            continue
        publish_at = _aware(song.publish_at)
        if not publish_at or publish_at > now:
            continue
        if not _has_final(song):
            continue
        if not song.youtube_playlist_id:
            logger.info("skip auto-publish %s — no playlist", song.id)
            continue
        due.append(song)
    return due


def run_prep_visual_mix(
    db: Session,
    song: SongProject,
    *,
    on_progress: ProgressFn | None = None,
) -> dict:
    """Generate visual (if needed) + always ensure final A/V mix."""
    prev_stage = song.stage
    song.stage = "prep_running"
    db.flush()

    result: dict = {"song_id": str(song.id)}
    try:
        need_visual = not _has_visual(song)
        if need_visual:
            report(on_progress, 5, "Auto-prep: generating visual…")
            visual = generate_visual_and_shorts(db, song, on_progress=on_progress)
            result["visual"] = visual
            result["engine"] = visual.get("engine")
        else:
            report(on_progress, 40, "Visual already present — mixing…")
            result["engine"] = "existing_visual"

        report(on_progress, 70, "Auto-prep: mixing audio + video + Shorts…")
        mix = mix_final_preview(db, song)
        result["mix"] = mix
        song.stage = "final_ready"
        # Keep a short status line in notes without wiping user notes entirely
        stamp = _now().strftime("%Y-%m-%d %H:%M IST")
        engine = result.get("engine") or "unknown"
        line = f"[auto-prep {stamp}] engine={engine}; final ready"
        notes = (song.notes or "").strip()
        if "[auto-prep" in notes:
            # replace last auto-prep line
            lines = [ln for ln in notes.splitlines() if not ln.startswith("[auto-prep")]
            lines.append(line)
            song.notes = "\n".join(lines).strip()
        else:
            song.notes = f"{notes}\n{line}".strip() if notes else line
        db.flush()
        report(on_progress, 100, "Auto-prep complete")
        result["stage"] = song.stage
        result["note"] = line
        return result
    except Exception as exc:
        song.stage = prev_stage if prev_stage not in {"prep_running"} else "music_ready"
        err_line = f"[auto-prep-error {_now().strftime('%Y-%m-%d %H:%M IST')}] {exc}"
        notes = (song.notes or "").strip()
        song.notes = f"{notes}\n{err_line}".strip() if notes else err_line
        db.flush()
        raise
