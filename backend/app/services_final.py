"""Mux Suno audio + Kling visual into a final YouTube preview (before publish)."""

from __future__ import annotations

import json
import logging
import math
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.lyrics_sections import pallavi_audio_window
from app.models import SongProject
from app.services_video import (
    MAIN_MIN_SEC,
    SHORT_MAX_SEC,
    _ffprobe_duration,
    _run_ffmpeg,
    smooth_extend_main_visual,
)

logger = logging.getLogger(__name__)


class FinalMixError(RuntimeError):
    pass


def detect_leading_silence_sec(
    audio: Path,
    *,
    min_silence_sec: float = 0.5,
    scan_sec: float = 20.0,
) -> float:
    """Return seconds of *true empty* audio at the start.

    Only digital silence (RMS = -inf) is trimmed. Soft pads, quiet intros, or
    any measurable music/sound are kept — never crop into those.
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-ss",
        "0",
        "-t",
        f"{scan_sec:.2f}",
        "-i",
        str(audio),
        "-af",
        "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Leading silence detect failed: %s", exc)
        return 0.0

    log = proc.stderr or ""
    rows: list[tuple[float, float]] = []
    cur_t: float | None = None
    for line in log.splitlines():
        m_t = re.search(r"pts_time:([0-9.]+)", line)
        if m_t:
            cur_t = float(m_t.group(1))
        m_r = re.search(r"RMS_level=(-inf|-?[0-9.]+)", line)
        if m_r and cur_t is not None:
            raw = m_r.group(1)
            rms = float("-inf") if raw == "-inf" else float(raw)
            rows.append((cur_t, rms))

    if not rows:
        return 0.0

    # Stop at the first frame with ANY measurable signal (music/pad/noise).
    first_sound_t: float | None = None
    for t, rms in rows:
        if rms != float("-inf"):
            first_sound_t = t
            break
    if first_sound_t is None:
        return 0.0
    if first_sound_t < min_silence_sec:
        return 0.0

    # Leave a tiny head so we never bite the first sound.
    lead = max(0.0, first_sound_t - 0.05)
    audio_dur = max(1.0, _ffprobe_duration(audio))
    lead = min(lead, audio_dur * 0.25, max(0.0, audio_dur - 20.0))
    if lead < min_silence_sec:
        return 0.0
    return round(lead, 3)


def trim_leading_silence(
    audio: Path,
    out_path: Path,
    *,
    lead_sec: float | None = None,
) -> tuple[Path, float]:
    """Write audio with leading hush removed. Returns (path, seconds_trimmed)."""
    lead = detect_leading_silence_sec(audio) if lead_sec is None else max(0.0, float(lead_sec))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if lead < 0.4:
        if audio.resolve() != out_path.resolve():
            _run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(audio),
                    "-vn",
                    "-ar",
                    "48000",
                    "-c:a",
                    "pcm_s16le",
                    str(out_path),
                ],
                timeout=300,
            )
            return out_path, 0.0
        return audio, 0.0

    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{lead:.3f}",
            "-i",
            str(audio),
            "-vn",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ],
        timeout=300,
    )
    if not out_path.exists() or out_path.stat().st_size < 500:
        raise FinalMixError(f"Failed to trim leading silence ({lead:.1f}s)")
    return out_path, lead


def _loudness_pre_filters() -> str:
    """Rumble cut + gentle vocal-presence lift applied before loudnorm."""
    settings = get_settings()
    presence_db = float(getattr(settings, "audio_vocal_presence_db", 2.0) or 0.0)
    chain = ["highpass=f=35"]
    if presence_db > 0.05:
        chain.append(f"equalizer=f=3000:t=q:w=1.0:g={presence_db:.2f}")
    return ",".join(chain)


def _measure_loudnorm(
    audio: Path, *, pre: str, target_i: float, target_tp: float, target_lra: float
) -> dict | None:
    """Run loudnorm pass 1 and return its measured JSON stats."""
    af = (
        f"{pre},loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
        ":print_format=json"
    )
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio), "-vn", "-af", af, "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("loudnorm measure failed: %s", exc)
        return None
    log = proc.stderr or ""
    start = log.rfind("{")
    end = log.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        stats = json.loads(log[start : end + 1])
    except json.JSONDecodeError:
        return None
    needed = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if not all(k in stats for k in needed):
        return None
    try:
        if not math.isfinite(float(stats["input_i"])):
            return None
    except (TypeError, ValueError):
        return None
    return stats


def normalize_loudness(audio: Path, out_path: Path) -> tuple[Path, float]:
    """Two-pass EBU R128 loudness normalize to YouTube's ~-14 LUFS target.

    Lossless WAV output — the only lossy encode happens once at final mux.
    Returns (path, applied gain in dB).
    """
    settings = get_settings()
    target_i = float(getattr(settings, "audio_target_lufs", -14.0))
    target_tp = float(getattr(settings, "audio_true_peak_db", -1.5))
    target_lra = float(getattr(settings, "audio_target_lra", 11.0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pre = _loudness_pre_filters()

    stats = _measure_loudnorm(
        audio, pre=pre, target_i=target_i, target_tp=target_tp, target_lra=target_lra
    )
    if stats:
        measured_i = float(stats["input_i"])
        gain = target_i - measured_i
        # Static gain + peak limiter keeps the song's dynamics; loudnorm's
        # dynamic fallback (big boosts) flattens LRA and sounds squashed.
        limit = 10 ** (target_tp / 20.0)
        loudnorm = (
            f"volume={gain:.2f}dB,"
            f"alimiter=limit={limit:.4f}:attack=5:release=60:level=0"
        )
    else:
        loudnorm = f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
        measured_i = float("nan")
        gain = 0.0

    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio),
            "-vn",
            "-af",
            f"{pre},{loudnorm}",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ],
        timeout=600,
    )
    if not out_path.exists() or out_path.stat().st_size < 500:
        raise FinalMixError("Loudness normalize failed")
    logger.info(
        "Loudness normalized %.1f LUFS → %.1f LUFS (%+.1f dB)",
        measured_i,
        target_i,
        gain,
    )
    return out_path, round(gain, 2)


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
    """Decode a precise lossless audio slice — avoids multi-input -ss quirks."""
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
        "-ar",
        "48000",
        "-c:a",
        "pcm_s16le",
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

    For Shorts, audio is pre-cut at audio_start_sec so Pallavi windows never
    accidentally share the wrong stanza.
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
            tmp = Path(tempfile.mkdtemp(prefix="ragam_audio_")) / "slice.wav"
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

        # Copy video bitstream — visual was already encoded at 720p; re-encoding
        # here washed detail and made uploads look soft / low-res on YouTube.
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
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "320k",
            "-ar",
            "48000",
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
    """Long-form = full audio + 16:9. Shorts = Pallavi hook audio + 9:16."""
    settings = get_settings()
    raw_audio = _latest_audio(song)
    visual = _visual_clip(song)
    lyrics = _latest_lyrics(song)

    out_dir = Path(settings.media_root) / "finals" / str(song.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Manual uploads keep original length — mux loops under the song as needed.
    # AI/short clips still soft-loop to ~45s so the visual stage isn't tiny.
    prompt = (song.visual_prompt or "").strip().lower()
    is_manual_upload = prompt.startswith("[manual_upload]")
    main_target = float(getattr(settings, "video_main_min_sec", MAIN_MIN_SEC) or MAIN_MIN_SEC)
    vis_dur = _ffprobe_duration(visual)
    if not is_manual_upload and vis_dur < main_target - 1.0:
        extended = (
            Path(settings.media_root)
            / "visuals"
            / str(song.id)
            / f"main_16x9_loop{int(main_target)}_{uuid.uuid4().hex[:10]}.mp4"
        )
        visual, vis_dur = smooth_extend_main_visual(
            visual,
            extended,
            target_sec=main_target,
        )
        song.video_clip_path = str(visual)
        logger.info(
            "Loop-extended main visual to %.1fs (native speed) for song %s",
            vis_dur,
            song.id,
        )

    # Drop hush / empty intro so the video starts with real music
    trimmed_audio = out_dir / f"audio_trim_{uuid.uuid4().hex[:8]}.wav"
    audio, lead_trimmed = trim_leading_silence(raw_audio, trimmed_audio)
    if lead_trimmed >= 0.4:
        logger.info(
            "Trimmed %.1fs leading silence from song %s",
            lead_trimmed,
            song.id,
        )

    loud_audio = out_dir / f"audio_loud_{uuid.uuid4().hex[:8]}.wav"
    audio, boost_db = normalize_loudness(audio, loud_audio)
    audio_dur = _ffprobe_duration(audio)

    main_out = out_dir / f"final_16x9_{uuid.uuid4().hex[:10]}.mp4"
    main_path, main_dur = mux_looped_av(video=visual, audio=audio, out_path=main_out)
    song.final_video_path = str(main_path)
    if song.stage in {"music_ready", "video_ready", "lyrics_draft", "awaiting_audio"}:
        song.stage = "final_ready"

    n_shorts = max(1, min(2, int(getattr(get_settings(), "shorts_count", 1) or 1)))
    short_results: list[dict] = []
    for short in sorted(song.shorts or [], key=lambda s: s.slot_index):
        if int(short.slot_index) > n_shorts:
            continue
        if not short.clip_path or not Path(short.clip_path).exists():
            continue
        # Always Pallavi (main hook) — not Charanam; windows are on trimmed audio
        a0, a1 = pallavi_audio_window(
            lyrics,
            audio_dur,
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
                "section": "pallavi",
                "url": f"/api/v1/songs/{song.id}/shorts/{short.slot_index}/final",
            }
        )

    db.flush()
    windows_note = "; ".join(
        f"Short {r['slot_index']} ← Pallavi "
        f"audio {r['audio_start_sec']:.0f}s–{r['audio_end_sec']:.0f}s"
        for r in short_results
    )
    lead_note = (
        f" Trimmed {lead_trimmed:.1f}s leading silence."
        if lead_trimmed >= 0.4
        else ""
    )
    boost_note = (
        f" Loudness normalized ({boost_db:+.1f}dB → "
        f"{get_settings().audio_target_lufs:.0f} LUFS)."
        if abs(boost_db) >= 0.5
        else ""
    )
    return {
        "final_video_path": str(main_path),
        "final_video_url": f"/api/v1/songs/{song.id}/final",
        "duration_sec": main_dur,
        "aspect_ratio": "16:9",
        "lead_silence_trimmed_sec": lead_trimmed,
        "audio_boost_db": boost_db,
        "shorts": short_results,
        "note": (
            "Final mix ready — long-form uses full Suno audio;"
            f"{lead_note}{boost_note} "
            f"Shorts use Pallavi hook cuts ({windows_note}). Preview before publish."
        ),
    }
