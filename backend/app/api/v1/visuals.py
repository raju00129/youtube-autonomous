"""Kling visual + final A/V mix (preview before publish)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from app.core.config import get_settings
from app.db import get_db
from app.models import SongProject
from app.providers.kling_video import KlingVideoError, is_configured as kling_configured
from app.services_final import FinalMixError, mix_final_preview
from app.services_video import apply_manual_visual_upload, generate_visual_and_shorts
from app.workers.tasks import visuals_generate

router = APIRouter(tags=["visuals"])

ALLOWED_VIDEO = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-m4v",
    "application/octet-stream",
}
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}


def _load_song(db: Session, song_id: uuid.UUID) -> SongProject:
    song = db.scalar(
        select(SongProject)
        .where(SongProject.id == song_id)
        .options(
            selectinload(SongProject.shorts),
            selectinload(SongProject.lyrics_versions),
            selectinload(SongProject.music_generations),
        )
    )
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


@router.post("/songs/{song_id}/visuals/generate")
def generate_visuals(song_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Enqueue Kling 16:9 + Shorts cut. Poll GET /api/v1/jobs/{job_id} for progress."""
    song = _load_song(db, song_id)
    if not kling_configured():
        raise HTTPException(status_code=503, detail="KLING_API_KEY missing")
    async_result = visuals_generate.delay(str(song.id))
    return {
        "data": {
            "job_id": async_result.id,
            "status": "queued",
            "song_id": str(song.id),
            "note": (
                "Visual generation started. Poll /api/v1/jobs/{job_id} for percent + message; "
                "Kling 4.0 then ffmpeg Shorts (no restart needed)."
            ),
        }
    }


@router.post("/songs/{song_id}/visuals/generate/sync")
def generate_visuals_sync(song_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Blocking generate (debug). Prefer async /visuals/generate + job poll in the UI."""
    song = _load_song(db, song_id)
    try:
        result = generate_visual_and_shorts(db, song)
    except KlingVideoError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Visual pipeline failed: {exc}") from exc
    db.commit()
    song = _load_song(db, song_id)
    return {
        "data": {
            **result,
            "song_id": str(song.id),
            "stage": song.stage,
            "video_url": f"/api/v1/songs/{song.id}/visuals/clip",
            "shorts": [
                {
                    "slot_index": s.slot_index,
                    "stage": s.stage,
                    "clip_path": s.clip_path,
                    "clip_url": f"/api/v1/songs/{song.id}/shorts/{s.slot_index}/clip"
                    if s.clip_path
                    else None,
                }
                for s in (song.shorts or [])
            ],
        }
    }


@router.post("/songs/{song_id}/visuals/upload")
async def upload_visual(
    song_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Upload a finished 16:9 (or any) video — skips AI generation; cuts Shorts via ffmpeg."""
    song = _load_song(db, song_id)
    name = file.filename or "upload.mp4"
    suffix = Path(name).suffix.lower() or ".mp4"
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in ALLOWED_VIDEO and suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video type: {content_type} ({suffix}). Use mp4, mov, or webm.",
        )

    settings = get_settings()
    dest_dir = Path(settings.media_root) / "visuals" / str(song.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(name).stem)[:80] or "visual"
    raw_path = dest_dir / f"manual_{uuid.uuid4().hex[:10]}_{safe}{suffix}"

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    if len(data) < 1000:
        raise HTTPException(status_code=400, detail="File looks empty")
    raw_path.write_bytes(data)

    try:
        result = apply_manual_visual_upload(
            db, song, source_path=raw_path, original_filename=name
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"Could not process uploaded video: {exc}"
        ) from exc

    db.commit()
    song = _load_song(db, song_id)
    return {
        "data": {
            **result,
            "song_id": str(song.id),
            "stage": song.stage,
            "video_url": f"/api/v1/songs/{song.id}/visuals/clip",
            "shorts": [
                {
                    "slot_index": s.slot_index,
                    "stage": s.stage,
                    "clip_path": s.clip_path,
                    "clip_url": f"/api/v1/songs/{song.id}/shorts/{s.slot_index}/clip"
                    if s.clip_path
                    else None,
                }
                for s in (song.shorts or [])
            ],
        }
    }


@router.get("/songs/{song_id}/visuals/clip")
def get_main_clip(song_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    song = _load_song(db, song_id)
    if not song.video_clip_path:
        raise HTTPException(status_code=404, detail="No visual clip yet — generate or upload first")
    path = Path(song.video_clip_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Visual clip file missing on disk")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/songs/{song_id}/shorts/{slot_index}/clip")
def get_short_clip(
    song_id: uuid.UUID, slot_index: int, db: Session = Depends(get_db)
) -> FileResponse:
    song = _load_song(db, song_id)
    short = next((s for s in (song.shorts or []) if s.slot_index == slot_index), None)
    if not short or not short.clip_path:
        raise HTTPException(status_code=404, detail="Short clip not ready")
    path = Path(short.clip_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Short clip file missing on disk")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.post("/songs/{song_id}/final/mix")
def mix_final(song_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Mux Suno audio + Kling visuals into final long-form + Shorts (preview before publish)."""
    song = _load_song(db, song_id)
    try:
        result = mix_final_preview(db, song)
    except FinalMixError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Final mix failed: {exc}") from exc
    db.commit()
    song = _load_song(db, song_id)
    return {
        "data": {
            **result,
            "song_id": str(song.id),
            "stage": song.stage,
        }
    }


@router.get("/songs/{song_id}/final")
def get_final_main(song_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    song = _load_song(db, song_id)
    if not getattr(song, "final_video_path", None):
        raise HTTPException(status_code=404, detail="No final mix yet — run Mix audio + video first")
    path = Path(song.final_video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Final video file missing on disk")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/songs/{song_id}/shorts/{slot_index}/final")
def get_final_short(
    song_id: uuid.UUID, slot_index: int, db: Session = Depends(get_db)
) -> FileResponse:
    song = _load_song(db, song_id)
    short = next((s for s in (song.shorts or []) if s.slot_index == slot_index), None)
    if not short or not getattr(short, "final_clip_path", None):
        raise HTTPException(status_code=404, detail="Short final mix not ready")
    path = Path(short.final_clip_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Short final file missing on disk")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
