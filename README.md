# 🎬 AI Shorts Studio — Autonomous YouTube Shorts System

A fully automated, multi-agent AI system designed to research, script, voice, illustrate, render, and publish high-retention 9:16 YouTube Shorts every day without manual intervention.

---

## ⚡ Core Architecture & Autonomous Pipeline

```
  [ Daily Cron Trigger / Webhook ]
                 │
                 ▼
     [ 1. Research Agent ]  ─────────► Selects high-CTR defense/tech topic & avoids repetition
                 │
                 ▼
     [ 2. Scriptwriter Agent ] ──────► 20-25s high-retention script (0-2s hook + punchy pacing)
                 │
                 ▼
     [ 3. Voice & Subtitle Agent ] ──► Edge-TTS neural speech + word-level synced ASS subtitles
                 │
                 ▼
     [ 4. Visual Generation Agent ] ─► 1080x1920 vertical cinematic visuals (Flux / DALL-E)
                 │
                 ▼
     [ 5. Video Assembly Engine ] ───► FFmpeg Ken Burns camera motion + audio ducking + subtitles
                 │
                 ▼
     [ 6. YouTube Publisher Agent ] ─► Direct upload via YouTube Data API v3 (#Shorts)
```

---

## 🚀 Quickstart Guide

### 1. Requirements
- Python 3.10+ (or Docker)
- macOS, Linux, or Windows

### 2. Run Directly on Your Machine

```bash
cd /Users/pranay/.gemini/antigravity/scratch/ai-shorts-studio

# 1. Activate the environment
source .venv/bin/activate

# 2. Launch the Web Studio Dashboard
python main.py --server

# Open http://localhost:8000 in your browser!
```

---

## 🛠️ CLI Commands

| Command | Action |
|---|---|
| `python main.py --generate` | Generates today's automated short immediately |
| `python main.py --topic "B-21 Raider"` | Generates a Short for a specific topic |
| `python main.py --generate --publish` | Generates and immediately uploads to YouTube |
| `python main.py --server --port 8000` | Starts the web management dashboard |
| `python main.py --auth-youtube` | Authorizes your YouTube channel for auto-publishing |
| `python scheduler.py` | Starts the daily automated daemon (runs at 8:00 PM IST) |

---

## 🔑 YouTube API Setup (One-Time)

To enable automatic direct upload to YouTube Shorts:

1. Visit [Google Cloud Console](https://console.cloud.google.com).
2. Create a project and enable **YouTube Data API v3**.
3. Go to **Credentials** → **Create Credentials** → **OAuth client ID**.
4. Select **Desktop app**.
5. Download the JSON file and save it as:
   ```
   credentials/client_secrets.json
   ```
6. Run the one-time authentication command:
   ```bash
   python main.py --auth-youtube
   ```
   *A browser window will open asking you to allow your channel. Once completed, your refresh token is saved securely in `credentials/youtube_tokens.json`.*

---

## ⏰ Daily Automation

The system can run completely hands-free:
```bash
python scheduler.py
```
- By default, it runs every day at **20:00 (8:00 PM IST)**.
- You can change the time and timezone in `.env`:
  ```ini
  SCHEDULE_TIME="20:00"
  SCHEDULE_TIMEZONE="Asia/Kolkata"
  DEFAULT_PRIVACY_STATUS="private"  # or "public" / "unlisted"
  ```

---

## 🐳 Running with Docker

```bash
docker compose up -d
```
Access the dashboard on `http://localhost:8000`.

---

## 🧰 Setup from a fresh clone

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                      # then fill in your own keys (never commit .env)
git clone https://github.com/calesthio/OpenMontage.git openmontage   # optional OpenMontage style
brew install ollama espeak-ng && ollama pull qwen2.5:7b              # local AI scriptwriter + Kokoro voice
```

- YouTube OAuth files live in `credentials/` and are git-ignored; run `python main.py --auth-youtube`.
- Hands-off daily automation: `scripts/install_scheduler.sh` (macOS LaunchAgent), status via `python scheduler.py --status`.
- Optional local engines: ACE-Step music (`scripts/start_acestep.sh`), Phosphene video clips.
