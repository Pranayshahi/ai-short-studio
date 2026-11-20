"""Daily car-edit queue routes."""
import os
import re
import io
import json
import time
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Response, Request
from fastapi.responses import FileResponse, JSONResponse

import config
from app.utils.storage import StorageManager

from app.web_app import (  # noqa: F401  shared helpers, models and singletons
    CarQueueRefillRequest,
    CarQueueUpdateRequest,
    NO_CACHE_HEADERS,
)

router = APIRouter()


@router.get("/api/car-queue")
def get_car_queue_endpoint():
    from app.automation import car_queue, notifier
    slots = car_queue.get_queue(auto_fill=True)
    return JSONResponse(
        content={
            "slots": slots,
            "moods": car_queue.MOOD_ROTATION,
            "channel": car_queue.CHANNEL_KEY,
            "channel_id": car_queue.CHANNEL_ID,
            "notifications": notifier.is_configured(),
        },
        headers=NO_CACHE_HEADERS,
    )


@router.post("/api/car-queue/refill")
def refill_car_queue_endpoint(req: CarQueueRefillRequest):
    from app.automation import car_queue
    slots = car_queue.refill_7_day_queue(force_reset=bool(req.force_reset))
    return JSONResponse(content={"status": "success", "slots": slots}, headers=NO_CACHE_HEADERS)


@router.post("/api/car-queue/{slot_id}/update")
def update_car_queue_slot_endpoint(slot_id: str, req: CarQueueUpdateRequest):
    from app.automation import car_queue
    updated = car_queue.update_slot(slot_id, req.dict(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail=f"Queue slot '{slot_id}' not found")
    return JSONResponse(content={"status": "success", "slot": updated, "slots": car_queue.get_queue(auto_fill=False)}, headers=NO_CACHE_HEADERS)


@router.post("/api/car-queue/{slot_id}/run")
def run_car_queue_slot_endpoint(slot_id: str, background_tasks: BackgroundTasks):
    """Runs one slot from the 7-day Car Edit queue in the background and dispatches Telegram approval."""
    from app.automation import car_queue
    slots = car_queue.get_queue(auto_fill=True)
    slot = next((s for s in slots if s.get("id") == slot_id), None)
    if not slot:
        raise HTTPException(status_code=404, detail=f"Queue slot '{slot_id}' not found")

    enq = car_queue.enqueue_slot_job(slot_id=slot_id)
    job = enq["job"]
    from app.automation import jobs as _jobs
    if _jobs.worker_alive("daily_car_edit"):
        # The scheduler's worker runs it (one video at a time for the whole machine)
        pos = _jobs.queue_position(job["id"]) or 1
        return JSONResponse(content={
            "status": "queued", "slot_id": slot_id, "job_id": job["id"], "car_name": slot["car_name"],
            "mood_label": slot["mood_label"], "queue_position": pos,
            "message": f"Queued Daily Car Edit for '{slot['car_name']}'" + ("" if pos <= 1 else f" ({pos - 1} ahead)"),
        }, headers=NO_CACHE_HEADERS)

    def _worker():
        try:
            # run THIS slot's job (claim_next() used to grab the oldest job of any kind)
            claimed = _jobs.claim(job["id"]) or job
            res = car_queue.run_car_edit_job(claimed)
            _jobs.complete(claimed["id"], res)
        except Exception as e:
            car_queue.update_slot(slot_id, {"status": "failed", "error": str(e)[:300]})
            print(f"[CarQueue] Slot {slot_id} failed: {e}")

    background_tasks.add_task(_worker)
    return JSONResponse(
        content={
            "status": "started",
            "slot_id": slot_id,
            "job_id": job["id"],
            "car_name": slot["car_name"],
            "mood_label": slot["mood_label"],
            "message": f"Started Daily Car Edit for '{slot['car_name']}' ({slot['mood_label']})",
        },
        headers=NO_CACHE_HEADERS,
    )


@router.post("/api/car-queue/poll-telegram")
def poll_telegram_approvals_endpoint():
    """Polls Telegram getUpdates for any Approve/Reject button presses and updates project + queue status."""
    from app.automation import car_queue, notifier, publish_gate
    handled = notifier.poll_decisions(publish_gate.handle_decision)
    return JSONResponse(
        content={
            "status": "success",
            "handled_decisions": handled,
            "slots": car_queue.get_queue(auto_fill=False),
        },
        headers=NO_CACHE_HEADERS,
    )

