import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.providers import mureka as music_provider
from app.providers.mureka import MurekaError
from app.progress import celery_progress
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.smoke_ping")
def smoke_ping(message: str = "pong") -> dict[str, str]:
    return {"status": "ok", "message": message}


@celery_app.task(
    name="app.workers.tasks.visuals_generate",
    bind=True,
    soft_time_limit=1500,
    time_limit=1800,
)
def visuals_generate(self, song_id: str) -> dict[str, Any]:
    """Gemini→Kling + ffmpeg Shorts; progress via Celery PROGRESS for GET /jobs/{id}."""
    from app.db import SessionLocal
    from app.models import SongProject
    from app.providers.gemini_video import GeminiVideoError
    from app.providers.kling_video import KlingVideoError
    from app.services_video import generate_visual_and_shorts

    celery_progress(self, 1, "Queued — starting visual pipeline…", song_id=song_id)
    db = SessionLocal()
    try:
        song = db.scalar(
            select(SongProject)
            .where(SongProject.id == uuid.UUID(song_id))
            .options(
                selectinload(SongProject.shorts),
                selectinload(SongProject.lyrics_versions),
                selectinload(SongProject.music_generations),
            )
        )
        if not song:
            raise ValueError(f"Song not found: {song_id}")

        def on_progress(percent: int, message: str) -> None:
            celery_progress(self, percent, message, song_id=song_id)

        try:
            result = generate_visual_and_shorts(db, song, on_progress=on_progress)
        except (KlingVideoError, GeminiVideoError):
            raise
        db.commit()
        celery_progress(self, 100, "Visual + Shorts ready", song_id=song_id)
        return {
            **result,
            "song_id": song_id,
            "stage": song.stage,
            "video_url": f"/api/v1/songs/{song_id}/visuals/clip",
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(
    name="app.workers.tasks.song_prep_visual_mix",
    bind=True,
    soft_time_limit=1800,
    time_limit=2100,
)
def song_prep_visual_mix(self, song_id: str) -> dict[str, Any]:
    """Auto: Gemini→Kling visual (if needed) + final A/V mix + Shorts."""
    from app.db import SessionLocal
    from app.models import SongProject
    from app.services_final import FinalMixError
    from app.services_pipeline import run_prep_visual_mix
    from app.providers.gemini_video import GeminiVideoError
    from app.providers.kling_video import KlingVideoError

    celery_progress(self, 1, "Auto-prep queued…", song_id=song_id)
    db = SessionLocal()
    try:
        song = db.scalar(
            select(SongProject)
            .where(SongProject.id == uuid.UUID(song_id))
            .options(
                selectinload(SongProject.shorts),
                selectinload(SongProject.lyrics_versions),
                selectinload(SongProject.music_generations),
            )
        )
        if not song:
            raise ValueError(f"Song not found: {song_id}")
        if song.stage == "published" or song.youtube_video_id:
            return {"song_id": song_id, "skipped": True, "reason": "already_published"}
        if song.stage == "prep_running":
            return {"song_id": song_id, "skipped": True, "reason": "prep_already_running"}

        def on_progress(percent: int, message: str) -> None:
            celery_progress(self, percent, message, song_id=song_id)

        try:
            result = run_prep_visual_mix(db, song, on_progress=on_progress)
            db.commit()
            celery_progress(self, 100, "Auto-prep complete", song_id=song_id)
            return result
        except (KlingVideoError, GeminiVideoError, FinalMixError, Exception):
            db.commit()  # keep auto-prep error notes / stage rollback
            raise
    finally:
        db.close()


@celery_app.task(
    name="app.workers.tasks.song_auto_publish",
    bind=True,
    soft_time_limit=1800,
    time_limit=2100,
)
def song_auto_publish(self, song_id: str) -> dict[str, Any]:
    """Auto YouTube upload at publish_at (no-op if already published)."""
    from app.db import SessionLocal
    from app.models import SongProject
    from app.services_publish import PublishError, publish_song_to_youtube

    celery_progress(self, 1, "Auto-publish queued…", song_id=song_id)
    db = SessionLocal()
    try:
        song = db.scalar(
            select(SongProject)
            .where(SongProject.id == uuid.UUID(song_id))
            .options(
                selectinload(SongProject.shorts),
                selectinload(SongProject.lyrics_versions),
                selectinload(SongProject.music_generations),
            )
        )
        if not song:
            raise ValueError(f"Song not found: {song_id}")
        if song.stage == "published" or song.youtube_video_id:
            return {"song_id": song_id, "skipped": True, "reason": "already_published"}
        if song.stage == "publish_running":
            return {"song_id": song_id, "skipped": True, "reason": "publish_already_running"}

        prev = song.stage
        song.stage = "publish_running"
        db.flush()

        def on_progress(percent: int, message: str) -> None:
            celery_progress(self, percent, message, song_id=song_id)

        try:
            published = publish_song_to_youtube(
                db, song, publish_now=True, on_progress=on_progress
            )
            db.commit()
            celery_progress(self, 100, "Auto-publish complete", song_id=song_id)
            return published
        except PublishError as exc:
            song.stage = prev if prev != "publish_running" else "final_ready"
            stamp = time.strftime("%Y-%m-%d %H:%M")
            err = f"[auto-publish-error {stamp}] {exc}"
            notes = (song.notes or "").strip()
            song.notes = f"{notes}\n{err}".strip() if notes else err
            db.commit()
            raise
        except Exception:
            db.rollback()
            raise
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.pipeline_tick")
def pipeline_tick() -> dict[str, Any]:
    """Beat entry: enqueue due prep (−1h) and due auto-publish jobs."""
    from app.db import SessionLocal
    from app.services_pipeline import songs_due_for_prep, songs_due_for_publish

    db = SessionLocal()
    enqueued_prep: list[str] = []
    enqueued_pub: list[str] = []
    try:
        for song in songs_due_for_prep(db):
            sid = str(song.id)
            song_prep_visual_mix.delay(sid)
            enqueued_prep.append(sid)
        for song in songs_due_for_publish(db):
            sid = str(song.id)
            song_auto_publish.delay(sid)
            enqueued_pub.append(sid)
        return {
            "prep": enqueued_prep,
            "publish": enqueued_pub,
            "prep_count": len(enqueued_prep),
            "publish_count": len(enqueued_pub),
        }
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.music_generate_poll", bind=True)
def music_generate_poll(
    self,
    payload: dict[str, Any],
    *,
    poll_interval_sec: float = 5.0,
    max_wait_sec: float = 600.0,
) -> dict[str, Any]:
    """Submit Mureka generation and poll until succeeded / failure."""
    started = music_provider.generate(
        title=payload["title"],
        style=payload.get("style")
        or "Telugu devotional, light Carnatic, temple atmosphere",
        lyrics=payload["lyrics"],
        instrumental=bool(payload.get("instrumental", False)),
        vocal_gender=payload.get("vocal_gender"),
        duration=payload.get("duration"),
        model=payload.get("model"),
    )
    task_id = started["task_id"]
    deadline = time.monotonic() + max_wait_sec
    last: dict[str, Any] = {"task_id": task_id, "status": "PENDING"}

    while time.monotonic() < deadline:
        last = music_provider.get_record(task_id)
        self.update_state(
            state="PROGRESS",
            meta={
                "task_id": task_id,
                "status": last.get("status"),
                "tracks": len(last.get("tracks") or []),
            },
        )
        if last.get("done") or last.get("failed"):
            break
        time.sleep(poll_interval_sec)

    if last.get("failed"):
        raise MurekaError(
            last.get("error_message") or f"mureka failed with status {last.get('status')}",
            payload=last,
        )
    if not last.get("done"):
        raise MurekaError(f"mureka timed out waiting for task {task_id}", payload=last)

    return {
        "provider": "mureka",
        "task_id": task_id,
        "status": last.get("status"),
        "tracks": last.get("tracks") or [],
    }
