"""
Daily Car Edit Automation: 7-Day Rolling Queue, Mood Rotation & Telegram Approval
---------------------------------------------------------------------------------
Manages a 7-day rolling queue of daily Car Edits for @AutoFlashX (UCuJ9LcSqliLH0VEJ9lWZsrQ):
  - Daily car edit: 1 scheduled car edit per day (auto-enqueued by scheduler.py or run on demand)
  - Mood rotation: 7 distinct Phonk + Motion + Beat-Sync mood profiles rotated across the week
  - Telegram approval: Sends the rendered MP4 video + inline Approve/Reject buttons to Telegram;
    Approve uploads/keeps the Short PRIVATE on @AutoFlashX (UCuJ9LcSqliLH0VEJ9lWZsrQ)
  - 7-day queue: Persistent 7-day lookahead schedule stored in output/automation/car_queue.json
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.automation import jobs, notifier, publish_gate, state
from app.utils.storage import StorageManager

QUEUE_STATE_NAME = "car_queue"
CHANNEL_KEY = "autoflashx"
CHANNEL_ID = "UCuJ9LcSqliLH0VEJ9lWZsrQ"

# 7-Day Mood Rotation Profiles (each day of the week gets a distinct Phonk + Motion + Cut feel)
MOOD_ROTATION: List[Dict[str, Any]] = [
    {
        "mood_id": "drift_phonk_velocity",
        "label": "🔥 Drift Phonk · Velocity Cuts",
        "phonk_style": "drift_phonk",
        "bpm": 130,
        "beat_sync_mode": "swxft_velocity",
        "car_motion_preset": "swxft_dynamic",
        "duration": 20.0,
        "style": "car_edit",
    },
    {
        "mood_id": "brazilian_phonk_rapid",
        "label": "⚡ Hard Brazilian Phonk · 2-Beat Rapid Cuts",
        "phonk_style": "brazilian_phonk",
        "bpm": 135,
        "beat_sync_mode": "every_2_beats",
        "car_motion_preset": "zoom_punch",
        "duration": 20.0,
        "style": "car_edit",
    },
    {
        "mood_id": "night_drive_wave",
        "label": "🌙 Midnight Wave Phonk · Slow-Mo Hero Holds",
        "phonk_style": "night_drive",
        "bpm": 124,
        "beat_sync_mode": "every_4_beats",
        "car_motion_preset": "cinematic_pan",
        "duration": 20.0,
        "style": "car_edit",
    },
    {
        "mood_id": "touge_jdm_attack",
        "label": "🎌 JDM Touge Attack · Whip-In Velocity",
        "phonk_style": "drift_phonk",
        "bpm": 130,
        "beat_sync_mode": "whip_in",
        "car_motion_preset": "swxft_dynamic",
        "duration": 20.0,
        "style": "car_edit",
    },
    {
        "mood_id": "hypercar_royalty",
        "label": "👑 Hypercar Royalty · Beat Drop + Speed Ramps",
        "phonk_style": "brazilian_phonk",
        "bpm": 135,
        "beat_sync_mode": "swxft_velocity",
        "car_motion_preset": "swxft_dynamic",
        "duration": 20.0,
        "style": "car_edit",
    },
    {
        "mood_id": "nurburgring_track",
        "label": "🏁 Track Weapon · High-Energy Zoom Punch",
        "phonk_style": "drift_phonk",
        "bpm": 130,
        "beat_sync_mode": "every_2_beats",
        "car_motion_preset": "zoom_punch",
        "duration": 20.0,
        "style": "car_edit",
    },
    {
        "mood_id": "vs_spec_showdown",
        "label": "⚔️ 'A vs B vs C' Head-to-Head Showdown",
        "phonk_style": "night_drive",
        "bpm": 124,
        "beat_sync_mode": "every_4_beats",
        "car_motion_preset": "cinematic_pan",
        "duration": 20.0,
        "style": "comparison",
    },
]

# Curated roster of high-retention enthusiasts / supercar / hypercar topics
CAR_ROSTER: List[str] = [
    "Porsche 911 GT3 RS",
    "Bugatti Tourbillon",
    "Nissan Skyline GT-R R34",
    "Ferrari F80",
    "Lamborghini Revuelto",
    "Toyota Supra MK4",
    "Porsche 911 GT3 RS vs Ferrari SF90 vs Lamborghini Revuelto",
    "Koenigsegg Jesko",
    "BMW M4 Competition",
    "McLaren P1",
    "Mercedes-AMG GT Black Series",
    "Mazda RX-7 FD3S",
    "Bugatti Chiron Super Sport",
    "Bugatti Tourbillon vs Koenigsegg Jesko vs Rimac Nevera",
    "Chevrolet Corvette ZR1",
    "Lamborghini Huracán STO",
    "Audi R8 V10 Performance",
    "McLaren 765LT",
    "Ford Mustang GTD",
    "Pagani Huayra R",
    "Nissan GT-R R34 vs Toyota Supra MK4 vs Mazda RX-7",
]

VS_SHOWDOWN_ROSTER: List[str] = [
    "Porsche 911 GT3 RS vs Ferrari SF90 vs Lamborghini Revuelto",
    "Bugatti Tourbillon vs Koenigsegg Jesko vs Rimac Nevera",
    "Nissan GT-R R34 vs Toyota Supra MK4 vs Mazda RX-7",
    "BMW M4 vs Mercedes-AMG GT vs Audi R8",
    "Ferrari F80 vs McLaren P1 vs Porsche 911 GT3 RS",
]


def _today() -> date:
    return datetime.now().date()


def get_queue(auto_fill: bool = True) -> List[Dict[str, Any]]:
    """Returns the 7-day car edit queue, automatically filling any missing upcoming days."""
    slots = state.read(QUEUE_STATE_NAME, [])
    if auto_fill:
        today_str = _today().isoformat()
        upcoming = [s for s in slots if s.get("scheduled_date", "") >= today_str]
        if len(upcoming) < 7:
            slots = refill_7_day_queue()
    return slots


def refill_7_day_queue(start_date: Optional[date] = None, force_reset: bool = False) -> List[Dict[str, Any]]:
    """
    Ensures the next 7 days (Day 1..Day 7 starting from today) each have a scheduled Car Edit slot
    with rotating mood profiles and non-repeating cars.
    """
    base_date = start_date or _today()
    existing = [] if force_reset else state.read(QUEUE_STATE_NAME, [])
    by_date: Dict[str, Dict[str, Any]] = {s["scheduled_date"]: s for s in existing if s.get("scheduled_date")}

    # Track recently used topics so we don't repeat cars within the window
    used_topics = {s.get("car_name", "").lower() for s in existing if s.get("car_name")}
    for p in StorageManager.get_all_projects()[:14]:
        if p.get("topic"):
            used_topics.add(str(p["topic"]).lower())

    new_slots: List[Dict[str, Any]] = []
    # Keep recent past slots (last 7 days) for history visibility
    cutoff_past = (base_date - timedelta(days=7)).isoformat()
    for s in existing:
        d_str = s.get("scheduled_date", "")
        if cutoff_past <= d_str < base_date.isoformat():
            new_slots.append(s)

    for day_offset in range(7):
        target_day = base_date + timedelta(days=day_offset)
        d_str = target_day.isoformat()
        if d_str in by_date and not force_reset:
            slot = by_date[d_str]
            slot["day_index"] = day_offset + 1
            new_slots.append(slot)
            continue

        # Rotate mood deterministically by ordinal day so every day of the week has a distinct mood
        mood_idx = (target_day.toordinal() + day_offset) % len(MOOD_ROTATION)
        mood = MOOD_ROTATION[mood_idx]

        # Pick a car (or "A vs B vs C" matchup on showdown days) not yet used
        pool = VS_SHOWDOWN_ROSTER if mood["style"] == "comparison" else [c for c in CAR_ROSTER if " vs " not in c.lower()]
        chosen_car = None
        for cand in pool:
            if cand.lower() not in used_topics:
                chosen_car = cand
                break
        if not chosen_car:
            chosen_car = pool[(target_day.toordinal() + day_offset) % len(pool)]
        used_topics.add(chosen_car.lower())

        slot = {
            "id": f"car_{d_str.replace('-', '')}_{uuid.uuid4().hex[:5]}",
            "day_index": day_offset + 1,
            "scheduled_date": d_str,
            "weekday": target_day.strftime("%a, %b %d"),
            "car_name": chosen_car,
            "style": mood["style"],
            "mood_id": mood["mood_id"],
            "mood_label": mood["label"],
            "phonk_style": mood["phonk_style"],
            "bpm": mood["bpm"],
            "beat_sync_mode": mood["beat_sync_mode"],
            "car_motion_preset": mood["car_motion_preset"],
            "duration": mood["duration"],
            "channel": CHANNEL_KEY,
            "channel_id": CHANNEL_ID,
            "status": "queued",  # queued | running | awaiting_telegram_approval | approved_private | rejected | failed
            "project_id": None,
            "telegram_sent": False,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        new_slots.append(slot)

    new_slots.sort(key=lambda x: x.get("scheduled_date", ""))
    state.update(QUEUE_STATE_NAME, [], lambda _: new_slots)
    return new_slots


def update_slot(slot_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates a 7-day queue slot's car_name, mood_id, duration, or status."""
    found: Dict[str, Any] = {}

    def fn(slots):
        for s in slots:
            if s.get("id") == slot_id:
                if "car_name" in updates and updates["car_name"]:
                    s["car_name"] = str(updates["car_name"]).strip()
                    if " vs " in s["car_name"].lower():
                        s["style"] = "comparison"
                if "mood_id" in updates and updates["mood_id"]:
                    m = next((x for x in MOOD_ROTATION if x["mood_id"] == updates["mood_id"]), None)
                    if m:
                        s["mood_id"] = m["mood_id"]
                        s["mood_label"] = m["label"]
                        s["phonk_style"] = m["phonk_style"]
                        s["bpm"] = m["bpm"]
                        s["beat_sync_mode"] = m["beat_sync_mode"]
                        s["car_motion_preset"] = m["car_motion_preset"]
                        s["style"] = m["style"]
                if "duration" in updates and updates["duration"]:
                    s["duration"] = max(5.0, min(180.0, float(updates["duration"])))
                for k in ("status", "project_id", "telegram_sent", "job_id", "error"):
                    if k in updates:
                        s[k] = updates[k]
                found["slot"] = dict(s)
        return slots

    state.update(QUEUE_STATE_NAME, [], fn)
    return found.get("slot")


