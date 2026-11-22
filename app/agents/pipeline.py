import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import config
from app.utils.storage import StorageManager
from app.agents.research_agent import ResearchAgent
from app.agents.script_agent import ScriptAgent
from app.agents.voice_agent import VoiceAgent
from app.agents.creator_agent import CreatorAgent
from app.agents.video_composer import VideoComposer
from app.agents.qa_validator_agent import QAValidatorAgent
from app.agents.youtube_publisher import YouTubePublisher, uses_synthetic_media

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


DESCRIPTION_LIMIT = 4900  # YouTube allows 5,000 characters


def _with_credits_block(description: str, credits: List[str]) -> str:
    """Appends EVERY photo credit (CC BY/BY-SA require attribution - the old 12-line cap dropped some).
    If the description would get too long, the credit lines get shorter, never fewer."""
    base = re.sub(r"\n*Photo credits:\n.*\Z", "", description or "", flags=re.S).rstrip()
    block = "\n\nPhoto credits:\n" + "\n".join(credits)
    if len(base) + len(block) > DESCRIPTION_LIMIT:
        short = [re.sub(r"https?://(www\.)?", "", c) for c in credits]
        block = "\n\nPhoto credits:\n" + "\n".join(short)
    if len(base) + len(block) > DESCRIPTION_LIMIT:
        base = base[: max(200, DESCRIPTION_LIMIT - len(block))].rstrip()
    return (base + block)[:5000]


def refresh_photo_credits(project: Dict[str, Any]) -> None:
    """Rebuilds the credits from the photos the video uses NOW (after auto-repair, feedback or a chart
    rebuild replaced images, the description used to keep crediting the old photographers)."""
    credits = photo_credit_lines(project.get("visual_records") or [])
    desc = project.get("description") or ""
    if credits:
        project["description"] = _with_credits_block(desc, credits)
    elif "Photo credits:" in desc:
        project["description"] = re.sub(r"\n*Photo credits:\n.*\Z", "", desc, flags=re.S).rstrip()


def photo_credit_lines(visual_records: List[Dict[str, Any]]) -> List[str]:
    credits, seen = [], set()
    poster_rec = next((v for v in visual_records if v.get("ranked_items") or v.get("evolution_pairs")), None)
    if poster_rec:
        from agents import evolution_poster as _evp
        return _evp.compact_credits(poster_rec.get("photo_credits") or [])
    for v in visual_records:
        if v.get("source") not in ("web_free", "car_showcase") or str(v.get("source_url", "")).startswith("reframed://"):
            continue
        link = v.get("page_url") or v.get("source_url")
        if not link or link in seen:
            continue
        seen.add(link)
        author = re.sub(r"\s+", " ", str(v.get("author") or "Unknown")).strip()[:60]
        credits.append(f"• {author} · {v.get('license') or 'see source'} · {link}")
    return credits


def attach_visual_metadata(script_data: Dict[str, Any], visual_records: List[Dict[str, Any]]) -> None:
    """Photo credits + poster-based description + per-scene source fields. Shared by the pipeline and
    the WeaponX regenerate endpoint (which used to skip it: no credits, scenes without visual_source)."""
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
        if v.get("source") not in ("web_free", "car_showcase") or str(v.get("source_url", "")).startswith("reframed://"):
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
    if poster_rec and poster_rec.get("ranked_items"):
        # 'Top 10' in the title/captions/narration must match the rows actually shown
        from agents.topic_weapon_list import fix_top_n
        n_rows = len(poster_rec["ranked_items"])
        script_data["title"] = fix_top_n(script_data.get("title") or "", n_rows)
        for sc in script_data.get("scenes", []):
            for k in ("on_screen_text", "narration", "voiceover_text"):
                if sc.get(k):
                    sc[k] = fix_top_n(sc[k], n_rows)
    if poster_rec:
        body = _evp.description_body(poster_rec)
        tags_line = next((ln for ln in script_data.get("description", "").splitlines() if ln.startswith("#")), "#Shorts")
        intro = "" if poster_rec.get("ranked_items") else (script_data.get('title') or '').split(' #')[0].replace(': WeaponX Lab Breakdown 🔥', '')
        script_data["description"] = "\n\n".join(x for x in (intro, body, tags_line) if x)
        credits = _evp.compact_credits(poster_rec.get("photo_credits") or [])
    if credits and "Photo credits:" not in script_data.get("description", ""):
        script_data["description"] = _with_credits_block(script_data.get("description", ""), credits)

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

CAR_MIN_SECONDS = 20.0


