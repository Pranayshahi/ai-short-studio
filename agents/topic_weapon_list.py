"""
A verified list of weapon systems for a broad WeaponX topic ("Modern Submarine Weapon Systems"),
so the WeaponX chart always shows a list of real models like the 'Hand Guns' chart, even when
Wikipedia has no "List of ..." page for the topic.

Where names come from: the local LLM (Ollama) suggests candidate model NAMES only, and Wikipedia
search adds more. Every name must resolve to a Wikipedia article about that kind of system, with a
photo; facts (year, origin, type) come from the article's infobox, never from the model. At least
5 verified rows are required; otherwise the caller falls back (verified hero photo).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# topic pattern -> chart kind (see ranked_poster.KINDS)
_KIND_RULES: List[Tuple[str, str]] = [
    (r"submarine weapon|torpedo|naval weapon|anti-ship|anti-submarine|ship.?(?:borne|launched) weapon|naval missile", "naval"),
    (r"air defen[cs]e|surface-to-air|\bsam\b|anti-aircraft|missile defen", "air_defense"),
    (r"missile|hypersonic|icbm|ballistic|cruise|rocket", "missile"),
    (r"submarine|warship|destroyer|frigate|corvette|aircraft carrier|navy ship|naval ship|battleship", "warship"),
    (r"fighter|jet|bomber|aircraft|helicopter|drone|uav|stealth plane|air force", "aircraft"),
    (r"artillery|howitzer|mortar|mlrs|rocket launcher", "artillery"),
    (r"tank|ifv|infantry fighting|apc|armou?red|combat vehicle", "vehicle"),
    (r"rifle|pistol|handgun|gun|carbine|sniper|firearm|small arms", "firearm"),
]


def kind_for(topic: str) -> str:
    t = (topic or "").lower()
    for pat, kind in _KIND_RULES:
        if re.search(pat, t):
            return kind
    return "missile"


NAMES_SCHEMA = {"type": "object", "properties": {"models": {"type": "array", "items": {"type": "string"}}},
                "required": ["models"]}


def _llm_names(topic: str, n: int = 16) -> List[str]:
    try:
        from agents import script_writer
        from app.automation import resources
        if not script_writer.can_run():
            return []
        with resources.lease("ollama"):
            if not script_writer.is_available():
                return []
            try:
                data = script_writer._ollama(
                    f"List the {n} most important, best-known military systems that belong in a chart titled '{topic}', "
                    "most capable first (current front-line systems for 'modern' or a year). "
                    "Use the exact model names as Wikipedia titles them (e.g. 'Mark 48 torpedo', 'UGM-133 Trident II', "
                    "'3M-54 Kalibr'). Only real systems in service or recently retired; no categories, no prototypes.",
                    NAMES_SCHEMA, timeout=120)
            finally:
                script_writer._unload()  # free the model now, so music/clip engines aren't blocked
        return [str(x).strip() for x in data.get("models") or [] if str(x).strip()][:n]
    except Exception as e:
        print(f"[TopicList] LLM names skipped: {e}")
        return []


# Extra Wikipedia searches per kind, so broad topics still yield enough verified models
KIND_QUERIES = {
    "naval": ["heavyweight torpedo", "lightweight torpedo", "submarine-launched cruise missile",
              "submarine-launched ballistic missile", "anti-ship missile", "anti-submarine missile"],
    "missile": ["cruise missile", "ballistic missile", "hypersonic missile", "anti-ship missile"],
    "air_defense": ["surface-to-air missile system", "air defence system"],
    "aircraft": ["fighter aircraft", "multirole combat aircraft", "attack helicopter"],
    "warship": ["destroyer class", "attack submarine class", "frigate class"],
    "artillery": ["self-propelled howitzer", "multiple rocket launcher"],
    "vehicle": ["main battle tank", "infantry fighting vehicle"],
}


def _list_article_links(query: str, limit: int = 300) -> List[str]:
    """Model titles linked from Wikipedia's own list article ('List of main battle tanks by generation'):
    a complete candidate pool (plain searches missed K2 Black Panther and Leclerc)."""
    from agents import equipment_catalog as ec
    data = ec._get({"action": "query", "list": "search", "srsearch": f"intitle:list {query}", "srlimit": 3}) or {}
    lists = [h["title"] for h in data.get("query", {}).get("search", []) if h["title"].lower().startswith("list of")][:2]
    out: List[str] = []
    for lt in lists:
        cont: Dict[str, Any] = {}
        for _page in range(4):
            d = ec._get({"action": "query", "titles": lt, "prop": "links", "plnamespace": 0, "pllimit": "max", **cont}) or {}
            for pg in d.get("query", {}).get("pages", []):
                out += [l["title"] for l in pg.get("links", []) if l["title"] not in out]
            cont = d.get("continue") or {}
            if not cont or len(out) >= limit:
                break
    return [t for t in out if not t.lower().startswith(("list of", "category:"))][:limit]


def _search_titles(topic: str, kind: str = "") -> List[str]:
    from agents import equipment_catalog as ec
    core = re.sub(r"\b(modern|systems?|the|top|best|most|powerful|world'?s?|of|weapons?)\b", " ", topic, flags=re.I)
    titles: List[str] = []
    sub = subtype_for(topic)
    extra = sub[2] if sub else KIND_QUERIES.get(kind, [])
    for q in (topic, core.strip(), f"{core.strip()} weapon", *extra):
        if not q.strip():
            continue
        data = ec._get({"action": "query", "list": "search", "srsearch": q, "srlimit": 15})
        for h in (data or {}).get("query", {}).get("search", []):
            if h["title"] not in titles and not h["title"].lower().startswith(("list of", "category:")):
                titles.append(h["title"])
    titles = titles[:60]
    if sub:  # a specific system type: Wikipedia's list articles give the complete pool
        for q in sub[2][:1]:
            titles += [t for t in _list_article_links(q) if t not in titles]
    return titles


def _clean_type(raw: str) -> str:
    """Infobox type without template code: '{{idp| *Cruise missile *Anti-ship ...' -> 'Cruise missile'."""
    t = re.sub(r"\{\{[^|}]*\|", "", str(raw or ""))
    t = re.sub(r"[{}\[\]]", "", t)
    parts = [x.strip(" *-,;") for x in re.split(r"\*|<br\s*/?>|;", t) if x.strip(" *-,;")]
    return re.sub(r"\s+", " ", parts[0] if parts else t).strip()


_BULLET_ORDER = ["Range", "Speed", "Warhead", "No. built", "Cartridge", "Calibre", "Fire rate", "Weight",
                 "Engine", "Guidance", "Length"]


# Realistic limits per kind (unit, low, high). A value outside them, or in another unit, is NOT shown:
# a wrong number on a chart is worse than a missing one (T-14 'Range - 5 km' was published).
_BOUNDS: Dict[str, Dict[str, Tuple[str, float, float]]] = {
    "vehicle": {"Range": ("km", 100, 1500), "Speed": ("km/h", 15, 140), "Weight": ("t", 2, 90), "Main gun": ("mm", 7, 160)},
    "artillery": {"Range": ("km", 3, 500), "Speed": ("km/h", 10, 140), "Weight": ("t", 1, 80)},
    "aircraft": {"Range": ("km", 100, 20000), "Speed": ("km/h", 100, 4500)},
    "warship": {"Range": ("km", 500, 60000), "Speed": ("km/h", 10, 100)},
    "missile": {"Range": ("km", 0.3, 20000)},
    "air_defense": {"Range": ("km", 1, 1000)},
    "naval": {"Range": ("km", 0.5, 20000)},
    "firearm": {"Range": ("m", 10, 3000), "Weight": ("kg", 0.2, 25), "Fire rate": ("rounds/min", 1, 6000)},
}


def _first_number(v: str) -> Optional[float]:
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", v or "")
    return float(m.group(1).replace(",", "")) if m else None


def _this_year() -> int:
    import datetime
    return datetime.date.today().year


def shown_year(m: Dict[str, Any]) -> str:
    """Service year for the chart: never a future (planned) year."""
    y = m.get("year")
    return str(y) if y and y <= _this_year() else ""


def checked_specs(m: Dict[str, Any]) -> Dict[str, str]:
    """The model's specs that are certainly right for THIS kind of system, everything else dropped."""
    kind = m.get("_kind") or ""
    specs = dict(m.get("specs") or {})
    vr = specs.pop("Vehicle range", None)
    if kind in ("vehicle", "artillery"):
        # a vehicle's range is its driving range; the plain 'range' field is its gun's (T-14: 5 km)
        specs.pop("Range", None)
        if vr:
            specs["Range"] = vr
        if m.get("calibre_mm"):
            specs["Main gun"] = f"{m['calibre_mm']:g} mm"
        if m.get("weight_t") and not specs.get("Weight"):
            specs["Weight"] = f"{m['weight_t']:g} t"
    if specs.get("Weight"):
        specs["Weight"] = re.sub(r"\s*(?:tonnes?|metric tons?)\b", " t", specs["Weight"])
    for label, (unit, lo, hi) in _BOUNDS.get(kind, {}).items():
        v = specs.get(label)
        if not v:
            continue
        if label == "Speed" and v.lower().startswith("mach"):
            continue  # Mach figures are checked by their own form
        n = _first_number(v)
        unit_ok = re.search(rf"\d\s*{re.escape(unit)}\b", v.replace("tonnes", "t").replace("tonne", "t")) is not None
        if n is None or not unit_ok or not (lo <= n <= hi):
            specs.pop(label)
    return specs


