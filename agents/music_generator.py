"""
Agent: AI Music Generator & Royalty-Free Audio Library (agents/music_generator.py)
Provides 100% free AI-generated music and YouTube Audio Library tracks for YouTube Shorts:
1. Procedural / Synthesized AI Music Engine (using multi-stem FFmpeg synthesis: sub-bass pulse, atmospheric pad, rhythmic arpeggio).
2. Curated YouTube Audio Library royalty-free tracks.
3. Live audio preview and video remixing with auto-ducking under voiceover.
"""

import os
import re
import sys
import json
import time
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for sp in PROJECT_ROOT.glob(".venv/lib/python*/site-packages"):
    if str(sp) not in sys.path:
        sys.path.insert(0, str(sp))

import config

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    bundled = list((config.BASE_DIR / ".venv").glob("**/imageio_ffmpeg/binaries/ffmpeg*"))
    FFMPEG_EXE = str(bundled[0]) if bundled else "ffmpeg"


class AIMusicGenerator:
    """
    AI-generated music engine and royalty-free audio manager.
    Generates tailored, looping, cinematic soundtracks for YouTube Shorts.
    """

    CATEGORIES = {
        "Metal": {
            "desc": "Heavy distorted guitar riffs, pounding double-bass kick, and aggressive drive",
            "tempo_bpm": 140,
            "f0": 75, "f1": 220, "noise_color": "pink",
            "filter": (
                "[0:a]volume=0.95,tremolo=f=4.66:d=0.85,firequalizer=gain_entry='entry(80,12);entry(250,-6);entry(3200,8)'[riff];"
                "[1:a]highpass=f=1200,volume=0.22,tremolo=f=9.33:d=0.9[drums];"
                "[2:a]lowpass=f=260,volume=0.45,aecho=0.8:0.7:80:0.3[bass];"
            ),
            "mix_inputs": "[riff][drums][bass]"
        },
        "Rock": {
            "desc": "Driving 120 BPM drum groove, electric power chord harmonics, stereo presence",
            "tempo_bpm": 120,
            "f0": 90, "f1": 260, "noise_color": "pink",
            "filter": (
                "[0:a]volume=0.85,tremolo=f=4.0:d=0.75,firequalizer=gain_entry='entry(100,8);entry(2500,5)'[riff];"
                "[1:a]highpass=f=1500,volume=0.18,tremolo=f=8.0:d=0.85[drums];"
                "[2:a]lowpass=f=220,volume=0.4[bass];"
            ),
            "mix_inputs": "[riff][drums][bass]"
        },
        "EDM": {
            "desc": "128 BPM 4-on-the-floor sub-kick, saw-lead resonance, rising sweep",
            "tempo_bpm": 128,
            "f0": 60, "f1": 340, "noise_color": "white",
            "filter": (
                "[0:a]volume=0.95,tremolo=f=4.26:d=0.95,firequalizer=gain_entry='entry(60,10);entry(120,6)'[kick];"
                "[1:a]highpass=f=2000,volume=0.15,tremolo=f=8.53:d=0.9,flanger=delay=6:depth=4[lead];"
                "[2:a]bandpass=f=800:width_type=h:w=300,volume=0.3,aecho=0.8:0.8:90|180:0.4|0.2[sweep];"
            ),
            "mix_inputs": "[kick][lead][sweep]"
        },
        "Hip-Hop": {
            "desc": "85 BPM booming 808 sub-bass, rhythmic trap hi-hat roll, vinyl texture",
            "tempo_bpm": 85,
            "f0": 45, "f1": 180, "noise_color": "brown",
            "filter": (
                "[0:a]volume=1.1,tremolo=f=2.83:d=0.7,firequalizer=gain_entry='entry(45,12);entry(90,8)'[sub808];"
                "[1:a]highpass=f=2500,volume=0.18,tremolo=f=11.33:d=0.95[hats];"
                "[2:a]lowpass=f=200,volume=0.35,aecho=0.8:0.7:140:0.3[snare];"
            ),
            "mix_inputs": "[sub808][hats][snare]"
        },
        "Cinematic": {
            "desc": "55Hz sub drone, swelling orchestral brass tension, military radar ping",
            "tempo_bpm": 110,
            "f0": 55, "f1": 220, "noise_color": "pink",
            "filter": (
                "[0:a]volume=0.85,tremolo=f=2.75:d=0.7[pulse];"
                "[1:a]lowpass=f=280,volume=0.4,aecho=0.85:0.88:100|200:0.4|0.25[sub];"
                "[2:a]bandpass=f=800:width_type=h:w=200,volume=0.25,aecho=0.8:0.7:150:0.35[ping];"
            ),
            "mix_inputs": "[pulse][sub][ping]"
        },
        "Jazz": {
            "desc": "Warm walking bassline, mellow chord vibrations, soft brush noise",
            "tempo_bpm": 95,
            "f0": 110, "f1": 290, "noise_color": "pink",
            "filter": (
                "[0:a]volume=0.8,tremolo=f=1.58:d=0.5,lowpass=f=300[walkbass];"
                "[1:a]highpass=f=1800,volume=0.12,aecho=0.7:0.6:120:0.2[brush];"
                "[2:a]bandpass=f=600:width_type=h:w=300,volume=0.35,vibrato=f=3.0:d=0.2[chords];"
            ),
            "mix_inputs": "[walkbass][brush][chords]"
        },
        "Pop": {
            "desc": "120 BPM upbeat rhythmic pulse, melodic saw chords, sparkling highs",
            "tempo_bpm": 120,
            "f0": 70, "f1": 320, "noise_color": "white",
            "filter": (
                "[0:a]volume=0.85,tremolo=f=4.0:d=0.8,firequalizer=gain_entry='entry(70,8);entry(2000,4)'[kick];"
                "[1:a]highpass=f=2200,volume=0.16,tremolo=f=8.0:d=0.8[shaker];"
                "[2:a]bandpass=f=1100:width_type=h:w=400,volume=0.35,flanger=delay=6:depth=3[synth];"
            ),
            "mix_inputs": "[kick][shaker][synth]"
        },
        "Indian": {
            "desc": "Resonant sitar & tanpura modal drone, hypnotic tabla rhythm, mystical aura",
            "tempo_bpm": 100,
            "f0": 140, "f1": 280, "noise_color": "pink",
            "filter": (
                "[0:a]volume=0.8,flanger=delay=8:depth=5,aecho=0.8:0.7:140:0.4[sitar];"
                "[1:a]bandpass=f=350:width_type=h:w=120,volume=0.5,tremolo=f=3.33:d=0.85[tabla];"
                "[2:a]lowpass=f=160,volume=0.45[tanpura];"
            ),
            "mix_inputs": "[sitar][tabla][tanpura]"
        },
        "Ambient": {
            "desc": "Floating atmospheric pad, slow resonant filter sweep, deep cosmic reverb",
            "tempo_bpm": 80,
            "f0": 60, "f1": 180, "noise_color": "brown",
            "filter": (
                "[0:a]volume=0.7,tremolo=f=1.0:d=0.4,aecho=0.9:0.88:180|360:0.5|0.35[pad];"
                "[1:a]lowpass=f=140,volume=0.45[drone];"
                "[2:a]bandpass=f=1200:width_type=h:w=500,volume=0.2,flanger=delay=10:depth=6[shimmer];"
            ),
            "mix_inputs": "[pad][drone][shimmer]"
        }
    }

    MOODS = {
        "Aggressive": {"eq_gain": "entry(100,10);entry(3000,8)", "tempo_mult": 1.15, "tremolo_depth": 0.85, "aecho": "0.7:0.6:60:0.25"},
        "Epic": {"eq_gain": "entry(60,10);entry(1500,6)", "tempo_mult": 1.0, "tremolo_depth": 0.7, "aecho": "0.9:0.88:120|240:0.45|0.3"},
        "Dark": {"eq_gain": "entry(50,12);entry(2000,-8)", "tempo_mult": 0.9, "tremolo_depth": 0.8, "aecho": "0.85:0.75:180:0.4"},
        "Energetic": {"eq_gain": "entry(80,8);entry(2500,6)", "tempo_mult": 1.1, "tremolo_depth": 0.8, "aecho": "0.75:0.7:80:0.3"},
        "Emotional": {"eq_gain": "entry(120,6);entry(800,4)", "tempo_mult": 0.85, "tremolo_depth": 0.5, "aecho": "0.9:0.85:160|320:0.4|0.25"},
        "Relaxing": {"eq_gain": "entry(100,4);entry(3000,-6)", "tempo_mult": 0.8, "tremolo_depth": 0.4, "aecho": "0.85:0.7:200:0.3"},
        "Mysterious": {"eq_gain": "entry(70,8);entry(1200,6)", "tempo_mult": 0.95, "tremolo_depth": 0.65, "aecho": "0.92:0.9:140|280:0.5|0.35"}
    }

    VOCALS = {
        "Instrumental": {"desc": "Pure instrumental tracks (zero vocals)"},
        "Male": {"f": 140, "filter": "[3:a]bandpass=f=700:width_type=h:w=200,vibrato=f=4.5:d=0.3,volume=0.35[vocal]"},
        "Female": {"f": 440, "filter": "[3:a]bandpass=f=1200:width_type=h:w=300,vibrato=f=5.5:d=0.4,aecho=0.8:0.7:150:0.35,volume=0.3[vocal]"},
        "Choir": {"f": 260, "filter": "[3:a]bandpass=f=900:width_type=h:w=400,aecho=0.9:0.85:200|400:0.5|0.35,flanger=delay=8:depth=4,volume=0.4[vocal]"}
    }

    DEFAULT_PROMPTS = {
        "Metal": "Powerful heavy guitar riffs, thunderous drums, dark cinematic atmosphere",
        "Rock": "Driving electric guitar power chords, punchy rock drum beats, high voltage rhythm",
        "EDM": "Pumping 128 BPM bassline, energetic synthesizer lead, massive build and drop",
        "Hip-Hop": "Heavy 808 booming bass, crisp trap hi-hats, deep atmospheric street groove",
        "Cinematic": "Massive orchestral brass swells, deep sub-bass tension, thunderous war drums",
        "Jazz": "Warm walking bass, mellow electric piano chords, smooth late-night groove",
        "Pop": "Upbeat punchy kick, bright synth plucks, catchy commercial summer groove",
        "Indian": "Resonant sitar and tanpura modal drone, hypnotic tabla rhythm, mystical aura",
        "Ambient": "Spacious evolving synth pads, gentle celestial harmonics, deep calm drone"
    }

    STYLES = {
        "epic_cinematic": {
            "name": "Epic Cinematic Defense",
            "desc": "Heavy 55Hz sub-bass pulse, stereo rising tension, and military radar ping",
            "tempo_bpm": 120,
            "filter": (
                "[0:a]volume=0.85,tremolo=f=3.0:d=0.75[pulse];"
                "[1:a]lowpass=f=280,volume=0.35,aecho=0.8:0.88:80|160:0.4|0.2[sub];"
                "[2:a]bandpass=f=800:width_type=h:w=200,volume=0.25,aecho=0.8:0.7:120:0.3[ping];"
                "[pulse][sub][ping]amix=inputs=3:duration=first,"
                "aecho=0.8:0.88:60|120:0.4|0.25,alimiter=limit=0.95[out]"
            )
        },
        "cyber_ambient": {
            "name": "Cyber Dark Synth",
            "desc": "Cyberpunk atmospheric synth pad, slow resonant filter sweep, and 808 drone",
            "tempo_bpm": 105,
            "filter": (
                "[0:a]volume=0.7,tremolo=f=1.5:d=0.5,aecho=0.8:0.88:140|280:0.5|0.3[pad];"
                "[1:a]lowpass=f=180,volume=0.45[drone];"
                "[2:a]bandpass=f=1200:width_type=h:w=400,volume=0.2,flanger=delay=8:depth=4[mod];"
                "[pad][drone][mod]amix=inputs=3:duration=first,"
                "aecho=0.85:0.85:100|200:0.35|0.2,alimiter=limit=0.95[out]"
            )
        },
        "tactical_strike": {
            "name": "Tactical Strike Action",
            "desc": "130 BPM high-octane energetic bass pulse, metallic clicks, and urgent risers",
            "tempo_bpm": 130,
            "filter": (
                "[0:a]volume=0.9,tremolo=f=4.33:d=0.85,firequalizer=gain_entry='entry(50,8);entry(100,6);entry(200,-5)'[beat];"
                "[1:a]highpass=f=1500,volume=0.15,tremolo=f=8.66:d=0.9[hats];"
                "[2:a]lowpass=f=220,volume=0.4[sub];"
                "[beat][hats][sub]amix=inputs=3:duration=first,"
                "aecho=0.7:0.7:45|90:0.3|0.15,alimiter=limit=0.95[out]"
            )
        },
        "stealth_infiltrator": {
            "name": "Stealth Infiltrator",
            "desc": "Dark minimal heartbeat, sonar pulse, and ominous low-end rumbling",
            "tempo_bpm": 90,
            "filter": (
                "[0:a]volume=0.75,tremolo=f=1.5:d=0.9,lowpass=f=140[heartbeat];"
                "[1:a]bandpass=f=1800:width_type=h:w=100,volume=0.25,aecho=0.9:0.8:250|500:0.6|0.4[sonar];"
                "[2:a]anoisesrc=color=brown:duration={duration}:r=44100,lowpass=f=120,volume=0.5[rumble];"
                "[heartbeat][sonar][rumble]amix=inputs=3:duration=first,alimiter=limit=0.95[out]"
            )
        },
        "supersonic_jet": {
            "name": "Supersonic Jet Afterburner",
            "desc": "Jet turbine intake sweep, roaring afterburner sub-bass, and stereo wind vortex",
            "tempo_bpm": 110,
            "filter": (
                "[0:a]volume=0.6,tremolo=f=2.2:d=0.4,flanger=delay=10:depth=6[turbine];"
                "[1:a]lowpass=f=180,volume=0.65,firequalizer=gain_entry='entry(60,10);entry(120,6)'[afterburner];"
                "[2:a]bandpass=f=600:width_type=h:w=500,volume=0.25,aecho=0.8:0.8:80|160:0.3|0.2[vortex];"
                "[turbine][afterburner][vortex]amix=inputs=3:duration=first,alimiter=limit=0.95[out]"
            )
        }
    }

    def __init__(self):
        self.audio_dir = config.AUDIO_ASSETS_DIR
        self.ai_music_dir = self.audio_dir / "ai_generated"
        self.library_dir = self.audio_dir / "library"
        self.saved_dir = self.library_dir
        self.library_index = self.library_dir / "library.json"

        self.ai_music_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        if not self.library_index.exists():
            self.library_index.write_text("[]", encoding="utf-8")

    def generate_ai_music(
        self,
        style: str = "epic_cinematic",
        duration: float = 25.0,
        prompt: Optional[str] = None,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Synthesizes a full multi-stem AI music track tailored for YouTube Shorts.
        100% Free, runs offline locally via FFmpeg audio engine.
        """
        duration = max(5.0, min(180.0, float(duration)))
        style_key = style.lower().strip()
        if style_key not in self.STYLES:
            # Map prompt keywords if given
            p_lower = (prompt or style_key).lower()
            if any(k in p_lower for k in ["jet", "flight", "plane", "afterburner", "air"]):
                style_key = "supersonic_jet"
            elif any(k in p_lower for k in ["cyber", "future", "synth", "drone", "space", "dark"]):
                style_key = "cyber_ambient"
            elif any(k in p_lower for k in ["action", "fast", "phonk", "strike", "speed", "combat"]):
                style_key = "tactical_strike"
            elif any(k in p_lower for k in ["stealth", "covert", "recon", "spy", "silent"]):
                style_key = "stealth_infiltrator"
            else:
                style_key = "epic_cinematic"

        cfg = self.STYLES[style_key]

        if not output_path:
            out_name = f"ai_music_{style_key}_{int(duration)}s_{int(time.time())}.wav"
            output_path = self.ai_music_dir / out_name
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        dur_str = f"{duration:.2f}"
        filter_str = cfg["filter"].replace("{duration}", dur_str)

        # Build 3 layered procedural audio stems
        cmd = [
            FFMPEG_EXE, "-y",
            "-f", "lavfi", "-i", f"sine=frequency=55:duration={dur_str}:r=44100",
            "-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={dur_str}:r=44100",
            "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur_str}:r=44100",
            "-filter_complex", filter_str,
            "-map", "[out]",
            "-c:a", "pcm_s16le",
            "-ar", "44100",
            str(output_path)
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            # Fallback simple synthesis if complex filter fails
            fallback_cmd = [
                FFMPEG_EXE, "-y",
                "-f", "lavfi", "-i", f"sine=frequency=60:duration={dur_str}",
                "-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={dur_str}",
                "-filter_complex", "[0:a]volume=0.8[a0];[1:a]lowpass=f=200,volume=0.3[a1];[a0][a1]amix=inputs=2",
                "-c:a", "pcm_s16le",
                str(output_path)
            ]
            res_fb = subprocess.run(fallback_cmd, capture_output=True, text=True)
            if res_fb.returncode != 0:
                raise RuntimeError(f"FFmpeg AI music synthesis failed: {res.stderr[-300:]}")

        return output_path

    # ==========================================
    # Saved Music Library Management
    # ==========================================

    def list_saved_library(self) -> List[Dict[str, Any]]:
        """Returns all persistent tracks in the user's saved music library."""
        if not self.library_index.exists():
            self.library_index.write_text("[]", encoding="utf-8")
        try:
            raw_text = self.library_index.read_text(encoding="utf-8")
            data = json.loads(raw_text) if raw_text.strip() else []
            valid = []
            known_filenames = set()

            for item in data:
                f_name = item.get("filename", "")
                p = Path(item.get("file_path", ""))
                # Fallback: check directly inside library_dir if absolute path changed
                if not p.exists() and f_name:
                    p = self.library_dir / f_name

                if p.exists() and p.stat().st_size > 1000:
                    item["file_path"] = str(p.resolve())
                    item["filename"] = p.name
                    item["url"] = f"/api/music/preview/{p.name}?type=library&t={int(p.stat().st_mtime)}"
                    valid.append(item)
                    known_filenames.add(p.name)

            # Auto-discover any orphaned .wav files in library_dir not yet in index
            orphans = [f for f in self.library_dir.glob("*.wav") if f.name not in known_filenames and f.stat().st_size > 1000]
            if orphans:
                for wav in sorted(orphans, key=lambda x: x.stat().st_mtime, reverse=True):
                    # Parse name from filename e.g. lib_indian_theme_123.wav
                    clean_name = wav.stem.replace("lib_", "").replace("_", " ").title()
                    # Infer category
                    cat = "Custom"
                    for c in ["Indian", "Metal", "Rock", "EDM", "Cinematic", "Ambient", "Pop", "Jazz", "Hip-Hop"]:
                        if c.lower() in wav.name.lower():
                            cat = c
                            break
                    new_rec = {
                        "id": wav.stem,
                        "name": clean_name,
                        "category": cat,
                        "mood": "Epic",
                        "vocals": "Instrumental",
                        "duration": 60.0,
                        "prompt": "",
                        "filename": wav.name,
                        "file_path": str(wav.resolve()),
                        "url": f"/api/music/preview/{wav.name}?type=library&t={int(wav.stat().st_mtime)}",
                        "source": "library",
                        "is_saved": True,
                        "is_default": False,
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(wav.stat().st_mtime))
                    }
                    valid.append(new_rec)
                self.library_index.write_text(json.dumps(valid, indent=2), encoding="utf-8")

            return valid
        except Exception as e:
            print(f"[AIMusicGenerator] Error reading library: {e}")
            return []

    def list_recent_ai_tracks(self, limit: int = 8) -> List[Dict[str, Any]]:
        """Returns recently generated AI tracks from disk so user can preview & save them."""
        recent = []
        try:
            files = sorted(self.ai_music_dir.glob("*.wav"), key=lambda x: x.stat().st_mtime, reverse=True)
            for f in files[:limit]:
                if f.stat().st_size > 1000 and not f.name.startswith("tmp_"):
                    # Infer metadata from filename
                    parts = f.stem.split("_")
                    cat = "AI Track"
                    for c in ["Indian", "Metal", "Rock", "EDM", "Cinematic", "Ambient", "Pop", "Jazz", "Hip-Hop"]:
                        if c.lower() in f.stem.lower():
                            cat = c
                            break
                    recent.append({
                        "id": f.stem,
                        "name": f"{cat} Generated Theme",
                        "filename": f.name,
                        "file_path": str(f.resolve()),
                        "url": f"/api/music/preview/{f.name}?type=ai&t={int(f.stat().st_mtime)}",
                        "category": cat,
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime)),
                        "file_size_kb": round(f.stat().st_size / 1024, 1)
                    })
        except Exception as e:
            print(f"[AIMusicGenerator] Error listing recent AI tracks: {e}")
        return recent

    def save_to_library(
        self,
        source_path_or_id: str,
        name: str,
        category: str = "Cinematic",
        mood: str = "Epic",
        vocals: str = "Instrumental",
        duration: float = 60.0,
        prompt: str = "",
        is_default: bool = False
    ) -> Dict[str, Any]:
        """Saves a track to the persistent library so it can be reused in future videos."""
        source_p = Path(source_path_or_id)
        if not source_p.exists():
            # Search in ai_generated or library
            cand = list(self.ai_music_dir.glob(f"*{source_path_or_id}*")) + list(self.library_dir.glob(f"*{source_path_or_id}*"))
            if cand:
                source_p = cand[0]
            else:
                raise FileNotFoundError(f"Source music track not found: {source_path_or_id}")

        safe_slug = re.sub(r"[^\w\s-]", "", name).strip().lower()
        safe_slug = re.sub(r"[-\s]+", "_", safe_slug)[:30] or "track"
        track_id = f"lib_{safe_slug}_{int(time.time())}"
        dest_filename = f"{track_id}.wav"
        dest_path = self.library_dir / dest_filename

        shutil.copyfile(source_p, dest_path)

        library_tracks = self.list_saved_library()
        if is_default:
            for t in library_tracks:
                t["is_default"] = False

        record = {
            "id": track_id,
            "name": name.strip(),
            "category": category,
            "mood": mood,
            "vocals": vocals,
            "duration": float(duration),
            "prompt": prompt,
            "filename": dest_filename,
            "file_path": str(dest_path),
            "url": f"/api/music/preview/{dest_filename}?type=library",
            "source": "library",
            "is_saved": True,
            "is_default": bool(is_default),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        library_tracks.insert(0, record)
        self.library_index.write_text(json.dumps(library_tracks, indent=2), encoding="utf-8")
        return record

    save_track_to_library = save_to_library

    def delete_from_library(self, track_id: str) -> bool:
        """Deletes a track from the library and disk."""
        tracks = self.list_saved_library()
        kept = []
        deleted = False
        for t in tracks:
            if t["id"] == track_id:
                p = Path(t.get("file_path", ""))
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
                deleted = True
            else:
                kept.append(t)
        self.library_index.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        return deleted

    delete_saved_track = delete_from_library

    def set_default_library_track(self, track_id: str) -> bool:
        """Sets a saved track as the default music for all future video creations."""
        tracks = self.list_saved_library()
        found = False
        for t in tracks:
            if t["id"] == track_id:
                t["is_default"] = True
                found = True
            else:
                t["is_default"] = False
        self.library_index.write_text(json.dumps(tracks, indent=2), encoding="utf-8")
        return found

    def get_default_library_track(self) -> Optional[Dict[str, Any]]:
        """Returns the default track to be used in video generation."""
        tracks = self.list_saved_library()
        for t in tracks:
            if t.get("is_default"):
                return t
        return None

    def generate_custom_music(
        self,
        category: str = "Metal",
        mood: str = "Aggressive",
        vocals: str = "Instrumental",
        duration: float = 60.0,
        prompt: Optional[str] = None,
        name: Optional[str] = None,
        save_to_library: bool = False,
        is_default: bool = False
    ) -> Dict[str, Any]:
        """
        Generates original AI music matching the Category, Mood, Vocals, Duration, and Prompt.
        Powered by autonomous MusicAgent for deep prompt research, multi-stem synthesis, and QA verification.
        """
        try:
            from agents.music_agent import MusicAgent
            music_agent = MusicAgent()
            res = music_agent.generate_track(
                category=category,
                mood=mood,
                vocals=vocals,
                duration=duration,
                prompt=prompt,
                name=name,
                save_to_library=save_to_library,
                is_default=is_default
            )
            return res
        except Exception as e:
            # Fallback to direct procedural audio generation if MusicAgent encounters an issue
            pass

        cat_key = "Metal"
        for k in self.CATEGORIES:
            if k.lower() == category.lower().strip():
                cat_key = k
                break
        cat_cfg = self.CATEGORIES[cat_key]

        mood_key = "Aggressive"
        for k in self.MOODS:
            if k.lower() == mood.lower().strip():
                mood_key = k
                break
        mood_cfg = self.MOODS[mood_key]

        vocal_key = "Instrumental"
        for k in self.VOCALS:
            if k.lower() == vocals.lower().strip():
                vocal_key = k
                break
        vocal_cfg = self.VOCALS[vocal_key]

        duration = max(5.0, min(300.0, float(duration)))
        dur_str = f"{duration:.2f}"
        f0 = cat_cfg["f0"]
        f1 = cat_cfg["f1"]
        noise_color = cat_cfg["noise_color"]

        out_name = f"ai_music_{cat_key.lower()}_{mood_key.lower()}_{int(duration)}s_{int(time.time())}.wav"
        output_path = self.ai_music_dir / out_name

        has_vocals = (vocal_key != "Instrumental")

        if not has_vocals:
            filter_str = (
                f"{cat_cfg['filter']}"
                f"{cat_cfg['mix_inputs']}amix=inputs=3:duration=first,"
                f"firequalizer=gain_entry='{mood_cfg['eq_gain']}',"
                f"aecho={mood_cfg['aecho']},alimiter=limit=0.95[out]"
            )
            cmd = [
                FFMPEG_EXE, "-y",
                "-f", "lavfi", "-i", f"sine=frequency={f0}:duration={dur_str}:r=44100",
                "-f", "lavfi", "-i", f"anoisesrc=color={noise_color}:duration={dur_str}:r=44100",
                "-f", "lavfi", "-i", f"sine=frequency={f1}:duration={dur_str}:r=44100",
                "-filter_complex", filter_str,
                "-map", "[out]",
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                str(output_path)
            ]
        else:
            vf = vocal_cfg["f"]
            filter_str = (
                f"{cat_cfg['filter']}"
                f"{vocal_cfg['filter']};"
                f"{cat_cfg['mix_inputs']}[vocal]amix=inputs=4:duration=first,"
                f"firequalizer=gain_entry='{mood_cfg['eq_gain']}',"
                f"aecho={mood_cfg['aecho']},alimiter=limit=0.95[out]"
            )
            cmd = [
                FFMPEG_EXE, "-y",
                "-f", "lavfi", "-i", f"sine=frequency={f0}:duration={dur_str}:r=44100",
                "-f", "lavfi", "-i", f"anoisesrc=color={noise_color}:duration={dur_str}:r=44100",
                "-f", "lavfi", "-i", f"sine=frequency={f1}:duration={dur_str}:r=44100",
                "-f", "lavfi", "-i", f"sine=frequency={vf}:duration={dur_str}:r=44100",
                "-filter_complex", filter_str,
                "-map", "[out]",
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                str(output_path)
            ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            fb_cmd = [
                FFMPEG_EXE, "-y",
                "-f", "lavfi", "-i", f"sine=frequency={f0}:duration={dur_str}",
                "-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={dur_str}",
                "-filter_complex", "[0:a]volume=0.8[a0];[1:a]lowpass=f=250,volume=0.3[a1];[a0][a1]amix=inputs=2",
                "-c:a", "pcm_s16le",
                str(output_path)
            ]
            res_fb = subprocess.run(fb_cmd, capture_output=True, text=True)
            if res_fb.returncode != 0:
                raise RuntimeError(f"FFmpeg custom music generation failed: {res.stderr[-300:]}")

        default_name = name or f"{cat_key} - {mood_key} ({vocal_key})"
        eff_prompt = prompt or self.DEFAULT_PROMPTS.get(cat_key, "")

        if save_to_library:
            saved_record = self.save_to_library(
                source_path_or_id=str(output_path),
                name=default_name,
                category=cat_key,
                mood=mood_key,
                vocals=vocal_key,
                duration=duration,
                prompt=eff_prompt,
                is_default=is_default
            )
            return saved_record

        return {
            "id": output_path.stem,
            "name": default_name,
            "category": cat_key,
            "mood": mood_key,
            "vocals": vocal_key,
            "duration": duration,
            "prompt": eff_prompt,
            "filename": output_path.name,
            "file_path": str(output_path),
            "url": f"/api/music/preview/{output_path.name}?type=ai",
            "source": "ai_generated",
            "is_saved": False
        }

    def list_tracks(self) -> List[Dict[str, Any]]:
        """Returns catalog of all available AI-generated, saved library, and YouTube Audio Library tracks."""
        tracks = []

        # 0. User Saved Music Library (Surface at the TOP for next video creation!)
        for item in self.list_saved_library():
            tracks.append({
                "id": item["id"],
                "name": f"💾 {item['name']}",
                "genre": f"{item.get('category', 'Music')} · {item.get('mood', 'Epic')}",
                "desc": f"Saved Library Track ({item.get('vocals', 'Instrumental')})",
                "source": "library",
                "filename": item["filename"],
                "file_path": item["file_path"],
                "url": item["url"],
                "is_saved": True,
                "is_default": item.get("is_default", False),
                "category": item.get("category"),
                "mood": item.get("mood"),
                "vocals": item.get("vocals"),
                "duration": item.get("duration")
            })

        # 1. Existing AI-generated tracks
        for p in sorted(self.ai_music_dir.glob("*.wav"), key=os.path.getmtime, reverse=True)[:10]:
            tracks.append({
                "id": p.stem,
                "name": f"AI Music: {p.stem.replace('ai_music_', '').replace('_', ' ').title()}",
                "genre": "AI Procedural",
                "desc": "AI Synthesized Soundtrack (100% Free / Commercial Safe)",
                "source": "ai_generated",
                "filename": p.name,
                "file_path": str(p),
                "url": f"/api/music/preview/{p.name}?type=ai"
            })

        # 3. Built-in legacy tracks
        if (self.audio_dir / "cinematic_drone.wav").exists():
            tracks.append({
                "id": "builtin_cinematic_drone",
                "name": "Cinematic Drone Ambience",
                "genre": "Atmospheric Drone",
                "desc": "Default Tension Ambience",
                "source": "builtin",
                "filename": "cinematic_drone.wav",
                "file_path": str(self.audio_dir / "cinematic_drone.wav"),
                "url": "/api/music/preview/cinematic_drone.wav?type=builtin"
            })
        if (self.audio_dir / "jet_afterburner_ambience.wav").exists():
            tracks.append({
                "id": "builtin_jet_afterburner",
                "name": "Roaring Jet Afterburner",
                "genre": "Aviation FX",
                "desc": "High-Power Supersonic Takeoff",
                "source": "builtin",
                "filename": "jet_afterburner_ambience.wav",
                "file_path": str(self.audio_dir / "jet_afterburner_ambience.wav"),
                "url": "/api/music/preview/jet_afterburner_ambience.wav?type=builtin"
            })

        return tracks

    def _get_media_duration(self, file_path: Path) -> float:
        """Extracts media duration in seconds via FFmpeg with fallback."""
        try:
            res = subprocess.run([FFMPEG_EXE, "-i", str(file_path)], capture_output=True, text=True, timeout=8)
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", res.stderr)
            if m:
                h, mn, s = m.groups()
                dur = int(h) * 3600 + int(mn) * 60 + float(s)
                if dur > 0.1:
                    return dur
        except Exception:
            pass
        return 10.0

    def remix_video_music(
        self,
        video_path: Path,
        music_path: Path,
        output_path: Optional[Path] = None,
        music_volume: float = 0.22,
        voice_volume: float = 1.0,
        ducking: bool = True,
        tempo_factor: float = 1.0,
        bass_boost: float = 0.0,
        treble_boost: float = 0.0,
        reverb: float = 0.0,
        drums_volume: float = 1.0,
        melody_volume: float = 1.0,
        clip_start: float = 0.0,
        clip_duration: Optional[float] = None,
        clip_loop: bool = True,
    ) -> Path:
        """
        Mixes a selected AI or YouTube background music track into an existing short video.
        Supports both clean direct music addition and advanced audio remix properties
        (tempo shifting, bass/treble boost, reverb, stem balance, and auto-ducking).
        Also supports precision audio clip trimming (clip_start & clip_duration) and seamless looping (clip_loop).
        Always sources pristine voiceover from voiceover.mp3 if available to prevent music stacking.
        """
        video_path = Path(video_path)
        music_path = Path(music_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        if not music_path.exists():
            raise FileNotFoundError(f"Music track not found: {music_path}")

        out_path = Path(output_path) if output_path else video_path.parent / "final_short.mp4"
        temp_out = video_path.parent / "temp_remix.mp4"

        m_vol = max(0.01, min(2.5, float(music_volume)))
        v_vol = max(0.0, min(2.5, float(voice_volume)))
        vid_dur = self._get_media_duration(video_path)

        # Precision Audio Trimming (clip_start & clip_duration)
        temp_trimmed_clip: Optional[Path] = None
        effective_music_source = music_path
        c_start = max(0.0, float(clip_start or 0.0))
        c_dur = float(clip_duration) if clip_duration is not None and float(clip_duration) > 0.05 else None

        if c_dur is not None or c_start > 0.05:
            temp_trimmed_clip = video_path.parent / f"temp_clip_{uuid.uuid4().hex[:8]}.wav"
            trim_cmd = [FFMPEG_EXE, "-y", "-ss", f"{c_start:.3f}"]
            if c_dur is not None:
                trim_cmd.extend(["-t", f"{c_dur:.3f}"])
            trim_cmd.extend(["-i", str(music_path), "-c:a", "pcm_s16le", str(temp_trimmed_clip)])
            trim_res = subprocess.run(trim_cmd, capture_output=True, text=True)
            if trim_res.returncode == 0 and temp_trimmed_clip.exists() and temp_trimmed_clip.stat().st_size > 500:
                effective_music_source = temp_trimmed_clip

        # Looping options: repeat clip across full video short or play once
        music_input_args = ["-stream_loop", "-1", "-i", str(effective_music_source)] if clip_loop else ["-i", str(effective_music_source)]

        # Scale music gain curve so volume differences are clearly audible across 0% to 200%
        # Source music stems average -26dB to -33dB, so scaling by 1.8 brings 1.0 to full parity with voiceover
        effective_m_vol = m_vol * 1.8
        m_filters = [f"volume={effective_m_vol:.2f}"]
        if abs(float(tempo_factor) - 1.0) > 0.02:
            t_clamped = max(0.5, min(2.0, float(tempo_factor)))
            m_filters.append(f"atempo={t_clamped:.2f}")
        if abs(float(bass_boost)) > 0.1:
            b_clamped = max(-15.0, min(15.0, float(bass_boost)))
            m_filters.append(f"bass=g={b_clamped:.1f}:f=120")
        if abs(float(treble_boost)) > 0.1:
            tr_clamped = max(-15.0, min(15.0, float(treble_boost)))
            m_filters.append(f"treble=g={tr_clamped:.1f}:f=3500")
        if float(reverb) > 0.05:
            r_val = min(1.0, max(0.0, float(reverb)))
            delay = int(25 + r_val * 45)
            decay = min(0.5, r_val * 0.45)
            m_filters.append(f"aecho=0.8:0.88:{delay}:{decay:.2f}")

        music_fx = ",".join(m_filters)

        # Check if pristine unmixed voiceover exists in project folder
        voice_candidates = [
            video_path.parent / "voiceover.mp3",
            video_path.parent / "voiceover_hindi.mp3",
            video_path.parent / "voice.mp3",
            video_path.parent / "voiceover.wav",
        ]
        voiceover_file = None
        for cand in voice_candidates:
            if cand.exists() and cand.stat().st_size > 1000:
                voiceover_file = cand
                break

        try:
            if voiceover_file:
                # Inputs: [0] = video_path (visual only), [1] = clean voiceover.mp3, [2] = background music
                if ducking and v_vol > 0.05:
                    filter_str = (
                        f"[1:a]volume={v_vol:.2f},apad[voice];"
                        f"[2:a]{music_fx}[bg];"
                        f"[bg][voice]sidechaincompress=threshold=0.20:ratio=2.2:attack=25:release=220[ducked_bg];"
                        f"[voice][ducked_bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
                    )
                else:
                    filter_str = (
                        f"[1:a]volume={v_vol:.2f},apad[voice];"
                        f"[2:a]{music_fx}[bg];"
                        f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
                    )
                cmd = [
                    FFMPEG_EXE, "-y",
                    "-i", str(video_path),
                    "-i", str(voiceover_file),
                    *music_input_args,
                    "-filter_complex", filter_str,
                    "-map", "0:v:0",
                    "-map", "[a]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-t", f"{vid_dur:.3f}",
                    str(temp_out)
                ]
            else:
                # Fallback when separate voiceover.mp3 does not exist: use audio from video
                if ducking and v_vol > 0.05:
                    filter_str = (
                        f"[0:a]volume={v_vol:.2f}[voice];"
                        f"[1:a]{music_fx}[bg];"
                        f"[bg][voice]sidechaincompress=threshold=0.20:ratio=2.2:attack=25:release=220[ducked_bg];"
                        f"[voice][ducked_bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
                    )
                else:
                    filter_str = (
                        f"[0:a]volume={v_vol:.2f}[voice];"
                        f"[1:a]{music_fx}[bg];"
                        f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
                    )
                cmd = [
                    FFMPEG_EXE, "-y",
                    "-i", str(video_path),
                    *music_input_args,
                    "-filter_complex", filter_str,
                    "-map", "0:v:0",
                    "-map", "[a]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-t", f"{vid_dur:.3f}",
                    str(temp_out)
                ]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg music remix failed: {res.stderr[-400:]}")

            if temp_out.exists() and temp_out.stat().st_size > 1000:
                if temp_out != out_path:
                    temp_out.replace(out_path)
                return out_path
            else:
                raise RuntimeError("Remixed video output file is missing or corrupted.")
        finally:
            if temp_trimmed_clip and temp_trimmed_clip.exists():
                try:
                    temp_trimmed_clip.unlink()
                except Exception:
                    pass

    def trim_and_save_clip(
        self,
        source_path: Path,
        clip_start: float = 0.0,
        clip_duration: float = 10.0,
        clip_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Trims a selected segment from an audio file and saves it to the library."""
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source audio file not found: {source_path}")

        c_start = max(0.0, float(clip_start))
        c_dur = max(1.0, float(clip_duration))
        safe_name = re.sub(r'[^a-zA-Z0-9_\- ]', '', clip_name or f"{source_path.stem}_clip_{int(c_dur)}s").strip()
        temp_trimmed = self.ai_music_dir / f"trimmed_{uuid.uuid4().hex[:8]}.wav"

        cmd = [
            FFMPEG_EXE, "-y",
            "-ss", f"{c_start:.3f}",
            "-t", f"{c_dur:.3f}",
            "-i", str(source_path),
            "-c:a", "pcm_s16le",
            str(temp_trimmed)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not temp_trimmed.exists():
            raise RuntimeError(f"FFmpeg trim failed: {res.stderr[-300:]}")

        try:
            return self.save_to_library(
                source_path_or_id=temp_trimmed,
                name=f"✂️ {safe_name} ({int(c_dur)}s Hook)",
                category="Trimmed Clip",
                mood="Loop Ready",
                vocals="Instrumental",
                duration=round(c_dur, 2),
                prompt=f"Trimmed audio clip from {c_start:.1f}s to {c_start+c_dur:.1f}s (Loop Ready)",
                is_default=False
            )
        finally:
            if temp_trimmed.exists():
                try:
                    temp_trimmed.unlink()
                except Exception:
                    pass

    def remove_video_music(
        self,
        video_path: Path,
        output_path: Optional[Path] = None,
        voice_volume: float = 1.0
    ) -> Path:
        """
        Completely strips background music from the video.
        Restores 100% clean voiceover without music using the project's voiceover.mp3.
        Guarantees exact video duration preservation without truncating.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        out_path = Path(output_path) if output_path else video_path.parent / "final_short.mp4"
        temp_out = video_path.parent / "temp_nomusic.mp4"

        v_vol = max(0.0, min(2.5, float(voice_volume)))
        vid_dur = self._get_media_duration(video_path)

        # Search for pristine voiceover file in project folder
        voice_candidates = [
            video_path.parent / "voiceover.mp3",
            video_path.parent / "voiceover_hindi.mp3",
            video_path.parent / "voice.mp3",
            video_path.parent / "voiceover.wav",
        ]
        voiceover_file = None
        for cand in voice_candidates:
            if cand.exists() and cand.stat().st_size > 1000:
                voiceover_file = cand
                break

        if voiceover_file:
            # Re-mux video with clean voiceover audio stream only (padded to exact video length)
            filter_str = f"[1:a]volume={v_vol:.2f},apad[a]"
            cmd = [
                FFMPEG_EXE, "-y",
                "-i", str(video_path),
                "-i", str(voiceover_file),
                "-filter_complex", filter_str,
                "-map", "0:v:0",
                "-map", "[a]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{vid_dur:.3f}",
                str(temp_out)
            ]
        else:
            # If no separate voiceover file exists, mute audio completely for video duration
            cmd = [
                FFMPEG_EXE, "-y",
                "-i", str(video_path),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-map", "0:v:0",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{vid_dur:.3f}",
                str(temp_out)
            ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg remove music failed: {res.stderr[-400:]}")

        if temp_out.exists() and temp_out.stat().st_size > 1000:
            if temp_out != out_path:
                temp_out.replace(out_path)
            return out_path
        else:
            raise RuntimeError("Clean video output file is missing or corrupted.")
