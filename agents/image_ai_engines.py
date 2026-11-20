"""AI image engines for ImageGeneratorAgent (Imagen 3, FLUX/Pollinations, ComfyUI) and the vision/CLIP
checks on generated images. Split out of image_generator.py; methods are unchanged."""
from agents.image_common import (  # noqa: F401  shared imports, flags and constants
    Any, COMFYUI_API_URL, Dict, HAS_PIL, HAS_REQUESTS, Image,
    ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat, List,
    Optional, Path, Tuple, WEAPONX_EXACT_SYSTEM_PROMPT, base64, brand_words,
    config, datetime, designators, io, json, math,
    mentions, mentions_any, os, random, re, requests,
    shutil, subject_core, threading, time, urllib, uuid,
)

# free Pollinations tier: 1 image every 45 s per IP (used by _generate_with_flux1 only)
_FLUX_REQUEST_LOCK = threading.Lock()
_FLUX_LAST_REQUEST_AT = 0.0
_FLUX_MIN_GAP_SECONDS = 46.0  # free Pollinations tier: 1 image every 45 s per IP


class AIImageEngineMixin:
    def _generate_with_imagen3(
        self,
        prompt: str,
        dest_path: Path,
        style: str = "default",
        topic: str = "",
    ) -> Tuple[bool, str, str, Dict[str, Any]]:
        """
        Generates an image via Google Imagen 3 (imagen-3.0-generate-002) or Gemini Multimodal Gen
        in exact 9:16 vertical full-bleed format (1080x1920) with zero watermarks.
        """
        api_key = self._get_gemini_api_key()
        if not api_key:
            return False, "", "", {"reason": "Gemini / Imagen API key not configured"}

        compiled_prompt, category = self._compile_category_locked_prompt(prompt, topic=topic, style=style)
        print(f"[{self.AGENT_NAME}] 🌟 Generating visual via Google Imagen 3 (Category: {category})...")

        # 1. Primary: Google Imagen 3 predict endpoint
        imagen_url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_key}"
        payload_imagen = {
            "instances": [{"prompt": compiled_prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "9:16",
                "outputMimeType": "image/png"
            }
        }

        try:
            req_data = json.dumps(payload_imagen).encode("utf-8")
            req = urllib.request.Request(
                imagen_url,
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=35) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    preds = data.get("predictions", [])
                    if preds and "bytesBase64Encoded" in preds[0]:
                        raw_bytes = base64.b64decode(preds[0]["bytesBase64Encoded"])
                        ok, q_info = self._process_and_verify_raw_bytes(raw_bytes, dest_path, style=style)
                        if ok:
                            print(f"[{self.AGENT_NAME}] 🌟 Successfully generated visual using Google Imagen 3!")
                            return True, imagen_url, "Google Imagen 3 (Ultra-HD 9:16)", q_info
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return False, "", "", {"reason": f"Google Imagen API {e.code}: {e.reason}"}
        except Exception:
            pass

        # 2. Secondary: Gemini 2.5 Flash Multimodal Image Generation
        gemini_img_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={api_key}"
        payload_gemini = {
            "contents": [{"parts": [{"text": f"{compiled_prompt}, vertical 9:16 orientation, full bleed"}]}]
        }
        try:
            req_data = json.dumps(payload_gemini).encode("utf-8")
            req = urllib.request.Request(
                gemini_img_url,
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=35) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    cands = data.get("candidates", [])
                    if cands:
                        parts = cands[0].get("content", {}).get("parts", [])
                        for p in parts:
                            if "inline_data" in p:
                                raw_bytes = base64.b64decode(p["inline_data"]["data"])
                                ok, q_info = self._process_and_verify_raw_bytes(raw_bytes, dest_path, style=style)
                                if ok:
                                    print(f"[{self.AGENT_NAME}] 🌟 Successfully generated visual using Gemini Flash Image!")
                                    return True, gemini_img_url, "Gemini Flash Image (9:16)", q_info
        except Exception:
            pass

        return False, "", "", {"reason": "Imagen 3 and Gemini Image generation unavailable"}

    def _audit_image_with_vision(
        self,
        img_path: Path,
        target_subject: str,
        target_prompt: str = "",
    ) -> Dict[str, Any]:
        """
        Closed-loop visual verification via Gemini Multimodal Vision API.
        Verifies that the generated image genuinely depicts target_subject,
        catching semantic drift (e.g. gun rendered as an airplane or street).
        """
        api_key = self._get_gemini_api_key()
        img_path = Path(img_path)
        if not img_path.exists():
            return {"passed": False, "score": 0, "reason": "Image file does not exist"}

        if not api_key:
            return self._verify_image_content(img_path, target_subject)
        try:
            raw_bytes = img_path.read_bytes()
            b64_img = base64.b64encode(raw_bytes).decode("ascii")
            clean_subj = re.sub(r'[\U00010000-\U0010ffff]|[\u2600-\u27ff]', '', target_subject).split('|')[0].strip()

            audit_prompt = (
                f"You are an expert visual QA director for documentary YouTube Shorts.\n"
                f"Strictly evaluate if this image accurately and authentically depicts: '{clean_subj}'.\n"
                f"Context prompt: '{target_prompt[:120]}'.\n\n"
                f"Return JSON ONLY with this schema:\n"
                f'{{"score": <integer 0-100>, "detected_subject": "<short description>", "is_topic_match": <true or false>, "critique": "<one brief sentence>"}}'
            )

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": audit_prompt},
                        {"inline_data": {"mime_type": "image/png", "data": b64_img}}
                    ]
                }]
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    json_match = re.search(r"\{.*\}", text, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group(0))
                        score = int(parsed.get("score", 75))
                        is_match = bool(parsed.get("is_topic_match", True))
                        detected = parsed.get("detected_subject", clean_subj)
                        critique = parsed.get("critique", "Subject verified")
                        passed = is_match and (score >= 65)
                        return {
                            "passed": passed,
                            "score": score,
                            "detected_subject": detected,
                            "critique": critique,
                            "checker": "gemini-vision",
                        }
        except Exception:
            pass

        # Gemini unavailable (e.g. HTTP 402): use the free local CLIP check instead of assuming a pass
        return self._verify_image_content(img_path, target_subject)

    def _verify_image_content(self, img_path: Path, target_subject: str, lenient: bool = False) -> Dict[str, Any]:
        """Local CLIP zero-shot check. Returns passed=None (UNVERIFIED) if CLIP isn't installed.
        lenient=True for real photos already matched by metadata (reject only clear mismatches)."""
        _, category = self._compile_category_locked_prompt("", topic=target_subject)
        try:
            from agents import image_verifier
            res = image_verifier.verify(img_path, category, lenient=lenient)
        except Exception as e:
            res = {"available": False, "passed": None, "reason": f"verifier error: {e}"}
        if not res.get("available"):
            return {
                "passed": None,
                "score": None,
                "verified": False,
                "checker": "none",
                "reason": f"UNVERIFIED: {res.get('reason', 'no content checker available')}",
            }
        res["checker"] = "clip-local"
        res["verified"] = True
        res["detected_subject"] = res.get("best_label")
        res["reason"] = f"CLIP: target {res.get('score')}%, top decoy '{res.get('top_decoy')}' {round((res.get('top_decoy_share') or 0)*100)}%"
        return res

    def _reframe_image(self, src: Path, dest: Path, variant: int = 1) -> bool:
        """Creates a distinct 9:16 framing (zoom + offset) of an already verified photo."""
        try:
            from PIL import Image
            img = Image.open(src).convert("RGB")
            w, h = img.size
            zoom = 1.18 + 0.06 * (variant % 3)
            cw, ch = int(w / zoom), int(h / zoom)
            offsets = [(0.5, 0.5), (0.3, 0.45), (0.7, 0.55), (0.5, 0.3), (0.5, 0.7)]
            fx, fy = offsets[variant % len(offsets)]
            left = int((w - cw) * fx)
            top = int((h - ch) * fy)
            img.crop((left, top, left + cw, top + ch)).resize((w, h), Image.LANCZOS).save(dest, "PNG")
            return True
        except Exception as e:
            print(f"[{self.AGENT_NAME}] Re-frame failed: {e}")
            return False

    def _generate_with_flux1(
        self,
        prompt: str,
        dest_path: Path,
        style: str = "default",
    ) -> Tuple[bool, str, str, Dict[str, Any]]:
        """
        Generates an image via FLUX.1 (Black Forest Labs via Pollinations AI)
        in 9:16 vertical full-bleed format (1080x1920) with zero watermarks.
        """
        seed = random.randint(1000, 999999)
        clean_p = self._sanitize_prompt_for_ai_engine(prompt)
        global _FLUX_LAST_REQUEST_AT

        # Place unique variation near the front to guarantee edge CDN / cache distinctness
        enhanced_prompt = (
            f"{clean_p}, angle {seed % 1000}, vertical 9:16 portrait composition, cinematic lighting, sharp focus, "
            f"clean background, no borders, no text, no watermarks, no logos"
        )
        encoded_prompt = urllib.parse.quote(enhanced_prompt)

        # High-availability endpoints (without custom width/height or model params that trigger paywall)
        endpoints = [
            f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true",
            f"https://image.pollinations.ai/prompt/{encoded_prompt}",
        ]

        last_error = "Unknown error"
        # The free FLUX endpoint rate-limits bursts (HTTP 402/429). Space requests out and
        # retry with back-off, otherwise a 2nd generation a few seconds after the 1st fails.
        retry_waits = [0, 6, 12]
        for attempt, extra_wait in enumerate(retry_waits):
            if extra_wait:
                print(f"[{self.AGENT_NAME}] ⏳ FLUX.1 rate-limited ({last_error}). Retry {attempt}/{len(retry_waits) - 1} in {extra_wait}s...")
                time.sleep(extra_wait)
            for p_url in endpoints:
                with _FLUX_REQUEST_LOCK:
                    gap = time.time() - _FLUX_LAST_REQUEST_AT
                    if gap < _FLUX_MIN_GAP_SECONDS:
                        time.sleep(_FLUX_MIN_GAP_SECONDS - gap)
                    try:
                        ok, q_info = self._download_and_verify_pixels(p_url, dest_path, style=style)
                    except Exception as e:
                        ok, q_info = False, {"reason": str(e)}
                    _FLUX_LAST_REQUEST_AT = time.time()
                if ok:
                    print(f"[{self.AGENT_NAME}] ⚡ Successfully generated visual using FLUX.1 (Black Forest Labs)!")
                    return True, p_url, "FLUX.1 (Black Forest Labs)", q_info
                last_error = q_info.get("reason", "Verification rejected")
            rate_limited = any(code in last_error for code in ("402", "429", "503", "timed out"))
            if not rate_limited:
                break

        return False, "", "", {"reason": f"FLUX.1 generation failed: {last_error}"}

    def _generate_with_comfyui(
        self,
        prompt: str,
        dest_path: Path,
        style: str = "default",
    ) -> Tuple[bool, str, str, Dict[str, Any]]:
        """
        Generates an image via local or remote ComfyUI API (default: http://127.0.0.1:8188).
        Validates server availability, discovers available checkpoint, submits workflow graph,
        polls history, and downloads the generated image.
        """
        comfy_url = getattr(self, "comfyui_url", None) or os.getenv("COMFYUI_API_URL", "http://127.0.0.1:8188").rstrip("/")

        # 1. Quick probe to verify ComfyUI is up and responsive (timeout 2.5s)
        try:
            if HAS_REQUESTS:
                probe = requests.get(f"{comfy_url}/system_stats", timeout=2.5)
                is_up = (probe.status_code == 200)
            else:
                req = urllib.request.Request(f"{comfy_url}/system_stats")
                with urllib.request.urlopen(req, timeout=2.5) as r:
                    is_up = (r.status == 200)
            if not is_up:
                return False, "", "", {"reason": f"ComfyUI server at {comfy_url} returned non-200 status"}
        except Exception as e:
            return False, "", "", {"reason": f"ComfyUI server offline at {comfy_url} ({e})"}

        # 2. Checkpoint discovery
        ckpt_name = "v1-5-pruned-emaonly.ckpt"
        try:
            if HAS_REQUESTS:
                info_resp = requests.get(f"{comfy_url}/object_info/CheckpointLoaderSimple", timeout=3.0)
                if info_resp.status_code == 200:
                    data = info_resp.json()
                    ckpts = data.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
                    if ckpts and len(ckpts) > 0:
                        ckpt_name = ckpts[0]
            else:
                req = urllib.request.Request(f"{comfy_url}/object_info/CheckpointLoaderSimple")
                with urllib.request.urlopen(req, timeout=3.0) as r:
                    data = json.loads(r.read().decode("utf-8"))
                    ckpts = data.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
                    if ckpts and len(ckpts) > 0:
                        ckpt_name = ckpts[0]
        except Exception:
            pass

        client_id = str(uuid.uuid4())
        seed = random.randint(1, 999999999999)

        # 9:16 portrait txt2img workflow graph
        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": 7.0,
                    "denoise": 1.0,
                    "latent_image": ["5", 0],
                    "model": ["4", 0],
                    "negative": ["7", 0],
                    "positive": ["6", 0],
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "seed": seed,
                    "steps": 20
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": ckpt_name
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "batch_size": 1,
                    "height": 1024,
                    "width": 576
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["4", 1],
                    "text": f"{prompt}, 9:16 vertical portrait composition, full-bleed vertical short format, 8k resolution, photorealistic cinematic lighting, sharp focus, highly detailed, no borders, no watermarks"
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["4", 1],
                    "text": "watermark, text, borders, blurry, ugly, distorted, low quality"
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "ai_shorts",
                    "images": ["8", 0]
                }
            }
        }

        # 3. Submit workflow to ComfyUI
        prompt_id = None
        try:
            submit_payload = {"prompt": workflow, "client_id": client_id}
            if HAS_REQUESTS:
                resp = requests.post(f"{comfy_url}/prompt", json=submit_payload, timeout=10)
                if resp.status_code == 200:
                    prompt_id = resp.json().get("prompt_id")
            else:
                p_data = json.dumps(submit_payload).encode("utf-8")
                req = urllib.request.Request(f"{comfy_url}/prompt", data=p_data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    prompt_id = json.loads(r.read().decode("utf-8")).get("prompt_id")
        except Exception as e:
            return False, "", "", {"reason": f"ComfyUI prompt submission failed: {e}"}

        if not prompt_id:
            return False, "", "", {"reason": "ComfyUI did not return a valid prompt_id"}

        # 4. Poll history until complete (up to 40 seconds)
        poll_start = time.time()
        out_image_info = None
        while time.time() - poll_start < 40:
            time.sleep(1.2)
            try:
                if HAS_REQUESTS:
                    h_resp = requests.get(f"{comfy_url}/history/{prompt_id}", timeout=5)
                    if h_resp.status_code == 200:
                        h_data = h_resp.json()
                else:
                    req = urllib.request.Request(f"{comfy_url}/history/{prompt_id}")
                    with urllib.request.urlopen(req, timeout=5) as r:
                        h_data = json.loads(r.read().decode("utf-8"))

                if prompt_id in h_data:
                    outputs = h_data[prompt_id].get("outputs", {})
                    for node_id, node_out in outputs.items():
                        images = node_out.get("images", [])
                        if images:
                            out_image_info = images[0]
                            break
                    if out_image_info:
                        break
            except Exception:
                pass

        if not out_image_info:
            return False, "", "", {"reason": f"ComfyUI timed out generating image for prompt_id {prompt_id}"}

        # 5. Download rendered image from ComfyUI /view endpoint
        fname = out_image_info.get("filename")
        subfolder = out_image_info.get("subfolder", "")
        f_type = out_image_info.get("type", "output")
        view_url = f"{comfy_url}/view?filename={urllib.parse.quote(fname)}&subfolder={urllib.parse.quote(subfolder)}&type={urllib.parse.quote(f_type)}"

        try:
            if HAS_REQUESTS:
                img_res = requests.get(view_url, timeout=15)
                raw_bytes = img_res.content if img_res.status_code == 200 else b""
            else:
                with urllib.request.urlopen(view_url, timeout=15) as r:
                    raw_bytes = r.read()

            if len(raw_bytes) < 8000:
                return False, "", "", {"reason": "ComfyUI image payload too small (<8KB)"}

            ok, q_info = self._process_and_verify_raw_bytes(raw_bytes, dest_path, style=style)
            if ok:
                print(f"[{self.AGENT_NAME}] 🎨 Successfully generated visual using ComfyUI ({comfy_url})!")
                return True, view_url, f"ComfyUI ({ckpt_name})", q_info
            return False, "", "", q_info
        except Exception as e:
            return False, "", "", {"reason": f"ComfyUI image fetch error: {e}"}

    def _generate_and_verify_ai_image(
        self,
        prompt: str,
        dest_path: Path,
        style: str = "default",
        engine: str = "auto",
        topic: str = "",
    ) -> Tuple[bool, str, str, Dict[str, Any]]:
        """
        Generates a topic-locked image via selected engine or automated fallback:
        1. Google Imagen 3 / Gemini Image (if key configured)
        2. FLUX.1 (Black Forest Labs)
        3. ComfyUI (Local: 127.0.0.1:8188)
        4. OpenAI DALL-E 3 (if key configured)
        Includes closed-loop Gemini Vision QA to detect and correct semantic drift.
        """
        eng = (engine or self.engine or "auto").lower().strip()

        # Helper to execute Vision QA check if image generated
        def _post_verify(success: bool, url: str, prov: str, info: Dict[str, Any], used_prompt: str) -> Tuple[bool, str, str, Dict[str, Any]]:
            if not success or not dest_path.exists():
                return success, url, prov, info

            target_subj = topic or prompt[:40]
            v_res = self._audit_image_with_vision(dest_path, target_subject=target_subj, target_prompt=used_prompt)
            info["vision_qa"] = v_res

            if v_res.get("passed") is False:
                critique = v_res.get("critique", "Subject mismatch")
                detected = v_res.get("detected_subject", "unknown")
                print(f"[{self.AGENT_NAME}] ⚠️ Vision QA rejected visual: {critique} (Detected: '{detected}' instead of '{target_subj}').")
                print(f"[{self.AGENT_NAME}] 🔄 Executing closed-loop retry with intensified category prompt...")

                # Intensify prompt focusing strictly on subject
                intensified_p, _ = self._compile_category_locked_prompt(
                    f"Macro authentic studio showcase of {target_subj}, clean view, no extraneous objects",
                    topic=target_subj,
                    style=style
                )

                retry_ok = False
                retry_info = {}
                if "Imagen" in prov:
                    retry_ok, _, _, retry_info = self._generate_with_imagen3(intensified_p, dest_path, style=style, topic=target_subj)
                elif "FLUX" in prov:
                    retry_ok, _, _, retry_info = self._generate_with_flux1(intensified_p, dest_path, style=style)

                if retry_ok:
                    retry_v = self._audit_image_with_vision(dest_path, target_subject=target_subj, target_prompt=intensified_p)
                    info["vision_qa_retry"] = retry_v
                    if retry_v.get("passed") is not False:
                        info["vision_qa"] = retry_v
                        print(f"[{self.AGENT_NAME}] ✓ Closed-loop retry visual approved by Vision QA!")
                        return True, url, f"{prov} (Vision Verified)", info

                # Still wrong after the retry: discard it rather than ship a hallucinated image
                try:
                    dest_path.unlink()
                except OSError:
                    pass
                info["reason"] = f"Rejected by content check: {critique}"
                return False, "", "", info

            return success, url, prov, info

        # Direct selection: Google Imagen 3
        if eng in ("imagen3", "imagen", "google"):
            print(f"[{self.AGENT_NAME}] 🌟 Using requested engine: Google Imagen 3...")
            ok_i, i_url, i_prov, i_info = self._generate_with_imagen3(prompt, dest_path, style=style, topic=topic)
            if ok_i:
                return _post_verify(True, i_url, i_prov, i_info, prompt)
            print(f"[{self.AGENT_NAME}] ⚠️ Imagen 3 unavailable ({i_info.get('reason')}). Falling back to FLUX.1...")
            ok_f, f_url, f_prov, f_info = self._generate_with_flux1(prompt, dest_path, style=style)
            if ok_f:
                return _post_verify(True, f_url, f_prov, f_info, prompt)
            return False, "", "", i_info

        # Direct selection: FLUX.1
        if eng in ("flux", "flux.1", "flux1"):
            print(f"[{self.AGENT_NAME}] ⚡ Using requested engine: FLUX.1...")
            ok_f, f_url, f_prov, f_info = self._generate_with_flux1(prompt, dest_path, style=style)
            if ok_f:
                return _post_verify(True, f_url, f_prov, f_info, prompt)
            print(f"[{self.AGENT_NAME}] ⚠️ FLUX.1 failed ({f_info.get('reason')}). Falling back to ComfyUI...")
            ok_c, c_url, c_prov, c_info = self._generate_with_comfyui(prompt, dest_path, style=style)
            if ok_c:
                return _post_verify(True, c_url, c_prov, c_info, prompt)
            return False, "", "", f_info

        # Direct selection: ComfyUI
        if eng in ("comfyui", "comfy"):
            print(f"[{self.AGENT_NAME}] 🎨 Using requested engine: ComfyUI...")
            ok_c, c_url, c_prov, c_info = self._generate_with_comfyui(prompt, dest_path, style=style)
            if ok_c:
                return _post_verify(True, c_url, c_prov, c_info, prompt)
            print(f"[{self.AGENT_NAME}] ℹ️ Local ComfyUI offline ({c_info.get('reason')}). Falling back to FLUX.1...")
            ok_f, f_url, f_prov, f_info = self._generate_with_flux1(prompt, dest_path, style=style)
            if ok_f:
                return _post_verify(True, f_url, "FLUX.1 (ComfyUI offline fallback)", f_info, prompt)
            return False, "", "", c_info

        # --- Automated Smart Fallback Mode: Imagen 3 -> FLUX.1 -> ComfyUI -> DALL-E 3 ---
        gemini_k = self._get_gemini_api_key()
        if gemini_k:
            print(f"[{self.AGENT_NAME}] 🌟 [Step 1/4] Attempting visual synthesis via Google Imagen 3...")
            ok_i, i_url, i_provider, i_info = self._generate_with_imagen3(prompt, dest_path, style=style, topic=topic)
            if ok_i:
                return _post_verify(True, i_url, i_provider, i_info, prompt)
            print(f"[{self.AGENT_NAME}] ℹ️ Imagen 3 skipped/unavailable ({i_info.get('reason')}). Next fallback: FLUX.1...")

        print(f"[{self.AGENT_NAME}] ⚡ [Step 2/4] Generating visual via FLUX.1 (Black Forest Labs)...")
        ok_f, f_url, f_provider, f_info = self._generate_with_flux1(prompt, dest_path, style=style)
        if ok_f:
            return _post_verify(True, f_url, f_provider, f_info, prompt)
        print(f"[{self.AGENT_NAME}] ⚠️ FLUX.1 unavailable ({f_info.get('reason')}). Falling back to ComfyUI...")

        print(f"[{self.AGENT_NAME}] 🎨 [Step 3/4] Generating visual via ComfyUI (127.0.0.1:8188)...")
        ok_c, c_url, c_provider, c_info = self._generate_with_comfyui(prompt, dest_path, style=style)
        if ok_c:
            return _post_verify(True, c_url, c_provider, c_info, prompt)

        # Optional DALL-E 3 fallback
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            print(f"[{self.AGENT_NAME}] ✨ [Step 4/4] Attempting fallback via OpenAI DALL-E 3...")
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                res = client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size="1024x1792",
                    quality="standard",
                    n=1,
                )
                dalle_url = res.data[0].url
                ok_d, q_d = self._download_and_verify_pixels(dalle_url, dest_path, style=style)
                if ok_d:
                    return _post_verify(True, dalle_url, "OpenAI DALL-E 3", q_d, prompt)
            except Exception:
                pass

        return False, "", "", {
            "reason": (
                "All AI image engines failed — "
                f"FLUX.1: {f_info.get('reason', 'unavailable')}; "
                f"ComfyUI: {c_info.get('reason', 'unavailable')}"
            )
        }

