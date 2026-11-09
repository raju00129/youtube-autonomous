from fastapi import APIRouter

from app.api.v1 import (
    branding,
    denoise,
    health,
    jobs,
    music,
    playlists_api,
    portal,
    publish,
    schedule,
    songs,
    system,
    visuals,
    youtube,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(portal.router)
api_router.include_router(system.router, tags=["system"])
api_router.include_router(jobs.router, tags=["jobs"])
api_router.include_router(music.router)
api_router.include_router(songs.router)
api_router.include_router(visuals.router)
api_router.include_router(schedule.router)
api_router.include_router(publish.router)
api_router.include_router(branding.router)
api_router.include_router(playlists_api.router)
api_router.include_router(youtube.router, tags=["youtube"])
api_router.include_router(denoise.router)
