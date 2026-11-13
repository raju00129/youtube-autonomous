"""Flag every published Ragam video/Short as altered/synthetic (AI) content on YouTube.

Run inside the backend container:
    docker compose exec -T backend python - < scripts/backfill_synthetic_media.py
    docker compose exec -T backend python - --extra < scripts/backfill_synthetic_media.py

--extra flags channel uploads that are not tracked in the DB (older/manual uploads).
"""

from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import SongProject
from app.providers.youtube import YouTubeUploadError, _yt_service, set_synthetic_media_flag


def _channel_upload_ids() -> list[str]:
    yt = _yt_service()
    uploads = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0][
        "contentDetails"
    ]["relatedPlaylists"]["uploads"]
    ids: list[str] = []
    token = None
    while True:
        page = (
            yt.playlistItems()
            .list(part="contentDetails", playlistId=uploads, maxResults=50, pageToken=token)
            .execute()
        )
        ids += [it["contentDetails"]["videoId"] for it in page.get("items", [])]
        token = page.get("nextPageToken")
        if not token:
            return ids


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

    if "--extra" in sys.argv:
        tracked = set(ids)
        ids = [vid for vid in _channel_upload_ids() if vid not in tracked]
        print(f"channel uploads not in DB: {len(ids)}")

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
