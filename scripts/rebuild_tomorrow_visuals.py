"""Rebuild tomorrow's scheduled songs: native loop + center Shorts + Kling crop."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import SongProject
from app.services_video import apply_manual_visual_upload

JOBS = [
    (
        "2b21fd92-ecaa-4fe9-af26-77f083772240",
        "manual_f68da34f97_kling_20261110_VIDEO_follow_the_30_0.mp4",
    ),
    (
        "90f57f3b-5fb5-4e8a-bd3d-19a2a7790ca1",
        "manual_7b12a56c22_kling_20261110_VIDEO_use_charec_142_0.mp4",
    ),
]


def main() -> None:
    db = SessionLocal()
    try:
        for sid, raw_name in JOBS:
            raw = Path(f"/app/storage/visuals/{sid}/{raw_name}")
            song = db.scalar(
                select(SongProject)
                .where(SongProject.id == uuid.UUID(sid))
                .options(
                    selectinload(SongProject.lyrics_versions),
                    selectinload(SongProject.music_generations),
                    selectinload(SongProject.shorts),
                )
            )
            if not song:
                print("MISSING", sid)
                continue
            if not raw.exists():
                print("MISSING_RAW", raw)
                continue
            print("==", song.title, song.stage)
            song.final_video_path = None
            for sh in song.shorts or []:
                sh.final_clip_path = None
            result = apply_manual_visual_upload(
                db, song, source_path=raw, original_filename=raw.name
            )
            db.commit()
            print(" done", result.get("note"))
            print(" main", song.video_clip_path)
            for sh in song.shorts or []:
                print(" short", sh.slot_index, sh.clip_path)
    finally:
        db.close()
    print("DONE")


if __name__ == "__main__":
    main()
