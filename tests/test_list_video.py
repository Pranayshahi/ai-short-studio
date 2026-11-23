"""Narrated list video: one scene per verified item, narration only says verified name + country."""
from pathlib import Path

from PIL import Image

from agents import list_video as lv


def _items(n=3):
    out = []
    for i in range(1, n + 1):
        row = {"rank": i, "name": f"Rifle X-{i}0", "country": "Austria", "year": "2004",
               "specs": {"_bullets": ["Range - 1,500 m", "Cartridge - .50 BMG"]}}
        out.append({"row": row, "model": {"title": f"Rifle X-{i}0", "image_file": f"r{i}.jpg"},
                    "photo": Image.new("RGB", (900, 300), (90, 90, 90)), "is_cut": False})
    return out


def test_spoken_names():
    assert lv.spoken("ASVK / KSVK") == "ASVK and KSVK"
    assert lv.spoken("Steyr HS .50") == "Steyr HS fifty"
    assert lv.spoken("MP-443 Grach (PYa)") == "MP-443 Grach"


def test_plan_and_frames(tmp_path):
    items = _items(10)
    scenes = lv.plan_scenes("World's Most Powerful Sniper Rifles", items, 25.0)
    assert len(scenes) == 12 and scenes[0]["list_scene"] == "intro" and scenes[-1]["list_scene"] == "outro"
    assert abs(sum(s["duration_seconds"] for s in scenes) - 25.0) < 0.6
    assert scenes[1]["narration"] == "Rifle X-10." and scenes[1]["caption_placement"] == "bottom"
    data = {"title": "World's Most Powerful Sniper Rifles", "items": items, "credits": [], "kind": "firearm"}
    rep = lv.build_visuals(tmp_path, scenes, data)
    assert len(rep["image_paths"]) == 12 and all(Image.open(p).size == (1080, 1920) for p in rep["image_paths"])
    rec = rep["visual_records"][0]
    assert len(rec["ranked_items"]) == 10 and rec["kind"] == "firearm" and all(r["source"] == "list_video" for r in rep["visual_records"])


def test_narration_passes_fact_check():
    from agents import fact_check as fc
    scenes = lv.plan_scenes("World's Most Powerful Sniper Rifles", _items(3), 25.0)
    for sc in scenes:
        assert not [n for n in fc.numbers(sc["narration"])], sc["narration"]  # names only: no unsupported numbers


def test_scene_cuts_follow_the_spoken_words():
    """Scene cuts come from the TTS word timings, not word-count estimates (pictures drifted from the voice)."""
    from app.agents.voice_agent import VoiceAgent
    scenes = [{"narration": "World's most powerful sniper rifles."}, {"narration": "Denel NTW-20."},
              {"narration": "Snipex Alligator."}, {"narration": "Which one would you pick?"}]
    words, t = [], 0.0
    for txt, dur in [("World's", .4), ("most", .3), ("powerful", .5), ("sniper", .4), ("rifles.", .5),
                     ("Denel", .4), ("NTW-20.", 1.1), ("Snipex", .5), ("Alligator.", .7),
                     ("Which", .3), ("one", .2), ("would", .2), ("you", .2), ("pick?", .4)]:
        words.append({"text": txt, "start": t, "end": t + dur}); t += dur + 0.05
    d = VoiceAgent._calculate_scene_durations(scenes, 25.0, words)
    starts = [round(sum(d[:i]), 2) for i in range(len(d))]
    assert abs(starts[1] - words[5]["start"]) < 0.02 and abs(starts[2] - words[7]["start"]) < 0.02
    assert abs(sum(d) - 25.0) < 0.05 and d[-1] > 15, "spare time goes to the last scene (the recap list)"
