"""Parse keerthana sections from lyrics body (Pallavi / Charanam / …)."""

from __future__ import annotations

import re


_SECTION_RE = re.compile(
    r"^\s*\[(?P<label>[^\]]+)\]\s*$",
    flags=re.MULTILINE,
)


def _clean_lines(block: str) -> list[str]:
    lines: list[str] = []
    for raw in block.splitlines():
        s = raw.strip()
        if not s or s.startswith("["):
            continue
        lines.append(s)
    return lines


def extract_sections(lyrics: str | None) -> dict[str, str]:
    """Return map of normalized section label → body text."""
    if not lyrics or not lyrics.strip():
        return {}
    matches = list(_SECTION_RE.finditer(lyrics))
    if not matches:
        return {"body": lyrics.strip()}

    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        label = re.sub(r"\s+", " ", m.group("label")).strip().lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(lyrics)
        body = "\n".join(_clean_lines(lyrics[start:end])).strip()
        if body:
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
        # Accept unlabeled "charanam" once
        for key, body in sections.items():
            if key == "charanam" and body not in charanams:
                charanams.append(body)
            if len(charanams) >= limit:
                break

    if len(charanams) < limit:
        for key in ("pallavi", "anupallavi", "slokam", "body"):
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
    """Song order: Pallavi → Anupallavi → Slokam → Charanam 1 → Charanam 2 → …"""
    sections = extract_sections(lyrics)
    if not sections:
        return []

    ordered: list[tuple[str, str]] = []
    used: set[str] = set()

    for key in ("pallavi", "anupallavi", "slokam"):
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
        # No structure: split usable middle into two equal halves for Short 1/2
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


def charanam_audio_window(
    lyrics: str | None,
    audio_duration_sec: float,
    *,
    charanam_index: int,
    clip_sec: float = 29.0,
) -> tuple[float, float]:
    """Start/end (sec) for a Short: middle of Charanam N (falls back to split halves)."""
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
        # Prefer any numbered charanam in order; else N-th section; else equal split
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
                # Equal thirds of song; take middle third pieces
                third = dur / 3.0
                if charanam_index <= 1:
                    seg = (third * 0.85, third * 1.85)
                else:
                    seg = (third * 1.85, third * 2.85)

    start, end = seg
    start = max(0.0, min(start, dur))
    end = max(start + 0.5, min(end, dur))
    seg_len = end - start

    if seg_len <= clip:
        # Expand around segment center within full track if stanza is shorter than Short
        mid = (start + end) / 2.0
        half = clip / 2.0
        a = mid - half
        b = mid + half
        if a < 0:
            a, b = 0.0, clip
        if b > dur:
            a, b = max(0.0, dur - clip), dur
        return round(a, 2), round(b, 2)

    # Middle of the stanza
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
