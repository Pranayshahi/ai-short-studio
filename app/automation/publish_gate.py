"""
Upload gate (channel rule: NOTHING is ever made public automatically).

Every upload is PRIVATE. You make videos public or schedule them yourself in YouTube Studio;
YouTubePublisher enforces this at the lowest level (YouTube only ever receives "private").

A video is uploaded without asking only if:
  1. Verify-video QA passed, and
  2. EVERY scene image is a verified real photo, a content-checked AI image, or your own upload,
  3. and the title/description/tags contain no prompt text.

AUTO_PUBLISH_MODE (.env):
  "review" (default) - gate passes: upload PRIVATE and ask you to approve the details.
  "auto"             - gate passes: upload PRIVATE without asking (still never public).
  "off"              - never upload automatically; always ask first.
Gate fails (any mode): nothing is uploaded; a review request lists the reasons.
Approve = keep/upload it PRIVATE with the final details ("approved_private"); then publish or
schedule it in YouTube Studio.
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


def _upload_private(project: Dict[str, Any]) -> Dict[str, Any]:
    from app.agents.youtube_publisher import YouTubePublisher
    res = YouTubePublisher.upload_short(
        video_path=project["video_path"],
        title=project.get("title") or project.get("topic"),
        description=project.get("description", ""),
        tags=project.get("tags", []),
        privacy_status="private",
        require_approval_before_live=True,
        project_dir=project.get("project_dir"),
        channel=project.get("channel"),
    )
    project["youtube"] = res
    project["status"] = "pending_approval"
    StorageManager.save_project(project)
    return res


def _studio_link(res: Dict[str, Any]) -> str:
    return res.get("studio_edit_url") or res.get("studio_channel_url") or res.get("url") or ""


def publish_or_request_approval(project: Dict[str, Any]) -> Dict[str, Any]:
    ok, reasons = evaluate(project)
    project["publish_gate"] = {"passed": ok, "reasons": reasons, "mode": MODE}
    StorageManager.save_project(project)
    pid = project["id"]

    if ok and MODE == "auto":
        res = _upload_private(project)
        notifier.send(_summary(project) + f"\n🔒 Uploaded as PRIVATE (passed every check).\n"
                      f"Make it public or schedule it in YouTube Studio: {_studio_link(res)}", title="Uploaded (private)")
        return {"action": "uploaded_private", "youtube": res}

    if ok and MODE == "review":
        res = _upload_private(project)
        notifier.send(_summary(project) + f"\n🔒 Uploaded as PRIVATE draft: {res.get('url')}\nPassed every check. "
                      "Approve to confirm the details; it stays private until you publish or schedule it in YouTube Studio.",
                      buttons=notifier.approval_buttons(pid), title="Ready for your review")
        return {"action": "uploaded_private_awaiting_approval", "youtube": res}

    project["status"] = "awaiting_review"
    StorageManager.save_project(project)
    why = "\n".join(f"• {r}" for r in reasons) or "• Automatic upload is turned off"
    notifier.send(_summary(project) + f"\n⚠️ Needs your review:\n{why}\nApprove uploads it as PRIVATE "
                  "(you publish or schedule it yourself in YouTube Studio).",
                  buttons=notifier.approval_buttons(pid), title="Review needed")
    return {"action": "awaiting_review", "reasons": reasons}


def handle_decision(action: str, project_id: str) -> str:
    """Approve/Reject from Telegram (or any caller). Approve never makes a video public."""
    project = StorageManager.get_project_by_id(project_id)
    if not project:
        return f"Project {project_id} not found."
    if action == "reject":
        project["status"] = "rejected"
        StorageManager.save_project(project)
        return f"Rejected: {project.get('title') or project_id}. Nothing was uploaded or changed on YouTube."
    if action == "approve":
        if project.get("status") in ("approved_private", "published"):
            return "Already approved. It is private on YouTube; publish or schedule it in YouTube Studio."
        from app.agents.youtube_publisher import YouTubePublisher
        yt = project.get("youtube") or {}
        if yt.get("video_id") and not str(yt.get("video_id")).startswith("staged_"):
            approve = getattr(YouTubePublisher, "approve_keep_private", None) or YouTubePublisher.approve_and_go_live
            res = approve(project=project, title=project.get("title"),
                          description=project.get("description"), tags=project.get("tags"),
                          channel=project.get("channel"))
        else:
            res = _upload_private(project)
        project["youtube"] = res
        project["status"] = "approved_private"
        StorageManager.save_project(project)
        return f"Approved and kept PRIVATE. Publish or schedule it in YouTube Studio: {_studio_link(res)}"
    return "Unknown action."
