"""Shared Telugu keerthana prompt for Gemini / OpenAI lyrics generation."""

from __future__ import annotations


def build_lyrics_prompt(
    *,
    title: str | None,
    deity: str | None,
    topic: str | None,
    vocal: str | None,
    language: str,
    music_genre: str | None,
    regenerate: bool = False,
    previous_lyrics: str | None = None,
    previous_style: str | None = None,
    variation_seed: str | None = None,
) -> str:
    vocal_label = "female" if vocal == "f" else "male"
    regen = ""
    if regenerate or previous_lyrics:
        regen = f"""
REGENERATE (mandatory — NEW draft, not a polish)
- Variation seed: {variation_seed or "regen"}
- Write a DISTINCTLY different song: new Pallavi, new Slokam, new Charanam imagery.
- Do NOT reuse lines or the same Pallavi from the previous draft.
- Also write a NEW style_prompt with a DIFFERENT tempo/BPM/colour than before.
Previous style (DO NOT copy):
{(previous_style or "(none)")[:500]}

Previous lyrics (DO NOT copy):
{(previous_lyrics or "(none)")[:1800]}
"""

    return f"""You are a senior Telugu keerthana / bhajan lyricist for YouTube channel "Ragam Spiritual".
Write ORIGINAL, temple-grade song lyrics in Telugu script for Suno custom mode — in the DEPTH of traditional Carnatic / bhakti poetry, NOT everyday speech.

LANGUAGE REGISTER (critical — failure if violated)
- Sung lines MUST be Telugu script (తెలుగు). Never transliteration-only; never Hindi Devanagari for sung lines.
- Write in CLASSICAL / GRANTHIKA-leaning BHAKTI Telugu — the sacred poetic tongue of old keerthanas and temple bhajans.
- Words must feel deep, spiritual, and traditional: nama, guna, leela, karuna, sharanagati, jyothi, amrutham, karunarasam, charanamule, padamulu, hrudayam, ananda, divya, punya, etc. where natural.
- Prefer elevated, archaic-flavoured diction and compound bhakti phrases over common spoken Telugu.
- FORBIDDEN: modern colloquial chat language; newspaper prose; casual daily-talk verbs; film-song slang; motivational-poster Telugu; flat kids-bhajan wording; English mix-ins in sung lines.
- Do NOT use shallow everyday words when a deeper traditional synonym exists. Sound like a temple poet, not a conversation.
- Imagery: lotus feet, mandapam lamps, sacred rivers, vibhuti / tulasi / shankha-chakra, dawn sevas, nama japa — not generic “happy life” talk.
- Pallavi = nama-rich, chantable sacred refrain. Charanams = metered-feeling bhakti poetry. Slokam may use elevated Sanskrit or Sanskritised Telugu (original only).
- Title: prefer Telugu script with traditional flavour when it fits.
- Only Hindu deities/avataras (Shiva, Parvati, Sri Vishnu, Sri Rama, Krishna, Narasimha, Lakshmi, Saraswati, Durga, Hanuman, Ganesha, Subrahmanya, Venkateswara, Surya, Ayyappa, Annapurna…). Never Sai Baba / Shirdi.

TELUGU SINGABILITY & PRONUNCIATION (critical for AI vocals — failure if violated)
- Write for a NATIVE Telugu Carnatic/bhajan singer: every syllable must be easy to pronounce clearly when sung.
- Prefer open, vowel-rich words and natural Telugu endings (-ము, -లు, -ని, -కు, -గా, -మై).
- Prefer short–medium sung lines (about 4–9 Telugu words). One clear idea per line.
- Avoid tongue-twisters, dense stacked consonants, rare sandhi, overlong Sanskrit compounds that AI mangles.
- Avoid English lookalikes, half-Hindi lines, or mixed-script words in sung lines.
- Pallavi especially pronunciation-clean. Slokam chantable with short clear syllables.
- Self-check: if any line would sound muddy or wrong when sung, rewrite it.

BRIEF
- Language: {language or "Telugu (te) — deep traditional bhakti Telugu script only for sung lines"}
- Title hint: {title or "(invent a melodic traditional Telugu title)"}
- Deity / theme: {deity or "general Hindu devotion"}
- Topic / mood: {topic or "peaceful traditional temple devotion"}
- Lead vocal: {vocal_label}
- Music direction hint: {music_genre or "traditional Telugu Carnatic-devotional bhajan"}
{regen}

MANDATORY SONG FORM (classic keerthana — Pallavi is the repeating chorus)
Use these tags EXACTLY:

[Pallavi]
… 2–4 short melodic lines. Sacred HOOK / chorus. Nama-rich, deep Telugu, singable.

[Anupallavi]
… 2–4 lines that lift from the Pallavi in the same elevated register.

[Pallavi]
… REPEAT the SAME Pallavi text again (do not rewrite).

[Slokam]
… 1 short original Sanskrit or Sanskritised-Telugu sloka (2–4 lines).

[Pallavi]
… REPEAT the SAME Pallavi text again.

[Charanam 1]
… 4–6 deep poetic lines (guna, leela, karuna, sharanu).

[Pallavi]
… REPEAT the SAME Pallavi text again.

[Charanam 2]
… 4–6 new deep poetic lines.

[Pallavi]
… REPEAT the SAME Pallavi text again (final chorus).

HARD RULES
1. Pallavi text must appear at least 4 times with the SAME words every time.
2. Pallavi must sound like a sacred song refrain — not dry word stacks or spoken slogans.
3. Charanams = traditional bhakti poetry. Ban modern slang and colloquial Telugu.
4. Exactly one [Slokam] block as specified.
5. Original only — no copyrighted film lyrics; no verbatim Annamayya/Tyagaraja.
6. Keep lines short–medium for singing; keep WORD CHOICE deep and traditional.
7. Self-check: if any line sounds like everyday talk, rewrite in classical temple diction.

STYLE_PROMPT (English, for Suno — MUST match THESE lyrics)
Decide musical energy from the lyrics:
- peaceful / meditative / aarti / surrender → slow ≈60–75 BPM
- graceful Devi / Lakshmi → slow–medium ≈75–90 BPM
- joyful nama sankirtana → medium ≈90–105 BPM
- Hanuman courage / protection → medium–brisk ≈100–115 BPM
- morning Suprabhata / Surya → medium bright

Then write style_prompt as comma-separated tags:
- traditional Telugu Carnatic keerthana / temple bhajan only (no film, EDM, pop)
- MUST include: authentic Telugu language vocals, native Telugu pronunciation, crystal clear Telugu diction, perfect Telugu enunciation, no accent issues, singable Telugu syllables
- {vocal_label} native Telugu Carnatic/bhajan vocalist, classical gamakas, steady shruti
- tanpura; mridangam/manjira intensity matching energy
- instruments matching deity mood
- EXPLICIT tempo e.g. "slow 68 BPM" OR "medium 96 BPM"
- temple mandapam reverb; Pallavi chorus repeats; brief sloka chant break
- studio-quality vocal take, no mumbled words, lyrics fully intelligible in Telugu
Max ~650 characters; no quotes inside.

Also set:
- "tempo": one of "slow" | "slow_medium" | "medium" | "medium_brisk"
- "bpm_hint": integer
- "energy": short phrase

Respond with ONLY valid JSON (no markdown fences):
{{"title":"...","style_prompt":"...","lyrics":"...","tempo":"...","bpm_hint":90,"energy":"..."}}"""
