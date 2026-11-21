"""Car "New Launch": upload the photos and short clips of a new car before creating its video."""
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from agents import new_launch
from app.web_app import NO_CACHE_HEADERS

router = APIRouter()


@router.post("/api/new-launch/upload")
async def upload_new_launch_media(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one photo or clip")
    payload = []
    for f in files:
        data = await f.read()
        payload.append((f.filename or "file", data))
    upload_id, dest = new_launch.new_upload_dir()
    res = new_launch.accept_files(payload, dest)
    if not res["images"] and not res["clips"]:
        raise HTTPException(status_code=400, detail="Nothing usable was uploaded: " + "; ".join(res["rejected"])[:500])
    return JSONResponse(content=_describe(upload_id, res), headers=NO_CACHE_HEADERS)


def _describe(upload_id: str, res: dict) -> dict:
    return {
        "upload_id": upload_id,
        "images": [{"name": Path(p).name, "url": f"/api/new-launch/{upload_id}/file/images/{Path(p).name}"} for p in res["images"]],
        "clips": [{"name": Path(p).name, "seconds": round(new_launch.clip_seconds(p) or 0, 1),
                   "url": f"/api/new-launch/{upload_id}/file/clips/{Path(p).name}"} for p in res["clips"]],
        "rejected": res.get("rejected", []),
    }


@router.get("/api/new-launch/{upload_id}")
def get_new_launch_upload(upload_id: str):
    media = new_launch.resolve_upload(upload_id)
    if not media:
        raise HTTPException(status_code=404, detail="Upload not found")
    return JSONResponse(content=_describe(upload_id, media), headers=NO_CACHE_HEADERS)


@router.get("/api/new-launch/{upload_id}/file/{kind}/{name}")
def new_launch_file(upload_id: str, kind: str, name: str):
    media = new_launch.resolve_upload(upload_id)
    if not media or kind not in ("images", "clips"):
        raise HTTPException(status_code=404, detail="Not found")
    match = next((p for p in media[kind] if Path(p).name == name), None)  # only files of this upload
    if not match:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(match, headers=NO_CACHE_HEADERS)
