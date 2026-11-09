"""Parse keerthana sections from lyrics body (Pallavi / Charanam / …)."""

from __future__ import annotations

import re


_BRACKET_RE = re.compile(
    r"^\s*\[(?P<label>[^\]]+)\]\s*$",
    flags=re.MULTILINE,
)
# Telugu decorative headers: ॥ పల్లవి ॥ / ॥ చరణం – 1 ॥ — strip from Suno lyrics
_TELUGU_HEADER_RE = re.compile(
    r"^\s*॥\s*(?P<label>[^॥]+?)\s*॥\s*$",
    flags=re.MULTILINE,
)


def sanitize_suno_lyrics(lyrics: str | None) -> str:
    """Remove Telugu ॥ section headers so Suno does not sing them.

    Keeps English [Pallavi]-style tags and sung Telugu lines.
    """
    if not lyrics:
        return ""
    out: list[str] = []
    for raw in lyrics.splitlines():
        s = raw.rstrip()
        if _TELUGU_HEADER_RE.match(s.strip()):
            continue
        out.append(s)
    # Collapse 3+ blank lines
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text + ("\n" if text else "")

# Stage-direction / cue sections — not sung stanzas for Shorts windows
_CUE_LABELS = frozenset(
    {
        "orchestra enter",
        "full carnatic orchestra enters",
        "sanskrit chant cue",
        "deep sanskrit chant",
        "deep sanskrit chant – traditional male voice",
        "deep sanskrit chant – traditional female voice",
        "deep sanskrit chant - traditional male voice",
        "deep sanskrit chant - traditional female voice",
    }
)


def _normalize_label(raw: str) -> str:
    label = re.sub(r"\s+", " ", (raw or "").strip()).lower()
    label = label.replace("–", "-").replace("—", "-")
    # Strip English stage suffixes after em dash / hyphen for opening hook etc.
    # Keep charanam numbers.

    # Telugu → English canonical keys
    telugu_map = (
        (r"^పల్లవి(\s*[-–—]?\s*ముగింపు)?$", "pallavi"),
        (r"^అనుపల్లవి$", "anupallavi"),
        (r"^(సంస్కృత\s*)?శ్లోకం$", "slokam"),
        (r"^చరణం\s*[-–—]?\s*1$", "charanam 1"),
        (r"^చరణం\s*[-–—]?\s*2$", "charanam 2"),
        (r"^చరణం\s*[-–—]?\s*3$", "charanam 3"),
        (r"^చరణం$", "charanam"),
    )
    for pat, canon in telugu_map:
        if re.match(pat, label):
            return canon

    if label.startswith("opening hook"):
        return "opening hook"
    if label.startswith("orchestra"):
        return "orchestra enter"
    if "sanskrit chant" in label:
        return "sanskrit chant cue"
    if label.startswith("grand chorus") or label.startswith("grand devotional chorus"):
        return "grand chorus"
    if label.startswith("pallavi"):
        return "pallavi"
    if label.startswith("anupallavi"):
        return "anupallavi"
    if label.startswith("slokam") or label.startswith("sloka"):
        return "slokam"
    m = re.match(r"charanam\s*[-]?\s*(\d+)", label)
    if m:
        return f"charanam {m.group(1)}"
    if label == "charanam":
        return "charanam"
    return label


def _clean_lines(block: str) -> list[str]:
    lines: list[str] = []
    for raw in block.splitlines():
        s = raw.strip()
        if not s or s.startswith("["):
            continue
        # Skip Telugu decorative headers inside a section body
        if _TELUGU_HEADER_RE.match(s):
            continue
        # Skip pure English cue sentences that leaked into body
        low = s.lower()
        if low.startswith("full carnatic orchestra") or low.startswith("deep sanskrit chant"):
            continue
        lines.append(s)
    return lines


def _iter_section_matches(lyrics: str) -> list[tuple[int, int, str]]:
    """List of (start_content, end_marker_pos, normalized_label) via bracket + Telugu headers."""
    markers: list[tuple[int, int, str]] = []
    for m in _BRACKET_RE.finditer(lyrics):
        markers.append((m.start(), m.end(), _normalize_label(m.group("label"))))
    for m in _TELUGU_HEADER_RE.finditer(lyrics):
        markers.append((m.start(), m.end(), _normalize_label(m.group("label"))))
    markers.sort(key=lambda t: t[0])

    # Dedupe overlapping markers at same position (prefer bracket)
    deduped: list[tuple[int, int, str]] = []
    for item in markers:
        if deduped and abs(item[0] - deduped[-1][0]) < 2:
            continue
        deduped.append(item)
    return deduped


