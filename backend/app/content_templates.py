"""Auto-fill YouTube long-form + Shorts copy (Telugu or Hindi channel)."""

from __future__ import annotations

import re
from typing import Any

from app.channels import get_channel
from app.lyrics_sections import charanam_hook, extract_sections


CHANNEL_HANDLE = "Ragam Spiritual Telugu"
CHANNEL_SHORT = "Ragam Spiritual"


def _is_hindi(language: str | None = None, channel_key: str | None = None) -> bool:
    if language and language.strip().lower().startswith("hi"):
        return True
    if channel_key and channel_key.strip().lower() == "hi":
        return True
    return False


def _brand(language: str | None = None, channel_key: str | None = None) -> tuple[str, str]:
    key = "hi" if _is_hindi(language, channel_key) else (channel_key or "te")
    try:
        ch = get_channel(key)
        return ch.display_name, ch.short_name
    except Exception:  # noqa: BLE001
        if _is_hindi(language, channel_key):
            return "Devotional Songs Hindi", "Devotional Songs Hindi"
        return CHANNEL_HANDLE, CHANNEL_SHORT


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    for ln in text.splitlines():
        s = ln.strip()
        if s:
            return s
    return text.strip()


def _hook_title(
    raw: str | None,
    *,
    max_chars: int = 42,
    language: str | None = None,
    channel_key: str | None = None,
) -> str:
    """Short title for thumbnails / SEO head."""
    s = (raw or "").strip()
    default = "हिंदी भक्ति गीत" if _is_hindi(language, channel_key) else "తెలుగు భక్తి గీతం"
    if not s:
        return default
    if "|" in s:
        s = s.split("|", 1)[0].strip()
    s = re.sub(r"\s+", " ", s)
    return s[:max_chars].strip() or default


# Back-compat alias
def _telugu_hook_title(raw: str | None, *, max_chars: int = 42) -> str:
    return _hook_title(raw, max_chars=max_chars, language="te")


