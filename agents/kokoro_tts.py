"""
Kokoro-82M local text-to-speech (free, Apache-2.0): more natural than Edge-TTS, runs on this Mac.

synthesize(text, voice, speed, out_mp3) -> list of word timings [{"text","start","end"}]
The pipeline is loaded once per process (~17 s, ~350 MB). English voices: am_michael (default),
am_onyx, am_fenrir, am_adam, bm_george, bm_lewis, af_heart ...
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_VOICE = os.getenv("KOKORO_VOICE", "am_michael")
SAMPLE_RATE = 24000
_pipe = None
_lock = threading.Lock()
_load_error: Optional[str] = None


def _pipeline():
    global _pipe, _load_error
    if _pipe is not None or _load_error:
        return _pipe
    with _lock:
        if _pipe is None and not _load_error:
            try:
                from kokoro import KPipeline
                _pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
            except Exception as e:
                _load_error = f"{type(e).__name__}: {e}"
    return _pipe


def is_available() -> bool:
    return _pipeline() is not None


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def synthesize(text: str, out_mp3: Path, voice: Optional[str] = None, speed: float = 1.0) -> List[Dict]:
    import numpy as np
    import soundfile as sf

    pipe = _pipeline()
    if pipe is None:
        raise RuntimeError(f"Kokoro unavailable: {_load_error}")
    voice = voice or DEFAULT_VOICE
    chunks, words = [], []
    offset = 0.0
    with _lock:  # the pipeline isn't thread-safe
        for r in pipe(text, voice=voice, speed=max(0.7, min(1.6, speed))):
            audio = r.audio.numpy() if hasattr(r.audio, "numpy") else np.asarray(r.audio)
            for tok in (r.tokens or []):
                if tok.start_ts is None or not any(ch.isalnum() for ch in tok.text):
                    continue  # punctuation tokens are not spoken words
                words.append({"text": tok.text, "start": round(offset + tok.start_ts, 3), "end": round(offset + tok.end_ts, 3)})
            chunks.append(audio)
            offset += len(audio) / SAMPLE_RATE
    if not chunks:
        raise RuntimeError("Kokoro produced no audio")
    out_mp3 = Path(out_mp3)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        sf.write(tmp.name, np.concatenate(chunks), SAMPLE_RATE)
        wav = tmp.name
    try:
        subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-i", wav, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-ar", "24000", "-codec:a", "libmp3lame", "-b:a", "128k", str(out_mp3)],
                       check=True, capture_output=True)
    finally:
        os.unlink(wav)
    return words


def to_srt(words: List[Dict], words_per_cue: int = 6) -> str:
    def ts(t: float) -> str:
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    cues = []
    for i in range(0, len(words), words_per_cue):
        grp = words[i:i + words_per_cue]
        cues.append(f"{len(cues) + 1}\n{ts(grp[0]['start'])} --> {ts(grp[-1]['end'])}\n{' '.join(w['text'] for w in grp)}\n")
    return "\n".join(cues)
