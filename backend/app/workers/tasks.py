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
    name="app.workers.tasks.denoise_video",
    bind=True,
    soft_time_limit=3600,
    time_limit=3900,
)
def denoise_video(self, job_id: str) -> dict[str, Any]:
    """Strip audio noise from a standalone upload; video stream copied as-is."""
    from app.core.config import get_settings
    from app.services_denoise import (
        DenoiseError,
        cleaned_path,
        denoise_job_dir,
        denoise_video_file,
        read_meta,
    )

    celery_progress(self, 5, "Starting audio noise removal…", job_id=job_id)
    settings = get_settings()
    job_dir = denoise_job_dir(settings.media_root, job_id)
    meta = read_meta(job_dir)
    input_name = str(meta.get("input_name") or "")
    source = job_dir / input_name if input_name else None
    if not source or not source.exists():
        # Fallback: first input_* file in the job dir
        candidates = sorted(job_dir.glob("input_*")) if job_dir.exists() else []
        if not candidates:
            raise ValueError(f"Denoise input missing for job {job_id}")
        source = candidates[0]

    out = cleaned_path(job_dir)
    celery_progress(self, 20, "Denoising audio (picture unchanged)…", job_id=job_id)
    try:
        denoise_video_file(source, out, timeout=3500)
    except DenoiseError:
        raise
    celery_progress(self, 100, "Noise removed — ready to download", job_id=job_id)
    return {
        "job_id": job_id,
        "download_path": f"/api/v1/denoise/{job_id}/download",
        "original_filename": meta.get("original_filename"),
    }


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
    from app.services_pipeline import claim_song_stage, run_prep_visual_mix
    from app.providers.gemini_video import GeminiVideoError
    from app.providers.kling_video import KlingVideoError

    celery_progress(self, 1, "Auto-prep queued…", song_id=song_id)
    db = SessionLocal()
    try:
        prev = claim_song_stage(
            db,
            uuid.UUID(song_id),
            lock_stage="prep_running",
            blocked={"published", "publish_running"},
        )
        if prev is None:
            return {"song_id": song_id, "skipped": True, "reason": "locked_or_published"}
        song = db.scalar(
            select(SongProject)
            .where(SongProject.id == uuid.UUID(song_id))
            .options(
                selectinload(SongProject.shorts),
                selectinload(SongProject.lyrics_versions),
                selectinload(SongProject.music_generations),
            )
        )
        if song.youtube_video_id:
            song.stage = prev
            db.commit()
            return {"song_id": song_id, "skipped": True, "reason": "already_published"}

        def on_progress(percent: int, message: str) -> None:
            celery_progress(self, percent, message, song_id=song_id)

        try:
            result = run_prep_visual_mix(
                db, song, on_progress=on_progress, prev_stage=prev
            )
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
    from app.services_pipeline import claim_song_stage
    from app.services_publish import publish_song_to_youtube

    celery_progress(self, 1, "Auto-publish queued…", song_id=song_id)
    db = SessionLocal()
    try:
        # Atomic claim: two queued publish tasks can no longer both upload.
        prev = claim_song_stage(
            db,
            uuid.UUID(song_id),
            lock_stage="publish_running",
            blocked={"published", "prep_running"},
        )
        if prev is None:
            return {"song_id": song_id, "skipped": True, "reason": "locked_or_published"}
        song = db.scalar(
            select(SongProject)
            .where(SongProject.id == uuid.UUID(song_id))
            .options(
                selectinload(SongProject.shorts),
                selectinload(SongProject.lyrics_versions),
                selectinload(SongProject.music_generations),
            )
        )

        def on_progress(percent: int, message: str) -> None:
            celery_progress(self, percent, message, song_id=song_id)

        try:
            published = publish_song_to_youtube(
                db, song, publish_now=True, on_progress=on_progress
            )
            db.commit()
            celery_progress(self, 100, "Auto-publish complete", song_id=song_id)
            return published
        except Exception as exc:
            # Uploaded ids are already committed by the publish service, so a
            # retry reuses them instead of uploading a duplicate.
            db.rollback()
            song = db.get(SongProject, uuid.UUID(song_id))
            if song is not None and song.stage == "publish_running":
                song.stage = prev
                stamp = time.strftime("%Y-%m-%d %H:%M")
                err = f"[auto-publish-error {stamp}] {exc}"
                notes = (song.notes or "").strip()
                song.notes = f"{notes}\n{err}".strip() if notes else err
                db.commit()
            raise
    finally:
        db.close()


