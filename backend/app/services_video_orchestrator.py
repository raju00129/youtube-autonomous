"""Cost-efficient scene video orchestrator.

Plan 10–15 lyric/ritual hero stills → animate (Ken Burns / optional i2v) →
FFmpeg assemble with transitions → silent master for mix+Shorts.

Provider chain for stills:
  Gemini → Kling → Cursor → local crop/grade from thumbnail (Ken Burns).
Video animate: local Ken Burns (default) → optional Kling image-to-video.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageEnhance
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.lyrics_sections import extract_sections
from app.models import SongProject
from app.progress import ProgressFn, report
from app.providers import cursor_images, gemini_images, kling_images, kling_video
from app.providers.kling_images import _ritual_event_from_lyrics, build_lyrics_scene_brief
from app.services_video import (
    MAIN_HEIGHT,
    MAIN_WIDTH,
    SHORT_MAX_SEC,
    _ffprobe_duration,
    _run_ffmpeg,
    _still_image_for_song,
    animate_still_to_clip,
    cut_short_clip,
    ensure_shorts_rows,
    loop_clip_under,
)
from app.thumbnail_compose import infer_mood

logger = logging.getLogger(__name__)

Motion = Literal["inout", "zoom_in", "zoom_out", "pan_left", "pan_right"]
MOTIONS: tuple[Motion, ...] = ("inout", "zoom_in", "zoom_out", "pan_left", "pan_right")

_QUOTA_RE = re.compile(
    r"429|quota|rate.?limit|balance|credit|insufficient|free.?tier|resource.?exhausted|"
    r"billing|payment|capacity|too many requests",
    re.IGNORECASE,
)


@dataclass
class ImageExhaustion:
    gemini: bool = False
    kling: bool = False
    cursor: bool = False

    def mark_from_error(self, provider: str, exc: BaseException) -> None:
        if not _QUOTA_RE.search(str(exc)):
            # Non-quota failures: still skip hammering same provider for this job
            # after first hard fail to keep latency down.
            pass
        if provider == "gemini":
            self.gemini = True
        elif provider == "kling":
            self.kling = True
        elif provider == "cursor":
            self.cursor = True


@dataclass
class HeroScene:
    index: int
    label: str
    lyric_focus: str
    ritual: str
    ritual_direction: str
    character_key: str
    motion: Motion
    prompt: str


def _latest_lyrics(song: SongProject) -> str | None:
    if not song.lyrics_versions:
        return None
    return song.lyrics_versions[-1].body


def _latest_audio_duration(song: SongProject) -> float:
    music = song.music_generations[-1] if song.music_generations else None
    if not music or not music.file_path:
        return 180.0
    path = Path(music.file_path)
    if not path.exists():
        return 180.0
    return max(60.0, _ffprobe_duration(path))


def plan_hero_scenes(
    song: SongProject,
    *,
    count: int = 12,
    lyrics: str | None = None,
) -> list[HeroScene]:
    """10–15 hero scenes from lyric sections + ritual events (not 1-per-5s AI videos)."""
    body = (lyrics or _latest_lyrics(song) or "").strip()
    sections = extract_sections(body)
    mood = infer_mood(
        lyrics=body,
        style_prompt=song.style_prompt,
        deity=song.deity,
        daypart=None,
    )
    character_key = (song.deity or "deity").strip().lower() or "deity"

    seeds: list[tuple[str, str]] = []
    order = (
        "pallavi",
        "anupallavi",
        "charanam 1",
        "charanam",
        "charanam 2",
        "charanam 3",
        "slokam",
        "sloka",
        "body",
    )
    for key in order:
        if key in sections and sections[key].strip():
            seeds.append((key.title(), sections[key].strip()[:280]))
    if not seeds:
        seeds.append(("Bhakti", (song.title or "Telugu bhakti").strip()[:280]))

    # Expand seeds to target count by pairing with ritual variants
    ritual_cycle = [
        _ritual_event_from_lyrics(
            lyrics=f"{focus} {body}",
            deity=song.deity,
            title=song.title,
            visual_style=song.visual_style,
            style_prompt=song.style_prompt,
            notes=getattr(song, "notes", None),
            mood=mood,
        )
        for _, focus in seeds
    ]
    while len(seeds) < count:
        base_label, base_focus = seeds[len(seeds) % max(len(seeds), 1)]
        seeds.append((f"{base_label} seva", base_focus))
        ritual_cycle.append(
            _ritual_event_from_lyrics(
                lyrics=f"{base_focus} aarti deepam alankaram {body}",
                deity=song.deity,
                title=song.title,
                visual_style=song.visual_style,
                style_prompt=song.style_prompt,
                notes=getattr(song, "notes", None),
                mood=mood,
            )
        )

    scenes: list[HeroScene] = []
    for i in range(count):
        label, focus = seeds[i]
        ritual, direction = ritual_cycle[i % len(ritual_cycle)]
        motion = MOTIONS[i % len(MOTIONS)]
        brief = build_lyrics_scene_brief(
            deity=song.deity,
            mood=mood,
            lyrics=f"[{label}]\n{focus}\n\n{body[:500]}",
            title=song.title,
            visual_style=song.visual_style,
            style_prompt=song.style_prompt,
            notes=f"{getattr(song, 'notes', None) or ''}\nScene {i + 1}: {ritual}",
            has_style_ref=False,
        )
        prompt = (
            f"{brief} "
            f"HERO SCENE {i + 1}/{count}: «{ritual}». "
            f"Same deity character identity ({character_key}) as other scenes in this song — "
            f"consistent murti face, ornaments, skin tone, temple setting family. "
            f"Vary only the ritual action / camera angle / lighting beat."
        )[:2200]
        scenes.append(
            HeroScene(
                index=i + 1,
                label=label,
                lyric_focus=focus,
                ritual=ritual,
                ritual_direction=direction,
                character_key=character_key,
                motion=motion,
                prompt=prompt,
            )
        )
    return scenes


def _derive_local_variant(
    *,
    base: Path,
    out_path: Path,
    scene: HeroScene,
) -> Path:
    """Zero-cost crop/grade variant from a clean base still (text-free)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(base).convert("RGB")
    w, h = img.size
    # Crop windows cycle: center, left, right, slightly up, slightly down
    zooms = (1.0, 1.12, 1.08, 1.15, 1.1)
    zoom = zooms[(scene.index - 1) % len(zooms)]
    cw, ch = int(w / zoom), int(h / zoom)
    # horizontal bias
    biases = (0.5, 0.28, 0.72, 0.42, 0.58)
    bx = biases[(scene.index - 1) % len(biases)]
    by_opts = (0.48, 0.42, 0.55, 0.45, 0.5)
    by = by_opts[(scene.index - 1) % len(by_opts)]
    left = max(0, min(w - cw, int(bx * w - cw / 2)))
    top = max(0, min(h - ch, int(by * h - ch / 2)))
    crop = img.crop((left, top, left + cw, top + ch)).resize(
        (1920, 1080), Image.Resampling.LANCZOS
    )

    ritual = (scene.ritual or "").lower()
    # Soft grade by ritual / index
    if any(k in ritual for k in ("aarti", "deepam", "diya", "lamp")):
        crop = ImageEnhance.Color(crop).enhance(1.08)
        crop = ImageEnhance.Brightness(crop).enhance(1.05)
    elif any(k in ritual for k in ("abhishekam", "snana", "jala")):
        crop = ImageEnhance.Color(crop).enhance(0.92)
        crop = ImageEnhance.Brightness(crop).enhance(1.06)
    elif any(k in ritual for k in ("alankaram", "pushpa", "flower")):
        crop = ImageEnhance.Color(crop).enhance(1.12)
    else:
        shifts = (1.0, 1.05, 0.96, 1.08, 0.94)
        crop = ImageEnhance.Color(crop).enhance(shifts[(scene.index - 1) % len(shifts)])

    crop.save(out_path, format="JPEG", quality=92, optimize=True)
    return out_path


