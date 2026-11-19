"""Suno style-prompt helpers — language-aware diction / pronunciation quality tags."""

from __future__ import annotations


_TE_STYLE_QUALITY_TAGS = (
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

_HI_STYLE_QUALITY_TAGS = (
    "authentic Hindi language vocals",
    "native Hindi pronunciation",
    "crystal clear Hindi diction",
    "perfect Hindi enunciation",
    "no accent issues",
    "singable Hindi Devanagari syllables",
    "studio-quality vocal take",
    "no mumbled words",
    "lyrics fully intelligible in Hindi",
)


def _is_hindi(language: str | None) -> bool:
    return (language or "te").strip().lower().startswith("hi")


def enrich_style_prompt(
    style: str | None, *, vocal: str | None = None, language: str | None = "te"
) -> str:
    """Keep pronunciation / vocal-quality tags for the song language in the Suno style field."""
    base = (style or "").strip()
    lower = base.lower()
    bits = [base] if base else []
    vocal_label = "female" if vocal == "f" else "male"
    if _is_hindi(language):
        must = [
            f"{vocal_label} native Hindi bhajan vocalist",
            "traditional Hindi temple bhajan",
            *_HI_STYLE_QUALITY_TAGS,
        ]
    else:
        must = [
            f"{vocal_label} native Telugu Carnatic bhajan vocalist",
            "traditional Telugu temple keerthana",
            *_TE_STYLE_QUALITY_TAGS,
        ]
    for tag in must:
        if tag.lower() not in lower:
            bits.append(tag)
            lower = f"{lower}, {tag.lower()}"
    out = ", ".join(b for b in bits if b).strip(", ")
    return out[:1000]


def default_style(
    deity: str | None,
    genre: str | None,
    vocal: str | None,
    *,
    language: str | None = "te",
) -> str:
    if _is_hindi(language):
        bits = [
            "traditional Hindi classical bhajan",
            "temple bhajan atmosphere",
            "tanpura drone",
            "soft tabla and manjira",
            "serene reverent mood",
            "classical bhajan ornamentation",
        ]
    else:
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
    return enrich_style_prompt(", ".join(bits), vocal=vocal, language=language)