def _bullets(m: Dict[str, Any]) -> Tuple[str, str]:
    """Two real specs from the article's infobox, like the reference chart ('Cartridge - 7.62x39 mm',
    'No. built - 75 million'); type / service year only when the article has no usable specs."""
    specs = checked_specs(m)
    order = _BULLET_ORDER
    if m.get("_kind") == "vehicle":
        # tanks/IFVs are compared by their gun and weight (like '120 mm gun' in editorial lists)
        order = ["Main gun", "Weight", "Speed", "Range", "No. built"]
        if specs.get("Weight"):
            specs["Weight"] = re.sub(r"\s*(?:tonnes?|metric tons?)\b", " t", specs["Weight"])
    picks = [f"{k} - {specs[k]}" for k in order if specs.get(k)][:2]
    if len(picks) < 2:
        typ = _clean_type(m.get("type") or "")
        if len(typ) > 34:
            typ = typ[:34].rsplit(" ", 1)[0]
            typ = re.sub(r"\s+(?:and|or|with|of|for|the|a|an|to|in)$", "", typ)
        yr = m.get("year") if (m.get("year") or 9999) <= _this_year() else None  # 2027 = planned, not in service
        for extra in ([f"Type - {typ}"] if typ else []) + ([f"In service - {yr}"] if yr else []):
            if len(picks) < 2:
                picks.append(extra)
    picks += [""] * (2 - len(picks))
    return picks[0], picks[1]


