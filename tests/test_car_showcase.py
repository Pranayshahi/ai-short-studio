"""Full-car showcase: only complete cars qualify; rendered 1080x1920; inserted as scenes; credited."""
import json
import subprocess
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw


def _photo(car_box):
    im = Image.new("RGB", (1024, 640), (90, 110, 130))
    ImageDraw.Draw(im).rectangle(car_box, fill=(200, 20, 20))
    return im


def _fake_cutout(photo, with_box=False):
    # the "car" is the red rectangle drawn by _photo
    px = photo.load()
    xs = [x for x in range(photo.width) for y in (photo.height // 2,) if px[x, y][0] > 150]
    ys = [y for y in range(photo.height) for x in (photo.width // 2,) if px[x, y][0] > 150]
    if not xs or not ys:
        return None
    box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    cut = photo.crop(box).convert("RGBA")
    return (cut, box) if with_box else cut


def test_only_complete_cars_qualify():
    from agents import car_showcase as cs, evolution_poster as ev
    with mock.patch.object(ev, "_cutout", _fake_cutout), mock.patch.object(ev, "_exterior_ok", lambda *a, **k: True):
        assert cs.full_car_cutout(_photo((150, 220, 870, 520))) is not None, "a whole car in frame qualifies"
        assert cs.full_car_cutout(_photo((0, 220, 700, 520))) is None, "clipped by the photo edge = not the full car"
        assert cs.full_car_cutout(_photo((450, 250, 560, 330))) is None, "too small"
        assert cs.full_car_cutout(_photo((420, 60, 600, 600))) is None, "tall shape = not a whole-car view"


def test_render_and_attach(tmp_path):
    from agents import car_showcase as cs, evolution_poster as ev
    (tmp_path / "scenes").mkdir()
    photo = _photo((150, 220, 870, 520))
    scenes, paths, recs = [], [], []
    for i in range(1, 6):
        p = tmp_path / "scenes" / f"scene_{i:02d}.png"
        Image.new("RGB", (1080, 1920), (i * 30, 40, 60)).save(p)
        scenes.append({"scene_number": i, "duration_seconds": 1.8, "beat_synced": True, "image_path": str(p)})
        paths.append(str(p))
        recs.append({"scene_number": i, "image_path": str(p), "source": "web_free", "author": f"A{i}",
                     "license": "CC BY 2.0", "source_url": f"https://example.invalid/{i}.jpg", "page_url": f"https://flickr.example/{i}"})
    with mock.patch.object(cs, "_download", lambda url: photo), mock.patch.object(ev, "_cutout", _fake_cutout), \
         mock.patch.object(ev, "_exterior_ok", lambda *a, **k: True):
        res = cs.attach(tmp_path, scenes, paths, recs, {"car_name": "Testcar GT", "bpm": 130, "subtitle_spec": "4.0L V8"}, "Testcar GT")
    assert res["added"] == 2 and len(scenes) == 7 and len(paths) == 7
    shows = [s for s in scenes if s.get("title_card") == "showcase"]
    assert len(shows) == 2 and all(Path(s["clip_path"]).exists() for s in shows)
    assert [s["scene_number"] for s in scenes] == list(range(1, 8))
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", shows[0]["clip_path"]],
                                     capture_output=True, text=True).stdout)
    v = info["streams"][0]
    assert (v["width"], v["height"]) == (1080, 1920) and abs(float(info["format"]["duration"]) - cs.showcase_seconds(130)) < 0.15
    from app.agents.pipeline import photo_credit_lines
    assert any("A" in c for c in photo_credit_lines(recs)), "showcase photographers are credited"
    assert sum(1 for r in recs if r["source"] == "car_showcase") == 2


def test_no_full_car_photo_means_no_showcase(tmp_path):
    from agents import car_showcase as cs
    (tmp_path / "scenes").mkdir()
    with mock.patch.object(cs, "pick_full_car_photos", lambda recs, n=2: []):
        res = cs.attach(tmp_path, [], [], [], {"bpm": 130}, "X")
    assert res == {"added": 0, "seconds": 0.0}
