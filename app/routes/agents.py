"""Agent endpoints (topic-agent, content-analyser, image-generator, verify-video, music-agent)."""
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
    ContentAnalyserRequest,
    NO_CACHE_HEADERS,
    TopicAgentRequest,
)

router = APIRouter()


@router.get("/api/agents")
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


@router.post("/api/agents/topic-agent")
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


@router.post("/api/agents/content-analyser")
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


@router.post("/api/agents/image-generator/{project_id}")
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


@router.get("/api/agents/verify-video/{project_id}")
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

