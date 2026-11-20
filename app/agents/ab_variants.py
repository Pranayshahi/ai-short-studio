"""
A/B test kit for YouTube Studio's "Test & compare": 3 title variants and 3 thumbnail variants per video.
YouTube's API can't create the test, so the kit is shown in the video's publish panel to copy/download.

Titles are built from the video's own facts (subject, specs, chart rows) - no invented claims - and go
through the same prompt-leak guard as normal titles. Thumbnails: the sharpest scene images (or the chart)
with a bold title treatment, 1080x1920.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920


def _font(size: int):
    for p in ("/System/Library/Fonts/Supplemental/Impact.ttf", "/System/Library/Fonts/Supplemental/Arial Black.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _subject(project: Dict[str, Any]) -> str:
    plan = project.get("car_edit_plan") or {}
    return (plan.get("car_name") or (project.get("content_analysis") or {}).get("topic_subject")
            or project.get("topic") or "").strip()


def title_variants(project: Dict[str, Any]) -> List[str]:
    subject = _subject(project)
    base = re.sub(r"\s*#\S+", "", project.get("title") or subject).strip()
    is_car = project.get("style") == "car_edit" or project.get("is_car_edit")
    spec = ((project.get("car_edit_plan") or {}).get("subtitle_spec") or "").strip()
    rows = [it.get("name") for r in (project.get("visual_records") or [])[:1] for it in (r.get("ranked_items") or [])]
    cands = [base]
    if is_car:
        if spec and spec.upper() not in ("PERFORMANCE EDITION · PURE ENGINEERING", "") and spec.upper() not in base.upper():
            cands.append(f"{subject}: {spec}")
        cands.append(f"{subject} | Built for the track")
        cands.append(f"The {subject} in 20 seconds")
    elif rows:
        cands.append(f"{len(rows)} {subject} compared")
        cands.append(f"{rows[0]} vs {rows[-1]}: {subject}")
        cands.append(f"{subject} ranked, side by side")
    else:
        cands.append(f"{subject}: what makes it different")
        cands.append(f"{subject} explained in seconds")
    tag = " #Shorts"
    out, seen = [], set()
    try:
        from agents.youtube_metadata import leaks
    except Exception:
        leaks = None
    for c in cands:
        c = re.sub(r"\s+", " ", c).strip()[: 100 - len(tag)] + tag
        if c.lower() in seen or (leaks and leaks(c, "", [], project.get("topic") or "")):
            continue
        seen.add(c.lower())
        out.append(c)
    return out[:3]


def _treat(img: Image.Image, headline: str, sub: str, style: int) -> Image.Image:
    img = img.convert("RGB").resize((W, H))
    if style == 1:  # dark gradient band at the bottom + huge headline
        band = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(band)
        for y in range(H // 2, H):
            d.line([(0, y), (W, y)], fill=int(220 * (y - H // 2) / (H // 2)))
        img = Image.composite(Image.new("RGB", (W, H), (5, 8, 15)), img, band)
    elif style == 2:  # punchy: slight zoom, contrast, top band
        img = img.crop((60, 100, W - 60, H - 100)).resize((W, H))
        from PIL import ImageEnhance
        img = ImageEnhance.Contrast(img).enhance(1.18)
    d = ImageDraw.Draw(img)
    words = headline.upper()
    size = 150 if len(words) <= 12 else (118 if len(words) <= 20 else 92)
    f = _font(size)
    lines, cur = [], ""
    for w in words.split():
        test = f"{cur} {w}".strip()
        if d.textlength(test, font=f) > W - 100 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    lines.append(cur)
    y0 = int(H * (0.70 if style != 2 else 0.08))
    for i, ln in enumerate(lines[:3]):
        d.text((W // 2, y0 + i * int(size * 1.05)), ln, font=f, fill=(255, 214, 0) if i == len(lines[:3]) - 1 else (255, 255, 255),
               anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0))
    if sub:
        fs = _font(54)
        d.text((W // 2, y0 + len(lines[:3]) * int(size * 1.05) + 20), sub.upper()[:40], font=fs, fill=(0, 229, 255),
               anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
    return img


def thumbnail_variants(project: Dict[str, Any]) -> List[Path]:
    from app.agents.thumbnail import _scene_images, sharpness
    out_dir = Path(project["project_dir"]) / "ab_variants"
    out_dir.mkdir(parents=True, exist_ok=True)
    # the clean photo (car scenes keep their in-video title overlay baked into scene_XX.png)
    imgs = [p.with_name(p.stem + "_base.png") if p.with_name(p.stem + "_base.png").exists() else p
            for p in _scene_images(project)]
    if not imgs:
        return []
    recs = project.get("visual_records") or []
    if recs and all(r.get("source") == "weaponx_lab_poster" for r in recs):
        # A chart already has its title header: no headline stamped over its rows. Variants = the full chart
        # and two zoomed crops where the first rows read larger at thumbnail size.
        chart = Image.open(imgs[0]).convert("RGB").resize((W, H))
        n_rows = len((recs[0].get("ranked_items") or []))
        subject = _subject(project).upper()
        variants = [chart]
        # B: huge two-line headline above a slightly smaller chart (reads at thumbnail size)
        b = Image.new("RGB", (W, H), "white")
        small = chart.resize((int(W * 0.80), int(H * 0.80)), Image.Resampling.LANCZOS)
        b.paste(small, ((W - small.width) // 2, H - small.height - 20))
        d = ImageDraw.Draw(b)
        f = _font(118 if len(subject) <= 18 else 92)
        words, lines, cur = subject.split(), [], ""
        for w in words:
            t = f"{cur} {w}".strip()
            if d.textlength(t, font=f) > W - 80 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines.append(cur)
        for i, ln in enumerate(lines[:2]):
            d.text((W // 2, 120 + i * 130), ln, font=f, fill=(15, 15, 15) if i == 0 else (214, 26, 44), anchor="mm")
        variants.append(b)
        # C: dark backdrop, chart framed, bold banner
        c = Image.new("RGB", (W, H), (10, 14, 22))
        mid = chart.resize((int(W * 0.86), int(H * 0.86)), Image.Resampling.LANCZOS)
        c.paste(mid, ((W - mid.width) // 2, 40))
        d = ImageDraw.Draw(c)
        banner = f"{n_rows} WEAPONS COMPARED" if n_rows else subject
        d.rectangle((0, H - 200, W, H), fill=(214, 26, 44))
        d.text((W // 2, H - 100), banner, font=_font(96), fill=(255, 255, 255), anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0))
        variants.append(c)
        paths = []
        for i, im in enumerate(variants, 1):
            out = out_dir / f"thumb_{i}.jpg"
            im.save(out, "JPEG", quality=92)
            paths.append(out)
        return paths
    ranked = sorted(imgs[:8], key=lambda p: -sharpness(p))
    picks = (ranked + ranked * 2)[:3]  # a single chart/poster gets three treatments
    subject = _subject(project)
    spec = ((project.get("car_edit_plan") or {}).get("subtitle_spec") or "")
    subs = [spec, "", "WATCH TILL THE END"]
    paths = []
    for i, src in enumerate(picks, 1):
        out = out_dir / f"thumb_{i}.jpg"
        _treat(Image.open(src), subject, subs[i - 1], i).save(out, "JPEG", quality=92)
        paths.append(out)
    return paths


def build(project: Dict[str, Any]) -> Dict[str, Any]:
    return {"titles": title_variants(project), "thumbnails": [str(p) for p in thumbnail_variants(project)]}