class ShortsPipeline:
    def _lookup_music_track(self, music_track: Any) -> Optional[str]:
        """Track id / filename / name / path -> existing audio file (None if not found)."""
        if not music_track:
            return None
        for t in self.music_generator.list_tracks():
            if t["id"] == music_track or t["filename"] == music_track or t["name"].lower() == str(music_track).lower():
                return t["file_path"] if Path(t["file_path"]).exists() else None
        for cand in (config.AUDIO_ASSETS_DIR / "ai_generated" / f"{music_track}.wav",
                     config.AUDIO_ASSETS_DIR / "library" / f"{music_track}.wav", Path(str(music_track))):
            if cand.exists():
                return str(cand)
        return None

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
        is_car_edit = (style or "").lower() in ("car_edit", "caredit", "swxft")
        if duration is not None:
            target_dur = max(5.0, min(180.0, float(duration)))
        elif is_wx_style:
            target_dur = 10.0
        elif is_car_edit:
            target_dur = 15.0
        elif is_om_style:
            target_dur = 30.0
        else:
            target_dur = 30.0
        if is_car_edit:
            # Car videos are never shorter than 20 s in total (intro + edit + outro), whatever was requested
            target_dur = max(CAR_MIN_SECONDS, target_dur)

        topic_info = self.topic_agent.run(
            topic=custom_topic,
            target_duration=target_dur,
            style="default" if is_car_edit else style,
        )
        topic_title = topic_info["topic"]
        effective_style = "car_edit" if is_car_edit else topic_info.get("style", style)

        slug = slugify(topic_title)
        project_id = f"{timestamp}_{slug}"
        project_dir = config.PROJECTS_DIR / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        eff_audio_mode = audio_mode or ("with_voice" if with_voice and with_music else ("without_music" if with_voice else "without_voice"))

        project_record = {
            "id": project_id,
            "title": f"Generating: {topic_title}...",
            "topic": topic_title,
            "category": "Automotive & Supercars" if is_car_edit else topic_info.get("category", "Defense Tech"),
            "style": effective_style,
            "is_weaponx_lab": bool(topic_info.get("is_weaponx_lab")) and not is_car_edit,
            "is_openmontage": bool(is_om_style or effective_style == "openmontage"),
            "is_car_edit": bool(is_car_edit),
            "engine": "Car Edit (Swxft)" if is_car_edit else ("OpenMontage" if is_om_style else ("WeaponX Lab" if is_wx_style else "AI Shorts Studio")),
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
            "channel": self._channel_key(channel or ("autoflashx" if is_car_edit else None)),
            "status": "in_progress",
            # Which process runs this generation (web server or scheduler), so a restart of one
            # never marks the other's live job as failed (see web_app.sweep_orphaned_generations)
            "worker_pid": __import__("os").getpid(),
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
        # Car Edit is decided at prepare time (the research style is rewritten to "default" for the
        # analyser), so the branch must follow the project record, not the research style.
        if project_record.get("is_car_edit") or project_record.get("style") == "car_edit":
            style = "car_edit"

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
            script_data = self.content_analyser.run(
                topic_research=topic_info,
                style="default" if style == "car_edit" else style,
                target_duration=target_dur,
            )

            car_plan = None
            if style == "car_edit":
                from agents.car_edit_agent import CarEditAgent
                target_dur = max(CAR_MIN_SECONDS, target_dur)
                from agents import car_title_cards
                _bpm = CarEditAgent.get_phonk_bpm(project_record.get("phonk_style") or "drift_phonk")
                _intro_d, _outro_d = car_title_cards.card_durations(_bpm)
                from agents import car_showcase
                _show_d = 2 * car_showcase.showcase_seconds(_bpm) if os.getenv("CAR_SHOWCASE", "on").lower() != "off" else 0.0
                car_plan = CarEditAgent.build_car_edit_scenes(
                    car_name=topic_title,
                    # the beat-cut edit fills the time between the intro/outro cards and the 2 full-car showcases
                    target_duration=round(target_dur - _intro_d - _outro_d - _show_d, 2),
                    custom_title=project_record.get("car_edit_title"),
                    topic_research=topic_info,
                    phonk_style=project_record.get("phonk_style") or "drift_phonk",
                    beat_sync_mode=project_record.get("beat_sync_mode") or "swxft_velocity",
                )
                script_data["title"] = car_plan["title"]
                script_data["description"] = car_plan["description"]
                script_data["tags"] = car_plan["tags"]
                script_data["hook"] = car_plan["hook"]
                script_data["scenes"] = car_plan["scenes"]
                if isinstance(script_data.get("image_data"), dict):
                    script_data["image_data"]["scenes"] = car_plan["scenes"]
                    script_data["image_data"]["is_weaponx_lab"] = False
                    script_data["image_data"]["is_weaponx_lab_static"] = False
                # New Launch: the scenes are the user's own photos and clips (every one used)
                _um = project_record.get("user_media") or {}
                if _um.get("images") or _um.get("clips"):
                    from agents import new_launch
                    _main = round(target_dur - _intro_d - _outro_d - (_show_d if _um.get("images") else 0.0), 2)
                    if not _um.get("images"):
                        _show_d = 0.0  # the full-car showcase needs a photo
                    car_plan["scenes"] = new_launch.plan_scenes(_um.get("images", []), _um.get("clips", []),
                                                                _main, _bpm, template=car_plan["scenes"])
                    script_data["scenes"] = car_plan["scenes"]
                    if isinstance(script_data.get("image_data"), dict):
                        script_data["image_data"]["scenes"] = car_plan["scenes"]
                project_record["car_edit_plan"] = car_plan

            # Facts: narration sentences that are off-topic or carry numbers not in the sources are removed
            # BEFORE the voice-over (owner's rule: correct data or nothing)
            if style != "music_only":
                try:
                    from agents import fact_check
                    removed = fact_check.filter_script(script_data, topic_info,
                                                       topic_info.get("topic_subject") or topic_title)
                    if removed:
                        print(f"[FactCheck] removed before the voice-over: {removed}")
                        project_record["fact_check_removed"] = removed
                except Exception as e:
                    print(f"[FactCheck] pre-check skipped: {e}")

            project_record["content_analysis"] = script_data

            # Option 3: compose the theme music in the background while images etc. are built (car videos
            # and narrated videos; WeaponX starts after its images because the weapon list uses Ollama)
            music_job = None
            if style in ("car_edit", "default", "openmontage"):
                music_job = self._start_theme_music(project_record, topic_title, style, with_music, music_track, target_dur)
            print(f"-> Title: {script_data['title']}")
            print(f"-> Scenes: {len(script_data['scenes'])} scenes verified & corrected")

            # Step 3: Image Generator Agent (deep search, source check, topic match & CHANGE_IMAGE replacement)
            # WeaponX: a chart approved in the dashboard preview is used as-is (no rebuild)
            if project_record.get("chart_preview_id") and isinstance(script_data.get("image_data"), dict):
                try:
                    from app.automation import chart_preview
                    meta = chart_preview.load(project_record["chart_preview_id"])
                    if meta:
                        script_data["image_data"]["chart_preview"] = meta
                except Exception as e:
                    print(f"[ChartPreview] not used: {e}")
            print(f"\n[Step 3/7] 🖼️ Running 'image-generator' agent using image_data from content-analyser...")
            project_record["progress_step"] = "image-generator: Generating & verifying topic images..."
            StorageManager.save_project(project_record)
            if style == "car_edit" and car_plan and any(sc.get("user_media") for sc in script_data.get("scenes", [])):
                from agents import new_launch
                project_record["progress_step"] = "new-launch: Using your uploaded photos & clips..."
                StorageManager.save_project(project_record)
                print(f"[NewLaunch] 🚀 Building scenes from {len(script_data['scenes'])} uploaded photos/clips (no web photos)")
                image_report = new_launch.build_visuals(project_dir, script_data["scenes"])
            else:
                image_report = self.image_generator.run(
                    topic_research=topic_info,
                    content_analysis=script_data,
                    output_dir=project_dir,
                    style=style,
                )
            project_record["image_report"] = image_report
            visual_records = image_report["visual_records"]
            image_paths = image_report["image_paths"]
            if music_job is None and style == "weaponx":
                music_job = self._start_theme_music(project_record, topic_title, style, with_music, music_track, target_dur)

            if style == "car_edit" and car_plan:
                from agents.car_edit_agent import CarEditAgent
                print(f"[{CarEditAgent.AGENT_NAME}] 🏎️ Applying Swxft-style condensed stacked title overlay & zoom/pan motion presets...")
                project_record["progress_step"] = "car-edit-agent: Rendering Swxft title overlay & zoom/pan motion..."
                StorageManager.save_project(project_record)
                CarEditAgent.apply_swxft_title_overlays(image_paths, car_plan, script_data.get("scenes", []))
                car_fx = CarEditAgent.build_scene_effects(
                    len(script_data.get("scenes", [])),
                    motion_preset=project_record.get("car_motion_preset") or "swxft_dynamic",
                    bpm=car_plan.get("bpm", 130.0),
                    beat_sync_mode=project_record.get("beat_sync_mode") or "swxft_velocity",
                )
                for idx_s, sc in enumerate(script_data.get("scenes", [])):
                    if idx_s < len(car_fx):
                        sc.update(car_fx[idx_s])
                # Intro: brand logo reveal. Outro: professional end card. (Inserted as real scenes so the
                # music and beat cuts run straight through.)
                try:
                    from agents import youtube_channels as _yc
                    handle = _yc.get(project_record.get("channel") or "autoflashx").get("handle") or ""
                except Exception:
                    handle = ""
                project_record["progress_step"] = "car-edit-agent: Rendering brand-logo intro & end card..."
                StorageManager.save_project(project_record)
                # Full-car showcase scenes: the whole car, cut out of its uncropped photo and animated
                if _show_d:
                    project_record["progress_step"] = "car-edit-agent: Building full-car showcase scenes..."
                    StorageManager.save_project(project_record)
                    try:
                        shown = car_showcase.attach(project_dir, script_data["scenes"], image_paths, visual_records,
                                                    car_plan, topic_title)
                    except Exception as e:
                        print(f"[CarShowcase] skipped: {e}")
                        shown = {"added": 0, "seconds": 0.0}
                    missing = round(_show_d - shown["seconds"], 3)
                    if missing > 0.05:
                        # fewer showcases than planned: the last car shot holds longer so the video keeps its length
                        last = next((sc for sc in reversed(script_data["scenes"]) if not sc.get("title_card")), None)
                        if last:
                            last["duration_seconds"] = round(float(last.get("duration_seconds") or 2.0) + missing, 3)
                    project_record["car_showcase"] = shown
                try:
                    cards = car_title_cards.attach(project_dir, script_data["scenes"], image_paths, visual_records,
                                                   car_plan, topic_title, handle)
                    project_record["title_cards"] = cards
                    image_report["image_paths"] = image_paths
                except Exception as e:
                    print(f"[CarTitleCards] skipped: {e}")
                project_record["target_duration"] = target_dur
                project_record["is_car_edit"] = True
                project_record["engine"] = "Car Edit (Swxft)"
            elif style == "openmontage":
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

            attach_visual_metadata(script_data, visual_records)

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
                if self._silent_beat_edit(with_voice, style, script_data.get("scenes", [])):
                    # Music-only car / beat edit: no narration is heard or captioned, so don't synthesize
                    # one (it used to voice ~70 s of text and throw it away: ~30 s per video)
                    voice_result = self._silent_voice_result(script_data.get("scenes", []), target_dur)
                else:
                    voice_result = VoiceAgent.generate_voiceover(
                        script_data, project_dir, voice=en_voice, scene_image_paths=image_paths,
                        caption_style=project_record.get("caption_style")
                    )

            if not with_voice:
                # In without-voice mode, total duration is driven by target duration
                voice_result["total_duration"] = target_dur
                scenes_list = script_data.get("scenes", [])
                if style == "car_edit" or any(s.get("beat_synced") for s in scenes_list):
                    voice_result["scene_durations"] = [float(s.get("duration_seconds", 2.0)) for s in scenes_list]
                    voice_result["total_duration"] = round(sum(voice_result["scene_durations"]), 3)
                    print(f"-> Beat-synced music mode: locked {len(scenes_list)} cuts to BPM grid ({voice_result['total_duration']:.2f}s)")
                else:
                    voice_result["scene_durations"] = VoiceAgent._calculate_scene_durations(
                        scenes_list, target_dur
                    )
                    print(f"-> Music-only mode: set video duration to {target_dur:.1f}s")
            elif not is_hindi:
                print(f"-> Voiceover duration: {voice_result['total_duration']:.1f}s ({voice_result['word_count']} words)")

            # Step 5: Video Assembly
            # Resolve custom AI / Saved Library / YouTube Audio Library music track
            resolved_music_path = None
            if with_music:
                from agents.car_edit_agent import CarEditAgent
                phonk_builtin_keys = tuple(CarEditAgent.PHONK_PROMPTS.keys())
                # First check if user selected a specific Newly Generated AI Track or Saved Library Track
                if music_track and str(music_track).lower() not in ("none", "mute", "off", "default", "acestep_phonk", *phonk_builtin_keys):
                    resolved_music_path = self._lookup_music_track(music_track)
                elif os.getenv("THEME_MUSIC", "on").lower() != "off" and style in ("car_edit", "weaponx", "default", "openmontage"):
                    # A NEW on-theme track for every car/weapon video, saved to the music library
                    from agents import theme_music
                    is_car = style == "car_edit"
                    phonk = (str(music_track).lower() if str(music_track).lower() in phonk_builtin_keys
                             else (project_record.get("phonk_style") or "drift_phonk"))
                    project_record["progress_step"] = "Music: composing a new on-theme track (saved to your library)..."
                    StorageManager.save_project(project_record)
                    rec = self._await_theme_music(music_job)
                    if rec is None:
                        try:
                            rec = theme_music.fresh_theme_track(
                                topic_title, float(voice_result.get("total_duration") or target_dur),
                                kind="car" if is_car else "weapon",
                                category=project_record.get("category") or "", phonk_style=phonk, wait_seconds=120)
                        except Exception as e:
                            print(f"[ThemeMusic] failed: {e}")
                    if rec:
                        resolved_music_path = rec["file_path"]
                        music_track = rec["id"]
                        project_record["music_theme"] = {"theme": rec.get("theme"), "engine": rec.get("engine"),
                                                         "library_id": rec["id"], "name": rec.get("name")}
                    elif is_car:
                        resolved_music_path = CarEditAgent.resolve_or_generate_phonk_track(
                            car_name=topic_title, duration=target_dur, phonk_style=phonk)
                        music_track = f"acestep_{phonk}"
                elif style == "car_edit":
                    phonk_style = (
                        str(music_track).lower()
                        if str(music_track).lower() in phonk_builtin_keys
                        else (project_record.get("phonk_style") or "drift_phonk")
                    )
                    project_record["progress_step"] = f"car-edit-agent: Synthesizing {phonk_style.replace('_', ' ').title()} soundtrack..."
                    StorageManager.save_project(project_record)
                    resolved_music_path = CarEditAgent.resolve_or_generate_phonk_track(
                        car_name=topic_title,
                        duration=target_dur,
                        phonk_style=phonk_style,
                    )
                    music_track = f"acestep_{phonk_style}"
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
            # 3. Motion clips on every scene (optional toggle) vs opening hook clip
            if project_record.get("animate_all_scenes"):
                self._animate_all_scenes(
                    script_data.get("scenes", []),
                    image_paths,
                    voice_result["scene_durations"],
                    project_dir,
                    topic_title,
                    project_record,
                )
            else:
                self._maybe_hook_clip(
                    script_data.get("scenes", []),
                    image_paths,
                    voice_result["scene_durations"],
                    project_dir,
                    topic_title,
                    project_record,
                )
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
            if style in ("weaponx", "default", "openmontage") and (project_record.get("channel") or "weaponxlabs") != "autoflashx":
                from agents.youtube_metadata import apply_weapon_hashtags
                clean_description, clean_tags = apply_weapon_hashtags(clean_description, clean_tags)
            elif style == "car_edit" or (project_record.get("channel") == "autoflashx"):
                from agents.youtube_metadata import apply_car_hashtags
                clean_description, clean_tags = apply_car_hashtags(clean_description, clean_tags)
            project_record.update({
                "progress_step": "Verify-video: Finalizing & verifying image and video...",
                "title": clean_title,
                "description": clean_description,
                "tags": clean_tags,
                "scenes": script_data["scenes"],
                "duration": voice_result["total_duration"],
                "scene_durations": voice_result.get("scene_durations"),
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
                # Re-renders must reuse the SAME narrator: only a voice the user picked is forced;
                # otherwise the default engine (Kokoro) speaks again (it used to switch to Edge "Christopher")
                "voice_explicit": bool(voice),
                "voice_engine": voice_result.get("voice_engine") if with_voice else None,
                "voice_rate_pct": voice_result.get("rate_pct") if with_voice else None,
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
            StorageManager.save_project(project_record)

            # Step 6b: Auto-repair. Never hand over a video that fails a check: fix what can be fixed
            # (new images for repeats, re-render, re-master, clean metadata) and verify again.
            if not qa_report.get("qa_passed") and qa_report.get("auto_fixes"):
                print(f"\n[Step 6b/7] 🔧 Auto-repairing: {', '.join(qa_report['auto_fixes'])}")
                project_record["progress_step"] = "Auto-repair: fixing the problems the checks found..."
                StorageManager.save_project(project_record)
                try:
                    project_record = self.auto_repair(project_record["id"])
                    qa_report = project_record["qa_report"]
                    final_video_path = project_record.get("video_path", final_video_path)
                except Exception as e:
                    print(f"[AutoRepair] skipped: {e}")

            project_record["ready_for_showing"] = bool(qa_report.get("qa_passed"))
            if qa_report.get("qa_passed"):
                project_record["status"] = "completed"
                project_record["progress_step"] = "Ready for showing (all checks passed)"
                project_record.pop("problems", None)
            else:
                # Not "completed": a person must look at it. The reasons are listed on the card.
                project_record["status"] = "needs_attention"
                project_record["problems"] = qa_report.get("blocking_failures") or qa_report.get("remediation_actions") or []
                project_record["progress_step"] = "Needs attention: " + "; ".join(project_record["problems"][:2])[:200]
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
                        synthetic=uses_synthetic_media(project_record),
                    )
                    project_record["youtube"] = upload_res
                    # Uploads are always private (the owner publishes in YouTube Studio): never 'published'
                    project_record["status"] = (
                        "pending_approval" if upload_res.get("approval_status") == "pending_approval" else "uploaded_private"
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
    def _start_theme_music(project_record: Dict[str, Any], topic: str, style: str, with_music: bool,
                           music_track: Any, target_dur: float) -> Optional[Dict[str, Any]]:
        """Starts composing this video's theme music on a background thread (None if not applicable)."""
        import threading
        if not with_music or os.getenv("THEME_MUSIC", "on").lower() == "off":
            return None
        from agents.car_edit_agent import CarEditAgent
        phonk_keys = tuple(CarEditAgent.PHONK_PROMPTS.keys())
        mt = str(music_track or "").lower()
        if mt and mt not in ("none", "mute", "off", "default", "acestep_phonk", *phonk_keys):
            return None  # the user picked a track
        from agents import theme_music
        is_car = style == "car_edit"
        phonk = mt if mt in phonk_keys else (project_record.get("phonk_style") or "drift_phonk")
        job: Dict[str, Any] = {"rec": None, "error": None}

        def work():
            try:
                job["rec"] = theme_music.fresh_theme_track(
                    topic, float(target_dur), kind="car" if is_car else "weapon",
                    category=project_record.get("category") or "", phonk_style=phonk, wait_seconds=420)
            except Exception as e:
                job["error"] = str(e)
        t = threading.Thread(target=work, name=f"theme-music-{project_record.get('id')}", daemon=True)
        job["thread"] = t
        t.start()
        print(f"[ThemeMusic] Composing music in the background while the video is built...")
        return job

    @staticmethod
    def _await_theme_music(job: Optional[Dict[str, Any]], timeout: float = 900.0) -> Optional[Dict[str, Any]]:
        if not job:
            return None
        job["thread"].join(timeout)
        if job["thread"].is_alive():
            print("[ThemeMusic] Background music is taking too long; composing it now instead.")
            return None
        if job.get("error"):
            print(f"[ThemeMusic] Background music failed: {job['error']}")
        return job.get("rec")

    @staticmethod
    def _silent_beat_edit(with_voice: bool, style: Optional[str], scenes: List[Dict[str, Any]]) -> bool:
        return (not with_voice) and (style == "car_edit" or any(s.get("beat_synced") for s in scenes or []))

    @staticmethod
    def _silent_voice_result(scenes: List[Dict[str, Any]], target_dur: float) -> Dict[str, Any]:
        durs = [float(s.get("duration_seconds") or 2.0) for s in scenes or []]
        return {"audio_path": None, "ass_path": None, "srt_path": None,
                "total_duration": round(sum(durs), 3) if durs else float(target_dur),
                "scene_durations": durs or [float(target_dur)], "word_count": 0,
                "voice_engine": None, "rate_pct": None}

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

    @staticmethod
    def _clean_source_image_for_clip(img_path: Path) -> Path:
        """
        Prefer the clean layer-free background (<stem>_bg.png or <stem>_base.png) when animating
        a scene via LTX/Phosphene/Wan so text overlays are not warped by the video model.
        VideoComposer._render_video_clip then composites <stem>_overlay.png back on top.
        """
        for suffix in ("_bg.png", "_base.png"):
            cand = img_path.parent / f"{img_path.stem}{suffix}"
            if cand.exists() and cand.stat().st_size > 1000:
                return cand
        return img_path

    @staticmethod
    def _resolve_clip_engine_chain(preferred: Optional[str] = None) -> list:
        import os
        from app.agents import clip_generator
        pref = (preferred or os.getenv("HOOK_CLIP_ENGINE", "auto") or "auto").strip().lower()
        if pref == "phosphene_ltx":
            return ["phosphene_ltx", "ltx23_hf", "wan22_hf"]
        if pref == "wan22_hf":
            chain = ["wan22_hf", "ltx23_hf"]
        elif pref in clip_generator.ENGINES:
            chain = [pref] + [k for k in ("ltx23_hf", "wan22_hf") if k != pref]
        else:
            chain = ["ltx23_hf", "wan22_hf"]
        if os.getenv("HOOK_CLIP_LOCAL", "0") == "1" or clip_generator.find_phosphene():
            if "phosphene_ltx" not in chain:
                chain.append("phosphene_ltx")
        return chain

    def _animate_all_scenes(self, scenes, image_paths, scene_durations, project_dir, topic, project_record) -> None:
        """
        3. Motion clips on every scene (Optional toggle):
        Animates each scene's verified still image into an AI motion clip using LTX-2.3 / Wan 2.2 (free HF quota)
        or local Phosphene LTX-2.5 (3-5 min/scene on Mac). Gracefully falls back to speed-ramp + zoom/pan on any
        scene if quota is exhausted and local Phosphene is not running.
        """
        if not scenes or not image_paths or project_record.get("is_weaponx_lab"):
            return
        from app.agents import clip_generator
        from app.automation import resources

        preferred_engine = project_record.get("clip_engine") or "auto"
        engines = self._resolve_clip_engine_chain(preferred_engine)
        total_sc = min(len(scenes), len(image_paths))
        report = []

        print(f"[ShortsPipeline] 🎞️ Motion Clips on Every Scene enabled ({total_sc} scenes · engine chain: {engines})...")
        for idx in range(total_sc):
            sc = scenes[idx]
            raw_img = Path(image_paths[idx])
            if not raw_img.exists() or sc.get("title_card"):
                continue
            src_img = self._clean_source_image_for_clip(raw_img)
            out = Path(project_dir) / "scenes" / f"scene_{idx+1:02d}_clip.mp4"
            dur = float(scene_durations[idx]) if idx < len(scene_durations) else float(sc.get("duration_seconds", 3.0))
            prompt = (
                f"{sc.get('visual_prompt') or sc.get('narration') or topic}. "
                "Smooth cinematic automotive/documentary camera tracking motion, realistic physics, "
                "subject stays consistent with the source image."
            )

            scene_errors = []
            animated_ok = False
            for engine in engines:
                label = clip_generator.ENGINES.get(engine, {}).get("label", engine)
                project_record["progress_step"] = f"Motion clips ({idx+1}/{total_sc}): animating scene {idx+1} via {label}..."
                StorageManager.save_project(project_record)
                try:
                    if engine == "phosphene_ltx":
                        with resources.lease("phosphene", keep_running=True):
                            meta = clip_generator.generate_scene_clip(engine, src_img, prompt, dur, out)
                    else:
                        meta = clip_generator.generate_scene_clip(engine, src_img, prompt, dur, out)
                    sc["clip_path"] = str(out)
                    sc["clip_meta"] = meta
                    report.append({"scene": idx + 1, "status": "animated", "path": str(out), **meta})
                    print(f"[ShortsPipeline] 🎞️ Scene {idx+1}/{total_sc} motion clip ready via {meta.get('engine_label')} in {meta.get('elapsed_seconds')}s")
                    animated_ok = True
                    break
                except Exception as e:
                    err_str = str(e)[:180]
                    scene_errors.append(f"{engine}: {err_str}")
                    print(f"[ShortsPipeline] Scene {idx+1} clip via {engine} failed: {err_str}")

            if not animated_ok:
                report.append({"scene": idx + 1, "status": "fallback_zoompan", "errors": scene_errors})

        project_record["scene_clips_report"] = report
        StorageManager.save_project(project_record)

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
        # The first REAL scene (car videos open with a brand-logo title card, which is already a clip)
        h = next((i for i, sc in enumerate(scenes) if not sc.get("title_card")), None)
        if h is None or h >= len(image_paths):
            return
        image = self._clean_source_image_for_clip(Path(image_paths[h]))
        out = Path(project_dir) / "scenes" / f"scene_{h + 1:02d}_clip.mp4"
        dur = float(scene_durations[h]) if h < len(scene_durations or []) else 4.0
        prompt = (f"{scenes[h].get('visual_prompt') or topic}. Smooth cinematic camera push-in, realistic physics, "
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
                # Reject a clip that came back smeared/melted: the still photo looks better than that
                from app.agents.thumbnail import clip_sharpness_ratio, MIN_CLIP_SHARPNESS_RATIO
                ratio = clip_sharpness_ratio(str(out), str(image_paths[h]))
                if ratio is not None and ratio < MIN_CLIP_SHARPNESS_RATIO:
                    try:
                        out.unlink()
                    except OSError:
                        pass
                    raise RuntimeError(f"clip too blurry ({ratio:.0%} of the source photo's sharpness)")
                meta["sharpness_ratio"] = round(ratio, 2) if ratio is not None else None
                scenes[h]["clip_path"] = str(out)
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
            # The subject's name protects captions from splitting it ("F-35 | LIGHTNING II")
            "topic": topic,
            "topic_subject": (project.get("content_analysis") or {}).get("topic_subject") or topic,
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
            # Only a voice the user chose is passed on; older records stored the Edge default even when
            # Kokoro spoke, so without voice_explicit the default engine is used again.
            chosen = bool(project.get("voice_explicit")) or (
                "voice_explicit" not in project and project_voice not in (None, "", "en-US-ChristopherNeural"))
            en_voice = project_voice if (chosen and project_voice and not str(project_voice).startswith("hi-")) else None
            if self._silent_beat_edit(with_voice, project.get("style"), scenes):
                voice_result = self._silent_voice_result(scenes, target_dur)
            else:
                voice_result = VoiceAgent.generate_voiceover(
                    script_data, project_dir, voice=en_voice, scene_image_paths=image_paths,
                    caption_style=project.get("caption_style")
                )

        if not with_voice:
            voice_result["total_duration"] = target_dur
            if project.get("style") == "car_edit" or any(s.get("beat_synced") for s in scenes):
                # Keep the beat-locked cut lengths (word-count timing gave scene 1 ~10 s and looped its clip)
                voice_result["scene_durations"] = [float(s.get("duration_seconds") or 2.0) for s in scenes]
                voice_result["total_duration"] = round(sum(voice_result["scene_durations"]), 3)
            else:
                voice_result["scene_durations"] = VoiceAgent._calculate_scene_durations(scenes, target_dur)

        # 2. Re-compose video (preserve the project's chosen music track & volume)
        music_path = project.get("music_path")
        if music_path and not Path(str(music_path)).exists():
            music_path = None
        if not music_path and with_music and project.get("music_track"):
            # Older projects (and Apply Music before the fix) stored only the track id
            music_path = self._lookup_music_track(project["music_track"])
            if music_path:
                project["music_path"] = music_path
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

        # Re-apply the Apply-Music mix (trim / loop / tempo / EQ / voice level) on the fresh render
        remix = project.get("music_remix") or {}
        if with_music and music_path and remix:
            try:
                rm = dict(remix)
                if not with_voice:
                    rm["voice_volume"] = 0.0
                final_video_path = str(self.music_generator.remix_video_music(
                    video_path=Path(final_video_path), music_path=Path(music_path), **rm))
            except Exception as e:
                print(f"[ShortsPipeline] ⚠️ Could not re-apply music mix settings ({e}); kept the plain mix.")

        # 3. Update project metadata
        project.update({
            "duration": voice_result["total_duration"],
            "scene_durations": voice_result.get("scene_durations"),
            "voice_engine": voice_result.get("voice_engine") if with_voice else None,
            "voice_rate_pct": voice_result.get("rate_pct") if with_voice else None,
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

        # Credits follow the photos the video uses now (images may have been replaced since creation)
        refresh_photo_credits(project)

        # 4. Verify-video inspection
        qa_report = self.verify_video.run(project_record=project)
        project["qa_report"] = qa_report
        project["verify_video_report"] = qa_report
        project["ready_for_showing"] = bool(qa_report.get("qa_passed"))
        if project.get("status") in ("completed", "needs_attention"):
            # The card always reflects the CURRENT video: fixed -> completed, broken -> needs attention
            project["status"] = "completed" if qa_report.get("qa_passed") else "needs_attention"
            if qa_report.get("qa_passed"):
                project.pop("problems", None)
            else:
                project["problems"] = qa_report.get("blocking_failures") or qa_report.get("remediation_actions") or []
        StorageManager.save_project(project)

        print(f"[ShortsPipeline] ✓ Re-render complete! Verify-video Score: {qa_report['overall_score']}%")
        return project

    # ------------------------------------------------------------------------------------------
    # Auto-repair: a video is only "completed" when Verify-video (incl. the Final Render Guard)
    # passes. Fixable failures are repaired and re-rendered automatically; anything left is
    # reported as "needs_attention" with the exact reasons instead of looking finished.
    # ------------------------------------------------------------------------------------------
    def auto_repair(self, project_id: str, max_rounds: int = 2, allow_rerender: bool = True) -> Dict[str, Any]:
        project = StorageManager.get_project_by_id(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")
        history = list(project.get("auto_repair") or [])
        # 0. The user's own feedback notes come first ("scene 3 image is wrong", "music is boring"...)
        if any(f.get("status") == "open" for f in (project.get("feedback") or [])):
            print(f"[AutoRepair] Applying the user's feedback notes...")
            if self.apply_feedback(project) and allow_rerender:
                project = self.rerender_project(project_id)  # re-voices, re-captions, masters, re-verifies
            else:
                project = StorageManager.get_project_by_id(project_id) or project
                project["qa_report"] = self.verify_video.run(project_record=project)
            notes = [f for f in project.get("feedback") or [] if f.get("handled_at")]
            history.append({"round": 0, "at": datetime.now().isoformat(), "fixed": [
                f"feedback: {f['text'][:60]} -> {f.get('status')}" for f in notes[-5:]],
                "passed_after": bool((project.get("qa_report") or {}).get("qa_passed"))})
            StorageManager.save_project(project)
        for rnd in range(1, max_rounds + 1):
            qa = project.get("qa_report") or self.verify_video.run(project_record=project)
            if qa.get("qa_passed"):
                break
            fixes = set(qa.get("auto_fixes") or [])
            if not fixes:
                break
            applied: List[str] = []
            need_rerender = False

            if "clean_metadata" in fixes:
                from agents.youtube_metadata import clean_metadata
                project["title"], project["description"], project["tags"] = clean_metadata(
                    project.get("title") or "", project.get("description") or "", project.get("tags") or [],
                    project.get("topic") or "")
                applied.append("cleaned metadata")

            if fixes & {"replace_duplicates", "replace_scenes"}:
                targets: List[int] = []
                for c in qa.get("all_checks", []):
                    if c.get("passed"):
                        continue
                    if c.get("fix") == "replace_duplicates":
                        targets += [max(pair) for pair in (c.get("dup_pairs") or [])]  # keep the earlier scene
                    elif c.get("fix") == "replace_scenes":
                        targets += list(c.get("scenes_to_replace") or [])
                for n in sorted(set(int(t) for t in targets if t)):
                    if self._replace_scene_image(project, n):
                        applied.append(f"new image for scene {n}")
                        need_rerender = True

            if "rerender" in fixes:
                need_rerender = True

            if "remove_unverified_text" in fixes:
                from agents import fact_check
                sd = {"scenes": project.get("scenes") or []}
                removed = fact_check.filter_script(sd, project.get("topic_research") or {},
                                                   (project.get("topic_research") or {}).get("topic_subject") or project.get("topic") or "")
                if removed:
                    project["scenes"] = sd["scenes"]
                    project.setdefault("fact_check_removed", []).extend(removed)
                    applied.append(f"removed {len(removed)} unverified line(s)")
                    need_rerender = True

            if "rebuild_chart" in fixes and self._static_chart_record(project):
                try:
                    if self.rebuild_weaponx_chart(project):
                        sd = {"title": project.get("title") or "", "description": project.get("description") or "",
                              "scenes": project.get("scenes") or []}
                        attach_visual_metadata(sd, project.get("visual_records") or [])
                        project["title"], project["description"] = sd["title"], sd["description"]
                        from agents.youtube_metadata import apply_weapon_hashtags
                        project["description"], project["tags"] = apply_weapon_hashtags(project["description"], project.get("tags") or [])
                        applied.append("chart rebuilt with verified data only")
                        need_rerender = True
                except Exception as e:
                    print(f"[AutoRepair] chart rebuild failed: {e}")

            if "restore_poster" in fixes and self.restore_weaponx_chart(project):
                applied.append("WeaponX chart restored on every scene")
                need_rerender = True

            if "relax_duration" in fixes:
                # Rushed narration: lengthen the video so the voice runs at most ~8% above natural pace
                rate = float(project.get("voice_rate_pct") or 0)
                cur = float(project.get("target_duration") or project.get("duration") or 30.0)
                natural = cur * (1 + rate / 100.0)
                new_target = round(min(59.0, max(cur + 1.0, natural / 1.08)), 1)
                if new_target > cur:
                    project["target_duration"] = new_target
                    applied.append(f"length {cur:.0f}s -> {new_target:.0f}s for a natural pace")
                    need_rerender = True

            if need_rerender and allow_rerender:
                StorageManager.save_project(project)
                print(f"[AutoRepair] Round {rnd}: re-rendering ({', '.join(applied) or 'render/caption/sync fix'})...")
                project = self.rerender_project(project_id)  # re-voices, re-captions, masters, re-verifies
                applied.append("re-rendered")
            elif "remaster" in fixes and project.get("video_path"):
                from app.agents.audio_master import master
                master(str(project["video_path"]))
                applied.append("re-mastered audio")

            if not applied:
                break
            if "re-rendered" not in applied:
                project["qa_report"] = self.verify_video.run(project_record=project)
                project["verify_video_report"] = project["qa_report"]
            history.append({"round": rnd, "at": datetime.now().isoformat(), "fixed": applied,
                            "passed_after": bool(project["qa_report"].get("qa_passed"))})
            StorageManager.save_project(project)
            print(f"[AutoRepair] Round {rnd}: {', '.join(applied)} -> "
                  f"{'PASSED' if project['qa_report'].get('qa_passed') else 'still failing'}")

        project["auto_repair"] = history
        StorageManager.save_project(project)
        return project

    def _replace_scene_image(self, project: Dict[str, Any], scene_num: int) -> bool:
        """New verified image for one scene (web photo first, then AI); never a repeat of another scene."""
        scenes = project.get("scenes") or []
        if not 1 <= scene_num <= len(scenes):
            return False
        sc = scenes[scene_num - 1]
        scenes_dir = Path(project["project_dir"]) / "scenes"
        dest = scenes_dir / f"scene_{scene_num:02d}.png"
        others = [str(s.get("image_path")) for i, s in enumerate(scenes, 1) if i != scene_num and s.get("image_path")]
        used = {str(r.get("source_url")) for r in (project.get("visual_records") or []) if r.get("source_url")}
        from agents.image_generator import ImageGeneratorAgent
        gen = ImageGeneratorAgent()
        rec = None
        try:
            rec = gen.acquire_fresh_web_image(project.get("topic", ""), sc, scene_num, dest,
                                              used_urls=used, existing_images=others)
        except Exception as e:
            print(f"[AutoRepair] Web image for scene {scene_num} failed: {e}")
        if not rec:
            try:
                tmp = scenes_dir / f"scene_{scene_num:02d}.ai.png"
                res = gen.generate_single_scene_image(sc.get("visual_prompt") or project.get("topic", ""), tmp,
                                                      style=project.get("style", "default"), topic=project.get("topic", ""),
                                                      scene=sc, allow_fallback=False)
                if res.get("success") and tmp.exists() and not gen._duplicate_of(tmp, others):
                    shutil.move(str(tmp), str(dest))
                    rec = {"scene_number": scene_num, "image_path": str(dest), "source": "ai_generated",
                           "content_verified": bool((res.get("content_check") or {}).get("passed")),
                           "source_provider": res.get("provider")}
                else:
                    tmp.unlink(missing_ok=True)
            except Exception as e:
                print(f"[AutoRepair] AI image for scene {scene_num} failed: {e}")
        if not rec:
            return False
        for suffix in ("_base.png", "_overlay.png", "_bg.png"):
            (scenes_dir / f"scene_{scene_num:02d}{suffix}").unlink(missing_ok=True)
        sc.update(image_path=str(dest), visual_source=rec.get("source"), visual_source_url=rec.get("source_url"),
                  visual_source_title=rec.get("source_title"))
        sc.pop("placeholder_from_scene", None)
        if sc.get("clip_path"):  # a clip animated from the OLD picture would bring it back
            sc.pop("clip_path", None)
        for records in ((project.get("image_report") or {}).get("visual_records"), project.get("visual_records")):
            if isinstance(records, list):
                records[:] = [r for r in records if r.get("scene_number") != scene_num]
                records.append({k: v for k, v in rec.items() if k != "visual_quality"})
        print(f"[AutoRepair] Scene {scene_num}: replaced with a new {rec.get('source')} image")
        return True

    def apply_feedback(self, project: Dict[str, Any]) -> bool:
        """Applies the user's open feedback notes (see agents/feedback_fixer.py) to the project.
        Returns True when a re-render is needed. Each note ends 'fixed' or 'needs_you'."""
        from agents import feedback_fixer as ff
        notes = [f for f in (project.get("feedback") or []) if f.get("status") == "open"]
        if not notes:
            return False
        need_rerender = False
        scenes = project.get("scenes") or []
        removals: List[int] = []
        chart_swaps: List[Optional[str]] = []
        chart_notes: List[Any] = []
        for note in notes:
            actions = ff.parse(note.get("text", ""), project)
            done: List[str] = []
            failed: List[str] = []
            for a in actions:
                act = a["action"]
                try:
                    if act == "set_title":
                        project["title"] = a["text"] if "#shorts" in a["text"].lower() else f"{a['text']} #Shorts"
                        done.append(ff.describe(a))
                    elif act == "set_narration":
                        sc = scenes[int(a["scene"]) - 1]
                        sc["narration"] = sc["voiceover_text"] = a["text"]
                        need_rerender = True
                        done.append(ff.describe(a))
                    elif act == "replace_image":
                        if self._replace_scene_image(project, int(a["scene"])):
                            need_rerender = True
                            done.append(ff.describe(a))
                        else:
                            failed.append(f"no new image found for scene {a['scene']}")
                    elif act == "new_music":
                        from agents import theme_music
                        is_car = project.get("style") == "car_edit" or project.get("is_car_edit")
                        rec = theme_music.fresh_theme_track(
                            project.get("topic", ""), float(project.get("duration") or 20), kind="car" if is_car else "weapon",
                            category=project.get("category") or "", phonk_style=project.get("phonk_style"),
                            wait_seconds=180)
                        if rec:
                            project.update(music_path=rec["file_path"], music_track=rec["id"], with_music=True,
                                           music_theme={"theme": rec.get("theme"), "engine": rec.get("engine"),
                                                        "library_id": rec["id"], "name": rec.get("name")})
                            project.pop("music_remix", None)  # trim/loop settings belonged to the old track
                            need_rerender = True
                            done.append(f"new music '{rec.get('name')}' (saved to library)")
                        else:
                            failed.append("could not compose new music")
                    elif act == "music_volume":
                        cur = float(project.get("music_volume") or 0.22)
                        new = round(max(0.05, min(0.6, cur * float(a.get("factor") or 1))), 3)
                        project["music_volume"] = new
                        if isinstance(project.get("music_remix"), dict):
                            project["music_remix"]["music_volume"] = new
                        need_rerender = True
                        done.append(f"{ff.describe(a)} ({cur:.2f} -> {new:.2f})")
                    elif act == "slower_voice":
                        cur = float(project.get("target_duration") or project.get("duration") or 20)
                        rate = float(project.get("voice_rate_pct") or 0)
                        project["target_duration"] = round(min(59.0, max(cur + 2.0, cur * (1 + rate / 100.0) * 1.05)), 1)
                        need_rerender = True
                        done.append(f"length {cur:.0f}s -> {project['target_duration']:.0f}s so the voice isn't rushed")
                    elif act == "remove_scene":
                        removals.append(int(a["scene"]))
                        done.append(ff.describe(a))
                    elif act == "rerender":
                        need_rerender = True
                        done.append(ff.describe(a))
                    elif act in ("chart_swap_row", "chart_rebuild"):
                        chart_swaps.append(a.get("name"))
                        chart_notes.append((note, ff.describe(a)))
                        continue
                except Exception as e:
                    failed.append(f"{act}: {e}")
            note["actions"] = actions
            note["status"] = "fixed" if done and not failed else ("partly_fixed" if done else "needs_you")
            note["result"] = "; ".join(done + [f"NOT DONE: {x}" for x in failed]) or \
                "Couldn't turn this into an automatic fix. Use Studio to change it, or reword the note (e.g. 'scene 3 image is wrong')."
            note["handled_at"] = datetime.now().isoformat(timespec="seconds")
        # WeaponX chart rows: one rebuild for all notes (rejected rows replaced, good rows kept)
        if chart_swaps:
            try:
                ok = self.rebuild_weaponx_chart(project, [n for n in chart_swaps if n])
            except Exception as e:
                ok, err = False, str(e)
            else:
                err = "" if ok else "this chart type can't be rebuilt automatically"
            for note, desc in chart_notes:
                if ok:
                    prev = note.get("result") or ""
                    prev = "" if prev.startswith("Couldn't turn") else prev
                    note["result"] = "; ".join(x for x in [prev, desc] if x)
                    note["status"] = "fixed" if note.get("status") in ("fixed", "needs_you") else note["status"]
                else:
                    note["result"] = f"NOT DONE: {desc} ({err[:120]})"
                    note["status"] = "needs_you"
            need_rerender = need_rerender or ok

        # Remove scenes last (highest first) so earlier scene numbers in other notes stay valid
        for n in sorted(set(removals), reverse=True):
            if 1 <= n <= len(scenes) and len(scenes) > 1:
                scenes.pop(n - 1)
                need_rerender = True
        if removals:
            for i, sc in enumerate(scenes, 1):
                old = sc.get("scene_number")
                sc["scene_number"] = sc["scene_id"] = i
                for records in ((project.get("image_report") or {}).get("visual_records"), project.get("visual_records")):
                    if isinstance(records, list):
                        for r in records:
                            if r.get("scene_number") == old and not r.get("_renum"):
                                r["scene_number"], r["_renum"] = i, True
            for records in ((project.get("image_report") or {}).get("visual_records"), project.get("visual_records")):
                if isinstance(records, list):
                    keep = [r for r in records if r.pop("_renum", False)]
                    records[:] = keep
            project["image_paths"] = [s.get("image_path") for s in scenes if s.get("image_path")]
            project["target_duration"] = round(sum(float(d) for d in (project.get("scene_durations") or [])[:len(scenes)])
                                               or float(project.get("target_duration") or 20), 1)
        project["scenes"] = scenes
        StorageManager.save_project(project)
        return need_rerender

    # ------------------------------------------------------------------ WeaponX chart repair
    @staticmethod
    def _static_chart_record(project: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        recs = project.get("visual_records") or []
        return next((r for r in recs if r.get("source") == "weaponx_lab_poster" and r.get("ranked_items")), None)

    def _apply_chart_to_all_scenes(self, project: Dict[str, Any], hero: Path, rec: Dict[str, Any]) -> None:
        """A WeaponX short shows its chart for the WHOLE video: every scene gets the chart again."""
        scenes = project.get("scenes") or []
        scenes_dir = Path(project["project_dir"]) / "scenes"
        records = []
        paths = []
        for i, sc in enumerate(scenes, 1):
            dest = scenes_dir / f"scene_{i:02d}.png"
            shutil.copyfile(hero, dest)
            for suffix in ("_base.png", "_overlay.png", "_bg.png"):
                (scenes_dir / f"scene_{i:02d}{suffix}").unlink(missing_ok=True)
            sc.update(image_path=str(dest), visual_source="weaponx_lab_poster", visual_source_url=rec.get("source_url"),
                      visual_source_title=None)
            sc.pop("clip_path", None)
            r = {k: v for k, v in rec.items() if k != "visual_quality"}
            r.update(scene_number=i, image_path=str(dest), static_image=True, channel_style="weaponx_lab_static")
            records.append(r)
            paths.append(str(dest))
        project["visual_records"] = records
        if isinstance(project.get("image_report"), dict):
            project["image_report"]["visual_records"] = records
            project["image_report"]["image_paths"] = paths
        project["image_paths"] = paths

    def restore_weaponx_chart(self, project: Dict[str, Any]) -> bool:
        """Puts the existing chart back on every scene (e.g. after a scene was replaced by mistake)."""
        rec = self._static_chart_record(project)
        hero = Path(project["project_dir"]) / "scenes" / "hero_master.png"
        if not rec or not hero.exists():
            return False
        self._apply_chart_to_all_scenes(project, hero, rec)
        return True

    def rebuild_weaponx_chart(self, project: Dict[str, Any], exclude_names: Optional[List[str]] = None) -> bool:
        """Rebuilds a WeaponX list chart: the rows the user rejected are replaced by other verified models,
        the other rows stay; every photo is re-checked. Only for list charts built from the topic."""
        rec = self._static_chart_record(project)
        if not rec or not (rec.get("list_chart") or "list chart" in str(rec.get("source_provider", ""))):
            return False
        items = rec.get("ranked_items") or []
        low = [n.lower() for n in (exclude_names or [])]
        excl = [it.get("article") or it.get("name") for it in items
                if any(x in str(it.get("article", "")).lower() or x in str(it.get("name", "")).lower() for x in low)]
        # the user rejected these rows: their library photos are never reused either
        try:
            from agents import photo_library
            for t in excl:
                photo_library.reject(t)
        except Exception as e:
            print(f"[PhotoLibrary] reject failed: {e}")
        excl = list(dict.fromkeys(excl + list(project.get("chart_excluded") or [])))
        keep = [it.get("article") or it.get("name") for it in items if (it.get("article") or it.get("name")) not in excl]
        hero = Path(project["project_dir"]) / "scenes" / "hero_master.png"
        topic = (project.get("content_analysis") or {}).get("topic_subject") or project.get("topic", "")
        new_rec = self.image_generator._acquire_topic_list_poster(topic, hero, keep_titles=keep, exclude_titles=excl)
        new_rec.update(static_image=True, channel_style="weaponx_lab_static")
        self._apply_chart_to_all_scenes(project, hero, new_rec)
        project["chart_excluded"] = excl
        return True
