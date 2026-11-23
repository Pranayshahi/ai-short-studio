"""
WeaponX 'size comparison' chart of the cartridges used in assault rifles worldwide (owner's reference:
a stack of brass cartridges from largest to smallest, name beside each).

Data (all from Wikipedia, verified, nothing invented - owner's rule):
  - WHICH cartridges: the cartridge column of 'List of assault rifles', counting only rifles that reached
    production (twins merged: .223 Remington -> 5.56x45mm, .308 Winchester -> 7.62x51mm);
  - SIZES: each cartridge's infobox (bullet / neck / shoulder / base / rim diameter, case length, overall
    length; inches converted to mm). A cartridge without complete dimensions is left out.
Drawings are to scale (lengths and diameters); only the shoulder's curve is stylised (no data for it).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
MERGE = {".223 Remington": "5.56×45mm", ".308 Winchester": "7.62×51mm", "5.45×39mm PSP": "5.45×39mm"}
NOT_RIFLE = {"9×19mm Parabellum"}  # a pistol cartridge (one AK variant), not an assault-rifle round
DIMS = ("bullet", "neck", "shoulder", "base", "rim_dia", "case_length", "length")


def _mm(raw: str) -> Optional[float]:
    """Infobox dimension -> mm. '{{convert|9.27|mm|in}}' / '5.70' (mm) / '.3078' or '1.290' (inches)."""
    t = re.sub(r"<ref.*?(?:</ref>|/>)", "", raw or "", flags=re.S)
    m = re.search(r"(\d*\.?\d+)\s*(?:\|\s*-?\s*\|?\s*[\d.]*\s*)?\|?\s*(mm|in)\b", t)
    if m:
        v = float(m.group(1))
        return v * 25.4 if m.group(2) == "in" else v
    m = re.search(r"(\d*\.?\d+)", t)
    if not m:
        return None
    v = float(m.group(1))
    return v * 25.4 if v < 4 else v  # bare numbers: inch figures are < 4 (.308, 2.800), mm figures >= 4


def cartridge_usage() -> Dict[str, Dict[str, Any]]:
    """{cartridge article: {'rifles': n production rifles, 'examples': [...]}} from 'List of assault rifles'."""
    from agents import equipment_catalog as ec
    d = ec._get({"action": "parse", "page": "List of assault rifles", "prop": "wikitext", "formatversion": 2}) or {}
    wt = (d.get("parse") or {}).get("wikitext") or ""
    count: Counter = Counter()
    examples: Dict[str, List[str]] = defaultdict(list)
    for row in wt.split("\n|-")[1:]:
        cells = [c.strip() for c in re.split(r"\n\|", "\n" + row.strip()) if c.strip()]
        if len(cells) < 6:
            continue
        serial = re.sub(r"<ref.*", "", cells[5].lower()).strip()
        if not serial or serial.startswith("no"):
            continue  # prototypes only
        names = re.findall(r"\[\[([^\]|#]+)", cells[0])
        for link in re.findall(r"\[\[([^\]|#]+)", cells[3]):
            k = link.replace("x", "×") if re.match(r"[\d.]+x\d", link) else link
            k = MERGE.get(k, k)
            if k in NOT_RIFLE:
                continue
            count[k] += 1
            if names:
                examples[k].append(names[0])
    return {k: {"rifles": v, "examples": examples[k][:4]} for k, v in count.items()}


def cartridge_facts(titles: List[str]) -> Dict[str, Dict[str, Any]]:
    """Infobox dimensions (mm) + origin + service year per cartridge article; incomplete ones omitted."""
    from agents import equipment_catalog as ec
    out: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(titles), 40):
        d = ec._get({"action": "query", "titles": "|".join(titles[i:i + 40]), "prop": "revisions", "rvprop": "content",
                     "rvslots": "main", "rvsection": 0, "redirects": 1, "formatversion": 2}) or {}
        q = d.get("query", {})
        back = {r["to"]: r["from"] for r in q.get("redirects", [])}
        for pg in q.get("pages", []):
            if pg.get("missing"):
                continue
            fb = ec._infobox(pg["revisions"][0]["slots"]["main"]["content"])
            dims = {k: _mm(fb.get(k, "")) for k in DIMS}
            if not all(dims[k] for k in ("bullet", "base", "case_length", "length")):
                continue  # no complete dimensions -> not drawn (never a guessed size)
            if not (3 <= dims["bullet"] <= 14 and 20 <= dims["case_length"] <= 110 and
                    dims["case_length"] < dims["length"] <= 140 and dims["bullet"] < dims["base"] <= 16):
                continue  # implausible numbers = parsing problem -> left out
            dims["neck"] = dims["neck"] or dims["bullet"] * 1.12
            dims["shoulder"] = dims["shoulder"] or dims["base"] * 0.96
            dims["rim_dia"] = dims["rim_dia"] or dims["base"]
            svc = re.search(r"\b(1[89]\d\d|20[0-2]\d)\b", ec._clean(fb.get("service", "") or fb.get("designed", "")))
            out[back.get(pg["title"], pg["title"])] = {
                "article": pg["title"], "dims": {k: round(v, 2) for k, v in dims.items()},
                "origin": re.sub(r"\s*\(.*?\)", "", ec._origin(fb)).strip(),  # as Wikipedia states it ('Soviet Union')
                "year": svc.group(1) if svc else ""}
    return out


# ------------------------------------------------------------------ real photos (free licence) / AI fallback
# Owner's choice: a free-licensed photo of each cartridge where one exists, otherwise an AI image; the
# to-scale drawing stays as the last resort. A picture is only used when it is ONE cartridge whose length
# to width ratio matches its real dimensions (+-12 %), so group shots, rifles, boxes and wrong rounds are
# rejected; it is then turned tip-right and scaled to the cartridge's real length.
RATIO_TOL = 0.12
_MULTI = re.compile(r"\+|\bvs\.?\b|comparison|\band\b|bullets|cartridges|rounds|lineup|family|box|magazine|rifle|"
                    r"carbine\b(?! ball)|headstamp|reload|primer|case only|projectile|"
                    r"cross.?section|section(?:ed)?\b|cutaway|cut.?away|\b3d\b|render|diagram|drawing|schematic|\.svg", re.I)
_CLIP_YES = ["a photo of a single complete rifle cartridge, brass case with a bullet, side view"]
_CLIP_NO = ["a cut-open sectioned cartridge showing gunpowder inside", "a 3D render cross section of ammunition",
            "several bullets or cartridges side by side", "a rifle or gun", "a metal pipe or rod", "a pen or lipstick"]


def looks_like_cartridge(cut: Image.Image, work: Path) -> bool:
    """Image check on the cutout: one complete round, not a sectioned / rendered / group picture."""
    try:
        from agents.image_generator import ImageGeneratorAgent
        bg = Image.new("RGB", (cut.width + 40, cut.height + 40), (255, 255, 255))
        bg.paste(cut, (20, 20), cut)
        f = work / "_clip_check.png"
        bg.save(f)
        share = ImageGeneratorAgent._clip_share(f, _CLIP_YES, _CLIP_NO)
        return share is None or share >= 0.5  # no CLIP installed: the proportion check alone decides
    except Exception:
        return True


def _key_tokens(name: str) -> List[str]:
    """What a photo's title/description must mention to be THIS cartridge: its numbers ('5.45', '39')."""
    nums = re.findall(r"\d+(?:\.\d+)?", name)
    return [n.lstrip("0") if n.startswith("0.") else n for n in nums]


