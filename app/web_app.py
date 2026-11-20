import os
import time
import shutil
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from PIL import Image, ImageEnhance
import io

import config
from app.utils.storage import StorageManager
from app.agents.pipeline import ShortsPipeline
from app.agents.youtube_publisher import YouTubePublisher
from app.agents import clip_generator

import hmac
import logging
import re
import threading
from datetime import datetime, timedelta
from fastapi import Request
from fastapi.responses import RedirectResponse, PlainTextResponse

app = FastAPI(title="AI Shorts Studio", version="1.0.0")
logger = logging.getLogger("ai_shorts_studio")

# ---------------------------------------------------------------------------
# Edit-conflict guard: a project can't be modified while it is still being
# generated (the pipeline would overwrite the edit with its stale copy), and
# only one modifying request per project runs at a time.
# ---------------------------------------------------------------------------
_PROJECT_MUTATION_PATH = re.compile(r"^/api/(?:projects|publish)/([^/]+)")
_project_locks: Dict[str, threading.Lock] = {}
_project_locks_guard = threading.Lock()
STALE_IN_PROGRESS_AFTER = timedelta(minutes=45)


def _project_lock(project_id: str) -> threading.Lock:
    with _project_locks_guard:
        return _project_locks.setdefault(project_id, threading.Lock())


def _is_stale_in_progress(project: Dict[str, Any]) -> bool:
    try:
        last = datetime.fromisoformat(project.get("updated_at") or project.get("created_at"))
        return datetime.now() - last > STALE_IN_PROGRESS_AFTER
    except Exception:
        return False


@app.middleware("http")
async def guard_project_mutations(request: Request, call_next):
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return await call_next(request)
    m = _PROJECT_MUTATION_PATH.match(request.url.path)
    if not m:
        return await call_next(request)
    project_id = m.group(1)
    project = StorageManager.get_project_by_id(project_id)
    if project and project.get("status") in ("in_progress", "queued") and not _is_stale_in_progress(project):
        return JSONResponse(
            status_code=409,
            content={"detail": "This project is still being generated. Wait until it finishes before editing it."},
        )
    lock = _project_lock(project_id)
    if not lock.acquire(blocking=False):
        return JSONResponse(
            status_code=409,
            content={"detail": "Another change to this project is still running. Try again when it finishes."},
        )
    try:
        return await call_next(request)
    finally:
        lock.release()


# Registered last so it runs FIRST (Starlette: last-added middleware is outermost)
# ---------------------------------------------------------------------------
# Access control: optional shared token (set STUDIO_API_TOKEN in .env).
# Open the dashboard once with ?token=<value>; a cookie keeps you signed in.
# API clients can send the "X-Studio-Token" header instead.
# ---------------------------------------------------------------------------
STUDIO_API_TOKEN = os.getenv("STUDIO_API_TOKEN", "").strip()
TOKEN_COOKIE = "studio_token"


@app.middleware("http")
async def require_studio_token(request: Request, call_next):
    if not STUDIO_API_TOKEN:
        return await call_next(request)
    supplied = (
        request.headers.get("x-studio-token")
        or request.cookies.get(TOKEN_COOKIE)
        or request.query_params.get("token")
        or ""
    )
    if not hmac.compare_digest(supplied, STUDIO_API_TOKEN):
        return PlainTextResponse("Unauthorized: open the studio with ?token=<STUDIO_API_TOKEN>", status_code=401)
    if request.query_params.get("token") and request.method == "GET":
        # Exchange the URL token for an HttpOnly cookie so it doesn't linger in the address bar
        clean_query = "&".join(f"{k}={v}" for k, v in request.query_params.multi_items() if k != "token")
        resp = RedirectResponse(url=request.url.path + (f"?{clean_query}" if clean_query else ""), status_code=303)
        resp.set_cookie(TOKEN_COOKIE, STUDIO_API_TOKEN, httponly=True, samesite="strict", max_age=60 * 60 * 24 * 30)
        return resp
    return await call_next(request)


def _pid_alive(pid: Any) -> bool:
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except (TypeError, ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True


def sweep_orphaned_generations(reason: str) -> List[str]:
    """
    Marks 'in_progress' projects whose generating process is gone as failed, so nothing stays
    "in progress" forever. A project still owned by a LIVE process (the scheduler running a car edit,
    or an old server process finishing a render after a restart) is left alone. Records without a
    worker_pid (older ones) are treated as interrupted.
    """
    marked = []
    try:
        from app.automation import jobs as _jobs
        live_jobs = {j["id"] for j in _jobs.all_jobs() if j["status"] in ("pending", "running")}
    except Exception:
        live_jobs = None
    for p in StorageManager.get_all_projects():
        if p.get("status") == "queued" and live_jobs is not None and p.get("queue_job_id") not in live_jobs:
            p["status"] = "failed"
            p["error"] = "Its queued job disappeared before it could run. Generate it again."
            p["progress_step"] = "Failed: queued job missing"
            StorageManager.save_project(p)
            marked.append(p.get("id"))
            continue
        if p.get("status") != "in_progress":
            continue
        pid = p.get("worker_pid")
        if pid is not None and (int(pid) == os.getpid() or _pid_alive(pid)):
            continue
        p["status"] = "failed"
        p["error"] = reason
        p["progress_step"] = f"Failed: {reason}"
        StorageManager.save_project(p)
        marked.append(p.get("id"))
        print(f"[WebAPI] Marked orphaned generation as failed: {p.get('id')} ({reason})")
    return marked


def _sweep_loop():
    while True:
        time.sleep(300)
        try:
            sweep_orphaned_generations("Interrupted: the process generating this video stopped.")
        except Exception as e:
            print(f"[WebAPI] Orphan sweep skipped: {e}")


@app.on_event("startup")
def mark_interrupted_generations():
    """Background generations don't survive a restart; don't leave them 'in progress' forever."""
    try:
        sweep_orphaned_generations("Interrupted: the server restarted while this video was generating.")
    except Exception as e:
        print(f"[WebAPI] Startup recovery skipped: {e}")
    threading.Thread(target=_sweep_loop, name="orphan-sweep", daemon=True).start()

NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0"
}

# Static assets with strict no-cache to prevent stale client UI
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")

pipeline = ShortsPipeline()

class GenerateRequest(BaseModel):
    topic: Optional[str] = None
    auto_publish: bool = False
    style: Optional[str] = "default"  # 'default', 'weaponx', or 'openmontage'
    with_voice: bool = True  # True or False
    with_music: bool = True  # True or False (Without Music)
    audio_mode: Optional[str] = "with_voice"  # 'with_voice', 'without_music', 'without_voice', 'mute'
    duration: Optional[float] = 30.0  # Duration in seconds (5.0 to 180.0)
    language: Optional[str] = "en"  # 'en' or 'hi'
    voice: Optional[str] = None  # 'hi-IN-MadhurNeural', 'hi-IN-SwaraNeural', etc.
    music_track: Optional[str] = None  # 'yt_epic_bravery', 'ai_cinematic', etc.
    music_volume: Optional[float] = 0.22
    # Default motion & image effects for every scene of the new video (see agents/scene_effects.py)
    motion: Optional[str] = None
    motion_strength: Optional[str] = None
    focus_point: Optional[Dict[str, float]] = None
    effects: Optional[Dict[str, Any]] = None
    # YouTube channel key/handle this video is for (weaponxlabs, autoflashx, ...); default = registry default
    channel: Optional[str] = None
    # Car Edit Mode (Swxft-style) optional parameters
    car_edit_title: Optional[str] = None
    car_motion_preset: Optional[str] = "swxft_dynamic"
    phonk_style: Optional[str] = "drift_phonk"
    beat_sync_mode: Optional[str] = "swxft_velocity"
    # 3. Motion clips on every scene (optional toggle: LTX-2.3 / Wan 2.2 on HF, or local Phosphene LTX-2.5)
    animate_all_scenes: Optional[bool] = False
    clip_engine: Optional[str] = "auto"

class PublishRequest(BaseModel):
    override_qa: bool = False  # 'Approve anyway' after seeing the failed quality checks
    privacy_status: Optional[str] = "private"
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list] = None
    category_id: Optional[str] = "28"
    made_for_kids: bool = False
    require_approval_before_live: bool = True
    channel: Optional[str] = None

class ApprovePublishRequest(BaseModel):
    override_qa: bool = False  # 'Approve anyway' after seeing the failed quality checks
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list] = None
    channel: Optional[str] = None

class StudioSettingsRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    hf_token: Optional[str] = None
    gemini_reference_url: Optional[str] = "https://gemini.google.com/u/1/app/dbdf5025a758bf01"
    youtube_channel_id: Optional[str] = "UC4KV67NYzLi8JlrfB9J4hGg"

class SceneClipGenerateRequest(BaseModel):
    engine: str = "ltx23_hf"
    prompt: Optional[str] = None
    duration: Optional[float] = None
    hd: Optional[bool] = False

class CaptionStyleRequest(BaseModel):
    style: Dict[str, Any]
    make_default: Optional[bool] = False

class CaptionPreviewRequest(BaseModel):
    project_id: str
    style: Dict[str, Any]
    scene: Optional[int] = 1
    sample_text: Optional[str] = None

class AddSceneRequest(BaseModel):
    position: Optional[int] = None      # scene number the new scene becomes (1 = first); None = append
    narration: str
    visual_prompt: Optional[str] = None
    on_screen_text: Optional[str] = None

class SceneTextRequest(BaseModel):
    narration: str

class SceneImageGenerateRequest(BaseModel):
    prompt: Optional[str] = None
    style: Optional[str] = "cinematic"
    engine: Optional[str] = "auto"

class RerenderRequest(BaseModel):
    with_voice: Optional[bool] = None
    with_music: Optional[bool] = None
    audio_mode: Optional[str] = None

class GenerateImagePromptRequest(BaseModel):
    prompt: Optional[str] = None
    style: Optional[str] = "weaponx"
    target_scene: Optional[int] = 1
    headline: Optional[str] = None
    engine: Optional[str] = "auto"

class EditImageOverlayRequest(BaseModel):
    scene_number: Optional[int] = 1
    heading: Optional[Dict[str, Any]] = None
    shape: Optional[Dict[str, Any]] = None
    layers: Optional[list] = None
    filters: Optional[Dict[str, Any]] = None
    rerender_video: Optional[bool] = False

