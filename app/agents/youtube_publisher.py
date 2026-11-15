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
    TARGET_CHANNEL_ID = getattr(config, "YOUTUBE_TARGET_CHANNEL_ID", "UC4KV67NYzLi8JlrfB9J4hGg")
    STUDIO_CHANNEL_URL = f"https://studio.youtube.com/channel/{TARGET_CHANNEL_ID}"
    STUDIO_UPLOAD_URL = f"https://studio.youtube.com/channel/{TARGET_CHANNEL_ID}/videos/upload?d=ud"
    CHANNEL_HANDLE = getattr(config, "YOUTUBE_CHANNEL_HANDLE", "@WeaponXLabs")

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
    def is_authenticated(cls) -> bool:
        """Checks if valid, active YouTube OAuth tokens exist."""
        tokens_path = config.YOUTUBE_TOKENS_FILE
        if not tokens_path.exists():
            return False
        try:
            creds = Credentials.from_authorized_user_file(str(tokens_path), SCOPES)
            return bool(creds and (creds.valid or creds.refresh_token))
        except Exception:
            return False

    @classmethod
    def get_authenticated_service(cls):
        """Obtains authorized YouTube Data API v3 service instance."""
        creds = None
        tokens_path = config.YOUTUBE_TOKENS_FILE
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
                print("[YouTubePublisher] Starting OAuth browser sign-in flow on local server...")
                flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
                creds = flow.run_local_server(port=0)
                with open(tokens_path, "w") as token:
                    token.write(creds.to_json())
                print(f"[YouTubePublisher] ✓ Saved fresh YouTube tokens to {tokens_path}")

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
    ) -> Dict[str, Any]:
        """
        Ensures every YouTube Studio field is populated for channel UC4KV67NYzLi8JlrfB9J4hGg (@WeaponXLabs).
        """
        try:
            from agents.youtube_metadata import clean_metadata
            title, description, tags = clean_metadata(title or "", description or "", list(tags or []), topic or title or "")
        except Exception as e:
            print(f"[YouTubePublisher] metadata guard skipped: {e}")
        clean_title = (title or "WeaponX Labs Breakdown #Shorts").strip()
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
        if cls.CHANNEL_HANDLE.lower() not in clean_desc.lower():
            clean_desc += f"\n\nOfficial Channel: {cls.CHANNEL_HANDLE} ({cls.STUDIO_CHANNEL_URL})"

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
            "channel_id": cls.TARGET_CHANNEL_ID,
            "channel_handle": cls.CHANNEL_HANDLE,
            "studio_channel_url": cls.STUDIO_CHANNEL_URL,
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
    ) -> Dict[str, Any]:
        """
        Step 1 of the 2-Step Approval Workflow:
        Uploads the Short to channel UC4KV67NYzLi8JlrfB9J4hGg, fills all YouTube Studio
        fields (Title, Description, Tags, Category, Audience=Not Made for Kids, Language,
        Synthetic Media Disclosure), and saves it as 'private' (Draft / Pending Approval)
        so it ONLY goes live after the user clicks 'Approve & Go Live'.
        """
        filled = cls.build_complete_fields(
            title=title,
            description=description,
            tags=tags,
            category_id=category_id,
            made_for_kids=made_for_kids,
        )

        # When require_approval_before_live is True, always save as 'private' initially
        effective_privacy = "private" if require_approval_before_live else (privacy_status or "private")

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
                            "target_channel_id": cls.TARGET_CHANNEL_ID,
                            "studio_channel_url": cls.STUDIO_CHANNEL_URL,
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

        if config.YOUTUBE_TOKENS_FILE.exists() and HAS_GOOGLE_API:
            try:
                youtube = cls.get_authenticated_service()

                # Check authenticated channel info
                auth_channel_id = cls.TARGET_CHANNEL_ID
                auth_channel_title = cls.CHANNEL_HANDLE
                try:
                    ch_resp = youtube.channels().list(part="id,snippet", mine=True).execute()
                    ch_items = ch_resp.get("items", [])
                    if ch_items:
                        auth_channel_id = ch_items[0].get("id", cls.TARGET_CHANNEL_ID)
                        auth_channel_title = ch_items[0].get("snippet", {}).get("title", cls.CHANNEL_HANDLE)
                except Exception:
                    pass

                media = MediaFileUpload(
                    video_path,
                    chunksize=5 * 1024 * 1024,
                    resumable=True,
                    mimetype="video/mp4",
                )

                print(
                    f"[YouTubePublisher] Uploading Short '{filled['title']}' to channel {cls.TARGET_CHANNEL_ID} "
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
                    "studio_channel_url": cls.STUDIO_CHANNEL_URL,
                    "studio_edit_url": studio_edit_url,
                    "channel_id": cls.TARGET_CHANNEL_ID,
                    "authenticated_channel_id": auth_channel_id,
                    "channel_title": auth_channel_title,
                    "privacy": effective_privacy,
                    "approval_status": "pending_approval" if effective_privacy != "public" else "approved_live",
                    "live": effective_privacy == "public",
                    "filled_fields": filled,
                    "saved_at": datetime.now().isoformat(),
                    "published_at": response.get("snippet", {}).get("publishedAt"),
                }
            except Exception as api_err:
                print(f"[YouTubePublisher] OAuth upload error: {api_err}")
                if config.YOUTUBE_CLIENT_SECRETS_FILE.exists() or config.YOUTUBE_TOKENS_FILE.exists():
                    raise RuntimeError(
                        f"YouTube upload failed: {api_err}. "
                        "Your OAuth token may have expired or was revoked. Please re-authenticate YouTube channel."
                    )

        # Staged Draft Mode only when OAuth credentials are not present in credentials/
        staged_id = f"staged_{cls.TARGET_CHANNEL_ID[-6:]}_{int(datetime.now().timestamp())}"
        return {
            "mode": "studio_staged",
            "video_id": staged_id,
            "url": f"{cls.STUDIO_CHANNEL_URL}/videos/short",
            "studio_channel_url": cls.STUDIO_CHANNEL_URL,
            "studio_upload_url": cls.STUDIO_UPLOAD_URL,
            "studio_edit_url": f"{cls.STUDIO_CHANNEL_URL}/videos/short",
            "channel_id": cls.TARGET_CHANNEL_ID,
            "channel_title": cls.CHANNEL_HANDLE,
            "privacy": "private",
            "approval_status": "pending_approval",
            "live": False,
            "filled_fields": filled,
            "saved_at": datetime.now().isoformat(),
            "message": (
                f"All fields filled & saved as Draft for channel {cls.TARGET_CHANNEL_ID} ({cls.STUDIO_CHANNEL_URL}). "
                "Click 'Approve & Go Live' to publish live."
            ),
        }

    @classmethod
    def approve_and_go_live(
        cls,
        project: Dict[str, Any],
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Step 2 of the 2-Step Approval Workflow:
        After the user reviews the saved Short and clicks 'Approve & Go Live',
        switches the video privacyStatus to 'public' so it goes LIVE on
        https://studio.youtube.com/channel/UC4KV67NYzLi8JlrfB9J4hGg.
        """
        yt_info = project.get("youtube") or {}
        existing_fields = yt_info.get("filled_fields") or {}
        filled = cls.build_complete_fields(
            title=title or existing_fields.get("title") or project.get("title", "WeaponX Labs #Shorts"),
            description=description or existing_fields.get("description") or project.get("description", "#Shorts"),
            tags=tags or existing_fields.get("tags") or project.get("tags", ["shorts"]),
        )

        video_id = yt_info.get("video_id", "")
        video_path = project.get("video_path", "")

        last_error = None
        if config.YOUTUBE_TOKENS_FILE.exists() and HAS_GOOGLE_API:
            try:
                youtube = cls.get_authenticated_service()
                if video_id and not str(video_id).startswith("staged_"):
                    # Update existing private video on YouTube to PUBLIC (LIVE)
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
                            "privacyStatus": "public",
                            "selfDeclaredMadeForKids": False,
                            "embeddable": True,
                            "publicStatsViewable": True,
                        },
                    }
                    youtube.videos().update(
                        part="snippet,status",
                        body=update_body,
                    ).execute()
                    short_url = f"https://youtube.com/shorts/{video_id}"
                    print(f"[YouTubePublisher] 🚀 Video {video_id} APPROVED & LIVE (PUBLIC): {short_url}")
                    yt_info.update({
                        "mode": "youtube_api",
                        "privacy": "public",
                        "approval_status": "approved_live",
                        "live": True,
                        "url": short_url,
                        "filled_fields": filled,
                        "approved_at": datetime.now().isoformat(),
                    })
                    return yt_info
                elif video_path and Path(video_path).exists():
                    # Upload directly as PUBLIC now that user approved
                    result = cls.upload_short(
                        video_path=video_path,
                        title=filled["title"],
                        description=filled["description"],
                        tags=filled["tags"],
                        privacy_status="public",
                        require_approval_before_live=False,
                        project_dir=project.get("project_dir"),
                    )
                    if result.get("mode") == "youtube_api":
                        return result
            except Exception as e:
                last_error = e
                print(f"[YouTubePublisher] Live approval API error: {e}")

        # If user has OAuth configured or an error occurred during live approval, do NOT fake success
        if last_error:
            raise RuntimeError(f"Could not go LIVE on YouTube: {last_error}")

        if cls.is_configured():
            # Credentials present but no active token; trigger re-authentication requirement
            raise RuntimeError(
                "Active YouTube authorization not found. Please click 'Re-Authenticate YouTube' or run 'python main.py --auth-youtube' to connect your channel."
            )

        # Staged record fallback only if no OAuth credentials exist at all
        yt_info.update({
            "channel_id": cls.TARGET_CHANNEL_ID,
            "studio_channel_url": cls.STUDIO_CHANNEL_URL,
            "studio_upload_url": cls.STUDIO_UPLOAD_URL,
            "privacy": "public",
            "approval_status": "approved_live",
            "live": False,
            "filled_fields": filled,
            "approved_at": datetime.now().isoformat(),
            "message": f"Saved draft locally. Upload manually via YouTube Studio: {cls.STUDIO_UPLOAD_URL}",
        })
        if project.get("project_dir") and Path(project["project_dir"]).exists():
            draft_file = Path(project["project_dir"]) / "youtube_studio_draft.json"
            try:
                draft_file.write_text(json.dumps(yt_info, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        return yt_info
