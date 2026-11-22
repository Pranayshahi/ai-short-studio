"""
Car specs database for end cards and title overlays (e.g. "4.0L TWIN-TURBO V8 · 907 PS").

Order: the curated list in CarEditAgent.KNOWN_CAR_SPECS -> this lookup -> the generic line.
Lookup: the car's Wikipedia article (the title must contain the model's designator: "McLaren 750S" must
not use the 720S article), engine from the infobox, power from the article's opening section. Nothing is
invented: missing data stays missing. Results are cached (output/cache/car_specs.json); you can pin your
own values in assets/data/car_specs_overrides.json ({"mclaren 750s": {"spec": "4.0L TWIN-TURBO V8 · 750 PS"}}).
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Dict, Optional

import config

OVERRIDES = Path(config.BASE_DIR) / "assets" / "data" / "car_specs_overrides.json"


def _cache_file() -> Path:
    d = Path(config.OUTPUT_DIR) / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / "car_specs.json"


def _read(path: Path) -> Dict[str, Dict[str, str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compact_engine(text: str, hybrid: bool = False) -> str:
    """'4.0 L L411 twin-turbocharged V8' -> '4.0L TWIN-TURBO V8'; '2992 cc ... twin-turbo V6' -> '3.0L TWIN-TURBO V6'."""
    t = html.unescape(text or "")
    vol = None
    m = re.search(r"(\d\.\d)\s*(?:L|litre|liter)\b", t, re.I)
    if m:
        vol = f"{m.group(1)}L"
    else:
        m = re.search(r"(\d{3,4})\s*cc\b", t, re.I)
        if m:
            vol = f"{int(m.group(1)) / 1000:.1f}L"
    ind = ("TWIN-TURBO" if re.search(r"twin[- ]turbo|bi[- ]?turbo", t, re.I) else
           "QUAD-TURBO" if re.search(r"quad[- ]turbo", t, re.I) else
           "SUPERCHARGED" if re.search(r"supercharg", t, re.I) else
           "TURBO" if re.search(r"turbo", t, re.I) else
           "NA" if re.search(r"naturally aspirated", t, re.I) else "")
    lay = re.search(r"\b(V\d{1,2}|W1[26]|flat[- ]\d{1,2}|straight[- ]\d|inline[- ]\d|I\d)\b", t, re.I)
    layout = lay.group(1).upper().replace(" ", "-") if lay else ""
    parts = [p for p in (vol, ind, layout) if p]
    if len(parts) < 2:
        return ""
    return " ".join(parts) + (" HYBRID" if hybrid else "")


def power_from_text(text: str) -> str:
    """First stated output in the text: '907 PS', '740 hp' (kW converted to hp)."""
    t = html.unescape(text or "")
    for m in re.finditer(r"(\d{1,2},\d{3}|\d{3,4})\s*(PS|hp|bhp|kW|cv)\b", t, re.I):
        val = int(m.group(1).replace(",", ""))
        unit = m.group(2).lower()
        if unit == "kw" and _CHARGING.search(t[max(0, m.start() - 60):m.end() + 40]):
            continue  # "DC fast charging up to 400 kW" is the charger, not the motor (was shown as 536 HP)
        if unit == "kw":
            val, unit = round(val * 1.341), "hp"
        if 150 <= val <= 2500:
            return f"{val:,} {'PS' if unit in ('ps', 'cv') else 'HP'}"
    return ""


_CHARGING = re.compile(r"charg|\bDC\b|\bAC\b|wallbox|plug", re.I)


def power_for_variant(field: str, name: str) -> str:
    """Infobox power for the requested version. Fields like '335 hp (i3 40L) | 463 hp (i3 50 xDrive) |
    603 hp (i3 60 xDrive M Performance)' list every trim: pick the one the car name names; with no trim
    named, the top output as 'UP TO 603 HP' (never one trim's number presented as the whole range)."""
    entries = []
    for part in re.split(r"\s*\|\s*|<br\s*/?>|\n", field or ""):
        pw = power_from_text(part)
        if pw:
            # hybrids list engine / motor / total: the total is the car's output
            # ("Total output: 1001 hp", "Combined: 1200 PS"; not "Electric motor (combined): 187 hp")
            if re.match(r"\s*(?:\{\{ubl\s*)?(total|combined|system)\b", part, re.I):
                return pw
            label = " ".join(re.findall(r"\(([^)]*)\)", part))
            entries.append((pw, label))
    if len(entries) <= 1 or sum(1 for _, lb in entries if lb) < 2:
        return entries[0][0] if entries else ""  # not a list of trims: first stated output (as before)
    want = set(re.findall(r"[a-z0-9]+", (name or "").lower()))
    scored = []
    for pw, label in entries:
        toks = set(re.findall(r"[a-z0-9]+", label.lower()))
        # trim words beyond the shared model name decide it ("50", "xdrive"); a different trim number loses
        extra = toks - want
        hit = len(toks & want) - 2 * len({t for t in extra if t.isdigit()})
        scored.append((hit, pw, label))
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]
    named = [t for t in want if t.isdigit() or t in ("xdrive", "quattro", "4matic", "awd", "rwd")]
    if best[0] > 0 and named and (len(scored) == 1 or best[0] > scored[1][0] or best[1] == scored[1][1]):
        return best[1]
    top = max(entries, key=lambda e: int(re.sub(r"\D", "", e[0]) or 0))[0]
    return f"UP TO {top}"