class AIMusicGenerateRequest(BaseModel):
    style: Optional[str] = "epic_cinematic"
    duration: Optional[float] = 30.0
    prompt: Optional[str] = None

class ApplyMusicRequest(BaseModel):
    track_id: Optional[str] = None
    music_track: Optional[str] = None
    volume: Optional[float] = None
    music_volume: Optional[float] = 0.22
    voice_volume: Optional[float] = 1.0
    ducking: Optional[bool] = True
    remove_music: Optional[bool] = False
    tempo_factor: Optional[float] = 1.0
    bass_boost: Optional[float] = 0.0
    treble_boost: Optional[float] = 0.0
    reverb: Optional[float] = 0.0
    drums_volume: Optional[float] = 1.0
    melody_volume: Optional[float] = 1.0
    clip_start: Optional[float] = 0.0
    clip_duration: Optional[float] = None
    clip_loop: Optional[bool] = True

class TrimAudioClipRequest(BaseModel):
    track_id: str
    clip_start: Optional[float] = 0.0
    clip_duration: Optional[float] = 10.0
    clip_name: Optional[str] = None

class ConvertHindiRequest(BaseModel):
    voice: Optional[str] = "hi-IN-MadhurNeural"

class CustomMusicGenerateRequest(BaseModel):
    category: Optional[str] = "Metal"
    mood: Optional[str] = "Aggressive"
    vocals: Optional[str] = "Instrumental"
    duration: Optional[float] = 60.0
    prompt: Optional[str] = "Powerful heavy guitar riffs, thunderous drums, dark cinematic atmosphere"
    name: Optional[str] = None
    save_to_library: Optional[bool] = False
    is_default: Optional[bool] = False
    lyrics: Optional[str] = None

class DeepVerifyMusicRequest(BaseModel):
    filename: Optional[str] = None
    file_path: Optional[str] = None
    category: Optional[str] = "Metal"
    mood: Optional[str] = "Aggressive"
    vocals: Optional[str] = "Instrumental"
    duration: Optional[float] = 60.0
    prompt: Optional[str] = None

class SaveMusicToLibraryRequest(BaseModel):
    track_id: Optional[str] = None
    filename: Optional[str] = None
    name: str
    category: Optional[str] = "Custom"
    mood: Optional[str] = "Epic"
    vocals: Optional[str] = "Instrumental"
    duration: Optional[float] = 60.0
    prompt: Optional[str] = ""
    is_default: Optional[bool] = False

@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
def get_favicon():
    return Response(status_code=204)

def _ui_build_id() -> str:
    """Changes whenever the dashboard's files change, so an open tab can notice new code."""
    try:
        return str(max(int(p.stat().st_mtime) for p in STATIC_DIR.glob("*") if p.is_file()))
    except ValueError:
        return "0"


@app.get("/")
def get_dashboard():
    index_file = STATIC_DIR / "index.html"
    html = index_file.read_text(encoding="utf-8")
    build = _ui_build_id()
    # Stamp the build id into the page and bust the browser cache of its script/stylesheet
    html = html.replace("?v=20", f"?v={build}").replace("<head>", f'<head><meta name="ui-build" content="{build}">', 1)
    return Response(content=html, media_type="text/html", headers=NO_CACHE_HEADERS)


@app.get("/api/ui-build")
def get_ui_build():
    return JSONResponse(content={"build": _ui_build_id()}, headers=NO_CACHE_HEADERS)

@app.get("/api/projects")
def list_projects():
    return JSONResponse(content=StorageManager.get_all_projects(), headers=NO_CACHE_HEADERS)

@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return JSONResponse(content=project, headers=NO_CACHE_HEADERS)

@app.post("/api/qa/run-sanity")
def run_qa_sanity_endpoint():
    """Runs the QA suite in a SEPARATE process (it mocks modules and switches settings while it runs;
    doing that inside the live server once switched the AI scriptwriter off for later videos)."""
    import subprocess
    import sys
    import tempfile
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "report.json"
        try:
            subprocess.run([sys.executable, str(root / "agents" / "qa_tester_agent.py"), "--json", str(out)],
                           cwd=str(root), capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="QA suite took longer than 15 minutes")
        if not out.exists():
            raise HTTPException(status_code=500, detail="QA suite crashed before producing a report")
        report = json.loads(out.read_text(encoding="utf-8"))
    return JSONResponse(content=report, headers=NO_CACHE_HEADERS)

@app.get("/api/qa/status")
def get_qa_status_endpoint():
    """Returns the LAST QA report (a GET used to re-run the whole ~45 s suite every time).
    Run a new one with POST /api/qa/run-sanity."""
    from agents.qa_tester_agent import last_report
    report = last_report()
    if report is None:
        return JSONResponse(content={"overall_status": "NOT_RUN", "message": "No QA run yet. POST /api/qa/run-sanity to run one."},
                            headers=NO_CACHE_HEADERS)
    return JSONResponse(content=report, headers=NO_CACHE_HEADERS)

@app.get("/api/qa/{project_id}")
def get_qa_report(project_id: str):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    qa_report = project.get("qa_report")
    if not qa_report or qa_report.get("agent") != "Verify-video":
        # Run Verify-video on demand
        from agents.verify_video import VerifyVideoAgent
        agent = VerifyVideoAgent()
        qa_report = agent.run(project_record=project)
        project["qa_report"] = qa_report
        project["verify_video_report"] = qa_report
        StorageManager.save_project(project)

    return JSONResponse(content=qa_report, headers=NO_CACHE_HEADERS)

@app.get("/api/qa_frame/{project_id}/{filename}")
def get_qa_frame(project_id: str, filename: str):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    p_dir = Path(project.get("project_dir", ""))
    frame_path = p_dir / "qa_frames" / filename
    if not frame_path.exists():
        frame_path = p_dir / filename
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail="Frame not found")

    return FileResponse(str(frame_path), media_type="image/png", headers=NO_CACHE_HEADERS)

@app.post("/api/generate")
def trigger_generation(req: GenerateRequest, background_tasks: BackgroundTasks):
    # Determine audio flags from audio_mode or explicit booleans
    audio_mode = req.audio_mode or ("with_voice" if req.with_voice else "without_voice")
    if audio_mode == "without_music":
        with_voice = True
        with_music = False
    elif audio_mode == "without_voice":
        with_voice = False
        with_music = True
    elif audio_mode == "mute":
        with_voice = False
        with_music = False
    else: # with_voice / voice_and_music
        with_voice = True
        with_music = getattr(req, "with_music", True)

    # Validate and clamp duration between 5.0 and 180.0 seconds
    raw_dur = req.duration if req.duration is not None else 30.0
    duration = max(5.0, min(180.0, float(raw_dur)))

    # One generation per subject+style at a time: a second click (or a second tab) for the same video
    # would build an identical copy and halve the speed of both (they share the free image services).
    with _generate_guard:
        running = _running_generation_for(req.topic, req.style)
        if running:
            return {
                "status": "already_running",
                "project_id": running["id"],
                "topic": running.get("topic"),
                "message": f"'{running.get('topic')}' is already being generated (started {str(running.get('created_at', ''))[11:16]}). Showing that one instead of starting a duplicate.",
            }
        return _start_generation(req, audio_mode, with_voice, with_music, duration, background_tasks)


_generate_guard = threading.Lock()

def _norm_topic(topic: Optional[str]) -> str:
    from agents.subject_match import subject_core
    return re.sub(r"[^a-z0-9]+", "", subject_core(topic or "").lower())

def _running_generation_for(topic: Optional[str], style: Optional[str]) -> Optional[Dict[str, Any]]:
    key = _norm_topic(topic)
    if not key:
        return None  # "surprise me" (no topic) runs pick their own topic
    style_key = (style or "default").lower()
    for p in StorageManager.get_all_projects():
        if p.get("status") not in ("in_progress", "queued") or _is_stale_in_progress(p):
            continue
        if _norm_topic(p.get("topic")) == key and (p.get("style") or "default").lower() in (style_key, "weaponx" if style_key == "weaponx" else style_key):
            return p
    return None


