"""
WeaponX Lab ranked chart ("Top 10 ..."): black rounded header, then one row per item with
flag + bold name (year) + country on the left, a real side-profile photo of that exact model, and
two spec bullets on the right; pure white background, 1080x1920.

Item facts (name, country, armament, capacity, in-service year) come from the user's own list.
Each item is matched to its Wikipedia article only to get a real photo (cut out on white) and the
country flag comes from Wikimedia Commons, so no drawing is ever a stand-in for the wrong model.
"""

from __future__ import annotations

import io
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw

from agents import equipment_catalog as ec
from agents import evolution_poster as ev
from agents.subject_match import designators, mentions_any

W, H = 1080, 1920


# ------------------------------------------------------------------ parsing the user's list

def is_ranked_list(text: str) -> bool:
    """A numbered list of items carrying spec lines ('Main armament', 'In service', ...)."""
    items = re.findall(r"(?m)^\s*\d{1,2}\.\s+\S", text or "")
    specs = len(re.findall(r"(?im)^\s*-?\s*(main armament|armament|in service|infantry capacity|calibre|caliber|crew)\s*:", text or ""))
    return len(items) >= 5 and specs >= len(items)


def parse_ranked_list(text: str) -> Dict[str, Any]:
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    title = next((ln.strip() for ln in lines if ln.strip()), "")
    items: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        m = re.match(r"^(\d{1,2})\.\s+(.+)$", s)
        if m and not re.match(r"(?i)^(main|infantry|key|secondary|in service)", m.group(2)):
            cur = {"rank": int(m.group(1)), "name": m.group(2).strip(), "country": "", "specs": {}}
            items.append(cur)
            continue
        if cur is None:
            continue
        kv = re.match(r"^-?\s*([A-Za-z][A-Za-z /]+?)\s*:\s*(.+)$", s)
        if kv:
            cur["specs"][kv.group(1).strip().lower()] = kv.group(2).strip()
        elif not cur["country"] and not s.startswith("-") and len(s) < 40 and not re.search(r"\+\d|database|defen[cs]e and", s, re.I):
            cur["country"] = s
    for it in items:
        svc = it["specs"].get("in service", "")
        y = re.search(r"\b(19|20)\d{2}s?\b", svc)
        it["year"] = y.group(0) if y else ""
    return {"title": re.split(r"\s+[–—-]\s+", title)[0] if title else "", "full_title": title, "items": items}


# ------------------------------------------------------------------ photo + flag lookup

def _simplify(name: str) -> List[str]:
    """'CV90 Mk IV' -> ['CV90 Mk IV', 'CV90']; 'M2A4 Bradley' -> [..., 'M2 Bradley']; 'Puma IFV' -> [..., 'Puma']."""
    out = [name]
    n = re.sub(r"\b(IFV|AFV|APC)\b", "", name).strip()
    n = re.sub(r"\s+Mk\.?\s*[IVX\d]+$", "", n, flags=re.I).strip()
    out.append(n)
    out.append(re.sub(r"\b([A-Z]+\d+)A\d\b", r"\1", n))       # M2A4 -> M2
    out.append(re.sub(r"\b([A-Z]+-\d+)[A-Z]\b", r"\1", n))     # ZBD-04A -> ZBD-04
    return [x for x in dict.fromkeys(o.strip() for o in out) if x]


