"""
Car video intro + outro cards (user request 2026-11-19).

Intro (~4 beats): the car BRAND LOGO on a dark studio backdrop with a reveal effect - scale-in with
de-blur, a light sweep across the logo, a flash on the beat, the brand name letter-spaced underneath,
then a zoom punch into the first car shot. No clean logo found -> the brand wordmark gets the same effect.

Outro (~6 beats): a professional end card - the hero shot blurred and darkened behind, slow push-in,
then staggered: small logo, car name, spec line between accent rules, channel handle + "SUBSCRIBE FOR
MORE" pill, and a fade to black.

Logos come from Wikipedia's file namespace (Commons/en.wikipedia), ranked strictly: exact
"<Brand> logo.svg"-style files first; photos (jpg) and unrelated files (stadiums, films, dealers) never.
"""
from __future__ import annotations

import io
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import config

W, H, FPS = 1080, 1920, 30
LOGO_DIR = Path(config.OUTPUT_DIR) / "cache" / "brand_logos"
_JUNK = re.compile(r"monaco|ford v|world|stadium|trattori|cigarette|espada|motorsport|diesel|\bse\b|finance|north america|"
                   r"center|centre|service|quito|sales|trofeo|bkk|bekleidung|clothing|team|racing|f1|formula|museum|"
                   r"dealer|night|building|sign|club|foundation|arena|\d{4}-\d{4}|\(\d{4}[-–]\d{4}\)|wortmarke|"
                   r"vodafone|mercedes(?!-benz)|cars?\s*\d|model|espada|tractor|bank|insurance|electric|energy", re.I)


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def _font(size: int, kind: str = "impact") -> ImageFont.FreeTypeFont:
    paths = {
        "impact": ["/System/Library/Fonts/Supplemental/Impact.ttf"],
        "din": ["/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"],
        "futura": ["/System/Library/Fonts/Supplemental/Futura.ttc", "/System/Library/Fonts/Supplemental/Futura.ttc"],
    }[kind] + ["/System/Library/Fonts/Supplemental/Arial Black.ttf", "/Library/Fonts/Arial Bold.ttf"]
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


# ------------------------------------------------------------------ logo

def brand_of(car_name: str, car_plan: Optional[Dict[str, Any]] = None) -> str:
    b = ((car_plan or {}).get("specs") or {}).get("brand") or ((car_plan or {}).get("headline_top") or "")
    if b and b.upper() not in ("SUPERCAR", ""):
        return b.strip().title() if b.isupper() else b.strip()
    return (car_name or "").split()[0] if car_name else ""


_ALLOWED = {"logo", "logos", "emblem", "badge", "wordmark", "crest", "vector", "hq", "official", "new", "old", "2d",
            "flat", "symbol", "icon", "automobili", "automotive", "automobiles", "motor", "motors", "company", "cars",
            "spa", "s", "p", "a", "ag", "gmbh", "inc", "ltd", "co", "black", "white", "color", "colour", "full",
            "italy", "germany", "japan", "uk", "england", "france", "usa", "sweden", "-", "and"}


def _rank(title: str, brand: str) -> int:
    """Higher = more likely THE brand logo. Any word besides the brand and generic logo words (a model
    like 'Urus', a business like 'Holding', a place, a team) disqualifies the file."""
    t = title[5:] if title.lower().startswith("file:") else title
    stem, ext = (t.rsplit(".", 1) + [""])[:2]
    ext = ext.lower()
    if ext not in ("svg", "png", "webp") or brand.lower() not in stem.lower() or _JUNK.search(stem):
        return -1
    words = [w for w in re.findall(r"[a-z0-9]+", stem.lower())]
    brand_words = set(re.findall(r"[a-z0-9]+", brand.lower()))
    extra = [w for w in words if w not in brand_words and w not in _ALLOWED and not re.fullmatch(r"(19|20)\d\d|\d", w)]
    if extra:
        return -1
    has_logo_word = any(w in ("logo", "logos", "emblem", "badge", "crest", "symbol") for w in words)
    score = 100 if has_logo_word else (80 if "wordmark" in words else 70)
    score -= 2 * (len(words) - len(brand_words))  # fewer extra words = more likely the main logo
    return score + (5 if ext == "svg" else 0)


