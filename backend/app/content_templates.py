"""Auto-fill YouTube long-form + Shorts copy (premium Telugu/English discovery style)."""

from __future__ import annotations

import re
from typing import Any

from app.lyrics_sections import charanam_hook, extract_charanams, extract_sections


CHANNEL_HANDLE = "Ragam Spiritual Telugu"
CHANNEL_SHORT = "Ragam Spiritual"


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    for ln in text.splitlines():
        s = ln.strip()
        if s:
            return s
    return text.strip()


def _telugu_hook_title(raw: str | None, *, max_chars: int = 42) -> str:
    """Short Telugu-facing title for thumbnails / SEO head."""
    s = (raw or "").strip()
    if not s:
        return "తెలుగు భక్తి గీతం"
    # If Gemini returned SEO title with pipes, take the Telugu head
    if "|" in s:
        s = s.split("|", 1)[0].strip()
    s = re.sub(r"\s+", " ", s)
    return s[:max_chars].strip()


def fill_youtube_longform(
    *,
    title: str,
    deity: str | None,
    topic: str | None,
    mood: str | None,
    lyrics_excerpt: str | None = None,
    lyrics_full: str | None = None,
) -> dict[str, str]:
    """Premium YouTube package in the Narasimha-reference style — always regenerate."""
    deity_bit = (deity or "Divine").strip()
    sections = extract_sections(lyrics_full or lyrics_excerpt)
    # ALWAYS prefer latest Pallavi as the Telugu title (keeps thumb + YT in sync with lyrics)
    pallavi_line = _first_line(sections.get("pallavi") or "")
    telugu = _telugu_hook_title(pallavi_line or title, max_chars=48)
    if not telugu or telugu == "తెలుగు భక్తి గీతం":
        telugu = _telugu_hook_title(title, max_chars=48)

    # YouTube title max 100
    yt_title = f"{telugu} | Powerful Telugu Devotional Song | {CHANNEL_HANDLE}"
    if len(yt_title) > 100:
        yt_title = f"{telugu} | Telugu Devotional | {CHANNEL_SHORT}"
    if len(yt_title) > 100:
        yt_title = yt_title[:100].rstrip(" |")

    highlights: list[str] = []
    sections = extract_sections(lyrics_full or lyrics_excerpt)
    for key in ("pallavi", "slokam", "charanam 1", "charanam 2"):
        body = sections.get(key)
        if body:
            highlights.append(_first_line(body)[:80])
    while len(highlights) < 3:
        highlights.append(f"{deity_bit} భక్తి మహిమ")

    topic_line = (topic or "").strip()
    mood_line = (mood or "").strip()

    telugu_banner = telugu.rstrip("!！")
    description = f"""🙏 **{telugu_banner}!** 🙏

Experience the divine power, devotion, and grace of {deity_bit} through this powerful Telugu devotional anthem.

With majestic Telugu Carnatic vocals, sacred shloka chanting, temple bells, mridangam rhythms, and heartfelt bhakti, this song is crafted for daily prayer and peaceful listening.

✨ **ఈ గీతం ప్రత్యేకతలు**
- {highlights[0]}
- {highlights[1]}
- {highlights[2]}
- శక్తివంతమైన తెలుగు భక్తి సాహిత్యం
- గంభీరమైన సంగీతం, భక్తిభావం
{f"- {topic_line}" if topic_line else ""}
{f"- Seasonal mood: {mood_line}" if mood_line else ""}

🙏 శ్రీ {deity_bit} వారి కృప అందరిపై ఉండాలని ప్రార్థిస్తున్నాము.

మీకు ఈ పాట నచ్చితే Like చేయండి, మీ కుటుంబ సభ్యులతో Share చేయండి, మరిన్ని తెలుగు భక్తిగీతాల కోసం **{CHANNEL_HANDLE}** ఛానల్‌ను Subscribe చేయండి.

**జై శ్రీ {deity_bit}!** 🙏
""".strip()

    # Clean blank bullet leftovers
    description = re.sub(r"\n- \n", "\n", description)
    description = re.sub(r"\n{3,}", "\n\n", description)

    tag_bits = [
        deity_bit.replace(" ", ""),
        "TeluguDevotionalSongs",
        "TeluguBhaktiSongs",
        "RagamSpiritualTelugu",
        "Bhakti",
        "CarnaticDevotional",
        mood.replace(" ", "") if mood else "TempleBhajan",
    ]
    hashtags = " ".join(f"#{t}" for t in tag_bits if t)
    description = f"{description}\n\n{hashtags}"

    tags = ",".join(
        [
            "Telugu Devotional Songs",
            "Telugu Bhakti Songs",
            deity_bit,
            CHANNEL_SHORT,
            CHANNEL_HANDLE,
            "bhajan",
            "keerthana",
            mood or "temple",
        ]
    )
    return {
        "title": telugu[:200],
        "youtube_title": yt_title[:100],
        "youtube_description": description,
        "youtube_tags": tags[:500],
        "telugu_title": telugu[:80],
    }


