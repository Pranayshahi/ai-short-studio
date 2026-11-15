#!/usr/bin/env bash
# Starts the local ACE-Step 1.5 music server (free, open source) on 127.0.0.1:8001
# using the ACESTEP_API_KEY from this project's .env. Override the install path with ACESTEP_DIR.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ACESTEP_DIR="${ACESTEP_DIR:-$HOME/workspace/ACE-Step-1.5}"
KEY="$(grep -E '^ACESTEP_API_KEY=' "$PROJECT_DIR/.env" | head -1 | cut -d= -f2- | tr -d '"' || true)"
cd "$ACESTEP_DIR"
exec env ACESTEP_API_KEY="$KEY" .venv/bin/acestep-api --host 127.0.0.1 --port 8001
