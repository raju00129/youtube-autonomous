"""Shared Telugu keerthana prompt for Gemini / OpenAI lyrics generation."""

from __future__ import annotations


SONG_FORM_BLOCK = """
MANDATORY SONG FORM (premium Rama-style keerthana arc — follow this shape exactly)
Use ONLY English bracket tags like [Pallavi], [Anupallavi], [Charanam 1].
FORBIDDEN in the lyrics body (Suno will sing them — never output these):
- Telugu section headers with dandas: ॥ పల్లవి ॥, ॥ అనుపల్లవి ॥, ॥ చరణం ॥, ॥ శ్లోకం ॥, etc.
- Any non-English section title lines. Tags must be English [Name] only.

[Opening Hook]
… 3–5 short nama-rich lines. Immediate {vocal_label} solo, a cappella feel —
NO orchestra yet. Pure voice calling the deity (e.g. రామా! రఘురామా! style for that deity).
Urgent, sacred, congregation-ready. Different from the Pallavi (shorter nama cascade).

[Orchestra Enter]
… Write ONLY this single cue line (no sung lyrics here):
Full Carnatic Orchestra Enters

[Pallavi]
… 3–4 short melodic lines. Sacred HOOK / repeating chorus. Nama-rich, deep Telugu,
singable; rhyme or assonance OK. This is the main refrain of the song.

[Anupallavi]
… 3–4 lines that lift from the Pallavi — guna / leela / karuna in elevated register.

[Pallavi]
… REPEAT the SAME Pallavi text again (do not rewrite).

[Slokam]
… 1 short ORIGINAL Sanskrit or Sanskritised-Telugu sloka (2–4 lines / one couplet)
praising THIS deity. Soft chant break. Not copied from famous stotras.

[Sanskrit Chant Cue]
… Write ONLY this single cue line (no new sung lyrics here):
Deep Sanskrit Chant – Traditional {vocal_label} Voice

[Pallavi]
… REPEAT the SAME Pallavi text again.

[Charanam 1]
… 6–8 deep poetic lines (guna, leela, karuna, sharanu). Traditional bhakti Telugu —
never prosaic speech. May use short stanza groups (4+4).

[Pallavi]
… REPEAT the SAME Pallavi text again.

[Charanam 2]
… 6–8 new deep poetic lines; return naturally toward Pallavi mood.

[Pallavi]
… REPEAT the SAME Pallavi text again (closing / ముగింపు chorus — same words).

[Grand Chorus]
… 3–5 short nama sankirtana lines — grand congregational close
(e.g. జయ జయ …! style for THIS deity). Climactic, joyful, temple-hall energy.
Not a copy of the Pallavi; a final nama burst that seals the song.

HARD RULES
1. Pallavi text must appear at least 4 times with the EXACT SAME words every time.
2. Opening Hook is NOT the Pallavi — it is a shorter a-cappella nama cascade before orchestra.
3. Grand Chorus is NOT a fifth Pallavi — it is a closing jaya/nama burst.
4. Include [Orchestra Enter] and [Sanskrit Chant Cue] exactly as cue lines (English OK there).
5. Sung lyric lines MUST be Telugu script (Slokam may be Sanskrit). Section tags and cue lines are English only.
6. NEVER write ॥ … ॥ Telugu headers — Suno sings them as lyrics. Use [Pallavi] etc. only.
7. Charanams = traditional bhakti poetry. Ban modern slang and colloquial Telugu.
8. Original only — no copyrighted film lyrics; no verbatim Annamayya/Tyagaraja.
9. Keep lines short–medium for singing; keep WORD CHOICE deep and traditional.
10. Self-check: if any line sounds like everyday talk, rewrite in classical temple diction.
""".strip()


