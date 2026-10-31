"""Kling main clip @ 16:9 → ffmpeg Shorts @ 9:16 center-crop, looped <30s (no Kling re-gen)."""

from __future__ import annotations

import logging
import math
import subprocess
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.content_templates import fill_shorts_pair
from app.lyrics_sections import extract_charanams
from app.models import ShortProject, SongProject
from app.progress import ProgressFn, report
from app.providers import gemini_video, kling_video
from app.providers.gemini_video import GeminiVideoError
from app.providers.kling_video import KlingVideoError

logger = logging.getLogger(__name__)

# YouTube Shorts must stay under 60s; product rule: keep each Short under 30s.
SHORT_MAX_SEC = 29.0
SHORT_WIDTH = 720
SHORT_HEIGHT = 1280  # 9:16
MAIN_WIDTH = 1280
MAIN_HEIGHT = 720  # 16:9 Kling 2.5 Turbo


def build_visual_prompt(song: SongProject) -> str:
    """Lyrics-driven Omni video prompt — not a fixed generic temple stock clip."""
    from app.providers.kling_images import build_lyrics_scene_brief
    from app.thumbnail_compose import infer_mood

    lyrics = _latest_lyrics(song)
    mood = infer_mood(
        lyrics=lyrics,
        style_prompt=song.style_prompt,
        deity=song.deity,
        daypart=None,
    )
    brief = build_lyrics_scene_brief(
        deity=song.deity,
        mood=mood,
        lyrics=lyrics,
        title=song.title,
        visual_style=song.visual_style,
        style_prompt=song.style_prompt,
        notes=getattr(song, "notes", None),
    )
    return (
        f"{brief} "
        "Motion: slow cinematic camera drift, gentle incense haze, flickering diya light, "
        "soft petal drift, continuous smooth single shot. "
        "Keep the deity near FRAME CENTER so a later 9:16 center-crop still frames the subject. "
        "NO text, NO letters, NO watermark, NO logo, NO Sai Baba, NO modern selfies."
    )[:2500]


def _latest_lyrics(song: SongProject) -> str | None:
    if not song.lyrics_versions:
        return None
    return song.lyrics_versions[-1].body


def _ffprobe_duration(path: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
            timeout=30,
        ).strip()
        return max(0.1, float(out))
    except Exception:  # noqa: BLE001
        return 10.0


def _run_ffmpeg(cmd: list[str], *, timeout: int = 180) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode("utf-8", errors="replace")[:600]
        raise RuntimeError(f"ffmpeg failed: {err}") from exc


def normalize_main_clip_16x9(source: Path, out_path: Path) -> Path:
    """Ensure main deliverable is explicit 16:9 1280x720 (letterbox if needed)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={MAIN_WIDTH}:{MAIN_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={MAIN_WIDTH}:{MAIN_HEIGHT}:(ow-iw)/2:(oh-ih)/2"
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
    )
    return out_path


def loop_clip_under(
    *,
    source: Path,
    out_path: Path,
    max_sec: float = SHORT_MAX_SEC,
    portrait_center_crop: bool = False,
) -> tuple[Path, float]:
    """Repeat the same clip until just under max_sec (default <30s).

    portrait_center_crop=True → 9:16 center crop (keeps frame center / deity).
    portrait_center_crop=False → keep 16:9 (main video).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    src_dur = _ffprobe_duration(source)
    target = min(max_sec, max(src_dur, min(max_sec, math.floor(max_sec / src_dur) * src_dur or src_dur)))
    # Prefer filling close to max_sec without exceeding
    if src_dur >= max_sec:
        target = max_sec
        loops = 0
    else:
        loops = max(0, math.ceil(max_sec / src_dur) - 1)
        target = min(max_sec, src_dur * (loops + 1))
        # trim a hair under 30s
        if target >= max_sec:
            target = max_sec - 0.05

    if portrait_center_crop:
        # Scale up to cover 9:16, then CENTER crop — keeps deity/chars in the middle
        vf = (
            f"scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{SHORT_HEIGHT}:(iw-{SHORT_WIDTH})/2:(ih-{SHORT_HEIGHT})/2"
        )
    else:
        vf = (
            f"scale={MAIN_WIDTH}:{MAIN_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={MAIN_WIDTH}:{MAIN_HEIGHT}:(ow-iw)/2:(oh-ih)/2"
        )

    cmd = ["ffmpeg", "-y"]
    if loops > 0:
        cmd += ["-stream_loop", str(loops)]
    cmd += [
        "-i",
        str(source),
        "-t",
        f"{target:.2f}",
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    _run_ffmpeg(cmd, timeout=240)
    return out_path, _ffprobe_duration(out_path)


def ensure_shorts_rows(db: Session, song: SongProject, *, lyrics: str | None) -> list[ShortProject]:
    charanams = extract_charanams(lyrics, limit=2)
    defs = fill_shorts_pair(
        title=song.title,
        deity=song.deity,
        main_url=song.youtube_url,
        youtube_title=song.youtube_title,
        youtube_description=song.youtube_description,
        charanams=charanams,
    )
    existing = {s.slot_index: s for s in (song.shorts or [])}
    rows: list[ShortProject] = []
    for short_def in defs:
        row = existing.get(short_def["slot_index"])
        if row is None:
            row = ShortProject(
                song_id=song.id,
                slot_index=short_def["slot_index"],
                title=short_def["title"],
                hook=short_def["hook"],
                description=short_def["description"],
                stage="planned",
                publish_at=song.publish_at,
            )
            db.add(row)
        else:
            # Refresh copy from latest Charanam whenever we rebuild visuals
            row.title = short_def["title"]
            row.hook = short_def["hook"]
            row.description = short_def["description"]
        rows.append(row)
    db.flush()
    return sorted(rows, key=lambda s: s.slot_index)


def _gemini_exhausted(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "429",
            "resource exhausted",
            "quota",
            "rate limit",
            "rate_limit",
            "insufficient",
            "billing",
            "403",
            "permission denied",
        )
    )


