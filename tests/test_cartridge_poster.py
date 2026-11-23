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


def test_photo_rules():
    """Only ONE complete round of THIS cartridge: no cut-open / 3D-render / group pictures, label must match."""
    assert cp._mentions("File:5.45x39.jpg", "5.45×39mm") and not cp._mentions("File:7.62x39.jpg", "5.45×39mm")
    for bad in ["File:5.56×45mm NATO cross section (3D model).png", "File:6.8 SPC + 223.jpg", "File:Five bullets.jpg",
                "File:SR-3 rifle.jpg", "File:9x39 cutaway.jpg"]:
        assert cp._MULTI.search(bad), bad
    assert not cp._MULTI.search("File:7.62x39 - FMJ - 4.jpg")


def test_proportion_check_rejects_wrong_shapes():
    from PIL import Image, ImageDraw
    dims = {"length": 56.0, "rim_dia": 11.33, "base": 11.33}
    rod = Image.new("RGB", (1000, 1000), "white")
    ImageDraw.Draw(rod).rectangle((100, 400, 900, 600), fill=(180, 90, 40))  # 4:1, a cartridge here is ~4.9:1 -> ok-ish
    sq = Image.new("RGB", (1000, 1000), "white")
    ImageDraw.Draw(sq).rectangle((300, 300, 700, 700), fill=(180, 90, 40))
    with mock.patch("agents.evolution_poster._cutout", lambda img, with_box=False: img.convert("RGBA").crop(img.convert("L").point(lambda v: 255 if v < 250 else 0).getbbox())):
        assert cp.normalize_cutout(sq, dims) is None, "a square blob is not a cartridge"


def test_commons_search_avoids_blocked_host():
    """commons.wikimedia.org is reset by this network: Commons search goes through api.wikimedia.org,
    file details through en.wikipedia.org."""
    import inspect
    from agents.image_generator import ImageGeneratorAgent
    src = inspect.getsource(ImageGeneratorAgent._commons_query)
    assert "api.wikimedia.org/core/v1/commons/search/page" in src and "en.wikipedia.org/w/api.php" in src
    assert "commons.wikimedia.org/w/api.php" not in inspect.getsource(ImageGeneratorAgent)
    assert "api.wikimedia.org/core/v1/commons/search/page" in inspect.getsource(cp.commons_search)


def test_blank_and_tiny_photos_rejected():
    assert cp._MULTI.search("File:Blank cartridge 7.62 x 51mm.jpg") and cp._MULTI.search("File:5.56 dummy round.jpg")
    from PIL import Image, ImageDraw
    small = Image.new("RGB", (240, 160), "white")
    ImageDraw.Draw(small).rectangle((10, 70, 190, 90), fill=(180, 90, 40))  # right shape, but only 180 px long
    dims = {"length": 57.4, "rim_dia": 9.6, "base": 9.58}
    with mock.patch("agents.evolution_poster._cutout", lambda img, with_box=False: img.convert("RGBA").crop(img.convert("L").point(lambda v: 255 if v < 250 else 0).getbbox())):
        assert cp.normalize_cutout(small, dims) is None
