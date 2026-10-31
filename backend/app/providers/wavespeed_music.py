"""Music via WaveSpeedAI ACE-Step 1.5 (multilingual lyrics, incl. Telugu-friendly)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings

SUCCESS_STATUSES = frozenset({"completed", "succeeded", "success"})
FAILURE_STATUSES = frozenset({"failed", "cancelled", "canceled", "timeout", "deleted", "error"})


class WaveSpeedMusicError(RuntimeError):
    def __init__(self, message: str, *, payload: Any = None):
        super().__init__(message)
        self.payload = payload


def _require_key() -> str:
    key = get_settings().wavespeed_api_key.strip()
    if not key:
        raise WaveSpeedMusicError(
            "WAVESPEED_API_KEY is empty. Create a key at https://wavespeed.ai/ then restart."
        )
    return key


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=settings.wavespeed_base_url.rstrip("/"),
        headers={
            "Authorization": f"Bearer {_require_key()}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    )


def is_configured() -> bool:
    return bool(get_settings().wavespeed_api_key.strip())


def generate(
    *,
    title: str,
    style: str,
    lyrics: str,
    duration: int | None = None,
    instrumental: bool = False,
    seed: int | None = None,
) -> dict[str, Any]:
    """Submit ACE-Step generation. Returns {task_id, raw}."""
    settings = get_settings()
    # Embed title into tags for player metadata; ACE-Step primary controls are tags + lyrics.
    tags = ", ".join(
        part
        for part in [
            style.strip(),
            "Telugu vocals" if not instrumental else "instrumental",
            f"title:{title[:60]}" if title else "",
        ]
        if part
    )
    payload: dict[str, Any] = {
        "tags": tags[:2000],
        "duration": max(10, min(240, int(duration or settings.wavespeed_music_duration))),
    }
    if not instrumental and lyrics.strip():
        payload["lyrics"] = lyrics[:5000]
    if seed is not None and seed >= 0:
        payload["seed"] = seed

    model_path = settings.wavespeed_music_model.lstrip("/")
    with _client() as client:
        response = client.post(f"/api/v3/{model_path}", json=payload)
        if response.status_code >= 400:
            raise WaveSpeedMusicError(
                f"wavespeed generate HTTP {response.status_code}: {response.text[:500]}",
                payload=response.text,
            )
        body = response.json()

    data = body.get("data", body) if isinstance(body, dict) else {}
    task_id = data.get("id") or body.get("id")
    if not task_id:
        raise WaveSpeedMusicError("wavespeed generate returned no prediction id", payload=body)
    return {"task_id": str(task_id), "raw": body}


def get_record(task_id: str) -> dict[str, Any]:
    """Poll WaveSpeed prediction result."""
    with _client() as client:
        response = client.get(f"/api/v3/predictions/{task_id}/result")
        if response.status_code >= 400:
            raise WaveSpeedMusicError(
                f"wavespeed poll HTTP {response.status_code}: {response.text[:500]}",
                payload=response.text,
            )
        body = response.json()

    data = body.get("data", body) if isinstance(body, dict) else {}
    status = str(data.get("status") or "pending").lower()
    outputs = data.get("outputs") or data.get("output") or []
    if isinstance(outputs, str):
        outputs = [outputs]
    if not isinstance(outputs, list):
        outputs = []

    tracks: list[dict[str, Any]] = []
    for idx, item in enumerate(outputs):
        if isinstance(item, str):
            tracks.append({"id": f"{task_id}-{idx}", "audio_url": item, "title": None})
        elif isinstance(item, dict):
            url = item.get("url") or item.get("audio_url") or item.get("output")
            if url:
                tracks.append(
                    {
                        "id": str(item.get("id") or f"{task_id}-{idx}"),
                        "audio_url": url,
                        "title": item.get("title"),
                        "duration": item.get("duration"),
                    }
                )

    return {
        "task_id": task_id,
        "status": status.upper(),
        "done": status in SUCCESS_STATUSES,
        "failed": status in FAILURE_STATUSES,
        "error_message": data.get("error") or data.get("message"),
        "tracks": tracks,
        "raw": body,
    }
