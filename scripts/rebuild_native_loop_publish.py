"""Rebuild evening visual at true 720p (clean SAR) and republish."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import SongProject
from app.services_final import mix_final_preview
from app.services_publish import publish_song_to_youtube
from app.services_video import apply_manual_visual_upload

SID = "4945c4b7-259d-4c6b-a440-925b81398b55"
RAW = Path(
    "/app/storage/visuals/4945c4b7-259d-4c6b-a440-925b81398b55/"
    "manual_fa37cf59f7_kling_20261109_VIDEO_Create_a_s_6060_0.mp4"
)


def load_song(db) -> SongProject:
    song = db.scalar(
        select(SongProject)
        .where(SongProject.id == uuid.UUID(SID))
        .options(
            selectinload(SongProject.lyrics_versions),
            selectinload(SongProject.music_generations),
            selectinload(SongProject.shorts),
        )
    )
    if not song:
        raise RuntimeError("song missing")
    return song


def main() -> None:
    if not RAW.exists():
        raise RuntimeError(f"missing raw {RAW}")

    db = SessionLocal()
    try:
        song = load_song(db)
        print("song", song.title, "old_yt", song.youtube_video_id)

        song.youtube_video_id = None
        song.youtube_url = None
        song.final_video_path = None
        for sh in song.shorts or []:
            sh.youtube_video_id = None
            sh.youtube_url = None
            sh.final_clip_path = None
        song.stage = "video_ready"
        db.flush()

        result = apply_manual_visual_upload(
            db, song, source_path=RAW, original_filename=RAW.name
        )
        print("visual", result)
        db.commit()

        # Probe SAR
        import subprocess

        main = Path(song.video_clip_path)
        probe = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,sample_aspect_ratio,display_aspect_ratio,bit_rate",
                "-of",
                "default=noprint_wrappers=1",
                str(main),
            ],
            text=True,
        )
        print("MAIN_PROBE\n", probe)

        song = load_song(db)
        print("mixing…")
        mix = mix_final_preview(db, song)
        db.commit()
        final = Path(song.final_video_path)
        probe2 = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,sample_aspect_ratio,display_aspect_ratio,bit_rate",
                "-of",
                "default=noprint_wrappers=1",
                str(final),
            ],
            text=True,
        )
        print("FINAL_PROBE\n", probe2)
        print("mix keys", list(mix.keys())[:6])

        song = load_song(db)
        print("publishing…")
        pub = publish_song_to_youtube(db, song, publish_now=True)
        db.commit()
        print("PUBLISHED", pub.get("youtube_url"))
        print(pub.get("note"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
