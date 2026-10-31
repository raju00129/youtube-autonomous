"""Song Studio — prepare lyrics for Suno, upload finished audio."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.publish import readiness as song_readiness
from app.core.config import get_settings
from app.db import get_db
from app.content_templates import fill_shorts_pair, sync_song_publish_copy
from app.lyrics_sections import extract_charanams
from app.models import LyricsVersion, MusicGeneration, ShortProject, SongProject
from app.providers import llm
from app.providers.cursor_llm import CursorLlmError
from app.providers.gemini_llm import GeminiLlmError
from app.providers.gemini_images import GeminiImageError
from app.providers.kling_images import KlingImageError
from app.providers.openai_llm import OpenAILlmError
from app.services_thumbnail import ensure_song_thumbnail, overlay_title_from_song
from app.style_prompt import default_style as _default_style
from app.style_prompt import enrich_style_prompt

router = APIRouter(prefix="/songs", tags=["songs"])

ALLOWED_AUDIO = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/aac",
    "audio/ogg",
    "application/octet-stream",
}


def _pipeline_payload(song: SongProject) -> dict:
    from app.services_pipeline import pipeline_status

    return pipeline_status(song)


def _short_audio_windows(song: SongProject, lyrics_body: str | None) -> dict[int, dict]:
    """Charanam mid-cut times for UI (Short N ← middle of Charanam N)."""
    from pathlib import Path

    from app.lyrics_sections import charanam_audio_window
    from app.services_video import SHORT_MAX_SEC, _ffprobe_duration

    music = song.music_generations[-1] if song.music_generations else None
    if not music or not music.file_path:
        return {}
    path = Path(music.file_path)
    if not path.exists():
        return {}
    try:
        dur = _ffprobe_duration(path)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[int, dict] = {}
    for s in getattr(song, "shorts", []) or []:
        a0, a1 = charanam_audio_window(
            lyrics_body,
            dur,
            charanam_index=int(s.slot_index),
            clip_sec=SHORT_MAX_SEC,
        )
        out[int(s.slot_index)] = {
            "audio_start_sec": a0,
            "audio_end_sec": a1,
            "charanam": int(s.slot_index),
        }
    return out


def _song_payload(song: SongProject) -> dict:
    # Always surface the latest version so Regenerate updates the studio UI
    # (approved-only preference hid new drafts after regenerate).
    latest = song.lyrics_versions[-1] if song.lyrics_versions else None
    approved = next((l for l in reversed(song.lyrics_versions) if l.approved), None)
    lyrics = latest
    music = song.music_generations[-1] if song.music_generations else None
    shorts = list(getattr(song, "shorts", []) or [])
    audio_windows = _short_audio_windows(song, lyrics.body if lyrics else None)
    return {
        "id": str(song.id),
        "title": song.title,
        "deity": song.deity,
        "language": song.language,
        "music_genre": song.music_genre,
        "vocal_preference": song.vocal_preference,
        "style_prompt": song.style_prompt,
        "visual_style": getattr(song, "visual_style", None),
        "stage": song.stage,
        "notes": song.notes,
        "publish_at": song.publish_at.isoformat() if getattr(song, "publish_at", None) else None,
        "youtube_title": getattr(song, "youtube_title", None),
        "youtube_description": getattr(song, "youtube_description", None),
        "youtube_tags": getattr(song, "youtube_tags", None),
        "youtube_video_id": getattr(song, "youtube_video_id", None),
        "youtube_url": getattr(song, "youtube_url", None),
        "youtube_playlist_id": getattr(song, "youtube_playlist_id", None),
        "youtube_playlist_title": getattr(song, "youtube_playlist_title", None),
        "shorts_playlist_id": getattr(song, "shorts_playlist_id", None),
        "shorts_playlist_title": getattr(song, "shorts_playlist_title", None),
        "created_at": song.created_at.isoformat() if song.created_at else None,
        "updated_at": song.updated_at.isoformat() if song.updated_at else None,
        "lyrics_approved": bool(approved),
        "lyrics": (
            {
                "id": str(lyrics.id),
                "version": lyrics.version,
                "body": lyrics.body,
                "approved": lyrics.approved,
            }
            if lyrics
            else None
        ),
        "music": (
            {
                "id": str(music.id),
                "provider": music.provider,
                "status": music.status,
                "original_filename": music.original_filename,
                "approved": music.approved,
                "download_path": f"/api/v1/songs/{song.id}/music/{music.id}/file",
            }
            if music
            else None
        ),
        "shorts": [
            {
                "id": str(s.id),
                "slot_index": s.slot_index,
                "title": s.title,
                "hook": s.hook,
                "description": s.description,
                "stage": s.stage,
                "clip_path": getattr(s, "clip_path", None),
                "clip_url": (
                    f"/api/v1/songs/{song.id}/shorts/{s.slot_index}/clip"
                    if getattr(s, "clip_path", None)
                    else None
                ),
                "final_clip_path": getattr(s, "final_clip_path", None),
                "final_url": (
                    f"/api/v1/songs/{song.id}/shorts/{s.slot_index}/final"
                    if getattr(s, "final_clip_path", None)
                    else None
                ),
                "youtube_video_id": getattr(s, "youtube_video_id", None),
                "youtube_url": getattr(s, "youtube_url", None),
                "audio_start_sec": (audio_windows.get(int(s.slot_index)) or {}).get(
                    "audio_start_sec"
                ),
                "audio_end_sec": (audio_windows.get(int(s.slot_index)) or {}).get(
                    "audio_end_sec"
                ),
                "publish_at": s.publish_at.isoformat() if s.publish_at else None,
            }
            for s in shorts
        ],
        "visual": {
            "prompt": getattr(song, "visual_prompt", None),
            "clip_path": getattr(song, "video_clip_path", None),
            "clip_url": (
                f"/api/v1/songs/{song.id}/visuals/clip"
                if getattr(song, "video_clip_path", None)
                else None
            ),
            "resolution": "720p",
            "shorts_from_same_clip": True,
        },
        "final": {
            "path": getattr(song, "final_video_path", None),
            "url": (
                f"/api/v1/songs/{song.id}/final"
                if getattr(song, "final_video_path", None)
                else None
            ),
            "ready": bool(getattr(song, "final_video_path", None)),
        },
        "thumbnail": {
            "requires_channel_logo": True,
            "requires_deity_image": True,
            "title_overlay": True,
            "path": getattr(song, "thumbnail_path", None),
        },
        "readiness": song_readiness(song),
        "pipeline": _pipeline_payload(song),
    }


def _load_song(db: Session, song_id: uuid.UUID) -> SongProject:
    song = db.scalar(
        select(SongProject)
        .where(SongProject.id == song_id)
        .options(
            selectinload(SongProject.lyrics_versions),
            selectinload(SongProject.music_generations),
            selectinload(SongProject.shorts),
        )
    )
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


class SongCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    deity: str | None = Field(default=None, max_length=120)
    language: str = Field(default="te", max_length=40)
    music_genre: str | None = Field(default="Telugu devotional / light Carnatic", max_length=200)
    vocal_preference: str | None = Field(default="m", max_length=40)
    style_prompt: str | None = None
    lyrics: str | None = Field(default=None, max_length=20000)
    notes: str | None = None


class SongUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    deity: str | None = None
    music_genre: str | None = None
    vocal_preference: str | None = None
    style_prompt: str | None = None
    notes: str | None = None
    publish_at: datetime | None = None


class LyricsUpsert(BaseModel):
    body: str = Field(..., min_length=1, max_length=20000)
    approve: bool = False


class AgentGenerateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    deity: str | None = Field(default=None, max_length=120)
    topic: str | None = Field(default=None, max_length=2000)
    vocal_preference: str | None = Field(default="m", max_length=40)
    music_genre: str | None = Field(default="Telugu devotional / light Carnatic", max_length=200)
    language: str = Field(default="te", max_length=40)
    approve: bool = False


@router.post("/generate")
def generate_song_with_agent(body: AgentGenerateRequest, db: Session = Depends(get_db)) -> dict:
    """OpenAI (or Cursor composer fallback) writes Telugu lyrics + style, then creates the song."""
    if not llm.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Set GEMINI_API_KEY for lyrics (or CURSOR_API_KEY / OPENAI_API_KEY fallback)",
        )
    try:
        generated = llm.generate_lyrics(
            title=body.title,
            deity=body.deity,
            topic=body.topic,
            vocal=body.vocal_preference,
            language=body.language,
            music_genre=body.music_genre,
        )
    except (GeminiLlmError, OpenAILlmError, CursorLlmError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    style = enrich_style_prompt(
        (generated.get("style_prompt") or "").strip()
        or _default_style(body.deity, body.music_genre, body.vocal_preference),
        vocal=body.vocal_preference,
    )
    lyrics_body = str(generated["lyrics"]).strip()
    gemini_title = (body.title or generated.get("title") or "Untitled Devotional").strip()

    song = SongProject(
        title=gemini_title[:200],
        deity=body.deity,
        language=body.language,
        music_genre=body.music_genre,
        vocal_preference=body.vocal_preference,
        style_prompt=style,
        stage="awaiting_audio" if body.approve else "lyrics_draft",
        notes=body.topic,
    )
    db.add(song)
    db.flush()
    db.add(
        LyricsVersion(
            song_id=song.id,
            version=1,
            body=lyrics_body,
            approved=body.approve,
        )
    )
    db.flush()
    # Always build premium YouTube package + Shorts copy from this lyrics
    sync_song_publish_copy(
        song,
        lyrics=lyrics_body,
        gemini_title=str(generated.get("title") or gemini_title),
        topic=body.topic,
        refresh_shorts=False,
    )
    for short_def in fill_shorts_pair(
        title=song.title,
        deity=song.deity,
        youtube_title=song.youtube_title,
        youtube_description=song.youtube_description,
        charanams=extract_charanams(lyrics_body, limit=2),
    ):
        db.add(
            ShortProject(
                song_id=song.id,
                slot_index=short_def["slot_index"],
                title=short_def["title"],
                hook=short_def["hook"],
                description=short_def["description"],
                stage="planned",
            )
        )
    db.flush()
    ensure_song_thumbnail(db, song)
    db.commit()
    return {"data": _song_payload(_load_song(db, song.id))}


@router.post("/{song_id}/lyrics/generate")
def regenerate_lyrics_with_agent(
    song_id: uuid.UUID,
    body: AgentGenerateRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Re-run OpenAI (Cursor composer fallback) and append a new lyrics version."""
    song = _load_song(db, song_id)
    if not llm.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Set GEMINI_API_KEY for lyrics (or CURSOR_API_KEY / OPENAI_API_KEY fallback)",
        )

    previous = song.lyrics_versions[-1].body if song.lyrics_versions else None
    previous_style = song.style_prompt
    try:
        generated = llm.generate_lyrics(
            title=body.title or song.title,
            deity=body.deity or song.deity,
            topic=body.topic or song.notes,
            vocal=body.vocal_preference or song.vocal_preference,
            language=body.language or song.language,
            music_genre=body.music_genre or song.music_genre,
            regenerate=True,
            previous_lyrics=previous,
            previous_style=previous_style,
        )
    except (GeminiLlmError, OpenAILlmError, CursorLlmError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    vocal = body.vocal_preference or song.vocal_preference
    new_style = str(generated.get("style_prompt") or "").strip()
    song.style_prompt = enrich_style_prompt(
        new_style
        or _default_style(
            body.deity or song.deity,
            body.music_genre or song.music_genre,
            vocal,
        ),
        vocal=vocal,
    )
    lyrics_body = str(generated["lyrics"]).strip()
    next_version = (song.lyrics_versions[-1].version + 1) if song.lyrics_versions else 1
    # New draft replaces prior approval until user re-approves
    for lv in song.lyrics_versions:
        lv.approved = False
    db.add(
        LyricsVersion(
            song_id=song.id,
            version=next_version,
            body=lyrics_body,
            approved=body.approve,
        )
    )
    song.stage = "awaiting_audio" if body.approve else "lyrics_draft"
    db.flush()
    # ALWAYS refresh title + YouTube package + Shorts from latest lyrics
    sync_song_publish_copy(
        song,
        lyrics=lyrics_body,
        gemini_title=str(generated.get("title") or body.title or song.title),
        topic=body.topic or song.notes,
        refresh_shorts=True,
    )
    # Fast local thumb only — AI rebuild is a separate button (avoids hanging regenerate)
    try:
        ensure_song_thumbnail(db, song, use_ai=False)
    except Exception:  # noqa: BLE001 — lyrics success matters more than thumb
        pass
    db.commit()
    return {"data": _song_payload(_load_song(db, song_id))}


@router.get("")
def list_songs(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(SongProject)
        .options(
            selectinload(SongProject.lyrics_versions),
            selectinload(SongProject.music_generations),
            selectinload(SongProject.shorts),
        )
        .order_by(SongProject.updated_at.desc())
    ).all()
    return {"data": [_song_payload(s) for s in rows]}


@router.post("")
def create_song(body: SongCreate, db: Session = Depends(get_db)) -> dict:
    style = body.style_prompt or _default_style(body.deity, body.music_genre, body.vocal_preference)
    song = SongProject(
        title=body.title.strip(),
        deity=body.deity,
        language=body.language,
        music_genre=body.music_genre,
        vocal_preference=body.vocal_preference,
        style_prompt=style,
        notes=body.notes,
        stage="lyrics_draft",
    )
    db.add(song)
    db.flush()
    if body.lyrics and body.lyrics.strip():
        db.add(
            LyricsVersion(
                song_id=song.id,
                version=1,
                body=body.lyrics.strip(),
                approved=False,
            )
        )
    db.commit()
    return {"data": _song_payload(_load_song(db, song.id))}


@router.get("/{song_id}")
def get_song(song_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return {"data": _song_payload(_load_song(db, song_id))}


@router.patch("/{song_id}")
def update_song(song_id: uuid.UUID, body: SongUpdate, db: Session = Depends(get_db)) -> dict:
    song = _load_song(db, song_id)
    data = body.model_dump(exclude_unset=True)
    publish_at = data.pop("publish_at", None)
    if "style_prompt" in data and data["style_prompt"] is not None:
        data["style_prompt"] = enrich_style_prompt(
            data["style_prompt"],
            vocal=data.get("vocal_preference") or song.vocal_preference,
        )
    for field, value in data.items():
        setattr(song, field, value)
    if "publish_at" in body.model_fields_set:
        song.publish_at = publish_at
        if publish_at is not None:
            for short in song.shorts:
                short.publish_at = publish_at
            if song.stage in {"music_ready", "lyrics_draft", "awaiting_audio"}:
                song.stage = "ready_to_publish"
    db.commit()
    return {"data": _song_payload(_load_song(db, song_id))}


@router.put("/{song_id}/lyrics")
def upsert_lyrics(song_id: uuid.UUID, body: LyricsUpsert, db: Session = Depends(get_db)) -> dict:
    song = _load_song(db, song_id)
    next_version = (song.lyrics_versions[-1].version + 1) if song.lyrics_versions else 1
    # New version; clear prior approvals if rewriting after approve
    if body.approve:
        for lv in song.lyrics_versions:
            lv.approved = False
    lyrics = LyricsVersion(
        song_id=song.id,
        version=next_version,
        body=body.body.strip(),
        approved=body.approve,
    )
    db.add(lyrics)
    song.stage = "awaiting_audio" if body.approve else "lyrics_draft"
    if body.approve and not song.style_prompt:
        song.style_prompt = _default_style(song.deity, song.music_genre, song.vocal_preference)
    db.flush()
    sync_song_publish_copy(song, lyrics=body.body.strip(), gemini_title=song.title, refresh_shorts=True)
    ensure_song_thumbnail(db, song)
    db.commit()
    return {"data": _song_payload(_load_song(db, song_id))}


@router.post("/{song_id}/lyrics/approve")
def approve_lyrics(song_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    song = _load_song(db, song_id)
    if not song.lyrics_versions:
        raise HTTPException(status_code=400, detail="No lyrics to approve")
    for lv in song.lyrics_versions:
        lv.approved = False
    song.lyrics_versions[-1].approved = True
    song.stage = "awaiting_audio"
    if not song.style_prompt:
        song.style_prompt = _default_style(song.deity, song.music_genre, song.vocal_preference)
    db.flush()
    lyrics = song.lyrics_versions[-1].body
    sync_song_publish_copy(song, lyrics=lyrics, gemini_title=song.title, refresh_shorts=True)
    ensure_song_thumbnail(db, song)
    db.commit()
    return {"data": _song_payload(_load_song(db, song_id))}


@router.get("/{song_id}/suno-pack")
def suno_pack(song_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Copy-ready title, style, and lyrics for pasting into the Suno app."""
    song = _load_song(db, song_id)
    approved = next((l for l in reversed(song.lyrics_versions) if l.approved), None)
    lyrics = approved or (song.lyrics_versions[-1] if song.lyrics_versions else None)
    if not lyrics:
        raise HTTPException(status_code=400, detail="Add lyrics first")
    style = enrich_style_prompt(
        song.style_prompt or _default_style(song.deity, song.music_genre, song.vocal_preference),
        vocal=song.vocal_preference,
    )
    body = lyrics.body
    pack_text = (
        f"TITLE:\n{song.title}\n\n"
        f"STYLE:\n{style}\n\n"
        f"LYRICS:\n{body}\n"
    )
    return {
        "data": {
            "song_id": str(song.id),
            "title": song.title,
            "style": style,
            "lyrics": body,
            "lyrics_approved": bool(approved),
            "copy_all": pack_text,
            "instructions": [
                "Open suno.com (your Pro account)",
                "Use Custom / Lyrics mode",
                "Paste the STYLE field exactly (includes Telugu pronunciation tags)",
                "Paste LYRICS (Telugu script) into the lyrics field — do not transliterate",
                "Set title to match",
                "Generate; if diction sounds off, regenerate once with the same style",
                "Download MP3 and upload here",
            ],
        }
    }


@router.post("/{song_id}/music/upload")
async def upload_music(
    song_id: uuid.UUID,
    file: UploadFile = File(...),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict:
    song = _load_song(db, song_id)
    approved = any(l.approved for l in song.lyrics_versions)
    if not approved and song.lyrics_versions:
        # Allow upload even if not formally approved, but prefer approve flow
        pass
    if not song.lyrics_versions:
        raise HTTPException(status_code=400, detail="Add lyrics before uploading music")

    content_type = (file.content_type or "application/octet-stream").lower()
    name = file.filename or "upload.mp3"
    suffix = Path(name).suffix.lower() or ".mp3"
    if content_type not in ALLOWED_AUDIO and suffix not in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
        raise HTTPException(status_code=400, detail=f"Unsupported audio type: {content_type}")

    settings = get_settings()
    dest_dir = Path(settings.media_root) / "music" / str(song.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(name).stem)[:80] or "track"
    dest = dest_dir / f"{uuid.uuid4().hex}_{safe}{suffix}"

    data = await file.read()
    max_bytes = settings.max_upload_bytes
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    dest.write_bytes(data)

    music = MusicGeneration(
        song_id=song.id,
        provider="manual_suno_upload",
        status="uploaded",
        file_path=str(dest),
        original_filename=name,
        mime_type=content_type,
        approved=True,
        notes=notes,
    )
    db.add(music)
    song.stage = "music_ready"
    db.commit()
    return {"data": _song_payload(_load_song(db, song_id))}


@router.get("/{song_id}/music/{music_id}/file")
def download_music(
    song_id: uuid.UUID,
    music_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    song = _load_song(db, song_id)
    music = next((m for m in song.music_generations if m.id == music_id), None)
    if not music or not music.file_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    path = Path(music.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")
    return FileResponse(
        path,
        media_type=music.mime_type or "audio/mpeg",
        filename=music.original_filename or path.name,
    )


@router.post("/{song_id}/deity-image")
async def upload_deity_image(
    song_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Optional deity / temple still used as thumbnail background (local compose, $0 AI)."""
    song = _load_song(db, song_id)
    name = file.filename or "deity.jpg"
    suffix = Path(name).suffix.lower() or ".jpg"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Use png/jpg/webp for deity image")
    settings = get_settings()
    dest_dir = Path(settings.media_root) / "thumbnails" / str(song.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"deity_{uuid.uuid4().hex[:8]}{suffix}"
    data = await file.read()
    if len(data) > 12_000_000:
        raise HTTPException(status_code=413, detail="Image too large")
    dest.write_bytes(data)
    song.deity_image_path = str(dest)
    db.commit()
    return {"data": _song_payload(_load_song(db, song_id))}


@router.post("/{song_id}/thumbnail/upload")
async def upload_thumbnail(
    song_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Upload a finished YouTube thumbnail (e.g. from ChatGPT) — used as-is for publish."""
    from PIL import Image
    import io

    song = _load_song(db, song_id)
    name = file.filename or "thumbnail.jpg"
    suffix = Path(name).suffix.lower() or ".jpg"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Use png/jpg/webp for thumbnail")
    data = await file.read()
    if len(data) > 20_000_000:
        raise HTTPException(status_code=413, detail="Image too large (max 20MB)")
    if len(data) < 1000:
        raise HTTPException(status_code=400, detail="File looks empty")

    settings = get_settings()
    dest_dir = Path(settings.media_root) / "thumbnails" / str(song.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"thumb_manual_{uuid.uuid4().hex[:10]}.jpg"
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        # Keep native aspect; only nudge toward 16:9 cover if wildly off
        w, h = img.size
        if w < 640 or h < 360:
            raise HTTPException(status_code=400, detail="Thumbnail too small (min ~640×360)")
        # Deliver sharp 1920×1080 cover for YouTube
        tw, th = 1920, 1080
        scale = max(tw / w, th / h)
        nw, nh = int(w * scale), int(h * scale)
        resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
        left, top = (nw - tw) // 2, (nh - th) // 2
        resized = resized.crop((left, top, left + tw, top + th))
        resized.save(dest, format="JPEG", quality=95, optimize=True, subsampling=0)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not read image: {exc}") from exc

    song.thumbnail_path = str(dest)
    db.commit()
    song = _load_song(db, song_id)
    return {
        "data": {
            "song_id": str(song.id),
            "thumbnail_path": song.thumbnail_path,
            "thumbnail_url": f"/api/v1/songs/{song.id}/thumbnail",
            "engine": "manual_upload",
            "note": "Manual thumbnail uploaded — will be used for YouTube publish as-is.",
            "song": _song_payload(song),
        }
    }


@router.post("/{song_id}/thumbnail/generate")
def generate_thumbnail(song_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Force a NEW Kling premium thumb using the latest lyrics title + refreshed YouTube copy."""
    song = _load_song(db, song_id)
    lyrics = song.lyrics_versions[-1].body if song.lyrics_versions else None
    # Re-sync YouTube package from latest lyrics before painting the title into the thumb
    meta = sync_song_publish_copy(
        song,
        lyrics=lyrics,
        gemini_title=song.title,
        refresh_shorts=True,
    )
    try:
        result = ensure_song_thumbnail(db, song, use_ai=True, force_ai=True)
    except (KlingImageError, GeminiImageError) as exc:
        raise HTTPException(status_code=502, detail=f"AI thumbnail failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Thumbnail compose failed: {exc}") from exc
    if not result:
        raise HTTPException(status_code=400, detail="Add lyrics or title before thumbnail")
    _out, engine = result
    db.commit()
    song = _load_song(db, song_id)
    thumb_title = overlay_title_from_song(song, lyrics)
    note = {
        "gemini_premium": (
            f"Gemini ultra-premium scene + 3D Telugu «{thumb_title}» + logo "
            "(ChatGPT-class still; Telugu stamped locally)."
        ),
        "kling_v3_omni_4k": (
            f"Kling Omni 4K fallback scene + Telugu «{thumb_title}» + logo."
        ),
        "ai_scene_cached": f"Cached AI scene + Telugu «{thumb_title}».",
        "user_upload": "Your uploaded deity still + local Telugu overlay.",
        "local_pillow": "Local procedural scene + Telugu overlay (AI unavailable).",
    }.get(engine, "Thumbnail composed.")
    return {
        "data": {
            "song_id": str(song.id),
            "thumbnail_path": song.thumbnail_path,
            "thumbnail_url": f"/api/v1/songs/{song.id}/thumbnail",
            "engine": engine,
            "overlay_title": thumb_title,
            "youtube_title": song.youtube_title or meta.get("youtube_title"),
            "note": note,
            "song": _song_payload(song),
        }
    }


@router.get("/{song_id}/thumbnail")
def get_thumbnail(song_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    song = _load_song(db, song_id)
    if not song.thumbnail_path:
        raise HTTPException(status_code=404, detail="No thumbnail yet — generate first")
    path = Path(song.thumbnail_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)
