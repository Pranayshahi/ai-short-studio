"""
Evolution comparison poster (WeaponX Lab style): historical models on the left, their modern
successors / counterparts on the right, one row per pair, 1080x1920.

Facts and photos come from equipment_catalog (Wikipedia infoboxes and lead photos), never from a
language model. Photos are cut out locally (rembg) and placed on a white catalogue page; if a
cutout looks incomplete the original photo is shown in a clean frame instead.
"""

from __future__ import annotations

import io
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config
from agents import equipment_catalog as ec

W, H = 1080, 1920
FONT_DIR = Path("/System/Library/Fonts/Supplemental")
INK = (17, 17, 17)
MUTED = (95, 95, 95)
RULE = (214, 214, 214)
ACCENT = (190, 30, 30)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for cand in (FONT_DIR / name, Path("/Library/Fonts") / name):
        if cand.exists():
            return ImageFont.truetype(str(cand), size)
    return ImageFont.load_default()


# ------------------------------------------------------------------ prompt parsing

def is_evolution_prompt(text: str) -> bool:
    t = (text or "").lower()
    return ("evolution" in t or "historical" in t) and ("modern" in t or "counterpart" in t or "successor" in t) \
        and ("column" in t or "comparison" in t)


def parse_prompt(text: str) -> Dict[str, Any]:
    def field(name: str) -> str:
        m = re.search(rf"\*\*{name}:\*\*\s*(.+)", text) or re.search(rf"(?im)^\s*{name}\s*:\s*(.+)$", text)
        return m.group(1).strip().strip("*").strip() if m else ""

    topic = field("TOPIC") or (text.strip().splitlines() or [""])[0][:60]
    title = field("TITLE") or f"THE EVOLUTION OF {topic}"
    left = re.search(r"LEFT COLUMN:\s*([^\n]+)", text, re.I)
    right = re.search(r"RIGHT COLUMN:\s*([^\n]+)", text, re.I)
    rows = re.search(r"(\d+)\s*[–-]\s*(\d+)\s+(?:historical|comparison)", text, re.I)
    return {
        "topic": topic,
        "title": title,
        "left_label": (left.group(1).strip() if left else "HISTORICAL ROOTS (ORIGINAL)").upper(),
        "right_label": (right.group(1).strip() if right else "ADVANCED MODERN COUNTERPARTS").upper(),
        "min_rows": int(rows.group(1)) if rows else 6,
        "max_rows": int(rows.group(2)) if rows else 8,
    }


# ------------------------------------------------------------------ data

def display_name(model: Dict[str, Any]) -> str:
    """'Marder (infantry fighting vehicle)' -> 'Marder'; 'FV510 Warrior' stays."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", model["title"]).strip()


def build_spec(topic: str, min_rows: int = 6, max_rows: int = 8) -> Dict[str, Any]:
    """Verified pairs for the topic, or {'error': ...} when Wikipedia can't support enough rows."""
    list_page = ec.find_list_page(topic)
    if not list_page:
        return {"error": f"No Wikipedia list page found for '{topic}', so the models can't be verified."}
    cands = ec.list_page_models(list_page)
    sections: Dict[str, str] = {}
    for t, sec in cands:
        sections.setdefault(t, sec)
    models = ec.fetch_models(list(sections.keys()))
    type_phrase = re.sub(r"\bcombat\b", "fighting", topic, flags=re.I)
    pairs = ec.build_pairs(models, max_rows=max_rows, type_phrase=type_phrase, sections=sections, min_rows=min_rows)
    if len(pairs) < min_rows:
        return {"error": f"Only {len(pairs)} verifiable historical→modern pairs for '{topic}' on Wikipedia (need {min_rows}).",
                "pairs": pairs, "list_page": list_page}
    return {"pairs": pairs, "list_page": list_page,
            "sources": sorted({p[s]["url"] for p in pairs for s in ("historical", "modern")})}


# ------------------------------------------------------------------ photos

_REMBG = None


