"""
Fresh, on-theme music for every car and weapon video, saved to the music library.

Before: weapon videos reused the same default library track every time, and car videos only got an
ACE-Step track if the ACE-Step server happened to be running already (otherwise a built-in synth),
and neither was saved to the library.

Now (fresh_theme_track):
  1. A theme prompt is built from the video: phonk in the chosen style for cars; for weapons, matched
     to the sub-genre (naval, air, armour, missiles, small arms) or a dark military trailer score.
  2. ACE-Step 1.5 generates a NEW track (started on demand and stopped afterwards by the memory manager).
     If it can't run, the built-in engines compose a new track instead (phonk synth / MusicAgent).
  3. The track is saved to the music library ("<topic> · <theme>") and the video uses that library copy.
A track the user explicitly picks for a video still wins (see ShortsPipeline.run).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# (pattern on topic/category, theme label, ACE-Step prompt, mood)
WEAPON_THEMES = [
    (r"submarine|naval|navy|warship|destroyer|frigate|carrier|torpedo|ship",
     "Naval Depths", "deep ominous naval score, sonar pings, sub bass pulses, low brass swells, slow war drums, "
                     "cold underwater atmosphere, cinematic tension", "Dark"),
    (r"\bf-?\d|jet|fighter|bomber|aircraft|air force|raptor|lightning|stealth|drone|uav|helicopter",
     "Sky Dominance", "soaring epic hybrid orchestral, fast driving strings, jet-age synth arps, big taiko hits, "
                      "heroic brass, high-energy trailer", "Epic"),
    (r"tank|armou?r|ifv|apc|artillery|howitzer|leopard|abrams|t-\d|infantry fighting|combat vehicle",
     "Armored Assault", "heavy industrial war percussion, distorted low brass, marching snares, metallic clanks, "
                        "relentless cinematic drive", "Aggressive"),
    (r"missile|hypersonic|icbm|rocket|nuclear|warhead",
     "Strike Countdown", "tense countdown pulses, rising synth risers, ticking clock percussion, massive impact hits, "
                         "dark cinematic electronic", "Tense"),
    (r"rifle|pistol|gun|carbine|sniper|firearm|small arms|ak-?47",
     "Tactical Ops", "gritty tactical percussion, dark synth bass, muted guitar chugs, suspenseful special-ops score",
     "Aggressive"),
]
DEFAULT_WEAPON_THEME = ("War Machine", "dark cinematic military trailer score, thunderous war drums, low brass, "
                        "tense strings, epic build", "Epic")
TECH_THEME = ("Future Tech", "cinematic modern electronic score, pulsing synths, clean percussion, sense of wonder, "
              "documentary trailer", "Inspiring")


def theme_for(topic: str, category: str = "", kind: str = "weapon", phonk_style: Optional[str] = None) -> Tuple[str, str, str]:
    """(theme label, generation prompt, mood) for the video."""
    if kind == "car":
        from agents.car_edit_agent import CarEditAgent
        style = phonk_style if phonk_style in CarEditAgent.PHONK_PROMPTS else "drift_phonk"
        label = style.replace("_", " ").title()
        return label, f"{CarEditAgent.PHONK_PROMPTS[style]}, car edit for {topic}", "Aggressive"
    text = f"{topic} {category}".lower()
    for pat, label, prompt, mood in WEAPON_THEMES:
        if re.search(pat, text):
            return label, f"{prompt}, for a YouTube Short about {topic}", mood
    if re.search(r"defen[cs]e|military|weapon|war|combat|army", text):
        label, prompt, mood = DEFAULT_WEAPON_THEME
    else:
        label, prompt, mood = TECH_THEME
    return label, f"{prompt}, for a YouTube Short about {topic}", mood


# ------------------------------------------------------------------ pre-made pool (option 2)
# Each theme keeps a few NEW tracks generated ahead of time (nightly). A video takes one; it is moved
# into the library under the video's name and never used again - so music stays new per video, but
# the ~3 min ACE-Step wait disappears.
POOL_STATE = "theme_music_pool"
USAGE_STATE = "theme_music_usage"
POOL_PER_THEME = 2
POOL_TRACK_SECONDS = 62.0


def _pool_dir() -> Path:
    import config
    d = config.AUDIO_ASSETS_DIR / "theme_pool"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pool_key(kind: str, label: str) -> str:
    return f"{kind}:{label}"


def pool_themes() -> List[Dict[str, Any]]:
    """Every theme the pool keeps tracks for (car phonk styles + weapon sub-genres)."""
    from agents.car_edit_agent import CarEditAgent
    out = [{"kind": "car", "label": st.replace("_", " ").title(), "phonk_style": st,
            "prompt": pr, "mood": "Aggressive", "genre": "EDM"} for st, pr in CarEditAgent.PHONK_PROMPTS.items()]
    for _, label, prompt, mood in WEAPON_THEMES:
        out.append({"kind": "weapon", "label": label, "prompt": prompt + ", for a defense technology YouTube Short",
                    "mood": mood, "genre": "Cinematic"})
    for label, prompt, mood in (DEFAULT_WEAPON_THEME, TECH_THEME):
        out.append({"kind": "weapon", "label": label, "prompt": prompt, "mood": mood, "genre": "Cinematic"})
    return out


def _pool() -> List[Dict[str, Any]]:
    from app.automation import state
    return [t for t in state.read(POOL_STATE, []) if Path(t.get("file", "")).exists()]


def pool_status() -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for t in _pool():
        counts[t["key"]] = counts.get(t["key"], 0) + 1
    themes = pool_themes()
    return {"tracks": sum(counts.values()), "per_theme": POOL_PER_THEME,
            "themes": {pool_key(t["kind"], t["label"]): counts.get(pool_key(t["kind"], t["label"]), 0) for t in themes}}


def take_from_pool(kind: str, label: str) -> Optional[Dict[str, Any]]:
    """Removes and returns the oldest pre-made track for the theme (atomic across processes)."""
    from app.automation import state
    key = pool_key(kind, label)
    taken: Dict[str, Any] = {}

    def pop(items):
        items = [t for t in items if Path(t.get("file", "")).exists()]
        mine = sorted((t for t in items if t.get("key") == key), key=lambda t: t.get("created", 0))
        if mine:
            taken.update(mine[0])
            items = [t for t in items if t is not mine[0]]
        return items
    state.update(POOL_STATE, [], pop)
    return taken or None


def _mark_used(kind: str, label: str) -> None:
    import time
    from app.automation import state
    key = pool_key(kind, label)
    state.update(USAGE_STATE, {}, lambda u: {**(u or {}), key: time.time()})


def refill_pool(max_tracks: int = 12, generator=None, deadline: Optional[float] = None) -> Dict[str, Any]:
    """Generates pre-made tracks for the themes that are short, most-recently-used themes first.
    Run at night by the scheduler (ACE-Step is started once and reused for every track)."""
    import time
    from app.automation import state
    if generator is None:
        from agents.acestep_music_agent import ACEStepMusicAgent
        generator = ACEStepMusicAgent()
    usage = state.read(USAGE_STATE, {}) or {}
    counts = pool_status()["themes"]
    need = [t for t in pool_themes() if counts.get(pool_key(t["kind"], t["label"]), 0) < POOL_PER_THEME]
    # empty themes first, then the ones videos use most recently
    need.sort(key=lambda t: (counts.get(pool_key(t["kind"], t["label"]), 0), -usage.get(pool_key(t["kind"], t["label"]), 0)))
    made, errors = [], []
    for t in need:
        if len(made) >= max_tracks or (deadline and time.time() > deadline):
            break
        key = pool_key(t["kind"], t["label"])
        try:
            res = generator.generate_track(category=t["genre"], mood=t["mood"], vocals="Instrumental",
                                           duration=POOL_TRACK_SECONDS, prompt=t["prompt"], name=f"Pool · {t['label']}")
            src = Path(res["file_path"])
            dest = _pool_dir() / f"{re.sub(r'[^a-z0-9]+', '_', key.lower())}_{int(time.time())}.wav"
            shutil.move(str(src), str(dest))
        except Exception as e:
            errors.append(f"{key}: {str(e)[:160]}")
            if "busy" in str(e).lower():
                break  # a video needs the machine: stop for tonight
            continue
        entry = {"key": key, "kind": t["kind"], "label": t["label"], "phonk_style": t.get("phonk_style"),
                 "prompt": t["prompt"], "file": str(dest), "created": time.time()}
        state.update(POOL_STATE, [], lambda items: list(items or []) + [entry])
        made.append(key)
    return {"generated": made, "errors": errors, **pool_status()}


def _generate_live(genre: str, mood: str, dur: float, prompt: str, name: str, wait_seconds: float) -> Optional[str]:
    """ACE-Step now. A busy machine (another model loaded) is waited for, up to wait_seconds, instead
    of dropping straight to the built-in synth."""
    import time
    from agents.acestep_music_agent import ACEStepMusicAgent
    from app.automation import resources
    deadline = time.time() + max(0.0, wait_seconds)
    while True:
        try:
            res = ACEStepMusicAgent().generate_track(category=genre, mood=mood, vocals="Instrumental",
                                                     duration=dur, prompt=prompt, name=name)
            return res.get("file_path") if res and Path(res.get("file_path") or "").exists() else None
        except resources.ResourceBusy as e:
            if time.time() > deadline:
                print(f"[ThemeMusic] ACE-Step still blocked ({e}); composing with the built-in engine.")
                return None
            time.sleep(5)
        except Exception as e:
            print(f"[ThemeMusic] ACE-Step unavailable ({str(e)[:120]}); composing with the built-in engine.")
            return None


def fresh_theme_track(topic: str, duration: float, kind: str = "weapon", category: str = "",
                      phonk_style: Optional[str] = None, wait_seconds: float = 0.0) -> Optional[Dict[str, Any]]:
    """A NEW on-theme track for this video, saved to the library: a pre-made pool track when one is
    ready (instant), else generated now (ACE-Step, else the built-in engines). None only if all fail."""
    label, prompt, mood = theme_for(topic, category, kind, phonk_style)
    dur = max(12.0, min(120.0, float(duration or 20.0) + 2.0))
    name = f"{topic[:40]} · {label}"
    genre = "EDM" if kind == "car" else "Cinematic"
    src: Optional[str] = None
    engine = None
    _mark_used(kind, label)

    pooled = take_from_pool(kind, label) if dur <= POOL_TRACK_SECONDS + 2 else None
    if pooled:
        src, engine = pooled["file"], "ACE-Step 1.5 (pre-made)"
        prompt = pooled.get("prompt") or prompt
        print(f"[ThemeMusic] 🎵 Using a pre-made, never-used '{label}' track (no wait)")

    if not src:
        print(f"[ThemeMusic] 🎵 Generating a new '{label}' track for '{topic}' with ACE-Step...")
        src = _generate_live(genre, mood, dur, prompt, name, wait_seconds)
        engine = "ACE-Step 1.5" if src else None

    # Built-in engines: still a NEW track each time
    if not src:
        try:
            if kind == "car":
                import time
                import config
                from agents.car_edit_agent import CarEditAgent
                out_dir = config.AUDIO_ASSETS_DIR / "ai_generated"
                out_dir.mkdir(parents=True, exist_ok=True)
                slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")[:24] or "car"
                out = out_dir / f"phonk_{slug}_{int(time.time())}.wav"
                CarEditAgent._synthesize_drift_phonk_wav(out, duration=dur, style=phonk_style or "drift_phonk")
                src, engine = str(out), "Built-in phonk synth"
            else:
                from agents.music_agent import MusicAgent
                res = MusicAgent().generate_track(category=genre, mood=mood, vocals="Instrumental",
                                                  duration=dur, prompt=prompt, name=name)
                src, engine = res.get("file_path"), "Built-in MusicAgent"
        except Exception as e:
            print(f"[ThemeMusic] Built-in composer failed: {e}")
    if not src or not Path(src).exists():
        return None

    # Save to the library (the video uses that copy); a pool file is consumed, never reused
    from agents.music_generator import AIMusicGenerator
    rec = AIMusicGenerator().save_to_library(source_path_or_id=src, name=name, category=genre, mood=mood,
                                             vocals="Instrumental", duration=dur, prompt=prompt, is_default=False)
    if pooled:
        Path(src).unlink(missing_ok=True)
    rec.update(engine=engine, theme=label)
    print(f"[ThemeMusic] ✓ New track '{name}' ({engine}) saved to the music library as {rec.get('id')}")
    return rec
