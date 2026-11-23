"""
Official brand media: real press photos from the car maker's own newsroom, tried FIRST for car videos.

Owner's rule (2026-11-22): for every car video, check the car brand's official website for its images
first, then go to other sources (Wikimedia, Openverse, ...).

How it finds them without a per-site scraper:
  1. brand in the car name -> the brand's official newsroom/media sites (BRAND_SITES)
  2. the site's robots.txt -> sitemap(s) -> page URLs whose slug names the model (e.g. ".../the-new-bmw-i3-...")
  3. each matching page -> its photos (og:image, <img>, srcset), the 1920px variant preferred
Results use the same candidate format as ImageGeneratorAgent's other sources, so the usual source,
topic-match, pixel and content checks still run on them. Sitemap URL lists are cached for a day.

Usage note: manufacturer press photos are published for editorial/media use; the source page is kept
with every image (candidate["page_url"]) so the credit/terms can be checked.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

AGENT = "brand-media"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
CACHE_DIR = Path(__file__).resolve().parent.parent / "assets" / "data" / "brand_media_cache"
SITEMAP_TTL = 24 * 3600
TIMEOUT = 12

# brand word (lower-case, as it appears in the car name) -> official newsroom / media sites
BRAND_SITES: Dict[str, List[str]] = {
    "bmw": ["https://newsroom.bmwgroup.com", "https://www.press.bmwgroup.com"],
    "mini": ["https://newsroom.bmwgroup.com"],
    "rolls-royce": ["https://www.press.rolls-roycemotorcars.com", "https://newsroom.bmwgroup.com"],
    "porsche": ["https://newsroom.porsche.com"],
    "ferrari": ["https://www.ferrari.com"],
    "lamborghini": ["https://media.lamborghini.com", "https://www.lamborghini.com"],
    "audi": ["https://www.audi-mediacenter.com"],
    "volkswagen": ["https://www.volkswagen-newsroom.com"],
    "vw": ["https://www.volkswagen-newsroom.com"],
    "bentley": ["https://www.bentleymedia.com"],
    "bugatti": ["https://newsroom.bugatti.com", "https://www.bugatti.com"],
    "mercedes": ["https://group-media.mercedes-benz.com", "https://media.mercedes-benz.com"],
    "mercedes-benz": ["https://group-media.mercedes-benz.com", "https://media.mercedes-benz.com"],
    "mercedes-amg": ["https://group-media.mercedes-benz.com", "https://media.mercedes-benz.com"],
    "amg": ["https://group-media.mercedes-benz.com"],
    "mclaren": ["https://cars.mclaren.press", "https://www.mclaren.com"],
    "aston": ["https://media.astonmartin.com"],
    "koenigsegg": ["https://www.koenigsegg.com"],
    "pagani": ["https://www.pagani.com"],
    "rimac": ["https://www.rimac-automobili.com"],
    "lotus": ["https://media.lotuscars.com"],
    "jaguar": ["https://media.jaguar.com"],
    "land rover": ["https://media.landrover.com"],
    "range rover": ["https://media.landrover.com"],
    "volvo": ["https://www.media.volvocars.com"],
    "polestar": ["https://media.polestar.com"],
    "tesla": ["https://www.tesla.com"],
    "toyota": ["https://pressroom.toyota.com", "https://global.toyota"],
    "lexus": ["https://pressroom.lexus.com"],
    "nissan": ["https://global.nissannews.com", "https://usa.nissannews.com"],
    "honda": ["https://hondanews.com", "https://global.honda"],
    "acura": ["https://acuranews.com"],
    "mazda": ["https://news.mazdausa.com", "https://newsroom.mazda.com"],
    "subaru": ["https://media.subaru.com"],
    "mitsubishi": ["https://www.mitsubishi-motors.com"],
    "hyundai": ["https://www.hyundainews.com", "https://www.hyundai.news"],
    "kia": ["https://www.kiamedia.com", "https://worldwide.kia.com"],
    "genesis": ["https://www.genesisnewsusa.com"],
    "ford": ["https://media.ford.com"],
    "chevrolet": ["https://news.gm.com", "https://media.chevrolet.com"],
    "corvette": ["https://news.gm.com", "https://media.chevrolet.com"],
    "cadillac": ["https://news.gm.com", "https://media.cadillac.com"],
    "gmc": ["https://news.gm.com"],
    "dodge": ["https://media.stellantisnorthamerica.com"],
    "jeep": ["https://media.stellantisnorthamerica.com"],
    "alfa": ["https://www.media.stellantis.com"],
    "maserati": ["https://www.media.stellantis.com", "https://www.maserati.com"],
    "fiat": ["https://www.media.stellantis.com"],
    "peugeot": ["https://www.media.stellantis.com"],
    "renault": ["https://media.renaultgroup.com"],
    "alpine": ["https://media.renaultgroup.com"],
    "lucid": ["https://lucidmotors.com"],
    "rivian": ["https://rivian.com"],
    "byd": ["https://www.byd.com"],
    "tata": ["https://www.tatamotors.com"],
    "mahindra": ["https://www.mahindra.com"],
    "maruti": ["https://www.marutisuzuki.com"],
    "suzuki": ["https://www.globalsuzuki.com"],
}

# Slug words that never identify a model
_STOP = {"the", "new", "all", "and", "car", "cars", "edit", "with", "for", "series", "edition"}
_IMG_RE = re.compile(r"""https?://[^\s"'<>()]+?\.(?:jpe?g|webp|png)(?:\?[^\s"'<>()]*)?""", re.I)
_BAD_IMG = re.compile(r"(logo|icon|favicon|sprite|avatar|placeholder|banner-ad|social|share|flag|qr[-_]?code|"
                      r"x-post|facebook|linkedin|twitter|instagram|youtube|whatsapp|"
                      r"signature|portrait|headshot|\bteam\b|thumb(?:nail)?s?/)", re.I)


