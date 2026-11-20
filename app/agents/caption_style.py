"""
User-configurable caption (burned-in subtitle) styling.

A caption style is a plain dict saved on the project (project["caption_style"]) or as the
studio default. `render_ass()` turns word timings + a style into an ASS subtitle file that
ffmpeg/libass burns into the video. English (VoiceAgent) and Hindi (HindiVoiceAgent) captions
both go through here when a style is set; with no style they keep their original built-in look.

Fonts are referenced by family name. The bundled ffmpeg resolves macOS system fonts by name,
and falls back per-glyph (e.g. Devanagari) when the chosen font lacks a script.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional

import config

# Fonts that ship with macOS and were verified to render through the bundled ffmpeg/libass.
FONTS: List[Dict[str, str]] = [
    {"name": "Impact", "label": "Impact (bold, tall)", "group": "Bold"},
    {"name": "Arial Black", "label": "Arial Black", "group": "Bold"},
    {"name": "Futura", "label": "Futura", "group": "Clean"},
    {"name": "Avenir Next", "label": "Avenir Next", "group": "Clean"},
    {"name": "Helvetica Neue", "label": "Helvetica Neue", "group": "Clean"},
    {"name": "Gill Sans", "label": "Gill Sans", "group": "Clean"},
    {"name": "Arial Rounded MT Bold", "label": "Arial Rounded", "group": "Clean"},
    {"name": "Georgia", "label": "Georgia (serif)", "group": "Serif"},
    {"name": "Didot", "label": "Didot (elegant serif)", "group": "Serif"},
    {"name": "Rockwell", "label": "Rockwell (slab)", "group": "Serif"},
    {"name": "American Typewriter", "label": "American Typewriter", "group": "Character"},
    {"name": "Copperplate", "label": "Copperplate", "group": "Character"},
    {"name": "Menlo", "label": "Menlo (monospace)", "group": "Character"},
    {"name": "Marker Felt", "label": "Marker Felt (handwritten)", "group": "Fun"},
    {"name": "Chalkduster", "label": "Chalkduster (chalk)", "group": "Fun"},
    {"name": "Bradley Hand", "label": "Bradley Hand (script)", "group": "Fun"},
    {"name": "Kohinoor Devanagari", "label": "Kohinoor Devanagari (Hindi)", "group": "Hindi"},
    {"name": "Devanagari Sangam MN", "label": "Devanagari Sangam MN (Hindi)", "group": "Hindi"},
]
FONT_NAMES = {f["name"] for f in FONTS}

DEFAULT_STYLE: Dict[str, Any] = {
    "enabled": True,
    "font": "Impact",
    "font_size": 84,
    "bold": True,
    "italic": False,
    "text_color": "#FFFFFF",
    "highlight_color": "#00F2FE",
    "highlight_mode": "pop",        # pop | color | none
    "pop_scale": 115,               # % size of the active word in "pop" mode
    "outline_color": "#000000",
    "outline_width": 8,
    "shadow": 4,
    "background": "none",           # none | box
    "box_color": "#000000",
    "box_opacity": 60,              # %
    "position": "auto",             # auto | top | middle | bottom
    "offset": 320,                  # px from the top/bottom edge (ignored for middle)
    "case": "upper",                # upper | original | lower | title
    "words_per_caption": 3,
    "letter_spacing": 2,
    "entrance": "none",             # none | fade | pop
}

PRESETS: Dict[str, Dict[str, Any]] = {
    "classic": {"label": "Classic Pop", "style": {}},
    "bold_yellow": {"label": "Bold Yellow", "style": {
        "font": "Arial Black", "font_size": 78, "highlight_color": "#FFD400", "outline_width": 7, "shadow": 3,
        "letter_spacing": 1}},
    "boxed": {"label": "Boxed", "style": {
        "font": "Avenir Next", "font_size": 70, "background": "box", "box_color": "#000000", "box_opacity": 70,
        "outline_width": 18, "shadow": 0, "highlight_mode": "color", "highlight_color": "#FFD400",
        "case": "original", "words_per_caption": 4, "letter_spacing": 0}},
    "minimal": {"label": "Minimal", "style": {
        "font": "Helvetica Neue", "font_size": 64, "bold": True, "highlight_mode": "none", "outline_width": 3,
        "shadow": 2, "case": "original", "words_per_caption": 5, "letter_spacing": 0, "entrance": "fade"}},
    "neon": {"label": "Neon", "style": {
        "font": "Futura", "font_size": 80, "text_color": "#E0FFFF", "highlight_color": "#FF2BD6",
        "outline_color": "#7A00FF", "outline_width": 5, "shadow": 0, "pop_scale": 125, "entrance": "pop"}},
    "documentary": {"label": "Documentary", "style": {
        "font": "Georgia", "font_size": 62, "bold": False, "highlight_mode": "none", "outline_width": 2,
        "shadow": 3, "case": "original", "words_per_caption": 6, "letter_spacing": 0, "position": "bottom",
        "offset": 220, "entrance": "fade"}},
    "one_word": {"label": "One Word", "style": {
        "font": "Impact", "font_size": 120, "words_per_caption": 1, "highlight_mode": "color",
        "highlight_color": "#FFFFFF", "position": "middle", "entrance": "pop", "letter_spacing": 3}},
    "handwritten": {"label": "Handwritten", "style": {
        "font": "Marker Felt", "font_size": 82, "bold": False, "case": "original", "highlight_color": "#FFB000",
        "outline_width": 6, "letter_spacing": 1}},
}

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
# Indic, Arabic and Thai scripts join letters into shaped clusters
_COMPLEX_SCRIPT = re.compile("[\u0600-\u06FF\u0900-\u0DFF\u0E00-\u0E7F]")
_CHOICES = {
    "highlight_mode": {"pop", "color", "none"},
    "background": {"none", "box"},
    "position": {"auto", "top", "middle", "bottom"},
    "case": {"upper", "original", "lower", "title"},
    "entrance": {"none", "fade", "pop"},
}
_RANGES = {
    "font_size": (30, 160), "pop_scale": (100, 160), "outline_width": (0, 30), "shadow": (0, 12),
    "box_opacity": (0, 100), "offset": (40, 900), "words_per_caption": (1, 8), "letter_spacing": (0, 12),
}


def preset_style(preset: str) -> Dict[str, Any]:
    style = dict(DEFAULT_STYLE)
    style.update(PRESETS.get(preset, PRESETS["classic"])["style"])
    style["preset"] = preset if preset in PRESETS else "classic"
    return style


def normalize_style(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate/clamp a user-supplied style; unknown or bad values fall back to defaults."""
    raw = raw or {}
    style = preset_style(raw.get("preset") or "classic") if raw.get("preset") in PRESETS else dict(DEFAULT_STYLE)
    for key, default in DEFAULT_STYLE.items():
        if key not in raw:
            continue
        val = raw[key]
        try:
            if key in _CHOICES:
                if val in _CHOICES[key]:
                    style[key] = val
            elif key in _RANGES:
                lo, hi = _RANGES[key]
                style[key] = int(max(lo, min(hi, round(float(val)))))
            elif key.endswith("_color"):
                m = _HEX.match(str(val).strip())
                if m:
                    style[key] = "#" + m.group(1).upper()
            elif isinstance(default, bool):
                style[key] = bool(val)
            elif key == "font":
                name = str(val).strip()
                if name in FONT_NAMES:
                    style[key] = name
        except (TypeError, ValueError):
            pass
    style["preset"] = raw.get("preset") if raw.get("preset") in PRESETS else "custom"
    return style


