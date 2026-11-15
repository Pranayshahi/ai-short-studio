import os
import json
import time
import urllib.request
from datetime import datetime
from typing import Dict, Any, Optional
try:
    import pytz
except ImportError:
    pytz = None

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
except ImportError:
    BlockingScheduler = None
import config

def send_webhook_alert(project_record: Optional[Dict[str, Any]], error: Optional[str] = None) -> Dict[str, Any]:
    """
    Phase 2 Webhook Alerts:
    Dispatches rich mobile notification alerts via Discord Webhook and Telegram Bot.
    Includes:
      - Video Title & Topic
      - Quality Score (e.g. 92% PASSED)
      - Duration & Video file path
      - Direct YouTube Shorts link or local Studio review URL
    """
    results = {"discord": None, "telegram": None}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if error:
        title = "❌ Automated Short Pipeline Failed"
        description = f"Error during autonomous run at {now_str}:\n```{error[:500]}```"
        color = 15682628 # Red
        fields = [{"name": "Status", "value": "FAILED", "inline": True}]
    else:
        rec = project_record or {}
        qa = rec.get("qa_report") or rec.get("verify_video_report") or {}
        qa_score = qa.get("overall_score", 90)
        qa_status = qa.get("status", "PASSED")
        topic = rec.get("topic", "Autonomous Topic")
        category = rec.get("category", "Defense & Military")
        title = rec.get("title") or f"Autonomous Short: {topic}"
        yt_data = rec.get("youtube") or {}
        yt_url = yt_data.get("url")
        duration = rec.get("target_duration") or qa.get("stream_checks", {}).get("duration_seconds", 25.0)

        description = f"Autonomous Short produced end-to-end at {now_str}."
        color = 62206 # Vibrant Cyan (#00f2fe)
        fields = [
            {"name": "🛡️ Quality Score", "value": f"**{qa_score}%** ({qa_status})", "inline": True},
            {"name": "🎯 Niche / Category", "value": f"{category}", "inline": True},
            {"name": "⏱️ Target Duration", "value": f"{duration}s", "inline": True},
        ]
        if yt_url:
            fields.append({"name": "🚀 YouTube Shorts Link", "value": f"[Watch Short Live]({yt_url})", "inline": False})
        else:
            fields.append({"name": "💻 Web Studio Review", "value": f"[Review on Dashboard](http://localhost:8000)", "inline": False})

    # 1. Dispatch Discord Webhook if configured
    discord_url = getattr(config, "DISCORD_WEBHOOK_URL", "") or os.getenv("DISCORD_WEBHOOK_URL", "")
    if discord_url and discord_url.startswith("http"):
        try:
            discord_payload = {
                "username": "AI Shorts Studio Bot",
                "avatar_url": "https://cdn-icons-png.flaticon.com/512/1384/1384060.png",
                "embeds": [{
                    "title": title,
                    "description": description,
                    "color": color,
                    "fields": fields,
                    "footer": {"text": "AI Shorts Studio • Autonomous Channel Engine"}
                }]
            }
            req = urllib.request.Request(
                discord_url,
                data=json.dumps(discord_payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "AIShortsStudio/2.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                results["discord"] = f"Delivered (HTTP {resp.status})"
                print(f"[Webhook] Discord notification dispatched: HTTP {resp.status}")
        except Exception as e:
            results["discord"] = f"Failed: {e}"
            print(f"[Webhook Warning] Discord dispatch error: {e}")

    # 2. Dispatch Telegram Bot alert if configured
    tg_token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = getattr(config, "TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        try:
            tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            msg_lines = [
                f"🎬 *{title}*",
                description,
                "",
            ]
            for f in fields:
                msg_lines.append(f"• *{f['name']}:* {f['value']}")

            tg_payload = {
                "chat_id": tg_chat,
                "text": "\n".join(msg_lines),
                "parse_mode": "Markdown"
            }
            req = urllib.request.Request(
                tg_url,
                data=json.dumps(tg_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                results["telegram"] = f"Delivered (HTTP {resp.status})"
                print(f"[Webhook] Telegram alert dispatched: HTTP {resp.status}")
        except Exception as e:
            results["telegram"] = f"Failed: {e}"
            print(f"[Webhook Warning] Telegram dispatch error: {e}")

    if not discord_url and not (tg_token and tg_chat):
        print(f"[Webhook Alert] Ready for dispatch (Title: '{title}'). Configure DISCORD_WEBHOOK_URL or TELEGRAM_BOT_TOKEN in .env for instant mobile push notifications.")

    return results

# =============================================================================
# Hands-off automation (Phase 1)
#   - daily job is ENQUEUED at SCHEDULE_TIME into a persistent queue (output/automation/jobs.json)
#   - a worker processes the queue with retries/back-off and resumes after crashes
#   - smart publish gate + Telegram Approve/Reject buttons
#   - health checks (alerts on change) + daily summary
# =============================================================================
import argparse
import fcntl
import sys
import threading

from app.automation import health, jobs, notifier, publish_gate

DAILY_SUMMARY_TIME = os.getenv("DAILY_SUMMARY_TIME", "21:30")
HEALTH_CHECK_MINUTES = int(os.getenv("HEALTH_CHECK_MINUTES", "30"))
_PID_LOCK = config.OUTPUT_DIR / "automation" / ".scheduler.pid.lock"


def scheduled_job():
    """Daily trigger: enqueue today's Short (deduplicated per day). The worker runs it."""
    key = f"daily-{datetime.now():%Y-%m-%d}"
    job = jobs.enqueue("daily_short", {}, dedupe_key=key)
    print(f"⏰ [Scheduler] Daily trigger at {datetime.now():%H:%M}: queued job {job['id']} ({key})")
    return job


def _run_daily_short(job: Dict[str, Any]) -> Dict[str, Any]:
    from app.agents.pipeline import ShortsPipeline
    from app.utils.storage import StorageManager

    # Resume: a previous attempt may have left its project 'in_progress' when the process died
    prev_pid = job.get("project_id")
    if prev_pid:
        prev = StorageManager.get_project_by_id(prev_pid)
        if prev and prev.get("status") == "in_progress":
            prev["status"] = "failed"
            prev["error"] = "Interrupted; the scheduler retried this job as a new project."
            StorageManager.save_project(prev)

    params = job.get("params") or {}
    topic = params.get("topic")
    if not topic:
        from agents.topic_agent import TopicAgent
        discovered = TopicAgent().discover_viral_trending_topic()
        topic = discovered.get("topic")
    jobs.heartbeat(job["id"], f"Generating: {topic}")

    pipeline = ShortsPipeline()
    record, topic_info = pipeline.prepare_project(
        custom_topic=topic,
        style=params.get("style", "default"),
        duration=params.get("duration"),
        language=params.get("language", "en"),
    )
    jobs.heartbeat(job["id"], f"Generating: {topic}", project_id=record["id"])

    stop = threading.Event()

    def beat():
        while not stop.wait(60):
            jobs.heartbeat(job["id"])
    t = threading.Thread(target=beat, daemon=True)
    t.start()
    try:
        record = pipeline.run(auto_publish=False, prepared_project=record, prepared_topic_info=topic_info)
    finally:
        stop.set()

    decision = publish_gate.publish_or_request_approval(record)
    return {"project_id": record["id"], "topic": topic, "publish": decision.get("action")}


def process_queue():
    """Runs at most one due job (the pipeline uses most of the Mac's resources)."""
    job = jobs.claim_next()
    if not job:
        return None
    print(f"▶️ [Scheduler] Running job {job['id']} ({job['kind']}), attempt {job['attempts']}/{job.get('max_attempts')}")
    try:
        if job["kind"] == "daily_short":
            result = _run_daily_short(job)
        else:
            raise ValueError(f"Unknown job kind: {job['kind']}")
        jobs.complete(job["id"], result)
        print(f"✅ [Scheduler] Job {job['id']} done: {result}")
        return result
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        updated = jobs.fail(job["id"], err)
        print(f"❌ [Scheduler] Job {job['id']} failed: {err}")
        if updated and updated["status"] == "failed":
            notifier.send(f"❌ Daily Short failed after {updated['attempts']} attempts.\nLast error: {err[:400]}",
                          title="Automation failed")
        elif updated:
            notifier.send(f"⚠️ Daily Short attempt {updated['attempts']} failed ({err[:200]}). Retrying at {updated['next_run_at'][11:16]}.")
        return None


def build_music_library():
    """Nightly: grow the mood music library with ACE-Step while nothing else needs the memory."""
    from app.automation import music_library
    res = music_library.build_overnight()
    print(f"🎵 [Scheduler] Music library: {res}")
    if res.get("generated"):
        notifier.send(f"🎵 Added {len(res['generated'])} music tracks overnight "
                      f"({res['moods_covered']}/{res['moods_total']} moods covered).")
    return res


def poll_approvals():
    try:
        notifier.poll_decisions(publish_gate.handle_decision)
    except Exception as e:
        print(f"[Scheduler] Approval poll error: {e}")


def _single_instance():
    _PID_LOCK.parent.mkdir(parents=True, exist_ok=True)
    fh = open(_PID_LOCK, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[Scheduler] Another scheduler is already running; exiting.")
        sys.exit(0)
    fh.write(str(os.getpid()))
    fh.flush()
    return fh  # keep the handle open for the lifetime of the process


def main():
    parser = argparse.ArgumentParser(description="AI Shorts Studio hands-off scheduler")
    parser.add_argument("--run-now", action="store_true", help="Queue a Short immediately and process it")
    parser.add_argument("--topic", help="Topic for --run-now (default: discover a trending topic)")
    parser.add_argument("--status", action="store_true", help="Print queue, health and resource status")
    parser.add_argument("--summary", action="store_true", help="Send the daily summary now")
    parser.add_argument("--test-alert", action="store_true", help="Send a test notification")
    parser.add_argument("--build-music", type=int, metavar="N", help="Generate N music library tracks now")
    args = parser.parse_args()

    if args.status:
        from app.automation import resources
        print(json.dumps({"jobs": jobs.all_jobs()[-10:], "health": health.check_all(alert=False),
                          "resources": resources.status(), "notifications": notifier.is_configured(),
                          "publish_mode": publish_gate.MODE}, indent=2, default=str))
        return
    if args.summary:
        print(health.daily_summary())
        return
    if args.build_music:
        from app.automation import music_library
        print(music_library.build_overnight(max_tracks=args.build_music))
        return
    if args.test_alert:
        print(notifier.send("✅ AI Shorts Studio test alert: notifications are working.", title="Test"))
        return
    if args.run_now:
        jobs.enqueue("daily_short", {"topic": args.topic} if args.topic else {})
        _lock = _single_instance()
        jobs.recover_interrupted(force=True)
        while process_queue():
            pass
        return

    if BlockingScheduler is None or pytz is None:
        print("[Scheduler Warning] apscheduler or pytz not installed. Run with: .venv/bin/python scheduler.py")
        return

    _lock = _single_instance()
    resumed = jobs.recover_interrupted(force=True)
    if resumed:
        print(f"[Scheduler] Resuming {len(resumed)} interrupted job(s): {resumed}")
    jobs.prune()

    tz = pytz.timezone(config.SCHEDULE_TIMEZONE)
    hour, minute = map(int, config.SCHEDULE_TIME.split(":"))
    s_hour, s_min = map(int, DAILY_SUMMARY_TIME.split(":"))

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(scheduled_job, "cron", hour=hour, minute=minute, id="daily_enqueue", misfire_grace_time=6 * 3600, coalesce=True)
    scheduler.add_job(process_queue, "interval", minutes=1, id="worker", max_instances=1, coalesce=True)
    scheduler.add_job(poll_approvals, "interval", seconds=20, id="approvals", max_instances=1, coalesce=True)
    scheduler.add_job(health.check_all, "interval", minutes=HEALTH_CHECK_MINUTES, id="health", max_instances=1,
                      coalesce=True, next_run_time=datetime.now(tz))
    scheduler.add_job(health.daily_summary, "cron", hour=s_hour, minute=s_min, id="summary", coalesce=True)
    m_hour, m_min = map(int, os.getenv("MUSIC_LIBRARY_TIME", "02:30").split(":"))
    scheduler.add_job(build_music_library, "cron", hour=m_hour, minute=m_min, id="music_library",
                      max_instances=1, coalesce=True, misfire_grace_time=3 * 3600)

    print("=" * 60)
    print("🤖 [AI Shorts Studio] Hands-off scheduler active")
    print(f"📍 Timezone {config.SCHEDULE_TIMEZONE} · daily Short {config.SCHEDULE_TIME} · summary {DAILY_SUMMARY_TIME}")
    print(f"🛡️ Publish mode: {publish_gate.MODE} · notifications: {notifier.is_configured()}")
    print("=" * 60)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nStopping scheduler...")


if __name__ == "__main__":
    main()
