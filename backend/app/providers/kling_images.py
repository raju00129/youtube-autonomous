"""Kling Image 3.0 Omni — ultra-premium cinematic scenes (style-matched to channel thumbs).

Telugu title is NEVER painted by Kling. services_thumbnail stamps 3D gold Telugu + logo.
Style reference images teach Omni the Ragam Spiritual premium look.
"""

from __future__ import annotations

import base64
import io
import re
import time
from pathlib import Path

import httpx
from PIL import Image

from app.core.config import get_settings
from app.progress import ProgressFn, kling_poll_percent, report


class KlingImageError(RuntimeError):
    pass


_OMNI_MODELS = frozenset({"kling-v3-omni", "kling-image-o1", "kling-image-v3-omni"})
_STYLE_DIR = Path(__file__).resolve().parent.parent / "assets" / "thumb_style_refs"


def is_configured() -> bool:
    return bool(get_settings().kling_api_key.strip())


def _base_url() -> str:
    return (get_settings().kling_base_url or "https://api-singapore.klingai.com").rstrip("/")


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().kling_api_key.strip()}",
        "Content-Type": "application/json",
    }


def _normalize_model(raw: str) -> str:
    m = (raw or "kling-v3-omni").strip()
    if m in {"kling-image-v3-omni", "kling-v3-omni"}:
        return "kling-v3-omni"
    if m == "kling-image-o1":
        return "kling-image-o1"
    return "kling-v3-omni"


def _normalize_resolution(raw: str, *, model: str) -> str:
    r = (raw or "4k").strip().lower()
    if r not in {"1k", "2k", "4k"}:
        r = "4k"
    if model == "kling-image-o1" and r == "4k":
        return "2k"
    return r


def _output_size(resolution: str) -> tuple[int, int]:
    if resolution == "4k":
        return (2560, 1440)
    if resolution == "2k":
        return (1920, 1080)
    return (1280, 720)


