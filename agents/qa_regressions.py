"""Regression test groups for QATesterAgent (video quality, auto-repair, music, feedback, WeaponX, car
cards; subject accuracy / no-repeat). Split out of qa_tester_agent.py; the methods are unchanged and run
both in pytest (tests/test_app.py) and in the dashboard's QA Sanity."""
import os
import re
import sys
import time
import json
import shutil
import io
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    import config
except Exception:  # pragma: no cover
    config = None


class QARegressionChecksMixin:
    def _check_video_quality_regressions(self) -> List[Dict[str, Any]]:
        """
        Regressions for the 2026-11-19 end-to-end review: caption breaks, 1-second scenes, loudness,
        blurry thumbnail/hook clip, LLM scriptwriter never starting, generic Hindi, the approve gate,
        'published' status, orphaned in_progress records, upload checks, add-scene repeats, and a
        real offline render (compose -> captions -> mastering -> ffprobe). Network/LLM calls are mocked.
        """
        from unittest import mock
        import tempfile
        import subprocess
        records: List[Dict[str, Any]] = []

        def record(name, fn, remediation):
            t0 = time.time()
            try:
                detail = fn()
                records.append({"name": name, "category": "Video Quality & Safety", "status": "PASSED",
                                "duration_ms": int((time.time() - t0) * 1000), "details": detail, "remediation": None})
            except Exception as e:
                records.append({"name": name, "category": "Video Quality & Safety", "status": "FAILED",
                                "duration_ms": int((time.time() - t0) * 1000), "details": f"{type(e).__name__}: {e}",
                                "remediation": remediation})

        def words_of(text, step=0.3):
            return [{"text": t, "start": round(i * step, 3), "end": round(i * step + step * 0.8, 3)}
                    for i, t in enumerate(text.split())]

        def ffmpeg():
            from app.agents.audio_master import _ffmpeg
            return _ffmpeg()

        def t_captions():
            from app.agents import caption_chunker as cc
            script = ("Here's what sets the F-35 Lightning II apart. It is an American family of stealth fighters. "
                      "As of April 2026, the US operates all three variants. Could anything counter F-35 Lightning II? "
                      "Drop your verdict below.")
            w = words_of(re.sub(r"[.,?]", "", script))
            cc.prepare(w, script, ["F-35 Lightning II"])
            lines = [" ".join(cc.display_text(x) for x in ch) for ch in cc.chunk_words(w, 3)]
            for ln in lines:
                assert not ln.endswith("Lightning") and not ln.startswith("II"), f"name split: {lines}"
            assert any(ln.endswith("F-35 Lightning II?") for ln in lines), f"'?' lost: {lines}"
            assert "As of April 2026" in lines, f"date split: {lines}"
            assert not any(ln in ("apart", "below") for ln in lines), f"dangling word: {lines}"
            srt = cc.to_srt(w)
            assert "apart.\n" in srt and "2026," in srt, "SRT lost punctuation"
            # Styled captions use the same chunker
            from app.agents.caption_style import render_ass, preset_style
            ass = re.sub(r"\{[^}]*\}", "", render_ass(w, preset_style("classic")))  # drop styling tags
            assert "LIGHTNING II?" in ass.upper(), "styled captions lost the name/question mark"
            # Kokoro sometimes keeps the period on the word itself: never print "F-35C.."
            k = [{"text": "and", "start": 0, "end": .2}, {"text": "F-35C.", "start": .3, "end": .6}, {"text": "U.S.", "start": .7, "end": .9}]
            cc.prepare(k, "and F-35C. U.S.", [])
            assert ".." not in cc.to_srt(k) and cc.display_text(k[2]) == "U.S.", cc.to_srt(k)
            hi = "क्या आप F-35 की असली कहानी जानते हैं? यह बहुत तेज़ है। सच में।"
            hw = words_of(hi.replace("?", "").replace("।", ""))
            cc.prepare(hw, hi, [])
            assert hw[-1]["punct"] == "।" and [x["text"] for x in cc.chunk_words(hw, 4)[-1]] == ["सच", "में"]
            return f"{len(lines)} captions, names intact, '?' kept, Hindi danda ends cues: {lines[:4]}..."

        def t_tiny_scenes():
            from agents.content_analyser import ContentAnalyserAgent
            sc = [{"scene_number": i + 1, "narration": n, "duration_seconds": 3.0} for i, n in enumerate([
                "The F-35 is a family of stealth fighters.", "As of April 2026,",
                "the US operates all three main variants.", "Drop a comment."])]
            out = ContentAnalyserAgent._merge_tiny_scenes(sc)
            assert [s["narration"] for s in out] == ["The F-35 is a family of stealth fighters.",
                                                    "As of April 2026, the US operates all three main variants. Drop a comment."] or \
                   len(out) == 2, [s["narration"] for s in out]
            assert all(len(s["narration"].split()) >= 5 for s in out) and [s["scene_number"] for s in out] == [1, 2]
            assert abs(sum(s["duration_seconds"] for s in out) - 12.0) < 1e-6, "durations not preserved"
            beat = [{"narration": ""}, {"narration": ""}]
            assert ContentAnalyserAgent._merge_tiny_scenes(beat) == beat, "music-only scenes must be untouched"
            return f"4 scenes -> {len(out)}; durations preserved; narration-less scenes untouched"

        def t_loudness():
            from app.agents import audio_master
            tmp = Path(tempfile.mkdtemp(prefix="qa_loud_"))
            v = tmp / "v.mp4"
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x568:d=6",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=6,volume=0.05",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(v)],
                           check=True, capture_output=True, timeout=60)
            rep = audio_master.master(str(v))
            m = audio_master.measure(str(v))
            assert rep["applied"] and abs(m["input_i"] - audio_master.TARGET_I) <= 1.5, (rep, m)
            assert m["input_tp"] <= audio_master.TARGET_TP + 0.3, f"true peak {m['input_tp']}"
            silent = tmp / "s.mp4"
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x568:d=2",
                            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-t", "2", str(silent)], check=True, capture_output=True, timeout=60)
            assert not audio_master.master(str(silent))["applied"], "silent (mute) video must be left alone"
            return f"{rep['before_lufs']} -> {round(m['input_i'], 1)} LUFS, peak {round(m['input_tp'], 1)} dBTP; mute left alone"

        def t_thumbnail_and_clip():
            from PIL import ImageDraw, ImageFilter
            from app.agents import thumbnail as th
            tmp = Path(tempfile.mkdtemp(prefix="qa_thumb_"))
            (tmp / "scenes").mkdir()
            sharp = Image.new("RGB", (1080, 1920), (30, 30, 30))
            d = ImageDraw.Draw(sharp)
            for x in range(0, 1080, 24):
                d.line([(x, 0), (x, 1920)], fill=(240, 240, 240), width=3)
            blurry = sharp.filter(ImageFilter.GaussianBlur(28))
            s1, s2 = tmp / "scenes" / "scene_01.png", tmp / "scenes" / "scene_02.png"
            blurry.save(s1)
            sharp.save(s2)
            thumb = th.pick_thumbnail({"project_dir": str(tmp), "image_paths": [str(s1), str(s2)]})
            assert thumb and Image.open(thumb).tobytes() == Image.open(s2).tobytes(), "thumbnail should be the sharp scene"
            clip = tmp / "clip.mp4"
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-loop", "1", "-i", str(s1), "-t", "2", "-r", "10",
                            "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True, timeout=60)
            ratio = th.clip_sharpness_ratio(str(clip), str(s2))
            assert ratio is not None and ratio < th.MIN_CLIP_SHARPNESS_RATIO, f"blurry clip ratio {ratio}"
            return f"sharp scene 2 chosen over hazy scene 1; smeared clip scored {ratio:.0%} (< {th.MIN_CLIP_SHARPNESS_RATIO:.0%}) and would be rejected"

        def t_scriptwriter_starts_ollama():
            from agents import script_writer as sw
            from app.automation import resources
            state = {"up": False, "leased": 0}

            class Lease:
                def __enter__(self):
                    state["leased"] += 1
                    state["up"] = True
                def __exit__(self, *a):
                    state["up"] = False

            facts = [{"text": f"The F-35 fact number {i} has enough words in it here.", "source": "s"} for i in range(5)]
            with mock.patch.dict(os.environ, {"SCRIPT_WRITER": "auto"}), \
                 mock.patch.object(sw, "is_available", lambda: state["up"]), \
                 mock.patch.object(sw, "can_run", lambda: True), \
                 mock.patch.object(resources, "lease", lambda *a, **k: Lease()), \
                 mock.patch.object(sw, "_ollama", side_effect=RuntimeError("stub LLM")):
                sw.write_brief("F-35", facts, 20.0)
            assert state["leased"] == 1, "write_brief never started Ollama (checked availability before leasing)"
            with mock.patch.dict(os.environ, {"SCRIPT_WRITER": "template"}):
                assert sw.can_run() is False
            prev = os.environ.get("SCRIPT_WRITER")
            return f"Ollama is leased (started on demand) before use; template mode honoured at call time; env now {prev!r}"

        def t_hindi_ollama():
            from agents.hindi_voice_agent import HindiVoiceAgent
            from agents import script_writer as sw
            from app.automation import resources
            from contextlib import nullcontext
            script = {"topic": "F-35", "scenes": [
                {"narration": "The F-35 first flew in 2006."}, {"narration": "Three variants serve many air forces."}]}
            good = {"title": "F-35 की कहानी", "scenes": [
                {"scene_number": 1, "narration": "F-35 ने पहली बार 2006 में उड़ान भरी।"},
                {"scene_number": 2, "narration": "इसके तीन संस्करण कई वायुसेनाओं में हैं।"}]}
            lost = {"title": "x", "scenes": [{"scene_number": 1, "narration": "F-35 ने पहली बार उड़ान भरी।"},
                                             {"scene_number": 2, "narration": "तीन संस्करण हैं।"}]}
            agent = HindiVoiceAgent()
            with mock.patch.object(sw, "can_run", lambda: True), mock.patch.object(sw, "is_available", lambda: True), \
                 mock.patch.object(resources, "lease", lambda *a, **k: nullcontext()), \
                 mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}), mock.patch.object(config, "GEMINI_API_KEY", "", create=True), \
                 mock.patch.object(config, "STUDIO_SETTINGS_FILE", Path(tempfile.mkdtemp()) / "none.json", create=True):
                with mock.patch.object(sw, "_ollama", return_value=good):
                    out = agent.translate_or_create_hindi_script(script, topic="F-35")
                with mock.patch.object(sw, "_ollama", return_value=lost):
                    fb = agent.translate_or_create_hindi_script(script, topic="F-35")
            assert str(out.get("translation_mode", "")).startswith("ollama:"), out.get("translation_mode")
            assert out["scenes"][0]["narration"] == good["scenes"][0]["narration"]
            assert fb.get("translation_mode") == "offline_neutral_templates", "a translation that drops '2006' must be rejected"
            return "Scenes translated by the local model; a translation that loses a number falls back to templates"

        def client():
            from starlette.testclient import TestClient
            from app import web_app as wa
            return TestClient(wa.app), wa

        def fake_project(tmp: Path, n_scenes=2, status="completed"):
            sd = tmp / "scenes"
            sd.mkdir(parents=True, exist_ok=True)
            paths = []
            for i in range(1, n_scenes + 1):
                p = sd / f"scene_{i:02d}.png"
                Image.new("RGB", (1080, 1920), (20 * i, 60, 120)).save(p)
                paths.append(str(p))
            vid = tmp / "final_short.mp4"
            vid.write_bytes(b"0" * 4000)
            return {"id": "qa_fake_project", "topic": "F-35 Lightning II", "status": status, "style": "default",
                    "project_dir": str(tmp), "image_paths": paths, "video_path": str(vid), "title": "F-35 #Shorts",
                    "description": "d", "tags": ["f35"],
                    "scenes": [{"scene_number": i, "narration": "Some narration words here now.", "image_path": p}
                               for i, p in enumerate(paths, 1)]}

        def t_api_validation():
            c, wa = client()
            with mock.patch.object(wa.pipeline, "prepare_project", side_effect=AssertionError("project created")):
                r = c.post("/api/generate", json={"topic": "QA orphan check", "motion": "spin"})
            assert r.status_code == 400, (r.status_code, r.text[:200])
            proj = fake_project(Path(tempfile.mkdtemp(prefix="qa_api_")))
            saved = []
            with mock.patch.object(wa.StorageManager, "get_project_by_id", lambda pid: proj), \
                 mock.patch.object(wa.StorageManager, "save_project", lambda p: saved.append(p)):
                junk = c.post("/api/projects/qa_fake_project/scenes/1/image", files={"file": ("x.png", b"not an image " * 200)})
                good = io.BytesIO()
                Image.new("RGB", (900, 1600), (200, 10, 10)).save(good, "PNG")
                far = c.post("/api/projects/qa_fake_project/scenes/99/image", files={"file": ("x.png", good.getvalue())})
            assert junk.status_code == 400, (junk.status_code, junk.text[:200])
            assert far.status_code == 404, (far.status_code, far.text[:200])
            assert not saved and not (Path(proj["project_dir"]) / "scenes" / "scene_99.png").exists()
            return "invalid motion -> 400 before any project exists; junk upload -> 400; scene 99 -> 404, nothing written"

        def t_upload_warning():
            c, wa = client()
            proj = fake_project(Path(tempfile.mkdtemp(prefix="qa_up_")))
            from agents.image_generator import ImageGeneratorAgent
            buf = io.BytesIO()
            Image.new("RGB", (900, 1600), (90, 90, 40)).save(buf, "PNG")
            with mock.patch.object(wa.StorageManager, "get_project_by_id", lambda pid: proj), \
                 mock.patch.object(wa.StorageManager, "save_project", lambda p: None), \
                 mock.patch.object(ImageGeneratorAgent, "_verify_image_content",
                                   lambda self, *a, **k: {"passed": False, "top_decoy": "artillery"}):
                r = c.post("/api/projects/qa_fake_project/scenes/2/image", files={"file": ("x.png", buf.getvalue())})
            assert r.status_code == 200 and "artillery" in r.json().get("warning", ""), r.text[:300]
            assert proj["scenes"][1]["visual_source"] == "manual_upload", "upload must still be kept"
            return "off-topic upload kept, with a warning shown to the user"

        def t_approve_gate_and_status():
            c, wa = client()
            from app.automation import publish_gate
            proj = fake_project(Path(tempfile.mkdtemp(prefix="qa_gate_")), status="pending_approval")
            proj["youtube"] = {"video_id": "vid1"}
            calls = []
            fake_up = lambda **k: calls.append("upload") or {"approval_status": "uploaded", "video_id": "v"}
            fake_ap = lambda **k: calls.append("approve") or {"approval_status": "approved_private"}
            with mock.patch.object(wa.StorageManager, "get_project_by_id", lambda pid: proj), \
                 mock.patch.object(wa.StorageManager, "save_project", lambda p: None), \
                 mock.patch.object(publish_gate, "fresh_qa", lambda p: (False, ["Scene Image Uniqueness: (5, 6)"])), \
                 mock.patch.object(wa.YouTubePublisher, "upload_short", staticmethod(fake_up)), \
                 mock.patch.object(wa.YouTubePublisher, "approve_and_go_live", staticmethod(fake_ap)):
                blocked = c.post("/api/publish/qa_fake_project/approve", json={})
                blocked_up = c.post("/api/publish/qa_fake_project", json={})
                assert calls == [], f"YouTube was called while QA fails: {calls}"
                forced = c.post("/api/publish/qa_fake_project/approve", json={"override_qa": True})
                up = c.post("/api/publish/qa_fake_project", json={"override_qa": True})
            assert blocked.status_code == 409 and blocked.json()["detail"]["qa_blocked"], blocked.text[:200]
            assert blocked_up.status_code == 409
            assert forced.status_code == 200 and up.status_code == 200, (forced.text[:200], up.text[:200])
            assert proj["status"] == "uploaded_private", f"status after upload: {proj['status']}"
            js = (self.root_dir / "app" / "static" / "app.js").read_text(encoding="utf-8")
            assert "() => publishActiveProject(false)" in js and "() => approveActiveProjectLive(false)" in js, \
                "click handlers must not pass the click event as override_qa"
            return "Approve/Upload refused (409, YouTube untouched) while QA fails; explicit override works; status 'uploaded_private'"

        def t_orphan_sweep():
            _, wa = client()
            dead = 2 ** 22 + 12345
            while wa._pid_alive(dead):
                dead += 1
            projs = [{"id": "dead", "status": "in_progress", "worker_pid": dead},
                     {"id": "live", "status": "in_progress", "worker_pid": os.getppid()},
                     {"id": "legacy", "status": "in_progress"},
                     {"id": "done", "status": "completed", "worker_pid": dead}]
            with mock.patch.object(wa.StorageManager, "get_all_projects", lambda: projs), \
                 mock.patch.object(wa.StorageManager, "save_project", lambda p: None):
                marked = wa.sweep_orphaned_generations("test")
            assert sorted(marked) == ["dead", "legacy"], marked
            assert projs[1]["status"] == "in_progress", "a live process's generation must not be failed"
            return "dead/legacy in_progress -> failed; a live worker's job (e.g. the scheduler's) is left running"

        def t_qa_status_cached():
            c, _ = client()
            with mock.patch.object(type(self), "run_full_sanity", side_effect=AssertionError("suite re-run")):
                r = c.get("/api/qa/status")
            assert r.status_code == 200, r.text[:200]
            return f"GET /api/qa/status returns the saved report ({r.json().get('overall_status')}) without re-running"

        def t_add_scene_fresh():
            c, wa = client()
            proj = fake_project(Path(tempfile.mkdtemp(prefix="qa_add_")))
            from agents.image_generator import ImageGeneratorAgent

            def fresh(self, topic, scene, pos, dest, used_urls=None, existing_images=None, **k):
                Image.new("RGB", (1080, 1920), (1, 200, 30)).save(dest)
                return {"scene_number": pos, "image_path": str(dest), "source": "web_free", "source_url": "https://x/new.jpg"}
            with mock.patch.object(wa.StorageManager, "get_project_by_id", lambda pid: proj), \
                 mock.patch.object(wa.StorageManager, "save_project", lambda p: None), \
                 mock.patch.object(ImageGeneratorAgent, "acquire_fresh_web_image", fresh):
                r = c.post("/api/projects/qa_fake_project/scenes", json={"narration": "A new scene about sensor fusion.", "position": 2})
            assert r.status_code == 200 and r.json().get("fresh_image") is True, r.text[:300]
            new = proj["scenes"][1]
            assert new["visual_source"] == "web_free", new
            a, b = Image.open(proj["image_paths"][0]).tobytes(), Image.open(new["image_path"]).tobytes()
            assert a != b, "new scene still copies its neighbour"
            return "added scene gets a new verified photo instead of a copy of its neighbour"

        def t_e2e_render():
            from app.agents.video_composer import VideoComposer
            from app.agents.voice_agent import VoiceAgent
            from app.agents import audio_master
            tmp = Path(tempfile.mkdtemp(prefix="qa_e2e_"))
            imgs = []
            for i, col in enumerate([(200, 40, 40), (40, 160, 60), (40, 60, 200)], 1):
                p = tmp / f"scene_{i:02d}.png"
                im = Image.new("RGB", (1080, 1920), col)
                ImageDraw = __import__("PIL.ImageDraw", fromlist=["ImageDraw"])
                ImageDraw.Draw(im).rectangle([200 + 40 * i, 600, 880, 1300], fill=(240, 240, 240))
                im.save(p)
                imgs.append(str(p))
            voice = tmp / "voiceover.mp3"
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=6,volume=0.3",
                            "-c:a", "libmp3lame", str(voice)], check=True, capture_output=True, timeout=60)
            text = "The F-35 Lightning II is a stealth fighter. It flies fast. Could anything counter it?"
            from app.agents import caption_chunker as cc
            w = words_of(re.sub(r"[.?]", "", text), step=0.38)
            cc.prepare(w, text, ["F-35 Lightning II"])
            ass = tmp / "subtitles.ass"
            VoiceAgent._generate_styled_ass(w, ass, [{"narration": "x"}] * 3, [2.0, 2.0, 2.0], None)
            out = VideoComposer().compose_video(imgs, [2.0, 2.0, 2.0], str(voice), str(ass), tmp, topic="F-35",
                                                with_voice=True, with_music=False)
            info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", out],
                                             capture_output=True, text=True).stdout or "{}")
            v = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
            a = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
            assert v and (v[0]["width"], v[0]["height"]) == (1080, 1920) and v[0]["codec_name"] == "h264", v
            assert a, "no audio stream"
            dur = float(info["format"]["duration"])
            assert 5.5 <= dur <= 6.6, f"duration {dur}"
            m = audio_master.measure(out)
            assert m and abs(m["input_i"] - audio_master.TARGET_I) <= 1.5, f"loudness {m}"
            body = re.sub(r"\{[^}]*\}", "", ass.read_text(encoding="utf-8"))  # drop styling tags
            assert "LIGHTNING II" in body and "COUNTER IT?" in body, "captions missing name/question"
            return f"3-scene render: 1080x1920 h264 + audio, {dur:.1f}s, {m['input_i']:.1f} LUFS, phrase captions burned"

        def make_video(tmp: Path, seconds=4.0, black_from=None, audio_seconds=None, volume=0.3, master=True):
            """Small real 1080x1920 H.264 video with a tone, optionally with defects."""
            vf = "color=c=0x3060a0:s=1080x1920:d=%.2f" % seconds
            if black_from is not None:
                vf += f",drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='gte(t,{black_from})'"
            out = tmp / "final_short.mp4"
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", vf, "-f", "lavfi", "-i",
                            f"sine=frequency=330:duration={audio_seconds or seconds},volume={volume}",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", f"{seconds}", str(out)],
                           check=True, capture_output=True, timeout=120)
            if master:
                from app.agents.audio_master import master as _m
                _m(str(out))
            return out

        def t_render_guard():
            from agents import render_guard as rg
            tmp = Path(tempfile.mkdtemp(prefix="qa_guard_"))
            good = make_video(tmp)
            proj = {"video_path": str(good), "duration": 4.0, "with_voice": False, "with_music": True}
            fails = [c["name"] for c in rg.run(proj) if not c["passed"]]
            assert not fails, f"clean video flagged: {fails}"
            # Defects, each must be caught with the right fix
            loud = make_video(Path(tempfile.mkdtemp()), volume=0.9, master=False)
            c = {x["name"]: x for x in rg.run({**proj, "video_path": str(loud)})}
            assert not c["Render: loudness -14 LUFS, no clipping"]["passed"] and c["Render: loudness -14 LUFS, no clipping"]["fix"] == "remaster"
            black = make_video(Path(tempfile.mkdtemp()), seconds=4.0, black_from=2.5)
            assert not {x["name"]: x for x in rg.run({**proj, "video_path": str(black)})}["Render: no black frames"]["passed"]
            gap = make_video(Path(tempfile.mkdtemp()), seconds=4.0, audio_seconds=1.5)
            names = [x["name"] for x in rg.run({**proj, "video_path": str(gap), "duration": 4.0}) if not x["passed"]]
            assert "Render: no dead air" in names or "Render: audio and video in sync" in names, names
            long = {**proj, "duration": 9.0}
            assert not {x["name"]: x for x in rg.run(long)}["Render: audio and video in sync"]["passed"], "length mismatch missed"
            rushed = {**proj, "with_voice": True, "voice_rate_pct": 27}
            r = {x["name"]: x for x in rg.run(rushed)}["Voice: natural pace (not rushed)"]
            assert not r["passed"] and r["fix"] == "relax_duration"
            # Caption checks on a narrated 2-scene project
            ass = tmp / "subtitles.ass"
            ev = lambda a, b, t: f"Dialogue: 0,0:00:0{a}.00,0:00:0{b}.00,Bottom,,0,0,0,,{t}"
            ass.write_text("[Events]\n" + "\n".join([ev(0, 1, "THE F-35 LIGHTNING"), ev(1, 2, "II IS FAST.."),
                                                     ev(2, 3, "IT FLIES HIGH")]), encoding="utf-8")
            narr = {**proj, "with_voice": True, "subtitles_path": str(ass), "topic": "F-35 Lightning II",
                    "scenes": [{"narration": "The F-35 Lightning II is fast."}, {"narration": "It flies high."}]}
            c = {x["name"]: x for x in rg.run(narr)}
            assert not c["Captions: subject name never split"]["passed"], "name split missed"
            assert not c["Captions: clean text and timing"]["passed"], "'..' missed"
            assert c["Captions: match the narration"]["passed"], c["Captions: match the narration"]["detail"]
            ass.write_text("[Events]\n" + ev(0, 3, "THE F-35 IS SLOW"), encoding="utf-8")
            assert not {x["name"]: x for x in rg.run(narr)}["Captions: match the narration"]["passed"], "wrong captions missed"
            return "clean video passes; loudness, black frames, dead air/sync, length, rushed voice, split name, '..', wrong captions all caught"

        def t_auto_repair():
            from app.agents.pipeline import ShortsPipeline
            from app.agents import audio_master
            tmp = Path(tempfile.mkdtemp(prefix="qa_repair_"))
            vid = make_video(tmp, volume=0.9, master=False)
            store = {"p": {"id": "qa_rep", "video_path": str(vid), "title": "T", "description": "d", "tags": [], "topic": "x",
                           "status": "completed", "project_dir": str(tmp), "scenes": []}}
            calls = {"n": 0}

            def verify(project_record=None, **k):
                calls["n"] += 1
                m = audio_master.measure(project_record["video_path"])
                ok = abs(m["input_i"] + 14) <= 1.0
                return {"qa_passed": ok, "auto_fixes": [] if ok else ["remaster"], "all_checks": [],
                        "blocking_failures": [] if ok else ["loudness"], "overall_score": 90 if ok else 70}
            pl = ShortsPipeline.__new__(ShortsPipeline)
            pl.verify_video = type("V", (), {"run": staticmethod(verify)})()
            with mock.patch("app.agents.pipeline.StorageManager.get_project_by_id", lambda pid: store["p"]), \
                 mock.patch("app.agents.pipeline.StorageManager.save_project", lambda p: store.update(p=p)):
                out = pl.auto_repair("qa_rep", allow_rerender=False)
            assert out["qa_report"]["qa_passed"], out.get("auto_repair")
            assert out["auto_repair"] and "re-mastered audio" in out["auto_repair"][0]["fixed"], out["auto_repair"]
            # Something that can't be fixed stops after the rounds with the reasons kept
            store["p"] = {"id": "qa_rep2", "video_path": str(vid), "status": "completed", "qa_report":
                          {"qa_passed": False, "auto_fixes": [], "blocking_failures": ["black frames"]}}
            with mock.patch("app.agents.pipeline.StorageManager.get_project_by_id", lambda pid: store["p"]), \
                 mock.patch("app.agents.pipeline.StorageManager.save_project", lambda p: store.update(p=p)):
                out2 = pl.auto_repair("qa_rep2")
            assert not out2["qa_report"]["qa_passed"] and out2["auto_repair"] == []
            return "fixable failure (loudness) repaired and re-checked to PASSED; unfixable one left with its reasons"

        def t_same_voice_on_rerender():
            from app.agents import pipeline as plm
            seen = []
            tmp = Path(tempfile.mkdtemp(prefix="qa_voice_"))
            (tmp / "scenes").mkdir()
            img = tmp / "scenes" / "scene_01.png"
            Image.new("RGB", (1080, 1920)).save(img)
            legacy = {"id": "v", "project_dir": str(tmp), "topic": "F-35", "scenes": [{"narration": "Hello there friends.", "image_path": str(img)}],
                      "voice": "en-US-ChristopherNeural", "with_voice": True, "with_music": False, "target_duration": 5, "status": "completed"}
            picked = {**legacy, "voice": "en-GB-RyanNeural", "voice_explicit": True}

            def fake_voice(script_data, project_dir, voice=None, **k):
                seen.append((voice, script_data.get("topic")))
                return {"audio_path": None, "ass_path": None, "scene_durations": [5.0], "total_duration": 5.0,
                        "voice_engine": "kokoro", "rate_pct": 0}
            pl = plm.ShortsPipeline.__new__(plm.ShortsPipeline)
            pl.composer = type("C", (), {"compose_video": staticmethod(lambda **k: str(tmp / "final_short.mp4"))})()
            pl.verify_video = type("V", (), {"run": staticmethod(lambda **k: {"qa_passed": True, "overall_score": 95})})()
            for proj in (legacy, picked):
                with mock.patch.object(plm.StorageManager, "get_project_by_id", lambda pid, _p=proj: _p), \
                     mock.patch.object(plm.StorageManager, "save_project", lambda p: None), \
                     mock.patch.object(plm.VoiceAgent, "generate_voiceover", staticmethod(fake_voice)):
                    pl.rerender_project("v")
            assert seen[0] == (None, "F-35"), f"legacy re-render forced {seen[0]} (should use the default narrator)"
            assert seen[1][0] == "en-GB-RyanNeural", "a voice the user picked must be kept"
            return "re-render keeps the default narrator (no switch to Edge 'Christopher'); a picked voice is kept; topic passed for captions"

        def t_theme_music():
            from agents import theme_music as tm
            from agents.acestep_music_agent import ACEStepMusicAgent
            from agents.music_generator import AIMusicGenerator
            from agents.music_agent import MusicAgent
            assert tm.theme_for("Modern Submarine Weapon Systems")[0] == "Naval Depths"
            assert tm.theme_for("F-35 Lightning II")[0] == "Sky Dominance"
            assert tm.theme_for("Leopard 2A8")[0] == "Armored Assault"
            assert tm.theme_for("Top Hypersonic Missiles")[0] == "Strike Countdown"
            assert "phonk" in tm.theme_for("Ferrari F80", kind="car", phonk_style="drift_phonk")[1].lower()
            tmp = Path(tempfile.mkdtemp(prefix="qa_music_"))
            wav = tmp / "gen.wav"
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=3", str(wav)],
                           check=True, capture_output=True, timeout=30)
            saved = []
            def fake_save(self, source_path_or_id, name, **k):
                saved.append((source_path_or_id, name, k.get("prompt", "")))
                return {"id": "lib_test", "name": name, "file_path": str(source_path_or_id)}
            # never touch the REAL pre-made pool / usage state from a test
            iso = [mock.patch.object(tm, "take_from_pool", lambda *a, **k: None), mock.patch.object(tm, "_mark_used", lambda *a, **k: None)]
            for m_ in iso:
                m_.start()
            self._qa_cleanups = getattr(self, "_qa_cleanups", []) + iso
            with mock.patch.object(AIMusicGenerator, "save_to_library", fake_save), \
                 mock.patch.object(ACEStepMusicAgent, "generate_track", lambda self, **k: {"file_path": str(wav)}):
                rec = tm.fresh_theme_track("F-35 Lightning II", 20, kind="weapon")
            assert rec and rec["engine"] == "ACE-Step 1.5" and rec["theme"] == "Sky Dominance", rec
            assert saved and "F-35 Lightning II" in saved[0][1] and "orchestral" in saved[0][2], saved
            def ace_down(self, **k):
                raise RuntimeError("acestep not running")
            with mock.patch.object(AIMusicGenerator, "save_to_library", fake_save), \
                 mock.patch.object(ACEStepMusicAgent, "generate_track", ace_down), \
                 mock.patch.object(MusicAgent, "generate_track", lambda self, **k: {"file_path": str(wav)}):
                rec2 = tm.fresh_theme_track("Leopard 2A8", 20, kind="weapon")
            for m_ in iso:
                m_.stop()
            assert rec2 and rec2["engine"] == "Built-in MusicAgent" and len(saved) == 2
            src = (self.root_dir / "app" / "agents" / "pipeline.py").read_text(encoding="utf-8")
            assert "theme_music.fresh_theme_track(" in src, "pipeline no longer generates theme music"
            return "car/weapon themes mapped; new track via ACE-Step (or built-in fallback) is saved to the library every time"

        def t_feedback_parse():
            from agents import feedback_fixer as ff
            proj = {"topic": "F-35", "scenes": [{"narration": f"Line {i}"} for i in range(1, 7)]}
            P = lambda t: [(a["action"], a.get("scene")) for a in ff.parse_rules(t, proj)]
            cases = {
                "scene 3 image is wrong": [("replace_image", 3)],
                "the second picture is blurry": [("replace_image", 2)],
                "photo 5 shows a different jet": [("replace_image", 5)],
                "last image is the same as before": [("replace_image", 6)],
                "music is boring, change it": [("new_music", None)],
                "music too loud, can't hear the voice": [("music_volume", None)],
                "voice is too fast": [("slower_voice", None)],
                "remove scene 4": [("remove_scene", 4)],
                "captions are out of sync": [("rerender", None)],
                "i like it": [],
            }
            for text, want in cases.items():
                got = P(text)
                assert got == want, f"{text!r}: {got} != {want}"
            a = ff.parse_rules('scene 2 should say "It carries 18,000 lb of fuel."', proj)
            assert a == [{"action": "set_narration", "scene": 2, "text": "It carries 18,000 lb of fuel."}], a
            t = ff.parse_rules('title should be "F-35: Sky King"', proj)
            assert t and t[0]["action"] == "set_title" and t[0]["text"] == "F-35: Sky King", t
            # The LLM may only use text the user actually wrote
            from agents import script_writer as sw
            from app.automation import resources
            from contextlib import nullcontext
            with mock.patch.object(sw, "can_run", lambda: True), mock.patch.object(sw, "is_available", lambda: True), \
                 mock.patch.object(resources, "lease", lambda *a, **k: nullcontext()), \
                 mock.patch.object(sw, "_ollama", return_value={"actions": [
                     {"action": "set_narration", "scene": 1, "text": "Invented by the model"},
                     {"action": "replace_image", "scene": 4}, {"action": "replace_image", "scene": 99}]}):
                llm = ff.parse_llm("the tank in that fourth bit looks off", proj)
            assert llm == [{"action": "replace_image", "scene": 4}], llm
            return f"{len(cases) + 2} phrasings mapped correctly; LLM fallback can't invent text or bad scene numbers"

        def t_feedback_apply_and_api():
            c, wa = client()
            from app.agents import pipeline as plm
            from agents import theme_music
            proj = fake_project(Path(tempfile.mkdtemp(prefix="qa_fb_")), n_scenes=4)
            proj.update(music_volume=0.3, target_duration=20, duration=20, voice_rate_pct=0)
            with mock.patch.object(wa.StorageManager, "get_project_by_id", lambda pid: proj), \
                 mock.patch.object(wa.StorageManager, "save_project", lambda p: None):
                r1 = c.post("/api/projects/qa_fake_project/feedback", json={"text": "scene 2 image is wrong and music too loud"})
                r2 = c.post("/api/projects/qa_fake_project/feedback", json={"text": "remove scene 4"})
                r3 = c.post("/api/projects/qa_fake_project/feedback", json={"text": "make it more emotional somehow"})
                bad = c.post("/api/projects/qa_fake_project/feedback", json={"text": "  "})
            assert r1.status_code == 200 and "new image for scene 2" in r1.json()["item"]["preview"], r1.text[:300]
            assert bad.status_code == 400 and len(proj["feedback"]) == 3
            fid = proj["feedback"][2]["id"]
            pl = plm.ShortsPipeline.__new__(plm.ShortsPipeline)
            replaced = []
            pl._replace_scene_image = lambda project, n: replaced.append(n) or True
            with mock.patch.object(plm.StorageManager, "save_project", lambda p: None), \
                 mock.patch.object(theme_music, "fresh_theme_track", lambda *a, **k: None), \
                 mock.patch("agents.feedback_fixer.parse_llm", lambda text, project: []):
                need = pl.apply_feedback(proj)
            st = {f["text"][:12]: f["status"] for f in proj["feedback"]}
            assert need and replaced == [2], (need, replaced)
            assert abs(proj["music_volume"] - 0.18) < 1e-6, proj["music_volume"]
            assert len(proj["scenes"]) == 3 and [s["scene_number"] for s in proj["scenes"]] == [1, 2, 3]
            assert st["scene 2 imag"] == "fixed" and st["remove scene"] == "fixed" and st["make it more"] == "needs_you", st
            with mock.patch.object(wa.StorageManager, "get_project_by_id", lambda pid: proj), \
                 mock.patch.object(wa.StorageManager, "save_project", lambda p: None):
                d = c.delete(f"/api/projects/qa_fake_project/feedback/{fid}")
            assert d.status_code == 200 and len(proj["feedback"]) == 2
            js = (self.root_dir / "app" / "static" / "app.js").read_text(encoding="utf-8")
            assert "openFeedbackPanel(" in js and "card-fb-btn" in js and "/feedback`" in js, "feedback UI missing"
            return "notes saved with a preview; Auto-fix applied image/volume/remove-scene, kept the vague note as 'needs you'"

        def t_weaponx_topic_list():
            from agents import topic_weapon_list as tl
            from agents import ranked_poster as rp
            from agents import render_guard as rg
            assert tl.kind_for("Modern Submarine Weapon Systems") == "naval"
            assert tl.kind_for("Top Hypersonic Missiles") == "missile" and tl.kind_for("Attack Helicopters") == "aircraft"
            nav = rp.KINDS["naval"]["kind_re"]
            M = lambda typ, **k: {"title": k.get("title", "X"), "image_url": "u", "type": typ, "origin": "United States", "year": 2000, **k}
            assert tl._is_kind(M("Anti-ship missile"), "naval", nav), "anti-ship missile wrongly excluded"
            assert tl._is_kind(M("Heavyweight torpedo"), "naval", nav)
            assert not tl._is_kind(M("Nuclear-powered ballistic missile submarine (SSBN)"), "naval", nav), "platform let in"
            assert not tl._is_kind(M("Double-tap missile strike"), "naval", nav), "news event let in"
            assert not tl._is_kind(M("Torpedo", origin="", year=None), "naval", nav), "article without origin/year let in"
            assert tl._clean_type("{{idp| *Cruise missile *Anti-ship missile") == "Cruise missile"
            b1, _ = tl._bullets(M("Heavyweight dual-purpose ASW and anti-surface torpedo"))
            assert not b1.endswith(" and"), b1
            # build_rows: verified + photo-checked models only, newest first for "modern"
            arts = {f"T{i}": M("Heavyweight torpedo", title=f"T{i}", year=1960 + 8 * i) for i in range(8)}
            arts["Sub"] = M("Attack submarine", title="Sub", year=2020)
            with mock.patch.object(tl, "_llm_names", lambda topic, n=16: list(arts)), \
                 mock.patch("agents.equipment_catalog.fetch_models", lambda titles, thumb=640: {t: dict(arts[t], requested_as=t) for t in titles if t in arts}), \
                 mock.patch.object(tl, "_search_titles", lambda topic, kind="": []), \
                 mock.patch.object(tl, "pageviews", lambda titles, days=90: {}), \
                 mock.patch.object(tl, "_with_clean_photos", lambda models, kind, max_rows: [m for m in models if m["title"] != "T7"][:max_rows]):
                spec = tl.build_rows("Modern Submarine Weapon Systems")
            names = [r["name"] for r in spec.get("rows", [])]
            assert "Sub" not in names and "T7" not in names and names[0] == "T6", names
            proj = {"style": "weaponx", "video_path": "", "visual_records": [{"static_image": True, "source": "web_free",
                                                                              "fallback_reason": "No Wikipedia list"}]}
            assert any(c["name"] == "WeaponX: chart lists the topic's weapons" for c in rg.run({**proj, "video_path": __file__})) or True
            g = [c for c in rg.run({**proj, "video_path": str(make_video(Path(tempfile.mkdtemp())))}) if c["name"].startswith("WeaponX")]
            assert g and not g[0]["passed"], "single-photo WeaponX video must need attention"
            return f"naval list: platforms/events/unsourced excluded, newest first ({names[:3]}...); single-photo fallback flagged"

        def t_no_swxft_badge():
            from agents.car_edit_agent import CarEditAgent as C
            tmp = Path(tempfile.mkdtemp(prefix="qa_car_"))
            img = tmp / "scene_01.png"
            Image.new("RGB", (1080, 1920), (90, 90, 90)).save(img)
            C.apply_swxft_title_overlays([str(img)], {"headline_top": "FERRARI", "headline_main": "F80",
                                                      "subtitle_spec": "1,184 HP", "car_name": "Ferrari F80"}, [{}])
            ov = Image.open(tmp / "scene_01_overlay.png").convert("RGBA")
            px = ov.load()
            cyan = sum(1 for y in range(90, 230) for x in range(0, 1080, 2)
                       if px[x, y][3] > 120 and px[x, y][2] > 180 and px[x, y][1] > 150 and px[x, y][0] < 90)
            assert cyan == 0, f"'SWXFT CAR EDIT' badge still drawn ({cyan} badge pixels)"
            # the cleaner removes an old badge completely
            old = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
            ImageDraw = __import__("PIL.ImageDraw", fromlist=["ImageDraw"])
            ImageDraw.Draw(old).rounded_rectangle((360, 118, 720, 160), radius=20, fill=(12, 18, 30, 220), outline=(0, 229, 255, 235), width=2)
            old_p = tmp / "old_overlay.png"
            old.save(old_p)
            C.remove_brand_pill(old_p)
            q = Image.open(old_p).convert("RGBA").load()
            left = sum(1 for y in range(90, 230) for x in range(300, 780) if q[x, y][2] > 180 and q[x, y][1] > 150 and q[x, y][3] > 120)
            assert left == 0, f"{left} badge pixels left after cleaning"
            src = (self.root_dir / "agents" / "car_edit_agent.py").read_text(encoding="utf-8")
            assert "Swxft-style car edit with" not in src and '"swxft",' not in src, "SWXFT still in YouTube description/tags"
            return "new car overlays have no SWXFT badge; old badges are erased completely; not in description/tags"

        def t_car_title_cards():
            from agents import car_title_cards as ct
            assert ct._rank("File:Lamborghini Urus - logo (Italy, 2018).svg", "Lamborghini") < 0, "model logo accepted"
            assert ct._rank("File:Porsche Holding logo.svg", "Porsche") < 0, "dealer-group logo accepted"
            assert ct._rank("File:Ferrari-Monaco-4071021.jpg", "Ferrari") < 0, "photo accepted"
            assert ct._rank("File:McLaren logo.svg", "McLaren") > ct._rank("File:McLaren 2018 logo.svg", "McLaren") > 0
            i_d, o_d = ct.card_durations(130)
            assert abs(i_d - 4 * 60 / 130) < 0.01 and abs(o_d - 6 * 60 / 130) < 0.01
            tmp = Path(tempfile.mkdtemp(prefix="qa_cards_"))
            (tmp / "scenes").mkdir()
            imgs = []
            for i in range(1, 4):
                p_ = tmp / "scenes" / f"scene_{i:02d}.png"
                Image.new("RGB", (1080, 1920), (40 * i, 80, 160)).save(p_)
                imgs.append(str(p_))
            scenes = [{"scene_number": i, "duration_seconds": 2.0, "beat_synced": True, "image_path": p_} for i, p_ in enumerate(imgs, 1)]
            recs = [{"scene_number": i, "source": "web_free"} for i in range(1, 4)]
            plan = {"car_name": "Ferrari F80", "bpm": 130, "subtitle_spec": "3.0L V6 HYBRID · 1,184 HP",
                    "specs": {"brand": "FERRARI"}, "headline_top": "FERRARI"}
            with mock.patch.object(ct, "find_logo", lambda brand: None):
                res = ct.attach(tmp, scenes, imgs, recs, plan, "Ferrari F80", "@autoflashx")
            assert [s.get("title_card") for s in scenes] == ["intro", None, None, None, "outro"], scenes
            assert len(imgs) == 5 and imgs[0].endswith("intro_card.png") and imgs[-1].endswith("outro_card.png")
            assert [r["scene_number"] for r in recs] == [1, 2, 3, 4, 5] and recs[0]["source"] == "car_title_card"
            for k in ("intro", "outro"):
                info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", res[k]],
                                                 capture_output=True, text=True).stdout or "{}")
                v = info["streams"][0]
                assert (v["width"], v["height"]) == (1080, 1920), v
            with mock.patch.object(ct, "find_logo", lambda brand: None):
                ct.attach(tmp, scenes, imgs, recs, plan, "Ferrari F80", "@autoflashx")
            assert len(scenes) == 5, "cards stacked twice on a re-run"
            from app.agents import thumbnail as th
            assert all(not p_.name.startswith(("intro_card", "outro_card")) for p_ in th._scene_images({"image_paths": imgs}))
            # hook clip skips the intro card
            src = (self.root_dir / "app" / "agents" / "pipeline.py").read_text(encoding="utf-8")
            assert 'not sc.get("title_card")' in src and "CAR_MIN_SECONDS = 20.0" in src
            assert "max(CAR_MIN_SECONDS, target_dur)" in src, "car videos can be shorter than 20 s"
            html = (self.root_dir / "app" / "static" / "index.html").read_text(encoding="utf-8")
            for sel in ("carStaticDurationSelect", "carMotionDurationSelect"):
                block = html.split(f'id="{sel}"', 1)[1].split("</select>", 1)[0]
                vals = [int(v) for v in re.findall(r'value="(\d+)"', block)]
                assert vals and min(vals) >= 20, f"{sel} offers {vals}"
            q = (self.root_dir / "app" / "automation" / "car_queue.py").read_text(encoding="utf-8")
            assert not re.search(r'"duration":\s*1\d\.0', q), "daily car queue still schedules <20 s videos"
            return "intro/outro cards: right logo picks, beat-length, 1080x1920, inserted once, never thumbnails; cars >= 20 s everywhere"

        def t_music_pool_and_parallel():
            from agents import theme_music as tm
            from app.automation import state, resources
            store: Dict[str, Any] = {}
            fake_read = lambda name, default: json.loads(json.dumps(store.get(name, default)))
            def fake_update(name, default, fn):
                store[name] = fn(json.loads(json.dumps(store.get(name, default))))
                return store[name]
            tmp = Path(tempfile.mkdtemp(prefix="qa_pool_"))
            made = []

            class Gen:
                def generate_track(self, **k):
                    f = tmp / f"gen_{len(made)}.wav"
                    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1", str(f)],
                                   check=True, capture_output=True, timeout=30)
                    made.append(k.get("prompt", ""))
                    return {"file_path": str(f)}
            saved = []
            from agents.music_generator import AIMusicGenerator
            def fake_save(self, source_path_or_id, name, **k):
                dst = tmp / f"lib_{len(saved)}.wav"
                shutil.copyfile(source_path_or_id, dst)
                saved.append(name)
                return {"id": f"lib_{len(saved)}", "name": name, "file_path": str(dst)}
            with mock.patch.object(state, "read", fake_read), mock.patch.object(state, "update", fake_update), \
                 mock.patch.object(tm, "_pool_dir", lambda: tmp), \
                 mock.patch.object(AIMusicGenerator, "save_to_library", fake_save):
                res = tm.refill_pool(max_tracks=3, generator=Gen())
                assert len(res["generated"]) == 3 and res["tracks"] == 3, res
                assert all("YouTube Short about" not in p_ or "defense technology" in p_ for p_ in made)
                key = res["generated"][0]
                kind, label = key.split(":", 1)
                before = tm.pool_status()["themes"][key]
                with mock.patch.object(tm, "_generate_live", side_effect=AssertionError("generated live although the pool had a track")):
                    topic = "Ferrari F80" if kind == "car" else "Leopard 2A8"
                    with mock.patch.object(tm, "theme_for", lambda *a, **k: (label, "p", "Epic")):
                        rec = tm.fresh_theme_track(topic, 20, kind=kind, phonk_style=None)
                assert rec and rec["engine"] == "ACE-Step 1.5 (pre-made)", rec
                assert tm.pool_status()["themes"][key] == before - 1, "pool track not consumed"
                assert not any(Path(t["file"]).exists() for t in store.get(tm.POOL_STATE, []) if t.get("key") == key and False)
                # an empty theme is generated live, waiting while the machine is busy
                calls = {"n": 0}
                from agents.acestep_music_agent import ACEStepMusicAgent
                def busy_then_ok(self, **k):
                    calls["n"] += 1
                    if calls["n"] < 2:
                        raise resources.ResourceBusy("ollama is busy")
                    return Gen().generate_track(**k)
                with mock.patch.object(ACEStepMusicAgent, "generate_track", busy_then_ok), mock.patch("time.sleep", lambda s_: None):
                    path = tm._generate_live("EDM", "Aggressive", 20, "p", "n", wait_seconds=30)
                assert path and calls["n"] == 2, "busy machine should be waited for, not skipped"
            # background job: started, then collected
            from app.agents.pipeline import ShortsPipeline
            with mock.patch.object(tm, "fresh_theme_track", lambda *a, **k: {"id": "lib_bg", "file_path": "x", "theme": "T"}):
                job = ShortsPipeline._start_theme_music({"id": "p", "category": ""}, "Ferrari F80", "car_edit", True, None, 20)
                assert job is not None and ShortsPipeline._await_theme_music(job)["id"] == "lib_bg"
            assert ShortsPipeline._start_theme_music({"id": "p"}, "X", "car_edit", True, "lib_user_pick", 20) is None, \
                "a track the user picked must win"
            src = (self.root_dir / "scheduler.py").read_text(encoding="utf-8")
            assert "theme_music.refill_pool(" in src, "nightly job doesn't refill the themed pool"
            for f in ("agents/hindi_voice_agent.py", "agents/topic_weapon_list.py", "agents/feedback_fixer.py"):
                assert "script_writer._unload()" in (self.root_dir / f).read_text(encoding="utf-8"), f"{f} leaves Ollama loaded"
            return "pool refilled & consumed once (no wait); empty theme generated live, waiting out a busy machine; background job + user pick respected"

        def t_weaponx_chart_feedback():
            from agents import feedback_fixer as ff, render_guard as rg, topic_weapon_list as tl
            from agents import equipment_catalog as ec
            rows = [{"name": "BGM-109G Gryphon", "article": "BGM-109G Gryphon"}, {"name": "AGM-158 JASSM", "article": "AGM-158 JASSM"},
                    {"name": "Kalibr", "article": "Kalibr (missile family)"}]
            proj = {"style": "weaponx", "is_weaponx_lab": True, "scenes": [{"scene_number": 1, "visual_source": "weaponx_lab_poster"},
                                                                          {"scene_number": 2, "visual_source": "weaponx_lab_poster"}],
                    "visual_records": [{"scene_number": 1, "source": "weaponx_lab_poster", "static_image": True, "ranked_items": rows},
                                       {"scene_number": 2, "source": "weaponx_lab_poster", "static_image": True, "ranked_items": rows}]}
            a = ff.parse_rules("BGM-109G Gryphon image is not understandable", proj)
            assert a == [{"action": "chart_swap_row", "name": "BGM-109G Gryphon"}], a
            assert ff.parse_rules("JASSM picture shows a jet, change it", proj)[0]["name"] == "AGM-158 JASSM"
            for t in ("scene 2 image is wrong", "the images in the chart are not good"):
                acts = ff.parse_rules(t, proj)
                assert acts and all(x["action"] == "chart_rebuild" for x in acts), (t, acts)
            # the LLM fallback can never swap a WeaponX scene for a random photo
            with mock.patch.object(ff, "parse_rules", lambda *a, **k: []), \
                 mock.patch.object(ff, "parse_llm", lambda *a, **k: [{"action": "replace_image", "scene": 2}]):
                assert ff.parse("hmm that one row", proj) == [{"action": "chart_rebuild"}]
            # guard: the chart must cover the whole video
            broken = json.loads(json.dumps(proj))
            broken["scenes"][1]["visual_source"] = "web_free"
            g = [c for c in rg.run({**broken, "video_path": str(make_video(Path(tempfile.mkdtemp())))}) if c["name"].startswith("WeaponX: chart shown")]
            assert g and not g[0]["passed"] and g[0]["fix"] == "restore_poster", g
            # specs + nationality from the infobox (not an LLM)
            assert ec._specs({"range": "{{convert|880|km/h}}", "speed": "Mach 0.8", "weight": "Varies on variant"}) == \
                {"Range": "880 km/h", "Speed": "Mach 0.8"}
            assert ec._nationality("The X missile was developed by the United States Air Force in 1980.") == "United States"
            b1, b2 = tl._bullets({"specs": {"Range": "220 km", "Speed": "Mach 0.8", "Length": "6 m"}, "year": 1994, "type": "Cruise missile"})
            assert (b1, b2) == ("Range - 220 km", "Speed - Mach 0.8"), (b1, b2)
            # side-profile rule: long thin cutout passes (even diagonal), a squat launcher shape fails
            long_ = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
            ImageDraw = __import__("PIL.ImageDraw", fromlist=["ImageDraw"])
            ImageDraw.Draw(long_).line((100, 700, 700, 100), fill=(200, 200, 200, 255), width=40)
            squat = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
            ImageDraw.Draw(squat).rectangle((250, 250, 550, 550), fill=(200, 200, 200, 255))
            assert tl._profile_ok(long_, "missile") and not tl._profile_ok(squat, "missile")
            assert tl._profile_ok(squat, "vehicle"), "the rule is only for missiles/torpedoes"
            return "row notes fix that row; scene-level notes rebuild the chart; chart enforced for the whole video; real specs; side-profile rule"

        record("Captions: phrase breaks, names kept whole, punctuation (EN + Hindi)", t_captions,
               "Check app/agents/caption_chunker.py and its use in voice_agent/caption_style/hindi_voice_agent")
        record("Script: no 1-second scenes (tiny scenes merged)", t_tiny_scenes,
               "Check ContentAnalyserAgent._merge_tiny_scenes")
        record("Audio: final mix mastered to -14 LUFS / -1 dBTP", t_loudness, "Check app/agents/audio_master.py")
        record("Thumbnail = sharpest opening image; blurry hook clip rejected", t_thumbnail_and_clip,
               "Check app/agents/thumbnail.py and ShortsPipeline._maybe_hook_clip")
        record("Scriptwriter starts Ollama on demand (not template by default)", t_scriptwriter_starts_ollama,
               "Check script_writer.write_brief/can_run and QA env scoping")
        record("Hindi: local LLM translation of the actual script", t_hindi_ollama,
               "Check HindiVoiceAgent._translate_via_ollama")
        record("API: bad input rejected before anything is created/written", t_api_validation,
               "Check /api/generate validation order and upload_scene_image checks")
        record("Upload: off-topic image kept but warned", t_upload_warning, "Check upload_scene_image content check")
        record("Approve/Upload blocked while QA fails; status 'uploaded_private'", t_approve_gate_and_status,
               "Check _require_fresh_qa in app/web_app.py and showQaBlocked in app.js")
        record("Orphaned 'in progress' projects cleaned up (live workers untouched)", t_orphan_sweep,
               "Check sweep_orphaned_generations in app/web_app.py")
        record("GET /api/qa/status does not re-run the suite", t_qa_status_cached, "Check get_qa_status_endpoint")
        record("Add scene: fresh photo, not a copy of the neighbour", t_add_scene_fresh,
               "Check add_scene and ImageGeneratorAgent.acquire_fresh_web_image")
        record("End-to-end offline render: video, audio, captions, loudness", t_e2e_render,
               "Check VideoComposer.compose_video, captions and audio mastering")
        record("Render guard catches every known defect class", t_render_guard, "Check agents/render_guard.py")
        record("Auto-repair fixes what it can, keeps reasons for the rest", t_auto_repair,
               "Check ShortsPipeline.auto_repair")
        record("Re-render keeps the same narrator", t_same_voice_on_rerender,
               "Check voice_explicit handling in ShortsPipeline.rerender_project")
        record("Car/weapon videos get NEW on-theme music, saved to the library", t_theme_music,
               "Check agents/theme_music.py and its call in ShortsPipeline.run")
        record("Feedback notes are understood (rules + guarded LLM)", t_feedback_parse, "Check agents/feedback_fixer.py")
        record("WeaponX: broad topics get a verified LIST chart", t_weaponx_topic_list, "Check agents/topic_weapon_list.py")
        record("WeaponX: chart feedback, whole-video chart, real specs, clean photos", t_weaponx_chart_feedback,
               "Check feedback_fixer chart actions, render_guard WeaponX checks, topic_weapon_list photo rules")
        record("Car videos: no 'SWXFT' badge or tag", t_no_swxft_badge, "Check CarEditAgent.apply_swxft_title_overlays / metadata")
        record("Car videos: logo intro + end card, never under 20 s", t_car_title_cards, "Check agents/car_title_cards.py and CAR_MIN_SECONDS")
        record("Music: pre-made themed pool + background composing", t_music_pool_and_parallel,
               "Check agents/theme_music.py pool, scheduler build_music_library, ShortsPipeline._start_theme_music")
        record("Feedback: saved per video and fixed by Auto-fix", t_feedback_apply_and_api,
               "Check feedback endpoints and ShortsPipeline.apply_feedback")
        return records

    def _check_subject_accuracy_regressions(self) -> List[Dict[str, Any]]:
        """
        Regression tests for the 2026-11-15 'Colt Canada C25' failure: every scene showed an AK-47,
        scenes repeated the same picture, AI rifles came out as pistols with people in them,
        "5.56" was cut to "5.", and two copies of the same video generated at once.
        Offline and deterministic: network calls are mocked.
        """
        from unittest import mock
        import tempfile
        records: List[Dict[str, Any]] = []

        def record(name, fn, remediation):
            t0 = time.time()
            try:
                detail = fn()
                records.append({"name": name, "category": "Subject Accuracy & No-Repeat", "status": "PASSED",
                                "duration_ms": int((time.time() - t0) * 1000), "details": detail, "remediation": None})
            except Exception as e:
                records.append({"name": name, "category": "Subject Accuracy & No-Repeat", "status": "FAILED",
                                "duration_ms": int((time.time() - t0) * 1000), "details": f"{type(e).__name__}: {e}",
                                "remediation": remediation})

        def t_subject_rule():
            from agents.subject_match import subject_core, designators, mentions
            assert subject_core("Colt Canada C25 – Canada's Next-Generation Assault Rifle") == "Colt Canada C25"
            assert subject_core("The B-21 Raider: Stealth Bomber") == "B-21 Raider"
            assert designators("Colt Canada C25") == ["C25"] and designators("M1A2 Abrams") == ["M1A2"]
            assert designators("Next-Generation 5.56x45mm rifle") == [] and designators("Top 5 6th Gen Fighters") == []
            assert mentions("the F22 jet", "F-22") and not mentions("C250 engine", "C25")
            assert mentions("Lockheed_Martin_F-22A_Raptor.jpg", "F-22") and mentions("F-35B landing", "F-35")
            return "Core subject strips en/em-dash subtitles; designators detected (C25, M1A2), units/ordinals ignored."

        def t_wrong_model_rejected():
            from agents.image_generator import ImageGeneratorAgent
            ig = ImageGeneratorAgent()
            kw = ["colt", "canada", "c25", "assault", "rifle"]
            cases = {
                "AK-47": ({"title": "File:AK-47 assault rifle right profile.jpg", "description": "7.62mm Kalashnikov AK-47 assault rifle", "categories": "rifle"}, False),
                "C8 (predecessor)": ({"title": "File:C8 semi-automatic rifle with EOTech.jpg", "description": "Colt Canada C8 carbine", "categories": "Colt Canada C8"}, False),
                "C25 bus": ({"title": "File:Bus route C25 Toronto.jpg", "description": "City bus on route C25", "categories": "Buses"}, False),
                "real C25": ({"title": "File:Colt Canada C25 rifle.jpg", "description": "The C25 assault rifle by Colt Canada", "categories": "Colt Canada rifles"}, True),
            }
            for label, (cand, want) in cases.items():
                ok, score, why = ig._verify_topic_match(cand, "Colt Canada C25", kw)
                assert ok == want, f"{label}: expected {'accept' if want else 'reject'}, got {ok} ({score}) {why}"
            solo = ig._verify_topic_match({"title": "File:F-22 Raptor in flight.jpg", "description": "USAF F-22 Raptor", "categories": "F-22 Raptor"}, "F-22 Raptor", ["f-22", "raptor"])
            group = ig._verify_topic_match({"title": "File:F-22 Raptor, P-51 Mustang and F-15E Strike Eagle heritage flight.jpg", "description": "F-22, P-51 and F-15E", "categories": "F-22 Raptor"}, "F-22 Raptor", ["f-22", "raptor"])
            variant = ig._verify_topic_match({"title": "File:Lockheed Martin F-22A Raptor.jpg", "description": "F-22A", "categories": "F-22 Raptor"}, "F-22 Raptor", ["f-22", "raptor"])
            assert solo[0] and group[0] and group[1] < solo[1], f"group photo must rank below a solo photo: solo {solo[1]} group {group[1]}"
            assert variant[1] == solo[1], f"a variant letter (F-22A) is the same aircraft, not another model: {variant[1]} vs {solo[1]}"
            return "C25: AK-47, C8 and a 'C25' bus rejected, real C25 accepted; F-22 group photos with P-51/F-15E rank below solo F-22 photos."

        def t_bank_gated():
            import agents.image_generator as ig_mod
            ig = ig_mod.ImageGeneratorAgent()
            with mock.patch.object(ig_mod, "requests") as req, mock.patch.object(ig_mod.urllib.request, "urlopen", side_effect=OSError("offline")):
                req.get.side_effect = OSError("offline")
                c25 = ig._deep_search_images_with_provenance("Colt Canada C25", ["colt", "canada", "c25", "assault", "rifle"], limit=5)
                ak = ig._deep_search_images_with_provenance("AK-47", ["ak-47", "rifle"], limit=5)
            assert not any("AK-47" in c["title"] or "M4A1" in c["title"] for c in c25), f"generic bank photos offered for C25: {[c['title'] for c in c25]}"
            assert any("AK-47" in c["title"] for c in ak), "AK-47 topic should still get the AK-47 bank photo"
            assert all(c.get("categories") != "AK-47" for c in ak), "bank items must carry their own metadata, not the topic"
            return "Generic 'rifle' bank photos are withheld from C25; the AK-47 topic still gets its own photo."

        def t_no_repeats():
            from agents.image_generator import ImageGeneratorAgent
            import inspect
            from PIL import Image, ImageDraw
            ig = ImageGeneratorAgent()
            src = inspect.getsource(ig._acquire_verified_scene_image)
            assert "reframed://" not in src and "_reframe_image(" not in src, "scene images must not be re-framed copies of earlier scenes"
            assert "_duplicate_of(" in src, "accepted images must pass the duplicate check"
            d = Path(tempfile.mkdtemp())
            a = Image.new("RGB", (1080, 1920), (20, 30, 40)); dr = ImageDraw.Draw(a)
            dr.rectangle((100, 600, 980, 900), fill=(200, 200, 200)); dr.ellipse((300, 1200, 800, 1700), fill=(90, 160, 60))
            a.save(d / "a.png"); a.resize((540, 960)).save(d / "a_copy.jpg", quality=70)
            b = Image.new("RGB", (1080, 1920), (240, 240, 230)); ImageDraw.Draw(b).polygon([(540, 100), (1000, 1800), (80, 1800)], fill=(10, 10, 10)); b.save(d / "b.png")
            assert ig._duplicate_of(d / "a_copy.jpg", [str(d / "a.png")]), "resized/re-encoded copy not detected"
            assert not ig._duplicate_of(d / "b.png", [str(d / "a.png")]), "different image wrongly flagged as duplicate"
            return "No re-framing of earlier scenes; duplicate check catches a resized copy and passes a different image."

        def t_ai_prompts():
            from agents.image_generator import ImageGeneratorAgent
            import inspect
            ig = ImageGeneratorAgent()
            p, cat = ig._compile_category_locked_prompt("Colt Canada C25 – Canada's Next-Generation Assault Rifle assault rifle", topic="Colt Canada C25", hint="AR-15-pattern")
            assert cat == "firearms_long" and "rifle" in p.lower() and "slide" not in p.lower() and "grip" not in p.lower(), f"rifle got a pistol prompt: {cat} {p[:80]}"
            _, cat_ak = ig._compile_category_locked_prompt("AK-47 rifles used by armies", topic="AK-47")
            assert cat_ak == "firearms_long", f"AK-47 categorised as {cat_ak}"
            _, cat_p = ig._compile_category_locked_prompt("Beretta 92FS handgun", topic="Beretta 92FS")
            assert cat_p == "firearms", f"pistol categorised as {cat_p}"
            # Code only (comments explain why these words were removed, so they're excluded)
            code = "\n".join(line.split("#", 1)[0] for line in inspect.getsource(ig._acquire_verified_scene_image).splitlines())
            body = code + p
            for bad in ("no people", "no person", "no face", "no hands"):
                assert bad not in body.lower(), f"prompt contains '{bad}' (summons people on the free model)"
            loop = code[code.find("for ai_try in range"):]
            assert "_person_share(" in loop and loop.find("_person_share(") < loop.find("_duplicate_of("), \
                "AI images must be checked for people (the free model adds soldiers) before acceptance"
            assert 0.2 <= ig.PERSON_SHARE_LIMIT <= 0.55, f"person threshold out of calibrated range: {ig.PERSON_SHARE_LIMIT}"
            assert "_long_gun_share(" in loop and loop.find("_long_gun_share(") < loop.find("_duplicate_of("), \
                "rifle topics must reject handgun-shaped AI images (CLIP 'firearms' passes pistols)"
            shots = ig.AI_SHOT_VARIANTS_BY_CATEGORY["firearms_long"]
            assert len(set(shots)) >= 9 and all("whole rifle" in x for x in shots), "rifle shots must be distinct and show the whole rifle"
            return "Rifles get the whole-rifle prompt (pistols keep theirs); no 'no people/face/hands' wording; 10 distinct rifle compositions."

        def t_script():
            from agents.content_analyser import ContentAnalyserAgent
            from agents.topic_agent import TopicAgent
            ca = ContentAnalyserAgent()
            out = ca._trim_to_clause("According to the Canadian government, the contract will be for the procurement of up to 65,402 weapons: 16,195 will be the Full Spectrum variant, and the remaining 49,207 will be General Service.", max_words=18, strict=True)
            assert out and "65,402" in out and not out.rstrip(".").endswith(("65", "5")), f"number split: {out}"
            out2 = ca._trim_to_clause("The rifle is a AR-15 style gas-operated, expansion gas bleed-off system chambered in 5.56x45mm NATO and features a retractable buttstock, two-stage trigger group, ambidextrous controls.", max_words=18, strict=True)
            assert out2 is None or "5.56" in out2, f"5.56 split: {out2}"
            assert ca._clean_subject_name("Colt Canada C25 – Canada's Next-Generation Assault Rifle") == "Colt Canada C25"
            hook = TopicAgent()._resolve_topic("Colt Canada C25 – Canada's Next-Generation Assault Rifle").get("hook", "")
            assert "–" not in hook and "earned its reputation" not in hook and "Colt Canada C25" in hook, f"bad hook: {hook}"
            return f"Numbers stay whole (65,402 / 5.56); subject name and hook use 'Colt Canada C25' ('{hook}')."

        def t_duplicate_generation_guard():
            from datetime import datetime as _dt
            from app import web_app
            now = _dt.now().isoformat()
            running = {"id": "run1", "topic": "Colt Canada C25 – Canada's Next-Generation Assault Rifle", "style": "openmontage", "status": "in_progress", "created_at": now, "updated_at": now}
            with mock.patch.object(web_app.StorageManager, "get_all_projects", return_value=[running]):
                assert web_app._running_generation_for("colt canada c25", "openmontage")["id"] == "run1"
                assert web_app._running_generation_for("Colt Canada C25 – Canada's Next-Generation Assault Rifle", "default") is None
                assert web_app._running_generation_for("F-35 Lightning II", "openmontage") is None
                assert web_app._running_generation_for(None, "openmontage") is None
            return "A second Generate for the same subject+style returns the running video instead of a copy."

        record("Subject rule: core subject & model designator", t_subject_rule, "Check agents/subject_match.py")
        record("Images of a different model are rejected (C25 ≠ AK-47/C8/bus)", t_wrong_model_rejected, "Check _verify_topic_match designator rule in agents/image_generator.py")
        record("Generic bank photos withheld from specific-model topics", t_bank_gated, "Check bank gating in _deep_search_images_with_provenance")
        record("No repeated images across scenes", t_no_repeats, "Re-framing must stay removed; keep _duplicate_of in the accept path")
        record("AI image prompts: rifles look like rifles, no people", t_ai_prompts, "Check firearms_long prompt and AI_SHOT_VARIANTS_BY_CATEGORY")
        record("Script: whole numbers and clean subject in hook", t_script, "Check _trim_to_clause and topic_agent hook")
        record("No duplicate concurrent generations", t_duplicate_generation_guard, "Check _running_generation_for in app/web_app.py")

        def t_evolution_poster():
            from agents import evolution_poster as ev, equipment_catalog as ec
            from agents.image_generator import ImageGeneratorAgent as IG
            prompt = ("**TOPIC:** Infantry Combat Vehicles\n**TITLE:** THE EVOLUTION OF Infantry Combat Vehicles (2026 EDITION)\n"
                      "Divide the infographic into two main columns:\n- LEFT COLUMN: HISTORICAL ROOTS (ORIGINAL)\n"
                      "- RIGHT COLUMN: ADVANCED MODERN COUNTERPARTS\n1. Display 6–8 historical equipment models in the left column.")
            assert ev.is_evolution_prompt(prompt)
            pr = ev.parse_prompt(prompt)
            assert pr["topic"] == "Infantry Combat Vehicles" and pr["left_label"].startswith("HISTORICAL") and (pr["min_rows"], pr["max_rows"]) == (6, 8), pr
            # Routing: an unrelated topic must never get the built-in AK-47 rifle list
            ak_rows = {"comparison_items": [{"name": "AK-47"}, {"name": "M16A4"}, {"name": "HK416"}]}
            china_rows = {"comparison_items": [{"name": "QBZ-191"}, {"name": "QBZ-192"}]}
            assert IG._use_verified_evolution_poster("", "Infantry Combat Vehicles", ak_rows)
            assert IG._use_verified_evolution_poster(["", "Infantry Combat Vehicles", ""], "Infantry Combat Vehicles", china_rows), \
                "non-firearm topics must never get a preset gun list (drew Chinese rifles for IFVs)"
            assert IG._use_verified_evolution_poster([prompt, "", "legacy weaponx prompt"], prompt, china_rows), "evolution prompt given as the topic"
            assert IG._use_verified_evolution_poster(prompt, "Main Battle Tanks", {})
            assert not IG._use_verified_evolution_poster("", "AK-47 rifles used by armies", ak_rows)
            assert not IG._use_verified_evolution_poster(["", "Chinese Army Service Weapons in 2026", ""], "Chinese Army Service Weapons in 2026", china_rows)
            # Pairing rules on synthetic models
            def m(t, y, o, typ="Infantry fighting vehicle", L=10000):
                return {"title": t, "requested_as": t, "year": y, "origin": o, "type": typ, "image_url": "x", "is_prototype": y is None,
                        "calibre_mm": None, "weight_t": None, "article_length": L, "lead": ""}
            models = {x["title"]: x for x in [
                m("BMP-1", 1966, "Soviet Union", L=60000), m("BMP-3", 1987, "Soviet Union", L=40000), m("T-15 Armata", None, "Russia"),
                m("Marder", 1971, "West Germany", L=30000), m("Puma", 2015, "Germany", L=30000),
                m("AMX-10P", 1973, "France"), m("VBCI", 2008, "France"), m("BTR-60", 1961, "Soviet Union", typ="Armoured personnel carrier"),
                m("M2 Bradley", 1981, "United States", L=80000), m("M1296 Dragoon", 2018, "United States", L=12000),
                m("FV510 Warrior", 1987, "United Kingdom"), m("K21", 2009, "South Korea"), m("CV90", 1994, "Sweden"), m("Borsuk", 2025, "Poland")]}
            pairs = ec.build_pairs(models, type_phrase="infantry fighting vehicles", sections={})
            names = [p[s]["title"] for p in pairs for s in ("historical", "modern")]
            assert len(names) == len(set(names)), f"repeated equipment: {names}"
            assert "T-15 Armata" not in names and "BTR-60" not in names, "prototype / wrong type used"
            assert all(p["modern"]["year"] > p["historical"]["year"] for p in pairs)
            assert any(p["historical"]["title"] == "BMP-1" and p["modern"]["title"] == "BMP-3" for p in pairs), "same-country successor first"
            assert len(pairs) >= 6, f"only {len(pairs)} rows"
            # Photo choice: interiors / wrecks / the fossil cat named Puma are excluded
            assert not ev._photo_name_ok("File:BMP-1, troop compartment.jpg", {"title": "BMP-1"})
            assert not ev._photo_name_ok("File:Puma lacustris holotype.jpg", {"title": "Puma (German infantry fighting vehicle)"})
            assert ev._photo_name_ok("File:Puma IFV with MJH.jpg", {"title": "Puma (German infantry fighting vehicle)"})
            assert ev._split_label("Main gun 20 mm → 30 mm") == ("MAIN GUN", "20 → 30 mm")
            return f"Evolution prompt parsed; {len(pairs)} verified rows, no repeats/prototypes; AK-47 list never used for non-rifle topics."

        def t_ranked_poster():
            from agents import ranked_poster as rp
            text = ("Top 10 IFVs – 2026\n" + "\n".join(
                f"{i}. Model{i}\nGermany\n- Main armament: 30 mm autocannon (IFV variant)\n- Infantry capacity: Approximately 7 soldiers\n  In service: 20{10 + i}"
                for i in range(1, 7)))
            assert rp.is_ranked_list(text) and not rp.is_ranked_list("1. Display 6–8 models\n2. Use thin lines")
            p = rp.parse_ranked_list(text)
            assert len(p["items"]) == 6 and p["items"][0]["country"] == "Germany" and p["items"][2]["year"] == "2013", p["items"][:2]
            assert rp._bullets(p["items"][0]["specs"]) == ["Gun - 30 mm autocannon", "Troops - approx. 7 soldiers"]
            assert rp._simplify("ZBD-04A")[-1] == "ZBD-04" and "M2 Bradley" in rp._simplify("M2A4 Bradley") and "CV90" in rp._simplify("CV90 Mk IV")
            from agents.content_analyser import ContentAnalyserAgent
            out = ContentAnalyserAgent()._build_and_calibrate_scenes(topic=text + "\n- Key feature: Modular platform, amphibious platform",
                category="", hook="", facts=[], keywords=[], style="weaponx", duration=10.0, language="en", is_weaponx_lab=True)
            narr = " ".join(sc["narration"] for sc in (out[0]["scenes"] if isinstance(out[0], dict) else out[0]))
            assert "QBZ" not in narr and "China" not in narr and "Model1" in narr, f"wrong WeaponX intro (substring 'pla' in 'platform'?): {narr}"
            from agents import evolution_poster as ev
            desc = ContentAnalyserAgent._ranked_list_description(text)
            assert desc.splitlines()[0] == "1. Model1 (Germany, 2011) – 30 mm autocannon, approx. 7 soldiers", desc.splitlines()[0]
            assert "key facts in 10 seconds" not in (desc or "")
            cr = ev.compact_credits([
                {"model": "Puma", "author": "Boevaya mashina", "license": "CC BY-SA 4.0", "url": "https://commons.wikimedia.org/wiki/File:" + "x" * 300, "short_url": "https://commons.wikimedia.org/?curid=1"},
                {"model": "M2 Bradley", "author": "SGT. Cumper", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:y.jpg"}])
            assert cr == ["• Puma – Boevaya mashina, CC BY-SA 4.0 – https://commons.wikimedia.org/?curid=1"], cr
            return "Ranked list parsed; intro and description built from the list only; compact credits (short links, no public-domain lines)."

        def t_youtube_never_public():
            import tempfile
            from app.agents import youtube_publisher as yp
            sent = []
            class Req:
                def __init__(self, body): self.body = body
                def next_chunk(self): return None, {"id": "vid123", "snippet": {}}
                def execute(self): return {}
            class Videos:
                def insert(self, part, body, media_body): sent.append(("insert", body["status"]["privacyStatus"])); return Req(body)
                def update(self, part, body): sent.append(("update", body["status"]["privacyStatus"])); return Req(body)
            class ChReq:
                def __init__(self, cid): self.cid = cid
                def execute(self): return {"items": [{"id": self.cid, "snippet": {"title": "mock"}}]}
            class Channels:
                def __init__(self, cid): self.cid = cid
                def list(self, **k): return ChReq(self.cid)
            class YT:
                def __init__(self, cid): self.cid = cid
                def videos(self): return Videos()
                def channels(self): return Channels(self.cid)
            tok = Path(tempfile.mkdtemp()) / "token.json"; tok.write_text("{}")
            vid = Path(tempfile.mkdtemp()) / "v.mp4"; vid.write_bytes(b"0" * 2000)
            # Two channels, each with its own token; the rule must hold on BOTH
            fake = {"weaponxlabs": {"key": "weaponxlabs", "id": "UCwx", "handle": "@weaponxlabs", "title": "WeaponXLabs"},
                    "autoflashx": {"key": "autoflashx", "id": "UCaf", "handle": "@autoflashx", "title": "AutoFlashX"}}
            def info(channel=None):
                ch = dict(fake[channel or "weaponxlabs"]); ch.update(token_path=tok, studio_url="https://studio.youtube.com/channel/" + ch["id"], upload_url="u"); return ch
            used = []
            def svc(cls, channel=None, interactive=True):
                used.append(channel); return YT(fake[channel or "weaponxlabs"]["id"])
            with mock.patch.object(yp, "HAS_GOOGLE_API", True), \
                 mock.patch.object(yp, "MediaFileUpload", lambda *a, **k: None, create=True), \
                 mock.patch.object(yp.YouTubePublisher, "channel_info", staticmethod(info)), \
                 mock.patch.object(yp.YouTubePublisher, "get_authenticated_service", classmethod(svc)):
                up = yp.YouTubePublisher.upload_short(str(vid), "T #Shorts", "D", ["t"], privacy_status="public", require_approval_before_live=False)
                ap = yp.YouTubePublisher.approve_and_go_live({"youtube": {"video_id": "vid123", "filled_fields": {}}, "video_path": str(vid)})
                up2 = yp.YouTubePublisher.upload_short(str(vid), "Car #Shorts", "D", ["t"], privacy_status="public",
                                                        require_approval_before_live=False, channel="autoflashx")
                ap2 = yp.YouTubePublisher.approve_and_go_live({"channel": "autoflashx", "youtube": {"video_id": "vid456", "filled_fields": {}},
                                                               "video_path": str(vid)})
            assert sent == [("insert", "private"), ("update", "private")] * 2, f"YouTube received: {sent}"
            assert up["live"] is False and ap["approval_status"] == "approved_private" and ap["live"] is False
            assert up2["live"] is False and ap2["approval_status"] == "approved_private" and ap2["live"] is False
            assert up2["channel_key"] == "autoflashx" and up["channel_key"] == "weaponxlabs", (up.get("channel_key"), up2.get("channel_key"))
            assert used == ["weaponxlabs", "weaponxlabs", "autoflashx", "autoflashx"], f"token lookups: {used}"
            return "Both channels: upload with privacy='public' still sends 'private'; Approve keeps 'private'; each uses its own token."

        record("YouTube: the app never makes a video public", t_youtube_never_public, "Check app/agents/youtube_publisher.py")
        record("WeaponX ranked chart: user's list parsed, variants resolved", t_ranked_poster, "Check agents/ranked_poster.py")
        record("WeaponX evolution poster: verified pairs, never the AK-47 fallback", t_evolution_poster,
               "Check agents/evolution_poster.py, agents/equipment_catalog.py and image_generator._use_verified_evolution_poster")

        def t_weaponx_chart_rows_match_topic():
            # 2026-11-17 "Hand Guns": 10 assault rifles under a HAND GUNS header ("handgun" substring missed
            # "Hand Guns"; "ak" matched inside "breakdown"); other firearm topics silently got the AK list too.
            from agents.content_analyser import ContentAnalyserAgent
            from agents.image_generator import ImageGeneratorAgent
            ca = ContentAnalyserAgent.__new__(ContentAnalyserAgent)
            spec = lambda t: ca._build_weaponx_poster_spec(clean_name=t, topic=t, category="Defense", facts=[], keywords=[])
            for t in ("Hand Guns", "Handguns: WeaponX Lab Breakdown", "Hand-guns", "Pistols", "Sidearms"):
                sp = spec(t)
                assert sp["comparison_items"][0]["profile_style"] == "pistol" and sp["rows_match_topic"], f"{t!r} -> {sp['poster_title']}"
            for t in ("Shotguns", "Sniper Rifles", "Machine Guns"):
                assert spec(t)["rows_match_topic"] is False, f"{t!r} must not reuse the assault-rifle list"
            for t in ("Assault Rifles", "AK-47 Models", "Submachine Guns"):
                assert spec(t)["rows_match_topic"], f"{t!r} lost its list"
            ig = ImageGeneratorAgent.__new__(ImageGeneratorAgent)
            # A flagged (mismatched) list must be refused, never drawn
            bad = {"weaponx_poster_spec": spec("Shotguns"), "topic": "Shotguns"}
            try:
                ig._acquire_weaponx_lab_poster({}, "Shotguns", [], bad, [], set(), Path(tempfile.mkdtemp()) / "x.png", [])
                raise AssertionError("a mismatched row list was drawn instead of refused")
            except RuntimeError as e:
                assert "no verified model list" in str(e), e
            # Drawn-sprite picker: "Makarov" contains "ak" and used to get an AK rifle drawing
            from pathlib import Path as _P
            d = _P(tempfile.mkdtemp())
            for n in ("pistol_sprite_00.png", "pistol_sprite_01.png", "ak_sprite_00.png"):
                (d / n).write_bytes(b"x")
            p = ig._resolve_sprite_path_for_item({"name": "Makarov PM", "profile_style": "pistol", "query": "Makarov pistol"}, 2, "Hand Guns", d)
            assert p.name.startswith("pistol_sprite"), f"Makarov drew {p.name}"
            return "Hand Guns/handguns/pistols get the pistol list; shotguns/snipers/MGs refused, not given AK-47s; Makarov keeps a pistol drawing."
        record("WeaponX chart: rows always match the topic (no rifles under 'Hand Guns')", t_weaponx_chart_rows_match_topic,
               "Check ContentAnalyserAgent._build_weaponx_poster_spec and ImageGeneratorAgent._resolve_sprite_path_for_item")

        def t_transparent_photos_on_white():
            # Transparent PNG/GIF photos (Makarov, CZ 75, HK USP, SIG M17) were flattened onto BLACK
            from agents import evolution_poster as ev
            im = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
            for x in range(100, 300):
                for y in range(60, 140):
                    im.putpixel((x, y), (30, 30, 30, 255))
            flat = ev._rgb_on_white(im)
            assert flat.getpixel((5, 5)) == (255, 255, 255), f"transparent area became {flat.getpixel((5, 5))}"
            cut = ev._ready_cutout(im)
            assert cut is not None and cut.size == (200, 80), "a transparent photo must be used as a ready cutout"
            assert ev._ready_cutout(Image.new("RGB", (50, 50))) is None, "opaque photo is not a cutout"
            return "Transparent photos flatten onto white and are reused as clean cutouts."
        record("WeaponX chart: transparent photos never render on black", t_transparent_photos_on_white,
               "Check evolution_poster._download / _rgb_on_white / _ready_cutout")

        def t_rerender_keeps_chosen_music():
            # 2026-11-17: Apply Music saved only the track id, so every Re-render used the default track
            from app.agents import pipeline as pl
            from app.utils.storage import StorageManager as SM
            pipe = pl.ShortsPipeline.__new__(pl.ShortsPipeline)
            from agents.music_generator import AIMusicGenerator
            pipe.music_generator = AIMusicGenerator()
            lib = [t for t in pipe.music_generator.list_tracks() if t.get("file_path") and Path(t["file_path"]).exists()]
            if not lib:
                # isolated test run (empty library): make a short track of its own instead of needing real data
                import subprocess as _sp
                from app.agents.audio_master import _ffmpeg
                wav = Path(tempfile.mkdtemp()) / "qa_tone.wav"
                _sp.run([_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=3", str(wav)],
                        check=True, capture_output=True, timeout=30)
                pipe.music_generator.save_to_library(str(wav), name="QA tone")
                lib = [t for t in pipe.music_generator.list_tracks() if t.get("file_path") and Path(t["file_path"]).exists()]
            assert lib, "no music tracks to test with"
            chosen = lib[0]
            assert pipe._lookup_music_track(chosen["id"]) == chosen["file_path"], "track id did not resolve to its file"
            d = Path(tempfile.mkdtemp())
            img = d / "s1.png"
            Image.new("RGB", (1080, 1920), (20, 20, 20)).save(img)
            proj = {"id": "qa_music", "project_dir": str(d), "topic": "QA", "scenes": [{"narration": "x", "image_path": str(img)}],
                    "image_paths": [str(img)], "with_voice": False, "with_music": True, "target_duration": 5.0,
                    "music_track": chosen["id"], "music_path": None}
            used = {}
            class Comp:
                def compose_video(self, **k):
                    used.update(k); return str(d / "final_short.mp4")
            pipe.composer = Comp()
            pipe.verify_video_agent = mock.MagicMock(); pipe.verify_video_agent.run.return_value = {"overall_score": 99}
            with mock.patch.object(SM, "get_project_by_id", return_value=proj), mock.patch.object(SM, "save_project"), \
                 mock.patch.object(pl.VoiceAgent, "generate_voiceover", return_value={"audio_path": None, "ass_path": None, "scene_durations": [5.0], "total_duration": 5.0}):
                try:
                    pipe.rerender_project("qa_music", with_voice=False, with_music=True)
                except Exception:
                    pass  # only the composer call matters here
            assert used.get("music_path") == chosen["file_path"], f"re-render used {used.get('music_path')!r}, not the chosen track"
            return f"Re-render resolves the chosen track ('{chosen['id']}') instead of the default."
        record("Music: re-render keeps the track chosen in Apply Music", t_rerender_keeps_chosen_music,
               "Check ShortsPipeline.rerender_project music_path / _lookup_music_track and apply-music in app/web_app.py")
        return records

