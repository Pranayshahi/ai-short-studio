"""
Caption chunking shared by every subtitle writer (built-in ASS, styled ASS, SRT, Hindi).

TTS engines return bare words ("apart", "It") with no punctuation, so captions used to be cut
every N words regardless of meaning: "F-35 LIGHTNING / II APART IT IS". This module:

1. attach_punctuation(): re-aligns the spoken words with the script text and stores each word's
   trailing punctuation in w["punct"] (the word's "text" is left untouched).
2. mark_phrases(): flags words inside a protected name (the video's subject, e.g. "F-35 Lightning II")
   with w["join_next"] so a caption never splits it.
3. chunk_words(): groups words into captions of about N words, breaking at sentence ends and
   commas, never inside a protected name, and without leaving a single dangling word before a
   sentence end.
"""

import re
from typing import Any, Dict, Iterable, List, Optional

_SENTENCE_END = set(".!?;:\u0964\u0965")  # incl. Hindi danda । ॥
_ALNUM = re.compile("[^0-9a-z\u0900-\u0963\u0966-\u097f]+")  # letters/digits incl. Devanagari, not the danda


def _norm(text: str) -> str:
    return _ALNUM.sub("", str(text or "").lower())


def _trailing_punct(token: str) -> str:
    m = re.search("(?:[^\\w\u0900-\u097f%]|[\u0964\u0965])+$", token)
    return m.group(0) if m else ""


def attach_punctuation(words: List[Dict[str, Any]], full_text: str) -> List[Dict[str, Any]]:
    """Sets w["punct"] for each word from the script text. Robust to words the TTS split or merged."""
    src = [t for t in (full_text or "").split() if t]
    j = 0
    for w in words:
        w["punct"] = ""
    i = 0
    while i < len(words) and j < len(src):
        w = words[i]
        wn = _norm(w.get("text"))
        if not wn:
            i += 1
            continue
        # Skip pure-punctuation source tokens ("—"), giving their mark to the previous word
        while j < len(src) and not _norm(src[j]):
            if i > 0:
                words[i - 1]["punct"] += src[j].strip()
            j += 1
        if j >= len(src):
            break
        sn = _norm(src[j])
        if sn == wn:
            w["punct"] = _trailing_punct(src[j])
            i += 1
            j += 1
            continue
        if sn.startswith(wn):
            # The TTS split one written token into several spoken words ("don't" -> "do", "n't")
            acc, k = wn, i + 1
            while k < len(words) and len(acc) < len(sn):
                acc += _norm(words[k].get("text"))
                k += 1
            if acc == sn:
                words[k - 1]["punct"] = _trailing_punct(src[j])
                i, j = k, j + 1
                continue
        if wn.startswith(sn):
            # The TTS merged several written tokens into one spoken word
            acc, k = sn, j + 1
            while k < len(src) and len(acc) < len(wn):
                acc += _norm(src[k])
                k += 1
            if acc == wn:
                w["punct"] = _trailing_punct(src[k - 1])
                i, j = i + 1, k
                continue
        # Mismatch: look a few tokens ahead in the source for this word, else leave it bare
        for look in range(1, 4):
            if j + look < len(src) and _norm(src[j + look]) == wn:
                j += look
                break
        else:
            i += 1
            continue
    return words


def mark_phrases(words: List[Dict[str, Any]], phrases: Iterable[Optional[str]]) -> List[Dict[str, Any]]:
    """Flags words inside any protected phrase so chunk_words() keeps the phrase on one caption."""
    norms = [_norm(w.get("text")) for w in words]
    for phrase in phrases:
        toks = [t for t in (_norm(x) for x in str(phrase or "").split()) if t]
        if len(toks) < 2:
            continue
        n = len(toks)
        for i in range(len(words) - n + 1):
            if norms[i:i + n] == toks:
                for k in range(i, i + n - 1):
                    words[k]["join_next"] = True
    return words


def chunk_words(words: List[Dict[str, Any]], max_words: int = 3) -> List[List[Dict[str, Any]]]:
    max_words = max(1, int(max_words or 3))
    hard_cap = max_words + 3  # a long protected name may stretch a caption a little
    chunks: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    for i, w in enumerate(words):
        cur.append(w)
        punct = w.get("punct") or ""
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None:
            break
        if w.get("join_next") and len(cur) < hard_cap:
            continue
        sentence_end = any(c in _SENTENCE_END for c in punct)
        comma = "," in punct
        if sentence_end or (comma and len(cur) >= 2):
            chunks.append(cur)
            cur = []
            continue
        if len(cur) >= max_words:
            # Don't strand one word before a sentence end ("... LIGHTNING II / APART.")
            # (also keeps "AS OF APRIL 2026," together instead of "AS OF APRIL / 2026 THE US")
            nxt_ends = any(c in _SENTENCE_END or c == "," for c in (nxt.get("punct") or ""))
            if max_words > 1 and nxt_ends and len(cur) < hard_cap:
                continue
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def _with_punct(w: Dict[str, Any], keep: Optional[str] = None) -> str:
    """The word plus its restored punctuation, without doubling marks the TTS already left on the
    word itself (Kokoro sometimes returns "F-35C." as the word: "F-35C" + "." gave "F-35C..").
    keep: only these marks are shown (captions keep '?' and '!'); an abbreviation's dot ("U.S.") stays."""
    text = str(w.get("text", ""))
    tail = _trailing_punct(text)
    base = text[: len(text) - len(tail)] if tail else text
    marks = w.get("punct") or ""
    if len(tail) > len(marks):
        marks = tail
    abbrev_dot = "." if (marks.startswith(".") and "." in base) else ""
    if keep is not None:
        marks = abbrev_dot + "".join(c for c in marks if c in keep)
    return f"{base}{marks}"


def display_text(w: Dict[str, Any]) -> str:
    """Caption text for a word: keeps '?' and '!' (they change meaning); periods/commas are dropped."""
    return _with_punct(w, keep="?!")


def prepare(words: List[Dict[str, Any]], full_text: str, phrases: Iterable[Optional[str]] = ()) -> List[Dict[str, Any]]:
    attach_punctuation(words, full_text)
    mark_phrases(words, phrases)
    return words


def to_srt(words: List[Dict[str, Any]], max_words: int = 7) -> str:
    def ts(t: float) -> str:
        ms = int(round(max(0.0, t) * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    cues = []
    for grp in chunk_words(words, max_words):
        text = " ".join(_with_punct(w) for w in grp)
        cues.append(f"{len(cues) + 1}\n{ts(grp[0]['start'])} --> {ts(grp[-1]['end'])}\n{text}\n")
    return "\n".join(cues)


def subject_phrases(script_data: Dict[str, Any]) -> List[str]:
    """Names a caption must not split: the subject and its short core form."""
    out = []
    for key in ("topic_subject", "topic", "subject"):
        v = script_data.get(key)
        if v:
            out.append(str(v))
    try:
        from agents.subject_match import subject_core
        out += [subject_core(v) for v in list(out)]
    except Exception:
        pass
    return [p for p in dict.fromkeys(out) if p]