def _get(url: str, timeout: int = TIMEOUT) -> Optional[str]:
    if requests is None:
        return None
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.text
    except Exception:
        return None


def brand_sites(car_name: str) -> Tuple[Optional[str], List[str]]:
    low = f" {(car_name or '').lower()} "
    # longest brand first ("mercedes-amg" before "amg", "land rover" before "rover")
    for brand in sorted(BRAND_SITES, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(brand)}(?![a-z0-9])", low):
            return brand, BRAND_SITES[brand]
    return None, []


def model_tokens(car_name: str, brand: Optional[str]) -> List[str]:
    words = re.findall(r"[a-z0-9]+", (car_name or "").lower())
    brand_parts = set(re.findall(r"[a-z0-9]+", brand or ""))
    return [w for w in words if w not in brand_parts and w not in _STOP]


def _cache_path(site: str) -> Path:
    return CACHE_DIR / (re.sub(r"[^a-z0-9]+", "_", site.lower()).strip("_") + ".json")


def _sitemap_urls(site: str, max_sitemaps: int = 40, max_urls: int = 60000) -> List[Tuple[str, str]]:
    """All (page url, lastmod) pairs from the site's sitemaps; cached for a day."""
    cp = _cache_path(site)
    try:
        cached = json.loads(cp.read_text())
        if time.time() - cached.get("ts", 0) < SITEMAP_TTL:
            return [tuple(x) for x in cached.get("urls", [])]
    except Exception:
        pass

    roots: List[str] = []
    robots = _get(f"{site}/robots.txt") or ""
    for line in robots.splitlines():
        m = re.match(r"\s*sitemap:\s*(\S+)", line, re.I)
        if m:
            roots.append(m.group(1).strip())
    if not roots:
        roots = [f"{site}/sitemap.xml", f"{site}/sitemap_index.xml"]
    # English / global sitemaps first
    roots.sort(key=lambda u: (0 if re.search(r"/(global|en|com|int)(/|$|[-_.])", u) else 1))

    out: List[Tuple[str, str]] = []
    queue, seen, fetched = list(roots), set(), 0
    while queue and fetched < max_sitemaps and len(out) < max_urls:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        xml = _get(sm)
        fetched += 1
        if not xml or "<loc" not in xml:
            continue
        blocks = re.findall(r"<(sitemap|url)>(.*?)</\1>", xml, re.S | re.I)
        for kind, body in blocks:
            loc = re.search(r"<loc>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</loc>", body, re.S | re.I)
            if not loc:
                continue
            u = html.unescape(loc.group(1).strip())
            if kind.lower() == "sitemap":
                # news/press/article/photo sitemaps first; skip other languages when an English one exists
                pri = 0 if re.search(r"(news|press|post|article|release|photo|image|gallery|model)", u, re.I) else 1
                (queue.insert(0, u) if pri == 0 else queue.append(u))
            else:
                lm = re.search(r"<lastmod>\s*([^<]+)</lastmod>", body, re.I)
                out.append((u, lm.group(1).strip()[:10] if lm else ""))
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps({"ts": time.time(), "urls": out}))
    except Exception:
        pass
    return out


