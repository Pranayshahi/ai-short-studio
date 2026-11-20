"""
Agent: Hindi Speaking Agent & LLM Voiceover Pipeline (agents/hindi_voice_agent.py)
Autonomous Hindi scriptwriting, translation, and neural voiceover agent for YouTube Shorts:
1. Translates & localizes defense/military/tech scripts into high-impact, authentic Hindi (शुद्ध और प्रभावशाली हिंदी).
2. Generates natural studio-grade Hindi voiceovers using Microsoft Neural Hindi voices (hi-IN-MadhurNeural, hi-IN-SwaraNeural) via edge-tts.
3. Synthesizes synchronized Devanagari word-level subtitles (.ass / .srt).
4. 100% Free with zero API subscriptions or credit cards required.
"""

import os
import re
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for sp in PROJECT_ROOT.glob(".venv/lib/python*/site-packages"):
    if str(sp) not in sys.path:
        sys.path.insert(0, str(sp))

import edge_tts
import config

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    bundled = list((config.BASE_DIR / ".venv").glob("**/imageio_ffmpeg/binaries/ffmpeg*"))
    FFMPEG_EXE = str(bundled[0]) if bundled else "ffmpeg"


def timedelta_to_ass(td: timedelta) -> str:
    """Formats a timedelta as H:MM:SS.cs for ASS subtitles."""
    total_seconds = td.total_seconds()
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    centiseconds = int((total_seconds - int(total_seconds)) * 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


class HindiVoiceAgent:
    """
    Autonomous Hindi Voice Agent for AI Shorts Studio.
    Converts English scripts or research into natural Hindi narration and synthesizes neural audio.
    """

    AGENT_NAME = "hindi-voice-agent"

    HINDI_VOICES = {
        "hi-IN-MadhurNeural": {
            "name": "Madhur (मधुर)",
            "gender": "Male",
            "style": "Deep Military / Authoritative Documentary",
            "locale": "hi-IN"
        },
        "hi-IN-SwaraNeural": {
            "name": "Swara (स्वरा)",
            "gender": "Female",
            "style": "Dynamic News / Fast-Paced Narrator",
            "locale": "hi-IN"
        }
    }

    # Core military/tech translation mapping for fallback translation
    DEFENSE_HINDI_VOCAB = {
        "fighter jet": "लड़ाकू विमान",
        "stealth bomber": "स्टील्थ बॉम्बर",
        "bomber": "बमवर्षक विमान",
        "hypersonic": "हाइपरसोनिक",
        "missile": "मिसाइल",
        "nuclear submarine": "परमाणु पनडुब्बी",
        "submarine": "पनडुब्बी",
        "aircraft carrier": "विमानवाहक पोत",
        "air defense": "वायु रक्षा प्रणाली",
        "radar": "रडार",
        "speed": "गति",
        "range": "मारक क्षमता",
        "warfare": "आधुनिक युद्ध",
        "weapon": "घातक हथियार",
        "military": "सैन्य शक्ति",
        "defense": "रक्षा तकनीक",
        "engine": "इंजन",
        "payload": "पेलोड क्षमता",
        "maximum speed": "अधिकतम गति",
        "mach": "मैक",
        "popular": "लोकप्रिय",
        "calibers": "कैलिबर",
        "ak-47": "एके-47",
        "assault rifle": "असॉल्ट राइफल",
        "tank": "बख्तरबंद टैंक",
        "drone": "मानवरहित ड्रोन",
        "laser": "लेजर हथियार"
    }

    def __init__(self):
        self.name = self.AGENT_NAME

    def translate_or_create_hindi_script(
        self,
        script_data: Dict[str, Any],
        topic: str = ""
    ) -> Dict[str, Any]:
        """
        Translates script data into authentic, high-impact Hindi.
        Uses Gemini LLM if configured, otherwise uses contextual Hindi defense translation.
        """
        topic = topic or script_data.get("topic", "")
        scenes = script_data.get("scenes", [])
        
        # Check if Gemini API Key is available
        gemini_key = os.getenv("GEMINI_API_KEY", "") or getattr(config, "GEMINI_API_KEY", "")
        if not gemini_key and getattr(config, "STUDIO_SETTINGS_FILE", None) and config.STUDIO_SETTINGS_FILE.exists():
            try:
                settings = json.loads(config.STUDIO_SETTINGS_FILE.read_text(encoding="utf-8"))
                gemini_key = settings.get("gemini_api_key", "")
            except Exception:
                pass

        translated = None
        if gemini_key:
            try:
                translated = self._translate_via_gemini(script_data, topic, gemini_key)
                if not (translated and "scenes" in translated):
                    translated = None
            except Exception as e:
                print(f"[HindiVoiceAgent] Gemini translation note: {e}")
                translated = None

        if translated is None:
            # Local LLM (Ollama, free): a real translation of what each scene says
            translated = self._translate_via_ollama(script_data, topic)

        if translated is None:
            # Offline fallback (no LLM available)
            translated = self._translate_offline(script_data, topic)

        # Scenes the user already wrote in Hindi (Devanagari) are kept exactly as written
        for src, dst in zip(scenes, translated.get("scenes", [])):
            own = str(src.get("narration", ""))
            if re.search(r"[\u0900-\u097F]", own):
                dst["narration"] = own
                dst["narration_hindi"] = own
        return translated

    def _translate_via_gemini(self, script_data: Dict[str, Any], topic: str, api_key: str) -> Optional[Dict[str, Any]]:
        """Queries Google Gemini to translate and polish script for Hindi YouTube Shorts."""
        try:
            import urllib.request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            
            scenes_text = "\n".join([f"Scene {s.get('scene_number', i+1)}: {s.get('narration', '')}" for i, s in enumerate(script_data.get("scenes", []))])
            prompt = (
                f"You are a professional Hindi defense documentary scriptwriter for YouTube Shorts.\n"
                f"Topic: {topic}\n"
                f"Translate and adapt the following scenes into pure, punchy, energetic Hindi (Devanagari script).\n"
                f"Tone: Authoritative, patriotic, high-retention military documentary (e.g. 'क्या आप जानते हैं...', 'यह घातक हथियार...').\n"
                f"Keep sentence length concise for 15-30 second shorts.\n\n"
                f"ORIGINAL ENGLISH SCENES:\n{scenes_text}\n\n"
                f"Output ONLY valid JSON in this exact structure:\n"
                f'{{"title": "Hindi Title", "scenes": [{{"scene_number": 1, "narration": "हिंदी संवाद"}}]}}'
            )

            req_payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(req_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                result = json.loads(response.read().decode("utf-8"))
                content = result["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(content)

                new_script = dict(script_data)
                new_script["title_hindi"] = data.get("title", script_data.get("title", topic))
                new_scenes = []
                for idx, sc in enumerate(script_data.get("scenes", [])):
                    sc_copy = dict(sc)
                    if idx < len(data.get("scenes", [])):
                        sc_copy["narration_hindi"] = data["scenes"][idx].get("narration", sc.get("narration"))
                        sc_copy["narration_orig"] = sc.get("narration")
                        sc_copy["narration"] = sc_copy["narration_hindi"]
                    new_scenes.append(sc_copy)
                new_script["scenes"] = new_scenes
                new_script["language"] = "hi"
                return new_script
        except Exception as e:
            print(f"[HindiVoiceAgent] Gemini API error: {e}")
            return None

    HINDI_SCHEMA = {"type": "object", "properties": {
        "title": {"type": "string"},
        "scenes": {"type": "array", "items": {"type": "object", "properties": {
            "scene_number": {"type": "integer"}, "narration": {"type": "string"}},
            "required": ["scene_number", "narration"]}}},
        "required": ["title", "scenes"]}

    def _translate_via_ollama(self, script_data: Dict[str, Any], topic: str) -> Optional[Dict[str, Any]]:
        """Translates each scene with the local Ollama model (same one as the scriptwriter).
        Returns None (offline templates are used) if Ollama can't run or the output isn't usable Hindi."""
        try:
            from agents import script_writer
            from app.automation import resources
            if not script_writer.can_run():
                return None
            src = script_data.get("scenes", [])
            if not src:
                return None
            scenes_text = "\n".join(
                f"Scene {i + 1}: {s.get('narration_orig') or s.get('narration', '')}" for i, s in enumerate(src))
            prompt = (
                "Translate this YouTube Shorts voiceover into natural, spoken Hindi (Devanagari script).\n"
                f"Topic: {topic}\n"
                "Rules: translate each scene's meaning faithfully - do not add facts, numbers or opinions. "
                "Keep names, model designations and numbers exactly as written (e.g. F-35, T-90, 2026) in Latin script. "
                "Keep each scene about as long as the English. Use everyday Hindi a viewer would hear on a news channel. "
                f"Return exactly {len(src)} scenes, numbered like the input.\n\n"
                f"SCENES:\n{scenes_text}"
            )
            with resources.lease("ollama"):
                if not script_writer.is_available():
                    return None
                try:
                    data = script_writer._ollama(prompt, self.HINDI_SCHEMA, timeout=180)
                finally:
                    script_writer._unload()  # free the model now, so music/clip engines aren't blocked
            out = data.get("scenes") or []
            if len(out) != len(src):
                print(f"[HindiVoiceAgent] Ollama returned {len(out)} scenes for {len(src)}; using offline templates")
                return None
            new_scenes = []
            for sc, tr in zip(src, out):
                hi = str(tr.get("narration") or "").strip()
                deva = len(re.findall(r"[\u0900-\u097F]", hi))
                latin = len(re.findall(r"[A-Za-z]", hi))
                if not hi or deva < 0.6 * (deva + latin):
                    print("[HindiVoiceAgent] Ollama output is not mostly Hindi; using offline templates")
                    return None
                # Every number in the English must survive the translation
                en = sc.get("narration_orig") or sc.get("narration", "")
                if any(n not in hi for n in re.findall(r"\d[\d,.]*\d|\d", en)):
                    print(f"[HindiVoiceAgent] A number was lost in translation ({en!r}); using offline templates")
                    return None
                c = dict(sc)
                c["narration_orig"] = en
                c["narration_hindi"] = hi
                c["narration"] = hi
                new_scenes.append(c)
            new_script = dict(script_data)
            new_script["title_hindi"] = str(data.get("title") or "").strip() or script_data.get("title", topic)
            new_script["scenes"] = new_scenes
            new_script["language"] = "hi"
            new_script["translation_mode"] = f"ollama:{script_writer.MODEL}"
            print(f"[HindiVoiceAgent] Translated {len(new_scenes)} scenes with local {script_writer.MODEL}")
            return new_script
        except Exception as e:
            print(f"[HindiVoiceAgent] Ollama translation skipped: {e}")
            return None

    def _translate_offline(self, script_data: Dict[str, Any], topic: str) -> Dict[str, Any]:
        """Offline contextual Hindi translation for military & technology shorts."""
        new_script = dict(script_data)
        topic_hi = topic
        for eng, hi in self.DEFENSE_HINDI_VOCAB.items():
            topic_hi = re.sub(rf"\b{re.escape(eng)}\b", hi, topic_hi, flags=re.IGNORECASE)

        new_script["title_hindi"] = f"जानिए {topic_hi} के बारे में रहस्य"
        new_scenes = []

        # Without an LLM we cannot truly translate, so use short lines that are accurate for ANY
        # military topic (no invented specs such as radar evasion or air combat), and never mix
        # untranslated English into the Hindi narration.
        opening = "क्या आप {topic} की असली कहानी जानते हैं?"
        middle_lines = [
            "{topic} को आधुनिक सेनाओं में ख़ास जगह मिली है।",
            "इसका डिज़ाइन असली युद्ध के अनुभवों से निकला है।",
            "दुनिया भर के रक्षा विशेषज्ञ इस पर नज़र रखते हैं।",
            "हर पीढ़ी के साथ इसकी तकनीक और बेहतर हुई है।",
            "इसकी विश्वसनीयता ही इसकी सबसे बड़ी ताकत है।",
        ]
        closing = "{topic} पर आपकी क्या राय है? कमेंट में बताएं।"

        src_scenes = script_data.get("scenes", [])
        for idx, sc in enumerate(src_scenes):
            sc_copy = dict(sc)
            raw_en = sc.get("narration_orig") or sc.get("narration", "")
            if idx == 0:
                hi_text = opening.format(topic=topic_hi)
            elif idx == len(src_scenes) - 1 and len(src_scenes) > 1:
                hi_text = closing.format(topic=topic_hi)
            else:
                hi_text = middle_lines[(idx - 1) % len(middle_lines)].format(topic=topic_hi)

            sc_copy["narration_hindi"] = hi_text
            sc_copy["narration_orig"] = raw_en
            sc_copy["narration"] = hi_text
            new_scenes.append(sc_copy)

        new_script["translation_mode"] = "offline_neutral_templates"
        new_script["scenes"] = new_scenes
        new_script["language"] = "hi"
        return new_script

    def generate_hindi_voiceover(
        self,
        script_data: Dict[str, Any],
        output_dir: Path,
        voice: str = "hi-IN-MadhurNeural",
        caption_style: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Synchronously generates neural Hindi voiceover and aligned subtitles.
        """
        if voice not in self.HINDI_VOICES:
            voice = "hi-IN-MadhurNeural"
        self._caption_style = caption_style
        return asyncio.run(self._generate_async(script_data, output_dir, voice))

    async def _generate_async(
        self,
        script_data: Dict[str, Any],
        output_dir: Path,
        voice: str
    ) -> Dict[str, Any]:
        scenes = script_data.get("scenes", [])
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Full Hindi text
        full_text = " ".join(sc.get("narration_hindi", sc.get("narration", "")).strip() for sc in scenes)
        if not full_text:
            full_text = "रक्षा एवं सैन्य तकनीक का सबसे शक्तिशाली हथियार।"

        audio_file = output_dir / "voiceover.mp3"
        ass_file = output_dir / "subtitles.ass"
        srt_file = output_dir / "subtitles.srt"

        async def _synthesize(rate: str):
            comm = edge_tts.Communicate(full_text, voice=voice, rate=rate, boundary="WordBoundary")
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

        base_pct = 12  # energetic cadence for Shorts
        audio_bytes, submaker, words = await _synthesize(f"+{base_pct}%")

        requested = script_data.get("target_duration")
        if requested and words:
            requested = float(requested)
            speech_end = words[-1]["end"] + 0.5
            if speech_end > requested * 1.08:
                new_pct = min(30, base_pct + int((speech_end / requested - 1.0) * 100) + 2)
                if new_pct > base_pct:
                    print(f"[HindiVoiceAgent] Narration {speech_end:.1f}s exceeds target {requested:.1f}s; re-voicing at +{new_pct}%...")
                    audio_bytes, submaker, words = await _synthesize(f"+{new_pct}%")

        with open(audio_file, "wb") as f:
            f.write(audio_bytes)

        # Phrase-aware captions: restore punctuation (incl. the danda) so cues end at sentence ends
        from app.agents import caption_chunker
        caption_chunker.prepare(words, full_text, [script_data.get("topic")])

        # Generate standard SRT
        srt_content = caption_chunker.to_srt(words) if words else submaker.get_srt()
        with open(srt_file, "w", encoding="utf-8") as f:
            f.write(srt_content)

        # Generate styled ASS subtitles for Hindi Devanagari typography
        caption_style = getattr(self, "_caption_style", None)
        if caption_style:
            from app.agents.caption_style import render_ass
            ass_content = render_ass(words, caption_style)
        else:
            ass_content = self._create_hindi_ass_subtitles(words, scenes)
        with open(ass_file, "w", encoding="utf-8") as f:
            f.write(ass_content)

        total_dur = words[-1]["end"] + 0.5 if words else 25.0
        scene_durations = self._calculate_scene_durations(scenes, total_dur)

        return {
            "audio_path": str(audio_file),
            "ass_path": str(ass_file),
            "srt_path": str(srt_file),
            "total_duration": total_dur,
            "scene_durations": scene_durations,
            "word_count": len(words),
            "voice": voice,
            "language": "hi"
        }

    def _create_hindi_ass_subtitles(self, words: List[Dict[str, Any]], scenes: List[Dict[str, Any]]) -> str:
        """Creates styled ASS subtitles formatted specifically for Hindi Devanagari text."""
        header = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n"
            "ScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: HindiBold,Mukta,62,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,1,5,3,2,60,60,260,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        events = []
        # Group words into 3-5 word chunks for optimal readability
        from app.agents.caption_chunker import chunk_words, display_text
        for chunk in chunk_words(words, 4):
            start_td = timedelta(seconds=chunk[0]["start"])
            end_td = timedelta(seconds=chunk[-1]["end"] + 0.1)
            text_str = " ".join(display_text(w) for w in chunk)
            start_str = timedelta_to_ass(start_td)
            end_str = timedelta_to_ass(end_td)
            events.append(f"Dialogue: 0,{start_str},{end_str},HindiBold,,0,0,0,,{text_str}")

        return header + "\n".join(events) + "\n"

    def _calculate_scene_durations(self, scenes: List[Dict[str, Any]], total_duration: float) -> List[float]:
        """Calculates scene durations based on Hindi word count proportion."""
        if not scenes:
            return [total_duration]

        word_counts = []
        for sc in scenes:
            text = sc.get("narration_hindi", sc.get("narration", ""))
            word_counts.append(max(1, len(text.split())))

        total_words = sum(word_counts)
        durations = []
        for wc in word_counts:
            dur = (wc / total_words) * total_duration
            durations.append(max(3.0, round(dur, 2)))

        diff = total_duration - sum(durations)
        durations[-1] = max(2.5, round(durations[-1] + diff, 2))
        return durations

    def convert_project_to_hindi(
        self,
        project_record: Dict[str, Any],
        voice: str = "hi-IN-MadhurNeural"
    ) -> Dict[str, Any]:
        """
        End-to-end converter: Translates an existing project into Hindi,
        synthesizes Hindi voiceover, and re-renders the final short video.
        """
        project_dir = Path(project_record.get("project_dir", config.PROJECTS_DIR / project_record["id"]))
        topic = project_record.get("topic", "Defense Technology")
        
        # 1. Translate script
        base = dict(project_record.get("content_analysis") or {})
        if project_record.get("scenes"):
            base["scenes"] = project_record["scenes"]  # include the user's scene text edits
        base["target_duration"] = project_record.get("target_duration") or base.get("target_duration")
        hindi_script = self.translate_or_create_hindi_script(base, topic=topic)
        project_record["content_analysis_hindi"] = hindi_script
        project_record["title_hindi"] = hindi_script.get("title_hindi")
        project_record["language"] = "hi"
        project_record["hindi_voice"] = voice
        project_record["voice"] = voice  # keep re-renders on the chosen Hindi voice

        # 2. Generate Hindi Voiceover
        hindi_audio = self.generate_hindi_voiceover(
            hindi_script, project_dir, voice=voice, caption_style=project_record.get("caption_style")
        )
        project_record["voiceover_hindi"] = hindi_audio
        project_record["duration"] = hindi_audio["total_duration"]

        # 3. Re-composite video with Hindi voiceover & subtitles
        from app.agents.video_composer import VideoComposer
        composer = VideoComposer()
        image_paths = [sc["image_path"] for sc in project_record.get("scenes", []) if sc.get("image_path")]
        if not image_paths:
            # Fallback to output directory images
            image_paths = sorted([str(p) for p in (project_dir / "scenes").glob("scene_*.png")])

        if image_paths:
            final_video = composer.compose_video(
                image_paths=image_paths,
                scene_durations=hindi_audio["scene_durations"],
                voiceover_path=hindi_audio["audio_path"],
                ass_path=hindi_audio["ass_path"],
                output_dir=project_dir,
                topic=topic,
                with_voice=True,
                with_music=project_record.get("with_music", True),
                music_path=project_record.get("music_path") if project_record.get("music_path") and Path(str(project_record.get("music_path"))).exists() else None,
                music_volume=project_record.get("music_volume"),
            )
            project_record["video_path"] = final_video
            project_record["final_short_path"] = final_video

        return project_record
