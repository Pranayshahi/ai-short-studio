"""Shared imports, optional-dependency flags and constants for the image-generator modules
(image_generator.py, image_ai_engines.py, image_posters.py)."""
import io
import config
import os
import re
import json
import time
import uuid
import math
import base64
import random
import shutil
import threading
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from agents.subject_match import subject_core, designators, mentions, mentions_any, brand_words
import urllib.request

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from PIL import Image, ImageEnhance, ImageDraw, ImageStat, ImageFont, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from config import COMFYUI_API_URL
except ImportError:
    COMFYUI_API_URL = os.getenv("COMFYUI_API_URL", "http://127.0.0.1:8188")

# Serialises requests to the free FLUX endpoint and spaces them out so rapid




WEAPONX_EXACT_SYSTEM_PROMPT = """Create a high-resolution vertical infographic that replicates the EXACT visual design, layout, UI structure, typography, spacing, and presentation style of the attached reference image.

**DESIGN STYLE:**
- Clean, professional military encyclopedia infographic.
- Pure white background.
- Portrait 9:16 aspect ratio.
- Tall vertical poster layout.
- Thin black outer border with rounded corners.
- Minimalist, information-dense editorial design.
- Sharp, realistic photographic cutouts of objects.
- No gradients, no shadows behind text, no decorative illustrations.

**1. HEADER DESIGN**
- Place a wide black horizontal rounded rectangle at the very top.
- Center the main headline inside it.
- Use bold, condensed, uppercase white typography.
- Text should be prominent, similar to Anton, Bebas Neue, or Impact font.
- Keep consistent left and right margins.

**2. MAIN CONTENT LAYOUT**
Create a vertically stacked list of 10–12 entries.

Every entry must follow EXACTLY the same three-column visual arrangement:

LEFT COLUMN:
- Small country flag icon aligned to the left.
- Subject name in bold black sans-serif typography.
- Year/date in regular-weight black typography beside the name.
- Country or category name underneath in smaller black text.

CENTER COLUMN:
- One large, realistic, high-quality isolated photographic image of the featured subject.
- Horizontal orientation.
- Object should be displayed from its side profile.
- Maintain realistic proportions, accurate details, and sharp edges.
- White background with no surrounding environment.
- Image should occupy most of the available horizontal space.
- Align each subject image consistently.

RIGHT COLUMN:
- Two compact black bullet points.
- Display key specifications or important facts.
- Use clean, bold-readable sans-serif typography.
- Keep bullets consistently aligned.
- Maintain uniform font size and spacing.

**3. SPACING AND ALIGNMENT**
- Stack all entries vertically with consistent spacing.
- Use a fixed row structure throughout the infographic.
- Maintain consistent image sizes and text positioning.
- Use approximately 90% of the available width for content.
- Avoid overlapping text and images.
- Ensure every entry is visually separated through whitespace rather than boxes.
- Keep the overall design compact, similar to a technical reference chart.

**4. COLOR PALETTE**
- Background: Pure white (#FFFFFF).
- Header: Solid black (#000000).
- Main text: Black (#111111).
- Secondary text: Dark gray (#444444).
- Country flags: Original flag colors.
- Outer border: Black.
- Bottom accent: Thin red horizontal line (#FF1744).

**5. TYPOGRAPHY**
- Headline: Extra-bold condensed uppercase font.
- Subject names: Bold sans-serif.
- Dates: Regular sans-serif.
- Supporting labels: Small regular sans-serif.
- Specification bullets: Medium-weight sans-serif.
- Typography must be sharp, professional, and readable.

**6. VISUAL QUALITY**
- 4K-quality output.
- High-resolution photographic object cutouts.
- Accurate colors and realistic textures.
- Extremely clean alignment.
- Crisp text rendering.
- Professional military/technical reference infographic aesthetic.

**7. FINAL REQUIREMENTS**
- Reproduce the reference image's design language as closely as possible.
- Do not redesign the layout.
- Do not introduce cards, colored backgrounds, gradients, icons, charts, or modern UI elements.
- Do not use a magazine-cover design.
- Do not change the three-column arrangement.
- Keep the black rounded header and white background.
- Preserve the dense vertical infographic composition.
- Add a thin red accent line along the bottom edge.

**IMPORTANT:** Design replication is the highest priority. Content should fit naturally into the same visual structure without changing its proportions or layout."""

__all__ = ['Any', 'COMFYUI_API_URL', 'Dict', 'HAS_PIL', 'HAS_REQUESTS', 'Image', 'ImageDraw', 'ImageEnhance', 'ImageFilter', 'ImageFont', 'ImageStat', 'List', 'Optional', 'Path', 'Tuple', 'WEAPONX_EXACT_SYSTEM_PROMPT', 'base64', 'brand_words', 'config', 'datetime', 'designators', 'io', 'json', 'math', 'mentions', 'mentions_any', 'os', 'random', 're', 'requests', 'shutil', 'subject_core', 'threading', 'time', 'urllib', 'uuid']
