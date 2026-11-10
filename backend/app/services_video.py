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
from app.lyrics_sections import extract_sections
from app.models import ShortProject, SongProject
from app.progress import ProgressFn, report
from app.providers import gemini_video, kling_images, kling_video
from app.providers.gemini_video import GeminiVideoError
from app.providers.kling_video import KlingVideoError

logger = logging.getLogger(__name__)

# YouTube Shorts must stay under 60s; product rule: keep each Short under 30s.
SHORT_MAX_SEC = 29.0
SHORT_WIDTH = 720
SHORT_HEIGHT = 1280  # 9:16
MAIN_WIDTH = 1280
MAIN_HEIGHT = 720  # 16:9 Kling 2.5 Turbo
# Long-form visual: soft-loop short AI/manual clips to ~45s at native speed (then mux loops under song)
MAIN_MIN_SEC = 45.0


def build_visual_prompt(song: SongProject) -> str:
    """Lyrics-driven ritual video — god ideal murti + pooja/event motion."""
    from app.providers.kling_images import (
        _ritual_event_from_lyrics,
        build_lyrics_scene_brief,
    )
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
    event_label, event_dir = _ritual_event_from_lyrics(
        lyrics=lyrics,
        deity=song.deity,
        title=song.title,
        visual_style=song.visual_style,
        style_prompt=song.style_prompt,
        notes=getattr(song, "notes", None),
        mood=mood,
    )
    return (
        f"{brief} "
        f"VIDEO MOTION — continuous single shot of the ritual «{event_label}»: {event_dir}. "
        "Animate the POOJA/EVENT itself (pouring abhishekam, circling aarti flame, "
        "garland placement, lamp flicker, incense rise, flower offering) — "
        "NOT only camera zoom on a still portrait. "
        "Deity stays classical murti/god ideal centered for later 9:16 crop. "
        "Slow sacred pacing, temple realism, soft haze. "
        "NO drama-actor face, NO text, letters, watermark, logo, Sai Baba, selfies."
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
        f"pad={MAIN_WIDTH}:{MAIN_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
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
            "fast",
            "-crf",
            "17",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
    )
    return out_path


def crop_kling_watermark(source: Path, out_path: Path | None = None) -> Path:
    """Drop bottom-right Kling mark while keeping the subject centered.

    Left-anchored crops push characters to the right on 9:16 reels. Trim a bit
    more from the right/bottom than the left, but keep the crop near center, then
    force clean 1280x720 square pixels.
    """
    src = Path(source)
    if not src.exists():
        raise RuntimeError(f"Missing video for watermark crop: {src}")
    dest = Path(out_path) if out_path else src.with_name(src.stem + "_nowm" + src.suffix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # ~3% left / ~9% right / ~8% bottom — removes BR mark, subject stays centered.
    vf = (
        f"crop=iw*0.88:ih*0.92:iw*0.03:0,"
        f"scale={MAIN_WIDTH}:{MAIN_HEIGHT}:flags=lanczos,"
        f"setsar=1,format=yuv420p"
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "17",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dest),
        ],
        timeout=420,
    )
    return dest


def _soft_loop_to_duration(
    source: Path,
    *,
    out_path: Path,
    target_sec: float,
) -> Path:
    """Repeat clip to target_sec with soft in/out fades (stable on VM — no xfade chains)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    src_dur = max(0.5, _ffprobe_duration(source))
    loops = max(0, math.ceil(target_sec / src_dur) - 1)
    fade_in = 0.5
    fade_out_start = max(0.0, target_sec - 0.6)
    vf = (
        f"fps=25,scale={MAIN_WIDTH}:{MAIN_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={MAIN_WIDTH}:{MAIN_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,"
        f"fade=t=in:st=0:d={fade_in:.2f},"
        f"fade=t=out:st={fade_out_start:.2f}:d=0.5"
    )
    cmd = ["ffmpeg", "-y"]
    if loops > 0:
        cmd += ["-stream_loop", str(loops)]
    cmd += [
        "-i",
        str(source),
        "-t",
        f"{target_sec:.2f}",
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "17",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    _run_ffmpeg(cmd, timeout=420)
    return out_path


def _ping_pong_video(source: Path, out_path: Path) -> Path:
    """Forward + reverse once so a short clip stretches without a hard cut jump."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filt = (
        "[0:v]split[f][r];"
        "[r]reverse[rev];"
        f"[f][rev]concat=n=2:v=1:a=0,"
        f"scale={MAIN_WIDTH}:{MAIN_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={MAIN_WIDTH}:{MAIN_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v]"
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-filter_complex",
            filt,
            "-map",
            "[v]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ],
        timeout=420,
    )
    return out_path


