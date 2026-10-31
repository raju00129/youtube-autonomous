"""Compose lyrics-suitable YouTube thumbnails (local, $0 AI) — always required."""

from __future__ import annotations

import colorsys
import hashlib
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# Sharp delivery size (Kling 4K scene is downscaled into this canvas)
W, H = 1920, 1080

DEITY_PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    "shiva": ((12, 24, 48), (40, 80, 120), (200, 180, 120)),
    "parvati": ((40, 16, 36), (130, 50, 100), (255, 200, 160)),
    "hanuman": ((48, 18, 12), (160, 60, 30), (240, 180, 80)),
    "subrahmanya": ((36, 16, 48), (100, 50, 140), (255, 200, 100)),
    "krishna": ((8, 28, 72), (30, 90, 160), (255, 200, 80)),
    "rama": ((16, 36, 28), (40, 110, 80), (220, 200, 120)),
    "sri rama": ((16, 36, 28), (40, 110, 80), (220, 200, 120)),
    "narasimha": ((48, 16, 8), (180, 70, 30), (255, 190, 90)),
    "vishnu": ((12, 32, 64), (40, 100, 160), (200, 180, 100)),
    "sri vishnu": ((12, 32, 64), (40, 100, 160), (200, 180, 100)),
    "lakshmi": ((48, 12, 40), (140, 40, 90), (255, 200, 140)),
    "saraswati": ((24, 28, 48), (80, 100, 160), (240, 240, 255)),
    "durga": ((48, 8, 24), (160, 30, 70), (255, 180, 100)),
    "venkateswara": ((40, 16, 8), (140, 70, 30), (255, 210, 120)),
    "ganesha": ((40, 20, 12), (150, 80, 40), (255, 190, 100)),
    "surya": ((60, 24, 8), (200, 100, 30), (255, 220, 100)),
    "ayyappa": ((32, 20, 12), (120, 70, 40), (240, 200, 120)),
    "annapurna": ((44, 20, 16), (150, 70, 50), (255, 210, 150)),
}


def _font_candidates() -> list[Path]:
    """Prefer heavy Telugu faces used on modern YouTube thumbs."""
    here = Path(__file__).resolve().parent / "assets" / "fonts"
    return [
        here / "Ramabhadra-Regular.ttf",
        here / "BalooTammudu2-ExtraBold.ttf",
        here / "BalooTammudu2-Bold.ttf",
        here / "NotoSansTelugu-Bold.ttf",
        here / "NotoSansTelugu-Regular.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoSansTelugu-Bold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSerifTelugu-Bold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf"),
        Path("/usr/share/fonts/truetype/lohit-telugu/Lohit-Telugu.ttf"),
    ]


def load_telugu_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _font_candidates():
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_yt_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    stroke_width: int = 6,
    stroke_fill: tuple[int, int, int, int] = (0, 0, 0, 255),
    shadow: tuple[int, int] = (4, 6),
) -> None:
    """Bold outlined text (fallback / secondary lines)."""
    x, y = xy
    sx, sy = shadow
    if sx or sy:
        draw.text(
            (x + sx, y + sy),
            text,
            font=font,
            fill=(0, 0, 0, 200),
            stroke_width=max(0, stroke_width - 1),
            stroke_fill=(0, 0, 0, 200),
        )
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def _draw_red_energy_splash(
    canvas: Image.Image,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    """Brush / energy splash behind titles (Narasimha / Hanuman style refs)."""
    splash = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(splash)
    # Soft irregular red-gold plume behind the title block
    for i, (dx, dy, a) in enumerate(
        ((0, 0, 110), (40, -20, 80), (-30, 25, 70), (80, 10, 55), (-50, -15, 50))
    ):
        rx = max(80, int(width * (0.55 + i * 0.05)))
        ry = max(40, int(height * (0.7 + i * 0.08)))
        cx, cy = x + width // 2 + dx, y + height // 2 + dy
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(160, 20, 10, a))
    splash = splash.filter(ImageFilter.GaussianBlur(28))
    canvas.alpha_composite(splash)


