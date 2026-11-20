"""
Turns the user's free-text feedback on a video into concrete fixes for Auto-fix & re-check.

Feedback lives on the project as project["feedback"] = [{id, text, status, created_at, actions, result}]
with status "open" -> "fixed" (actions applied) or "needs_you" (nothing safe to do automatically).

parse(text, project) -> list of actions. Rules first (deterministic), then the local LLM (Ollama) for
phrasing the rules don't understand, constrained to the same small set of actions:
  replace_image {scene}       new verified photo / AI image for that scene
  new_music {}                a fresh on-theme track (saved to the library)
  music_volume {factor}       music louder (>1) or quieter (<1)
  slower_voice {}             give the video more time so the narrator isn't rushed
  set_narration {scene, text} change what a scene says
  remove_scene {scene}
  set_title {text}
  rerender {}                 rebuild voice + captions (caption glitches, sync)
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

ACTIONS = ("replace_image", "new_music", "music_volume", "slower_voice", "set_narration", "remove_scene",
           "set_title", "rerender", "chart_swap_row", "chart_rebuild")
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
        "ninth": 9, "tenth": 10, "1st": 1, "2nd": 2, "3rd": 3}
_IMG = r"(?:image|images|picture|pictures|photo|photos|pic|visual|shot|frame)"
_SCENE_REF = re.compile(rf"(?:scene|{_IMG}|clip|slide|part)\s*(?:no\.?|number|#)?\s*(\d+)", re.I)
_ORD_REF = re.compile(rf"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last|\d+(?:st|nd|rd|th))\s+(?:scene|{_IMG}|clip|slide|part)", re.I)
_QUOTED = r"[\"“”'‘’](.+?)[\"“”'‘’]"


def new_item(text: str) -> Dict[str, Any]:
    return {"id": uuid.uuid4().hex[:10], "text": str(text).strip()[:1000], "status": "open",
            "created_at": datetime.now().isoformat(timespec="seconds"), "actions": [], "result": None}


def _scenes_in(text: str, n_scenes: int) -> List[int]:
    found = [int(m) for m in _SCENE_REF.findall(text)]
    for word in _ORD_REF.findall(text):
        w = word.lower()
        if w == "last":
            found.append(n_scenes)
        elif w in _ORD:
            found.append(_ORD[w])
        else:
            num = re.match(r"\d+", w)
            if num:
                found.append(int(num.group(0)))
    return sorted({s for s in found if 1 <= s <= max(1, n_scenes)})


def _clauses(text: str) -> List[str]:
    """Splits a note into independent complaints, so 'scene 2 image is wrong and music too loud' doesn't
    read 'wrong' as a music complaint. Quoted text is removed first (it's content, not a complaint)."""
    t = re.sub(_QUOTED, " ", str(text))
    parts = re.split(r"[.;!?\n]+|,(?!\d)|\s+(?:and|but|also|plus)\s+", t, flags=re.I)
    return [p.strip() for p in parts if p and p.strip()]


def chart_rows(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Rows of a WeaponX chart video ([] for normal videos)."""
    for r in project.get("visual_records") or []:
        if r.get("source") == "weaponx_lab_poster" and r.get("ranked_items"):
            return list(r["ranked_items"])
    return []


def is_static_chart(project: Dict[str, Any]) -> bool:
    recs = project.get("visual_records") or []
    return bool(recs) and any(r.get("source") == "weaponx_lab_poster" for r in recs) and \
        (project.get("style") == "weaponx" or project.get("is_weaponx_lab"))


def _row_tokens(row: Dict[str, Any]) -> List[str]:
    """Distinctive words that identify a row in a note: 'Gryphon', 'BGM-109G', 'JASSM', 'Kalibr'."""
    toks = set()
    for field in (row.get("name"), row.get("article")):
        for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", str(field or "")):
            lw = w.lower()
            if (any(c.isdigit() for c in lw) and len(lw) >= 3) or (len(lw) >= 5 and lw not in
                    ("missile", "family", "rocket", "torpedo", "system", "systems", "class", "cruise", "launcher")):
                toks.add(lw)
    return sorted(toks)


def _chart_actions(text: str, project: Dict[str, Any]) -> List[Dict[str, Any]]:
    t = " " + str(text).lower() + " "
    complaint = re.search(r"wrong|bad|blur|ugly|poor|not (?:good|clear|understand|look|the|a |right|correct)|"
                          r"doesn'?t|isn'?t|weird|replace|change|remove|delete|drop|other|another|fake|confusing|"
                          r"unclear|understandable|cropped|cut off|hidden", t)
    acts = []
    for row in chart_rows(project):
        if any(re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", t) for tok in _row_tokens(row)):
            if complaint:
                acts.append({"action": "chart_swap_row", "name": row.get("article") or row.get("name")})
    if not acts and complaint and re.search(rf"{_IMG}|chart|poster|list|row", t):
        acts.append({"action": "chart_rebuild"})
    return acts


def parse_rules(text: str, project: Dict[str, Any]) -> List[Dict[str, Any]]:
    n = len(project.get("scenes") or [])
    acts: List[Dict[str, Any]] = []
    if is_static_chart(project):
        # WeaponX short = ONE chart for the whole video: a note about a row (e.g. "Gryphon image is not good")
        # fixes that row; never swap a whole scene for an unrelated photo
        chart = _chart_actions(text, project)
        rest = [a for a in _parse_generic(text, project, n) if a["action"] not in ("replace_image", "remove_scene")]
        return chart + rest
    return _parse_generic(text, project, n)


def _parse_generic(text: str, project: Dict[str, Any], n: int) -> List[Dict[str, Any]]:
    acts: List[Dict[str, Any]] = []

    # Rules that need the user's quoted text work on the whole note
    m = re.search(rf"title\s*(?:should be|to|=|:|as)\s*{_QUOTED}", text, re.I)
    if m:
        acts.append({"action": "set_title", "text": m.group(1).strip()})
    m = re.search(rf"(?:scene|part)\s*(\d+)[^\"“']*?(?:should say|say|says? instead|text to|change (?:it )?to|replace (?:it )?with|narration to)\s*{_QUOTED}", text, re.I)
    if m and 1 <= int(m.group(1)) <= n:
        acts.append({"action": "set_narration", "scene": int(m.group(1)), "text": m.group(2).strip()})
    narrated = {a.get("scene") for a in acts if a["action"] == "set_narration"}

    last_scenes: List[int] = []
    for clause in _clauses(text):
        t = " " + clause.lower() + " "
        scenes = _scenes_in(t, n) or ([] if re.search(r"music|song|track|bgm|voice|narrat|caption|subtitle|title", t) else last_scenes)
        if scenes:
            last_scenes = scenes

        removed = []
        for s_ in scenes:
            if re.search(rf"(?:remove|delete|drop|cut)\s+(?:the\s+)?(?:scene|{_IMG}|part)\s*#?\s*{s_}\b", t) or \
               re.search(rf"(?:remove|delete|drop|cut)\s+(?:the\s+)?\w+\s+(?:scene|{_IMG}|part)", t) or \
               re.search(rf"(?:scene|part)\s*{s_}\s+(?:is\s+)?(?:not needed|unnecessary|useless)", t):
                acts.append({"action": "remove_scene", "scene": s_})
                removed.append(s_)

        image_issue = (re.search(_IMG, t) or re.search(r"scene\s*\d+\s+(?:is|looks|shows)", t)) and re.search(
            r"wrong|bad|blur|ugly|poor|low.?quality|repeat|same|duplicate|not (?:the|a|an|right|correct|matching)|"
            r"doesn'?t match|irrelevant|different|replace|change|fake|weird|cropped|cut off|another|incorrect|pixel", t)
        if image_issue:
            targets = scenes or (list(range(1, n + 1)) if re.search(rf"all (?:the )?{_IMG}|every {_IMG}", t) else [])
            for s_ in targets:
                if s_ not in removed and s_ not in narrated:
                    acts.append({"action": "replace_image", "scene": s_})

        if re.search(r"music|song|track|bgm|soundtrack|\bbeat\b", t):
            if re.search(r"too loud|very loud|louder than|overpower|drown|can'?t hear (?:the )?(?:voice|narrat)|lower|reduce|softer", t):
                acts.append({"action": "music_volume", "factor": 0.6})
            elif re.search(r"too (?:quiet|low|soft)|can'?t hear (?:the )?music|louder|increase|boost", t):
                acts.append({"action": "music_volume", "factor": 1.6})
            if re.search(r"change|new|different|another|boring|bad|wrong|not (?:match|fit|good|suit)|doesn'?t (?:match|fit|suit)|"
                         r"don'?t like|hate|generic|same|repeat|replace|better|theme|mood", t):
                acts.append({"action": "new_music"})

        if re.search(r"voice|narrat|speak|talk|speech", t) and re.search(r"fast|rush|quick|hurr", t):
            acts.append({"action": "slower_voice"})

        if (re.search(r"caption|subtitle|text on screen|on-screen text|words on", t) and
                re.search(r"wrong|missing|out of sync|late|early|split|broken|glitch|typo|mismatch|not match|overlap|cut", t)) or \
                re.search(r"out of sync|not in sync|lip|delay|lag", t):
            acts.append({"action": "rerender"})

    seen, out = set(), []
    for a in acts:
        key = tuple(sorted(a.items()))
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


FEEDBACK_SCHEMA = {"type": "object", "properties": {"actions": {"type": "array", "items": {"type": "object", "properties": {
    "action": {"type": "string", "enum": list(ACTIONS)}, "scene": {"type": "integer"},
    "text": {"type": "string"}, "factor": {"type": "number"}}, "required": ["action"]}}}, "required": ["actions"]}


def parse_llm(text: str, project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Maps feedback the rules didn't understand onto the allowed actions with the local LLM."""
    try:
        from agents import script_writer
        from app.automation import resources
        if not script_writer.can_run():
            return []
        scenes = "\n".join(f"Scene {i}: {s.get('narration', '')}" for i, s in enumerate(project.get("scenes") or [], 1))
        prompt = (
            "A creator left feedback on their YouTube Short. Map it to fixes from this list ONLY:\n"
            "replace_image(scene) = that scene's picture is wrong/bad; new_music = music doesn't fit; "
            "music_volume(factor: 0.6 quieter, 1.6 louder); slower_voice = narration too fast; "
            "set_narration(scene, text) = scene must say exactly this text (only if the feedback gives the text); "
            "remove_scene(scene); set_title(text) = only if the feedback gives the title; rerender = captions/sync glitch.\n"
            "If nothing fits, return an empty list. Never invent text.\n\n"
            f"VIDEO: {project.get('topic')}\n{scenes}\n\nFEEDBACK: {text}")
        with resources.lease("ollama"):
            if not script_writer.is_available():
                return []
            try:
                data = script_writer._ollama(prompt, FEEDBACK_SCHEMA, timeout=120)
            finally:
                script_writer._unload()  # free the model now, so music/clip engines aren't blocked
        n = len(project.get("scenes") or [])
        out = []
        for a in data.get("actions") or []:
            act = a.get("action")
            if act not in ACTIONS:
                continue
            if act in ("replace_image", "remove_scene", "set_narration") and not (isinstance(a.get("scene"), int) and 1 <= a["scene"] <= n):
                continue
            if act in ("set_narration", "set_title") and not str(a.get("text") or "").strip():
                continue
            if act in ("set_narration", "set_title") and str(a["text"]).strip().lower() not in text.lower():
                continue  # the text must come from the user, never from the model
            item = {"action": act}
            for k in ("scene", "text", "factor"):
                if a.get(k) not in (None, ""):
                    item[k] = a[k]
            if act == "music_volume":
                item["factor"] = 0.6 if float(item.get("factor") or 1) < 1 else 1.6
            out.append(item)
        return out
    except Exception as e:
        print(f"[FeedbackFixer] LLM parse skipped: {e}")
        return []


def parse(text: str, project: Dict[str, Any]) -> List[Dict[str, Any]]:
    acts = parse_rules(text, project)
    if acts:
        return acts
    acts = parse_llm(text, project)
    if is_static_chart(project):
        # the model doesn't know the video is one chart: scene-level fixes become a chart rebuild
        acts = [a for a in acts if a["action"] not in ("replace_image", "remove_scene", "set_narration")] + \
               ([{"action": "chart_rebuild"}] if any(a["action"] == "replace_image" for a in acts) else [])
    return acts


def describe(a: Dict[str, Any]) -> str:
    act = a["action"]
    return {
        "replace_image": f"new image for scene {a.get('scene')}",
        "new_music": "new on-theme music",
        "music_volume": "music quieter" if float(a.get("factor") or 1) < 1 else "music louder",
        "slower_voice": "more time so the voice isn't rushed",
        "set_narration": f"scene {a.get('scene')} text changed",
        "remove_scene": f"scene {a.get('scene')} removed",
        "set_title": "title changed",
        "rerender": "voice & captions rebuilt",
        "chart_swap_row": f"chart row '{a.get('name')}' replaced with another verified weapon",
        "chart_rebuild": "chart rebuilt with re-checked photos",
    }.get(act, act)
