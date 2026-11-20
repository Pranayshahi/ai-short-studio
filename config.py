import os
from pathlib import Path
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

# Base paths
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Data folders can be redirected (the test suite points them at a temporary copy, so tests never
# touch real projects, music, state or credentials)
OUTPUT_DIR = Path(os.getenv("AI_SHORTS_OUTPUT_DIR") or BASE_DIR / "output")
PROJECTS_DIR = OUTPUT_DIR / "projects"
ASSETS_DIR = BASE_DIR / "assets"
AUDIO_ASSETS_DIR = Path(os.getenv("AI_SHORTS_AUDIO_DIR") or ASSETS_DIR / "audio")
FONTS_DIR = BASE_DIR / "assets" / "fonts"
CREDENTIALS_DIR = Path(os.getenv("AI_SHORTS_CREDENTIALS_DIR") or BASE_DIR / "credentials")

for d in [OUTPUT_DIR, PROJECTS_DIR, ASSETS_DIR, AUDIO_ASSETS_DIR, FONTS_DIR, CREDENTIALS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Project Configuration
NICHE = os.getenv("NICHE", "Defense, Military & Advanced Technology")
TARGET_DURATION_SECONDS = int(os.getenv("TARGET_DURATION_SECONDS", "25"))
TARGET_WORD_COUNT = int(os.getenv("TARGET_WORD_COUNT", "55"))

# Video Resolution (9:16 Vertical for YouTube Shorts)
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1080"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1920"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "30"))

# Voiceover configuration (Edge-TTS is 100% free with ultra-high quality neural voices)
# High-impact documentary voices: en-US-ChristopherNeural, en-US-GuyNeural, en-US-EricNeural
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "en-US-ChristopherNeural")
VOICE_RATE = os.getenv("VOICE_RATE", "+0%")
VOICE_PITCH = os.getenv("VOICE_PITCH", "+0Hz")

# LLM & AI Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ComfyUI local image generation server (free, local AI)
COMFYUI_API_URL = os.getenv("COMFYUI_API_URL", "http://127.0.0.1:8188")

# ACE-Step 1.5 local music server (free, open source)
ACESTEP_API_URL = os.getenv("ACESTEP_API_URL", "http://127.0.0.1:8001")
ACESTEP_API_KEY = os.getenv("ACESTEP_API_KEY", "")
GEMINI_REFERENCE_URL = os.getenv(
    "GEMINI_REFERENCE_URL",
    "https://gemini.google.com/u/1/app/dbdf5025a758bf01"
)
WEAPONX_REFERENCE_IMAGE = ASSETS_DIR / "weaponx_reference.png"
STUDIO_SETTINGS_FILE = OUTPUT_DIR / "studio_settings.json"

# YouTube Data API & Target Channel (@WeaponXLabs)
YOUTUBE_CLIENT_SECRETS_FILE = CREDENTIALS_DIR / "client_secrets.json"
YOUTUBE_TOKENS_FILE = CREDENTIALS_DIR / "youtube_tokens.json"
YOUTUBE_TARGET_CHANNEL_ID = os.getenv("YOUTUBE_TARGET_CHANNEL_ID", "UC4KV67NYzLi8JlrfB9J4hGg")
YOUTUBE_STUDIO_CHANNEL_URL = f"https://studio.youtube.com/channel/{YOUTUBE_TARGET_CHANNEL_ID}"
YOUTUBE_CHANNEL_HANDLE = os.getenv("YOUTUBE_CHANNEL_HANDLE", "@WeaponXLabs")
DEFAULT_PRIVACY_STATUS = os.getenv("DEFAULT_PRIVACY_STATUS", "private") # Saved as 'private' first; goes 'public' after approval

# Daily schedule (in 24-hr format, e.g. "20:00" for 8:00 PM)
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "20:00")
SCHEDULE_TIMEZONE = os.getenv("SCHEDULE_TIMEZONE", "Asia/Kolkata")

# Phase 2 Automation: Webhook Alerts (Discord & Telegram)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Wikimedia Commons User-Agent policy (https://w.wiki/4wJS) requires real contact info
# (an email or URL you control). Without it, upload.wikimedia.org answers HTTP 403.
WIKIMEDIA_CONTACT = os.getenv("WIKIMEDIA_CONTACT", "").strip()
WIKIMEDIA_USER_AGENT = (
    f"AIShortsStudio/2.1 ({WIKIMEDIA_CONTACT}) python-requests"
    if WIKIMEDIA_CONTACT else "AIShortsStudio/2.1 (contact not configured; set WIKIMEDIA_CONTACT) python-requests"
)
