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
