"""Studio settings, YouTube secrets/auth and channel routes."""
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
    ChannelDefaultRequest,
    Image,
    NO_CACHE_HEADERS,
    StudioSettingsRequest,
    YouTubePublisher,
    clip_generator,
)

router = APIRouter()


@router.get("/api/settings")
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
            "youtube_authenticated": YouTubePublisher.is_authenticated(),  # default channel
            "youtube_channels": __import__("agents.youtube_channels", fromlist=["x"]).public_summary()["channels"],
            "hf_token_configured": bool(clip_generator.get_hf_token()),
        },
        headers=NO_CACHE_HEADERS,
    )


@router.post("/api/settings")
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


@router.post("/api/settings/weaponx-reference")
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


@router.post("/api/settings/youtube-secrets")
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


@router.get("/api/channels")
def list_channels():
    """Registered YouTube channels (no tokens): [{key, id, handle, title, authorized, is_default, studio_url}]."""
    from agents import youtube_channels as reg
    return JSONResponse(content=reg.public_summary(), headers=NO_CACHE_HEADERS)


@router.post("/api/channels/default")
def set_default_channel(req: ChannelDefaultRequest):
    from agents import youtube_channels as reg
    try:
        reg.set_default(req.channel)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown channel '{req.channel}'")
    return JSONResponse(content=reg.public_summary(), headers=NO_CACHE_HEADERS)


@router.post("/api/settings/youtube-auth")
def trigger_youtube_oauth(channel: Optional[str] = None):
    """Opens the Google sign-in for one channel (query ?channel=autoflashx; default = registry default)
    and saves that channel's own token file."""
    try:
        YouTubePublisher.get_authenticated_service(channel=channel)
        from agents import youtube_channels as reg
        return {"status": "success", "youtube_oauth_configured": True, "channel": reg.get(channel)["key"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

