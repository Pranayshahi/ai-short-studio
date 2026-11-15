import os
import random
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import config

class VisualAgent:
    @staticmethod
    def generate_scene_images(
        script_data: Dict[str, Any],
        output_dir: Path
    ) -> List[str]:
        """
        Generates 1080x1920 vertical cinematic images for each scene.
        Returns list of absolute file paths to generated scene images.
        """
        scenes_dir = output_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        image_paths = []
        scenes = script_data.get("scenes", [])

        for scene in scenes:
            scene_num = scene.get("scene_number", len(image_paths) + 1)
            prompt = scene.get("visual_prompt", "")
            img_path = scenes_dir / f"scene_{scene_num:02d}.png"

            print(f"[VisualAgent] Generating Scene {scene_num}/{len(scenes)} visual...")

            # 1. Try Pollinations (Flux model, free high quality)
            success = VisualAgent._generate_pollinations(prompt, img_path)

            # 2. Try OpenAI DALL-E 3 if API key available and Pollinations failed
            if not success and config.OPENAI_API_KEY:
                success = VisualAgent._generate_dalle(prompt, img_path)

            # 3. Fallback: Generate polished synthetic scene background if network/provider fails
            if not success or not img_path.exists():
                VisualAgent._generate_cinematic_fallback(scene, img_path)

            image_paths.append(str(img_path))

        return image_paths

    @staticmethod
    def _generate_pollinations(prompt: str, output_path: Path) -> bool:
        try:
            # Enhance prompt for vertical 9:16 defense aesthetics
            enhanced_prompt = f"{prompt}, 8k resolution, cinematic lighting, photorealistic, 9:16 vertical orientation, unreal engine 5 render, military documentary style"
            encoded = urllib.parse.quote(enhanced_prompt)
            seed = random.randint(10000, 999999)
            
            url = f"https://image.pollinations.ai/prompt/{encoded}?width={config.VIDEO_WIDTH}&height={config.VIDEO_HEIGHT}&model=flux&nologo=true&seed={seed}"
            
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200 and len(response.content) > 10000:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                
                # Verify and normalize to exact 1080x1920
                with Image.open(output_path) as img:
                    if img.size != (config.VIDEO_WIDTH, config.VIDEO_HEIGHT):
                        resized = img.resize((config.VIDEO_WIDTH, config.VIDEO_HEIGHT), Image.Resampling.LANCZOS)
                        resized.save(output_path)
                return True
        except Exception as e:
            print(f"[VisualAgent] Pollinations error: {e}")
        return False

    @staticmethod
    def _generate_dalle(prompt: str, output_path: Path) -> bool:
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
            print(f"[VisualAgent] DALL-E error: {e}")
        return False

    @staticmethod
    def _generate_cinematic_fallback(scene: Dict[str, Any], output_path: Path):
        """Generates a high-resolution dark military tech backdrop with glowing HUD elements."""
        w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
        img = Image.new("RGB", (w, h), color=(12, 16, 24))
        draw = ImageDraw.Draw(img)

        # Tactical grid lines
        for y in range(0, h, 120):
            draw.line([(0, y), (w, y)], fill=(20, 30, 45), width=1)
        for x in range(0, w, 120):
            draw.line([(x, 0), (x, h)], fill=(20, 30, 45), width=1)

        # Glowing tactical target circle in center
        cx, cy = w // 2, h // 2
        for r, col in [(280, (0, 160, 255, 80)), (240, (0, 220, 255, 120)), (180, (0, 255, 200, 160))]:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 180, 255), width=2)
        
        draw.line([cx - 320, cy, cx + 320, cy], fill=(0, 200, 255), width=2)
        draw.line([cx, cy - 320, cx, cy + 320], fill=(0, 200, 255), width=2)

        # Tactical HUD telemetry text
        scene_num = scene.get("scene_number", 1)
        draw.text((60, 140), f"[ TACTICAL RECONNAISSANCE :: SCENE {scene_num:02d} ]", fill=(0, 220, 255))
        draw.text((60, 180), "STATUS: ENGAGED // SENSOR: EO/IR // RADAR: ACTIVE", fill=(140, 170, 200))
        
        # Vignette blur
        img.save(output_path, "PNG")
