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


def build(topic: str, preview_id: Optional[str] = None, exclude: Optional[List[str]] = None,
          ranked_list: Optional[str] = None) -> Dict[str, Any]:
    """Builds (or rebuilds, keeping the other rows) a verified WeaponX list chart for the topic.
    ranked_list: the user's own numbered list (e.g. from ChatGPT): kept in their order with their names,
    every row verified on Wikipedia; 'Replace' drops a row and the next list entry moves up."""
    from agents.image_generator import ImageGeneratorAgent
    old = load(preview_id) if preview_id else None
    ranked_list = ranked_list or (old or {}).get("ranked_list")
    if ranked_list:
        from agents import ranked_poster
        if not ranked_poster.is_ranked_list(ranked_list):
            raise ValueError("Paste a numbered list of at least 5 models (1. ..., 2. ..., ...)")
        pid = preview_id if old else _id_for(topic or ranked_poster.parse_ranked_list(ranked_list)["title"])
        folder = _root() / pid
        folder.mkdir(parents=True, exist_ok=True)
        excluded = list(dict.fromkeys(list((old or {}).get("excluded") or []) + list(exclude or [])))
        dest = folder / "chart.png"
        cache = Path(config.OUTPUT_DIR) / "cache" / "evolution_photos"
        res = ranked_poster.make_poster(ranked_list, dest, cache, exclude=excluded)
        if res.get("error"):
            raise ValueError(res["error"])
        agent = ImageGeneratorAgent()
        rec = {"scene_number": 1, "image_path": str(dest), "source": "weaponx_lab_poster",
               "source_url": "https://commons.wikimedia.org", "source_domain": "commons.wikimedia.org",
               "source_provider": "WeaponX Labs ranked chart (your list, Wikipedia-verified, Wikimedia Commons photos)",
               "license": "Photos CC/PD from Wikimedia Commons — see photo_credits", "author": "@WeaponXLabs Studio Engine",
               "source_verified": True, "topic_matched": True, "topic_match_score": 99,
               "topic_match_reason": f"{res['rows']} rows from the user's ranked list, each verified on Wikipedia",
               "ranked_items": res["items"], "photo_credits": res["credits"], "skipped": res.get("skipped") or [],
               "visual_quality": {"output_resolution": f"{agent.target_width}x{agent.target_height}", "passed": True,
                                  "photos": res.get("photos")},
               "static_image": True, "channel_style": "weaponx_lab_static", "prompt": ranked_list[:500]}
        title = topic or res.get("title") or "Ranked list"
        meta = {"id": pid, "topic": title, "path": str(dest), "record": rec, "excluded": excluded,
                "ranked_list": ranked_list, "built_at": time.time()}
        (folder / "meta.json").write_text(json.dumps(meta, default=str), encoding="utf-8")
        return meta
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