def _draw_premium_gold_text(
    canvas: Image.Image,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    stroke_width: int = 8,
) -> None:
    """3D metallic gold Telugu — thick red bevel like Ragam Spiritual premium thumbs."""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = xy
    red_bevel = max(stroke_width + 6, 14)

    # Outer glow
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.text(
        (x, y),
        text,
        font=font,
        fill=(255, 160, 40, 70),
        stroke_width=red_bevel + 14,
        stroke_fill=(255, 80, 20, 50),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(10))
    canvas.alpha_composite(glow)

    # Drop shadow
    d.text(
        (x + 8, y + 10),
        text,
        font=font,
        fill=(20, 5, 0, 230),
        stroke_width=red_bevel + 2,
        stroke_fill=(10, 0, 0, 240),
    )
    # Deep crimson outer bevel (signature of the reference thumbs)
    d.text(
        (x + 3, y + 4),
        text,
        font=font,
        fill=(120, 20, 10, 255),
        stroke_width=red_bevel,
        stroke_fill=(90, 8, 4, 255),
    )
    # Mid bronze edge
    d.text(
        (x + 1, y + 2),
        text,
        font=font,
        fill=(180, 70, 15, 255),
        stroke_width=max(4, stroke_width),
        stroke_fill=(100, 30, 5, 255),
    )
    # Main metallic gold body
    d.text(
        (x, y),
        text,
        font=font,
        fill=(255, 200, 55, 255),
        stroke_width=max(2, stroke_width - 3),
        stroke_fill=(140, 50, 10, 255),
    )
    # Top highlight
    d.text((x, y - 3), text, font=font, fill=(255, 240, 150, 255), stroke_width=0)
    # Specular
    d.text((x, y - 5), text, font=font, fill=(255, 252, 230, 170), stroke_width=0)
    canvas.alpha_composite(layer)


def _draw_filigree(draw: ImageDraw.ImageDraw, cx: int, y: int, half_w: int, color: tuple[int, int, int, int]) -> None:
    """Simple gold ornament bars flanking a subtitle (premium divider)."""
    # Left flourish
    x1, x2 = cx - half_w, cx - 18
    draw.line([(x1, y), (x2, y)], fill=color, width=2)
    draw.ellipse((x1 - 4, y - 4, x1 + 4, y + 4), fill=color)
    draw.ellipse((x2 - 3, y - 3, x2 + 3, y + 3), fill=color)
    # Right flourish
    x3, x4 = cx + 18, cx + half_w
    draw.line([(x3, y), (x4, y)], fill=color, width=2)
    draw.ellipse((x3 - 3, y - 3, x3 + 3, y + 3), fill=color)
    draw.ellipse((x4 - 4, y - 4, x4 + 4, y + 4), fill=color)


def thumbnail_hook_title(title: str, *, max_words: int = 5, max_chars: int = 36) -> str:
    """Short, punchy hook — modern thumbs use ~3–5 words, not the full YouTube title."""
    clean = sanitize_overlay_text(title, max_len=120)
    if not clean:
        return "Ragam Spiritual"
    words = clean.split()
    if len(words) <= max_words and len(clean) <= max_chars:
        return clean
    short = " ".join(words[:max_words])
    return short[:max_chars].rstrip()


def sanitize_overlay_text(text: str | None, *, max_len: int = 110) -> str:
    """Keep Telugu + Latin for Pillow overlay; drop Devanagari / junk symbols that show as boxes."""
    if not text:
        return ""
    # Normalize fancy separators / whitespace
    cleaned = (
        text.replace("\u00a0", " ")
        .replace("·", " ")
        .replace("•", " ")
        .replace("…", " ")
        .replace("|", " ")
        .replace("—", " ")
        .replace("–", " ")
    )
    # Keep Telugu block, basic Latin, digits, and simple punctuation
    cleaned = re.sub(
        r"[^\u0C00-\u0C7F\u0020-\u007E\n]",
        "",
        cleaned,
    )
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned[:max_len]


