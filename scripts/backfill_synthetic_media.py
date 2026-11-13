"""Flag every published Ragam video/Short as altered/synthetic (AI) content on YouTube.

Run inside the backend container:
    docker compose exec -T backend python - < scripts/backfill_synthetic_media.py
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import SongProject
from app.providers.youtube import YouTubeUploadError, set_synthetic_media_flag


def main() -> None:
    db = SessionLocal()
    try:
        ids: list[str] = []
        for song in db.scalars(
            select(SongProject)
            .options(selectinload(SongProject.shorts))
            .where(SongProject.youtube_video_id.is_not(None))
        ):
            ids.append(song.youtube_video_id)
            ids += [s.youtube_video_id for s in song.shorts or [] if s.youtube_video_id]
    finally:
        db.close()

    changed = unchanged = failed = 0
    for vid in dict.fromkeys(ids):
        try:
            result = set_synthetic_media_flag(video_id=vid, value=True)
        except YouTubeUploadError as exc:
            failed += 1
            print("fail", vid, str(exc)[:160])
            if "quotaExceeded" in str(exc):
                break
            continue
        if result["changed"]:
            changed += 1
            print("flagged", vid)
        else:
            unchanged += 1
    print(f"DONE changed={changed} already={unchanged} failed={failed}")


if __name__ == "__main__":
    main()
