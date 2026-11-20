"""Verified photo library: good cutouts are kept and reused (no download); rejected photos never return."""
from unittest import mock

from PIL import Image


def _cut(w=600, h=120):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.paste((200, 200, 200, 255), (10, 30, w - 10, h - 30))
    return im


def test_add_get_reject_restore():
    from agents import photo_library as pl
    assert pl.get("Test Missile X") is None
    assert pl.add("Test Missile X", "missile", _cut(), source_file="File:X.jpg")
    assert pl.get("Test Missile X") is not None
    assert not pl.add("Test Missile X", "missile", _cut(), source_file="File:Y.jpg"), "an approved photo is kept"
    pl.reject("Test Missile X")
    assert pl.get("Test Missile X") is None and "File:X.jpg" in pl.rejected_sources("Test Missile X")
    assert not pl.add("Test Missile X", "missile", _cut(), source_file="File:X.jpg"), "a rejected photo never comes back"
    assert pl.restore("Test Missile X") and pl.get("Test Missile X") is not None


def test_fetch_photo_uses_library_first(tmp_path):
    from agents import evolution_poster as ev, photo_library as pl
    pl.add("Test Missile Y", "missile", _cut(), source_file="File:Y.jpg")
    model = {"title": "Test Missile Y", "image_url": "https://example.invalid/y.jpg", "image_file": "Y.jpg", "_kind": "missile"}
    with mock.patch.object(ev, "_download", side_effect=AssertionError("downloaded although the library had it")):
        img, is_cut = ev.fetch_photo(model, tmp_path)
    assert img is not None and is_cut


def test_rejected_lead_photo_is_never_used(tmp_path):
    from agents import evolution_poster as ev, photo_library as pl
    pl.add("Test Missile Z", "missile", _cut(), source_file="Z.jpg")
    pl.reject("Test Missile Z")
    model = {"title": "Test Missile Z", "image_url": "https://example.invalid/z.jpg", "image_file": "Z.jpg", "_kind": "missile"}
    with mock.patch.object(ev, "_download", side_effect=AssertionError("re-downloaded the rejected photo")), \
         mock.patch.object(ev, "_commons_photos", return_value=[]):
        img, is_cut = ev.fetch_photo(model, tmp_path)
    assert img is None, "no other photo -> the model is skipped, not shown with the rejected one"


def test_new_good_cutout_joins_library(tmp_path):
    from agents import evolution_poster as ev, photo_library as pl
    model = {"title": "Test Tank Q", "image_url": "u", "image_file": "Q.jpg", "_kind": "vehicle"}
    (tmp_path / "Test_Tank_Q_cut.png").write_bytes(b"")
    _cut().save(tmp_path / "Test_Tank_Q_cut.png")
    img, is_cut = ev.fetch_photo(model, tmp_path)
    assert is_cut and pl.get("Test Tank Q") is not None


def test_library_api():
    from starlette.testclient import TestClient
    from app.web_app import app
    from agents import photo_library as pl
    pl.add("Test Api Photo", "missile", _cut(), source_file="A.jpg")
    c = TestClient(app)
    items = c.get("/api/photo-library").json()["items"]
    key = next(i["key"] for i in items if i["title"] == "Test Api Photo")
    assert c.get(f"/api/photo-library/{key}/image").status_code == 200
    assert c.post(f"/api/photo-library/{key}/reject").json()["status"] == "rejected"
    assert pl.get("Test Api Photo") is None
    assert c.post(f"/api/photo-library/{key}/restore").json()["status"] == "approved"
