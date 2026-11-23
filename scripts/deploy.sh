#!/usr/bin/env bash
# The one safe way to put new code live: restarts the web dashboard AND the scheduler together.
#   scripts/deploy.sh             refuse if a video is generating/queued, else test + restart + verify
#   scripts/deploy.sh --wait      wait (up to 2 h) until nothing is generating, then deploy
#   scripts/deploy.sh --check-only   exit 0 if it is safe to restart right now, 1 if not
# Restarting while a video renders kills that video, so this never does it.
set -uo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1
PY="$PROJECT_DIR/.venv/bin/python"
UIDN="$(id -u)"
WEB="com.aishortsstudio.web"
SCHED="com.aishortsstudio.scheduler"
PORT="${STUDIO_PORT:-8000}"
MODE="${1:-}"
# the dashboard may require the studio token (STUDIO_API_TOKEN in .env)
TOKEN="$(grep -E '^STUDIO_API_TOKEN=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
AUTH=()
[ -n "$TOKEN" ] && AUTH=(-H "X-Studio-Token: $TOKEN")

busy() {  # prints what is busy; exit status 0 = busy
  "$PY" - <<'PYEOF'
import sys
sys.path.insert(0, ".")
from app.utils.storage import StorageManager
from app.automation import jobs
busy = [f"project {p['id']} ({p['status']})" for p in StorageManager.get_all_projects() if p.get("status") in ("in_progress", "queued")]
busy += [f"job {j['id']} ({j['kind']}) running" for j in jobs.all_jobs() if j["status"] == "running"]
print("\n".join(busy))
sys.exit(0 if busy else 1)
PYEOF
}

queue() {  # pause / resume the job queue (see app/automation/jobs.pause)
  "$PY" -c "import sys; sys.path.insert(0, '.'); from app.automation import jobs; jobs.$1()"
}
# Pause the queue BEFORE the last 'nothing running' check, so no job can start during the tests and get
# cut off by the restart; always resume on exit (success, failure or Ctrl-C).
trap 'queue resume >/dev/null 2>&1' EXIT
if [ "$MODE" = "--wait" ]; then
  for _ in $(seq 1 720); do
    queue pause
    busy >/dev/null || break
    queue resume; sleep 10
  done
else
  queue pause
fi
if out="$(busy)"; then
  echo "NOT restarting: still busy:"; echo "$out"
  echo "Run again when it's done, or use: scripts/deploy.sh --wait"
  exit 1
fi
[ "$MODE" = "--check-only" ] && { echo "Safe to restart (nothing generating)."; exit 0; }

echo "1/4 Tests..."
"$PY" -m pytest -q -x || { echo "Tests failed: NOT deploying."; exit 1; }

echo "2/4 Restarting the web dashboard..."
OLD_PIDS="$(pgrep -f "main.py --server" || true)"
if launchctl print "gui/$UIDN/$WEB" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$UIDN/$WEB"
else
  [ -n "$(lsof -tiTCP:"$PORT" -sTCP:LISTEN)" ] && kill $(lsof -tiTCP:"$PORT" -sTCP:LISTEN) 2>/dev/null
  sleep 3
  nohup "$PY" main.py --server --port "$PORT" >> output/automation/web.log 2>&1 &
  echo "   (not installed as a service yet: run scripts/install_web_service.sh once)"
fi
# An old server can survive SIGTERM as an orphan (non-daemon render thread): nothing renders now, so end it
sleep 4
for pid in $OLD_PIDS; do
  if kill -0 "$pid" 2>/dev/null && [ "$pid" != "$(lsof -tiTCP:"$PORT" -sTCP:LISTEN)" ]; then kill -9 "$pid" 2>/dev/null && echo "   ended orphaned old server $pid"; fi
done

echo "3/4 Restarting the scheduler..."
if launchctl print "gui/$UIDN/$SCHED" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$UIDN/$SCHED"
else
  echo "   scheduler service not installed (scripts/install_scheduler.sh)"
fi

echo "4/4 Verifying..."
ok_web=0; ok_worker=0
for _ in $(seq 1 30); do
  curl -sf "${AUTH[@]}" "http://127.0.0.1:$PORT/api/ui-build" >/dev/null && ok_web=1
  "$PY" -c "import sys; sys.path.insert(0,'.'); from app.automation import jobs; sys.exit(0 if jobs.worker_alive('studio_generate') else 1)" && ok_worker=1
  [ $ok_web = 1 ] && [ $ok_worker = 1 ] && break
  sleep 3
done
echo "   web dashboard: $([ $ok_web = 1 ] && echo OK || echo NOT RESPONDING - see output/automation/web.log)"
echo "   video worker:  $([ $ok_worker = 1 ] && echo OK || echo NO HEARTBEAT - see output/automation/scheduler.log)"
[ $ok_web = 1 ] && [ $ok_worker = 1 ] && echo "Deployed $(git rev-parse --short HEAD)." || exit 1
