"""Small JSON state store shared by the scheduler and the web server (file-locked, atomic)."""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

import config

STATE_DIR = config.OUTPUT_DIR / "automation"
STATE_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def _file_lock(name: str):
    lock_path = STATE_DIR / f".{name}.lock"
    with open(lock_path, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _path(name: str) -> Path:
    return STATE_DIR / f"{name}.json"


def read(name: str, default: Any) -> Any:
    p = _path(name)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(name: str, data: Any) -> None:
    p = _path(name)
    fd, tmp = tempfile.mkstemp(dir=str(STATE_DIR), prefix=f".{name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def update(name: str, default: Any, fn: Callable[[Any], Any]) -> Any:
    """Atomically read-modify-write a state file. fn receives the current value and returns the new one."""
    with _file_lock(name):
        current = read(name, default)
        new = fn(current)
        _write(name, new)
        return new
