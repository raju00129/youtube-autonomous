"""Standalone video audio noise remover — not linked to song pipeline."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.services_denoise import (
    cleaned_path,
    denoise_job_dir,
    read_meta,
    write_meta,
)
from app.workers.tasks import denoise_video

router = APIRouter(prefix="/denoise", tags=["denoise"])

ALLOWED_VIDEO = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "video/x-m4v",
    "application/octet-stream",
}
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}


@router.post("")
async def upload_and_denoise(file: UploadFile = File(...)) -> dict:
    name = file.filename or "upload.mp4"
    suffix = Path(name).suffix.lower() or ".mp4"
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in ALLOWED_VIDEO and suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video type: {content_type} ({suffix}). Use mp4, mov, mkv, or webm.",
        )

    settings = get_settings()
    job_id = str(uuid.uuid4())
    job_dir = denoise_job_dir(settings.media_root, job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(name).stem)[:80] or "video"
    input_name = f"input_{safe}{suffix}"
    input_path = job_dir / input_name

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    if len(data) < 1000:
        raise HTTPException(status_code=400, detail="File looks empty")
    input_path.write_bytes(data)
    write_meta(job_dir, original_filename=name, input_name=input_name)

    denoise_video.apply_async(args=[job_id], task_id=job_id)
    return {
        "data": {
            "job_id": job_id,
            "status": "queued",
            "original_filename": name,
            "download_path": f"/api/v1/denoise/{job_id}/download",
        }
    }


@router.get("/{job_id}/download")
def download_cleaned(job_id: str) -> FileResponse:
    try:
        uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job id") from exc

    settings = get_settings()
    job_dir = denoise_job_dir(settings.media_root, job_id)
    out = cleaned_path(job_dir)
    if not out.exists():
        if not job_dir.exists():
            raise HTTPException(status_code=404, detail="Denoise job not found")
        raise HTTPException(
            status_code=409,
            detail="Cleaned video not ready yet — wait for the job to finish",
        )

    meta = read_meta(job_dir)
    original = str(meta.get("original_filename") or "video.mp4")
    stem = Path(original).stem or "video"
    download_name = f"{stem}_denoised.mp4"
    return FileResponse(out, media_type="video/mp4", filename=download_name)
