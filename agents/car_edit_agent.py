"""
Car Edit Mode Agent (Swxft-Style Automotive Shorts)
---------------------------------------------------
Implements:
  Car name + time -> real verified car photos, dynamic zoom/pan motion cuts,
  ACE-Step (or procedural fallback) Drift Phonk track, and Swxft-style stacked
  condensed title overlay. Works out-of-the-box with today's tooling.
"""
from __future__ import annotations

import math
import os
import random
import re
import struct
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config


class CarEditAgent:
    """Builds Swxft-style car edit shorts with real photos, zoom/pan motion, Phonk audio, and bold title overlays."""

    AGENT_NAME = "car-edit-agent"

    # Curated specs for popular enthusiast / supercar models (used for Swxft subtitle badges;
    # any unknown car automatically extracts clean specs from Wikipedia/topic research)
    KNOWN_CAR_SPECS: Dict[str, Dict[str, str]] = {
        "porsche 911 gt3 rs": {"brand": "PORSCHE", "model": "911 GT3 RS (992)", "spec": "4.0L FLAT-6 · 518 HP · 9,000 RPM", "tag": "TRACK WEAPON"},
        "bugatti tourbillon": {"brand": "BUGATTI", "model": "TOURBILLON", "spec": "8.3L NA V16 HYBRID · 1,800 HP", "tag": "HYPERCAR ROYALTY"},
        "bugatti chiron": {"brand": "BUGATTI", "model": "CHIRON SUPER SPORT", "spec": "8.0L QUAD-TURBO W16 · 1,578 HP", "tag": "300+ MPH ICON"},
        "ferrari f80": {"brand": "FERRARI", "model": "F80 HYPERCAR", "spec": "3.0L TWIN-TURBO V6 HYBRID · 1,184 HP", "tag": "MARANELLO FLAGSHIP"},
        "ferrari sf90": {"brand": "FERRARI", "model": "SF90 XX STRADALE", "spec": "4.0L TWIN-TURBO V8 · 1,016 HP", "tag": "FIORANO RECORD"},
        "lamborghini revuelto": {"brand": "LAMBORGHINI", "model": "REVUELTO", "spec": "6.5L NA V12 HYBRID · 1,001 HP", "tag": "V12 RAGING BULL"},
        "lamborghini huracan": {"brand": "LAMBORGHINI", "model": "HURACÁN STO", "spec": "5.2L NA V10 · 631 HP · RWD", "tag": "V10 SCREAMER"},
        "nissan gt-r": {"brand": "NISSAN", "model": "SKYLINE GT-R R34", "spec": "RB26DETT TWIN-TURBO I6 · AWD", "tag": "GODZILLA LEGEND"},
        "r34": {"brand": "NISSAN", "model": "SKYLINE GT-R R34", "spec": "RB26DETT TWIN-TURBO I6 · AWD", "tag": "GODZILLA LEGEND"},
        "r35": {"brand": "NISSAN", "model": "GT-R NISMO (R35)", "spec": "3.8L VR38DETT TWIN-TURBO V6 · 600 HP", "tag": "GODZILLA"},
        "toyota supra": {"brand": "TOYOTA", "model": "SUPRA MK4 (A80)", "spec": "3.0L 2JZ-GTE TWIN-TURBO I6", "tag": "JDM ICON"},
        "supra": {"brand": "TOYOTA", "model": "SUPRA MK4 (A80)", "spec": "3.0L 2JZ-GTE TWIN-TURBO I6", "tag": "JDM ICON"},
        "bmw m4": {"brand": "BMW M", "model": "M4 COMPETITION (G82)", "spec": "3.0L S58 TWIN-TURBO I6 · 523 HP", "tag": "BAVARIAN BEAST"},
        "bmw m3": {"brand": "BMW M", "model": "M3 GTR / G80", "spec": "TWIN-TURBO INLINE-6 · M xDRIVE", "tag": "ULTIMATE M"},
        "BMW m5": {"brand": "BMW M", "model": "M5 CS (F90)", "spec": "4.4L TWIN-TURBO V8 · 627 HP", "tag": "SUPER SEDAN"},
        "mclaren p1": {"brand": "McLAREN", "model": "P1 HYPERCAR", "spec": "3.8L TWIN-TURBO V8 HYBRID · 903 HP", "tag": "HOLY TRINITY"},
        "mclaren 765lt": {"brand": "McLAREN", "model": "765LT", "spec": "4.0L TWIN-TURBO V8 · 755 HP", "tag": "LONGTAIL"},
        "koenigsegg jesko": {"brand": "KOENIGSEGG", "model": "JESKO ABSOLUT", "spec": "5.0L TWIN-TURBO V8 · 1,600 HP", "tag": "SPEED KING"},
        "pagani huayra": {"brand": "PAGANI", "model": "HUAYRA R", "spec": "6.0L NA V12 · 838 HP · 9,000 RPM", "tag": "ART ON WHEELS"},
        "mercedes amg gt": {"brand": "MERCEDES-AMG", "model": "AMG GT BLACK SERIES", "spec": "4.0L FLAT-PLANE V8 · 720 HP", "tag": "NÜRBURGRING KING"},
        "audi r8": {"brand": "AUDI SPORT", "model": "R8 V10 PERFORMANCE", "spec": "5.2L NATURALLY ASPIRATED V10 · 602 HP", "tag": "V10 SYMPHONY"},
        "dodge challenger": {"brand": "DODGE", "model": "CHALLENGER SRT DEMON 170", "spec": "6.2L SUPERCHARGED HEMI V8 · 1,025 HP", "tag": "MUSCLE KING"},
        "ford mustang": {"brand": "FORD", "model": "MUSTANG GTD", "spec": "5.2L SUPERCHARGED V8 · 815 HP", "tag": "LE MANS STREET"},
        "chevrolet corvette": {"brand": "CORVETTE", "model": "ZR1 (C8)", "spec": "5.5L TWIN-TURBO FLAT-PLANE V8 · 1,064 HP", "tag": "AMERICAN HYPERCAR"},
        "mazda rx-7": {"brand": "MAZDA", "model": "RX-7 FD3S", "spec": "13B-REW TWIN-ROTOR TURBO · 9,000 RPM", "tag": "ROTARY LEGEND"},
    }

    MOTION_SEQUENCES: Dict[str, List[str]] = {
        "swxft_dynamic": ["zoom_in", "pan_right", "focus", "zoom_out", "pan_left", "zoom_in", "pan_up", "focus"],
        "zoom_punch": ["zoom_in", "zoom_out", "zoom_in", "focus", "zoom_in", "zoom_out"],
        "cinematic_pan": ["pan_right", "pan_left", "zoom_in", "pan_up", "pan_down", "focus"],
    }

    PHONK_BPMS: Dict[str, float] = {
        "drift_phonk": 130.0,
        "brazilian_phonk": 135.0,
        "night_drive": 124.0,
        "tokyo_touge": 132.0,
        "aggressive_cowbell": 138.0,
        "cyber_supercar": 128.0,
        "dark_memphis": 126.0,
        "hypercar_orchestral": 130.0,
    }

    PHONK_PROMPTS: Dict[str, str] = {
        "drift_phonk": (
            "aggressive drift phonk car edit, distorted 808 cowbell melody, heavy sidechained sub bass, "
            "crisp rolling trap hi-hats, night highway street racing energy, 130 BPM, instrumental"
        ),
        "brazilian_phonk": (
            "hard brazilian phonk car edit, ultra punchy distorted kick, aggressive metallic cowbell hook, "
            "high energy automotive montage rhythm, 135 BPM, instrumental"
        ),
        "night_drive": (
            "atmospheric night drive wave phonk, deep Reese sub bass, reverb-soaked cowbell lead, "
            "wet asphalt midnight supercar cruise, 124 BPM, instrumental"
        ),
        "tokyo_touge": (
            "japanese tokyo touge drift phonk, high-pitched JDM cowbell melody, turbo flutter percussion, "
            "fast mountain pass drift rhythm, 132 BPM, instrumental"
        ),
        "aggressive_cowbell": (
            "ultra aggressive 808 cowbell phonk anthem, overdriven sub bass slides, rapid trap hi-hat rolls, "
            "maximum adrenaline car edit drop, 138 BPM, instrumental"
        ),
        "cyber_supercar": (
            "futuristic cyber supercar synth phonk, dark analog arpeggio, heavy 808 kick and cowbell lead, "
            "neon highway hypercar aesthetic, 128 BPM, instrumental"
        ),
        "dark_memphis": (
            "dark underground memphis drift phonk, lo-fi saturated 808 bass, eerie minor cowbell hook, "
            "street racing edit, 126 BPM, instrumental"
        ),
        "hypercar_orchestral": (
            "epic orchestral hybrid drift phonk, staccato brass and strings layered with 808 cowbell and sub bass, "
            "flagship hypercar showcase, 130 BPM, instrumental"
        ),
    }

    @classmethod
    def get_phonk_bpm(cls, phonk_style: str = "drift_phonk") -> float:
        return float(cls.PHONK_BPMS.get(phonk_style or "drift_phonk", 130.0))

    @classmethod
    def detect_audio_bpm_and_beats(cls, wav_path: Optional[Path], fallback_bpm: float = 130.0) -> Dict[str, Any]:
        """
        Inspects a WAV file's low-frequency energy envelope (20ms windows) to detect kick/808 beat onsets,
        falling back cleanly to the exact known BPM grid when not provided.
        """
        bpm = float(fallback_bpm or 130.0)
        beat_sec = 60.0 / bpm
        onsets: List[float] = []
        if wav_path and Path(wav_path).exists():
            try:
                with wave.open(str(wav_path), "rb") as wf:
                    sr = wf.getframerate()
                    ch = wf.getnchannels()
                    sw = wf.getsampwidth()
                    max_frames = min(wf.getnframes(), sr * 30)
                    raw = wf.readframes(max_frames)
                if sw == 2 and len(raw) >= 4000:
                    win = max(1, int(sr * 0.02))  # 20ms window
                    step_bytes = win * ch * 2
                    energies: List[float] = []
                    for offset in range(0, len(raw) - step_bytes, step_bytes):
                        # Sample every 8th frame in window for fast RMS
                        s_sum = 0.0
                        count = 0
                        for pos in range(offset, offset + step_bytes, ch * 2 * 8):
                            val = struct.unpack_from("<h", raw, pos)[0] / 32768.0
                            s_sum += val * val
                            count += 1
                        energies.append(math.sqrt(s_sum / max(1, count)))
                    if energies:
                        mean_e = sum(energies) / len(energies)
                        thresh = mean_e * 1.28
                        last_t = -1.0
                        for idx_w, e_val in enumerate(energies):
                            if 0 < idx_w < len(energies) - 1:
                                if e_val > thresh and e_val >= energies[idx_w - 1] and e_val >= energies[idx_w + 1]:
                                    t_sec = round(idx_w * 0.02, 3)
                                    if t_sec - last_t >= 0.34:
                                        onsets.append(t_sec)
                                        last_t = t_sec
            except Exception:
                pass
        return {
            "bpm": bpm,
            "beat_sec": round(beat_sec, 4),
            "detected_onsets": onsets[:64],
        }

    @classmethod
    def compute_beat_synced_cuts(
        cls,
        target_duration: float = 15.0,
        bpm: float = 130.0,
        beat_sync_mode: str = "swxft_velocity",
    ) -> List[Dict[str, Any]]:
        """
        Quantizes scene cuts onto the exact musical beat grid of the Phonk track:
        - 'swxft_velocity': 4-beat intro hook (whip_in) -> rapid 2-beat drop cuts (velocity) -> 4-beat hero hold (velocity)
        - 'every_2_beats': Rapid-fire 2-beat cuts (~0.92s at 130 BPM) with velocity speed ramps
        - 'every_4_beats': 4-beat bar cuts (~1.85s at 130 BPM) with deep velocity speed ramps
        - 'whip_in': Beat-locked cuts with explosive whip-in -> slow-mo hold
        """
        dur = max(5.0, min(180.0, float(target_duration or 15.0)))
        beat_sec = 60.0 / max(60.0, float(bpm or 130.0))

        # Pattern of beats per scene
        if beat_sync_mode == "every_2_beats":
            beat_pattern = [2, 2, 2, 2, 2, 2, 2, 2]
        elif beat_sync_mode == "every_4_beats":
            beat_pattern = [4, 4, 4, 4, 4, 4]
        else:
            # Signature Swxft cadence: 4-beat intro -> two rapid 2-beat drop cuts -> 4-beat slow-mo hero -> two 2-beat cuts
            beat_pattern = [4, 2, 2, 4, 2, 2, 4, 2, 2, 4]

        cuts: List[Dict[str, Any]] = []
        elapsed = 0.0
        idx = 0
        while elapsed < dur - 0.35 and len(cuts) < 20:
            beats = beat_pattern[idx % len(beat_pattern)]
            seg_dur = round(beats * beat_sec, 3)
            remaining = round(dur - elapsed, 3)
            if remaining < seg_dur * 1.35 or len(cuts) == 19:
                seg_dur = max(0.6, remaining)
                beats = max(1, int(round(seg_dur / beat_sec)))
            if beat_sync_mode == "whip_in":
                ramp = "whip_in"
            elif idx == 0:
                ramp = "whip_in"
            elif elapsed + seg_dur >= dur - 0.05:
                ramp = "whip_out"
            else:
                ramp = "velocity"

            cuts.append({
                "scene_number": idx + 1,
                "beats": beats,
                "start_sec": round(elapsed, 3),
                "duration_seconds": round(seg_dur, 3),
                "speed_ramp": ramp,
                "beat_sync": True,
                "bpm": bpm,
            })
            elapsed = round(elapsed + seg_dur, 3)
            idx += 1

        # Guarantee exact total duration sum
        if cuts:
            diff = round(dur - sum(c["duration_seconds"] for c in cuts), 3)
            cuts[-1]["duration_seconds"] = round(max(0.5, cuts[-1]["duration_seconds"] + diff), 3)
        return cuts

    @classmethod
    def resolve_car_specs(cls, car_name: str, key_facts: Optional[List[str]] = None) -> Dict[str, str]:
        clean = re.sub(r"\s+", " ", (car_name or "Porsche 911 GT3 RS")).strip()
        low = clean.lower()
        # 1. the owner's own pinned values (assets/data/car_specs_overrides.json) are trusted as-is
        try:
            from agents import specs_db
            pinned = specs_db._read(specs_db.OVERRIDES).get(re.sub(r"\s+", " ", low))
        except Exception:
            pinned = None
        for key, spec in cls.KNOWN_CAR_SPECS.items():
            if key in low:
                out = dict(spec)
                if pinned and pinned.get("spec"):
                    out["spec"] = pinned["spec"].upper()
                    return out
                # 2. built-in values are only shown when the car's sources confirm every number
                #    (owner's rule: correct data or nothing)
                try:
                    from agents import fact_check
                    checked = fact_check.verify_spec_line(out["spec"], clean, " ".join(key_facts or []))
                except Exception as e:
                    print(f"[{cls.AGENT_NAME}] spec check failed ({e}): numbers left out")
                    checked = " · ".join(x for x in out["spec"].split(" · ") if not re.search(r"\d", x))
                out["spec"] = checked or "PERFORMANCE EDITION · PURE ENGINEERING"
                return out

        # Parse brand + model from user input
        tokens = clean.split()
        brand = tokens[0].upper() if tokens else "SUPERCAR"
        model = " ".join(tokens[1:]).upper() if len(tokens) > 1 else clean.upper()

        # Specs database: the car's own Wikipedia article (engine + power), never a sibling model's
        try:
            from agents import specs_db
            found = specs_db.lookup_car(clean)
        except Exception as e:
            print(f"[{cls.AGENT_NAME}] specs lookup skipped: {e}")
            found = None
        if found and found.get("spec"):
            return {"brand": brand, "model": model, "spec": found["spec"].upper(), "tag": "",
                    "spec_source": found.get("source")}

        # Extract any HP / engine tokens from facts if available
        spec_parts = []
        joined_facts = " ".join(key_facts or [])
        eng_m = re.search(r"\b(V\d{1,2}|W16|Flat-6|Inline-6|I6|Twin-Turbo|Supercharged|Hybrid)\b", joined_facts, re.I)
        hp_m = re.search(r"\b(\d{3,4})\s*(?:hp|bhp|horsepower|PS)\b", joined_facts, re.I)
        if eng_m:
            spec_parts.append(eng_m.group(1).upper())
        if hp_m:
            spec_parts.append(f"{hp_m.group(1)} HP")
        if not spec_parts:
            spec_parts = ["PERFORMANCE EDITION", "PURE ENGINEERING"]

        return {
            "brand": brand,
            "model": model,
            "spec": " · ".join(spec_parts),
            "tag": "",  # no third-party branding badge on the video (user request: remove "SWXFT")
        }


    @staticmethod
    def _fact_sentences(key_facts: Any) -> List[str]:
        """key_facts may arrive as one string; indexing that picked single LETTERS as scene narration
        ('h', 'e', ' '), which also made music-only re-renders give scene 1 ~10 s (word-count timing)."""
        if not key_facts:
            return []
        if isinstance(key_facts, str):
            key_facts = re.split(r"(?<=[.!?])\s+", key_facts)
        return [str(f).strip() for f in key_facts if str(f).strip() and len(str(f).split()) >= 3]

    @classmethod
    def build_car_edit_scenes(
        cls,
        car_name: str,
        target_duration: float = 15.0,
        custom_title: Optional[str] = None,
        topic_research: Optional[Dict[str, Any]] = None,
        phonk_style: str = "drift_phonk",
        beat_sync_mode: str = "swxft_velocity",
    ) -> Dict[str, Any]:
        """
        Builds a high-retention Swxft-style car edit scene breakdown with beat-quantized cuts
        (2-beat rapid drop cuts & 4-beat hero holds), velocity speed ramps, and varied real-photo search angles.
        """
        clean_car = re.sub(r"\s+", " ", (car_name or "Porsche 911 GT3 RS")).strip()
        dur = max(5.0, min(180.0, float(target_duration or 15.0)))
        facts = cls._fact_sentences((topic_research or {}).get("key_facts"))
        specs = cls.resolve_car_specs(clean_car, facts)
        bpm = cls.get_phonk_bpm(phonk_style)
        beat_cuts = cls.compute_beat_synced_cuts(target_duration=dur, bpm=bpm, beat_sync_mode=beat_sync_mode)

        angles = [
            ("front three-quarter stance", f"{clean_car} front three-quarter view exterior photo", f"{specs['brand']} {specs['model']}"),
            ("side profile aerodynamic silhouette", f"{clean_car} side profile view photo", specs["spec"]),
            ("rear diffuser, exhaust and wing", f"{clean_car} rear view wing tail lights photo", "AERODYNAMIC PRECISION"),
            ("track cornering action shot", f"{clean_car} track driving action photo", "BUILT FOR THE APEX"),
            ("close-up wheel, brake caliper & bodywork", f"{clean_car} wheel rim headlight detail photo", "RACE-BRED HARDWARE"),
            ("engine bay & powertrain engineering", f"{clean_car} engine bay powertrain photo", specs["spec"]),
            ("cockpit & driver interior", f"{clean_car} interior steering wheel cockpit photo", "DRIVER-FOCUSED COCKPIT"),
            ("rolling highway night stance", f"{clean_car} coupe sports car photo", f"{specs['brand']} LEGACY"),
        ]

        scenes: List[Dict[str, Any]] = []
        for i, cut in enumerate(beat_cuts):
            angle_desc, search_q, badge_txt = angles[i % len(angles)]
            fact_line = facts[i % len(facts)] if facts else f"{clean_car} — {angle_desc}."
            narration = (
                f"{clean_car}: {specs['spec']}."
                if i == 0
                else fact_line
            )
            scenes.append({
                "scene_number": i + 1,
                "duration_seconds": cut["duration_seconds"],
                "beats": cut["beats"],
                "beat_synced": True,
                "beat_sync": True,
                "bpm": bpm,
                "speed_ramp": cut["speed_ramp"],
                "narration": narration,
                "on_screen_text": (custom_title.strip().upper() if (i == 0 and custom_title and custom_title.strip()) else badge_txt),
                "visual_prompt": (
                    f"Real automotive photography of {clean_car}, {angle_desc}, "
                    f"sharp reflections, dramatic lighting, vertical 9:16 car edit frame"
                ),
                "search_query": search_q,
                "car_angle": angle_desc,
            })

        headline_top = custom_title.strip().upper() if (custom_title and custom_title.strip()) else specs["brand"]
        headline_main = specs["model"] if not (custom_title and custom_title.strip()) else f"{specs['brand']} {specs['model']}"

        title_yt = f"{clean_car} — {specs['spec']} 🔥 #Shorts #Cars #CarEdit"
        desc_yt = (
            f"{clean_car} ({specs['spec']}) car edit with real automotive photography and drift phonk soundtrack.\n\n"
            f"#Shorts #{re.sub(r'[^A-Za-z0-9]', '', specs['brand'])} #CarEdit #Phonk #Supercars"
        )
        tags_yt = [
            clean_car.lower(),
            specs["brand"].lower(),
            "car edit",
            "phonk",
            "supercars",
            "shorts",
        ]

        return {
            "car_name": clean_car,
            "specs": specs,
            "bpm": bpm,
            "beat_sync_mode": beat_sync_mode,
            "headline_top": headline_top,
            "headline_main": headline_main,
            "subtitle_spec": specs["spec"],
            "tag_pill": specs["tag"],
            "title": title_yt[:95],
            "description": desc_yt,
            "tags": tags_yt,
            "hook": f"{clean_car} — {specs['spec']}",
            "scenes": scenes,
            "target_duration": dur,
        }

    @classmethod
    def build_scene_effects(
        cls,
        num_scenes: int,
        motion_preset: str = "swxft_dynamic",
        bpm: float = 130.0,
        beat_sync_mode: str = "swxft_velocity",
    ) -> List[Dict[str, Any]]:
        """
        Generates per-scene zoom/pan motion, velocity speed ramps, beat-flash & colour grade settings
        compatible with agents/scene_effects.py.
        """
        seq = cls.MOTION_SEQUENCES.get(motion_preset) or cls.MOTION_SEQUENCES["swxft_dynamic"]
        out: List[Dict[str, Any]] = []
        for idx in range(num_scenes):
            motion = seq[idx % len(seq)]
            if beat_sync_mode == "whip_in":
                speed_ramp = "whip_in"
            elif idx == 0:
                speed_ramp = "whip_in"
            elif idx == num_scenes - 1 and num_scenes > 2:
                speed_ramp = "whip_out"
            else:
                speed_ramp = "velocity"
            out.append({
                "motion": motion,
                "motion_strength": "strong",
                "speed_ramp": speed_ramp,
                "beat_sync": True,
                "bpm": float(bpm or 130.0),
                "focus_point": {"x": 0.5, "y": 0.52},
                "effects": {
                    "filter": "cinematic",
                    "vignette": True,
                    "focus_blur": False,
                    "beat_flash": True,
                    "fade_in": (idx == 0),
                    "fade_out": False,
                },
            })
        return out

    @classmethod
    def _load_font(cls, size: int, bold: bool = True):
        from PIL import ImageFont
        candidates = [
            "/System/Library/Fonts/Supplemental/Impact.ttf",
            "/System/Library/Fonts/Supplemental/Arial Black.ttf",
            "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/Library/Fonts/Arial Bold.ttf",
        ]
        for c in candidates:
            if Path(c).exists():
                try:
                    return ImageFont.truetype(c, size=size)
                except Exception:
                    continue
        return ImageFont.load_default()

    @classmethod
    def remove_brand_pill(cls, overlay_path: Path) -> bool:
        """Erases the old "⚡ SWXFT CAR EDIT" pill from an already-rendered overlay by repainting that
        area with the overlay's own top gradient (same geometry as apply_swxft_title_overlays)."""
        from PIL import Image, ImageDraw
        overlay_path = Path(overlay_path)
        if not overlay_path.exists():
            return False
        ov = Image.open(overlay_path).convert("RGBA")
        w = ov.width
        d = ImageDraw.Draw(ov)
        font_tag = cls._load_font(28)
        tb = d.textbbox((0, 0), "⚡ SWXFT CAR EDIT", font=font_tag)
        pw, ph = (tb[2] - tb[0]) + 44, (tb[3] - tb[1]) + 20
        px, py = (w - pw) // 2, 118
        px_ = ov.load()
        # Locate the pill by its cyan outline (older renders used different widths); fall back to the
        # computed box when no outline is found
        cyan = [(x, y) for y in range(90, min(ov.height, 230)) for x in range(w)
                if px_[x, y][3] > 120 and px_[x, y][2] > 180 and px_[x, y][1] > 150 and px_[x, y][0] < 90]
        if cyan:
            x0, x1 = min(c[0] for c in cyan), max(c[0] for c in cyan)
            y0, y1 = min(c[1] for c in cyan), max(c[1] for c in cyan)
        else:
            x0, x1, y0, y1 = px, px + pw, py, py + ph
        for y in range(max(0, y0 - 6), min(ov.height, y1 + 7)):
            alpha = int(175 * (1.0 - (y / 380.0)) ** 1.5) if y < 380 else 0
            for x in range(max(0, x0 - 8), min(w, x1 + 9)):
                px_[x, y] = (5, 8, 15, alpha)
        ov.save(overlay_path, "PNG")
        return True

    @classmethod
    def apply_swxft_title_overlays(
        cls,
        image_paths: List[str],
        car_plan: Dict[str, Any],
        scenes: List[Dict[str, Any]],
    ) -> None:
        from PIL import Image, ImageDraw, ImageEnhance
        """
        Writes `<scene>_bg.png` (high-contrast real car photo) and `<scene>_overlay.png`
        (transparent RGBA Swxft-style condensed stacked title + spec pill + subtle top/bottom vignette)
        so VideoComposer zooms/pans the car photo while keeping the Swxft title razor-sharp!
        Also updates `<scene>.png` with the composited preview so thumbnails in the UI show the title.
        """
        w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
        headline_top = str(car_plan.get("headline_top") or "SUPERCAR").upper()
        headline_main = str(car_plan.get("headline_main") or car_plan.get("car_name") or "").upper()
        subtitle_spec = str(car_plan.get("subtitle_spec") or "").upper()
        tag_pill = str(car_plan.get("tag_pill") or "").upper()
        if "SWXFT" in tag_pill:
            tag_pill = ""

        font_tag = cls._load_font(28)
        font_top = cls._load_font(54)
        font_main = cls._load_font(76 if len(headline_main) <= 16 else 58)
        font_spec = cls._load_font(30)
        font_scene_badge = cls._load_font(34)

        for idx, img_path_str in enumerate(image_paths):
            img_p = Path(img_path_str)
            if not img_p.exists():
                continue

            try:
                raw_bg = Image.open(img_p).convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
                # Subtle car-edit contrast & saturation polish on the background photo
                bg_enhanced = ImageEnhance.Contrast(raw_bg).enhance(1.10)
                bg_enhanced = ImageEnhance.Color(bg_enhanced).enhance(1.08)

                bg_path = img_p.parent / f"{img_p.stem}_bg.png"
                base_path = img_p.parent / f"{img_p.stem}_base.png"
                overlay_path = img_p.parent / f"{img_p.stem}_overlay.png"

                bg_enhanced.save(bg_path, "PNG")
                bg_enhanced.save(base_path, "PNG")

                # Build transparent RGBA overlay with Swxft-style header & bottom beat badge
                overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)

                # Top and bottom cinematic dark gradient bars for high legibility
                for y in range(380):
                    alpha = int(175 * (1.0 - (y / 380.0)) ** 1.5)
                    draw.line([(0, y), (w, y)], fill=(5, 8, 15, alpha))
                for y in range(h - 320, h):
                    prog = (y - (h - 320)) / 320.0
                    alpha = int(165 * (prog ** 1.5))
                    draw.line([(0, y), (w, y)], fill=(5, 8, 15, alpha))

                # 1. Top Pill Badge (only when a tag is set; the title keeps the same position either way)
                pill_text = f"⚡ {tag_pill or 'X'}"
                tb = draw.textbbox((0, 0), pill_text, font=font_tag)
                pw = (tb[2] - tb[0]) + 44
                ph = (tb[3] - tb[1]) + 20
                px = (w - pw) // 2
                py = 118
                if tag_pill:
                    draw.rounded_rectangle((px, py, px + pw, py + ph), radius=ph // 2, fill=(12, 18, 30, 220),
                                           outline=(0, 229, 255, 235), width=2)
                    draw.text((w // 2, py + ph // 2), pill_text, font=font_tag, fill=(0, 229, 255, 255), anchor="mm")

                # 2. Swxft-Style Stacked Brand + Model Title with heavy black stroke & glow
                y_top = py + ph + 44
                draw.text(
                    (w // 2, y_top),
                    headline_top,
                    font=font_top,
                    fill=(255, 255, 255, 255),
                    anchor="mm",
                    stroke_width=5,
                    stroke_fill=(0, 0, 0, 255),
                )

                y_main = y_top + 68
                draw.text(
                    (w // 2, y_main),
                    headline_main,
                    font=font_main,
                    fill=(255, 230, 0, 255),
                    anchor="mm",
                    stroke_width=6,
                    stroke_fill=(0, 0, 0, 255),
                )

                # 3. Spec Bar (e.g. "4.0L FLAT-6 · 518 HP · 9,000 RPM")
                if subtitle_spec:
                    y_spec = y_main + 58
                    sb = draw.textbbox((0, 0), subtitle_spec, font=font_spec)
                    sw = (sb[2] - sb[0]) + 48
                    sh = (sb[3] - sb[1]) + 18
                    sx = (w - sw) // 2
                    sy = y_spec - sh // 2
                    draw.rounded_rectangle(
                        (sx, sy, sx + sw, sy + sh),
                        radius=10,
                        fill=(0, 0, 0, 200),
                        outline=(255, 230, 0, 180),
                        width=2,
                    )
                    draw.text(
                        (w // 2, y_spec),
                        subtitle_spec,
                        font=font_spec,
                        fill=(248, 250, 252, 255),
                        anchor="mm",
                    )

                # 4. Per-scene bottom-center callout (if scene > 0)
                sc_text = ""
                if idx < len(scenes):
                    sc_text = str(scenes[idx].get("on_screen_text") or "").strip().upper()
                if sc_text and sc_text not in (headline_main, subtitle_spec):
                    # Large, readable caption (viral-strategy brief): 72 px, shrunk only as far as a long
                    # line needs to fit the frame width (was a fixed 34 px - unreadable on a phone)
                    size, cap_font = 72, cls._load_font(72)
                    while size > 40 and draw.textbbox((0, 0), sc_text, font=cap_font, stroke_width=6)[2] > w - 90:
                        size -= 4
                        cap_font = cls._load_font(size)
                    draw.text(
                        (w // 2, h - 300),
                        sc_text,
                        font=cap_font,
                        fill=(255, 255, 255, 250),
                        anchor="mm",
                        stroke_width=6,
                        stroke_fill=(0, 0, 0, 245),
                    )

                overlay.save(overlay_path, "PNG")

                # Save composited preview to img_p so dashboard thumbnail & scene preview display the Swxft title
                composited = Image.alpha_composite(bg_enhanced.convert("RGBA"), overlay).convert("RGB")
                composited.save(img_p, "PNG")
            except Exception as e:
                print(f"[{cls.AGENT_NAME}] Warning: Swxft overlay skipped for {img_p.name}: {e}")

    @classmethod
    def resolve_or_generate_phonk_track(
        cls,
        car_name: str,
        duration: float = 15.0,
        phonk_style: str = "drift_phonk",
    ) -> str:
        """
        1. If user passed a specific existing audio file/track ID, returns it.
        2. If local ACE-Step 1.5 server is available, generates a fresh Drift Phonk track via ACEStepMusicAgent.
        3. Otherwise synthesizes a punchy 130 BPM Drift Phonk track (808 cowbell lead + distorted 808 sub bass + trap drums)
           so Car Edit Mode works 100% out-of-the-box with today's tooling.
        """
        prompt = cls.PHONK_PROMPTS.get(phonk_style) or cls.PHONK_PROMPTS["drift_phonk"]
        dur = max(10.0, min(180.0, float(duration or 15.0)))

        # 1. Try local ACE-Step 1.5 server if reachable
        try:
            from agents.acestep_music_agent import ACEStepMusicAgent
            ace = ACEStepMusicAgent()
            if ace.health_error() is None:
                print(f"[{cls.AGENT_NAME}] 🎵 ACE-Step 1.5 server live — generating Drift Phonk track for '{car_name}'...")
                res = ace.generate_track(
                    category="EDM",
                    mood="Aggressive",
                    vocals="Instrumental",
                    duration=dur,
                    prompt=f"{prompt}, car edit for {car_name}",
                    name=f"ACE-Step Phonk · {car_name}",
                )
                if res and res.get("file_path") and Path(res["file_path"]).exists():
                    return str(res["file_path"])
        except Exception as e:
            print(f"[{cls.AGENT_NAME}] ACE-Step live server not active ({e}); using built-in Drift Phonk synthesizer.")

        # 2. Built-in procedural 130 BPM Drift Phonk synthesizer (808 cowbell melody + distorted 808 sub + trap hi-hats)
        out_dir = config.AUDIO_ASSETS_DIR / "ai_generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", (car_name or "car_edit").lower()).strip("_")[:24]
        out_path = out_dir / f"acestep_phonk_{slug}_{int(time.time())}.wav"
        cls._synthesize_drift_phonk_wav(out_path, duration=dur, style=phonk_style)
        return str(out_path)

    @classmethod
    def _synthesize_drift_phonk_wav(cls, out_path: Path, duration: float = 15.0, style: str = "drift_phonk") -> Path:
        """
        Synthesizes an authentic 44.1kHz stereo Drift Phonk beat:
        - Roland TR-808 style dual-oscillator metallic cowbell melody (540Hz / 800Hz ratio) in E Phrygian
        - Hard-clipped distorted 808 sub-bass slides (41.2Hz - 65.4Hz) with kick sidechain ducking
        - Punchy kick + crisp snare on beats 2 & 4 + 16th-note trap hi-hat rolls
        """
        sr = 44100
        bpm = cls.get_phonk_bpm(style)
        beat_sec = 60.0 / bpm
        step_sec = beat_sec / 4.0  # 16th note

        total_samples = int(sr * max(5.0, min(180.0, float(duration))))
        # Synthesize a 4-bar loop (16 beats = ~7.4s) and tile seamlessly across total_samples
        loop_steps = 64
        loop_samples = int(loop_steps * step_sec * sr)

        # Distinct cowbell riffs per Phonk style (frequencies in Hz, 0 = rest)
        riffs_by_style = {
            "drift_phonk": [
                329.63, 0, 329.63, 349.23, 392.00, 0, 349.23, 329.63,
                493.88, 0, 440.00, 392.00, 349.23, 0, 329.63, 0,
                329.63, 329.63, 349.23, 392.00, 440.00, 0, 392.00, 349.23,
                523.25, 0, 493.88, 440.00, 392.00, 349.23, 329.63, 0,
            ],
            "brazilian_phonk": [
                369.99, 369.99, 0, 392.00, 440.00, 0, 392.00, 369.99,
                554.37, 0, 493.88, 440.00, 392.00, 369.99, 0, 369.99,
                369.99, 0, 440.00, 493.88, 554.37, 0, 493.88, 440.00,
                587.33, 554.37, 493.88, 440.00, 392.00, 369.99, 329.63, 0,
            ],
            "night_drive": [
                293.66, 0, 0, 329.63, 349.23, 0, 440.00, 0,
                392.00, 0, 349.23, 0, 329.63, 0, 293.66, 0,
                293.66, 0, 349.23, 0, 440.00, 0, 523.25, 0,
                493.88, 0, 440.00, 392.00, 349.23, 0, 329.63, 0,
            ],
            "tokyo_touge": [
                392.00, 0, 440.00, 466.16, 523.25, 0, 466.16, 440.00,
                587.33, 0, 523.25, 466.16, 440.00, 392.00, 0, 392.00,
                392.00, 440.00, 466.16, 523.25, 587.33, 0, 622.25, 587.33,
                523.25, 466.16, 440.00, 392.00, 349.23, 0, 392.00, 0,
            ],
            "aggressive_cowbell": [
                349.23, 349.23, 369.99, 349.23, 415.30, 0, 369.99, 349.23,
                523.25, 523.25, 466.16, 415.30, 369.99, 349.23, 369.99, 0,
                349.23, 349.23, 415.30, 466.16, 523.25, 554.37, 523.25, 466.16,
                622.25, 0, 554.37, 523.25, 466.16, 415.30, 349.23, 0,
            ],
        }
        riff_notes = riffs_by_style.get(style) or riffs_by_style["drift_phonk"]
        bass_roots = [41.20, 41.20, 43.65, 49.00]  # E1, E1, F1, G1

        rng = random.Random(1337)
        noise_table = [rng.uniform(-1.0, 1.0) for _ in range(4096)]

        loop_buf = bytearray(loop_samples * 4)
        two_pi = 2.0 * math.pi

        for i in range(loop_samples):
            t = i / float(sr)
            step_idx = int(t / step_sec) % loop_steps
            step_pos = (t % step_sec) / step_sec  # 0..1 within current 16th note
            beat_pos = (t % beat_sec) / beat_sec  # 0..1 within current quarter-note beat
            bar_idx = (step_idx // 16) % 4

            # 1. Punchy Kick on steps 0, 3, 6, 8, 11, 14 of each 16-step bar
            bar_step = step_idx % 16
            kick = 0.0
            if bar_step in (0, 3, 6, 8, 11, 14):
                kt = step_pos * step_sec
                if kt < 0.16:
                    kf = 52.0 + 130.0 * math.exp(-kt * 42.0)
                    kick = math.sin(two_pi * kf * kt) * math.exp(-kt * 16.0) * 0.95

            # 2. Distorted 808 Sub-Bass (sidechained to kick)
            f_bass = bass_roots[bar_idx]
            sidechain = 0.25 + 0.75 * (1.0 - math.exp(-beat_pos * 5.5))
            raw_sub = math.sin(two_pi * f_bass * t) + 0.45 * math.sin(two_pi * (f_bass * 2.0) * t)
            # Soft-clip saturation for Phonk grit
            sub = math.tanh(raw_sub * 2.4) * 0.52 * sidechain

            # 3. Signature 808 Cowbell Lead (dual square-like oscillators at 1 : 1.481 ratio + bandpass character)
            note_f = riff_notes[step_idx % len(riff_notes)]
            cb_l = cb_r = 0.0
            if note_f > 0:
                ct = step_pos * step_sec
                env = math.exp(-ct * 11.5)
                osc1 = math.sin(two_pi * note_f * t) + 0.35 * math.sin(two_pi * note_f * 3.0 * t)
                osc2 = math.sin(two_pi * (note_f * 1.481) * t)
                cb = math.tanh((osc1 + 0.85 * osc2) * 1.9) * env * 0.42
                cb_l = cb * 1.06
                cb_r = cb * 0.94

            # 4. Crisp Snare / Clap on steps 4 and 12 (beats 2 and 4)
            snare = 0.0
            if bar_step in (4, 12):
                st = step_pos * step_sec
                if st < 0.14:
                    n_val = noise_table[i & 4095]
                    body = math.sin(two_pi * 185.0 * st) * math.exp(-st * 28.0)
                    snare = (n_val * math.exp(-st * 22.0) * 0.75 + body * 0.45) * 0.65

            # 5. Rolling 16th-note Trap Hi-Hats (with double-time roll on step 15)
            ht = (step_pos * 2.0 % 1.0) * (step_sec * 0.5) if bar_step in (7, 15) else step_pos * step_sec
            hat = noise_table[(i * 7) & 4095] * math.exp(-ht * 55.0) * 0.20

            mix_l = kick + sub + snare + hat * 1.08 + cb_l
            mix_r = kick + sub + snare + hat * 0.92 + cb_r

            # Master limiter
            s_l = int(max(-32000, min(32000, math.tanh(mix_l * 1.15) * 30500)))
            s_r = int(max(-32000, min(32000, math.tanh(mix_r * 1.15) * 30500)))
            struct.pack_into("<hh", loop_buf, i * 4, s_l, s_r)

        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            written = 0
            while written < total_samples:
                chunk = min(loop_samples, total_samples - written)
                wf.writeframesraw(memoryview(loop_buf)[: chunk * 4])
                written += chunk

        return out_path