def _mentions(text: str, name: str) -> bool:
    t = re.sub(r"[x×X]", "×", (text or "").replace("_", " "))
    toks = _key_tokens(name)
    return bool(toks) and all(re.search(rf"(?<![\d.]){re.escape(tok)}(?!\d)", t) for tok in toks)


def _imageinfo(files: List[str]) -> List[Dict[str, Any]]:
    """URL + licence + author for File: titles (via en.wikipedia, which serves Commons files)."""
    from agents import equipment_catalog as ec
    out = []
    for i in range(0, len(files), 20):
        d = ec._get({"action": "query", "titles": "|".join(files[i:i + 20]), "prop": "imageinfo",
                     "iiprop": "url|extmetadata|size", "iiurlwidth": 900, "formatversion": 2}) or {}
        for pg in d.get("query", {}).get("pages", []):
            ii = (pg.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata") or {}
            lic = (meta.get("LicenseShortName") or {}).get("value", "")
            if not ii.get("thumburl") or not re.search(r"public domain|cc0|cc[- ]by|pd", lic, re.I):
                continue  # only free licences
            out.append({"title": pg["title"], "url": ii["thumburl"], "page_url": ii.get("descriptionurl", ""),
                        "description": re.sub(r"<[^>]+>", " ", (meta.get("ImageDescription") or {}).get("value", ""))[:300],
                        "license": lic, "author": re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()[:80] or "Unknown",
                        "short_url": f"https://commons.wikimedia.org/?curid={pg['pageid']}" if pg.get("pageid") and pg.get("imagerepository") == "shared" else ii.get("descriptionurl", "")})
    return out


def commons_search(query: str, limit: int = 25) -> List[str]:
    """File titles on Wikimedia Commons for a query. commons.wikimedia.org is blocked on this network (TCP
    reset); Wikimedia's API gateway (api.wikimedia.org) serves the same search."""
    import requests
    from agents import equipment_catalog as ec
    try:
        r = requests.get("https://api.wikimedia.org/core/v1/commons/search/page",
                         params={"q": query, "limit": limit}, headers=ec.HEADERS, timeout=20)
        if r.status_code == 200:
            return [p["title"] for p in r.json().get("pages", []) if str(p.get("title", "")).startswith("File:")
                    and re.search(r"\.(jpe?g|png)$", p["title"], re.I)]
    except Exception as e:
        print(f"[Cartridges] Commons search failed for '{query}': {e}")
    return []


def photo_candidates(name: str, article: str) -> List[Dict[str, Any]]:
    from agents import equipment_catalog as ec
    cands: List[Dict[str, Any]] = []
    # Wikimedia Commons first (largest free collection), then the article's own images, then Openverse
    files = list(dict.fromkeys(commons_search(f"{name} cartridge") + commons_search(name)))
    cands += _imageinfo(files)
    d = ec._get({"action": "query", "titles": article, "prop": "images", "imlimit": 50, "redirects": 1, "formatversion": 2}) or {}
    files = [i["title"] for pg in d.get("query", {}).get("pages", []) for i in pg.get("images", [])
             if re.search(r"\.(jpe?g|png)$", i["title"], re.I)]
    cands += [c for c in _imageinfo(files) if c["title"] not in {x["title"] for x in cands}]
    try:
        from agents.image_generator import ImageGeneratorAgent
        cands += [dict(c, page_url=c.get("page_url"), short_url=c.get("page_url"))
                  for c in ImageGeneratorAgent()._search_openverse_images(f"{name} cartridge", limit=15)]
    except Exception as e:
        print(f"[Cartridges] Openverse skipped for {name}: {e}")
    # this cartridge only, one round per picture
    def clean_title(t: str) -> str:
        t = re.sub(r"^(File:|Openverse:)", "", t).replace("_", " ")
        for w in re.findall(r"[A-Za-z]{3,}", name):  # the cartridge's own name ('.30 Carbine') isn't a red flag
            t = re.sub(rf"\b{re.escape(w)}\b", " ", t, flags=re.I)
        return t
    return [c for c in cands if _mentions(f"{c['title']} {c.get('description', '')}", name)
            and not _MULTI.search(clean_title(c["title"]))]


def _download(url: str) -> Optional[Image.Image]:
    import io
    import requests
    from agents import equipment_catalog as ec
    try:
        r = requests.get(url, headers=ec.HEADERS, timeout=30)
        if r.status_code == 200 and len(r.content) > 5000:
            return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        pass
    return None


def normalize_cutout(img: Image.Image, dims: Dict[str, float]) -> Optional[Image.Image]:
    """One cartridge from the picture, turned horizontal with the bullet tip on the right, or None when the
    object isn't a single round of these proportions."""
    import numpy as np
    from agents import evolution_poster as ev
    cut = ev._cutout(img)
    if cut is None:
        return None
    a = np.asarray(cut.split()[3]) > 40
    ys, xs = np.nonzero(a)
    if len(xs) < 400:
        return None
    cov = np.cov(np.vstack([xs, ys]).astype(float))
    vals, vecs = np.linalg.eigh(cov)
    major = vecs[:, int(np.argmax(vals))]
    angle = float(np.degrees(np.arctan2(major[1], major[0])))
    rot = cut.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    box = rot.split()[3].point(lambda v: 255 if v > 40 else 0).getbbox()
    if not box:
        return None
    rot = rot.crop(box)
    real = dims["length"] / max(dims["rim_dia"], dims["base"])
    got = rot.width / max(1, rot.height)
    if abs(got - real) / real > RATIO_TOL:
        return None  # not a single, complete, side-on round of this cartridge
    al = np.asarray(rot.split()[3]) > 40
    span = max(3, rot.width // 8)
    left, right = al[:, :span].sum(axis=0).mean(), al[:, -span:].sum(axis=0).mean()
    if left < right:  # the narrower end is the bullet tip: put it on the right
        rot = rot.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return rot


def ai_cartridge(name: str, dims: Dict[str, float], work: Path) -> Optional[Image.Image]:
    """AI image of the round (only when no free photo passes), held to the same proportion check."""
    try:
        from agents.image_generator import ImageGeneratorAgent
        dest = work / f"ai_{re.sub(r'[^a-z0-9]+', '_', name.lower())}.png"
        prompt = (f"studio product photo of a single {name} rifle cartridge, brass case and copper bullet, "
                  f"exact side view, lying horizontally, bullet pointing right, isolated on a plain white background, "
                  f"sharp focus, no text, no other objects")
        gen = ImageGeneratorAgent()
        for attempt in range(3):  # the free engine often draws rods / several rounds: up to 3 tries
            ok, _u, _e, _q = gen._generate_with_flux1(prompt, dest)
            if ok and dest.exists():
                cut = normalize_cutout(Image.open(dest).convert("RGB"), dims)
                if cut is not None and looks_like_cartridge(cut, work):
                    return cut
            print(f"[Cartridges] AI try {attempt + 1} for {name}: not a correct single round, rejected")
    except Exception as e:
        print(f"[Cartridges] AI image skipped for {name}: {e}")
    return None


def picture_for(row: Dict[str, Any], work: Path, use_ai: bool = True) -> Dict[str, Any]:
    """{'img': RGBA or None, 'source': 'photo'|'ai'|'drawn', 'credit': {...} or None}"""
    for c in photo_candidates(row["name"], row["article"])[:14]:
        img = _download(c["url"])
        cut = normalize_cutout(img, row["dims"]) if img is not None else None
        if cut is not None and looks_like_cartridge(cut, work):
            return {"img": cut, "source": "photo", "credit": {"model": row["name"], "file": c["title"], "author": c["author"],
                                                              "license": c["license"], "url": c["page_url"], "short_url": c.get("short_url") or c["page_url"]}}
    if use_ai:
        cut = ai_cartridge(row["name"], row["dims"], work)
        if cut is not None:
            return {"img": cut, "source": "ai", "credit": None}
    return {"img": None, "source": "drawn", "credit": None}


# ------------------------------------------------------------------ drawing

def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for f in (["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"] if bold else []) + \
             ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"]:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def _gradient_fill(mask: Image.Image, top: tuple, mid: tuple, bottom: tuple) -> Image.Image:
    """Metallic vertical shading inside a mask (highlight above the middle, dark edge below)."""
    w, h = mask.size
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        if t < 0.32:
            a, b, k = top, mid, t / 0.32
        else:
            a, b, k = mid, bottom, (t - 0.32) / 0.68
        grad.putpixel((0, y), tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3)))
    img = grad.resize((w, h))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def draw_cartridge(d: Dict[str, float], px_per_mm: float) -> Image.Image:
    """Side view to scale: rim, extractor groove, tapered body, shoulder, neck, bullet ogive."""
    s = px_per_mm
    L, cl = d["length"] * s, d["case_length"] * s
    rim, base, sh, neck, bul = (d["rim_dia"] * s, d["base"] * s, d["shoulder"] * s, d["neck"] * s, d["bullet"] * s)
    hgt = int(max(rim, base) + 8)
    cy = hgt / 2
    img_w = int(L + 8)
    case = Image.new("L", (img_w, hgt), 0)
    cd = ImageDraw.Draw(case)
    x0 = 4
    rim_w, groove_w = 1.3 * s, 1.1 * s
    neck_len = max(neck * 0.9, 3.5 * s)
    sh_len = max(1.5 * s, (sh - neck) * 1.1) if sh > neck else 0
    body_end = x0 + cl - neck_len - sh_len
    pts = [(x0, cy - rim / 2), (x0 + rim_w, cy - rim / 2), (x0 + rim_w, cy - base * 0.42),
           (x0 + rim_w + groove_w, cy - base * 0.42), (x0 + rim_w + groove_w * 1.6, cy - base / 2),
           (body_end, cy - sh / 2), (body_end + sh_len, cy - neck / 2), (x0 + cl, cy - neck / 2)]
    poly = pts + [(x, 2 * cy - y) for x, y in reversed(pts)]
    cd.polygon(poly, fill=255)
    brass = _gradient_fill(case, (255, 236, 160), (214, 168, 66), (122, 84, 22))
    # bullet: cylinder then a tangent ogive to the tip
    bullet = Image.new("L", (img_w, hgt), 0)
    bd = ImageDraw.Draw(bullet)
    bx0, bx1 = x0 + cl - 0.5 * s, x0 + L
    ogive = max((bx1 - bx0) * 0.62, bul * 1.2)
    pts_b = [(bx0, cy - bul / 2), (bx1 - ogive, cy - bul / 2)]
    for i in range(1, 21):
        t = i / 20
        pts_b.append((bx1 - ogive + ogive * t, cy - (bul / 2) * (1 - t ** 1.9) ** 0.75))
    poly_b = pts_b + [(x, 2 * cy - y) for x, y in reversed(pts_b)]
    bd.polygon(poly_b, fill=255)
    copper = _gradient_fill(bullet, (255, 196, 160), (201, 110, 60), (110, 50, 22))
    out = Image.new("RGBA", (img_w, hgt), (0, 0, 0, 0))
    out.alpha_composite(copper)
    out.alpha_composite(brass)
    # crisp outline + rim/groove lines
    od = ImageDraw.Draw(out)
    od.line(poly + [poly[0]], fill=(110, 76, 20, 170), width=1)
    od.line([(x0 + rim_w, cy - rim / 2), (x0 + rim_w, cy + rim / 2)], fill=(120, 84, 24, 200), width=1)
    return out