# Platforms are not weapons: a "submarine weapon systems" chart must not list submarines or ships
_EXCLUDE = {
    # 'submarine' as the thing itself (not "anti-submarine" / "submarine-launched")
    "naval": r"(?<![-\w])submarine(?!-)|\bclass\b|(?<![-\w])ship\b|vessel|aircraft carrier|destroyer|frigate|engine|turbofan",
    "missile": r"\bclass\b|(?<![-\w])ship\b|(?<![-\w])submarine(?!-)|engine|turbofan|aircraft\s*$",
    "air_defense": r"\bclass\b|(?<![-\w])ship\b|engine|radar\s*$",
}


# A narrower topic narrows the chart: "Main Battle Tanks" lists tanks only (it listed IFVs and the NLAW
# anti-tank missile, because their infobox types contain "tank"/"vehicle"). (topic, type must match,
# type must not match, extra Wikipedia searches)
_SUBTYPES: List[Tuple[str, str, str, List[str]]] = [
    (r"(?<!anti-)(?<!anti )\btanks?\b", r"\btank\b",
     r"anti-?\s?tank|tank destroyer|infantry|personnel|amphibious|recovery|bridge|engineer|reconnaissance|light tank",
     ["main battle tank", "third-generation main battle tank"]),
    (r"infantry fighting|\bifvs?\b", r"infantry fighting", r"anti-?\s?tank", ["infantry fighting vehicle"]),
    # APC families are often typed 'Armoured fighting vehicle' (Boxer, Eitan, Piranha V, AMPV) or 'Heavy APC'
    (r"\bapcs?\b|personnel carrier", r"personnel carrier|\bapc\b|armou?red fighting vehicle|infantry carrier|troop carrier|multi-?purpose vehicle",
     r"anti-?\s?tank|^infantry fighting vehicle|tank destroyer|assault gun|main battle tank|armou?red car|reconnaissance|self-propelled",
     ["armoured personnel carrier", "wheeled armoured fighting vehicle", "heavy armoured personnel carrier"]),
    (r"handgun|pistol", r"pistol|handgun|revolver", r"submachine|machine pistol|rifle|carbine", ["semi-automatic pistol"]),
    (r"sniper", r"sniper|marksman|anti-materiel", r"", ["sniper rifle"]),
    (r"assault rifle", r"assault rifle|battle rifle", r"", ["assault rifle"]),
    (r"attack helicopter|helicopter gunship|combat helicopter", r"attack|gunship|armed|anti-?\s?tank", r"transport|utility|cargo|trainer",
     ["attack helicopter", "helicopter gunship", "armed reconnaissance helicopter"]),
    (r"helicopter", r"helicopter", r"", ["attack helicopter", "military helicopter"]),
    (r"bomber", r"bomber", r"", ["strategic bomber"]),
    (r"\bdrones?\b|\buavs?\b|unmanned", r"unmanned|uav|drone|loitering", r"", ["unmanned combat aerial vehicle"]),
    (r"stealth", r"stealth|low[- ]observab|fifth[- ]generation|sixth[- ]generation", r"helicopter|trainer",
     ["stealth fighter", "fifth-generation fighter", "stealth multirole fighter"]),
    (r"fighter", r"fighter|multirole|air superiority", r"helicopter|bomber|trainer", ["fighter aircraft", "multirole combat aircraft"]),
    (r"howitzer", r"howitzer", r"", ["self-propelled howitzer"]),
    (r"torpedo", r"torpedo", r"", ["heavyweight torpedo", "lightweight torpedo"]),
]


