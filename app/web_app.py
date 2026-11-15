import os
import time
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
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
    if project and project.get("status") == "in_progress" and not _is_stale_in_progress(project):
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


@app.on_event("startup")
def mark_interrupted_generations():
    """Background generations don't survive a restart; don't leave them 'in progress' forever."""
    try:
        for p in StorageManager.get_all_projects():
            if p.get("status") == "in_progress":
                p["status"] = "failed"
                p["error"] = "Interrupted: the server restarted while this video was generating."
                p["progress_step"] = "Failed: interrupted by server restart"
                StorageManager.save_project(p)
                print(f"[WebAPI] Marked interrupted generation as failed: {p.get('id')}")
    except Exception as e:
        print(f"[WebAPI] Startup recovery skipped: {e}")

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

class PublishRequest(BaseModel):
    privacy_status: Optional[str] = "private"
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list] = None
    category_id: Optional[str] = "28"
    made_for_kids: bool = False
    require_approval_before_live: bool = True

class ApprovePublishRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list] = None

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

@app.get("/")
def get_dashboard():
    index_file = STATIC_DIR / "index.html"
    return FileResponse(str(index_file))

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
    """Runs the QA Tester Agent full sanity suite and returns structured report."""
    from agents.qa_tester_agent import QATesterAgent
    tester = QATesterAgent()
    report = tester.run_full_sanity()
    return JSONResponse(content=report, headers=NO_CACHE_HEADERS)

@app.get("/api/qa/status")
def get_qa_status_endpoint():
    """Returns the latest QA status and sanity metrics."""
    from agents.qa_tester_agent import QATesterAgent
    tester = QATesterAgent()
    report = tester.run_full_sanity()
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
        if p.get("status") != "in_progress" or _is_stale_in_progress(p):
            continue
        if _norm_topic(p.get("topic")) == key and (p.get("style") or "default").lower() in (style_key, "weaponx" if style_key == "weaponx" else style_key):
            return p
    return None


def _start_generation(req, audio_mode, with_voice, with_music, duration, background_tasks):
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
            music_volume=req.music_volume
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare project: {e}")

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
async def upload_scene_image(project_id: str, scene_idx: int, file: UploadFile = File(...)):
    """
    Manually upload/replace an image for a specific scene.
    Automatically formats into full-bleed 1080x1920 9:16 vertical.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content = await file.read()
    if not content or len(content) < 1000:
        raise HTTPException(status_code=400, detail="Invalid image file")

    try:
        raw_img = Image.open(io.BytesIO(content)).convert("RGB")
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

        StorageManager.save_project(project)
        return {"status": "success", "image_url": f"/api/scene_image/{project_id}/{scene_idx}"}
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

    # Grow the target length so the existing scenes aren't squeezed to make room
    if project.get("target_duration"):
        project["target_duration"] = round(float(project["target_duration"]) + est, 2)
    project["updated_at"] = datetime.now().isoformat()
    StorageManager.save_project(project)
    return {
        "status": "success",
        "scene_number": pos,
        "message": f"Scene {pos} added (~{est:.1f}s). It uses a copy of a neighbouring image; replace it, then Re-render.",
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

    try:
        res = YouTubePublisher.upload_short(
            video_path=video_path,
            title=project.get("title", "WeaponX Labs Breakdown #Shorts"),
            description=project.get("description", "#Shorts #WeaponXLabs"),
            tags=project.get("tags", ["shorts", "weaponx lab"]),
            privacy_status=req.privacy_status,
            require_approval_before_live=req.require_approval_before_live,
            project_dir=project.get("project_dir"),
            category_id=req.category_id or "28",
            made_for_kids=req.made_for_kids,
        )
        project["youtube"] = res
        project["status"] = "pending_approval" if res.get("approval_status") == "pending_approval" else "published"
        StorageManager.save_project(project)
        return {"status": "success", "youtube": res, "project": project}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/publish/{project_id}/approve")
def approve_and_publish_live(project_id: str, req: ApprovePublishRequest):
    """
    Step 2: Triggered when the user clicks 'Approve & Go Live'.
    Switches the saved video on channel UC4KV67NYzLi8JlrfB9J4hGg from 'private' (draft)
    to 'public' so it immediately goes LIVE on YouTube Shorts.
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

    try:
        res = YouTubePublisher.approve_and_go_live(
            project=project,
            title=project.get("title"),
            description=project.get("description"),
            tags=project.get("tags"),
        )
        project["youtube"] = res
        project["status"] = "published"
        StorageManager.save_project(project)
        return {"status": "success", "youtube": res, "project": project}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/settings")
