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
TRASH_DIR = config.OUTPUT_DIR / ".trash"

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
        """Moves a project to the recycle bin (output/.trash) instead of erasing it.
        Restore with restore_project(); bin items older than TRASH_KEEP_DAYS are purged."""
        import shutil
        with _locked():
            projects = cls._read_json(PROJECTS_INDEX_FILE, [], strict=True)
            target = next((p for p in projects if p.get("id") == project_id), None)
            if not target:
                return False

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bin_dir = TRASH_DIR / f"{project_id}__{stamp}"
            bin_dir.mkdir(parents=True, exist_ok=True)
            p_dir = target.get("project_dir")
            if p_dir and Path(p_dir).exists():
                shutil.move(str(p_dir), str(bin_dir / "files"))
            target["deleted_at"] = datetime.now().isoformat()
            with open(bin_dir / "project_record.json", "w", encoding="utf-8") as f:
                json.dump(target, f, indent=2, ensure_ascii=False)

            # Only drop it from the index once the files are safely in the bin
            cls._write_json(PROJECTS_INDEX_FILE, [p for p in projects if p.get("id") != project_id])
        return True

    @classmethod
    def list_trash(cls) -> List[Dict[str, Any]]:
        items = []
        if TRASH_DIR.exists():
            for d in sorted(TRASH_DIR.iterdir(), reverse=True):
                rec_file = d / "project_record.json"
                if d.is_dir() and rec_file.exists():
                    try:
                        rec = json.loads(rec_file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    items.append({"trash_id": d.name, "id": rec.get("id"), "title": rec.get("title"),
                                  "topic": rec.get("topic"), "deleted_at": rec.get("deleted_at"),
                                  "has_files": (d / "files").exists()})
        return items

    @classmethod
    def restore_project(cls, trash_id: str) -> Optional[Dict[str, Any]]:
        import shutil
        bin_dir = TRASH_DIR / trash_id
        if "/" in trash_id or ".." in trash_id or not (bin_dir / "project_record.json").exists():
            return None
        with _locked():
            rec = json.loads((bin_dir / "project_record.json").read_text(encoding="utf-8"))
            projects = cls._read_json(PROJECTS_INDEX_FILE, [], strict=True)
            if any(p.get("id") == rec.get("id") for p in projects):
                raise ValueError(f"A project with id {rec.get('id')} already exists")
            dest = Path(rec.get("project_dir") or (config.PROJECTS_DIR / rec["id"]))
            if (bin_dir / "files").exists():
                if dest.exists():
                    raise ValueError(f"Folder {dest} already exists")
                shutil.move(str(bin_dir / "files"), str(dest))
            rec.pop("deleted_at", None)
            projects.insert(0, rec)
            cls._write_json(PROJECTS_INDEX_FILE, projects)
        shutil.rmtree(bin_dir, ignore_errors=True)
        return rec

    @classmethod
    def purge_trash(cls, keep_days: Optional[int] = None) -> int:
        """Permanently removes bin items older than keep_days (default TRASH_KEEP_DAYS=30)."""
        import shutil
        import os
        days = keep_days if keep_days is not None else int(os.getenv("TRASH_KEEP_DAYS", "30"))
        cutoff = datetime.now().timestamp() - days * 86400
        removed = 0
        if TRASH_DIR.exists():
            for d in TRASH_DIR.iterdir():
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
        return removed
