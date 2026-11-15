"""
Phone notifications.

- Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID): messages AND Approve/Reject buttons.
  Button presses are collected by polling getUpdates (works behind NAT, no public URL needed).
  Only presses from the configured chat are accepted.
- Discord (DISCORD_WEBHOOK_URL): messages only. Incoming webhooks cannot receive button
  clicks, so approvals from Discord happen in the dashboard.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable, Dict, List, Optional

import config
from app.automation import state


def _tg_creds():
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = getattr(config, "TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_CHAT_ID", "")
    return token.strip(), str(chat).strip()


def _discord_url() -> str:
    return (getattr(config, "DISCORD_WEBHOOK_URL", "") or os.getenv("DISCORD_WEBHOOK_URL", "")).strip()


def is_configured() -> Dict[str, bool]:
    token, chat = _tg_creds()
    return {"telegram": bool(token and chat), "discord": _discord_url().startswith("http")}


def _post_json(url: str, payload: Dict[str, Any], timeout: int = 10) -> Dict[str, Any]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "AIShortsStudio/2.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8") or "{}"
        try:
            return json.loads(body)
        except ValueError:
            return {"ok": True, "status": resp.status}


def send(text: str, buttons: Optional[List[List[Dict[str, str]]]] = None, title: Optional[str] = None) -> Dict[str, Any]:
    """Send a message to every configured channel. buttons = Telegram inline keyboard rows."""
    results: Dict[str, Any] = {"telegram": None, "discord": None}
    token, chat = _tg_creds()
    if token and chat:
        try:
            payload: Dict[str, Any] = {"chat_id": chat, "text": text, "disable_web_page_preview": True}
            if buttons:
                payload["reply_markup"] = {"inline_keyboard": buttons}
            r = _post_json(f"https://api.telegram.org/bot{token}/sendMessage", payload)
            results["telegram"] = "sent" if r.get("ok") else f"error: {r}"
        except Exception as e:
            results["telegram"] = f"failed: {e}"
    url = _discord_url()
    if url.startswith("http"):
        try:
            content = (f"**{title}**\n" if title else "") + text
            if buttons:
                content += "\n_Approve or reject this in the AI Shorts Studio dashboard (Discord can't receive button clicks)._"
            _post_json(url, {"username": "AI Shorts Studio", "content": content[:1990]})
            results["discord"] = "sent"
        except Exception as e:
            results["discord"] = f"failed: {e}"
    if not results["telegram"] and not results["discord"]:
        print(f"[Notifier] (no channel configured) {title + ': ' if title else ''}{text[:300]}")
    return results


def approval_buttons(project_id: str) -> List[List[Dict[str, str]]]:
    return [[
        {"text": "✅ Approve (stays private)", "callback_data": f"approve:{project_id}"[:64]},
        {"text": "❌ Reject", "callback_data": f"reject:{project_id}"[:64]},
    ]]


def poll_decisions(handler: Callable[[str, str], str]) -> int:
    """
    Fetch new Telegram button presses and pass (action, project_id) to handler, which returns
    a short status text shown back to the user. Returns the number of handled presses.
    """
    token, chat = _tg_creds()
    if not (token and chat):
        return 0
    offset = state.read("telegram", {}).get("offset", 0)
    try:
        r = _post_json(
            f"https://api.telegram.org/bot{token}/getUpdates",
            {"offset": offset, "timeout": 0, "allowed_updates": ["callback_query"]},
            timeout=15,
        )
    except Exception as e:
        print(f"[Notifier] Telegram poll failed: {e}")
        return 0
    handled = 0
    last_id = offset - 1
    for upd in r.get("result", []):
        last_id = max(last_id, upd.get("update_id", 0))
        cq = upd.get("callback_query")
        if not cq:
            continue
        from_chat = str(((cq.get("message") or {}).get("chat") or {}).get("id", ""))
        reply = "Ignored: not from the configured chat."
        if from_chat == chat:
            data = cq.get("data", "")
            action, _, project_id = data.partition(":")
            if action in ("approve", "reject") and project_id:
                try:
                    reply = handler(action, project_id)
                except Exception as e:
                    reply = f"Failed: {e}"
                handled += 1
        try:
            _post_json(f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                       {"callback_query_id": cq.get("id"), "text": reply[:190]})
            msg = cq.get("message") or {}
            if from_chat == chat and msg.get("message_id"):
                _post_json(f"https://api.telegram.org/bot{token}/editMessageReplyMarkup",
                           {"chat_id": chat, "message_id": msg["message_id"], "reply_markup": {"inline_keyboard": []}})
                send(reply)
        except Exception:
            pass
    if last_id >= offset:
        state.update("telegram", {}, lambda s: {**s, "offset": last_id + 1})
    return handled