def render(rows: List[Dict[str, Any]], out_path: Path, title: str, subtitle: str) -> Dict[str, Any]:
    """rows: [{'name', 'dims', 'rifles', 'origin', 'year'}] largest first."""
    img = Image.new("RGB", (W, H), (248, 247, 244))
    dr = ImageDraw.Draw(img)
    # WeaponX header: black rounded bar, white bold title
    dr.rounded_rectangle((40, 40, W - 40, 230), radius=28, fill=(12, 12, 14))
    tf = _font(58)
    lines = title.split("\n")
    y = 135 - 34 * len(lines)
    for ln in lines:
        w = dr.textlength(ln, font=tf)
        dr.text(((W - w) / 2, y), ln, font=tf, fill=(255, 255, 255))
        y += 68
    sf = _font(28, bold=False)
    w = dr.textlength(subtitle, font=sf)
    dr.text(((W - w) / 2, 248), subtitle, font=sf, fill=(70, 70, 70))
    top, bottom = 310, H - 120
    n = len(rows)
    row_h = (bottom - top) / n
    longest = max(r["dims"]["length"] for r in rows)
    widest = max(max(r["dims"]["rim_dia"], r["dims"]["base"]) for r in rows)
    s = min(560 / longest, (row_h * 0.78) / widest)  # one scale for every cartridge = true size comparison
    name_f, meta_f = _font(34), _font(24, bold=False)
    for i, r in enumerate(rows):
        cy = top + row_h * (i + 0.5)
        pic = r.get("picture")
        if pic is not None:
            tw = max(20, int(r["dims"]["length"] * s))  # real length on the common scale
            c = pic.resize((tw, max(8, int(pic.height * tw / pic.width))), Image.Resampling.LANCZOS)
        else:
            c = draw_cartridge(r["dims"], s)
        shadow = Image.new("RGBA", c.size, (0, 0, 0, 0))
        shadow.putalpha(c.split()[3].point(lambda a: int(a * 0.28)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(4))
        x = 50
        img.paste((40, 30, 20), (x + 3, int(cy - c.height / 2 + 6)), shadow)
        img.paste(c, (x, int(cy - c.height / 2)), c)
        tx = x + c.width + 24
        dr.text((tx, cy - 30), r["name"], font=name_f, fill=(18, 18, 18))
        meta = f"Ø {r['dims']['bullet']:.2f} mm · {r['dims']['length']:.1f} mm long · {r['rifles']} rifle{'s' if r['rifles'] != 1 else ''}"
        dr.text((tx, cy + 10), meta, font=meta_f, fill=(85, 85, 85))
    srcs = Counter(r.get("source", "drawn") for r in rows)
    parts = []
    if srcs.get("photo"):
        parts.append(f"{srcs['photo']} free-licence photos (credits in description)")
    if srcs.get("ai"):
        parts.append(f"{srcs['ai']} AI images")
    if srcs.get("drawn"):
        parts.append(f"{srcs['drawn']} drawn from Wikipedia dimensions")
    foot = "All to scale · " + " · ".join(parts)
    ff = _font(22, bold=False)
    w = dr.textlength(foot, font=ff)
    dr.text(((W - w) / 2, H - 80), foot, font=ff, fill=(110, 110, 110))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return {"path": str(out_path), "rows": n}


def build(out_path: Path, title: str = "ASSAULT RIFLE CARTRIDGES\nOF THE WORLD", photos: bool = True,
          use_ai: bool = True) -> Dict[str, Any]:
    usage = cartridge_usage()
    if not usage:
        return {"error": "Couldn't read Wikipedia's List of assault rifles"}
    facts = cartridge_facts(list(usage))
    rows, skipped = [], []
    for k, u in usage.items():
        f = facts.get(k)
        if not f:
            skipped.append(f"{k}: no complete dimensions on Wikipedia")
            continue
        name = re.sub(r"\s*\((?:cartridge|firearms?)\)$", "", f["article"])
        name = re.sub(r"\bcarbine\b", "Carbine", name)  # '.30 carbine' -> '.30 Carbine' 
        rows.append({"name": name, "article": f["article"], "dims": f["dims"], "rifles": u["rifles"],
                     "examples": u["examples"], "origin": f["origin"], "year": f["year"]})
    if len(rows) < 5:
        return {"error": f"Only {len(rows)} cartridges with verified dimensions", "skipped": skipped}
    rows.sort(key=lambda r: -r["dims"]["length"])
    work = Path(out_path).parent / "cartridge_pictures"
    work.mkdir(parents=True, exist_ok=True)
    credits = []
    for r in rows:
        if photos:
            got = picture_for(r, work, use_ai=use_ai)
            r["picture"], r["source"] = got["img"], got["source"]
            if got["credit"]:
                credits.append(got["credit"])
        else:
            r["picture"], r["source"] = None, "drawn"
        print(f"[Cartridges] {r['name']}: {r['source']}")
    subtitle = f"{len(rows)} cartridges · largest to smallest · to scale"
    res = render(rows, out_path, title, subtitle)
    items = [{"rank": i, "name": r["name"], "article": r["article"], "country": r["origin"], "year": r["year"],
              "bullets": [f"Overall length - {r['dims']['length']:.1f} mm", f"Bullet diameter - {r['dims']['bullet']:.2f} mm"],
              "rifles": r["rifles"], "examples": r["examples"], "dims": r["dims"], "picture": r["source"]}
             for i, r in enumerate(rows, 1)]
    return {**res, "items": items, "skipped": skipped, "title": title.replace("\n", " "), "credits": credits}


def verify_items(items: List[Dict[str, Any]]) -> List[str]:
    """Fact check: every drawn cartridge's numbers re-read from Wikipedia; [] when all match."""
    facts = cartridge_facts([it.get("article") or it["name"] for it in items])
    by_article = {f["article"]: f for f in facts.values()}
    bad = []
    for it in items:
        f = by_article.get(it.get("article") or it["name"])
        if not f:
            bad.append(f"{it['name']}: dimensions no longer verifiable on Wikipedia")
            continue
        for k in ("length", "bullet", "case_length", "base"):
            if abs(float(f["dims"][k]) - float((it.get("dims") or {}).get(k, -1))) > 0.05:
                bad.append(f"{it['name']}: {k} {it.get('dims', {}).get(k)} mm vs Wikipedia {f['dims'][k]} mm")
    return bad