def get_studio_settings():
    import json as _json
    settings_file = config.STUDIO_SETTINGS_FILE
    saved = {}
    if settings_file.exists():
        try:
            saved = _json.loads(settings_file.read_text(encoding="utf-8"))
        except Exception:
            saved = {}
    has_key = bool(saved.get("gemini_api_key") or config.GEMINI_API_KEY)
    return JSONResponse(
        content={
            "gemini_configured": has_key,
            "gemini_reference_url": saved.get("gemini_reference_url", config.GEMINI_REFERENCE_URL),
            "has_weaponx_reference_image": config.WEAPONX_REFERENCE_IMAGE.exists(),
            "youtube_channel_id": saved.get("youtube_channel_id", config.YOUTUBE_TARGET_CHANNEL_ID),
            "youtube_studio_url": f"https://studio.youtube.com/channel/{saved.get('youtube_channel_id', config.YOUTUBE_TARGET_CHANNEL_ID)}",
            "youtube_oauth_configured": YouTubePublisher.is_configured(),
            "youtube_authenticated": YouTubePublisher.is_authenticated(),
            "hf_token_configured": bool(clip_generator.get_hf_token()),
        },
        headers=NO_CACHE_HEADERS,
    )


@app.post("/api/settings")
def update_studio_settings(req: StudioSettingsRequest):
    import json as _json
    settings_file = config.STUDIO_SETTINGS_FILE
    saved = {}
    if settings_file.exists():
        try:
            saved = _json.loads(settings_file.read_text(encoding="utf-8"))
        except Exception:
            saved = {}
    if req.gemini_api_key is not None and req.gemini_api_key.strip():
        saved["gemini_api_key"] = req.gemini_api_key.strip()
        os.environ["GEMINI_API_KEY"] = req.gemini_api_key.strip()
    if req.hf_token is not None and req.hf_token.strip():
        saved["hf_token"] = req.hf_token.strip()
    if req.gemini_reference_url:
        saved["gemini_reference_url"] = req.gemini_reference_url.strip()
    if req.youtube_channel_id:
        saved["youtube_channel_id"] = req.youtube_channel_id.strip()
    settings_file.write_text(_json.dumps(saved, indent=2), encoding="utf-8")
    return {"status": "success", "gemini_configured": bool(saved.get("gemini_api_key") or config.GEMINI_API_KEY)}


