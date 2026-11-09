"""Standalone audio noise removal — video bitstream unchanged."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class DenoiseError(RuntimeError):
    pass


def denoise_job_dir(media_root: str | Path, job_id: str) -> Path:
    return Path(media_root) / "denoise" / job_id


def cleaned_path(job_dir: Path) -> Path:
    return job_dir / "cleaned.mp4"


def meta_path(job_dir: Path) -> Path:
    return job_dir / "meta.json"


def write_meta(job_dir: Path, *, original_filename: str, input_name: str) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    meta_path(job_dir).write_text(
        json.dumps(
            {
                "original_filename": original_filename,
                "input_name": input_name,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def read_meta(job_dir: Path) -> dict:
    path = meta_path(job_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _has_audio_stream(source: Path) -> bool:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(source),
            ],
            stderr=subprocess.STDOUT,
            timeout=60,
        )
        return bool(out.decode("utf-8", errors="replace").strip())
    except Exception as exc:  # noqa: BLE001
        raise DenoiseError(f"Could not inspect audio streams: {exc}") from exc


def denoise_video_file(
    source: Path,
    out_path: Path,
    *,
    timeout: int = 3600,
) -> Path:
    """Remove audio noise; stream-copy video so picture/timing stay identical."""
    if not source.exists():
        raise DenoiseError(f"Input missing: {source}")
    if not _has_audio_stream(source):
        raise DenoiseError("This video has no audio track to denoise")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        "copy",
        "-af",
        "afftdn=nf=-25",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DenoiseError("Denoise timed out — try a shorter clip") from exc
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode("utf-8", errors="replace")[:600]
        raise DenoiseError(f"ffmpeg denoise failed: {err}") from exc

    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise DenoiseError("Denoise produced an empty output")
    return out_path
