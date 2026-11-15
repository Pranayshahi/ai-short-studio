"""
Scene clip generator — 100% free image-to-video for a scene's still image.

Engines:
  wan22_hf       Wan 2.2 I2V A14B on a free Hugging Face ZeroGPU Space (~1 min, <=5 s clips, 480x832)
  ltx23_hf       LTX-2.3 distilled on Lightricks' official free ZeroGPU Space (~30 s, <=10 s clips)
  phosphene_ltx  LTX-2.5 running locally on this Mac through the Phosphene app (unlimited, offline, slow)

ZeroGPU Spaces have a daily free GPU quota. Anonymous use runs out after ~2 clips; a free
Hugging Face account token (HF_TOKEN) raises it. Phosphene has no quota but needs the app
installed and running (https://github.com/mrbizarro/phosphene).
"""

import json
import math
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests
from PIL import Image

import config

ENGINES: Dict[str, Dict[str, Any]] = {
    "wan22_hf": {
        "label": "Wan 2.2 (free HF Space)",
        "where": "Hugging Face ZeroGPU",
        "space": os.getenv("WAN_HF_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster"),
        "max_seconds": 5.0,
        "typical": "about 1 min",
    },
    "ltx23_hf": {
        "label": "LTX-2.3 (free HF Space)",
        "where": "Hugging Face ZeroGPU",
        "space": os.getenv("LTX_HF_SPACE", "Lightricks/LTX-2-3"),
        "max_seconds": 10.0,
        "typical": "about 30-60 s",
    },
    "phosphene_ltx": {
        "label": "LTX-2.5 (Phosphene, local)",
        "where": "this Mac",
        "max_seconds": 10.0,
        "typical": "several minutes (448x768 on Macs under 48 GB)",
    },
}

WAN_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, warped geometry, melting, morphing objects, flicker, jitter, "
    "text, watermark, logo, subtitles, static frame, extra limbs"
)

# Phosphene's "Compact" tier (Macs under 48 GB) caps image-to-video at 768 px on the long side,
# snapped to /64, so 448x768 is the largest portrait size it renders as-is.
# Override with PHOSPHENE_SIZE=WxH on a 48 GB+ Mac (e.g. 704x1280).
PHOSPHENE_SIZE = os.getenv("PHOSPHENE_SIZE", "448x768")
# 8198 Pinokio / manual install, 8199 dev profile, 8930-8999 the Mac app (agent_discovery.py)
PHOSPHENE_PORTS = [8198, 8199] + list(range(8930, 9000))


class ClipGenerationError(RuntimeError):
    pass


StatusFn = Callable[[str, Optional[float]], None]


def _noop_status(msg: str, pct: Optional[float] = None) -> None:
    print(f"[ClipGenerator] {msg}" + (f" ({pct:.0f}%)" if pct is not None else ""))


# ---------------------------------------------------------------- settings

def get_hf_token() -> str:
    """HF_TOKEN env var wins; otherwise the token saved from the studio UI. Optional."""
    tok = os.getenv("HF_TOKEN", "").strip()
    if tok:
        return tok
    try:
        saved = json.loads(config.STUDIO_SETTINGS_FILE.read_text(encoding="utf-8"))
        return str(saved.get("hf_token", "")).strip()
    except Exception:
        return ""


def _portrait_input(image_path: Path, workdir: Path, long_side: int = 1024) -> Path:
    """Downscale the 1080x1920 scene image (the models render well below that anyway)."""
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((long_side, long_side), Image.Resampling.LANCZOS)
    out = workdir / "input.jpg"
    img.save(out, "JPEG", quality=93)
    return out


# ---------------------------------------------------------------- Hugging Face Spaces

_QUOTA_RE = re.compile(r"(exceeded your ZeroGPU (?:quota|runs limit)[^.]*\.?)(?:.*?Try again in ([0-9:]+))?", re.I | re.S)


def _friendly_hf_error(exc: Exception, engine_label: str) -> ClipGenerationError:
    msg = str(exc)
    m = _QUOTA_RE.search(msg)
    if m:
        wait = f" It resets in {m.group(2)}." if m.group(2) else ""
        hint = (" Add a free Hugging Face token for more daily quota, or" if not get_hf_token() else " You can")
        return ClipGenerationError(
            f"Free Hugging Face GPU quota used up for {engine_label}.{wait}{hint} use Phosphene (local, unlimited)."
        )
    if "upstream Gradio app has raised an exception" in msg:
        return ClipGenerationError(f"{engine_label}: the free Space returned an error (it may be busy or restarting). Try again in a minute.")
    return ClipGenerationError(f"{engine_label} failed: {msg[:300]}")