def subtype_for(topic: str) -> Optional[Tuple[str, str, List[str]]]:
    t = (topic or "").lower()
    for topic_re, must, never, queries in _SUBTYPES:
        if re.search(topic_re, t):
            if "fighter" in t and "bomber" not in t:
                never = f"{never}|bomber" if never else "bomber"  # 'Stealth Fighter Jets' listed the B-21 bomber
            return must, never, queries
    return None


def _is_kind(m: Dict[str, Any], kind: str, kind_re: str, sub: Optional[Tuple[str, str, List[str]]] = None) -> bool:
    """The article's infobox TYPE must say it's this kind of system (the lead text alone let in
    'India and weapons of mass destruction' and 'Virginia-class submarine')."""
    typ = str(m.get("type") or "")
    if not typ or not m.get("image_url") or m["title"].lower().startswith(("list of", "category:")):
        return False
    if not re.search(kind_re, typ, re.I):
        return False
    # Events and incidents are not weapons ("2026 Minab school attack" is typed "missile strike")
    if re.search(r"attack(?!\s+(?:helicopter|aircraft|submarine))|strike(?!\s+fighter)|incident|bombing|massacre|\bbattle\b(?!\s+(?:tank|rifle))|\bwar\b|operation|crisis|crash|shootdown|explosion|test\b", typ, re.I):
        return False
    # A weapon article states where it's from or when it entered service
    if not (m.get("origin") or m.get("year")):
        return False
    ex = _EXCLUDE.get(kind)
    if ex and re.search(ex, typ, re.I):
        return False
    if kind == "firearm" and re.search(r"^\.\d|^\d+(?:\.\d+)?\s?(?:mm\b|×|x\d)|\b(?:ACP|S&W|Parabellum)\s*$|cartridge",
                                       f"{m['title']}|{typ}".split("|")[0] + (" cartridge" if "cartridge" in typ.lower() else ""), re.I):
        return False  # '.45 ACP', '9×19mm Parabellum' are cartridges (their infobox type says 'Pistol'), not guns
    if kind == "vehicle" and re.search(r"anti-?\s?tank|anti-?\s?armou?r", typ, re.I):
        return False  # an anti-tank weapon is not an armoured vehicle
    if sub:
        must, never, _q = sub
        # "stealth" is rarely the infobox type (F-22: 'Air superiority fighter'); the opening sentence says it
        about = f"{typ} {m.get('lead') or ''}" if "stealth" in must else typ
        if not re.search(must, about, re.I) or (never and re.search(never, typ, re.I)):
            return False
    if re.search(r"generation (?:fighter|jet|tank)|^(?:fighter|attack|multirole) aircraft$", m["title"], re.I):
        return False  # a category article ('Fourth-generation fighter'), not a model
    return True


