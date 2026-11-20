"""
WeaponX chart preview: build the chart alone (no video), let the user drop rows, then make the video with
exactly the approved chart. Previews live in output/chart_previews/<id>/ (chart.png + meta.json).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import config


def _root() -> Path:
    d = Path(config.OUTPUT_DIR) / "chart_previews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _id_for(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40] or "chart"
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{slug}"


def build(topic: str, preview_id: Optional[str] = None, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    """Builds (or rebuilds, keeping the other rows) a verified WeaponX list chart for the topic."""
    from agents.image_generator import ImageGeneratorAgent
    old = load(preview_id) if preview_id else None
    pid = preview_id if old else _id_for(topic)
    folder = _root() / pid
    folder.mkdir(parents=True, exist_ok=True)
    items = (old or {}).get("record", {}).get("ranked_items") or []
    excluded = list(dict.fromkeys(list((old or {}).get("excluded") or []) + list(exclude or [])))
    keep = [it.get("article") or it.get("name") for it in items if (it.get("article") or it.get("name")) not in excluded]
    if exclude:
        from agents import photo_library
        for t in exclude:
            photo_library.reject(t)  # the user didn't like this row's photo
    dest = folder / "chart.png"
    rec = ImageGeneratorAgent()._acquire_topic_list_poster(topic, dest, keep_titles=keep or None, exclude_titles=excluded or None)
    rec.update(static_image=True, channel_style="weaponx_lab_static")
    meta = {"id": pid, "topic": topic, "path": str(dest), "record": rec, "excluded": excluded, "built_at": time.time()}
    (folder / "meta.json").write_text(json.dumps(meta, default=str), encoding="utf-8")
    return meta


def load(preview_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not preview_id or not re.fullmatch(r"[A-Za-z0-9_-]+", preview_id):
        return None
    f = _root() / preview_id / "meta.json"
    if not f.exists():
        return None
    try:
        meta = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return meta if Path(meta.get("path", "")).exists() else None