@app.post("/api/settings/weaponx-reference")
async def upload_weaponx_reference_image(file: UploadFile = File(...)):
    """Uploads a reference image from the user's Gemini session (https://gemini.google.com/u/1/app/dbdf5025a758bf01)."""
    content = await file.read()
    if not content or len(content) < 1000:
        raise HTTPException(status_code=400, detail="Invalid image file")
    try:
        raw_img = Image.open(io.BytesIO(content)).convert("RGB")
        raw_img.save(config.WEAPONX_REFERENCE_IMAGE, "PNG")
        return {"status": "success", "path": str(config.WEAPONX_REFERENCE_IMAGE)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save reference image: {e}")


@app.post("/api/settings/youtube-secrets")
async def upload_youtube_client_secrets(file: UploadFile = File(...)):
    """Uploads Google Cloud OAuth client_secrets.json into credentials/client_secrets.json."""
    import json as _json
    content = await file.read()
    try:
        parsed = _json.loads(content.decode("utf-8"))
        if "installed" not in parsed and "web" not in parsed:
            raise ValueError("JSON must be a Google OAuth 2.0 Client ID file ('installed' or 'web' key).")
        config.YOUTUBE_CLIENT_SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.YOUTUBE_CLIENT_SECRETS_FILE.write_text(_json.dumps(parsed, indent=2), encoding="utf-8")
        return {"status": "success", "path": str(config.YOUTUBE_CLIENT_SECRETS_FILE)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid client_secrets.json: {e}")


@app.post("/api/settings/youtube-auth")
def trigger_youtube_oauth():
    """Triggers YouTube OAuth 2.0 browser sign-in flow and saves credentials/youtube_tokens.json."""
    try:
        YouTubePublisher.get_authenticated_service()
        return {"status": "success", "youtube_oauth_configured": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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

    image_paths = project.get("image_paths", [])
    if image_paths and Path(image_paths[0]).exists():
        return FileResponse(str(image_paths[0]), media_type="image/png")

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

@app.get("/api/agents")
def list_agents():
    """Returns metadata on all autonomous studio agents."""
    return {
        "agents": [
            {
                "id": "topic-agent",
                "class": "TopicAgent",
                "module": "agents.topic_agent",
                "description": "Takes topics and performs deep research from Wikipedia, DuckDuckGo, and verified knowledge bases.",
            },
            {
                "id": "content-analyser",
                "class": "ContentAnalyserAgent",
                "module": "agents.content_analyser",
                "description": "Checks, fact-verifies, and corrects text coming from topic-agent, calibrating hooks and scene pacing.",
            },
            {
                "id": "image-generator",
                "class": "ImageGeneratorAgent",
                "module": "agents.image_generator",
                "description": "Deep searches images, checks source provenance/licenses, verifies images match the topic, and triggers CHANGE_IMAGE replacements if required.",
            },
            {
                "id": "music-agent",
                "class": "MusicAgent",
                "module": "agents.music_agent",
                "description": "Performs deep prompt research, multi-stem algorithmic composition (drums, bass, guitar riffs, leads, choir formants), and prompt adherence verification.",
            },
            {
                "id": "hindi-voice-agent",
                "class": "HindiVoiceAgent",
                "module": "agents.hindi_voice_agent",
                "description": "Translates and localizes scripts into authentic Hindi (शुद्ध हिंदी) with neural voices and synchronized Devanagari subtitles.",
            },
            {
                "id": "Verify-video",
                "class": "VerifyVideoAgent",
                "module": "agents.verify_video",
                "description": "End-to-end verifier that checks topic research, content corrections, image sources & topic match, audio/subtitles, and decoded video frames.",
            },
            {
                "id": "qa-tester-agent",
                "class": "QATesterAgent",
                "module": "agents.qa_tester_agent",
                "description": "Autonomous full-stack QA engineer that audits DOM contracts, AST syntax, PIL image engines, and agent pipelines.",
            },
        ]
    }

@app.post("/api/agents/topic-agent")
def run_topic_agent_endpoint(req: TopicAgentRequest):
    from agents.topic_agent import TopicAgent
    agent = TopicAgent(language=req.language)
    res = agent.run(
        topic=req.topic,
        language=req.language,
        target_duration=req.target_duration,
        custom_notes=req.custom_notes,
    )
    return JSONResponse(content=res, headers=NO_CACHE_HEADERS)

@app.post("/api/agents/content-analyser")
def run_content_analyser_endpoint(req: ContentAnalyserRequest):
    from agents.content_analyser import ContentAnalyserAgent
    agent = ContentAnalyserAgent()
    res = agent.run(
        topic_research=req.topic_research,
        style=req.style,
        target_duration=req.target_duration,
        language=req.language,
    )
    return JSONResponse(content=res, headers=NO_CACHE_HEADERS)

@app.post("/api/agents/image-generator/{project_id}")
def run_image_generator_endpoint(project_id: str):
    """Runs 'image-generator' on an existing project to re-verify sources and replace any mismatched images."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from agents.image_generator import ImageGeneratorAgent
    p_dir = Path(project.get("project_dir", ""))
    topic_res = project.get("topic_research") or {"topic": project.get("topic", "")}
    content_res = project.get("content_analysis") or {
        "topic": project.get("topic", ""),
        "scenes": project.get("scenes", []),
    }
    agent = ImageGeneratorAgent()
    img_report = agent.run(
        topic_research=topic_res,
        content_analysis=content_res,
        output_dir=p_dir,
        style=project.get("style", "default"),
    )
    project["image_report"] = img_report
    project["visual_records"] = img_report["visual_records"]
    project["image_paths"] = img_report["image_paths"]
    StorageManager.save_project(project)
    return JSONResponse(content=img_report, headers=NO_CACHE_HEADERS)

@app.get("/api/agents/verify-video/{project_id}")
def run_verify_video_endpoint(project_id: str):
    """Runs 'Verify-video' across all stages of a project."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from agents.verify_video import VerifyVideoAgent
    agent = VerifyVideoAgent()
    report = agent.run(project_record=project)
    project["qa_report"] = report
    project["verify_video_report"] = report
    StorageManager.save_project(project)
    return JSONResponse(content=report, headers=NO_CACHE_HEADERS)


# ==========================================
# AI Music & Saved Music Library
# ==========================================

@app.get("/api/music/tracks")
def get_music_tracks():
    """Lists available AI-generated and saved library music tracks."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    return JSONResponse(content={
        "tracks": mg.list_tracks(),
        "styles": AIMusicGenerator.STYLES
    }, headers=NO_CACHE_HEADERS)


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

@app.post("/api/music/generate-ai")
def generate_ai_music_endpoint(req: AIMusicGenerateRequest):
    """Procedurally synthesizes an AI music track with multi-stem audio layering."""
    from agents.music_generator import AIMusicGenerator
    dur = req.duration if req.duration is not None else 30.0
    # Real AI music via the local ACE-Step model when it's running
    from agents.acestep_music_agent import ACEStepMusicAgent
    acestep = ACEStepMusicAgent()
    if acestep.is_available():
        try:
            style_key = (req.style or "epic_cinematic").lower()
            category = "Electronic" if "cyber" in style_key else ("Rock" if "strike" in style_key else "Cinematic")
            mood = "Tense" if ("stealth" in style_key or "cyber" in style_key) else "Epic"
            track = acestep.generate_track(category=category, mood=mood, vocals="Instrumental",
                                           duration=max(10.0, dur), prompt=req.prompt)
            return JSONResponse(content={
                "status": "success",
                "engine": "ace-step",
                "filename": track.get("filename"),
                "url": track.get("url"),
                "style": req.style,
                "duration": dur,
                "file_path": track.get("file_path"),
                "track": track,
            }, headers=NO_CACHE_HEADERS)
        except Exception as e:
            logger.warning(f"ACE-Step generation failed in generate-ai, falling back to synth: {e}")
    mg = AIMusicGenerator()
    try:
        out_path = mg.generate_ai_music(style=req.style or "epic_cinematic", duration=dur, prompt=req.prompt)
        return JSONResponse(content={
            "status": "success",
            "engine": "procedural_synth",
            "warning": SYNTH_FALLBACK_WARNING,
            "filename": out_path.name,
            "url": f"/api/music/preview/{out_path.name}?type=ai",
            "style": req.style,
            "duration": dur,
            "file_path": str(out_path)
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI music generation failed: {e}")

@app.get("/api/music/meta")
def get_music_meta():
    """Returns categories, moods, vocal types, durations, and default prompts."""
    from agents.music_generator import AIMusicGenerator
    return JSONResponse(content={
        "categories": list(AIMusicGenerator.CATEGORIES.keys()),
        "categories_info": {k: {"desc": v["desc"], "bpm": v["tempo_bpm"]} for k, v in AIMusicGenerator.CATEGORIES.items()},
        "moods": list(AIMusicGenerator.MOODS.keys()),
        "vocals": list(AIMusicGenerator.VOCALS.keys()),
        "durations": [
            {"label": "30 sec", "seconds": 30.0},
            {"label": "60 sec", "seconds": 60.0},
            {"label": "2 min", "seconds": 120.0},
            {"label": "3 min", "seconds": 180.0}
        ],
        "default_prompts": AIMusicGenerator.DEFAULT_PROMPTS
    }, headers=NO_CACHE_HEADERS)

@app.post("/api/music/agent/research")
def research_music_prompt_endpoint(req: CustomMusicGenerateRequest):
    """Deeply researches user music prompt, extracts BPM, scale, root key, and composition specs."""
    from agents.music_agent import MusicAgent
    agent = MusicAgent()
    try:
        specs = agent.deep_research_prompt(
            prompt=req.prompt,
            category=req.category or "Metal",
            mood=req.mood or "Aggressive",
            vocals=req.vocals or "Instrumental",
            duration=req.duration or 60.0
        )
        return JSONResponse(content={"status": "success", "research_specs": specs}, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Music research failed: {e}")

@app.post("/api/music/agent/generate")
@app.post("/api/agents/music-agent")
def generate_music_agent_endpoint(req: CustomMusicGenerateRequest):
    """Autonomous MusicAgent: Researches prompt deeply, composes multi-stem audio, and validates adherence.
    Prefers ACE-Step 1.5 neural generator when available."""
    from agents.acestep_music_agent import ACEStepMusicAgent
    acestep = ACEStepMusicAgent()
    if acestep.is_available():
        try:
            track = acestep.generate_track(
                category=req.category or "Cinematic",
                mood=req.mood or "Epic",
                vocals=req.vocals or "Instrumental",
                duration=req.duration or 60.0,
                prompt=req.prompt,
                name=req.name,
                lyrics=req.lyrics,
            )
            return JSONResponse(content={"status": "success", "track": track}, headers=NO_CACHE_HEADERS)
        except Exception as e:
            logger.warning(f"ACE-Step generation in MusicAgent failed, using procedural fallback: {e}")

    from agents.music_agent import MusicAgent
    agent = MusicAgent()
    try:
        res = agent.generate_track(
            category=req.category or "Metal",
            mood=req.mood or "Aggressive",
            vocals=req.vocals or "Instrumental",
            duration=req.duration or 60.0,
            prompt=req.prompt,
            name=req.name,
            save_to_library=bool(req.save_to_library),
            is_default=bool(req.is_default)
        )
        return JSONResponse(content={"status": "success", "track": _mark_synth_fallback(res),
                                     "warning": SYNTH_FALLBACK_WARNING}, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MusicAgent generation failed: {e}")

@app.post("/api/music/agent/deep-verify")
def deep_verify_music_endpoint(req: DeepVerifyMusicRequest):
    """
    Performs deep acoustic and theory verification of the generated music track
    against the requested Category, Mood, Vocals, Duration, and Prompt.
    """
    from agents.music_agent import MusicAgent
    agent = MusicAgent()
    audio_p = None
    if req.file_path and Path(req.file_path).exists():
        audio_p = Path(req.file_path)
    elif req.filename:
        cand = list(agent.ai_music_dir.glob(f"*{req.filename}*")) + list(agent.library_dir.glob(f"*{req.filename}*")) + list(agent.yt_music_dir.glob(f"*{req.filename}*"))
        if cand:
            audio_p = cand[0]

    if not audio_p or not audio_p.exists():
        raise HTTPException(status_code=404, detail=f"Audio track not found: {req.filename or req.file_path}")

    try:
        report = agent.deep_verify_audio(
            audio_path=audio_p,
            category=req.category or "Metal",
            mood=req.mood or "Aggressive",
            vocals=req.vocals or "Instrumental",
            duration=req.duration or 60.0,
            prompt=req.prompt
        )
        return JSONResponse(content={"status": "success", "verification": report}, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deep verification failed: {e}")

@app.post("/api/music/generate-custom")
def generate_custom_music_endpoint(req: CustomMusicGenerateRequest):
    """Generates original AI music matching Category, Mood, Vocals, Duration, and Prompt.
    Automatically prioritizes the ACE-Step 1.5 neural engine if active."""
    from agents.acestep_music_agent import ACEStepMusicAgent
    acestep = ACEStepMusicAgent()
    if acestep.is_available():
        try:
            track = acestep.generate_track(
                category=req.category or "Cinematic",
                mood=req.mood or "Epic",
                vocals=req.vocals or "Instrumental",
                duration=req.duration or 60.0,
                prompt=req.prompt,
                name=req.name,
                lyrics=req.lyrics,
            )
            return JSONResponse(content={"status": "success", "track": track}, headers=NO_CACHE_HEADERS)
        except Exception as e:
            logger.warning(f"ACE-Step generation failed in custom endpoint, falling back to procedural: {e}")

    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    try:
        res = mg.generate_custom_music(
            category=req.category or "Metal",
            mood=req.mood or "Aggressive",
            vocals=req.vocals or "Instrumental",
            duration=req.duration or 60.0,
            prompt=req.prompt,
            name=req.name,
            save_to_library=bool(req.save_to_library),
            is_default=bool(req.is_default)
        )
        return JSONResponse(content={"status": "success", "track": _mark_synth_fallback(res),
                                     "warning": SYNTH_FALLBACK_WARNING}, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Custom music generation failed: {e}")

@app.get("/api/music/acestep/status")
def acestep_status():
    """Reports whether the local ACE-Step 1.5 API server is reachable."""
    from agents.acestep_music_agent import ACEStepMusicAgent
    a = ACEStepMusicAgent()
    return JSONResponse(content={"available": a.is_available(), "url": a.base_url}, headers=NO_CACHE_HEADERS)

@app.post("/api/music/acestep/generate")
def acestep_generate(req: CustomMusicGenerateRequest):
    """Generates music with the local ACE-Step 1.5 server (free)."""
    from agents.acestep_music_agent import ACEStepMusicAgent
    agent = ACEStepMusicAgent()
    if agent.health_error():
        raise HTTPException(status_code=503, detail=f"ACE-Step unavailable: {agent.health_error()}")
    try:
        track = agent.generate_track(
            category=req.category or "Cinematic", mood=req.mood or "Epic",
            vocals=req.vocals or "Instrumental", duration=req.duration or 60.0,
            prompt=req.prompt, name=req.name, lyrics=req.lyrics,
        )
        return JSONResponse(content={"status": "success", "track": track}, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ACE-Step generation failed: {e}")

@app.get("/api/music/library")
def get_saved_music_library():
    """Returns list of user's saved library music tracks."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    return JSONResponse(content={"library": mg.list_saved_library()}, headers=NO_CACHE_HEADERS)

@app.get("/api/music/recent-generated")
def get_recent_generated_music():
    """Returns recently synthesized AI music tracks from assets/audio/ai_generated."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    return JSONResponse(content={"recent": mg.list_recent_ai_tracks(limit=12)}, headers=NO_CACHE_HEADERS)

@app.post("/api/music/library/save")
def save_music_to_library_endpoint(req: SaveMusicToLibraryRequest):
    """Saves any generated track to persistent library so it can be reused in future video creation."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    source = req.filename or req.track_id
    if not source:
        raise HTTPException(status_code=400, detail="filename or track_id is required")
    try:
        record = mg.save_to_library(
            source_path_or_id=source,
            name=req.name,
            category=req.category or "Custom",
            mood=req.mood or "Epic",
            vocals=req.vocals or "Instrumental",
            duration=req.duration or 60.0,
            prompt=req.prompt or "",
            is_default=bool(req.is_default)
        )
        return JSONResponse(content={"status": "success", "message": "Saved to library successfully!", "track": record}, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save to library: {e}")

@app.delete("/api/music/library/{track_id}")
def delete_music_from_library_endpoint(track_id: str):
    """Deletes a saved music track from user's library."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    deleted = mg.delete_from_library(track_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Track not found in library")
    return JSONResponse(content={"status": "success", "message": "Deleted from library"}, headers=NO_CACHE_HEADERS)

@app.post("/api/music/library/{track_id}/set-default")
def set_default_music_endpoint(track_id: str):
    """Sets a saved track as the default music for future video creations."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    ok = mg.set_default_library_track(track_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Track not found in library")
    return JSONResponse(content={"status": "success", "message": "Set as default music for next video creations"}, headers=NO_CACHE_HEADERS)

@app.get("/api/music/preview/{filename}")
def preview_music(filename: str, type: Optional[str] = None):
    """Streams preview audio for web playback."""
    candidates = [
        config.AUDIO_ASSETS_DIR / "library" / filename,
        config.AUDIO_ASSETS_DIR / "ai_generated" / filename,
        config.AUDIO_ASSETS_DIR / "youtube" / filename,
        config.AUDIO_ASSETS_DIR / filename
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            media = "audio/wav" if p.suffix.lower() == ".wav" else "audio/mpeg"
            return FileResponse(str(p), media_type=media, headers=NO_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="Audio track not found")

@app.post("/api/projects/{project_id}/apply-music")
def apply_music_endpoint(project_id: str, req: ApplyMusicRequest):
    """
    Applies background music or advanced audio remix onto an existing short video.
    Also handles cleanly removing music from video while restoring 100% clean voiceover.
    """
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    video_path = project.get("video_path")
    p_dir = Path(project.get("project_dir", ""))
    if not video_path or not Path(video_path).exists():
        video_path = p_dir / "final_short.mp4"
        if not video_path.exists():
            raise HTTPException(status_code=400, detail="Video file not found for project.")

    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()

    mv = float(req.music_volume) if req.music_volume is not None else (float(req.volume) if req.volume is not None else 0.22)
    vv = float(req.voice_volume) if req.voice_volume is not None else 1.0

    # 1. Option to remove music completely
    if req.remove_music:
        try:
            clean_path = mg.remove_video_music(
                video_path=Path(video_path),
                voice_volume=vv
            )
            project["video_path"] = str(clean_path)
            project["with_music"] = False
            project["audio_mode"] = "without_music"
            project["music_track"] = None
            project["voice_volume"] = vv
            StorageManager.save_project(project)
            return JSONResponse(content={
                "status": "success",
                "message": "Background music removed from video! Voiceover is now 100% clean.",
                "video_path": str(clean_path),
                "project": project
            }, headers=NO_CACHE_HEADERS)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to remove music: {e}")

    # 2. Add or Remix Music onto video
    track_id = req.track_id or req.music_track
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id is required to add or remix music")

    music_file = None
    for t in mg.list_tracks():
        if t["id"] == track_id or t["filename"] == track_id:
            music_file = Path(t["file_path"])
            break
    if not music_file and Path(track_id).exists():
        music_file = Path(track_id)

    if not music_file or not music_file.exists():
        raise HTTPException(status_code=404, detail=f"Music track '{track_id}' not found.")

    try:
        c_dur = float(req.clip_duration) if req.clip_duration is not None and float(req.clip_duration) > 0.05 else None
        c_start = float(req.clip_start or 0.0)
        c_loop = bool(req.clip_loop) if req.clip_loop is not None else True

        remixed_path = mg.remix_video_music(
            video_path=Path(video_path),
            music_path=music_file,
            music_volume=mv,
            voice_volume=vv,
            ducking=req.ducking if req.ducking is not None else True,
            tempo_factor=req.tempo_factor or 1.0,
            bass_boost=req.bass_boost or 0.0,
            treble_boost=req.treble_boost or 0.0,
            reverb=req.reverb or 0.0,
            drums_volume=req.drums_volume or 1.0,
            melody_volume=req.melody_volume or 1.0,
            clip_start=c_start,
            clip_duration=c_dur,
            clip_loop=c_loop,
        )
        project["video_path"] = str(remixed_path)
        project["music_track"] = track_id
        project["music_volume"] = mv
        project["voice_volume"] = vv
        project["with_music"] = True
        project["audio_mode"] = "with_voice"
        project["clip_start"] = c_start
        project["clip_duration"] = c_dur
        project["clip_loop"] = c_loop
        StorageManager.save_project(project)

        clip_info = f" (Trimmed: {c_start:.1f}s - {c_start+c_dur:.1f}s | {'Looping 🔁' if c_loop else 'Once'})" if c_dur else ""
        return JSONResponse(content={
            "status": "success",
            "message": f"Successfully applied '{music_file.name}'{clip_info} (Voice: {int(vv*100)}% · Music: {int(mv*100)}%)!",
            "video_path": str(remixed_path),
            "project": project
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply music: {e}")

@app.post("/api/music/trim-clip")
def trim_clip_endpoint(req: TrimAudioClipRequest):
    """Trims a selected segment from a music track and registers it in the saved library."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    track_file = None
    for t in mg.list_tracks():
        if t["id"] == req.track_id or t["filename"] == req.track_id:
            track_file = Path(t["file_path"])
            break
    if not track_file and Path(req.track_id).exists():
        track_file = Path(req.track_id)
    if not track_file or not track_file.exists():
        raise HTTPException(status_code=404, detail=f"Source music track '{req.track_id}' not found.")

    try:
        new_track = mg.trim_and_save_clip(
            source_path=track_file,
            clip_start=float(req.clip_start or 0.0),
            clip_duration=float(req.clip_duration or 10.0),
            clip_name=req.clip_name
        )
        return JSONResponse(content={
            "status": "success",
            "message": f"Trimmed clip saved as '{new_track['name']}'!",
            "track": new_track
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trim audio clip: {e}")

@app.post("/api/projects/{project_id}/remove-music")
def remove_music_endpoint(project_id: str):
    """Convenience endpoint to remove all background music from a video."""
    return apply_music_endpoint(project_id, ApplyMusicRequest(remove_music=True))

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


