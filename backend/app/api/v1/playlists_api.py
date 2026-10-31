"""YouTube playlist listing + auto-pick / manual select for songs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SongProject
from app.playlists import apply_playlists_to_song, pick_playlist, suggest_playlist_names
from app.providers import youtube as yt

router = APIRouter(prefix="/playlists", tags=["playlists"])


@router.get("")
def list_channel_playlists() -> dict:
    if not yt.is_connected():
        raise HTTPException(status_code=503, detail="YouTube not connected — connect OAuth first")
    try:
        items = yt.list_playlists()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "data": {
            "playlists": items,
            "count": len(items),
            "hint": (
                "Name playlists after deities (Shiva, Hanuman, Lakshmi, …) plus "
                "'Morning Devotional' / 'Evening Aarti'. Shorts reuse the main video playlist."
            ),
        }
    }


@router.get("/suggest")
def suggest(deity: str | None = None, daypart: str | None = "morning") -> dict:
    channel: list[dict[str, str]] = []
    youtube_error: str | None = None
    if yt.is_connected():
        try:
            channel = yt.list_playlists()
        except Exception as exc:  # noqa: BLE001
            youtube_error = str(exc)
            channel = []
    longform = pick_playlist(
        deity=deity, daypart=daypart, channel_playlists=channel, for_shorts=False
    )
    shorts = {
        **longform,
        "reason": "Same playlist as main long-form (Shorts reuse main content)",
        "same_as_longform": True,
    }
    return {
        "data": {
            "longform": longform,
            "shorts": shorts,
            "preferred_titles": suggest_playlist_names(deity=deity, daypart=daypart),
            "channel_playlists": channel,
            "channel_playlist_count": len(channel),
            "needs_manual": not bool(longform.get("playlist_id")),
            "youtube_error": youtube_error,
        }
    }


class AssignPlaylistBody(BaseModel):
    playlist_id: str | None = Field(default=None, max_length=64)
    playlist_title: str | None = Field(default=None, max_length=200)
    for_shorts: bool = False
    both: bool = True
    auto: bool = True
    daypart: str | None = "morning"


@router.post("/songs/{song_id}/assign")
def assign_playlist(
    song_id: uuid.UUID,
    body: AssignPlaylistBody,
    db: Session = Depends(get_db),
) -> dict:
    song = db.get(SongProject, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    # Manual select — always wins when playlist_id is provided
    if body.playlist_id and not body.auto:
        title = body.playlist_title
        if not title and yt.is_connected():
            try:
                for pl in yt.list_playlists():
                    if pl.get("id") == body.playlist_id:
                        title = pl.get("title")
                        break
            except Exception:  # noqa: BLE001
                pass
        title = title or body.playlist_id
        if body.both or not body.for_shorts:
            song.youtube_playlist_id = body.playlist_id
            song.youtube_playlist_title = title
        if body.both or body.for_shorts:
            song.shorts_playlist_id = body.playlist_id
            song.shorts_playlist_title = title
        db.commit()
        return {
            "data": {
                "song_id": str(song.id),
                "assignment": {
                    "playlist_id": body.playlist_id,
                    "playlist_title": title,
                    "matched": True,
                    "reason": "manual select",
                },
                "auto": False,
                "song": {
                    "youtube_playlist_id": song.youtube_playlist_id,
                    "youtube_playlist_title": song.youtube_playlist_title,
                    "shorts_playlist_id": song.shorts_playlist_id,
                    "shorts_playlist_title": song.shorts_playlist_title,
                },
            }
        }

    channel: list[dict[str, str]] = []
    youtube_error: str | None = None
    if yt.is_connected():
        try:
            channel = yt.list_playlists()
        except Exception as exc:  # noqa: BLE001
            youtube_error = str(exc)
            channel = []

    if body.both:
        picks = apply_playlists_to_song(
            song, daypart=body.daypart, channel_playlists=channel
        )
        db.commit()
        return {
            "data": {
                "song_id": str(song.id),
                "assignment": picks,
                "auto": True,
                "needs_manual": not bool(song.youtube_playlist_id),
                "channel_playlists": channel,
                "youtube_error": youtube_error,
                "song": {
                    "youtube_playlist_id": song.youtube_playlist_id,
                    "youtube_playlist_title": song.youtube_playlist_title,
                    "shorts_playlist_id": song.shorts_playlist_id,
                    "shorts_playlist_title": song.shorts_playlist_title,
                },
            }
        }

    pick = pick_playlist(
        deity=song.deity,
        daypart=body.daypart,
        channel_playlists=channel,
        for_shorts=body.for_shorts,
    )
    if body.for_shorts:
        song.shorts_playlist_id = pick.get("playlist_id")
        song.shorts_playlist_title = pick.get("playlist_title")
    else:
        song.youtube_playlist_id = pick.get("playlist_id")
        song.youtube_playlist_title = pick.get("playlist_title")
    db.commit()
    return {
        "data": {
            "song_id": str(song.id),
            "assignment": pick,
            "auto": True,
            "needs_manual": not bool(pick.get("playlist_id")),
            "channel_playlists": channel,
            "youtube_error": youtube_error,
        }
    }