def lookup_car(name: str) -> Optional[Dict[str, str]]:
    key = re.sub(r"\s+", " ", (name or "").strip().lower())
    if not key:
        return None
    pinned = _read(OVERRIDES).get(key)
    if pinned:
        return pinned
    cache = _read(_cache_file())
    if key in cache:
        return cache[key] or None
    spec = _lookup_wikipedia(name)
    cache[key] = spec or {}
    _cache_file().write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return spec


def _lookup_wikipedia(name: str) -> Optional[Dict[str, str]]:
    from agents import equipment_catalog as ec
    from agents.subject_match import designators
    try:
        d = ec._get({"action": "query", "list": "search", "srsearch": name, "srlimit": 5}) or {}
        titles = [h["title"] for h in d.get("query", {}).get("search", [])]
    except Exception:
        return None
    desig = [x.lower() for x in designators(name)]
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", name) if len(w) > 1]
    for title in titles[:3]:
        tl = title.lower()
        # the article must be about THIS model (designator in the title), not a sibling (720S for 750S)
        if desig and not all(x in re.sub(r"[^a-z0-9]", "", tl) for x in (re.sub(r"[^a-z0-9]", "", x) for x in desig)):
            continue
        if not desig and not all(w in tl for w in words[:2]):
            continue
        w = ec._get({"action": "query", "titles": title, "prop": "revisions", "rvprop": "content", "rvslots": "main",
                     "rvsection": 0, "redirects": 1}) or {}
        pages = w.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            continue
        wt = pages[0]["revisions"][0]["slots"]["main"]["content"]
        fb = ec._infobox(wt)
        body = ec._clean(re.sub(r"\{\{\s*Infobox.*?\n\}\}", "", wt, flags=re.S | re.I))
        hybrid = bool(re.search(r"\bhybrid\b", f"{fb.get('engine', '')} {fb.get('electric_motor', '')} {body[:1500]}", re.I))
        engine = compact_engine(ec._clean(fb.get("engine", "")), hybrid)
        pfield = ec._clean(fb.get("power", "") or fb.get("max_power", "") or fb.get("powerout", "")
                           or fb.get("power_output", ""))
        power = power_for_variant(pfield, name) or power_from_text(body[:3000])
        parts = [p for p in (engine, power) if p]
        if parts:
            return {"spec": " · ".join(parts), "engine": engine, "power": power, "source": f"Wikipedia: {pages[0]['title']}"}
    return None