def enqueue_slot_job(slot_id: Optional[str] = None, for_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Enqueues a 'daily_car_edit' job into jobs.json for the specified slot (or today's slot).
    """
    slots = get_queue(auto_fill=True)
    target_slot = None
    if slot_id:
        target_slot = next((s for s in slots if s.get("id") == slot_id), None)
    if not target_slot:
        d_key = for_date or _today().isoformat()
        target_slot = next((s for s in slots if s.get("scheduled_date") == d_key), None)
    if not target_slot and slots:
        target_slot = slots[0]
    if not target_slot:
        raise ValueError("No car queue slot available.")

    dedupe = None if slot_id else f"daily-car-{target_slot['scheduled_date']}"
    job = jobs.enqueue(
        kind="daily_car_edit",
        params={
            "slot_id": target_slot["id"],
            "topic": target_slot["car_name"],
            "style": "weaponx" if target_slot.get("style") == "comparison" else "car_edit",
            "duration": target_slot.get("duration", 15.0),
            "phonk_style": target_slot.get("phonk_style", "drift_phonk"),
            "beat_sync_mode": target_slot.get("beat_sync_mode", "swxft_velocity"),
            "car_motion_preset": target_slot.get("car_motion_preset", "swxft_dynamic"),
            "mood_label": target_slot.get("mood_label", "🔥 Drift Phonk"),
            "channel": CHANNEL_KEY,
        },
        dedupe_key=dedupe,
    )
    update_slot(target_slot["id"], {"status": "running", "job_id": job["id"]})
    return {"slot": target_slot, "job": job}


def run_car_edit_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a queued daily_car_edit job through ShortsPipeline, dispatches the video + inline
    Approve/Reject buttons to Telegram, and routes approval to @AutoFlashX (UCuJ9LcSqliLH0VEJ9lWZsrQ).
    """
    from app.agents.pipeline import ShortsPipeline

    params = job.get("params") or {}
    slot_id = params.get("slot_id")
    topic = params.get("topic") or "Porsche 911 GT3 RS"
    style = params.get("style") or ("weaponx" if " vs " in topic.lower() else "car_edit")
    duration = float(params.get("duration") or 15.0)
    phonk_style = params.get("phonk_style") or "drift_phonk"
    beat_sync_mode = params.get("beat_sync_mode") or "swxft_velocity"
    car_motion_preset = params.get("car_motion_preset") or "swxft_dynamic"
    mood_label = params.get("mood_label") or "🔥 Drift Phonk · Velocity Cuts"

    if slot_id:
        update_slot(slot_id, {"status": "running", "job_id": job["id"]})

    pipeline = ShortsPipeline()
    with_voice = (style != "car_edit")
    audio_mode = "with_voice" if with_voice else "without_voice"
    record, topic_info = pipeline.prepare_project(
        custom_topic=topic,
        style=style,
        with_voice=with_voice,
        with_music=True,
        duration=duration,
        audio_mode=audio_mode,
        language="en",
        music_track=phonk_style,
        music_volume=0.25 if with_voice else 0.92,
        channel=CHANNEL_KEY,
    )
    record["phonk_style"] = phonk_style
    record["beat_sync_mode"] = beat_sync_mode
    record["car_motion_preset"] = car_motion_preset
    record["car_mood_label"] = mood_label
    record["car_queue_slot_id"] = slot_id
    StorageManager.save_project(record)

    jobs.heartbeat(job["id"], f"Car Edit: {topic} ({mood_label})", project_id=record["id"])
    record = pipeline.run(auto_publish=False, prepared_project=record, prepared_topic_info=topic_info)

    # Gate + Telegram Approval with MP4 video preview & inline Approve/Reject buttons
    decision = publish_gate.publish_or_request_approval(record)
    vid_path = record.get("video_path")
    tg_video_res = None
    if vid_path and Path(vid_path).exists():
        caption = (
            f"🏎️ *Daily Car Edit Ready for @AutoFlashX*\n"
            f"• *Car:* {topic}\n"
            f"• *Mood:* {mood_label} ({params.get('bpm', 130)} BPM)\n"
            f"• *Channel:* `UCuJ9LcSqliLH0VEJ9lWZsrQ` (Private)\n"
            f"• *Status:* {decision.get('action')}\n\n"
            f"Tap *Approve* below to lock it as PRIVATE on @AutoFlashX YouTube Studio."
        )
        tg_video_res = notifier.send_video(
            video_path=Path(vid_path),
            caption=caption,
            buttons=notifier.approval_buttons(record["id"]),
        )

    if slot_id:
        new_status = "approved_private" if record.get("status") == "approved_private" else "awaiting_telegram_approval"
        update_slot(slot_id, {
            "status": new_status,
            "project_id": record["id"],
            "telegram_sent": bool((tg_video_res or {}).get("telegram") == "sent" or notifier.is_configured().get("telegram")),
        })

    return {
        "project_id": record["id"],
        "slot_id": slot_id,
        "topic": topic,
        "mood": mood_label,
        "channel": CHANNEL_KEY,
        "publish": decision.get("action"),
        "telegram_video": tg_video_res,
    }
