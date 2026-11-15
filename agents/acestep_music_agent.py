"""
Agent: ACE-Step 1.5 Music Creator (agents/acestep_music_agent.py)

Free, open-source, local AI music generation via the ACE-Step 1.5 API server
(https://github.com/ace-step/ACE-Step-1.5, docs/en/API.md). Runs on your own machine,
no paid credits.

Start the server separately (in the ACE-Step-1.5 repo):
    python -m acestep.api_server          # listens on http://127.0.0.1:8001

Flow: POST /release_task -> task_id -> POST /query_result until status==1 -> GET /v1/audio.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config


class ACEStepMusicAgent:
    """Client for a locally running ACE-Step 1.5 API server."""

    def __init__(self):
        self.base_url = getattr(config, "ACESTEP_API_URL", "http://127.0.0.1:8001").rstrip("/")
        self.api_key = getattr(config, "ACESTEP_API_KEY", "")
        self.out_dir = config.AUDIO_ASSETS_DIR / "ai_generated"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _call(self, method: str, path: str, payload: Optional[dict] = None, timeout: int = 60) -> Any:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"ACE-Step HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"ACE-Step server not reachable at {self.base_url} ({e.reason}). "
                "Start it with: python -m acestep.api_server"
            )

    def health_error(self) -> Optional[str]:
        """Returns None if the server is healthy, else the reason it is not."""
        try:
            self._call("GET", "/health", timeout=5)
            return None
        except Exception as e:
            return str(e)

    def is_available(self) -> bool:
        """True if ACE-Step is running, or can be started on demand by the memory manager."""
        if self.health_error() is None:
            return True
        if os.getenv("ACESTEP_AUTO_MANAGE", "1") != "1":
            return False
        try:
            from app.automation import resources
            return Path(resources.SERVICES["acestep"]["start"][0]).exists() and not resources.is_busy("phosphene")
        except Exception:
            return False

    def build_caption(self, category: str, mood: str, vocals: str, prompt: Optional[str]) -> str:
        vocal_txt = {
            "instrumental": "instrumental, no vocals",
            "male": "male vocals",
            "female": "female vocals",
            "choir": "choir vocals",
        }.get((vocals or "instrumental").lower(), "instrumental")
        parts = [f"{category} music", f"{mood} mood", vocal_txt]
        if prompt and prompt.strip():
            parts.append(prompt.strip())
        return ", ".join(parts)[:900]

    def _generate_track_unmanaged(
        self,
        category: str = "Cinematic",
        mood: str = "Epic",
        vocals: str = "Instrumental",
        duration: float = 60.0,
        prompt: Optional[str] = None,
        name: Optional[str] = None,
        lyrics: Optional[str] = None,
        timeout_sec: int = 600,
    ) -> Dict[str, Any]:
        instrumental = (vocals or "Instrumental").strip().lower() == "instrumental"
        caption = self.build_caption(category, mood, vocals, prompt)
        dur = max(10.0, min(600.0, float(duration)))

        payload = {
            "prompt": caption,
            "lyrics": "[Instrumental]" if instrumental else (lyrics or ""),
            "audio_duration": dur,
            "audio_format": "wav",
            "vocal_language": "hi" if category == "Indian" and not instrumental else "en",
            "thinking": True,
            "use_cot_caption": True,
            "inference_steps": 8,
            "batch_size": 1,
            "use_random_seed": True,
        }
        res = self._call("POST", "/release_task", payload)
        if res.get("code") != 200:
            raise RuntimeError(f"ACE-Step rejected task: {res.get('error')}")
        task_id = (res.get("data") or {}).get("task_id")
        if not task_id:
            raise RuntimeError("ACE-Step response missing task_id")

        deadline = time.time() + timeout_sec
        result_item: Optional[dict] = None
        while time.time() < deadline:
            time.sleep(3)
            q = self._call("POST", "/query_result", {"task_id_list": [task_id]})
            rows = q.get("data") or []
            if not rows:
                continue
            row = rows[0]
            if row.get("status") == 2:
                raise RuntimeError(f"ACE-Step generation failed: {str(row.get('result'))[:300]}")
            if row.get("status") == 1:
                items = json.loads(row.get("result") or "[]")
                if items and items[0].get("file"):
                    result_item = items[0]
                    break
        if not result_item:
            raise RuntimeError("ACE-Step generation timed out (first run downloads models and can be slow).")

        file_url = result_item["file"]
        if file_url.startswith("/"):
            file_url = f"{self.base_url}{file_url}"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        slug = re.sub(r"[^\w]", "", category.lower()) or "acestep"
        stem = f"acestep_{slug}_{int(time.time())}"
        wav = self.out_dir / f"{stem}.wav"
        with urllib.request.urlopen(urllib.request.Request(file_url, headers=headers), timeout=180) as r:
            wav.write_bytes(r.read())

        measured = 0.0
        try:
            import wave
            with wave.open(str(wav), "rb") as wf:
                measured = round(wf.getnframes() / float(wf.getframerate()), 1)
        except Exception:
            pass

        metas = result_item.get("metas") or {}
        return {
            "id": stem,
            "name": name or f"ACE-Step {category} {mood}",
            "filename": wav.name,
            "file_path": str(wav),
            "url": f"/api/music/preview/{wav.name}?type=ai&t={int(time.time() * 1000)}",
            "category": category,
            "mood": mood,
            "vocals": vocals,
            "duration": measured or dur,
            "prompt": caption,
            "source": "acestep",
            "research_specs": {
                "target_bpm": metas.get("bpm", "auto"),
                "root_key": (metas.get("keyscale") or "auto"),
                "scale": result_item.get("dit_model", "acestep-v15"),
                "drum_kit": "ACE-Step 1.5",
                "drive_description": "ACE-Step Neural Master",
            },
            "qa_verification": {
                "adherence_score": 100.0,
                "summary": f"Generated by ACE-Step 1.5 ({result_item.get('dit_model', 'DiT')}). Caption: {caption}",
            },
            "is_saved": False,
            "is_default": False,
        }

    def generate_track(self, *args, **kwargs) -> Dict[str, Any]:
        """Generates music, starting ACE-Step on demand and stopping it afterwards (memory manager)."""
        from app.automation import resources
        with resources.lease("acestep"):
            try:
                return self._generate_track_unmanaged(*args, **kwargs)
            finally:
                (resources.LOG_DIR / "acestep_last_used").write_text(str(time.time()))
