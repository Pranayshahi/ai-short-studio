"""WeaponX chart preview: build, replace a row (others kept), and the video uses exactly that chart."""
from pathlib import Path
from unittest import mock

from PIL import Image


def _fake_topic_list(calls):
    def fake(self, topic, dest, keep_titles=None, exclude_titles=None):
        calls.append({"keep": keep_titles, "exclude": exclude_titles})
        Image.new("RGB", (1080, 1920), "white").save(dest)
        names = [t for t in (keep_titles or []) if t not in (exclude_titles or [])] or ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
        while len(names) < 5:
            names.append(f"New{len(names)}")
        return {"source": "weaponx_lab_poster", "list_chart": True, "image_path": str(dest),
                "ranked_items": [{"name": n, "article": n, "country": "X", "year": 2000, "bullets": ["Range - 1 km"]} for n in names]}
    return fake


def test_build_replace_row_and_reuse(tmp_path):
    from agents.image_generator import ImageGeneratorAgent
    from app.automation import chart_preview
    calls = []
    with mock.patch.object(ImageGeneratorAgent, "_acquire_topic_list_poster", _fake_topic_list(calls)):
        meta = chart_preview.build("Cruise Missiles")
        assert Path(meta["path"]).exists() and len(meta["record"]["ranked_items"]) == 5
        meta2 = chart_preview.build("Cruise Missiles", preview_id=meta["id"], exclude=["Bravo"])
    assert meta2["id"] == meta["id"], "a row replacement updates the same preview"
    assert calls[1]["exclude"] == ["Bravo"] and "Bravo" not in calls[1]["keep"] and "Alpha" in calls[1]["keep"]
    assert chart_preview.load(meta["id"])["excluded"] == ["Bravo"]
    from agents import photo_library
    assert "Bravo" in [i["title"] for i in photo_library.listing() if i["status"] == "rejected"]


def test_video_uses_the_approved_chart(tmp_path):
    from agents.image_generator import ImageGeneratorAgent
    src = tmp_path / "approved.png"
    Image.new("RGB", (1080, 1920), (1, 2, 3)).save(src)
    preview = {"path": str(src), "record": {"source": "weaponx_lab_poster", "ranked_items": [{"name": "A"}] * 5}}
    dest = tmp_path / "hero.png"
    rec = ImageGeneratorAgent()._acquire_weaponx_lab_poster({}, "Cruise Missiles", [], {"chart_preview": preview}, [], set(), dest, [])
    assert rec["image_path"] == str(dest) and Image.open(dest).getpixel((5, 5)) == (1, 2, 3)


def test_api_and_generate_carry_the_preview(tmp_path):
    from starlette.testclient import TestClient
    from app import web_app as wa
    from agents.image_generator import ImageGeneratorAgent
    calls = []
    c = TestClient(wa.app)
    with mock.patch.object(ImageGeneratorAgent, "_acquire_topic_list_poster", _fake_topic_list(calls)):
        r = c.post("/api/chart-preview", json={"topic": "Cruise Missiles"})
    assert r.status_code == 200 and len(r.json()["rows"]) == 5, r.text
    pid = r.json()["preview_id"]
    assert c.get(f"/api/chart-preview/{pid}/image").status_code == 200
    assert c.post("/api/chart-preview", json={"topic": " "}).status_code == 400

    def prepare(**kw):
        rec = {"id": "qa_prev_proj", "topic": kw["custom_topic"], "status": "in_progress", "project_dir": str(tmp_path),
               "created_at": "2026-11-20T10:00:00", "updated_at": "2026-11-20T10:00:00"}
        wa.StorageManager.save_project(rec)
        return rec, {}
    with mock.patch.object(wa.pipeline, "prepare_project", side_effect=prepare), mock.patch.object(wa.pipeline, "run"):
        g = c.post("/api/generate", json={"topic": "Cruise Missiles", "style": "weaponx", "chart_preview_id": pid})
    assert g.status_code == 200
    assert wa.StorageManager.get_project_by_id("qa_prev_proj")["chart_preview_id"] == pid