def _cutout(img: Image.Image) -> Optional[Image.Image]:
    """Background-removed RGBA keeping only the largest object, or None if it looks incomplete."""
    global _REMBG
    try:
        from rembg import new_session, remove
        import numpy as np
        from scipy import ndimage
        if _REMBG is None:
            _REMBG = new_session("isnet-general-use")
        rgba = remove(img, session=_REMBG)
        alpha = np.array(rgba.split()[3]) > 128
        # Open the mask first so thin connections (a sign board touching the hull) don't merge
        # objects, pick the largest, then grow it back within the original mask
        opened = ndimage.binary_opening(alpha, structure=np.ones((9, 9)))
        labels, n = ndimage.label(opened)
        if n == 0:
            return None
        sizes = ndimage.sum(opened, labels, range(1, n + 1))
        core = labels == (int(np.argmax(sizes)) + 1)
        keep = ndimage.binary_dilation(core, structure=np.ones((9, 9)), iterations=2) & alpha
        ys, xs = np.where(keep)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        obj = keep[y0:y1 + 1, x0:x1 + 1]
        # A complete vehicle stands on tracks/wheels spanning most of its width. Calibrated
        # 2026-11-15: complete cutouts 0.57-0.96; a hull with the tracks lost in a dust cloud 0.10,
        # a vehicle merged with a sign board 0.25.
        base_width = obj[int(obj.shape[0] * 0.75):, :].any(axis=0).mean()
        if base_width < 0.45 or keep.mean() < 0.06:
            return None
        a = Image.fromarray((keep * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.8))
        out = rgba.copy()
        out.putalpha(a)
        return out.crop((x0, y0, x1 + 1, y1 + 1))
    except Exception:
        return None


def _download(url: str, dest: Path) -> bool:
    headers = {"User-Agent": getattr(config, "WIKIMEDIA_USER_AGENT", "AIShortsStudio/2.1")}
    for attempt in range(4):
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200 and len(r.content) > 5000:
                im = Image.open(io.BytesIO(r.content))
                ready = _ready_cutout(im)
                if ready is not None:  # keep the transparency (a ready-made cutout) next to the JPEG
                    ready.save(_alpha_path(dest))
                _rgb_on_white(im).save(dest, quality=92)  # white, never black, behind transparent areas
                return True
        except (requests.RequestException, OSError):
            pass
        time.sleep(4 * (attempt + 1))
    return False


_BAD_PHOTO_WORDS = re.compile(r"interior|kampfraum|cockpit|inside|innen|compartment|wreck|destroy|burn|knocked|captured|"
                              r"abandon|diagram|drawing|scheme|model kit|scale model|toy|map|logo|insignia|engine|turret only|"
                              r"holotype|fossil|skull|specimen|animal", re.I)


def _photo_name_ok(file_title: str, model: Dict[str, Any]) -> bool:
    """The file must name the model (designator like 'BMP-1', or its name like 'Puma') and not be an
    interior / wreck / drawing."""
    from agents.subject_match import designators, mentions_any
    if _BAD_PHOTO_WORDS.search(file_title):
        return False
    name = display_name(model)
    desigs = designators(name)
    if desigs:
        return mentions_any(file_title, desigs)
    # Plain names ("Puma") are ambiguous: also require a vehicle word in the file name
    named = any(w.lower() in file_title.lower() for w in re.findall(r"[A-Za-z]{4,}", name))
    return named and bool(re.search(r"ifv|spz|sch[uü]tzenpanzer|vehicle|panzer|apc|tank|army|armou?r|military|bundeswehr", file_title, re.I))


