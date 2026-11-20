"""
Local AI scriptwriter (free): Qwen 2.5 7B via Ollama, grounded ONLY in researched facts.

Produces a ChatGPT-style brief: title, subtitle, overview, spec table, key features,
timed scenes (narration + on-screen text), description and hashtags.

Grounding rules (enforced in code, not just asked of the model):
  * Facts are numbered [F1..Fn] with their source; every scene must cite >= 1 fact id.
  * Every number in a narration / spec value must literally appear in the cited facts
    (catches invented calibres, years, speeds). Failing scenes are dropped; if too few
    scenes survive, one retry, then the caller falls back to the template script.
  * The model is unloaded right after use (keep_alive=0) to protect the 18 GB of RAM.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("SCRIPT_WRITER_MODEL", "qwen2.5:7b")
ENABLED = os.getenv("SCRIPT_WRITER", "auto").lower()  # auto | llm | template (import-time default)


def _mode() -> str:
    """Read on every call: a value cached at import time stuck at 'template' if the QA suite
    (which switches it off temporarily) happened to import this module first."""
    return os.getenv("SCRIPT_WRITER", "auto").lower()
# Word budget at the narrator's NATURAL pace. Kokoro (am_michael at 1.15) speaks ~1.85 words/s; a
# 135-wpm (2.25 w/s) budget overshot every time and forced a +27-30% rushed re-voice.
WORDS_PER_SECOND = (2.0 if os.getenv("TTS_ENGINE", "kokoro").lower() == "kokoro" else 135.0 / 60.0)

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


_WORD_NUMS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
              "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15",
              "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "hundred": "100",
              "thousand": "1000", "million": "1000000", "dozen": "12", "first": "1", "second": "2", "third": "3"}
_ORDINAL_OK = {"first", "second", "third"}  # common in prose ("first flew"); only flagged if used with a number word


def _numbers(text: str) -> List[str]:
    nums = [n.replace(",", "") for n in _NUM.findall(text or "")]
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if w in _WORD_NUMS and w not in _ORDINAL_OK:
            nums.append(_WORD_NUMS[w])
    return nums


def _norm_num(n: str) -> str:
    n = n.replace(",", "")
    return n.rstrip("0").rstrip(".") if "." in n else n


def _grounded(text: str, fact_texts: List[str], subject: str) -> Tuple[bool, List[str]]:
    """All numbers in text must appear in the cited facts (numbers in the subject name are allowed)."""
    allowed = {_norm_num(n) for f in fact_texts for n in _numbers(f)} | {_norm_num(n) for n in _numbers(subject)}
    bad = [n for n in _numbers(text) if _norm_num(n) not in allowed]
    return (not bad), bad


_STOP = {"the", "and", "with", "from", "that", "this", "into", "will", "have", "been", "their", "which",
         "about", "also", "were", "they", "them", "than", "more", "most", "over", "under", "after"}


def _content_words(text: str, subject: str) -> set:
    subj = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9-]+", subject)}
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text or "")} - _STOP - subj


def _supporting_facts(text: str, facts: List[Dict[str, str]], subject: str) -> List[int]:
    """1-based ids of facts that actually support this line (all its numbers, or >=2 shared key words)."""
    nums = {_norm_num(n) for n in _numbers(text)} - {_norm_num(n) for n in _numbers(subject)}
    words = _content_words(text, subject)
    ids = []
    for i, f in enumerate(facts, 1):
        f_nums = {_norm_num(n) for n in _numbers(f["text"])}
        if nums and nums <= f_nums:
            ids.append(i)
        elif not nums and len(words & _content_words(f["text"], subject)) >= 2:
            ids.append(i)
    if nums and not ids:  # numbers spread across several facts
        ids = [i for i, f in enumerate(facts, 1) if nums & {_norm_num(n) for n in _numbers(f["text"])}]
    return ids


GENERIC_SPEC_LABELS = {"calibre", "caliber", "cartridge", "manufacturer", "maker", "country", "origin", "weight",
                       "length", "engine", "engines", "crew", "speed", "range", "variants", "users", "operators",
                       "status", "role", "type", "designer", "unit", "action", "barrel", "magazine", "optic", "sights"}
_HYPE = re.compile(r"\b(\w+-like|best|most|deadliest|fastest|strongest|unmatched|unrivall?ed|ultimate|premier|"
                   r"world'?s|legendary|revolutionary|game[- ]changer|unstoppable|invincible)\b", re.I)


def _embellished(line: str, fact: str) -> List[str]:
    """Hype/comparison phrases in the line that its source fact never uses ("most advanced" must
    appear as a phrase in the fact; the word "most" elsewhere in the fact doesn't count)."""
    fl = " ".join(fact.lower().split())
    found = []
    for m in _HYPE.finditer(line):
        nxt = re.match(r"\s+([a-z-]+)", line[m.end():].lower())
        phrase = m.group(0).lower() + (" " + nxt.group(1) if nxt else "")
        if phrase not in fl:
            found.append(phrase)
    return found


def _label_supported(label: str, fact_texts: List[str]) -> bool:
    words = [w for w in re.findall(r"[a-z]{3,}", label.lower())]
    if not words or any(w in GENERIC_SPEC_LABELS for w in words):
        return True
    joined = " ".join(fact_texts).lower()
    return all(w in joined for w in words)


def is_available() -> bool:
    if _mode() == "template":
        return False
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            models = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
        return any(m == MODEL or m.startswith(MODEL.split(":")[0]) for m in models)
    except Exception:
        return False


def can_run() -> bool:
    """True if the LLM scriptwriter can be used: Ollama is already serving the model, or it is
    installed locally and can be started on demand by resources.lease("ollama")."""
    if _mode() == "template":
        return False
    if is_available():
        return True
    try:
        from app.automation import resources
        return Path(resources.SERVICES["ollama"]["start"][0]).exists()
    except Exception:
        return False


LINE_SCHEMA = {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "object",
               "properties": {"fact": {"type": "integer"}, "line": {"type": "string"},
                              "caption": {"type": "string"}, "role": {"type": "string"}},
               "required": ["fact", "line", "caption", "role"]}}},
               "required": ["lines"]}
