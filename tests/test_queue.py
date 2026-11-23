"""One job queue for the whole machine: dashboard videos are queued to the scheduler's worker (one video
at a time); without a live worker the web server still renders them itself."""
import os
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture()
def fresh_queue():
    from app.automation import jobs, state
    state.update(jobs.NAME, [], lambda _old: [])
    state.update(jobs.WORKER_HEARTBEAT, {}, lambda _old: {})
    yield jobs
    state.update(jobs.NAME, [], lambda _old: [])
    state.update(jobs.WORKER_HEARTBEAT, {}, lambda _old: {})


def test_claim_specific_job_and_positions(fresh_queue):
    jobs = fresh_queue
    a = jobs.enqueue("daily_short", {})
    b = jobs.enqueue("studio_generate", {"project_id": "p1"}, max_attempts=1)
    assert b["max_attempts"] == 1
    assert jobs.queue_position(a["id"]) == 1 and jobs.queue_position(b["id"]) == 2
    got = jobs.claim(b["id"])  # the car "Run now" button must run ITS job, not the oldest one
    assert got and got["id"] == b["id"] and got["status"] == "running"
    assert jobs.claim(b["id"]) is None, "a running job can't be claimed twice"
    assert next(j for j in jobs.all_jobs() if j["id"] == a["id"])["status"] == "pending"


def test_worker_heartbeat(fresh_queue):
    jobs = fresh_queue
    assert not jobs.worker_alive("studio_generate"), "no heartbeat = no worker"
    jobs.write_worker_heartbeat(["daily_short", "studio_generate"])
    assert jobs.worker_alive("studio_generate")
    assert not jobs.worker_alive("something_new"), "an older worker without the capability isn't used"
    from app.automation import state
    state.update(jobs.WORKER_HEARTBEAT, {}, lambda hb: {**hb, "at": "2020-01-01T00:00:00"})
    assert not jobs.worker_alive("studio_generate"), "a stale heartbeat means the worker is gone"


def _fake_prepare(tmp_path):
    def prepare(**kw):
        rec = {"id": "qa_queue_proj", "topic": kw.get("custom_topic"), "status": "in_progress",
               "project_dir": str(tmp_path), "style": kw.get("style"), "created_at": "2026-11-20T10:00:00",
               "updated_at": "2026-11-20T10:00:00"}
        from app.utils.storage import StorageManager
        StorageManager.save_project(rec)
        return rec, {"topic": kw.get("custom_topic")}
    return prepare


def test_generate_is_queued_when_worker_alive(fresh_queue, tmp_path):
    from starlette.testclient import TestClient
    from app import web_app as wa
    jobs = fresh_queue
    jobs.write_worker_heartbeat(["daily_short", "daily_car_edit", "studio_generate"])
    with mock.patch.object(wa.pipeline, "prepare_project", side_effect=_fake_prepare(tmp_path)), \
         mock.patch.object(wa.pipeline, "run", side_effect=AssertionError("must not render in the web server")):
        r = TestClient(wa.app).post("/api/generate", json={"topic": "QA Queue Test", "style": "default"})
    assert r.status_code == 200 and r.json()["status"] == "queued", r.text
    queued = [j for j in jobs.all_jobs() if j["kind"] == "studio_generate"]
    assert len(queued) == 1 and queued[0]["params"]["project_id"] == "qa_queue_proj"
    assert queued[0]["params"]["run_kwargs"]["style"] == "default"
    from app.utils.storage import StorageManager
    assert StorageManager.get_project_by_id("qa_queue_proj")["status"] == "queued"


def test_generate_falls_back_without_worker(fresh_queue, tmp_path):
    from starlette.testclient import TestClient
    from app import web_app as wa
    ran = []
    with mock.patch.object(wa.pipeline, "prepare_project", side_effect=_fake_prepare(tmp_path)), \
         mock.patch.object(wa.pipeline, "run", side_effect=lambda **k: ran.append(k)):
        r = TestClient(wa.app).post("/api/generate", json={"topic": "QA Fallback Test", "style": "default"})
    assert r.status_code == 200 and r.json()["status"] == "started", r.text
    assert ran, "without a worker the web server renders the video itself (as before)"
    assert not [j for j in fresh_queue.all_jobs() if j["kind"] == "studio_generate"]


def test_worker_runs_studio_job(fresh_queue, tmp_path):
    import scheduler
    from app.utils.storage import StorageManager
    StorageManager.save_project({"id": "qa_worker_proj", "topic": "T", "status": "queued", "project_dir": str(tmp_path),
                                 "topic_research": {"topic": "T"}})
    job = fresh_queue.enqueue("studio_generate", {"project_id": "qa_worker_proj", "run_kwargs": {"style": "default", "duration": 20.0}})
    seen = {}

    def fake_run(self, **kw):
        p = StorageManager.get_project_by_id("qa_worker_proj")
        seen.update(kw, status=p["status"], pid=p.get("worker_pid"))
        p["status"] = "completed"
        StorageManager.save_project(p)
    from app.agents.pipeline import ShortsPipeline
    with mock.patch.object(ShortsPipeline, "__init__", lambda self: None), mock.patch.object(ShortsPipeline, "run", fake_run):
        res = scheduler._run_studio_generate(fresh_queue.claim(job["id"]))
    assert seen["status"] == "in_progress" and seen["pid"] == os.getpid() and seen["duration"] == 20.0
    assert seen["prepared_project"]["id"] == "qa_worker_proj" and res["status"] == "completed"


def test_queued_project_without_job_is_cleaned_up(fresh_queue, tmp_path):
    from app import web_app as wa
    from app.utils.storage import StorageManager
    StorageManager.save_project({"id": "qa_lost", "topic": "L", "status": "queued", "queue_job_id": "gone", "project_dir": str(tmp_path)})
    job = fresh_queue.enqueue("studio_generate", {"project_id": "qa_ok"})
    StorageManager.save_project({"id": "qa_ok", "topic": "K", "status": "queued", "queue_job_id": job["id"], "project_dir": str(tmp_path)})
    marked = wa.sweep_orphaned_generations("test")
    assert "qa_lost" in marked and "qa_ok" not in marked
    assert StorageManager.get_project_by_id("qa_ok")["status"] == "queued"


def test_paused_queue_starts_nothing(fresh_queue):
    """deploy.sh pauses the queue before its final check: no job may start during tests + restart."""
    jobs = fresh_queue
    j = jobs.enqueue("daily_car_edit", {})
    jobs.pause(minutes=5)
    try:
        assert jobs.paused() and jobs.claim_next() is None and jobs.claim(j["id"]) is None
    finally:
        jobs.resume()
    assert not jobs.paused() and jobs.claim_next()["id"] == j["id"]
    jobs.pause(minutes=-1)  # an expired pause (crashed deploy) never blocks the queue
    assert not jobs.paused()
    jobs.resume()


def test_car_comparisons_are_not_labelled_weaponx():
    import inspect
    from app.agents import pipeline
    src = inspect.getsource(pipeline)
    assert 'channel") == "autoflashx" and style == "weaponx"' in src and '": Head-to-Head"' in src
    js = open("app/static/app.js").read()
    assert "🏎️ Car Comparison" in js
