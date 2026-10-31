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
                "via": "gemini_then_kling_no_audio",
                "prep_lead_minutes": settings.prep_lead_minutes,
                "cost_hint": (
                    "VIDEO_PROVIDER=auto: Gemini first, Kling 4.0 on quota/fail; "
                    f"auto prep {settings.prep_lead_minutes}m before publish_at"
                ),
                "shorts": (
                    "ffmpeg 9:16 CENTER crop from same 16:9 clip; "
                    "loop each Short <30s; Charanam 1→Short1, Charanam 2→Short2"
                ),
            },
            "youtube": {
                "connected": yt_status.get("connected"),
                "configured_channel": yt_status.get("configured_channel"),
            },
            "notes": {
                "llm": f"Gemini lyrics ({settings.gemini_llm_model}) — LLM_PROVIDER={settings.llm_provider}",
                "thumbnails": (
                    f"Primary: Gemini Image ({settings.gemini_image_model}) ultra-premium still "
                    f"(provider={settings.thumbnail_image_provider}); "
                    "Kling Omni fallback; 3D Telugu + logo stamped locally "
                    "(AI cannot paint real Telugu)"
                ),
                "music": "Primary: manual Suno Pro upload. Optional Mureka API if configured.",
                "video": (
                    f"VIDEO_PROVIDER={settings.video_provider}: Gemini "
                    f"({settings.gemini_video_model}) → Kling ({settings.kling_video_model}) @ "
                    f"{settings.kling_video_resolution}, audio=off; "
                    f"auto video+mix {settings.prep_lead_minutes}m before publish_at; "
                    "auto YouTube at publish_at (Publish now still works)"
                ),
                "youtube": "Connected when OAuth token present",
            },
        }
    }
