"""Third-party Suno music API via sunoapi.org (not AIMLAPI, not platform.suno.com)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings

SUCCESS_STATUSES = frozenset({"SUCCESS", "FIRST_SUCCESS"})
FAILURE_STATUSES = frozenset(
    {
        "CREATE_TASK_FAILED",
        "GENERATE_AUDIO_FAILED",
        "CALLBACK_EXCEPTION",
        "SENSITIVE_WORD_ERROR",
    }
)


class SunoApiError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.code = code
        self.payload = payload


def _require_key() -> str:
    key = get_settings().sunoapi_api_key.strip()
    if not key:
        raise SunoApiError(
            "SUNOAPI_API_KEY is empty. Add your key from https://sunoapi.org/ then restart."
        )
    return key


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=settings.sunoapi_base_url.rstrip("/"),
        headers={
            "Authorization": f"Bearer {_require_key()}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    )


def _raise_for_api(body: dict[str, Any], *, context: str) -> None:
    code = body.get("code")
    if code == 200:
        return
    msg = body.get("msg") or body.get("message") or context
    raise SunoApiError(f"{context}: {msg}", code=code if isinstance(code, int) else None, payload=body)


def is_configured() -> bool:
    return bool(get_settings().sunoapi_api_key.strip())


def generate(
    *,
    title: str,
    style: str,
    lyrics: str,
    instrumental: bool = False,
    vocal_gender: str | None = None,
    duration: int | None = None,
    model: str | None = None,
    negative_tags: str | None = None,
) -> dict[str, Any]:
    """Submit custom-mode music generation. Returns {task_id, raw}."""
    settings = get_settings()
    payload: dict[str, Any] = {
        "customMode": True,
        "instrumental": instrumental,
        "model": model or settings.sunoapi_model,
        "title": title[:80],
        "style": style[:1000],
        "lyrics": lyrics[:5000],
        "callBackUrl": settings.sunoapi_callback_url,
    }
    if vocal_gender in {"m", "f"}:
        payload["vocalGender"] = vocal_gender
    if duration is not None:
        payload["duration"] = max(10, min(360, int(duration)))
    if negative_tags:
        payload["negativeTags"] = negative_tags[:1000]

    with _client() as client:
        response = client.post("/api/v1/generate", json=payload)
        response.raise_for_status()
        body = response.json()

    _raise_for_api(body, context="sunoapi generate")
    data = body.get("data") or {}
    task_id = data.get("taskId") or data.get("task_id")
    if not task_id:
        raise SunoApiError("sunoapi generate returned no taskId", payload=body)
    return {"task_id": task_id, "raw": body}


def get_record(task_id: str) -> dict[str, Any]:
    """Poll generation status. Returns normalized status + tracks."""
    with _client() as client:
        response = client.get("/api/v1/generate/record-info", params={"taskId": task_id})
        response.raise_for_status()
        body = response.json()

    _raise_for_api(body, context="sunoapi record-info")
    data = body.get("data") or {}
    status = (data.get("status") or "PENDING").upper()
    response_block = data.get("response") or {}
    suno_data = response_block.get("sunoData") or response_block.get("suno_data") or []

    tracks: list[dict[str, Any]] = []
    for item in suno_data:
        if not isinstance(item, dict):
            continue
        tracks.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "audio_url": item.get("audio_url") or item.get("source_audio_url"),
                "stream_audio_url": item.get("stream_audio_url"),
                "image_url": item.get("image_url"),
                "duration": item.get("duration"),
                "tags": item.get("tags"),
                "model_name": item.get("model_name"),
                "prompt": item.get("prompt"),
            }
        )

    return {
        "task_id": data.get("taskId") or task_id,
        "status": status,
        "done": status in SUCCESS_STATUSES,
        "failed": status in FAILURE_STATUSES,
        "error_code": data.get("errorCode"),
        "error_message": data.get("errorMessage"),
        "tracks": tracks,
        "raw": body,
    }


def download_track(audio_url: str, dest: Path) -> Path:
    """Download a finished track URL into media storage."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.get(audio_url)
        response.raise_for_status()
        dest.write_bytes(response.content)
    return dest


def default_download_path(task_id: str, track_id: str | None, audio_url: str) -> Path:
    settings = get_settings()
    suffix = Path(urlparse(audio_url).path).suffix or ".mp3"
    name = f"{track_id or 'track'}{suffix}"
    return Path(settings.media_root) / "music" / task_id / name
