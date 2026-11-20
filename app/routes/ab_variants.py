"""A/B test kit routes: title + thumbnail variants for YouTube Studio's Test & compare."""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.utils.storage import StorageManager
from app.web_app import NO_CACHE_HEADERS

router = APIRouter()


@router.get("/api/projects/{project_id}/ab-variants")
def ab_variants(project_id: str):
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    from app.agents import ab_variants as ab
    kit = ab.build(project)
    return JSONResponse(content={
        "titles": kit["titles"],
        "thumbnails": [f"/api/projects/{project_id}/ab-variants/thumb/{i}" for i in range(1, len(kit["thumbnails"]) + 1)],
        "how_to": "YouTube Studio > the video > Test & compare: add these titles/thumbnails; YouTube picks the winner.",
    }, headers=NO_CACHE_HEADERS)


@router.get("/api/projects/{project_id}/ab-variants/thumb/{n}")
def ab_variant_thumb(project_id: str, n: int):
    project = StorageManager.get_project_by_id(project_id)
    if not project or not re.fullmatch(r"[1-3]", str(n)):
        raise HTTPException(status_code=404, detail="Not found")
    path = Path(project["project_dir"]) / "ab_variants" / f"thumb_{n}.jpg"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Open the A/B kit first")
    return FileResponse(str(path), media_type="image/jpeg", filename=f"{project_id}_thumb_{n}.jpg", headers=NO_CACHE_HEADERS)
