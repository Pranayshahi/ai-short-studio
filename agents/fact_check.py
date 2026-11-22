"""
Fact check for every video (owner's rule, 2026-11-21: "exact content and correct content must be given",
otherwise leave it out). Published mistakes that this exists for:
  - 'T-14 Armata - Range 5 km' on a chart (the gun's range; the tank's is 500 km);
  - 'The species has a prominent and simple nose-leaf.' in the Ghost Bat (MQ-28 drone) video: the
    research mixed in Wikipedia's article on the ghost bat ANIMAL.

What is checked:
  1. sources   - every research article must be about the right kind of thing (an animal / person / place /
                 film article is never a source for a weapon or car video): off_domain().
  2. sentences - every narration / caption sentence must be on-topic, and every number in it must appear
                 in the on-topic sources (unit conversions allowed). filter_script() removes failing
                 sentences BEFORE the voice-over is made; check_project() reports anything left.
  3. charts    - every row's numbers are re-verified against the model's Wikipedia article
                 (topic_weapon_list.checked_specs), no future years, 'Top N' == rows shown.
  4. car spec  - the spec line's numbers (HP, litres, RPM...) must be in the car's sources.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

# A short description / opening sentence that says the article is about something that is not a machine
OFF_DOMAIN = re.compile(
    r"\b(?:species|genus|subspecies|family of (?:bats|birds|plants|insects|fish|snakes)|a (?:bat|bird|mammal|fish|insect|"
    r"plant|reptile|snake|frog|spider|beetle|moth|butterfly|shark|whale|dog|cat|horse) (?:species|native|found)|"
    r"(?:village|town|city|municipality|commune|river|mountain|lake|island|county|district) in|"
    r"footballer|cricketer|basketball player|singer|rapper|actor|actress|politician|album by|song by|single by|"
    r"(?:\d{4} )?(?:film|novel|video game|television series|tv series|comic|manga|anime|band|wrestler)\b)",
    re.I)

_STOP = set("""a an the and or of to in on for with by from at as is are was were be been this that these those it its
into over under than then them they their there here which who what when where while also can could will would
has have had not no nor but so such more most very just about after before between during per each other only""".split())

# unit -> (family, factor to the family's base unit). Numbers are only compared within one family.
_UNITS = {
    "km": ("len", 1), "kilometre": ("len", 1), "kilometres": ("len", 1), "kilometer": ("len", 1), "kilometers": ("len", 1),
    "mi": ("len", 1.609), "mile": ("len", 1.609), "miles": ("len", 1.609), "nmi": ("len", 1.852), "m": ("len", 0.001),
    "metre": ("len", 0.001), "metres": ("len", 0.001), "meter": ("len", 0.001), "meters": ("len", 0.001), "ft": ("len", 0.0003048),
    "km/h": ("spd", 1), "kph": ("spd", 1), "mph": ("spd", 1.609), "knots": ("spd", 1.852), "knot": ("spd", 1.852),
    "kn": ("spd", 1.852), "kt": ("spd", 1.852), "m/s": ("spd", 3.6),
    "t": ("mass", 1), "tonne": ("mass", 1), "tonnes": ("mass", 1), "ton": ("mass", 1), "tons": ("mass", 1),
    "kg": ("mass", 0.001), "lb": ("mass", 0.0004536),
    "hp": ("pow", 1), "bhp": ("pow", 1), "ps": ("pow", 0.9863), "cv": ("pow", 0.9863), "kw": ("pow", 1.341),
    "l": ("vol", 1), "litre": ("vol", 1), "litres": ("vol", 1), "liter": ("vol", 1), "liters": ("vol", 1), "cc": ("vol", 0.001),
    "mm": ("cal", 1), "cm": ("cal", 10), "in": ("cal", 25.4),
    "rpm": ("rpm", 1), "rounds/min": ("rof", 1), "%": ("pct", 1), "nm": ("torque", 1), "lb-ft": ("torque", 1.356),
}
_UNIT_RE = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))
_NUM = re.compile(rf"(?<![\w.])(\d{{1,3}}(?:,\d{{3}})+|\d+(?:\.\d+)?)\s*(million|billion|thousand|lakh|crore)?\s*-?\s*(?:({_UNIT_RE})(?![a-z]))?", re.I)
_MACH = re.compile(r"mach\s*(\d+(?:\.\d+)?)", re.I)
_MULT = {"thousand": 1e3, "lakh": 1e5, "million": 1e6, "crore": 1e7, "billion": 1e9}


def off_domain(text: str) -> bool:
    """True when an article's description/opening says it's an animal, person, place, film, album..."""
    return bool(OFF_DOMAIN.search((text or "")[:260]))


# ------------------------------------------------------------------ numbers

def numbers(text: str) -> List[Tuple[float, Optional[str], str]]:
    """Numeric claims: [(value in the family's base unit, family or None, raw)], ignoring ranks ('1.'),
    'Top 10', 'Part 3', aspect ratios, hashtags and links."""
    t = re.sub(r"https?://\S+|#\w+|\bpart\s+\d+\b|\btop\s+\d+\b|\b9:16\b|\b\d+/\d+\b", " ", text or "", flags=re.I)
    t = re.sub(r"(?m)^\s*\d{1,2}[.)]\s", " ", t)  # list ranks
    out: List[Tuple[float, Optional[str], str]] = []
    for m in _MACH.finditer(t):
        out.append((float(m.group(1)), "mach", m.group(0)))
    t = _MACH.sub(" ", t)
    for m in _NUM.finditer(t):
        raw = m.group(0).strip()
        a, b = m.start(1), m.end(1)
        # part of a model name, not a claim: 'BGM-109G', 'T-90', 'F-35', 'AK-47', '2A82-1M', 'Mk4'
        if (b < len(t) and t[b].isalpha() and not m.group(3)) or \
                (a >= 2 and t[a - 1] in "-‐" and t[a - 2].isalnum()) or (a >= 1 and t[a - 1].isalpha()):
            continue
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if m.group(2):
            v *= _MULT[m.group(2).lower()]
        unit = (m.group(3) or "").lower()
        fam = None
        if unit:
            fam, factor = _UNITS[unit]
            v *= factor
        if v < 2 and not fam:  # counting words / list numbers
            continue
        out.append((v, fam, raw))
    return out


def _corpus_numbers(corpus: str) -> List[Tuple[float, Optional[str], str]]:
    return numbers(corpus)


def number_supported(v: float, pool, fam: Optional[str] = None) -> bool:
    """The same quantity is in the sources: same unit family (converted), within rounding (2 %).
    A number without a unit (a year, a count) must appear exactly."""
    for item in pool:
        pv, pf = (item[0], item[1]) if isinstance(item, tuple) else (item, None)
        if fam and pf != fam:
            continue
        tol = abs(v) * 0.02 + 1e-9 if fam else max(0.01, abs(v) * 0.005)  # rounding only, never a different figure
        if fam == "mass" and pf == "mass":
            tol = max(tol, abs(v) * 0.1)  # short / long / metric tons
        if abs(pv - v) <= tol:
            return True
    return False


# ------------------------------------------------------------------ sources

def _cache() -> Path:
    d = Path(config.OUTPUT_DIR) / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / "fact_sources.json"


def source_text(url: str) -> Tuple[str, str]:
    """(short description, plain-text article) for a Wikipedia URL, cached. ('', '') if unavailable."""
    m = re.match(r"https?://(\w+)\.wikipedia\.org/wiki/([^?#]+)", url or "")
    if not m:
        return "", ""
    lang, title = m.group(1), urllib.parse.unquote(m.group(2)).replace("_", " ")
    try:
        cache = json.loads(_cache().read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    key = f"{lang}:{title}"
    if key in cache:
        return tuple(cache[key])  # type: ignore[return-value]
    from agents import equipment_catalog as ec
    d = ec._get({"action": "query", "titles": title, "prop": "extracts|description", "explaintext": 1, "redirects": 1}) or {}
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return "", ""
    res = (pages[0].get("description") or "", (pages[0].get("extract") or "")[:60000])
    cache[key] = list(res)
    try:
        _cache().write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass
    return res


def corpus(project_or_research: Dict[str, Any]) -> Tuple[str, List[str]]:
    """(text of the ON-TOPIC sources, titles of the off-topic sources that were thrown out)."""
    tr = project_or_research.get("topic_research") or project_or_research
    good, bad = [], []
    unreachable = False
    for s in tr.get("sources") or []:
        url = s.get("url") or ""
        desc, text = source_text(url) if "wikipedia.org/wiki/" in url and "Special:" not in url else ("", "")
        if "wikipedia.org/wiki/" in url and not text:
            unreachable = True
        if off_domain(f"{desc}. {text[:300]}") or off_domain(s.get("snippet") or ""):
            bad.append(s.get("title") or url)
            continue
        good.append(text or s.get("snippet") or "")
        if s.get("source_type") == "user_input":
            good.append(s.get("snippet") or "")
    for k in ("verified_facts", "key_facts"):
        for f in tr.get(k) or []:
            if isinstance(f, str) and not off_domain(f):
                good.append(f)
    if unreachable and tr.get("research_text"):
        # an article couldn't be fetched (offline / rate limit): use the saved research text, minus
        # paragraphs about something else, rather than deleting correct sentences
        good += [para for para in str(tr["research_text"]).split("\n") if para.strip() and not off_domain(para)
                 and not any(b and b.lower() in para.lower()[:80] for b in bad)]
    notes = tr.get("custom_notes") or ""
    if notes:
        good.append(notes)
    return "\n".join(good), bad


# ------------------------------------------------------------------ sentences

_CTA = re.compile(r"\?\s*$|comment|subscribe|drop your|let us know|like and|follow for|share this|stay tuned|which one", re.I)


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z0-9-]{2,}", (s or "").lower()) if w not in _STOP}


def _sentences(text: str) -> List[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", text or "") if x.strip()]


def judge_sentence(sentence: str, good_text: str, good_pool: List[float], subject: str) -> Optional[str]:
    """None when fine, else the reason the sentence must not be in the video."""
    s = sentence.strip()
    if len(s) < 12 or _CTA.search(s):
        return None
    if off_domain(s):
        return "about something else (animal / person / place / media), not the subject"
    for v, fam, raw in numbers(s):
        if not number_supported(v, good_pool, fam):
            return f"'{raw}' is not in the sources"
    return None


def scene_sentences(scenes: List[Dict[str, Any]], key: str = "narration") -> List[Tuple[str, List[int]]]:
    """Sentences of the whole narration with the scene indexes each one spans (scenes split sentences)."""
    out, cur, idxs = [], "", []
    for i, sc in enumerate(scenes):
        part = str(sc.get(key) or "").strip()
        if not part:
            continue
        for piece in re.split(r"(?<=[.!?])\s+", part):
            cur = f"{cur} {piece}".strip()
            if i not in idxs:
                idxs.append(i)
            if re.search(r"[.!?]$", piece):
                out.append((cur, idxs))
                cur, idxs = "", []
    if cur:
        out.append((cur, idxs))
    return out


def filter_script(script_data: Dict[str, Any], research: Dict[str, Any], subject: str = "") -> List[str]:
    """BEFORE the voice-over: removes narration sentences that are off-topic or have numbers not in the
    sources (scenes left without words are dropped), and captions with unsupported numbers. Returns what
    was removed."""
    scenes = script_data.get("scenes") or []
    if not scenes:
        return []
    text, bad_sources = corpus(research)
    pool = _corpus_numbers(text)
    removed: List[str] = [f"source dropped (off-topic): {b}" for b in bad_sources]
    for key in ("narration", "voiceover_text"):
        for sent, idxs in scene_sentences(scenes, key):
            why = judge_sentence(sent, text, pool, subject)
            if not why:
                continue
            if key == "narration":
                removed.append(f"'{sent[:90]}': {why}")
            for i in idxs:
                left = scenes[i].get(key) or ""
                for frag in re.split(r"(?<=[.!?])\s+", sent):
                    left = left.replace(frag, " ")
                scenes[i][key] = re.sub(r"\s+", " ", left).strip()
    for sc in scenes:
        cap = str(sc.get("on_screen_text") or "")
        if any(not number_supported(v, pool, f) for v, f, _ in numbers(cap)):
            removed.append(f"caption '{cap[:60]}': number not in the sources")
            sc["on_screen_text"] = re.sub(_NUM, "", cap).strip(" ·-") or (subject or "").upper()[:40]
    # a narrated scene that lost all its words would be silent: drop it (keep at least 3 scenes)
    narrated = any(str(sc.get("narration") or "").strip() for sc in scenes)
    if narrated:
        keep = [sc for sc in scenes if str(sc.get("narration") or "").strip() or sc.get("title_card")]
        if len(keep) >= 3 and len(keep) < len(scenes):
            script_data["scenes"] = keep
            for n, sc in enumerate(keep, 1):
                sc["scene_number"] = n
    return removed


# ------------------------------------------------------------------ the whole finished video

def check_project(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Problems with the facts of a finished video: [{'kind', 'detail', 'fix'}] (empty = all verified)."""
    if project.get("style") == "music_only":
        return []
    problems: List[Dict[str, Any]] = []
    text, bad_sources = corpus(project)
    pool = _corpus_numbers(text)
    subject = (project.get("topic_research") or {}).get("topic_subject") or project.get("topic") or ""
    scenes = project.get("scenes") or []
    if project.get("style") == "car_edit" or project.get("is_car_edit"):
        name = (project.get("car_edit_plan") or {}).get("car_name") or project.get("topic") or ""
        text = text + "\n" + car_text(name)
        pool = _corpus_numbers(text)
    poster = next((v for v in project.get("visual_records") or [] if v.get("ranked_items")), None)
    chart_text = ""
    if poster:
        chart_text = json.dumps(poster.get("ranked_items"), ensure_ascii=False)
        pool = pool + _corpus_numbers(chart_text)
        problems += _check_chart(poster, project)

    for sent, idxs in scene_sentences(scenes, "narration"):
        why = judge_sentence(sent, text, pool, subject)
        if why:
            problems.append({"kind": "narration", "detail": f"Scene {idxs[0] + 1}: \"{sent[:100]}\" - {why}",
                             "fix": "remove_unverified_text"})
    for i, sc in enumerate(scenes):
        if sc.get("title_card"):
            continue
        cap = str(sc.get("on_screen_text") or "")
        for v, fam, raw in numbers(cap):
            if not number_supported(v, pool, fam):
                problems.append({"kind": "caption", "detail": f"Scene {i + 1} caption '{cap[:60]}': '{raw}' not in the sources",
                                 "fix": "remove_unverified_text"})
    # title + description (hashtags, links and the credits block are ignored)
    desc = re.split(r"\n\s*Photo credits:", project.get("description") or "")[0]
    for field, val in (("title", project.get("title") or ""), ("description", desc)):
        for sent in [x for line in val.splitlines() for x in _sentences(re.sub(r"^\s*\d{1,2}[.)]\s+", "", line))]:
            if off_domain(sent):
                problems.append({"kind": field, "detail": f"{field}: \"{sent[:90]}\" is about something else", "fix": None})
            for v, fam, raw in numbers(sent):
                if not number_supported(v, pool, fam):
                    problems.append({"kind": field, "detail": f"{field}: '{raw}' in \"{sent[:80]}\" is not in the sources",
                                     "fix": "rebuild_chart" if poster else None})
    # car spec line
    spec = str((project.get("car_edit_plan") or {}).get("subtitle_spec") or "")
    for v, fam, raw in numbers(spec):
        if not number_supported(v, pool, fam):
            problems.append({"kind": "car_spec", "detail": f"car spec '{spec}': '{raw}' is not in the car's sources", "fix": None})
    if bad_sources and any(p["kind"] == "narration" for p in problems):
        problems.append({"kind": "sources", "detail": f"off-topic research source(s) used: {', '.join(bad_sources)}", "fix": None})
    # one line per distinct problem
    seen, out = set(), []
    for p in problems:
        if p["detail"] not in seen:
            seen.add(p["detail"])
            out.append(p)
    return out


def _check_chart(poster: Dict[str, Any], project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every chart row's numbers re-verified on the model's Wikipedia article."""
    from agents import equipment_catalog as ec
    from agents import topic_weapon_list as twl
    items = poster.get("ranked_items") or []
    if poster.get("kind") == "cartridge":  # to-scale cartridge chart: every dimension re-read from Wikipedia
        from agents import cartridge_poster
        return [{"kind": "chart", "detail": d, "fix": "rebuild_chart"} for d in cartridge_poster.verify_items(items)]
    kind = poster.get("kind") or twl.kind_for(project.get("topic") or "")
    out: List[Dict[str, Any]] = []
    try:
        arts = ec.fetch_models([it.get("article") or it.get("name") for it in items if it.get("article") or it.get("name")])
    except Exception:
        arts = {}
    for it in items:
        name = it.get("name") or ""
        if str(it.get("year") or "").isdigit() and int(it["year"]) > twl._this_year():
            out.append({"kind": "chart", "detail": f"{name}: year {it['year']} is in the future", "fix": "rebuild_chart"})
        m = arts.get(it.get("article") or name)
        if not m:
            out.append({"kind": "chart", "detail": f"{name}: Wikipedia article not found, row can't be verified",
                        "fix": "rebuild_chart"})
            continue
        m["_kind"] = kind
        good = twl.checked_specs(m)
        typ_year = {f"Type - {twl._clean_type(m.get('type') or '')}"[:60]}
        for b in it.get("bullets") or []:
            if " - " not in b:
                continue
            lab, val = b.split(" - ", 1)
            if lab in ("Type", "Gun", "Troops") or b[:60] in typ_year:
                continue  # type text / the user's own spec sheet
            if lab == "In service":
                if val.isdigit() and int(val) > twl._this_year():
                    out.append({"kind": "chart", "detail": f"{name}: '{b}' is a planned year", "fix": "rebuild_chart"})
                continue
            if lab == "Calibre" and kind == "vehicle":
                lab = "Main gun"
            if good.get(lab) != val:
                out.append({"kind": "chart", "detail": f"{name}: shows '{b}', verified value: {good.get(lab) or 'none (not certain)'}",
                            "fix": "rebuild_chart"})
    n = len(items)
    topn = twl.top_n(project.get("title") or "")
    if topn and topn != n:
        out.append({"kind": "chart", "detail": f"title says Top {topn} but the chart shows {n}", "fix": "rebuild_chart"})
    return out


def car_text(car_name: str) -> str:
    """Plain text of the car's Wikipedia article(s): the top search hits whose title names the brand."""
    from agents import equipment_catalog as ec
    try:
        d = ec._get({"action": "query", "list": "search", "srsearch": car_name, "srlimit": 4}) or {}
    except Exception:
        return ""
    brand = (car_name.split() or [""])[0].lower()
    texts = []
    for h in d.get("query", {}).get("search", [])[:3]:
        if brand and brand in h["title"].lower():
            texts.append(source_text("https://en.wikipedia.org/wiki/" + urllib.parse.quote(h["title"].replace(" ", "_")))[1])
    return "\n".join(texts)


def verify_spec_line(spec: str, car_name: str, extra_text: str = "") -> str:
    """Keeps only the parts of a car spec line ('4.0L FLAT-6 · 518 HP · 9,000 RPM') whose numbers are in the
    car's Wikipedia article / research; parts without numbers (FLAT-6, HYBRID) stay. '' if nothing is left."""
    parts = [x.strip() for x in re.split(r"\s*·\s*", spec or "") if x.strip()]
    if not any(numbers(x) for x in parts):
        return spec
    pool = _corpus_numbers(car_text(car_name) + "\n" + (extra_text or ""))
    kept = [x for x in parts if all(number_supported(v, pool, f) for v, f, _ in numbers(x))]
    if len(kept) < len(parts):
        print(f"[FactCheck] car spec '{spec}': kept only the verified parts -> '{' · '.join(kept)}'")
    return " · ".join(kept)
