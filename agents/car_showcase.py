"""
Full-car showcase scenes for car videos (user request 2026-11-21).

The beat-cut edit fills the vertical frame, so landscape car photos are cropped to a door, a wheel or a
headlight. Two showcase scenes per video show the WHOLE car instead: the car is cut out of its original,
uncropped photo and animated on a styled backdrop from start to end:
  slide-in with motion blur + speed lines -> beat flash & shake -> light sweep across the body with a rim
  glow and slow push-in -> car name + spec -> zoom punch into the next cut.
A photo is only used when the cut-out car is complete (not clipped by the photo edges), a whole-car view
(not a wheel/interior/engine), not crowded with people, and large enough. No good photo -> no showcase.
"""
from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFilter

import config
from agents.car_title_cards import FPS, H, W, _font, _writer, card_durations

SHOWCASE_BEATS = 6
EDGE_MARGIN = 0.015      # the car must not touch the photo's left/right/top edge (= clipped)
MIN_AREA = 0.10          # car mask covers at least 10% of the photo
ASPECT_RANGE = (1.25, 4.5)  # whole-car views are wide


def showcase_seconds(bpm: float) -> float:
    return round(SHOWCASE_BEATS * 60.0 / float(bpm or 130.0), 3)


def _cache() -> Path:
    d = Path(config.OUTPUT_DIR) / "cache" / "car_showcase"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(url: str) -> Optional[Image.Image]:
    if not url or not url.startswith("http"):
        return None
    f = _cache() / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg")
    if not f.exists():
        try:
            from agents import equipment_catalog as ec
            r = requests.get(url, headers=ec.HEADERS, timeout=30)
            if r.status_code != 200 or len(r.content) < 20000:
                return None
            f.write_bytes(r.content)
        except Exception:
            return None
    try:
        return Image.open(f).convert("RGB")
    except Exception:
        return None


def full_car_cutout(photo: Image.Image) -> Optional[Tuple[Image.Image, float]]:
    """(cutout RGBA cropped to the car, quality score) when the photo shows a complete car, else None."""
    from agents import evolution_poster as ev
    res = ev._cutout(photo, with_box=True)
    if not res:
        return None
    cut, (x0, y0, x1, y1) = res
    alpha = cut.split()[3].point(lambda v: 255 if v > 40 else 0)
    pw, ph = photo.size
    mx, my = pw * EDGE_MARGIN, ph * EDGE_MARGIN
    if x0 <= mx or x1 >= pw - mx or y0 <= my:
        return None  # clipped by the photo edge: not the full car
    area = (sum(1 for v in alpha.resize((80, 80)).getdata() if v) / (80 * 80)) * ((x1 - x0) * (y1 - y0)) / (pw * ph)
    aspect = (x1 - x0) / max(1, (y1 - y0))
    if area < MIN_AREA or not (ASPECT_RANGE[0] <= aspect <= ASPECT_RANGE[1]):
        return None
    if not ev._exterior_ok(cut, "car"):
        return None
    centered = 1 - abs(((x0 + x1) / 2) / pw - 0.5)
    return cut, area * 2 + centered


def pick_full_car_photos(visual_records: List[Dict[str, Any]], n: int = 2) -> List[Dict[str, Any]]:
    """The best n complete-car photos among the video's own (verified) photos."""
    found = []
    for rec in visual_records:
        if rec.get("source") == "manual_upload":
            # New Launch: the user's own photo (clips are not used for the showcase)
            if rec.get("media_type") != "image" or not rec.get("local_path"):
                continue
            try:
                photo = Image.open(rec["local_path"]).convert("RGB")
            except Exception:
                continue
        elif rec.get("source") != "web_free":
            continue
        else:
            photo = _download(rec.get("source_url") or "")
        if photo is None:
            continue
        res = full_car_cutout(photo)
        if res:
            found.append({"record": rec, "photo": photo, "cut": res[0], "score": res[1]})
        if len(found) >= n + 3:
            break
    found.sort(key=lambda x: -x["score"])
    return found[:n]


# ------------------------------------------------------------------ render

