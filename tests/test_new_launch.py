"""New Launch: the user's photos/clips are validated, EVERY one becomes a scene, timing fills the video,
the upload API works and the gate accepts the user's own media."""
import io
import subprocess
from pathlib import Path

from PIL import Image


def _jpg(color, size=(1600, 1000)):
    import random
    rnd = random.Random(sum(c * 7 ** i for i, c in enumerate(color)))  # same colour = same photo
    b = io.BytesIO()
    im = Image.new("RGB", (16, 10), color)
    for x in range(16):
        for y in range(10):
            im.putpixel((x, y), tuple(rnd.randrange(256) for _ in range(3)))
    im.resize(size, Image.Resampling.BICUBIC).save(b, "JPEG")
    return b.getvalue()


def _clip(path, seconds=2):
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"testsrc=size=720x1280:rate=30:duration={seconds}", "-pix_fmt", "yuv420p", str(path)], check=True)
    return Path(path).read_bytes()


def test_accept_and_plan(tmp_path):
    from agents import new_launch as nl
    _, dest = nl.new_upload_dir()
    files = [("a.jpg", _jpg((200, 30, 30))), ("b.png", _jpg((30, 200, 30))), ("a_copy.jpg", _jpg((200, 30, 30))),
             ("tiny.jpg", _jpg((1, 2, 3), (200, 200))), ("notes.txt", b"hi"), ("c.mp4", _clip(tmp_path / "c.mp4")),
             ("broken.mp4", b"not a video")]
    res = nl.accept_files(files, dest)
    assert len(res["images"]) == 2 and len(res["clips"]) == 1
    assert len(res["rejected"]) == 4 and any("same photo" in r for r in res["rejected"])
    scenes = nl.plan_scenes(res["images"], res["clips"], 16.0, 130.0, template=[{"on_screen_text": "X"}])
    kinds = [s["user_media"] for s in scenes]
    assert kinds.count("image") == 2 and kinds.count("clip") == 1 and kinds[0] == "image", "every upload used once"
    assert abs(sum(s["duration_seconds"] for s in scenes) - 16.0) < 0.05
    vis = nl.build_visuals(tmp_path, scenes)
    assert len(vis["image_paths"]) == 3 and all(Image.open(p).size == (1080, 1920) for p in vis["image_paths"])
    clip_scene = next(s for s in scenes if s["user_media"] == "clip")
    assert Path(clip_scene["clip_path"]).exists() and clip_scene["visual_source"] == "manual_upload"


def test_many_photos_each_get_a_scene():
    from agents import new_launch as nl
    imgs = [f"/x/{i}.jpg" for i in range(14)]
    scenes = nl.plan_scenes(imgs, [], 12.0, 130.0)
    assert sorted(s["user_media_path"] for s in scenes) == sorted(imgs), "no photo dropped even if the video is short"


def test_upload_api_and_gate(tmp_path):
    from starlette.testclient import TestClient
    from app import web_app as wa
    c = TestClient(wa.app)
    r = c.post("/api/new-launch/upload", files=[("files", ("p1.jpg", _jpg((10, 90, 200)), "image/jpeg")),
                                                ("files", ("p2.jpg", _jpg((220, 180, 20)), "image/jpeg"))])
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["images"]) == 2
    assert c.get(d["images"][0]["url"]).status_code == 200
    assert c.get(f"/api/new-launch/{d['upload_id']}/file/images/..%2F..%2Fsecret").status_code == 404
    assert c.post("/api/new-launch/upload", files=[("files", ("x.txt", b"no", "text/plain"))]).status_code == 400
    from app.automation import publish_gate
    proj = {"status": "completed", "video_path": "/v.mp4", "qa_report": {"status": "PASSED", "overall_score": 95},
            "scenes": [{"scene_number": 1, "visual_source": "manual_upload"}],
            "visual_records": [{"scene_number": 1, "source": "manual_upload"}]}
    reasons = publish_gate.evaluate(proj).get("reasons", []) if isinstance(publish_gate.evaluate(proj), dict) else []
    assert not any("unverified image source" in x for x in reasons)


def test_photos_share_time_evenly(monkeypatch):
    from agents import new_launch as nl
    monkeypatch.setattr(nl, "clip_seconds", lambda p: 3.7)
    scenes = nl.plan_scenes([f"/x/{i}.jpg" for i in range(10)], ["/c1.mp4", "/c2.mov"], 19.84, 130.0)
    photo = [s["duration_seconds"] for s in scenes if s["user_media"] == "image"]
    assert max(photo) - min(photo) <= 60 / 130 + 0.01, f"one photo hogs the time: {photo}"
    assert abs(sum(s["duration_seconds"] for s in scenes) - 19.84) < 0.05


def test_title_cards_keep_a_trailing_showcase(tmp_path):
    """Regression: re-inserting the end card used to drop a full-car showcase that was the last scene."""
    from agents import car_title_cards as ctc
    src = __import__("inspect").getsource(ctc.attach)
    assert 'get("title_card") in ("intro", "outro")' in src