def _commons_photos(model: Dict[str, Any], limit: int = 8) -> List[Dict[str, str]]:
    """Exterior photo candidates: the model's Commons category first, then its article's images."""
    found: List[Dict[str, str]] = []
    name = display_name(model)
    queries = [
        {"generator": "categorymembers", "gcmtitle": f"Category:{name}", "gcmtype": "file", "gcmlimit": 40},
        {"generator": "images", "titles": model["title"], "gimlimit": 40},
    ]
    for q in queries:
        api = "https://commons.wikimedia.org/w/api.php" if "gcmtitle" in q else ec.API
        params = {"action": "query", "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": 640,
                  "format": "json", "formatversion": 2, "redirects": 1, **q}
        try:
            r = requests.get(api, params=params, headers=ec.HEADERS, timeout=30)
            data = r.json() if r.status_code == 200 else {}
        except (requests.RequestException, ValueError):
            data = {}
        for pg in data.get("query", {}).get("pages", []):
            ii = (pg.get("imageinfo") or [{}])[0]
            if ii.get("mime") == "image/jpeg" and ii.get("width", 0) >= 900 and ii.get("width", 0) > ii.get("height", 1) \
                    and ii.get("thumburl") and _photo_name_ok(pg["title"], model) and pg["title"] not in [f["file"] for f in found]:
                found.append({"file": pg["title"], "url": ii["thumburl"]})
        time.sleep(1)
        if len(found) >= limit:
            break
    return found[:limit]


PERSON_SHARE_MAX = 0.15


def _exterior_ok(cut: Image.Image, kind: str = "vehicle") -> bool:
    """AI check on the cutout: an outside view of a complete vehicle, not an interior/wreck/partial.
    kind='firearm': the weapon on its own, not a person holding/firing it (an M1911 chart showed a Marine)."""
    try:
        from agents import image_verifier as iv
        if not iv._load():
            return True
        import torch
        noun = {"naval": "torpedo or missile", "missile": "missile", "aircraft": "military aircraft",
                "warship": "warship", "artillery": "artillery gun", "air_defense": "missile launcher vehicle"}.get(kind)
        if kind == "firearm":
            good = ["a product photo of a handgun on a plain background", "a photo of a pistol by itself",
                    "a side view of a firearm with nobody in the picture"]
            bad = ["a soldier holding a pistol", "a person aiming a gun", "a photo of a person",
                   "a close-up of a machine part", "a box of ammunition", "a gun holster"]
        elif noun:
            good = [f"a photo of a {noun}", f"a side view of a complete {noun}", f"a {noun} on display"]
            bad = ["a photo of a person", "a group of people", "a close-up of a machine part", "a document or diagram",
                   "the interior of a building", "a map"]
            if kind in ("missile", "naval"):
                # the weapon itself, not what carries or hides it (JASSM shown as an F-35; Gryphon under camo netting)
                bad += ["a fighter jet aircraft", "a military truck", "camouflage netting over a vehicle", "a warship"]
        else:
            good = ["an exterior photo of a complete armoured military vehicle", "a military vehicle seen from the side"]
            bad = ["the interior of a vehicle", "a destroyed or burnt-out vehicle", "a vehicle partly submerged in water",
                   "a vehicle covered in dust and smoke", "a close-up of a machine part"]
        bg = Image.new("RGB", cut.size, "white")
        bg.paste(cut, mask=cut.split()[3])
        inputs = iv._processor(text=good + bad, images=bg, return_tensors="pt", padding=True).to(iv._device)
        with torch.no_grad():
            probs = iv._model(**inputs).logits_per_image.softmax(dim=-1)[0].cpu().tolist()
        ok = sum(probs[:len(good)]) >= 0.6
        if ok and noun:
            # A weapon chart shows the weapon, not the crew around it (Mark 54 photo: four workers)
            import tempfile
            from agents.image_generator import ImageGeneratorAgent
            with tempfile.NamedTemporaryFile(suffix=".png") as tf:
                bg.save(tf.name)
                share = ImageGeneratorAgent._person_share(Path(tf.name))
            if share is not None and share > PERSON_SHARE_MAX:
                return False
        return ok
    except Exception:
        return True


def _alpha_path(jpg: Path) -> Path:
    return jpg.with_name(jpg.stem + "_alpha.png")