@celery_app.task(
    name="app.workers.tasks.song_fill_lyrics",
    bind=True,
    soft_time_limit=300,
    time_limit=360,
)
def song_fill_lyrics(
    self,
    song_id: str,
    *,
    title_hint: str,
    deity: str | None = None,
    topic: str | None = None,
    vocal: str | None = "m",
    music_genre: str | None = None,
    energy_hint: str | None = None,
    approve: bool = False,
    daypart: str | None = "morning",
) -> dict[str, Any]:
    """Background Gemini lyrics after a fast song create (allows parallel creates)."""
    from app.content_templates import fill_shorts_pair, fill_youtube_longform, sync_song_publish_copy
    from app.db import SessionLocal
    from app.models import LyricsVersion, SongProject
    from app.providers import llm
    from app.providers.cursor_llm import CursorLlmError
    from app.providers.gemini_llm import GeminiLlmError
    from app.providers.openai_llm import OpenAILlmError
    from app.style_prompt import enrich_style_prompt

    celery_progress(self, 5, "Writing Telugu lyrics with Gemini…", song_id=song_id)
    db = SessionLocal()
    try:
        song = db.scalar(
            select(SongProject)
            .where(SongProject.id == uuid.UUID(song_id))
            .options(
                selectinload(SongProject.shorts),
                selectinload(SongProject.lyrics_versions),
            )
        )
        if not song:
            raise ValueError(f"Song not found: {song_id}")
        if song.lyrics_versions:
            return {"song_id": song_id, "skipped": True, "reason": "already_has_lyrics"}

        try:
            from app.lyrics_uniqueness import recent_lyrics_echo
            import time as _time

            avoid = recent_lyrics_echo(
                db,
                deity=deity or song.deity,
                exclude_song_id=song.id,
                limit=4,
            )
            generated = llm.generate_lyrics(
                title=title_hint,
                deity=deity or song.deity,
                topic=topic or song.notes,
                vocal=vocal or song.vocal_preference or "m",
                music_genre=music_genre or song.music_genre,
                energy_hint=energy_hint,
                avoid_echo=avoid or None,
                variation_seed=f"{song.id}-{int(_time.time())}",
            )
        except (GeminiLlmError, OpenAILlmError, CursorLlmError):
            song.stage = "scheduled"
            song.notes = (song.notes or "") + "\n[lyrics_error] Gemini failed — regenerate from song page."
            db.commit()
            raise

        celery_progress(self, 70, "Saving lyrics + YouTube package…", song_id=song_id)
        lyrics_body = str(generated["lyrics"]).strip()
        style = enrich_style_prompt(
            (generated.get("style_prompt") or "").strip()
            or (song.style_prompt or ""),
            vocal=vocal or song.vocal_preference,
        )
        gemini_title = str(generated.get("title") or title_hint)[:200]
        song.title = gemini_title
        song.style_prompt = style or song.style_prompt
        db.add(
            LyricsVersion(
                song_id=song.id,
                version=1,
                body=lyrics_body,
                approved=approve,
            )
        )
        song.stage = "awaiting_audio" if approve else "lyrics_draft"
        db.flush()
        sync_song_publish_copy(
            song,
            lyrics=lyrics_body,
            gemini_title=gemini_title,
            topic=topic or song.notes,
            refresh_shorts=False,
        )
        # Refresh Shorts copy from Pallavi hook
        from app.lyrics_sections import extract_sections

        pallavi = (extract_sections(lyrics_body).get("pallavi") or song.title or "").strip()
        short_defs = {
            d["slot_index"]: d
            for d in fill_shorts_pair(
                title=song.title,
                deity=song.deity,
                daypart=daypart or "morning",
                youtube_title=song.youtube_title,
                youtube_description=song.youtube_description,
                charanams=[pallavi] if pallavi else None,
            )
        }
        for short in song.shorts:
            d = short_defs.get(int(short.slot_index))
            if not d:
                continue
            short.title = d["title"]
            short.hook = d["hook"]
            short.description = d["description"]
        db.commit()
        celery_progress(self, 100, "Lyrics ready", song_id=song_id)
        return {"song_id": song_id, "title": song.title, "stage": song.stage}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.cleanup_published_media")
def cleanup_published_media() -> dict[str, Any]:
    """Daily: delete audio/video/thumbs for songs published before today (IST)."""
    from app.db import SessionLocal
    from app.services_cleanup import cleanup_published_media as run_cleanup

    db = SessionLocal()
    try:
        return run_cleanup(db)
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
