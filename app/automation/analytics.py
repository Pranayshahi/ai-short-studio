"""
YouTube performance loop (read-only): which topics, styles and music themes work on each channel.

refresh()  - for every uploaded video, reads views / likes / comments / privacy from the YouTube Data API
             (videos.list, the channel's own token, never opens a browser) and stores them on the project,
             with a daily history so growth can be seen. Runs daily from the scheduler (07:15) and from the
             dashboard's Refresh button.
summary()  - totals and averages per style, music theme, channel and category, top videos, 7-day growth.

Retention / click-through rate need the separate YouTube Analytics API (scope yt-analytics.readonly),
which needs each channel re-authorized; views/likes/comments work with the existing authorization.
Private videos have no public views: numbers start once you publish them in YouTube Studio.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

from app.utils.storage import StorageManager

HISTORY_DAYS = 60


def _uploaded() -> List[Dict[str, Any]]:
    out = []
    for p in StorageManager.get_all_projects():
        vid = str((p.get("youtube") or {}).get("video_id") or "")
        if vid and not vid.startswith("staged_") and p.get("status") not in ("in_progress", "queued"):
            out.append(p)
    return out


def _channel_of(p: Dict[str, Any]) -> str:
    return p.get("channel") or (p.get("youtube") or {}).get("channel_key") or "weaponxlabs"


def refresh(service_factory=None) -> Dict[str, Any]:
    from app.agents.youtube_publisher import YouTubePublisher
    factory = service_factory or (lambda ch: YouTubePublisher.get_authenticated_service(channel=ch, interactive=False))
    by_channel: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in _uploaded():
        by_channel[_channel_of(p)].append(p)
    updated, errors = 0, []
    today = datetime.now().strftime("%Y-%m-%d")
    for ch, projects in by_channel.items():
        try:
            yt = factory(ch)
        except Exception as e:
            errors.append(f"{ch}: not authorized ({str(e)[:100]})")
            continue
        for i in range(0, len(projects), 50):
            batch = projects[i:i + 50]
            ids = ",".join(p["youtube"]["video_id"] for p in batch)
            try:
                resp = yt.videos().list(part="statistics,status", id=ids).execute()
            except Exception as e:
                errors.append(f"{ch}: {str(e)[:120]}")
                continue
            found = {it["id"]: it for it in resp.get("items", [])}
            for p in batch:
                it = found.get(p["youtube"]["video_id"])
                fresh = StorageManager.get_project_by_id(p["id"]) or p
                if not it:
                    fresh["youtube_stats"] = {**(fresh.get("youtube_stats") or {}), "missing": True,
                                              "fetched_at": datetime.now().isoformat(timespec="seconds")}
                    StorageManager.save_project(fresh)
                    continue
                st = it.get("statistics") or {}
                views, likes, comments = (int(st.get(k) or 0) for k in ("viewCount", "likeCount", "commentCount"))
                hist = [h for h in ((fresh.get("youtube_stats") or {}).get("history") or []) if h.get("date") != today]
                hist = (hist + [{"date": today, "views": views, "likes": likes}])[-HISTORY_DAYS:]
                fresh["youtube_stats"] = {"views": views, "likes": likes, "comments": comments,
                                          "privacy": (it.get("status") or {}).get("privacyStatus"),
                                          "fetched_at": datetime.now().isoformat(timespec="seconds"), "history": hist}
                StorageManager.save_project(fresh)
                updated += 1
        time.sleep(0.5)
    res = {"updated": updated, "errors": errors}
    print(f"[Analytics] {res}")
    return res


def _views_7d(p: Dict[str, Any]) -> int:
    hist = (p.get("youtube_stats") or {}).get("history") or []
    if len(hist) < 2:
        return 0
    recent = hist[-1]["views"]
    week_ago = next((h["views"] for h in reversed(hist[:-1])
                     if (datetime.now() - datetime.fromisoformat(h["date"])).days >= 7), hist[0]["views"])
    return max(0, recent - week_ago)


def summary() -> Dict[str, Any]:
    vids = []
    for p in _uploaded():
        st = p.get("youtube_stats") or {}
        vids.append({
            "id": p["id"], "title": p.get("title") or p.get("topic"), "topic": p.get("topic"),
            "channel": _channel_of(p), "style": p.get("style") or "default",
            "music_theme": (p.get("music_theme") or {}).get("theme") or "-",
            "category": p.get("category") or "-", "privacy": st.get("privacy") or "unknown",
            "views": int(st.get("views") or 0), "likes": int(st.get("likes") or 0),
            "comments": int(st.get("comments") or 0), "views_7d": _views_7d(p),
            "url": f"https://studio.youtube.com/video/{p['youtube']['video_id']}/edit",
            "fetched_at": st.get("fetched_at"),
        })

    def group(field: str) -> List[Dict[str, Any]]:
        g: Dict[str, Dict[str, Any]] = {}
        for v in vids:
            k = v[field]
            a = g.setdefault(k, {"name": k, "videos": 0, "public_videos": 0, "views": 0, "likes": 0})
            a["videos"] += 1
            a["public_videos"] += v["privacy"] == "public"
            a["views"] += v["views"]
            a["likes"] += v["likes"]
        for a in g.values():
            a["avg_views"] = round(a["views"] / a["public_videos"]) if a["public_videos"] else 0
        return sorted(g.values(), key=lambda a: (-a["avg_views"], -a["views"]))

    public = [v for v in vids if v["privacy"] == "public"]
    return {
        "videos": sorted(vids, key=lambda v: -v["views"]),
        "totals": {"videos": len(vids), "public": len(public), "views": sum(v["views"] for v in vids),
                   "likes": sum(v["likes"] for v in vids), "views_7d": sum(v["views_7d"] for v in vids)},
        "by_style": group("style"), "by_music_theme": group("music_theme"),
        "by_channel": group("channel"), "by_category": group("category"),
        "last_refresh": max((v["fetched_at"] or "" for v in vids), default=None),
        "note": None if public else "All uploads are still private: views start once you publish them in YouTube Studio.",
    }
