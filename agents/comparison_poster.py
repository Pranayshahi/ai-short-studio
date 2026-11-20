"""
"A vs B vs C" Head-to-Head Comparison Poster Engine (agents/comparison_poster.py)
---------------------------------------------------------------------------------
4. Comparison format: "A vs B vs C" posters with real photos and specs — the proven
WeaponX / AutoFlashX comparison format, modernised for 9:16 YouTube Shorts (1080x1920).

Supports 2-way ("A vs B"), 3-way ("A vs B vs C"), and 4-way ("A vs B vs C vs D")
comparisons for both Automotive/Supercars and Defense/Military hardware using real
Wikipedia/Wikimedia Commons photos, country flags, and verified specifications with
automatic category-winner highlights.
"""
from __future__ import annotations

import io
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

import config
from agents import equipment_catalog as ec
from agents.subject_match import designators, mentions_any

W, H = 1080, 1920

# Curated verified specs for popular cars & defense hardware (supplemented live by Wikipedia infoboxes)
CURATED_SPECS: Dict[str, Dict[str, Any]] = {
    "porsche 911 gt3 rs": {
        "name": "Porsche 911 GT3 RS", "year": "2023", "country": "Germany", "kind": "car",
        "wiki": "Porsche 911 GT3",
        "engine": "4.0L Flat-6 NA", "power": "518 HP", "power_num": 518,
        "speed": "296 km/h (184 mph)", "speed_num": 296,
        "accel": "3.2s (0-100) · RWD", "accel_num": 3.2,
    },
    "ferrari f80": {
        "name": "Ferrari F80", "year": "2025", "country": "Italy", "kind": "car",
        "wiki": "Ferrari F80",
        "engine": "3.0L TT V6 Hybrid", "power": "1,184 HP", "power_num": 1184,
        "speed": "350 km/h (217 mph)", "speed_num": 350,
        "accel": "2.15s (0-100) · AWD", "accel_num": 2.15,
    },
    "ferrari sf90": {
        "name": "Ferrari SF90 Stradale", "year": "2020", "country": "Italy", "kind": "car",
        "wiki": "Ferrari SF90 Stradale",
        "engine": "4.0L TT V8 Hybrid", "power": "986 HP", "power_num": 986,
        "speed": "340 km/h (211 mph)", "speed_num": 340,
        "accel": "2.5s (0-100) · AWD", "accel_num": 2.5,
    },
    "lamborghini revuelto": {
        "name": "Lamborghini Revuelto", "year": "2024", "country": "Italy", "kind": "car",
        "wiki": "Lamborghini Revuelto",
        "engine": "6.5L V12 Hybrid", "power": "1,001 HP", "power_num": 1001,
        "speed": "350 km/h (217 mph)", "speed_num": 350,
        "accel": "2.5s (0-100) · AWD", "accel_num": 2.5,
    },
    "lamborghini huracan": {
        "name": "Lamborghini Huracán STO", "year": "2021", "country": "Italy", "kind": "car",
        "wiki": "Lamborghini Huracán",
        "engine": "5.2L V10 NA", "power": "631 HP", "power_num": 631,
        "speed": "310 km/h (193 mph)", "speed_num": 310,
        "accel": "3.0s (0-100) · RWD", "accel_num": 3.0,
    },
    "bugatti tourbillon": {
        "name": "Bugatti Tourbillon", "year": "2026", "country": "France", "kind": "car",
        "wiki": "Bugatti Tourbillon",
        "engine": "8.3L V16 Hybrid", "power": "1,800 HP", "power_num": 1800,
        "speed": "445 km/h (277 mph)", "speed_num": 445,
        "accel": "2.0s (0-100) · AWD", "accel_num": 2.0,
    },
    "bugatti chiron": {
        "name": "Bugatti Chiron Super Sport", "year": "2021", "country": "France", "kind": "car",
        "wiki": "Bugatti Chiron",
        "engine": "8.0L Quad-Turbo W16", "power": "1,578 HP", "power_num": 1578,
        "speed": "440 km/h (273 mph)", "speed_num": 440,
        "accel": "2.4s (0-100) · AWD", "accel_num": 2.4,
    },
    "koenigsegg jesko": {
        "name": "Koenigsegg Jesko Absolut", "year": "2023", "country": "Sweden", "kind": "car",
        "wiki": "Koenigsegg Jesko",
        "engine": "5.0L Twin-Turbo V8", "power": "1,600 HP", "power_num": 1600,
        "speed": "500+ km/h (310 mph)", "speed_num": 500,
        "accel": "2.5s (0-100) · RWD", "accel_num": 2.5,
    },
    "rimac nevera": {
        "name": "Rimac Nevera", "year": "2022", "country": "Croatia", "kind": "car",
        "wiki": "Rimac Nevera",
        "engine": "Quad-Motor Electric", "power": "1,914 HP", "power_num": 1914,
        "speed": "412 km/h (256 mph)", "speed_num": 412,
        "accel": "1.81s (0-100) · AWD", "accel_num": 1.81,
    },
    "mclaren p1": {
        "name": "McLaren P1", "year": "2013", "country": "United Kingdom", "kind": "car",
        "wiki": "McLaren P1",
        "engine": "3.8L TT V8 Hybrid", "power": "903 HP", "power_num": 903,
        "speed": "350 km/h (217 mph)", "speed_num": 350,
        "accel": "2.8s (0-100) · RWD", "accel_num": 2.8,
    },
    "mclaren 765lt": {
        "name": "McLaren 765LT", "year": "2020", "country": "United Kingdom", "kind": "car",
        "wiki": "McLaren 720S",
        "engine": "4.0L Twin-Turbo V8", "power": "755 HP", "power_num": 755,
        "speed": "330 km/h (205 mph)", "speed_num": 330,
        "accel": "2.8s (0-100) · RWD", "accel_num": 2.8,
    },
    "nissan gt-r r34": {
        "name": "Nissan Skyline GT-R R34", "year": "1999", "country": "Japan", "kind": "car",
        "wiki": "Nissan Skyline GT-R",
        "engine": "2.6L RB26DETT TT I6", "power": "276+ HP (Tuned 600+)", "power_num": 320,
        "speed": "250 km/h (155 mph)", "speed_num": 250,
        "accel": "4.8s (0-100) · AWD", "accel_num": 4.8,
    },
    "skyline gt-r": {
        "name": "Nissan Skyline GT-R R34", "year": "1999", "country": "Japan", "kind": "car",
        "wiki": "Nissan Skyline GT-R",
        "engine": "2.6L RB26DETT TT I6", "power": "276+ HP", "power_num": 320,
        "speed": "250 km/h (155 mph)", "speed_num": 250,
        "accel": "4.8s (0-100) · AWD", "accel_num": 4.8,
    },
    "gt-r r34": {
        "name": "Nissan Skyline GT-R R34", "year": "1999", "country": "Japan", "kind": "car",
        "wiki": "Nissan Skyline GT-R",
        "engine": "2.6L RB26DETT TT I6", "power": "276+ HP", "power_num": 320,
        "speed": "250 km/h (155 mph)", "speed_num": 250,
        "accel": "4.8s (0-100) · AWD", "accel_num": 4.8,
    },
    "nissan gt-r": {
        "name": "Nissan GT-R NISMO (R35)", "year": "2020", "country": "Japan", "kind": "car",
        "wiki": "Nissan GT-R",
        "engine": "3.8L VR38DETT TT V6", "power": "600 HP", "power_num": 600,
        "speed": "315 km/h (196 mph)", "speed_num": 315,
        "accel": "2.7s (0-100) · AWD", "accel_num": 2.7,
    },
    "toyota supra": {
        "name": "Toyota Supra MK4 (A80)", "year": "1993", "country": "Japan", "kind": "car",
        "wiki": "Toyota Supra",
        "engine": "3.0L 2JZ-GTE TT I6", "power": "320 HP", "power_num": 320,
        "speed": "250 km/h (155 mph)", "speed_num": 250,
        "accel": "4.6s (0-100) · RWD", "accel_num": 4.6,
    },
    "supra mk4": {
        "name": "Toyota Supra MK4 (A80)", "year": "1993", "country": "Japan", "kind": "car",
        "wiki": "Toyota Supra",
        "engine": "3.0L 2JZ-GTE TT I6", "power": "320 HP", "power_num": 320,
        "speed": "250 km/h (155 mph)", "speed_num": 250,
        "accel": "4.6s (0-100) · RWD", "accel_num": 4.6,
    },
    "mazda rx-7": {
        "name": "Mazda RX-7 FD3S", "year": "1992", "country": "Japan", "kind": "car",
        "wiki": "Mazda RX-7",
        "engine": "1.3L 13B-REW Twin-Rotor", "power": "276 HP", "power_num": 276,
        "speed": "250 km/h (155 mph)", "speed_num": 250,
        "accel": "5.1s (0-100) · RWD", "accel_num": 5.1,
    },
    "rx-7": {
        "name": "Mazda RX-7 FD3S", "year": "1992", "country": "Japan", "kind": "car",
        "wiki": "Mazda RX-7",
        "engine": "1.3L 13B-REW Twin-Rotor", "power": "276 HP", "power_num": 276,
        "speed": "250 km/h (155 mph)", "speed_num": 250,
        "accel": "5.1s (0-100) · RWD", "accel_num": 5.1,
    },
    "bmw m4": {
        "name": "BMW M4 Competition (G82)", "year": "2021", "country": "Germany", "kind": "car",
        "wiki": "BMW M4",
        "engine": "3.0L S58 Twin-Turbo I6", "power": "503 HP", "power_num": 503,
        "speed": "290 km/h (180 mph)", "speed_num": 290,
        "accel": "3.5s (0-100) · AWD", "accel_num": 3.5,
    },
    "mercedes amg gt": {
        "name": "Mercedes-AMG GT Black Series", "year": "2021", "country": "Germany", "kind": "car",
        "wiki": "Mercedes-AMG GT",
        "engine": "4.0L Flat-Plane TT V8", "power": "720 HP", "power_num": 720,
        "speed": "325 km/h (202 mph)", "speed_num": 325,
        "accel": "3.2s (0-100) · RWD", "accel_num": 3.2,
    },
    "audi r8": {
        "name": "Audi R8 V10 Performance", "year": "2019", "country": "Germany", "kind": "car",
        "wiki": "Audi R8",
        "engine": "5.2L Naturally Aspirated V10", "power": "612 HP", "power_num": 612,
        "speed": "331 km/h (205 mph)", "speed_num": 331,
        "accel": "3.1s (0-100) · AWD", "accel_num": 3.1,
    },
    "corvette zr1": {
        "name": "Chevrolet Corvette ZR1 (C8)", "year": "2025", "country": "United States", "kind": "car",
        "wiki": "Chevrolet Corvette (C8)",
        "engine": "5.5L LT7 Twin-Turbo V8", "power": "1,064 HP", "power_num": 1064,
        "speed": "375 km/h (233 mph)", "speed_num": 375,
        "accel": "2.3s (0-100) · RWD", "accel_num": 2.3,
    },
    "f-22": {
        "name": "F-22 Raptor", "year": "2005", "country": "United States", "kind": "defense",
        "wiki": "Lockheed Martin F-22 Raptor",
        "engine": "2x P&W F119 Turbofans", "power": "70,000 lbf Thrust", "power_num": 70000,
        "speed": "Mach 2.25 (2,414 km/h)", "speed_num": 2414,
        "accel": "20mm M61A2 + 8x AAMs", "accel_num": None,
    },
    "su-57": {
        "name": "Sukhoi Su-57 Felon", "year": "2020", "country": "Russia", "kind": "defense",
        "wiki": "Sukhoi Su-57",
        "engine": "2x Saturn AL-41F1", "power": "64,000 lbf Thrust", "power_num": 64000,
        "speed": "Mach 2.0 (2,135 km/h)", "speed_num": 2135,
        "accel": "30mm GSh-30-1 + R-77M", "accel_num": None,
    },
    "j-20": {
        "name": "Chengdu J-20 Mighty Dragon", "year": "2017", "country": "China", "kind": "defense",
        "wiki": "Chengdu J-20",
        "engine": "2x Shenyang WS-15", "power": "72,000 lbf Thrust", "power_num": 72000,
        "speed": "Mach 2.0 (2,100 km/h)", "speed_num": 2100,
        "accel": "PL-15 Long-Range AAMs", "accel_num": None,
    },
}