def _api(params: Dict[str, Any]) -> Dict[str, Any]:
    from agents import equipment_catalog as ec
    for base in ("https://en.wikipedia.org/w/api.php", "https://commons.wikimedia.org/w/api.php"):
        try:
            r = requests.get(base, headers=ec.HEADERS, timeout=25, params={**params, "format": "json", "formatversion": 2})
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return {}


def find_logo(brand: str) -> Optional[Path]:
    """PNG (transparent where possible) of the brand's logo, cached; None if no clean logo exists."""
    if not brand:
        return None
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", brand.lower()).strip("_")
    cached = LOGO_DIR / f"{slug}.png"
    miss = LOGO_DIR / f"{slug}.none"
    if cached.exists():
        return cached
    if miss.exists():
        return None
    # The canonical file names first (search doesn't always surface them), then search results
    titles: List[str] = [f"File:{brand} logo.svg", f"File:{brand} Logo.svg", f"File:{brand}.svg", f"File:{brand} logo.png"]
    for q in (f"{brand} logo", f"{brand} emblem", f"{brand} badge"):
        data = _api({"action": "query", "list": "search", "srnamespace": 6, "srsearch": q, "srlimit": 15})
        titles += [h["title"] for h in data.get("query", {}).get("search", []) if h["title"] not in titles]
    ranked = sorted(((r, t) for t in titles if (r := _rank(t, brand)) >= 0), reverse=True)
    for _, title in ranked[:4]:
        info = _api({"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": 900})
        pages = info.get("query", {}).get("pages", [])
        ii = (pages[0].get("imageinfo") or [{}])[0] if pages else {}
        url = ii.get("thumburl") or ii.get("url")
        if not url:
            continue
        try:
            from agents import equipment_catalog as ec
            raw = requests.get(url, headers=ec.HEADERS, timeout=30)
            if raw.status_code != 200:
                continue
            img = Image.open(io.BytesIO(raw.content)).convert("RGBA")
        except Exception:
            continue
        img = _clean_logo(img)
        if img is None:
            continue
        img.save(cached)
        (LOGO_DIR / f"{slug}.source.txt").write_text(f"{title}\n{url}\n", encoding="utf-8")
        print(f"[CarTitleCards] Logo for {brand}: {title}")
        return cached
    miss.write_text("no clean logo found", encoding="utf-8")
    return None


def _clean_logo(img: Image.Image) -> Optional[Image.Image]:
    """Transparent background, trimmed; rejects photo-like images (too many colours)."""
    alpha = img.split()[3]
    opaque = alpha.getextrema()[0] > 250
    if opaque:  # no transparency: knock out a near-white (or near-black) background
        rgb = img.convert("RGB")
        corner = rgb.getpixel((2, 2))
        bg = Image.new("RGB", rgb.size, corner)
        diff = ImageOps.grayscale(Image.fromarray(__import__("numpy").abs(
            __import__("numpy").asarray(rgb, dtype="int16") - __import__("numpy").asarray(bg, dtype="int16")).astype("uint8")))
        mask = diff.point(lambda v: 255 if v > 28 else 0).filter(ImageFilter.GaussianBlur(0.8))
        img = rgb.convert("RGBA")
        img.putalpha(mask)
    bbox = img.split()[3].point(lambda v: 255 if v > 20 else 0).getbbox()
    if not bbox:
        return None
    img = img.crop(bbox)
    # A rendered vector logo comes with transparency (gradient crests have many colours, that's fine);
    # an opaque image with very many colours is a photograph, not a logo
    small = img.convert("RGB").resize((64, 64))
    if opaque and len(set(small.getdata())) > 1800:
        return None
    return img