UNIQUENESS_BLOCK = """
UNIQUENESS (critical — channel must not sound like the same song every day)
- Invent a FRESH angle for THIS draft. Do not default to a generic “morning wake-up / prabhata seva” template.
- Pick ONE distinct poetic focus and stay with it (examples — choose something NEW, not a list dump):
  leela scene, specific nama/guna, karuna plea, temple sthala mood, river/mountain abode,
  vibhuti-bilva-tulasi seva detail, dance/nataraja energy, cool moonlight, inner silence,
  sharanagati, guru-parampara gratitude, family lamp-row devotion, protective ugra-karuna, etc.
- Title MUST feel new — not a near-clone of recent channel titles. Prefer vivid, specific Telugu titles.
- Pallavi must NOT recycle stock openings like “ప్రభాత సమయాన…”, “ప్రాభాత సమయే…”, “ఉదయకాల…శివా”,
  or the same “లింగార్చన + ఓం నమః శివాయ + కాపాడుము” combo every Shiva song.
- FORBIDDEN cookie-cutter patterns unless the topic EXPLICITLY demands that exact scene:
  - Starting every morning song with ప్రభాత/ప్రాభాత/ఉదయం wake-up framing
  - Same 3–4 nama lines reshuffled as Pallavi across songs
  - Charanams that only say “you protect us / we surrender” with no fresh imagery
- Even if topic mentions “morning” or “aarti”, find a NEW metaphor (conch echo, cool stone floor,
  bilva fragrance, first lamp spark, silent mandapam before crowd — not “prabhata samayam” again).
- Vary rhyme/assonance shapes and line lengths vs a typical previous draft.
- Self-check: if this song could be mistaken for yesterday’s Shiva/morning song after changing 3 words, REWRITE.
""".strip()


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
    avoid_echo: str | None = None,
) -> str:
    vocal_label = "female" if vocal == "f" else "male"
    seed = variation_seed or "fresh"
    regen = ""
    if regenerate or previous_lyrics:
        regen = f"""
REGENERATE (mandatory — NEW draft, not a polish)
- Variation seed: {seed}
- Write a DISTINCTLY different song: new Opening Hook, new Pallavi, new Slokam, new Charanams, new Grand Chorus.
- Do NOT reuse lines or the same Pallavi from the previous draft.
- Also write a NEW style_prompt with a DIFFERENT tempo/BPM/colour than before.
Previous style (DO NOT copy):
{(previous_style or "(none)")[:500]}

Previous lyrics (DO NOT copy):
{(previous_lyrics or "(none)")[:1800]}
"""

    echo = ""
    if avoid_echo and avoid_echo.strip():
        echo = f"""
AVOID ECHOING THESE RECENT CHANNEL SONGS (do not reuse titles, Pallavi lines, or near-paraphrases):
{avoid_echo.strip()[:2200]}
"""

    form = SONG_FORM_BLOCK.format(vocal_label=vocal_label)

    return f"""You are a senior Telugu keerthana / bhajan lyricist for YouTube channel "Ragam Spiritual".
Write ORIGINAL, temple-grade song lyrics in Telugu script for Suno custom mode — in the DEPTH of traditional Carnatic / bhakti poetry, NOT everyday speech.
Variation seed for uniqueness: {seed}

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
- Write a beautiful timeless deity song. Do NOT force calendar festivals or month names (Kartika masam, Deepavali, Navaratri, etc.) unless the topic explicitly asks for that festival.
- Morning / daypart is ONLY a light mood hint — do NOT force a Suprabhata / ప్రభాత-సమయం song every time.
{regen}
{echo}

{UNIQUENESS_BLOCK}

{form}

STYLE_PROMPT (English, for Suno — MUST match THESE lyrics)
Decide musical energy from the lyrics, then write comma-separated tags that include this arc:
- opening: a cappella {vocal_label} solo nama hook, no instruments at first
- then full Carnatic orchestra enters under Pallavi
- brief deep Sanskrit chant break at Slokam
- grand congregational chorus finale
Also include:
- traditional Telugu Carnatic keerthana / temple bhajan only (no film, EDM, pop)
- MUST include: authentic Telugu language vocals, native Telugu pronunciation, crystal clear Telugu diction, perfect Telugu enunciation, no accent issues, singable Telugu syllables
- {vocal_label} native Telugu Carnatic/bhajan vocalist, classical gamakas, steady shruti
- tanpura; mridangam/manjira intensity matching energy
- instruments matching deity mood
- EXPLICIT tempo e.g. "slow 68 BPM" OR "medium 96 BPM"
- temple mandapam reverb; Pallavi chorus repeats; brief sloka chant break; grand nama finale
- studio-quality vocal take, no mumbled words, lyrics fully intelligible in Telugu
Tempo guide:
- peaceful / meditative / aarti / surrender → slow ≈60–75 BPM
- graceful Devi / Lakshmi → slow–medium ≈75–90 BPM
- joyful nama sankirtana → medium ≈90–105 BPM
- Hanuman courage / protection → medium–brisk ≈100–115 BPM
- morning Suprabhata / Surya → medium bright
Max ~650 characters; no quotes inside.

Also set:
- "tempo": one of "slow" | "slow_medium" | "medium" | "medium_brisk"
- "bpm_hint": integer
- "energy": short phrase

Respond with ONLY valid JSON (no markdown fences):
{{"title":"...","style_prompt":"...","lyrics":"...","tempo":"...","bpm_hint":90,"energy":"..."}}"""
