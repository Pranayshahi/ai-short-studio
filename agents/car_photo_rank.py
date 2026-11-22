"""
Car photo ranking: pick the BEST real photo for each scene of a car video, and frame it on the car.

Why (BMW i3 review, 2026-11-22): scenes got a tiny car in a landscape, a dashboard screen with German
text, cars sliced in half by a dead-centre 9:16 crop, and - once a few rejected photos had used up every
scene's attempts - AI cars that weren't the real model.

  analyse(path)            -> car share, shot type, subject box, fill, sharpness, brightness, score
  rank(candidates, dir)    -> downloaded + analysed candidates, unusable ones dropped, best first
  pick(ranked, wanted, used) -> best unused photo of the wanted shot type(s), else best unused overall
  render(info, out, variant) -> 1080x1920 frame framed on the car (crop, or full car over a blurred
                                backdrop when the car is too wide for a vertical crop)
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter

W, H = 1080, 1920

# Shot types (CLIP labels). Each scene asks for one or more of these.
SHOTS: Dict[str, str] = {
    "headlight": "a close-up of a car's glowing headlights in the dark",
    "front": "the front of a car seen head-on, showing the grille and headlights",
    "front34": "a whole car seen from the front three-quarter angle",
    "side": "a side profile view of a whole car",
    "rear": "the rear of a car showing its taillights",
    "interior": "the interior of a car with dashboard, screens and steering wheel",
    "charging": "an electric car plugged into a charging cable",
    "driving": "a car driving on a road with motion blur",
    "wheel": "a close-up of a car wheel and rim",
}
# Not hero material even when a car is technically present
BAD: Dict[str, str] = {
    "screen": "a close-up of a digital display showing numbers or text",
    "people": "people posing or standing in front of a car",
    "far": "a wide landscape where the car is tiny and far away",
    "graphic": "a map, chart or infographic",
    "text": "a photo with large words or a slogan printed over it",
    "prototype": "a camouflaged prototype test car covered in a black and white wrap pattern",
    "material": "a close-up of seat fabric, leather or material texture",
}
CAR_YES = ["a photo of a car", "a car driving on a road", "a close-up of a car headlight or wheel",
           "the interior dashboard of a car", "an electric car at a charging station"]
CAR_NO = ["a group of people posing for a photo", "people standing outdoors", "a landscape with no car",
          "a map or infographic", "a building or monument"]

# car_edit scene angles (agents/car_edit_agent.py) -> shot types wanted, best first
ANGLE_SHOTS: Dict[str, List[str]] = {
    "front three-quarter": ["front34", "front", "headlight"],
    "side profile": ["side", "front34", "driving"],
    "rear": ["rear", "front34"],
    "track cornering": ["driving", "front34", "side"],
    "close-up wheel": ["wheel", "headlight", "front"],
    "engine bay": ["charging", "front", "wheel"],
    "cockpit": ["interior"],
    "interior": ["interior"],
    "highway night": ["driving", "headlight", "rear"],
}

MIN_CAR = 0.5      # CLIP car share (BMW newsroom: car shots 0.83-1.0, team/landscape 0.0-0.1)
MIN_FILL = 0.10    # subject must cover >= 10% of the photo (the far-away aurora shot ~3%)
MAX_BAD = 0.45     # share of BAD labels above which the photo is not used


def wanted_shots(scene: Dict[str, Any]) -> List[str]:
    explicit = scene.get("wanted_shots")
    if explicit:
        return list(explicit)
    angle = str(scene.get("car_angle") or scene.get("visual_prompt") or "").lower()
    for key, shots in ANGLE_SHOTS.items():
        if key in angle:
            return shots
    return []


def _clip_probs(img: Image.Image, labels: List[str]) -> Optional[List[float]]:
    try:
        from agents import image_verifier as iv
        if not iv._load():
            return None
        import torch
        inputs = iv._processor(text=labels, images=img, return_tensors="pt", padding=True).to(iv._device)
        with torch.no_grad():
            return iv._model(**inputs).logits_per_image.softmax(dim=-1)[0].cpu().tolist()
    except Exception:
        return None


_REMBG = None


def _subject_box(img: Image.Image) -> Tuple[Tuple[float, float, float, float], float, Tuple[float, float]]:
    """(box x0,y0,x1,y1 as 0-1 fractions, fill fraction, centroid) of the largest foreground object."""
    global _REMBG
    try:
        import numpy as np
        from rembg import new_session, remove
        from scipy import ndimage
        if _REMBG is None:
            _REMBG = new_session("isnet-general-use")
        small = img.copy()
        small.thumbnail((640, 640))
        alpha = np.array(remove(small, session=_REMBG).split()[3]) > 128
        labels, n = ndimage.label(ndimage.binary_opening(alpha, structure=np.ones((5, 5))))
        if n == 0:
            raise ValueError("no subject")
        sizes = ndimage.sum(alpha, labels, range(1, n + 1))
        keep = labels == (int(np.argmax(sizes)) + 1)
        ys, xs = np.where(keep)
        h, w = keep.shape
        box = (xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h)
        return box, float(keep.mean()), (float(xs.mean() / w), float(ys.mean() / h))
    except Exception:
        return (0.0, 0.0, 1.0, 1.0), 0.0, (0.5, 0.5)


HERO_SHOTS = ("front34", "front", "side", "rear", "driving", "headlight", "charging")
CLOSEUPS = ("wheel", "interior", "headlight", "detail")
TEXT_LIMIT = 0.95  # CLIP fallback (BMW calibration: slogans 0.968-0.991, clean road shot 0.915)


def _overlay_text_share(img: Image.Image, work: Image.Image) -> float:
    """How strongly the photo carries printed words. Uses OCR (rapidocr) when installed: share of the
    photo covered by large text, scaled to 0-1; otherwise a CLIP text-vs-no-text comparison."""
    try:
        from rapidocr_onnxruntime import RapidOCR  # optional dependency
        import numpy as np
        global _OCR
        if _OCR is None:
            _OCR = RapidOCR()
        res, _ = _OCR(np.asarray(work))
        area = 0.0
        for box, txt, conf in res or []:
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            h = max(ys) - min(ys)
            if conf > 0.6 and h > work.height * 0.05 and len(txt.strip()) >= 3:  # big words, not a plate
                area += (max(xs) - min(xs)) * h
        return min(1.0, area / (work.width * work.height) * 20)
    except ImportError:
        pass
    except Exception:
        return 0.0
    p = _clip_probs(work, ["a car photo with big white words printed over the image", "a car photo with no text"])
    return round(p[0], 3) if p else 0.0


_OCR = None


def _sharpness(img: Image.Image) -> float:
    try:
        import numpy as np
        g = np.asarray(img.convert("L").resize((512, int(512 * img.height / img.width))), dtype="float32")
        lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
        return float(lap.var())
    except Exception:
        return 0.0


def analyse(path: Path, source_hint: str = "") -> Dict[str, Any]:
    """source_hint: the photo's URL / page / title (catches 'prototype' galleries CLIP may miss)."""
    img = Image.open(path).convert("RGB")
    work = img.copy()
    work.thumbnail((1280, 1280))
    info: Dict[str, Any] = {"path": str(path), "width": img.width, "height": img.height,
                            "source_hint": source_hint}

    car = _clip_probs(work, CAR_NO + CAR_YES)
    info["car"] = round(sum(car[len(CAR_NO):]), 3) if car else None

    shot_keys, bad_keys = list(SHOTS), list(BAD)
    probs = _clip_probs(work, [SHOTS[k] for k in shot_keys] + [BAD[k] for k in bad_keys])
    if probs:
        sp, bp = probs[:len(shot_keys)], probs[len(shot_keys):]
        order = sorted(range(len(sp)), key=lambda i: -sp[i])
        info["shot"] = shot_keys[order[0]]
        info["shot2"] = shot_keys[order[1]]
        info["shot_conf"] = round(sp[order[0]] / max(1e-6, sum(sp)), 3)
        info["bad"] = round(sum(bp), 3)
        info["bad_kind"] = bad_keys[max(range(len(bp)), key=lambda i: bp[i])]
    else:
        info.update(shot="front34", shot2="side", shot_conf=0.0, bad=0.0, bad_kind="")

    box, fill, centroid = _subject_box(work)
    info.update(box=box, fill=round(fill, 3), centroid=centroid)
    info["sharpness"] = round(_sharpness(work), 1)
    lum = sum(work.convert("L").resize((64, 64)).getdata()) / (64 * 64)
    info["brightness"] = round(lum, 1)

    # A "whole car" shot whose car runs off the photo's edge is really a detail (BMW's portrait rear-quarter
    # shot was picked as the final hero and showed only a wheel arch)
    if info["shot"] in ("side", "front34", "rear", "front") and (box[0] <= 0.01 or box[2] >= 0.99):
        info["shot2"], info["shot"] = info["shot"], "detail"
    # Close-ups (interior, wheel, headlight, detail) fill the frame differently: no single whole object
    closeup = info["shot"] in ("interior", "wheel", "headlight", "detail")
    # Camouflaged test cars don't show the production design (brief: never change the car's look)
    if re.search(r"prototyp|camouflag|erlkoenig|test-?drive|testing", (info.get("source_hint") or "").lower()):
        info["bad"], info["bad_kind"] = max(info["bad"], 0.99), "prototype"
    # Slogans printed on press photos ("EFFICIENCY", "SYMBIOTIC") would sit under our own captions
    info["text"] = _overlay_text_share(img, work)
    if info["text"] >= TEXT_LIMIT:
        info["bad"], info["bad_kind"] = max(info["bad"], 0.99), "printed text"
    usable = (info["car"] is None or info["car"] >= MIN_CAR) and info["bad"] < MAX_BAD \
        and (closeup or fill >= MIN_FILL) and min(img.width, img.height) >= 700
    info["usable"] = bool(usable)
    info["reject_reason"] = "" if usable else (
        f"not the car ({info['car']})" if info["car"] is not None and info["car"] < MIN_CAR
        else f"{info['bad_kind']} ({info['bad']})" if info["bad"] >= MAX_BAD
        else f"car too small ({fill:.0%} of the photo)" if not closeup and fill < MIN_FILL
        else f"low resolution ({img.width}x{img.height})")

    res = min(1.0, min(img.width, img.height) / 1600)
    sharp = min(1.0, info["sharpness"] / 400)
    light = 1.0 - min(1.0, abs(lum - 95) / 95)            # very dark / blown-out photos rank lower
    hero = 0.8 if info["shot"] in HERO_SHOTS else 0.0  # the whole car beats a wheel / seat detail
    info["score"] = round((info["car"] or 0.8) * 2 + min(fill, 0.45) * 3 + sharp + res + light * 0.7
                          + info["shot_conf"] * 0.5 + hero - info["bad"] * 2, 3)
    return info


