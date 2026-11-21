"""
New Launch car videos (user request 2026-11-21): the user's OWN photos and clips of a new car.

Free photo sites only have older models (a 2026 facelift has no CC photos yet), so for a new launch the
user uploads the media and the video is built from it:
  - EVERY uploaded photo is used, each in its own scene, with the car-edit treatment (title overlay,
    beat-synced zoom/pan, speed ramps) - and the best complete-car photos also get the full-car showcase.
  - Every uploaded clip becomes its own scene (cut to the beat, interleaved with the photos).
  - No web photos are mixed in (they would show the old model).
Everything else is the normal car video: logo intro, end card, new on-theme music, >= 20 s, checks.

Uploads: output/uploads/<upload_id>/{images,clips}/ ; project_record["user_media"] = {"images": [...], "clips": [...]}
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

import config

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
CLIP_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_IMAGES = 20
MAX_CLIPS = 10
MAX_IMAGE_MB = 25
MAX_CLIP_MB = 200
MAX_CLIP_SECONDS = 60
W, H = 1080, 1920


def _ffprobe() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def clip_seconds(path: str) -> Optional[float]:
    try:
        out = subprocess.run([_ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "format=duration",
                              "-of", "json", str(path)], capture_output=True, text=True, timeout=60).stdout
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return None


def new_upload_dir() -> Tuple[str, Path]:
    uid = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    d = Path(config.OUTPUT_DIR) / "uploads" / uid
    (d / "images").mkdir(parents=True, exist_ok=True)
    (d / "clips").mkdir(parents=True, exist_ok=True)
    return uid, d


def accept_files(files: List[Tuple[str, bytes]], dest: Path) -> Dict[str, Any]:
    """Validates and saves uploads. files: [(filename, bytes)]. Duplicate photos are dropped.
    Returns {"images": [paths], "clips": [paths], "rejected": [reasons]}."""
    from agents.image_generator import ImageGeneratorAgent
    images, clips, rejected, hashes = [], [], [], []
    for name, data in files:
        ext = Path(name or "").suffix.lower()
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name or "file").name)[:80] or "file"
        if ext in IMAGE_EXTS:
            if len(images) >= MAX_IMAGES:
                rejected.append(f"{name}: more than {MAX_IMAGES} photos")
                continue
            if len(data) > MAX_IMAGE_MB * 1e6:
                rejected.append(f"{name}: larger than {MAX_IMAGE_MB} MB")
                continue
            try:
                import io
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            except Exception:
                rejected.append(f"{name}: not a readable image")
                continue
            if min(im.size) < 400:
                rejected.append(f"{name}: too small ({im.width}x{im.height}); use at least 400 px")
                continue
            out = dest / "images" / f"{len(images) + 1:02d}_{Path(safe).stem}.jpg"
            im.save(out, "JPEG", quality=94)
            h = ImageGeneratorAgent._dhash(out)
            if h is not None and any(bin(h ^ o).count("1") <= 6 for o in hashes):
                out.unlink(missing_ok=True)
                rejected.append(f"{name}: same photo as one already uploaded")
                continue
            hashes.append(h) if h is not None else None
            images.append(str(out))
        elif ext in CLIP_EXTS:
            if len(clips) >= MAX_CLIPS:
                rejected.append(f"{name}: more than {MAX_CLIPS} clips")
                continue
            if len(data) > MAX_CLIP_MB * 1e6:
                rejected.append(f"{name}: larger than {MAX_CLIP_MB} MB")
                continue
            out = dest / "clips" / f"{len(clips) + 1:02d}_{safe}"
            out.write_bytes(data)
            secs = clip_seconds(str(out))
            if not secs:
                out.unlink(missing_ok=True)
                rejected.append(f"{name}: not a playable video")
                continue
            if secs > MAX_CLIP_SECONDS:
                out.unlink(missing_ok=True)
                rejected.append(f"{name}: {secs:.0f} s long; use clips up to {MAX_CLIP_SECONDS} s")
                continue
            clips.append(str(out))
        else:
            rejected.append(f"{name}: unsupported type (photos: jpg/png/webp, clips: mp4/mov/m4v/webm)")
    return {"images": images, "clips": clips, "rejected": rejected}


# ------------------------------------------------------------------ scenes from the uploads

def resolve_upload(upload_id: str) -> Optional[Dict[str, List[str]]]:
    """The saved media of an upload (output/uploads/<id>), or None if it doesn't exist."""
    if not re.fullmatch(r"[A-Za-z0-9_]{6,40}", upload_id or ""):
        return None
    d = Path(config.OUTPUT_DIR) / "uploads" / upload_id
    if not d.is_dir():
        return None
    images = sorted(str(f) for f in (d / "images").glob("*") if f.suffix.lower() in IMAGE_EXTS)
    clips = sorted(str(f) for f in (d / "clips").glob("*") if f.suffix.lower() in CLIP_EXTS)
    return {"images": images, "clips": clips} if (images or clips) else None


