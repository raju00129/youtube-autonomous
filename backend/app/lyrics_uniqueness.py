"""Build anti-echo context so new lyrics don't clone recent channel songs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import SongProject


def recent_lyrics_echo(
    db: Session,
    *,
    deity: str | None = None,
    exclude_song_id=None,
    limit: int = 4,
) -> str:
    """Return short excerpts of recent titles + Pallavi-ish lines to avoid echoing."""
    q = (
        select(SongProject)
        .options(selectinload(SongProject.lyrics_versions))
        .order_by(SongProject.created_at.desc())
        .limit(24)
    )
    if deity:
        q = q.where(SongProject.deity == deity)

    rows = list(db.scalars(q).all())
    chunks: list[str] = []
    for song in rows:
        if exclude_song_id and str(song.id) == str(exclude_song_id):
            continue
        if not song.lyrics_versions:
            continue
        body = (song.lyrics_versions[-1].body or "").strip()
        if not body:
            continue
        # Keep title + first ~12 non-empty lines (usually hook/pallavi region)
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        head = "\n".join(lines[:12])
        chunks.append(f"- Title: {song.title}\n{head}")
        if len(chunks) >= limit:
            break
    return "\n\n".join(chunks)
