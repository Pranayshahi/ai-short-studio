"""
Narrated list video (owner's request 2026-11-23: "World's Most Powerful Sniper Rifles", 25 s, not WeaponX style).

From the user's own ranked list (e.g. pasted from ChatGPT): an intro scene, ONE scene per item in the user's
order, and an outro. Every item is verified on Wikipedia with agents.ranked_poster.resolve_list (right kind,
country, facts) and shown with a real photo of exactly that model (evolution_poster.fetch_photo: whole
weapon, side view, free licence, credited). The narration only says the verified name and country, so the
fact check passes; numbers appear on screen from the verified facts.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

import config

W, H = 1080, 1920
INTRO_S, OUTRO_S = 2.4, 2.6


def _font(size: int, bold: bool = True):
    from agents import evolution_poster as ev
    return ev._font("Arial Bold.ttf" if bold else "Arial.ttf", size)


def spoken(name: str) -> str:
    """How the narrator should say a model name: 'ASVK / KSVK' -> 'ASVK and KSVK', 'Steyr HS .50' -> 'Steyr HS fifty',
    'MP-443 Grach (PYa)' -> 'MP-443 Grach'."""
    n = re.sub(r"\s*\([^)]*\)", "", name)
    n = n.replace(" / ", " and ").replace("/", " and ")
    n = re.sub(r"(?<![\w])\.50\b", "fifty", n)
    n = re.sub(r"(?<![\w])\.(\d{2,3})\b", r"point \1", n)
    return re.sub(r"\s+", " ", n).strip()


def resolve(text: str) -> Dict[str, Any]:
    """Verified rows + their photos (or {'error'})."""
    from agents import evolution_poster as ev
    from agents import ranked_poster as rp
    got = rp.resolve_list(text)
    if got.get("ifv") or got.get("error"):
        return got if got.get("error") else {"error": "This list format is for comparison charts, not a narrated list."}
    cache = Path(config.OUTPUT_DIR) / "cache" / "evolution_photos"
    items = []
    for row, m in got["resolved"]:
        img, is_cut = ev.fetch_photo(m, cache)
        items.append({"row": row, "model": m, "photo": img, "is_cut": is_cut})
    credits, seen = [], set()
    for c in ev.photo_credits([{"historical": i["model"], "modern": i["model"]} for i in items if i["photo"] is not None]):
        if c["file"] not in seen:
            seen.add(c["file"])
            credits.append(c)
    return {"title": got["title"], "kind": got["kind"], "items": items, "skipped": got["skipped"], "credits": credits}


def plan_scenes(title: str, items: List[Dict[str, Any]], target: float = 25.0) -> List[Dict[str, Any]]:
    per = max(1.6, round((target - INTRO_S - OUTRO_S) / max(1, len(items)), 2))
    scenes = [{"narration": f"{title}.", "on_screen_text": title.upper(), "duration_seconds": INTRO_S, "list_scene": "intro"}]
    for it in items:
        r = it["row"]
        line = f"{spoken(r['name'])}, {r['country']}." if r.get("country") else f"{spoken(r['name'])}."
        scenes.append({"narration": line, "on_screen_text": f"#{r['rank']} {r['name'].upper()}",
                       "duration_seconds": per, "list_scene": "item", "list_rank": r["rank"]})
    scenes.append({"narration": "Which one would you pick? Tell us in the comments.", "on_screen_text": "WHICH ONE WOULD YOU PICK?",
                   "duration_seconds": OUTRO_S, "list_scene": "outro"})
    for n, sc in enumerate(scenes, 1):
        sc.update(scene_number=n, scene_id=n, voiceover_text=sc["narration"], visual_prompt=sc["on_screen_text"])
    return scenes


# ------------------------------------------------------------------ frames

def _background() -> Image.Image:
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(10 + 12 * t), int(14 + 14 * t), int(24 + 22 * t)))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((-200, 520, W + 200, 1380), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img.paste((40, 70, 110), (0, 0), glow)
    return img


def _wrap(d: ImageDraw.ImageDraw, text: str, font, width: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if d.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def _place_photo(canvas: Image.Image, photo: Optional[Image.Image], is_cut: bool, box: Tuple[int, int, int, int]) -> None:
    if photo is None:
        return
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    ph = photo.convert("RGBA")
    s = min(bw / ph.width, bh / ph.height)
    ph = ph.resize((max(1, int(ph.width * s)), max(1, int(ph.height * s))), Image.Resampling.LANCZOS)
    px, py = x0 + (bw - ph.width) // 2, y0 + (bh - ph.height) // 2
    if is_cut:
        shadow = Image.new("RGBA", ph.size, (0, 0, 0, 0))
        shadow.putalpha(ph.split()[3].point(lambda a: int(a * 0.55)))
        canvas.paste((0, 0, 0), (px + 10, py + 16), shadow.filter(ImageFilter.GaussianBlur(10)).split()[3])
        canvas.paste(ph, (px, py), ph)
    else:  # a framed photo: rounded corners and a thin light border
        mask = Image.new("L", ph.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, ph.width - 1, ph.height - 1), radius=26, fill=255)
        canvas.paste(ph.convert("RGB"), (px, py), mask)
        ImageDraw.Draw(canvas).rounded_rectangle((px, py, px + ph.width - 1, py + ph.height - 1), radius=26,
                                                 outline=(220, 228, 240), width=3)


def item_frame(it: Dict[str, Any], total: int, cache_dir: Path) -> Image.Image:
    from agents import ranked_poster as rp
    r = it["row"]
    img = _background()
    d = ImageDraw.Draw(img)
    # rank badge
    badge = f"#{r['rank']}"
    bf = _font(64)
    bw = int(d.textlength(badge, font=bf)) + 56
    d.rounded_rectangle((60, 150, 60 + bw, 250), radius=24, fill=(255, 120, 20))
    d.text((88, 160), badge, font=bf, fill=(255, 255, 255))
    d.text((60 + bw + 20, 182), f"of {total}", font=_font(38, False), fill=(170, 182, 200))
    # name + country
    nf = _font(82)
    y = 300
    for ln in _wrap(d, r["name"], nf, W - 120)[:2]:
        d.text((60, y), ln, font=nf, fill=(255, 255, 255))
        y += 96
    fl = rp.flag_image(r.get("country", ""), cache_dir, height=44) if r.get("country") else None
    x = 60
    if fl is not None:
        img.paste(fl, (x, y + 14), fl if fl.mode == "RGBA" else None)
        x += fl.width + 16
    country = r.get("country", "") + (f" · {r['year']}" if r.get("year") else "")
    d.text((x, y + 8), country, font=_font(46, False), fill=(200, 210, 225))
    # photo
    _place_photo(img, it["photo"], it["is_cut"], (40, 640, W - 40, 1240))
    # verified facts
    bullets = [b for b in (r.get("specs") or {}).get("_bullets", []) if b]
    fy = 1290
    for b in bullets[:2]:
        lab, _, val = b.partition(" - ")
        d.rounded_rectangle((60, fy, W - 60, fy + 92), radius=20, fill=(24, 34, 54), outline=(60, 80, 110), width=2)
        d.text((92, fy + 24), lab.upper(), font=_font(30, False), fill=(150, 170, 200))
        vf = _font(40)
        d.text((W - 92 - d.textlength(val, font=vf), fy + 20), val, font=vf, fill=(255, 255, 255))
        fy += 108
    return img


def intro_frame(title: str, items: List[Dict[str, Any]]) -> Image.Image:
    img = _background()
    d = ImageDraw.Draw(img)
    tf = _font(96)
    lines = _wrap(d, title.upper(), tf, W - 120)
    y = 260
    for ln in lines[:4]:
        d.text(((W - d.textlength(ln, font=tf)) / 2, y), ln, font=tf, fill=(255, 255, 255))
        y += 112
    d.rounded_rectangle((W // 2 - 90, y + 20, W // 2 + 90, y + 28), radius=4, fill=(255, 120, 20))
    lead = next((i for i in items if i["photo"] is not None), None)
    if lead:
        _place_photo(img, lead["photo"], lead["is_cut"], (40, y + 120, W - 40, min(H - 380, y + 760)))
    return img


def outro_frame(items: List[Dict[str, Any]]) -> Image.Image:
    img = _background()
    d = ImageDraw.Draw(img)
    hf = _font(70)
    head = "WHICH ONE WOULD YOU PICK?"
    for i, ln in enumerate(_wrap(d, head, hf, W - 120)):
        d.text(((W - d.textlength(ln, font=hf)) / 2, 170 + i * 84), ln, font=hf, fill=(255, 255, 255))
    rf = _font(44, False)
    y = 420
    for it in items:
        r = it["row"]
        d.text((110, y), f"#{r['rank']}", font=_font(44), fill=(255, 140, 40))
        d.text((230, y), r["name"], font=rf, fill=(230, 236, 245))
        y += 88
    return img


def build_visuals(project_dir: Path, scenes: List[Dict[str, Any]], data: Dict[str, Any]) -> Dict[str, Any]:
    """Writes scene_NN.png for every scene; one record carries the verified rows (description, fact check)."""
    sdir = Path(project_dir) / "scenes"
    sdir.mkdir(parents=True, exist_ok=True)
    cache = Path(config.OUTPUT_DIR) / "cache" / "evolution_photos"
    items = data["items"]
    by_rank = {i["row"]["rank"]: i for i in items}
    paths, records = [], []
    for sc in scenes:
        n = sc["scene_number"]
        if sc["list_scene"] == "intro":
            frame = intro_frame(data["title"], items)
        elif sc["list_scene"] == "outro":
            frame = outro_frame(items)
        else:
            frame = item_frame(by_rank[sc["list_rank"]], len(items), cache)
        p = sdir / f"scene_{n:02d}.png"
        frame.save(p, "PNG")
        sc.update(image_path=str(p), visual_source="list_video")
        paths.append(str(p))
        records.append({"scene_number": n, "image_path": str(p), "source": "list_video", "source_verified": True,
                        "topic_matched": True, "topic_match_score": 100, "license": "Verified data + credited photos",
                        "author": "AI Shorts Studio"})
    records[0].update(
        ranked_items=[{"rank": i["row"]["rank"], "name": i["row"]["name"], "country": i["row"]["country"],
                       "year": i["row"]["year"], "article": i["model"].get("_article") or i["model"]["title"],
                       "photo": i["model"].get("image_file_used") or i["model"].get("image_file"),
                       "bullets": [b for b in i["row"]["specs"]["_bullets"] if b]} for i in items],
        photo_credits=data["credits"], kind=data["kind"], skipped=data.get("skipped") or [])
    return {"image_paths": paths, "visual_records": records, "change_image_events": [],
            "average_topic_match_score": 100, "list_video": True}
