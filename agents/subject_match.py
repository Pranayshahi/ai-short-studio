"""
Shared "what exactly is this video about?" helpers.

A topic like "Colt Canada C25 – Canada's Next-Generation Assault Rifle" has a core subject
("Colt Canada C25") and a model designator ("C25"). When a topic names a specific model, research
facts and images must mention that designator: a generic "assault rifle" photo or an article about
a different rifle is not a match, however many other words it shares with the title.
"""

from __future__ import annotations

import re
from typing import List

_EMOJI = re.compile(r"[\U00010000-\U0010ffff☀-⟿]")
# Subtitle separators: dashes surrounded by spaces, colon, pipe
_SUBTITLE_SPLIT = re.compile(r"\s+[–—-]\s+|\s*[:|]\s+|\s*[–—]\s*")
# Letters+digits tokens like C25, F-22, AK-47, M4A1, 92FS, T-90M, Su-57
_DESIGNATOR = re.compile(r"(?<![\w.-])([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)(?![\w-])")
# Ordinals, units and calibres are not model names (6th, 30mm, 5.56x45mm, 2026s)
_NOT_DESIGNATOR = re.compile(r"^\d+(st|nd|rd|th|s|mm|cm|km|kg|lb|lbs|m|x|k|g|ft|hp|v|kt|nm)$|^\d+x\d+\w*$|mm$", re.IGNORECASE)


def subject_core(topic: str) -> str:
    """'Colt Canada C25 – Canada's Next-Generation Assault Rifle' -> 'Colt Canada C25'."""
    s = _EMOJI.sub("", str(topic or "")).strip()
    s = re.sub(r"#\w+", "", s).strip()
    core = _SUBTITLE_SPLIT.split(s, maxsplit=1)[0].strip(" -–—:|")
    core = re.sub(r"^(the|an|a)\s+", "", core, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", core).strip() or s


def designators(text: str) -> List[str]:
    """Model designators in the text, as written (e.g. ['C25'], ['F-22'], ['AK-47'])."""
    out: List[str] = []
    for m in _DESIGNATOR.finditer(text or ""):
        tok = m.group(1)
        if not re.search(r"[A-Za-z]", tok) or not re.search(r"\d", tok) or len(tok) > 10:
            continue
        if _NOT_DESIGNATOR.match(tok):
            continue
        if tok not in out:
            out.append(tok)
    return out


def _norm(text: str) -> str:
    # Join hyphenated designators (F-22 == F22), treat _ and / as spaces (file names, URLs)
    t = str(text or "").lower().replace("_", " ").replace("/", " ")
    return re.sub(r"(?<=[a-z0-9])[-‐‑](?=[a-z0-9])", "", t)


def mentions(text: str, designator: str) -> bool:
    """True when the text names this designator as a whole token (C25 ≠ C250, F-22 == F22)."""
    d = re.escape(_norm(designator))
    # A variant letter suffix still names the model (F-22A, F-35B), a longer number does not (C250)
    return bool(re.search(rf"(?<![a-z0-9]){d}[a-z]{{0,2}}(?![a-z0-9])", _norm(text)))


def mentions_any(text: str, desigs: List[str]) -> bool:
    return any(mentions(text, d) for d in desigs)


def brand_words(core: str, desigs: List[str]) -> List[str]:
    """Words of the core subject other than its designators ('Colt Canada C25' -> ['Colt', 'Canada'])."""
    rest = core
    for d in desigs:
        rest = re.sub(rf"(?<![\w-]){re.escape(d)}(?![\w-])", " ", rest)
    return [w for w in re.findall(r"[A-Za-z][A-Za-z'&.]+", rest) if len(w) > 1]
