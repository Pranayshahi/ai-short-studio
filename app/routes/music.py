"""Music routes: library, AI/ACE-Step generation, trims, previews, apply/remove music on a project."""
import os
import re
import io
import json
import time
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Response, Request
from fastapi.responses import FileResponse, JSONResponse

import config
from app.utils.storage import StorageManager

from app.web_app import (  # noqa: F401  shared helpers, models and singletons
    AIMusicGenerateRequest,
    ApplyMusicRequest,
    CustomMusicGenerateRequest,
    DeepVerifyMusicRequest,
    MusicOnlyClipsRequest,
    NO_CACHE_HEADERS,
    SYNTH_FALLBACK_WARNING,
    SaveMusicToLibraryRequest,
    TrimAudioClipRequest,
    _mark_synth_fallback,
    logger,
)

router = APIRouter()


@router.get("/api/music/tracks")
def get_music_tracks():
    """Lists available AI-generated and saved library music tracks."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    return JSONResponse(content={
        "tracks": mg.list_tracks(),
        "styles": AIMusicGenerator.STYLES
    }, headers=NO_CACHE_HEADERS)


@router.post("/api/music/generate-ai")
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


@router.get("/api/music/meta")
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


@router.post("/api/music/agent/research")
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


@router.post("/api/music/agent/generate")
@router.post("/api/agents/music-agent")
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


@router.post("/api/music/agent/deep-verify")
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


@router.post("/api/music/generate-custom")
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


@router.get("/api/music/acestep/status")
def acestep_status():
    """Reports whether the local ACE-Step 1.5 API server is reachable."""
    from agents.acestep_music_agent import ACEStepMusicAgent
    a = ACEStepMusicAgent()
    return JSONResponse(content={"available": a.is_available(), "url": a.base_url}, headers=NO_CACHE_HEADERS)


@router.post("/api/music/acestep/generate")
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


@router.get("/api/music/library")
def get_saved_music_library():
    """Returns list of user's saved library music tracks."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    return JSONResponse(content={"library": mg.list_saved_library()}, headers=NO_CACHE_HEADERS)


@router.get("/api/music/recent-generated")
def get_recent_generated_music():
    """Returns recently synthesized AI music tracks from assets/audio/ai_generated."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    return JSONResponse(content={"recent": mg.list_recent_ai_tracks(limit=12)}, headers=NO_CACHE_HEADERS)


@router.post("/api/music/library/save")
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


@router.delete("/api/music/library/{track_id}")
def delete_music_from_library_endpoint(track_id: str):
    """Deletes a saved music track from user's library."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    deleted = mg.delete_from_library(track_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Track not found in library")
    return JSONResponse(content={"status": "success", "message": "Deleted from library"}, headers=NO_CACHE_HEADERS)


@router.post("/api/music/library/{track_id}/set-default")
def set_default_music_endpoint(track_id: str):
    """Sets a saved track as the default music for future video creations."""
    from agents.music_generator import AIMusicGenerator
    mg = AIMusicGenerator()
    ok = mg.set_default_library_track(track_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Track not found in library")
    return JSONResponse(content={"status": "success", "message": "Set as default music for next video creations"}, headers=NO_CACHE_HEADERS)


@router.get("/api/music/preview/{filename}")
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


@router.post("/api/projects/{project_id}/apply-music")
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
    # Music-only projects: remix rebuilds audio from voiceover.mp3, which would bring the removed voice back
    voice_off = project.get("with_voice") is False or project.get("audio_mode") in ("without_voice", "mute")
    if voice_off:
        vv = 0.0

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
            project["music_path"] = None
            project["music_remix"] = None
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
        # Re-render reads music_path: without it every re-render fell back to the default track
        project["music_path"] = str(music_file)
        # ...and re-applies the same mix (trim/loop/tempo/EQ), which the composer alone can't do
        project["music_remix"] = {
            "music_volume": mv, "voice_volume": vv,
            "ducking": req.ducking if req.ducking is not None else True,
            "tempo_factor": req.tempo_factor or 1.0, "bass_boost": req.bass_boost or 0.0,
            "treble_boost": req.treble_boost or 0.0, "reverb": req.reverb or 0.0,
            "drums_volume": req.drums_volume or 1.0, "melody_volume": req.melody_volume or 1.0,
            "clip_start": c_start, "clip_duration": c_dur, "clip_loop": c_loop,
        }
        project["music_volume"] = mv
        project["voice_volume"] = vv
        project["with_music"] = True
        project["audio_mode"] = "without_voice" if voice_off else "with_voice"
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


@router.post("/api/music/trim-clip")
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


@router.post("/api/projects/{project_id}/remove-music")
def remove_music_endpoint(project_id: str):
    """Convenience endpoint to remove all background music from a video."""
    return apply_music_endpoint(project_id, ApplyMusicRequest(remove_music=True))


@router.get("/api/music/options")
def get_music_only_options_endpoint():
    """Returns the Music-Only relaxation & meditation options (Sleep Music, Flute Meditation, Deep Relaxation, Binaural Beats, Raga Therapy)."""
    from agents.music_agent import MusicAgent
    return JSONResponse(content={
        "options": MusicAgent.MUSIC_ONLY_OPTIONS,
        "categories": MusicAgent.CATEGORIES
    }, headers=NO_CACHE_HEADERS)


@router.post("/api/music/create-clips")
def create_music_only_clips_endpoint(req: MusicOnlyClipsRequest):
    """Generates Music-Only relaxation track and creates synchronized 9:16 vertical visual video clips + full Short."""
    from agents.music_agent import MusicAgent
    agent = MusicAgent()
    try:
        res = agent.create_music_only_clips(
            category=req.category or "Sleep Music",
            mood=req.mood or "Relaxing",
            vocals=req.vocals or "Instrumental",
            duration=req.duration or 30.0,
            clip_count=req.clip_count or 3,
            prompt=req.prompt,
            track_id=req.track_id,
            clip_start=req.clip_start or 0.0,
            clip_duration=req.clip_duration,
            clip_loop=req.clip_loop if req.clip_loop is not None else True,
        )
        return JSONResponse(content=res, headers=NO_CACHE_HEADERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Music-only clips creation failed: {e}")


@router.get("/api/music/clip-video/{project_id}/{filename}")
def stream_music_clip_video(project_id: str, filename: str):
    """Streams an individual generated visual clip MP4 from a Music-Only project."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    p_dir = Path(project.get("project_dir", ""))
    safe_name = Path(filename).name
    cand = p_dir / "clips" / safe_name
    if not cand.exists():
        cand = p_dir / safe_name
    if not cand.exists():
        raise HTTPException(status_code=404, detail="Clip video file not found")
    return FileResponse(str(cand), media_type="video/mp4", headers=NO_CACHE_HEADERS)

