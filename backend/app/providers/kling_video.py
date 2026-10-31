"""Kling Video 4.0 — Flagship resource pack (4.0 / 4.0 Flash).

Default: POST /text-to-video/kling-4.0
With first frame: POST /image-to-video/kling-4.0
Native audio stays OFF — song MP3 is muxed later. Shorts are ffmpeg-cut from this clip.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.progress import ProgressFn, kling_poll_percent, report


class KlingVideoError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(get_settings().kling_api_key.strip())


def _base_url() -> str:
    return (get_settings().kling_base_url or "https://api-singapore.klingai.com").rstrip("/")


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().kling_api_key.strip()}",
        "Content-Type": "application/json",
    }


def _normalize_model(raw: str) -> str:
    m = (raw or "kling-4.0").strip().lower().replace("_", "-")
    if m in {"kling-4.0-flash", "kling-4-flash", "4.0-flash", "flash"}:
        return "kling-4.0-flash"
    if m in {"kling-4.0", "kling-4", "kling4", "4.0", "flagship"}:
        return "kling-4.0"
    if m in {
        "kling-v3-omni",
        "kling-3.0-omni",
        "kling-video-o1",
        "kling-omni",
        "omni",
    }:
        return "kling-3.0-omni"
    if "2.5" in m or "turbo" in m:
        return "kling-2.5-turbo"
    # Flagship Trial / Flagship packs only cover 4.0 family — default there
    return "kling-4.0"


def _create_url(model: str, *, image_to_video: bool) -> str:
    if model == "kling-3.0-omni":
        return f"{_base_url()}/omni-video/kling-3.0-omni"
    if model in {"kling-4.0", "kling-4.0-flash"}:
        kind = "image-to-video" if image_to_video else "text-to-video"
        return f"{_base_url()}/{kind}/{model}"
    aliases = {
        "kling-2.5-turbo": "/text-to-video/kling-2.5-turbo",
        "kling-v2-5-turbo": "/text-to-video/kling-2.5-turbo",
    }
    return f"{_base_url()}{aliases.get(model, f'/text-to-video/{model}')}"


def _image_as_data_url(path: Path) -> str:
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _poll_video_task(
    client: httpx.Client,
    task_id: str,
    *,
    timeout_sec: float,
    on_progress: ProgressFn | None = None,
) -> str:
    started = time.monotonic()
    deadline = started + timeout_sec
    last = ""
    while time.monotonic() < deadline:
        response = client.get(
            f"{_base_url()}/tasks",
            headers=_auth_headers(),
            params={"task_ids": task_id},
        )
        if response.status_code >= 400:
            raise KlingVideoError(
                f"Kling video poll HTTP {response.status_code}: {response.text[:400]}"
            )
        body = response.json()
        rows = body.get("data") if isinstance(body, dict) else None
        if not isinstance(rows, list) or not rows:
            time.sleep(3)
            continue
        row = rows[0] if isinstance(rows[0], dict) else {}
        status = str(row.get("status") or "").lower()
        last = status
        pct = kling_poll_percent(
            elapsed=time.monotonic() - started,
            timeout=timeout_sec,
            status=status,
        )
        report(on_progress, pct, f"Kling video: {status or 'waiting'}…")
        if status in {"succeeded", "succeed", "success", "completed"}:
            for out in row.get("outputs") or []:
                if isinstance(out, dict) and out.get("type") == "video" and out.get("url"):
                    return str(out["url"])
            raise KlingVideoError(f"Kling video succeeded but no url: {str(row)[:500]}")
        if status in {"failed", "fail", "error"}:
            raise KlingVideoError(f"Kling video failed: {row.get('message') or status}")
        time.sleep(4)
    raise KlingVideoError(f"Kling video timed out (last status={last or 'unknown'})")


def generate_clip(
    *,
    prompt: str,
    out_path: str | Path,
    resolution: str | None = None,
    aspect_ratio: str | None = None,
    duration_sec: int | None = None,
    first_frame_path: str | Path | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Generate ONE silent Kling 4.0 clip. Shorts cut later via ffmpeg."""
    settings = get_settings()
    if not settings.kling_api_key.strip():
        raise KlingVideoError("KLING_API_KEY missing")

    report(on_progress, 3, "Preparing Kling video request…")
    model = _normalize_model(settings.kling_video_model)
    res = (resolution or settings.kling_video_resolution or "720p").strip().lower()
    if res not in {"720p", "1080p", "4k"}:
        res = "720p"
    if model in {"kling-4.0", "kling-4.0-flash"} and res not in {"720p", "1080p"}:
        res = "1080p" if res == "4k" else "720p"
    if model == "kling-2.5-turbo" and res not in {"720p", "1080p"}:
        res = "720p"

    ar = (aspect_ratio or settings.kling_video_aspect_ratio or "16:9").strip()
    if ar not in {"16:9", "9:16", "1:1", "21:9"}:
        ar = "16:9"

    dur = int(duration_sec or settings.kling_video_duration or 10)
    if model in {"kling-4.0", "kling-4.0-flash"}:
        dur = max(3, min(30, dur))
    else:
        dur = max(3, min(15, dur))

    audio = (settings.kling_video_audio or "off").strip().lower()
    if audio not in {"off", "native", "original"}:
        audio = "off"

    timeout = float(settings.kling_video_timeout_sec or 900)
    text = (prompt or "").strip()[:2500]

    frame = Path(first_frame_path) if first_frame_path else None
    use_frame = bool(frame and frame.exists() and frame.stat().st_size < 30_000_000)

    # --- Kling 4.0 / 4.0 Flash (Flagship pack) ---
    if model in {"kling-4.0", "kling-4.0-flash"}:
        if use_frame:
            payload = {
                "contents": [
                    {
                        "type": "prompt",
                        "text": (
                            f"Animate @image_1 as a cinematic living temple scene. {text}"
                        )[:2500],
                    },
                    {
                        "type": "first_frame",
                        "url": _image_as_data_url(frame),  # type: ignore[arg-type]
                        "id": "image_1",
                    },
                ],
                "settings": {
                    "resolution": res,
                    "duration": dur,
                },
                "options": {"watermark_info": {"enabled": False}},
            }
        else:
            payload = {
                "prompt": text,
                "settings": {
                    "resolution": res,
                    "aspect_ratio": ar,
                    "duration": dur,
                },
                "options": {"watermark_info": {"enabled": False}},
            }
        create_url = _create_url(model, image_to_video=use_frame)

    # --- Omni 3.0 path (legacy / non-Flagship) ---
    elif model == "kling-3.0-omni":
        contents: list[dict] = [{"type": "prompt", "text": text}]
        if use_frame:
            contents.append(
                {
                    "type": "first_frame",
                    "url": _image_as_data_url(frame),  # type: ignore[arg-type]
                    "id": "image_1",
                }
            )
            contents[0]["text"] = (
                f"Animate @image_1 as a cinematic living temple scene. {text}"
            )[:2500]
        payload = {
            "contents": contents,
            "settings": {
                "resolution": res,
                "aspect_ratio": ar,
                "duration": dur,
                "audio": audio,
                "multi_shot": False,
            },
            "options": {"watermark_info": {"enabled": False}},
        }
        create_url = _create_url(model, image_to_video=False)

    else:
        # 2.5 Turbo — NOT covered by Flagship Trial (needs separate Video pack)
        payload = {
            "prompt": text,
            "settings": {
                "resolution": res if res in {"720p", "1080p"} else "720p",
                "aspect_ratio": ar if ar in {"16:9", "9:16", "1:1"} else "16:9",
                "duration": 10 if dur >= 8 else 5,
            },
            "options": {"watermark_info": {"enabled": False}},
        }
        create_url = _create_url(model, image_to_video=False)

    try:
        with httpx.Client(timeout=timeout) as client:
            create = client.post(
                create_url,
                headers=_auth_headers(),
                json=payload,
            )
            body: dict = {}
            try:
                body = create.json()
            except Exception:  # noqa: BLE001
                body = {}
            api_code = body.get("code")
            if create.status_code >= 400 or api_code not in (0, "0", None):
                msg = str(body.get("message") or create.text[:400])
                if api_code in (1101, 1102, "1101", "1102") or "balance" in msg.lower():
                    raise KlingVideoError(
                        f"Kling API has no usable credits for model `{model}` "
                        f"(code 1102). Flagship Trial only covers Kling 4.0 / "
                        f"4.0 Flash — set KLING_VIDEO_MODEL=kling-4.0. "
                        f"Other models need a separate Video pack: "
                        f"https://kling.ai/dev/pricing?scrollTo=video "
                        f"Detail: {msg}"
                    )
                raise KlingVideoError(
                    f"Kling video create HTTP {create.status_code} "
                    f"code={api_code}: {msg}"
                )
            data = body.get("data") or {}
            task_id = data.get("id") or data.get("task_id")
            if not task_id:
                raise KlingVideoError(f"Kling video missing task id: {str(body)[:400]}")

            report(on_progress, 10, f"Kling {model} rendering…")
            video_url = _poll_video_task(
                client, str(task_id), timeout_sec=timeout, on_progress=on_progress
            )
            report(on_progress, 92, "Downloading Kling video…")
            dl = client.get(video_url)
            if dl.status_code >= 400:
                raise KlingVideoError(f"Kling video download HTTP {dl.status_code}")
            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(dl.content)
            report(on_progress, 98, "Video clip saved…")
            return out
    except httpx.RequestError as exc:
        raise KlingVideoError(f"Kling video unreachable: {exc}") from exc
