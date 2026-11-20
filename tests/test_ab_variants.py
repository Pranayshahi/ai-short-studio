"""A/B test kit: 3 distinct, grounded titles and 3 clean 1080x1920 thumbnails per video."""
from PIL import Image


def _proj(tmp_path, chart=False):
    sd = tmp_path / "scenes"
    sd.mkdir()
    paths = []
    for i in range(1, 4):
        p = sd / f"scene_{i:02d}.png"
        Image.new("RGB", (1080, 1920), (40 * i, 90, 140)).save(p)
        paths.append(str(p))
    proj = {"id": "ab1", "project_dir": str(tmp_path), "image_paths": paths, "topic": "Ferrari F80"}
    if chart:
        proj.update(style="weaponx", topic="Cruise Missiles", title="Cruise Missiles: WeaponX Lab Breakdown 🔥 #Shorts",
                    visual_records=[{"source": "weaponx_lab_poster", "ranked_items": [{"name": n} for n in ("Tomahawk", "Kalibr", "Storm Shadow")]}])
    else:
        proj.update(style="car_edit", is_car_edit=True, title="Ferrari F80 — 3.0L TWIN-TURBO V6 HYBRID 🔥 #Shorts",
                    car_edit_plan={"car_name": "Ferrari F80", "subtitle_spec": "3.0L TWIN-TURBO V6 HYBRID"})
    return proj


def test_car_kit(tmp_path):
    from app.agents import ab_variants as ab
    kit = ab.build(_proj(tmp_path))
    assert len(kit["titles"]) == 3 and len({t.lower() for t in kit["titles"]}) == 3
    assert all(t.endswith("#Shorts") and len(t) <= 100 and "Ferrari F80" in t for t in kit["titles"])
    assert len(kit["thumbnails"]) == 3 and all(Image.open(t).size == (1080, 1920) for t in kit["thumbnails"])


def test_chart_kit_keeps_the_chart_whole(tmp_path):
    from app.agents import ab_variants as ab
    kit = ab.build(_proj(tmp_path, chart=True))
    assert any("3 Cruise Missiles compared" in t for t in kit["titles"]), kit["titles"]
    assert any("Tomahawk vs Storm Shadow" in t for t in kit["titles"])
    assert len(kit["thumbnails"]) == 3


def test_kit_api(tmp_path):
    from unittest import mock
    from starlette.testclient import TestClient
    from app import web_app as wa
    proj = _proj(tmp_path)
    with mock.patch.object(wa.StorageManager, "get_project_by_id", lambda pid: proj):
        c = TestClient(wa.app)
        r = c.get("/api/projects/ab1/ab-variants")
        assert r.status_code == 200 and len(r.json()["titles"]) == 3
        assert c.get(r.json()["thumbnails"][0]).status_code == 200
        assert c.get("/api/projects/ab1/ab-variants/thumb/9").status_code == 404