def _run_space(engine: str, call: Callable[[Any], Any], on_status: StatusFn):
    try:
        from gradio_client import Client
    except ImportError as e:
        raise ClipGenerationError("gradio_client is not installed. Run: pip install gradio_client") from e

    spec = ENGINES[engine]
    token = get_hf_token() or None
    last_exc: Optional[Exception] = None
    # ZeroGPU Spaces run several replicas; a call can land on a different one than the upload
    # and fail with 403/session_not_found. A fresh client on retry usually fixes it.
    for attempt in range(2):
        try:
            on_status(f"Connecting to {spec['space']}..." if attempt == 0 else "Retrying on a fresh connection...", None)
            client = Client(spec["space"], token=token, verbose=False)
            on_status(f"Rendering on free Hugging Face GPU ({spec['typical']})...", None)
            return call(client)
        except Exception as e:
            last_exc = e
            text = str(e)
            if _QUOTA_RE.search(text):
                break
            if not any(k in text for k in ("403", "404", "session_not_found", "Connection", "timed out")):
                break
    raise _friendly_hf_error(last_exc, spec["label"])


def _gen_wan_hf(image: Path, prompt: str, duration: float, on_status: StatusFn) -> Path:
    from gradio_client import handle_file

    dur = max(1.0, min(5.0, duration))

    def call(client):
        return client.predict(
            input_image=handle_file(str(image)),
            prompt=prompt,
            steps=6,
            negative_prompt=WAN_NEGATIVE_PROMPT,
            duration_seconds=dur,
            guidance_scale=1,
            guidance_scale_2=1,
            seed=42,
            randomize_seed=True,
            api_name="/generate_video",
        )

    result = _run_space("wan22_hf", call, on_status)
    return Path(result[0] if isinstance(result, (list, tuple)) else result)


def _gen_ltx_hf(image: Path, prompt: str, duration: float, on_status: StatusFn, hd: bool = False) -> Path:
    from gradio_client import handle_file

    dur = max(1.0, min(10.0, duration))
    # Portrait sizes the Space itself suggests for a 9:16 image (standard / high-res).
    height, width = (1536, 1024) if hd else (768, 512)

    def call(client):
        return client.predict(
            handle_file(str(image)),
            prompt,
            dur,
            False,   # enhance_prompt
            42,      # seed
            True,    # randomize_seed
            height,
            width,
            api_name="/generate_video",
        )

    result = _run_space("ltx23_hf", call, on_status)
    path = result[0] if isinstance(result, (list, tuple)) else result
    if not path:
        raise ClipGenerationError("LTX-2.3 Space returned no video (it may have hit its GPU time limit). Try a shorter clip or turn off HD.")
    return Path(path)


# ---------------------------------------------------------------- Phosphene (local)

def find_phosphene() -> Optional[str]:
    """Returns the base URL of a running Phosphene panel, or None."""
    candidates = []
    servers_dir = Path.home() / ".phosphene" / "servers"
    if servers_dir.is_dir():
        for f in sorted(servers_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
            try:
                txt = f.read_text(encoding="utf-8")
                try:
                    data = json.loads(txt)
                    url = data.get("url") or data.get("base_url") or (f"http://127.0.0.1:{data['port']}" if data.get("port") else None)
                except Exception:
                    m = re.search(r"https?://127\.0\.0\.1:\d+|(?<!\d)(\d{4,5})(?!\d)", txt)
                    url = (m.group(0) if m and m.group(0).startswith("http") else f"http://127.0.0.1:{m.group(1)}") if m else None
                if url:
                    candidates.append(url.rstrip("/"))
            except Exception:
                continue
    candidates += [f"http://127.0.0.1:{p}" for p in PHOSPHENE_PORTS]

    seen = set()
    for base in candidates:
        if base in seen:
            continue
        seen.add(base)
        try:
            r = requests.get(f"{base}/agents/info", timeout=0.25)
            if r.ok and (r.json() or {}).get("app") == "phosphene":
                return base
        except (requests.RequestException, ValueError):
            continue
    return None


def _phosphene_status(base: str) -> Dict[str, Any]:
    # /status can carry raw control characters from multi-line prompts (Phosphene docs/API.md)
    raw = requests.get(f"{base}/status", timeout=30).content
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw.decode("utf-8", "replace"))
    return json.loads(text, strict=False)


def _phosphene_outputs(row: Dict[str, Any]) -> list:
    """Same field lookup as Phosphene's own agents/phosphene_client.py row_outputs()."""
    paths = []
    for v in [row.get(k) for k in ("output_path", "output_paths", "outputs", "paths", "raw_path")]:
        if isinstance(v, str) and v:
            paths.append(v)
        elif isinstance(v, list):
            paths += [x if isinstance(x, str) else (x or {}).get("path") for x in v if isinstance(x, (str, dict))]
    return [p for p in dict.fromkeys(paths) if p and str(p).lower().endswith((".mp4", ".mov", ".webm"))]


