"""
Web search (Tavily) - the FIRST research step of every video (owner's request 2026-11-23: "first check the
search engine and get results, then do the usual stuff").

search(query) -> [{'title', 'url', 'domain', 'content', 'score', 'reliability'}]
  - TAVILY_API_KEY from .env; results cached for a day (output/cache/web_search.json);
  - social / video / Q&A sites are skipped (not sources);
  - reliability: 'official' (.gov / .mil / manufacturers / defence ministries), 'reference' (encyclopedias,
    established news / defence media), else 'web'.
corroborated_sentences(results, reference_text) keeps only sentences whose numbers are confirmed by a SECOND
independent site or by the reference text (Wikipedia) - one site saying it isn't enough (owner's rule:
correct data or nothing).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

import config

SKIP_DOMAINS = re.compile(r"(?:^|\.)(?:youtube\.com|youtu\.be|tiktok\.com|instagram\.com|facebook\.com|pinterest\.\w+|"
                          r"quora\.com|reddit\.com|x\.com|twitter\.com|linkedin\.com|threads\.net|scribd\.com|"
                          r"amazon\.\w+|ebay\.\w+|aliexpress\.com|fandom\.com)$", re.I)
# official = government / military domains (mod.gov.in, af.mil, army.mod.uk) or the maker's own site;
# a private site merely NAMED 'defence.in' is not official
OFFICIAL = re.compile(r"\.(?:gov|mil)(?:\.\w\w)?$|\.(?:mod|gov|mil)\.\w\w$|"
                      r"(?:^|\.)(?:lockheedmartin|northropgrumman|boeing|raytheon|rtx|baesystems|rheinmetall|saab|"
                      r"thalesgroup|airbus|leonardo|kmweg|generaldynamics|gd|hanwha|elbitsystems|rafael|iai|"
                      r"bmw|bmwgroup|press\.bmwgroup|mercedes-benz|porsche|ferrari|lamborghini|mclaren|toyota|"
                      r"mahindra|tatamotors|hyundai|kia|audi|volkswagen|ford|gm|tesla|bugatti|koenigsegg)"
                      r"(?:bharat|india|usa|uk|global|group|media|newsroom|press)?\.\w+",  # toyotabharat.com, bmwgroup.com
                      re.I)
REFERENCE = re.compile(r"(?:^|\.)(?:wikipedia\.org|britannica\.com|reuters\.com|apnews\.com|bbc\.\w+|"
                       r"janes\.com|defensenews\.com|armyrecognition\.com|militarytoday\.com|globalsecurity\.org|"
                       r"thedrive\.com|airforce-technology\.com|army-technology\.com|naval-technology\.com|"
                       r"caranddriver\.com|motortrend\.com|topgear\.com|autocar\.\w+|carwow\.\w+)$", re.I)


def _cache_file() -> Path:
    d = Path(config.OUTPUT_DIR) / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / "web_search.json"


def available() -> bool:
    return bool(os.getenv("TAVILY_API_KEY", "").strip())


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")


def reliability(domain: str) -> str:
    if OFFICIAL.search(domain):
        return "official"
    if REFERENCE.search(domain):
        return "reference"
    return "web"


def search(query: str, max_results: int = 8, depth: str = "advanced", ttl: float = 86400) -> List[Dict[str, Any]]:
    """Tavily web search; [] when no key / offline / error (research then continues as usual)."""
    key = os.getenv("TAVILY_API_KEY", "").strip()
    query = re.sub(r"\s+", " ", query or "").strip()[:380]
    if not key or not query:
        return []
    ck = hashlib.sha1(f"{query}|{max_results}|{depth}".encode()).hexdigest()
    try:
        cache = json.loads(_cache_file().read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    hit = cache.get(ck)
    if hit and time.time() - hit.get("at", 0) < ttl:
        return hit["results"]
    import requests
    try:
        r = requests.post("https://api.tavily.com/search", timeout=30, json={
            "api_key": key, "query": query, "max_results": max_results, "search_depth": depth,
            "include_answer": False, "include_raw_content": False})
        if r.status_code != 200:
            print(f"[WebSearch] Tavily HTTP {r.status_code} for '{query[:60]}'")
            return []
        data = r.json()
    except Exception as e:
        print(f"[WebSearch] Tavily unavailable ({e}); research continues without it")
        return []
    out = []
    for it in data.get("results") or []:
        url = it.get("url") or ""
        dom = _domain(url)
        if not url or SKIP_DOMAINS.search(dom):
            continue
        out.append({"title": (it.get("title") or "").strip()[:200], "url": url, "domain": dom,
                    "content": re.sub(r"\s+", " ", it.get("content") or "").strip()[:2000],
                    "score": float(it.get("score") or 0), "reliability": reliability(dom)})
    cache[ck] = {"at": time.time(), "results": out}
    try:
        if len(cache) > 500:  # keep the newest entries
            cache = dict(sorted(cache.items(), key=lambda kv: kv[1].get("at", 0))[-400:])
        _cache_file().write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass
    return out


def search_images(query: str, max_results: int = 8) -> List[Dict[str, Any]]:
    """[{'url', 'description', 'domain'}] image results for a query. LICENCE UNKNOWN: web images are not
    free to reuse by default - callers must confirm the licence (or the owner's permission) before an image
    goes into a video."""
    key = os.getenv("TAVILY_API_KEY", "").strip()
    query = re.sub(r"\s+", " ", query or "").strip()[:380]
    if not key or not query:
        return []
    import requests
    try:
        r = requests.post("https://api.tavily.com/search", timeout=30, json={
            "api_key": key, "query": query, "max_results": max_results, "include_images": True,
            "include_image_descriptions": True, "search_depth": "basic"})
        data = r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"[WebSearch] Tavily images unavailable ({e})")
        return []
    out = []
    for im in data.get("images") or []:
        url = im if isinstance(im, str) else im.get("url")
        if url and not SKIP_DOMAINS.search(_domain(url)):
            out.append({"url": url, "description": "" if isinstance(im, str) else (im.get("description") or ""),
                        "domain": _domain(url), "license": "unknown"})
    return out


# Page chrome / listicle framing / uncertain wording: never a fact
_JUNK = re.compile(r"\[\.\.\.\]|\.\.\.|#|loading|read more|click|subscribe|cookie|sign up|here are|key takeaways|"
                   r"summary|\bfaq\b|top \d+ facts|\d+ facts|in this article|we (?:will|have)|you (?:can|will)|"
                   r"claim|estimat|report(?:ed|edly)|allegedly|rumou?r|expected to|could be|may be|might|"
                   r"speculat|unconfirmed|approx", re.I)


def _clean_text(t: str) -> str:
    """Tavily 'content' snippets carry markdown and page fragments: drop headings, links and list marks."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t or "")      # [text](link) -> text
    t = re.sub(r"(?:^|\s)#{1,6}\s+[^.!?]*?(?=\s[A-Z]|$)", " ", t)  # '## Engine & Transmission' headings
    t = re.sub(r"\s+[|•*]\s+", ". ", t)
    return re.sub(r"\s+", " ", t).strip()


def _confirmed(v: float, fam, raw: str, sent: str, others, ref_pool, other_text: str) -> bool:
    """A number with a unit: the same quantity elsewhere. A bare number ('12 variants', 'in 2004'): the same
    number followed by the same word elsewhere ('12' alone appears everywhere)."""
    from agents import fact_check as fc
    if fam:
        return fc.number_supported(v, others, fam) or fc.number_supported(v, ref_pool, fam)
    m = re.search(rf"{re.escape(raw)}\s*[-–]?\s*([A-Za-z]{{3,}})", sent)
    if m and not re.fullmatch(r"(?:and|the|of|in|on|to|for|with|from|at|by|or|as)", m.group(1), re.I):
        stem = m.group(1).lower().rstrip("s")
        return bool(re.search(rf"(?<![\d.,]){re.escape(raw)}\s*[-–]?\s*{re.escape(stem)}", other_text, re.I))
    return bool(re.search(rf"(?<![\d.,]){re.escape(raw)}(?![\d.,]\d)", other_text))


def corroborated_sentences(results: List[Dict[str, Any]], reference_text: str = "", limit: int = 12) -> List[str]:
    """Sentences from the web results that are safe to use: on-topic, and every number in them is stated
    by another independent site or by the reference text. Official sites' sentences without numbers pass."""
    from agents import fact_check as fc
    ref_pool = fc.numbers(reference_text or "")
    out: List[str] = []
    for i, r in enumerate(results):
        if fc.off_domain(f"{r['title']}. {r['content'][:300]}"):
            continue
        other_text = " ".join(x["content"] for j, x in enumerate(results) if j != i and x["domain"] != r["domain"])
        others = fc.numbers(other_text)
        for sent in re.split(r"(?<=[.!?])\s+", _clean_text(r["content"])):
            sent = sent.strip(" +-•*")
            if not (30 <= len(sent) <= 260) or fc.off_domain(sent) or sent in out or _JUNK.search(sent):
                continue
            nums = fc.numbers(sent)
            if nums:
                if not all(_confirmed(v, f, raw, sent, others, ref_pool, other_text + " " + (reference_text or ""))
                           for v, f, raw in nums):
                    continue  # a single site's number is never enough
            elif r["reliability"] == "web":
                continue  # plain claims only from official / reference sites
            out.append(sent)
            if len(out) >= limit:
                return out
    return out