def _light_version(logo: Image.Image) -> Image.Image:
    """Dark logos (black wordmarks) become a brushed-silver white so they read on the dark backdrop;
    colourful logos (crests, badges) are kept as they are."""
    if _luma(logo) >= 70:
        return logo
    a = logo.split()[3]
    grad = Image.linear_gradient("L").resize(logo.size).point(lambda v: 205 + int(50 * (1 - v / 255)))
    out = Image.merge("RGBA", (grad, grad, grad.point(lambda v: min(255, v + 6)), a))
    return out


def _luma(img: Image.Image) -> float:
    rgb = img.convert("RGB")
    a = img.split()[3]
    data = [(0.299 * r + 0.587 * g + 0.114 * b) for (r, g, b), al in zip(rgb.getdata(), a.getdata()) if al > 128]
    return sum(data) / len(data) if data else 255.0


# ------------------------------------------------------------------ helpers

def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _backdrop(seed_tint=(10, 14, 22)) -> Image.Image:
    """Dark studio backdrop with a soft spotlight and floor reflection band."""
    bg = Image.new("RGB", (W, H), seed_tint)
    glow = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(glow)
    d.ellipse((W * 0.05, H * 0.22, W * 0.95, H * 0.68), fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    light = Image.new("RGB", (W, H), (58, 66, 84))
    bg = Image.composite(light, bg, glow)
    vign = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vign).rectangle((0, 0, W, H), fill=0)
    return bg


def _letterspaced(draw: ImageDraw.ImageDraw, text: str, font, cx: int, y: int, spacing: int, fill) -> None:
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + spacing


def _writer(out_path: Path, seconds: float):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "fast",
                             "-crf", "18", "-pix_fmt", "yuv420p", "-t", f"{seconds:.3f}", str(out_path)],
                            stdin=subprocess.PIPE)
    return proc


# ------------------------------------------------------------------ intro

