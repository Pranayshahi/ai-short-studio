"""
YouTube metadata guard: title / description / tags must never contain the creator's prompt.

Every place that produces or uploads metadata calls `clean_metadata()`:
  * pipeline.run (when a video is made)        * YouTubePublisher.build_complete_fields (before upload)
and Verify-video blocks publishing if `leaks()` still finds prompt text.

What counts as prompt text:
  * markdown request fields (**TOPIC:**, **TITLE:**, **VISUAL LAYOUT:** ...), "**" bold markers
  * production instructions (9:16, 1080 x 1920, "Create a ...", "Divide the ...", "Display ...",
    "LEFT COLUMN", "CONTENT ARRANGEMENT", resolution/format words)
  * any sentence that appears verbatim in the original pasted request
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

TITLE_MAX = 100
DESC_MAX = 4900
TAG_MAX_LEN = 30
TAGS_TOTAL_MAX = 460

_MD_FIELD = re.compile(r"\*\*\s*[A-Z][A-Z0-9 /&()-]{2,40}:\s*\*\*")          # **TOPIC:**
_PLAIN_FIELD = re.compile(r"(?m)^\s*(TOPIC|TITLE|VISUAL LAYOUT|CONTENT ARRANGEMENT|STYLE|FORMAT|LAYOUT|"
                          r"REQUIREMENTS|INSTRUCTIONS|OUTPUT|RULES)\s*:", re.I)
_INSTRUCTION_START = re.compile(
    r"^\s*(?:[-*•\d.)]+\s*)?(create|generate|make|design|divide|display|arrange|use|include|ensure|add|show|"
    r"place|render|produce|write|draw|keep|avoid|do not|don't|must|each|every|left column|right column)\b", re.I)
_PROMPT_MARKERS = re.compile(
    r"9\s*:\s*16|1080\s*[x×]\s*1920|1920\s*[x×]\s*1080|portrait format|vertical format|infographic|"
    r"\bleft column\b|\bright column\b|content arrangement|visual layout|museum catalogue|"
    r"\bprompt\b|\bhigh-resolution\b|\bphotorealistic\b|\b8k\b|\b4k\b|aspect ratio|\btext overlay\b", re.I)


def extract_request_fields(text: str) -> Dict[str, str]:
    """Pulls **TOPIC:** / **TITLE:** (or plain TOPIC:/TITLE:) out of a pasted request."""
    out: Dict[str, str] = {}
    for key in ("TITLE", "TOPIC"):
        m = (re.search(rf"\*\*\s*{key}\s*:\s*\*\*\s*(.+)", text or "")
             or re.search(rf"(?im)^\s*{key}\s*:\s*(.+)$", text or ""))
        if m:
            out[key.lower()] = re.sub(r"\*\*", "", m.group(1)).strip()
    return out


def subject_from_request(topic: str) -> str:
    """A short human subject for metadata: TOPIC field, else TITLE field, else the first clean clause."""
    fields = extract_request_fields(topic)
    if fields.get("topic"):
        return fields["topic"][:80]
    if fields.get("title"):
        return fields["title"][:80]
    first = re.sub(r"\*\*", "", str(topic or "")).strip().splitlines()[0] if topic else ""
    first = re.split(r"[.:;!?\n]|\s[–—-]\s", first)[0].strip()
    return first[:80] or "Military Technology"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _prompt_sentences(source_prompt: Optional[str]) -> List[str]:
    """Distinct sentences/lines of the original request (normalised, >= 5 words)."""
    if not source_prompt or len(source_prompt) < 60:
        return []
    parts = re.split(r"[\n.!?]+", re.sub(r"\*\*", "", source_prompt))
    return [_norm(p) for p in parts if len(_norm(p).split()) >= 5]


_SECTION_HEADER = re.compile(r"^\s*[A-Z][A-Z0-9 &/()'-]{2,40}:\s*$")   # "VISUAL STYLE:", "FINAL RESULT:"


def _allowed(source_prompt: Optional[str]) -> List[str]:
    """The request's own TOPIC/TITLE values are legitimate metadata (that's the subject)."""
    f = extract_request_fields(source_prompt or "")
    return [_norm(v) for v in f.values() if v]


def is_prompt_like(line: str, source_prompt: Optional[str] = None) -> bool:
    if not line or not line.strip():
        return False
    if _MD_FIELD.search(line) or _PLAIN_FIELD.search(line) or _SECTION_HEADER.match(line):
        return True
    if _INSTRUCTION_START.match(line) and len(line.split()) >= 4:
        return True
    if _PROMPT_MARKERS.search(line):
        return True
    n = _norm(re.sub(r"#\w+", "", line))
    if not source_prompt or len(n) < 12:
        return False
    if any(n == a or n in a for a in _allowed(source_prompt)):
        return False  # the subject itself (e.g. "Infantry Combat Vehicles")
    # Any line found verbatim in the pasted request is request text, however short
    if n in _norm(source_prompt):
        return True
    return any(len(sent) >= 25 and (sent in n or n in sent) for sent in _prompt_sentences(source_prompt) if len(n) >= 20)


def _strip_basic(text: str) -> str:
    text = re.sub(r"\*\*", "", text or "")
    return text.replace("<", "").replace(">", "")  # YouTube rejects angle brackets


def clean_title(title: str, subject: str, source_prompt: Optional[str] = None) -> str:
    t = _strip_basic(title).strip()
    # Keep only the part before a prompt-like segment (e.g. "...catalogue. Divide the infographic...")
    segments = re.split(r"(?<=[.!?:])\s+", t)
    kept = []
    for seg in segments:
        if is_prompt_like(seg, source_prompt):
            break
        kept.append(seg)
    t = " ".join(kept).strip(" :-–—|")
    t = re.sub(r"\s*#shorts\b", "", t, flags=re.I).strip()
    if len(t) < 6 or len(t) > 90 or is_prompt_like(t, source_prompt):
        t = subject
    return f"{t[:TITLE_MAX - 8].rstrip()} #Shorts"


def clean_description(description: str, subject: str, source_prompt: Optional[str] = None) -> str:
    lines = _strip_basic(description).splitlines()
    kept: List[str] = []
    for line in lines:
        if is_prompt_like(line, source_prompt):
            continue
        kept.append(line.rstrip())
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    if len(re.sub(r"#\w+", "", text).split()) < 8:  # nothing meaningful left
        text = f"{subject}: key facts in under a minute.\n\n{text}".strip()
    return text[:DESC_MAX]


def clean_tags(tags: List[str], subject: str, source_prompt: Optional[str] = None) -> List[str]:
    out: List[str] = []
    total = 0
    for t in list(tags or []) + [subject]:
        t = _strip_basic(str(t)).strip().lstrip("#").strip()
        if not t or len(t) > TAG_MAX_LEN or is_prompt_like(t, source_prompt) or "," in t:
            continue
        if t.lower() in (x.lower() for x in out):
            continue
        if total + len(t) + 1 > TAGS_TOTAL_MAX:
            break
        out.append(t)
        total += len(t) + 1
    return out


def clean_metadata(title: str, description: str, tags: List[str], topic: str) -> Tuple[str, str, List[str]]:
    """Returns (title, description, tags) with all prompt text removed. `topic` = the original request."""
    source_prompt = topic if topic and (len(topic) > 120 or "\n" in topic or "**" in topic) else None
    subject = subject_from_request(topic)
    return (clean_title(title, subject, source_prompt),
            clean_description(description, subject, source_prompt),
            clean_tags(tags, subject, source_prompt))


def leaks(title: str, description: str, tags: List[str], topic: str = "") -> List[str]:
    """Problems that would block publishing (used by Verify-video)."""
    source_prompt = topic if topic and (len(topic) > 120 or "\n" in topic or "**" in topic) else None
    problems = []
    if is_prompt_like(re.sub(r"#shorts", "", title or "", flags=re.I), source_prompt) or "**" in (title or ""):
        problems.append(f"title contains prompt text: {title[:80]!r}")
    if len(title or "") > TITLE_MAX:
        problems.append(f"title longer than {TITLE_MAX} characters")
    bad_lines = [l for l in (description or "").splitlines() if is_prompt_like(l, source_prompt) or "**" in l]
    if bad_lines:
        problems.append(f"description contains prompt text: {bad_lines[0][:80]!r}")
    if "<" in (description or "") or ">" in (description or "") or "<" in (title or "") or ">" in (title or ""):
        problems.append("angle brackets (YouTube rejects them)")
    bad_tags = [t for t in tags or [] if len(str(t)) > TAG_MAX_LEN or is_prompt_like(str(t), source_prompt)]
    if bad_tags:
        problems.append(f"tag(s) contain prompt text or are too long: {str(bad_tags[0])[:60]!r}")
    return problems
