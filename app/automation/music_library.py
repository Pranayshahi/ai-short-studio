"""
Overnight music library (free, local ACE-Step).

build_overnight() runs from the scheduler at night when nothing else is busy and generates a few
instrumental tracks per night until every mood in MOODS has one (then it refreshes the oldest).
pick(topic) chooses a mood-appropriate library track for a video, least-recently-used first,
so consecutive videos don't share the same music.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional

import config
from app.automation import state

MOODS: Dict[str, Dict[str, str]] = {
    "cinematic_epic":     {"category": "Cinematic", "mood": "Epic", "prompt": "epic orchestral trailer, big drums, brass swells"},
    "cinematic_tense":    {"category": "Cinematic", "mood": "Tense", "prompt": "tense cinematic pulses, low strings, ticking percussion"},
    "heroic_orchestral":  {"category": "Orchestral", "mood": "Heroic", "prompt": "heroic orchestral theme, french horns, snare rolls"},
    "dark_ambient":       {"category": "Ambient", "mood": "Dark", "prompt": "dark ambient drones, sub bass, distant metallic hits"},
    "military_drums":     {"category": "Cinematic", "mood": "Powerful", "prompt": "military marching drums, taiko, driving rhythm"},
    "electronic_pulse":   {"category": "Electronic", "mood": "Driving", "prompt": "driving electronic pulse, analog synth bass, modern documentary"},
    "hybrid_trailer":     {"category": "Cinematic", "mood": "Intense", "prompt": "hybrid trailer music, braams, risers, synth and orchestra"},
    "suspense_strings":   {"category": "Orchestral", "mood": "Suspenseful", "prompt": "suspenseful staccato strings, pizzicato, building tension"},
    "triumphant_brass":   {"category": "Orchestral", "mood": "Triumphant", "prompt": "triumphant brass fanfare, timpani, uplifting finale"},
    "cold_war_synth":     {"category": "Electronic", "mood": "Mysterious", "prompt": "1980s cold war synth, arpeggiator, espionage mood"},
    "rock_action":        {"category": "Rock", "mood": "Aggressive", "prompt": "action rock, distorted guitars, punchy drums, instrumental"},
    "industrial":         {"category": "Electronic", "mood": "Heavy", "prompt": "industrial percussion, mechanical clanks, heavy bass"},
    "stealth_minimal":    {"category": "Ambient", "mood": "Calm", "prompt": "minimal stealth ambience, soft pulses, airy pads"},
    "aerial_soaring":     {"category": "Cinematic", "mood": "Uplifting", "prompt": "soaring aerial cinematic theme, wide strings, sense of flight"},
    "naval_ocean":        {"category": "Orchestral", "mood": "Majestic", "prompt": "majestic naval theme, deep brass, rolling ocean percussion"},
    "desert_ops":         {"category": "Cinematic", "mood": "Tense", "prompt": "desert operations, middle eastern percussion, tense strings"},
    "hightech_cyber":     {"category": "Electronic", "mood": "Futuristic", "prompt": "futuristic high-tech electronic, glitch percussion, clean synths"},
    "documentary_calm":   {"category": "Cinematic", "mood": "Reflective", "prompt": "reflective documentary piano and strings, gentle"},
    "countdown_tension":  {"category": "Cinematic", "mood": "Urgent", "prompt": "countdown tension, accelerating rhythm, alarms-like synths"},
    "victory_finale":     {"category": "Orchestral", "mood": "Epic", "prompt": "victory finale, full orchestra and choir pads, instrumental"},
}

TOPIC_MOODS = [
    (("jet", "fighter", "raptor", "aircraft", "bomber", "f-", "su-", "air force", "stealth"), ["aerial_soaring", "cinematic_epic", "heroic_orchestral", "hybrid_trailer"]),
    (("missile", "hypersonic", "icbm", "rocket", "nuclear"), ["countdown_tension", "hybrid_trailer", "dark_ambient", "cinematic_tense"]),
    (("rifle", "pistol", "gun", "carbine", "ak-", "smg", "sniper", "firearm"), ["military_drums", "rock_action", "industrial", "cinematic_tense"]),
    (("tank", "armor", "armour", "artillery", "howitzer"), ["industrial", "military_drums", "heroic_orchestral"]),
    (("ship", "navy", "naval", "submarine", "carrier", "destroyer"), ["naval_ocean", "cinematic_epic", "suspense_strings"]),
    (("drone", "laser", "cyber", "ai ", "quantum", "radar"), ["hightech_cyber", "electronic_pulse", "cold_war_synth"]),
    (("history", "war ii", "ww2", "cold war", "vietnam", "legacy"), ["documentary_calm", "cold_war_synth", "triumphant_brass"]),
]

NIGHTLY_TRACKS = 5
TRACK_SECONDS = 60.0


def _manifest() -> List[Dict]:
    return [t for t in state.read("music_library", []) if Path(t.get("file", "")).exists()]


def status() -> Dict:
    have = {t["mood_key"] for t in _manifest()}
    return {"tracks": len(_manifest()), "moods_covered": len(have), "moods_total": len(MOODS),
            "missing": [m for m in MOODS if m not in have]}


def _plan(n: int) -> List[str]:
    tracks = _manifest()
    have = {t["mood_key"] for t in tracks}
    missing = [m for m in MOODS if m not in have]
    if len(missing) >= n:
        return missing[:n]
    oldest = sorted(tracks, key=lambda t: t.get("created", 0))
    return missing + [t["mood_key"] for t in oldest][: n - len(missing)]


def build_overnight(max_tracks: int = NIGHTLY_TRACKS, generator=None) -> Dict:
    """Generates up to max_tracks tracks. Stops early if a heavy service is busy or a job is running."""
    from app.automation import jobs, resources
    if any(j["status"] == "running" for j in jobs.all_jobs()):
        return {"skipped": "a video job is running"}
    if resources.is_busy("phosphene"):
        return {"skipped": "Phosphene is rendering"}
    if generator is None:
        from agents.acestep_music_agent import ACEStepMusicAgent
        generator = ACEStepMusicAgent()
    made, errors = [], []
    for mood_key in _plan(max_tracks):
        spec = MOODS[mood_key]
        try:
            track = generator.generate_track(category=spec["category"], mood=spec["mood"], vocals="Instrumental",
                                             duration=TRACK_SECONDS, prompt=spec["prompt"],
                                             name=f"Library · {mood_key.replace('_', ' ').title()}")
        except resources.ResourceBusy as e:
            errors.append(str(e))
            break
        except Exception as e:
            errors.append(f"{mood_key}: {e}")
            continue
        entry = {"mood_key": mood_key, "file": track["file_path"], "name": track.get("name"),
                 "created": time.time(), "last_used": 0}
        replaced = [t for t in state.read("music_library", []) if t.get("mood_key") == mood_key]
        state.update("music_library", [], lambda lib: [t for t in lib if t.get("mood_key") != mood_key] + [entry])
        for old in replaced:  # refreshed mood: remove the superseded audio file
            try:
                Path(old["file"]).unlink()
            except OSError:
                pass
        made.append(mood_key)
    return {"generated": made, "errors": errors, **status()}


def pick(topic: str) -> Optional[Path]:
    """Least-recently-used library track whose mood suits the topic (None if the library is empty)."""
    tracks = _manifest()
    if not tracks:
        return None
    t_lower = f" {topic.lower()} "
    wanted = next((moods for keys, moods in TOPIC_MOODS if any(k in t_lower for k in keys)), ["cinematic_epic", "hybrid_trailer"])
    candidates = [t for t in tracks if t["mood_key"] in wanted] or tracks
    choice = min(candidates, key=lambda t: (t.get("last_used", 0), wanted.index(t["mood_key"]) if t["mood_key"] in wanted else 99))

    def mark(lib):
        for t in lib:
            if t.get("file") == choice["file"]:
                t["last_used"] = time.time()
        return lib
    state.update("music_library", [], mark)
    return Path(choice["file"])