def ass_color(hex_color: str, opacity_pct: float = 100.0) -> str:
    """#RRGGBB + opacity% -> ASS &HAABBGGRR (ASS alpha: 00 opaque .. FF transparent)."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    alpha = int(round(255 * (1 - max(0.0, min(100.0, opacity_pct)) / 100.0)))
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _override_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def _transform_case(text: str, case: str) -> str:
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "title":
        return " ".join(w[:1].upper() + w[1:].lower() if w else w for w in text.split(" "))
    return text


def _escape(text: str) -> str:
    # Braces start override blocks in ASS; newlines would break the event line.
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\r", " ").replace("\n", " ").strip()


def _ts(seconds: float) -> str:
    td = timedelta(seconds=max(0.0, seconds))
    total = td.total_seconds()
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = total % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_header(style: Dict[str, Any]) -> str:
    w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    bold = -1 if style["bold"] else 0
    italic = -1 if style["italic"] else 0
    primary = ass_color(style["text_color"])
    secondary = ass_color(style["highlight_color"])
    boxed = style["background"] == "box"
    off = style["offset"]
    lines = []
    for name, align, margin_v in (("Bottom", 2, off), ("Top", 8, off), ("Middle", 5, 0)):
        if boxed:
            # The box is its own layer (Box*): one unbroken BorderStyle-3 box per caption. Drawing it
            # on the text runs instead gives one box per colour run, and semi-transparent overlaps
            # show up as dark bands between words. Text styles then carry no outline/box.
            lines.append(
                f"Style: Box{name},{style['font']},{style['font_size']},{ass_color('#000000', 0)},{secondary},"
                f"{ass_color(style['box_color'], style['box_opacity'])},{ass_color('#000000', 0)},"
                f"{bold},{italic},0,0,100,100,{style['letter_spacing']},0,3,{max(4, style['outline_width'])},0,"
                f"{align},70,70,{margin_v},1"
            )
            outline_col, outline, shadow = ass_color("#000000", 0), 0, 0
        else:
            outline_col, outline, shadow = ass_color(style["outline_color"]), style["outline_width"], style["shadow"]
        lines.append(
            f"Style: {name},{style['font']},{style['font_size']},{primary},{secondary},{outline_col},"
            f"{ass_color('#000000', 55)},{bold},{italic},0,0,100,100,{style['letter_spacing']},0,1,{outline},"
            f"{shadow},{align},70,70,{margin_v},1"
        )
    return (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        + "\n".join(lines)
        + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def render_ass(
    words: List[Dict[str, Any]],
    style: Dict[str, Any],
    placement_at: Optional[Callable[[float], str]] = None,
) -> str:
    """
    words: [{"text", "start", "end"}] in seconds. placement_at(t) -> "top"|"bottom" is used when
    the style's position is "auto" (scene-aware placement); otherwise the fixed position wins.
    """
    style = normalize_style(style)
    if any(_COMPLEX_SCRIPT.search(str(w.get("text", ""))) for w in words):
        # Letter spacing is inserted between the parts of a Devanagari/Indic cluster and breaks
        # its shaping (e.g. क्या renders as क्‌या), so it is turned off for these scripts.
        style["letter_spacing"] = 0
    header = build_header(style)
    if not style["enabled"] or not words:
        return header

    n = style["words_per_caption"]
    mode = style["highlight_mode"]
    text_c = _override_color(style["text_color"])
    hi_c = _override_color(style["highlight_color"])
    scale = style["pop_scale"] if mode == "pop" else 100
    active = rf"{{\c{hi_c}\fscx{scale}\fscy{scale}}}"
    normal = rf"{{\c{text_c}\fscx100\fscy100}}"
    events: List[str] = []

    def style_for(t: float) -> str:
        pos = style["position"]
        if pos == "auto":
            pos = (placement_at(t) if placement_at else "bottom") or "bottom"
            pos = "top" if pos == "top" else "bottom"
        return {"top": "Top", "middle": "Middle"}.get(pos, "Bottom")

    def entrance_tag() -> str:
        if style["entrance"] == "fade":
            return r"{\fad(160,0)}"
        if style["entrance"] == "pop":
            return r"{\fscx70\fscy70\t(0,140,\fscx100\fscy100)}"
        return ""

    boxed = style["background"] == "box"
    from app.agents.caption_chunker import chunk_words, display_text
    chunks = chunk_words(words, n)
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else None
        tokens = [_escape(_transform_case(display_text(w), style["case"])) for w in chunk]
        style_name = style_for((chunk[0]["start"] + chunk[-1]["end"]) / 2.0)
        chunk_end = min(chunk[-1]["end"] + 0.18, next_start) if next_start else chunk[-1]["end"] + 0.25
        if boxed:
            # One box for the whole caption, behind the text (layer 0); its text is invisible. It is
            # sized at the pop scale so the enlarged active word never sticks out of the box.
            # Height: the popped word is as tall as the line, so scale fully. Width: only one word
            # grows at a time, so widen by roughly that word's share of the caption.
            sy = scale
            sx = int(round(100 + (scale - 100) * min(1.0, 1.6 / len(chunk))))
            if style["entrance"] == "pop":
                box_scale = rf"{{\fscx{int(sx * 0.7)}\fscy{int(sy * 0.7)}\t(0,140,\fscx{sx}\fscy{sy})}}"
            else:
                box_scale = (r"{\fad(160,0)}" if style["entrance"] == "fade" else "") + rf"{{\fscx{sx}\fscy{sy}}}"
            events.append(
                f"Dialogue: 0,{_ts(chunk[0]['start'])},{_ts(max(chunk[0]['start'] + 0.1, chunk_end))},"
                f"Box{style_name},,0,0,0,,{box_scale}{{\\1a&HFF&}}{' '.join(tokens)}"
            )

        if mode == "none":
            line = entrance_tag() + normal + " ".join(tokens)
            events.append(f"Dialogue: 1,{_ts(chunk[0]['start'])},{_ts(max(chunk[0]['start'] + 0.1, chunk_end))},{style_name},,0,0,0,,{line}")
            continue

        for k, w in enumerate(chunk):
            start = w["start"]
            if k + 1 < len(chunk):
                end = min(w["end"] + 0.08, chunk[k + 1]["start"])
                if end <= start:
                    end = w["end"] + 0.08
            else:
                end = chunk_end
            parts = [(active if j == k else normal) + tok for j, tok in enumerate(tokens)]
            # Entrance animates the chunk once, on its first word, so later words don't re-trigger it
            line = (entrance_tag() if k == 0 else "") + " ".join(parts)
            events.append(f"Dialogue: 1,{_ts(start)},{_ts(max(start + 0.05, end))},{style_name},,0,0,0,,{line}")

    return header + "\n".join(events) + "\n"


def sample_words(text: str, start: float = 0.0, per_word: float = 0.38) -> List[Dict[str, Any]]:
    """Evenly timed words for previews."""
    out, t = [], start
    for tok in (text or "").split():
        out.append({"text": tok, "start": round(t, 3), "end": round(t + per_word * 0.9, 3)})
        t += per_word
    return out