PACK_SCHEMA = {"type": "object", "properties": {
    "title": {"type": "string"}, "subtitle": {"type": "string"}, "overview": {"type": "string"},
    "hook": {"type": "string"}, "closing": {"type": "string"},
    "on_screen_text": {"type": "array", "items": {"type": "string"}},
    "roles": {"type": "array", "items": {"type": "string"}},
    "specs": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                                          "required": ["label", "value"]}},
    "features": {"type": "array", "items": {"type": "string"}},
    "description": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}}},
    "required": ["title", "subtitle", "overview", "hook", "closing", "on_screen_text", "roles", "specs", "features", "description", "hashtags"]}


def _ollama(prompt: str, schema: Dict[str, Any], keep_alive: Any = "2m", timeout: int = 240) -> Dict[str, Any]:
    payload = {"model": MODEL, "stream": False, "keep_alive": keep_alive, "format": schema,
               "options": {"temperature": 0.35, "num_ctx": 8192},
               "messages": [{"role": "system", "content": (
                   "You write factual, energetic YouTube Shorts voiceovers about defense technology. "
                   "Use ONLY information from the given facts. Never invent numbers, dates, comparisons or capabilities.")},
                   {"role": "user", "content": prompt}]}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(json.loads(r.read())["message"]["content"])