def _slug_has(url: str, tok: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", path) is not None


_FOREIGN = re.compile(r"/(?!en(?:-[a-z]{2})?/)[a-z]{2}(?:-[a-z]{2})?/")
_PRESS_KIT = re.compile(r"(?<![a-z])(new|premiere|launch|unveil|reveal|design|media|photo|imagery|gallery|"
                        r"images|assets|press-kit|world-premiere)(?![a-z])")
_NOT_PRODUCT = re.compile(r"(?<![a-z])(sales|quarter|quarterly|results|plant|production|statement|conference|"
                          r"marathon|award|awards|investing|investment|supply|partnership|keynote|streaming|"
                          r"satellite|employees|financial)(?![a-z])")


def find_model_pages(car_name: str, max_pages: int = 10) -> List[str]:
    """Newsroom pages about this model, best first: the model's launch press kit / photo pages beat
    trim-specific stories, English beats translations of the same story, product pages beat
    business news (sales, plants, awards) that only mention the car."""
    brand, sites = brand_sites(car_name)
    toks = model_tokens(car_name, brand)
    if not brand or not toks:
        return []
    # The model designator: the word with a number (i3, 911, f80) beats a platform/series name
    # ("BMW Neue Klasse i3" keyed on "neue" and found only generic Neue Klasse pages); else the first word
    key = next((t for t in toks if re.search(r"\d", t)), toks[0])
    scored: List[Tuple[int, str, str]] = []
    for site in sites:
        for url, lastmod in _sitemap_urls(site):
            if not _slug_has(url, key):
                continue
            path = urllib.parse.urlparse(url).path.lower()
            score = 20 + 3 * sum(1 for t in toks if t != key and _slug_has(url, t))  # other words: small bonus
            if _slug_has(url, brand.split()[0]):
                score += 3
            score += 6 * min(2, len(_PRESS_KIT.findall(path)))
            if _NOT_PRODUCT.search(path):
                score -= 12
            if _FOREIGN.search(path):
                score -= 15  # a translation of an English page we already rank
            scored.append((score, lastmod, url))
        if scored:
            break  # first official site that has the model wins
    # Model names get reused across generations (BMW i3 2013 hatchback / 2026 Neue Klasse sedan): keep only
    # pages from the current generation's era - within 2 years of the newest page about the model
    dated = [lm for _, lm, _ in scored if re.match(r"\d{4}-\d{2}", lm or "")]
    if dated:
        newest = max(dated)
        cutoff = f"{int(newest[:4]) - 2}{newest[4:]}"
        scored = [x for x in scored if not re.match(r"\d{4}-\d{2}", x[1] or "") or x[1] >= cutoff]
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    pages, seen = [], set()
    for _, _, u in scored:
        # the same story per region/language: /global/x/, /emea/en-ie/x-en-ie/, /apac/en-au/x/ -> "x"
        slug = urllib.parse.urlparse(u).path.lower().rstrip("/").rsplit("/", 1)[-1]
        norm = re.sub(r"-(en|de|fr|es|it|nl|pt|ja|zh|ko)(-[a-z]{2})?$", "", re.sub(r"\.html?$", "", slug))
        if norm in seen:
            continue
        seen.add(norm)
        pages.append(u)
        if len(pages) >= max_pages:
            break
    return pages


def _best_variant(urls: List[str]) -> List[str]:
    """Group size variants of the same photo ('500_X.jpg', '1920_X.jpg', 'X.jpg') and keep ~1920 px."""
    groups: Dict[str, List[Tuple[int, str]]] = {}
    for u in urls:
        name = urllib.parse.urlparse(u).path.rsplit("/", 1)[-1]
        m = re.match(r"^(\d{3,4})[_-](.+)$", name)
        size = int(m.group(1)) if m else 0
        stem = re.sub(r"[-_]\d{2,4}x\d{2,4}(?=\.)", "", m.group(2) if m else name).lower()
        groups.setdefault(stem, []).append((size, u))
    out = []
    for variants in groups.values():
        sized = [v for v in variants if v[0] >= 1280]
        if sized:
            out.append(min(sized)[1])           # smallest variant that is still >= 1280 px
        else:
            orig = [v for v in variants if v[0] == 0]
            out.append((orig or sorted(variants)[-1:])[0][1])  # original, else the largest
    return out


def _page_images(page_url: str, html_text: str) -> Tuple[str, List[Dict[str, str]]]:
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.S | re.I)
    og_t = re.search(r'property="og:title"\s+content="([^"]+)"', html_text, re.I)
    page_title = html.unescape((og_t.group(1) if og_t else (title_m.group(1) if title_m else "")).strip())
    page_title = re.sub(r"\s+", " ", page_title)

    alts: Dict[str, str] = {}
    for tag in re.findall(r"<img\b[^>]*>", html_text, re.I):
        alt = re.search(r'\balt="([^"]*)"', tag, re.I)
        for u in _IMG_RE.findall(html.unescape(tag)):
            alts[urllib.parse.urljoin(page_url, u)] = html.unescape(alt.group(1)) if alt else ""

    found = []
    og = re.findall(r'property="og:image(?::url)?"\s+content="([^"]+)"', html_text, re.I)
    for u in og + _IMG_RE.findall(html.unescape(html_text)):
        u = urllib.parse.urljoin(page_url, u)
        if _BAD_IMG.search(u) or u in found:
            continue
        found.append(u)
    imgs = []
    for u in _best_variant(found):
        imgs.append({"url": u, "alt": alts.get(u, "")})
    return page_title, imgs