def _mild_slow_video(source: Path, out_path: Path, *, factor: float) -> Path:
    """Slow with blend frame interpolation (keeps motion calm vs raw setpts)."""
    factor = max(1.05, min(float(factor), 4.0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"setpts={factor:.3f}*PTS,"
        f"minterpolate=fps=25:mi_mode=blend,"
        f"scale={MAIN_WIDTH}:{MAIN_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={MAIN_WIDTH}:{MAIN_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
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
            str(out_path),
        ],
        timeout=480,
    )
    return out_path


def smooth_extend_main_visual(
    source: Path,
    out_path: Path,
    *,
    target_sec: float | None = None,
) -> tuple[Path, float]:
    """Build a 16:9 silent visual from a short clip at native speed.

    Keep the source motion as-is (no slow-mo / ping-pong). If the clip is
    shorter than target, soft-loop it; final mux also loops under the song.
    """
    settings = get_settings()
    want = float(target_sec or getattr(settings, "video_main_min_sec", MAIN_MIN_SEC) or MAIN_MIN_SEC)
    want = max(40.0, min(want, 180.0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    src_dur = max(0.5, _ffprobe_duration(source))

    if src_dur >= want - 0.5:
        normalize_main_clip_16x9(source, out_path)
        return out_path, _ffprobe_duration(out_path)

    _soft_loop_to_duration(source, out_path=out_path, target_sec=want)
    return out_path, _ffprobe_duration(out_path)

def short_visual_start_sec(src_dur: float, *, slot_index: int) -> float:
    """Legacy mid-offset for video-cut Shorts (fallback only).

    Short 1 → 0s. Short 2+ → mid-point when Ken Burns still is unavailable.
    """
    dur = max(0.5, float(src_dur or 0.0))
    slot = max(1, int(slot_index or 1))
    if slot <= 1:
        return 0.0
    start = dur * 0.5
    return min(start, max(0.0, dur - 0.75))


def mint_short2_still(
    *,
    song: SongProject,
    out_path: Path,
) -> tuple[Path, str]:
    """Fresh AI still for Short 2 — Kling first (credits), then Gemini, then Cursor."""
    from app.providers import cursor_images, gemini_images, kling_images
    from app.thumbnail_compose import infer_mood

    out_path.parent.mkdir(parents=True, exist_ok=True)
    lyrics = _latest_lyrics(song)
    mood = infer_mood(
        lyrics=lyrics,
        style_prompt=song.style_prompt,
        deity=song.deity,
        daypart=None,
    )
    title = f"{song.title or 'Ragam Spiritual'} — Short 2 ritual seva"
    style = (
        f"Distinct Shorts plate (not a video frame grab): classical murti ideal of "
        f"{song.deity or 'deity'}, temple darshan, aarti / alankaram beat, "
        f"ultra-premium cinematic still, NO text, NO watermark, NO logo."
    )
    base_kwargs = dict(
        deity=song.deity,
        mood=mood,
        lyrics=lyrics,
        title=title,
        visual_style=song.visual_style,
        style_prompt=style,
        notes=getattr(song, "notes", None),
        out_path=out_path,
    )
    errors: list[str] = []
    # Prefer Kling for Short 2 — user keeps image credits here; Gemini often 429.
    # Use 2K + no style-ref for faster Omni turnaround on Shorts.
    for name, mod in (
        ("kling", kling_images),
        ("gemini", gemini_images),
        ("cursor", cursor_images),
    ):
        if not mod.is_configured():
            continue
        try:
            kwargs = dict(base_kwargs)
            if name == "kling":
                kwargs["resolution"] = "2k"
                kwargs["use_style_ref"] = False
            path = mod.generate_rich_deity_scene(**kwargs)
            return path, name
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}:{exc}")
            logger.warning("Short2 still %s failed: %s", name, exc)
    raise RuntimeError(
        "Short2 AI still failed (" + "; ".join(errors[-3:]) + ")"
        if errors
        else "Short2 AI still failed — no image provider configured"
    )


def cut_short_clip(
    *,
    slot_index: int,
    video_source: Path,
    out_path: Path,
    still_image: Path | None = None,
    song: SongProject | None = None,
    mint_ai_still: bool = True,
    max_sec: float = SHORT_MAX_SEC,
) -> tuple[Path, float, dict]:
    """Build one Short visual.

    Short 1 = 9:16 crop/loop from the main video.
    Short 2+ = Ken Burns from a freshly minted AI still (Kling→Gemini→Cursor),
    not a video re-cut. Falls back to provided still, then mid-offset video cut.
    """
    slot = max(1, int(slot_index or 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta: dict = {"slot_index": slot, "aspect_ratio": "9:16", "crop": "center"}

    if slot <= 1:
        _, dur = loop_clip_under(
            source=video_source,
            out_path=out_path,
            max_sec=max_sec,
            portrait_center_crop=True,
            start_sec=0.0,
        )
        meta.update({"method": "video_crop", "visual_start_sec": 0.0})
        return out_path, dur, meta

    still: Path | None = None
    still_source = "provided"
    if mint_ai_still and song is not None:
        ai_path = out_path.parent / f"short{slot}_ai_still_{uuid.uuid4().hex[:10]}.jpg"
        try:
            still, still_source = mint_short2_still(song=song, out_path=ai_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Short %s AI still mint failed (%s) — local still", slot, exc)
            meta["ai_still_error"] = str(exc)[:240]

    if still is None and still_image and still_image.exists():
        still = still_image
        still_source = "local_thumb"

    if still is None:
        v_start = short_visual_start_sec(
            _ffprobe_duration(video_source), slot_index=slot
        )
        _, dur = loop_clip_under(
            source=video_source,
            out_path=out_path,
            max_sec=max_sec,
            portrait_center_crop=True,
            start_sec=v_start,
        )
        meta.update(
            {
                "method": "video_crop_mid_fallback",
                "visual_start_sec": v_start,
                "note": "no AI/local still — mid video cut",
            }
        )
        return out_path, dur, meta

    # Distinct motion from typical main Ken Burns cycle for Short 2
    motions = ("pan_right", "zoom_out", "pan_left", "zoom_in")
    motion = motions[(slot - 2) % len(motions)]
    kb_path = out_path.parent / f".kb_short{slot}_{uuid.uuid4().hex[:8]}.mp4"
    try:
        animate_still_to_clip(
            image_path=still,
            out_path=kb_path,
            duration_sec=10,
            width=MAIN_WIDTH,
            height=MAIN_HEIGHT,
            motion=motion,
        )
        _, dur = loop_clip_under(
            source=kb_path,
            out_path=out_path,
            max_sec=max_sec,
            portrait_center_crop=True,
            start_sec=0.0,
        )
    finally:
        try:
            kb_path.unlink(missing_ok=True)
        except OSError:
            pass

    meta.update(
        {
            "method": "kenburns_still",
            "visual_start_sec": 0.0,
            "motion": motion,
            "still": str(still),
            "still_source": still_source,
        }
    )
    return out_path, dur, meta


def loop_clip_under(
    *,
    source: Path,
    out_path: Path,
    max_sec: float = SHORT_MAX_SEC,
    portrait_center_crop: bool = False,
    start_sec: float = 0.0,
) -> tuple[Path, float]:
    """Repeat the same clip until just under max_sec (default <30s).

    portrait_center_crop=True → 9:16 center crop (keeps frame center / deity).
    portrait_center_crop=False → keep 16:9 (main video).
    start_sec → seek into the (looped) source first, so Short 2 can open mid-clip.
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

    seek = max(0.0, float(start_sec or 0.0))
    if seek >= src_dur - 0.25:
        seek = 0.0

    # Phase-rotate once (mid→end + 0→mid) so Short 2 opens mid-clip, then loop.
    # Avoids slow -ss-after-input on a long stream_loop decode.
    loop_source = source
    rotated: Path | None = None
    if seek > 0.05:
        rotated = out_path.parent / f".rot_{out_path.stem}_{uuid.uuid4().hex[:6]}.mp4"
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-filter_complex",
                (
                    f"[0:v]trim=start={seek:.3f},setpts=PTS-STARTPTS[a];"
                    f"[0:v]trim=duration={seek:.3f},setpts=PTS-STARTPTS[b];"
                    f"[a][b]concat=n=2:v=1:a=0[v]"
                ),
                "-map",
                "[v]",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                str(rotated),
            ],
            timeout=180,
        )
        loop_source = rotated

    if portrait_center_crop:
        # Scale up to cover 9:16, then CENTER crop — keeps deity/chars in the middle
        vf = (
            f"scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{SHORT_HEIGHT}:(iw-{SHORT_WIDTH})/2:(ih-{SHORT_HEIGHT})/2,"
            f"setsar=1,format=yuv420p"
        )
    else:
        vf = (
            f"scale={MAIN_WIDTH}:{MAIN_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={MAIN_WIDTH}:{MAIN_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
        )

    cmd = ["ffmpeg", "-y"]
    if loops > 0:
        cmd += ["-stream_loop", str(loops)]
    cmd += [
        "-i",
        str(loop_source),
        "-t",
        f"{target:.2f}",
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "17",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    try:
        _run_ffmpeg(cmd, timeout=240)
    finally:
        if rotated is not None:
            try:
                rotated.unlink(missing_ok=True)
            except OSError:
                pass
    return out_path, _ffprobe_duration(out_path)


def configured_shorts_count() -> int:
    return max(1, min(2, int(getattr(get_settings(), "shorts_count", 1) or 1)))


def active_shorts(song: SongProject) -> list[ShortProject]:
    """Shorts rows honored by SHORTS_COUNT (hides paused Short 2+ in API/UI)."""
    n = configured_shorts_count()
    return sorted(
        (s for s in (song.shorts or []) if int(s.slot_index) <= n),
        key=lambda s: s.slot_index,
    )


def ensure_shorts_rows(db: Session, song: SongProject, *, lyrics: str | None) -> list[ShortProject]:
    n_shorts = configured_shorts_count()
    pallavi = (extract_sections(lyrics).get("pallavi") or song.title or "").strip()
    defs = fill_shorts_pair(
        title=song.title,
        deity=song.deity,
        main_url=song.youtube_url,
        youtube_title=song.youtube_title,
        youtube_description=song.youtube_description,
        charanams=[pallavi] if pallavi else None,
        count=n_shorts,
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
            # Refresh copy from latest Pallavi whenever we rebuild visuals
            row.title = short_def["title"]
            row.hook = short_def["hook"]
            row.description = short_def["description"]
        rows.append(row)
    db.flush()
    return sorted(rows, key=lambda s: s.slot_index)


def _provider_exhausted(exc: BaseException) -> bool:
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
            "balance",
            "credit",
        )
    )


def _strip_text_from_stamped_thumbnail(thumb: Path) -> Path | None:
    """Best-effort: remove Telugu/logo from an old stamped thumb.

    New thumbs already save `thumb_clean_bg.jpg` *before* text is painted.
    Legacy: cover logo + right/bottom text bands by cloning nearby scene pixels.
    """
    from PIL import Image, ImageFilter

    try:
        img = Image.open(thumb).convert("RGB")
    except OSError:
        return None
    w, h = img.size
    if w < 64 or h < 64:
        return None

    clean = img.copy()

    def _cover(box: tuple[int, int, int, int], src_box: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = box
        sx0, sy0, sx1, sy1 = src_box
        if x1 <= x0 or y1 <= y0 or sx1 <= sx0 or sy1 <= sy0:
            return
        patch = img.crop((sx0, sy0, sx1, sy1)).resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
        patch = patch.filter(ImageFilter.GaussianBlur(1.2))
        clean.paste(patch, (x0, y0))

    # Top-left logo / RAGAM badge
    _cover((0, 0, min(260, w), min(220, h)), (0, min(220, h // 2), min(260, w), min(440, h)))
    # Right text column (prefer_photo layout)
    _cover((int(w * 0.42), int(h * 0.18), w, int(h * 0.78)), (int(w * 0.08), int(h * 0.18), int(w * 0.40), int(h * 0.78)))
    # Bottom title / subtitle band (non-photo layout)
    _cover((0, int(h * 0.52), w, h), (0, int(h * 0.22), w, int(h * 0.50)))

    clean = clean.filter(ImageFilter.SMOOTH)
    out = thumb.parent / "thumb_clean_bg.jpg"
    clean.save(out, format="JPEG", quality=92, optimize=True, subsampling=0)
    return out if out.exists() else None


def _still_image_for_song(song: SongProject) -> Path | None:
    """Clean still only — never animate Telugu-stamped YouTube thumbs as-is.

    Order: deity upload → AI scene → saved text-free plate → strip text from
    stamped thumbnail as last resort.
    """
    raw = getattr(song, "deity_image_path", None)
    if raw and Path(raw).exists():
        return Path(raw)

    settings = get_settings()
    thumb_dir = Path(settings.media_root) / "thumbnails" / str(song.id)

    premium = thumb_dir / "ai_scene_premium.png"
    if premium.exists():
        return premium
    if thumb_dir.is_dir():
        scenes = sorted(
            thumb_dir.glob("ai_scene_*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if scenes:
            return scenes[0]

    # Saved at compose time (scene before Telugu/logo) — prefer over strip guess
    clean_plate = thumb_dir / "thumb_clean_bg.jpg"
    stamped = getattr(song, "thumbnail_path", None)
    stamped_path = Path(stamped) if stamped else None
    if (
        clean_plate.exists()
        and stamped_path
        and stamped_path.exists()
        and clean_plate.stat().st_mtime >= stamped_path.stat().st_mtime - 1
    ):
        return clean_plate
    if clean_plate.exists() and (not stamped_path or not stamped_path.exists()):
        return clean_plate

    # Legacy stamped thumb — derive text-free still (overwrites older strip)
    if stamped_path and stamped_path.exists():
        stripped = _strip_text_from_stamped_thumbnail(stamped_path)
        if stripped and stripped.exists():
            return stripped
    return None


def _ensure_petal_assets() -> list[Path]:
    """Realistic Kling flower petals (cached). Falls back to drawn petals if Kling fails."""
    from PIL import Image, ImageDraw

    settings = get_settings()
    petal_dir = Path(settings.media_root) / "assets" / "petals"
    petal_dir.mkdir(parents=True, exist_ok=True)

    real = sorted(petal_dir.glob("petal_real_*.png"))
    if len(real) >= 4:
        return real

    if kling_images.is_configured():
        try:
            from app.providers.kling_images import generate_realistic_petals

            return generate_realistic_petals(petal_dir, count=6)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Kling realistic petals failed (%s) — drawn fallback", exc)

    # Last resort: simple drawn petals (not preferred)
    colors = [
        ((255, 140, 40, 230), (255, 200, 80, 200)),
        ((255, 90, 110, 220), (255, 170, 180, 190)),
        ((255, 210, 60, 230), (255, 240, 140, 200)),
        ((255, 120, 60, 220), (255, 180, 100, 190)),
        ((240, 80, 120, 220), (255, 150, 170, 190)),
        ((255, 160, 50, 230), (255, 220, 120, 200)),
    ]
    paths: list[Path] = []
    for i, (outer, inner) in enumerate(colors):
        path = petal_dir / f"petal_drawn_{i}.png"
        if not path.exists():
            img = Image.new("RGBA", (64, 80), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((8, 4, 56, 72), fill=outer)
            draw.ellipse((18, 18, 46, 58), fill=inner)
            draw.ellipse((28, 30, 36, 48), fill=(255, 255, 220, 160))
            img.save(path)
        paths.append(path)
    return paths


def animate_still_to_clip(
    *,
    image_path: Path,
    out_path: Path,
    duration_sec: int = 10,
    width: int = MAIN_WIDTH,
    height: int = MAIN_HEIGHT,
    motion: str = "inout",
) -> Path:
    """Local still animation — no API credits.

    Motions: inout (5s in/5s out), zoom_in, zoom_out, pan_left, pan_right.
    Falling flower petals overlaid. Two-pass to stay light on VM memory.
    """
    if not image_path.exists():
        raise RuntimeError(f"Still image missing: {image_path}")

    motion_key = (motion or "inout").strip().lower()
    # Longer duration = slower sacred zoom/pan (native frames — not jerky setpts)
    dur = max(5, min(20, int(duration_sec or 10)))
    if motion_key == "inout" and int(duration_sec or 0) <= 0:
        dur = 10
    fps = 25
    frames = dur * fps
    half = max(1, frames // 2)

    if motion_key == "zoom_in":
        z_expr = f"1+0.32*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_key == "zoom_out":
        z_expr = f"1.32-0.32*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_key == "pan_left":
        z_expr = "1.18"
        x_expr = f"(iw-iw/zoom)*(1-on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_key == "pan_right":
        z_expr = "1.18"
        x_expr = f"(iw-iw/zoom)*on/{frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        # inout
        z_expr = (
            f"if(lte(on\\,{half})"
            f"\\,1+0.32*on/{half}"
            f"\\,1.32-0.32*(on-{half})/{half})"
        )
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    zoom_tmp = out_path.with_name(f"{out_path.stem}_zoom{out_path.suffix}")

    # Pass 1: camera move (moderate upscale — 8000 OOM'd the VM)
    zoom_vf = (
        f"scale=3200:-2,"
        f"zoompan=z='{z_expr}'"
        f":x='{x_expr}':y='{y_expr}'"
        f":d={frames}:s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-vf",
            zoom_vf,
            "-t",
            str(dur),
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(zoom_tmp),
        ],
        timeout=240,
    )

    petals = _ensure_petal_assets()
    petal_specs = [
        # (asset_idx, scale, x_base, speed_px_s, phase, sway, spin_hz)
        (0, 48, 90, 95, 0.0, 18, 0.35),
        (1, 40, 260, 120, 1.2, 22, -0.45),
        (2, 56, 430, 85, 2.4, 14, 0.28),
        (3, 44, 620, 110, 0.6, 20, -0.38),
        (4, 52, 820, 100, 1.8, 16, 0.42),
        (5, 42, 1040, 130, 3.1, 24, -0.32),
        (0, 46, 180, 105, 2.0, 19, 0.5),
        (2, 54, 720, 115, 2.8, 17, -0.4),
    ]

    cmd: list[str] = ["ffmpeg", "-y", "-i", str(zoom_tmp)]
    for asset_idx, *_rest in petal_specs:
        cmd += ["-loop", "1", "-t", str(dur), "-i", str(petals[asset_idx % len(petals)])]

    filter_parts = ["[0:v]format=rgba[base]"]
    last = "base"
    for i, (asset_idx, scale, x_base, speed, phase, sway, spin_hz) in enumerate(petal_specs):
        pin = i + 1
        scaled = f"p{i}"
        # Rotate continuously while falling (c=none keeps transparent canvas)
        filter_parts.append(
            f"[{pin}:v]scale={scale}:-1,format=rgba,"
            f"rotate=a='{spin_hz}*2*PI*t+{phase}':c=none:ow=rotw(iw):oh=roth(ih),"
            f"colorchannelmixer=aa=0.92[{scaled}]"
        )
        nxt = f"v{i}"
        y_expr = f"-h+mod({speed}*t+{phase * 40:.1f}\\, {height}+h)"
        x_expr = f"{x_base}+{sway}*sin(2*PI*t/3+{phase})"
        filter_parts.append(
            f"[{last}][{scaled}]overlay=x='{x_expr}':y='{y_expr}':shortest=1[{nxt}]"
        )
        last = nxt
    filter_parts.append(f"[{last}]format=yuv420p[outv]")

    cmd += [
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[outv]",
        "-t",
        str(dur),
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(out_path),
    ]
    try:
        _run_ffmpeg(cmd, timeout=300)
    finally:
        zoom_tmp.unlink(missing_ok=True)

    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError("Ken Burns animate produced empty clip")
    return out_path


def _generate_raw_clip(
    *,
    prompt: str,
    raw_path: Path,
    still_image: Path | None = None,
    on_progress: ProgressFn | None = None,
) -> tuple[str, str]:
    """Return (engine, resolution). Gemini → Kling → Ken Burns still."""
    settings = get_settings()
    provider = (settings.video_provider or "auto").strip().lower()
    res = (settings.kling_video_resolution or settings.gemini_video_resolution or "720p").strip().lower()
    if res not in {"720p", "1080p"}:
        res = "720p"
    w, h = (1280, 720) if res == "720p" else (1920, 1080)
    dur = int(settings.kling_video_duration or settings.gemini_video_duration or 10)

    def _still(reason: str) -> str:
        if still_image is None:
            raise KlingVideoError(
                f"{reason}; no clean still for Ken Burns fallback. "
                "Upload a deity image or generate an AI scene (text-stamped "
                "YouTube thumbnails are not used)."
            )
        report(on_progress, 8, f"{reason} — animating still (Ken Burns, local)…")
        animate_still_to_clip(
            image_path=still_image,
            out_path=raw_path,
            duration_sec=dur,
            width=w,
            height=h,
        )
        report(on_progress, 88, "Ken Burns clip ready…")
        return "ken_burns_still"

    def _kling() -> str:
        if not kling_video.is_configured():
            return _still("Kling not configured")

        def _kling_progress(pct: int, message: str) -> None:
            mapped = 5 + int(max(0, min(100, pct)) * 0.83)
            report(on_progress, mapped, message)

        report(on_progress, 5, f"Submitting Kling ({settings.kling_video_model}) 16:9 silent…")
        try:
            kling_video.generate_clip(
                prompt=prompt,
                out_path=raw_path,
                resolution=res,
                aspect_ratio="16:9",
                duration_sec=settings.kling_video_duration,
                on_progress=_kling_progress,
            )
            return "kling_4_0"
        except KlingVideoError as exc:
            if provider in {"kling", "kling-4.0", "kling_4_0"} and still_image is None:
                raise
            logger.warning("Kling video failed (%s) — Ken Burns fallback", exc)
            kind = "quota" if _provider_exhausted(exc) else "error"
            return _still(f"Kling exhausted/failed ({kind})")

    use_gemini = provider in {"auto", "gemini"} and gemini_video.is_configured()
    force_kling = provider in {"kling", "kling-4.0", "kling_4_0"}
    force_still = provider in {"still", "kenburns", "ken_burns", "image", "animate"}

    if force_still:
        return _still("Forced still animation"), res

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
        if provider == "gemini" and still_image is None:
            raise
        logger.warning("Gemini video failed (%s) — falling back", exc)
        report(
            on_progress,
            6,
            f"Gemini exhausted/failed ({'quota' if _provider_exhausted(exc) else 'error'}) — next fallback…",
        )
        if provider == "gemini":
            return _still("Gemini failed"), res
        return _kling(), res


def generate_visual_and_shorts(
    db: Session,
    song: SongProject,
    *,
    on_progress: ProgressFn | None = None,
) -> dict:
    """Preferred: scene orchestrator. Fallback: single AI/Ken Burns clip → Shorts."""
    settings = get_settings()
    pipeline = (getattr(settings, "video_pipeline", None) or "scenes").strip().lower()
    if pipeline in {"scenes", "scene", "orchestrator", "reel"}:
        try:
            from app.services_video_orchestrator import generate_scene_visual_and_shorts

            return generate_scene_visual_and_shorts(db, song, on_progress=on_progress)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Scene orchestrator failed (%s) — falling back to singleshot",
                exc,
            )
            report(on_progress, 3, f"Scene reel failed ({exc}) — singleshot fallback…")

    still = _still_image_for_song(song)
    if (
        not gemini_video.is_configured()
        and not kling_video.is_configured()
        and still is None
    ):
        raise KlingVideoError(
            "No video provider and no clean still — set GEMINI/KLING keys, "
            "upload a deity image, or generate an AI scene (no text stamp)"
        )

    report(on_progress, 2, "Building lyrics-driven visual prompt…")
    prompt = build_visual_prompt(song)
    song.visual_prompt = prompt
    lyrics = _latest_lyrics(song)

    out_dir = Path(settings.media_root) / "visuals" / str(song.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"raw_{uuid.uuid4().hex[:10]}.mp4"

    engine, res = _generate_raw_clip(
        prompt=prompt,
        raw_path=raw_path,
        still_image=still,
        on_progress=on_progress,
    )

    # Main = native-speed ~45s 16:9 (soft-loop only — no slow-mo) + Kling mark crop
    report(on_progress, 90, "Building looped ~45s 16:9 main visual…")
    looped_main = out_dir / f"main_16x9_{uuid.uuid4().hex[:10]}.mp4"
    main_target = float(getattr(get_settings(), "video_main_min_sec", MAIN_MIN_SEC) or MAIN_MIN_SEC)
    _, main_dur = smooth_extend_main_visual(
        raw_path,
        looped_main,
        target_sec=main_target,
    )
    main_path = out_dir / f"{looped_main.stem}_nowm.mp4"
    crop_kling_watermark(looped_main, main_path)
    main_dur = _ffprobe_duration(main_path)
    try:
        looped_main.unlink(missing_ok=True)
    except OSError:
        pass
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
    raw_dur = _ffprobe_duration(raw_path)
    short_still = still or _still_image_for_song(song)
    cut_paths: list[dict] = []
    for short in shorts:
        report(
            on_progress,
            93 + short.slot_index * 3,
            (
                f"Short {short.slot_index}: video crop…"
                if short.slot_index <= 1
                else f"Short {short.slot_index}: Ken Burns still (not video re-cut)…"
            ),
        )
        out = out_dir / f"short_{short.slot_index}_9x16_{uuid.uuid4().hex[:8]}.mp4"
        _, short_dur, short_meta = cut_short_clip(
            slot_index=short.slot_index,
            video_source=raw_path,
            out_path=out,
            still_image=short_still,
            song=song,
            max_sec=SHORT_MAX_SEC,
        )
        short.clip_path = str(out)
        short.stage = "clip_ready"
        cut_paths.append(
            {
                **short_meta,
                "path": str(out),
                "duration_sec": short_dur,
                "section": "pallavi",
                "pallavi_hook": (short.hook or "")[:120],
                "looped_from_sec": raw_dur,
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
            f"main native-speed loop ~{int(main_dur)}s 16:9; "
            "Short1=video 9:16 crop, Short2=Ken Burns still "
            "(Pallavi hook audio)."
        ),
    }


def _stream_copy_as_is(
    source: Path,
    out_path: Path,
    *,
    max_sec: float | None = None,
    start_sec: float = 0.0,
) -> Path:
    """Remux video bitstream only — no scale, crop, pad, or re-encode."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y"]
    seek = max(0.0, float(start_sec or 0.0))
    if seek > 0.05:
        cmd += ["-ss", f"{seek:.3f}"]
    cmd += ["-i", str(source)]
    if max_sec is not None:
        cmd += ["-t", f"{float(max_sec):.2f}"]
    cmd += [
        "-map",
        "0:v:0",
        "-c:v",
        "copy",
        "-an",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    _run_ffmpeg(cmd, timeout=600)
    return out_path


def apply_manual_visual_upload(
    db: Session,
    song: SongProject,
    *,
    source_path: Path,
    original_filename: str | None = None,
) -> dict:
    """Use an uploaded video as-is for main; cut Shorts as 9:16 center-crop.

    Main long-form: bitstream copy only (no scale/pad/watermark/re-encode).
    Shorts: true 9:16 center crop from that original (Short1 video, Short2+ still).
    """
    if not source_path.exists() or source_path.stat().st_size < 1000:
        raise RuntimeError("Uploaded video file is missing or empty")

    settings = get_settings()
    out_dir = Path(settings.media_root) / "visuals" / str(song.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    main_path = out_dir / f"main_manual_as_is_{uuid.uuid4().hex[:10]}.mp4"
    try:
        _stream_copy_as_is(source_path, main_path)
    except Exception as exc:  # noqa: BLE001
        # Odd containers: keep the original bytes rather than re-encode.
        logger.warning("stream-copy remux failed (%s) — copying bytes", exc)
        main_path.write_bytes(source_path.read_bytes())
    main_dur = _ffprobe_duration(main_path)

    lyrics = _latest_lyrics(song)
    shorts = ensure_shorts_rows(db, song, lyrics=lyrics)
    short_still = _still_image_for_song(song)
    cut_paths: list[dict] = []
    for short in shorts:
        out = out_dir / f"short_{short.slot_index}_manual_9x16_{uuid.uuid4().hex[:8]}.mp4"
        _, short_dur, short_meta = cut_short_clip(
            slot_index=short.slot_index,
            video_source=main_path,
            out_path=out,
            still_image=short_still,
            song=song,
            max_sec=SHORT_MAX_SEC,
        )
        short.clip_path = str(out)
        short.final_clip_path = None
        short.stage = "clip_ready"
        cut_paths.append({**short_meta, "path": str(out), "duration_sec": short_dur})

    song.video_clip_path = str(main_path)
    label = (original_filename or source_path.name).strip()[:120] or "manual.mp4"
    song.visual_prompt = f"[manual_upload] {label}"[:2000]
    if song.stage in {
        "lyrics_draft",
        "lyrics_ready",
        "awaiting_audio",
        "music_ready",
        "prep_running",
        "scheduled",
        "ready_to_publish",
        "final_ready",
        "video_ready",
    }:
        song.stage = "video_ready"

    # Stale muxed finals must not publish after a visual swap
    song.final_video_path = None

    db.flush()
    return {
        "video_clip_path": str(main_path),
        "resolution": "original",
        "aspect_ratio": "original",
        "duration_sec": main_dur,
        "engine": "manual_upload",
        "shorts": cut_paths,
        "note": (
            f"Manual video uploaded ({label}) — main kept as-is (~{int(main_dur)}s); "
            "Shorts = 9:16 center-crop. "
            "AI generation skipped. Run Mix to attach audio before publish."
        ),
    }
