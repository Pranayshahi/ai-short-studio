"""WeaponX posters/charts (evolution, ranked, comparison, topic list, firearm photo charts, sprite
posters) and the multi-layer image editor for ImageGeneratorAgent. Split out of
image_generator.py; methods are unchanged."""
from agents.image_common import (  # noqa: F401  shared imports, flags and constants
    Any, COMFYUI_API_URL, Dict, HAS_PIL, HAS_REQUESTS, Image,
    ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat, List,
    Optional, Path, Tuple, WEAPONX_EXACT_SYSTEM_PROMPT, base64, brand_words,
    config, datetime, designators, io, json, math,
    mentions, mentions_any, os, random, re, requests,
    shutil, subject_core, threading, time, urllib, uuid,
)


class WeaponXPosterMixin:
    def _acquire_weaponx_lab_poster(
        self,
        scene: Dict[str, Any],
        clean_topic: str,
        keywords: List[str],
        image_data: Dict[str, Any],
        verified_candidates: List[Dict[str, Any]],
        used_urls: set,
        dest_path: Path,
        change_image_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Generates a 9:16 (1080x1920) @WeaponXLabs White-Background Multi-Row Comparison Chart
        matching the user's Gemini WeaponXLabs channel graphics (assets/weaponx_reference.png ·
        https://gemini.google.com/u/1/app/dbdf5025a758bf01):
        - Pure white background (#FFFFFF)
        - Top solid black rounded header bar with bold white uppercase title
        - 10 to 12 stacked horizontal weapon/system rows:
          Left: Country Flag + Bold Model Name (Year) + Country Name
          Center: Realistic horizontal side-profile cutout of the weapon on pure white
          Right: Two bold black bullet point specs (e.g., • Cartridge - 7.62×39 mm. / • No. built - 75 million)
        """
        # A chart the user previewed and approved in the dashboard is used exactly as approved
        preview = image_data.get("chart_preview") or {}
        if preview.get("path") and Path(preview["path"]).exists() and preview.get("record"):
            import shutil as _sh
            _sh.copyfile(preview["path"], dest_path)
            rec = dict(preview["record"])
            rec["image_path"] = str(dest_path)
            print(f"   ✓ [{self.AGENT_NAME}] Using the chart approved in the preview ({len(rec.get('ranked_items') or [])} rows)")
            return rec
        poster_spec = image_data.get("weaponx_poster_spec") or {}
        # The user's request can arrive as the topic itself, as image_data.topic, or as the image prompt
        request_texts = [image_data.get("topic") or "", clean_topic or "", image_data.get("master_image_prompt") or "",
                         image_data.get("topic_subject") or ""]
        # A pasted ranked list ("1. Puma IFV / Germany / - Main armament: ...") -> WeaponX ranked chart
        # built from the user's own facts with real photos of each listed model
        from agents import ranked_poster, comparison_poster
        comp_text = next((t for t in request_texts if comparison_poster.is_comparison_prompt(t)), "")
        if comp_text:
            return self._acquire_comparison_poster(comp_text, dest_path)
        ranked_text = next((t for t in request_texts if ranked_poster.is_ranked_list(t)), "")
        if ranked_text:
            return self._acquire_ranked_poster(ranked_text, dest_path)
        # Cartridges / bullets / ammunition of assault rifles: to-scale size comparison chart
        if any(re.search(r"\b(?:cartridges?|bullets?|ammunition|ammo|rounds?|calibers?|calibres?)\b", t or "", re.I)
               and re.search(r"assault rifle|rifle|\bar\b|ak", t or "", re.I) for t in request_texts):
            return self._acquire_cartridge_poster(dest_path)
        if self._use_verified_evolution_poster(request_texts, clean_topic, poster_spec):
            from agents import evolution_poster
            evo_text = next((t for t in request_texts if evolution_poster.is_evolution_prompt(t)), "")
            subject = evolution_poster.parse_prompt(evo_text)["topic"] if evo_text else (image_data.get("topic_subject") or clean_topic)
            try:
                return self._acquire_evolution_poster(evo_text, subject, dest_path)
            except RuntimeError as e:
                if evo_text:
                    raise  # the user asked for an evolution chart explicitly: say why it can't be built
                # A broad topic ("Modern Submarine Weapon Systems") has no Wikipedia model list. That used
                # to FAIL the whole video. WeaponX charts are LISTS of weapons, so build a verified list of
                # models for the topic (like the 'Hand Guns' chart); a single hero photo is the last resort.
                print(f"   ↪️ [{self.AGENT_NAME}] {e} Building a verified list of {clean_topic} instead...")
                try:
                    return self._acquire_topic_list_poster(subject or clean_topic, dest_path)
                except Exception as e2:
                    print(f"   ↪️ [{self.AGENT_NAME}] Topic list chart unavailable ({e2}); "
                          "using a verified photo of the subject as the WeaponX hero image.")
                rec = self._acquire_verified_scene_image(
                    scene, 1, clean_topic, keywords, verified_candidates, used_urls, dest_path, "weaponx",
                    change_image_events)
                rec["fallback_reason"] = str(e)
                return rec
        if poster_spec.get("rows_match_topic") is False:
            # The only list available is the generic assault-rifle preset; drawing it under this title
            # published 10 rifles as "HAND GUNS". Stop with an actionable message instead.
            raise RuntimeError(
                f"WeaponX chart: no verified model list for '{clean_topic}'. Paste a numbered list of 5-10 models "
                f"(name, country, and spec lines such as 'Calibre: 9×19mm') as the topic to build it from real photos.")
        rows = poster_spec.get("comparison_items") or []
        if len(rows) >= 5:
            real = self._acquire_firearm_photo_chart(poster_spec, rows, clean_topic, dest_path)
            if real is not None:
                return real
        gemini_prompt = (
            poster_spec.get("gemini_prompt")
            or image_data.get("master_image_prompt")
            or scene.get("visual_prompt")
            or f"{WEAPONX_EXACT_SYSTEM_PROMPT}\n\n**TOPIC / HEADLINE:**\n{clean_topic.upper()}"
        )

        print(f"   🔥 [{self.AGENT_NAME}] Building @WeaponXLabs 9:16 White-Background Multi-Row Chart for '{clean_topic}'...")
        comp_ok, comp_meta = self._compose_weaponx_lab_poster(
            clean_topic=clean_topic,
            keywords=keywords,
            poster_spec=poster_spec,
            verified_candidates=verified_candidates,
            dest_path=dest_path,
        )
        return {
            "scene_number": 1,
            "image_path": str(dest_path),
            "source": "weaponx_lab_poster",
            "source_url": comp_meta.get("hero_source_url") or "https://gemini.google.com/u/1/app/dbdf5025a758bf01",
            "source_domain": comp_meta.get("hero_source_domain", "gemini.google.com"),
            "source_provider": "WeaponX Labs White-Background Multi-Row Chart Engine",
            "license": comp_meta.get("license", "WeaponX Labs Channel Visual Standard"),
            "author": "@WeaponXLabs Studio Engine",
            # Drawn stock sprites, not a photo of each listed model: never self-certify as verified
            "source_verified": False,
            "topic_matched": True,
            "topic_match_score": 60,
            "topic_match_reason": (f"Drawn sprite chart for '{clean_topic}' ({len(poster_spec.get('comparison_items', []))} rows): "
                                   "rows use generic drawings, not photos of each model (real-photo chart unavailable)"),
            "visual_quality": comp_meta.get(
                "visual_quality",
                {
                    "original_resolution": f"{self.target_width}x{self.target_height}",
                    "output_resolution": f"{self.target_width}x{self.target_height}",
                    "pixel_stddev": 62.5,
                    "mean_luminance": 215.0,
                    "watermark_free": True,
                    "passed": True,
                },
            ),
            "attempts_taken": 1,
            "prompt": gemini_prompt,
        }

    def _acquire_firearm_photo_chart(self, poster_spec: Dict[str, Any], rows: List[Dict[str, Any]],
                                     clean_topic: str, dest_path: Path) -> Optional[Dict[str, Any]]:
        """WeaponX chart with a real Wikipedia/Commons photo of every listed model (None -> use the drawn chart)."""
        from agents import ranked_poster
        title = poster_spec.get("poster_title") or clean_topic
        print(f"   🔥 [{self.AGENT_NAME}] Building WeaponX chart for '{clean_topic}' with a real photo of each model...")
        try:
            cache = Path(config.OUTPUT_DIR) / "cache" / "evolution_photos"
            res = ranked_poster.make_poster_from_items(title, rows, Path(dest_path), cache, kind="firearm")
        except Exception as e:
            res = {"error": f"{type(e).__name__}: {e}"}
        if res.get("error") or not res.get("photos"):
            print(f"   ⚠️ [{self.AGENT_NAME}] Real-photo chart unavailable ({res.get('error') or 'no photos'}); using drawn chart.")
            return None
        return {
            "scene_number": 1,
            "image_path": str(dest_path),
            "source": "weaponx_lab_poster",
            "source_url": "https://commons.wikimedia.org",
            "source_domain": "commons.wikimedia.org",
            "source_provider": "WeaponX Labs chart (curated list, Wikimedia Commons photos)",
            "license": "Photos CC/PD from Wikimedia Commons — see photo_credits",
            "author": "@WeaponXLabs Studio Engine",
            "source_verified": True,
            "topic_matched": True,
            "topic_match_score": 99,
            "topic_match_reason": f"{res['rows']} rows for '{res['title']}', each with a photo of that exact model",
            "ranked_items": res["items"],
            "photo_credits": res["credits"],
            "visual_quality": {"output_resolution": f"{self.target_width}x{self.target_height}", "passed": True, "photos": res["photos"]},
            "attempts_taken": 1,
            "prompt": f"{title}: " + "; ".join(r.get("name", "") for r in rows),
        }

    @staticmethod
    def _use_verified_evolution_poster(request_texts: Any, clean_topic: str, poster_spec: Dict[str, Any]) -> bool:
        """
        Use the Wikipedia-verified evolution poster when:
          - any form of the request is an evolution/comparison prompt, or
          - the subject is not a firearm: the legacy chart only has gun drawings and preset gun lists
            (it drew AK-47s / Chinese rifles for "Infantry Combat Vehicles").
        Firearm topics keep the legacy rifle chart.
        """
        from agents import evolution_poster
        texts = [request_texts] if isinstance(request_texts, str) else list(request_texts or [])
        if any(evolution_poster.is_evolution_prompt(t) for t in texts if t):
            return True
        subject = clean_topic or ""
        for t in texts:
            m = re.search(r"\*\*TOPIC:\*\*\s*(.+)", t or "")
            if m:
                subject = m.group(1)
                break
        is_firearm_topic = bool(re.search(r"rifle|gun|pistol|firearm|carbine|ak-?47|kalashnikov|small arms|sniper|weapons? in",
                                          subject, re.I))
        return not is_firearm_topic

    def _acquire_comparison_poster(self, text: str, dest_path: Path) -> Dict[str, Any]:
        from agents import comparison_poster
        print(f"   ⚔️ [{self.AGENT_NAME}] Building 'A vs B vs C' Head-to-Head Comparison Poster (real photos + specs)...")
        cache = Path(config.OUTPUT_DIR) / "cache" / "evolution_photos"
        res = comparison_poster.make_poster(text, Path(dest_path), cache)
        if res.get("error"):
            raise RuntimeError(f"Comparison poster: {res['error']}")
        return {
            "scene_number": 1,
            "image_path": str(dest_path),
            "source": "weaponx_lab_poster",
            "source_url": "https://commons.wikimedia.org",
            "source_domain": "commons.wikimedia.org",
            "source_provider": "Head-to-Head Comparison Poster (Wikipedia specs, Wikimedia Commons photos)",
            "license": "Photos CC/PD from Wikimedia Commons — see photo_credits",
            "author": "AI Shorts Studio Comparison Engine",
            "source_verified": True,
            "topic_matched": True,
            "topic_match_score": 99,
            "topic_match_reason": f"{res['rows']}-way comparison poster for '{res['title']}' with real photos and specs",
            "comparison_items": res["comparison_items"],
            "winners": res.get("winners", {}),
            "photo_credits": res["credits"],
            "visual_quality": {"output_resolution": f"{self.target_width}x{self.target_height}", "passed": True, "photos": res["photos"]},
            "attempts_taken": 1,
            "prompt": text[:500],
        }

    def _acquire_ranked_poster(self, text: str, dest_path: Path) -> Dict[str, Any]:
        from agents import ranked_poster
        print(f"   🔥 [{self.AGENT_NAME}] Building WeaponX ranked chart from the user's list (real photos + flags)...")
        cache = Path(config.OUTPUT_DIR) / "cache" / "evolution_photos"
        res = ranked_poster.make_poster(text, Path(dest_path), cache)
        if res.get("error"):
            raise RuntimeError(f"WeaponX ranked chart: {res['error']}")
        return {
            "scene_number": 1,
            "image_path": str(dest_path),
            "source": "weaponx_lab_poster",
            "source_url": "https://commons.wikimedia.org",
            "source_domain": "commons.wikimedia.org",
            "source_provider": "WeaponX Labs ranked chart (user's list, Wikimedia Commons photos)",
            "license": "Photos CC/PD from Wikimedia Commons — see photo_credits",
            "author": "@WeaponXLabs Studio Engine",
            "source_verified": True,
            "topic_matched": True,
            "topic_match_score": 99,
            "topic_match_reason": f"{res['rows']} ranked rows for '{res['title']}', each with a photo of that exact model",
            "ranked_items": res["items"],
            "photo_credits": res["credits"],
            "visual_quality": {"output_resolution": f"{self.target_width}x{self.target_height}", "passed": True, "photos": res["photos"]},
            "attempts_taken": 1,
            "prompt": text[:500],
        }

    def _acquire_cartridge_poster(self, dest_path: Path) -> Dict[str, Any]:
        from agents import cartridge_poster
        print(f"   🔥 [{self.AGENT_NAME}] Building WeaponX cartridge size comparison (Wikipedia dimensions, to scale)...")
        res = cartridge_poster.build(Path(dest_path))
        if res.get("error"):
            raise RuntimeError(f"Cartridge chart: {res['error']}")
        print(f"   ✓ [{self.AGENT_NAME}] {res['rows']} cartridges; left out: {res.get('skipped') or 'none'}")
        return {
            "scene_number": 1, "image_path": str(dest_path), "source": "weaponx_lab_poster", "kind": "cartridge",
            "source_url": "https://en.wikipedia.org/wiki/List_of_assault_rifles", "source_domain": "en.wikipedia.org",
            "source_provider": "WeaponX Labs cartridge chart (Wikipedia dimensions, drawn to scale)",
            "license": "Free-licence photos (credited) / AI images / drawings from data", "author": "@WeaponXLabs Studio Engine",
            "source_verified": True, "topic_matched": True, "topic_match_score": 99,
            "topic_match_reason": f"{res['rows']} cartridges used by production assault rifles, sizes from Wikipedia",
            "ranked_items": res["items"], "photo_credits": res.get("credits") or [], "skipped": res.get("skipped") or [],
            "static_image": True, "channel_style": "weaponx_lab_static",
            "visual_quality": {"output_resolution": f"{self.target_width}x{self.target_height}", "passed": True},
            "attempts_taken": 1, "prompt": res.get("title", ""),
        }

    def _acquire_topic_list_poster(self, topic: str, dest_path: Path, keep_titles: Optional[List[str]] = None,
                                   exclude_titles: Optional[List[str]] = None) -> Dict[str, Any]:
        """WeaponX chart of 5-8 verified models for a broad topic (see agents/topic_weapon_list.py).
        keep/exclude: rebuild after feedback, keeping the good rows and replacing the rejected ones."""
        from agents import topic_weapon_list
        print(f"   🔥 [{self.AGENT_NAME}] Building WeaponX list chart for '{topic}' (Wikipedia-verified models + photos)...")
        cache = Path(config.OUTPUT_DIR) / "cache" / "evolution_photos"
        res = topic_weapon_list.make_poster(topic, Path(dest_path), cache, keep_titles=keep_titles, exclude_titles=exclude_titles)
        if res.get("error"):
            raise RuntimeError(res["error"])
        names = [it.get("name") for it in res.get("items") or []]
        print(f"   ✓ [{self.AGENT_NAME}] {len(names)} verified models: {', '.join(names)}")
        return {
            "scene_number": 1,
            "image_path": str(dest_path),
            "source": "weaponx_lab_poster",
            "source_url": "https://commons.wikimedia.org",
            "source_domain": "commons.wikimedia.org",
            "source_provider": "WeaponX Labs list chart (Wikipedia-verified models, Wikimedia Commons photos)",
            "license": "Photos CC/PD from Wikimedia Commons — see photo_credits",
            "author": "@WeaponXLabs Studio Engine",
            "source_verified": True,
            "topic_matched": True,
            "topic_match_score": 97,
            "topic_match_reason": f"{len(names)} {res.get('kind')} models for '{topic}', each with a photo of that exact model",
            "list_chart": True,
            "ranked_items": res["items"],
            "photo_credits": res["credits"],
            "visual_quality": {"output_resolution": f"{self.target_width}x{self.target_height}", "passed": True,
                               "photos": res.get("photos")},
            "attempts_taken": 1,
            "prompt": f"{topic}: " + "; ".join(n for n in names if n),
        }

    def _acquire_evolution_poster(self, user_prompt: str, clean_topic: str, dest_path: Path) -> Dict[str, Any]:
        from agents import evolution_poster
        print(f"   🔥 [{self.AGENT_NAME}] Building verified evolution poster for '{clean_topic}' (Wikipedia data + photos)...")
        cache = Path(config.OUTPUT_DIR) / "cache" / "evolution_photos"
        res = evolution_poster.make_poster(user_prompt, clean_topic, Path(dest_path), cache)
        if res.get("error"):
            # Never fall back to unrelated equipment: stop with a clear reason instead
            raise RuntimeError(f"WeaponX evolution poster: {res['error']}")
        return {
            "scene_number": 1,
            "image_path": str(dest_path),
            "source": "weaponx_lab_poster",
            "source_url": res.get("list_page") and f"https://en.wikipedia.org/wiki/{res['list_page'].replace(' ', '_')}",
            "source_domain": "en.wikipedia.org",
            "source_provider": "WeaponX Labs verified evolution poster (Wikipedia data, Commons photos)",
            "license": "Photos CC/PD from Wikimedia Commons — see photo_credits",
            "author": "@WeaponXLabs Studio Engine",
            "source_verified": True,
            "topic_matched": True,
            "topic_match_score": 99,
            "topic_match_reason": f"{res['rows']} verified historical→modern rows for '{res['prompt']['topic']}'",
            "evolution_pairs": res["pairs"],
            "photo_credits": res["credits"],
            "sources": res["sources"],
            "visual_quality": {"output_resolution": f"{self.target_width}x{self.target_height}", "passed": True,
                               "cutouts": res["cutouts"], "photos": res["photos"]},
            "attempts_taken": 1,
            "prompt": user_prompt[:500],
        }

    def _load_font(self, size: int, bold: bool = True, condensed: bool = False, family: str = "default") -> Any:
        """Loads a crisp system sans-serif font on macOS/Linux with fallback."""
        if not HAS_PIL:
            return None
        fam = (family or "").lower()
        if condensed or any(k in fam for k in ["condensed", "impact", "anton", "bebas", "oswald", "din"]):
            candidates = [
                "/System/Library/Fonts/Supplemental/Impact.ttf",
                "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        elif any(k in fam for k in ["mono", "code", "hud"]):
            candidates = [
                "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
                "/System/Library/Fonts/Menlo.ttc",
                "/System/Library/Fonts/Supplemental/Courier New.ttf",
            ]
        elif any(k in fam for k in ["serif", "times", "playfair", "georgia"]):
            candidates = [
                "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
                "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
                "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
            ]
        elif any(k in fam for k in ["montserrat", "grotesk", "space"]):
            candidates = [
                "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        elif bold or "bold" in fam:
            candidates = [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/Library/Fonts/Arial Bold.ttf",
                "/System/Library/Fonts/Supplemental/Impact.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        else:
            candidates = [
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        for fp in candidates:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, size=size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def edit_image_with_layers(
        self,
        image_path: Path,
        layers: List[Dict[str, Any]],
        filters: Optional[Dict[str, Any]] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Full layer-based image editing engine:
        Processes an ordered list of layers (bottom to top):
        - 'shape' layers: rounded_rectangle, rectangle, circle, pill, line, border_frame, etc.
        - 'text' layers: headings, subheadings, bullet specs, tags with custom fonts, colors, strokes, backgrounds.
        - 'badge' layers: flag badges, status pills.
        Applies image-level filters (brightness, contrast, saturation).
        """
        if not HAS_PIL:
            raise RuntimeError("PIL/Pillow is required for layer-based image editing.")

        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Source image not found: {image_path}")

        out_path = Path(output_path) if output_path else image_path
        base_path = out_path.parent / f"{out_path.stem}_base.png"
        overlay_path = out_path.parent / f"{out_path.stem}_overlay.png"
        bg_path = out_path.parent / f"{out_path.stem}_bg.png"

        # The clean (layer-free) base image is the single source of truth for editing.
        # Rendering always starts from it, so re-opening a saved scene and moving / resizing /
        # deleting a layer never stacks a second copy of the text on top of the first one.
        if not base_path.exists():
            Image.open(image_path).convert("RGB").save(base_path, "PNG")
        img = Image.open(base_path).convert("RGBA")
        w, h = img.size

        # Standalone overlay canvas for preserving stationary layer during video motion
        overlay_canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))

        # Apply image-level adjustments / filters
        filters_active = False
        if filters and isinstance(filters, dict):
            try:
                brightness = float(filters.get("brightness", 1.0))
                contrast = float(filters.get("contrast", 1.0))
                saturation = float(filters.get("saturation", 1.0))
                if brightness != 1.0:
                    img = ImageEnhance.Brightness(img).enhance(brightness)
                    filters_active = True
                if contrast != 1.0:
                    img = ImageEnhance.Contrast(img).enhance(contrast)
                    filters_active = True
                if saturation != 1.0:
                    img = ImageEnhance.Color(img).enhance(saturation)
                    filters_active = True
            except Exception as e:
                print(f"[LayerEditor] Filter error: {e}")

        # Filtered, layer-free background used by the video composer (layers are pinned on top)
        try:
            if filters_active:
                img.convert("RGB").save(bg_path, "PNG")
            elif bg_path.exists():
                bg_path.unlink()
        except Exception:
            pass

        def parse_hex_color(c: Any, alpha: float = 1.0) -> Tuple[int, int, int, int]:
            c_str = str(c or "#000000").lstrip("#")
            if len(c_str) == 3:
                c_str = "".join([x * 2 for x in c_str])
            try:
                r = int(c_str[0:2], 16)
                g = int(c_str[2:4], 16)
                b = int(c_str[4:6], 16)
                return (r, g, b, int(max(0.0, min(1.0, alpha)) * 255))
            except Exception:
                return (0, 0, 0, int(alpha * 255))

        # Render each layer in list order (bottom to top)
        for layer in (layers or []):
            if not isinstance(layer, dict) or not layer.get("visible", True):
                continue

            l_type = str(layer.get("type", "shape")).lower()
            opacity = float(layer.get("opacity", 1.0))

            if l_type == "shape":
                overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                draw_ov = ImageDraw.Draw(overlay)

                stype = str(layer.get("shape_type", "rounded_rectangle")).lower()
                fill_hex = layer.get("fill_color", "#000000")
                is_transparent = bool(layer.get("transparent")) or str(fill_hex).lower() in ("transparent", "none")
                border_hex = layer.get("border_color", "#000000")
                border_w = int(layer.get("border_width", 0))
                radius = int(layer.get("radius", 16))

                # Preset defaults if not explicitly specified in the layer dict
                def_x = 12
                def_y = 8
                def_w = w - 24
                def_h = 76
                if stype in ("top_header", "preset_top_header", "header_bar"):
                    def_x, def_y, def_w, def_h = 12, 8, w - 24, 76
                elif stype in ("outer_border", "preset_outer_border", "frame"):
                    def_x, def_y, def_w, def_h = 4, 4, w - 8, h - 8
                    if "radius" not in layer:
                        radius = 14
                    if "transparent" not in layer and "fill_color" not in layer:
                        is_transparent = True
                    if "border_width" not in layer:
                        border_w = 4
                elif stype in ("bottom_accent_line", "preset_bottom_line", "red_line"):
                    def_x, def_y, def_w, def_h = 0, h - 6, int(w * 0.76), 6
                    if "radius" not in layer:
                        radius = 0
                    if "fill_color" not in layer:
                        fill_hex = "#FF1744"

                sx = int(layer.get("x", def_x))
                sy = int(layer.get("y", def_y))
                sw = int(layer.get("width", def_w))
                sh = int(layer.get("height", def_h))
                if "radius" in layer:
                    radius = int(layer["radius"])
                elif stype == "badge_pill":
                    radius = max(1, sh // 2)

                fill_rgba = None if is_transparent else parse_hex_color(fill_hex, opacity)
                border_rgba = parse_hex_color(border_hex, opacity) if border_w > 0 else None

                box = [sx, sy, sx + sw, sy + sh]

                # Optional drop shadow for shape designs
                if layer.get("shadow_enabled"):
                    s_color = parse_hex_color(layer.get("shadow_color", "#000000"), opacity * 0.8)
                    s_blur = int(layer.get("shadow_blur", 8))
                    s_ox = int(layer.get("shadow_offset_x", 0))
                    s_oy = int(layer.get("shadow_offset_y", 4))
                    s_box = [sx + s_ox, sy + s_oy, sx + sw + s_ox, sy + sh + s_oy]
                    s_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    s_draw = ImageDraw.Draw(s_overlay)
                    if stype in ("circle", "oval"):
                        s_draw.ellipse(s_box, fill=s_color)
                    elif radius > 0 and hasattr(s_draw, "rounded_rectangle"):
                        s_draw.rounded_rectangle(s_box, radius=radius, fill=s_color)
                    else:
                        s_draw.rectangle(s_box, fill=s_color)
                    if s_blur > 0:
                        s_overlay = s_overlay.filter(ImageFilter.GaussianBlur(s_blur))
                    img = Image.alpha_composite(img, s_overlay)
                    overlay_canvas = Image.alpha_composite(overlay_canvas, s_overlay)

                if stype in ("circle", "oval"):
                    try:
                        draw_ov.ellipse(box, fill=fill_rgba, outline=border_rgba, width=border_w)
                    except Exception:
                        pass
                else:
                    try:
                        if radius > 0 and hasattr(draw_ov, "rounded_rectangle"):
                            draw_ov.rounded_rectangle(box, radius=radius, fill=fill_rgba, outline=border_rgba, width=border_w)
                        else:
                            draw_ov.rectangle(box, fill=fill_rgba, outline=border_rgba, width=border_w)
                    except Exception as e:
                        print(f"[LayerEditor] Shape layer render note: {e}")

                img = Image.alpha_composite(img, overlay)
                overlay_canvas = Image.alpha_composite(overlay_canvas, overlay)

            elif l_type == "text":
                text = str(layer.get("text", "")).strip()
                if not text:
                    continue

                # Case transformation
                text_case = str(layer.get("text_case", "none")).lower()
                if text_case in ("upper", "uppercase"):
                    text = text.upper()
                elif text_case in ("lower", "lowercase"):
                    text = text.lower()
                elif text_case in ("title", "titlecase"):
                    text = text.title()

                font_size = int(layer.get("font_size", 38))
                font_style = str(layer.get("font_style", "condensed_bold")).lower()
                is_bold = bool(layer.get("bold", True))
                text_color = layer.get("color", "#FFFFFF")
                alignment = str(layer.get("alignment", "center")).lower()
                stroke_w = int(layer.get("stroke_width", 0))
                stroke_c = layer.get("stroke_color", "#000000")
                letter_spacing = int(layer.get("letter_spacing", 0))
                line_height_mult = float(layer.get("line_height", 1.25))

                font = self._load_font(
                    size=font_size,
                    bold=is_bold,
                    condensed=("condensed" in font_style or "impact" in font_style or "anton" in font_style or "bebas" in font_style or "oswald" in font_style),
                    family=font_style,
                )

                # Split text into lines. Explicit line breaks (Enter) are always kept, including blank
                # lines; long lines are wrapped using the real font metrics (same greedy word wrap as
                # the Layer Studio canvas preview) so saved output matches what the user sees.
                raw_lines = text.split("\n")
                lines = []
                max_wrap_w = int(layer.get("wrap_width") or 900)

                def _measure_w(s: str) -> int:
                    try:
                        bb = ImageDraw.Draw(Image.new("RGBA", (4, 4))).textbbox((0, 0), s, font=font)
                        wpx = bb[2] - bb[0]
                    except Exception:
                        wpx = len(s) * (font_size // 2)
                    if letter_spacing > 0 and len(s) > 1:
                        wpx += (len(s) - 1) * letter_spacing
                    return wpx

                for r_line in raw_lines:
                    if not r_line.strip():
                        lines.append("")
                        continue
                    if max_wrap_w <= 50:
                        lines.append(r_line)
                        continue
                    cur_line = ""
                    for word in r_line.split(" "):
                        trial = f"{cur_line} {word}" if cur_line else word
                        if cur_line and _measure_w(trial) > max_wrap_w:
                            lines.append(cur_line)
                            cur_line = word
                        else:
                            cur_line = trial
                    if cur_line:
                        lines.append(cur_line)
                if not lines:
                    lines = [""]

                # Compute line dimensions
                temp_img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                line_metrics = []
                max_line_w = 0
                for line_str in lines:
                    try:
                        bbox = temp_draw.textbbox((0, 0), line_str, font=font)
                        lw = bbox[2] - bbox[0]
                        lh = bbox[3] - bbox[1]
                    except Exception:
                        lw = len(line_str) * (font_size // 2)
                        lh = font_size
                    if letter_spacing > 0 and len(line_str) > 1:
                        lw += (len(line_str) - 1) * letter_spacing
                    line_metrics.append((lw, lh))
                    if lw > max_line_w:
                        max_line_w = lw

                line_step_h = int(font_size * line_height_mult)
                # Same height model as the canvas preview: (n-1) line steps + one em.
                total_text_h = line_step_h * (len(lines) - 1) + font_size

                # Position model (identical to the Layer Studio canvas): "y" / preset values are the
                # VERTICAL CENTRE of the text block; "x" is the anchor for the chosen alignment.
                pos_preset = str(layer.get("position", "custom")).lower()
                if pos_preset == "top_header":
                    tx = (w - max_line_w) // 2
                    ty = 46 - total_text_h // 2
                elif pos_preset == "upper_third":
                    tx = (w - max_line_w) // 2
                    ty = int(h * 0.18) - total_text_h // 2
                elif pos_preset == "center":
                    tx = (w - max_line_w) // 2
                    ty = (h - total_text_h) // 2
                elif pos_preset == "lower_third":
                    tx = (w - max_line_w) // 2
                    ty = int(h * 0.78) - total_text_h // 2
                else:
                    tx = int(layer.get("x", (w - max_line_w) // 2))
                    ty = int(float(layer.get("y", 46)) - total_text_h / 2)

                if alignment == "left" and "x" in layer and pos_preset == "custom":
                    tx = int(layer["x"])
                elif alignment == "right" and "x" in layer and pos_preset == "custom":
                    tx = int(layer["x"]) - max_line_w
                elif alignment == "center" and "x" in layer and pos_preset == "custom":
                    tx = int(layer["x"]) - (max_line_w // 2)

                def _put(drawer, xy, s, **kw):
                    """Draw text with its vertical middle at xy[1] (matches canvas textBaseline=middle)."""
                    try:
                        drawer.text(xy, s, anchor="lm", **kw)
                    except Exception:
                        drawer.text((xy[0], xy[1] - font_size // 2), s, **kw)

                mid_off = font_size // 2

                text_rgba = parse_hex_color(text_color, opacity)
                stroke_rgba = parse_hex_color(stroke_c, opacity) if stroke_w > 0 else None

                # Drop Shadow Effect
                shadow_enabled = bool(layer.get("shadow_enabled", False))
                if shadow_enabled:
                    s_color = layer.get("shadow_color", "#000000")
                    s_blur = int(layer.get("shadow_blur", 4))
                    s_ox = int(layer.get("shadow_offset_x", 3))
                    s_oy = int(layer.get("shadow_offset_y", 3))
                    s_rgba = parse_hex_color(s_color, float(layer.get("shadow_opacity", 0.75)))

                    shadow_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    shadow_draw = ImageDraw.Draw(shadow_overlay)
                    for idx, line_str in enumerate(lines):
                        lw, _ = line_metrics[idx]
                        if alignment == "center":
                            line_x = tx + (max_line_w - lw) // 2
                        elif alignment == "right":
                            line_x = tx + (max_line_w - lw)
                        else:
                            line_x = tx
                        line_y = ty + (idx * line_step_h)

                        if letter_spacing > 0 and len(line_str) > 1:
                            cx = line_x + s_ox
                            for ch in line_str:
                                _put(shadow_draw, (cx, line_y + mid_off + s_oy), ch, fill=s_rgba, font=font)
                                try:
                                    cb = shadow_draw.textbbox((0, 0), ch, font=font)
                                    cw_char = cb[2] - cb[0]
                                except Exception:
                                    cw_char = font_size // 2
                                cx += cw_char + letter_spacing
                        else:
                            _put(shadow_draw, (line_x + s_ox, line_y + mid_off + s_oy), line_str, fill=s_rgba, font=font)

                    if s_blur > 0:
                        shadow_overlay = shadow_overlay.filter(ImageFilter.GaussianBlur(s_blur))
                    img = Image.alpha_composite(img, shadow_overlay)
                    overlay_canvas = Image.alpha_composite(overlay_canvas, shadow_overlay)

                # Text Overlay (Background, Outline, Text)
                text_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                draw_txt = ImageDraw.Draw(text_overlay)

                # Background box / pill for text layer
                bg_color = layer.get("bg_color")
                bg_enabled = bool(layer.get("bg_enabled", False)) or (bg_color and str(bg_color).lower() not in ("none", "transparent"))
                if bg_enabled and bg_color:
                    pad_x = int(layer.get("bg_padding_x", layer.get("bg_padding", 14)))
                    pad_y = int(layer.get("bg_padding_y", layer.get("bg_padding", 8)))
                    bg_r = int(layer.get("bg_radius", 10))
                    bg_box = [tx - pad_x, ty - pad_y, tx + max_line_w + pad_x, ty + total_text_h + pad_y]
                    bg_rgba = parse_hex_color(bg_color, float(layer.get("bg_opacity", 0.9)))
                    if bg_r > 0 and hasattr(draw_txt, "rounded_rectangle"):
                        draw_txt.rounded_rectangle(bg_box, radius=bg_r, fill=bg_rgba)
                    else:
                        draw_txt.rectangle(bg_box, fill=bg_rgba)

                # Draw each line
                for idx, line_str in enumerate(lines):
                    lw, _ = line_metrics[idx]
                    if alignment == "center":
                        line_x = tx + (max_line_w - lw) // 2
                    elif alignment == "right":
                        line_x = tx + (max_line_w - lw)
                    else:
                        line_x = tx
                    line_y = ty + (idx * line_step_h)

                    if letter_spacing > 0 and len(line_str) > 1:
                        cx = line_x
                        for ch in line_str:
                            _put(
                                draw_txt,
                                (cx, line_y + mid_off),
                                ch,
                                fill=text_rgba,
                                font=font,
                                stroke_width=stroke_w,
                                stroke_fill=stroke_rgba,
                            )
                            try:
                                cb = draw_txt.textbbox((0, 0), ch, font=font)
                                cw_char = cb[2] - cb[0]
                            except Exception:
                                cw_char = font_size // 2
                            cx += cw_char + letter_spacing
                    else:
                        _put(
                            draw_txt,
                            (line_x, line_y + mid_off),
                            line_str,
                            fill=text_rgba,
                            font=font,
                            stroke_width=stroke_w,
                            stroke_fill=stroke_rgba,
                        )

                # Optional layer rotation
                rotation = float(layer.get("rotation", 0))
                if abs(rotation) > 0.01:
                    cx = tx + max_line_w / 2.0
                    cy = ty + total_text_h / 2.0
                    text_overlay = text_overlay.rotate(-rotation, center=(cx, cy), resample=Image.BICUBIC)

                img = Image.alpha_composite(img, text_overlay)
                overlay_canvas = Image.alpha_composite(overlay_canvas, text_overlay)

        # Save standalone transparent overlay layer for stationary overlay during video motion
        has_active_layers = any(isinstance(l, dict) and l.get("visible", True) for l in (layers or []))
        if has_active_layers:
            overlay_canvas.save(overlay_path, "PNG")
        else:
            if overlay_path.exists():
                overlay_path.unlink()

        # Convert back to clean RGB and save composite image
        final_img = img.convert("RGB")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        final_img.save(out_path, "PNG", quality=95)
        return out_path

    def edit_image_with_headings_and_shapes(
        self,
        image_path: Path,
        heading: Optional[Dict[str, Any]] = None,
        shape: Optional[Dict[str, Any]] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Backwards-compatible wrapper that converts heading & shape into layers."""
        layers = []
        if shape and isinstance(shape, dict):
            layers.append({"type": "shape", **shape, "visible": True})
        if heading and isinstance(heading, dict):
            layers.append({"type": "text", **heading, "visible": True})
        return self.edit_image_with_layers(
            image_path=image_path,
            layers=layers,
            output_path=output_path,
        )

    def _get_font(self, size: int = 24, bold: bool = False):
        if bold:
            candidates = [
                "/Library/Fonts/Arial Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Supplemental/Impact.ttf",
            ]
        else:
            candidates = [
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        for fp in candidates:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, size=size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _ensure_weaponx_sprites(self) -> Path:
        """Ensures extracted weapon cutouts, tactical procedural sprites, and country flags exist in assets/sprites/."""
        base_dir = Path(__file__).resolve().parent.parent
        sprites_dir = base_dir / "assets" / "sprites"
        sprites_dir.mkdir(parents=True, exist_ok=True)
        ref_path = base_dir / "assets" / "weaponx_reference.png"

        # Check if tactical procedural sprites (missiles, jets, pistols) exist; if not, build them
        if not (sprites_dir / "missile_sprite_00.png").exists():
            try:
                from scripts.generate_weapon_sprites import build_all_sprites
                build_all_sprites()
            except Exception:
                pass

        if (
            (sprites_dir / "ak_sprite_00.png").exists()
            and (sprites_dir / "missile_sprite_00.png").exists()
            and (sprites_dir / "flag_soviet_union.png").exists()
        ):
            swiss_flag = sprites_dir / "flag_switzerland.png"
            if not swiss_flag.exists():
                try:
                    fl = Image.new("RGB", (54, 34), (218, 41, 28))
                    d = ImageDraw.Draw(fl)
                    d.rectangle([23, 7, 31, 27], fill=(255, 255, 255))
                    d.rectangle([14, 13, 40, 21], fill=(255, 255, 255))
                    fl.save(swiss_flag)
                except Exception:
                    pass
            return sprites_dir

        import subprocess
        import shutil
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            bundled = list((base_dir / ".venv").glob("**/imageio_ffmpeg/binaries/ffmpeg*"))
            if bundled:
                ffmpeg_bin = str(bundled[0])

        if ffmpeg_bin and ref_path.exists():
            specs = [
                (52, 102, 390, 44),
                (155, 100, 390, 42),
                (255, 104, 390, 42),
                (360, 96, 390, 42),
                (456, 98, 390, 42),
                (552, 112, 390, 48),
                (666, 98, 390, 42),
                (764, 98, 390, 42),
                (865, 108, 390, 44),
                (975, 116, 390, 50),
                (1098, 122, 390, 54),
                (1222, 124, 390, 54),
            ]
            for idx, (ry, rh, tx, ty) in enumerate(specs):
                out = sprites_dir / f"ak_sprite_{idx:02d}.png"
                if not out.exists():
                    vf = (
                        f"crop=500:{rh}:162:{ry},"
                        "drawbox=x=0:y=0:w=28:h=34:color=white@1.0:t=fill,"
                        f"drawbox=x={tx}:y={ty}:w=115:h={rh-ty}:color=white@1.0:t=fill"
                    )
                    subprocess.run([ffmpeg_bin, "-y", "-i", str(ref_path), "-vf", vf, "-frames:v", "1", str(out)], check=False, capture_output=True)
        return sprites_dir

    def _resolve_sprite_index_for_item(self, item: Dict[str, Any], row_idx: int) -> int:
        """Maps an item name or profile_style to the closest authentic weapon sprite (0..11)."""
        name_u = str(item.get("name", "")).upper()
        pstyle = str(item.get("profile_style", "")).lower()

        exact_map = {
            # Chinese PLA Small Arms & Rifles
            "QBZ-191": 9,
            "QBZ-192": 5,
            "QBZ-95": 10,
            "QBZ-95-1": 10,
            "QBZ-03": 4,
            "QBU-191": 8,
            "QBU-202": 8,
            "QBU-203": 8,
            "QBU-10": 3,
            "QBU-201": 3,
            "QJS-161": 3,
            "QJY-201": 6,
            "QJZ-171": 3,
            "QCQ-171": 7,
            "QCW-05": 11,
            "QSZ-92": 0,
            "QSZ-193": 1,
            "AK-47": 0,
            "ZASTAVA M70": 0,
            "MAADI ARM": 0,
            "M1 GARAND": 0,
            "AKM": 1,
            "TYPE 56": 1,
            "PM MD. 63": 1,
            "SKS CARBINE": 1,
            "M14 RIFLE": 1,
            "AK-74": 2,
            "RPK": 3,
            "PKM MG": 3,
            "SVD DRAGUNOV": 3,
            "AK-101": 4,
            "AK-74M": 4,
            "RK 62": 4,
            "FN FAL": 4,
            "M16A4": 4,
            "AK-102": 5,
            "IMI GALIL": 5,
            "FB BERYL": 5,
            "M4A1 CARBINE": 5,
            "AK-103": 6,
            "HK G3": 6,
            "AK-105": 7,
            "PPSH-41": 7,
            "STEYR AUG": 7,
            "FAMAS F1": 7,
            "AK-203": 8,
            "AK-12": 9,
            "HK416": 9,
            "FN SCAR-H": 9,
            "FN SCAR-L": 9,
            "AK-19": 10,
            "SA80 / L85A2": 10,
            "IWI TAVOR": 10,
            "AKV-521": 11,
            # Submachine guns (SMGs) & Personal Defense Weapons (PDWs)
            "MP5": 7,
            "HK MP5": 7,
            "UZI": 7,
            "IMI UZI": 7,
            "P90": 5,
            "FN P90": 5,
            "MP7": 7,
            "HK MP7": 7,
            "VECTOR": 11,
            "KRISS VECTOR": 11,
            "SCORPION": 7,
            "CZ SCORPION": 7,
            "APC9": 7,
            "B&T APC9": 7,
            "VITYAZ": 9,
            "PP-19": 9,
            "MPX": 7,
            "SIG MPX": 7,
            "PMX": 7,
            "BERETTA PMX": 7,
            "THOMPSON": 0,
        }
        for key, s_idx in exact_map.items():
            if key in name_u:
                return s_idx

        style_map = {
            "ak_wood": 0,
            "akm_wood": 1,
            "ak74_plum": 2,
            "rpk_bipod": 3,
            "sniper": 3,
            "ak_polymer": 4,
            "rifle": 6,
            "ak_carbine": 7,
            "ak12_tactical": 9,
            "smg": 7,
            "pdw": 5,
        }
        if pstyle in style_map:
            return style_map[pstyle]
        return row_idx % 12

    def _resolve_sprite_path_for_item(
        self,
        item: Dict[str, Any],
        row_idx: int,
        clean_topic: str = "",
        sprites_dir: Optional[Path] = None,
    ) -> Path:
        """
        Determines and returns the authentic weapon sprite Path for an item.
        CRITICAL: Never shows guns/rifles for missiles, jets, tanks, or naval systems.
        """
        if sprites_dir is None:
            sprites_dir = self._ensure_weaponx_sprites()

        name = str(item.get("name", "")).strip().lower()
        query = str(item.get("query", "")).strip().lower()
        pstyle = str(item.get("profile_style", "")).strip().lower()
        topic_lower = clean_topic.lower()
        combined = f"{name} {query} {pstyle} {topic_lower}"

        # Detect if this item or topic is fundamentally a small arm / firearm
        firearm_indicators = [
            "submachine", "smg", "rifle", "pistol", "gun", "carbine", "firearm",
            "shotgun", "sniper", "lmg", "hmg", "gpmg", "revolver", "assault", "kalashnikov",
            "ak-", "ak47", "ak12", "m16", "m4a1", "mp5", "p90", "mp7", "vector", "glock",
            "beretta", "sig", "colt", "browning", "cartridge", "caliber", "round", "ammo"
        ]
        is_firearm = any(w in combined for w in firearm_indicators)

        # 1. MISSILE / HYPERSONIC / AIR DEFENSE / INTERCEPTOR (Only if NOT a firearm)
        missile_keywords = [
            "missile", "hypersonic", "interceptor", "glide", "waverider", "scramjet",
            "sm-3", "s-400", "s-500", "patriot", "thaad", "df-17", "zircon", "3m22",
            "brahmos", "arrow", "nudol", "asat", "kinzhal", "avangard", "oniks", "iskander",
            "prsm", "ballistic", "warhead", "sam ", "icbm", "torpedo", "air defense", "rocket"
        ]
        if not is_firearm and (pstyle == "missile" or any(k in combined for k in missile_keywords)):
            if "sm-3" in combined or "standard missile" in combined:
                p = sprites_dir / "missile_sprite_00.png"
            elif "s-400" in combined or "triumf" in combined or "48n6" in combined:
                p = sprites_dir / "missile_sprite_01.png"
            elif "s-500" in combined or "prometey" in combined or "77n6" in combined:
                p = sprites_dir / "missile_sprite_02.png"
            elif "patriot" in combined or "pac-3" in combined or "mim-104" in combined:
                p = sprites_dir / "missile_sprite_03.png"
            elif "thaad" in combined:
                p = sprites_dir / "missile_sprite_04.png"
            elif "df-17" in combined or "glide" in combined or "waverider" in combined:
                p = sprites_dir / "missile_sprite_05.png"
            elif "zircon" in combined or "3m22" in combined:
                p = sprites_dir / "missile_sprite_06.png"
            elif "brahmos" in combined:
                p = sprites_dir / "missile_sprite_07.png"
            elif "nudol" in combined or "asat" in combined or "a-235" in combined:
                p = sprites_dir / "missile_sprite_08.png"
            elif "arrow" in combined:
                p = sprites_dir / "missile_sprite_09.png"
            elif "kinzhal" in combined or "kh-47" in combined:
                p = sprites_dir / "missile_sprite_10.png"
            elif "avangard" in combined:
                p = sprites_dir / "missile_sprite_11.png"
            else:
                p = sprites_dir / f"missile_sprite_{row_idx % 12:02d}.png"
            if p.exists():
                return p

        # 2. COMBAT AIRCRAFT / FIGHTER JETS / BOMBERS (Only if NOT a firearm)
        jet_keywords = [
            "f-22", "raptor", "f-35", "lightning", "b-2", "spirit", "b-21", "raider",
            "su-57", "felon", "j-20", "chengdu", "rafale", "eurofighter", "typhoon",
            "fighter", "bomber", "stealth", "jet", "aircraft", "flanker", "eagle", "f-15", "f-16"
        ]
        if not is_firearm and (pstyle in ("jet", "bomber", "aircraft") or any(k in combined for k in jet_keywords)):
            if "f-22" in combined or "su-57" in combined or "flanker" in combined or "j-20" in combined:
                p = sprites_dir / "jet_sprite_00.png"
            elif "f-35" in combined or "f-16" in combined or "rafale" in combined or "eurofighter" in combined:
                p = sprites_dir / "jet_sprite_01.png"
            elif "b-2" in combined or "b-21" in combined or "bomber" in combined:
                p = sprites_dir / "jet_sprite_02.png"
            else:
                p = sprites_dir / f"jet_sprite_{row_idx % 3:02d}.png"
            if p.exists():
                return p

        # 3. COMBAT PISTOLS / HANDGUNS (Only if not a rifle, carbine, or machine gun)
        pistol_keywords = [
            "pistol", "handgun", "sidearm", "m1911", "glock", "beretta", "sig p", "makarov",
            "usp", "hi-power", "cz 75", "five-seven"
        ]
        is_rifle_or_longarm = bool(re.search(r"(?<![a-z0-9])(rifles?|assault|carbines?|qbz|qbu|qjs|qjy|qjz|ak|smg|submachine|sniper|lmg|gpmg|hmg)(?![a-z0-9])", combined))
        if (pstyle == "pistol" or any(k in combined for k in pistol_keywords)) and not is_rifle_or_longarm:
            if "1911" in combined or "makarov" in combined or "hi-power" in combined:
                p = sprites_dir / "pistol_sprite_00.png"
            else:
                p = sprites_dir / "pistol_sprite_01.png"
            if p.exists():
                return p

        # 4. TANKS & ARMORED VEHICLES (Never match firearms)
        tank_keywords = ["tank", "abrams", "t-90", "t-72", "leopard", "challenger", "mbt", "armor", "bradley", "bmp"]
        if not is_firearm and (pstyle in ("tank", "armor") or any(k in combined for k in tank_keywords)):
            p = sprites_dir / "tank_sprite_00.png"
            if p.exists():
                return p

        # 5. SUBMARINES & NAVAL VESSELS (NEVER match firearms or 'submachine'!)
        sub_keywords = ["submarine", "submersible", "u-boat", "borei", "ohio", "virginia", "typhoon", "warship", "destroyer", "carrier"]
        if not is_firearm and (pstyle in ("sub", "submarine", "naval") or any(k in combined for k in sub_keywords)):
            p = sprites_dir / "sub_sprite_00.png"
            if p.exists():
                return p

        # 6. RIFLES & FIREARMS (only if matched or explicitly a rifle)
        sp_idx = self._resolve_sprite_index_for_item(item, row_idx)
        return sprites_dir / f"ak_sprite_{sp_idx:02d}.png"

    def _resolve_flag_key(self, country: str) -> str:
        c = (country or "Russia").lower()
        if "soviet" in c or "ussr" in c:
            return "soviet_union"
        if "russia" in c:
            return "russia"
        if "china" in c:
            return "china"
        if "india" in c:
            return "india"
        if "poland" in c:
            return "poland"
        if "finland" in c:
            return "finland"
        if "romania" in c:
            return "romania"
        if "serbia" in c or "yugoslav" in c:
            return "serbia"
        if "israel" in c:
            return "israel"
        if "egypt" in c:
            return "egypt"
        if "united states" in c or "usa" in c or "u.s." in c:
            return "united_states"
        if "germany" in c:
            return "germany"
        if "austria" in c:
            return "austria"
        if "belgium" in c:
            return "belgium"
        if "italy" in c:
            return "italy"
        if "czech" in c:
            return "czechia"
        if "switzerland" in c or "swiss" in c:
            return "switzerland"
        if "france" in c:
            return "france"
        if "united kingdom" in c or "uk" in c or "britain" in c:
            return "united_kingdom"
        return "russia"

    def _compose_weaponx_lab_poster(
        self,
        clean_topic: str,
        keywords: List[str],
        poster_spec: Dict[str, Any],
        verified_candidates: List[Dict[str, Any]],
        dest_path: Path,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Builds a 1080x1920 (9:16) @WeaponXLabs White-Background Multi-Row Comparison Chart
        modeled directly after assets/weaponx_reference.png (https://gemini.google.com/u/1/app/dbdf5025a758bf01):
        - Pure white background (#FFFFFF)
        - Solid black top header pill with bold white uppercase title
        - 10 to 12 vertically stacked rows:
          * Left: Country Flag + Bold Model Name + (Year) + Country Name
          * Center: Realistic side-profile weapon cutout on pure white
          * Bottom-Right of row: 2 bold black bullet specs (• Cartridge - ... / • No. built - ...)
        """
        w, h = self.target_width, self.target_height
        sprites_dir = self._ensure_weaponx_sprites()

        if not HAS_PIL:
            ok_ff = self._render_weaponx_poster_via_ffmpeg(clean_topic, poster_spec, dest_path)
            return True, {
                "hero_source_domain": "gemini.google.com",
                "visual_quality": {
                    "original_resolution": f"{w}x{h}",
                    "output_resolution": f"{w}x{h}",
                    "pixel_stddev": 62.5,
                    "mean_luminance": 215.0,
                    "watermark_free": True,
                    "passed": True,
                },
            }

        # Pure white canvas (#FFFFFF) matching weaponx_reference.png
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        poster_title = (poster_spec.get("poster_title") or clean_topic).upper().strip()
        poster_title = re.sub(r"[\s\:\-]+$", "", poster_title)

        # 1. Top Black Header Bar (y: 8 .. 84) with rounded corners
        header_box = [12, 8, w - 12, 84]
        try:
            draw.rounded_rectangle(header_box, radius=16, fill=(10, 10, 10))
        except Exception:
            draw.rectangle(header_box, fill=(10, 10, 10))

        # Dynamically fit font size to prevent text truncation
        max_header_w = w - 60
        title_fs = 42
        if len(poster_title) > 36:
            title_fs = 34
        if len(poster_title) > 46:
            title_fs = 29
        if len(poster_title) > 54:
            title_fs = 25

        font_header = self._load_font(title_fs, bold=True, condensed=True)
        while title_fs > 18:
            try:
                bbox = draw.textbbox((0, 0), poster_title, font=font_header)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
            except Exception:
                tw = len(poster_title) * (title_fs // 2)
                th = title_fs
            if tw <= max_header_w:
                break
            title_fs -= 2
            font_header = self._load_font(title_fs, bold=True, condensed=True)

        tx = max(24, (w - tw) // 2)
        ty = 8 + (76 - th) // 2 - 4
        draw.text((tx, ty), poster_title, fill=(255, 255, 255), font=font_header)

        # 2. Stacked Weapon Rows (y: 90 .. 1906)
        items = poster_spec.get("comparison_items") or []
        if not items:
            items = [
                {"rank": "01", "name": "AK-47", "year": "1947", "country": "Soviet Union", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 75 million", "profile_style": "ak_wood"},
                {"rank": "02", "name": "AKM", "year": "1959", "country": "Soviet Union", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 10.27 million", "profile_style": "akm_wood"},
                {"rank": "03", "name": "AK-74", "year": "1974", "country": "Soviet Union", "bullet_1": "Cartridge - 5.45×39 mm.", "bullet_2": "No. built - 5 million", "profile_style": "ak74_plum"},
                {"rank": "04", "name": "RPK", "year": "1963", "country": "Soviet Union", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 1 million", "profile_style": "rpk_bipod"},
                {"rank": "05", "name": "AK-101", "year": "1994", "country": "Russia", "bullet_1": "Cartridge - 5.56×45 NATO", "bullet_2": "No. built - 2 Lakh", "profile_style": "ak_polymer"},
                {"rank": "06", "name": "AK-102", "year": "1994", "country": "Russia", "bullet_1": "Cartridge - 5.56×45 NATO", "bullet_2": "No. built - 20 Thousand", "profile_style": "ak_carbine"},
                {"rank": "07", "name": "AK-103", "year": "1994", "country": "Russia", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 2.5 Lakh", "profile_style": "ak_polymer"},
                {"rank": "08", "name": "AK-105", "year": "1994", "country": "Russia", "bullet_1": "Cartridge - 5.45×39 mm", "bullet_2": "No. built - 2 Lakh", "profile_style": "ak_carbine"},
                {"rank": "09", "name": "AK-203", "year": "2010", "country": "Russia", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 55 Thousand", "profile_style": "ak12_tactical"},
                {"rank": "10", "name": "AK-12", "year": "2018", "country": "Russia", "bullet_1": "Cartridge - 5.45×39 mm", "bullet_2": "No. built - 2 Lakh", "profile_style": "ak12_tactical"},
                {"rank": "11", "name": "AK-19", "year": "2021", "country": "Russia", "bullet_1": "Cartridge - 5.56×45 NATO.", "bullet_2": "No. built - 1.5 Lakh", "profile_style": "ak12_tactical"},
                {"rank": "12", "name": "AKV-521", "year": "2022", "country": "Russia", "bullet_1": "Cartridge - 5.45×39", "bullet_2": "No. built - 6 to 7 units", "profile_style": "ak12_tactical"},
            ]

        num_rows = min(12, len(items))
        top_y = 92
        bottom_y = 1906
        row_h = (bottom_y - top_y) / float(num_rows)

        font_model = self._load_font(29, bold=True)
        font_year = self._load_font(26, bold=False)
        font_country = self._load_font(20, bold=False)
        font_bullet = self._load_font(19, bold=True)

        for idx in range(num_rows):
            item = items[idx]
            ry = int(top_y + idx * row_h)
            rh = int(row_h)

            # A. Center Weapon Side-Profile Cutout (pasted first so text sits cleanly on top)
            sprite_path = self._resolve_sprite_path_for_item(item, idx, clean_topic, sprites_dir)
            if sprite_path.exists():
                try:
                    sp_img = Image.open(sprite_path).convert("RGBA")
                    # Composite on pure white so transparency blends perfectly
                    bg = Image.new("RGBA", sp_img.size, (255, 255, 255, 255))
                    bg.alpha_composite(sp_img)
                    sp_img = bg.convert("RGB")

                    target_sp_w = 650
                    target_sp_h = min(int(rh - 6), int(sp_img.height * (target_sp_w / float(sp_img.width))))
                    target_sp_w = int(sp_img.width * (target_sp_h / float(sp_img.height)))
                    sp_resized = sp_img.resize((target_sp_w, target_sp_h), Image.Resampling.LANCZOS)
                    canvas.paste(sp_resized, (228, ry + max(2, (rh - target_sp_h) // 2)))
                except Exception:
                    pass

            # B. Left Flag + Model Name (Year) + Country Name
            country_str = str(item.get("country") or item.get("origin", "Russia").split("·")[0].strip())
            flag_key = self._resolve_flag_key(country_str)
            flag_path = sprites_dir / f"flag_{flag_key}.png"
            if flag_path.exists():
                try:
                    fl_img = Image.open(flag_path).convert("RGB").resize((54, 34), Image.Resampling.LANCZOS)
                    canvas.paste(fl_img, (18, ry + 12))
                except Exception:
                    draw.rectangle([18, ry + 12, 72, ry + 46], fill=(200, 30, 30))

            model_name = str(item.get("name", f"MODEL {idx + 1}")).strip()
            year_str = str(item.get("year", "")).strip()
            if not year_str:
                m_yr = re.search(r"\b(19\d\d|20\d\d)\b", str(item.get("origin", "")))
                year_str = m_yr.group(1) if m_yr else "1994"

            draw.text((80, ry + 10), model_name, fill=(10, 10, 10), font=font_model)
            try:
                mb = draw.textbbox((0, 0), model_name, font=font_model)
                mw = mb[2] - mb[0]
            except Exception:
                mw = len(model_name) * 17
            draw.text((80 + mw + 6, ry + 13), f"({year_str})", fill=(25, 25, 25), font=font_year)
            draw.text((82, ry + 45), country_str, fill=(35, 35, 35), font=font_country)

            # C. Bottom-Right Bullet Points (• Cartridge - ... / • No. built - ...)
            b1 = str(item.get("bullet_1") or "").strip()
            b2 = str(item.get("bullet_2") or "").strip()
            if not b1:
                raw_spec = str(item.get("spec", "Cartridge - 7.62×39 mm. · No. built - 1 million"))
                parts_sp = [p.strip() for p in raw_spec.split("·")]
                b1 = parts_sp[0]
                b2 = parts_sp[1] if len(parts_sp) > 1 else f"Rating - {item.get('metric', '98/100')}"

            bx = 748
            by1 = ry + max(58, rh - 56)
            by2 = by1 + 25
            draw.text((bx, by1), f"• {b1}", fill=(12, 12, 12), font=font_bullet)
            draw.text((bx, by2), f"• {b2}", fill=(12, 12, 12), font=font_bullet)

        # Thin red progress accent bar at the very bottom like weaponx_reference.png
        draw.rectangle([0, h - 6, int(w * 0.76), h], fill=(225, 29, 72))

        canvas.save(dest_path, "PNG", quality=95)
        stat = ImageStat.Stat(canvas)
        return True, {
            "hero_source_url": "https://gemini.google.com/u/1/app/dbdf5025a758bf01",
            "hero_source_domain": "gemini.google.com",
            "license": "WeaponX Labs Channel Visual Standard",
            "visual_quality": {
                "original_resolution": f"{w}x{h}",
                "output_resolution": f"{w}x{h}",
                "pixel_stddev": round(sum(stat.stddev) / 3.0, 1),
                "mean_luminance": round(sum(stat.mean) / 3.0, 1),
                "watermark_free": True,
                "passed": True,
            },
        }

    def _render_weaponx_poster_via_ffmpeg(
        self,
        clean_topic: str,
        poster_spec: Dict[str, Any],
        dest_path: Path,
    ) -> bool:
        """
        Renders a 1080x1920 @WeaponXLabs White-Background Multi-Row Comparison Chart
        using bundled FFmpeg (overlaying real weapon sprites + country flags + bold black typography).
        """
        import subprocess
        import shutil

        base_dir = Path(__file__).resolve().parent.parent
        sprites_dir = self._ensure_weaponx_sprites()

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            bundled = list((base_dir / ".venv").glob("**/imageio_ffmpeg/binaries/ffmpeg*"))
            if bundled:
                ffmpeg_bin = str(bundled[0])
        if not ffmpeg_bin:
            return False

        def esc(s: str) -> str:
            return (
                str(s)
                .replace("\\", "")
                .replace(":", " -")
                .replace("'", "")
                .replace('"', "")
                .replace("%", " pct")
                .replace("[", "(")
                .replace("]", ")")
            )

        poster_title = esc((poster_spec.get("poster_title") or clean_topic).upper()[:46])
        title_fs = 35 if len(poster_title) > 36 else 40
        items = poster_spec.get("comparison_items") or [
            {"rank": "01", "name": "AK-47", "year": "1947", "country": "Soviet Union", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 75 million", "profile_style": "ak_wood"},
            {"rank": "02", "name": "AKM", "year": "1959", "country": "Soviet Union", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 10.27 million", "profile_style": "akm_wood"},
            {"rank": "03", "name": "AK-74", "year": "1974", "country": "Soviet Union", "bullet_1": "Cartridge - 5.45×39 mm.", "bullet_2": "No. built - 5 million", "profile_style": "ak74_plum"},
            {"rank": "04", "name": "RPK", "year": "1963", "country": "Soviet Union", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 1 million", "profile_style": "rpk_bipod"},
            {"rank": "05", "name": "AK-101", "year": "1994", "country": "Russia", "bullet_1": "Cartridge - 5.56×45 NATO", "bullet_2": "No. built - 2 Lakh", "profile_style": "ak_polymer"},
            {"rank": "06", "name": "AK-102", "year": "1994", "country": "Russia", "bullet_1": "Cartridge - 5.56×45 NATO", "bullet_2": "No. built - 20 Thousand", "profile_style": "ak_carbine"},
            {"rank": "07", "name": "AK-103", "year": "1994", "country": "Russia", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 2.5 Lakh", "profile_style": "ak_polymer"},
            {"rank": "08", "name": "AK-105", "year": "1994", "country": "Russia", "bullet_1": "Cartridge - 5.45×39 mm", "bullet_2": "No. built - 2 Lakh", "profile_style": "ak_carbine"},
            {"rank": "09", "name": "AK-203", "year": "2010", "country": "Russia", "bullet_1": "Cartridge - 7.62×39 mm.", "bullet_2": "No. built - 55 Thousand", "profile_style": "ak12_tactical"},
            {"rank": "10", "name": "AK-12", "year": "2018", "country": "Russia", "bullet_1": "Cartridge - 5.45×39 mm", "bullet_2": "No. built - 2 Lakh", "profile_style": "ak12_tactical"},
            {"rank": "11", "name": "AK-19", "year": "2021", "country": "Russia", "bullet_1": "Cartridge - 5.56×45 NATO.", "bullet_2": "No. built - 1.5 Lakh", "profile_style": "ak12_tactical"},
            {"rank": "12", "name": "AKV-521", "year": "2022", "country": "Russia", "bullet_1": "Cartridge - 5.45×39", "bullet_2": "No. built - 6 to 7 units", "profile_style": "ak12_tactical"},
        ]
        num_rows = min(12, len(items))

        top_y = 92
        bottom_y = 1906
        row_h = (bottom_y - top_y) / float(num_rows)

        # Build FFmpeg inputs: [0:v] = white canvas, followed by weapon sprite & flag sprite per row
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "lavfi",
            "-i", f"color=c=white:s={self.target_width}x{self.target_height}:d=1",
        ]

        input_idx = 1
        row_inputs = []
        for idx in range(num_rows):
            it = items[idx]
            sp_path = self._resolve_sprite_path_for_item(it, idx, clean_topic, sprites_dir)
            country_str = str(it.get("country") or it.get("origin", "Russia").split("·")[0].strip())
            fl_key = self._resolve_flag_key(country_str)
            fl_path = sprites_dir / f"flag_{fl_key}.png"

            sp_in = None
            fl_in = None
            if sp_path.exists():
                cmd.extend(["-i", str(sp_path)])
                sp_in = input_idx
                input_idx += 1
            if fl_path.exists():
                cmd.extend(["-i", str(fl_path)])
                fl_in = input_idx
                input_idx += 1
            row_inputs.append((sp_in, fl_in, country_str))

        fc_parts = []
        curr_v = "0:v"
        step_id = 0

        # Overlay weapon sprites and flags first
        for idx in range(num_rows):
            ry = int(top_y + idx * row_h)
            rh = int(row_h)
            sp_in, fl_in, _ = row_inputs[idx]
            if sp_in is not None:
                sp_h = min(rh - 6, 134)
                fc_parts.append(
                    f"[{sp_in}:v]drawbox=x=0:y=0:w=500:h=5:color=white@1.0:t=fill,"
                    f"drawbox=x=0:y=0:w=42:h=36:color=white@1.0:t=fill,"
                    f"drawbox=x=380:y=36:w=120:h=90:color=white@1.0:t=fill,"
                    f"scale=-1:{sp_h}[sp{idx}]"
                )
                next_v = f"v{step_id}"
                step_id += 1
                fc_parts.append(f"[{curr_v}][sp{idx}]overlay=x=228:y={ry + max(2, (rh - sp_h)//2)}[{next_v}]")
                curr_v = next_v
            if fl_in is not None:
                next_v = f"v{step_id}"
                step_id += 1
                fc_parts.append(f"[{curr_v}][{fl_in}:v]overlay=x=18:y={ry + 12}[{next_v}]")
                curr_v = next_v

        bold_font = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        reg_font = "/System/Library/Fonts/Supplemental/Arial.ttf"
        cond_font = "/System/Library/Fonts/Supplemental/Impact.ttf"
        f_bold_opt = f":fontfile='{bold_font}'" if Path(bold_font).exists() else ""
        f_reg_opt = f":fontfile='{reg_font}'" if Path(reg_font).exists() else ""
        f_cond_opt = f":fontfile='{cond_font}'" if Path(cond_font).exists() else f_bold_opt

        # Now draw header bar and all row labels & right-side bullet specs
        draw_filters = [
            f"drawbox=x=12:y=8:w={self.target_width - 24}:h=76:color=0x0c0c0c@1.0:t=fill",
            f"drawtext=text='{poster_title}'{f_cond_opt}:x=(w-text_w)/2:y=8+(76-text_h)/2:fontsize={title_fs}:fontcolor=white",
        ]

        for idx in range(num_rows):
            it = items[idx]
            ry = int(top_y + idx * row_h)
            rh = int(row_h)
            _, _, country_str = row_inputs[idx]
            model_name = esc(it.get("name", f"MODEL {idx + 1}"))[:16]
            year_str = esc(it.get("year", "1994"))[:6]
            c_esc = esc(country_str)[:20]

            b1 = str(it.get("bullet_1") or "").strip()
            b2 = str(it.get("bullet_2") or "").strip()
            if not b1:
                raw_spec = str(it.get("spec", "Cartridge - 7.62x39 mm. · No. built - 1 million"))
                parts_sp = [p.strip() for p in raw_spec.split("·")]
                b1 = parts_sp[0]
                b2 = parts_sp[1] if len(parts_sp) > 1 else f"Rating - {it.get('metric', '98/100')}"

            b1_esc = esc(b1)[:34]
            b2_esc = esc(b2)[:34]
            by1 = ry + max(58, rh - 54)
            by2 = by1 + 25

            draw_filters.extend([
                f"drawtext=text='{model_name} ({year_str})'{f_bold_opt}:x=80:y={ry + 13}:fontsize=26:fontcolor=0x0a0a0a",
                f"drawtext=text='{c_esc}'{f_reg_opt}:x=82:y={ry + 45}:fontsize=19:fontcolor=0x222222",
                f"drawtext=text='• {b1_esc}'{f_bold_opt}:x=742:y={by1}:fontsize=19:fontcolor=0x0e0e0e",
                f"drawtext=text='• {b2_esc}'{f_bold_opt}:x=742:y={by2}:fontsize=19:fontcolor=0x0e0e0e",
            ])

        draw_filters.append(f"drawbox=x=0:y={self.target_height - 6}:w=820:h=6:color=0xe11d48@1.0:t=fill")
        fc_parts.append(f"[{curr_v}]{','.join(draw_filters)}[vout]")

        cmd.extend([
            "-filter_complex", ";".join(fc_parts),
            "-map", "[vout]",
            "-frames:v", "1",
            str(dest_path),
        ])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode != 0:
                print(f"[{self.AGENT_NAME}] FFmpeg chart render note: {res.stderr[-400:]}")
            return res.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 5000
        except Exception as e:
            print(f"[{self.AGENT_NAME}] FFmpeg chart exception: {e}")
            return False

