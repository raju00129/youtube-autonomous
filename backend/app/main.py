from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db import check_database
from app.schema_migrate import ensure_schema

settings = get_settings()

app = FastAPI(
    title="Ragam Spiritual API",
    version="0.1.0",
    description="Autonomous Telugu devotional YouTube production platform",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
def ensure_media_dirs() -> None:
    root = Path(settings.media_root)
    for sub in ("temp", "logs", "cache", "music", "branding", "thumbnails", "visuals"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    ensure_schema()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    db_ok = check_database()
    redis_ok = False
    try:
        client = redis.from_url(settings.redis_url)
        redis_ok = client.ping() is True
    except Exception:
        redis_ok = False

    status = "ready" if db_ok and redis_ok else "degraded"
    return {
        "status": status,
        "database": db_ok,
        "redis": redis_ok,
        "providers": settings.provider_readiness,
    }
