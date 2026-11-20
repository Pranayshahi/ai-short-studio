#!/usr/bin/env bash
# Opens the dashboard signed in (the studio token from .env is passed once; a cookie keeps you signed in 30 days).
cd "$(dirname "$0")/.." || exit 1
TOKEN="$(grep -E '^STUDIO_API_TOKEN=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
URL="http://127.0.0.1:${STUDIO_PORT:-8000}/"
[ -n "$TOKEN" ] && URL="${URL}?token=${TOKEN}"
open "$URL"