def _start_generation(req, audio_mode, with_voice, with_music, duration, background_tasks):
    # Validate the video-wide motion & effects BEFORE creating the project, so a bad value
    # returns 400 without leaving an orphaned 'in_progress' record that never runs.
    from agents import scene_effects as _sfx
    try:
        _defaults = _sfx.validate({"motion": req.motion, "motion_strength": req.motion_strength,
                                   "focus_point": req.focus_point, "effects": req.effects})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        project_record, topic_info = pipeline.prepare_project(
            custom_topic=req.topic,
            style=req.style,
            with_voice=with_voice,
            with_music=with_music,
            duration=duration,
            audio_mode=audio_mode,
            language=req.language or "en",
            voice=req.voice,
            music_track=req.music_track,
            music_volume=req.music_volume,
            channel=req.channel,
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Unknown YouTube channel: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare project: {e}")

    # Video-wide default motion & effects chosen at creation time (validated above)
    if _defaults:
        project_record["scene_defaults"] = _defaults
        StorageManager.save_project(project_record)

    if getattr(req, "car_edit_title", None) or (req.style or "").lower() == "car_edit":
        project_record["car_edit_title"] = getattr(req, "car_edit_title", None)
        project_record["car_motion_preset"] = getattr(req, "car_motion_preset", "swxft_dynamic") or "swxft_dynamic"
        project_record["phonk_style"] = getattr(req, "phonk_style", "drift_phonk") or "drift_phonk"
        project_record["beat_sync_mode"] = getattr(req, "beat_sync_mode", "swxft_velocity") or "swxft_velocity"
        StorageManager.save_project(project_record)

    if getattr(req, "animate_all_scenes", False):
        project_record["animate_all_scenes"] = True
        project_record["clip_engine"] = getattr(req, "clip_engine", "auto") or "auto"
        StorageManager.save_project(project_record)

    # One job queue for the whole machine: when the scheduler's worker is alive, the video is queued and
    # rendered there one at a time (dashboard + scheduled videos used to compete for the same 18 GB).
    # If the worker isn't running (or runs older code), render here as before.
    from app.automation import jobs as _jobs
    run_kwargs = dict(auto_publish=req.auto_publish, style=req.style, with_voice=with_voice, with_music=with_music,
                      duration=duration, audio_mode=audio_mode, language=req.language or "en", voice=req.voice,
                      music_track=req.music_track, music_volume=req.music_volume)
    if _jobs.worker_alive("studio_generate"):
        job = _jobs.enqueue("studio_generate", {"project_id": project_record["id"], "run_kwargs": run_kwargs},
                            dedupe_key=f"studio-{project_record['id']}", max_attempts=1)
        pos = _jobs.queue_position(job["id"]) or 1
        project_record.update(status="queued", queue_job_id=job["id"],
                              progress_step="Queued: starting now" if pos <= 1 else f"Queued: {pos - 1} video(s) ahead")
        StorageManager.save_project(project_record)
        return {
            "status": "queued",
            "project_id": project_record["id"],
            "topic": project_record["topic"],
            "duration": duration,
            "audio_mode": audio_mode,
            "queue_position": pos,
            "message": f"'{project_record['topic']}' queued" + ("" if pos <= 1 else f" ({pos - 1} video(s) ahead)") +
                       " - videos render one at a time.",
        }

    def run_job(prepared_project, prepared_topic_info, auto_publish, style, with_voice, with_music, duration, audio_mode, language, voice, music_track, music_volume):
        try:
            pipeline.run(
                auto_publish=auto_publish,
                style=style,
                with_voice=with_voice,
                with_music=with_music,
                duration=duration,
                audio_mode=audio_mode,
                language=language,
                voice=voice,
                music_track=music_track,
                music_volume=music_volume,
                prepared_project=prepared_project,
                prepared_topic_info=prepared_topic_info
            )
        except Exception as e:
            print(f"[WebAPI] Pipeline execution error: {e}")

    background_tasks.add_task(
        run_job,
        project_record,
        topic_info,
        req.auto_publish,
        req.style,
        with_voice,
        with_music,
        duration,
        audio_mode,
        req.language or "en",
        req.voice,
        req.music_track,
        req.music_volume
    )

    if with_voice and with_music:
        mode_label = "voiceover + music"
    elif with_voice and not with_music:
        mode_label = "voiceover only (without music)"
    elif not with_voice and with_music:
        mode_label = "music only (without voice)"
    else:
        mode_label = "mute (no audio)"

    return {
        "status": "started",
        "project_id": project_record["id"],
        "topic": project_record["topic"],
        "duration": duration,
        "audio_mode": audio_mode,
        "message": f"Shorts generation started for '{project_record['topic']}' ({req.style} style · {duration:.0f}s · {mode_label})"
    }

@app.post("/api/projects/{project_id}/scenes/{scene_idx}/image")
def upload_scene_image(project_id: str, scene_idx: int, file: UploadFile = File(...)):
    # Plain def: the decode/resize/CLIP work runs in the threadpool instead of blocking the event loop
    """
    Manually upload/replace an image for a specific scene.
    Automatically formats into full-bleed 1080x1920 9:16 vertical.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content = file.file.read()
    if not content or len(content) < 1000:
        raise HTTPException(status_code=400, detail="Invalid image file")

    n_scenes = len(project.get("scenes") or [])
    if n_scenes and not 1 <= scene_idx <= n_scenes:
        raise HTTPException(status_code=404, detail=f"Scene {scene_idx} not found (project has {n_scenes} scenes)")

    try:
        raw_img = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Not a readable image file (use PNG, JPG or WEBP)")

    try:
        target_w, target_h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT

        # Full-Bleed 9:16 Cover scaling
        scale = max(target_w / raw_img.width, target_h / raw_img.height)
        scaled_w = int(raw_img.width * scale)
        scaled_h = int(raw_img.height * scale)
        scaled = raw_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        crop_x = (scaled_w - target_w) // 2
        crop_y = (scaled_h - target_h) // 2
        canvas = scaled.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))
        canvas = ImageEnhance.Contrast(canvas).enhance(1.12)

        project_dir = Path(project["project_dir"])
        scenes_dir = project_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        img_path = scenes_dir / f"scene_{scene_idx:02d}.png"
        canvas.save(img_path, "PNG")

        # Also update base image and clear stale overlays so re-rendering immediately reflects the new image
        base_path = scenes_dir / f"scene_{scene_idx:02d}_base.png"
        try:
            canvas.save(base_path, "PNG")
        except Exception:
            pass

        for stale_suffix in ["_overlay.png", "_bg.png"]:
            stale_f = scenes_dir / f"scene_{scene_idx:02d}{stale_suffix}"
            if stale_f.exists():
                try:
                    stale_f.unlink()
                except Exception:
                    pass

        # Update project record
        scenes = project.get("scenes", [])
        idx = scene_idx - 1
        if 0 <= idx < len(scenes):
            scenes[idx]["image_path"] = str(img_path)
            scenes[idx]["visual_source"] = "manual_upload"
            scenes[idx]["visual_source_url"] = None
            _sync_visual_record(project, scene_idx, {
                "image_path": str(img_path), "source": "manual_upload", "source_url": None, "source_domain": "local",
                "source_provider": "User upload", "license": "Provided by the user", "author": "User",
                "source_verified": True, "topic_matched": True, "topic_match_score": None, "content_verified": None,
                "topic_match_reason": "Uploaded by the user", "prompt": None,
            })

        image_paths = project.get("image_paths", [])
        if 0 <= idx < len(image_paths):
            image_paths[idx] = str(img_path)
        else:
            image_paths.append(str(img_path))
        project["image_paths"] = image_paths

        # Reset any scene layers for this scene since a new image was uploaded
        if "scene_layers" in project and isinstance(project["scene_layers"], dict):
            project["scene_layers"].pop(str(scene_idx), None)

        # Your uploads are trusted (never blocked), but warn when the picture doesn't look like the
        # subject's kind of thing (e.g. an artillery photo in an F-35 video)
        warning = None
        try:
            from agents.image_generator import ImageGeneratorAgent
            chk = ImageGeneratorAgent()._verify_image_content(img_path, project.get("topic", ""), lenient=False)
            if chk.get("passed") is False:
                warning = (f"This picture may not show {project.get('topic')}: it looks more like "
                           f"'{chk.get('top_decoy') or chk.get('best_label')}'. Kept it as you asked.")
                if 0 <= idx < len(scenes):
                    scenes[idx]["upload_warning"] = warning
            elif 0 <= idx < len(scenes):
                scenes[idx].pop("upload_warning", None)
        except Exception as e:
            print(f"[WebAPI] Upload content check skipped: {e}")

        StorageManager.save_project(project)
        out = {"status": "success", "image_url": f"/api/scene_image/{project_id}/{scene_idx}"}
        if warning:
            out["warning"] = warning
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image processing error: {e}")

# Background clip-generation jobs (in memory; a server restart drops running jobs)
_clip_jobs: Dict[str, Dict[str, Any]] = {}
_clip_jobs_guard = threading.Lock()

ALLOWED_CLIP_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}

def _scene_clip_files(scenes_dir: Path, scene_idx: int):
    return [p for p in scenes_dir.glob(f"scene_{scene_idx:02d}_clip.*") if p.suffix.lower() in ALLOWED_CLIP_EXTS]

@app.post("/api/projects/{project_id}/scenes/{scene_idx}/clip")
async def upload_scene_clip(project_id: str, scene_idx: int, file: UploadFile = File(...)):
    """
    Attach a video clip to a scene. On re-render the clip replaces the scene's still image:
    it is scaled/cropped to 9:16, looped or trimmed to the scene duration, and its audio is dropped.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    scenes = project.get("scenes", [])
    idx = scene_idx - 1
    if not (0 <= idx < len(scenes)):
        raise HTTPException(status_code=400, detail=f"Scene {scene_idx} does not exist")

    ext = Path(file.filename or "").suffix.lower() or ".mp4"
    if ext not in ALLOWED_CLIP_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported clip type '{ext}'. Use MP4, MOV, M4V, WEBM or MKV.")

    scenes_dir = Path(project["project_dir"]) / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    for old in _scene_clip_files(scenes_dir, scene_idx):
        old.unlink(missing_ok=True)

    clip_path = scenes_dir / f"scene_{scene_idx:02d}_clip{ext}"
    with open(clip_path, "wb") as out:
        shutil.copyfileobj(file.file, out)
    if clip_path.stat().st_size < 1000:
        clip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Invalid or empty video file")

    scenes[idx]["clip_path"] = str(clip_path)
    scenes[idx]["clip_name"] = file.filename
    scenes[idx].pop("clip_meta", None)
    StorageManager.save_project(project)
    return {"status": "success", "clip_url": f"/api/scene_clip/{project_id}/{scene_idx}"}

def _scene_duration(project: Dict[str, Any], scene: Dict[str, Any]) -> float:
    d = scene.get("duration_seconds") or scene.get("duration")
    if d:
        return float(d)
    n = max(1, len(project.get("scenes") or []))
    return float(project.get("duration") or project.get("target_duration") or 5.0 * n) / n

@app.get("/api/clip-engines")
def list_clip_engines():
    status = clip_generator.engine_status()
    return JSONResponse(content={
        "hf_token_configured": status["hf_token"],
        "phosphene_running": bool(status["phosphene_url"]),
        "engines": [
            {"id": k, "label": v["label"], "where": v["where"], "max_seconds": v["max_seconds"], "typical": v["typical"]}
            for k, v in clip_generator.ENGINES.items()
        ],
    }, headers=NO_CACHE_HEADERS)

def _active_clip_job(project_id: str, scene_idx: int) -> Optional[Dict[str, Any]]:
    for job in _clip_jobs.values():
        if job["project_id"] == project_id and job["scene_idx"] == scene_idx and job["status"] == "running":
            return job
    return None

@app.post("/api/projects/{project_id}/scenes/{scene_idx}/generate-clip")
def generate_scene_clip_endpoint(project_id: str, scene_idx: int, req: SceneClipGenerateRequest):
    """
    Starts a free image-to-video job (Wan 2.2 / LTX-2.3 on Hugging Face, or LTX-2.5 via local
    Phosphene) for the scene's current image. Returns a job id; poll /api/clip-jobs/{job_id}.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = project.get("scenes", [])
    idx = scene_idx - 1
    if not (0 <= idx < len(scenes)):
        raise HTTPException(status_code=400, detail=f"Scene {scene_idx} does not exist")
    if req.engine not in clip_generator.ENGINES:
        raise HTTPException(status_code=400, detail=f"Unknown engine '{req.engine}'")

    scene = scenes[idx]
    scenes_dir = Path(project["project_dir"]) / "scenes"
    image_path = None
    for cand in (scene.get("image_path"), scenes_dir / f"scene_{scene_idx:02d}.png", scenes_dir / "hero_master.png"):
        if cand and Path(cand).exists():
            image_path = Path(cand)
            break
    if not image_path:
        raise HTTPException(status_code=400, detail="This scene has no image to animate. Add or generate an image first.")

    prompt = (req.prompt or "").strip() or (
        f"{scene.get('visual_prompt') or scene.get('narration') or project.get('topic', '')}. "
        "Smooth cinematic camera motion, realistic physics, subject stays consistent with the source image."
    )
    duration = float(req.duration) if req.duration else _scene_duration(project, scene)

    with _clip_jobs_guard:
        existing = _active_clip_job(project_id, scene_idx)
        if existing:
            return {"status": "running", "job_id": existing["id"], "message": "A clip is already being generated for this scene."}
        job_id = f"clip_{int(time.time() * 1000)}_{scene_idx}"
        job = {
            "id": job_id, "project_id": project_id, "scene_idx": scene_idx, "engine": req.engine,
            "engine_label": clip_generator.ENGINES[req.engine]["label"], "status": "running",
            "message": "Starting...", "progress": None, "started_at": time.time(), "result": None, "error": None,
        }
        _clip_jobs[job_id] = job

    def on_status(msg: str, pct: Optional[float] = None):
        job["message"] = msg
        job["progress"] = pct

    def worker():
        out_path = scenes_dir / f"scene_{scene_idx:02d}_clip_{req.engine}.mp4"
        try:
            meta = clip_generator.generate_scene_clip(
                req.engine, image_path, prompt, duration, out_path, on_status=on_status, hd=bool(req.hd)
            )
            on_status("Saving clip to the scene...", 100)
            # Commit under the project lock (same lock the edit-guard middleware uses)
            lock = _project_lock(project_id)
            if not lock.acquire(timeout=300):
                raise RuntimeError(f"Project stayed busy; the clip was kept as {out_path.name}")
            try:
                proj = StorageManager.get_project_by_id(project_id)
                if not proj or not (0 <= idx < len(proj.get("scenes", []))):
                    raise RuntimeError("Project or scene was removed while the clip was generating")
                final_path = scenes_dir / f"scene_{scene_idx:02d}_clip.mp4"
                for old in _scene_clip_files(scenes_dir, scene_idx):
                    old.unlink(missing_ok=True)
                out_path.replace(final_path)
                sc = proj["scenes"][idx]
                sc["clip_path"] = str(final_path)
                sc["clip_name"] = f"{meta['engine_label']} clip"
                sc["clip_meta"] = meta
                StorageManager.save_project(proj)
            finally:
                lock.release()
            job["result"] = {"clip_url": f"/api/scene_clip/{project_id}/{scene_idx}", "clip_name": sc["clip_name"], "meta": meta}
            job["message"] = f"Scene {scene_idx} clip generated with {meta['engine_label']} in {meta['elapsed_seconds']:.0f}s (free)"
            job["status"] = "done"
        except clip_generator.ClipGenerationError as e:
            job["error"] = str(e)
            job["status"] = "failed"
        except Exception as e:
            job["error"] = f"Clip generation error: {e}"
            job["status"] = "failed"
        finally:
            if job["status"] != "done" and out_path.exists() and "kept as" not in (job["error"] or ""):
                out_path.unlink(missing_ok=True)
            job["finished_at"] = time.time()

    threading.Thread(target=worker, name=f"clipgen-{job_id}", daemon=True).start()
    return {"status": "running", "job_id": job_id, "message": job["message"]}

@app.get("/api/clip-jobs/{job_id}")
def get_clip_job(job_id: str):
    job = _clip_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Clip job not found (the server may have restarted)")
    return JSONResponse(content={
        "id": job["id"], "status": job["status"], "message": job["message"], "progress": job["progress"],
        "engine_label": job["engine_label"], "scene_idx": job["scene_idx"], "project_id": job["project_id"],
        "elapsed": round((job.get("finished_at") or time.time()) - job["started_at"], 1),
        "result": job["result"], "error": job["error"],
    }, headers=NO_CACHE_HEADERS)

@app.get("/api/projects/{project_id}/clip-jobs")
def list_project_clip_jobs(project_id: str):
    """Running jobs for a project, so a reopened modal can resume showing progress."""
    return {"jobs": [
        {"id": j["id"], "scene_idx": j["scene_idx"], "engine_label": j["engine_label"], "message": j["message"]}
        for j in _clip_jobs.values() if j["project_id"] == project_id and j["status"] == "running"
    ]}

# ---------------------------------------------------------------------------
# Caption (subtitle) design: presets, fonts, per-project style, live preview
# ---------------------------------------------------------------------------
from app.agents import caption_style as caption_style_mod

def _studio_settings() -> Dict[str, Any]:
    try:
        import json as _json
        return _json.loads(config.STUDIO_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

@app.get("/api/caption-styles")
def get_caption_styles(project_id: Optional[str] = None):
    default = _studio_settings().get("caption_style_default")
    current = None
    if project_id:
        project = StorageManager.get_project_by_id(project_id)
        if project and project.get("caption_style"):
            current = caption_style_mod.normalize_style(project["caption_style"])
    return JSONResponse(content={
        "fonts": caption_style_mod.FONTS,
        "presets": [{"id": k, "label": v["label"], "style": caption_style_mod.preset_style(k)} for k, v in caption_style_mod.PRESETS.items()],
        "studio_default": caption_style_mod.normalize_style(default) if isinstance(default, dict) else None,
        "project_style": current,
        "builtin_default": caption_style_mod.preset_style("classic"),
    }, headers=NO_CACHE_HEADERS)

@app.post("/api/projects/{project_id}/caption-style")
def save_caption_style(project_id: str, req: CaptionStyleRequest):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    style = caption_style_mod.normalize_style(req.style)
    project["caption_style"] = style
    project["updated_at"] = datetime.now().isoformat()
    StorageManager.save_project(project)
    if req.make_default:
        import json as _json
        saved = _studio_settings()
        saved["caption_style_default"] = style
        config.STUDIO_SETTINGS_FILE.write_text(_json.dumps(saved, indent=2), encoding="utf-8")
    msg = "Caption style saved" + (" and set as the default for new videos" if req.make_default else "") + ". Click Re-render to apply."
    return {"status": "success", "style": style, "message": msg}

@app.delete("/api/projects/{project_id}/caption-style")
def reset_caption_style(project_id: str):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.pop("caption_style", None)
    StorageManager.save_project(project)
    return {"status": "success", "message": "Captions reset to the built-in style. Click Re-render to apply."}

@app.post("/api/caption-preview")
def caption_preview(req: CaptionPreviewRequest):
    """
    Renders one frame of the scene with the given caption style, using the same ASS generator
    and ffmpeg/libass as the final video. Read-only, so it sits outside the project edit lock.
    """
    import tempfile
    import subprocess
    from app.agents.voice_agent import VoiceAgent
    from app.agents.video_composer import VideoComposer

    project = StorageManager.get_project_by_id(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = project.get("scenes") or []
    idx = max(1, min(int(req.scene or 1), max(1, len(scenes))))
    scene = scenes[idx - 1] if scenes else {}
    scenes_dir = Path(project.get("project_dir", "")) / "scenes"
    image = None
    for cand in (scene.get("image_path"), scenes_dir / f"scene_{idx:02d}.png", scenes_dir / "hero_master.png"):
        if cand and Path(cand).exists():
            image = Path(cand)
            break

    style = caption_style_mod.normalize_style(req.style)
    is_hindi = project.get("language") == "hi"
    text = (req.sample_text or "").strip()
    if not text:
        if is_hindi:
            hs = (project.get("content_analysis_hindi") or {}).get("scenes") or []
            text = (hs[idx - 1].get("narration_hindi") if idx - 1 < len(hs) else "") or ""
        text = text or scene.get("narration") or project.get("title") or "Your caption text appears here"
    words = caption_style_mod.sample_words(text)[: max(style["words_per_caption"] * 2, 4)]
    placement = VoiceAgent._detect_image_focal_area(str(image)) if image else "bottom"
    ass_text = caption_style_mod.render_ass(words, style, lambda t: placement)
    # Show the frame where the 2nd word is active (or the 1st when captions are one word long)
    t = words[min(1, len(words) - 1)]["start"] + 0.2 if words else 0.2

    ffmpeg = VideoComposer().ffmpeg_exe
    w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    with tempfile.TemporaryDirectory(prefix="capprev_") as tmp:
        ass_file = Path(tmp) / "p.ass"
        ass_file.write_text(ass_text, encoding="utf-8")
        out = Path(tmp) / "p.jpg"
        src = ["-loop", "1", "-framerate", "30", "-t", f"{t + 0.5:.2f}", "-i", str(image)] if image else \
              ["-f", "lavfi", "-t", f"{t + 0.5:.2f}", "-i", f"color=c=0x1e293b:s={w}x{h}:r=30"]
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
              f"ass='{str(ass_file)}',scale=540:960")
        cmd = [ffmpeg, "-y", "-v", "error", *src, "-vf", vf, "-ss", f"{t:.2f}", "-frames:v", "1", "-q:v", "3", str(out)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0 or not out.exists():
            raise HTTPException(status_code=500, detail=f"Preview render failed: {(res.stderr or '')[-300:]}")
        data = out.read_bytes()
    return Response(content=data, media_type="image/jpeg", headers=NO_CACHE_HEADERS)

# ---------------------------------------------------------------------------
# Add / remove scenes. Scene assets are named by position (scene_NN.png, _base, _bg,
# _overlay, _clip.*), so inserting or removing a scene renumbers every later scene's files.
# ---------------------------------------------------------------------------
WORDS_PER_SECOND = 2.6

def _scene_asset_files(scenes_dir: Path, n: int):
    return [p for p in list(scenes_dir.glob(f"scene_{n:02d}.*")) + list(scenes_dir.glob(f"scene_{n:02d}_*")) if p.is_file()]

def _renumber_scene_assets(project: Dict[str, Any], scenes_dir: Path, old_to_new: Dict[int, int]):
    """
    Moves each scene's files from its old number to its new one and rewrites every path/key that
    refers to them. `old_to_new` covers the scenes that survive; a scene missing from it must
    already have had its files deleted.
    """
    moves = {n: m for n, m in old_to_new.items() if n != m}
    stamp = f"renum{int(time.time() * 1000)}"
    staged = []  # two phases via temp names, so 2->3 can't clobber 3 before 3->4 runs
    for old, new in moves.items():
        for f in _scene_asset_files(scenes_dir, old):
            tmp = f.with_name(f"{stamp}_{new:02d}{f.name[len(f'scene_{old:02d}'):]}")
            f.rename(tmp)
            staged.append((tmp, f, new, old))
    path_map: Dict[str, str] = {}
    for tmp, orig, new, old in staged:
        final = orig.with_name(f"scene_{new:02d}{orig.name[len(f'scene_{old:02d}'):]}")
        tmp.rename(final)
        path_map[str(orig)] = str(final)

    for s in project.get("scenes", []):
        for key in ("image_path", "clip_path"):
            if s.get(key) in path_map:
                s[key] = path_map[s[key]]
    layers = project.get("scene_layers")
    if isinstance(layers, dict):
        project["scene_layers"] = {
            str(old_to_new[int(k)]): v for k, v in layers.items()
            if k.isdigit() and int(k) in old_to_new
        }

def _resync_scene_numbers(project: Dict[str, Any], scenes_dir: Path):
    for i, s in enumerate(project.get("scenes", []), 1):
        s["scene_number"] = i
        s["scene_id"] = i
    paths = []
    for i, s in enumerate(project.get("scenes", []), 1):
        p = s.get("image_path")
        if not p or not Path(p).exists():
            cand = scenes_dir / f"scene_{i:02d}.png"
            if cand.exists():
                s["image_path"] = p = str(cand)
        if p:
            paths.append(p)
    project["image_paths"] = paths

def _refuse_while_clip_jobs(project_id: str):
    # A running clip job commits to a scene NUMBER; renumbering underneath it would misfile the clip.
    with _clip_jobs_guard:
        if any(j["project_id"] == project_id and j["status"] == "running" for j in _clip_jobs.values()):
            raise HTTPException(status_code=409, detail="A video clip is still generating for this project. Wait for it to finish before adding or removing scenes.")

@app.post("/api/projects/{project_id}/scenes")
def add_scene(project_id: str, req: AddSceneRequest):
    """
    Inserts a new scene. It starts with a copy of its neighbour's image (so re-rendering always
    works) flagged as a placeholder; replace it with Add Image / Regenerate AI / Add Clip.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    narration = (req.narration or "").strip()
    if not narration:
        raise HTTPException(status_code=400, detail="Write the narration for the new scene first.")
    _refuse_while_clip_jobs(project_id)

    scenes = project.setdefault("scenes", [])
    if len(scenes) >= 99:
        raise HTTPException(status_code=400, detail="A project can have at most 99 scenes.")
    n = len(scenes)
    pos = n + 1 if req.position is None else max(1, min(int(req.position), n + 1))
    scenes_dir = Path(project["project_dir"]) / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    # Shift scenes pos..n up by one (files first, highest number first is handled by staging)
    _renumber_scene_assets(project, scenes_dir, {i: (i if i < pos else i + 1) for i in range(1, n + 1)})

    # Placeholder image: the previous scene's picture (or the next one's when inserting at the start)
    neighbour_num = pos - 1 if pos > 1 else (2 if n >= 1 else None)
    new_img = scenes_dir / f"scene_{pos:02d}.png"
    src = None
    if neighbour_num:
        for cand in (scenes_dir / f"scene_{neighbour_num:02d}_base.png", scenes_dir / f"scene_{neighbour_num:02d}.png"):
            if cand.exists():
                src = cand
                break
    if src:
        shutil.copyfile(src, new_img)
    else:
        Image.new("RGB", (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), (12, 16, 28)).save(new_img, "PNG")

    words = len(narration.split())
    est = round(max(2.5, words / WORDS_PER_SECOND), 2)
    template = scenes[pos - 2] if pos > 1 and scenes else (scenes[0] if scenes else {})
    new_scene = {
        "scene_number": pos,
        "scene_id": pos,
        "duration_seconds": est,
        "narration": narration,
        "voiceover_text": narration,
        "visual_prompt": (req.visual_prompt or "").strip() or narration,
        "key_subject": template.get("key_subject") or project.get("topic", ""),
        "on_screen_text": (req.on_screen_text or "").strip(),
        "background_music": template.get("background_music"),
        "visual_source": "placeholder_copy",
        "visual_source_url": None,
        # Files were renumbered first, so neighbour_num is already the neighbour's new scene number
        "placeholder_from_scene": neighbour_num if src else None,
        "image_path": str(new_img),
        "user_added": True,
    }
    scenes.insert(pos - 1, new_scene)
    _resync_scene_numbers(project, scenes_dir)

    # Try a NEW verified photo of the subject (a copy of the neighbour is a guaranteed repeat that
    # Verify-video flags). Web photos only, so this stays quick; the copy remains if nothing new fits.
    fresh = None
    if not project.get("is_weaponx_lab") and project.get("style") not in ("weaponx", "car_edit", "music_only"):
        try:
            from agents.image_generator import ImageGeneratorAgent
            used = {str(r.get("source_url")) for r in (project.get("visual_records") or []) if r.get("source_url")}
            others = [str(p) for i, p in enumerate(project.get("image_paths") or [], 1) if i != pos and p]
            fresh = ImageGeneratorAgent().acquire_fresh_web_image(
                project.get("topic", ""), new_scene, pos, new_img, used_urls=used, existing_images=others)
        except Exception as e:
            print(f"[WebAPI] Fresh image for new scene {pos} failed: {e}")
            fresh = None
    if fresh:
        Path(new_img).with_name(f"scene_{pos:02d}_base.png").unlink(missing_ok=True)
        new_scene.update(visual_source="web_free", visual_source_url=fresh.get("source_url"),
                         placeholder_from_scene=None, image_path=str(new_img))
        _sync_visual_record(project, pos, {k: v for k, v in fresh.items() if k != "visual_quality"})

    # Grow the target length so the existing scenes aren't squeezed to make room
    if project.get("target_duration"):
        project["target_duration"] = round(float(project["target_duration"]) + est, 2)
    project["updated_at"] = datetime.now().isoformat()
    StorageManager.save_project(project)
    return {
        "status": "success",
        "scene_number": pos,
        "fresh_image": bool(fresh),
        "message": (f"Scene {pos} added (~{est:.1f}s) with a new verified photo. Re-render to apply." if fresh else
                    f"Scene {pos} added (~{est:.1f}s). No new photo was found, so it uses a copy of a neighbouring image; replace it, then Re-render."),
        "project": project,
    }

