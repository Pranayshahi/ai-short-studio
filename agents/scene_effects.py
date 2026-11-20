"""
Per-scene motion & image effects (FFmpeg filter builder).

Scene fields (missing values fall back to project["scene_defaults"], then "auto"):
  motion           "auto" | "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "pan_up" | "pan_down" | "focus" | "static"
  motion_strength  "subtle" | "normal" | "strong"
  focus_point      {"x": 0-1, "y": 0-1}   target of zoom/focus motions and of focus_blur
  effects          {"filter": "none|cinematic|bw|sepia|vintage|warm|cool|vivid",
                    "vignette": bool, "focus_blur": bool, "fade_in": bool, "fade_out": bool}

Motion is rendered with zoompan on a 2x pre-scaled image (removes the stair-step jitter of
zooming a frame-sized image) and smoothstep easing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MOTIONS = [
    ("auto", "Auto (alternating zoom)"), ("zoom_in", "Zoom in"), ("zoom_out", "Zoom out"),
    ("pan_left", "Pan left"), ("pan_right", "Pan right"), ("pan_up", "Pan up"), ("pan_down", "Pan down"),
    ("focus", "Focus push-in"), ("static", "Static (no motion)"),
]
STRENGTHS = [("subtle", "Subtle"), ("normal", "Normal"), ("strong", "Strong")]
SPEED_RAMPS = [
    ("none", "Smooth (standard)"),
    ("velocity", "Swxft Velocity (Fast · Slow-Mo · Fast)"),
    ("whip_in", "Whip-In → Slow-Mo Hold"),
    ("whip_out", "Slow-Mo → Whip-Out Exit"),
]
FILTERS = [
    ("none", "None"), ("cinematic", "Cinematic"), ("bw", "Black & white"), ("sepia", "Sepia"),
    ("vintage", "Vintage film"), ("warm", "Warm"), ("cool", "Cool"), ("vivid", "Vivid"),
]
TOGGLES = [
    ("vignette", "Vignette"),
    ("focus_blur", "Focus blur"),
    ("beat_flash", "Beat flash & pulse"),
    ("fade_in", "Fade in"),
    ("fade_out", "Fade out"),
]

ZOOM_DELTA = {"subtle": 0.08, "normal": 0.16, "strong": 0.28}
DEFAULT_FOCUS = {"x": 0.5, "y": 0.45}
DEFAULT_BPM = 130.0

COLOR_FILTERS = {
    "none": "",
    "cinematic": "eq=contrast=1.08:saturation=1.08,colorbalance=rs=-0.06:gs=-0.02:bs=0.06:rh=0.06:gh=0.02:bh=-0.06",
    "bw": "hue=s=0,eq=contrast=1.12",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "vintage": "curves=preset=vintage,eq=saturation=0.9,noise=alls=8:allf=t",
    "warm": "colortemperature=temperature=4800",
    "cool": "colortemperature=temperature=8800",
    "vivid": "eq=saturation=1.35:contrast=1.05",
}
FADE_SECONDS = 0.35


def options() -> Dict[str, Any]:
    return {
        "motions": [{"id": i, "label": l} for i, l in MOTIONS],
        # Strengths and toggles are plain ids (their labels live in "labels"), so a UI that prints
        # them directly can never show "[object Object]"
        "strengths": [i for i, _ in STRENGTHS],
        "speed_ramps": [{"id": i, "label": l} for i, l in SPEED_RAMPS],
        "filters": [{"id": i, "label": l} for i, l in FILTERS],
        "toggles": [i for i, _ in TOGGLES],
        "labels": {**dict(STRENGTHS), **dict(TOGGLES), **dict(SPEED_RAMPS)},
        "defaults": {
            "motion": "auto",
            "motion_strength": "normal",
            "speed_ramp": "none",
            "beat_sync": False,
            "bpm": DEFAULT_BPM,
            "focus_point": DEFAULT_FOCUS,
            "effects": {
                "filter": "none",
                "vignette": False,
                "focus_blur": False,
                "beat_flash": False,
                "fade_in": False,
                "fade_out": False,
            },
        },
    }


def validate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Returns only the provided, valid fields (raises ValueError with a readable message)."""
    out: Dict[str, Any] = {}
    if "motion" in payload and payload["motion"] is not None:
        if payload["motion"] not in dict(MOTIONS):
            raise ValueError(f"motion must be one of {[m for m, _ in MOTIONS]}")
        out["motion"] = payload["motion"]
    if "motion_strength" in payload and payload["motion_strength"] is not None:
        if payload["motion_strength"] not in ZOOM_DELTA:
            raise ValueError(f"motion_strength must be one of {list(ZOOM_DELTA)}")
        out["motion_strength"] = payload["motion_strength"]
    if "speed_ramp" in payload and payload["speed_ramp"] is not None:
        if payload["speed_ramp"] not in dict(SPEED_RAMPS):
            raise ValueError(f"speed_ramp must be one of {[r for r, _ in SPEED_RAMPS]}")
        out["speed_ramp"] = payload["speed_ramp"]
    if "beat_sync" in payload and payload["beat_sync"] is not None:
        out["beat_sync"] = bool(payload["beat_sync"])
    if "bpm" in payload and payload["bpm"] is not None:
        try:
            bpm_val = float(payload["bpm"])
        except Exception:
            raise ValueError("bpm must be a number between 40 and 240")
        if not (40.0 <= bpm_val <= 240.0):
            raise ValueError("bpm must be between 40 and 240")
        out["bpm"] = round(bpm_val, 2)
    if "focus_point" in payload and payload["focus_point"] is not None:
        fp = payload["focus_point"]
        try:
            x, y = float(fp["x"]), float(fp["y"])
        except Exception:
            raise ValueError("focus_point must be {\"x\": 0-1, \"y\": 0-1}")
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("focus_point x and y must be between 0 and 1")
        out["focus_point"] = {"x": round(x, 4), "y": round(y, 4)}
    if "effects" in payload and payload["effects"] is not None:
        fx = payload["effects"]
        if not isinstance(fx, dict):
            raise ValueError("effects must be an object")
        clean: Dict[str, Any] = {}
        if "filter" in fx:
            if fx["filter"] not in COLOR_FILTERS:
                raise ValueError(f"effects.filter must be one of {list(COLOR_FILTERS)}")
            clean["filter"] = fx["filter"]
        for key, _ in TOGGLES:
            if key in fx:
                clean[key] = bool(fx[key])
        unknown = set(fx) - set(clean) - {"filter"}
        if unknown:
            raise ValueError(f"unknown effects keys: {sorted(unknown)}")
        out["effects"] = clean
    return out