def _unload() -> None:
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=json.dumps({"model": MODEL, "keep_alive": 0}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        pass


def _clean_line(text: str, proper: Optional[set] = None) -> str:
    text = re.sub(r"\s*[\[(]?\b(?:Fact|FACT|F)\s?\d+[\])]?:?", "", text or "").strip()
    text = re.sub(r"\s+([.,!?])", r"\1", text)
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        # ALL-CAPS line -> sentence case, keeping designators like F-22 / C25 / 92FS intact
        proper = proper or set()
        def fix(w):
            if re.search(r"\d", w):
                return w
            core = re.sub(r"[^A-Za-z'-]", "", w)
            base = core.lower().split("'")[0]
            if base in proper:  # restore names seen capitalised in the research (Canada, Colt, Boeing)
                return w.lower().replace(base, base.capitalize(), 1)
            return w.lower()
        text = " ".join(fix(w) for w in text.split())
        text = text[:1].upper() + text[1:]
    if text and text[-1] not in ".!?":
        text += "."
    return text


def write_brief(subject: str, facts: List[Dict[str, str]], duration: float) -> Optional[Dict[str, Any]]:
    """
    facts: [{"text": ..., "source": ...}] (already researched & cleaned).
    Two local LLM calls: (1) edit chosen facts down into voiceover lines, (2) package the brief.
    Returns a validated brief, or None (caller falls back to the template script).
    """
    facts = [f for f in facts if f.get("text") and len(f["text"].split()) >= 5][:14]
    if len(facts) < 3 or not can_run():
        return None
    target_words = int(duration * WORDS_PER_SECOND)
    # Qwen 7B edits facts into ~10-word lines; hook + closing add ~14 words
    n_body = max(2, min(len(facts), -(-(target_words - 14) // 10)))
    chosen = facts[:n_body]
    from app.automation import resources

    notes: List[str] = []
    all_text = [f["text"] for f in facts]
    proper = {w.lower() for f in all_text for w in re.findall(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})", f)}
    try:
        # lease() starts Ollama when it isn't running (it used to be checked BEFORE starting, so a
        # stopped Ollama always meant the template script) and stops it afterwards if it started it.
        with resources.lease("ollama"):
            if not is_available():
                print(f"[script-writer] Ollama is up but model {MODEL} is missing; using template")
                return None

            def edit_lines(batch):
                out = _ollama(
                    f"Edit each FACT into ONE spoken voiceover line for a YouTube Short about {subject}. "
                    "Keep the important names and numbers exactly, cut filler, make it energetic. "
                    "Each line must be 10 to 16 words. Do not add anything that is not in that fact "
                    "(no new numbers, durations, comparisons or opinions).\n"
                    + "\n".join(f"FACT {i + 1}: {f['text']}" for i, f in enumerate(batch)), LINE_SCHEMA)
                got = []
                for item in out.get("lines", []):
                    k = item.get("fact")
                    if not isinstance(k, int) or not 1 <= k <= len(batch):
                        continue
                    line = _clean_line(item.get("line", ""), proper)
                    src = batch[k - 1]
                    ok, bad = _grounded(line, [src["text"]], subject)
                    shared = _content_words(line, subject) & _content_words(src["text"], subject)
                    hype = _embellished(line, src["text"])
                    if not ok:
                        notes.append(f"dropped '{line[:50]}': numbers {bad} not in its fact")
                    elif hype:
                        notes.append(f"dropped '{line[:50]}': embellishment {hype} not in its fact")
                    elif len(shared) < 2 and len(line.split()) > 5:
                        notes.append(f"dropped '{line[:50]}': doesn't match its fact")
                    else:
                        fid = facts.index(src) + 1
                        cap = (item.get("caption") or "").strip()
                        if not _grounded(cap, [src["text"]], subject)[0]:
                            cap = ""
                        got.append({"narration": line, "fact_ids": [fid], "sources": [src["source"]],
                                    "on_screen_text": cap.upper()[:40], "role": (item.get("role") or "Fact").strip().title()})
                return got

            body = edit_lines(chosen)
            if len(body) < max(2, n_body - 1):
                retry = edit_lines(chosen)  # one retry if too many lines were dropped
                if len(retry) > len(body):
                    body = retry
            # Top up with unused facts until the narration fills the requested length
            remaining = facts[n_body:]
            while remaining and 14 + sum(len(b["narration"].split()) for b in body) < 0.9 * target_words:
                batch, remaining = remaining[:2], remaining[2:]
                body += edit_lines(batch)
            if len(body) < 2:
                print(f"[script-writer] Not enough grounded lines ({len(body)}): {notes[:3]}")
                return None

            pack = _ollama(
                f"SUBJECT: {subject}\nFACTS:\n" + "\n".join(f"F{i + 1}: {f['text']}" for i, f in enumerate(facts))
                + "\n\nVOICEOVER BODY LINES:\n" + "\n".join(f"{i + 1}. {b['narration']}" for i, b in enumerate(body))
                + f"""\n\nWrite the package for this Short:
- title: catchy, max 70 characters, names the subject (one relevant emoji or flag allowed at the end)
- subtitle: short descriptive line supported by the facts (e.g. "Canada's Next-Generation Assault Rifle")
- overview: 1-2 factual sentences
- hook: a 6-10 word opening line that names the subject and creates curiosity, no new facts
- closing: a 6-10 word closing line (a question to the viewer is good), no new facts
- on_screen_text: exactly 2 captions, 2-4 words each, ALL CAPS: one for the hook, one for the closing
- roles: ["Introduction", "Conclusion"]
- specs: 4-8 rows of label/value copied from the facts. The label must say exactly what the fact says
  and use words FROM the fact (e.g. "Contract: up to 65,402 weapons", not "Number built: 65,402";
  "In service: 2026", never "First flight" for a rifle). Generic labels like Calibre, Manufacturer, Weight are fine.
- features: 3-5 short feature lines from the facts
- description: 2-3 factual sentences for YouTube
- hashtags: 5-8 hashtags including #Shorts""", PACK_SCHEMA)
    except resources.ResourceBusy as e:
        print(f"[script-writer] Skipped: {e}")
        return None
    except Exception as e:
        print(f"[script-writer] Ollama call failed: {e}")
        return None
    finally:
        _unload()

    hook = _clean_line(pack.get("hook", ""), proper) or f"Meet the {subject}."
    closing = _clean_line(pack.get("closing", ""), proper) or f"What do you think of the {subject}?"
    for name, line in (("hook", hook), ("closing", closing)):
        if not _grounded(line, all_text, subject)[0]:
            notes.append(f"{name} had invented numbers; replaced")
            hook = f"Meet the {subject}." if name == "hook" else hook
            closing = f"What do you think of the {subject}?" if name == "closing" else closing
    caps = pack.get("on_screen_text", []) or []
    hook_cap = caps[0] if caps and _grounded(caps[0], all_text, subject)[0] else subject
    close_cap = caps[-1] if len(caps) > 1 and _grounded(caps[-1], all_text, subject)[0] else ""
    # Body captions/roles come from the SAME call as their line, so they can't drift onto another scene
    scenes = ([{"narration": hook, "fact_ids": [], "sources": [], "role": "Introduction", "on_screen_text": hook_cap.upper()[:40]}]
              + body
              + [{"narration": closing, "fact_ids": [], "sources": [], "role": "Conclusion", "on_screen_text": close_cap.upper()[:40]}])

    specs = []
    for row in pack.get("specs", []):
        # The model sometimes writes "Thrust: 70,000 lbs" as the LABEL; split it into label + value
        lab, val = str(row.get("label", "")), str(row.get("value", ""))
        if ":" in lab:
            head, tail = lab.split(":", 1)
            row = {"label": head.strip(), "value": f"{tail.strip()} ({val.strip()})" if val.strip() else tail.strip()}
        val = f"{row.get('label', '')} {row.get('value', '')}"
        ids = _supporting_facts(val, facts, subject)
        if ids and _grounded(row.get("value", ""), all_text, subject)[0] and _label_supported(row.get("label", ""), [facts[i - 1]["text"] for i in ids]):
            specs.append({"label": row["label"].strip(), "value": row["value"].strip(), "source": facts[ids[0] - 1]["source"]})
        else:
            notes.append(f"spec '{row.get('label')}: {row.get('value')}' not supported; dropped")
    features = [f for f in pack.get("features", []) if _grounded(f, all_text, subject)[0]
                and _supporting_facts(f, facts, subject) and not _embellished(f, " ".join(all_text))]
    texts = {}
    for key in ("title", "subtitle", "overview", "description"):
        val = (pack.get(key) or "").strip()
        texts[key] = val if _grounded(val, all_text, subject)[0] else ""
        if val and not texts[key]:
            notes.append(f"{key} had unsupported numbers; removed")
    total_words = sum(len(s["narration"].split()) for s in scenes)
    if total_words < 0.7 * target_words:
        print(f"[script-writer] Script too short ({total_words}/{target_words} words); using template")
        return None
    return {
        "engine": f"ollama:{MODEL}",
        "title": texts["title"] or subject,
        "subtitle": texts["subtitle"],
        "overview": texts["overview"],
        "specs": specs,
        "features": features,
        "scenes": scenes,
        "description": texts["description"],
        "hashtags": [h if h.startswith("#") else f"#{h}" for h in pack.get("hashtags", [])][:8],
        "facts": facts,
        "word_count": total_words,
        "grounding_notes": notes,
    }