def is_comparison_prompt(text: str) -> bool:
    """True when text is an 'A vs B' or 'A vs B vs C' head-to-head comparison."""
    if not text:
        return False
    first_line = (text.strip().splitlines() or [""])[0].strip()
    if len(first_line) > 160:
        return False
    parts = re.split(r"\s+(?:vs\.?|versus)\s+", first_line, flags=re.I)
    return 2 <= len(parts) <= 4 and all(2 <= len(p.strip()) <= 55 for p in parts)


def parse_comparison_prompt(text: str) -> Dict[str, Any]:
    """Splits 'A vs B vs C' into contender names and builds a clean poster headline."""
    first_line = (text.strip().splitlines() or [""])[0].strip()
    first_line = re.sub(r"^(?:compare|comparison\s*:?)\s+", "", first_line, flags=re.I)
    raw_parts = re.split(r"\s+(?:vs\.?|versus)\s+", first_line, flags=re.I)
    items = [re.sub(r"\s+", " ", p).strip(" -–—:;,") for p in raw_parts if p.strip()]
    items = items[:4]
    title = " VS ".join(i.upper() for i in items)
    return {
        "title": title,
        "contender_names": items,
        "count": len(items),
    }


def _lookup_curated(name: str) -> Optional[Dict[str, Any]]:
    low = name.lower().strip()
    for k, spec in CURATED_SPECS.items():
        if k in low or low in k:
            return dict(spec)
    return None


