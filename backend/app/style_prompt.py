"""Suno style-prompt helpers — Telugu diction / pronunciation quality tags."""

from __future__ import annotations

_STYLE_QUALITY_TAGS = (
    "authentic Telugu language vocals",
    "native Telugu pronunciation",
    "crystal clear Telugu diction",
    "perfect Telugu enunciation",
    "no accent issues",
    "singable Telugu syllables",
    "studio-quality vocal take",
    "no mumbled words",
    "lyrics fully intelligible in Telugu",
)


def enrich_style_prompt(style: str | None, *, vocal: str | None = None) -> str:
    """Always keep Telugu pronunciation / vocal-quality tags in the Suno style field."""
    base = (style or "").strip()
    lower = base.lower()
    bits = [base] if base else []
    vocal_label = "female" if vocal == "f" else "male"
    must = [
        f"{vocal_label} native Telugu Carnatic bhajan vocalist",
        "traditional Telugu temple keerthana",
        *_STYLE_QUALITY_TAGS,
    ]
    for tag in must:
        if tag.lower() not in lower:
            bits.append(tag)
            lower = f"{lower}, {tag.lower()}"
    out = ", ".join(b for b in bits if b).strip(", ")
    return out[:1000]


def default_style(deity: str | None, genre: str | None, vocal: str | None) -> str:
    bits = [
        "traditional Telugu Carnatic keerthana",
        "temple bhajan atmosphere",
        "tanpura drone",
        "soft mridangam and manjira",
        "serene reverent mood",
        "classical gamakas",
    ]
    if deity:
        bits.append(f"devotion to {deity}")
    if genre:
        bits.append(genre)
    return enrich_style_prompt(", ".join(bits), vocal=vocal)
