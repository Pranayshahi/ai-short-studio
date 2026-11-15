"""
OpenMontage Agent (OpenMontageAgent)
Integration with OpenMontage (https://github.com/calesthio/OpenMontage)
Agentic Video Production System for Documentary Montages, Cinematic Storyboards,
Archive Corpus Retrieval, and Film-Style Motion Composition.
"""

from __future__ import annotations

import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

try:
    from PIL import Image, ImageEnhance, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class OpenMontageAgent:
    """
    OpenMontage Agent:
    Interfaces with the OpenMontage engine to plan and construct
    documentary montages inspired by thematic narrative arcs,
    semantic archive asset retrieval, beat-synced pacing, and cinematic color grading.
    """

    AGENT_NAME = "openmontage-agent"
    OPENMONTAGE_ROOT = Path(__file__).resolve().parent.parent / "openmontage"

    DOCUMENTARY_REGISTERS = [
        "elegiac",
        "investigative",
        "kinetic",
        "analytical",
        "mythic",
        "philosophical"
    ]

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or self.OPENMONTAGE_ROOT
        self._ensure_openmontage_path()

    def _ensure_openmontage_path(self) -> bool:
        if self.workspace_root.exists() and str(self.workspace_root) not in sys.path:
            sys.path.insert(0, str(self.workspace_root))
            return True
        return False

    def is_available(self) -> bool:
        """Returns True if the OpenMontage repository and pipelines are available on disk."""
        defs_dir = self.workspace_root / "pipeline_defs"
        return defs_dir.exists() and (defs_dir / "documentary-montage.yaml").exists()

    def get_supported_pipelines(self) -> List[str]:
        """Lists available OpenMontage production pipeline definitions."""
        defs_dir = self.workspace_root / "pipeline_defs"
        if not defs_dir.exists():
            return ["documentary-montage", "cinematic", "animated-explainer"]
        return [p.stem for p in sorted(defs_dir.glob("*.yaml"))]

    def build_montage_brief(
        self,
        topic: str,
        category: str = "Defense & Technology",
        target_duration: float = 30.0,
        tone: str = "investigative",
    ) -> Dict[str, Any]:
        """
        Synthesizes an OpenMontage documentary brief following the
        documentary-montage.yaml specification:
        - Thematic question (single sentence hook)
        - Tone register
        - Target duration & hold times
        - Music plan (mood/tempo)
        - Philosophical end-tag closing thesis
        """
        cat_lower = f"{category} {topic}".lower()
        if any(w in cat_lower for w in ["defense", "military", "weapon", "missile", "combat", "fighter", "tank", "naval", "stealth"]):
            thematic_q = f"How did {topic} redefine modern strategic warfare and reshape global defense doctrine?"
            end_tag = f"In the final calculus of strategic power, {topic} proves that technology does not follow history — it writes it."
            genre = "Cinematic Orchestral / Hybrid Electronic"
            tempo = "mid-tempo build"
        elif any(w in cat_lower for w in ["space", "astronomy", "cosm", "orbit", "satellite", "telescope"]):
            thematic_q = f"What secrets of the cosmos does {topic} unlock for the future of human exploration?"
            end_tag = f"As humanity gazes deeper into the unknown, {topic} reminds us that curiosity is our greatest frontier."
            genre = "Ambient Cinematic Space"
            tempo = "slow atmospheric build"
        elif any(w in cat_lower for w in ["history", "ancient", "war", "century", "empire", "civilization"]):
            thematic_q = f"How did {topic} alter the course of human civilization and redefine world history?"
            end_tag = f"Centuries later, the enduring legacy of {topic} continues to echo across the modern world."
            genre = "Acoustic Historical Documentary"
            tempo = "contemplative narrative"
        elif any(w in cat_lower for w in ["ai", "quantum", "computer", "software", "tech", "chip", "robot"]):
            thematic_q = f"How is {topic} fundamentally rewriting the laws of technology and what comes next?"
            end_tag = f"At the threshold of a new era, {topic} proves that the only limit to discovery is human imagination."
            genre = "Electronic Pulse / Tech Arpeggio"
            tempo = "kinetic pulse"
        else:
            thematic_q = f"What is the untold reality behind {topic}—and why does it continue to fascinate us?"
            end_tag = f"Looking forward, {topic} stands as a powerful testament to the ongoing evolution of our world."
            genre = "Modern Cinematic Documentary"
            tempo = "dynamic narrative"

        slot_count = max(3, min(8, int(round(target_duration / 5.5))))
        base_hold = round(target_duration / slot_count, 1)

        slots = []
        for i in range(slot_count):
            slots.append({
                "slot_index": i + 1,
                "role": "hero" if i in (0, slot_count - 1) else "supporting",
                "target_hold_seconds": base_hold,
                "preferred_sources": ["wikimedia", "nasa", "archive.org", "pexels", "ai_cinematic"],
            })

        return {
            "pipeline": "documentary-montage",
            "version": "1.0",
            "topic": topic,
            "category": category,
            "tone_register": tone if tone in self.DOCUMENTARY_REGISTERS else "investigative",
            "thematic_question": thematic_q,
            "target_duration_seconds": target_duration,
            "slot_count": slot_count,
            "slots": slots,
            "music_plan": {
                "genre": genre,
                "tempo": tempo,
                "sync_mode": "beat_synced_cuts",
            },
            "end_tag_plan": {
                "text": end_tag,
                "duration_seconds": 4.0,
                "mode": "overlay",
                "palette": "documentary_warm",
            },
            "color_grade": {
                "profile": "35mm_documentary_film",
                "contrast": 1.15,
                "saturation": 1.10,
                "temperature": "warm_neutral",
            }
        }

    def apply_openmontage_film_grade(self, image_path: Path) -> bool:
        """
        Applies OpenMontage's signature 35mm documentary film color grade:
        enhances mid-tone contrast, adds filmic color richness, and applies subtle sharpness.
        """
        if not HAS_PIL or not image_path.exists():
            return False
        try:
            with Image.open(image_path) as img:
                canvas = img.convert("RGB")
                # Filmic color grade
                canvas = ImageEnhance.Contrast(canvas).enhance(1.16)
                canvas = ImageEnhance.Color(canvas).enhance(1.12)
                canvas = ImageEnhance.Sharpness(canvas).enhance(1.15)
                canvas.save(image_path, "PNG", quality=95)
            return True
        except Exception:
            return False