def resolve(scene: Optional[Dict[str, Any]], defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merges scene overrides over project defaults over built-in defaults."""
    base = options()["defaults"]
    d = defaults or {}
    s = scene or {}
    effects = {**base["effects"], **(d.get("effects") or {}), **(s.get("effects") or {})}
    beat_sync = s.get("beat_sync") if s.get("beat_sync") is not None else (
        d.get("beat_sync") if d.get("beat_sync") is not None else bool(effects.get("beat_flash"))
    )
    if beat_sync:
        effects["beat_flash"] = True
    return {
        "motion": s.get("motion") or d.get("motion") or base["motion"],
        "motion_strength": s.get("motion_strength") or d.get("motion_strength") or base["motion_strength"],
        "speed_ramp": s.get("speed_ramp") or d.get("speed_ramp") or base["speed_ramp"],
        "beat_sync": bool(beat_sync),
        "bpm": float(s.get("bpm") or d.get("bpm") or base["bpm"]),
        "focus_point": s.get("focus_point") or d.get("focus_point") or base["focus_point"],
        "effects": effects,
    }


def _easing_expr(speed_ramp: str, n: int) -> str:
    """
    Returns FFmpeg frame-normalized progress expression e(on) in [0, 1]:
    - 'velocity': Swxft Fast-Slow-Fast speed ramp (3x whip entry on the beat cut -> slow-mo hero hold -> 3x whip exit)
    - 'whip_in': Explosive whip-in on the beat cut that decelerates into a slow-motion hold
    - 'whip_out': Slow-motion hold that accelerates rapidly into the next beat cut
    - 'none': Standard smoothstep easing
    """
    u = f"(on/{n})"
    if speed_ramp == "velocity":
        d = f"({u}-0.5)"
        return f"(0.85*(0.5+4*{d}*{d}*{d})+0.15*{u})"
    if speed_ramp == "whip_in":
        inv = f"(1-{u})"
        return f"(1-{inv}*{inv}*{inv})"
    if speed_ramp == "whip_out":
        return f"({u}*{u}*{u})"
    return f"({u}*{u}*(3-2*{u}))"


def _motion_filter(motion: str, strength: str, focus: Dict[str, float], frames: int, fps: int,
                   w: int, h: int, scene_idx: int, speed_ramp: str = "none",
                   beat_sync: bool = False, bpm: float = DEFAULT_BPM) -> str:
    D = ZOOM_DELTA.get(strength, ZOOM_DELTA["normal"])
    n = max(frames - 1, 1)
    e = _easing_expr(speed_ramp, n)
    fx, fy = float(focus.get("x", 0.5)), float(focus.get("y", 0.45))
    if motion == "auto":
        motion, fx, fy = ("zoom_in" if scene_idx % 2 == 0 else "zoom_out"), 0.5, 0.5
    clamp_x = lambda expr: f"max(0,min(iw-iw/zoom,{expr}))"
    clamp_y = lambda expr: f"max(0,min(ih-ih/zoom,{expr}))"
    if motion == "zoom_in":
        z, x, y = f"1+{D}*{e}", clamp_x(f"{fx}*iw-iw/zoom/2"), clamp_y(f"{fy}*ih-ih/zoom/2")
    elif motion == "zoom_out":
        z, x, y = f"1+{D}*(1-{e})", clamp_x(f"{fx}*iw-iw/zoom/2"), clamp_y(f"{fy}*ih-ih/zoom/2")
    elif motion == "focus":
        cx, cy = f"(0.5+({fx}-0.5)*{e})", f"(0.5+({fy}-0.5)*{e})"
        z, x, y = f"1+{D * 1.6:.3f}*{e}", clamp_x(f"{cx}*iw-iw/zoom/2"), clamp_y(f"{cy}*ih-ih/zoom/2")
    elif motion in ("pan_left", "pan_right", "pan_up", "pan_down"):
        z = f"{1 + D:.3f}"
        x = clamp_x(f"{fx}*iw-iw/zoom/2")
        y = clamp_y(f"{fy}*ih-ih/zoom/2")
        if motion == "pan_left":
            x = f"(iw-iw/zoom)*(1-{e})"
        elif motion == "pan_right":
            x = f"(iw-iw/zoom)*{e}"
        elif motion == "pan_up":
            y = f"(ih-ih/zoom)*(1-{e})"
        else:
            y = f"(ih-ih/zoom)*{e}"
    else:  # static
        z, x, y = "1", "0", "0"

    if beat_sync and motion != "static":
        fpb = max(4.0, float(fps) * 60.0 / max(40.0, float(bpm or DEFAULT_BPM)))
        # Downbeat impact zoom kick + sub-beat bass pulse synced to BPM
        z = f"({z})+0.045*exp(-on/3.2)+0.022*exp(-mod(on,{fpb:.2f})/2.5)"

    return (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},setsar=1")


def color_chain(effects: Dict[str, Any], beat_sync: bool = False) -> str:
    parts = [COLOR_FILTERS.get(effects.get("filter") or "none", "")]
    if beat_sync or effects.get("beat_flash"):
        # Swxft beat-hit exposure flash & contrast punch on the cut downbeat
        parts.append("eq=brightness='0.15*exp(-t*18)':contrast='1+0.12*exp(-t*18)':eval=frame")
    if effects.get("vignette"):
        parts.append("vignette=angle=PI/4.5")
    return ",".join(p for p in parts if p)


def fade_chain(effects: Dict[str, Any], duration: float) -> str:
    parts = []
    if effects.get("fade_in"):
        parts.append(f"fade=t=in:st=0:d={FADE_SECONDS}")
    if effects.get("fade_out") and duration > FADE_SECONDS * 2:
        parts.append(f"fade=t=out:st={duration - FADE_SECONDS:.3f}:d={FADE_SECONDS}")
    return ",".join(parts)


def focus_mask(path: Path, w: int, h: int, focus: Dict[str, float], motion: str) -> Path:
    """Soft radial mask (white = sharp). Zoom/focus motions end centred on the focus point,
    so their mask sits at the frame centre; static/pan keep the focus point where it is."""
    from PIL import Image, ImageDraw, ImageFilter
    if motion in ("zoom_in", "zoom_out", "focus", "auto"):
        cx, cy = 0.5 * w, 0.5 * h
    else:
        cx, cy = float(focus.get("x", 0.5)) * w, float(focus.get("y", 0.45)) * h
    rx, ry = 0.36 * w, 0.26 * h
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
    m.filter(ImageFilter.GaussianBlur(radius=max(w, h) // 14)).save(path)
    return path


def build_image_filter(settings: Dict[str, Any], duration: float, fps: int, w: int, h: int, scene_idx: int,
                       overlay_input: Optional[int], mask_input: Optional[int]) -> str:
    """filter_complex for an image scene. Input 0 = image, overlay_input = layer overlay (optional),
    mask_input = focus-blur mask (optional). Output label [v]."""
    frames = max(int(round(duration * fps)), 1)
    fx = settings["effects"]
    speed_ramp = settings.get("speed_ramp") or "none"
    beat_sync = bool(settings.get("beat_sync") or fx.get("beat_flash"))
    bpm = float(settings.get("bpm") or DEFAULT_BPM)
    bg = _motion_filter(
        settings["motion"], settings["motion_strength"], settings["focus_point"],
        frames, fps, w, h, scene_idx,
        speed_ramp=speed_ramp, beat_sync=beat_sync, bpm=bpm,
    )
    color = color_chain(fx, beat_sync=beat_sync)
    chains = [f"[0:v]{bg}{(',' + color) if color else ''}[pre]"]
    last = "pre"
    if fx.get("focus_blur") and mask_input is not None:
        chains += [f"[{last}]split[sh][bl0]", "[bl0]gblur=sigma=14[bl]",
                   f"[{mask_input}:v]format=gray,scale={w}:{h}[mk]", "[sh][mk]alphamerge[sa]", "[bl][sa]overlay=0:0[fb]"]
        last = "fb"
    if overlay_input is not None:
        chains.append(f"[{overlay_input}:v]scale={w}:{h}[ovl]")  # fits full-size layers to preview sizes too
        chains.append(f"[{last}][ovl]overlay=0:0:shortest=1[ov]")
        last = "ov"
    fades = fade_chain(fx, duration)
    chains.append(f"[{last}]{(fades + ',') if fades else ''}format=yuv420p[v]")
    return ";".join(chains)


def clip_speed_ramp_vf(speed_ramp: str, duration: float) -> str:
    """
    Nonlinear PTS speed ramp for motion video clips:
    - 'velocity': 3.3x fast whip at cut entry & exit, 0.74x slow-motion hero hold in the middle
    - 'whip_in': 3.3x fast whip entry decelerating into slow-motion
    - 'whip_out': slow-motion start accelerating into 3.3x fast whip exit
    """
    dur = max(0.5, float(duration))
    u = f"min(1,max(0,T/{dur:.3f}))"
    # The ramp clamps every frame after `dur` to the same timestamp. With a looped (-stream_loop -1) input the
    # output clock would never pass `dur`, so ffmpeg's -t never fires and it reads forever. Trim the input first.
    head = f"trim=duration={dur:.3f},setpts=PTS-STARTPTS,"
    if speed_ramp == "velocity":
        # Smoothstep PTS curve -> derivative is 0.30 at u=0,1 (3.3x fast whip) and 1.35 at u=0.5 (slow-mo hold)
        g = f"(0.70*{u}*{u}*(3-2*{u})+0.30*{u})"
        return f"{head}setpts='({dur:.3f}/TB)*{g}'"
    if speed_ramp == "whip_in":
        g = f"(0.70*{u}*{u}+0.30*{u})"
        return f"{head}setpts='({dur:.3f}/TB)*{g}'"
    if speed_ramp == "whip_out":
        inv = f"(1-{u})"
        g = f"(0.70*(1-{inv}*{inv})+0.30*{u})"
        return f"{head}setpts='({dur:.3f}/TB)*{g}'"
    return ""


def clip_extra_vf(settings: Dict[str, Any], duration: float) -> str:
    """For video-clip scenes: speed ramp + beat flash + colour grade + vignette + fades."""
    fx = settings.get("effects") or {}
    speed_ramp = settings.get("speed_ramp") or "none"
    beat_sync = bool(settings.get("beat_sync") or fx.get("beat_flash"))
    parts = [
        clip_speed_ramp_vf(speed_ramp, duration),
        color_chain(fx, beat_sync=beat_sync),
        fade_chain(fx, duration),
    ]
    return ",".join(p for p in parts if p)
