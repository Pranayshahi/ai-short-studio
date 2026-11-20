"""Performance (YouTube stats) routes: summary and manual refresh."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.automation import analytics
from app.web_app import NO_CACHE_HEADERS

router = APIRouter()


@router.get("/api/analytics")
def analytics_summary():
    return JSONResponse(content=analytics.summary(), headers=NO_CACHE_HEADERS)


@router.post("/api/analytics/refresh")
def analytics_refresh():
    res = analytics.refresh()
    return JSONResponse(content={**res, **analytics.summary()}, headers=NO_CACHE_HEADERS)