def match_article(name: str, category_words: str = "fighting vehicle") -> Optional[Dict[str, Any]]:
    """
    The Wikipedia article for a model name. Accepted only if the title or the article's opening text
    names the model, and the article is about a vehicle. Exact title matches rank first
    ('ASCOD' -> 'ASCOD', not 'ASCOD 2'); 'CV90' is found via 'The Combat Vehicle 90 (CV90) ...'.
    """
    for q in _simplify(name):
        desigs = designators(q)
        words = [w for w in re.findall(r"[A-Za-z]{3,}", q) if w.lower() not in ("ifv", "afv")]
        found: List[str] = []
        for query in (q, f"{q} {category_words}"):
            data = ec._get({"action": "query", "list": "search", "srsearch": query, "srlimit": 6})
            found += [h["title"] for h in (data or {}).get("query", {}).get("search", []) if h["title"] not in found]
        models = ec.fetch_models(found[:10]) if found else {}
        scored = []
        for t in found:
            m = models.get(t)
            if not m or not m.get("image_url") or t.lower().startswith("list of"):
                continue
            text = f"{t} {m.get('lead', '')[:300]}"
            named = mentions_any(text, desigs) if desigs else bool(words) and words[0].lower() in t.lower()
            kind_ok = re.search(r"fighting vehicle|armou?red|infantry|tank|vehicle", f"{m.get('type', '')} {m.get('lead', '')}", re.I)
            if not (named and kind_ok):
                continue
            base = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip().lower()
            score = 3 if base == q.lower() else (2 if (mentions_any(t, desigs) if desigs else words[0].lower() in t.lower()) else 1)
            scored.append((score, -len(t), m))
        if scored:
            return max(scored, key=lambda x: (x[0], x[1]))[2]
    return None


_FLAG_FILES = {
    "united states": "Flag of the United States.svg", "usa": "Flag of the United States.svg",
    "united kingdom": "Flag of the United Kingdom.svg", "uk": "Flag of the United Kingdom.svg",
    "china": "Flag of the People's Republic of China.svg", "south korea": "Flag of South Korea.svg",
    "netherlands": "Flag of the Netherlands.svg", "czech republic": "Flag of the Czech Republic.svg",
    "russia": "Flag of Russia.svg", "soviet union": "Flag of the Soviet Union.svg",
}


def flag_image(country: str, cache_dir: Path, height: int = 34) -> Optional[Image.Image]:
    name = country.strip()
    file = _FLAG_FILES.get(name.lower(), f"Flag of {name}.svg")
    key = re.sub(r"[^A-Za-z0-9]+", "_", file)
    p = cache_dir / f"flag_{key}.png"
    if not p.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        for attempt in range(4):  # Commons throttles bursts; retry with back-off
            try:
                r = requests.get("https://commons.wikimedia.org/w/api.php", headers=ec.HEADERS, timeout=30, params={
                    "action": "query", "titles": f"File:{file}", "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 120,
                    "format": "json", "formatversion": 2})
                url = ((r.json()["query"]["pages"][0].get("imageinfo") or [{}])[0]).get("thumburl") if r.status_code == 200 else None
                if url:
                    img = requests.get(url, headers=ec.HEADERS, timeout=30)
                    if img.status_code == 200:
                        Image.open(io.BytesIO(img.content)).convert("RGBA").save(p)
                        break
            except Exception:
                pass
            time.sleep(4 * (attempt + 1))
    if not p.exists():
        return None
    f = Image.open(p).convert("RGBA")
    return f.resize((int(f.width * height / f.height), height))


# ------------------------------------------------------------------ render

def _tidy(spec: str) -> str:
    """Drop filler so a spec fits a bullet: '30–40 mm cannon, depending on variant' -> '30–40 mm cannon'."""
    s = re.sub(r"\s*\([^)]*\)", "", spec)
    s = re.sub(r",?\s*depending on (the )?variant.*$", "", s, flags=re.I)
    s = re.sub(r"\bapproximately\b", "approx.", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" ,;")


def _bullets(specs: Dict[str, str]) -> List[str]:
    out = []
    arm = specs.get("main armament") or specs.get("armament")
    if arm:
        out.append(f"Gun - {_tidy(arm)}")
    cap = specs.get("infantry capacity") or specs.get("crew")
    if cap:
        out.append(f"Troops - {_tidy(cap)}")
    return out[:2]


