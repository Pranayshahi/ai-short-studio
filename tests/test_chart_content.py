"""WeaponX list charts must list the RIGHT kind of system (regressions found 2026-11-21):
'Modern Main Battle Tanks' listed IFVs + the NLAW anti-tank missile and no tanks at all ('battle' was
treated as an event); handguns listed cartridges; aircraft infobox fields weren't read."""
from agents import equipment_catalog as ec
from agents import ranked_poster as rp
from agents import topic_weapon_list as t


def ok(topic, title, typ, lead="", year=2000):
    kind = t.kind_for(topic)
    return t._is_kind({"title": title, "type": typ, "lead": lead, "image_url": "x", "origin": "X", "year": year},
                      kind, rp.KINDS[kind]["kind_re"], t.subtype_for(topic))


def test_tanks_chart_lists_only_tanks():
    topic = "Modern Main Battle Tanks"
    assert ok(topic, "Leopard 2", "Main battle tank") and ok(topic, "M1 Abrams", "Main battle tank")
    for title, typ in [("Borsuk", "Infantry fighting vehicle"), ("NLAW", "Anti-tank missile"),
                       ("Type 05", "Amphibious assault vehicle"), ("M2 Bradley", "Infantry fighting vehicle")]:
        assert not ok(topic, title, typ), title


def test_handguns_not_cartridges_or_rifles():
    topic = "Best Handguns"
    assert ok(topic, "Glock 17", "Semi-automatic pistol") and ok(topic, "Colt Detective Special", "Revolver")
    for title, typ in [(".45 ACP", "Pistol"), (".40 S&W", "Pistol"), ("9×19mm Parabellum", "Pistol"),
                       ("AK-47", "Assault rifle"), ("MP5", "Submachine gun")]:
        assert not ok(topic, title, typ), title


def test_aircraft_topics():
    assert ok("Attack Helicopters", "AH-64 Apache", "Attack helicopter")
    assert not ok("Attack Helicopters", "Sikorsky S-70", "Medium-lift transport/utility helicopter")
    assert ok("Stealth Fighter Jets", "F-22 Raptor", "Air superiority fighter", lead="a stealth tactical fighter")
    assert not ok("Stealth Fighter Jets", "F-15E Strike Eagle", "Multirole strike fighter", lead="an all-weather fighter")
    assert not ok("Stealth Fighter Jets", "Fourth-generation fighter", "Fighter aircraft", lead="stealth")
    assert not ok("Stealth Fighter Jets", "B-21 Raider", "Stealth strategic bomber", lead="stealth bomber")
    assert ok("Modern Missiles", "BrahMos", "Supersonic cruise missile")
    assert not ok("Modern Missiles", "2026 Minab school attack", "Missile strike")


def test_aircraft_infobox_fields_are_read():
    wt = "{{Infobox aircraft\n |name = AH-64 Apache\n |aircraft_type = [[Attack helicopter]]\n |national origin = United States\n |introduction = {{start date|1986|4}}\n}}"
    fb = ec._infobox(wt)
    assert fb.get("national_origin") == "United States"
    assert ec._origin(fb) == "United States" and ec._service_year(fb) == 1986


CHATGPT_LIST = """Top 20 Main Battle Tanks in the World – 2026
Here is a list of 20 of the world's most advanced Main Battle Tanks (MBTs) in 2026.

Note: This is an editorial ranking.

1. Leopard 2A8

Germany 🇩🇪

Latest-generation Leopard with advanced armour.

2. M1A2 Abrams SEPv3

United States 🇺🇸

Powerful 120 mm gun.

3. K2 Black Panther
South Korea 🇰🇷
4. Merkava Mk4 Barak
Israel 🇮🇱
5. T-90M Proryv
Russia 🇷🇺
6. Challenger 3
United Kingdom 🇬🇧
"""


def test_chatgpt_style_list_is_read():
    p = rp.parse_ranked_list(CHATGPT_LIST)
    assert rp.is_ranked_list(CHATGPT_LIST)
    assert p["title"] == "Top 20 Main Battle Tanks in the World"
    assert [i["name"] for i in p["items"]][:3] == ["Leopard 2A8", "M1A2 Abrams SEPv3", "K2 Black Panther"]
    assert p["items"][0]["country"] == "Germany" and p["items"][0]["note"].startswith("Latest-generation")


def test_variant_names_fall_back_to_the_base_article():
    for name, base in [("Leopard 2A8", "Leopard 2"), ("T-72B3M", "T-72"), ("Merkava Mk4 Barak", "Merkava"),
                       ("Type 99A", "Type 99"), ("T-80BVM", "T-80"), ("T-90M Proryv", "T-90")]:
        assert base in rp._simplify(name), (name, rp._simplify(name))


