"""Dev-friendly additive schema updates (create_all + IF NOT EXISTS columns)."""

from __future__ import annotations

from sqlalchemy import text

from app.db import Base, engine
import app.models  # noqa: F401


SONG_COLUMNS = [
    ("visual_style", "TEXT"),
    ("visual_prompt", "TEXT"),
    ("video_clip_path", "TEXT"),
    ("final_video_path", "TEXT"),
    ("publish_at", "TIMESTAMPTZ"),
    ("youtube_title", "VARCHAR(100)"),
    ("youtube_description", "TEXT"),
    ("youtube_tags", "TEXT"),
    ("youtube_video_id", "VARCHAR(64)"),
    ("youtube_url", "VARCHAR(255)"),
    ("deity_image_path", "TEXT"),
    ("thumbnail_path", "TEXT"),
    ("youtube_playlist_id", "VARCHAR(64)"),
    ("youtube_playlist_title", "VARCHAR(200)"),
    ("shorts_playlist_id", "VARCHAR(64)"),
    ("shorts_playlist_title", "VARCHAR(200)"),
]

SHORT_COLUMNS = [
    ("clip_path", "TEXT"),
    ("final_clip_path", "TEXT"),
    ("youtube_video_id", "VARCHAR(64)"),
    ("youtube_url", "VARCHAR(255)"),
]

SCHEDULE_COLUMNS = [
    ("daypart", "VARCHAR(20) DEFAULT 'morning'"),
]


def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for col, typ in SONG_COLUMNS:
            conn.execute(
                text(
                    f"ALTER TABLE song_projects ADD COLUMN IF NOT EXISTS {col} {typ}"
                )
            )
        for col, typ in SHORT_COLUMNS:
            conn.execute(
                text(
                    f"ALTER TABLE short_projects ADD COLUMN IF NOT EXISTS {col} {typ}"
                )
            )
        # schedule_slots may already exist from earlier weeks
        conn.execute(
            text(
                "ALTER TABLE schedule_slots ADD COLUMN IF NOT EXISTS daypart VARCHAR(20) DEFAULT 'morning'"
            )
        )
        conn.execute(
            text(
                "UPDATE schedule_slots SET daypart = 'morning' WHERE daypart IS NULL OR daypart = ''"
            )
        )
        # Drop duplicate empty planned slots (same date+daypart), keep one
        conn.execute(
            text(
                """
                DELETE FROM schedule_slots a USING schedule_slots b
                WHERE a.song_id IS NULL AND b.song_id IS NULL
                  AND a.slot_date = b.slot_date
                  AND a.week_start = b.week_start
                  AND COALESCE(a.daypart, 'morning') = COALESCE(b.daypart, 'morning')
                  AND a.ctid < b.ctid
                """
            )
        )
