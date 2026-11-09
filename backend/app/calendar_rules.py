"""Telugu / South-Indian weekday + daypart deity rotation (beautiful deity songs)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Full Hindu pantheon used by Ragam Spiritual (no Sai / non-Hindu figures).
HINDU_DEITIES: dict[str, dict[str, str]] = {
    "Shiva": {
        "topic": "Shaiva bhakti — choose a FRESH angle (not the same prabhata-linga song every time)",
        "music_genre": "traditional Telugu Shaiva keerthana; tempo from lyric mood (often meditative slow–medium)",
        "energy_hint": "meditative",
        "topic_angles": [
            "Kailasa cool moonlight, Gangadhara stillness, soft damaru hush",
            "Nataraja cosmic dance — ananda tandava, flaming aureole devotion",
            "bilva archana fragrance, vibhuti streaks, silent stone linga glow",
            "Neelakantha karuna — halahala swallowed for the worlds",
            "Pashupati protector — gentle ugra-karuna for the devotee",
            "Ardhanarishwara unity — Shiva-Shakti one form, serene mandapam",
            "Chandrashekhara night vigil — crescent coolness, deep Om Namah Shivaya",
            "inner linga jyothi — heart-cave meditation, not wake-up-clock framing",
        ],
    },
    "Parvati": {
        "topic": "Parvati / Ambika — motherly grace, Uma-Maheshwara shakti",
        "music_genre": "traditional Telugu Devi keerthana; graceful slow–medium",
        "vocal_preference": "f",
        "energy_hint": "graceful",
    },
    "Hanuman": {
        "topic": "Hanuman courage and protection — Anjaneya, Rama dasa bhakti",
        "music_genre": "traditional Telugu Hanuman bhajan; medium–brisk classical drive when courageous",
        "energy_hint": "courageous-bhakti",
    },
    "Subrahmanya": {
        "topic": "Subrahmanya / Kartikeya / Murugan — vel, peacock, youthful shakti",
        "music_genre": "traditional Telugu Subrahmanya keerthana; bright medium classical",
        "energy_hint": "bright-devotion",
    },
    "Krishna": {
        "topic": "Krishna leela — flute, Gopala, soft Vrindavana devotion",
        "music_genre": "traditional Telugu Krishna keerthana with flute; tempo from lyric mood",
        "energy_hint": "lyrical",
    },
    "Sri Rama": {
        "topic": "Sri Rama — dharma, maryada, Kodanda, Sita-Rama bhakti",
        "music_genre": "traditional Telugu Rama keerthana; noble medium, clear classical diction",
        "energy_hint": "noble-bhakti",
    },
    "Narasimha": {
        "topic": "Narasimha — ugra-karuna, Prahlada rakshana, Ahobilam mood",
        "music_genre": "traditional Telugu Narasimha keerthana; firm medium for protection, softer for karuna",
        "energy_hint": "protective-bhakti",
    },
    "Sri Vishnu": {
        "topic": "Sri Vishnu / Narayana — shanka-chakra, Vaikuntha surrender, ashtakshari",
        "music_genre": "traditional Telugu Vaishnava keerthana; serene to medium sankirtana",
        "energy_hint": "vaishnava-bhakti",
    },
    "Lakshmi": {
        "topic": "Lakshmi / Sri Devi — prosperity, padma, lamp-lit grace",
        "music_genre": "traditional Telugu Lakshmi keerthana; graceful slow–medium",
        "vocal_preference": "f",
        "energy_hint": "graceful",
    },
    "Saraswati": {
        "topic": "Saraswati — vidya, veena, white lotus, vak-shuddhi",
        "music_genre": "traditional Telugu Saraswati keerthana; lyrical slow–medium, veena colour",
        "vocal_preference": "f",
        "energy_hint": "lyrical-wisdom",
    },
    "Durga": {
        "topic": "Durga / Chandika — shakti, protection, Navaratri fire of dharma",
        "music_genre": "traditional Telugu Durga keerthana; medium firm classical, never film/EDM",
        "vocal_preference": "f",
        "energy_hint": "shakti",
    },
    "Venkateswara": {
        "topic": "Venkateswara / Balaji — Tirumala, Govinda namam, surrender",
        "music_genre": "traditional Telugu Venkateswara sankirtana; often medium joyful Govinda nama",
        "energy_hint": "sankirtana-joy",
    },
    "Ganesha": {
        "topic": "Ganesha / Vinayaka — vighna-hara, mangala arambham",
        "music_genre": "traditional Telugu Ganapati keerthana; warm medium classical",
        "energy_hint": "auspicious",
    },
    "Surya Narayana": {
        "topic": "Surya / Aditya — morning light, gratitude, Gayatri radiance",
        "music_genre": "traditional Telugu morning devotion; bright medium Suprabhata feel",
        "energy_hint": "morning-bright",
    },
    "Ayyappa": {
        "topic": "Ayyappa / Hariharaputra — Sabarimala, saranam Ayyappa, vrata bhakti",
        "music_genre": "traditional Telugu Ayyappa bhajan; medium classical devotion",
        "energy_hint": "vrata-bhakti",
    },
    "Annapurna": {
        "topic": "Annapurna Devi — annam, motherly nourishment, Kashi grace",
        "music_genre": "traditional Telugu Annapurna/Devi keerthana; soft medium, warm",
        "vocal_preference": "f",
        "energy_hint": "motherly",
    },
}

# Morning = classic weekday association
WEEKDAY_MORNING: dict[int, str] = {
    0: "Shiva",
    1: "Hanuman",
    2: "Krishna",
    3: "Narasimha",
    4: "Lakshmi",
    5: "Venkateswara",
    6: "Surya Narayana",
}

# Evening = second deity so Sri Rama, Vishnu, Durga, and others appear every week
WEEKDAY_EVENING: dict[int, str] = {
    0: "Parvati",
    1: "Subrahmanya",
    2: "Sri Rama",
    3: "Sri Vishnu",
    4: "Saraswati",
    5: "Ganesha",
    6: "Ayyappa",
}

# Extra rotation so Durga / Annapurna / others also get evening slots across weeks
WEEKLY_EVENING_ALT: list[str] = [
    "Durga",
    "Annapurna",
    "Sri Rama",
    "Sri Vishnu",
    "Durga",
    "Saraswati",
    "Ganesha",
]

MONTH_MOOD: dict[int, dict[str, str]] = {
    1: {
        "mood": "Sankranti / harvest gratitude",
        "festive_hint": "Makara Sankranti season — abundance, sugarcane, new beginnings",
        "visual_style": "golden sunrise fields, temple flags, warm harvest light",
    },
    2: {
        "mood": "Shivaratri devotion",
        "festive_hint": "Maha Shivaratri season — night vigil, bilva, cool moonlight",
        "visual_style": "moonlit Shiva temple, bilva leaves, serene blue-grey night",
    },
    3: {
        "mood": "Spring / Holi-Ugadi approach",
        "festive_hint": "Late Holi into Ugadi approach — color, renewal",
        "visual_style": "spring flowers, soft pastel temple courtyard",
    },
    4: {
        "mood": "Ugadi / Sri Rama Navami",
        "festive_hint": "Ugadi & Sri Rama Navami — new year, dharma, Rama bhakti",
        "visual_style": "mango leaves toranam, Rama shrine, fresh green and gold",
    },
    5: {
        "mood": "Summer serene bhakti",
        "festive_hint": "Peak summer — cool evening temple aarti mood",
        "visual_style": "evening lamps, soft amber stone temple corridors",
    },
    6: {
        "mood": "Monsoon bhakti",
        "festive_hint": "Monsoon rains — reflective devotion, petrichor temple steps",
        "visual_style": "rain-washed gopuram, wet stone, soft grey-green mist",
    },
    7: {
        "mood": "Guru Purnima / early Varalakshmi season",
        "festive_hint": "Guru Purnima — gratitude to Guru, soft full-moon devotion",
        "visual_style": "full moon over temple tank, lotus, silver-gold light",
    },
    8: {
        "mood": "Janmashtami / Varalakshmi / Vinayaka",
        "festive_hint": "Krishna Janmashtami, Varalakshmi, Vinayaka Chavithi season",
        "visual_style": "butter lamps, peacock feather accents, festive marigold",
    },
    9: {
        "mood": "Ganesh / Navaratri prep",
        "festive_hint": "Ganesh visarjan into Navaratri preparation — joyful then Devi power",
        "visual_style": "modak offerings, then red-gold Devi altar tones",
    },
    10: {
        "mood": "Navaratri / Dussehra",
        "festive_hint": "Navaratri & Vijayadashami — Durga shakti, victory of dharma",
        "visual_style": "nine-night lamps, vibrant red-gold, soft Devi altar",
    },
    11: {
        "mood": "Diwali / Kartika Deepam",
        "festive_hint": "Deepavali & Kartika deepams — rows of lamps, home and temple light",
        "visual_style": "rows of diyas, warm night glow, marigold and gold",
    },
    12: {
        "mood": "Kartika / Vaikuntha season",
        "festive_hint": "Kartika deepam into Vaikuntha Ekadashi — Sri Vishnu surrender",
        "visual_style": "deep winter night lamps, Vaikuntha gate motif, cool blue-gold",
    },
}


_MORNING_PREFIXES = [
    "Fresh temple devotion — invent a unique angle (avoid repeating prabhata wake-up formulas)",
    "Serene mandapam bhakti — soft light, but NOT another identical sunrise-suprabhata lyric",
    "Quiet hour devotion — cool stone, first conch, new imagery each day",
    "Dawn-adjacent mood only as light colour — focus on deity leela/guna, not clock-time lyrics",
]
_EVENING_PREFIXES = [
    "Lamp-lit evening devotion — warm mandapam, fresh imagery (not the same sandhya lines every day)",
    "Sandhya mood as colour only — invent a new poetic focus for this deity",
    "Dusk temple hush — deep karuna / nama, avoid cookie-cutter aarti templates",
]

DAYPART_FLAVOR = {
    # Channel data (Nov 2026): long-form avg views ~2× stronger at ~6 AM IST than ~7 PM;
    # Shorts slightly stronger at ~7 PM. Keep both dayparts; morning favors long-form,
    # evening favors Shorts. Publish at window start so indexing meets viewers.
    "morning": {
        "label": "Morning (మంగళారతి / early devotion)",
        "topic_prefix": _MORNING_PREFIXES[0],
        "default_hour": 6,
        "default_minute": 0,
        "short2_stagger_hours": 6,  # → ~12 PM Shorts lunch-scroll peak
    },
    "evening": {
        "label": "Evening (సాయంకాల హారతి)",
        "topic_prefix": _EVENING_PREFIXES[0],
        "default_hour": 19,
        "default_minute": 0,
        "short2_stagger_hours": 0,  # same evening window — Shorts peak 7–9 PM
    },
}

# Back-compat alias used by older imports
WEEKDAY_DEITY = {
    i: {"deity": name, **HINDU_DEITIES[name]} for i, name in WEEKDAY_MORNING.items()
}


def _iso_week(d: date) -> int:
    return int(d.strftime("%G%V"))


def resolve_deity(d: date, daypart: str) -> str:
    """Morning = weekday classic; evening = paired deity, with weekly alt for more coverage."""
    weekday = d.weekday()
    if daypart != "evening":
        return WEEKDAY_MORNING[weekday]
    # Odd ISO weeks: use alt roster entry for that weekday so Durga etc. rotate in
    if _iso_week(d) % 2 == 1:
        return WEEKLY_EVENING_ALT[weekday % len(WEEKLY_EVENING_ALT)]
    return WEEKDAY_EVENING[weekday]


def deity_profile(name: str) -> dict[str, str]:
    return dict(HINDU_DEITIES.get(name, {
        "topic": f"{name} bhakti — traditional temple devotion",
        "music_genre": "traditional Telugu Carnatic-devotional keerthana",
        "energy_hint": "devotional",
    }))


def suggest_for_date(
    when: date | datetime | None = None,
    *,
    daypart: str = "morning",
) -> dict[str, Any]:
    d = when.date() if isinstance(when, datetime) else (when or date.today())
    part = daypart if daypart in DAYPART_FLAVOR else "morning"
    flavor = DAYPART_FLAVOR[part]
    weekday = d.weekday()
    deity = resolve_deity(d, part)
    day = deity_profile(deity)
    vocal = day.get("vocal_preference", "m")
    # Rotate daypart colour + deity angle so lyrics don't clone yesterday
    if part == "morning":
        prefix = _MORNING_PREFIXES[(d.toordinal() + weekday) % len(_MORNING_PREFIXES)]
    else:
        prefix = _EVENING_PREFIXES[(d.toordinal() + weekday) % len(_EVENING_PREFIXES)]
    angles = day.get("topic_angles") or []
    angle = ""
    if angles:
        angle = angles[(d.toordinal() + sum(ord(c) for c in deity)) % len(angles)]
    base_topic = day["topic"]
    # Beautiful deity song only — do not force calendar-month festivals
    # (Kartika, Navaratri, etc.) into every topic.
    topic = (
        f"{prefix}. {base_topic}. "
        + (f"Today's unique angle: {angle}. " if angle else "")
        + "Timeless temple bhakti — unique title/Pallavi for this draft; "
        "do not clone recent channel songs."
    )
    visual = day.get(
        "visual_style",
        "serene South Indian temple sanctum, soft oil-lamp glow, "
        "fresh flowers, peaceful murti devotion",
    )
    return {
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "weekday_index": weekday,
        "daypart": part,
        "daypart_label": flavor["label"],
        "publish_hour": flavor["default_hour"],
        "publish_minute": flavor["default_minute"],
        "deity": deity,
        "topic": topic,
        "music_genre": day["music_genre"],
        "energy_hint": day.get("energy_hint"),
        "vocal_preference": vocal,
        "month_mood": "peaceful temple devotion",
        "festive_hint": "",
        "visual_style": visual,
        "pantheon": sorted(HINDU_DEITIES.keys()),
        "shorts_plan": (
            "Same long-form audio + looping visual → cut 2 Shorts clips; "
            "publish both Shorts at this daypart time with link to main song."
        ),
        "thumbnail_notes": (
            f"Feature {deity} prominently; serene temple look: {visual}; "
            "include channel logo + Telugu song title."
        ),
    }


def week_suggestions(start: date) -> list[dict[str, Any]]:
    from datetime import timedelta

    out: list[dict[str, Any]] = []
    for i in range(7):
        day = start + timedelta(days=i)
        out.append(suggest_for_date(day, daypart="morning"))
        out.append(suggest_for_date(day, daypart="evening"))
    return out