def _generate_scene_still(
    *,
    song: SongProject,
    scene: HeroScene,
    out_path: Path,
    character_ref: Path | None,
    fallback_still: Path | None,
    exhausted: ImageExhaustion,
) -> tuple[Path, str]:
    """Gemini → Kling → Cursor → local thumb variants. Returns (path, source_tag)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mood = infer_mood(
        lyrics=_latest_lyrics(song),
        style_prompt=song.style_prompt,
        deity=song.deity,
        daypart=None,
    )
    errors: list[str] = []

    if gemini_images.is_configured() and not exhausted.gemini:
        try:
            path = gemini_images.generate_rich_deity_scene(
                deity=song.deity,
                mood=mood,
                lyrics=_latest_lyrics(song),
                title=f"{song.title} — {scene.ritual}",
                visual_style=song.visual_style,
                style_prompt=scene.prompt,
                notes=getattr(song, "notes", None),
                out_path=out_path,
            )
            return path, "gemini"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"gemini:{exc}")
            exhausted.mark_from_error("gemini", exc)
            logger.warning("Scene %s Gemini still failed: %s", scene.index, exc)

    if kling_images.is_configured() and not exhausted.kling:
        try:
            path = kling_images.generate_rich_deity_scene(
                deity=song.deity,
                mood=mood,
                lyrics=_latest_lyrics(song),
                title=f"{song.title} — {scene.ritual}",
                visual_style=song.visual_style,
                style_prompt=scene.prompt,
                notes=getattr(song, "notes", None),
                out_path=out_path,
            )
            return path, "kling"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"kling:{exc}")
            exhausted.mark_from_error("kling", exc)
            logger.warning("Scene %s Kling still failed: %s", scene.index, exc)

    if cursor_images.is_configured() and not exhausted.cursor:
        try:
            path = cursor_images.generate_rich_deity_scene(
                deity=song.deity,
                mood=mood,
                lyrics=_latest_lyrics(song),
                title=f"{song.title} — {scene.ritual}",
                visual_style=song.visual_style,
                style_prompt=scene.prompt,
                notes=getattr(song, "notes", None),
                out_path=out_path,
            )
            return path, "cursor"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"cursor:{exc}")
            exhausted.mark_from_error("cursor", exc)
            logger.warning("Scene %s Cursor still failed: %s", scene.index, exc)

    # Final path: animate thumbnail / clean still (local crop/grade + Ken Burns)
    src = character_ref if character_ref and character_ref.exists() else fallback_still
    if src and src.exists():
        return _derive_local_variant(base=src, out_path=out_path, scene=scene), "local_variant"

    raise RuntimeError(
        f"Scene {scene.index} still failed — no clean thumbnail/deity still and APIs down "
        f"({'; '.join(errors) or 'no providers'}). "
        "Upload a deity image or generate a thumbnail while Gemini/Kling/Cursor still work."
    )


def _animate_scene_clip(
    *,
    still: Path,
    out_path: Path,
    motion: Motion,
    duration_sec: int,
    width: int,
    height: int,
    animate_mode: str,
) -> str:
    """Return engine tag. Prefer Ken Burns; optional Kling i2v."""
    mode = (animate_mode or "kenburns").strip().lower()
    if mode in {"kling", "kling_i2v", "auto"} and kling_video.is_configured():
        try:
            kling_video.generate_clip(
                prompt=(
                    "Sacred temple ritual motion from this first frame: "
                    "gentle aarti / lamp flicker / incense, classical murti stays consistent, "
                    "no text, no drama actor face"
                ),
                out_path=out_path,
                resolution="720p",
                aspect_ratio="16:9",
                duration_sec=min(10, max(5, int(duration_sec))),
                first_frame_path=still,
            )
            return "kling_i2v"
        except Exception as exc:  # noqa: BLE001
            if mode != "auto":
                logger.warning("Kling i2v failed (%s) — Ken Burns", exc)
            else:
                logger.info("Kling i2v skipped/failed (%s) — Ken Burns", exc)

    animate_still_to_clip(
        image_path=still,
        out_path=out_path,
        duration_sec=duration_sec,
        width=width,
        height=height,
        motion=motion,
    )
    return f"kenburns_{motion}"


def assemble_clips_with_transitions(
    clips: list[Path],
    *,
    out_path: Path,
    target_duration_sec: float,
    fade_sec: float = 0.75,
) -> Path:
    """Crossfade-assemble scene clips, looping the reel until target duration."""
    if not clips:
        raise RuntimeError("No scene clips to assemble")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fade = max(0.2, min(1.5, float(fade_sec)))

    # Build enough clips to cover target (+ small buffer)
    playlist: list[Path] = []
    total = 0.0
    i = 0
    while total < target_duration_sec + 2.0 and i < 200:
        c = clips[i % len(clips)]
        playlist.append(c)
        total += max(1.0, _ffprobe_duration(c) - (fade if i else 0.0))
        i += 1

    if len(playlist) == 1:
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(playlist[0]),
                "-t",
                f"{target_duration_sec:.2f}",
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
            timeout=600,
        )
        return out_path

    # filter_complex xfade chain
    cmd: list[str] = ["ffmpeg", "-y"]
    for p in playlist:
        cmd += ["-i", str(p)]

    parts: list[str] = []
    # Normalize each input
    for idx in range(len(playlist)):
        parts.append(
            f"[{idx}:v]fps=25,scale={MAIN_WIDTH}:{MAIN_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={MAIN_WIDTH}:{MAIN_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{idx}]"
        )

    durations = [_ffprobe_duration(p) for p in playlist]
    current = "v0"
    offset = durations[0]
    for idx in range(1, len(playlist)):
        nxt_label = f"x{idx}"
        # offset is start time of fade on the running timeline
        off = max(0.1, offset - fade)
        parts.append(
            f"[{current}][v{idx}]xfade=transition=fade:duration={fade:.2f}:offset={off:.2f}[{nxt_label}]"
        )
        current = nxt_label
        offset = off + durations[idx]

    parts.append(f"[{current}]trim=duration={target_duration_sec:.2f},setpts=PTS-STARTPTS[outv]")
    cmd += [
        "-filter_complex",
        ";".join(parts),
        "-map",
        "[outv]",
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
    ]
    _run_ffmpeg(cmd, timeout=900)
    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError("Scene assemble produced empty video")
    return out_path


def generate_scene_visual_and_shorts(
    db: Session,
    song: SongProject,
    *,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Hero stills → animate → FFmpeg assemble → Shorts from master."""
    settings = get_settings()
    count = max(6, min(18, int(getattr(settings, "video_scene_count", 12) or 12)))
    # 12–20s Ken Burns = slower sacred motion (native frames, not jerky time-stretch)
    clip_sec = max(8, min(20, int(getattr(settings, "video_scene_clip_sec", 15) or 15)))
    animate_mode = (getattr(settings, "video_scene_animate", None) or "kenburns").strip().lower()
    res = (settings.kling_video_resolution or "720p").strip().lower()
    if res not in {"720p", "1080p"}:
        res = "720p"
    w, h = (1280, 720) if res == "720p" else (1920, 1080)

    lyrics = _latest_lyrics(song)
    fallback = _still_image_for_song(song)
    audio_dur = _latest_audio_duration(song)
    exhausted = ImageExhaustion()
    any_image_api = (
        gemini_images.is_configured()
        or kling_images.is_configured()
        or cursor_images.is_configured()
    )
    if fallback is None and not any_image_api:
        raise RuntimeError(
            "No clean thumbnail/deity still and no image APIs configured. "
            "Upload a deity image or set GEMINI/KLING/CURSOR keys."
        )

    report(on_progress, 2, f"Planning {count} hero scenes (lyric rituals)…")
    scenes = plan_hero_scenes(song, count=count, lyrics=lyrics)
    song.visual_prompt = (
        f"[scene_orchestrator x{count}] " + " | ".join(f"{s.index}:{s.ritual}" for s in scenes)
    )[:2000]

    out_dir = Path(settings.media_root) / "visuals" / str(song.id) / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"

    character_ref: Path | None = None
    still_paths: list[Path] = []
    clip_paths: list[Path] = []
    engines: list[str] = []
    still_sources: list[str] = []

    for scene in scenes:
        pct = 4 + int(80 * (scene.index - 1) / max(count, 1))
        report(on_progress, pct, f"Scene {scene.index}/{count}: {scene.ritual}…")
        still_path = out_dir / f"scene_{scene.index:02d}_still.jpg"
        try:
            still, source_tag = _generate_scene_still(
                song=song,
                scene=scene,
                out_path=still_path,
                character_ref=character_ref,
                fallback_still=fallback,
                exhausted=exhausted,
            )
            still_sources.append(source_tag)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scene %s still hard-fail: %s", scene.index, exc)
            if not still_paths and not fallback:
                raise
            still = still_paths[-1] if still_paths else fallback  # type: ignore[assignment]
            assert still is not None
            still_sources.append("reuse_fail")

        if character_ref is None:
            character_ref = still
        still_paths.append(still)

        clip_path = out_dir / f"scene_{scene.index:02d}_{scene.motion}.mp4"
        engine = _animate_scene_clip(
            still=still,
            out_path=clip_path,
            motion=scene.motion,
            duration_sec=clip_sec,
            width=w,
            height=h,
            animate_mode=animate_mode,
        )
        clip_paths.append(clip_path)
        engines.append(engine)

    report(on_progress, 86, "Assembling scenes with fades to song length…")
    raw_path = out_dir.parent / f"raw_scenes_{uuid.uuid4().hex[:10]}.mp4"
    assemble_clips_with_transitions(
        clip_paths,
        out_path=raw_path,
        target_duration_sec=min(audio_dur, 480.0),
        fade_sec=0.8,
    )

    # Assembled reel already matches song length — keep it for long-form.
    # If short, soft-loop at native speed (no slow-mo), then Kling mark crop.
    report(on_progress, 90, "Preparing looped 16:9 main visual…")
    looped_main = out_dir.parent / f"main_16x9_{uuid.uuid4().hex[:10]}.mp4"
    assembled_dur = _ffprobe_duration(raw_path)
    main_min = float(getattr(settings, "video_main_min_sec", 45) or 45)
    if assembled_dur >= main_min - 0.5:
        from app.services_video import normalize_main_clip_16x9

        normalize_main_clip_16x9(raw_path, looped_main)
        main_dur = _ffprobe_duration(looped_main)
    else:
        from app.services_video import smooth_extend_main_visual

        _, main_dur = smooth_extend_main_visual(
            raw_path,
            looped_main,
            target_sec=main_min,
        )
    from app.services_video import crop_kling_watermark

    main_path = out_dir.parent / f"{looped_main.stem}_nowm.mp4"
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
    # Prefer a later hero still if/when Short 2 is re-enabled
    short2_still = (
        still_paths[min(1, len(still_paths) - 1)]
        if still_paths
        else (fallback if fallback and fallback.exists() else None)
    )
    cut_paths: list[dict] = []
    for short in shorts:
        method_hint = "video crop" if short.slot_index <= 1 else "Ken Burns still"
        report(
            on_progress,
            93 + short.slot_index * 3,
            f"Cutting Short {short.slot_index} (9:16, {method_hint})…",
        )
        out = out_dir.parent / f"short_{short.slot_index}_9x16_{uuid.uuid4().hex[:8]}.mp4"
        still_for_slot = short2_still if short.slot_index > 1 else None
        _, short_dur, short_meta = cut_short_clip(
            slot_index=short.slot_index,
            video_source=raw_path,
            out_path=out,
            still_image=still_for_slot,
            song=song,
            max_sec=SHORT_MAX_SEC,
        )
        short.clip_path = str(out)
        short.stage = "clip_ready"
        cut_paths.append(
            {
                "slot_index": short.slot_index,
                "path": str(out),
                "aspect_ratio": "9:16",
                "section": "pallavi",
                "crop": "center",
                "duration_sec": short_dur,
                "charanam_index": short.slot_index,
                "charanam_hook": (short.hook or "")[:120],
                **short_meta,
            }
        )

    manifest = {
        "pipeline": "scenes",
        "scene_count": count,
        "clip_sec": clip_sec,
        "audio_duration_sec": audio_dur,
        "animate_mode": animate_mode,
        "engines": engines,
        "still_sources": still_sources,
        "image_exhausted": {
            "gemini": exhausted.gemini,
            "kling": exhausted.kling,
            "cursor": exhausted.cursor,
        },
        "scenes": [asdict(s) for s in scenes],
        "still_paths": [str(p) for p in still_paths],
        "clip_paths": [str(p) for p in clip_paths],
        "raw_path": str(raw_path),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report(on_progress, 100, "Scene reel + Shorts ready")
    return {
        "video_clip_path": str(main_path),
        "resolution": res,
        "aspect_ratio": "16:9",
        "duration_sec": main_dur,
        "engine": "scene_orchestrator",
        "pipeline": "scenes",
        "scene_count": count,
        "raw_path": str(raw_path),
        "manifest_path": str(manifest_path),
        "shorts": cut_paths,
        "note": (
            f"{count} hero stills → animate ({animate_mode}) → FFmpeg fades "
            f"to ~{audio_dur:.0f}s; Shorts center-cropped from reel"
        ),
    }
