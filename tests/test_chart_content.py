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


SPETSNAZ = """Weapons Used by Russian Spetsnaz – 2026

1. AK-12
Assault Rifle
- Calibre: 5.45×39mm
- Status: Operational

2. AS Val
- Calibre: 9×39mm
- Status: Operational

3. VSS Vintorez
- Calibre: 9×39mm
- Status: Operational
"""


def test_firearm_list_with_calibre_lines(monkeypatch, tmp_path):
    """'Weapons Used by Russian Spetsnaz' + 'Calibre:' lines is a FIREARM list (was read as missiles, and
    'Assault Rifle' became AK-12's country); two weapons sharing one article each get a row."""
    arts = {"AK-12": {"title": "AK-12", "type": "Assault rifle", "origin": "Russia", "year": 2018, "image_url": None, "specs": {}},
            "AS Val": {"title": "AS Val and VSS Vintorez", "type": "Assault rifle (AS Val)", "origin": "Soviet Union", "year": None,
                       "image_url": "x", "image_file": "AS_Val_&_VSS_Vintorez_noBG.png", "specs": {"Cartridge": "9×39mm", "Range": "400 m"}},
            "VSS Vintorez": None}
    arts["VSS Vintorez"] = arts["AS Val"]
    monkeypatch.setattr(rp, "match_article", lambda name, words, kind: dict(arts[name]) if arts.get(name) else None)
    monkeypatch.setattr(rp, "render", lambda chart, resolved, out, cache: {"path": str(out), "rows": len(resolved), "photos": 0})
    monkeypatch.setattr(rp.ev, "photo_credits", lambda x: [])
    monkeypatch.setattr(rp.time, "sleep", lambda s: None)
    spetsnaz = SPETSNAZ + "4. SR-3 Vikhr\n- Calibre: 9×39mm\n5. SV-98\n- Calibre: 7.62×54mmR\n"
    arts["SR-3 Vikhr"] = {"title": "SR-3 Vikhr", "type": "Assault rifle", "origin": "Russia", "year": 1996, "image_url": "x", "specs": {}}
    arts["SV-98"] = {"title": "SV-98", "type": "Sniper rifle", "origin": "Russia", "year": 2003, "image_url": "x", "specs": {}}
    r = rp.make_poster(spetsnaz, tmp_path / "c.png", tmp_path)
    assert r["kind"] == "firearm", r
    names = [i["name"] for i in r["items"]]
    assert names[:3] == ["AK-12", "AS Val", "VSS Vintorez"], (names, r.get("skipped"))
    assert r["items"][0]["country"] == "Russia", "'Assault Rifle' is not a country"
    assert all(i["article"] == "AS Val and VSS Vintorez" for i in r["items"][1:3])
    assert all(b.startswith("Cartridge") for i in r["items"][1:3] for b in i["bullets"]), "shared article: cartridge only"


def test_firearm_photo_view_rules():
    from PIL import Image, ImageDraw
    from agents import evolution_poster as ev
    side = Image.new("RGBA", (600, 120), (0, 0, 0, 0)); ImageDraw.Draw(side).rectangle((0, 40, 599, 80), fill=(20, 20, 20, 255))
    front = Image.new("RGBA", (200, 220), (0, 0, 0, 0)); ImageDraw.Draw(front).ellipse((30, 20, 170, 200), fill=(20, 20, 20, 255))
    rifle = {"type": "Sniper rifle"}
    assert ev.firearm_view_ok(side, rifle) and not ev.firearm_view_ok(front, rifle), "front views are not side views"
    assert ev.firearm_view_ok(front, {"type": "Semi-automatic pistol"}), "pistols are compact"
    # cut through the body at the photo's right edge vs a thin muzzle touching it
    assert not ev.firearm_view_ok(side, rifle, box=(10, 0, 1000, 120), size=(1000, 400))


def test_conditional_ranges_are_not_shown_as_one_number():
    """SV-98: '600 m iron sights / 1000 m scope' -> no single 'Range'; max_range is labelled 'Max range'."""
    fb = ec._infobox("{{Infobox weapon\n| range = {{convert|600|m|yd}} iron sights<br/>{{convert|1000|m|yd}} with scope\n"
                     "| max_range = over {{convert|2000|m|yd}}\n}}")
    sp = ec._specs(fb)
    assert "Range" not in sp and sp.get("Max range") == "over 2,000 m", sp
    assert ec._specs(ec._infobox("{{I\n| range = {{convert|300|m|yd}}\n}}")).get("Range") == "300 m"


def test_list_chart_records_its_kind_and_list():
    import inspect
    from app.automation import chart_preview
    src = inspect.getsource(chart_preview.build)
    assert '"kind": res.get("kind")' in src and '"ranked_list": ranked_list' in src