def fill_youtube_longform(
    *,
    title: str,
    deity: str | None,
    topic: str | None,
    mood: str | None,
    lyrics_excerpt: str | None = None,
    lyrics_full: str | None = None,
    lock_title: bool = False,
    language: str | None = "te",
    channel_key: str | None = None,
) -> dict[str, str]:
    """Premium YouTube package — language follows channel."""
    deity_bit = (deity or "Divine").strip()
    hindi = _is_hindi(language, channel_key)
    handle, short = _brand(language, channel_key)
    sections = extract_sections(lyrics_full or lyrics_excerpt)
    if lock_title and (title or "").strip():
        hook = _hook_title(title, max_chars=48, language=language, channel_key=channel_key)
    else:
        pallavi_line = _first_line(sections.get("pallavi") or "")
        hook = _hook_title(
            pallavi_line or title, max_chars=48, language=language, channel_key=channel_key
        )
        default = "हिंदी भक्ति गीत" if hindi else "తెలుగు భక్తి గీతం"
        if not hook or hook == default:
            hook = _hook_title(title, max_chars=48, language=language, channel_key=channel_key)

    if hindi:
        yt_title = f"{hook} | Powerful Hindi Devotional Song | {handle}"
        if len(yt_title) > 100:
            yt_title = f"{hook} | Hindi Devotional | {short}"
    else:
        yt_title = f"{hook} | Powerful Telugu Devotional Song | {handle}"
        if len(yt_title) > 100:
            yt_title = f"{hook} | Telugu Devotional | {short}"
    if len(yt_title) > 100:
        yt_title = yt_title[:100].rstrip(" |")

    highlights: list[str] = []
    for key in ("pallavi", "slokam", "charanam 1", "charanam 2"):
        body = sections.get(key)
        if body:
            highlights.append(_first_line(body)[:80])
    while len(highlights) < 3:
        if hindi:
            highlights.append(f"{deity_bit} भक्ति महिमा")
        else:
            highlights.append(f"{deity_bit} భక్తి మహిమ")

    topic_line = (topic or "").strip()
    banner = hook.rstrip("!！")

    if hindi:
        description = f"""🙏 **{banner}!** 🙏

Experience the divine power, devotion, and grace of {deity_bit} through this powerful Hindi devotional anthem.

With majestic Hindi bhajan vocals, sacred shloka chanting, temple bells, tabla rhythms, and heartfelt bhakti, this song is crafted for daily prayer and peaceful listening.

✨ **इस गीत की विशेषताएँ**
- {highlights[0]}
- {highlights[1]}
- {highlights[2]}
- शक्तिशाली हिंदी भक्ति साहित्य
- गंभीर संगीत, भक्ति भाव
{f"- {topic_line}" if topic_line and "Seasonal mood" not in topic_line and "Kartika" not in topic_line and "Deepavali" not in topic_line else ""}

🙏 श्री {deity_bit} की कृपा सब पर बनी रहे — यही हमारी प्रार्थना है।

यदि यह गीत पसंद आए तो Like करें, परिवार के साथ Share करें, और और हिंदी भक्ति गीतों के लिए **{handle}** चैनल को Subscribe करें।

**जय श्री {deity_bit}!** 🙏
""".strip()
        tag_bits = [
            deity_bit.replace(" ", ""),
            "HindiDevotionalSongs",
            "HindiBhaktiSongs",
            "DevotionalSongsHindi",
            "Bhakti",
            "Bhajan",
            mood.replace(" ", "") if mood else "TempleBhajan",
        ]
        tags = ",".join(
            [
                "Hindi Devotional Songs",
                "Hindi Bhakti Songs",
                deity_bit,
                short,
                handle,
                "bhajan",
                "kirtan",
                mood or "temple",
            ]
        )
    else:
        description = f"""🙏 **{banner}!** 🙏

Experience the divine power, devotion, and grace of {deity_bit} through this powerful Telugu devotional anthem.

With majestic Telugu Carnatic vocals, sacred shloka chanting, temple bells, mridangam rhythms, and heartfelt bhakti, this song is crafted for daily prayer and peaceful listening.

✨ **ఈ గీతం ప్రత్యేకతలు**
- {highlights[0]}
- {highlights[1]}
- {highlights[2]}
- శక్తివంతమైన తెలుగు భక్తి సాహిత్యం
- గంభీరమైన సంగీతం, భక్తిభావం
{f"- {topic_line}" if topic_line and "Seasonal mood" not in topic_line and "Kartika" not in topic_line and "Deepavali" not in topic_line else ""}

🙏 శ్రీ {deity_bit} వారి కృప అందరిపై ఉండాలని ప్రార్థిస్తున్నాము.

మీకు ఈ పాట నచ్చితే Like చేయండి, మీ కుటుంబ సభ్యులతో Share చేయండి, మరిన్ని తెలుగు భక్తిగీతాల కోసం **{handle}** ఛానల్‌ను Subscribe చేయండి.

**జై శ్రీ {deity_bit}!** 🙏
""".strip()
        tag_bits = [
            deity_bit.replace(" ", ""),
            "TeluguDevotionalSongs",
            "TeluguBhaktiSongs",
            "RagamSpiritualTelugu",
            "Bhakti",
            "CarnaticDevotional",
            mood.replace(" ", "") if mood else "TempleBhajan",
        ]
        tags = ",".join(
            [
                "Telugu Devotional Songs",
                "Telugu Bhakti Songs",
                deity_bit,
                short,
                handle,
                "bhajan",
                "keerthana",
                mood or "temple",
            ]
        )

    description = re.sub(r"\n- \n", "\n", description)
    description = re.sub(r"\n{3,}", "\n\n", description)
    hashtags = " ".join(f"#{t}" for t in tag_bits if t)
    description = f"{description}\n\n{hashtags}"

    return {
        "title": hook[:200],
        "youtube_title": yt_title[:100],
        "youtube_description": description,
        "youtube_tags": tags[:500],
        "telugu_title": hook[:80],
        "hook_title": hook[:80],
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
    count: int = 1,
    language: str | None = "te",
    channel_key: str | None = None,
) -> list[dict[str, Any]]:
    """Shorts metadata from Pallavi hook (visual/audio cut separately)."""
    n_shorts = max(1, min(2, int(count or 1)))
    deity_bit = deity or "Divine"
    hindi = _is_hindi(language, channel_key)
    handle, _short = _brand(language, channel_key)
    hook_title = _hook_title(
        title or youtube_title, max_chars=48, language=language, channel_key=channel_key
    )
    verses = list(charanams or [])
    pallavi_body = (verses[0].strip() if verses else "") or hook_title
    while len(verses) < n_shorts:
        verses.append(pallavi_body)

    link_line = (
        f"\n\n▶ Full song: {main_url}"
        if main_url
        else "\n\n▶ Full song on our channel (link added after long-form publish)."
    )

    tag_lang = "#HindiDevotional" if hindi else "#TeluguDevotional"
    brand_tag = "#DevotionalSongsHindi" if hindi else "#RagamSpiritualTelugu"

    shorts: list[dict[str, Any]] = []
    for n in range(1, n_shorts + 1):
        verse = pallavi_body
        hook = charanam_hook(verse, max_chars=160)
        suffix = " | Pallavi"
        core = hook_title[: max(1, 100 - len(suffix))]
        shorts.append(
            {
                "slot_index": n,
                "title": f"{core}{suffix}",
                "hook": hook,
                "description": (
                    f"🙏 **Pallavi** — {hook_title}\n\n{verse[:900]}\n\n"
                    f"Full song on {handle}."
                    f"{link_line}\n\n#Shorts {tag_lang} #{deity_bit.replace(' ', '')} "
                    f"{brand_tag}"
                ),
                "section": "pallavi",
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
    lock_title: bool = False,
) -> dict[str, str]:
    """Refresh YouTube package + Shorts copy from latest lyrics."""
    seed_title = (gemini_title or song.title or "").strip()
    language = getattr(song, "language", None) or "te"
    channel_key = getattr(song, "channel_key", None) or "te"
    meta = fill_youtube_longform(
        title=seed_title,
        deity=getattr(song, "deity", None),
        topic=topic if topic is not None else getattr(song, "notes", None),
        mood=mood or getattr(song, "visual_style", None),
        lyrics_excerpt=(lyrics or "")[:500],
        lyrics_full=lyrics,
        lock_title=lock_title,
        language=language,
        channel_key=channel_key,
    )
    song.title = meta["title"]
    song.youtube_title = meta["youtube_title"]
    song.youtube_description = meta["youtube_description"]
    song.youtube_tags = meta["youtube_tags"]

    if refresh_shorts and getattr(song, "shorts", None) is not None:
        sections = extract_sections(lyrics)
        pallavi = (sections.get("pallavi") or meta["title"] or "").strip()
        defs = fill_shorts_pair(
            title=meta["title"],
            deity=song.deity,
            main_url=getattr(song, "youtube_url", None),
            youtube_title=meta["youtube_title"],
            youtube_description=meta["youtube_description"],
            charanams=[pallavi] if pallavi else None,
            language=language,
            channel_key=channel_key,
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