def _section(lyrics: str, name: str) -> str:
    m = re.search(
        rf"\[{name}\]\s*(.+?)(?=\n\s*\[|\Z)",
        lyrics,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    lines = [
        ln.strip()
        for ln in m.group(1).splitlines()
        if ln.strip() and not ln.strip().startswith("[")
    ]
    return " ".join(lines[:6])


def _deity_visual(deity: str | None) -> str:
    """Classical murti / shastra ideal — NOT a drama human actor."""
    key = (deity or "").lower()
    table = {
        "narasimha": (
            "Ugra Narasimha murti ideal — lion head, four arms, sudarshana and chakra, "
            "divine aura, Ahobilam-style sanctum, NOT a human actor in makeup"
        ),
        "hanuman": (
            "Anjaneya murti ideal — vanara face with serene bhakti eyes, gada, "
            "orange silk, temple garbhagriha darshan look, NOT a CGI film warrior-human hybrid"
        ),
        "lakshmi": (
            "Sri Lakshmi murti ideal — four arms, padma, gold ornaments, seated on lotus, "
            "South Indian temple idol grace, NOT a fashion model / actress face"
        ),
        "shiva": (
            "Lord Shiva murti / linga ideal — Tripundra, jata, crescent, rudraksha, "
            "serene yogic divinity or lingam with bilva, NOT a shirtless drama hero"
        ),
        "parvati": (
            "Goddess Parvati / Ambika murti — motherly grace, silk saree, temple crown, "
            "Uma-Maheshwara sanctum mood, classical idol proportions"
        ),
        "vishnu": (
            "Lord Vishnu murti — kiritam, shankha chakra, blue divine form, "
            "Vaikuntha sanctum, classical agama iconography"
        ),
        "venkateswara": (
            "Sri Venkateswara / Balaji murti — Tirumala idol form, namam, "
            "shankha chakra, gold kavacham, temple darshan mood"
        ),
        "rama": (
            "Sri Rama murti — kodanda, serene maryada face, classical icon, "
            "NOT a TV serial prince"
        ),
        "krishna": (
            "Sri Krishna murti — peacock feather, flute, pitambara, soft divine smile, "
            "temple idol / classical painting ideal"
        ),
        "durga": (
            "Goddess Durga murti — multiple arms, trishula, lion vahana, "
            "Navaratri sanctum shakti, classical idol not action-heroine"
        ),
        "ganesha": (
            "Sri Ganesha murti — elephant head, modaka, red-gold silk, "
            "temple vigneshwara idol ideal"
        ),
        "ayyappa": (
            "Lord Ayyappa murti — Sabarimala idol form, yellow silk, "
            "serene dhyana posture, temple lamp glow"
        ),
        "surya": (
            "Surya Narayana murti — radiant solar deity, chariot / lotus aura, "
            "classical sun-god iconography"
        ),
        "subrahmanya": (
            "Lord Subrahmanya / Murugan murti — vel, peacock, "
            "youthful divine ideal, temple form"
        ),
        "saraswati": (
            "Goddess Saraswati murti — veena, white silk, swan, "
            "vidya radiance, classical idol"
        ),
    }
    for name, desc in table.items():
        if name in key:
            return desc
    return (
        f"classical South Indian temple murti ideal of {deity or 'the deity'} — "
        "agama iconography, divine serene face, NOT a human drama actor"
    )


def _ritual_event_from_lyrics(
    *,
    lyrics: str | None,
    deity: str | None,
    title: str | None,
    visual_style: str | None,
    style_prompt: str | None,
    notes: str | None,
    mood: str | None,
) -> tuple[str, str]:
    """Return (event_label, event_direction) from lyric/deity cues."""
    blob = f"{lyrics or ''} {title or ''} {visual_style or ''} {style_prompt or ''} {notes or ''} {deity or ''} {mood or ''}".lower()
    deity_l = (deity or "").lower()

    rules: list[tuple[tuple[str, ...], str, str]] = [
        (
            ("అభిషేక", "abhishek", "లింగ", "linga", "lingam", "పంచామృత", "panchamrita"),
            "Lingam / murti abhishekam",
            "sacred milk-water-ghee pour over Shiva lingam or murti, bilva leaves, "
            "priests' hands optional only as blur, focus on divine form and falling sacred liquids",
        ),
        (
            ("ఆరతి", "aarti", "హారతి", "harathi", "నీరాజన", "deepa"),
            "Mangala aarti / harathi",
            "circling brass aarti plate with flaming camphor/diyas before the murti, "
            "incense smoke, bells implied by motion, devotees soft in background",
        ),
        (
            ("అలంకార", "alankar", "పూజ", "pooja", "puja", "అర్చన", "archana", "నైవేద్య", "naivedya"),
            "Alankaram & archana pooja",
            "murti decorated with fresh garlands, turmeric-kumkum, flowers offered to feet, "
            "silver plates, temple sanctum ritual in progress",
        ),
        (
            ("దర్శన", "darshan", "గర్భగుడి", "garbhagriha", "సన్నిధి"),
            "Garbhagriha darshan",
            "intimate sanctum darshan of the decorated murti under oil lamps, "
            "soft crowd silhouettes, sacred stillness",
        ),
        (
            ("నవరాత్రి", "navaratri", "దుర్గ", "durga", "చండి"),
            "Navaratri Durga utsavam",
            "Durga murti with garlands, lamps rows, festive red-gold temple hall, "
            "shakti utsav energy without action-movie violence",
        ),
        (
            ("దీపావళి", "deepavali", "diwali", "కార్తీక", "kartika", "దీపం", "deepam"),
            "Kartika / Deepavali deepotsavam",
            "rows of oil lamps, marigold, murti glowing in lamp light, "
            "temple courtyard deepam festival",
        ),
        (
            ("సంధ్య", "sandhya", "సాయం", "pradosha", "ప్రదోష"),
            "Sandhya / pradosha worship",
            "dusk temple aarti mood, indigo-gold sky beyond gopuram, "
            "lamps lighting before the murti",
        ),
        (
            ("సూర్య", "surya", "ఆదిత్య", "ఉదయ", "prabhata", "సూర్యనమస్కార"),
            "Surya prabhata archana",
            "sunrise rays on Surya or morning deity murti, lotus, "
            "water offering, dawn temple courtyard",
        ),
        (
            ("సబరిమల", "sabarimala", "అయ్యప్ప", "ayyappa", "శరణం", "saranam"),
            "Ayyappa temple worship",
            "Sabarimala-style murti, ghee lamp, irumudi mood, "
            "serene saranam chant atmosphere",
        ),
        (
            ("గోవింద", "govinda", "వెంకటేశ్వర", "tirupati", "బాలాజీ"),
            "Venkateswara seva / darshan",
            "Balaji murti with gold kavacham, namam, flower seva, "
            "Tirumala sanctum lamp glow",
        ),
        (
            ("కమల", "lotus", "పద్మ", "స్వర్ణ", "gold coin", "లక్ష్మీ"),
            "Lakshmi ashtottara / lotus seva",
            "Lakshmi murti on lotus, coin-petal offering, "
            "diyas and prosperity alankaram",
        ),
        (
            ("సముద్ర", "ocean", "sea", "సేతు", "సుందర"),
            "Seashore / Setu bhakti scene",
            "divine murti or Hanuman ideal at sacred shore, "
            "waves and sky as backdrop to worship mood — not a war scene",
        ),
    ]
    for keys, label, direction in rules:
        if any(k in blob for k in keys):
            return label, direction

    # Deity defaults when lyrics are sparse
    if any(k in deity_l for k in ("shiva", "శివ")):
        return (
            "Shiva alankaram & deepa archana",
            "Shiva murti or lingam with bilva, rudraksha, oil lamps, gentle abhishekam mist",
        )
    if any(k in deity_l for k in ("hanuman", "anjaneya", "ఆంజనేయ")):
        return (
            "Hanuman sindooram alankaram",
            "Anjaneya murti with sindooram, garland, oil lamps, temple archana in progress",
        )
    if "morning" in blob or "dawn" in blob or "prabhata" in blob:
        return (
            "Prabhata mangala aarti",
            "early-morning temple aarti before the murti, soft sunrise through mandapam",
        )
    if "evening" in blob or "aarti" in blob:
        return (
            "Sayamkala aarti",
            "evening harathi with many diyas circling before the murti",
        )
    return (
        "Temple murti seva from the lyric mood",
        "active pooja moment from the song meaning — garlands, lamps, offerings, "
        "sanctum ritual — not a static portrait with empty decorated background",
    )


def pick_style_reference(deity: str | None) -> Path | None:
    """Pick a channel-style reference thumb closest to the deity."""
    if not _STYLE_DIR.exists():
        return None
    key = (deity or "").lower()
    prefer: list[str] = []
    if "narasimha" in key:
        prefer = ["Narasimha"]
    elif "hanuman" in key or "anjaneya" in key:
        prefer = ["Hanuman"]
    elif "lakshmi" in key or "kamala" in key:
        prefer = ["Lakshmi", "Goddess"]
    else:
        prefer = ["Lakshmi", "Narasimha", "Hanuman"]
    files = sorted(_STYLE_DIR.glob("*.jpg")) + sorted(_STYLE_DIR.glob("*.png"))
    for needle in prefer:
        for f in files:
            if needle.lower() in f.name.lower():
                return f
    return files[0] if files else None


def build_lyrics_scene_brief(
    *,
    deity: str | None,
    mood: str | None,
    lyrics: str | None,
    title: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    has_style_ref: bool = False,
) -> str:
    body = (lyrics or "").strip()
    pallavi = _section(body, "Pallavi")
    anu = _section(body, "Anupallavi")
    char1 = _section(body, "Charanam 1") or _section(body, "Charanam")
    char2 = _section(body, "Charanam 2")
    sloka = _section(body, "Slokam") or _section(body, "Sloka")
    lyric_bits = [b for b in (pallavi, anu, char1, char2, sloka) if b]
    lyric_story = " | ".join(lyric_bits)[:700] if lyric_bits else (title or "Telugu bhakti")

    event_label, event_dir = _ritual_event_from_lyrics(
        lyrics=body,
        deity=deity,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        mood=mood,
    )

    hero = _deity_visual(deity)
    mood_bit = mood or "bhakti / sacred stillness"
    style_bit = (visual_style or "").strip()[:140]
    notes_bit = (notes or "").strip()[:140]

    ref_line = (
        "Match ONLY the lighting richness and temple-gold grade of <<<image_1>>> "
        "(Ragam Spiritual). Invent a NEW ritual scene for THIS song — "
        "do not copy the same deity pose or any text from the reference. "
        if has_style_ref
        else ""
    )

    return (
        f"{ref_line}"
        f"Sacred 16:9 Hindu temple VISUAL — classical murti / agama GOD IDEAL, "
        f"South Indian sanctum realism, oil-lamp warmth, marigold, incense haze. "
        f"NOT a Bollywood/TV drama human, NOT a fashion model, NOT shirtless CGI hero, "
        f"NOT 'mythological movie poster' actor face — divine idol / shastra ideal form only. "
        f"FULL-BLEED single ritual SCENE (no collage, no split panels, no text box). "
        f"DEITY (god ideal): {hero}. Mood: {mood_bit}. "
        f"RITUAL EVENT (must be visible): {event_label} — {event_dir}. "
        f"LYRICS TO ILLUSTRATE (turn meaning into the pooja/event, not a blank portrait): "
        f"{lyric_story}. "
        f"{('Visual style: ' + style_bit + '. ') if style_bit else ''}"
        f"{('Notes: ' + notes_bit + '. ') if notes_bit else ''}"
        f"Composition: murti + ritual action filling LEFT–CENTER ~55–60%; RIGHT softer for later title. "
        f"Show offerings, lamps, garlands, abhishekam/aarti/archana in progress — "
        f"never a lone character on empty decorated backdrop. "
        f"CRITICAL — ZERO TEXT: no Telugu/Hindi/English letters, no captions, logos, "
        f"watermarks, Sai Baba, selfies, or modern phones."
    )[:2400]


def _poll_omni_task(
    client: httpx.Client,
    task_id: str,
    *,
    timeout_sec: float,
    on_progress: ProgressFn | None = None,
) -> str:
    started = time.monotonic()
    deadline = started + timeout_sec
    url = f"{_base_url()}/v1/images/omni-image/{task_id}"
    last = ""
    while time.monotonic() < deadline:
        response = client.get(url, headers=_auth_headers())
        if response.status_code >= 400:
            raise KlingImageError(
                f"Kling Omni poll HTTP {response.status_code}: {response.text[:400]}"
            )
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise KlingImageError(f"Unexpected Kling Omni poll payload: {str(body)[:400]}")
        status = str(data.get("task_status") or "").lower()
        last = status
        pct = kling_poll_percent(
            elapsed=time.monotonic() - started,
            timeout=timeout_sec,
            status=status,
        )
        report(on_progress, pct, f"Kling Omni image: {status or 'waiting'}…")
        if status in {"succeed", "succeeded", "success"}:
            result = data.get("task_result") or {}
            images = result.get("images") or result.get("series_images") or []
            if not images:
                raise KlingImageError(f"Kling Omni succeed but empty: {str(data)[:400]}")
            img_url = images[0].get("url")
            if not img_url:
                raise KlingImageError(f"Kling Omni missing url: {str(images[0])[:300]}")
            return str(img_url)
        if status in {"failed", "fail", "error"}:
            msg = data.get("task_status_msg") or body.get("message") or status
            raise KlingImageError(f"Kling Omni failed: {msg}")
        time.sleep(2.5)
    raise KlingImageError(f"Kling Omni timed out (last status={last or 'unknown'})")


def generate_rich_deity_scene(
    *,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None = None,
    out_path: str | Path,
    lyrics: str | None = None,
    title: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    resolution: str | None = None,
    use_style_ref: bool = True,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Kling Omni — ultra-premium lyrics-driven plate, zero text."""
    settings = get_settings()
    if not settings.kling_api_key.strip():
        raise KlingImageError("KLING_API_KEY missing")

    report(on_progress, 3, "Building ultra-premium scene prompt…")
    model = _normalize_model(settings.kling_image_model)
    resolution = _normalize_resolution(
        resolution or getattr(settings, "kling_image_resolution", None) or "4k",
        model=model,
    )

    style_ref = pick_style_reference(deity) if use_style_ref else None
    image_list: list[dict] = []
    if style_ref and style_ref.exists() and style_ref.stat().st_size < 9_000_000:
        # Resize ref so payload stays light
        ref_img = Image.open(style_ref).convert("RGB")
        ref_img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        ref_img.save(buf, format="JPEG", quality=88)
        image_list.append({"image": base64.b64encode(buf.getvalue()).decode("ascii")})
        report(on_progress, 5, f"Style ref: {style_ref.name}")

    full_lyrics = (lyrics or lyrics_hint or "").strip()
    prompt = build_lyrics_scene_brief(
        deity=deity,
        mood=mood,
        lyrics=full_lyrics,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        has_style_ref=bool(image_list),
    )

    timeout = float(settings.kling_image_timeout_sec or 240)
    payload: dict = {
        "model_name": model if model in _OMNI_MODELS else "kling-v3-omni",
        "prompt": prompt,
        "resolution": resolution,
        "result_type": "single",
        "n": 1,
        "aspect_ratio": "16:9",
        "watermark_info": {"enabled": False},
    }
    if image_list:
        payload["image_list"] = image_list

    try:
        with httpx.Client(timeout=timeout) as client:
            report(on_progress, 6, f"Submitting Kling Omni {resolution}…")
            create = client.post(
                f"{_base_url()}/v1/images/omni-image",
                headers=_auth_headers(),
                json=payload,
            )
            try:
                body = create.json()
            except Exception:  # noqa: BLE001
                body = {}
            api_code = body.get("code")
            if create.status_code >= 400 or api_code not in (0, "0", None):
                msg = str(body.get("message") or create.text[:400])
                if api_code in (1101, 1102, "1101", "1102") or "balance" in msg.lower():
                    raise KlingImageError(
                        "Kling API has no usable credits (code 1102). "
                        "Buy an Image pack at https://kling.ai/dev/pricing?scrollTo=image "
                        f"then retry. Detail: {msg}"
                    )
                raise KlingImageError(
                    f"Kling Omni create HTTP {create.status_code} code={api_code}: {msg}"
                )

            data = body.get("data") or {}
            task_id = data.get("task_id")
            if not task_id:
                raise KlingImageError(f"Kling Omni missing task_id: {str(body)[:400]}")

            report(on_progress, 10, "Kling Omni rendering ultra-premium scene…")
            image_url = _poll_omni_task(
                client, str(task_id), timeout_sec=timeout, on_progress=on_progress
            )
            report(on_progress, 90, "Downloading Omni image…")
            dl = client.get(image_url)
            if dl.status_code >= 400:
                raise KlingImageError(f"Kling Omni download HTTP {dl.status_code}")

            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            img = Image.open(io.BytesIO(dl.content)).convert("RGB")
            tw, th = _output_size(resolution)
            if img.width != tw or img.height != th:
                img = img.resize((tw, th), Image.Resampling.LANCZOS)
            if out.suffix.lower() in {".jpg", ".jpeg"}:
                img.save(out, format="JPEG", quality=95, optimize=True, subsampling=0)
            else:
                img.save(out, format="PNG", optimize=True)
            report(on_progress, 96, "Scene ready — composing 3D Telugu title + logo…")
            return out
    except httpx.RequestError as exc:
        raise KlingImageError(f"Kling images unreachable: {exc}") from exc


def generate_premium_thumbnail(
    *,
    title: str,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None,
    out_path: str | Path,
    logo_path: str | Path | None = None,
    channel_name: str = "Ragam Spiritual",
    lyrics: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    del logo_path, channel_name
    return generate_rich_deity_scene(
        deity=deity,
        mood=mood,
        lyrics_hint=lyrics_hint,
        lyrics=lyrics or lyrics_hint,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        out_path=out_path,
        on_progress=on_progress,
    )


def generate_deity_background(
    *,
    deity: str | None,
    mood: str | None,
    lyrics_hint: str | None,
    out_path: str | Path,
    title: str | None = None,
    logo_path: str | Path | None = None,
    lyrics: str | None = None,
    visual_style: str | None = None,
    style_prompt: str | None = None,
    notes: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    del logo_path
    return generate_rich_deity_scene(
        deity=deity,
        mood=mood,
        lyrics_hint=lyrics_hint,
        lyrics=lyrics or lyrics_hint,
        title=title,
        visual_style=visual_style,
        style_prompt=style_prompt,
        notes=notes,
        out_path=out_path,
        on_progress=on_progress,
    )


def _chroma_to_alpha(img: Image.Image) -> Image.Image:
    """Knock out green-screen / flat studio backdrop for petal cutouts."""
    rgba = img.convert("RGBA")
    px = rgba.load()
    assert px is not None
    w, h = rgba.size
    # Sample corner colors — AI often returns black/white instead of green
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            # Chroma green / lime
            if g >= 90 and g > r + 25 and g > b + 25:
                px[x, y] = (r, g, b, 0)
                continue
            if g >= 70 and r < 90 and b < 90 and g > max(r, b) + 15:
                px[x, y] = (r, g, b, 0)
                continue
            # Near-black backdrop
            if r < 28 and g < 28 and b < 28:
                px[x, y] = (r, g, b, 0)
                continue
            # Near-white / light gray studio backdrop
            if r > 235 and g > 235 and b > 235:
                px[x, y] = (r, g, b, 0)
                continue
            # Match flat corner backdrop color (tolerance)
            for cr, cg, cb, _ca in corners:
                if abs(r - cr) < 18 and abs(g - cg) < 18 and abs(b - cb) < 18:
                    # only if corner itself looks like a flat backdrop (not petal)
                    if max(cr, cg, cb) < 40 or min(cr, cg, cb) > 220 or (
                        cg > cr + 20 and cg > cb + 20
                    ):
                        px[x, y] = (r, g, b, 0)
                        break
    return rgba


def _split_opaque_blobs(rgba: Image.Image, *, min_area: int = 900) -> list[Image.Image]:
    """Connected-component crop of opaque pixels → individual petal images."""
    w, h = rgba.size
    px = rgba.load()
    assert px is not None
    visited = [[False] * w for _ in range(h)]
    crops: list[Image.Image] = []

    def neighbors(x: int, y: int) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    out.append((nx, ny))
        return out

    for y0 in range(h):
        for x0 in range(w):
            if visited[y0][x0]:
                continue
            if px[x0, y0][3] < 40:
                visited[y0][x0] = True
                continue
            stack = [(x0, y0)]
            visited[y0][x0] = True
            cells: list[tuple[int, int]] = []
            while stack:
                x, y = stack.pop()
                cells.append((x, y))
                for nx, ny in neighbors(x, y):
                    if visited[ny][nx]:
                        continue
                    visited[ny][nx] = True
                    if px[nx, ny][3] >= 40:
                        stack.append((nx, ny))
            if len(cells) < min_area:
                continue
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
            crop = rgba.crop(box)
            # trim tiny margin
            crops.append(crop)
    crops.sort(key=lambda im: im.size[0] * im.size[1], reverse=True)
    return crops


def generate_realistic_petals(
    out_dir: str | Path,
    *,
    count: int = 6,
    force: bool = False,
    on_progress: ProgressFn | None = None,
) -> list[Path]:
    """Kling Omni: photoreal flower petals on chroma green → cut out PNGs (cached)."""
    settings = get_settings()
    if not settings.kling_api_key.strip():
        raise KlingImageError("KLING_API_KEY missing")

    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    existing = sorted(dest.glob("petal_real_*.png"))
    if existing and not force and len(existing) >= 4:
        return existing[: max(count, len(existing))]

    report(on_progress, 4, "Generating realistic flower petals with Kling…")
    model = _normalize_model(settings.kling_image_model)
    prompt = (
        "Studio product photo of SIX separate photorealistic flower petals arranged in a neat "
        "2-row by 3-column grid with LARGE empty gaps between each petal so they do not touch. "
        "Petals only (no stems, no leaves, no whole flowers): "
        "1 marigold orange petal, 2 rose pink petal, 3 jasmine cream-white petal, "
        "4 hibiscus deep red petal, 5 lotus soft pink petal, 6 champaka / temple yellow petal. "
        "Each petal shows natural veins, soft curl, delicate translucent edge, macro photography. "
        "Background MUST be solid pure chroma key green #00FF00 only — flat, no gradient, "
        "no floor, no shadow plate, no text, no watermark, no logo. Square 1:1 composition."
    )
    sheet_path = dest / "petal_sheet_kling.png"
    timeout = float(settings.kling_image_timeout_sec or 240)
    payload = {
        "model_name": model if model in _OMNI_MODELS else "kling-v3-omni",
        "prompt": prompt,
        "resolution": "1k",
        "result_type": "single",
        "n": 1,
        "aspect_ratio": "1:1",
        "watermark_info": {"enabled": False},
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            create = client.post(
                f"{_base_url()}/v1/images/omni-image",
                headers=_auth_headers(),
                json=payload,
            )
            try:
                body = create.json()
            except Exception:  # noqa: BLE001
                body = {}
            api_code = body.get("code")
            if create.status_code >= 400 or api_code not in (0, "0", None):
                msg = str(body.get("message") or create.text[:400])
                raise KlingImageError(
                    f"Kling petal create HTTP {create.status_code} code={api_code}: {msg}"
                )
            task_id = (body.get("data") or {}).get("task_id")
            if not task_id:
                raise KlingImageError(f"Kling petal missing task_id: {str(body)[:400]}")
            report(on_progress, 12, "Kling rendering petal sheet…")
            image_url = _poll_omni_task(
                client, str(task_id), timeout_sec=timeout, on_progress=on_progress
            )
            dl = client.get(image_url)
            if dl.status_code >= 400:
                raise KlingImageError(f"Kling petal download HTTP {dl.status_code}")
            sheet_path.write_bytes(dl.content)
    except httpx.RequestError as exc:
        raise KlingImageError(f"Kling petals unreachable: {exc}") from exc

    report(on_progress, 88, "Cutting petals from chroma sheet…")
    sheet = Image.open(sheet_path)
    cut = _chroma_to_alpha(sheet)
    cut.save(dest / "petal_sheet_alpha.png")
    blobs = _split_opaque_blobs(cut, min_area=700)
    # Clear old real petals before rewrite
    for old in dest.glob("petal_real_*.png"):
        old.unlink(missing_ok=True)
    paths: list[Path] = []
    for i, blob in enumerate(blobs[: max(count, 6)]):
        # Normalize size for overlay (~128px long side)
        bw, bh = blob.size
        scale = 128 / max(bw, bh, 1)
        nw = max(24, int(bw * scale))
        nh = max(24, int(bh * scale))
        resized = blob.resize((nw, nh), Image.Resampling.LANCZOS)
        path = dest / f"petal_real_{i}.png"
        resized.save(path)
        paths.append(path)

    if len(paths) < 3:
        raise KlingImageError(
            f"Could not cut enough petals from Kling sheet (got {len(paths)}). "
            "Re-run with force=True."
        )
    report(on_progress, 96, f"Ready: {len(paths)} realistic petals")
    return paths
