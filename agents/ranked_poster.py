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
    items = re.findall(r"(?m)^\s*\d{1,2}\.\s+(.+)$", text or "")
    specs = len(re.findall(r"(?im)^\s*-?\s*(main armament|armament|in service|infantry capacity|calibre|caliber|crew)\s*:", text or ""))
    if len(items) < 5:
        return False
    # a plain ranked list of model names ('1. Leopard 2A8' / 'Germany 🇩🇪' / one-line note), e.g. from ChatGPT
    short = sum(1 for it in items if len(it.strip()) <= 40)
    return specs >= len(items) or short >= 0.8 * len(items)


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
            cur["country"] = re.sub(r"[\U0001F1E6-\U0001F1FF\uFFFD]+", "", s).strip(" /-")  # 'Germany 🇩🇪' -> 'Germany'
        elif "note" not in cur and not s.startswith("-") and not kv:
            cur["note"] = s[:140]  # the list's one-line description of the model
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
    # newer variants whose Wikipedia article is the base model (2026 lists name the latest variant)
    v = re.sub(r"\s+Mk\.?\s*\d+\w*.*$", "", name, flags=re.I).strip()          # Merkava Mk4 Barak -> Merkava
    v = re.sub(r"\b(\d+)A\d+\w*\b", r"\1", v)                                 # Leopard 2A8 -> Leopard 2
    v = re.sub(r"\b([A-Z]{1,3}-\d+)[A-Z][A-Z0-9]*\b", r"\1", v)                # T-72B3M / T-80BVM -> T-72 / T-80
    v = re.sub(r"\b(Type \d+)[A-Z]\b", r"\1", v)                               # Type 99A -> Type 99
    v = re.sub(r"\s+(SEP\w*|XLR|Mk\w*|[IVX]+)$", "", v).strip()                # Leclerc XLR, Al-Khalid I
    out.append(v)
    first = re.match(r"^(\S+(?:\s\d+)?)", v)                                      # T-90M Proryv -> T-90
    if first and first.group(1) != v:
        out.append(first.group(1))
    return [x for x in dict.fromkeys(o.strip() for o in out) if x]


# What a valid article must be about, per chart kind (a pistol chart must never accept a vehicle article)
KINDS: Dict[str, Dict[str, str]] = {
    "vehicle": {"words": "fighting vehicle", "kind_re": r"fighting vehicle|armou?red|infantry|tank|vehicle"},
    "firearm": {"words": "pistol", "kind_re": r"pistol|handgun|revolver|firearm|semi-automatic|rifle|carbine|submachine|machine gun|shotgun"},
    # Broad WeaponX topics (agents/topic_weapon_list.py): each row must be an article about this kind of system
    "naval": {"words": "naval weapon", "kind_re": r"torpedo|missile|cruise|ballistic|naval mine|anti-ship|anti-submarine|"
                                                  r"submarine-launched|SLBM|depth charge|close-in weapon|naval gun|vertical launch"},
    "missile": {"words": "missile", "kind_re": r"missile|rocket|cruise|ballistic|hypersonic|glide vehicle|interceptor|munition"},
    "aircraft": {"words": "military aircraft", "kind_re": r"aircraft|fighter|bomber|helicopter|unmanned|drone|interceptor|airlifter|gunship"},
    "warship": {"words": "warship", "kind_re": r"submarine|ship|destroyer|frigate|corvette|aircraft carrier|cruiser|vessel|warship"},
    "artillery": {"words": "artillery", "kind_re": r"howitzer|artillery|mortar|rocket launcher|multiple rocket|self-propelled|field gun"},
    "air_defense": {"words": "air defence system", "kind_re": r"surface-to-air|air defen[cs]e|anti-aircraft|missile system|interceptor|SAM"},
}