def family_key(title: str) -> str:
    """'Leopard 2E' / 'Leopard 2A4M CAN' / 'Leopard 2' -> 'leopard2'; 'Type 99 tank' -> 'type99';
    'T-90M' -> 't90'; 'M1 Abrams' -> 'm1'. One chart row per family (variants crowded out famous models)."""
    t = re.sub(r"\s*\([^)]*\)", "", title or "").lower()
    m = re.search(r"((?:type\s+)?[a-z]+(?:-[a-z]+)*[\s-]?\d+)", t)
    return re.sub(r"[^a-z0-9]", "", m.group(1) if m else t.split(" ")[0])


def pageviews(titles: List[str], days: int = 90) -> Dict[str, int]:
    """English-Wikipedia views over the last ~3 months per article: how well-known/important a system is
    right now (what editorial 'top' lists rank by). Cached a week; 0 when unknown."""
    import json
    import time as _t
    import urllib.parse
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date, timedelta
    import config
    import requests
    from agents import equipment_catalog as ec
    cf = Path(config.OUTPUT_DIR) / "cache" / "pageviews.json"
    try:
        cache = json.loads(cf.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    end = date.today().replace(day=1) - timedelta(days=1)
    start = (end - timedelta(days=days)).replace(day=1)

    def one(title: str) -> int:
        hit = cache.get(title)
        if hit and _t.time() - hit[1] < 7 * 86400:
            return hit[0]
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
               f"{urllib.parse.quote(title.replace(' ', '_'), safe='')}/monthly/{start:%Y%m%d}00/{end:%Y%m%d}00")
        try:
            r = requests.get(url, headers=ec.HEADERS, timeout=15)
            views = sum(i.get("views", 0) for i in r.json().get("items", [])) if r.status_code == 200 else 0
        except Exception:
            return 0
        cache[title] = [views, _t.time()]
        return views
    with ThreadPoolExecutor(max_workers=6) as pool:
        out = dict(zip(titles, pool.map(one, titles)))
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass
    return out


def fix_top_n(text: str, n: int) -> str:
    """'Top 10 ...' -> 'Top 8 ...' when only 8 models could be verified (a 'Top 10' showing 8 is wrong)."""
    return re.sub(r"(?i)\b(top)(\s+)(\d{1,2})\b", lambda m: f"{m.group(1)}{m.group(2)}{n}" if int(m.group(3)) != n else m.group(0), text or "")


def top_n(topic: str) -> Optional[int]:
    m = re.search(r"\btop\s+(\d{1,2})\b", topic or "", re.I)
    return int(m.group(1)) if m else None


SIDE_PROFILE_KINDS = ("missile", "naval")
MIN_ELONGATION = 4.0  # measured: clean missiles/torpedoes 5-10; launcher tripods, pylons, trucks, crews 1.4-3.9