def render_intro(brand: str, logo_path: Optional[Path], out_path: Path, seconds: float = 1.85) -> Path:
    n = max(12, int(round(seconds * FPS)))
    base = _backdrop()
    logo = Image.open(logo_path).convert("RGBA") if logo_path and Path(logo_path).exists() else None
    if logo is not None:
        scale = min(W * 0.74 / logo.width, H * 0.28 / logo.height)
        logo = logo.resize((max(1, int(logo.width * scale)), max(1, int(logo.height * scale))), Image.Resampling.LANCZOS)
        logo = _light_version(logo)
    dark_logo = False
    f_brand = _font(64, "din")
    f_word = _font(150, "impact")
    word = brand.upper()
    proc = _writer(out_path, seconds)
    for i in range(n):
        t = i / FPS
        p = i / (n - 1)
        frame = base.copy().convert("RGBA")
        # reveal 0-30%, hold + sweep 25-70%, punch-out 85-100%
        rev = _ease_out(p / 0.30)
        punch = max(0.0, (p - 0.85) / 0.15)
        zoom = 1.18 - 0.18 * rev + 0.22 * punch ** 2
        opacity = rev * (1 - 0.0 * punch)
        cy = int(H * 0.45)
        if logo is not None:
            lw, lh = max(1, int(logo.width * zoom)), max(1, int(logo.height * zoom))
            lg = logo.resize((lw, lh), Image.Resampling.BICUBIC)
            if rev < 1:
                lg = lg.filter(ImageFilter.GaussianBlur(6 * (1 - rev)))
            if dark_logo:  # a dark logo gets a soft light halo so it reads on the dark backdrop
                halo = Image.new("L", (W, H), 0)
                ImageDraw.Draw(halo).ellipse((W / 2 - lw * 0.75, cy - lh * 0.95, W / 2 + lw * 0.75, cy + lh * 0.95), fill=int(150 * rev))
                halo = halo.filter(ImageFilter.GaussianBlur(70))
                frame.alpha_composite(Image.merge("RGBA", (Image.new("L", (W, H), 235),) * 3 + (halo,)))
            # glow behind the logo
            glow = lg.split()[3].filter(ImageFilter.GaussianBlur(28)).point(lambda v: int(v * 0.55 * rev))
            gl = Image.new("RGBA", lg.size, (0, 229, 255, 0))
            gl.putalpha(glow)
            pos = (W // 2 - lw // 2, cy - lh // 2)
            frame.alpha_composite(gl, pos)
            a = lg.split()[3].point(lambda v: int(v * opacity))
            lg.putalpha(a)
            # light sweep: a bright diagonal band crossing the logo (masked to the logo)
            sp = (p - 0.28) / 0.42
            if 0 <= sp <= 1:
                band = Image.new("L", lg.size, 0)
                bx = int(-lw * 0.4 + sp * lw * 1.8)
                ImageDraw.Draw(band).polygon([(bx, 0), (bx + lw * 0.18, 0), (bx + lw * 0.18 - lh * 0.6, lh), (bx - lh * 0.6, lh)], fill=200)
                band = band.filter(ImageFilter.GaussianBlur(10))
                band = Image.composite(band, Image.new("L", lg.size, 0), lg.split()[3])
                shine = Image.new("RGBA", lg.size, (255, 255, 255, 0))
                shine.putalpha(band)
                lg.alpha_composite(shine)
            frame.alpha_composite(lg, pos)
            name_y = cy + lh // 2 + 70
        else:
            # Wordmark fallback with the same reveal
            txt = Image.new("RGBA", (W, 260), (0, 0, 0, 0))
            dt = ImageDraw.Draw(txt)
            dt.text((W // 2, 130), word, font=f_word, fill=(255, 255, 255, int(255 * opacity)), anchor="mm",
                    stroke_width=2, stroke_fill=(0, 229, 255, int(200 * opacity)))
            tw, th = int(W * zoom), int(260 * zoom)
            txt = txt.resize((tw, th), Image.Resampling.BICUBIC)
            frame.alpha_composite(txt, (W // 2 - tw // 2, cy - th // 2))
            name_y = cy + 150
        # brand name under the logo, letter-spaced, fades in after the reveal
        if logo is not None:
            na = _ease_out((p - 0.35) / 0.25)
            if na > 0:
                dn = ImageDraw.Draw(frame)
                _letterspaced(dn, word, f_brand, W // 2, name_y, 18, (235, 240, 248, int(255 * na * (1 - punch))))
        # thin accent line that draws across under everything
        la = _ease_out((p - 0.30) / 0.35)
        if la > 0:
            dl = ImageDraw.Draw(frame)
            half = int(260 * la)
            dl.line((W // 2 - half, name_y + 100, W // 2 + half, name_y + 100), fill=(0, 229, 255, int(220 * (1 - punch))), width=4)
        # flash on the beat (when the reveal lands)
        fl = max(0.0, 1 - abs(p - 0.30) / 0.045)
        if fl > 0:
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(60 * fl))))
        # fade from black at the start, to white flash at the punch-out
        if p < 0.06:
            frame.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * (1 - p / 0.06)))))
        if punch > 0:
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(200 * punch ** 2))))
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    return out_path


# ------------------------------------------------------------------ outro

