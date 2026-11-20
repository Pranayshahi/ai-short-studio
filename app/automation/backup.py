"""
Nightly backup (scheduler job, 03:30) - also runnable by hand: `python -m app.automation.backup`.

Destination: ~/Backups/ai-shorts-studio (override with BACKUP_DIR). Private (0700 dirs, 0600 files).
  - daily/<date>.tar.gz : the small, irreplaceable things - credentials/ (YouTube OAuth tokens), .env,
    the project index, automation state (queue, music pool, car queue), studio settings and the saved
    music library. The newest BACKUP_KEEP_DAYS (14) archives are kept.
  - projects_mirror/    : incremental rsync mirror of output/projects (videos, images) - only changes copy.
The backup stays on this Mac; copy ~/Backups to an external drive or Time Machine for off-machine safety.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import config

PROJECT_DIR = Path(__file__).resolve().parents[2]
KEEP_DAYS = int(os.getenv("BACKUP_KEEP_DAYS", "14"))


def backup_root() -> Path:
    return Path(os.getenv("BACKUP_DIR", str(Path.home() / "Backups" / "ai-shorts-studio")))


def _critical_paths() -> List[Path]:
    out = Path(config.OUTPUT_DIR)
    items = [PROJECT_DIR / "credentials", PROJECT_DIR / ".env", out / "projects_index.json", out / "automation",
             config.AUDIO_ASSETS_DIR / "library"]
    items += [p for p in out.glob("*.json")]
    settings = getattr(config, "STUDIO_SETTINGS_FILE", None)
    if settings:
        items.append(Path(settings))
    seen, uniq = set(), []
    for p in items:
        if p.exists() and p.resolve() not in seen:
            seen.add(p.resolve())
            uniq.append(p)
    return uniq


def _private(path: Path) -> None:
    try:
        path.chmod(0o700 if path.is_dir() else 0o600)
    except OSError:
        pass


def run_backup() -> Dict[str, Any]:
    t0 = time.time()
    root = backup_root()
    daily = root / "daily"
    for d in (root, daily):
        d.mkdir(parents=True, exist_ok=True)
        _private(d)

    # 1) small critical archive
    archive = daily / f"{datetime.now():%Y-%m-%d_%H%M}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for p in _critical_paths():
            tar.add(str(p), arcname=str(p.relative_to(PROJECT_DIR)) if PROJECT_DIR in p.parents or p == PROJECT_DIR
                    else p.name, filter=lambda ti: None if ti.name.endswith((".log", ".lock")) else ti)
    _private(archive)
    archives = sorted(daily.glob("*.tar.gz"))
    for old in archives[:-KEEP_DAYS]:
        old.unlink(missing_ok=True)

    # 2) incremental mirror of project media
    mirror = root / "projects_mirror"
    mirror.mkdir(exist_ok=True)
    src = Path(config.OUTPUT_DIR) / "projects"
    rsync = shutil.which("rsync")
    mirrored = False
    if src.exists() and rsync:
        res = subprocess.run([rsync, "-a", "--delete-after", "--exclude", "temp_render_*", f"{src}/", f"{mirror}/"],
                             capture_output=True, text=True, timeout=3600)
        mirrored = res.returncode == 0
    # 3) the verified photo library (grows as charts are built; slow to rebuild)
    lib_src = Path(config.PHOTO_LIBRARY_DIR)
    if lib_src.exists() and rsync:
        (root / "photo_library_mirror").mkdir(exist_ok=True)
        subprocess.run([rsync, "-a", f"{lib_src}/", f"{root / 'photo_library_mirror'}/"], capture_output=True, timeout=1800)
    report = {"archive": str(archive), "archive_mb": round(archive.stat().st_size / 1e6, 1),
              "kept_archives": min(len(archives), KEEP_DAYS), "projects_mirrored": mirrored,
              "seconds": round(time.time() - t0, 1)}
    print(f"[Backup] {report}")
    return report


if __name__ == "__main__":
    run_backup()