def render(parsed: Dict[str, Any], resolved: List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]], out_path: Path, cache_dir: Path) -> Dict[str, Any]:
    canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    d = ImageDraw.Draw(canvas)
    # Header: black rounded bar with white condensed title (WeaponX channel style)
    title = parsed["title"].upper()
    f_title = ev._font("Impact.ttf", 58)
    while d.textlength(title, font=f_title) > W - 90 and f_title.size > 34:
        f_title = ev._font("Impact.ttf", f_title.size - 2)
    d.rounded_rectangle((18, 14, W - 18, 104), radius=22, fill=(10, 10, 10, 255))
    d.text((W // 2, 59), title, font=f_title, fill=(255, 255, 255), anchor="mm")

    rows = resolved
    top0, bottom = 122, H - 26
    row_h = (bottom - top0) // len(rows)
    f_name = ev._font("Arial Bold.ttf", 31)
    f_year = ev._font("Arial.ttf", 27)
    f_country = ev._font("Arial.ttf", 20)
    f_bullet = ev._font("Arial Bold.ttf", 19)
    placed = 0
    for i, (item, model) in enumerate(rows):
        top = top0 + i * row_h
        x = 26
        countries = [c.strip() for c in re.split(r"\s*/\s*|\s+and\s+", item.get("country", "")) if c.strip()]
        for c in countries[:2]:
            fl = flag_image(c, cache_dir)
            if fl is not None:
                canvas.alpha_composite(fl, (x, top + 8))
                x += fl.width + 6
        name_x = x + 6
        d.text((name_x, top + 4), item["name"], font=f_name, fill=(10, 10, 10))
        nw = d.textlength(item["name"], font=f_name)
        if item.get("year"):
            d.text((name_x + nw + 8, top + 7), f"({item['year']})", font=f_year, fill=(10, 10, 10))
        d.text((name_x, top + 42), " / ".join(countries) or item.get("country", ""), font=f_country, fill=(40, 40, 40))
        # Photo of the exact model, centred in the row, sitting on a common baseline
        if model is not None:
            img, is_cut = ev.fetch_photo(model, cache_dir)
            if img is not None:
                ev._paste_item(canvas, img, is_cut, 520, top + 30, 470, row_h - 44)
                placed += 1
        # Spec bullets, bottom right
        # Bullets may wrap to a second line (indented) instead of being cut off
        blines: List[Tuple[str, bool]] = []
        for b in _bullets(item.get("specs", {})):
            for k, ln in enumerate(ev._wrap(d, b, f_bullet, 292)):
                blines.append((ln, k == 0))
        by = top + row_h - 16 - 24 * len(blines)
        for j, (ln, first) in enumerate(blines):
            d.text((760, by + j * 24), ("• " if first else "   ") + ln, font=f_bullet, fill=(10, 10, 10))
    d.line((18, H - 14, W - 18, H - 14), fill=(214, 40, 70), width=6)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "PNG")
    return {"path": str(out_path), "rows": len(rows), "photos": placed}


def make_poster(text: str, out_path: Path, cache_dir: Path) -> Dict[str, Any]:
    parsed = parse_ranked_list(text)
    if len(parsed["items"]) < 5:
        return {"error": "Could not read a numbered list of at least 5 items."}
    resolved, missing = [], []
    for it in parsed["items"]:
        m = match_article(it["name"])
        if m is None:
            missing.append(it["name"])
        resolved.append((it, m))
        time.sleep(0.5)
    if missing:
        # Never draw a stand-in for a model we couldn't find a real photo of
        return {"error": f"No verified photo found for: {', '.join(missing)}", "parsed": parsed}
    res = render(parsed, resolved, out_path, cache_dir)
    pairs_like = [{"historical": m, "modern": m} for _, m in resolved]
    credits = ev.photo_credits([{"historical": m, "modern": m} for _, m in resolved])
    seen, uniq = set(), []
    for c in credits:
        if c["file"] not in seen:
            seen.add(c["file"])
            uniq.append(c)
    return {**res, "title": parsed["title"], "items": [
        {"rank": it["rank"], "name": it["name"], "country": it["country"], "year": it["year"], "article": m["title"],
         "photo": m.get("image_file_used") or m.get("image_file")} for it, m in resolved], "credits": uniq}