def extract_pallavi_line(lyrics: str | None) -> str | None:
    if not lyrics:
        return None
    m = re.search(
        r"\[Pallavi\]\s*(.+?)(?=\n\s*\[|\Z)",
        lyrics,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        for line in lyrics.splitlines():
            s = sanitize_overlay_text(line.strip(), max_len=90)
            if s and not s.startswith("["):
                return s
        return None
    block = m.group(1).strip()
    lines = [
        sanitize_overlay_text(ln.strip(), max_len=90)
        for ln in block.splitlines()
        if ln.strip() and not ln.strip().startswith("[")
    ]
    lines = [ln for ln in lines if ln]
    if not lines:
        return None
    return " ".join(lines[:2])[:110]


def infer_mood(
    *,
    lyrics: str | None,
    style_prompt: str | None,
    deity: str | None,
    daypart: str | None,
) -> str:
    """Mood for palette/scene only — do not drive a visible badge on the thumb."""
    blob = f"{style_prompt or ''} {lyrics or ''} {deity or ''} {daypart or ''}".lower()
    # Prefer explicit daypart over fuzzy keyword hits (e.g. "lamp" in every temple prompt)
    if daypart == "evening":
        return "aarti"
    if daypart == "morning":
        return "dawn"
    if any(
        k in blob
        for k in ("brisk", "courage", "hanuman", "narasimha", "ugra", "sankirtana", "108", "115")
    ):
        return "sankirtana"
    if any(k in blob for k in ("sayankala", "sandhya aarti", "evening aarti", "aarti")):
        return "aarti"
    if any(k in blob for k in ("suprabhat", "morning", "surya", "sunrise")):
        return "dawn"
    if any(k in blob for k in ("slow", "meditat", "peace", "surrender", "68 bpm", "72 bpm")):
        return "meditative"
    return "temple"


def _palette_for(deity: str | None) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    key = (deity or "").lower()
    for name, pal in DEITY_PALETTES.items():
        if name in key:
            return pal
    digest = hashlib.md5(key.encode() or b"ragam").hexdigest()
    h = int(digest[:2], 16) / 255.0
    c1 = tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, 0.55, 0.22))
    c2 = tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, 0.65, 0.55))
    c3 = tuple(int(x * 255) for x in colorsys.hsv_to_rgb((h + 0.08) % 1, 0.45, 0.92))
    return c1, c2, c3  # type: ignore[return-value]


def _vertical_gradient(
    size: tuple[int, int],
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
) -> Image.Image:
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    w, h = size
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.replace("\n", " ").split()
    if not words:
        return [text]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines[:3]


