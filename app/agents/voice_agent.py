import asyncio
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import timedelta
try:
    import edge_tts
except ImportError:
    edge_tts = None
import config

def timedelta_to_ass(td: timedelta) -> str:
    """Formats a timedelta as H:MM:SS.cs for ASS subtitles."""
    total_seconds = td.total_seconds()
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    centiseconds = int((total_seconds - int(total_seconds)) * 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

def _pct(rate: str) -> int:
    try:
        return int(str(rate).replace("%", "").replace("+", "") or 0)
    except ValueError:
        return 0


class VoiceAgent:
    @staticmethod
    def generate_voiceover(
        script_data: Dict[str, Any],
        output_dir: Path,
        voice: str = None,
        scene_image_paths: List[str] = None,
        caption_style: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Synchronously runs the async edge-tts generation.
        Generates dynamic saliency-aware subtitles that move up/down
        based on each scene's visual focal point.
        """
        script_data = {**script_data, "_explicit_voice": bool(voice)}
        voice = voice or config.DEFAULT_VOICE
        return asyncio.run(VoiceAgent._generate_async(script_data, output_dir, voice, scene_image_paths, caption_style))

    @staticmethod
    async def _generate_async(
        script_data: Dict[str, Any],
        output_dir: Path,
        voice: str,
        scene_image_paths: List[str] = None,
        caption_style: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        scenes = script_data.get("scenes", [])
        is_wx = bool(
            script_data.get("is_weaponx_lab")
            or script_data.get("style") == "weaponx"
            or script_data.get("target_duration") == 10.0
        )
        
        # Combine all narrations with natural micro-pauses
        full_text = " ".join(scene["narration"].strip() for scene in scenes)
        
        audio_file = output_dir / "voiceover.mp3"
        ass_file = output_dir / "subtitles.ass"
        srt_file = output_dir / "subtitles.srt"

        voice_rate = "+12%" if is_wx else config.VOICE_RATE

        async def _synthesize(rate: str):
            comm = edge_tts.Communicate(
                full_text,
                voice=voice,
                rate=rate,
                pitch=config.VOICE_PITCH,
                boundary="WordBoundary"
            )
            sm = edge_tts.SubMaker()
            audio = bytearray()
            wds = []
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    sm.feed(chunk)
                    start_sec = chunk["offset"] / 10_000_000.0
                    dur_sec = chunk["duration"] / 10_000_000.0
                    wds.append({"text": chunk["text"], "start": start_sec, "end": start_sec + dur_sec})
            return audio, sm, wds

        # Kokoro (local, more natural) is the default English engine unless an Edge voice was chosen explicitly
        engine = os.getenv("TTS_ENGINE", "kokoro").lower()
        use_kokoro = engine == "kokoro" and not script_data.get("_explicit_voice") and str(voice).startswith("en")
        if use_kokoro:
            try:
                from agents import kokoro_tts
                use_kokoro = kokoro_tts.is_available()
            except Exception:
                use_kokoro = False

        class _SrtFromWords:
            def __init__(self, wds):
                self.wds = wds

            def get_srt(self):
                from agents import kokoro_tts
                return kokoro_tts.to_srt(self.wds)

        async def _synthesize_kokoro(rate: str):
            from agents import kokoro_tts
            try:
                pct = int(str(rate).replace("%", "").replace("+", "") or 0)
            except ValueError:
                pct = 0
            tmp_mp3 = output_dir / "voiceover.kokoro.mp3"
            # am_michael speaks ~108 wpm at 1.0; KOKORO_SPEED (default 1.15) brings it near Edge's pace
            base = float(os.getenv("KOKORO_SPEED", "1.15"))
            wds = await asyncio.to_thread(kokoro_tts.synthesize, full_text, tmp_mp3, None, min(1.5, base * (1.0 + pct / 100.0)))
            data = tmp_mp3.read_bytes()
            tmp_mp3.unlink(missing_ok=True)
            return bytearray(data), _SrtFromWords(wds), wds

        synth = _synthesize_kokoro if use_kokoro else _synthesize
        try:
            audio_bytes, submaker, words = await synth(voice_rate)
        except Exception as e:
            if not use_kokoro:
                raise
            print(f"[VoiceAgent] Kokoro failed ({e}); falling back to Edge-TTS")
            synth, use_kokoro = _synthesize, False
            audio_bytes, submaker, words = await synth(voice_rate)
        print(f"[VoiceAgent] Voice engine: {'Kokoro (' + os.getenv('KOKORO_VOICE', 'am_michael') + ')' if use_kokoro else 'Edge-TTS (' + str(voice) + ')'}")

        # Duration fit: if narration overshoots the requested length, re-voice faster (max +30%)
        rate_used = voice_rate
        requested = script_data.get("target_duration")
        if requested and words:
            speech_end = words[-1]["end"] + 0.5
            requested = float(requested)
            if speech_end > requested * 1.08:
                try:
                    base_pct = int(str(voice_rate).replace("%", "").replace("+", "") or 0)
                except ValueError:
                    base_pct = 0
                needed_pct = int((speech_end / requested - 1.0) * 100) + 2
                new_pct = min(30, base_pct + needed_pct)
                if new_pct > base_pct:
                    print(f"[VoiceAgent] Narration {speech_end:.1f}s exceeds target {requested:.1f}s; re-voicing at +{new_pct}% rate...")
                    rate_used = f"+{new_pct}%"
                    audio_bytes, submaker, words = await synth(rate_used)

        with open(audio_file, "wb") as f:
            f.write(audio_bytes)

        # Restore script punctuation on the spoken words and protect the subject's name, so captions
        # break at sentence ends and never split "F-35 Lightning / II".
        from app.agents import caption_chunker
        caption_chunker.prepare(words, full_text, caption_chunker.subject_phrases(script_data))

        # Save standard SRT (phrase-aware cues with punctuation)
        srt_content = caption_chunker.to_srt(words) if words else submaker.get_srt()
        with open(srt_file, "w", encoding="utf-8") as f:
            f.write(srt_content)

        target_dur = script_data.get("target_duration")
        if target_dur:
            target_dur = float(target_dur)
            actual_speech_dur = words[-1]["end"] + 0.5 if words else target_dur
            total_duration = max(target_dur, actual_speech_dur)
        elif is_wx:
            total_duration = 10.0
        else:
            total_duration = words[-1]["end"] + 0.5 if words else 25.0

        # Estimate scene durations proportionally based on scene word counts
        scene_durations = VoiceAgent._calculate_scene_durations(scenes, total_duration)

        # Generate custom dynamic saliency-aware ASS subtitle file
        VoiceAgent._generate_styled_ass(
            words, ass_file, scenes, scene_durations, scene_image_paths, is_wx=is_wx, caption_style=caption_style
        )

        return {
            "audio_path": str(audio_file),
            "ass_path": str(ass_file),
            "srt_path": str(srt_file),
            "total_duration": total_duration,
            "scene_durations": scene_durations,
            "word_count": len(words),
            "voice_engine": "kokoro" if use_kokoro else "edge-tts",
            # Speed-up applied ON TOP of the engine's normal pace (0 = natural)
            "rate_pct": max(0, _pct(rate_used) - _pct(voice_rate)),
        }

    @staticmethod
    def _calculate_scene_durations(scenes: List[Dict[str, Any]], total_duration: float) -> List[float]:
        if not scenes:
            return [total_duration]
        min_dur = min(1.2, round(total_duration / len(scenes), 2))
        word_counts = [max(1, len(s["narration"].split())) for s in scenes]
        total_words = sum(word_counts)
        
        # Proportional duration
        durations = []
        for wc in word_counts:
            d = (wc / total_words) * total_duration
            durations.append(max(min_dur, round(d, 2)))
        
        # Adjust last scene to match total_duration exactly
        diff = total_duration - sum(durations)
        durations[-1] = max(min_dur, round(durations[-1] + diff, 2))
        return durations

    @staticmethod
    def _generate_styled_ass(
        words: List[Dict[str, Any]],
        ass_path: Path,
        scenes: List[Dict[str, Any]] = None,
        scene_durations: List[float] = None,
        scene_image_paths: List[str] = None,
        is_wx: bool = False,
        caption_style: Dict[str, Any] = None
    ):
        """
        Creates dynamic saliency-aware ASS subtitles for vertical 1080x1920 YouTube Shorts.
        Analyzes scene images to detect whether the subject is in the top or bottom half,
        and dynamically shifts text to avoid occluding the primary visual subject!
        """
        # Determine text placement ('top' or 'bottom') for each scene
        scene_placements = []
        if is_wx:
            scene_placements = ["weaponx_bottom"] * (len(scenes) if scenes else 2)
        elif scene_image_paths:
            for p in scene_image_paths:
                placement = VoiceAgent._detect_image_focal_area(p)
                scene_placements.append(placement)
        else:
            scene_placements = ["bottom"] * (len(scenes) if scenes else 5)

        # Build timeline map for scenes: [(start_sec, end_sec, placement), ...]
        timeline = []
        cur_t = 0.0
        durations = scene_durations or [5.0] * len(scene_placements)
        for idx, dur in enumerate(durations):
            plc = scene_placements[idx] if idx < len(scene_placements) else "bottom"
            timeline.append((cur_t, cur_t + dur, plc))
            cur_t += dur

        if caption_style:
            # User-chosen caption design. "auto" position keeps the scene-aware top/bottom placement.
            from app.agents.caption_style import render_ass

            def placement_at(t: float) -> str:
                for t_start, t_end, plc in timeline:
                    if t_start <= t <= t_end:
                        return "top" if plc == "top" else "bottom"
                return "bottom"

            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(render_ass(words, caption_style, placement_at))
            return

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.VIDEO_WIDTH}
PlayResY: {config.VIDEO_HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: BottomDefault,Impact,80,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,7,3,2,60,60,320,1
Style: BottomHighlight,Impact,84,&H0000D7FF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,4,2,60,60,320,1
Style: TopDefault,Impact,80,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,7,3,8,60,60,300,1
Style: TopHighlight,Impact,84,&H0000D7FF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,4,8,60,60,300,1
Style: WeaponXBottom,Impact,62,&H0000D7FF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,6,3,2,50,50,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        from app.agents.caption_chunker import chunk_words, display_text
        chunks = chunk_words(words, 3)
        # Phase 2 KaraFun-Style Animated Dynamic Captions:
        # Highlights the active spoken word in vibrant cyan (&H00FEF200& / #00f2fe)
        # with an eye-catching 1.15x scale pop (\fscx115\fscy115) while keeping
        # adjacent words in the chunk clean white (&H00FFFFFF&)!
        ACTIVE_CYAN = r"{\c&H00FEF200&\fscx115\fscy115}"
        INACTIVE_WHITE = r"{\c&H00FFFFFF&\fscx100\fscy100}"
        RESET_TAG = r"{\c&H00FFFFFF&\fscx100\fscy100}"

        for ci, chunk in enumerate(chunks):
            next_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else None

            # Resolve placement style for this chunk
            chunk_mid_s = (chunk[0]["start"] + chunk[-1]["end"]) / 2.0
            style_name = "WeaponXBottom" if is_wx else "BottomHighlight"
            if not is_wx:
                for t_start, t_end, plc in timeline:
                    if t_start <= chunk_mid_s <= t_end:
                        style_name = "TopHighlight" if plc == "top" else "BottomHighlight"
                        break

            # Generate word-by-word KaraFun pop states for this chunk
            for k, active_word in enumerate(chunk):
                w_start = active_word["start"]
                # Extend end seamlessly into next word or chunk to eliminate visual flicker
                if k + 1 < len(chunk):
                    w_end = min(active_word["end"] + 0.08, chunk[k + 1]["start"])
                    if w_end <= w_start:
                        w_end = active_word["end"] + 0.08
                else:
                    max_ext = next_start if next_start else (active_word["end"] + 0.25)
                    w_end = min(active_word["end"] + 0.18, max_ext)

                start_td = timedelta(seconds=max(0.0, w_start))
                end_td = timedelta(seconds=max(w_start + 0.05, w_end))
                start_str = timedelta_to_ass(start_td)
                end_str = timedelta_to_ass(end_td)

                # Assemble chunk text with active word highlighted
                chunk_tokens = []
                for j, w in enumerate(chunk):
                    raw_w = display_text(w).upper().replace("\r\n", " ").replace("\n", " ").strip()
                    if j == k:
                        chunk_tokens.append(f"{ACTIVE_CYAN}{raw_w}{RESET_TAG}")
                    else:
                        chunk_tokens.append(f"{INACTIVE_WHITE}{raw_w}{RESET_TAG}")

                line_text = " ".join(chunk_tokens)
                events.append(f"Dialogue: 0,{start_str},{end_str},{style_name},,0,0,0,,{line_text}")

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")

    @staticmethod
    def _detect_image_focal_area(img_path: str) -> str:
        """
        Analyzes edge energy of top third vs bottom third of the image.
        If the bottom third has dense visual details (e.g. cockpit, weapon body),
        returns 'top' so text moves UP to avoid covering the subject!
        """
        try:
            import numpy as np
            from PIL import Image, ImageFilter
            if not Path(img_path).exists():
                return "bottom"

            with Image.open(img_path) as im:
                gray = im.convert("L")
                edges = gray.filter(ImageFilter.FIND_EDGES)
                arr = np.array(edges)
                
                # Top third zone (Y from 250 to 750)
                top_zone = arr[250:750, :]
                # Bottom third zone (Y from 1200 to 1700)
                bottom_zone = arr[1200:1700, :]

                top_energy = float(np.mean(top_zone))
                bottom_energy = float(np.mean(bottom_zone))

                # If bottom third contains the primary visual detail, move text to TOP
                if bottom_energy > top_energy * 1.25:
                    return "top"
                return "bottom"
        except Exception:
            return "bottom"