def _generate_raw_clip(
    *,
    prompt: str,
    raw_path: Path,
    on_progress: ProgressFn | None = None,
) -> tuple[str, str]:
    """Return (engine, resolution). Gemini first when VIDEO_PROVIDER=auto."""
    settings = get_settings()
    provider = (settings.video_provider or "auto").strip().lower()
    res = (settings.kling_video_resolution or settings.gemini_video_resolution or "720p").strip().lower()
    if res not in {"720p", "1080p"}:
        res = "720p"

    def _kling() -> str:
        if not kling_video.is_configured():
            raise KlingVideoError("KLING_API_KEY missing")

        def _kling_progress(pct: int, message: str) -> None:
            mapped = 5 + int(max(0, min(100, pct)) * 0.83)
            report(on_progress, mapped, message)

        report(on_progress, 5, f"Submitting Kling ({settings.kling_video_model}) 16:9 silent…")
        kling_video.generate_clip(
            prompt=prompt,
            out_path=raw_path,
            resolution=res,
            aspect_ratio="16:9",
            duration_sec=settings.kling_video_duration,
            on_progress=_kling_progress,
        )
        return "kling_4_0"

    use_gemini = provider in {"auto", "gemini"} and gemini_video.is_configured()
    force_kling = provider in {"kling", "kling-4.0", "kling_4_0"}

    if force_kling or not use_gemini:
        return _kling(), res

    try:
        report(on_progress, 5, f"Submitting Gemini video ({settings.gemini_video_model})…")
        gemini_video.generate_clip(
            prompt=prompt,
            out_path=raw_path,
            resolution=res,
            aspect_ratio="16:9",
            duration_sec=settings.gemini_video_duration,
        )
        report(on_progress, 88, "Gemini clip ready…")
        return "gemini", res
    except GeminiVideoError as exc:
        if provider == "gemini":
            raise
        logger.warning("Gemini video failed (%s) — falling back to Kling", exc)
        report(
            on_progress,
            6,
            f"Gemini exhausted/failed ({'quota' if _gemini_exhausted(exc) else 'error'}) — Kling fallback…",
        )
        return _kling(), res


def generate_visual_and_shorts(
    db: Session,
    song: SongProject,
    *,
    on_progress: ProgressFn | None = None,
) -> dict:
    """One silent 16:9 clip (Gemini→Kling) → main + 2 Shorts 9:16 center-crop <30s."""
    settings = get_settings()
    if not gemini_video.is_configured() and not kling_video.is_configured():
        raise KlingVideoError("No video provider configured (GEMINI_API_KEY / KLING_API_KEY)")

    report(on_progress, 2, "Building lyrics-driven visual prompt…")
    prompt = build_visual_prompt(song)
    song.visual_prompt = prompt
    lyrics = _latest_lyrics(song)

    out_dir = Path(settings.media_root) / "visuals" / str(song.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"raw_{uuid.uuid4().hex[:10]}.mp4"

    engine, res = _generate_raw_clip(prompt=prompt, raw_path=raw_path, on_progress=on_progress)

    # Main = 16:9, looped under 30s from the same clip (no second AI call)
    report(on_progress, 90, "Looping 16:9 main under 30s (ffmpeg)…")
    main_path = out_dir / f"main_16x9_{uuid.uuid4().hex[:10]}.mp4"
    _, main_dur = loop_clip_under(
        source=raw_path,
        out_path=main_path,
        max_sec=SHORT_MAX_SEC,
        portrait_center_crop=False,
    )
    song.video_clip_path = str(main_path)
    if song.stage in {
        "lyrics_draft",
        "lyrics_ready",
        "music_ready",
        "prep_running",
        "scheduled",
        "ready_to_publish",
    }:
        song.stage = "video_ready"

    shorts = ensure_shorts_rows(db, song, lyrics=lyrics)
    charanams = extract_charanams(lyrics, limit=2)
    cut_paths: list[dict] = []
    for short, verse in zip(shorts, charanams, strict=False):
        report(
            on_progress,
            93 + short.slot_index * 3,
            f"Cutting Short {short.slot_index} (9:16 center-crop)…",
        )
        out = out_dir / f"short_{short.slot_index}_9x16_{uuid.uuid4().hex[:8]}.mp4"
        _, short_dur = loop_clip_under(
            source=raw_path,
            out_path=out,
            max_sec=SHORT_MAX_SEC,
            portrait_center_crop=True,
        )
        short.clip_path = str(out)
        short.stage = "clip_ready"
        cut_paths.append(
            {
                "slot_index": short.slot_index,
                "path": str(out),
                "aspect_ratio": "9:16",
                "crop": "center",
                "duration_sec": short_dur,
                "charanam_index": short.slot_index,
                "charanam_hook": (short.hook or "")[:120],
                "looped_from_sec": _ffprobe_duration(raw_path),
            }
        )

    report(on_progress, 100, "Visual + Shorts ready")
    engine_label = "Gemini" if engine == "gemini" else f"Kling ({settings.kling_video_model})"
    return {
        "video_clip_path": str(main_path),
        "resolution": res,
        "aspect_ratio": "16:9",
        "duration_sec": main_dur,
        "engine": engine,
        "shorts": cut_paths,
        "note": (
            f"{engine_label} once silent @ {res} 16:9; "
            f"main looped <{int(SHORT_MAX_SEC)+1}s; "
            f"2 Shorts = ffmpeg 9:16 CENTER crop + loop "
            "(Charanam 1 / Charanam 2) — no second AI call."
        ),
    }