def test_list_keeps_user_order_and_skips_unverifiable(monkeypatch, tmp_path):
    arts = {"Leopard 2A8": ("Leopard 2", 1979), "M1A2 Abrams SEPv3": ("M1 Abrams", 1980), "K2 Black Panther": ("K2 Black Panther", 2014),
            "T-90M Proryv": ("T-90", 1992), "Challenger 3": ("Challenger 3", 2027)}

    def fake_match(name, words, kind):
        if name not in arts:
            return None  # 'Merkava Mk4 Barak' can't be verified here
        t, y = arts[name]
        return {"title": t, "type": "Main battle tank", "origin": "X", "year": y, "image_url": "x", "specs": {}}
    monkeypatch.setattr(rp, "match_article", fake_match)
    monkeypatch.setattr(rp, "render", lambda chart, resolved, out, cache: {"path": str(out), "rows": len(resolved), "photos": 0})
    monkeypatch.setattr(rp.ev, "photo_credits", lambda x: [])
    monkeypatch.setattr(rp.time, "sleep", lambda s: None)
    r = rp.make_poster(CHATGPT_LIST, tmp_path / "c.png", tmp_path)
    assert [i["name"] for i in r["items"]] == ["Leopard 2A8", "M1A2 Abrams SEPv3", "K2 Black Panther", "T-90M Proryv", "Challenger 3"]
    assert r["items"][0]["year"] == "" and r["items"][2]["year"] == "2014", "base-model year never shown for a variant"
    assert any("Merkava" in s for s in r["skipped"])
    r2 = rp.make_poster(CHATGPT_LIST + "7. Type 10\nJapan\n", tmp_path / "c.png", tmp_path, exclude=["M1 Abrams"])
    assert "M1A2 Abrams SEPv3" not in [i["name"] for i in r2.get("items", [])]


def test_family_key_and_top_n():
    assert t.family_key("Leopard 2E") == t.family_key("Leopard 2A4M CAN") == t.family_key("Leopard 2")
    assert t.family_key("Challenger 2") != t.family_key("Challenger 3")
    assert t.family_key("Type 99 tank") == t.family_key("Type 99A")
    assert t.top_n("Top 10 Main Battle Tanks") == 10 and t.top_n("Modern tanks") is None


def test_numbers_on_charts_are_right_or_absent():
    """2026-11-21: 'T-14 Armata - Range 5 km' was published (the article's 'range' field is the GUN's range;
    the tank's is vehicle_range = 500 km). A wrong number is worse than a missing one."""
    fb = ec._infobox("{{Infobox weapon\n| vehicle_range = Min. {{convert|500|km|mi}}<ref name=a/>\n"
                     "| range = 5 km, [[Uralvagonzavod]] claims\n| speed = {{convert|75|–|80|km/h}} (estimated)\n"
                     "| number = Over 200,000<ref>x</ref>\n}}")
    sp = ec._specs(fb)
    m = {"_kind": "vehicle", "specs": sp, "year": 2015}
    good = t.checked_specs(m)
    assert good.get("Range") == "at least 500 km", good
    assert "Speed" not in good, "estimated values are never shown"
    assert sp.get("No. built") == "over 200,000"
    assert ec._metric("300 mi") == "483 km" and ec._metric("30 mph") == "48 km/h"
    # out-of-range or wrong-unit values are dropped, per kind
    assert "Range" not in t.checked_specs({"_kind": "vehicle", "specs": {"Vehicle range": "5 km"}})
    assert "Range" not in t.checked_specs({"_kind": "firearm", "specs": {"Range": "50 km"}})
    assert t.checked_specs({"_kind": "firearm", "specs": {"Range": "600 m"}})["Range"] == "600 m"
    # never a future (planned) service year
    assert t.shown_year({"year": 2027}) == "" and t.shown_year({"year": 2014}) == "2014"
    b1, b2 = t._bullets({"_kind": "vehicle", "specs": {}, "type": "Main battle tank", "year": 2027})
    assert "2027" not in b1 + b2
    assert "at least at least" not in ec._specs(ec._infobox("{{I\n| range = At least 200 km\n}}")).get("Range", "").lower()


def test_top_n_matches_rows_shown():
    assert t.fix_top_n("Top 10 Main Battle Tanks", 8) == "Top 8 Main Battle Tanks"
    assert t.fix_top_n("TOP 10 MOST ADVANCED APCS", 10) == "TOP 10 MOST ADVANCED APCS"
    from app.agents.pipeline import attach_visual_metadata
    sd = {"title": "Top 10 Tanks: WeaponX Lab Breakdown 🔥 #Shorts", "description": "#Shorts",
          "scenes": [{"on_screen_text": "TOP 10 TANKS", "narration": "this is Top 10 Tanks."}]}
    rec = {"source": "weaponx_lab_poster", "image_path": "x", "ranked_items": [{"rank": i, "name": f"T{i}", "country": "X", "year": "", "bullets": []} for i in range(1, 9)]}
    attach_visual_metadata(sd, [rec])
    assert sd["title"].startswith("Top 8") and sd["scenes"][0]["on_screen_text"] == "TOP 8 TANKS" and "Top 8" in sd["scenes"][0]["narration"]