def rank(candidates: Iterable[Dict[str, Any]], work_dir: Path, download, limit: int = 40,
         log=print) -> List[Dict[str, Any]]:
    """download(url, path) -> bool. Returns usable candidates (with 'analysis'), best first."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out, seen_hash = [], set()
    for cand in list(candidates)[:limit]:
        url = cand.get("url") or ""
        path = work_dir / (hashlib.md5(url.encode()).hexdigest()[:16] + ".jpg")
        if not path.exists() and not download(url, path):
            continue
        try:
            info = analyse(path, " ".join(str(cand.get(k) or "") for k in ("url", "page_url", "title")))
        except Exception as e:
            log(f"   [car-photo-rank] skipped {url[-40:]}: {e}")
            continue
        try:
            h = Image.open(path).convert("L").resize((9, 8)).tobytes()
            dh = bytes(int(h[r * 9 + c] > h[r * 9 + c + 1]) for r in range(8) for c in range(8))
        except Exception:
            dh = url.encode()
        if dh in seen_hash:
            continue  # the same photo in another size / from another page
        seen_hash.add(dh)
        if not info["usable"]:
            log(f"   [car-photo-rank] not used: {url.rsplit('/', 1)[-1][:40]} - {info['reject_reason']}")
            continue
        out.append(dict(cand, analysis=info, local_path=str(path)))
    out.sort(key=lambda c: -c["analysis"]["score"])
    log(f"   [car-photo-rank] {len(out)} usable photos; shots: "
        + ", ".join(f"{k}={sum(1 for c in out if c['analysis']['shot'] == k)}" for k in SHOTS
                    if any(c['analysis']['shot'] == k for c in out)))
    return out


def pick(ranked: List[Dict[str, Any]], wanted: List[str], used: set) -> Optional[Dict[str, Any]]:
    free = [c for c in ranked if c["url"] not in used]
    for shot in wanted:
        for c in free:
            if c["analysis"]["shot"] == shot:
                return c
    closeups = ("wheel", "interior", "headlight", "detail")
    for shot in wanted:
        for c in free:
            # second-best label only when it's the same kind of shot (a wheel close-up whose runner-up
            # label is "side" is not a side view of the car)
            if c["analysis"].get("shot2") == shot and (c["analysis"]["shot"] in closeups) == (shot in closeups):
                return c
    if wanted and wanted[0] not in closeups:
        full = [c for c in free if c["analysis"]["shot"] not in closeups]
        if full:
            return full[0]
        return None  # caller re-frames a used full-car photo rather than showing a close-up
    return free[0] if free else None


def render(info: Dict[str, Any], out_path: Path, variant: int = 0) -> Path:
    """Vertical frame centred on the car. variant > 0: a different framing of the same photo
    (used when a car's photos run out, instead of an AI car)."""
    img = Image.open(info["path"]).convert("RGB")
    iw, ih = img.size
    x0, y0, x1, y1 = info.get("box") or (0, 0, 1, 1)
    cx, cy = info.get("centroid") or (0.5, 0.5)
    target = W / H
    crop_w = ih * target  # full-height vertical window
    car_w = (x1 - x0) * iw
    wide_car = info.get("shot") in ("side", "front34", "rear", "driving") and car_w > crop_w * 1.3

    if variant:
        # Alternate framing: tighter crop on the front / back half of the car or a detail zoom
        zoom = 1.35 + 0.15 * (variant % 2)
        focus_x = x0 + (x1 - x0) * (0.3 if variant % 2 else 0.7)
        cw, ch = crop_w / zoom, ih / zoom
        left = min(max(0, focus_x * iw - cw / 2), iw - cw)
        top = min(max(0, cy * ih - ch / 2), ih - ch)
        frame = img.crop((int(left), int(top), int(left + cw), int(top + ch))).resize((W, H), Image.Resampling.LANCZOS)
    elif wide_car and iw / ih > target:
        # Whole car over a blurred, darkened copy of the photo (a vertical crop would slice it)
        bg = img.crop((int(max(0, cx * iw - crop_w / 2)), 0, int(max(0, cx * iw - crop_w / 2) + crop_w), ih))
        bg = bg.resize((W, H)).filter(ImageFilter.GaussianBlur(28))
        bg = ImageEnhance.Brightness(bg).enhance(0.55)
        # the car spans the frame width (its bumpers just touch the edges), never taller than the frame
        scale = min((W * 1.04) / max(1.0, car_w), (H * 0.62) / ih)
        fg = img.resize((int(iw * scale), int(ih * scale)), Image.Resampling.LANCZOS)
        fx = int(W / 2 - ((x0 + x1) / 2) * fg.width)
        fx = min(0, max(W - fg.width, fx))
        fy = int(H * 0.5 - fg.height / 2)
        mask = Image.new("L", fg.size, 255)
        feather = max(8, fg.height // 14)
        for i in range(feather):  # soft top/bottom edges
            a = int(255 * i / feather)
            for y in (i, fg.height - 1 - i):
                mask.paste(a, (0, y, fg.width, y + 1))
        bg.paste(fg, (fx, fy), mask)
        frame = bg
    elif iw / ih > target:
        left = min(max(0, cx * iw - crop_w / 2), iw - crop_w)
        frame = img.crop((int(left), 0, int(left + crop_w), ih)).resize((W, H), Image.Resampling.LANCZOS)
    else:
        crop_h = iw / target
        top = min(max(0, cy * ih - crop_h / 2), ih - crop_h)
        frame = img.crop((0, int(top), iw, int(top + crop_h))).resize((W, H), Image.Resampling.LANCZOS)

    frame = ImageEnhance.Contrast(frame).enhance(1.08)
    frame = ImageEnhance.Color(frame).enhance(1.06)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.save(out_path, "PNG")
    return out_path
