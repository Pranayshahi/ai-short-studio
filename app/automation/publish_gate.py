"""
Smart auto-publishing.

A video may be published without a human only if:
  1. Verify-video QA passed, and
  2. EVERY scene image is either a verified real photo (web source) or an AI image whose
     content was actually checked (content_verified True). Unverified AI images block it.

AUTO_PUBLISH_MODE (.env):
  "review" (default) - gate passes: upload PRIVATE and ask for approval (Approve = go live).
  "auto"             - gate passes: upload and go PUBLIC immediately.
  "off"              - never upload automatically; always ask.
Gate fails (any mode): nothing is uploaded; an approval request lists the reasons.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from app.automation import notifier
from app.utils.storage import StorageManager

MODE = os.getenv("AUTO_PUBLISH_MODE", "review").strip().lower()


def evaluate(project: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    qa = project.get("qa_report") or {}
    if not qa.get("qa_passed"):
        reasons.append(f"QA did not pass (score {qa.get('overall_score')}%, status {qa.get('status')})")
    records = project.get("visual_records") or []
    if not records:
        reasons.append("No scene image records")
    # A scene whose image the user uploaded/replaced themselves is user-approved, whatever the
    # (possibly stale) generation record says
    user_scenes = {sc.get("scene_number") or i + 1 for i, sc in enumerate(project.get("scenes") or [])
                   if sc.get("visual_source") in ("manual_upload", "user_upload")}
    for v in records:
        n = v.get("scene_number")
        src = v.get("source")
        if n in user_scenes:
            continue
        if src == "web_free":
            # Real (Wikimedia) photo matched to the subject by its metadata = verified real photo.
            # Block only if a content check actually RAN and rejected it (passed is False);
            # passed None just means no checker was installed.
            check = (v.get("visual_quality") or {}).get("content_check") or {}
            if check.get("passed") is False:
                reasons.append(f"Scene {n}: real photo failed the content check ({check.get('reason', '')[:80]})")
        elif src in ("ai_generated",):
            if v.get("content_verified") is not True:
                reasons.append(f"Scene {n}: AI image not content-verified")
        elif src in ("weaponx_lab_poster",):
            pass  # rendered locally from verified data rows
        else:
            reasons.append(f"Scene {n}: unverified image source '{src}'")
    if not project.get("video_path"):
        reasons.append("No rendered video")
    try:
        from agents.youtube_metadata import leaks
        reasons += [f"Metadata: {m}" for m in leaks(project.get("title") or "", project.get("description") or "",
                                                     project.get("tags") or [], project.get("topic") or "")]
    except Exception as e:
        reasons.append(f"Metadata check failed: {e}")
    return (not reasons), reasons


def _summary(project: Dict[str, Any]) -> str:
    qa = project.get("qa_report") or {}
    return (f"🎬 {project.get('title') or project.get('topic')}\n"
            f"Topic: {project.get('topic')}\n"
            f"Length: {round(float(project.get('duration') or 0), 1)}s · QA {qa.get('overall_score')}% ({qa.get('status')})\n"
            f"Project: {project.get('id')}")


def _upload(project: Dict[str, Any], go_public: bool) -> Dict[str, Any]:
    from app.agents.youtube_publisher import YouTubePublisher
    res = YouTubePublisher.upload_short(
        video_path=project["video_path"],
        title=project.get("title") or project.get("topic"),
        description=project.get("description", ""),
        tags=project.get("tags", []),
        privacy_status="public" if go_public else "private",
        require_approval_before_live=not go_public,
        project_dir=project.get("project_dir"),
    )
    project["youtube"] = res
    project["status"] = "published" if res.get("approval_status") == "approved_live" else "pending_approval"
    StorageManager.save_project(project)
    return res


def publish_or_request_approval(project: Dict[str, Any]) -> Dict[str, Any]:
    ok, reasons = evaluate(project)
    project["publish_gate"] = {"passed": ok, "reasons": reasons, "mode": MODE}
    StorageManager.save_project(project)
    pid = project["id"]

    if ok and MODE == "auto":
        res = _upload(project, go_public=True)
        notifier.send(_summary(project) + f"\n✅ Published automatically: {res.get('url')}", title="Short published")
        return {"action": "published", "youtube": res}

    if ok and MODE == "review":
        res = _upload(project, go_public=False)
        notifier.send(_summary(project) + f"\n🔒 Uploaded as PRIVATE draft: {res.get('url')}\nPassed every check. Approve to make it public.",
                      buttons=notifier.approval_buttons(pid), title="Ready to publish")
        return {"action": "uploaded_private_awaiting_approval", "youtube": res}

    project["status"] = "awaiting_review"
    StorageManager.save_project(project)
    why = "\n".join(f"• {r}" for r in reasons) or "• Auto-publish is turned off"
    notifier.send(_summary(project) + f"\n⚠️ Needs your review before publishing:\n{why}\nApprove uploads it and makes it public.",
                  buttons=notifier.approval_buttons(pid), title="Review needed")
    return {"action": "awaiting_review", "reasons": reasons}


def handle_decision(action: str, project_id: str) -> str:
    """Approve/Reject from Telegram (or any caller). Returns a short human-readable result."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        return f"Project {project_id} not found."
    if action == "reject":
        project["status"] = "rejected"
        StorageManager.save_project(project)
        return f"Rejected: {project.get('title') or project_id}. Nothing was published."
    if action == "approve":
        if project.get("status") == "published":
            return "Already published."
        from app.agents.youtube_publisher import YouTubePublisher
        yt = project.get("youtube") or {}
        if yt.get("video_id") and not str(yt.get("video_id")).startswith("staged_"):
            res = YouTubePublisher.approve_and_go_live(project=project, title=project.get("title"),
                                                       description=project.get("description"), tags=project.get("tags"))
            project["youtube"] = res
            project["status"] = "published"
            StorageManager.save_project(project)
        else:
            res = _upload(project, go_public=True)
        return f"Published: {res.get('url')}"
    return "Unknown action."