def render_outro(car_name: str, spec: str, handle: str, hero_path: Optional[str], logo_path: Optional[Path],
                 out_path: Path, seconds: float = 2.8) -> Path:
    n = max(15, int(round(seconds * FPS)))
    if hero_path and Path(hero_path).exists():
        hero = Image.open(hero_path).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)
        hero = hero.filter(ImageFilter.GaussianBlur(22))
        hero = Image.blend(hero, Image.new("RGB", (W, H), (6, 8, 14)), 0.58)
    else:
        hero = _backdrop()
    logo = Image.open(logo_path).convert("RGBA") if logo_path and Path(logo_path).exists() else None
    if logo is not None:
        s = min(440 / logo.width, 220 / logo.height)
        logo = _light_version(logo.resize((max(1, int(logo.width * s)), max(1, int(logo.height * s))), Image.Resampling.LANCZOS))
    name = car_name.upper()
    f_name = _font(128 if len(name) <= 14 else (104 if len(name) <= 20 else 84), "impact")
    f_spec = _font(48, "din")
    f_handle = _font(62, "din")
    f_sub = _font(42, "din")
    spec_txt = re.sub(r"\s+", " ", (spec or "").upper()).strip()
    proc = _writer(out_path, seconds)
    for i in range(n):
        p = i / (n - 1)
        z = 1.0 + 0.06 * p
        bw, bh = int(W * z), int(H * z)
        frame = hero.resize((bw, bh), Image.Resampling.BICUBIC).crop(((bw - W) // 2, (bh - H) // 2, (bw - W) // 2 + W, (bh - H) // 2 + H)).convert("RGBA")
        d = ImageDraw.Draw(frame)
        y = int(H * 0.30)
        a_logo = _ease_out(p / 0.18)
        if logo is not None:
            lg = logo.copy()
            lg.putalpha(lg.split()[3].point(lambda v: int(v * a_logo)))
            frame.alpha_composite(lg, (W // 2 - lg.width // 2, y - lg.height // 2 + int(20 * (1 - a_logo))))
            y += lg.height // 2 + 70
        else:
            y += 40
        a_name = _ease_out((p - 0.10) / 0.22)
        if a_name > 0:
            dy = int(30 * (1 - a_name))
            d.text((W // 2, y + 60 + dy), name, font=f_name, fill=(255, 255, 255, int(255 * a_name)), anchor="mm",
                   stroke_width=3, stroke_fill=(0, 0, 0, int(200 * a_name)))
        y += 150
        a_spec = _ease_out((p - 0.22) / 0.22)
        if a_spec > 0 and spec_txt:
            half = int(330 * a_spec)
            d.line((W // 2 - half, y, W // 2 + half, y), fill=(0, 229, 255, int(230 * a_spec)), width=3)
            d.text((W // 2, y + 46), spec_txt[:48], font=f_spec, fill=(220, 228, 240, int(255 * a_spec)), anchor="mm")
            d.line((W // 2 - half, y + 92, W // 2 + half, y + 92), fill=(0, 229, 255, int(230 * a_spec)), width=3)
        y += 230
        a_cta = _ease_out((p - 0.40) / 0.22)
        if a_cta > 0 and handle:
            d.text((W // 2, y), handle, font=f_handle, fill=(255, 255, 255, int(255 * a_cta)), anchor="mm")
            pill = "SUBSCRIBE FOR MORE"
            tw = d.textlength(pill, font=f_sub)
            px0, py0 = W // 2 - tw / 2 - 34, y + 50
            pulse = 1 + 0.04 * math.sin(p * math.pi * 6) * a_cta
            pw, ph = (tw + 68) * pulse, 70 * pulse
            d.rounded_rectangle((W // 2 - pw / 2, py0, W // 2 + pw / 2, py0 + ph), radius=int(ph / 2),
                                fill=(214, 26, 44, int(235 * a_cta)))
            d.text((W // 2, py0 + ph / 2), pill, font=f_sub, fill=(255, 255, 255, int(255 * a_cta)), anchor="mm")
        # cinematic letterbox bars + fade in from white (matches the cut from the last scene) and fade to black
        bar = int(120 * _ease_out(p / 0.2))
        d.rectangle((0, 0, W, bar), fill=(0, 0, 0, 255))
        d.rectangle((0, H - bar, W, H), fill=(0, 0, 0, 255))
        if p < 0.08:
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(160 * (1 - p / 0.08)))))
        if p > 0.82:
            frame.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * ((p - 0.82) / 0.18)))))
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    return out_path


def still_of(video: Path, out_png: Path, at: float) -> Path:
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", str(out_png)],
                   check=True, capture_output=True, timeout=60)
    return out_png


# ------------------------------------------------------------------ pipeline integration

def card_durations(bpm: float) -> Tuple[float, float]:
    """Intro = 4 beats, outro = 6 beats, so the cuts land on the music."""
    beat = 60.0 / float(bpm or 130.0)
    return round(4 * beat, 3), round(6 * beat, 3)


def attach(project_dir: Path, scenes: List[Dict[str, Any]], image_paths: List[str],
           visual_records: List[Dict[str, Any]], car_plan: Dict[str, Any], car_name: str,
           channel_handle: str = "") -> Dict[str, Any]:
    """Renders the intro/outro cards and inserts them as the first and last scenes (in place).
    Returns {'intro': path, 'outro': path, 'logo': source or None}."""
    scenes_dir = Path(project_dir) / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    # Never stack cards twice (re-runs)
    while scenes and scenes[0].get("title_card") in ("intro", "outro"):
        scenes.pop(0); image_paths.pop(0)
    while scenes and scenes[-1].get("title_card") in ("intro", "outro"):
        scenes.pop(); image_paths.pop()
    visual_records[:] = [r for r in visual_records if r.get("source") != "car_title_card"]

    brand = brand_of(car_name, car_plan)
    logo = None
    try:
        logo = find_logo(brand)
    except Exception as e:
        print(f"[CarTitleCards] Logo lookup failed for {brand}: {e}")
    intro_d, outro_d = card_durations(car_plan.get("bpm") or 130.0)
    intro_mp4 = render_intro(brand, logo, scenes_dir / "intro_card.mp4", intro_d)
    hero = next((p for p in image_paths if p and Path(p).exists()), None)
    hero_base = Path(hero).with_name(Path(hero).stem + "_base.png") if hero else None
    spec = car_plan.get("subtitle_spec") or ((car_plan.get("specs") or {}).get("spec")) or ""
    outro_mp4 = render_outro(car_plan.get("car_name") or car_name, spec, channel_handle,
                             str(hero_base if hero_base and hero_base.exists() else hero or ""), logo,
                             scenes_dir / "outro_card.mp4", outro_d)
    intro_png = still_of(intro_mp4, scenes_dir / "intro_card.png", intro_d * 0.6)
    outro_png = still_of(outro_mp4, scenes_dir / "outro_card.png", outro_d * 0.6)

    def card(kind: str, png: Path, mp4: Path, dur: float) -> Dict[str, Any]:
        return {"narration": "", "voiceover_text": "", "duration_seconds": dur, "beat_synced": True,
                "title_card": kind, "visual_source": f"car_{kind}", "image_path": str(png), "clip_path": str(mp4),
                "motion": "static", "speed_ramp": "none", "beat_sync": False, "effects": {},
                "visual_prompt": f"{brand} {kind} card"}
    scenes.insert(0, card("intro", intro_png, intro_mp4, intro_d))
    scenes.append(card("outro", outro_png, outro_mp4, outro_d))
    image_paths.insert(0, str(intro_png))
    image_paths.append(str(outro_png))
    for r in visual_records:
        r["scene_number"] = int(r.get("scene_number") or 0) + 1
    src = (LOGO_DIR / f"{re.sub(r'[^a-z0-9]+', '_', brand.lower()).strip('_')}.source.txt")
    logo_src = src.read_text(encoding="utf-8").splitlines()[0] if src.exists() else None
    for n, kind, png in ((1, "intro", intro_png), (len(scenes), "outro", outro_png)):
        visual_records.append({"scene_number": n, "image_path": str(png), "source": "car_title_card",
                               "source_provider": "AutoFlashX title card", "license": "Brand logo: " + (logo_src or "wordmark text"),
                               "source_verified": True, "topic_matched": True, "title_card": kind})
    visual_records.sort(key=lambda r: r.get("scene_number") or 0)
    for i, sc in enumerate(scenes, 1):
        sc["scene_number"] = sc["scene_id"] = i
    print(f"[CarTitleCards] Intro ({intro_d:.2f}s, logo: {logo_src or 'wordmark'}) and outro ({outro_d:.2f}s) added")
    return {"intro": str(intro_mp4), "outro": str(outro_mp4), "logo": logo_src}
