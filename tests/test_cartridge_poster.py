"""Cartridge size chart: sizes from Wikipedia infoboxes (inch/mm), drawn to scale, verified."""
from unittest import mock

from agents import cartridge_poster as cp


def test_dimension_units():
    assert cp._mm("{{convert|9.27|mm|in|abbr=on}}") == 9.27
    assert abs(cp._mm(".3078") - 7.818) < 0.01 and abs(cp._mm("2.800") - 71.12) < 0.01
    assert cp._mm("44.70") == 44.70 and abs(cp._mm("0.308 in (7.82 mm)") - 7.82) < 0.01
    assert cp._mm("") is None


def test_render_to_scale(tmp_path):
    rows = [{"name": "Long", "dims": {"bullet": 7.8, "neck": 8.7, "shoulder": 11.5, "base": 11.9, "rim_dia": 12.0,
                                      "case_length": 51.2, "length": 71.1}, "rifles": 3, "origin": "", "year": ""},
            {"name": "Short", "dims": {"bullet": 5.7, "neck": 6.4, "shoulder": 9.0, "base": 9.6, "rim_dia": 9.6,
                                       "case_length": 44.7, "length": 57.4}, "rifles": 91, "origin": "", "year": ""}]
    res = cp.render(rows, tmp_path / "c.png", "T", "s")
    assert res["rows"] == 2
    a, b = cp.draw_cartridge(rows[0]["dims"], 6), cp.draw_cartridge(rows[1]["dims"], 6)
    assert abs(a.width / b.width - (71.1 + 1.33) / (57.4 + 1.33)) < 0.03, "same scale for every cartridge"


def test_verify_items_catches_changed_numbers():
    facts = {"5.56×45mm NATO": {"article": "5.56×45mm NATO", "dims": {"length": 57.4, "bullet": 5.7, "case_length": 44.7, "base": 9.58}}}
    with mock.patch.object(cp, "cartridge_facts", lambda titles: facts):
        ok = [{"name": "5.56×45mm NATO", "article": "5.56×45mm NATO", "dims": {"length": 57.4, "bullet": 5.7, "case_length": 44.7, "base": 9.58}}]
        bad = [{"name": "5.56×45mm NATO", "article": "5.56×45mm NATO", "dims": {"length": 60.0, "bullet": 5.7, "case_length": 44.7, "base": 9.58}}]
        assert cp.verify_items(ok) == [] and cp.verify_items(bad)


def test_weaponx_chart_mode_is_not_only_10_seconds():
    """A 15 s WeaponX request became a generic multi-scene video without the chart (static mode was == 10.0)."""
    import inspect
    from agents import content_analyser, image_generator
    src = inspect.getsource(content_analyser) + inspect.getsource(image_generator)
    assert "duration == 10.0" not in src and "target_dur == 10.0" not in src


def test_cartridge_topics_route_to_the_size_chart():
    import re
    from agents import image_posters
    src = open(image_posters.__file__).read()
    assert "_acquire_cartridge_poster(dest_path)" in src
    pat = r"\b(?:cartridges?|bullets?|ammunition|ammo|rounds?|calibers?|calibres?)\b"
    assert re.search(pat, "All Bullets Used in Assault Rifles Worldwide", re.I)