def _ready_cutout(im: Image.Image) -> Optional[Image.Image]:
    """A photo that already has a transparent background IS a clean cutout: trim and use it as-is."""
    if im.mode not in ("RGBA", "LA", "PA") and not (im.mode == "P" and "transparency" in im.info):
        return None
    rgba = im.convert("RGBA")
    alpha = rgba.getchannel("A")
    hist = alpha.histogram()
    clear_share = sum(hist[:16]) / float(rgba.width * rgba.height)
    if not 0.05 <= clear_share <= 0.95:  # fully opaque (or nearly empty): not a usable cutout
        return None
    bbox = alpha.point(lambda a: 255 if a > 16 else 0).getbbox()
    return rgba.crop(bbox) if bbox else None


def _rgb_on_white(im: Image.Image) -> Image.Image:
    """Flatten onto WHITE; .convert('RGB') alone turns transparent pixels black."""
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.alpha_composite(rgba)
        return bg.convert("RGB")
    return im.convert("RGB")


def fetch_photo(model: Dict[str, Any], cache_dir: Path) -> Tuple[Optional[Image.Image], bool]:
    """(image, is_cutout). Lead photo first; if it can't be cut out cleanly, other photos from the
    same article; the framed lead photo is the last resort. Cached per article."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", model["title"])[:60]
    cut_p, raw_p = cache_dir / f"{key}_cut.png", cache_dir / f"{key}.jpg"
    if cut_p.exists():
        cached = Image.open(cut_p).convert("RGBA")
        # Cutouts cached under older, weaker checks are re-checked for strict kinds
        if model.get("_kind", "vehicle") == "vehicle" or _exterior_ok(cached, model.get("_kind")):
            return cached, True
        cut_p.unlink(missing_ok=True)
    if not raw_p.exists():
        _download(model["image_url"], raw_p)
        time.sleep(1)
    if not raw_p.exists():
        return None, False
    kind = model.get("_kind", "vehicle")
    strict = kind != "vehicle"  # vehicles keep the original behaviour; other kinds re-check every candidate
    src = Image.open(raw_p)
    alpha_p = _alpha_path(raw_p)
    ready = _ready_cutout(Image.open(alpha_p)) if alpha_p.exists() else None
    if ready is not None and (not strict or _exterior_ok(ready, kind)):
        ready.save(cut_p)
        return ready, True
    raw = _rgb_on_white(src)
    cut = _cutout(raw)
    if cut is not None and strict and not _exterior_ok(cut, kind):
        cut = None
    if cut is None:
        lead_file = (model.get("image_file") or "").replace(" ", "_")
        for i, alt in enumerate(_commons_photos(model)):
            if lead_file and lead_file in alt["file"].replace(" ", "_"):
                continue
            alt_p = cache_dir / f"{key}_alt{i}.jpg"
            if alt_p.exists() or _download(alt["url"], alt_p):
                alt_a = _alpha_path(alt_p)
                cut = (_ready_cutout(Image.open(alt_a)) if alt_a.exists() else None) or _cutout(Image.open(alt_p).convert("RGB"))
                if cut is not None and _exterior_ok(cut, kind):
                    model["image_file_used"] = alt["file"]
                    break
                cut = None
            time.sleep(1)
    if cut is not None:
        cut.save(cut_p)
        return cut, True
    return raw, False


# ------------------------------------------------------------------ render

def _fit(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    s = min(box_w / img.width, box_h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.Resampling.LANCZOS)


def _split_label(label: str) -> Tuple[str, str]:
    """'Main gun 20 mm → 30 mm' -> ('MAIN GUN', '20 → 30 mm'); 'Weight 13.2 t → 18.7 t' -> ('WEIGHT', '13.2 → 18.7 t')."""
    m = re.match(r"^(Main gun|Weight)\s+([\d.]+)\s*(mm|t)\s*→\s*([\d.]+)\s*(mm|t)$", label)
    if m:
        return m.group(1).upper(), f"{m.group(2)} → {m.group(4)} {m.group(5)}"
    m = re.match(r"^(Main gun|Weight)\s+(.+)$", label)
    if m:
        return m.group(1).upper(), m.group(2)
    m = re.match(r"^(\d+) years of development$", label)
    if m:
        return "DEVELOPMENT", f"{m.group(1)} years"
    return "", label


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> List[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _paste_item(canvas: Image.Image, img: Image.Image, is_cut: bool, cx: int, top: int, box_w: int, box_h: int,
                shadow: bool = True):
    item = _fit(img, box_w, box_h)
    x = cx - item.width // 2
    y = top + (box_h - item.height)  # sit on a common baseline
    if is_cut and not shadow:  # hand-held objects don't stand on the ground
        canvas.alpha_composite(item.convert("RGBA"), (x, top + (box_h - item.height) // 2))
    elif is_cut:
        # Soft contact shadow beneath the vehicle
        sh = Image.new("L", (item.width, max(8, item.height // 9)), 0)
        ImageDraw.Draw(sh).ellipse((item.width * 0.06, 0, item.width * 0.94, sh.height), fill=90)
        sh = sh.filter(ImageFilter.GaussianBlur(7))
        shadow = Image.new("RGBA", sh.size, (0, 0, 0, 255))
        shadow.putalpha(sh)
        canvas.alpha_composite(shadow, (x, y + item.height - sh.height // 2))
        canvas.alpha_composite(item.convert("RGBA"), (x, y))
    else:
        framed = Image.new("RGBA", (item.width + 6, item.height + 6), (225, 225, 225, 255))
        framed.paste(item.convert("RGBA"), (3, 3))
        canvas.alpha_composite(framed, (x - 3, y - 3))


def render(spec: Dict[str, Any], prompt: Dict[str, Any], out_path: Path, cache_dir: Path) -> Dict[str, Any]:
    pairs = spec["pairs"]
    canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    d = ImageDraw.Draw(canvas)

    # Title: "THE EVOLUTION OF" small, topic large, edition line
    title = prompt["title"].upper()
    m = re.match(r"(THE EVOLUTION OF)\s+(.*?)\s*(\(.*\))?$", title)
    kicker, main, edition = (m.group(1), m.group(2), m.group(3) or "") if m else ("", title, "")
    y = 52
    if kicker:
        f = _font("Arial Bold.ttf", 34)
        d.text((W // 2, y), kicker, font=f, fill=MUTED, anchor="mt")
        y += 46
    f_main = _font("Arial Black.ttf", 66)
    for line in _wrap(d, main, f_main, W - 100):
        d.text((W // 2, y), line, font=f_main, fill=INK, anchor="mt")
        y += 76
    if edition:
        d.text((W // 2, y + 2), edition, font=_font("Arial Bold.ttf", 30), fill=ACCENT, anchor="mt")
        y += 44
    y += 18

    # Column headers
    col_l, col_r, mid = 270, 810, W // 2
    f_head = _font("Arial Black.ttf", 25)
    for cx, label in ((col_l, prompt["left_label"]), (col_r, prompt["right_label"])):
        for i, line in enumerate(_wrap(d, label, f_head, 440)):
            d.text((cx, y + i * 30), line, font=f_head, fill=INK, anchor="mt")
    y += 70
    d.line((40, y, W - 40, y), fill=INK, width=3)
    y += 14

    # Rows
    n = len(pairs)
    foot = 64
    row_h = (H - y - foot) // n
    img_h = int(row_h * 0.62)
    f_name = _font("Arial Bold.ttf", 25)
    f_year = _font("Arial.ttf", 23)
    f_label = _font("Arial Bold.ttf", 22)
    f_label_head = _font("Arial Bold.ttf", 16)
    used_cutouts = 0
    for i, p in enumerate(pairs):
        top = y + i * row_h
        for side, cx in (("historical", col_l), ("modern", col_r)):
            model = p[side]
            img, is_cut = fetch_photo(model, cache_dir)
            used_cutouts += int(is_cut)
            if img is not None:
                _paste_item(canvas, img, is_cut, cx, top + 10, 400, img_h - 10)
            name = f"{display_name(model)}"
            d.text((cx, top + img_h + 14), name, font=f_name, fill=INK, anchor="mt")
            nw = d.textlength(name, font=f_name)
            d.text((cx, top + img_h + 46), f"({model['year']})", font=f_year, fill=MUTED, anchor="mt")
        # Middle spec label: small heading over the values ("MAIN GUN" / "20 → 30 mm")
        head, value = _split_label(p["label"])
        ly = top + img_h // 2 - 26
        d.text((mid, ly), head, font=f_label_head, fill=MUTED, anchor="mt")
        for j, line in enumerate(_wrap(d, value, f_label, 170)):
            d.text((mid, ly + 26 + j * 26), line, font=f_label, fill=ACCENT, anchor="mt")
        if i < n - 1:
            d.line((60, top + row_h - 4, W - 60, top + row_h - 4), fill=RULE, width=2)

    d.text((W // 2, H - 38), "Data & photos: Wikipedia / Wikimedia Commons", font=_font("Arial.ttf", 18), fill=MUTED, anchor="mm")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "PNG")
    return {"path": str(out_path), "rows": n, "cutouts": used_cutouts, "photos": 2 * n}


# ------------------------------------------------------------------ attribution

def photo_credits(pairs: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Author + licence of every photo used (CC BY / BY-SA require attribution)."""
    files = []
    for p in pairs:
        for side in ("historical", "modern"):
            m = p[side]
            f = m.get("image_file_used") or (f"File:{m['image_file']}" if m.get("image_file") else None)
            if f:
                files.append((display_name(m), f if f.startswith("File:") else f"File:{f}"))
    credits: List[Dict[str, str]] = []
    for i in range(0, len(files), 5):
        batch = files[i:i + 5]
        # extmetadata is large: the API answers part of a batch and continues; follow it
        pages: Dict[str, Any] = {}
        cont: Dict[str, str] = {}
        for _ in range(8):
            data = {}
            for attempt in range(4):
                try:
                    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=ec.HEADERS, timeout=30, params={
                        "action": "query", "titles": "|".join(f for _, f in batch), "prop": "imageinfo",
                        "iiprop": "extmetadata|url", "format": "json", "formatversion": 2, **cont})
                    if r.status_code == 200:
                        data = r.json()
                        break
                    time.sleep(int(r.headers.get("retry-after") or 0) or 5 * (attempt + 1))
                except (requests.RequestException, ValueError):
                    time.sleep(3 * (attempt + 1))
            norm = {n["to"]: n["from"] for n in data.get("query", {}).get("normalized", [])}
            for pg in data.get("query", {}).get("pages", []):
                if pg.get("imageinfo"):
                    pages[pg["title"].replace("_", " ")] = pg
                    if pg["title"] in norm:
                        pages[norm[pg["title"]].replace("_", " ")] = pg
            if "continue" not in data:
                break
            cont = data["continue"]
            time.sleep(1)
        time.sleep(1.5)
        for model_name, f in batch:
            pg = pages.get(f.replace("_", " "), {})
            meta = ((pg.get("imageinfo") or [{}])[0]).get("extmetadata", {})
            artist = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip() or "Unknown author"
            credits.append({
                "model": model_name,
                "file": f,
                "author": artist[:80],
                "license": (meta.get("LicenseShortName") or {}).get("value", "see file page"),
                "url": ((pg.get("imageinfo") or [{}])[0]).get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{f.replace(' ', '_')}",
                # Short stable link to the file page (the full URL of a Korean/accented file name is huge)
                "short_url": f"https://commons.wikimedia.org/?curid={pg['pageid']}" if pg.get("pageid") else "",
            })
    # Anything the batches missed (throttling, long continuations): ask one file at a time
    for c in credits:
        if c["author"] != "Unknown author" and "see file" not in c["license"]:
            continue
        for attempt in range(3):
            try:
                r = requests.get("https://commons.wikimedia.org/w/api.php", headers=ec.HEADERS, timeout=30, params={
                    "action": "query", "titles": c["file"], "prop": "imageinfo", "iiprop": "extmetadata|url",
                    "format": "json", "formatversion": 2})
                if r.status_code == 200:
                    pg = (r.json().get("query", {}).get("pages") or [{}])[0]
                    meta = ((pg.get("imageinfo") or [{}])[0]).get("extmetadata", {})
                    if meta:
                        c["author"] = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()[:80] or c["author"]
                        c["license"] = (meta.get("LicenseShortName") or {}).get("value", c["license"])
                    if pg.get("pageid"):
                        c["short_url"] = f"https://commons.wikimedia.org/?curid={pg['pageid']}"
                    break
                time.sleep(5 * (attempt + 1))
            except (requests.RequestException, ValueError):
                time.sleep(3)
        time.sleep(1)
    return credits


