"""
Persistent job queue for hands-off generation (output/automation/jobs.json).

Job lifecycle: pending -> running -> done | failed (after max attempts)
- A failed attempt is retried with back-off (5 min, 30 min, 2 h ...).
- If the scheduler process dies mid-job, the job is "running" with a stale heartbeat;
  recover_interrupted() puts it back to pending (resume) instead of losing it.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.automation import state

NAME = "jobs"
MAX_ATTEMPTS = int(os.getenv("JOB_MAX_ATTEMPTS", "3"))
BACKOFF_MINUTES = [5, 30, 120]
STALE_AFTER = timedelta(minutes=int(os.getenv("JOB_STALE_MINUTES", "60")))


def _now() -> datetime:
    return datetime.now()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def all_jobs() -> List[Dict[str, Any]]:
    return state.read(NAME, [])


def enqueue(kind: str = "daily_short", params: Optional[Dict[str, Any]] = None, dedupe_key: Optional[str] = None) -> Dict[str, Any]:
    """Adds a job. With dedupe_key (e.g. 'daily-2026-11-15') a second enqueue is a no-op."""
    job = {
        "id": uuid.uuid4().hex[:10],
        "kind": kind,
        "params": params or {},
        "dedupe_key": dedupe_key,
        "status": "pending",
        "attempts": 0,
        "max_attempts": MAX_ATTEMPTS,
        "next_run_at": _iso(_now()),
        "created_at": _iso(_now()),
        "history": [],
    }
    result = {}

    def fn(jobs):
        if dedupe_key and any(j.get("dedupe_key") == dedupe_key for j in jobs):
            result["job"] = next(j for j in jobs if j.get("dedupe_key") == dedupe_key)
            result["duplicate"] = True
            return jobs
        result["job"] = job
        return jobs + [job]

    state.update(NAME, [], fn)
    return result["job"]


def claim_next() -> Optional[Dict[str, Any]]:
    """Marks the oldest due pending job as running and returns it (None if nothing is due)."""
    claimed = {}

    def fn(jobs):
        now = _now()
        due = [j for j in jobs if j["status"] == "pending" and datetime.fromisoformat(j["next_run_at"]) <= now]
        if not due:
            return jobs
        job = sorted(due, key=lambda j: j["next_run_at"])[0]
        job["status"] = "running"
        job["attempts"] += 1
        job["started_at"] = _iso(now)
        job["heartbeat_at"] = _iso(now)
        claimed["job"] = dict(job)
        return jobs

    state.update(NAME, [], fn)
    return claimed.get("job")


def _modify(job_id: str, mutate) -> Optional[Dict[str, Any]]:
    out = {}

    def fn(jobs):
        for j in jobs:
            if j["id"] == job_id:
                mutate(j)
                out["job"] = dict(j)
        return jobs

    state.update(NAME, [], fn)
    return out.get("job")


def heartbeat(job_id: str, note: Optional[str] = None, **fields) -> None:
    def m(j):
        j["heartbeat_at"] = _iso(_now())
        if note:
            j["progress"] = note
        j.update(fields)
    _modify(job_id, m)


def complete(job_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    def m(j):
        j["status"] = "done"
        j["finished_at"] = _iso(_now())
        j["result"] = result
        j["history"].append({"at": _iso(_now()), "event": "done"})
    return _modify(job_id, m)


def fail(job_id: str, error: str) -> Optional[Dict[str, Any]]:
    """Records a failed attempt; schedules a retry with back-off or gives up after max attempts."""
    def m(j):
        j["history"].append({"at": _iso(_now()), "event": "attempt_failed", "attempt": j["attempts"], "error": error[:500]})
        j["last_error"] = error[:500]
        if j["attempts"] >= j.get("max_attempts", MAX_ATTEMPTS):
            j["status"] = "failed"
            j["finished_at"] = _iso(_now())
        else:
            wait = BACKOFF_MINUTES[min(j["attempts"] - 1, len(BACKOFF_MINUTES) - 1)]
            j["status"] = "pending"
            j["next_run_at"] = _iso(_now() + timedelta(minutes=wait))
    return _modify(job_id, m)


def recover_interrupted(force: bool = False) -> List[str]:
    """
    Resume jobs left 'running' by a crashed/stopped scheduler (stale heartbeat, or force=True at
    startup since only one scheduler runs). They go back to pending immediately; the attempt counts.
    """
    recovered: List[str] = []

    def fn(jobs):
        now = _now()
        for j in jobs:
            if j["status"] != "running":
                continue
            hb = datetime.fromisoformat(j.get("heartbeat_at") or j.get("started_at"))
            if force or now - hb > STALE_AFTER:
                j["history"].append({"at": _iso(now), "event": "interrupted_resumed", "attempt": j["attempts"]})
                if j["attempts"] >= j.get("max_attempts", MAX_ATTEMPTS):
                    j["status"] = "failed"
                    j["last_error"] = "Interrupted on its final attempt (scheduler stopped or crashed)."
                    j["finished_at"] = _iso(now)
                else:
                    j["status"] = "pending"
                    j["next_run_at"] = _iso(now)
                recovered.append(j["id"])
        return jobs

    state.update(NAME, [], fn)
    return recovered


def prune(keep_days: int = 30) -> None:
    cutoff = _now() - timedelta(days=keep_days)

    def fn(jobs):
        return [j for j in jobs if j["status"] in ("pending", "running")
                or datetime.fromisoformat(j.get("finished_at") or j["created_at"]) > cutoff]

    state.update(NAME, [], fn)
