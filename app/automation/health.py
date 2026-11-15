"""
Health checks + daily summary.

check_all() runs every HEALTH_CHECK_MINUTES. It alerts only when a check CHANGES state
(ok -> failing, or failing -> recovered), so a long outage doesn't spam your phone.
daily_summary() reports the last 24 h: videos made, approved (private), awaiting review, failed (and why).
"""
from __future__ import annotations

import json
import shutil
import time
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Tuple

import config
from app.automation import jobs, notifier, resources, state
from app.utils.storage import StorageManager

ACESTEP_IDLE_STOP_MIN = 20


def _http_status(url: str, headers: Dict[str, str] | None = None, timeout: int = 10) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "AIShortsStudio/2.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(300).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def _check_wikimedia() -> Tuple[bool, str]:
    ua = {"User-Agent": getattr(config, "WIKIMEDIA_USER_AGENT", "AIShortsStudio/2.1")}
    for attempt in range(3):  # this network sees occasional TLS resets from Wikimedia
        code, body = _http_status("https://commons.wikimedia.org/w/api.php?action=query&meta=siteinfo&format=json", ua)
        if code == 200 or code in (403, 429):
            break
        time.sleep(2 * (attempt + 1))
    if code == 200:
        hint = "" if getattr(config, "WIKIMEDIA_CONTACT", "") else " (WIKIMEDIA_CONTACT not set: photo downloads get throttled)"
        return True, "reachable" + hint
    return False, f"HTTP {code}: {body[:120]}"


def _check_youtube() -> Tuple[bool, str]:
    try:
        from app.agents.youtube_publisher import YouTubePublisher
        return (True, "authorized") if YouTubePublisher.is_authenticated() else (False, "not authorized: run `python main.py --auth-youtube`")
    except Exception as e:
        return False, f"check failed: {e}"


