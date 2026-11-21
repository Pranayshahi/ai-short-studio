"""Watchdog: a video job stuck past the limit is stopped (stacks logged, job + project failed, worker
restarts) instead of blocking the queue for hours."""
import time
from unittest import mock

import pytest


def test_stuck_job_is_stopped(tmp_path, capsys):
    import scheduler
    from app.automation import jobs, state
    from app.utils.storage import StorageManager
    state.update(jobs.NAME, [], lambda _o: [])
    job = jobs.enqueue("studio_generate", {"project_id": "wd_proj"})
    jobs.claim(job["id"])
    StorageManager.save_project({"id": "wd_proj", "topic": "T", "status": "in_progress", "project_dir": str(tmp_path)})
    scheduler._CURRENT.update(id=job["id"], kind="studio_generate", project_id="wd_proj",
                              started=time.time() - (scheduler.JOB_MAX_MINUTES + 5) * 60)
    with mock.patch.object(scheduler.os, "_exit", side_effect=SystemExit(3)), mock.patch.object(scheduler.notifier, "send"):
        with pytest.raises(SystemExit):
            scheduler.job_watchdog()
    out = capsys.readouterr().out
    assert "Watchdog" in out and "Thread" in out, "thread stacks must be logged to find the cause"
    j = next(x for x in jobs.all_jobs() if x["id"] == job["id"])
    assert j["status"] == "failed" and "watchdog" in j["last_error"].lower()
    assert StorageManager.get_project_by_id("wd_proj")["status"] == "failed"
    scheduler._CURRENT.clear()
    state.update(jobs.NAME, [], lambda _o: [])


def test_normal_job_is_left_alone():
    import scheduler
    scheduler._CURRENT.update(id="x", kind="studio_generate", started=time.time() - 60)
    with mock.patch.object(scheduler.os, "_exit", side_effect=AssertionError("killed a healthy job")):
        scheduler.job_watchdog()
    scheduler._CURRENT.clear()