@app.delete("/api/projects/{project_id}/scenes/{scene_idx}")
def remove_scene(project_id: str, scene_idx: int):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = project.get("scenes", [])
    n = len(scenes)
    if not (1 <= scene_idx <= n):
        raise HTTPException(status_code=400, detail=f"Scene {scene_idx} does not exist")
    if n <= 1:
        raise HTTPException(status_code=400, detail="A video needs at least one scene.")
    _refuse_while_clip_jobs(project_id)

    scenes_dir = Path(project["project_dir"]) / "scenes"
    for f in _scene_asset_files(scenes_dir, scene_idx):
        f.unlink(missing_ok=True)
    removed = scenes.pop(scene_idx - 1)
    _renumber_scene_assets(project, scenes_dir, {i: (i if i < scene_idx else i - 1) for i in range(1, n + 1) if i != scene_idx})
    _resync_scene_numbers(project, scenes_dir)

    if project.get("target_duration"):
        project["target_duration"] = round(max(5.0, float(project["target_duration"]) - float(removed.get("duration_seconds") or 0)), 2)
    project["updated_at"] = datetime.now().isoformat()
    StorageManager.save_project(project)
    return {"status": "success", "message": f"Scene {scene_idx} removed. Click Re-render to apply.", "project": project}

@app.delete("/api/projects/{project_id}/scenes/{scene_idx}/clip")
def delete_scene_clip(project_id: str, scene_idx: int):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = project.get("scenes", [])
    idx = scene_idx - 1
    if not (0 <= idx < len(scenes)):
        raise HTTPException(status_code=400, detail=f"Scene {scene_idx} does not exist")
    for old in _scene_clip_files(Path(project["project_dir"]) / "scenes", scene_idx):
        old.unlink(missing_ok=True)
    scenes[idx].pop("clip_path", None)
    scenes[idx].pop("clip_name", None)
    scenes[idx].pop("clip_meta", None)
    StorageManager.save_project(project)
    return {"status": "success"}