def extract_sections(lyrics: str | None) -> dict[str, str]:
    """Return map of normalized section label → body text.

    Repeated labels (Pallavi cycles) keep the first non-empty body
    (all Pallavi repeats should be identical).
    """
    if not lyrics or not lyrics.strip():
        return {}
    matches = _iter_section_matches(lyrics)
    if not matches:
        return {"body": lyrics.strip()}

    out: dict[str, str] = {}
    for i, (_start, content_start, label) in enumerate(matches):
        end = matches[i + 1][0] if i + 1 < len(matches) else len(lyrics)
        body = "\n".join(_clean_lines(lyrics[content_start:end])).strip()
        if not body:
            continue
        if label in _CUE_LABELS:
            continue
        # First wins for repeated Pallavi / identical keys
        if label not in out:
            out[label] = body
    return out


def extract_charanams(lyrics: str | None, *, limit: int = 2) -> list[str]:
    """Ordered Charanam bodies (Charanam 1, 2, …). Falls back to Pallavi / body."""
    sections = extract_sections(lyrics)
    found: list[tuple[int, str]] = []
    for key, body in sections.items():
        m = re.match(r"charanam\s*(\d+)", key, flags=re.IGNORECASE)
        if m:
            found.append((int(m.group(1)), body))
    found.sort(key=lambda t: t[0])
    charanams = [body for _, body in found]

    if len(charanams) < limit:
        for key, body in sections.items():
            if key == "charanam" and body not in charanams:
                charanams.append(body)
            if len(charanams) >= limit:
                break

    if len(charanams) < limit:
        for key in ("pallavi", "anupallavi", "opening hook", "grand chorus", "slokam", "body"):
            body = sections.get(key)
            if body and body not in charanams:
                charanams.append(body)
            if len(charanams) >= limit:
                break

    while len(charanams) < limit:
        charanams.append(charanams[-1] if charanams else "Ragam Spiritual bhakti")

    return charanams[:limit]


def charanam_hook(text: str, *, max_chars: int = 120) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "Ragam Spiritual"
    joined = " ".join(lines[:2]).strip()
    return joined[:max_chars]


def _section_weight(body: str) -> int:
    """Rough sung-length proxy: non-empty lines × chars (min 1)."""
    lines = [ln for ln in body.splitlines() if ln.strip()]
    chars = sum(len(ln) for ln in lines) or len(body.strip()) or 1
    return max(chars, len(lines) * 24, 1)


def ordered_keerthana_sections(lyrics: str | None) -> list[tuple[str, str]]:
    """Song order: Opening → Pallavi → Anupallavi → Slokam → Charanams → Grand Chorus."""
    sections = extract_sections(lyrics)
    if not sections:
        return []

    ordered: list[tuple[str, str]] = []
    used: set[str] = set()

    for key in ("opening hook", "pallavi", "anupallavi", "slokam"):
        body = sections.get(key)
        if body:
            ordered.append((key, body))
            used.add(key)

    numbered: list[tuple[int, str, str]] = []
    for key, body in sections.items():
        m = re.match(r"charanam\s*(\d+)$", key, flags=re.IGNORECASE)
        if m:
            numbered.append((int(m.group(1)), key, body))
            used.add(key)
    for _, key, body in sorted(numbered, key=lambda t: t[0]):
        ordered.append((key, body))

    if "charanam" in sections and "charanam" not in used:
        ordered.append(("charanam", sections["charanam"]))
        used.add("charanam")

    if "grand chorus" in sections and "grand chorus" not in used:
        ordered.append(("grand chorus", sections["grand chorus"]))
        used.add("grand chorus")

    for key, body in sections.items():
        if key in used or key == "body":
            continue
        ordered.append((key, body))

    if not ordered and sections.get("body"):
        ordered.append(("body", sections["body"]))

    return ordered