def _elongation(img) -> float:
    """How long-and-thin the cutout is along its own main axis (rotation-proof, so a diagonal missile counts)."""
    import numpy as np
    small = img.split()[3].resize((max(1, img.width // 2), max(1, img.height // 2)))
    ys, xs = np.nonzero(np.asarray(small) > 40)
    if len(xs) < 20:
        return 0.0
    ev = np.sort(np.linalg.eigvalsh(np.cov(np.vstack([xs, ys]).astype(float))))
    return float(np.sqrt(ev[1] / max(ev[0], 1e-6)))


def _profile_ok(img, kind: str) -> bool:
    """Missiles/torpedoes are drawn as long side profiles (reference look): a cutout that isn't long and
    thin is something else - a launcher on a tripod, a missile under an aircraft pylon, a camouflaged truck."""
    if kind not in SIDE_PROFILE_KINDS:
        return True
    try:
        return _elongation(img) >= MIN_ELONGATION
    except Exception:
        return True


def _with_clean_photos(models: List[Dict[str, Any]], kind: str, max_rows: int, min_rows: int = 5) -> List[Dict[str, Any]]:
    """Keeps (in order) models with a clean photo of the weapon itself, like the reference chart: clean
    side-profile cutouts on white. Framed photos only fill up to the minimum row count when there aren't
    enough cutouts. Models whose photos show people/aircraft/trucks/launchers are skipped (next model in)."""
    import config
    from pathlib import Path
    from agents import evolution_poster as ev
    cache = Path(config.OUTPUT_DIR) / "cache" / "evolution_photos"
    cut_ok, framed_ok = [], []
    for m in models:
        if len(cut_ok) >= max_rows:
            break
        m["_kind"] = kind
        try:
            img, is_cut = ev.fetch_photo(m, cache)
        except Exception:
            img, is_cut = None, False
        if img is None:
            continue
        if is_cut and _profile_ok(img, kind):
            cut_ok.append(m)
        elif not is_cut and ev._exterior_ok(img.convert("RGBA"), kind):
            framed_ok.append(m)
        else:
            print(f"[TopicList] Skipping {m['title']}: no clean side-profile photo of the weapon itself")
    keep = cut_ok[:max_rows] + framed_ok[: max(0, min_rows - len(cut_ok))]
    order = {id(m): i for i, m in enumerate(models)}
    return sorted(keep, key=lambda m: order[id(m)])[:max_rows]


def build_rows(topic: str, min_rows: int = 5, max_rows: int = 8, keep_titles: Optional[List[str]] = None,
               exclude_titles: Optional[List[str]] = None) -> Dict[str, Any]:
    """{'kind', 'rows', 'models'} with only Wikipedia-verified models, or {'error': ...}.
    keep_titles: rows to keep (in this order) when re-building after feedback; exclude_titles: never use."""
    from agents import equipment_catalog as ec
    from agents import ranked_poster as rp
    kind = kind_for(topic)
    n = top_n(topic)
    if n:  # "Top 10 ..." -> 10 rows (a 1080x1920 chart holds at most 10 readable rows)
        max_rows = max(min_rows, min(n, rp.MAX_LIST_ROWS))
        min_rows = min(min_rows, max_rows)
    spec = rp.KINDS.get(kind, rp.KINDS["missile"])
    kind_re, words = spec["kind_re"], spec["words"]
    sub = subtype_for(topic)
    # "most advanced / latest / best" lists mean today's systems too (an APC chart showed a 1943 Kangaroo)
    modern = bool(re.search(r"\bmodern|current|today|new(?:est)?\b|advanced|latest|best|most capable|deadliest|powerful", topic, re.I))
    excluded = {t.lower() for t in (exclude_titles or [])}
    verified: Dict[str, Dict[str, Any]] = {}
    if keep_titles:
        for t, m in ec.fetch_models([k for k in keep_titles if k.lower() not in excluded]).items():
            if m.get("image_url"):
                verified[t] = m

    names = _llm_names(topic)
    # 1) LLM names as exact Wikipedia titles (redirects followed), 2) fuzzy match for the rest
    direct = ec.fetch_models(names) if names else {}
    for m in direct.values():
        if _is_kind(m, kind, kind_re, sub):
            verified.setdefault(m["title"], m)
    matched_names = {m.get("requested_as") for m in direct.values()}
    for name in names:
        if len(verified) >= max_rows + 6 or name in matched_names:
            continue
        m = rp.match_article(name, words, kind)
        if m and _is_kind(m, kind, kind_re, sub):
            verified.setdefault(m["title"], m)

    if len(verified) < max_rows + 6 or sub:  # a specific type: always rank the full pool, not the first hits
        titles = [t for t in _search_titles(topic, kind) if t not in verified]
        for m in (ec.fetch_models(titles) if titles else {}).values():
            if len(verified) >= 250:
                break
            if _is_kind(m, kind, kind_re, sub):
                verified.setdefault(m["title"], m)

    # every row carries a flag + country (reference style); never a row the user rejected
    verified = {t: m for t, m in verified.items() if m.get("origin") and t.lower() not in excluded
                and str(m.get("requested_as", "")).lower() not in excluded}
    kept = [verified[t] for t in (keep_titles or []) if t in verified]
    # Rank like an editorial "top" list: the best-known, most important systems first (Wikipedia
    # readership), one row per family (Leopard 2E / 2A4M CAN were listed instead of Abrams, K2, Merkava)
    views = pageviews([t for t in verified if t not in (keep_titles or [])])
    best: Dict[str, Dict[str, Any]] = {}
    for t, m in verified.items():
        if m in kept:
            continue
        m["_views"] = views.get(t, 0)
        fk = family_key(t)
        if fk in {family_key(k["title"]) for k in kept}:
            continue
        if fk not in best or m["_views"] > best[fk]["_views"]:
            best[fk] = m
    rest = sorted(best.values(), key=lambda m: (-m["_views"], -(m.get("year") or 0)))  # equal fame: newer first
    if (modern or re.search(r"\b20[2-3]\d\b", topic)) and not keep_titles:
        # "Modern ..." / "... 2026": systems from 1980 on; older designs only if nothing newer exists
        # front-line = in service today (Leopard 2 / Merkava entered service in 1979 and still lead),
        # or introduced from 1980 on; retired designs only if nothing else exists
        def current(m):
            st = str(m.get("status") or "").lower()
            if re.search(r"retired|out of service|withdrawn|museum|cancel", st):
                return False
            # many infoboxes have no status: entered service from 1975 on = current generation
            return "in service" in st or "active" in st or (m.get("year") or 0) >= 1975
        recent = [m for m in rest if current(m)]
        rest = recent if len(recent) >= min_rows else recent + [m for m in rest if m not in recent]
    models = kept + rest
    # cancelled prototypes / category pages have no service year: only when there aren't enough real models
    dated = [m for m in models if m.get("year")]
    if len(dated) >= min_rows + 2:
        models = dated + [m for m in models if not m.get("year") and m["title"] in (keep_titles or [])]
    models = _with_clean_photos(models, kind, max_rows)
    if len(models) < min_rows:
        return {"error": f"Only {len(models)} verified models found for '{topic}' (need {min_rows}).", "kind": kind}
    rows = []
    for i, m in enumerate(models, 1):
        b1, b2 = _bullets(m)
        rows.append({"rank": i, "name": re.sub(r"\s*\([^)]*\)\s*$", "", m["title"]).strip(), "query": m["title"],
                     "country": ec._country(m.get("origin") or "") if m.get("origin") else "",
                     "year": shown_year(m), "bullet_1": b1, "bullet_2": b2})
    return {"kind": kind, "rows": rows, "models": models}


def make_poster(topic: str, out_path, cache_dir, keep_titles: Optional[List[str]] = None,
                exclude_titles: Optional[List[str]] = None) -> Dict[str, Any]:
    """Renders the chart from the verified articles directly (re-searching each name could pick a
    different article, e.g. an engine instead of the torpedo)."""
    from agents import ranked_poster as rp
    from agents import evolution_poster as ev
    spec = build_rows(topic, keep_titles=keep_titles, exclude_titles=exclude_titles)
    if spec.get("error"):
        return spec
    title = fix_top_n(re.sub(r"\s+", " ", topic).strip().upper(), len(spec["rows"]))
    items, resolved = [], []
    for r, m in zip(spec["rows"], spec["models"]):
        m["_kind"] = spec["kind"]
        it = {"rank": r["rank"], "name": r["name"], "country": r["country"], "year": str(r["year"] or ""),
              "lookup": m["title"], "specs": {"_bullets": [r["bullet_1"], r["bullet_2"]]}}
        items.append(it)
        resolved.append((it, m))
    parsed = {"title": title, "full_title": title, "items": items, "kind": spec["kind"]}
    res = rp.render(parsed, resolved, out_path, cache_dir)
    if res.get("error"):
        return res
    credits, seen = [], set()
    for c in ev.photo_credits([{"historical": m, "modern": m} for _, m in resolved]):
        if c["file"] not in seen:
            seen.add(c["file"])
            credits.append(c)
    return {**res, "kind": spec["kind"], "title": title, "credits": credits, "items": [
        {"rank": it["rank"], "name": it["name"], "country": it["country"], "year": it["year"], "article": m["title"],
         "photo": m.get("image_file_used") or m.get("image_file"), "bullets": [b for b in it["specs"]["_bullets"] if b]}
        for it, m in resolved]}
