import os
import uuid
import time
import shutil
import hashlib
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None
import config

FFMPEG_TIMEOUT_S = int(os.getenv("FFMPEG_TIMEOUT_S", "900"))

class VideoComposer:
    def __init__(self):
        if imageio_ffmpeg:
            self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        else:
            bundled = list((config.BASE_DIR / ".venv").glob("**/imageio_ffmpeg/binaries/ffmpeg*"))
            self.ffmpeg_exe = str(bundled[0]) if bundled else "ffmpeg"

    def compose_video(
        self,
        image_paths: List[str],
        scene_durations: List[float],
        voiceover_path: str,
        ass_path: str,
        output_dir: Path,
        topic: str = "",
        with_voice: bool = True,
        with_music: bool = True,
        music_path: Optional[str] = None,
        music_volume: Optional[float] = None,
        voice_volume: Optional[float] = None,
        scene_clip_paths: Optional[List[Optional[str]]] = None,
        scene_effects: Optional[List[Optional[Dict[str, Any]]]] = None,
    ) -> str:
        """
        Assembles 1080x1920 vertical short with Ken Burns camera motion,
        ambient background tension audio, voiceover, and styled animated subtitles.
        """
        output_dir = Path(output_dir)
        render_id = f"{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        temp_dir = output_dir / f"temp_render_{render_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        final_video_path = output_dir / "final_short.mp4"
        temp_final_video = temp_dir / "final_mastered.mp4"
        concat_video = temp_dir / "concatenated.mp4"
        concat_txt = temp_dir / "concat_list.txt"
        clip_paths = []

        try:
            total_duration = sum(scene_durations)
            scene_clip_paths = list(scene_clip_paths or [])
            has_scene_clips = any(c and Path(c).exists() for c in scene_clip_paths)
            is_single_hero_image = (not has_scene_clips) and self._all_images_identical(image_paths)
            topic_lower = topic.lower()
            is_vertical_motion = any(kw in topic_lower for kw in ["vertical", "takeoff", "climb", "demo team", "afterburner"])

            if is_single_hero_image:
                # WeaponX Lab Mode: Static 9:16 vertical channel hero image locked across the 10s Short
                print(f"[VideoComposer] 🎬 WeaponX Lab Static Hero Image Mode: Rendering {total_duration:.1f}s 9:16 (1080x1920) Short...")
                static_filter = f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT},format=yuv420p"

                single_cmd = [
                    self.ffmpeg_exe, "-y",
                    "-loop", "1",
                    "-framerate", str(config.VIDEO_FPS),
                    "-i", image_paths[0],
                    "-vf", static_filter,
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "22",
                    "-pix_fmt", "yuv420p",
                    "-t", f"{total_duration:.3f}",
                    str(concat_video)
                ]
                self._run_ffmpeg(single_cmd, "Rendering WeaponX Lab static hero 9:16 video")
            else:
                # Multi-image mode: Render animated clips for each scene
                print(f"[VideoComposer] Generating Ken Burns motion for {len(image_paths)} scenes...")
                clip_paths = []
                for idx, (img_path, duration) in enumerate(zip(image_paths, scene_durations)):
                    clip_path = temp_dir / f"clip_{idx:02d}.mp4"
                    img_p = Path(img_path)
                    if not img_p.exists():
                        fallback_cands = sorted(list((output_dir / "scenes").glob("scene_*.png")))
                        if fallback_cands:
                            img_p = fallback_cands[min(idx, len(fallback_cands) - 1)]

                    user_clip = scene_clip_paths[idx] if idx < len(scene_clip_paths) else None
                    if user_clip and Path(user_clip).exists():
                        try:
                            _, clip_overlay_src = self._resolve_clip_sources(img_p)
                            self._render_video_clip(
                                user_clip, duration, clip_path, idx,
                                vf_extra=self._clip_vf_extra(scene_effects, idx, duration),
                                overlay_path=clip_overlay_src,
                            )
                            if clip_path.exists() and clip_path.stat().st_size > 1000:
                                clip_paths.append(clip_path)
                                continue
                        except Exception as vid_err:
                            print(f"[VideoComposer] ⚠️ User video clip failed for scene {idx+1}: {vid_err}. Falling back to image...")

                    try:
                        self._render_scene_clip(str(img_p), duration, clip_path, idx,
                                                settings=self._scene_settings(scene_effects, idx))
                    except Exception as clip_err:
                        print(f"[VideoComposer] ⚠️ Ken Burns motion render failed for scene {idx+1}: {clip_err}. Using static fallback...")
                        self._render_static_clip(str(img_p), duration, clip_path)

                    if clip_path.exists() and clip_path.stat().st_size > 1000:
                        clip_paths.append(clip_path)
                    else:
                        self._render_static_clip(str(img_p), duration, clip_path)
                        if clip_path.exists() and clip_path.stat().st_size > 1000:
                            clip_paths.append(clip_path)

                if not clip_paths:
                    raise RuntimeError("No scene video clips were successfully generated.")

                concat_txt = temp_dir / "concat_list.txt"
                with open(concat_txt, "w", encoding="utf-8") as f:
                    for p in clip_paths:
                        safe_p = str(p.resolve()).replace("\\", "/").replace("'", "'\\''")
                        f.write(f"file '{safe_p}'\n")

                concat_cmd = [
                    self.ffmpeg_exe, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(concat_txt),
                    "-c", "copy",
                    str(concat_video)
                ]
                try:
                    self._run_ffmpeg(concat_cmd, "Concatenating scenes")
                except Exception as concat_err:
                    print(f"[VideoComposer] ⚠️ Concat copy failed ({concat_err}). Trying re-encode concat...")
                    reencode_cmd = [
                        self.ffmpeg_exe, "-y",
                        "-f", "concat", "-safe", "0",
                        "-i", str(concat_txt),
                        "-c:v", "libx264",
                        "-preset", "fast",
                        "-crf", "22",
                        "-pix_fmt", "yuv420p",
                        str(concat_video)
                    ]
                    self._run_ffmpeg(reencode_cmd, "Re-encode concatenating scenes")

            # 3. Final assemble with audio mixing and subtitle burning
            jet_audio = config.AUDIO_ASSETS_DIR / "jet_afterburner_ambience.wav"
            drone_audio = config.AUDIO_ASSETS_DIR / "cinematic_drone.wav"

            # Check if user specified a custom AI or YouTube music track
            if music_path and Path(music_path).exists():
                bg_music = Path(music_path)
                bg_vol = float(music_volume) if music_volume is not None else 0.20
                print(f"[VideoComposer] 🎵 Selected Music Track: {bg_music.name} (volume: {bg_vol:.2f})")
            elif with_music and (default_pick := self._pick_default_music(topic_lower)):
                # Real music (mood-matched library / ACE-Step tracks) instead of a synthetic drone loop
                bg_music = default_pick
                bg_vol = float(music_volume) if music_volume is not None else 0.18
                print(f"[VideoComposer] 🎵 Selected default music: {bg_music.name} (volume: {bg_vol:.2f})")
            elif is_vertical_motion or any(kw in topic_lower for kw in ["jet", "raptor", "f-22", "fighter", "aircraft"]):
                bg_music = jet_audio if jet_audio.exists() else drone_audio
                bg_vol = float(music_volume) if music_volume is not None else 0.20
                print(f"[VideoComposer] 🔊 Selected Audio Track: Roaring Jet Afterburner Ambience ({bg_music.name})")
            else:
                bg_music = drone_audio
                bg_vol = float(music_volume) if music_volume is not None else 0.14
                print(f"[VideoComposer] 🔊 Selected Audio Track: Cinematic Drone Ambience ({bg_music.name})")

            has_bg = bg_music.exists()

            print("[VideoComposer] Burning styled subtitles and mastering audio...")
            
            # Escape path for FFmpeg filter syntax
            safe_ass_path = str(Path(ass_path).resolve()).replace("\\", "/").replace(":", "\\:") if ass_path else ""
            has_swxft_overlay = (not with_voice) and any(
                (Path(p).parent / f"{Path(p).stem}_overlay.png").exists() for p in image_paths if p
            )
            v_filter = "[0:v]null[v]" if (is_single_hero_image or has_swxft_overlay or not safe_ass_path) else f"[0:v]ass='{safe_ass_path}'[v]"
            v_vol = float(voice_volume) if voice_volume is not None else 1.15

            if not with_voice or not voiceover_path:
                # Without Voiceover
                if has_bg and with_music:
                    print("[VideoComposer] 🎵 'Without Voice' (Music Only) Mode: Rendering pure music/ambience track...")
                    cmd = [
                        self.ffmpeg_exe, "-y",
                        "-i", str(concat_video),
                        "-stream_loop", "-1", "-i", str(bg_music),
                        "-filter_complex",
                        f"{v_filter};[1:a]volume=0.92[a]",
                        "-map", "[v]",
                        "-map", "[a]",
                        "-c:v", "libx264",
                        "-preset", "fast",
                        "-crf", "22",
                        "-pix_fmt", "yuv420p",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-t", f"{total_duration:.3f}",
                        str(temp_final_video)
                    ]
                else:
                    print("[VideoComposer] 🔇 'Mute' Mode: Rendering silent audio track...")
                    cmd = [
                        self.ffmpeg_exe, "-y",
                        "-i", str(concat_video),
                        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-filter_complex",
                        f"{v_filter}",
                        "-map", "[v]",
                        "-map", "1:a",
                        "-c:v", "libx264",
                        "-preset", "fast",
                        "-crf", "22",
                        "-pix_fmt", "yuv420p",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-t", f"{total_duration:.3f}",
                        str(temp_final_video)
                    ]
            elif not with_music or not has_bg:
                print(f"[VideoComposer] 🎙️ 'Without Music' Mode: Rendering clean voiceover track (vol={v_vol:.2f}, no BGM)...")
                cmd = [
                    self.ffmpeg_exe, "-y",
                    "-i", str(concat_video),
                    "-i", voiceover_path,
                    "-filter_complex",
                    f"{v_filter};[1:a]volume={v_vol:.2f}[a]",
                    "-map", "[v]",
                    "-map", "[a]",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "22",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-t", f"{total_duration:.3f}",
                    str(temp_final_video)
                ]
            else:
                print(f"[VideoComposer] 🔊 Voice + Music Mode: Mastering voiceover (vol={v_vol:.2f}) with BGM (vol={bg_vol:.2f})...")
                cmd = [
                    self.ffmpeg_exe, "-y",
                    "-i", str(concat_video),
                    "-i", voiceover_path,
                    "-stream_loop", "-1", "-i", str(bg_music),
                    "-filter_complex",
                    f"{v_filter};[1:a]volume={v_vol:.2f},apad[voice];[2:a]volume={bg_vol:.2f}[bg];[voice][bg]amix=inputs=2:duration=longest:normalize=0[a]",
                    "-map", "[v]",
                    "-map", "[a]",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "22",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-t", f"{total_duration:.3f}",
                    str(temp_final_video)
                ]

            self._run_ffmpeg(cmd, "Final mastering and subtitle burn")

            # Atomic file swap to ensure frontend players never read partially written files
            if temp_final_video.exists():
                shutil.move(str(temp_final_video), str(final_video_path))

            # Loudness mastering: -14 LUFS integrated, -1 dBTP ceiling (YouTube's playback target)
            from app.agents.audio_master import master
            self.last_audio_master = master(str(final_video_path))

            print(f"[VideoComposer] Successfully created: {final_video_path}")
            return str(final_video_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            legacy_temp = output_dir / "temp_render"
            if legacy_temp.exists():
                shutil.rmtree(legacy_temp, ignore_errors=True)

    @staticmethod
    def _pick_default_music(topic_lower: str = "") -> Optional[Path]:
        """Best real music track available locally: saved library first, then ACE-Step generations.
        Prefers cinematic/epic moods; skips trimmed test clips and synthesized ambience."""
        try:
            from app.automation import music_library
            picked = music_library.pick(topic_lower)  # mood-matched, least-recently-used
            if picked and picked.exists():
                return picked
        except Exception as e:
            print(f"[VideoComposer] Music library pick skipped: {e}")
        audio = config.AUDIO_ASSETS_DIR
        cands = sorted((audio / "library").glob("*.wav")) + sorted((audio / "ai_generated").glob("acestep_*.wav"))
        cands = [c for c in cands if not any(t in c.name.lower() for t in ("trim", "qa_", "hook", "test"))]
        if not cands:
            return None
        order = ["cinematic", "epic", "metal", "rock", "edm", "ambient"]
        def rank(c: Path):
            n = c.name.lower()
            return next((i for i, k in enumerate(order) if k in n), len(order))
        return sorted(cands, key=rank)[0]

    @staticmethod
    def _all_images_identical(image_paths: List[str]) -> bool:
        """
        True only when every scene really shows the same picture (WeaponX static poster mode).
        Compared by file content, not by path: an uploaded / regenerated / edited scene image
        must never be swallowed just because another scene shares the old hero file.
        """
        paths = [Path(p) for p in image_paths if p]
        if not paths:
            return False
        if len(set(str(p) for p in paths)) == 1:
            return True
        try:
            digests = set()
            for p in paths:
                if not p.exists():
                    return False
                digests.add(hashlib.md5(p.read_bytes()).hexdigest())
                if len(digests) > 1:
                    return False
            return len(digests) == 1
        except Exception:
            return False

    @staticmethod
    def _resolve_clip_sources(img_p: Path):
        """
        Returns (background_image, overlay_image_or_None) for a scene.

        The stationary layer overlay is only used together with the clean layer-free background.
        When there is no overlay, the scene file itself is the truth, so a stale *_base.png left
        behind by an earlier image can never hide a freshly uploaded / generated picture.
        """
        base_p = img_p.parent / f"{img_p.stem}_base.png"
        bg_p = img_p.parent / f"{img_p.stem}_bg.png"
        overlay_p = img_p.parent / f"{img_p.stem}_overlay.png"
        has_overlay = overlay_p.exists() and overlay_p.stat().st_size > 500
        if has_overlay and img_p.exists():
            # If the main scene image was updated after the overlay was generated, the overlay is stale
            if img_p.stat().st_mtime > overlay_p.stat().st_mtime + 0.1:
                has_overlay = False
        if has_overlay:
            if bg_p.exists():
                return str(bg_p), overlay_p
            if base_p.exists():
                return str(base_p), overlay_p
        return str(img_p), None

    @staticmethod
    def _scene_settings(scene_effects, idx: int) -> Dict[str, Any]:
        from agents import scene_effects as sfx
        given = (scene_effects or [None] * (idx + 1))[idx] if scene_effects and idx < len(scene_effects) else None
        return given if (given and "effects" in given and "motion" in given) else sfx.resolve(given)

    def _clip_vf_extra(self, scene_effects, idx: int, duration: float) -> str:
        from agents import scene_effects as sfx
        return sfx.clip_extra_vf(self._scene_settings(scene_effects, idx), duration)

    def _render_scene_clip(self, img_path: str, duration: float, output_clip: Path, scene_idx: int,
                           settings: Optional[Dict[str, Any]] = None, size: Optional[tuple] = None):
        """Renders one image scene with its motion (zoom/pan/focus), colour grade, vignette,
        focus blur and fades (agents/scene_effects.py). settings=None -> 'auto' (alternating zoom)."""
        from agents import scene_effects as sfx
        fps = config.VIDEO_FPS
        w, h = size or (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)
        settings = settings or sfx.resolve(None)
        img_p = Path(img_path)
        bg_img, overlay_src = self._resolve_clip_sources(img_p)
        inputs = ["-i", str(bg_img)]  # single frame: zoompan expands it to the scene's frame count
        overlay_idx = mask_idx = None
        if overlay_src is not None:
            inputs += ["-loop", "1", "-framerate", str(fps), "-i", str(overlay_src)]
            overlay_idx = 1
        if settings["effects"].get("focus_blur"):
            mask = sfx.focus_mask(Path(output_clip).with_suffix(".mask.png"), w, h, settings["focus_point"], settings["motion"])
            inputs += ["-loop", "1", "-framerate", str(fps), "-i", str(mask)]
            mask_idx = 2 if overlay_idx else 1
        filter_complex = sfx.build_image_filter(settings, duration, fps, w, h, scene_idx, overlay_idx, mask_idx)
        cmd = [self.ffmpeg_exe, "-y", *inputs,
               "-filter_complex", filter_complex, "-map", "[v]",
               "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
               "-r", str(fps), "-t", f"{duration:.3f}", str(output_clip)]
        self._run_ffmpeg(cmd, f"Rendering scene {scene_idx+1} ({settings['motion']}, {settings['effects'].get('filter')})")

    def render_scene_preview(self, img_path: str, settings: Dict[str, Any], seconds: float, output: Path,
                             scene_idx: int = 0) -> Path:
        """Short low-res (360x640) preview of one scene's motion & effects (for the dashboard)."""
        self._render_scene_clip(img_path, max(1.0, min(4.0, float(seconds))), Path(output), scene_idx,
                                settings=settings, size=(360, 640))
        return Path(output)

    def _render_video_clip(self, video_path: str, duration: float, output_clip: Path, scene_idx: int,
                           vf_extra: str = "", overlay_path: Optional[Path] = None):
        """
        Normalizes a user-supplied or AI-generated (LTX/Phosphene/Wan) video clip to a scene segment:
        9:16 cover crop at the project resolution/fps, speed-ramped & beat-flashed if configured,
        stationary Swxft/Layer Studio overlay composited on top if present, looped/trimmed to scene duration.
        """
        fps = config.VIDEO_FPS
        vf = (
            f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT},setsar=1,fps={fps},format=yuv420p"
        )
        if vf_extra:  # scene speed ramp / beat flash / colour grade / vignette / fades
            vf = f"{vf},{vf_extra},fps={fps},format=yuv420p"
        # Play the clip ONCE; if it is shorter than the scene, hold its last frame instead of looping it
        # (a 2 s hook clip looped 4-5x when its scene was longer)
        vf = f"{vf},tpad=stop_mode=clone:stop_duration={duration:.3f}"

        if overlay_path is not None and Path(overlay_path).exists():
            filter_complex = (
                f"[0:v]{vf}[bg];"
                f"[1:v]scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}[ovl];"
                f"[bg][ovl]overlay=0:0:shortest=1,format=yuv420p[v]"
            )
            cmd = [
                self.ffmpeg_exe, "-y",
                "-i", video_path,
                "-loop", "1", "-framerate", str(fps), "-i", str(overlay_path),
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-an",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-t", f"{duration:.3f}",
                str(output_clip)
            ]
        else:
            cmd = [
                self.ffmpeg_exe, "-y",
                "-i", video_path,
                "-vf", vf,
                "-an",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-t", f"{duration:.3f}",
                str(output_clip)
            ]
        self._run_ffmpeg(cmd, f"Rendering video clip for scene {scene_idx+1}")

    def _render_static_clip(self, img_path: str, duration: float, output_clip: Path):
        fps = config.VIDEO_FPS
        img_p = Path(img_path)
        bg_img, overlay_src = self._resolve_clip_sources(img_p)
        overlay_p = overlay_src
        has_overlay = overlay_src is not None

        static_filter = f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT},format=yuv420p"
        if has_overlay:
            filter_complex = f"[0:v]{static_filter}[bg];[bg][1:v]overlay=0:0:shortest=1[v]"
            cmd = [
                self.ffmpeg_exe, "-y",
                "-loop", "1", "-framerate", str(fps), "-i", bg_img,
                "-loop", "1", "-framerate", str(fps), "-i", str(overlay_p),
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-t", f"{duration:.3f}",
                str(output_clip)
            ]
        else:
            cmd = [
                self.ffmpeg_exe, "-y",
                "-loop", "1",
                "-framerate", str(fps),
                "-i", bg_img,
                "-vf", static_filter,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-t", f"{duration:.3f}",
                str(output_clip)
            ]
        self._run_ffmpeg(cmd, f"Rendering static fallback clip {output_clip.name}")

    def _run_ffmpeg(self, cmd: List[str], task_name: str):
        try:
            # Safety net: a filter that never ends must not hang the pipeline/queue forever
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"FFmpeg timed out after {FFMPEG_TIMEOUT_S}s during {task_name}")
        if res.returncode != 0:
            err = res.stderr[-800:] if res.stderr else "Unknown FFmpeg error"
            raise RuntimeError(f"FFmpeg failed during {task_name}: {err}")