def _draw_temple_scene(
    base: Image.Image,
    *,
    accent: tuple[int, int, int],
    mid: tuple[int, int, int],
    mood: str,
) -> Image.Image:
    """Procedural mandapam / lamp / dawn art so every thumb looks intentional without AI."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # Floor plane
    d.polygon(
        [(0, H), (0, int(H * 0.72)), (W, int(H * 0.62)), (W, H)],
        fill=(*mid, 90),
    )

    # Temple gopuram silhouette (right third)
    base_x = int(W * 0.58)
    roof_y = int(H * 0.18)
    d.polygon(
        [
            (base_x, int(H * 0.70)),
            (base_x + 40, roof_y + 80),
            (base_x + 160, roof_y),
            (base_x + 280, roof_y + 80),
            (base_x + 320, int(H * 0.70)),
        ],
        fill=(8, 6, 4, 160),
    )
    # Pillars
    for px in (base_x + 70, base_x + 150, base_x + 230):
        d.rectangle((px, int(H * 0.38), px + 28, int(H * 0.70)), fill=(12, 10, 8, 170))
    # Kalasha
    d.ellipse((base_x + 140, roof_y - 36, base_x + 180, roof_y + 8), fill=(*accent, 200))

    if mood in {"dawn", "sankirtana"}:
        # Sun / radiance
        cx, cy = int(W * 0.28), int(H * 0.28)
        for i in range(12):
            ang = (math.pi * 2 * i) / 12
            x2 = cx + int(math.cos(ang) * 260)
            y2 = cy + int(math.sin(ang) * 160)
            d.line([(cx, cy), (x2, y2)], fill=(*accent, 55), width=6)
        d.ellipse((cx - 70, cy - 70, cx + 70, cy + 70), fill=(*accent, 120))

    if mood in {"aarti", "meditative", "temple"}:
        # Diya row
        for i, x in enumerate(range(90, 520, 70)):
            y = int(H * 0.58) + (i % 2) * 8
            d.ellipse((x, y, x + 36, y + 18), fill=(40, 24, 10, 200))
            d.ellipse((x + 10, y - 28, x + 26, y - 4), fill=(*accent, 210))
            d.ellipse((x + 14, y - 40, x + 22, y - 26), fill=(255, 240, 180, 180))

    if mood == "meditative":
        # Soft mandala rings left
        cx, cy = int(W * 0.30), int(H * 0.36)
        for r in (40, 80, 120, 160):
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(*accent, 70), width=3)

    if mood == "sankirtana":
        # Energetic arcs
        for i in range(5):
            y0 = 80 + i * 40
            d.arc((40, y0, 520, y0 + 280), start=200, end=340, fill=(*accent, 90), width=5)

    layer = layer.filter(ImageFilter.GaussianBlur(0.6))
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def compose_thumbnail(
    *,
    title: str,
    deity: str | None,
    logo_path: str | Path | None,
    deity_image_path: str | Path | None = None,
    out_path: str | Path,
    lyrics: str | None = None,
    style_prompt: str | None = None,
    daypart: str | None = None,
    subtitle: str | None = None,
    prefer_photo: bool = False,
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    mood = infer_mood(lyrics=lyrics, style_prompt=style_prompt, deity=deity, daypart=daypart)
    dark, mid, accent = _palette_for(deity)

    # Mood shifts palette slightly
    if mood == "dawn":
        mid = tuple(min(255, c + 30) for c in mid)  # type: ignore[assignment]
        accent = tuple(min(255, c + 20) for c in accent)  # type: ignore[assignment]
    elif mood == "aarti":
        dark = tuple(max(0, c - 8) for c in dark)  # type: ignore[assignment]

    base = _vertical_gradient((W, H), dark, mid)
    has_photo = bool(deity_image_path and Path(deity_image_path).exists())

    if has_photo:
        photo = Image.open(deity_image_path).convert("RGB")
        photo = _cover(photo, (W, H))
        if prefer_photo:
            # AI / uploaded still is the hero — light grade only
            photo = ImageEnhance.Brightness(photo).enhance(0.88)
            photo = ImageEnhance.Color(photo).enhance(1.05)
            base = Image.blend(base, photo, 0.88)
        else:
            photo = ImageEnhance.Brightness(photo).enhance(0.78)
            photo = ImageEnhance.Color(photo).enhance(1.08)
            base = Image.blend(base, photo, 0.55)

    # Procedural temple art only when we lack a strong photo background
    if not (has_photo and prefer_photo):
        base = _draw_temple_scene(base, accent=accent, mid=mid, mood=mood)

    # Ultra-premium cinematic grade (match Ragam Spiritual reference thumbs)
    if prefer_photo and has_photo:
        base = ImageEnhance.Color(base).enhance(1.18)
        base = ImageEnhance.Contrast(base).enhance(1.14)
        base = ImageEnhance.Sharpness(base).enhance(1.12)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    cx, cy = (int(W * 0.32), int(H * 0.38)) if (prefer_photo and has_photo) else (int(W * 0.62), int(H * 0.36))
    for i, alpha in enumerate((34, 20, 12)):
        r = 280 - i * 55
        gdraw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 150, 40, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(38))
    base = Image.alpha_composite(base.convert("RGBA"), glow).convert("RGB")

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    text_on_right = bool(prefer_photo and has_photo)
    if text_on_right:
        left = int(W * 0.40)
        for x in range(left, W):
            t = max(0.0, min(1.0, (x - left) / max(1, W - left)))
            a = int(25 + 165 * (t**1.15))
            od.line([(x, 0), (x, H)], fill=(0, 0, 0, a))
        top = int(H * 0.70)
        for y in range(top, H):
            t = max(0.0, min(1.0, (y - top) / max(1, H - top)))
            od.line([(0, y), (W, y)], fill=(0, 0, 0, int(35 + 100 * t)))
    else:
        grad_top = int(H * 0.45)
        for y in range(grad_top, H):
            t = max(0.0, min(1.0, (y - grad_top) / max(1, H - grad_top)))
            od.line([(0, y), (W, y)], fill=(0, 0, 0, int(40 + 190 * (t**1.15))))
    canvas = Image.alpha_composite(base.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(canvas)
    title_font = load_telugu_font(168)
    hook_font = load_telugu_font(56)
    brand_font = load_telugu_font(32)

    hook = thumbnail_hook_title(title.strip() or "Ragam Spiritual", max_words=4, max_chars=28)
    if hook and not hook.endswith(("!", "।")):
        hook = f"{hook}!"
    pallavi = extract_pallavi_line(lyrics)
    sub_line = sanitize_overlay_text(subtitle, max_len=40) if subtitle else ""
    if not sub_line or sub_line.lower() in {hook.lower().rstrip("!"), "ragam spiritual"}:
        sub_line = sanitize_overlay_text(pallavi, max_len=36) if pallavi else ""
        if sub_line and thumbnail_hook_title(sub_line, max_words=4, max_chars=28) == hook.rstrip("!"):
            sub_line = ""

    max_text_w = int(W * 0.52) if text_on_right else W - 160
    size = 172
    lines = _wrap(draw, hook, title_font, max_text_w)[:2]
    while size > 100:
        title_font = load_telugu_font(size)
        lines = _wrap(draw, hook, title_font, max_text_w)[:2]
        too_wide = any(draw.textlength(ln, font=title_font) > max_text_w for ln in lines)
        if len(lines) <= 2 and not too_wide:
            break
        size -= 8

    line_gap = int(getattr(title_font, "size", 100) * 1.12)
    widest = max((draw.textlength(ln, font=title_font) for ln in lines), default=200)
    stroke_w = max(10, int(getattr(title_font, "size", 100) * 0.11))
    block_h = line_gap * len(lines) + (80 if sub_line else 0)

    if text_on_right:
        x = int(W * 0.46)
        y = int(H * 0.30)
        if x + widest > W - 48:
            x = int(W - 48 - widest)
        x = max(int(W * 0.40), x)
    else:
        x = 48
        y = max(int(H * 0.48), H - 56 - block_h)

    _draw_red_energy_splash(
        canvas, x=x - 40, y=y - 30, width=int(widest) + 80, height=block_h + 40
    )

    for line in lines:
        _draw_premium_gold_text(canvas, (x, y), line, font=title_font, stroke_width=stroke_w)
        y += line_gap

    if sub_line:
        y += 14
        hook_lines = _wrap(draw, sub_line, hook_font, max_text_w)[:1]
        for line in hook_lines:
            lw = draw.textlength(line, font=hook_font)
            mid = int(x + lw / 2)
            banner = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            bd = ImageDraw.Draw(banner)
            pad_x, pad_y = 28, 14
            bd.rounded_rectangle(
                (
                    x - pad_x,
                    y - pad_y,
                    x + lw + pad_x,
                    y + int(getattr(hook_font, "size", 56)) + pad_y,
                ),
                radius=10,
                fill=(90, 10, 15, 200),
                outline=(255, 190, 70, 230),
                width=3,
            )
            canvas.alpha_composite(banner)
            _draw_filigree(
                draw, mid, y - pad_y - 8, half_w=min(160, int(lw / 2) + 24), color=(255, 205, 90, 230)
            )
            _draw_yt_text(
                draw,
                (x, y),
                line,
                font=hook_font,
                fill=(255, 255, 255, 255),
                stroke_width=max(4, stroke_w - 4),
                stroke_fill=(40, 10, 0, 255),
                shadow=(2, 3),
            )
            _draw_filigree(
                draw,
                mid,
                y + int(getattr(hook_font, "size", 56)) + pad_y + 6,
                half_w=min(160, int(lw / 2) + 24),
                color=(255, 205, 90, 210),
            )

    # Channel logo TOP-LEFT (Lakshmi / Hanuman reference layout)
    if logo_path and Path(logo_path).exists():
        logo = Image.open(logo_path).convert("RGBA")
        max_logo = 200
        lw, lh = logo.size
        scale = min(max_logo / lw, max_logo / lh, 1.0)
        logo = logo.resize((max(1, int(lw * scale)), max(1, int(lh * scale))), Image.Resampling.LANCZOS)
        pad = 28
        lx, ly = pad, pad
        plate = Image.new("RGBA", (logo.width + 28, logo.height + 28), (0, 0, 0, 0))
        pld = ImageDraw.Draw(plate)
        pld.rounded_rectangle(
            (0, 0, plate.width - 1, plate.height - 1),
            radius=16,
            fill=(0, 0, 0, 150),
            outline=(255, 200, 80, 160),
            width=2,
        )
        canvas.alpha_composite(plate, (lx - 14, ly - 14))
        canvas.alpha_composite(logo, (lx, ly))
    else:
        brand = "RAGAM"
        bw = draw.textlength(brand, font=brand_font)
        draw.rounded_rectangle((20, 20, 20 + int(bw) + 36, 78), radius=12, fill=(0, 0, 0, 170))
        draw.text((38, 36), brand, font=brand_font, fill=(255, 220, 140, 255))

    final = canvas.convert("RGB")
    final.save(out, format="JPEG", quality=95, optimize=True, subsampling=0)
    return out
