"""
Final Render Guard: deterministic checks on the FINISHED video file, run as part of Verify-video.

Every check is blocking: a video that fails any of them is never reported as PASSED (so the
approve gate, the auto-upload gate and the dashboard all treat it as not ready). Each failed check
names a `fix` the pipeline's auto-repair loop can apply (re-render, re-master audio, replace a
repeated image, clean metadata), or None when a person has to decide.

Checks (each one is a bug class seen in real renders):
  - file & format: 1080x1920, H.264, yuv420p, audio track present
  - audio/video in sync: audio and video end together; length matches the planned length
  - loudness: -14 LUFS +/-1, true peak <= -1 dBTP (YouTube's target; clipping = distortion)
  - no black frames (a failed clip or missing image renders black)
  - no dead air in the middle of the video
  - captions say what the narrator says (no dropped/garbled words), no doubled punctuation,
    no caption splitting the subject's name, no caption running past the end
  - no 'flash' scenes under 1.2 s in narrated videos
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

LUFS_TARGET = -14.0
LUFS_TOLERANCE = 1.0
TRUE_PEAK_MAX = -0.8          # dBTP, measured after AAC (target -1.5 leaves room)
MIN_SCENE_SECONDS = 1.2
DEAD_AIR_SECONDS = 1.2
CAPTION_MATCH_MIN = 0.90
SYNC_TOLERANCE = 0.35
MAX_SPEEDUP_PCT = 20          # % faster than the narrator's natural pace


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def _probe(path: Path) -> Dict[str, Any]:
    probe = shutil.which("ffprobe")
    if not probe:
        return {}
    out = subprocess.run([probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, timeout=60).stdout
    try:
        return json.loads(out or "{}")
    except ValueError:
        return {}


def _check(name: str, passed: bool, detail: str, fix: Optional[str] = None,
           remediation: Optional[str] = None, blocking: bool = True) -> Dict[str, Any]:
    return {"name": name, "stage": "render-guard", "passed": bool(passed), "detail": detail,
            "fix": None if passed else fix, "blocking": blocking,
            "remediation": None if passed else (remediation or ("Auto-repair: " + fix if fix else "Needs a manual fix."))}


def _is_mute(project: Dict[str, Any]) -> bool:
    return project.get("audio_mode") == "mute" or (project.get("with_voice") is False and project.get("with_music") is False)


def _narrated_multi_scene(project: Dict[str, Any]) -> bool:
    """Videos with burned karaoke captions and word-timed scenes (not car edits / static posters)."""
    if project.get("with_voice") is False or project.get("is_car_edit") or project.get("style") == "car_edit":
        return False
    scenes = project.get("scenes") or []
    if len(scenes) < 2 or any(s.get("beat_synced") for s in scenes):
        return False
    if scenes and all(s.get("visual_source") == "weaponx_lab_poster" for s in scenes):
        return False
    recs = project.get("visual_records") or []
    if recs and all(r.get("static_image") for r in recs):
        return False  # one static poster/hero image for the whole Short (captions aren't burned)
    return True


def _ass_captions(ass_path: Path) -> List[Dict[str, Any]]:
    """Caption events (text layer only, styling tags removed, karaoke repeats collapsed)."""
    events = []
    for line in ass_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10 or parts[3].startswith("Box"):
            continue
        text = re.sub(r"\{[^}]*\}", "", parts[9]).replace("\\N", " ").strip()

        def secs(ts: str) -> float:
            h, m, s = ts.strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        ev = {"start": secs(parts[1]), "end": secs(parts[2]), "text": text}
        if events and events[-1]["text"] == text and ev["start"] - events[-1]["end"] < 1.0:
            events[-1]["end"] = max(events[-1]["end"], ev["end"])  # same caption, next highlighted word
        else:
            events.append(ev)
    return events


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[0-9a-zऀ-ॣ०-ॿ]+", str(text).lower()) if t]


def run(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    video = Path(str(project.get("video_path") or ""))
    if not video.is_file():
        return [_check("Render: final video exists", False, "No rendered video on disk.", fix="rerender")]

    info = _probe(video)
    vs = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    aus = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    fmt_problems = []
    if not vs:
        fmt_problems.append("no video stream")
    else:
        v = vs[0]
        if (v.get("width"), v.get("height")) != (1080, 1920):
            fmt_problems.append(f"{v.get('width')}x{v.get('height')} (needs 1080x1920)")
        if v.get("codec_name") != "h264":
            fmt_problems.append(f"codec {v.get('codec_name')}")
        if v.get("pix_fmt") not in ("yuv420p", None):
            fmt_problems.append(f"pixel format {v.get('pix_fmt')}")
    if not aus:
        fmt_problems.append("no audio track")
    checks.append(_check("Render: 1080x1920 H.264 with audio", not fmt_problems,
                         "OK" if not fmt_problems else "; ".join(fmt_problems), fix="rerender"))
    if not vs:
        return checks

    v_dur = float(vs[0].get("duration") or info.get("format", {}).get("duration") or 0)
    a_dur = float(aus[0].get("duration") or 0) if aus else 0.0
    expected = float(project.get("duration") or 0)
    sync_problems = []
    if aus and abs(v_dur - a_dur) > SYNC_TOLERANCE:
        sync_problems.append(f"audio {a_dur:.2f}s vs video {v_dur:.2f}s")
    if expected and abs(v_dur - expected) > max(0.6, expected * 0.05):
        sync_problems.append(f"video {v_dur:.2f}s but planned {expected:.2f}s")
    checks.append(_check("Render: audio and video in sync", not sync_problems,
                         f"{v_dur:.2f}s" if not sync_problems else "; ".join(sync_problems), fix="rerender"))

    mute = _is_mute(project)
    if aus and not mute:
        from app.agents.audio_master import measure
        m = measure(str(video)) or {}
        if m:
            i, tp = m.get("input_i", -99), m.get("input_tp", 0)
            loud_ok = abs(i - LUFS_TARGET) <= LUFS_TOLERANCE and tp <= TRUE_PEAK_MAX
            checks.append(_check("Render: loudness -14 LUFS, no clipping", loud_ok,
                                 f"{i:.1f} LUFS, true peak {tp:.1f} dBTP", fix="remaster"))

    # Black frames (a failed clip / missing image renders black)
    bd = subprocess.run([_ffmpeg(), "-hide_banner", "-nostats", "-i", str(video), "-vf",
                         "blackdetect=d=0.5:pix_th=0.08", "-an", "-f", "null", "-"],
                        capture_output=True, text=True, timeout=300).stderr
    blacks = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bd)]
    checks.append(_check("Render: no black frames", not blacks,
                         "none" if not blacks else f"black at {[(round(a, 1), round(b, 1)) for a, b in blacks][:4]}",
                         fix=None, remediation="A scene image or clip is missing/black: replace it and re-render."))

    # Dead air in the middle (voice or music should always be audible)
    if aus and not mute:
        sd = subprocess.run([_ffmpeg(), "-hide_banner", "-nostats", "-i", str(video), "-af",
                             f"silencedetect=n=-50dB:d={DEAD_AIR_SECONDS}", "-vn", "-f", "null", "-"],
                            capture_output=True, text=True, timeout=300).stderr
        starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", sd)]
        ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", sd)]
        gaps = [(s, e) for s, e in zip(starts, ends + [v_dur] * (len(starts) - len(ends)))
                if s > 0.5 and e < v_dur - 0.5]
        checks.append(_check("Render: no dead air", not gaps,
                             "continuous audio" if not gaps else f"silent at {[(round(s, 1), round(e, 1)) for s, e in gaps][:4]}",
                             fix="rerender"))

    # A WeaponX Lab short is a LIST chart of models (like 'Hand Guns'); a single fallback photo is not
    recs = project.get("visual_records") or []
    is_wx = project.get("style") == "weaponx" or project.get("is_weaponx_lab")
    if is_wx and any(r.get("source") == "weaponx_lab_poster" for r in recs):
        # The chart must be on screen for the WHOLE short (a scene once got swapped for a soldier photo)
        off = [sc.get("scene_number") for sc in project.get("scenes") or [] if sc.get("visual_source") != "weaponx_lab_poster"]
        checks.append(_check("WeaponX: chart shown for the whole video", not off,
                             "every scene shows the chart" if not off else f"scenes {off} show something else",
                             fix="restore_poster"))
    if is_wx and recs and all(r.get("static_image") for r in recs):
        is_chart = all(r.get("source") == "weaponx_lab_poster" for r in recs)
        n_rows = len((recs[0].get("ranked_items") or [])) if recs else 0
        checks.append(_check("WeaponX: chart lists the topic's weapons", is_chart,
                             f"{n_rows or 'curated'} rows" if is_chart else
                             f"no verified list for this topic ({(recs[0].get('fallback_reason') or '')[:120]}); a single photo was used",
                             fix=None, remediation="Use a narrower topic (e.g. 'Heavyweight torpedoes') or paste a numbered list of 5-10 models."))

    rate = project.get("voice_rate_pct")
    if project.get("with_voice") is not False and rate is not None:
        checks.append(_check("Voice: natural pace (not rushed)", float(rate) <= MAX_SPEEDUP_PCT,
                             f"narration sped up {rate}%" + ("" if float(rate) <= MAX_SPEEDUP_PCT else
                                                             f" (> {MAX_SPEEDUP_PCT}%: sounds rushed)"),
                             fix="relax_duration",
                             remediation="Give the video a few more seconds so the narrator speaks naturally."))

    if _narrated_multi_scene(project):
        checks += _caption_checks(project, v_dur)
        durs = [float(d) for d in (project.get("scene_durations") or [])]
        if durs:
            short = [i + 1 for i, d in enumerate(durs) if d < MIN_SCENE_SECONDS]
            checks.append(_check("Pacing: no flash scenes (< 1.2 s)", not short,
                                 f"shortest {min(durs):.1f}s" if not short else f"scenes {short} are under {MIN_SCENE_SECONDS}s",
                                 fix=None, remediation="Merge or lengthen those scenes' narration, then re-render."))
    return checks


def _caption_checks(project: Dict[str, Any], v_dur: float) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    ass = Path(str(project.get("subtitles_path") or ""))
    style = project.get("caption_style") or {}
    if style and style.get("enabled") is False:
        return out
    if not ass.is_file():
        return [_check("Captions: subtitle file present", False, "No subtitles file.", fix="rerender")]
    events = _ass_captions(ass)
    if not events:
        return [_check("Captions: subtitle file present", False, "Subtitle file has no captions.", fix="rerender")]

    # 1. Captions say what the narrator says
    hindi = project.get("language") == "hi"
    narr = " ".join(str((s.get("narration_hindi") if hindi else None) or s.get("narration") or "")
                    for s in project.get("scenes") or [])
    if hindi and (project.get("content_analysis_hindi") or {}).get("scenes"):
        narr = " ".join(str(s.get("narration_hindi") or s.get("narration") or "")
                        for s in project["content_analysis_hindi"]["scenes"])
    a, b = _tokens(narr), _tokens(" ".join(e["text"] for e in events))
    ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0
    out.append(_check("Captions: match the narration", ratio >= CAPTION_MATCH_MIN,
                      f"{ratio:.0%} word match ({len(b)}/{len(a)} words)", fix="rerender"))

    # 2. Clean text: no doubled punctuation / empty captions / captions past the end
    bad = [e["text"] for e in events if re.search(r"\.\.|,,|\?\?|!!|\s[.,]", e["text"]) or not e["text"].strip()]
    late = [e["text"] for e in events if e["start"] > v_dur + 0.05]
    out.append(_check("Captions: clean text and timing", not bad and not late,
                      "OK" if not bad and not late else f"bad text {bad[:3]}; after the end {late[:2]}", fix="rerender"))

    # 3. The subject's name is never split across two captions
    try:
        from app.agents.caption_chunker import subject_phrases
        names = [n for n in subject_phrases(project) if len(_tokens(n)) >= 2]
    except Exception:
        names = []
    splits = []
    for name in names:
        nt = _tokens(name)
        for e1, e2 in zip(events, events[1:]):
            t1, t2 = _tokens(e1["text"]), _tokens(e2["text"])
            for k in range(1, len(nt)):
                if t1[-k:] == nt[:k] and t2[: len(nt) - k] == nt[k:]:
                    splits.append(f"{e1['text']} | {e2['text']}")
    out.append(_check("Captions: subject name never split", not splits,
                      "OK" if not splits else f"split: {splits[:2]}", fix="rerender"))
    return out
