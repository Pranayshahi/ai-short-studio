import json
import os
import tempfile
import threading
import fcntl
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import config

HISTORY_FILE = config.OUTPUT_DIR / "history.json"
PROJECTS_INDEX_FILE = config.OUTPUT_DIR / "projects_index.json"

# Serializes read-modify-write cycles across the web server's worker threads...
_THREAD_LOCK = threading.RLock()
# ...and across processes (web server + background scheduler share these JSON files)
_LOCK_FILE = config.OUTPUT_DIR / ".storage.lock"


@contextmanager
def _locked():
    with _THREAD_LOCK:
        _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOCK_FILE, "a+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


_LOCK = None  # kept for backwards compatibility; use _locked()

class StorageManager:
    @staticmethod
    def _read_json(file_path: Path, default_val: Any, strict: bool = False) -> Any:
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                if strict:
                    # Never fall back to an empty default before a write: that would wipe all records
                    raise RuntimeError(f"[StorageManager] {file_path} is unreadable ({e}); refusing to overwrite it.")
                print(f"[StorageManager] Warning: could not read {file_path}: {e}")
                return default_val
        return default_val

    @staticmethod
    def _write_json(file_path: Path, data: Any) -> None:
        """Atomic write: temp file in the same directory, then os.replace."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(file_path.parent), prefix=f".{file_path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, file_path)
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            print(f"[StorageManager] Error writing {file_path}: {e}")
            raise

    @classmethod
    def get_history(cls) -> List[str]:
        return cls._read_json(HISTORY_FILE, [])

    @classmethod
    def add_to_history(cls, topic: str) -> None:
        with _locked():
            history = cls._read_json(HISTORY_FILE, [], strict=True)
            if topic not in history:
                history.append(topic)
                cls._write_json(HISTORY_FILE, history)

    @classmethod
    def get_all_projects(cls) -> List[Dict[str, Any]]:
        return cls._read_json(PROJECTS_INDEX_FILE, [])

    @classmethod
    def save_project(cls, project_data: Dict[str, Any]) -> None:
        with _locked():
            projects = cls._read_json(PROJECTS_INDEX_FILE, [], strict=True)
            # Update existing or append new
            project_id = project_data.get("id")
            existing_idx = next((i for i, p in enumerate(projects) if p.get("id") == project_id), None)

            project_data["updated_at"] = datetime.now().isoformat()
            if existing_idx is not None:
                projects[existing_idx] = project_data
            else:
                project_data.setdefault("created_at", datetime.now().isoformat())
                projects.insert(0, project_data)  # newest first

            cls._write_json(PROJECTS_INDEX_FILE, projects)

    @classmethod
    def get_project_by_id(cls, project_id: str) -> Optional[Dict[str, Any]]:
        projects = cls.get_all_projects()
        for p in projects:
            if p.get("id") == project_id:
                return p
        return None

    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        """Removes project metadata and deletes project folder from disk."""
        import shutil
        with _locked():
            projects = cls._read_json(PROJECTS_INDEX_FILE, [], strict=True)
            target = next((p for p in projects if p.get("id") == project_id), None)
            if not target:
                return False

            # 1. Remove from list and save
            updated = [p for p in projects if p.get("id") != project_id]
            cls._write_json(PROJECTS_INDEX_FILE, updated)

        # 2. Delete project directory from disk
        p_dir = target.get("project_dir")
        if p_dir and Path(p_dir).exists():
            shutil.rmtree(p_dir, ignore_errors=True)

        return True