def credits_text(credits: List[Dict[str, str]]) -> str:
    return "\n".join(f"• {c['model']}: {c['author']}, {c['license']} — {c['url']}" for c in credits)


def make_poster(prompt_text: str, topic: str, out_path: Path, cache_dir: Path) -> Dict[str, Any]:
    """End to end: parse prompt -> verified pairs -> render -> credits. Returns {'error': ...} if the
    data can't be verified (never draws unverified equipment)."""
    pr = parse_prompt(prompt_text) if prompt_text and is_evolution_prompt(prompt_text) else {
        "topic": topic, "title": f"THE EVOLUTION OF {topic}", "left_label": "HISTORICAL ROOTS (ORIGINAL)",
        "right_label": "ADVANCED MODERN COUNTERPARTS", "min_rows": 6, "max_rows": 8}
    if not pr.get("topic"):
        pr["topic"] = topic
    spec = build_spec(pr["topic"], min_rows=pr["min_rows"], max_rows=pr["max_rows"])
    if spec.get("error"):
        return {"error": spec["error"], "prompt": pr}
    res = render(spec, pr, out_path, cache_dir)
    credits = photo_credits(spec["pairs"])
    return {**res, "prompt": pr, "pairs": [
        {"historical": f"{display_name(p['historical'])} ({p['historical']['year']})",
         "modern": f"{display_name(p['modern'])} ({p['modern']['year']})", "label": p["label"], "kind": p["kind"]}
        for p in spec["pairs"]], "sources": spec["sources"], "list_page": spec["list_page"], "credits": credits}


