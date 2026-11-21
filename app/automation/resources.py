"""
Memory manager for heavy local AI services on an 18 GB Mac.

ACE-Step (music, ~10-21 GB once models are loaded) and Phosphene (LTX-2.5 video, most of RAM
while rendering) must never run at the same time. Use:

    with resources.lease("acestep"):
        ... generate music ...

lease() starts the service if needed (stopping the OTHER heavy service first if it is idle),
waits until it is healthy, and stops it again afterwards if lease() was the one that started it.
A busy service is never stopped: lease() raises ResourceBusy instead.
"""
from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional

import config

PROJECT_DIR = Path(config.BASE_DIR)
LOG_DIR = config.OUTPUT_DIR / "automation"
LOG_DIR.mkdir(parents=True, exist_ok=True)

SERVICES: Dict[str, Dict] = {
    "acestep": {
        "port": 8001,
        "start": [str(PROJECT_DIR / "scripts" / "start_acestep.sh")],
        "health": "http://127.0.0.1:8001/health",
        "start_timeout": 480,  # cold starts under memory pressure took >240 s (nightly runs failed)
        "min_free_pct": 35,   # ACE-Step grows to ~21 GB incl. swap after its first generation
    },
    "phosphene": {
        "port": 8198,
        "start": [str(Path.home() / "phosphene" / "run_panel.sh"), "--bg"],
        "health": "http://127.0.0.1:8198/agents/info",
        "start_timeout": 120,
        "min_free_pct": 45,   # an LTX render needs most of the 18 GB
    },
    "ollama": {
        "port": 11434,
        "start": ["/opt/homebrew/opt/ollama/bin/ollama", "serve"],
        "health": "http://127.0.0.1:11434/api/tags",
        "start_timeout": 60,
        "min_free_pct": 25,   # Qwen 2.5 7B needs ~5-6 GB while loaded (unloaded right after use)
    },
}
HEAVY = ("acestep", "phosphene", "ollama")


class ResourceBusy(RuntimeError):
    pass


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_running(name: str) -> bool:
    return _port_open(SERVICES[name]["port"])


def _healthy(name: str) -> bool:
    try:
        with urllib.request.urlopen(SERVICES[name]["health"], timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def is_busy(name: str) -> bool:
    """True if the service is doing work right now (never stop it then)."""
    if not is_running(name):
        return False
    if name == "phosphene":
        try:
            raw = urllib.request.urlopen("http://127.0.0.1:8198/status", timeout=10).read()
            st = json.loads(re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b" ", raw).decode("utf-8", "replace"), strict=False)
            return bool(st.get("running") or st.get("current") or st.get("queue"))
        except Exception:
            return True  # unknown -> assume busy (safe)
    if name == "ollama":
        try:
            ps = json.loads(urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=5).read())
            return bool(ps.get("models"))  # a model is loaded = generating (we unload right after use)
        except Exception:
            return False
    if name == "acestep":
        lock = LOG_DIR / ".acestep_in_use"
        return lock.exists() and time.time() - lock.stat().st_mtime < 900
    return True


def holds_models(name: str) -> bool:
    """True if the service currently has large models loaded. Idle Ollama (no model) and an idle
    Phosphene panel (helper not alive, ~2 GB) are cheap, so they are left running for the user."""
    if not is_running(name):
        return False
    if name == "ollama":
        try:
            return bool(json.loads(urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=5).read()).get("models"))
        except Exception:
            return False
    if name == "phosphene":
        try:
            raw = urllib.request.urlopen("http://127.0.0.1:8198/status", timeout=10).read()
            st = json.loads(re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b" ", raw).decode("utf-8", "replace"), strict=False)
            return bool((st.get("helper") or {}).get("alive"))
        except Exception:
            return True
    return True  # ACE-Step keeps its models resident while running


def free_memory_pct() -> Optional[int]:
    """macOS 'System-wide memory free percentage' (None if unavailable)."""
    try:
        out = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"free percentage:\s*(\d+)%", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _listening_pids(port: int):
    try:
        out = subprocess.run(["lsof", "-tiTCP:%d" % port, "-sTCP:LISTEN"], capture_output=True, text=True, timeout=10).stdout
        return [int(p) for p in out.split()]
    except Exception:
        return []


def stop(name: str, wait: int = 30) -> bool:
    """Gracefully stops a service (SIGTERM, then SIGKILL). Refuses if it is busy."""
    if not is_running(name):
        return True
    if is_busy(name):
        raise ResourceBusy(f"{name} is busy; not stopping it.")
    pids = _listening_pids(SERVICES[name]["port"])
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + wait
    while time.time() < deadline and is_running(name):
        time.sleep(1)
    if is_running(name):
        for pid in _listening_pids(SERVICES[name]["port"]):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(1)
    print(f"[Resources] Stopped {name} to free memory.")
    return not is_running(name)


def start(name: str) -> None:
    svc = SERVICES[name]
    if is_running(name):
        return
    # One heavy service at a time
    for other in (h for h in HEAVY if h in SERVICES):
        if other != name and is_running(other):
            if is_busy(other):
                raise ResourceBusy(f"Can't start {name}: {other} is busy and both don't fit in memory.")
            if holds_models(other):  # only stop a service that is holding big models in memory
                stop(other)
    free = free_memory_pct()
    if free is not None and free < svc["min_free_pct"]:
        raise ResourceBusy(f"Can't start {name}: only {free}% memory free (needs {svc['min_free_pct']}%).")
    if not Path(svc["start"][0]).exists():
        raise RuntimeError(f"{name} start script not found: {svc['start'][0]}")
    log = open(LOG_DIR / f"{name}.log", "ab")
    subprocess.Popen(svc["start"], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    # monotonic: stops while the Mac sleeps, so a start interrupted by sleep isn't declared failed on wake
    deadline = time.monotonic() + svc["start_timeout"]
    while time.monotonic() < deadline:
        if _healthy(name):
            print(f"[Resources] {name} is up.")
            return
        time.sleep(2)
    raise RuntimeError(f"{name} did not become healthy within {svc['start_timeout']}s (see {LOG_DIR / (name + '.log')}).")


@contextmanager
def lease(name: str, keep_running: bool = False):
    """Use a heavy service for one task; stop it afterwards if this lease started it."""
    for other in (h for h in HEAVY if h in SERVICES):
        if other != name and is_busy(other):
            raise ResourceBusy(f"{other} is busy; not running {name} at the same time (memory).")
    started_here = not is_running(name)
    start(name)
    marker = LOG_DIR / f".{name}_in_use"
    marker.touch()
    try:
        yield
    finally:
        try:
            marker.unlink()
        except OSError:
            pass
        if started_here and not keep_running:
            try:
                stop(name)
            except ResourceBusy:
                pass


def status() -> Dict[str, Dict]:
    return {n: {"running": is_running(n), "busy": is_busy(n)} for n in SERVICES} | {"memory_free_pct": free_memory_pct()}


def is_registered(name: str) -> bool:
    return name in SERVICES