def _search_wiki_model(name: str, wiki_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    queries = [wiki_hint] if wiki_hint else []
    queries += [name, f"{name} car", f"{name} automobile"]
    found: List[str] = []
    for q in dict.fromkeys(x for x in queries if x):
        data = ec._get({"action": "query", "list": "search", "srsearch": q, "srlimit": 5})
        for h in (data or {}).get("query", {}).get("search", []):
            t = h.get("title", "")
            if t and not t.lower().startswith("list of") and t not in found:
                found.append(t)
        if found:
            break
    if not found:
        return None
    models = ec.fetch_models(found[:5])
    for t in found[:5]:
        m = models.get(t)
        if m and m.get("image_url"):
            return m
    return None


def resolve_contender(name: str, cache_dir: Path) -> Dict[str, Any]:
    """Resolves a contender's specs, Wikipedia article + real photo, and country flag."""
    from agents import evolution_poster as ev
    curated = _lookup_curated(name)
    wiki_model = _search_wiki_model(name, wiki_hint=(curated or {}).get("wiki"))

    if curated:
        spec = dict(curated)
    else:
        lead = (wiki_model or {}).get("lead", "")
        hp_m = re.search(r"\b(\d{3,4})\s*(?:hp|bhp|PS|horsepower)\b", lead, re.I)
        spd_m = re.search(r"\b(\d{3})\s*km/h\b", lead, re.I)
        eng_m = re.search(r"\b(\d\.\d\s*L\s*(?:V\d+|I\d+|Flat-\d+|W\d+)?|V\d+|W16|Flat-6|Inline-6|Electric)\b", lead, re.I)
        hp_val = int(hp_m.group(1)) if hp_m else None
        spd_val = int(spd_m.group(1)) if spd_m else None
        spec = {
            "name": ev.display_name(wiki_model) if wiki_model else name.strip(),
            "year": str((wiki_model or {}).get("year") or "2024"),
            "country": (wiki_model or {}).get("origin") or "International",
            "kind": "car",
            "engine": eng_m.group(1).upper() if eng_m else "High-Output Powertrain",
            "power": f"{hp_val} HP" if hp_val else (f"{wiki_model['calibre_mm']} mm gun" if (wiki_model or {}).get("calibre_mm") else " Factory Spec"),
            "power_num": hp_val,
            "speed": f"{spd_val} km/h" if spd_val else "Track / Combat Rated",
            "speed_num": spd_val,
            "accel": f"{wiki_model['weight_t']} t" if (wiki_model or {}).get("weight_t") else "Performance Spec",
            "accel_num": None,
        }

    if wiki_model:
        spec["model"] = wiki_model
        spec["article"] = wiki_model.get("title", spec["name"])
    else:
        spec["model"] = None
        spec["article"] = spec["name"]
    return spec


def _mark_winners(contenders: List[Dict[str, Any]]) -> Dict[str, str]:
    """Marks the best power, top speed, and 0-100 acceleration across contenders."""
    winners: Dict[str, str] = {}
    powers = [(i, c.get("power_num")) for i, c in enumerate(contenders) if c.get("power_num")]
    if len(powers) >= 2:
        best_p = max(p for _, p in powers)
        for i, p in powers:
            if p == best_p:
                contenders[i]["win_power"] = True
                winners["power"] = contenders[i]["name"]

    speeds = [(i, c.get("speed_num")) for i, c in enumerate(contenders) if c.get("speed_num")]
    if len(speeds) >= 2:
        best_s = max(s for _, s in speeds)
        for i, s in speeds:
            if s == best_s:
                contenders[i]["win_speed"] = True
                winners["speed"] = contenders[i]["name"]

    accels = [(i, c.get("accel_num")) for i, c in enumerate(contenders) if c.get("accel_num")]
    if len(accels) >= 2:
        best_a = min(a for _, a in accels)  # lower 0-100s is quicker
        for i, a in accels:
            if a == best_a:
                contenders[i]["win_accel"] = True
                winners["accel"] = contenders[i]["name"]
    return winners


def render(parsed: Dict[str, Any], contenders: List[Dict[str, Any]], out_path: Path, cache_dir: Path) -> Dict[str, Any]:
    from PIL import Image, ImageDraw
    from agents import evolution_poster as ev
    from agents import ranked_poster as rp

    winners = _mark_winners(contenders)
    canvas = Image.new("RGBA", (W, H), (248, 250, 252, 255))
    d = ImageDraw.Draw(canvas)

    # 1. Top Header Bar (Dark Carbon Rounded Header with "HEAD-TO-HEAD COMPARISON" + A VS B VS C)
    d.rounded_rectangle((18, 16, W - 18, 152), radius=24, fill=(11, 15, 25, 255), outline=(0, 229, 255, 220), width=3)
    f_sub = ev._font("Arial Bold.ttf", 22)
    d.text((W // 2, 46), "⚡ HEAD-TO-HEAD SPEC & PHOTO COMPARISON ⚡", font=f_sub, fill=(0, 229, 255), anchor="mm")

    title = parsed["title"]
    f_title = ev._font("Impact.ttf", 52)
    while d.textlength(title, font=f_title) > W - 84 and f_title.size > 26:
        f_title = ev._font("Impact.ttf", f_title.size - 2)
    d.text((W // 2, 106), title, font=f_title, fill=(255, 255, 255), anchor="mm")

    # 2. Stacked Contender Cards
    n = len(contenders)
    top0 = 172
    bottom_footer_h = 128
    avail_h = H - top0 - bottom_footer_h - 18
    gap = 22
    card_h = (avail_h - gap * (n - 1)) // n

    f_badge = ev._font("Impact.ttf", 30)
    f_name = ev._font("Arial Bold.ttf", 34 if n <= 3 else 28)
    f_meta = ev._font("Arial Bold.ttf", 21)
    f_lbl = ev._font("Arial Bold.ttf", 17)
    f_val = ev._font("Arial Bold.ttf", 22 if n <= 3 else 19)
    f_win = ev._font("Arial Bold.ttf", 15)
    f_vs = ev._font("Impact.ttf", 28)

    placed_photos = 0
    letters = ["A", "B", "C", "D"]

    for idx, c in enumerate(contenders):
        cy0 = top0 + idx * (card_h + gap)
        cy1 = cy0 + card_h

        # Card container with crisp border
        d.rounded_rectangle((22, cy0, W - 22, cy1), radius=20, fill=(255, 255, 255, 255), outline=(203, 213, 225, 255), width=3)
        # Left accent stripe
        stripe_col = [(225, 29, 72), (14, 165, 233), (245, 158, 11), (16, 185, 129)][idx % 4]
        d.rounded_rectangle((22, cy0, 36, cy1), radius=8, fill=(*stripe_col, 255))

        # Top row inside card: Letter Badge + Flag + Model Name + (Year) + Country
        bx = 52
        by = cy0 + 16
        d.rounded_rectangle((bx, by, bx + 44, by + 44), radius=10, fill=(*stripe_col, 255))
        d.text((bx + 22, by + 22), letters[idx], font=f_badge, fill=(255, 255, 255), anchor="mm")

        nx = bx + 58
        fl = rp.flag_image(c.get("country", ""), cache_dir, height=34)
        if fl is not None:
            canvas.alpha_composite(fl, (nx, by + 5))
            nx += fl.width + 12

        disp_name = f"{c['name']} ({c.get('year', '')})" if c.get("year") else c["name"]
        d.text((nx, by + 4), disp_name, font=f_name, fill=(15, 23, 42))
        d.text((nx, by + 42), str(c.get("country", "")).upper(), font=f_meta, fill=(100, 116, 139))

        # Photo Area (Left half of card below header)
        photo_top = by + 72
        photo_h = max(120, cy1 - photo_top - 16)
        photo_w = 500
        photo_cx = 48 + photo_w // 2
        photo_cy = photo_top + photo_h // 2

        model = c.get("model")
        if model is not None:
            img, is_cut = ev.fetch_photo(model, cache_dir)
            if img is not None:
                ev._paste_item(canvas, img, is_cut, photo_cx, photo_cy, photo_w - 16, photo_h - 12)
                placed_photos += 1

        # Right Column: 4 Modern Spec Rows with Winner Highlights
        spec_rows = [
            ("POWERTRAIN / ENGINE", c.get("engine", "—"), False),
            ("HORSEPOWER / OUTPUT", c.get("power", "—"), bool(c.get("win_power"))),
            ("TOP SPEED", c.get("speed", "—"), bool(c.get("win_speed"))),
            ("0-100 KM/H · DRIVE", c.get("accel", "—"), bool(c.get("win_accel"))),
        ]
        sx0 = 568
        sx1 = W - 40
        row_band_h = max(52, (cy1 - photo_top - 14) // 4)

        for r_idx, (lbl, val, is_win) in enumerate(spec_rows):
            ry0 = photo_top + r_idx * row_band_h
            ry1 = ry0 + row_band_h - 6
            bg_fill = (236, 253, 245, 255) if is_win else (241, 245, 249, 255)
            bd_fill = (16, 185, 129, 255) if is_win else (226, 232, 240, 255)
            d.rounded_rectangle((sx0, ry0, sx1, ry1), radius=10, fill=bg_fill, outline=bd_fill, width=2 if is_win else 1)
            d.text((sx0 + 14, ry0 + 8), lbl, font=f_lbl, fill=(100, 116, 139))
            d.text((sx0 + 14, ry0 + 28), str(val)[:28], font=f_val, fill=(6, 95, 70) if is_win else (15, 23, 42))
            if is_win:
                d.rounded_rectangle((sx1 - 88, ry0 + 10, sx1 - 10, ry0 + 36), radius=8, fill=(16, 185, 129, 255))
                d.text((sx1 - 49, ry0 + 23), "★ BEST", font=f_win, fill=(255, 255, 255), anchor="mm")

        # Draw circular "VS" badge between cards
        if idx < n - 1:
            vs_y = cy1 + gap // 2
            d.ellipse((W // 2 - 30, vs_y - 30, W // 2 + 30, vs_y + 30), fill=(225, 29, 72, 255), outline=(255, 255, 255, 255), width=4)
            d.text((W // 2, vs_y), "VS", font=f_vs, fill=(255, 255, 255), anchor="mm")

    # 3. Bottom Summary Winner Bar
    fy0 = H - bottom_footer_h
    d.rounded_rectangle((18, fy0, W - 18, H - 16), radius=20, fill=(11, 15, 25, 255), outline=(245, 158, 11, 220), width=2)
    f_foot_hdr = ev._font("Arial Bold.ttf", 20)
    f_foot_val = ev._font("Arial Bold.ttf", 22)
    d.text((W // 2, fy0 + 26), "🏆 CATEGORY WINNERS SUMMARY 🏆", font=f_foot_hdr, fill=(251, 191, 36), anchor="mm")

    summary_parts = []
    if winners.get("power"):
        summary_parts.append(f"⚡ Power: {winners['power']}")
    if winners.get("speed"):
        summary_parts.append(f"🚀 Speed: {winners['speed']}")
    if winners.get("accel"):
        summary_parts.append(f"🏁 0-100: {winners['accel']}")
    summary_line = "   ·   ".join(summary_parts) if summary_parts else "Comment your winner below! 👇"
    d.text((W // 2, fy0 + 70), summary_line[:68], font=f_foot_val, fill=(255, 255, 255), anchor="mm")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "PNG")
    return {
        "path": str(out_path),
        "rows": len(contenders),
        "photos": placed_photos,
        "winners": winners,
    }


def make_poster(text: str, out_path: Path, cache_dir: Path) -> Dict[str, Any]:
    from agents import evolution_poster as ev
    parsed = parse_comparison_prompt(text)
    if len(parsed["contender_names"]) < 2:
        return {"error": "Comparison requires 2 to 4 contenders separated by 'vs'."}
    contenders = [resolve_contender(name, cache_dir) for name in parsed["contender_names"]]
    res = render(parsed, contenders, out_path, cache_dir)
    models_with_photos = [c["model"] for c in contenders if c.get("model")]
    credits = ev.photo_credits([{"historical": m, "modern": m} for m in models_with_photos]) if models_with_photos else []
    seen, uniq = set(), []
    for c in credits:
        if c["file"] not in seen:
            seen.add(c["file"])
            uniq.append(c)
    return {
        **res,
        "title": parsed["title"],
        "comparison_items": [
            {
                "name": c["name"],
                "country": c.get("country", ""),
                "year": c.get("year", ""),
                "engine": c.get("engine", ""),
                "power": c.get("power", ""),
                "speed": c.get("speed", ""),
                "accel": c.get("accel", ""),
            }
            for c in contenders
        ],
        "credits": uniq,
    }
