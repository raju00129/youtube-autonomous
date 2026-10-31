"""Pick the right YouTube playlist from deity / daypart / content type."""

from __future__ import annotations

from typing import Any

# Preferred playlist *titles* on the channel (matched case-insensitively / contains).
# Create these playlists on YouTube (or rename existing ones to match).
DEITY_PLAYLIST_TITLES: dict[str, list[str]] = {
    "shiva": ["Shiva", "Lord Shiva", "Shaiva", "Mahadev"],
    "parvati": ["Parvati", "Ambika", "Uma", "Devi"],
    "hanuman": ["Hanuman", "Anjaneya", "Bajrang"],
    "subrahmanya": ["Subrahmanya", "Kartikeya", "Murugan", "Skanda"],
    "krishna": ["Krishna", "Lord Krishna", "Gopala"],
    "sri rama": ["Sri Rama", "Rama", "Kodanda Rama", "Sita Rama"],
    "rama": ["Rama", "Sri Rama"],
    "narasimha": ["Narasimha", "Narasimha Swamy", "Ahobilam", "Lakshmi Narasimha"],
    "sri vishnu": ["Sri Vishnu", "Vishnu", "Narayana", "Perumal"],
    "vishnu": ["Vishnu", "Narayana", "Sri Vishnu"],
    "lakshmi": ["Lakshmi", "Sri Devi", "Goddess", "Ammavaru"],
    "saraswati": ["Saraswati", "Sharada", "Vagdevi"],
    "durga": ["Durga", "Chandika", "Devi", "Amman"],
    "venkateswara": ["Venkateswara", "Tirupati", "Balaji", "Govinda"],
    "ganesha": ["Ganesha", "Ganapati", "Vinayaka"],
    "surya narayana": ["Surya", "Aditya", "Suprabhatam"],
    "ayyappa": ["Ayyappa", "Sabarimala", "Hariharaputra"],
    "annapurna": ["Annapurna", "Annapoorna", "Devi"],
}

DAYPART_PLAYLIST_TITLES = {
    "morning": ["Morning Devotional", "Suprabhatam", "Morning Bhajans", "Morning"],
    "evening": ["Evening Aarti", "Evening Devotional", "Sandhya", "Evening"],
}

SHORTS_PLAYLIST_TITLES = ["Shorts", "YT Shorts", "Devotional Shorts", "Reels"]
DEFAULT_PLAYLIST_TITLES = ["Telugu Devotional", "Devotional Songs", "All Songs", "Ragam Spiritual"]


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _match_titles(candidates: list[str], playlists: list[dict[str, str]]) -> dict[str, str] | None:
    """Return {id, title} for first playlist whose title contains any candidate token."""
    for cand in candidates:
        c = _norm(cand)
        if not c:
            continue
        for pl in playlists:
            title = _norm(pl.get("title") or "")
            if c in title or title in c:
                return {"id": pl["id"], "title": pl["title"], "matched_on": cand}
    return None


def deity_key(deity: str | None) -> str:
    return _norm(deity or "")


def suggest_playlist_names(*, deity: str | None, daypart: str | None = None) -> list[str]:
    """Ordered preferred titles to create/match on the channel."""
    key = deity_key(deity)
    names: list[str] = []
    for dkey, titles in DEITY_PLAYLIST_TITLES.items():
        if dkey in key or key in dkey:
            names.extend(titles)
            break
    if daypart in DAYPART_PLAYLIST_TITLES:
        names.extend(DAYPART_PLAYLIST_TITLES[daypart])
    names.extend(DEFAULT_PLAYLIST_TITLES)
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def pick_playlist(
    *,
    deity: str | None,
    daypart: str | None,
    channel_playlists: list[dict[str, str]],
    for_shorts: bool = False,
) -> dict[str, Any]:
    """
    Pick best playlist from live channel list.
    Returns id/title if matched; otherwise suggested_title to create.
    """
    if for_shorts:
        hit = _match_titles(SHORTS_PLAYLIST_TITLES, channel_playlists)
        suggested = SHORTS_PLAYLIST_TITLES[0]
        if hit:
            return {
                "playlist_id": hit["id"],
                "playlist_title": hit["title"],
                "reason": f"Shorts playlist matched '{hit['matched_on']}'",
                "suggested_title": suggested,
                "matched": True,
            }
        return {
            "playlist_id": None,
            "playlist_title": suggested,
            "reason": "No Shorts playlist on channel yet — create one named 'Shorts'",
            "suggested_title": suggested,
            "matched": False,
        }

    preferred = suggest_playlist_names(deity=deity, daypart=daypart)
    hit = _match_titles(preferred, channel_playlists)
    if hit:
        return {
            "playlist_id": hit["id"],
            "playlist_title": hit["title"],
            "reason": f"Matched deity/daypart preference '{hit['matched_on']}'",
            "suggested_title": preferred[0] if preferred else DEFAULT_PLAYLIST_TITLES[0],
            "matched": True,
            "candidates": preferred[:5],
        }

    suggested = preferred[0] if preferred else DEFAULT_PLAYLIST_TITLES[0]
    return {
        "playlist_id": None,
        "playlist_title": suggested,
        "reason": (
            f"No matching playlist for {deity or 'song'} — "
            f"create playlist titled '{suggested}' (or map an existing ID)"
        ),
        "suggested_title": suggested,
        "matched": False,
        "candidates": preferred[:5],
    }


def apply_playlists_to_song(
    song: Any,
    *,
    daypart: str | None,
    channel_playlists: list[dict[str, str]],
) -> dict[str, Any]:
    """Set long-form playlist; Shorts reuse the same playlist as the main video."""
    longform = pick_playlist(
        deity=getattr(song, "deity", None),
        daypart=daypart,
        channel_playlists=channel_playlists,
        for_shorts=False,
    )
    # Shorts are cuts of the same song — land in the same deity/daypart playlist.
    shorts = {
        "playlist_id": longform.get("playlist_id"),
        "playlist_title": longform.get("playlist_title"),
        "reason": "Same playlist as main long-form (Shorts reuse main content)",
        "suggested_title": longform.get("suggested_title"),
        "matched": longform.get("matched"),
        "same_as_longform": True,
    }
    song.youtube_playlist_id = longform.get("playlist_id")
    song.youtube_playlist_title = longform.get("playlist_title")
    song.shorts_playlist_id = shorts.get("playlist_id")
    song.shorts_playlist_title = shorts.get("playlist_title")
    return {"longform": longform, "shorts": shorts}
