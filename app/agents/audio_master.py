"""
Final loudness mastering for every rendered Short.

YouTube normalises playback to about -14 LUFS. Videos used to leave the mixer un-normalised (peaks
at -0.4 dBFS, loudness varying with the music track), so some Shorts sounded quieter than others
and peaks could clip after AAC encoding. master() measures the finished file and applies gain
to -14 LUFS with a soft pre-limiter, then a measured (linear) loudnorm pass for an exact level with
true-peak control (-1.5 dBTP ceiling). Video is
stream-copied, so this takes a second or two.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

TARGET_I = -14.0
TARGET_TP = -1.5             # headroom so AAC encoding stays under -1 dBTP
TARGET_LRA = 11.0
PRE_LIMIT = 0.708            # -3 dBFS soft pre-limiter: shaves voice transients so gain isn't peak-blocked


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def measure(path: str, prefilter: str = "") -> Optional[Dict[str, float]]:
    """loudnorm's measurement of the file's audio (after an optional prefilter chain), or None."""
    chain = (prefilter + "," if prefilter else "") + f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json"
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", chain, "-f", "null", "-"],
        capture_output=True, text=True, timeout=180)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    if not m:
        return None
    try:
        raw = json.loads(m.group(0))
        return {k: float(v) for k, v in raw.items() if k != "normalization_type"}
    except (ValueError, TypeError):
        return None


def master(video_path: str) -> Dict[str, Any]:
    """Normalises the video's audio in place. Never raises: returns a report, video untouched on failure."""
    path = Path(video_path)
    report: Dict[str, Any] = {"target_lufs": TARGET_I, "target_tp": TARGET_TP, "applied": False}
    try:
        m = measure(str(path))
        if not m:
            report["note"] = "no audio stream"
            return report
        report["before_lufs"] = round(m["input_i"], 1)
        report["before_tp"] = round(m["input_tp"], 1)
        if m["input_i"] < -60:  # silent (mute mode)
            report["note"] = "silent track; left as is"
            return report
        if abs(m["input_i"] - TARGET_I) <= 0.5 and m["input_tp"] <= TARGET_TP + 0.5:
            report["note"] = "already mastered"
            report["after_lufs"] = report["before_lufs"]
            return report
        # 1) gain to the target + soft pre-limiter (voice transients would otherwise block the gain)
        # 2) measure THAT signal, 3) loudnorm in linear mode with the measurement = an exact final gain
        #    with true-peak control. (A one-pass dynamic loudnorm overshot short clips: -12.8 LUFS on 10 s.)
        # Corrected once if it still lands >0.5 LU off; every attempt renders from the ORIGINAL audio.
        src = path.with_name(path.stem + ".premaster" + path.suffix)
        shutil.copyfile(path, src)
        tmp = path.with_name(path.stem + ".mastering" + path.suffix)
        gain = TARGET_I - m["input_i"]
        limit = PRE_LIMIT
        after: Dict[str, float] = {}
        try:
            for _ in range(4):
                pre = f"volume={gain:.2f}dB,alimiter=limit={limit:.3f}:attack=2:release=50:level=false"
                st = measure(str(src), pre) or {}
                if not st:
                    break
                af = (f"{pre},loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={max(TARGET_LRA, st['input_lra'] + 1):.1f}"
                      f":measured_I={st['input_i']}:measured_TP={st['input_tp']}:measured_LRA={st['input_lra']}"
                      f":measured_thresh={st['input_thresh']}:offset={st['target_offset']}:linear=true,aresample=48000")
                subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0",
                                "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                                str(tmp)], check=True, capture_output=True, timeout=300)
                after = measure(str(tmp)) or {}
                if not after:
                    break
                level_ok = abs(after["input_i"] - TARGET_I) <= 0.5
                peak_ok = after["input_tp"] <= TARGET_TP + 0.5  # <= -1.0 dBTP after AAC
                if level_ok and peak_ok:
                    break
                if not level_ok:
                    gain += TARGET_I - after["input_i"]
                if not peak_ok:
                    limit *= 0.84  # dense, hard-hitting tracks (phonk): limit transients 1.5 dB harder
            if tmp.exists():
                shutil.move(str(tmp), str(path))
        finally:
            src.unlink(missing_ok=True)
            tmp.unlink(missing_ok=True)
        report.update(applied=True, gain_db=round(gain, 1), after_lufs=round(after.get("input_i", TARGET_I), 1),
                      after_tp=round(after.get("input_tp", TARGET_TP), 1))
        print(f"[AudioMaster] Loudness {report['before_lufs']} -> {report['after_lufs']} LUFS "
              f"(peak {report['before_tp']} -> {report['after_tp']} dBTP)")
    except Exception as e:
        report["note"] = f"mastering skipped: {e}"
        print(f"[AudioMaster] {report['note']}")
    return report
