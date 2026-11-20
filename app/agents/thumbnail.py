"""
Sharpness scoring for thumbnails and hook clips.

- pick_thumbnail(): the dashboard card / review thumbnail used to be scene 1's image no matter what.
  Scene 1 is often an atmospheric shot (vapour cone, haze, motion blur) that reads as a smear at
  card size. We pick the sharpest of the first few scene images instead (scene 1 wins ties).
- clip_sharpness_ratio(): compares an AI hook clip's frames with its source photo, so a clip that
  came back smeared/melted is rejected and the scene keeps its still image.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageFilter, ImageStat

THUMB_NAME = "thumbnail.png"
CANDIDATE_SCENES = 4          # only the opening scenes represent the video
SCENE1_BONUS = 1.25           # prefer the opening image unless another is clearly sharper
MIN_CLIP_SHARPNESS_RATIO = 0.40


def sharpness(img: Any) -> float:
    """Edge variance on a normalised 540x960 grayscale copy (higher = crisper detail)."""
    im = img if isinstance(img, Image.Image) else Image.open(img)
    g = im.convert("L").resize((540, 960))
    return float(ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0])


def _scene_images(project: Dict[str, Any]) -> List[Path]:
    paths = [Path(p) for p in (project.get("image_paths") or []) if p]
    # car intro/outro cards (logo, end card) are not the picture that represents the video
    return [p for p in paths if p.exists() and not p.name.startswith(("intro_card", "outro_card"))]


def pick_thumbnail(project: Dict[str, Any]) -> Optional[Path]:
    """Returns <project_dir>/thumbnail.png, (re)building it when a scene image is newer."""
    imgs = _scene_images(project)
    if not imgs:
        return None
    project_dir = Path(project.get("project_dir") or imgs[0].parent.parent)
    thumb = project_dir / THUMB_NAME
    candidates = imgs[:CANDIDATE_SCENES]
    newest = max(p.stat().st_mtime for p in candidates)
    if thumb.exists() and thumb.stat().st_mtime >= newest:
        return thumb
    best, best_score = candidates[0], -1.0
    for i, p in enumerate(candidates):
        try:
            score = sharpness(p) * (SCENE1_BONUS if i == 0 else 1.0)
        except Exception:
            continue
        if score > best_score:
            best, best_score = p, score
    try:
        shutil.copyfile(best, thumb)
        return thumb
    except OSError:
        return best


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def clip_sharpness_ratio(clip_path: str, source_image: str, samples=(0.25, 0.5, 0.75)) -> Optional[float]:
    """Mean sharpness of frames sampled through the clip divided by the source image's sharpness."""
    try:
        src = sharpness(source_image)
        if src <= 1e-6:
            return None
        dur = _duration(clip_path) or 4.0
        scores = []
        with tempfile.TemporaryDirectory() as td:
            for k, frac in enumerate(samples):
                out = Path(td) / f"f{k}.png"
                subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{dur * frac:.2f}", "-i", str(clip_path),
                                "-frames:v", "1", str(out)], capture_output=True, timeout=60)
                if out.exists():
                    scores.append(sharpness(out))
        if not scores:
            return None
        return (sum(scores) / len(scores)) / src
    except Exception:
        return None


def _duration(path: str) -> Optional[float]:
    try:
        probe = shutil.which("ffprobe")
        if probe:
            out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                 capture_output=True, text=True, timeout=30).stdout.strip()
            return float(out)
    except Exception:
        pass
    return None
