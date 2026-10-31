"""Mux Suno audio + Kling visual into a final YouTube preview (before publish)."""

from __future__ import annotations

import logging
import math
import tempfile
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.lyrics_sections import charanam_audio_window
from app.models import SongProject
from app.services_video import SHORT_MAX_SEC, _ffprobe_duration, _run_ffmpeg

logger = logging.getLogger(__name__)


class FinalMixError(RuntimeError):
    pass


def _latest_audio(song: SongProject) -> Path:
    music = song.music_generations[-1] if song.music_generations else None
    if not music or not music.file_path:
        raise FinalMixError("Upload song audio first")
    path = Path(music.file_path)
    if not path.exists():
        raise FinalMixError(f"Audio file missing: {path}")
    return path


def _latest_lyrics(song: SongProject) -> str | None:
    if not song.lyrics_versions:
        return None
    return song.lyrics_versions[-1].body


def _visual_clip(song: SongProject) -> Path:
    if not song.video_clip_path:
        raise FinalMixError("Generate the 16:9 visual clip first")
    path = Path(song.video_clip_path)
    if not path.exists():
        raise FinalMixError(f"Visual clip missing: {path}")
    return path


def _extract_audio_slice(
    *,
    audio: Path,
    start_sec: float,
    duration_sec: float,
    out_path: Path,
) -> Path:
    """Decode a precise audio slice to AAC — avoids multi-input -ss quirks."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    start = max(0.0, float(start_sec))
    dur = max(1.0, float(duration_sec))
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(audio),
        "-t",
        f"{dur:.3f}",
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out_path),
    ]
    _run_ffmpeg(cmd, timeout=180)
    if not out_path.exists() or out_path.stat().st_size < 500:
        raise FinalMixError(f"Audio slice failed at {start:.1f}s for {dur:.1f}s")
    return out_path


def mux_looped_av(
    *,
    video: Path,
    audio: Path,
    out_path: Path,
    max_duration: float | None = None,
    audio_start_sec: float = 0.0,
) -> tuple[Path, float]:
    """Loop silent video under an audio slice, mux AAC, H.264.

    For Shorts, audio is pre-cut at audio_start_sec so Charanam windows never
    accidentally share the song opening.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio_dur = _ffprobe_duration(audio)
    video_dur = _ffprobe_duration(video)
    start = max(0.0, float(audio_start_sec or 0.0))
    if start >= max(audio_dur - 0.5, 0.5):
        start = 0.0

    remaining = max(audio_dur - start, 0.5)
    target = remaining
    if max_duration is not None:
        target = min(target, max_duration)
    if target < 1:
        raise FinalMixError("Audio/video duration too short to mux")

    slice_path: Path | None = None
    audio_input = audio
    try:
        if start > 0.05 or (max_duration is not None and max_duration < audio_dur - 1):
            # Always pre-cut for Shorts (and any seek) so the mux cannot ignore -ss
            tmp = Path(tempfile.mkdtemp(prefix="ragam_audio_")) / "slice.m4a"
            slice_path = _extract_audio_slice(
                audio=audio,
                start_sec=start,
                duration_sec=target,
                out_path=tmp,
            )
            audio_input = slice_path
            start_for_mux = 0.0
            target = min(target, _ffprobe_duration(slice_path) or target)
        else:
            start_for_mux = 0.0

        loops = 0
        if video_dur > 0 and video_dur < target:
            loops = max(0, math.ceil(target / video_dur) - 1)

        cmd = ["ffmpeg", "-y"]
        if loops > 0:
            cmd += ["-stream_loop", str(loops)]
        cmd += [
            "-i",
            str(video),
            "-i",
            str(audio_input),
            "-t",
            f"{target:.2f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        # start_for_mux kept 0 after pre-cut; silence unused-var lint via assert
        assert start_for_mux == 0.0
        _run_ffmpeg(cmd, timeout=600)
        return out_path, _ffprobe_duration(out_path)
    finally:
        if slice_path is not None:
            try:
                slice_path.unlink(missing_ok=True)
                slice_path.parent.rmdir()
            except OSError:
                pass


def mix_final_preview(db: Session, song: SongProject) -> dict:
    """Long-form = full audio + 16:9. Shorts = mid-Charanam audio slices + 9:16."""
    settings = get_settings()
    audio = _latest_audio(song)
    visual = _visual_clip(song)
    lyrics = _latest_lyrics(song)
    audio_dur = _ffprobe_duration(audio)

    out_dir = Path(settings.media_root) / "finals" / str(song.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    main_out = out_dir / f"final_16x9_{uuid.uuid4().hex[:10]}.mp4"
    main_path, main_dur = mux_looped_av(video=visual, audio=audio, out_path=main_out)
    song.final_video_path = str(main_path)
    if song.stage in {"music_ready", "video_ready", "lyrics_draft", "awaiting_audio"}:
        song.stage = "final_ready"

    short_results: list[dict] = []
    for short in sorted(song.shorts or [], key=lambda s: s.slot_index):
        if not short.clip_path or not Path(short.clip_path).exists():
            continue
        a0, a1 = charanam_audio_window(
            lyrics,
            audio_dur,
            charanam_index=int(short.slot_index),
            clip_sec=SHORT_MAX_SEC,
        )
        slice_len = max(1.0, a1 - a0)
        short_out = out_dir / f"final_short_{short.slot_index}_{uuid.uuid4().hex[:8]}.mp4"
        path, dur = mux_looped_av(
            video=Path(short.clip_path),
            audio=audio,
            out_path=short_out,
            max_duration=min(SHORT_MAX_SEC, slice_len),
            audio_start_sec=a0,
        )
        short.final_clip_path = str(path)
        short.stage = "final_ready"
        short_results.append(
            {
                "slot_index": short.slot_index,
                "path": str(path),
                "duration_sec": dur,
                "audio_start_sec": a0,
                "audio_end_sec": round(a0 + dur, 2),
                "charanam": short.slot_index,
                "url": f"/api/v1/songs/{song.id}/shorts/{short.slot_index}/final",
            }
        )

    db.flush()
    windows_note = "; ".join(
        f"Short {r['slot_index']} ← Charanam {r['charanam']} "
        f"audio {r['audio_start_sec']:.0f}s–{r['audio_end_sec']:.0f}s"
        for r in short_results
    )
    return {
        "final_video_path": str(main_path),
        "final_video_url": f"/api/v1/songs/{song.id}/final",
        "duration_sec": main_dur,
        "aspect_ratio": "16:9",
        "shorts": short_results,
        "note": (
            "Final mix ready — long-form uses full Suno audio; "
            f"Shorts use mid-stanza cuts ({windows_note}). Preview before publish."
        ),
    }
