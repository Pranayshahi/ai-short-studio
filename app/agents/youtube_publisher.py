import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    HAS_GOOGLE_API = True
except ImportError:
    HAS_GOOGLE_API = False
import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class YouTubePublisher:
    """Multi-channel publisher. Every method takes an optional `channel` key (registry in
    agents/youtube_channels.py); None = the registry's default channel. One OAuth token per channel.
    Channel rule (user, 2026-11-15): uploads are ALWAYS private, on every channel."""

    # Legacy constants (default channel) kept for old callers; new code uses cls.channel_info()
    TARGET_CHANNEL_ID = getattr(config, "YOUTUBE_TARGET_CHANNEL_ID", "UC4KV67NYzLi8JlrfB9J4hGg")
    STUDIO_CHANNEL_URL = f"https://studio.youtube.com/channel/{TARGET_CHANNEL_ID}"
    STUDIO_UPLOAD_URL = f"https://studio.youtube.com/channel/{TARGET_CHANNEL_ID}/videos/upload?d=ud"
    CHANNEL_HANDLE = getattr(config, "YOUTUBE_CHANNEL_HANDLE", "@WeaponXLabs")

    @staticmethod
    def channel_info(channel: Optional[str] = None) -> Dict[str, Any]:
        """Resolved channel record: key, id, handle, title, token_path, studio_url, upload_url."""
        from agents import youtube_channels as reg
        ch = reg.get(channel)
        studio = reg.studio_url(ch)
        return {**ch, "studio_url": studio, "upload_url": f"{studio}/videos/upload?d=ud"}

    @classmethod
    def channel_of(cls, project: Optional[Dict[str, Any]]) -> Optional[str]:
        """The channel key a project belongs to (None -> default channel)."""
        return (project or {}).get("channel") or None

    @classmethod
    def auto_discover_client_secrets(cls) -> bool:
        """Automatically looks for downloaded client_secret*.json in ~/Downloads, ~/Desktop, or workspace."""
        secrets_path = config.YOUTUBE_CLIENT_SECRETS_FILE
        if secrets_path.exists():
            return True
        search_dirs = [
            Path.home() / "Downloads",
            Path.home() / "Desktop",
            config.BASE_DIR,
            config.BASE_DIR.parent,
        ]
        for sdir in search_dirs:
            try:
                if not sdir.exists():
                    continue
                matches = sorted(
                    list(sdir.glob("client_secret*.json")) + list(sdir.glob("*client_secrets*.json")),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                for m in matches:
                    raw = json.loads(m.read_text(encoding="utf-8"))
                    if "installed" in raw or "web" in raw:
                        secrets_path.parent.mkdir(parents=True, exist_ok=True)
                        secrets_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
                        print(f"[YouTubePublisher] ✓ Auto-imported client_secrets.json from {m}")
                        return True
            except Exception:
                continue
        return False

    @classmethod
    def is_configured(cls) -> bool:
        """Checks if YouTube OAuth client_secrets.json is present."""
        if config.YOUTUBE_CLIENT_SECRETS_FILE.exists():
            return True
        return cls.auto_discover_client_secrets()

    @classmethod
    def is_authenticated(cls, channel: Optional[str] = None) -> bool:
        """Checks if valid, active YouTube OAuth tokens exist for the channel."""
        tokens_path = cls.channel_info(channel)["token_path"]
        if not tokens_path.exists():
            return False
        try:
            creds = Credentials.from_authorized_user_file(str(tokens_path), SCOPES)
            return bool(creds and (creds.valid or creds.refresh_token))
        except Exception:
            return False

    @classmethod
    def get_authenticated_service(cls, channel: Optional[str] = None, interactive: bool = True):
        """Authorized YouTube Data API v3 service for the channel (one token file per channel).
        interactive=False never opens a browser: it raises if the channel isn't authorized."""
        creds = None
        ch = cls.channel_info(channel)
        tokens_path = ch["token_path"]
        secrets_path = config.YOUTUBE_CLIENT_SECRETS_FILE
        cls.auto_discover_client_secrets()

        if tokens_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(tokens_path), SCOPES)
            except Exception as e:
                print(f"[YouTubePublisher] Error reading tokens: {e}")
                creds = None

        if not creds or not creds.valid:
            refreshed = False
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(tokens_path, "w") as token:
                        token.write(creds.to_json())
                    refreshed = True
                    print("[YouTubePublisher] ✓ Successfully refreshed expired YouTube OAuth token.")
                except Exception as refresh_err:
                    print(f"[YouTubePublisher] Refresh token failed or expired ({refresh_err}). Removing stale tokens.")
                    if tokens_path.exists():
                        try:
                            tokens_path.unlink()
                        except Exception:
                            pass
                    creds = None

            if not refreshed:
                if not secrets_path.exists():
                    raise FileNotFoundError(
                        f"YouTube client secrets not found at {secrets_path}. Please place client_secrets.json in credentials/."
                    )
                if not interactive:
                    raise RuntimeError(
                        f"YouTube channel '{ch['key']}' ({ch.get('handle')}) is not authorized. "
                        f"Run: python main.py --auth-youtube --channel {ch['key']}"
                    )
                print(f"[YouTubePublisher] Starting OAuth browser sign-in for channel '{ch['key']}' ({ch.get('handle')})...")
                print("[YouTubePublisher] In the Google window, choose the account AND the channel that matches.")
                flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
                creds = flow.run_local_server(port=0)
                # Verify the signed-in channel is the one requested before saving its token
                probe = build("youtube", "v3", credentials=creds)
                mine = probe.channels().list(part="id,snippet", mine=True).execute().get("items", [])
                got_id = mine[0]["id"] if mine else ""
                got_title = mine[0]["snippet"].get("title", "") if mine else ""
                if ch.get("id") and got_id and got_id != ch["id"]:
                    raise RuntimeError(
                        f"You signed in as '{got_title}' ({got_id}), but channel '{ch['key']}' is {ch.get('handle')} "
                        f"({ch['id']}). Token NOT saved. Run the command again and pick {ch.get('handle')} in the Google window."
                    )
                tokens_path.parent.mkdir(parents=True, exist_ok=True)
                with open(tokens_path, "w") as token:
                    token.write(creds.to_json())
                if got_id:
                    from agents import youtube_channels as reg
                    reg.register(ch["key"], id=got_id, title=got_title or ch.get("title", ""))
                print(f"[YouTubePublisher] ✓ Saved YouTube tokens for '{got_title or ch['key']}' to {tokens_path}")

        return build("youtube", "v3", credentials=creds)

    @classmethod
    def build_complete_fields(
        cls,
        title: str,
        description: str,
        tags: List[str],
        category_id: str = "28",
        made_for_kids: bool = False,
        language: str = "en",
        topic: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ensures every YouTube Studio field is populated for channel UC4KV67NYzLi8JlrfB9J4hGg (@WeaponXLabs).
        """
        try:
            from agents.youtube_metadata import clean_metadata
            title, description, tags = clean_metadata(title or "", description or "", list(tags or []), topic or title or "")
        except Exception as e:
            print(f"[YouTubePublisher] metadata guard skipped: {e}")
        ch = cls.channel_info(channel)
        clean_title = (title or f"{ch.get('title') or 'Shorts'} #Shorts").strip()
        if "#shorts" not in clean_title.lower():
            if len(clean_title) <= 91:
                clean_title = f"{clean_title} #Shorts"
            else:
                clean_title = f"{clean_title[:91].rstrip()} #Shorts"
        clean_title = clean_title[:100]

        clean_desc = (description or "").strip()
        required_hashtags = ["#Shorts", "#WeaponXLabs", "#MilitaryTech", "#Defense"]
        for ht in required_hashtags:
            if ht.lower() not in clean_desc.lower():
                clean_desc = f"{clean_desc}\n{ht}".strip()
        if ch.get("handle") and ch["handle"].lower() not in clean_desc.lower():
            clean_desc += f"\n\nOfficial Channel: {ch['handle']} (https://www.youtube.com/{ch['handle']})"

        raw_tags = list(tags or []) + [
            "WeaponXLabs",
            "weaponx lab",
            "shorts",
            "youtube shorts",
            "military tech",
            "defense technology",
            "weapons breakdown",
        ]
        deduped_tags: List[str] = []
        total_tag_chars = 0
        for t in raw_tags:
            t_clean = str(t).strip().lstrip("#")
            if not t_clean or t_clean.lower() in [x.lower() for x in deduped_tags]:
                continue
            if total_tag_chars + len(t_clean) > 460:
                break
            deduped_tags.append(t_clean)
            total_tag_chars += len(t_clean) + 1

        return {
            "channel_key": ch["key"],
            "channel_id": ch["id"],
            "channel_handle": ch.get("handle"),
            "studio_channel_url": ch["studio_url"],
            "title": clean_title,
            "description": clean_desc,
            "tags": deduped_tags,
            "categoryId": str(category_id or "28"),
            "categoryName": "Science & Technology" if str(category_id or "28") == "28" else "Education",
            "defaultLanguage": language,
            "defaultAudioLanguage": language,
            "selfDeclaredMadeForKids": bool(made_for_kids),
            "containsSyntheticMedia": True,
            "license": "youtube",
            "embeddable": True,
            "publicStatsViewable": True,
        }

    @classmethod
    def upload_short(
        cls,
        video_path: str,
        title: str,
        description: str,
        tags: list,
        privacy_status: Optional[str] = None,
        require_approval_before_live: bool = True,
        project_dir: Optional[str] = None,
        category_id: str = "28",
        made_for_kids: bool = False,
        channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Step 1 of the 2-Step Approval Workflow:
        Uploads the Short to the given channel (default: registry default), fills all YouTube Studio
        fields (Title, Description, Tags, Category, Audience=Not Made for Kids, Language,
        Synthetic Media Disclosure), and saves it as 'private' (Draft / Pending Approval)
        so it ONLY goes live after the user clicks 'Approve & Go Live'.
        """
        ch = cls.channel_info(channel)
        filled = cls.build_complete_fields(
            title=title,
            description=description,
            tags=tags,
            category_id=category_id,
            made_for_kids=made_for_kids,
            channel=ch["key"],
        )

        # Channel rule (user, 2026-11-15): the app NEVER makes a video public. Every upload is private;
        # the owner makes it public or schedules it in YouTube Studio.
        if privacy_status and privacy_status != "private":
            print(f"[YouTubePublisher] Requested privacy '{privacy_status}' ignored: uploads are always private.")
        effective_privacy = "private"

        body = {
            "snippet": {
                "title": filled["title"],
                "description": filled["description"],
                "tags": filled["tags"],
                "categoryId": filled["categoryId"],
                "defaultLanguage": filled["defaultLanguage"],
                "defaultAudioLanguage": filled["defaultAudioLanguage"],
            },
            "status": {
                "privacyStatus": effective_privacy,
                "selfDeclaredMadeForKids": filled["selfDeclaredMadeForKids"],
                "embeddable": filled["embeddable"],
                "publicStatsViewable": filled["publicStatsViewable"],
                "license": filled["license"],
            },
        }

        # Save filled YouTube Studio package on disk in project folder
        if project_dir and Path(project_dir).exists():
            draft_file = Path(project_dir) / "youtube_studio_draft.json"
            try:
                draft_file.write_text(
                    json.dumps(
                        {
                            "target_channel_key": ch["key"],
                            "target_channel_id": ch["id"],
                            "studio_channel_url": ch["studio_url"],
                            "video_path": str(video_path),
                            "filled_fields": filled,
                            "api_body": body,
                            "saved_at": datetime.now().isoformat(),
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass

        if ch["token_path"].exists() and HAS_GOOGLE_API:
            try:
                youtube = cls.get_authenticated_service(channel=ch["key"], interactive=False)

                # The token must belong to the channel we are publishing to: never upload elsewhere
                auth_channel_id = ch["id"]
                auth_channel_title = ch.get("handle") or ch.get("title")
                try:
                    ch_resp = youtube.channels().list(part="id,snippet", mine=True).execute()
                    ch_items = ch_resp.get("items", [])
                    if ch_items:
                        auth_channel_id = ch_items[0].get("id", ch["id"])
                        auth_channel_title = ch_items[0].get("snippet", {}).get("title", auth_channel_title)
                except Exception:
                    pass
                if ch.get("id") and auth_channel_id != ch["id"]:
                    raise RuntimeError(
                        f"Token for channel '{ch['key']}' belongs to '{auth_channel_title}' ({auth_channel_id}), "
                        f"not {ch.get('handle')} ({ch['id']}). Re-authorize: python main.py --auth-youtube --channel {ch['key']}"
                    )

                media = MediaFileUpload(
                    video_path,
                    chunksize=5 * 1024 * 1024,
                    resumable=True,
                    mimetype="video/mp4",
                )

                print(
                    f"[YouTubePublisher] Uploading Short '{filled['title']}' to {ch.get('handle')} ({ch['id']}) "
                    f"(saved as '{effective_privacy}' awaiting user approval)..."
                )
                request = youtube.videos().insert(
                    part=",".join(body.keys()),
                    body=body,
                    media_body=media,
                )

                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        print(f"[YouTubePublisher] Uploaded {int(status.progress() * 100)}%")

                video_id = response.get("id")
                short_url = f"https://youtube.com/shorts/{video_id}"
                studio_edit_url = f"https://studio.youtube.com/video/{video_id}/edit"
                print(f"[YouTubePublisher] ✓ Saved on YouTube Studio ({effective_privacy}): {studio_edit_url}")

                return {
                    "mode": "youtube_api",
                    "video_id": video_id,
                    "url": short_url,
                    "studio_channel_url": ch["studio_url"],
                    "studio_edit_url": studio_edit_url,
                    "channel_key": ch["key"],
                    "channel_id": ch["id"],
                    "authenticated_channel_id": auth_channel_id,
                    "channel_title": auth_channel_title,
                    "privacy": effective_privacy,
                    "approval_status": "pending_approval",
                    "live": False,
                    "filled_fields": filled,
                    "saved_at": datetime.now().isoformat(),
                    "published_at": response.get("snippet", {}).get("publishedAt"),
                }
            except Exception as api_err:
                print(f"[YouTubePublisher] OAuth upload error: {api_err}")
                if config.YOUTUBE_CLIENT_SECRETS_FILE.exists() or ch["token_path"].exists():
                    raise RuntimeError(
                        f"YouTube upload failed: {api_err}. "
                        f"Your OAuth token for '{ch['key']}' may have expired or was revoked. "
                        f"Re-authenticate: python main.py --auth-youtube --channel {ch['key']}"
                    )

        # Staged Draft Mode only when this channel has no OAuth token yet
        staged_id = f"staged_{(ch['id'] or ch['key'])[-6:]}_{int(datetime.now().timestamp())}"
        return {
            "mode": "studio_staged",
            "video_id": staged_id,
            "url": f"{ch['studio_url']}/videos/short",
            "studio_channel_url": ch["studio_url"],
            "studio_upload_url": ch["upload_url"],
            "studio_edit_url": f"{ch['studio_url']}/videos/short",
            "channel_key": ch["key"],
            "channel_id": ch["id"],
            "channel_title": ch.get("handle") or ch.get("title"),
            "privacy": "private",
            "approval_status": "pending_approval",
            "live": False,
            "filled_fields": filled,
            "saved_at": datetime.now().isoformat(),
            "message": (
                f"All fields filled & saved as Draft for {ch.get('handle')} ({ch['studio_url']}); channel not yet authorized "
                f"(python main.py --auth-youtube --channel {ch['key']}). "
                "Approve it in the studio, then make it public or schedule it in YouTube Studio."
            ),
        }

    @classmethod
    def approve_and_go_live(
        cls,
        project: Dict[str, Any],
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Approve a Short WITHOUT making it public (channel rule, 2026-11-15): updates its title,
        description and tags on YouTube and keeps it PRIVATE. The owner makes it public or schedules
        it in YouTube Studio. (Name kept for existing callers; see approve_keep_private.)
        """
        # The project's own channel wins; a video must never be approved/edited via another channel's token
        ch = cls.channel_info(channel or cls.channel_of(project) or (project.get("youtube") or {}).get("channel_key"))
        yt_info = project.get("youtube") or {}
        existing_fields = yt_info.get("filled_fields") or {}
        filled = cls.build_complete_fields(
            title=title or existing_fields.get("title") or project.get("title", "WeaponX Labs #Shorts"),
            description=description or existing_fields.get("description") or project.get("description", "#Shorts"),
            tags=tags or existing_fields.get("tags") or project.get("tags", ["shorts"]),
            channel=ch["key"],
        )

        video_id = yt_info.get("video_id", "")
        video_path = project.get("video_path", "")

        last_error = None
        if ch["token_path"].exists() and HAS_GOOGLE_API:
            try:
                youtube = cls.get_authenticated_service(channel=ch["key"], interactive=False)
                if video_id and not str(video_id).startswith("staged_"):
                    update_body = {
                        "id": video_id,
                        "snippet": {
                            "title": filled["title"],
                            "description": filled["description"],
                            "tags": filled["tags"],
                            "categoryId": filled["categoryId"],
                            "defaultLanguage": filled["defaultLanguage"],
                            "defaultAudioLanguage": filled["defaultAudioLanguage"],
                        },
                        "status": {
                            "privacyStatus": "private",
                            "selfDeclaredMadeForKids": False,
                            "embeddable": True,
                            "publicStatsViewable": True,
                        },
                    }
                    youtube.videos().update(part="snippet,status", body=update_body).execute()
                    studio_edit_url = f"https://studio.youtube.com/video/{video_id}/edit"
                    print(f"[YouTubePublisher] ✅ Video {video_id} approved and kept PRIVATE: {studio_edit_url}")
                    yt_info.update({
                        "mode": "youtube_api",
                        "privacy": "private",
                        "approval_status": "approved_private",
                        "live": False,
                        "url": f"https://youtube.com/shorts/{video_id}",
                        "studio_edit_url": studio_edit_url,
                        "filled_fields": filled,
                        "approved_at": datetime.now().isoformat(),
                        "message": "Approved and saved as Private. Make it public or schedule it in YouTube Studio.",
                    })
                    return yt_info
                elif video_path and Path(video_path).exists():
                    # Not uploaded yet: upload it now, private
                    result = cls.upload_short(
                        video_path=video_path,
                        title=filled["title"],
                        description=filled["description"],
                        tags=filled["tags"],
                        privacy_status="private",
                        require_approval_before_live=True,
                        project_dir=project.get("project_dir"),
                    )
                    if result.get("mode") == "youtube_api":
                        result.update({"approval_status": "approved_private", "approved_at": datetime.now().isoformat(),
                                       "message": "Approved and saved as Private. Make it public or schedule it in YouTube Studio."})
                        return result
            except Exception as e:
                last_error = e
                print(f"[YouTubePublisher] Approval API error: {e}")

        # If user has OAuth configured or an error occurred during live approval, do NOT fake success
        if last_error:
            raise RuntimeError(f"Could not update the private video on YouTube: {last_error}")

        if cls.is_configured():
            # Credentials present but no active token; trigger re-authentication requirement
            raise RuntimeError(
                "Active YouTube authorization not found. Please click 'Re-Authenticate YouTube' or run 'python main.py --auth-youtube' to connect your channel."
            )

        # Staged record fallback only if no OAuth credentials exist at all
        yt_info.update({
            "channel_key": ch["key"],
            "channel_id": ch["id"],
            "studio_channel_url": ch["studio_url"],
            "studio_upload_url": ch["upload_url"],
            "privacy": "private",
            "approval_status": "approved_private",
            "live": False,
            "filled_fields": filled,
            "approved_at": datetime.now().isoformat(),
            "message": f"Saved draft locally. Upload manually via YouTube Studio: {ch['upload_url']}",
        })
        if project.get("project_dir") and Path(project["project_dir"]).exists():
            draft_file = Path(project["project_dir"]) / "youtube_studio_draft.json"
            try:
                draft_file.write_text(json.dumps(yt_info, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        return yt_info


# Clearer name for the approval step: it never publishes
YouTubePublisher.approve_keep_private = YouTubePublisher.approve_and_go_live

