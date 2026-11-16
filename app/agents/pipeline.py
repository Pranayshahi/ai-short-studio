import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import config
from app.utils.storage import StorageManager
from app.agents.research_agent import ResearchAgent
from app.agents.script_agent import ScriptAgent
from app.agents.voice_agent import VoiceAgent
from app.agents.creator_agent import CreatorAgent
from app.agents.video_composer import VideoComposer
from app.agents.qa_validator_agent import QAValidatorAgent
from app.agents.youtube_publisher import YouTubePublisher

from agents.topic_agent import TopicAgent
from agents.content_analyser import ContentAnalyserAgent
from agents.image_generator import ImageGeneratorAgent
from agents.verify_video import VerifyVideoAgent
from agents.hindi_voice_agent import HindiVoiceAgent
from agents.music_generator import AIMusicGenerator
from agents.openmontage_agent import OpenMontageAgent

def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)[:40]

class ShortsPipeline:
    def __init__(self):
        self.composer = VideoComposer()
        self.topic_agent = TopicAgent()
        self.content_analyser = ContentAnalyserAgent()
        self.image_generator = ImageGeneratorAgent(
            target_width=config.VIDEO_WIDTH,
            target_height=config.VIDEO_HEIGHT,
        )
        self.verify_video = VerifyVideoAgent(
            target_width=config.VIDEO_WIDTH,
            target_height=config.VIDEO_HEIGHT,
        )
        self.hindi_agent = HindiVoiceAgent()
        self.music_generator = AIMusicGenerator()
        self.openmontage = OpenMontageAgent()

    def prepare_project(
        self,
        custom_topic: Optional[str] = None,
        style: str = "default",
        with_voice: bool = True,
        with_music: bool = True,
        duration: Optional[float] = None,
        audio_mode: Optional[str] = None,
        language: str = "en",
        voice: Optional[str] = None,
        music_track: Optional[str] = None,
        music_volume: Optional[float] = 0.22,
        channel: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Initializes a pending project record immediately using 'topic-agent'
        so the web UI can track progress and display deep research sources.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        is_wx_style = (style or "").lower() in ("weaponx", "weaponx_lab", "weaponx lab")
        is_om_style = (style or "").lower() in ("openmontage", "open_montage", "open montage")
        if duration is not None:
            target_dur = max(5.0, min(180.0, float(duration)))
        elif is_wx_style:
            target_dur = 10.0
        elif is_om_style:
            target_dur = 30.0
        else:
            target_dur = 30.0

        topic_info = self.topic_agent.run(
            topic=custom_topic,
            target_duration=target_dur,
            style=style,
        )
        topic_title = topic_info["topic"]
        effective_style = topic_info.get("style", style)

        slug = slugify(topic_title)
        project_id = f"{timestamp}_{slug}"
        project_dir = config.PROJECTS_DIR / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        eff_audio_mode = audio_mode or ("with_voice" if with_voice and with_music else ("without_music" if with_voice else "without_voice"))

        project_record = {
            "id": project_id,
            "title": f"Generating: {topic_title}...",
            "topic": topic_title,
            "category": topic_info.get("category", "Defense Tech"),
            "style": effective_style,
            "is_weaponx_lab": bool(topic_info.get("is_weaponx_lab")),
            "is_openmontage": bool(is_om_style or effective_style == "openmontage"),
            "engine": "OpenMontage" if is_om_style else ("WeaponX Lab" if is_wx_style else "AI Shorts Studio"),
            "aspect_ratio": "9:16",
            "target_duration": target_dur,
            "duration": target_dur,
            "with_voice": with_voice,
            "with_music": with_music,
            "audio_mode": eff_audio_mode,
            "language": language,
            "voice": voice,
            "music_track": music_track,
            "music_volume": music_volume,
            "channel": self._channel_key(channel),
            "status": "in_progress",
            "progress_step": "topic-agent: Deep researching topic & sending instructions...",
            "project_dir": str(project_dir),
            "topic_research": topic_info,
            "created_at": datetime.now().isoformat()
        }
        default_caption_style = self._default_caption_style()
        if default_caption_style:
            project_record["caption_style"] = default_caption_style
        StorageManager.save_project(project_record)
        return project_record, topic_info

    @staticmethod
    def _default_caption_style():
        """The caption design saved as 'default for new videos' in the studio, if any."""
        try:
            import json
            saved = json.loads(config.STUDIO_SETTINGS_FILE.read_text(encoding="utf-8"))
            style = saved.get("caption_style_default")
            if isinstance(style, dict):
                from app.agents.caption_style import normalize_style
                return normalize_style(style)
        except Exception:
            pass
        return None

    def run(
        self,
        custom_topic: Optional[str] = None,
        auto_publish: bool = False,
        style: str = "default",
        with_voice: bool = True,
        with_music: bool = True,
        duration: Optional[float] = None,
        audio_mode: Optional[str] = None,
        language: str = "en",
        voice: Optional[str] = None,
        music_track: Optional[str] = None,
        music_volume: Optional[float] = 0.22,
        prepared_project: Optional[Dict[str, Any]] = None,
        prepared_topic_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes the end-to-end autonomous YouTube Shorts creation pipeline.
        Supports 'style': 'default' or 'weaponx'.
        Supports 'duration': 5.0 to 180.0 seconds (3 minutes).
        Supports audio modes: 'with_voice' (Voice + BGM), 'without_music' (Voice Only), 'without_voice' (Music Only), 'mute'.
        Supports Hindi voiceover via HindiVoiceAgent (Madhur/Swara) and AI/YouTube music soundtrack.
        """
        if prepared_project and prepared_topic_info:
            project_record = prepared_project
            topic_info = prepared_topic_info
            topic_title = topic_info["topic"]
            project_id = project_record["id"]
            project_dir = Path(project_record["project_dir"])
            timestamp = project_id.split("_")[0]
            with_voice = project_record.get("with_voice", with_voice)
            with_music = project_record.get("with_music", with_music)
            target_dur = float(project_record.get("target_duration", duration or 30.0))
            language = project_record.get("language", language)
            voice = project_record.get("voice", voice)
            music_track = project_record.get("music_track", music_track)
            music_volume = project_record.get("music_volume", music_volume)
        else:
            project_record, topic_info = self.prepare_project(
                custom_topic=custom_topic,
                style=style,
                with_voice=with_voice,
                with_music=with_music,
                duration=duration,
                audio_mode=audio_mode,
                language=language,
                voice=voice,
                music_track=music_track,
                music_volume=music_volume
            )
            topic_title = topic_info["topic"]
            project_id = project_record["id"]
            project_dir = Path(project_record["project_dir"])
            timestamp = project_id.split("_")[0]
            target_dur = float(project_record.get("target_duration", 30.0))

        style = topic_info.get("style", style)

        if with_voice and with_music:
            mode_str = "VOICE + MUSIC"
        elif with_voice and not with_music:
            mode_str = "WITHOUT MUSIC (VOICE ONLY)"
        elif not with_voice and with_music:
            mode_str = "WITHOUT VOICE (MUSIC ONLY)"
        else:
            mode_str = "MUTE (NO AUDIO)"

        print("\n" + "=" * 60)
        print(f"🎬 [AI Shorts Studio] Starting automated pipeline ({style.upper()} style · {mode_str} · {target_dur}s) at {timestamp}")
        print(f"-> Project ID: {project_id}")
        print(f"-> Selected Topic: {topic_title}")
        print("=" * 60)

        try:
            # Step 2: Content Analyser Agent (checks & corrects output from topic-agent & creates image_data)
            print(f"\n[Step 2/7] 🧠 Running 'content-analyser' agent to check & correct researched text and build image_data ({style} style · {target_dur}s)...")
            project_record["progress_step"] = "content-analyser: Checking script & building image_data..."
            StorageManager.save_project(project_record)
            script_data = self.content_analyser.run(topic_research=topic_info, style=style, target_duration=target_dur)
            project_record["content_analysis"] = script_data
            print(f"-> Title: {script_data['title']}")
            print(f"-> Scenes: {len(script_data['scenes'])} scenes verified & corrected")

            # Step 3: Image Generator Agent (deep search, source check, topic match & CHANGE_IMAGE replacement)
            print(f"\n[Step 3/7] 🖼️ Running 'image-generator' agent using image_data from content-analyser...")
            project_record["progress_step"] = "image-generator: Generating & verifying topic images..."
            StorageManager.save_project(project_record)
            image_report = self.image_generator.run(
                topic_research=topic_info,
                content_analysis=script_data,
                output_dir=project_dir,
                style=style,
            )
            project_record["image_report"] = image_report
            visual_records = image_report["visual_records"]
            image_paths = image_report["image_paths"]

            if style == "openmontage":
                print(f"[{self.openmontage.AGENT_NAME}] 🎬 Applying OpenMontage 35mm documentary film grade & manifest...")
                for p in image_paths:
                    self.openmontage.apply_openmontage_film_grade(Path(p))
                om_brief = self.openmontage.build_montage_brief(
                    topic=topic_title,
                    category=project_record.get("category", "Defense Tech"),
                    target_duration=target_dur
                )
                project_record["openmontage_brief"] = om_brief
                project_record["is_openmontage"] = True
                project_record["engine"] = "OpenMontage"
            web_count = sum(1 for v in visual_records if v["source"] == "web_free")
            ai_count = sum(1 for v in visual_records if v["source"] == "ai_generated")
            replacements = len(image_report.get("change_image_events", []))
            print(
                f"-> Sourced {len(image_paths)} verified visuals: {web_count} Web Free, {ai_count} AI "
                f"(Topic Match Avg: {image_report.get('average_topic_match_score', 90)}%, Replacements: {replacements})"
            )

            # Photo credits: CC BY / BY-SA require attribution; public-domain photos are credited as courtesy
            credits, seen = [], set()
            for v in visual_records:
                # Composite posters (e.g. WeaponX evolution poster) carry the credits of every photo inside
                for pc in v.get("photo_credits") or []:
                    link = pc.get("url")
                    if link and link not in seen:
                        seen.add(link)
                        who = re.sub(r"\s+", " ", str(pc.get("author") or "Unknown")).strip()[:60]
                        model = f"{pc.get('model')}: " if pc.get("model") else ""
                        credits.append(f"• {model}{who} · {pc.get('license') or 'see source'} · {link}")
                if v.get("source") != "web_free" or str(v.get("source_url", "")).startswith("reframed://"):
                    continue
                link = v.get("page_url") or v.get("source_url")
                if not link or link in seen:
                    continue
                seen.add(link)
                author = re.sub(r"\s+", " ", str(v.get("author") or "Unknown")).strip()[:60]
                credits.append(f"• {author} · {v.get('license') or 'see source'} · {link}")
            # Composite WeaponX posters: describe what the poster actually shows, and credit its photos
            # compactly (only licences that require it, short links) instead of the long per-photo block
            from agents import evolution_poster as _evp
            poster_rec = next((v for v in visual_records if v.get("ranked_items") or v.get("evolution_pairs")), None)
            if poster_rec:
                body = _evp.description_body(poster_rec)
                tags_line = next((ln for ln in script_data.get("description", "").splitlines() if ln.startswith("#")), "#Shorts")
                intro = "" if poster_rec.get("ranked_items") else (script_data.get('title') or '').split(' #')[0].replace(': WeaponX Lab Breakdown 🔥', '')
                script_data["description"] = "\n\n".join(x for x in (intro, body, tags_line) if x)
                credits = _evp.compact_credits(poster_rec.get("photo_credits") or [])
            if credits and "Photo credits:" not in script_data.get("description", ""):
                script_data["description"] = (script_data.get("description", "").rstrip()
                                              + "\n\nPhoto credits:\n" + "\n".join(credits[:12]))[:4900]

            # Attach source & topic-match metadata to scenes
            for idx, sc in enumerate(script_data.get("scenes", [])):
                if idx < len(visual_records):
                    sc["visual_source"] = visual_records[idx]["source"]
                    sc["visual_source_url"] = visual_records[idx].get("source_url")
                    sc["visual_source_title"] = visual_records[idx].get("source_title", "")
                    sc["visual_source_domain"] = visual_records[idx].get("source_domain")
                    sc["visual_license"] = visual_records[idx].get("license")
                    sc["topic_match_score"] = visual_records[idx].get("topic_match_score")
                    sc["image_path"] = visual_records[idx]["image_path"]

            # Step 4: Voiceover & Dynamic Saliency-Aware Subtitle Alignment
            is_hindi = (language == "hi") or bool(voice and "hi-" in str(voice))
            if is_hindi and with_voice:
                print("\n[Step 4/7] 🎙️ Running 'hindi-voice-agent' (translating script and synthesizing Hindi neural voiceover)...")
                project_record["progress_step"] = "hindi-voice-agent: Synthesizing Hindi voiceover & Devanagari subtitles..."
                StorageManager.save_project(project_record)
                hindi_script = self.hindi_agent.translate_or_create_hindi_script(script_data, topic=topic_title)
                project_record["content_analysis_hindi"] = hindi_script
                if hindi_script.get("title_hindi"):
                    project_record["title_hindi"] = hindi_script["title_hindi"]
                voice_result = self.hindi_agent.generate_hindi_voiceover(
                    hindi_script, project_dir, voice=voice or "hi-IN-MadhurNeural",
                    caption_style=project_record.get("caption_style")
                )
                print(f"-> Hindi voiceover generated: {voice_result['total_duration']:.1f}s ({voice_result['word_count']} Hindi words, voice: {voice_result['voice']})")
            else:
                print("\n[Step 4/7] 🎙️ Synthesizing voiceover and calculating saliency-aware subtitle placement...")
                project_record["progress_step"] = "Synthesizing voiceover & subtitles..."
                StorageManager.save_project(project_record)
                en_voice = voice if (voice and not str(voice).startswith("hi-")) else None
                voice_result = VoiceAgent.generate_voiceover(
                    script_data, project_dir, voice=en_voice, scene_image_paths=image_paths,
                    caption_style=project_record.get("caption_style")
                )

            if not with_voice:
                # In without-voice mode, total duration is driven by target duration
                voice_result["total_duration"] = target_dur
                voice_result["scene_durations"] = VoiceAgent._calculate_scene_durations(
                    script_data.get("scenes", []), target_dur
                )
                print(f"-> Music-only mode: set video duration to {target_dur:.1f}s")
            elif not is_hindi:
                print(f"-> Voiceover duration: {voice_result['total_duration']:.1f}s ({voice_result['word_count']} words)")

            # Step 5: Video Assembly
            # Resolve custom AI / Saved Library / YouTube Audio Library music track
            resolved_music_path = None
            if with_music:
                if music_track and str(music_track).lower() not in ("none", "mute", "off", "default"):
                    for t in self.music_generator.list_tracks():
                        if t["id"] == music_track or t["filename"] == music_track or t["name"].lower() == str(music_track).lower():
                            resolved_music_path = t["file_path"]
                            break
                    if not resolved_music_path and Path(str(music_track)).exists():
                        resolved_music_path = str(music_track)
                else:
                    # Check if user set a saved library track as default for new video creations
                    default_lib_track = self.music_generator.get_default_library_track()
                    if default_lib_track and Path(default_lib_track["file_path"]).exists():
                        resolved_music_path = default_lib_track["file_path"]
                        music_track = default_lib_track["id"]
                        print(f"-> Using user saved default library track: {default_lib_track['name']}")

            print(f"\n[Step 5/7] 🎥 Composing 9:16 vertical video (music: {music_track or 'default'}, lang: {language})...")
            project_record["progress_step"] = "Composing 9:16 vertical video..."
            StorageManager.save_project(project_record)
            # Optional motion clip for the hook scene (free engines; never blocks the video)
            self._maybe_hook_clip(script_data.get("scenes", []), image_paths, voice_result["scene_durations"],
                                  project_dir, topic_title, project_record)
            final_video_path = self.composer.compose_video(
                image_paths=image_paths,
                scene_durations=voice_result["scene_durations"],
                voiceover_path=voice_result["audio_path"] if with_voice else None,
                ass_path=voice_result["ass_path"],
                output_dir=project_dir,
                topic=topic_title,
                with_voice=with_voice,
                with_music=with_music,
                music_path=resolved_music_path,
                music_volume=music_volume,
                scene_clip_paths=[s.get("clip_path") for s in script_data.get("scenes", [])],
                scene_effects=self._scene_effects(script_data.get("scenes", []), project_record),
            )

            # Metadata guard: the pasted request (or any instruction text) must never reach YouTube
            from agents.youtube_metadata import clean_metadata
            clean_title, clean_description, clean_tags = clean_metadata(
                script_data.get("title_hindi") if is_hindi else script_data["title"],
                script_data["description"], script_data["tags"], topic_title)
            project_record.update({
                "progress_step": "Verify-video: Finalizing & verifying image and video...",
                "title": clean_title,
                "description": clean_description,
                "tags": clean_tags,
                "scenes": script_data["scenes"],
                "duration": voice_result["total_duration"],
                "target_duration": target_dur,
                "video_path": final_video_path,
                "audio_path": voice_result["audio_path"] if with_voice else None,
                "subtitles_path": voice_result["ass_path"],
                "image_paths": image_paths,
                "visual_records": visual_records,
                "with_voice": with_voice,
                "with_music": with_music,
                "audio_mode": project_record.get("audio_mode", "with_voice"),
                "language": "hi" if is_hindi else "en",
                "voice": voice or ("hi-IN-MadhurNeural" if is_hindi else "en-US-ChristopherNeural"),
                "music_track": music_track or "default",
                "music_path": resolved_music_path,
                "music_volume": music_volume,
                "youtube": None
            })
            StorageManager.save_project(project_record)

            # Step 6: Verify-video Agent (Finalizes & verifies image + video before showing)
            print("\n[Step 6/7] 🛡️ Running 'Verify-video' agent (finalizing & verifying research, content, image & video)...")
            qa_report = self.verify_video.run(
                project_record=project_record,
                topic_research=topic_info,
                content_analysis=script_data,
                image_report=image_report,
            )
            project_record["qa_report"] = qa_report
            project_record["verify_video_report"] = qa_report
            project_record["ready_for_showing"] = bool(qa_report.get("ready_for_showing", True))
            project_record["status"] = "completed"
            project_record["progress_step"] = "Ready for showing (Verified by Verify-video)"
            StorageManager.save_project(project_record)
            
            print(f"-> Verify-video Result: {qa_report['status']} (Overall Quality Score: {qa_report['overall_score']}% · Ready for showing: {project_record['ready_for_showing']})")
            print(f"   Resolution: {qa_report['stream_checks'].get('resolution')} | Duration: {qa_report['stream_checks'].get('duration_seconds')}s")

            # Step 7: YouTube Publishing (if enabled and QA passed)
            if auto_publish and qa_report.get("qa_passed"):
                print("\n[Step 7/7] 🚀 Uploading to YouTube Shorts (QA Verified)...")
                try:
                    upload_res = YouTubePublisher.upload_short(
                        video_path=final_video_path,
                        title=script_data["title"],
                        description=script_data["description"],
                        tags=script_data["tags"],
                        project_dir=str(project_dir),
                        channel=project_record.get("channel"),
                    )
                    project_record["youtube"] = upload_res
                    # Uploads are private until approved; only mark 'published' when actually live
                    project_record["status"] = (
                        "pending_approval" if upload_res.get("approval_status") == "pending_approval" else "published"
                    )
                    StorageManager.save_project(project_record)
                    print(f"-> Published: {upload_res['url']}")
                except Exception as e:
                    print(f"-> YouTube upload failed or pending auth: {e}")
                    project_record["upload_error"] = str(e)
                    StorageManager.save_project(project_record)
            else:
                print("\n[Step 7/7] ℹ️ Auto-publish disabled. Video QA verified & ready for review.")

            print("\n" + "=" * 60)
            print(f"✅ [AI Shorts Studio] Pipeline completed successfully!")
            print(f"📹 Final Video: {final_video_path}")
            print(f"🛡️ QA Score: {qa_report['overall_score']}% ({qa_report['status']})")
            print("=" * 60 + "\n")

            return project_record

        except Exception as e:
            print(f"❌ [AI Shorts Studio] Pipeline error: {e}")
            project_record["status"] = "failed"
            project_record["error"] = str(e)
            project_record["progress_step"] = f"Failed: {e}"
            StorageManager.save_project(project_record)
            raise

    @staticmethod
    def _channel_key(channel: Optional[str]) -> str:
        """Validated channel key for a new project (default channel when none given)."""
        from agents import youtube_channels as reg
        return reg.get(channel)["key"]

    @staticmethod
    def _scene_effects(scenes, project) -> list:
        """Per-scene motion & effects: scene overrides > project scene_defaults > 'auto'."""
        from agents import scene_effects as sfx
        defaults = (project or {}).get("scene_defaults") or {}
        return [sfx.resolve(sc, defaults) for sc in scenes]

    def _maybe_hook_clip(self, scenes, image_paths, scene_durations, project_dir, topic, project_record) -> None:
        """Animates scene 1's verified image into a short motion clip (HOOK_CLIP_ENGINE=auto|off|<engine>)."""
        import os
        setting = os.getenv("HOOK_CLIP_ENGINE", "auto").strip().lower()
        if setting == "off" or not scenes or not image_paths or project_record.get("is_weaponx_lab"):
            return
        from app.agents import clip_generator
        from app.automation import resources
        engines = [setting] if setting in clip_generator.ENGINES else ["ltx23_hf", "wan22_hf"]
        if setting == "auto" and os.getenv("HOOK_CLIP_LOCAL", "0") == "1":
            engines.append("phosphene_ltx")
        image = Path(image_paths[0])
        out = Path(project_dir) / "scenes" / "scene_01_clip.mp4"
        dur = float(scene_durations[0]) if scene_durations else 4.0
        prompt = (f"{scenes[0].get('visual_prompt') or topic}. Smooth cinematic camera push-in, realistic physics, "
                  "subject stays consistent with the source image.")
        project_record["progress_step"] = "Hook clip: animating the opening scene (free engine)..."
        StorageManager.save_project(project_record)
        errors = []
        for engine in engines:
            try:
                if engine == "phosphene_ltx":
                    with resources.lease("phosphene", keep_running=True):
                        meta = clip_generator.generate_scene_clip(engine, image, prompt, dur, out)
                else:
                    meta = clip_generator.generate_scene_clip(engine, image, prompt, dur, out)
                scenes[0]["clip_path"] = str(out)
                project_record["hook_clip"] = {**meta, "path": str(out)}
                print(f"[ShortsPipeline] 🎞️ Hook clip ready via {meta.get('engine_label')} in {meta.get('elapsed_seconds')}s")
                return
            except Exception as e:
                errors.append(f"{engine}: {str(e)[:160]}")
                print(f"[ShortsPipeline] Hook clip via {engine} failed: {str(e)[:160]}")
        project_record["hook_clip"] = {"skipped": True, "errors": errors}

    def rerender_project(
        self,
        project_id: str,
        with_voice: Optional[bool] = None,
        with_music: Optional[bool] = None,
        audio_mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Re-renders an existing project after the user has manually added/replaced
        images or edited scene text.
        """
        project = StorageManager.get_project_by_id(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        project_dir = Path(project["project_dir"])
        scenes = project.get("scenes", [])
        image_paths = project.get("image_paths", [])
        topic = project.get("topic", "")

        # Reconcile image paths to guarantee latest scene images (uploaded/regenerated) are picked up
        synced_paths = []
        for i, s in enumerate(scenes, 1):
            p = s.get("image_path")
            if not p or not Path(p).exists():
                candidate = project_dir / "scenes" / f"scene_{i:02d}.png"
                if candidate.exists():
                    p = str(candidate)
                    s["image_path"] = p
            if p and Path(p).exists():
                synced_paths.append(str(p))
        if synced_paths:
            image_paths = synced_paths
            project["image_paths"] = image_paths

        if audio_mode:
            if audio_mode == "without_music":
                with_voice = True
                with_music = False
            elif audio_mode == "without_voice":
                with_voice = False
                with_music = True
            elif audio_mode == "mute":
                with_voice = False
                with_music = False
            elif audio_mode in ("with_voice", "voice_and_music"):
                with_voice = True
                with_music = True

        if with_voice is None:
            with_voice = project.get("with_voice", True)
        if with_music is None:
            with_music = project.get("with_music", True)

        project["with_voice"] = with_voice
        project["with_music"] = with_music
        if audio_mode:
            project["audio_mode"] = audio_mode

        mode_desc = "Voice + Music" if with_voice and with_music else ("Without Music" if with_voice else ("Without Voice" if with_music else "Mute"))
        print(f"\n[ShortsPipeline] 🔄 Re-rendering project '{project_id}' ({mode_desc})...")

        # 1. Voiceover & Subtitles from updated scene narrations
        target_dur = float(project.get("target_duration", 30.0))
        script_data = {
            "title": project.get("title", ""),
            "scenes": scenes,
            "style": project.get("style", "default"),
            "is_weaponx_lab": bool(project.get("is_weaponx_lab") or project.get("style") == "weaponx"),
            "target_duration": target_dur,
        }
        project_voice = project.get("voice")
        is_hindi = project.get("language") == "hi" or bool(project_voice and "hi-" in str(project_voice))
        if is_hindi and with_voice:
            # Keep Hindi projects in Hindi: re-translate the (possibly edited) scenes and re-voice
            hindi_script = self.hindi_agent.translate_or_create_hindi_script(script_data, topic=topic)
            project["content_analysis_hindi"] = hindi_script
            voice_result = self.hindi_agent.generate_hindi_voiceover(
                hindi_script, project_dir, voice=project_voice or "hi-IN-MadhurNeural",
                caption_style=project.get("caption_style")
            )
        else:
            en_voice = project_voice if (project_voice and not str(project_voice).startswith("hi-")) else None
            voice_result = VoiceAgent.generate_voiceover(
                script_data, project_dir, voice=en_voice, scene_image_paths=image_paths,
                caption_style=project.get("caption_style")
            )

        if not with_voice:
            voice_result["total_duration"] = target_dur
            voice_result["scene_durations"] = VoiceAgent._calculate_scene_durations(scenes, target_dur)

        # 2. Re-compose video (preserve the project's chosen music track & volume)
        music_path = project.get("music_path")
        if music_path and not Path(str(music_path)).exists():
            music_path = None
        final_video_path = self.composer.compose_video(
            image_paths=image_paths,
            scene_durations=voice_result["scene_durations"],
            voiceover_path=voice_result["audio_path"] if with_voice else None,
            ass_path=voice_result["ass_path"],
            output_dir=project_dir,
            topic=topic,
            with_voice=with_voice,
            with_music=with_music,
            music_path=music_path,
            music_volume=project.get("music_volume"),
            scene_clip_paths=[s.get("clip_path") for s in scenes],
            scene_effects=self._scene_effects(scenes, project),
        )

        # 3. Update project metadata
        project.update({
            "duration": voice_result["total_duration"],
            "video_path": final_video_path,
            "subtitles_path": voice_result["ass_path"],
            "with_voice": with_voice,
            "with_music": with_music,
            "updated_at": datetime.now().isoformat()
        })
        if with_voice:
            project["audio_path"] = voice_result["audio_path"]
        else:
            project["audio_path"] = None

        # 4. Verify-video inspection
        qa_report = self.verify_video.run(project_record=project)
        project["qa_report"] = qa_report
        project["verify_video_report"] = qa_report
        StorageManager.save_project(project)

        print(f"[ShortsPipeline] ✓ Re-render complete! Verify-video Score: {qa_report['overall_score']}%")
        return project