def match_article(name: str, category_words: str = "fighting vehicle", kind: str = "vehicle") -> Optional[Dict[str, Any]]:
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
            # an article without a lead photo is fine: the photo is then searched by the model's name
            if not m or t.lower().startswith("list of"):
                continue
            text = f"{t} {m.get('lead', '')[:300]}"
            base = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip().lower()
            exact = base == q.lower()  # article titled exactly as the model ('CZ 75': no designator, no 3-letter word)
            named = exact or (mentions_any(text, desigs) if desigs else bool(words) and words[0].lower() in t.lower())
            kre = KINDS.get(kind, KINDS["vehicle"])["kind_re"]
            if (m.get("type") or "").strip():
                kind_ok = re.search(kre, m["type"], re.I)
            else:  # no infobox type: the opening sentence must SAY it is one ("... is a main battle tank")
                kind_ok = re.search(rf"\b(?:is|was) an?\s+(?:[\w-]+\s+){{0,6}}?(?:{kre})", m.get("lead", ""), re.I) \
                    and not re.search(r"\b(?:is|was) an?\s+(?:[\w'-]+\s+){0,4}?(?:sight|fire[- ]control|radar|engine|system for|turret)", m.get("lead", ""), re.I)
            if kind == "vehicle" and re.search(r"anti-?\s?tank|anti-?\s?armou?r", m.get("type") or "", re.I):
                kind_ok = None
            if not (named and kind_ok):
                continue
            score = 3 if exact else (2 if (mentions_any(t, desigs) if desigs else bool(words) and words[0].lower() in t.lower()) else 1)
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
        # Commons throttles bursts (and sometimes resets connections outright); en.wikipedia's API serves
        # the same Commons file info, so alternate between the two
        apis = ["https://commons.wikimedia.org/w/api.php", "https://en.wikipedia.org/w/api.php"]
        for attempt in range(4):
            try:
                r = requests.get(apis[attempt % 2], headers=ec.HEADERS, timeout=30, params={
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
            time.sleep(2 * (attempt + 1))
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
    s = re.sub(r"^Up to\b", "up to", s)
    return re.sub(r"\s+", " ", s).strip(" ,;")


def _bullets(specs: Dict[str, str]) -> List[str]:
    if specs.get("_bullets"):  # pre-written bullets (curated firearm lists: "Cartridge - 9×19mm", "No. built - ...")
        return [b for b in specs["_bullets"] if b][:2]
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
        country_txt = " / ".join(countries) or item.get("country", "")
        year_txt = f"({item['year']})" if item.get("year") else ""
        photo_left = 560 - 190 if parsed.get("kind") == "firearm" else W
        if year_txt and name_x + nw + 8 + d.textlength(year_txt, font=f_year) > photo_left - 10:
            country_txt = f"{country_txt} · {item['year']}" if country_txt else item["year"]  # no room: year moves down
            year_txt = ""
        if year_txt:
            d.text((name_x + nw + 8, top + 7), year_txt, font=f_year, fill=(10, 10, 10))
        d.text((name_x, top + 42), country_txt, font=f_country, fill=(40, 40, 40))
        # Photo of the exact model, centred in the row, sitting on a common baseline
        if model is not None:
            img, is_cut = ev.fetch_photo(model, cache_dir)
            if img is not None:
                if parsed.get("kind") == "firearm":  # short, wide objects: use the full row height
                    ev._paste_item(canvas, img, is_cut, 560, top + 10, 380, row_h - 22, shadow=False)
                else:
                    # Below the name/year and country lines (a framed photo used to cover "(1990)")
                    ev._paste_item(canvas, img, is_cut, 520, top + 68, 470, row_h - 82)
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


def make_poster_from_items(title: str, rows: List[Dict[str, Any]], out_path: Path, cache_dir: Path,
                           kind: str = "firearm") -> Dict[str, Any]:
    """
    Same chart from an already-structured list (the curated WeaponX rows: name, year, country,
    bullet_1, bullet_2, query). Each row still needs a real photo of that exact model, or nothing is drawn.
    """
    items = [{"rank": int(r.get("rank") or i), "name": r["name"], "country": r.get("country", ""),
              "year": str(r.get("year") or ""), "lookup": r.get("query") or r["name"],
              "specs": {"_bullets": [r.get("bullet_1", ""), r.get("bullet_2", "")]}}
             for i, r in enumerate(rows, 1) if r.get("name")]
    return _build({"title": title, "full_title": title, "items": items}, out_path, cache_dir, kind)


MAX_LIST_ROWS = 10  # 1080x1920: more rows than this are unreadable on a phone


def _norm(n: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)\s*$", "", n or "").lower().replace(" tank", ""))


def make_poster(text: str, out_path: Path, cache_dir: Path, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    """The user's own ranked list (e.g. pasted from ChatGPT), in THEIR order with THEIR names. Every row is
    verified on Wikipedia (right kind of system, real photo, country); a name that can't be verified is
    skipped and reported, and the next list entries fill the chart (up to MAX_LIST_ROWS)."""
    parsed = parse_ranked_list(text)
    spec_keys = {k for it in parsed["items"] for k in it["specs"]}
    if spec_keys & {"main armament", "armament", "infantry capacity", "crew"}:
        return _build(parsed, out_path, cache_dir, "vehicle")  # the original IFV spec-sheet format
    from agents import topic_weapon_list as twl
    title = parsed["title"] or "Ranked list"
    # a list with 'Calibre:' / 'Cartridge:' lines is a firearm list, whatever the title says
    # ('Weapons Used by Russian Spetsnaz' was read as a missile chart)
    kind = "firearm" if spec_keys & {"calibre", "caliber", "cartridge"} else twl.kind_for(title)
    sub = twl.subtype_for(title)
    words = (sub[2][0] if sub and sub[2] else KINDS.get(kind, KINDS["vehicle"])["words"])
    excluded = {_norm(x) for x in exclude or []}
    resolved, skipped, used = [], [], set()
    for it in parsed["items"]:
        if len(resolved) >= MAX_LIST_ROWS:
            break
        if _norm(it["name"]) in excluded:
            continue
        m = match_article(it["name"], words, kind)
        if m is None:
            skipped.append(f"{it['name']}: no Wikipedia article with a photo found")
            continue
        # the user named this model: only the broad category must match (an APC list may include the VBCI,
        # which Wikipedia types 'infantry fighting vehicle'); a sight, a missile or a truck is still rejected
        if not twl._is_kind({**m, "origin": m.get("origin") or it.get("country") or "x",
                             "image_url": m.get("image_url") or "photo searched by name"}, kind,
                            KINDS.get(kind, KINDS["vehicle"])["kind_re"], None):
            skipped.append(f"{it['name']}: Wikipedia says '{m['title']}' is a {(m.get('type') or 'different system')[:40]}")
            continue
        if _norm(m["title"]) in excluded:
            continue
        multi_article = bool(re.search(r"\s(?:and|&)\s", m["title"])) and _norm(it["name"]) != _norm(m["title"])
        if m["title"] in used or multi_article:
            # two weapons in one article ('AS Val and VSS Vintorez'): a row of its own when the article title
            # names it; its photo is then searched by its own name (never the other row's photo)
            if not (_norm(it["name"]) and _norm(it["name"]) in _norm(m["title"])) or it["name"] in used:
                skipped.append(f"{it['name']}: same article as another row ({m['title']})")
                continue
            # the shared infobox mostly describes the other weapon: keep only the cartridge, no year
            other_names = [x.strip() for x in re.split(r"\s+(?:and|&)\s+", m["title"]) if _norm(x) != _norm(it["name"])]
            m = dict(m, _article=m["title"], title=it["name"], image_url=None, image_file=None, year=None, type="",
                     _exclude_names=other_names,
                     specs={k: v for k, v in (m.get("specs") or {}).items() if k == "Cartridge"})
        if re.search(r"(?:&|\band\b|_and_|\+)", str(m.get("image_file") or ""), re.I):
            m = dict(m, image_url=None, image_file=None)  # a group picture: search a photo of this model alone
        used.add(m["title"])
        m["_kind"] = kind
        same_model = _norm(it["name"]) == _norm(m["title"])
        b1, b2 = twl._bullets(m)
        row = {"rank": len(resolved) + 1, "name": it["name"],
               # Wikipedia's origin first; the list's own line only when it really is a country
               # (ChatGPT lists put the weapon type there: 'Assault Rifle')
               "country": (ec._country(m["origin"]) if m.get("origin") else "") or (
                   it.get("country") if it.get("country") and not re.search(
                       r"rifle|gun|pistol|carbine|weapon|launcher|missile|tank|vehicle|sniper|machine|system|\d",
                       it["country"], re.I) else ""),
               # the article's service year is the BASE model's: only shown when the row IS that model
               "year": twl.shown_year(m) if same_model else "",
               "lookup": m["title"], "specs": {"_bullets": [b1, b2]}, "note": it.get("note", "")}
        resolved.append((row, m))
        time.sleep(0.3)
    if len(resolved) < 5:
        return {"error": f"Only {len(resolved)} of the listed models could be verified on Wikipedia (need 5). "
                         f"Not verified: {'; '.join(skipped)[:400]}", "skipped": skipped}
    title = twl.fix_top_n(title, len(resolved))  # the user's 'Top 20' list shows at most 10 rows
    chart = {"title": title.upper(), "full_title": parsed["full_title"], "items": [r for r, _ in resolved], "kind": kind}
    res = render(chart, resolved, out_path, cache_dir)
    if res.get("error"):
        return res
    credits, seen = [], set()
    for c in ev.photo_credits([{"historical": m, "modern": m} for _, m in resolved]):
        if c["file"] not in seen:
            seen.add(c["file"])
            credits.append(c)
    return {**res, "title": title, "kind": kind, "skipped": skipped, "credits": credits, "items": [
        {"rank": r["rank"], "name": r["name"], "country": r["country"], "year": r["year"],
         "article": m.get("_article") or m["title"],
         "photo": m.get("image_file_used") or m.get("image_file"), "note": r["note"],
         "bullets": [b for b in r["specs"]["_bullets"] if b]} for r, m in resolved]}


def _build(parsed: Dict[str, Any], out_path: Path, cache_dir: Path, kind: str) -> Dict[str, Any]:
    if len(parsed["items"]) < 5:
        return {"error": "Could not read a numbered list of at least 5 items."}
    parsed["kind"] = kind
    words = KINDS.get(kind, KINDS["vehicle"])["words"]
    resolved, missing = [], []
    for it in parsed["items"]:
        m = match_article(it.get("lookup") or it["name"], words, kind)
        if m is not None:
            m["_kind"] = kind  # photo selection checks what a good picture of this kind looks like
            if (it.get("specs") or {}).get("_bullets") is not None:
                # Built-in (hand-written) rows: every fact comes from the model's Wikipedia article and passes
                # the checks; the hand-written numbers were unsourced ('SIG M17 - 500 Thousand' vs 200,000)
                from agents import topic_weapon_list as twl
                it["specs"]["_bullets"] = [b for b in twl._bullets(m) if b]
                it["year"] = twl.shown_year(m) if _norm(it["name"]) == _norm(m["title"]) else ""
                if m.get("origin"):
                    it["country"] = ec._country(m["origin"])
        if m is None:
            missing.append(it["name"])
        resolved.append((it, m))
        time.sleep(0.5)
    if missing:
        # Never draw a stand-in for a model we couldn't find a real photo of
        return {"error": f"No verified photo found for: {', '.join(missing)}", "parsed": parsed}
    res = render(parsed, resolved, out_path, cache_dir)
    credits = ev.photo_credits([{"historical": m, "modern": m} for _, m in resolved])
    seen, uniq = set(), []
    for c in credits:
        if c["file"] not in seen:
            seen.add(c["file"])
            uniq.append(c)
    return {**res, "title": parsed["title"], "items": [
        {"rank": it["rank"], "name": it["name"], "country": it["country"], "year": it["year"], "article": m["title"],
         "photo": m.get("image_file_used") or m.get("image_file"),
         "bullets": _bullets(it["specs"]),
         "gun": _tidy(it["specs"].get("main armament") or it["specs"].get("armament") or ""),
         "troops": _tidy(it["specs"].get("infantry capacity") or it["specs"].get("crew") or "")}
        for it, m in resolved], "credits": uniq}