def search_official_images(car_name: str, limit: int = 40) -> List[Dict[str, Any]]:
    """Official press photos of this car, in ImageGeneratorAgent candidate format ([] if none found)."""
    t0 = time.time()
    brand, sites = brand_sites(car_name)
    if not brand:
        return []
    pages = find_model_pages(car_name)
    # Collect each page's photos, then take them in turn (page 1 photo 1, page 2 photo 1, ...): one story's
    # gallery (e.g. a road trip) otherwise fills every scene and the launch kit's studio/interior shots are lost
    per_page: List[List[Dict[str, Any]]] = []
    seen = set()
    for page in pages:
        if time.time() - t0 > 90:
            break
        text = _get(page)
        if not text:
            continue
        page_title, imgs = _page_images(page, text)
        rows = []
        for im in imgs:
            if im["url"] in seen:
                continue
            seen.add(im["url"])
            rows.append({
                "title": f"{page_title} {im['alt']}".strip()[:200] or car_name,
                "url": im["url"],
                "page_url": page,
                # The page is about this model: say so, so the usual topic-match check can confirm it
                "description": f"Official {brand.title()} press photo: {car_name}. {im['alt']} ({page_title})"[:300],
                "categories": f"official manufacturer press image; {brand}",
                "license": f"Official {brand.title()} press image (editorial use; see source page)",
                "author": f"{brand.title()} (official newsroom)",
                "width": 0, "height": 0,
                "mime": "image/jpeg",
                "official_brand": True,
            })
        if rows:
            per_page.append(rows)
    results: List[Dict[str, Any]] = []
    i = 0
    while len(results) < limit and any(i < len(r) for r in per_page):
        for rows in per_page:
            if i < len(rows) and len(results) < limit:
                results.append(rows[i])
        i += 1
    print(f"[{AGENT}] {car_name}: {len(results)} official {brand.upper()} photos from {len(pages)} newsroom page(s) "
          f"in {time.time() - t0:.1f}s")
    return results


def official_text(car_name: str, max_pages: int = 8) -> str:
    """Plain text of the car maker's own press pages about this model (for the fact checker): the
    manufacturer's figures (0-100 time, charging power...) count as a source alongside Wikipedia."""
    out = []
    for page in find_model_pages(car_name, max_pages=max_pages):
        raw = _get(page) or ""
        raw = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", raw)
        txt = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
        out.append(re.sub(r"\s+", " ", txt).strip()[:60000])
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    name = " ".join(sys.argv[1:]) or "BMW i3 50 xDrive"
    print("pages:", *find_model_pages(name), sep="\n  ")
    for r in search_official_images(name, limit=10):
        print(r["url"], "|", r["title"][:80])
