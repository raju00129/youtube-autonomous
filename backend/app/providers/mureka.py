"""Official Mureka music API (platform.mureka.ai)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings

SUCCESS_STATUSES = frozenset({"succeeded", "success", "completed", "complete"})
FAILURE_STATUSES = frozenset({"failed", "error", "cancelled", "canceled", "timeout"})


class MurekaError(RuntimeError):
    def __init__(self, message: str, *, payload: Any = None):
        super().__init__(message)
        self.payload = payload


def _require_key() -> str:
    key = get_settings().mureka_api_key.strip()
    if not key:
        raise MurekaError(
            "MUREKA_API_KEY is empty. Create a key at https://platform.mureka.ai/ then restart."
        )
    return key


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=settings.mureka_base_url.rstrip("/"),
        headers={
            "Authorization": f"Bearer {_require_key()}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    )


def is_configured() -> bool:
    return bool(get_settings().mureka_api_key.strip())


def generate(
    *,
    title: str,
    style: str,
    lyrics: str,
    instrumental: bool = False,
    vocal_gender: str | None = None,
    duration: int | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Submit lyrics-to-song. Returns {task_id, raw}."""
    settings = get_settings()
    # Prefer desc (comma style tags). Include Telugu hint in style for our use case.
    style_bits = [style.strip()]
    if vocal_gender == "f":
        style_bits.append("female vocal")
    elif vocal_gender == "m":
        style_bits.append("male vocal")
    if "telugu" not in style.lower():
        style_bits.append("Telugu language vocals")

    payload: dict[str, Any] = {
        "lyrics": "[Instrumental]" if instrumental else lyrics[:5000],
        "model": model or settings.mureka_model,
        "title": title[:50],
        "desc": ", ".join(p for p in style_bits if p)[:1000],
    }
    # Mureka lyrics-to-song requires duration in [120, 300] when provided
    if duration is not None:
        payload["duration"] = max(120, min(300, int(duration)))
    else:
        payload["duration"] = 120
    if vocal_gender in {"m", "f", "male", "female"}:
        # API accepts gender on newer models (changelog 2026.6.25)
        payload["gender"] = "female" if vocal_gender in {"f", "female"} else "male"

    with _client() as client:
        response = client.post("/v1/song/generate", json=payload)
        if response.status_code >= 400:
            raise MurekaError(
                f"mureka generate HTTP {response.status_code}: {response.text[:500]}",
                payload=response.text,
            )
        body = response.json()

    if isinstance(body, dict) and body.get("error"):
        err = body["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise MurekaError(f"mureka generate: {msg}", payload=body)

    task_id = body.get("id") or body.get("task_id")
    if not task_id:
        raise MurekaError("mureka generate returned no task id", payload=body)
    return {"task_id": str(task_id), "raw": body}


def get_record(task_id: str) -> dict[str, Any]:
    """Poll GET /v1/song/query/{task_id}."""
    with _client() as client:
        response = client.get(f"/v1/song/query/{task_id}")
        if response.status_code >= 400:
            raise MurekaError(
                f"mureka query HTTP {response.status_code}: {response.text[:500]}",
                payload=response.text,
            )
        body = response.json()

    if isinstance(body, dict) and body.get("error"):
        err = body["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise MurekaError(f"mureka query: {msg}", payload=body)

    status = str(body.get("status") or "preparing").lower()
    # Choices / songs array shapes vary by model version
    choices = body.get("choices") or body.get("songs") or body.get("data") or []
    if isinstance(choices, dict):
        choices = [choices]
    if not isinstance(choices, list):
        choices = []

    tracks: list[dict[str, Any]] = []
    for idx, item in enumerate(choices):
        if not isinstance(item, dict):
            continue
        url = (
            item.get("url")
            or item.get("audio_url")
            or item.get("mp3_url")
            or item.get("wav_url")
        )
        tracks.append(
            {
                "id": str(item.get("id") or f"{task_id}-{idx}"),
                "title": item.get("title") or body.get("title"),
                "audio_url": url,
                "wav_url": item.get("wav_url"),
                "duration": item.get("duration"),
                "lyrics": item.get("lyrics"),
            }
        )

    # Some responses put urls at top level once finished
    if not tracks:
        top_url = body.get("url") or body.get("audio_url") or body.get("mp3_url") or body.get("wav_url")
        if top_url:
            tracks.append({"id": task_id, "audio_url": top_url, "title": body.get("title")})

    return {
        "task_id": str(body.get("id") or task_id),
        "status": status.upper(),
        "done": status in SUCCESS_STATUSES,
        "failed": status in FAILURE_STATUSES,
        "error_message": body.get("failed_reason") or body.get("message"),
        "tracks": tracks,
        "raw": body,
    }
