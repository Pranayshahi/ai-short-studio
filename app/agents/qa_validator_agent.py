import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
from PIL import Image, ImageFilter
import imageio_ffmpeg
import config

class QAValidatorAgent:
    """
    Autonomous QA, Deep Frame Inspector & Quality Assurance Agent.
    Performs comprehensive end-to-end verification of rendered video,
    audio levels, frame motion, sharpness, black frames, subtitle safe-zones,
    and asset validity before publishing.
    """
    def __init__(self):
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    def inspect_project(
        self,
        project_record: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Runs full QA inspection suite on a generated Shorts project.
        Returns a detailed QA report dictionary with scores and frame metrics.
        """
        project_dir = Path(project_record.get("project_dir", ""))
        video_path = project_record.get("video_path") or str(project_dir / "final_short.mp4")
        ass_path = project_record.get("subtitles_path") or str(project_dir / "subtitles.ass")
        image_paths = project_record.get("image_paths", [])

        qa_frames_dir = project_dir / "qa_frames"
        qa_frames_dir.mkdir(parents=True, exist_ok=True)

        report = {
            "project_id": project_record.get("id"),
            "status": "PASSED",
            "overall_score": 100,
            "stream_checks": {},
            "audio_checks": {},
            "motion_checks": {},
            "subtitle_checks": {},
            "watermark_checks": {
                "watermark_detected": False,
                "clean_frames": True,
                "flagged_corners": []
            },
            "asset_checks": {},
            "frame_inspections": [],
            "warnings": [],
            "errors": [],
            "qa_passed": True
        }

        # 1. Container & Stream Validation
        self._verify_container_and_streams(video_path, report)

        # 2. Audio Level & Silence Analysis
        self._verify_audio_quality(video_path, report)

        # 3. Deep Frame-by-Frame Inspection (Sharpness, Motion, Black Frames, Letterboxing)
        self._deep_frame_inspection(video_path, qa_frames_dir, report)

        # 4. Subtitle & Safe Zone Validation
        self._verify_subtitles(ass_path, report)

        # 5. Asset & Scene Images Validation
        self._verify_scene_assets(image_paths, report)

        # 6. Final Score Calculation
        self._calculate_final_score(report)

        # Save report to project folder
        report_file = project_dir / "qa_report.json"
        import json
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return report

    def _verify_container_and_streams(self, video_path: str, report: Dict[str, Any]):
        v_path = Path(video_path)
        if not v_path.exists():
            report["errors"].append("Final video file does not exist on disk.")
            report["overall_score"] -= 100
            report["qa_passed"] = False
            return

        size_mb = v_path.stat().st_size / (1024 * 1024)
        report["stream_checks"]["file_size_mb"] = round(size_mb, 2)
        if size_mb < 0.5:
            report["errors"].append(f"File size too small ({size_mb:.2f} MB), possible corrupt render.")
            report["overall_score"] -= 40

        # Query streams with ffmpeg
        cmd = [self.ffmpeg_exe, "-i", video_path]
        res = subprocess.run(cmd, capture_output=True, text=True)
        stderr = res.stderr

        # Check resolution
        res_match = re.search(r"(\d{3,4})x(\d{3,4})", stderr)
        if res_match:
            width, height = int(res_match.group(1)), int(res_match.group(2))
            report["stream_checks"]["resolution"] = f"{width}x{height}"
            if width != config.VIDEO_WIDTH or height != config.VIDEO_HEIGHT:
                report["warnings"].append(f"Resolution {width}x{height} does not match target {config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}.")
                report["overall_score"] -= 15
        else:
            report["errors"].append("Unable to determine video resolution.")
            report["overall_score"] -= 20

        # Check duration
        dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", stderr)
        if dur_match:
            hrs, mins, secs = int(dur_match.group(1)), int(dur_match.group(2)), float(dur_match.group(3))
            total_dur = hrs * 3600 + mins * 60 + secs
            report["stream_checks"]["duration_seconds"] = round(total_dur, 2)
            if total_dur < 5.0:
                report["errors"].append(f"Video duration ({total_dur:.1f}s) is too short for YouTube Shorts.")
                report["overall_score"] -= 30
            elif total_dur > 180.0:
                report["errors"].append(f"Video duration ({total_dur:.1f}s) exceeds YouTube Shorts 3-minute limit.")
                report["overall_score"] -= 30
        else:
            report["errors"].append("Unable to determine video duration.")

        # Check codecs
        has_h264 = "h264" in stderr.lower()
        has_aac = "aac" in stderr.lower()
        report["stream_checks"]["video_codec_h264"] = has_h264
        report["stream_checks"]["audio_codec_aac"] = has_aac
        if not has_h264:
            report["warnings"].append("Video is not encoded in standard H.264.")
            report["overall_score"] -= 10
        if not has_aac:
            report["warnings"].append("Audio is not encoded in standard AAC.")
            report["overall_score"] -= 10

    def _verify_audio_quality(self, video_path: str, report: Dict[str, Any]):
        cmd = [self.ffmpeg_exe, "-i", video_path, "-af", "volumedetect", "-f", "null", "-"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        stderr = res.stderr

        mean_vol = re.search(r"mean_volume:\s*([-\d\.]+)\s*dB", stderr)
        max_vol = re.search(r"max_volume:\s*([-\d\.]+)\s*dB", stderr)

        if mean_vol and max_vol:
            m_db = float(mean_vol.group(1))
            mx_db = float(max_vol.group(1))
            report["audio_checks"]["mean_volume_db"] = m_db
            report["audio_checks"]["max_volume_db"] = mx_db

            # Recommended loudness for Shorts is -14 to -26 dB
            if m_db < -32.0:
                report["warnings"].append(f"Audio is quiet (mean: {m_db:.1f} dB). Recommend boosting gain.")
                report["overall_score"] -= 8
            elif m_db > -8.0:
                report["warnings"].append(f"Audio is loud (mean: {m_db:.1f} dB). Risk of ear fatigue.")
                report["overall_score"] -= 8

            if mx_db > -0.2:
                report["warnings"].append(f"Audio peak ({mx_db:.1f} dB) is near clipping.")
                report["overall_score"] -= 5
        else:
            report["errors"].append("No audio track detected in final video!")
            report["overall_score"] -= 35

    def _deep_frame_inspection(self, video_path: str, frames_dir: Path, report: Dict[str, Any]):
        dur = report["stream_checks"].get("duration_seconds", 25.0)
        # Sample 5 key checkpoints across timeline (10%, 30%, 50%, 70%, 90%)
        sample_ratios = [0.10, 0.30, 0.50, 0.70, 0.90]
        
        sharpness_scores = []
        motion_deltas = []

        for i, ratio in enumerate(sample_ratios):
            t_sec = dur * ratio
            f1_path = frames_dir / f"inspect_frame_{i+1}_t1.png"
            f2_path = frames_dir / f"inspect_frame_{i+1}_t2.png"

            # Extract frame at t and t + 0.4s (to measure Ken Burns motion)
            c1 = [self.ffmpeg_exe, "-y", "-ss", str(round(t_sec, 2)), "-i", video_path, "-frames:v", "1", "-update", "1", str(f1_path)]
            c2 = [self.ffmpeg_exe, "-y", "-ss", str(round(t_sec + 0.4, 2)), "-i", video_path, "-frames:v", "1", "-update", "1", str(f2_path)]
            
            subprocess.run(c1, capture_output=True)
            subprocess.run(c2, capture_output=True)

            if not f1_path.exists():
                continue

            with Image.open(f1_path) as im:
                gray = im.convert("L")
                arr = np.array(gray, dtype=float)

                # 1. Black/Blank frame check
                mean_lum = float(np.mean(arr))
                is_black = bool(mean_lum < 8.0)

                # 2. Sharpness check (Edge Variance)
                edge = gray.filter(ImageFilter.FIND_EDGES)
                sharpness = float(np.var(np.array(edge)))
                sharpness_scores.append(sharpness)

                # 3. Letterbox check (left and right edges)
                left_col = arr[:, :20]
                right_col = arr[:, -20:]
                has_letterbox = bool(np.mean(left_col) < 5.0 and np.mean(right_col) < 5.0)

                # 4. Watermark & Logo Detection in Corners
                # Stock logos, channel stamps, and AI watermarks appear in the 4 corners
                w_img, h_img = im.size
                corner_boxes = {
                    "bottom_right": (w_img - 220, h_img - 140, w_img, h_img),
                    "bottom_left": (0, h_img - 140, 220, h_img),
                    "top_right": (w_img - 220, 0, w_img, 140),
                    "top_left": (0, 0, 220, 140)
                }
                frame_wm_flag = False
                for c_name, c_box in corner_boxes.items():
                    c_crop = gray.crop(c_box)
                    c_edges = np.array(c_crop.filter(ImageFilter.FIND_EDGES))
                    # Concentrated high-edge count indicates text logos or watermark badge
                    high_edge_px = int(np.sum(c_edges > 130))
                    if high_edge_px > 1800:
                        report["watermark_checks"]["watermark_detected"] = True
                        report["watermark_checks"]["clean_frames"] = False
                        flag_desc = f"{c_name} at {t_sec:.1f}s"
                        if flag_desc not in report["watermark_checks"]["flagged_corners"]:
                            report["watermark_checks"]["flagged_corners"].append(flag_desc)
                        frame_wm_flag = True

                # 5. Motion Delta
                motion_val = 0.0
                if f2_path.exists():
                    with Image.open(f2_path) as im2:
                        arr2 = np.array(im2.convert("L"), dtype=float)
                        motion_val = float(np.mean(np.abs(arr - arr2)))
                        motion_deltas.append(motion_val)

            frame_metric = {
                "checkpoint_sec": round(t_sec, 1),
                "preview_image": str(f1_path.name),
                "luminance": round(mean_lum, 1),
                "sharpness": round(sharpness, 1),
                "motion_delta": round(motion_val, 2),
                "is_black": is_black,
                "has_pillarbox": has_letterbox,
                "watermark_detected": frame_wm_flag
            }
            report["frame_inspections"].append(frame_metric)

            if is_black:
                report["warnings"].append(f"Blank/black frame detected at {t_sec:.1f}s.")
                report["overall_score"] -= 10
            if has_letterbox:
                report["warnings"].append(f"Possible pillarboxing (black bars on sides) at {t_sec:.1f}s.")
                report["overall_score"] -= 5
            if frame_wm_flag:
                report["warnings"].append(f"Watermark/logo pattern detected at {t_sec:.1f}s.")
                report["overall_score"] -= 15

        # Summarize motion
        avg_motion = float(np.mean(motion_deltas)) if motion_deltas else 0.0
        report["motion_checks"]["avg_motion_delta"] = round(avg_motion, 2)
        report["motion_checks"]["motion_active"] = bool(avg_motion > 0.5)
        if avg_motion < 0.3:
            report["warnings"].append("Video has low camera motion; feels static.")
            report["overall_score"] -= 10

        # Summarize sharpness
        avg_sharpness = float(np.mean(sharpness_scores)) if sharpness_scores else 0.0
        report["stream_checks"]["avg_sharpness"] = round(avg_sharpness, 1)
        if avg_sharpness < 40.0:
            report["warnings"].append("Visuals have low detail/sharpness score.")
            report["overall_score"] -= 8

    def _verify_subtitles(self, ass_path: str, report: Dict[str, Any]):
        a_path = Path(ass_path)
        if not a_path.exists():
            report["warnings"].append("Subtitle file (subtitles.ass) not found.")
            report["subtitle_checks"]["subtitles_found"] = False
            report["overall_score"] -= 15
            return

        report["subtitle_checks"]["subtitles_found"] = True
        with open(a_path, "r", encoding="utf-8") as f:
            content = f.read()

        dialogues = re.findall(r"Dialogue:\s*\d+,(.*?),(.*?),.*?,.*?,.*?,.*?,.*?,.*?,(.*)", content)
        report["subtitle_checks"]["dialogue_lines_count"] = len(dialogues)

        if not dialogues:
            report["warnings"].append("No dialogue events found inside subtitles.")
            report["overall_score"] -= 10
        else:
            # Check safe-zone positioning (MarginV)
            margin_match = re.search(r"Style:\s*Highlight.*?,(\d+),\d+\s*$", content, re.MULTILINE)
            if margin_match:
                margin_v = int(margin_match.group(1))
                report["subtitle_checks"]["margin_v"] = margin_v
                # In 1920h, safe zone bottom margin is between 400 and 900
                is_safe = 400 <= margin_v <= 900
                report["subtitle_checks"]["in_safe_zone"] = is_safe
                if not is_safe:
                    report["warnings"].append(f"Subtitles margin ({margin_v}) may overlap YouTube UI buttons.")
                    report["overall_score"] -= 5

    def _verify_scene_assets(self, image_paths: List[str], report: Dict[str, Any]):
        report["asset_checks"]["total_scenes"] = len(image_paths)
        valid_count = 0
        for p in image_paths:
            path_obj = Path(p)
            if path_obj.exists() and path_obj.stat().st_size > 5000:
                valid_count += 1
        report["asset_checks"]["valid_scene_images"] = valid_count
        if valid_count < len(image_paths):
            report["warnings"].append(f"Only {valid_count}/{len(image_paths)} scene images are valid on disk.")
            report["overall_score"] -= 10

    def _calculate_final_score(self, report: Dict[str, Any]):
        score = max(0, min(100, report["overall_score"]))
        report["overall_score"] = score

        if report["errors"]:
            report["status"] = "FAILED"
            report["qa_passed"] = False
        elif score >= 85:
            report["status"] = "PASSED"
            report["qa_passed"] = True
        else:
            report["status"] = "WARNINGS"
            report["qa_passed"] = True  # passes with warnings