# ------------------------------------------------------------------ YouTube description helpers

_NO_ATTRIBUTION = re.compile(r"public domain|^pd\b|cc0|no restrictions", re.I)


def compact_credits(credits: List[Dict[str, str]]) -> List[str]:
    """One short line per photo whose licence REQUIRES attribution (CC BY / BY-SA / OGL ...):
    'Puma – Boevaya mashina, CC BY-SA 4.0 – https://commons.wikimedia.org/?curid=123'.
    Public-domain / CC0 photos need no credit and are left out."""
    lines, seen = [], set()
    for c in credits:
        lic = str(c.get("license") or "")
        if _NO_ATTRIBUTION.search(lic):
            continue
        link = c.get("short_url") or c.get("url") or ""
        if link in seen:
            continue
        seen.add(link)
        author = re.sub(r"\s+", " ", str(c.get("author") or "Unknown")).strip()
        # Keep the readable part of bilingual credits ("대한민국 국군 Republic of Korea Armed Forces")
        latin = re.findall(r"[A-Za-z][A-Za-z .,'()&-]+", author)
        if latin and len(" ".join(latin)) >= 6 and not re.match(r"[A-Za-z]", author):
            author = " ".join(latin).strip()
        lines.append(f"• {c.get('model')} – {author[:50]}, {lic} – {link}")
    return lines


def description_body(record: Dict[str, Any]) -> Optional[str]:
    """Description text made only of the poster's real content (ranked items or verified pairs)."""
    if record.get("ranked_items"):
        rows = []
        for it in record["ranked_items"]:
            spec = ", ".join(x for x in (it.get("gun"), it.get("troops")) if x) or ", ".join(it.get("bullets") or [])
            yr = f", {it['year']}" if it.get("year") else ""
            rows.append(f"{it['rank']}. {it['name']} ({it['country']}{yr})" + (f" – {spec}" if spec else ""))
        return "\n".join(rows)
    if record.get("evolution_pairs"):
        return "\n".join(f"{p['historical']} → {p['modern']} – {p['label']}" for p in record["evolution_pairs"])
    return None