def estimate_section_windows(
    lyrics: str | None,
    audio_duration_sec: float,
    *,
    intro_frac: float = 0.08,
    outro_frac: float = 0.04,
) -> dict[str, tuple[float, float]]:
    """Map lyric sections → approximate [start, end] seconds on the full audio.

    Weights by lyric length. Reserves a short intro/outro for instrumental.
    """
    dur = max(float(audio_duration_sec or 0), 1.0)
    sections = ordered_keerthana_sections(lyrics)
    if not sections:
        intro = dur * intro_frac
        outro = dur * outro_frac
        usable = max(dur - intro - outro, 1.0)
        mid = intro + usable / 2
        return {
            "charanam 1": (intro, mid),
            "charanam 2": (mid, dur - outro),
        }

    intro = min(dur * intro_frac, 12.0)
    outro = min(dur * outro_frac, 8.0)
    usable = max(dur - intro - outro, 1.0)
    weights = [_section_weight(body) for _, body in sections]
    total_w = float(sum(weights)) or 1.0

    windows: dict[str, tuple[float, float]] = {}
    t = intro
    for (key, _body), w in zip(sections, weights, strict=True):
        seg = usable * (w / total_w)
        windows[key] = (t, t + seg)
        t += seg
    return windows


def _clip_around_segment(
    start: float,
    end: float,
    *,
    dur: float,
    clip: float,
) -> tuple[float, float]:
    start = max(0.0, min(start, dur))
    end = max(start + 0.5, min(end, dur))
    seg_len = end - start

    if seg_len <= clip:
        mid = (start + end) / 2.0
        half = clip / 2.0
        a = mid - half
        b = mid + half
        if a < 0:
            a, b = 0.0, clip
        if b > dur:
            a, b = max(0.0, dur - clip), dur
        return round(a, 2), round(b, 2)

    mid = (start + end) / 2.0
    half = clip / 2.0
    a = mid - half
    b = mid + half
    if a < start:
        a, b = start, start + clip
    if b > end:
        a, b = end - clip, end
    a = max(0.0, a)
    b = min(dur, max(a + 1.0, b))
    return round(a, 2), round(b, 2)


def pallavi_audio_window(
    lyrics: str | None,
    audio_duration_sec: float,
    *,
    clip_sec: float = 29.0,
) -> tuple[float, float]:
    """Start/end (sec) for a Short: middle of Pallavi (hook/chorus).

    Prefer the sung Pallavi window over Charanam — strongest nama hook for Shorts.
    Falls back to opening-hook, then early track if structure is missing.
    """
    dur = max(float(audio_duration_sec or 0), 1.0)
    clip = max(3.0, min(float(clip_sec), 29.0, dur))
    windows = estimate_section_windows(lyrics, dur)

    seg: tuple[float, float] | None = None
    for key in ("pallavi", "opening hook", "anupallavi", "grand chorus"):
        if key in windows:
            seg = windows[key]
            break
    if seg is None:
        # Early song = where Pallavi usually lives after a short intro
        intro = min(dur * 0.08, 12.0)
        seg = (intro, min(dur, intro + max(clip, dur * 0.18)))

    return _clip_around_segment(seg[0], seg[1], dur=dur, clip=clip)


def charanam_audio_window(
    lyrics: str | None,
    audio_duration_sec: float,
    *,
    charanam_index: int,
    clip_sec: float = 29.0,
) -> tuple[float, float]:
    """Start/end (sec) for a Short: middle of Charanam N (legacy; prefer pallavi_audio_window)."""
    dur = max(float(audio_duration_sec or 0), 1.0)
    clip = max(3.0, min(float(clip_sec), 29.0, dur))
    windows = estimate_section_windows(lyrics, dur)

    key_candidates = [
        f"charanam {charanam_index}",
        f"charanam{charanam_index}",
        "charanam" if charanam_index == 1 else "",
    ]
    seg: tuple[float, float] | None = None
    for key in key_candidates:
        if key and key in windows:
            seg = windows[key]
            break
    if seg is None:
        numbered = sorted(
            ((k, v) for k, v in windows.items() if re.match(r"charanam\s*\d+", k)),
            key=lambda kv: int(re.search(r"\d+", kv[0]).group())  # type: ignore[union-attr]
            if re.search(r"\d+", kv[0])
            else 0,
        )
        if numbered and charanam_index - 1 < len(numbered):
            seg = numbered[charanam_index - 1][1]
        else:
            items = list(windows.values())
            if charanam_index - 1 < len(items):
                seg = items[charanam_index - 1]
            else:
                third = dur / 3.0
                if charanam_index <= 1:
                    seg = (third * 0.85, third * 1.85)
                else:
                    seg = (third * 1.85, third * 2.85)

    return _clip_around_segment(seg[0], seg[1], dur=dur, clip=clip)
