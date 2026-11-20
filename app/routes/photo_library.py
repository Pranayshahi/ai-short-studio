"""Verified photo library routes: browse the saved cutouts, reject a bad one, restore it."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from agents import photo_library
from app.web_app import NO_CACHE_HEADERS  # noqa: F401

router = APIRouter()


@router.get("/api/photo-library")
def list_photo_library():
    items = photo_library.listing()
    for it in items:
        it["image_url"] = f"/api/photo-library/{it['key']}/image"
    return JSONResponse(content={"items": items, "approved": sum(1 for i in items if i["status"] == "approved")},
                        headers=NO_CACHE_HEADERS)


@router.get("/api/photo-library/{key}/image")
def photo_library_image(key: str):
    path = photo_library.image_path(key)
    if not path:
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(str(path), media_type="image/png", headers=NO_CACHE_HEADERS)


@router.post("/api/photo-library/{key}/reject")
def reject_photo(key: str):
    items = {i["key"]: i for i in photo_library.listing()}
    if key not in items:
        raise HTTPException(status_code=404, detail="Photo not found")
    photo_library.reject(items[key]["title"])
    return {"status": "rejected", "key": key, "message": "Won't be used again; the next chart finds another photo."}


@router.post("/api/photo-library/{key}/restore")
def restore_photo(key: str):
    items = {i["key"]: i for i in photo_library.listing()}
    if key not in items or not photo_library.restore(items[key]["title"]):
        raise HTTPException(status_code=404, detail="Photo not found")
    return {"status": "approved", "key": key}
