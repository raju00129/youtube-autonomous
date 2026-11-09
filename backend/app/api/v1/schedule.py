"""Weekly schedule — 2 songs/day (morning + evening); each → 2 Shorts from same A/V."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.calendar_rules import DAYPART_FLAVOR, suggest_for_date, week_suggestions
from app.content_templates import fill_shorts_pair, fill_youtube_longform
from app.db import get_db
from app.models import ScheduleSlot, ShortProject, SongProject
from app.playlists import apply_playlists_to_song
from app.providers import llm
from app.providers import youtube as yt

router = APIRouter(prefix="/schedule", tags=["schedule"])
IST = ZoneInfo("Asia/Kolkata")
DAYPARTS = ("morning", "evening")


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _default_publish_at(slot_date: date, daypart: str) -> datetime:
    flavor = DAYPART_FLAVOR.get(daypart, DAYPART_FLAVOR["morning"])
    return datetime.combine(
        slot_date,
        time(flavor["default_hour"], flavor["default_minute"]),
        tzinfo=IST,
    )


def _slot_payload(slot: ScheduleSlot) -> dict:
    daypart = slot.daypart or "morning"
    song = getattr(slot, "song", None)
    published = bool(
        slot.status == "published"
        or (song and (song.stage == "published" or song.youtube_video_id))
    )
    return {
        "id": str(slot.id),
        "week_start": slot.week_start.isoformat(),
        "slot_date": slot.slot_date.isoformat(),
        "weekday": slot.slot_date.strftime("%A"),
        "daypart": daypart,
        "daypart_label": DAYPART_FLAVOR.get(daypart, {}).get("label", daypart),
        "publish_at": slot.publish_at.isoformat() if slot.publish_at else None,
        "title_hint": slot.title_hint,
        "topic_override": slot.topic_override,
        "deity_override": slot.deity_override,
        "status": "published" if published else slot.status,
        "published": published,
        "song_id": str(slot.song_id) if slot.song_id else None,
        "song_title": (song.title if song else None),
        "song_stage": (song.stage if song else None),
        "youtube_url": (song.youtube_url if song else None),
        "youtube_video_id": (song.youtube_video_id if song else None),
        "auto_deity": slot.auto_deity,
        "auto_topic": slot.auto_topic,
        "auto_mood": slot.auto_mood,
        "notes": slot.notes,
        "shorts_per_song": 2,
        "suggestion": suggest_for_date(slot.slot_date, daypart=daypart),
    }


class WeekEnsureRequest(BaseModel):
    week_start: date | None = None
    morning_hour: int = Field(default=6, ge=0, le=23)
    morning_minute: int = Field(default=0, ge=0, le=59)
    evening_hour: int = Field(default=19, ge=0, le=23)
    evening_minute: int = Field(default=0, ge=0, le=59)


class SlotUpdate(BaseModel):
    title_hint: str | None = Field(default=None, max_length=200)
    topic_override: str | None = None
    deity_override: str | None = Field(default=None, max_length=120)
    publish_at: datetime | None = None
    notes: str | None = None


class MaterializeRequest(BaseModel):
    generate_lyrics: bool = True
    approve_lyrics: bool = False


@router.get("/calendar/suggest")
def calendar_suggest(on: date | None = None, daypart: str = "morning") -> dict:
    return {"data": suggest_for_date(on, daypart=daypart)}


@router.get("/weeks/{week_start}")
def get_week(week_start: date, db: Session = Depends(get_db)) -> dict:
    monday = _monday_of(week_start)
    slots = db.scalars(
        select(ScheduleSlot)
        .where(ScheduleSlot.week_start == monday)
        .options(selectinload(ScheduleSlot.song))
        .order_by(ScheduleSlot.slot_date, ScheduleSlot.daypart.desc())
        # morning before evening: 'evening' < 'morning' alphabetically false
        # use custom: morning first via CASE — simpler sort in Python
    ).all()
    slots_sorted = sorted(
        slots,
        key=lambda s: (s.slot_date, 0 if (s.daypart or "morning") == "morning" else 1),
    )
    by_day: dict[str, list] = {}
    for s in slots_sorted:
        key = s.slot_date.isoformat()
        by_day.setdefault(key, []).append(_slot_payload(s))
    return {
        "data": {
            "week_start": monday.isoformat(),
            "plan": {
                "songs_per_day": 2,
                "shorts_per_song": 2,
                "shorts_per_day": 4,
                "note": (
                    "Morning song → 2 Short clips from same A/V at morning time; "
                    "Evening song → 2 Short clips from same A/V at evening time."
                ),
            },
            "suggestions": week_suggestions(monday),
            "slots": [_slot_payload(s) for s in slots_sorted],
            "days": [{"date": d, "slots": items} for d, items in by_day.items()],
        }
    }


@router.post("/weeks/ensure")
def ensure_week(body: WeekEnsureRequest, db: Session = Depends(get_db)) -> dict:
    """Create 14 slots (7 days × morning + evening) with auto deity/mood."""
    monday = _monday_of(body.week_start or date.today())
    existing_rows = db.scalars(
        select(ScheduleSlot)
        .where(ScheduleSlot.week_start == monday)
        .options(selectinload(ScheduleSlot.song))
    ).all()
    existing = {(s.slot_date, (s.daypart or "morning")): s for s in existing_rows}
    created = 0

    hour_map = {
        "morning": (body.morning_hour, body.morning_minute),
        "evening": (body.evening_hour, body.evening_minute),
    }

    refreshed = 0
    for i in range(7):
        day = monday + timedelta(days=i)
        for daypart in DAYPARTS:
            suggestion = suggest_for_date(day, daypart=daypart)
            h, m = hour_map[daypart]
            publish_at = datetime.combine(day, time(h, m), tzinfo=IST)
            key = (day, daypart)
            if key in existing:
                slot = existing[key]
                # Refresh auto deity/topic for empty planned slots (pantheon updates)
                if slot.song_id is None and slot.status in {"planned", "song_created"}:
                    if not slot.deity_override:
                        slot.auto_deity = suggestion["deity"]
                    if not slot.topic_override:
                        slot.auto_topic = suggestion["topic"]
                    slot.auto_mood = suggestion["month_mood"]
                    refreshed += 1
                continue
            db.add(
                ScheduleSlot(
                    week_start=monday,
                    slot_date=day,
                    daypart=daypart,
                    publish_at=publish_at,
                    status="planned",
                    auto_deity=suggestion["deity"],
                    auto_topic=suggestion["topic"],
                    auto_mood=suggestion["month_mood"],
                )
            )
            created += 1
    db.commit()
    payload = get_week(monday, db)
    payload["meta"] = {
        "created_slots": created,
        "refreshed_slots": refreshed,
        "songs_per_day": 2,
        "shorts_per_day": 4,
    }
    return payload


@router.patch("/slots/{slot_id}")
def update_slot(slot_id: uuid.UUID, body: SlotUpdate, db: Session = Depends(get_db)) -> dict:
    slot = db.get(ScheduleSlot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    data = body.model_dump(exclude_unset=True)
    if "publish_at" in data and data["publish_at"] is not None:
        when = data["publish_at"]
        if when.tzinfo is None:
            when = when.replace(tzinfo=IST)
        else:
            when = when.astimezone(IST)
        data["publish_at"] = when
        # Keep slot on its planned week/day so it does not vanish from the week view.
        # Only publish_at (and linked song) change.
    for key, value in data.items():
        setattr(slot, key, value)

    # Linked song follows slot time; Short 1 same time, Short 2 +stagger hours
    if "publish_at" in data and slot.song_id and data["publish_at"] is not None:
        song = db.get(SongProject, slot.song_id)
        if song:
            song.publish_at = data["publish_at"]
            from app.services_publish import apply_short_publish_times
            from sqlalchemy.orm import selectinload

            song = db.scalar(
                select(SongProject)
                .where(SongProject.id == song.id)
                .options(selectinload(SongProject.shorts))
            )
            if song:
                apply_short_publish_times(song, data["publish_at"])

    db.commit()
    slot = db.scalar(
        select(ScheduleSlot)
        .where(ScheduleSlot.id == slot_id)
        .options(selectinload(ScheduleSlot.song))
    )
    assert slot is not None
    return {"data": _slot_payload(slot)}


@router.post("/slots/{slot_id}/materialize")
def materialize_slot(
    slot_id: uuid.UUID,
    body: MaterializeRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Create 1 song + Cursor lyrics + 2 Shorts (clips from same future A/V)."""
    slot = db.get(ScheduleSlot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.song_id:
        raise HTTPException(status_code=409, detail="Slot already has a song")

    daypart = slot.daypart or "morning"
    suggestion = suggest_for_date(slot.slot_date, daypart=daypart)
    deity = slot.deity_override or slot.auto_deity or suggestion["deity"]
    raw_topic = slot.topic_override or slot.auto_topic or suggestion["topic"]
    festive_tokens = (
        "kartika", "karthika", "diwali", "deepavali", "navaratri",
        "sankranti", "ugadi", "janmashtami", "shivaratri", "vaikuntha",
        "seasonal mood", "festive",
    )
    # Drop leftover calendar-month festival forcing from older slots
    if any(t in (raw_topic or "").lower() for t in festive_tokens):
        topic = suggestion["topic"]
    else:
        topic = raw_topic
    title_hint = (
        slot.title_hint
        or f"{deity} — {slot.slot_date.strftime('%a')} {daypart}"
    )
    vocal = suggestion.get("vocal_preference", "m")
    genre = suggestion.get("music_genre")
    visual = suggestion.get("visual_style")
    raw_mood = slot.auto_mood or suggestion.get("month_mood") or ""
    mood = (
        "peaceful temple devotion"
        if any(t in raw_mood.lower() for t in festive_tokens)
        else (raw_mood or "peaceful temple devotion")
    )

    # Fast create: never block HTTP on Gemini. Lyrics run in Celery so
    # multiple "Create song" clicks can run in parallel.
    lyrics_job_id: str | None = None
    if body.generate_lyrics and not llm.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Set GEMINI_API_KEY for generate (or CURSOR_API_KEY / OPENAI_API_KEY)",
        )

    title = title_hint
    meta = fill_youtube_longform(
        title=title,
        deity=deity,
        topic=topic,
        mood=mood,
        lyrics_excerpt=None,
        lyrics_full=None,
    )

    song = SongProject(
        title=meta.get("title") or title,
        deity=deity,
        language="te",
        music_genre=genre,
        vocal_preference=vocal,
        style_prompt=None,
        visual_style=visual,
        stage="generating_lyrics" if body.generate_lyrics else "scheduled",
        notes=f"[{daypart}] {topic}",
        publish_at=slot.publish_at,
        youtube_title=meta["youtube_title"],
        youtube_description=meta["youtube_description"],
        youtube_tags=meta["youtube_tags"],
    )
    db.add(song)
    db.flush()

    from app.services_publish import short_release_at

    for short_def in fill_shorts_pair(
        title=title,
        deity=deity,
        main_url=None,
        daypart=daypart,
        youtube_title=meta["youtube_title"],
        youtube_description=meta["youtube_description"],
        charanams=None,
    ):
        db.add(
            ShortProject(
                song_id=song.id,
                slot_index=short_def["slot_index"],
                title=short_def["title"],
                hook=short_def["hook"],
                description=short_def["description"],
                stage="planned",
                publish_at=(
                    short_release_at(slot.publish_at, short_def["slot_index"])
                    if slot.publish_at
                    else None
                ),
            )
        )

    channel_playlists: list[dict[str, str]] = []
    if yt.is_connected():
        try:
            channel_playlists = yt.list_playlists()
        except Exception:  # noqa: BLE001 — still create song if YouTube list fails
            channel_playlists = []
    playlist_pick = apply_playlists_to_song(
        song, daypart=daypart, channel_playlists=channel_playlists
    )

    slot.song_id = song.id
    slot.status = "song_created"
    slot.auto_deity = deity
    slot.auto_topic = topic
    slot.auto_mood = mood
    db.commit()

    if body.generate_lyrics:
        from app.workers.tasks import song_fill_lyrics

        async_result = song_fill_lyrics.delay(
            str(song.id),
            title_hint=title_hint,
            deity=deity,
            topic=topic,
            vocal=vocal,
            music_genre=genre,
            energy_hint=suggestion.get("energy_hint"),
            approve=body.approve_lyrics,
            daypart=daypart,
        )
        lyrics_job_id = str(async_result.id)

    song = db.scalar(
        select(SongProject)
        .where(SongProject.id == song.id)
        .options(selectinload(SongProject.shorts), selectinload(SongProject.lyrics_versions))
    )
    assert song is not None
    slot = db.scalar(
        select(ScheduleSlot)
        .where(ScheduleSlot.id == slot_id)
        .options(selectinload(ScheduleSlot.song))
    )
    assert slot is not None
    return {
        "data": {
            "slot": _slot_payload(slot),
            "song_id": str(song.id),
            "title": song.title,
            "daypart": daypart,
            "stage": song.stage,
            "lyrics_pending": bool(lyrics_job_id),
            "lyrics_job_id": lyrics_job_id,
            "playlists": playlist_pick,
            "youtube_playlist_title": song.youtube_playlist_title,
            "shorts_playlist_title": song.shorts_playlist_title,
            "shorts": [
                {
                    "id": str(s.id),
                    "slot_index": s.slot_index,
                    "title": s.title,
                    "hook": s.hook,
                    "publish_at": s.publish_at.isoformat() if s.publish_at else None,
                    "source": "same_longform_av",
                }
                for s in song.shorts
            ],
            "next": [
                "Lyrics generate in the background — open the song when ready",
                "Approve lyrics → Suno → upload MP3 (one audio for this daypart)",
                "Generate visual once; cut 2 Short clips from the same audio+video",
                "Publish long-form + 2 Shorts at this daypart time; Shorts link to main",
            ],
            "note": (
                "Song created. Gemini lyrics are generating in the background — "
                "you can create another slot now."
                if lyrics_job_id
                else "Song created without lyrics."
            ),
        }
    }
