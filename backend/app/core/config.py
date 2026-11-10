from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    app_secret_key: str = "dev-secret"
    token_encryption_key: str = "dev-token-key"
    cors_origins: str = "http://localhost:5173"
    # Simple studio gate — required on every portal visit / API call
    portal_access_key: str = "0214"

    database_url: str = "postgresql+psycopg://ragam:ragam@localhost:5432/ragam"
    redis_url: str = "redis://localhost:6379/0"

    media_root: str = "/app/storage"
    max_upload_bytes: int = 838_860_800  # 800MB — long Kling masters

    # LLM — Gemini for lyrics (text); Kling for image + video
    llm_provider: str = "gemini"  # gemini | cursor | openai | auto
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_llm_model: str = "gpt-4o-mini"
    openai_image_model: str = "dall-e-3"
    openai_image_enabled: bool = False

    gemini_api_key: str = ""
    gemini_llm_model: str = "gemini-3.8-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"
    gemini_image_timeout_sec: int = 180
    # Thumbnails / stills ladder starts here: gemini | kling | cursor
    thumbnail_image_provider: str = "gemini"
    gemini_video_model: str = "gemini-omni-1.1-flash"
    gemini_video_duration: int = 10
    gemini_video_resolution: str = "720p"
    gemini_video_aspect_ratio: str = "16:9"
    # Video: auto = Gemini first, Kling on quota/fail; gemini | kling force one
    video_provider: str = "auto"
    # scenes = hero stills → animate → FFmpeg assemble (cost-efficient)
    # singleshot = one AI video clip (legacy)
    video_pipeline: str = "scenes"
    video_scene_count: int = 12
    # Longer Ken Burns = slower sacred motion (avoid jerky time-stretch)
    video_scene_clip_sec: int = 15
    # kenburns (default, $0) | auto (try Kling i2v then Ken Burns) | kling_i2v
    video_scene_animate: str = "kenburns"
    # Long-form silent visual target before audio mux (smooth extend, not hard 10s loop)
    video_main_min_sec: float = 45.0
    # Mix: volume-only bump for quiet Suno/uploads (never changes tempo/pitch)
    audio_target_mean_db: float = -12.0
    audio_quiet_below_db: float = -16.0
    audio_max_boost_db: float = 10.0
    # Auto pipeline: start video+mix this many minutes before publish_at
    prep_lead_minutes: int = 60
    # Allow late prep up to this many minutes after publish_at if mix missing
    prep_grace_minutes: int = 15
    # Short 1 with main video; Short 2+ stagger this many hours later on YouTube
    short_stagger_hours: int = 5
    # How many Shorts to cut per song (1 for now — Short 2 paused)
    shorts_count: int = 1

    cursor_api_key: str = ""
    cursor_llm_model: str = "composer-2.5"
    cursor_image_model: str = "composer-2.5"
    lyrics_agent_url: str = "http://lyrics-agent:8020"
    lyrics_agent_timeout_sec: int = 180
    cursor_image_timeout_sec: int = 300

    # Music — official Mureka API (platform.mureka.ai)
    mureka_api_key: str = ""
    mureka_base_url: str = "https://api.mureka.ai"
    mureka_model: str = "auto"

    # Optional backups (not primary)
    wavespeed_api_key: str = ""
    wavespeed_base_url: str = "https://api.wavespeed.ai"
    wavespeed_music_model: str = "wavespeed-ai/ace-step-1.5"
    wavespeed_music_duration: int = 120
    sunoapi_api_key: str = ""
    sunoapi_base_url: str = "https://api.sunoapi.org"
    sunoapi_model: str = "V6"
    sunoapi_callback_url: str = "https://httpbin.org/post"

    # Kling — thumbnails + video (paid subscription)
    kling_api_key: str = ""
    kling_base_url: str = "https://api-singapore.klingai.com"
    # Rich thumbs: Image 3.0 Omni @ 4K (16 units) — multi-ref Telugu plate
    kling_image_model: str = "kling-v3-omni"
    kling_image_resolution: str = "4k"
    kling_image_timeout_sec: int = 240
    # Video: Kling 2.5 Turbo @ 720p silent (0.3 units/s) — mux Suno later
    # Omni stays for images; Kling native audio stays off
    kling_video_model: str = "kling-4.0"  # Flagship Trial: 4.0 / 4.0 Flash only
    kling_video_duration: int = 10
    kling_video_resolution: str = "720p"
    kling_video_aspect_ratio: str = "16:9"
    kling_video_timeout_sec: int = 600
    kling_video_audio: str = "off"  # never buy native audio; mux Suno later

    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8010/api/v1/youtube/callback"
    google_project_id: str = ""
    youtube_channel_id: str = ""
    youtube_channel_handle: str = ""
    youtube_channel_url: str = ""

    n8n_webhook_secret: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def provider_readiness(self) -> dict[str, bool]:
        """Active stack only — unused OpenAI keys are not shown as missing."""
        gemini_ok = bool(self.gemini_api_key.strip())
        kling_ok = bool(self.kling_api_key.strip())
        return {
            "gemini_lyrics": gemini_ok,
            "gemini_images": gemini_ok,
            "kling_thumbnails": kling_ok,
            "cursor_images": bool(self.cursor_api_key.strip()),
            "suno_manual_upload": True,
            "mureka_music": bool(self.mureka_api_key.strip()),
            "kling_video_720p": kling_ok,
            "gemini_video": gemini_ok,
            "youtube_oauth": bool(
                self.google_client_id.strip() and self.google_client_secret.strip()
            ),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
