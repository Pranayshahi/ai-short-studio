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
    foot = "Drawn to scale from Wikipedia dimensions · rifles = production assault rifles in Wikipedia's list"
    ff = _font(22, bold=False)
    w = dr.textlength(foot, font=ff)
    dr.text(((W - w) / 2, H - 80), foot, font=ff, fill=(110, 110, 110))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return {"path": str(out_path), "rows": n}


def build(out_path: Path, title: str = "ASSAULT RIFLE CARTRIDGES\nOF THE WORLD") -> Dict[str, Any]:
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
    subtitle = f"{len(rows)} cartridges · largest to smallest · drawn to scale"
    res = render(rows, out_path, title, subtitle)
    items = [{"rank": i, "name": r["name"], "article": r["article"], "country": r["origin"], "year": r["year"],
              "bullets": [f"Overall length - {r['dims']['length']:.1f} mm", f"Bullet diameter - {r['dims']['bullet']:.2f} mm"],
              "rifles": r["rifles"], "examples": r["examples"], "dims": r["dims"]} for i, r in enumerate(rows, 1)]
    return {**res, "items": items, "skipped": skipped, "title": title.replace("\n", " ")}


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
