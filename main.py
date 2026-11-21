import argparse
import os
import sys
import uvicorn
from app.agents.pipeline import ShortsPipeline
from app.agents.youtube_publisher import YouTubePublisher

def _serve(args):
    import config  # noqa: F401  (loads .env so STUDIO_API_TOKEN is visible)
    # `kill -USR1 <pid>` writes every thread's Python stack to the log (diagnose a hang without admin rights)
    import faulthandler
    import signal
    faulthandler.register(signal.SIGUSR1, all_threads=True)
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
    parser.add_argument("--auth-youtube", action="store_true", help="Authenticate a YouTube channel (see --channel)")
    parser.add_argument("--channel", type=str, default=None,
                        help="Channel key/handle for --auth-youtube or --generate (e.g. weaponxlabs, autoflashx); default = registry default")
    parser.add_argument("--list-channels", action="store_true", help="List registered YouTube channels and their auth state")
    parser.add_argument("--host", type=str, default=os.getenv("STUDIO_HOST", "127.0.0.1"),
                        help="Interface to bind (default 127.0.0.1 = this computer only; use 0.0.0.0 to expose on the network)")
    parser.add_argument("--reload", action="store_true",
                        help="Auto-reload on code changes (development only; restarts kill running generations)")

    args = parser.parse_args()

    if args.list_channels:
        from agents import youtube_channels as reg
        for key, ch in reg.all_channels().items():
            print(f"{'*' if ch['is_default'] else ' '} {key:14} {ch.get('handle',''):16} {ch.get('id','')}  "
                  f"{'authorized' if ch['authorized'] else 'NOT authorized'}")
        print("(* = default channel)")
        return

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
        from agents import youtube_channels as reg
        ch = reg.get(args.channel)
        print(f"[AI Shorts Studio] Launching YouTube OAuth for channel '{ch['key']}' ({ch.get('handle')}).")
        print(f"  In the Google window, pick the account/channel for {ch.get('handle')}; another channel will be refused.")
        YouTubePublisher.get_authenticated_service(channel=ch["key"])
        print(f"✅ YouTube authentication successful for {ch.get('handle')}! Token saved to {ch['token_path'].name}")
        return

    if args.server:
        _serve(args)
        return

    if args.generate or args.topic:
        pipeline = ShortsPipeline()
        result = pipeline.run(custom_topic=args.topic, auto_publish=args.publish, style=args.style, channel=args.channel)
        print(f"\n🎉 Done! Video produced at: {result.get('video_path')}")
        return

    # Default action if no arguments passed: print help and start dashboard
    print("No flag provided. Starting Web Studio by default...")
    _serve(args)

if __name__ == "__main__":
    main()
