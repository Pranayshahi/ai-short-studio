"""WeaponX chart preview routes: build a chart, drop rows, then generate the video with it."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.automation import chart_preview
from app.web_app import NO_CACHE_HEADERS

router = APIRouter()


class ChartPreviewRequest(BaseModel):
    topic: str
    preview_id: Optional[str] = None
    exclude: Optional[List[str]] = None
    ranked_list: Optional[str] = None  # the user's own numbered list (e.g. pasted from ChatGPT)


def _public(meta):
    rec = meta.get("record") or {}
    return {"preview_id": meta["id"], "topic": meta["topic"], "image_url": f"/api/chart-preview/{meta['id']}/image",
            "rows": [{"name": it.get("name"), "article": it.get("article"), "country": it.get("country"),
                      "year": it.get("year"), "bullets": it.get("bullets")} for it in rec.get("ranked_items") or []],
            "excluded": meta.get("excluded") or [], "from_list": bool(meta.get("ranked_list")),
            "skipped": rec.get("skipped") or []}


@router.post("/api/chart-preview")
def build_chart_preview(req: ChartPreviewRequest):
    topic = (req.topic or "").strip()
    if not topic and not (req.ranked_list or "").strip():
        raise HTTPException(status_code=400, detail="Enter a topic or paste a ranked list first.")
    try:
        meta = chart_preview.build(topic, preview_id=req.preview_id, exclude=req.exclude,
                                   ranked_list=(req.ranked_list or "").strip() or None)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Couldn't build a verified chart for '{topic}': {str(e)[:200]}. "
                                                    "Try a narrower topic or paste a numbered list of models.")
    return JSONResponse(content=_public(meta), headers=NO_CACHE_HEADERS)


@router.get("/api/chart-preview/{preview_id}/image")
def chart_preview_image(preview_id: str):
    meta = chart_preview.load(preview_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(meta["path"], media_type="image/png", headers=NO_CACHE_HEADERS)