def _check_gemini() -> Tuple[bool, str]:
    key = getattr(config, "GEMINI_API_KEY", "")
    if not key:
        return True, "not configured (optional)"
    # Listing models succeeds even without billing; a 1-token generation shows the real state (402 = no billing)
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
        data=json.dumps({"contents": [{"parts": [{"text": "ok"}]}], "generationConfig": {"maxOutputTokens": 1}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, "working"
    except urllib.error.HTTPError as e:
        why = "no billing / quota" if e.code in (402, 429) else e.reason
        return False, f"HTTP {e.code} ({why}); image AI + Hindi translation use free fallbacks"
    except Exception as e:
        return False, f"unreachable: {e}"


def _check_disk() -> Tuple[bool, str]:
    free_gb = shutil.disk_usage(config.OUTPUT_DIR).free / 1e9
    return free_gb >= 5, f"{free_gb:.1f} GB free"


def _check_memory() -> Tuple[bool, str]:
    pct = resources.free_memory_pct()
    if pct is None:
        return True, "unknown"
    return pct >= 10, f"{pct}% free"


def _check_dashboard() -> Tuple[bool, str]:
    code, _ = _http_status("http://127.0.0.1:8000/", timeout=5)
    if code == 200:
        return True, "up"
    # The dashboard is optional for hands-off runs; only alert if you said it must always be up
    import os
    required = os.getenv("DASHBOARD_REQUIRED", "0") == "1"
    return (not required), "not running" + ("" if required else " (optional; approvals still work via Telegram)")


CHECKS: Dict[str, Callable[[], Tuple[bool, str]]] = {
    "Wikimedia photos": _check_wikimedia,
    "YouTube upload": _check_youtube,
    "Gemini (optional)": _check_gemini,
    "Disk space": _check_disk,
    "Memory": _check_memory,
    "Dashboard": _check_dashboard,
}


def stop_idle_acestep() -> bool:
    """ACE-Step keeps ~21 GB after use; stop it once it has been idle for a while."""
    if not resources.is_running("acestep") or resources.is_busy("acestep"):
        return False
    marker = resources.LOG_DIR / "acestep_last_used"
    last = float(marker.read_text()) if marker.exists() else 0.0
    if last == 0.0:
        started = state.read("health", {}).get("_acestep_seen_running_at")
        if not started:
            state.update("health", {}, lambda s: {**s, "_acestep_seen_running_at": time.time()})
            return False
        last = started
    if time.time() - last >= ACESTEP_IDLE_STOP_MIN * 60:
        resources.stop("acestep")
        state.update("health", {}, lambda s: {k: v for k, v in s.items() if k != "_acestep_seen_running_at"})
        notifier.send(f"🧠 Stopped idle ACE-Step music server (unused {ACESTEP_IDLE_STOP_MIN}+ min) to free memory.")
        return True
    return False


def check_all(alert: bool = True) -> Dict[str, Dict[str, Any]]:
    results = {}
    for name, fn in CHECKS.items():
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"check error: {e}"
        results[name] = {"ok": ok, "detail": detail, "at": datetime.now().isoformat(timespec="seconds")}

    changes: List[str] = []

    def fn(prev):
        prev = prev or {}
        for name, r in results.items():
            old = prev.get(name) or {}
            fails = 0 if r["ok"] else int(old.get("consecutive_failures", 0)) + 1
            alerted = bool(old.get("alerted"))
            # Alert only after 2 consecutive failures (ignores one-off network blips),
            # and send a recovery note only for outages we actually alerted about.
            if fails == 2 and not alerted:
                verb = "is failing" if old.get("ever_ok") is False or "ever_ok" not in old else "stopped working"
                changes.append(f"❌ {name} {verb}: {r['detail']}")
                alerted = True
            elif r["ok"] and alerted:
                changes.append(f"✅ {name} recovered: {r['detail']}")
                alerted = False
            r["consecutive_failures"] = fails
            r["alerted"] = alerted
            r["ever_ok"] = bool(old.get("ever_ok")) or r["ok"]
            r["since"] = old.get("since") if old.get("ok") == r["ok"] else r["at"]
            prev[name] = r
        return prev

    state.update("health", {}, fn)
    if alert and changes:
        notifier.send("\n".join(changes), title="Service health changed")
    try:
        stop_idle_acestep()
    except Exception as e:
        print(f"[Health] idle ACE-Step check failed: {e}")
    return results


def daily_summary(send: bool = True) -> str:
    since = datetime.now() - timedelta(hours=24)
    recent = []
    for p in StorageManager.get_all_projects():
        try:
            if datetime.fromisoformat(p.get("created_at", "")[:19]) >= since:
                recent.append(p)
        except ValueError:
            continue
    by = lambda *st: [p for p in recent if p.get("status") in st]
    published = by("published", "approved_private")
    pending = by("pending_approval", "awaiting_review")
    failed = by("failed")
    lines = [f"📊 Daily report · {datetime.now():%d %b %Y}",
             f"Videos made: {len(recent)} · Approved (private on YouTube): {len(published)} · Awaiting you: {len(pending)} · Failed: {len(failed)}"]
    for p in published:
        lines.append(f"🔒 {p.get('title') or p.get('topic')} (private; publish/schedule in Studio): {(p.get('youtube') or {}).get('url', '')}")
    for p in pending:
        why = "; ".join((p.get("publish_gate") or {}).get("reasons", [])[:2]) or "approve to go live"
        lines.append(f"⏳ {p.get('title') or p.get('topic')} ({why})")
    for p in failed:
        lines.append(f"❌ {p.get('topic')}: {str(p.get('error', 'unknown error'))[:140]}")
    failed_jobs = [j for j in jobs.all_jobs() if j["status"] == "failed" and j.get("finished_at", "") >= since.isoformat()]
    for j in failed_jobs:
        lines.append(f"❌ Job {j['id']} gave up after {j['attempts']} attempts: {j.get('last_error', '')[:140]}")
    bad = [f"{n}: {r['detail']}" for n, r in (state.read("health", {}) or {}).items()
           if isinstance(r, dict) and r.get("ok") is False]
    if bad:
        lines.append("Service issues: " + " | ".join(bad))
    text = "\n".join(lines)
    if send:
        notifier.send(text, title="Daily report")
    return text
