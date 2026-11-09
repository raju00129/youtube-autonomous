from fastapi import APIRouter

from app.core.config import get_settings
from app.providers import youtube as yt

router = APIRouter(prefix="/system")


@router.get("/providers")
def provider_status() -> dict:
    settings = get_settings()
    yt_status = yt.connection_status()
    return {
        "data": {
            "readiness": settings.provider_readiness,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.gemini_llm_model
            if settings.llm_provider in {"gemini", "auto"}
            else settings.cursor_llm_model,
            "image_model": settings.kling_image_model,
            "music_provider": "suno_manual_upload",
            "music_model": "manual",
            "music_optional_api": {
                "provider": "mureka",
                "model": settings.mureka_model,
                "configured": bool(settings.mureka_api_key.strip()),
            },
            "video_model": settings.kling_video_model,
            "video_provider": settings.video_provider,
            "video_defaults": {
                "duration": settings.kling_video_duration,
                "resolution": settings.kling_video_resolution,
                "aspect_ratio": settings.kling_video_aspect_ratio,
                "audio": settings.kling_video_audio or "off",
                "via": "scenes_stills_animate_ffmpeg",
                "pipeline": getattr(settings, "video_pipeline", "scenes"),
                "scene_count": getattr(settings, "video_scene_count", 12),
                "scene_clip_sec": getattr(settings, "video_scene_clip_sec", 8),
                "scene_animate": getattr(settings, "video_scene_animate", "kenburns"),
                "prep_lead_minutes": settings.prep_lead_minutes,
                "stills_ladder": "gemini→kling→cursor→thumb_kenburns",
                "cost_hint": (
                    "VIDEO_PIPELINE=scenes: 10–15 hero stills → Ken Burns/i2v → "
                    "FFmpeg fades (not dozens of AI videos); "
                    "stills Gemini→Kling→Cursor→thumbnail Ken Burns; "
                    "singleshot fallback Gemini→Kling→Ken Burns; "
                    f"auto prep {settings.prep_lead_minutes}m before publish_at"
                ),
                "shorts": (
                    f"SHORTS_COUNT={getattr(settings, 'shorts_count', 1)} — "
                    "currently one Short (9:16 crop from main video); "
                    "Short 2 paused for later"
                ),
                "shorts_count": getattr(settings, "shorts_count", 1),
            },
            "youtube": {
                "connected": yt_status.get("connected"),
                "configured_channel": yt_status.get("configured_channel"),
            },
            "notes": {
                "llm": f"Gemini lyrics ({settings.gemini_llm_model}) — LLM_PROVIDER={settings.llm_provider}",
                "thumbnails": (
                    f"Ladder: Gemini ({settings.gemini_image_model}) → Kling Omni → Cursor GenerateImage "
                    f"(provider hint={settings.thumbnail_image_provider}); "
                    "3D Telugu + logo stamped locally (AI cannot paint real Telugu)"
                ),
                "music": "Primary: manual Suno Pro upload. Optional Mureka API if configured.",
                "video": (
                    f"VIDEO_PIPELINE={getattr(settings, 'video_pipeline', 'scenes')}: "
                    f"{getattr(settings, 'video_scene_count', 12)} hero stills "
                    "(Gemini→Kling→Cursor→thumbnail Ken Burns) → "
                    f"animate={getattr(settings, 'video_scene_animate', 'kenburns')} → "
                    "FFmpeg transitions + music mux; "
                    f"fallback singleshot VIDEO_PROVIDER={settings.video_provider} "
                    f"(Gemini→Kling→Ken Burns) @ {settings.kling_video_resolution}; "
                    f"auto prep {settings.prep_lead_minutes}m before publish_at"
                ),
                "youtube": "Connected when OAuth token present",
            },
        }
    }
