"""
Verified photo library: clean cutouts of exact models (missiles, tanks, jets, pistols...) that passed
every photo check, kept permanently and reused by every chart.

Why: charts were limited by photo supply - each one re-downloaded and re-cut photos from Wikimedia
(which often refuses connections), and good cutouts were rare. Now the first good cutout of a model is
saved here and the next chart uses it instantly, offline.

  get(title)      approved cutout for that Wikipedia article (None if none / rejected)
  add(...)        save a cutout that passed the checks (never overwrites an approved one)
  reject(title)   the user rejected it (chart feedback / library page): never reused; its source file
                  is remembered so the same photo isn't picked again
Index: shared state 'photo_library' (backed up nightly); images: config.PHOTO_LIBRARY_DIR.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from app.automation import state

STATE = "photo_library"


def _dir() -> Path:
    d = Path(config.PHOTO_LIBRARY_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def key_of(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(title or "")).strip("_")[:80] or "item"


def _index() -> Dict[str, Dict[str, Any]]:
    return state.read(STATE, {}) or {}


def entry(title: str) -> Optional[Dict[str, Any]]:
    return _index().get(key_of(title))


def get(title: str):
    """Approved cutout (RGBA PIL image) for the article, or None."""
    e = entry(title)
    if not e or e.get("status") != "approved":
        return None
    f = _dir() / e["file"]
    if not f.exists():
        return None
    from PIL import Image
    try:
        return Image.open(f).convert("RGBA")
    except Exception:
        return None


def rejected_sources(title: str) -> List[str]:
    e = entry(title) or {}
    return list(e.get("rejected_sources") or [])


def add(title: str, kind: str, img, source_file: str = "", source_url: str = "") -> bool:
    """Saves a checked cutout. Keeps an existing approved photo; never re-adds a rejected source."""
    k = key_of(title)
    cur = _index().get(k) or {}
    if cur.get("status") == "approved" and (_dir() / cur.get("file", "")).exists():
        return False
    if source_file and source_file in (cur.get("rejected_sources") or []):
        return False
    fname = f"{k}.png"
    img.save(_dir() / fname, "PNG")
    new = {**cur, "title": title, "kind": kind, "file": fname, "status": "approved", "source_file": source_file,
           "source_url": source_url, "added": time.time(), "rejected_sources": cur.get("rejected_sources") or []}
    state.update(STATE, {}, lambda idx: {**(idx or {}), k: new})
    return True


def reject(title: str) -> bool:
    k = key_of(title)

    def fn(idx):
        idx = dict(idx or {})
        e = dict(idx.get(k) or {"title": title, "file": f"{k}.png", "rejected_sources": []})
        if e.get("source_file") and e["source_file"] not in e.setdefault("rejected_sources", []):
            e["rejected_sources"].append(e["source_file"])
        e.update(status="rejected", rejected_at=time.time())
        idx[k] = e
        return idx
    state.update(STATE, {}, fn)
    return True


def restore(title: str) -> bool:
    k = key_of(title)
    ok = {}

    def fn(idx):
        idx = dict(idx or {})
        e = idx.get(k)
        if e and (_dir() / e.get("file", "")).exists():
            e = dict(e)
            if e.get("source_file") in (e.get("rejected_sources") or []):
                e["rejected_sources"] = [s for s in e["rejected_sources"] if s != e.get("source_file")]
            e["status"] = "approved"
            idx[k] = e
            ok["v"] = True
        return idx
    state.update(STATE, {}, fn)
    return bool(ok)


def listing() -> List[Dict[str, Any]]:
    out = []
    for k, e in sorted(_index().items(), key=lambda kv: -float(kv[1].get("added") or 0)):
        out.append({"key": k, **{f: e.get(f) for f in ("title", "kind", "status", "source_file", "source_url", "added")},
                    "exists": (_dir() / e.get("file", "")).exists()})
    return out


def image_path(key: str) -> Optional[Path]:
    e = _index().get(key)
    if not e:
        return None
    f = _dir() / e.get("file", "")
    return f if f.exists() else None