@app.get("/api/scene_clip/{project_id}/{scene_idx}")
def get_scene_clip(project_id: str, scene_idx: int):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = project.get("scenes", [])
    idx = scene_idx - 1
    p = scenes[idx].get("clip_path") if 0 <= idx < len(scenes) else None
    if not p or not Path(p).exists():
        raise HTTPException(status_code=404, detail="Scene clip not found")
    return FileResponse(p, headers=NO_CACHE_HEADERS)

def _sync_visual_record(project: Dict[str, Any], scene_idx: int, fields: Dict[str, Any]) -> None:
    """Keep the per-scene image record (read by QA / publish gate) in step with the scene after an
    upload or regenerate, instead of leaving the old image's provenance behind."""
    for records in ((project.get("image_report") or {}).get("visual_records"), project.get("visual_records")):
        if not isinstance(records, list):
            continue
        rec = next((r for r in records if r.get("scene_number") == scene_idx), None)
        if rec is None:
            rec = {"scene_number": scene_idx}
            records.append(rec)
        for k in ("visual_quality", "content_check", "source_title", "page_url"):
            rec.pop(k, None)
        rec.update(fields)

@app.post("/api/projects/{project_id}/scenes/{scene_idx}/text")
def update_scene_text(project_id: str, scene_idx: int, req: SceneTextRequest):
    """
    Manually update the narration text for a specific scene.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    scenes = project.get("scenes", [])
    idx = scene_idx - 1
    if not (0 <= idx < len(scenes)):
        raise HTTPException(status_code=400, detail=f"Scene {scene_idx} does not exist")

    scenes[idx]["narration"] = req.narration.strip()
    StorageManager.save_project(project)
    return {"status": "success", "narration": req.narration.strip()}

@app.post("/api/projects/{project_id}/scenes/{scene_idx}/generate-image")
def generate_scene_image_endpoint(project_id: str, scene_idx: int, req: SceneImageGenerateRequest):
    """
    Generates or regenerates an AI image for a specific scene using a custom prompt or scene narration.
    Formats image to full-bleed 1080x1920 9:16 vertical and updates scene records.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from agents.image_generator import ImageGeneratorAgent

    scenes = project.get("scenes", [])
    idx = scene_idx - 1
    target_scene = scenes[idx] if (0 <= idx < len(scenes)) else {}

    # Extract or build prompt
    prompt = (req.prompt or "").strip()
    if not prompt:
        prompt = target_scene.get("visual_prompt") or target_scene.get("narration") or f"Cinematic 8k shot of {project.get('topic', 'Military Technology')}"

    project_dir = Path(project["project_dir"])
    scenes_dir = project_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    img_path = scenes_dir / f"scene_{scene_idx:02d}.png"

    ig = ImageGeneratorAgent(engine=req.engine or "auto")
    style = req.style or project.get("style", "cinematic")
    res = ig.generate_single_scene_image(
        prompt=prompt,
        dest_path=img_path,
        style=style,
        topic=project.get("topic", ""),
        scene=target_scene,
        engine=req.engine or "auto",
        allow_fallback=True,
    )

    if not res.get("success", False) or not img_path.exists():
        err_msg = res.get("error") or res.get("fallback_reason") or "AI image generation failed. Please wait a few seconds and try again."
        raise HTTPException(status_code=503, detail=f"AI Generation Failed: {err_msg}")

    # Synchronize base image and remove stale overlays so the new generation shows everywhere
    base_path = scenes_dir / f"scene_{scene_idx:02d}_base.png"
    try:
        shutil.copy2(img_path, base_path)
    except Exception:
        pass
    for stale_suffix in ["_overlay.png", "_bg.png"]:
        st = scenes_dir / f"scene_{scene_idx:02d}{stale_suffix}"
        if st.exists():
            try:
                st.unlink()
            except Exception:
                pass

    # Update project record
    if 0 <= idx < len(scenes):
        scenes[idx]["image_path"] = str(img_path)
        scenes[idx]["visual_source"] = res.get("source", "ai_generated")
        scenes[idx]["visual_source_url"] = res.get("source_url")
        scenes[idx]["visual_prompt"] = res.get("prompt", prompt)
        vqa = (res.get("visual_quality") or {}).get("vision_qa") or {}
        _sync_visual_record(project, scene_idx, {
            "image_path": str(img_path), "source": res.get("source", "ai_generated"), "source_url": res.get("source_url"),
            "source_provider": res.get("source_provider"), "license": res.get("license"),
            "topic_match_score": vqa.get("score"), "content_verified": vqa.get("passed") is True,
            "topic_match_reason": vqa.get("reason") or "Regenerated from the scene editor", "prompt": res.get("prompt", prompt),
        })

    image_paths = project.get("image_paths", [])
    if 0 <= idx < len(image_paths):
        image_paths[idx] = str(img_path)
    else:
        while len(image_paths) < idx:
            image_paths.append(str(img_path))
        image_paths.append(str(img_path))
    project["image_paths"] = image_paths

    StorageManager.save_project(project)
    return JSONResponse(
        content={
            "status": "success",
            "message": f"Scene {scene_idx} image generated via AI!",
            "image_url": f"/api/scene_image/{project_id}/{scene_idx}?t={int(time.time()*1000)}",
            "prompt": res.get("prompt", prompt),
            "source": res.get("source", "ai_generated"),
            "provider": res.get("source_provider", "AI Generative Engine")
        },
        headers=NO_CACHE_HEADERS
    )

