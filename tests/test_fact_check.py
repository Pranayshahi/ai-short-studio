"""Every video's facts are verified or left out (owner's rule 2026-11-21). Offline: sources are mocked."""
from unittest import mock

from agents import fact_check as fc

DRONE = ("Unmanned combat aerial vehicle", "The Boeing MQ-28 Ghost Bat is a stealth, jet-powered unmanned aircraft. "
         "It has a range of 3,700 km and is 11.7 m long. It first flew in 2021.")
BAT = ("Species of bat", "The ghost bat is a species of bat found in northern Australia. The species has a prominent nose-leaf.")
RESEARCH = {"topic_subject": "Ghost Bat", "sources": [
    {"title": "Ghost bat", "url": "https://en.wikipedia.org/wiki/Ghost_bat", "snippet": "The ghost bat is a species of bat"},
    {"title": "Boeing MQ-28 Ghost Bat", "url": "https://en.wikipedia.org/wiki/Boeing_MQ-28_Ghost_Bat", "snippet": "drone"}]}


def _src(url):
    return BAT if url.endswith("/Ghost_bat") else DRONE


def test_numbers_are_unit_aware_and_skip_model_names():
    got = [(r, f) for _, f, r in fc.numbers("BGM-109G and T-90, a 4.0-litre flat-six, 386 kW, Mach 2.25, 1,500 built in 2014")]
    assert ("4.0-litre", "vol") in got and ("386 kW", "pow") in got and ("Mach 2.25", "mach") in got
    assert not any(r.startswith(("109", "90")) for r, _ in got), got
    pool = fc.numbers("386 kW (525 PS; 518 hp), 3,700 km")
    assert fc.number_supported(518, pool, "pow") and fc.number_supported(1.609 * 2299, pool, "len")
    assert not fc.number_supported(518, fc.numbers("518 units built"), "pow"), "a bare 518 doesn't confirm 518 hp"


def test_off_topic_source_and_sentence_removed_before_voiceover():
    sd = {"scenes": [
        {"narration": "The MQ-28 is a stealth unmanned aircraft.", "on_screen_text": "GHOST BAT"},
        {"narration": "It has a range of 3,700 km.", "on_screen_text": "RANGE 3,700 KM"},
        {"narration": "It is 15 m long.", "on_screen_text": "TOP SPEED 1,200 KM/H"},
        {"narration": "The species has a prominent nose-leaf.", "on_screen_text": "PART 4"},
        {"narration": "Could anything counter it? Drop your verdict below.", "on_screen_text": "GHOST BAT"}]}
    with mock.patch.object(fc, "source_text", _src):
        removed = fc.filter_script(sd, RESEARCH, "Ghost Bat")
    text = " ".join(s["narration"] for s in sd["scenes"])
    assert "nose-leaf" not in text and "15 m" not in text and "3,700 km" in text, text
    assert "Drop your verdict" in text, "a question / call to action is not a claim"
    assert any("Ghost bat" in r for r in removed), "the animal article is reported as an off-topic source"
    assert all("1,200" not in s["on_screen_text"] for s in sd["scenes"]), "unsupported caption number removed"


def test_finished_video_is_blocked_until_fixed():
    proj = {"style": "default", "topic": "Ghost Bat", "title": "Ghost Bat 🔥 #Shorts", "description": "The MQ-28 first flew in 2021.",
            "topic_research": RESEARCH,
            "scenes": [{"narration": "The species has a prominent nose-leaf."}, {"narration": "It first flew in 2021."}]}
    with mock.patch.object(fc, "source_text", _src):
        probs = fc.check_project(proj)
        from agents import render_guard as rg
        checks = rg.fact_checks(proj)
    assert any("nose-leaf" in p["detail"] for p in probs)
    narr = next(c for c in checks if c["name"].startswith("Facts: narration"))
    assert not narr["passed"] and narr["blocking"] and narr["fix"] == "remove_unverified_text"
    assert all(c["passed"] for c in checks if not c["name"].startswith("Facts: narration"))


def test_off_domain_descriptions():
    for d in ["Species of bat", "Indian footballer", "2019 film by X", "Village in Poland", "Album by Metallica"]:
        assert fc.off_domain(d), d
    for d in ["Unmanned combat aerial vehicle", "Main battle tank", "Sports car manufactured by Porsche"]:
        assert not fc.off_domain(d), d
