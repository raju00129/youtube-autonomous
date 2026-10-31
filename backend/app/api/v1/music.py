"""Music generation via official Mureka API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.providers import mureka as music_provider
from app.providers.mureka import MurekaError
from app.workers.tasks import music_generate_poll

router = APIRouter(prefix="/music", tags=["music"])


class MusicGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=50)
    style: str = Field(
        default="Telugu devotional, light Carnatic, temple atmosphere, serene male vocals",
        max_length=1000,
    )
    lyrics: str = Field(..., min_length=1, max_length=5000)
    instrumental: bool = False
    vocal_gender: Literal["m", "f"] | None = "m"
    duration: int | None = Field(default=120, ge=120, le=300)
    model: str | None = Field(default=None, max_length=32)
    wait: bool = Field(
        default=False,
        description="If true, enqueue Celery job that polls until succeeded/failure",
    )


@router.get("/status")
def music_provider_status() -> dict:
    settings = get_settings()
    return {
        "data": {
            "provider": "mureka",
            "model": settings.mureka_model,
            "configured": music_provider.is_configured(),
            "base_url": settings.mureka_base_url,
            "notes": "Official Mureka API. Telugu not in FAQ language list — test vocals carefully.",
        }
    }


@router.post("/generate")
def generate_music(body: MusicGenerateRequest) -> dict:
    if not music_provider.is_configured():
        raise HTTPException(
            status_code=503,
            detail="MUREKA_API_KEY missing. Sign up at https://platform.mureka.ai/",
        )
    try:
        if body.wait:
            async_result = music_generate_poll.delay(body.model_dump(exclude={"wait"}))
            return {
                "data": {
                    "job_id": async_result.id,
                    "status": "queued",
                    "job_type": "music_generate_poll",
                    "provider": "mureka",
                    "model": body.model or get_settings().mureka_model,
                }
            }

        result = music_provider.generate(
            title=body.title,
            style=body.style,
            lyrics=body.lyrics,
            instrumental=body.instrumental,
            vocal_gender=body.vocal_gender,
            duration=body.duration,
            model=body.model,
        )
        return {
            "data": {
                "task_id": result["task_id"],
                "status": "PENDING",
                "provider": "mureka",
                "model": body.model or get_settings().mureka_model,
            }
        }
    except MurekaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"mureka error: {exc}") from exc


@router.get("/tasks/{task_id}")
def get_music_task(task_id: str) -> dict:
    if not music_provider.is_configured():
        raise HTTPException(status_code=503, detail="MUREKA_API_KEY missing")
    try:
        return {"data": music_provider.get_record(task_id)}
    except MurekaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"mureka error: {exc}") from exc