class FeedbackRequest(BaseModel):
    text: str


@app.get("/api/projects/{project_id}/feedback")
def list_feedback(project_id: str):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return JSONResponse(content={"feedback": project.get("feedback") or []}, headers=NO_CACHE_HEADERS)


@app.post("/api/projects/{project_id}/feedback")
def add_feedback(project_id: str, req: FeedbackRequest):
    """Saves a note about what's wrong with this video. 'Auto-fix & re-check' turns open notes into fixes."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Write what's wrong with the video first.")
    from agents import feedback_fixer
    item = feedback_fixer.new_item(text)
    # Show right away what Auto-fix will do with it (rules only: instant, no LLM)
    item["preview"] = [feedback_fixer.describe(a) for a in feedback_fixer.parse_rules(text, project)]
    project.setdefault("feedback", []).append(item)
    StorageManager.save_project(project)
    return JSONResponse(content={"status": "saved", "item": item, "feedback": project["feedback"]}, headers=NO_CACHE_HEADERS)


@app.delete("/api/projects/{project_id}/feedback/{feedback_id}")
def delete_feedback(project_id: str, feedback_id: str):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    before = len(project.get("feedback") or [])
    project["feedback"] = [f for f in project.get("feedback") or [] if f.get("id") != feedback_id]
    if len(project["feedback"]) == before:
        raise HTTPException(status_code=404, detail="Feedback note not found")
    StorageManager.save_project(project)
    return JSONResponse(content={"status": "deleted", "feedback": project["feedback"]}, headers=NO_CACHE_HEADERS)


@app.post("/api/projects/{project_id}/auto-repair")
def auto_repair_endpoint(project_id: str):
    """Re-checks the video and automatically fixes what it can (new images for repeated/wrong scenes,
    re-render for caption/sync problems, re-master audio, clean metadata), then re-checks again."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project["qa_report"] = pipeline.verify_video.run(project_record=project)
    StorageManager.save_project(project)
    try:
        repaired = pipeline.auto_repair(project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-repair failed: {e}")
    qa = repaired.get("qa_report") or {}
    if repaired.get("status") in ("completed", "needs_attention"):
        repaired["status"] = "completed" if qa.get("qa_passed") else "needs_attention"
        repaired["problems"] = [] if qa.get("qa_passed") else (qa.get("blocking_failures") or [])
        StorageManager.save_project(repaired)
    return JSONResponse(content={"status": "success", "passed": bool(qa.get("qa_passed")),
                                 "problems": repaired.get("problems") or [], "rounds": repaired.get("auto_repair") or [],
                                 "feedback": repaired.get("feedback") or [],
                                 "project": repaired}, headers=NO_CACHE_HEADERS)


@app.post("/api/projects/{project_id}/rerender")
def rerender_project_endpoint(project_id: str, req: RerenderRequest):
    """
    Re-renders the video after manual image or text updates.
    """
    try:
        updated_project = pipeline.rerender_project(
            project_id,
            with_voice=req.with_voice,
            with_music=req.with_music,
            audio_mode=req.audio_mode
        )
        return {"status": "success", "project": updated_project}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Re-render error: {e}")

@app.get("/api/scene_image/{project_id}/{scene_idx}")
def get_scene_image(project_id: str, scene_idx: int):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    idx = scene_idx - 1
    image_paths = project.get("image_paths", [])
    if 0 <= idx < len(image_paths) and Path(image_paths[idx]).exists():
        return FileResponse(str(image_paths[idx]), media_type="image/png", headers=NO_CACHE_HEADERS)

    p_dir = Path(project.get("project_dir", ""))
    target = p_dir / "scenes" / f"scene_{scene_idx:02d}.png"
    if target.exists():
        return FileResponse(str(target), media_type="image/png", headers=NO_CACHE_HEADERS)

    hero = p_dir / "scenes" / "hero_master.png"
    if hero.exists():
        return FileResponse(str(hero), media_type="image/png", headers=NO_CACHE_HEADERS)

    raise HTTPException(status_code=404, detail="Scene image not found")

@app.get("/api/scene_base_image/{project_id}/{scene_idx}")
def get_scene_base_image(project_id: str, scene_idx: int):
    """
    Returns the clean, layer-free base image for a scene.
    Used by Multi-Layer Image Studio to prevent re-baking or ghost layers.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    p_dir = Path(project.get("project_dir", ""))
    base_target = p_dir / "scenes" / f"scene_{scene_idx:02d}_base.png"
    if base_target.exists():
        return FileResponse(str(base_target), media_type="image/png", headers=NO_CACHE_HEADERS)

    # Fallback to scene image itself if clean base does not exist yet
    idx = scene_idx - 1
    image_paths = project.get("image_paths", [])
    if 0 <= idx < len(image_paths) and Path(image_paths[idx]).exists():
        return FileResponse(str(image_paths[idx]), media_type="image/png", headers=NO_CACHE_HEADERS)

    target = p_dir / "scenes" / f"scene_{scene_idx:02d}.png"
    if target.exists():
        return FileResponse(str(target), media_type="image/png", headers=NO_CACHE_HEADERS)

    hero = p_dir / "scenes" / "hero_master.png"
    if hero.exists():
        return FileResponse(str(hero), media_type="image/png", headers=NO_CACHE_HEADERS)

    raise HTTPException(status_code=404, detail="Scene base image not found")

@app.delete("/api/projects/{project_id}")
def delete_project_endpoint(project_id: str):
    success = StorageManager.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted", "id": project_id, "recoverable": True,
            "message": "Moved to the recycle bin (GET /api/trash, restore with POST /api/trash/{trash_id}/restore)."}


@app.get("/api/trash")
def list_trash():
    """Deleted projects that can still be restored (kept TRASH_KEEP_DAYS days, default 30)."""
    return JSONResponse(content=StorageManager.list_trash(), headers=NO_CACHE_HEADERS)


@app.post("/api/trash/{trash_id}/restore")
def restore_from_trash(trash_id: str):
    try:
        rec = StorageManager.restore_project(trash_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not rec:
        raise HTTPException(status_code=404, detail="Not found in the recycle bin")
    return {"status": "restored", "id": rec.get("id"), "project": rec}

@app.post("/api/publish/{project_id}")
def publish_to_youtube(project_id: str, req: PublishRequest):
    """
    Step 1: Uploads the Short to YouTube Studio channel UC4KV67NYzLi8JlrfB9J4hGg,
    fills all fields (title, description, tags, category, made_for_kids=False),
    and saves it as Private / Pending Approval.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    video_path = project.get("video_path")
    if not video_path or not Path(video_path).exists():
        raise HTTPException(status_code=400, detail="Video file does not exist")

    if req.title:
        project["title"] = req.title.strip()
    if req.description:
        project["description"] = req.description.strip()
    if req.tags is not None:
        project["tags"] = req.tags

    _require_fresh_qa(project, req.override_qa)

    is_car_proj = bool(project.get("is_car_edit") or project.get("style") == "car_edit")
    target_channel = req.channel or ("autoflashx" if is_car_proj else project.get("channel"))
    if target_channel:
        from agents import youtube_channels as _reg
        project["channel"] = _reg.get(target_channel)["key"]

    try:
        res = YouTubePublisher.upload_short(
            video_path=video_path,
            title=project.get("title", "WeaponX Labs Breakdown #Shorts"),
            description=project.get("description", "#Shorts #WeaponXLabs"),
            tags=project.get("tags", ["shorts", "weaponx lab"]),
            privacy_status="private",
            require_approval_before_live=req.require_approval_before_live,
            channel=project.get("channel"),
            project_dir=project.get("project_dir"),
            category_id=req.category_id or "28",
            made_for_kids=req.made_for_kids,
        )
        project["youtube"] = res
        # Uploads are always PRIVATE, so never call them "published"
        project["status"] = "pending_approval" if res.get("approval_status") == "pending_approval" else "uploaded_private"
        StorageManager.save_project(project)
        return {"status": "success", "youtube": res, "project": project}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _require_fresh_qa(project: Dict[str, Any], override: bool) -> None:
    """Blocks upload/approve (409) when the video fails Verify-video NOW, unless the user overrides."""
    from app.automation.publish_gate import fresh_qa
    ok, reasons = fresh_qa(project)
    if not ok and not override:
        raise HTTPException(status_code=409, detail={
            "qa_blocked": True,
            "message": "This video fails its quality check. Fix the issues and re-render, or approve anyway.",
            "reasons": reasons[:8],
            "score": (project.get("qa_report") or {}).get("overall_score"),
        })


@app.post("/api/publish/{project_id}/approve")
def approve_and_publish_live(project_id: str, req: ApprovePublishRequest):
    """
    Step 2: 'Approve' — updates the video's fields on YouTube and keeps it PRIVATE.
    The app never makes a video public; the owner publishes or schedules it in YouTube Studio.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if req.title:
        project["title"] = req.title.strip()
    if req.description:
        project["description"] = req.description.strip()
    if req.tags is not None:
        project["tags"] = req.tags

    _require_fresh_qa(project, req.override_qa)

    is_car_proj = bool(project.get("is_car_edit") or project.get("style") == "car_edit")
    target_channel = req.channel or ("autoflashx" if is_car_proj else project.get("channel"))
    if target_channel:
        from agents import youtube_channels as _reg
        project["channel"] = _reg.get(target_channel)["key"]

    try:
        res = YouTubePublisher.approve_and_go_live(
            project=project,
            title=project.get("title"),
            description=project.get("description"),
            tags=project.get("tags"),
            channel=project.get("channel"),
        )
        project["youtube"] = res
        # Approved but still PRIVATE on YouTube: the owner publishes/schedules it in YouTube Studio
        project["status"] = "approved_private"
        StorageManager.save_project(project)
        return {"status": "success", "youtube": res, "project": project}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))












class ChannelDefaultRequest(BaseModel):
    channel: str






@app.post("/api/projects/{project_id}/regenerate-weaponx-image")
def regenerate_weaponx_poster_for_project(project_id: str):
    """Regenerates a project's visual using the @WeaponXLabs 9:16 poster style and re-renders the 10s Short."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from agents.topic_agent import TopicAgent
    from agents.content_analyser import ContentAnalyserAgent
    from agents.image_generator import ImageGeneratorAgent

    p_dir = Path(project["project_dir"])
    topic = project.get("topic", "Military Technology")
    t_res = TopicAgent().run(topic=topic, target_duration=10.0, style="weaponx")
    c_res = ContentAnalyserAgent().run(topic_research=t_res, style="weaponx", target_duration=10.0)
    i_res = ImageGeneratorAgent().run(
        topic_research=t_res,
        content_analysis=c_res,
        output_dir=p_dir,
        style="weaponx",
    )
    project["style"] = "weaponx"
    project["is_weaponx_lab"] = True
    project["target_duration"] = 10.0
    # Same scene-source fields, poster description and photo credits as a fresh generation
    from app.agents.pipeline import attach_visual_metadata
    from agents.youtube_metadata import clean_metadata
    attach_visual_metadata(c_res, i_res["visual_records"])
    project["title"], project["description"], project["tags"] = clean_metadata(
        c_res.get("title") or project.get("title", ""), c_res.get("description", ""),
        c_res.get("tags") or project.get("tags") or [], topic)
    project["topic_research"] = t_res
    project["content_analysis"] = c_res
    project["image_report"] = i_res
    project["scenes"] = c_res["scenes"]
    project["image_paths"] = i_res["image_paths"]
    project["visual_records"] = i_res["visual_records"]
    StorageManager.save_project(project)

    updated = pipeline.rerender_project(project_id, with_voice=project.get("with_voice", True))
    return {"status": "success", "project": updated}

@app.get("/api/projects/{project_id}/image-prompt")
def get_project_image_prompt(project_id: str):
    """Returns the active image prompt, the WeaponX master template, and current poster title."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from agents.image_generator import WEAPONX_EXACT_SYSTEM_PROMPT

    topic = project.get("topic", "")
    content_res = project.get("content_analysis") or {}
    poster_spec = content_res.get("image_data", {}).get("weaponx_poster_spec") or {}
    headline = poster_spec.get("poster_title") or project.get("title") or topic.upper()

    active_prompt = (
        project.get("custom_image_prompt")
        or project.get("image_report", {}).get("prompt")
        or poster_spec.get("gemini_prompt")
        or f"{WEAPONX_EXACT_SYSTEM_PROMPT}\n\n**SPECIFIC CONTENT FOR THIS INFOGRAPHIC:**\n- Main Header Headline: {headline}\n- Focus / Topic: {topic}"
    )

    return JSONResponse(
        content={
            "project_id": project_id,
            "topic": topic,
            "headline": headline,
            "style": project.get("style", "weaponx"),
            "current_prompt": active_prompt,
            "weaponx_template": WEAPONX_EXACT_SYSTEM_PROMPT,
        },
        headers=NO_CACHE_HEADERS,
    )


@app.post("/api/projects/{project_id}/generate-from-prompt")
def generate_image_from_prompt(project_id: str, req: GenerateImagePromptRequest):
    """
    Regenerates/Calls image generator again using a customized prompt and/or custom headline.
    Updates the project visuals and re-renders the Short video.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from agents.topic_agent import TopicAgent
    from agents.content_analyser import ContentAnalyserAgent
    from agents.image_generator import ImageGeneratorAgent

    p_dir = Path(project["project_dir"])
    topic = project.get("topic", "Military Technology")
    style = req.style or project.get("style", "weaponx")

    t_res = project.get("topic_research") or TopicAgent().run(topic=topic, target_duration=10.0, style=style)
    c_res = project.get("content_analysis") or ContentAnalyserAgent().run(topic_research=t_res, style=style, target_duration=10.0)

    # If user provided a custom headline or prompt, inject it
    c_res.setdefault("image_data", {})
    poster_spec = c_res["image_data"].setdefault("weaponx_poster_spec", {})
    if req.headline:
        poster_spec["poster_title"] = req.headline.strip().upper()
    if req.prompt:
        poster_spec["gemini_prompt"] = req.prompt.strip()
        c_res["image_data"]["master_image_prompt"] = req.prompt.strip()

    i_res = ImageGeneratorAgent(engine=req.engine or "auto").run(
        topic_research=t_res,
        content_analysis=c_res,
        output_dir=p_dir,
        style=style,
        engine=req.engine or "auto",
    )

    project["style"] = style
    project["custom_image_prompt"] = req.prompt
    project["topic_research"] = t_res
    project["content_analysis"] = c_res
    project["image_report"] = i_res
    project["image_paths"] = i_res["image_paths"]
    project["visual_records"] = i_res["visual_records"]
    StorageManager.save_project(project)

    updated = pipeline.rerender_project(project_id, with_voice=project.get("with_voice", True))
    return {
        "status": "success",
        "message": "Image regenerated successfully from prompt!",
        "image_url": f"/api/scene_image/{project_id}/1",
        "project": updated,
    }


@app.post("/api/projects/{project_id}/edit-image")
def edit_image_overlay(project_id: str, req: EditImageOverlayRequest):
    """
    Modifies and edits a project image by adding a custom heading (with font style,
    font size, and color) and shapes (rounded rectangles, boxes, banners, borders).
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from agents.image_generator import ImageGeneratorAgent

    p_dir = Path(project.get("project_dir", ""))
    s_num = req.scene_number or 1

    # Find the target image to edit
    target_img = p_dir / "scenes" / f"scene_{s_num:02d}.png"
    if not target_img.exists():
        target_img = p_dir / "scenes" / "hero_master.png"
    if not target_img.exists():
        img_paths = project.get("image_paths", [])
        if img_paths and Path(img_paths[0]).exists():
            target_img = Path(img_paths[0])
        else:
            raise HTTPException(status_code=404, detail="Target image not found on disk")

    ig = ImageGeneratorAgent()
    try:
        if req.layers:
            ig.edit_image_with_layers(
                image_path=target_img,
                layers=req.layers,
                filters=req.filters,
                output_path=target_img,
            )
            if "scene_layers" not in project or not isinstance(project["scene_layers"], dict):
                project["scene_layers"] = {}
            project["scene_layers"][str(s_num)] = req.layers
            project["image_layers"] = req.layers
            project["image_filters"] = req.filters
        else:
            ig.edit_image_with_headings_and_shapes(
                image_path=target_img,
                heading=req.heading,
                shape=req.shape,
                output_path=target_img,
            )

        # If hero_master also exists, keep it in sync
        hero_img = p_dir / "scenes" / "hero_master.png"
        if hero_img.exists() and hero_img.resolve() != target_img.resolve() and s_num == 1:
            try:
                import shutil
                shutil.copy2(target_img, hero_img)
            except Exception:
                pass

        if req.rerender_video:
            updated = pipeline.rerender_project(project_id, with_voice=project.get("with_voice", True))
            project = updated
        else:
            StorageManager.save_project(project)

        return {
            "status": "success",
            "message": "Image modified and saved successfully!",
            "image_url": f"/api/scene_image/{project_id}/{s_num}",
            "project": project,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image modification error: {e}")

@app.get("/api/video/{project_id}")
def stream_video(project_id: str):
    project = StorageManager.get_project_by_id(project_id)
    if not project or not project.get("video_path"):
        raise HTTPException(status_code=404, detail="Video not found")
    
    video_path = Path(project["video_path"])
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing on disk")

    return FileResponse(str(video_path), media_type="video/mp4", headers=NO_CACHE_HEADERS)

@app.get("/api/projects/{project_id}/voiceover")
def get_project_voiceover(project_id: str):
    """Streams project clean voiceover for live audition mixing."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    p_dir = Path(project.get("project_dir", ""))
    candidates = [
        p_dir / "voiceover_hindi.mp3",
        p_dir / "voiceover.mp3",
        p_dir / "voice.mp3",
        p_dir / "voiceover.wav"
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 500:
            media = "audio/wav" if c.suffix.lower() == ".wav" else "audio/mpeg"
            return FileResponse(str(c), media_type=media, headers=NO_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="No voiceover audio found for project")

@app.get("/api/thumbnail/{project_id}")
def get_thumbnail(project_id: str):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Sharpest of the opening scene images (scene 1 is often a hazy/atmospheric shot)
    from app.agents.thumbnail import pick_thumbnail
    thumb = pick_thumbnail(project)
    if thumb and Path(thumb).exists():
        return FileResponse(str(thumb), media_type="image/png", headers=NO_CACHE_HEADERS)

    # Fallback to general icon
    return JSONResponse(status_code=404, content={"message": "No thumbnail"})


# ==============================================================================
# MULTI-AGENT ENDPOINTS (topic-agent, content-analyser, image-generator, Verify-video)
# ==============================================================================

class TopicAgentRequest(BaseModel):
    topic: Optional[str] = None
    language: str = "en"
    target_duration: float = 25.0
    custom_notes: Optional[str] = None

class ContentAnalyserRequest(BaseModel):
    topic_research: Dict[str, Any]
    style: str = "default"
    target_duration: Optional[float] = 25.0
    language: Optional[str] = "en"







# ==========================================
# AI Music & Saved Music Library
# ==========================================



SYNTH_FALLBACK_WARNING = "ACE-Step music server is not running, so this is a synthesized ambience (tones + noise), not AI music. Start it with scripts/start_acestep.sh."


def _mark_synth_fallback(track):
    """Labels procedural-synth output honestly so it isn't mistaken for AI-composed music."""
    if isinstance(track, dict):
        track["engine"] = "procedural_synth"
        track["warning"] = SYNTH_FALLBACK_WARNING
        name = track.get("name") or ""
        if name and not name.startswith("Synth ambience"):
            track["name"] = f"Synth ambience · {name}"
    return track


















class MusicOnlyClipsRequest(BaseModel):
    category: Optional[str] = "Sleep Music"
    mood: Optional[str] = "Relaxing"
    vocals: Optional[str] = "Instrumental"
    duration: Optional[float] = 30.0
    clip_count: Optional[int] = 3
    prompt: Optional[str] = None
    track_id: Optional[str] = None
    clip_start: Optional[float] = 0.0
    clip_duration: Optional[float] = None
    clip_loop: Optional[bool] = True




# ==========================================
# Hindi Speaking Agent & Voiceover API
# ==========================================

@app.get("/api/voices")
def get_available_voices():
    """Lists available Hindi (Madhur, Swara) and English voices."""
    from agents.hindi_voice_agent import HindiVoiceAgent
    return JSONResponse(content={
        "hindi": HindiVoiceAgent.HINDI_VOICES,
        "english": {
            "en-US-ChristopherNeural": {"name": "Christopher (US)", "gender": "Male", "style": "Authoritative Narrative"},
            "en-US-EricNeural": {"name": "Eric (US)", "gender": "Male", "style": "Dynamic Fast-Paced"},
            "en-IN-PrabhatNeural": {"name": "Prabhat (Indian English)", "gender": "Male", "style": "Professional Defense Documentary"}
        }
    }, headers=NO_CACHE_HEADERS)

@app.post("/api/projects/{project_id}/convert-hindi")
def convert_hindi_endpoint(project_id: str, req: ConvertHindiRequest):
    """Converts an existing short into Hindi voiceover with synchronized Devanagari subtitles."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from agents.hindi_voice_agent import HindiVoiceAgent
    agent = HindiVoiceAgent()
    try:
        updated_project = agent.convert_project_to_hindi(project, voice=req.voice or "hi-IN-MadhurNeural")
        StorageManager.save_project(updated_project)
        return JSONResponse(content={
            "status": "success",
            "message": f"Successfully converted project to Hindi with voice {req.voice}!",
            "project": updated_project
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hindi conversion failed: {e}")

# ---------------------------------------------------------------------------
# Per-scene motion & image effects (zoom / pan / focus / colour grades / focus blur / fades)
# ---------------------------------------------------------------------------
class SceneEffectsRequest(BaseModel):
    motion: Optional[str] = None
    motion_strength: Optional[str] = None
    speed_ramp: Optional[str] = None
    beat_sync: Optional[bool] = None
    bpm: Optional[float] = None
    focus_point: Optional[Dict[str, float]] = None
    effects: Optional[Dict[str, Any]] = None
    apply_to_all: Optional[bool] = False


class SceneEffectPreviewRequest(SceneEffectsRequest):
    project_id: str
    scene: int = 1
    seconds: Optional[float] = 2.5


@app.get("/api/scene-effects/options")
def scene_effect_options():
    from agents import scene_effects as sfx
    return JSONResponse(content=sfx.options(), headers=NO_CACHE_HEADERS)


@app.post("/api/projects/{project_id}/scenes/{scene_idx}/effects")
def save_scene_effects(project_id: str, scene_idx: int, req: SceneEffectsRequest):
    """Validates and saves motion/effects for one scene (or, with apply_to_all, as the video default).
    Re-render the project to apply them to the video."""
    from agents import scene_effects as sfx
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = project.get("scenes") or []
    if not 1 <= scene_idx <= len(scenes):
        raise HTTPException(status_code=404, detail=f"Scene {scene_idx} not found (project has {len(scenes)} scenes)")
    try:
        values = sfx.validate(req.dict(exclude={"apply_to_all"}))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    keys = ("motion", "motion_strength", "speed_ramp", "beat_sync", "bpm", "focus_point", "effects")
    if req.apply_to_all:
        merged = {**(project.get("scene_defaults") or {}), **values}
        if "effects" in values:
            merged["effects"] = {**((project.get("scene_defaults") or {}).get("effects") or {}), **values["effects"]}
        project["scene_defaults"] = merged
        for sc in scenes:  # the new default applies everywhere
            for k in keys:
                sc.pop(k, None)
    else:
        sc = scenes[scene_idx - 1]
        for k, v in values.items():
            sc[k] = {**(sc.get("effects") or {}), **v} if k == "effects" else v
    project["scenes"] = scenes
    StorageManager.save_project(project)
    return JSONResponse(content={"status": "saved", "applied_to": "all scenes" if req.apply_to_all else f"scene {scene_idx}",
                                 "resolved": sfx.resolve(scenes[scene_idx - 1], project.get("scene_defaults")),
                                 "project": project}, headers=NO_CACHE_HEADERS)


@app.post("/api/scene-effect-preview")
def scene_effect_preview(req: SceneEffectPreviewRequest):
    """Read-only 360x640 MP4 preview of one scene with the given (unsaved) motion & effects."""
    import tempfile
    from agents import scene_effects as sfx
    from app.agents.video_composer import VideoComposer
    project = StorageManager.get_project_by_id(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = project.get("scenes") or []
    if not 1 <= req.scene <= len(scenes):
        raise HTTPException(status_code=404, detail=f"Scene {req.scene} not found")
    scene = scenes[req.scene - 1]
    img = scene.get("image_path") or (project.get("image_paths") or [None] * req.scene)[req.scene - 1]
    if not img or not Path(img).exists():
        raise HTTPException(status_code=400, detail="This scene has no image to preview")
    try:
        overrides = sfx.validate(req.dict(exclude={"apply_to_all", "project_id", "scene", "seconds"}))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    merged_scene = {**scene, **overrides}
    if "effects" in overrides:
        merged_scene["effects"] = {**(scene.get("effects") or {}), **overrides["effects"]}
    settings = sfx.resolve(merged_scene, project.get("scene_defaults"))
    out = Path(tempfile.mkdtemp(prefix="fxprev_")) / "preview.mp4"
    try:
        VideoComposer().render_scene_preview(img, settings, req.seconds or 2.5, out, scene_idx=req.scene - 1)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview render failed: {str(e)[-300:]}")
    return FileResponse(str(out), media_type="video/mp4", headers=NO_CACHE_HEADERS)


# ---------------------------------------------------------------------------
# Daily Car Edit Automation: 7-Day Queue, Mood Rotation & Telegram Approval
# ---------------------------------------------------------------------------
class CarQueueUpdateRequest(BaseModel):
    car_name: Optional[str] = None
    mood_id: Optional[str] = None
    duration: Optional[float] = None


class CarQueueRefillRequest(BaseModel):
    force_reset: Optional[bool] = False













# ------------------------------------------------------------------------------------------------
# Route groups split into app/routes/ (imported last: they use the models/helpers defined above)
# ------------------------------------------------------------------------------------------------
from app.routes import agents as _routes_agents, car_queue as _routes_car_queue, music as _routes_music, \
    settings as _routes_settings  # noqa: E402

for _r in (_routes_music, _routes_car_queue, _routes_agents, _routes_settings):
    app.include_router(_r.router)