def _gen_phosphene(image: Path, prompt: str, duration: float, on_status: StatusFn, timeout_s: float = 3600) -> Path:
    base = find_phosphene()
    if not base:
        raise ClipGenerationError(
            "Phosphene isn't running. Install it (free) from https://github.com/mrbizarro/phosphene, "
            "download the LTX-2.5 model in Settings → Models, keep the app open, then try again."
        )
    try:
        w, h = (int(v) for v in PHOSPHENE_SIZE.lower().split("x"))
    except Exception:
        w, h = 480, 864
    w, h = max(64, (w // 64) * 64), max(64, (h // 64) * 64)
    # LTX is trained at 24 fps; frames must be 8k+1.
    frames = 8 * math.ceil(max(1.0, min(10.0, duration)) * 24 / 8) + 1

    on_status("Uploading image to Phosphene...", None)
    with open(image, "rb") as f:
        up = requests.post(f"{base}/upload", files={"image": (image.name, f, "image/jpeg")}, timeout=60)
    if not up.ok or "path" not in up.json():
        raise ClipGenerationError(f"Phosphene upload failed ({up.status_code}): {up.text[:300]}")

    job = requests.post(f"{base}/queue/add", data={
        "mode": "i2v",
        "prompt": prompt,
        "image": up.json()["path"],
        "width": w,
        "height": h,
        "frames": frames,
        "frame_rate": 24,
        "quality": "balanced",
        "enhance": "false",
        "upscale": "off",
        "engine": "ltx",
        "open_when_done": "off",
        "label": "AI Shorts Studio scene clip",
    }, timeout=60)
    body = job.json() if job.headers.get("content-type", "").startswith("application/json") else {}
    if not job.ok or not body.get("id"):
        if body.get("code") == "pack_missing":
            raise ClipGenerationError("Phosphene is running but the LTX-2.5 model isn't downloaded. Open Phosphene → Settings → Models → Download.")
        raise ClipGenerationError(f"Phosphene rejected the job ({job.status_code}): {body.get('error') or job.text[:300]}")
    job_id = body["id"]

    deadline = time.time() + timeout_s
    status_failures = 0
    while time.time() < deadline:
        time.sleep(5)
        try:
            st = _phosphene_status(base)
            status_failures = 0
        except Exception as e:
            status_failures += 1
            if status_failures >= 12:   # ~1 minute of an unreachable/garbled panel
                raise ClipGenerationError(f"Lost contact with Phosphene while rendering: {e}")
            continue
        cur = st.get("current") or {}
        if cur.get("id") == job_id:
            prog = cur.get("progress") or {}
            eta = prog.get("remaining_sec") or prog.get("eta_sec")
            label = prog.get("phase_label") or prog.get("phase") or "Rendering"
            on_status(f"Phosphene: {label}" + (f" · ~{int(eta // 60)}m{int(eta % 60):02d}s left" if eta else ""), prog.get("pct"))
            continue
        if any((q or {}).get("id") == job_id for q in st.get("queue") or []):
            on_status("Phosphene: waiting in its queue...", None)
            continue
        for h_entry in st.get("history") or []:
            if h_entry.get("id") != job_id:
                continue
            status = h_entry.get("status")
            if status == "done":
                for out in _phosphene_outputs(h_entry):
                    if Path(out).exists():
                        return Path(out)
                raise ClipGenerationError("Phosphene finished but its output file was not found.")
            if status in ("failed", "cancelled", "stopped", "error"):
                raise ClipGenerationError(f"Phosphene job {status}: {h_entry.get('error') or 'no details'}")
    raise ClipGenerationError(f"Phosphene job {job_id} did not finish within {int(timeout_s // 60)} minutes.")


# ---------------------------------------------------------------- public API

def engine_status() -> Dict[str, Any]:
    return {"hf_token": bool(get_hf_token()), "phosphene_url": find_phosphene()}


def generate_scene_clip(
    engine: str,
    image_path: Path,
    prompt: str,
    duration: float,
    output_path: Path,
    on_status: Optional[StatusFn] = None,
    hd: bool = False,
) -> Dict[str, Any]:
    """Animate image_path into output_path (MP4). Returns metadata about the generation."""
    if engine not in ENGINES:
        raise ClipGenerationError(f"Unknown clip engine '{engine}'. Use one of: {', '.join(ENGINES)}")
    image_path = Path(image_path)
    if not image_path.exists():
        raise ClipGenerationError(f"Scene image not found: {image_path}")
    on_status = on_status or _noop_status
    spec = ENGINES[engine]
    duration = max(1.0, min(float(duration or 5.0), spec["max_seconds"]))
    prompt = prompt.strip()
    started = time.time()

    with tempfile.TemporaryDirectory(prefix="clipgen_") as tmp:
        src = _portrait_input(image_path, Path(tmp))
        if engine == "wan22_hf":
            produced = _gen_wan_hf(src, prompt, duration, on_status)
        elif engine == "ltx23_hf":
            produced = _gen_ltx_hf(src, prompt, duration, on_status, hd=hd)
        else:
            produced = _gen_phosphene(src, prompt, duration, on_status)

        if not produced.exists() or produced.stat().st_size < 1000:
            raise ClipGenerationError(f"{spec['label']} produced an empty video.")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, output_path)

    return {
        "engine": engine,
        "engine_label": spec["label"],
        "where": spec["where"],
        "prompt": prompt,
        "requested_seconds": duration,
        "hd": bool(hd) if engine == "ltx23_hf" else None,
        "elapsed_seconds": round(time.time() - started, 1),
        "cost_usd": 0.0,
    }
