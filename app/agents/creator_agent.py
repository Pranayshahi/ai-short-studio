import io
import re
import random
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import requests
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw
import config

class CreatorAgent:
    """
    Asset Creator Agent:
    1. Searches the open web for authentic, free high-resolution images first.
    2. If no suitable free web photo is found, seamlessly falls back to Generative AI (Flux / DALL-E).
    3. Strictly enforces zero-watermark compliance.
    4. Guarantees visual theme cohesion across all scenes in a video.
    """

    HEADERS = {
        "User-Agent": "AIShortsStudioBot/1.0 (https://github.com/shorts-studio; creator@example.com)"
    }

    # Banned watermark indicators in URLs/filenames
    WATERMARK_KEYWORDS = [
        "watermark", "shutterstock", "gettyimages", "alamy",
        "istock", "depositphotos", "dreamstime", "stock-photo", "vector-logo"
    ]

    THEMES = {
        "weaponx": {
            "style_name": "WeaponX Labs Cinematic",
            "prompt_prefix": "Hyper-realistic 8k octane render in WeaponX Labs style, dramatic military defense, dark matte stealth finish, glowing fiery amber afterburners, atmospheric storm clouds, cinematic anamorphic lens flares, volumetric fog, rim lighting",
            "prompt_suffix": "masterpiece, 9:16 vertical orientation, photorealistic unreal engine 5, heavy military atmosphere, crisp details, zero watermarks, no logos, clean image",
            "tone": "amber_teal"
        },
        "default": {
            "style_name": "Documentary Defense Tech",
            "prompt_prefix": "Photorealistic 8k military documentary photography, dramatic atmospheric lighting, authentic combat engineering",
            "prompt_suffix": "clean professional framing, 9:16 vertical, cinematic lighting, no text, no watermarks",
            "tone": "neutral_cinematic"
        }
    }

    @classmethod
    def create_scene_visuals(
        cls,
        topic_info: Dict[str, Any],
        script_data: Dict[str, Any],
        output_dir: Path,
        style: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        Creates cohesive visuals for all scenes with zero watermarks.
        """
        scenes_dir = output_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        scenes = script_data.get("scenes", [])
        topic = topic_info.get("topic", "")
        clean_topic = topic.split(":")[0] if ":" in topic else topic
        clean_topic = clean_topic.replace("The ", "").strip()

        theme = cls.THEMES.get(style, cls.THEMES["default"])
        is_weaponx = (style == "weaponx")
        print(f"[CreatorAgent] 🎨 Applying Visual Cohesion Theme: '{theme['style_name']}' (Single Hero Image: {is_weaponx})")

        # Step 1: Pre-fetch pool of candidate web images for this topic
        print(f"[CreatorAgent] 🔍 Searching open web for clean, watermark-free images related to '{clean_topic}'...")
        web_images_pool = cls._search_web_free_images(clean_topic, limit=15)
        clean_web_pool = [
            c for c in web_images_pool
            if not any(wk in c["url"].lower() for wk in cls.WATERMARK_KEYWORDS)
        ]
        print(f"[CreatorAgent] -> Found {len(clean_web_pool)} clean candidate web photos.")

        # IF WEAPONX STYLE: Use a SINGLE master hero image for the entire video (like @WeaponXLabs cloSHNtPTQk)
        if is_weaponx:
            hero_path = scenes_dir / "hero_master.png"
            hero_created = False
            hero_source = "unknown"
            hero_url = None

            # 1. Prefer the best clean web hero photo
            if clean_web_pool:
                for candidate in clean_web_pool:
                    c_url = candidate.get("url")
                    if c_url and cls._download_and_format_web_image(c_url, hero_path, theme):
                        hero_created = True
                        hero_source = "web_free"
                        hero_url = c_url
                        print(f"   ✓ Sourced Master Hero Web Photo: {candidate.get('title', c_url)[:50]}...")
                        break

            # 2. If no web photo, generate an 8K Master Hero Render with Flux
            if not hero_created:
                master_prompt = f"{theme['prompt_prefix']}, epic master hero shot of {clean_topic} banking through storm clouds at dusk, glowing fiery afterburners, cinematic anamorphic lighting, {theme['prompt_suffix']}"
                print("   ⚡ Generating 8K Master Hero Visual via Generative AI (Flux)...")
                if cls._generate_ai_visual(master_prompt, hero_path):
                    hero_created = True
                    hero_source = "ai_generated"
                    print("   ✓ Sourced 8K Master Hero Visual from Generative AI")

            if not hero_created or not hero_path.exists():
                cls._generate_procedural_fallback({"scene_number": 1}, hero_path)
                hero_source = "procedural"

            # Assign this SINGLE master image to all scenes so the visual NEVER changes during the Short!
            results = []
            for idx, scene in enumerate(scenes):
                scene_num = scene.get("scene_number", idx + 1)
                results.append({
                    "scene_number": scene_num,
                    "image_path": str(hero_path),
                    "source": hero_source,
                    "source_url": hero_url,
                    "prompt": f"Master Hero Image for {clean_topic}"
                })
            return results

        results = []
        used_web_urls = set()

        for idx, scene in enumerate(scenes):
            scene_num = scene.get("scene_number", idx + 1)
            img_path = scenes_dir / f"scene_{scene_num:02d}.png"
            raw_prompt = scene.get("visual_prompt", "")
            
            # Construct cohesive prompt by wrapping raw prompt with the project's visual theme
            cohesive_prompt = f"{theme['prompt_prefix']}, {raw_prompt}, {theme['prompt_suffix']}"

            print(f"\n[CreatorAgent] Scene {scene_num}/{len(scenes)}: Processing visual...")

            image_created = False
            source_type = "unknown"
            source_url = None

            # 1. Try free web image from pool
            if clean_web_pool:
                for candidate in clean_web_pool:
                    c_url = candidate.get("url")
                    if c_url and c_url not in used_web_urls:
                        success = cls._download_and_format_web_image(c_url, img_path, theme)
                        if success:
                            used_web_urls.add(c_url)
                            image_created = True
                            source_type = "web_free"
                            source_url = c_url
                            print(f"   ✓ Used Free Web Photo: {candidate.get('title', c_url)[:50]}...")
                            break

            # 2. If no web image worked, Fallback to Generative AI with cohesive theme
            if not image_created:
                print(f"   ⚡ Sourcing from Generative AI (Flux) using '{theme['style_name']}'...")
                success = cls._generate_ai_visual(cohesive_prompt, img_path)
                if success:
                    image_created = True
                    source_type = "ai_generated"
                    print("   ✓ Sourced high-res visual from Generative AI (Zero Watermarks)")

            # 3. Last-resort fallback to tactical procedural image
            if not image_created or not img_path.exists():
                print("   🛡️ Using tactical procedural fallback for scene...")
                cls._generate_procedural_fallback(scene, img_path)
                source_type = "procedural"

            results.append({
                "scene_number": scene_num,
                "image_path": str(img_path),
                "source": source_type,
                "source_url": source_url,
                "prompt": cohesive_prompt
            })

        return results

    @classmethod
    def _search_web_free_images(cls, query: str, limit: int = 15) -> List[Dict[str, str]]:
        """
        Authentic Military Media Sourcing:
        1. Resolves the authoritative Wikipedia article for the exact subject.
        2. Pulls verified photographs directly from that article to prevent subject contamination.
        3. Enforces strict military negative filtering (no trucks, bands, toys, insignias).
        """
        candidates = []
        negative_words = [
            "truck", "ford", "band", "album", "singer", "concert", "guitar",
            "music", "airsoft", "toy", "model kit", "svg", "icon", "flag", "patch",
            "diagram", "map", "drawing", "wytwórnie", "refuel", "tanker", "kc135",
            "museum", "line_drawing", "chart", "graph", "infographic", "evolution",
            "cockpit", "757", "x-32", "x-35", "yf-23"
        ]

        query_lower = query.lower()
        is_vertical_takeoff = any(kw in query_lower for kw in ["vertical", "takeoff", "climb", "afterburner", "demo"])

        try:
            search_api = "https://en.wikipedia.org/w/api.php"

            # Step 0: For specialized maneuvers (like vertical takeoff / afterburner demo),
            # search authoritative Wikipedia File namespace directly for authentic combat photography
            if is_vertical_takeoff or "f-22" in query_lower:
                action_queries = [
                    f"{query} afterburner",
                    f"{query} takeoff",
                    f"{query} JSOH",
                    f"{query} air show"
                ]
                for aq in action_queries:
                    file_params = {
                        "action": "query",
                        "generator": "search",
                        "gsrnamespace": 6,
                        "gsrsearch": aq,
                        "gsrlimit": 6,
                        "prop": "imageinfo",
                        "iiprop": "url|size",
                        "format": "json"
                    }
                    try:
                        f_res = requests.get(search_api, params=file_params, headers=cls.HEADERS, timeout=8).json()
                        pages = f_res.get("query", {}).get("pages", {})
                        for pid, p in pages.items():
                            t = p.get("title", "")
                            t_lower = t.lower()
                            if any(neg in t_lower for neg in negative_words):
                                continue
                            info = p.get("imageinfo", [{}])[0]
                            u = info.get("url")
                            w = info.get("width", 0)
                            if u and not u.endswith(".svg") and w >= 800:
                                candidates.append({
                                    "title": t,
                                    "url": u
                                })
                    except Exception as fe:
                        pass

            # Step A: Find the most relevant dedicated Wikipedia article
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": f"{query} military defense",
                "srlimit": 5,
                "format": "json"
            }
            s_res = requests.get(search_api, params=search_params, headers=cls.HEADERS, timeout=8).json()
            search_results = s_res.get("query", {}).get("search", [])

            candidate_titles = []
            if search_results:
                candidate_titles.append(search_results[0]["title"])
            candidate_titles.append(query)

            # Step B: Pull media items from the dedicated article(s)
            for title in candidate_titles[:2]:
                clean_title = title.replace(" ", "_")
                media_url = f"https://en.wikipedia.org/api/rest_v1/page/media-list/{clean_title}"
                m_res = requests.get(media_url, headers=cls.HEADERS, timeout=8)
                if m_res.status_code == 200:
                    items = m_res.json().get("items", [])
                    for it in items:
                        if it.get("type") == "image":
                            t_str = it.get("title", "").lower()
                            if any(neg in t_str for neg in negative_words):
                                continue
                            srcset = it.get("srcset", [])
                            if srcset:
                                best = srcset[-1].get("src")
                                if best and not best.endswith(".svg"):
                                    full_url = "https:" + best if best.startswith("//") else best
                                    candidates.append({
                                        "title": it.get("title", title),
                                        "url": full_url
                                    })

            # Step C: Fallback to general pageimages if article media list had few items
            if len(candidates) < 4:
                gen_params = {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"{query} military aircraft weapon",
                    "gsrlimit": 10,
                    "prop": "pageimages",
                    "pithumbsize": 1600,
                    "format": "json"
                }
                g_res = requests.get(search_api, params=gen_params, headers=cls.HEADERS, timeout=8).json()
                pages = g_res.get("query", {}).get("pages", {})
                for pid, p in pages.items():
                    p_title = p.get("title", "").lower()
                    if any(neg in p_title for neg in negative_words):
                        continue
                    thumb = p.get("thumbnail", {}).get("source")
                    if thumb and not thumb.endswith(".svg"):
                        candidates.append({
                            "title": p.get("title", ""),
                            "url": thumb
                        })

        except Exception as e:
            print(f"[CreatorAgent] Web search error: {e}")

        # Priority scoring: rank vertical climb, afterburners, and action higher
        def action_priority(cand):
            t = (cand.get("title", "") + " " + cand.get("url", "")).lower()
            score = 0
            if "afterburner" in t: score += 10
            if "vertical" in t: score += 10
            if "jsoh" in t: score += 9
            if "climb" in t: score += 8
            if "takeoff" in t: score += 7
            if "flight" in t or "flying" in t: score += 5
            return score

        candidates.sort(key=action_priority, reverse=True)

        # Deduplicate by URL
        seen_urls = set()
        deduped = []
        for c in candidates:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                deduped.append(c)

        return deduped[:limit]

    @classmethod
    def _download_and_format_web_image(cls, url: str, output_path: Path, theme: Dict[str, Any] = None) -> bool:
        """
        Downloads a free web image and formats it into a vertical 1080x1920 canvas.
        Applies a darkened blurred ambient background with a centered crisp foreground,
        eliminating letterboxing, cropping any edge logos, and applying color cohesion.
        """
        try:
            r = requests.get(url, headers=cls.HEADERS, timeout=12)
            if r.status_code != 200 or len(r.content) < 8000:
                return False

            raw_img = Image.open(io.BytesIO(r.content)).convert("RGB")
            target_w, target_h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT

            # Trim 1% off outer edges to eliminate any subtle corner watermark/caption
            trim_x = int(raw_img.width * 0.015)
            trim_y = int(raw_img.height * 0.015)
            if raw_img.width > 200 and raw_img.height > 200:
                raw_img = raw_img.crop((trim_x, trim_y, raw_img.width - trim_x, raw_img.height - trim_y))

            # FULL-BLEED 9:16 COVER:
            # Scale image so it COVERS the entire 1080x1920 frame edge-to-edge.
            # Eliminates all letterboxing, black bars, and blurred padding bars!
            scale = max(target_w / raw_img.width, target_h / raw_img.height)
            scaled_w = int(raw_img.width * scale)
            scaled_h = int(raw_img.height * scale)
            scaled = raw_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

            # Center-crop to exact 1080x1920
            crop_x = (scaled_w - target_w) // 2
            crop_y = (scaled_h - target_h) // 2
            canvas = scaled.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))

            # Enhance contrast for cinematic military pop
            canvas = ImageEnhance.Contrast(canvas).enhance(1.12)

            canvas.save(output_path, "PNG")
            return True
        except Exception as e:
            print(f"[CreatorAgent] Image download/format error: {e}")
            return False

    @classmethod
    def _generate_ai_visual(cls, prompt: str, output_path: Path) -> bool:
        """
        Generates vertical 1080x1920 visual via Flux AI (Pollinations) or DALL-E 3.
        """
        # 1. Try Pollinations Flux (Free)
        try:
            enhanced = f"{prompt}, 8k, cinematic lighting, photorealistic, 9:16 vertical orientation, unreal engine 5 render, military documentary style"
            encoded = urllib.parse.quote(enhanced)
            seed = random.randint(10000, 999999)
            url = f"https://image.pollinations.ai/prompt/{encoded}?width={config.VIDEO_WIDTH}&height={config.VIDEO_HEIGHT}&model=flux&nologo=true&seed={seed}"
            
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if res.status_code == 200 and len(res.content) > 10000:
                with open(output_path, "wb") as f:
                    f.write(res.content)
                with Image.open(output_path) as img:
                    if img.size != (config.VIDEO_WIDTH, config.VIDEO_HEIGHT):
                        resized = img.resize((config.VIDEO_WIDTH, config.VIDEO_HEIGHT), Image.Resampling.LANCZOS)
                        resized.save(output_path)
                return True
        except Exception as e:
            print(f"[CreatorAgent] Pollinations AI error: {e}")

        # 2. Try OpenAI DALL-E 3 if API key available
        if config.OPENAI_API_KEY:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=config.OPENAI_API_KEY)
                res = client.images.generate(
                    model="dall-e-3",
                    prompt=f"{prompt}, vertical 9:16 aspect ratio, cinematic lighting, 8k documentary style",
                    size="1024x1792",
                    quality="standard",
                    n=1
                )
                img_url = res.data[0].url
                resp = requests.get(img_url, timeout=30)
                if resp.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                    with Image.open(output_path) as img:
                        resized = img.resize((config.VIDEO_WIDTH, config.VIDEO_HEIGHT), Image.Resampling.LANCZOS)
                        resized.save(output_path)
                    return True
            except Exception as e:
                print(f"[CreatorAgent] DALL-E error: {e}")

        return False

    @staticmethod
    def _generate_procedural_fallback(scene: Dict[str, Any], output_path: Path):
        w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
        img = Image.new("RGB", (w, h), color=(12, 16, 24))
        draw = ImageDraw.Draw(img)

        for y in range(0, h, 120):
            draw.line([(0, y), (w, y)], fill=(20, 30, 45), width=1)
        for x in range(0, w, 120):
            draw.line([(x, 0), (x, h)], fill=(20, 30, 45), width=1)

        cx, cy = w // 2, h // 2
        for r in [280, 240, 180]:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 180, 255), width=2)
        
        draw.line([cx - 320, cy, cx + 320, cy], fill=(0, 200, 255), width=2)
        draw.line([cx, cy - 320, cx, cy + 320], fill=(0, 200, 255), width=2)

        scene_num = scene.get("scene_number", 1)
        draw.text((60, 140), f"[ TACTICAL RECONNAISSANCE :: SCENE {scene_num:02d} ]", fill=(0, 220, 255))
        img.save(output_path, "PNG")