def _paste(frame: Image.Image, img: Image.Image, x: int, y: int) -> None:
    """alpha_composite that tolerates positions partly off-screen (slide-in starts outside the frame)."""
    l, t = max(0, -x), max(0, -y)
    r, b = min(img.width, frame.width - x), min(img.height, frame.height - y)
    if r <= l or b <= t:
        return
    frame.alpha_composite(img.crop((l, t, r, b)), (x + l, y + t))


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _backdrop(photo: Image.Image) -> Image.Image:
    """Blurred, darkened version of the same photo (cover fill) + vignette + floor glow."""
    s = max(W / photo.width, H / photo.height)
    bg = photo.resize((int(photo.width * s) + 1, int(photo.height * s) + 1)).crop((0, 0, W, H))
    bg = bg.filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (6, 8, 14)), 0.62)
    vign = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vign).ellipse((-W * 0.3, H * 0.15, W * 1.3, H * 0.95), fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(140))
    bg = Image.composite(bg, Image.new("RGB", (W, H), (2, 3, 6)), vign)
    floor = Image.new("L", (W, H), 0)
    ImageDraw.Draw(floor).ellipse((W * 0.05, H * 0.60, W * 0.95, H * 0.74), fill=120)
    floor = floor.filter(ImageFilter.GaussianBlur(50))
    return Image.composite(Image.new("RGB", (W, H), (40, 80, 110)), bg, floor)


def _motion_blur(img: Image.Image, strength: int) -> Image.Image:
    """Horizontal motion blur (squash + stretch keeps it fast)."""
    if strength <= 1:
        return img
    w, h = img.size
    small = img.resize((max(1, w // strength), h), Image.Resampling.BILINEAR)
    return small.resize((w, h), Image.Resampling.BILINEAR)


def render_showcase(cut: Image.Image, photo: Image.Image, car_name: str, spec: str, out_path: Path,
                    seconds: float, from_left: bool = False) -> Path:
    n = max(15, int(round(seconds * FPS)))
    base = _backdrop(photo).convert("RGBA")
    scale = (W * 0.94) / cut.width
    car = cut.resize((int(cut.width * scale), int(cut.height * scale)), Image.Resampling.LANCZOS)
    if car.height > H * 0.42:
        s2 = (H * 0.42) / car.height
        car = car.resize((int(car.width * s2), int(car.height * s2)), Image.Resampling.LANCZOS)
    cx, cy = W // 2, int(H * 0.50)
    refl = car.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    refl = refl.resize((refl.width, max(1, int(refl.height * 0.55))))  # a short, faint floor reflection
    ra = refl.split()[3]
    fade = Image.linear_gradient("L").resize(refl.size).point(lambda v: int((255 - v) * 0.17))
    refl.putalpha(Image.composite(fade, Image.new("L", refl.size, 0), ra))
    glow_src = car.split()[3].filter(ImageFilter.GaussianBlur(26))
    f_name = _font(104 if len(car_name) <= 16 else 84, "impact")
    f_spec = _font(44, "din")
    name = car_name.upper()
    spec_txt = (spec or "").upper()[:46]
    direction = -1 if from_left else 1
    proc = _writer(out_path, seconds)
    for i in range(n):
        p = i / (n - 1)
        frame = base.copy()
        arrive = _ease_out(p / 0.22)
        offset = int(direction * W * 1.1 * (1 - arrive))
        speed = 1 - arrive
        push = 1.0 + 0.07 * max(0.0, (p - 0.25) / 0.75)
        punch = max(0.0, (p - 0.90) / 0.10)
        zoom = push + 0.25 * punch ** 2
        shake = 0
        if 0.22 <= p <= 0.32:
            shake = int(14 * math.sin(p * 220) * (1 - (p - 0.22) / 0.10))
        cw, ch = int(car.width * zoom), int(car.height * zoom)
        c = car.resize((cw, ch), Image.Resampling.BICUBIC) if zoom != 1 else car.copy()
        if speed > 0.05:
            c = _motion_blur(c, int(2 + 30 * speed))
            d = ImageDraw.Draw(frame)
            for k in range(14):  # speed lines
                y = int(cy - ch * 0.6 + (k * 97 % max(1, int(ch * 1.2))))
                length = int(W * (0.2 + 0.5 * ((k * 37) % 10) / 10) * speed)
                x = int(W / 2 + offset - direction * length)
                d.line((x, y, x + direction * length, y), fill=(220, 240, 255, int(140 * speed)), width=3)
        x = cx - cw // 2 + offset + shake
        y = cy - ch // 2
        # rim glow behind the car (after it lands)
        ga = 0.55 * max(0.0, min(1.0, (p - 0.22) / 0.2))
        if ga > 0:
            g = glow_src.resize((cw, ch)).point(lambda v: int(v * ga))
            glow = Image.new("RGBA", (cw, ch), (0, 229, 255, 0))
            glow.putalpha(g)
            _paste(frame, glow, x, y)
        # floor reflection
        rr = refl.resize((cw, int(refl.height * zoom)))
        _paste(frame, rr, x, y + ch - 6)
        # light sweep across the body
        sp = (p - 0.32) / 0.40
        if 0 <= sp <= 1:
            band = Image.new("L", (cw, ch), 0)
            bx = int(-cw * 0.3 + sp * cw * 1.6) if not from_left else int(cw * 1.3 - sp * cw * 1.6)
            ImageDraw.Draw(band).polygon([(bx, 0), (bx + cw * 0.10, 0), (bx + cw * 0.10 - ch * 0.5, ch), (bx - ch * 0.5, ch)], fill=170)
            band = band.filter(ImageFilter.GaussianBlur(14))
            band = Image.composite(band, Image.new("L", (cw, ch), 0), c.split()[3])
            shine = Image.new("RGBA", (cw, ch), (255, 255, 255, 0))
            shine.putalpha(band)
            c.alpha_composite(shine)
        _paste(frame, c, x, y)
        # name + spec
        ta = _ease_out((p - 0.38) / 0.18) * (1 - punch)
        if ta > 0:
            d = ImageDraw.Draw(frame)
            ty = int(H * 0.76 + 30 * (1 - ta))
            d.text((W // 2, ty), name, font=f_name, fill=(255, 255, 255, int(255 * ta)), anchor="mm",
                   stroke_width=5, stroke_fill=(0, 0, 0, int(220 * ta)))
            if spec_txt:
                tw = d.textlength(spec_txt, font=f_spec)
                d.rounded_rectangle((W / 2 - tw / 2 - 24, ty + 62, W / 2 + tw / 2 + 24, ty + 124), radius=30,
                                    fill=(0, 0, 0, int(170 * ta)), outline=(0, 229, 255, int(230 * ta)), width=3)
                d.text((W // 2, ty + 93), spec_txt, font=f_spec, fill=(0, 229, 255, int(255 * ta)), anchor="mm")
        # flashes: on the landing beat and into the next cut
        fl = max(0.0, 1 - abs(p - 0.23) / 0.04)
        if fl > 0:
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(90 * fl))))
        if punch > 0:
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(180 * punch ** 2))))
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    return out_path


