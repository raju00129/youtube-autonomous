"""Song studio, weekly schedule, shorts, branding."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChannelBrand(Base):
    """Singleton-ish channel branding (logo for thumbnails)."""

    __tablename__ = "channel_brand"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    channel_name: Mapped[str] = mapped_column(String(200), default="Ragam Spiritual")
    logo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SongProject(Base):
    __tablename__ = "song_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    deity: Mapped[str | None] = mapped_column(String(120), nullable=True)
    language: Mapped[str] = mapped_column(String(40), default="te")
    music_genre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vocal_preference: Mapped[str | None] = mapped_column(String(40), nullable=True)
    style_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_style: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(String(40), default="lyrics_draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # YouTube / schedule
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    youtube_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    youtube_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    youtube_playlist_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    youtube_playlist_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    shorts_playlist_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shorts_playlist_title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Thumbnail composition hints
    deity_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Kling visual clip (Shorts cut from this — never re-generated)
    visual_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_clip_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Muxed Suno audio + looped visual — preview before publish
    final_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    lyrics_versions: Mapped[list[LyricsVersion]] = relationship(
        back_populates="song", cascade="all, delete-orphan", order_by="LyricsVersion.version"
    )
    music_generations: Mapped[list[MusicGeneration]] = relationship(
        back_populates="song", cascade="all, delete-orphan", order_by="MusicGeneration.created_at"
    )
    shorts: Mapped[list[ShortProject]] = relationship(
        back_populates="song", cascade="all, delete-orphan", order_by="ShortProject.slot_index"
    )
    schedule_slots: Mapped[list[ScheduleSlot]] = relationship(back_populates="song")


class LyricsVersion(Base):
    __tablename__ = "lyrics_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    song_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("song_projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    song: Mapped[SongProject] = relationship(back_populates="lyrics_versions")


class MusicGeneration(Base):
    __tablename__ = "music_generations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    song_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("song_projects.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), default="manual_suno_upload")
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    song: Mapped[SongProject] = relationship(back_populates="music_generations")


class ShortProject(Base):
    """Two Shorts per main song, published at the same scheduled time with main link."""

    __tablename__ = "short_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    song_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("song_projects.id", ondelete="CASCADE"), nullable=False
    )
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 or 2
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hook: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # description should include link to main long-form when known
    stage: Mapped[str] = mapped_column(String(40), default="planned")
    clip_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_clip_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    song: Mapped[SongProject] = relationship(back_populates="shorts")


class ScheduleSlot(Base):
    """Weekly plan: 2 songs/day (morning + evening); each song → 2 Shorts from same A/V."""

    __tablename__ = "schedule_slots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)  # Monday of week
    slot_date: Mapped[date] = mapped_column(Date, nullable=False)
    # morning | evening — two long-form songs per day
    daypart: Mapped[str] = mapped_column(String(20), default="morning", nullable=False)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    title_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    topic_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    deity_override: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="planned")
    # planned | song_created | awaiting_audio | music_ready | publishing | done
    song_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("song_projects.id", ondelete="SET NULL"), nullable=True
    )
    auto_deity: Mapped[str | None] = mapped_column(String(120), nullable=True)
    auto_topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_mood: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    song: Mapped[SongProject | None] = relationship(back_populates="schedule_slots")
