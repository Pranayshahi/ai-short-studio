"""
YouTube channel registry: one OAuth token per channel, so the app can publish to several
channels (WeaponXLabs for defense shorts, AutoFlashX for car edits, ...).

credentials/channels.json:
  {"default": "weaponxlabs",
   "channels": {"weaponxlabs": {"id": "UC...", "handle": "@weaponxlabs", "title": "WeaponXLabs",
                                "token_file": "youtube_tokens.json"},
                "autoflashx":  {"id": "UC...", "handle": "@autoflashx", "title": "AutoFlashX",
                                "token_file": "youtube_tokens_autoflashx.json"}}}

The pre-existing single-channel setup (youtube_tokens.json + YOUTUBE_TARGET_CHANNEL_ID) is
migrated into this file automatically the first time the registry is read.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

import config

REGISTRY_FILE = config.CREDENTIALS_DIR / "channels.json"

# Channels the user has told us about; a sign-in fills in / confirms the real id and title.
KNOWN: Dict[str, Dict[str, str]] = {
    "weaponxlabs": {"id": "UC4KV67NYzLi8JlrfB9J4hGg", "handle": "@weaponxlabs", "title": "WeaponXLabs",
                    "token_file": "youtube_tokens.json"},
    "autoflashx": {"id": "UCuJ9LcSqliLH0VEJ9lWZsrQ", "handle": "@autoflashx", "title": "AutoFlashX",
                   "token_file": "youtube_tokens_autoflashx.json"},
}


def key_for(value: str) -> str:
    """Normalises a handle / title / key: '@AutoFlashX' -> 'autoflashx'."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower().lstrip("@"))


def _read() -> Dict[str, Any]:
    if REGISTRY_FILE.exists():
        try:
            data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "channels" in data:
                return data
        except Exception:
            pass
    # Migration from the single-channel layout
    data = {"default": "weaponxlabs", "channels": {"weaponxlabs": dict(KNOWN["weaponxlabs"])}}
    legacy_id = getattr(config, "YOUTUBE_TARGET_CHANNEL_ID", "")
    if legacy_id and legacy_id != KNOWN["weaponxlabs"]["id"]:
        data["channels"]["weaponxlabs"]["id"] = legacy_id
    _write(data)
    return data


def _write(data: Dict[str, Any]) -> None:
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def all_channels() -> Dict[str, Dict[str, Any]]:
    data = _read()
    out = {}
    for key, ch in data["channels"].items():
        token = config.CREDENTIALS_DIR / ch.get("token_file", f"youtube_tokens_{key}.json")
        out[key] = {**ch, "key": key, "token_path": token, "authorized": token.exists(),
                    "is_default": key == data.get("default")}
    return out


def default_key() -> str:
    return _read().get("default", "weaponxlabs")


def get(key: Optional[str] = None) -> Dict[str, Any]:
    """Channel record for a key (or handle/title); falls back to the default channel.
    Unknown keys that match KNOWN are registered on the fly (not yet authorized)."""
    chans = all_channels()
    k = key_for(key) if key else default_key()
    if k in chans:
        return chans[k]
    for ck, ch in chans.items():  # allow matching by handle, title or channel id
        if k in (key_for(ch.get("handle", "")), key_for(ch.get("title", "")), key_for(ch.get("id", ""))):
            return ch
    if k in KNOWN:
        register(k, **KNOWN[k])
        return all_channels()[k]
    raise KeyError(f"Unknown YouTube channel '{key}'. Known: {sorted(chans)}")


def register(key: str, id: str = "", handle: str = "", title: str = "", token_file: Optional[str] = None,
             make_default: bool = False) -> Dict[str, Any]:
    key = key_for(key)
    data = _read()
    ch = data["channels"].get(key, {})
    ch.update({"id": id or ch.get("id", ""), "handle": handle or ch.get("handle", f"@{key}"),
               "title": title or ch.get("title", key),
               "token_file": token_file or ch.get("token_file") or f"youtube_tokens_{key}.json"})
    data["channels"][key] = ch
    if make_default or not data.get("default"):
        data["default"] = key
    _write(data)
    return all_channels()[key]


def set_default(key: str) -> None:
    data = _read()
    key = key_for(key)
    if key not in data["channels"]:
        raise KeyError(key)
    data["default"] = key
    _write(data)


def studio_url(channel: Dict[str, Any]) -> str:
    return f"https://studio.youtube.com/channel/{channel['id']}"


def public_summary() -> Dict[str, Any]:
    """Safe to show in the dashboard (no tokens)."""
    return {"default": default_key(),
            "channels": [{"key": k, "id": c["id"], "handle": c["handle"], "title": c["title"],
                          "authorized": c["authorized"], "is_default": c["is_default"],
                          "studio_url": studio_url(c)} for k, c in all_channels().items()]}