# ------------------------------------------------------------------ pipeline integration

def attach(project_dir: Path, scenes: List[Dict[str, Any]], image_paths: List[str],
           visual_records: List[Dict[str, Any]], car_plan: Dict[str, Any], car_name: str) -> Dict[str, Any]:
    """Renders up to two showcase scenes and inserts them into the edit (after the first car shot and
    before the end). Returns {'added': n, 'seconds': total showcase seconds}."""
    scenes_dir = Path(project_dir) / "scenes"
    picks = pick_full_car_photos(visual_records, n=2)
    if not picks:
        print("[CarShowcase] No complete full-car photo among the video's photos: no showcase scene")
        return {"added": 0, "seconds": 0.0}
    secs = showcase_seconds(car_plan.get("bpm") or 130.0)
    spec = car_plan.get("subtitle_spec") or ""
    name = car_plan.get("car_name") or car_name
    real = [i for i, s in enumerate(scenes) if not s.get("title_card")]
    positions = [real[1] if len(real) > 2 else (real[0] + 1 if real else 0), (real[-1] + 1) if real else len(scenes)]
    added = 0
    for k, (pick, pos) in enumerate(zip(picks, positions)):
        mp4 = render_showcase(pick["cut"], pick["photo"], name, spec, scenes_dir / f"showcase_{k + 1}.mp4", secs,
                              from_left=bool(k % 2))
        from agents.car_title_cards import still_of
        png = still_of(mp4, scenes_dir / f"showcase_{k + 1}.png", secs * 0.6)
        rec = pick["record"]
        scene = {"narration": "", "voiceover_text": "", "duration_seconds": secs, "beat_synced": True,
                 "title_card": "showcase", "visual_source": "car_showcase", "image_path": str(png),
                 "clip_path": str(mp4), "motion": "static", "speed_ramp": "none", "beat_sync": False, "effects": {}}
        ins = min(pos + added, len(scenes))
        scenes.insert(ins, scene)
        image_paths.insert(ins, str(png))
        added += 1
        # credit the photographer of the photo the showcase uses
        visual_records.append({**{k2: v for k2, v in rec.items() if k2 not in ("visual_quality", "scene_number")},
                               "source": "car_showcase", "image_path": str(png), "_showcase_slot": ins})
    # renumber scenes and records in scene order
    for i, sc in enumerate(scenes, 1):
        sc["scene_number"] = sc["scene_id"] = i
    by_path = {sc["image_path"]: sc["scene_number"] for sc in scenes}
    for r in visual_records:
        r.pop("_showcase_slot", None)
        if r.get("image_path") in by_path:
            r["scene_number"] = by_path[r["image_path"]]
    visual_records.sort(key=lambda r: r.get("scene_number") or 0)
    print(f"[CarShowcase] Added {added} full-car showcase scene(s) ({secs:.2f}s each)")
    return {"added": added, "seconds": round(secs * added, 3)}