def fill_shorts_pair(
    *,
    title: str,
    deity: str | None,
    main_url: str | None = None,
    daypart: str | None = None,
    youtube_title: str | None = None,
    youtube_description: str | None = None,
    charanams: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Two Shorts from SAME 16:9 main clip (ffmpeg 9:16 center crop).

    Short 1 ↔ Charanam 1, Short 2 ↔ Charanam 2. Each Short visual loops to <30s.
    """
    deity_bit = deity or "Divine"
    telugu = _telugu_hook_title(title or youtube_title, max_chars=48)
    verses = list(charanams or [])
    while len(verses) < 2:
        verses.append(telugu)

    link_line = (
        f"\n\n▶ Full song: {main_url}"
        if main_url
        else "\n\n▶ Full song on our channel (link added after long-form publish)."
    )

    shorts: list[dict[str, Any]] = []
    for n in (1, 2):
        verse = verses[n - 1].strip()
        hook = charanam_hook(verse, max_chars=160)
        suffix = f" | Charanam {n}"
        core = telugu[: max(1, 100 - len(suffix))]
        shorts.append(
            {
                "slot_index": n,
                "title": f"{core}{suffix}",
                "hook": hook,
                "description": (
                    f"🙏 **Charanam {n}** — {telugu}\n\n{verse[:900]}\n\n"
                    f"Full song on {CHANNEL_HANDLE}."
                    f"{link_line}\n\n#Shorts #TeluguDevotional #{deity_bit.replace(' ', '')} "
                    f"#RagamSpiritualTelugu"
                ),
                "charanam_index": n,
                "charanam_text": verse[:1200],
                "source": "ffmpeg_center_crop_9x16_loop_lt30s",
            }
        )
    return shorts


def sync_song_publish_copy(
    song: Any,
    *,
    lyrics: str | None,
    gemini_title: str | None = None,
    topic: str | None = None,
    mood: str | None = None,
    refresh_shorts: bool = True,
) -> dict[str, str]:
    """Always refresh song.title + YouTube package + Shorts copy from latest lyrics."""
    seed_title = (gemini_title or song.title or "").strip()
    meta = fill_youtube_longform(
        title=seed_title,
        deity=getattr(song, "deity", None),
        topic=topic if topic is not None else getattr(song, "notes", None),
        mood=mood or getattr(song, "visual_style", None),
        lyrics_excerpt=(lyrics or "")[:500],
        lyrics_full=lyrics,
    )
    song.title = meta["title"]
    song.youtube_title = meta["youtube_title"]
    song.youtube_description = meta["youtube_description"]
    song.youtube_tags = meta["youtube_tags"]

    if refresh_shorts and getattr(song, "shorts", None) is not None:
        charanams = extract_charanams(lyrics, limit=2)
        defs = fill_shorts_pair(
            title=meta["title"],
            deity=song.deity,
            main_url=getattr(song, "youtube_url", None),
            youtube_title=meta["youtube_title"],
            youtube_description=meta["youtube_description"],
            charanams=charanams,
        )
        by_slot = {s.slot_index: s for s in (song.shorts or [])}
        for short_def in defs:
            row = by_slot.get(short_def["slot_index"])
            if row is None:
                continue
            row.title = short_def["title"]
            row.hook = short_def["hook"]
            row.description = short_def["description"]

    return meta
