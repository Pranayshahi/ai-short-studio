import argparse
import os
import sys
import uvicorn
from app.agents.pipeline import ShortsPipeline
from app.agents.youtube_publisher import YouTubePublisher

def _serve(args):
    import config  # noqa: F401  (loads .env so STUDIO_API_TOKEN is visible)
    if args.host not in ("127.0.0.1", "localhost", "::1") and not os.getenv("STUDIO_API_TOKEN"):
        print("⚠️  [AI Shorts Studio] Binding to", args.host, "WITHOUT a STUDIO_API_TOKEN: anyone on your network can")
        print("    publish, delete and re-authorize YouTube. Set STUDIO_API_TOKEN in .env to require a token.")
    print(f"[AI Shorts Studio] Launching Web Studio on http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}...")
    uvicorn.run("app.web_app:app", host=args.host, port=args.port, reload=args.reload)

def main():
    parser = argparse.ArgumentParser(description="AI Shorts Studio — Fully Autonomous YouTube Shorts System")
    parser.add_argument("--generate", action="store_true", help="Generate a complete YouTube Short now")
    parser.add_argument("--topic", type=str, default=None, help="Specific topic to generate (e.g. 'B-21 Raider')")
    parser.add_argument("--style", type=str, default="default", choices=["default", "weaponx"], help="Visual style: 'default' or 'weaponx' (@WeaponXLabs style)")
    parser.add_argument("--publish", action="store_true", help="Automatically publish the generated video to YouTube")
    parser.add_argument("--server", action="store_true", help="Launch the Web Studio Dashboard")
    parser.add_argument("--port", type=int, default=8000, help="Port for Web Studio (default: 8000)")
    parser.add_argument("--auth-youtube", action="store_true", help="Authenticate with your YouTube channel")
    parser.add_argument("--host", type=str, default=os.getenv("STUDIO_HOST", "127.0.0.1"),
                        help="Interface to bind (default 127.0.0.1 = this computer only; use 0.0.0.0 to expose on the network)")
    parser.add_argument("--reload", action="store_true",
                        help="Auto-reload on code changes (development only; restarts kill running generations)")

    args = parser.parse_args()

    if args.auth_youtube:
        import time
        import webbrowser
        import config
        print("[AI Shorts Studio] Checking for YouTube OAuth client_secrets.json...")
        if not YouTubePublisher.auto_discover_client_secrets():
            print("\n⚠️  client_secrets.json not found yet.")
            print("Opening Google Cloud Console in your browser to download your OAuth 2.0 Desktop Client JSON...")
            webbrowser.open("https://console.cloud.google.com/apis/library/youtube.googleapis.com")
            webbrowser.open("https://console.cloud.google.com/apis/credentials")
            print(f"Waiting for you to download client_secret_*.json into ~/Downloads (or save to {config.YOUTUBE_CLIENT_SECRETS_FILE})...")
            for _ in range(180):
                if YouTubePublisher.auto_discover_client_secrets():
                    break
                time.sleep(2)
        print("[AI Shorts Studio] Launching YouTube OAuth authentication flow...")
        YouTubePublisher.get_authenticated_service()
        print("✅ YouTube authentication successful! Credentials saved.")
        return

    if args.server:
        _serve(args)
        return

    if args.generate or args.topic:
        pipeline = ShortsPipeline()
        result = pipeline.run(custom_topic=args.topic, auto_publish=args.publish, style=args.style)
        print(f"\n🎉 Done! Video produced at: {result.get('video_path')}")
        return

    # Default action if no arguments passed: print help and start dashboard
    print("No flag provided. Starting Web Studio by default...")
    _serve(args)

if __name__ == "__main__":
    main()