def plan_scenes(images: List[str], clips: List[str], main_seconds: float, bpm: float,
                template: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """One scene per photo and per clip (clips interleaved), durations on the beat, filling main_seconds.
    Clips get up to their own length; photos share the rest."""
    beat = 60.0 / float(bpm or 130.0)
    order: List[Tuple[str, str]] = []
    imgs, cls = list(images), list(clips)
    # photos first (the title overlay opens on a photo), then alternate photo / clip
    if imgs:
        order.append(("image", imgs.pop(0)))
    while imgs or cls:
        if cls:
            order.append(("clip", cls.pop(0)))
        if imgs:
            order.append(("image", imgs.pop(0)))
        if imgs and len(imgs) > len(cls):
            order.append(("image", imgs.pop(0)))
    if not order:
        return []
    total_beats = max(len(order) * 2, int(round(main_seconds / beat)))
    n_img = sum(1 for k, _ in order if k == "image")
    clip_beats = {}
    for kind, path in order:
        if kind == "clip":
            secs = clip_seconds(path) or 3.0
            clip_beats[path] = max(2, min(int(secs / beat), 8))
    # photos keep at least 3 beats each when there's room; clips give way first
    while n_img and sum(clip_beats.values()) > total_beats - 3 * n_img and any(b > 2 for b in clip_beats.values()):
        longest = max(clip_beats, key=clip_beats.get)
        clip_beats[longest] -= 1
    left = max(2 * n_img, total_beats - sum(clip_beats.values()))
    # spread the photo beats evenly (the remainder goes one beat each to the first photos)
    img_beats = [left // n_img + (1 if i < left % n_img else 0) for i in range(n_img)] if n_img else []
    scenes, used, k = [], 0, 0
    for i, (kind, path) in enumerate(order, 1):
        if kind == "clip":
            beats = clip_beats[path]
        else:
            beats, k = img_beats[k], k + 1
        scenes.append({"scene_number": i, "scene_id": i, "beats": beats, "duration_seconds": round(beats * beat, 3),
                       "beat_synced": True, "beat_sync": True, "bpm": bpm, "narration": "", "voiceover_text": "",
                       "user_media": kind, "user_media_path": path, "speed_ramp": "velocity" if kind == "image" else "none",
                       "visual_prompt": "user-supplied photo" if kind == "image" else "user-supplied clip"})
        if template:
            t = template[(i - 1) % len(template)]
            scenes[-1].update(on_screen_text=t.get("on_screen_text", ""), narration=t.get("narration", ""),
                              car_angle=t.get("car_angle", ""))
        used += beats
    # land exactly on main_seconds (rounding): adjust the last photo scene
    # (only a fraction of a beat; when every photo needs its 2 beats the video simply runs a little longer)
    diff = round(main_seconds - sum(s["duration_seconds"] for s in scenes), 3)
    if abs(diff) < beat:
        target = next((s for s in reversed(scenes) if s["user_media"] == "image"), scenes[-1])
        target["duration_seconds"] = round(max(beat * 2, target["duration_seconds"] + diff), 3)
    return scenes


def _cover(im: Image.Image) -> Image.Image:
    s = max(W / im.width, H / im.height)
    r = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.Resampling.LANCZOS)
    left, top = (r.width - W) // 2, (r.height - H) // 2
    return r.crop((left, top, left + W, top + H))


def build_visuals(project_dir: Path, scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Scene images (photos framed 1080x1920; clips: their first frame) + records marking them as the
    user's own media. Clips are attached as the scene's clip (the composer plays them in place of the image)."""
    sdir = Path(project_dir) / "scenes"
    sdir.mkdir(parents=True, exist_ok=True)
    image_paths, records = [], []
    for sc in scenes:
        n = sc["scene_number"]
        dest = sdir / f"scene_{n:02d}.png"
        src = sc["user_media_path"]
        if sc["user_media"] == "image":
            _cover(Image.open(src).convert("RGB")).save(dest, "PNG")
        else:
            ext = Path(src).suffix.lower()
            clip_dest = sdir / f"scene_{n:02d}_clip{ext}"
            shutil.copyfile(src, clip_dest)
            sc["clip_path"] = str(clip_dest)
            tmp = sdir / f"scene_{n:02d}_frame.png"
            subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", "0.3", "-i", src, "-frames:v", "1", str(tmp)],
                           capture_output=True, timeout=60)
            _cover(Image.open(tmp).convert("RGB") if tmp.exists() else Image.new("RGB", (W, H), (10, 12, 18))).save(dest, "PNG")
            tmp.unlink(missing_ok=True)
        sc.update(image_path=str(dest), visual_source="manual_upload")
        image_paths.append(str(dest))
        records.append({"scene_number": n, "image_path": str(dest), "source": "manual_upload",
                        "source_provider": "Your upload", "license": "Provided by the user", "author": "User",
                        "source_verified": True, "topic_matched": True, "topic_match_score": 100,
                        "local_path": src, "media_type": sc["user_media"]})
    return {"image_paths": image_paths, "visual_records": records, "change_image_events": [],
            "average_topic_match_score": 100, "user_media": True}
