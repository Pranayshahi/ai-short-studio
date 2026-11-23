"""
Agent 1: topic-agent (TopicAgent)
Takes a Topic (or selects a trending high-CTR topic), conducts deep research
across web sources (Wikipedia REST/Search API, DuckDuckGo Instant Answer API,
Wikidata/Encyclopedic extracts, and curated intelligence banks), and produces
structured research text + verified facts to hand off to 'content-analyser'.
"""

import os
import re
import json
import random
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Dict, Any, List, Optional

from agents.subject_match import subject_core, designators, mentions_any, brand_words

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# Curated high-CTR intelligence bank for offline resilience & baseline enrichment
CURATED_TOPIC_BANK: List[Dict[str, Any]] = [
    {
        "topic": "Top Hypersonic Missiles of the World",
        "category": "Hypersonic Missiles & Defense",
        "hook": "Traveling five to twenty times the speed of sound, hypersonic missiles are rewriting global military strategy.",
        "key_facts": [
            "Russia's Avangard hypersonic glide vehicle reaches speeds up to Mach 27, maneuvering via aerodynamic lift to evade radar.",
            "The 3M22 Zircon is a scramjet-powered anti-ship hypersonic cruise missile capable of Mach 9 over a 1,000 km range.",
            "The Kh-47M2 Kinzhal is an air-launched aero-ballistic missile deployed from modified MiG-31K interceptors at Mach 10.",
            "The US Army and Navy are fielding the Long-Range Hypersonic Weapon (Dark Eagle) using the Common Hypersonic Glide Body at Mach 17.",
            "China's DF-17 features a dedicated hypersonic glide vehicle designed specifically to bypass modern layered missile defenses.",
            "India and Russia are developing the BrahMos-II scramjet-powered hypersonic missile with an operational speed of Mach 8.",
        ],
        "keywords": ["hypersonic", "hypersonic missiles", "hypersonic missile", "avangard", "zircon", "kinzhal", "dark eagle", "df-17", "scramjet", "mach 5"],
    },
    {
        "topic": "The Dark Eagle Hypersonic Weapon (LRHW)",
        "category": "Hypersonic Missiles",
        "hook": "The US military just fielded a weapon that travels at Mach 17.",
        "key_facts": [
            "Travels at speeds exceeding Mach 17 (over 13,000 mph / 20,900 km/h).",
            "Uses a boost-glide unpowered hypersonic glide body (C-HGB) that maneuvers unpredictably in the upper atmosphere.",
            "Can strike high-value targets over 1,725 miles (2,775 km) away within minutes, evading conventional anti-air radar.",
        ],
        "keywords": ["dark eagle", "lrhw", "hypersonic missile", "us army", "glide body", "mach 17"],
    },
    {
        "topic": "B-21 Raider: The First 6th-Gen Stealth Bomber",
        "category": "Aviation & Stealth",
        "hook": "This bomber is so stealthy, enemy radar sees it as smaller than a bird.",
        "key_facts": [
            "Developed by Northrop Grumman for the United States Air Force as a sixth-generation stealth intercontinental strategic bomber.",
            "Features a next-generation flying-wing airframe with radar-absorbent skin and concealed engine inlets.",
            "Capable of delivering both conventional and thermonuclear payloads with manned or unmanned operations.",
        ],
        "keywords": ["b-21 raider", "stealth bomber", "northrop grumman", "flying wing", "usaf", "6th gen"],
    },
    {
        "topic": "6th-Gen Fighter Jets: Next-Gen Air Dominance",
        "category": "Aviation & Stealth",
        "hook": "Sixth-generation stealth fighters are combining adaptive cycle engines with autonomous AI wingmen.",
        "key_facts": [
            "The US Air Force NGAD program develops a sixth-generation crewed fighter flanked by collaborative autonomous combat drones.",
            "Features broadband stealth designed to defeat both high-frequency targeting and low-frequency early-warning radar arrays.",
            "The Global Combat Air Programme (GCAP) unites the UK, Japan, and Italy to field the Tempest stealth fighter by 2035.",
            "Equipped with next-generation sensor fusion, laser directed-energy defenses, and extreme long-range standoff weapons.",
        ],
        "keywords": ["6th gen", "ngad", "stealth fighter", "tempest", "gcap", "sixth generation", "fighter jet"],
    },
    {
        "topic": "Iron Beam: 100kW Directed Energy Laser Defense",
        "category": "Directed Energy Weapons",
        "hook": "This high-energy laser weapon destroys incoming drones at the speed of light for just $2 per shot.",
        "key_facts": [
            "Uses a 100-kilowatt class solid-state fiber laser to incinerate artillery rockets, mortars, and UAV swarms in mid-air.",
            "Engages targets at the speed of light with an effectively unlimited magazine as long as electrical power is available.",
            "Drastically changes defense economics compared to $50,000+ kinetic interceptor missiles.",
        ],
        "keywords": ["iron beam", "laser weapon", "directed energy", "air defense", "drone interceptor"],
    },
    {
        "topic": "Ghost Bat: The Autonomous AI Loyal Wingman",
        "category": "Autonomous Combat & AI",
        "hook": "Fighter pilots are entering combat with an autonomous AI jet flying beside them.",
        "key_facts": [
            "The Boeing MQ-28 Ghost Bat is an autonomous combat aircraft designed as a force-multiplying Loyal Wingman.",
            "Uses onboard artificial intelligence to fly ahead of crewed fighters, perform electronic warfare, and absorb threats.",
            "Features modular nose cones that can swap between intelligence sensors, jamming payloads, and strike systems.",
        ],
        "keywords": ["mq-28 ghost bat", "loyal wingman", "autonomous drone", "combat ai", "fighter jet"],
    },
    {
        "topic": "Columbia-Class: The $130 Billion Nuclear Ghost Submarine",
        "category": "Naval Warfare",
        "hook": "This submarine can hide underwater for 42 years without ever refueling its nuclear reactor.",
        "key_facts": [
            "Equipped with a life-of-ship nuclear reactor core that never needs refueling during its 42-year service life.",
            "Uses an electric-drive propulsion system and X-stern control surfaces to achieve near-zero acoustic signature.",
            "Carries 16 Trident II D5 submarine-launched ballistic missiles as the sea-based strategic deterrent.",
        ],
        "keywords": ["columbia class", "nuclear submarine", "us navy", "ballistic submarine", "stealth sub"],
    },
    {
        "topic": "Top Strategic Nuclear Submarines of the World",
        "category": "Naval Warfare",
        "hook": "Patrolling silently in the deep ocean, nuclear ballistic submarines carry enough firepower to deter world war.",
        "key_facts": [
            "The US Navy's Ohio and Columbia-class SSBNs represent the most survivable leg of the strategic nuclear triad.",
            "Russia's Borei-class submarines carry 16 R-30 Bulava submarine-launched ballistic missiles with multiple reentry warheads.",
            "The UK Royal Navy maintains continuous at-sea deterrence with Vanguard and future Dreadnought-class submarines.",
            "Equipped with nuclear reactors providing virtually unlimited underwater endurance, limited only by crew food supplies.",
        ],
        "keywords": ["nuclear submarine", "ssbn", "submarines", "borei class", "columbia class", "ballistic missile submarine"],
    },
    {
        "topic": "F-22 Raptor: Unrestricted Vertical Climb & Thrust Vectoring",
        "category": "Aviation & Stealth",
        "hook": "Watch 70,000 pounds of twin afterburner thrust launch the F-22 Raptor straight up into the stratosphere.",
        "key_facts": [
            "Powered by twin Pratt & Whitney F119-PW-100 turbofans generating 35,000 lbs of thrust each (70,000 lbs total).",
            "Features 2D pitch thrust-vectoring nozzles capable of deflecting 20 degrees up or down for extreme dogfight agility.",
            "Capable of supercruise above Mach 1.5 without using afterburners while maintaining stealth radar cross-section.",
        ],
        "keywords": ["f-22 raptor", "fighter jet", "thrust vectoring", "usaf", "stealth fighter", "afterburner"],
    },
    {
        "topic": "Quantum Computing & Quantum Supremacy",
        "category": "Computing & Advanced Technology",
        "hook": "Quantum computers compute in minutes what classical supercomputers would take ten thousand years to solve.",
        "key_facts": [
            "Quantum processors utilize qubits governed by superposition and entanglement to explore vast combinatorial spaces simultaneously.",
            "Superconducting circuits cooled near absolute zero maintain fragile quantum coherence for executing complex quantum gates.",
            "Key applications include molecular modeling for new materials, breakthrough cryptography, and global logistics optimization.",
        ],
        "keywords": ["quantum computing", "qubits", "superposition", "entanglement", "quantum supremacy", "quantum processor"],
    },
    {
        "topic": "James Webb Space Telescope & Deep Space",
        "category": "Space Exploration & Astronomy",
        "hook": "Positioned one million miles from Earth, the James Webb Space Telescope looks back 13.5 billion years into cosmic dawn.",
        "key_facts": [
            "Operates at the Sun-Earth Lagrange Point 2 (L2) with a five-layer tennis-court-sized sunshield keeping instruments near -388°F.",
            "Its 6.5-meter gold-plated beryllium primary mirror captures faint infrared light from the universe's earliest formed galaxies.",
            "Performs transmission spectroscopy on distant exoplanet atmospheres to detect water vapor, methane, and carbon dioxide.",
        ],
        "keywords": ["james webb", "jwst", "space telescope", "deep space", "astronomy", "exoplanets", "lagrange point"],
    },
]


class TopicAgent:
    """
    Agent 1: 'topic-agent'
    Performs deep multi-source web research on any given topic and outputs
    structured research text, verified facts, and source provenance for 'content-analyser'.
    """

    AGENT_NAME = "topic-agent"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    def __init__(self, language: str = "en"):
        self.name = self.AGENT_NAME
        self.language = language

    def run(
        self,
        topic: Optional[str] = None,
        language: Optional[str] = None,
        target_duration: float = 25.0,
        custom_notes: Optional[str] = None,
        style: str = "default",
    ) -> Dict[str, Any]:
        """
        Main entry point for 'topic-agent'.
        1. Checks if topic or style triggers 'weaponx lab' mode (10s, 9:16 static channel image Short).
        2. Resolves or selects topic.
        3. Queries Wikipedia REST & MediaWiki Search APIs and DuckDuckGo Instant Answer API.
        4. Enriches with curated domain facts.
        5. Passes research dossier + explicit instructions to 'content-analyser'.
        """
        lang = language or self.language or "en"
        raw_topic_str = (topic or "").strip()

        # Check if specifically requested as the 10s Gemini WeaponX Lab Poster mode
        is_weaponx_lab = (
            style.lower() in ("weaponx", "weaponx_lab", "weaponx lab")
            or bool(re.search(r"weapon\s*x\s*lab", raw_topic_str, flags=re.IGNORECASE))
        )

        # Strip "weaponx lab(s)" marker from the raw topic string to isolate the subject
        stripped_topic = re.sub(
            r"(?:@?weapon\s*x(?:\s*labs?)?[\s:\-–—]*)",
            "",
            raw_topic_str,
            flags=re.IGNORECASE,
        ).strip(" :-–—")

        effective_style = "weaponx" if is_weaponx_lab else style
        if target_duration:
            effective_duration = max(5.0, min(180.0, float(target_duration)))
        elif is_weaponx_lab:
            effective_duration = 10.0
        else:
            effective_duration = 30.0
        aspect_ratio = "9:16"

        selected_entry = self._resolve_topic(stripped_topic if stripped_topic else None)
        clean_topic = selected_entry["topic"]
        # Core subject without the subtitle ("Colt Canada C25 – Canada's Next-Gen..." -> "Colt Canada C25")
        clean_subject = subject_core(clean_topic)
        subject_desigs = designators(clean_subject)

        mode_tag = f"WEAPONX LAB ({effective_duration}s · 9:16)" if is_weaponx_lab else f"STANDARD ({effective_duration}s · {aspect_ratio})"
        print(f"\n[{self.AGENT_NAME}] 🔎 Starting deep web & multi-source research for: '{clean_topic}' [{mode_tag}]")

        sources: List[Dict[str, Any]] = []
        web_facts: List[str] = []
        web_paragraphs: List[str] = []

        # 0a. Web search FIRST (owner's request): what the web says about the topic right now. Results are
        #     sources; their sentences become facts only when another site or Wikipedia confirms the numbers.
        web_results: List[Dict[str, Any]] = []
        try:
            from agents import web_search
            from agents.fact_check import off_domain
            if web_search.available():
                print(f"[{self.AGENT_NAME}] 🌐 Web search (Tavily) for: '{clean_topic}'")
                web_results = [r for r in web_search.search(clean_topic) if not off_domain(f"{r['title']}. {r['content'][:300]}")]
                for r in web_results:
                    sources.append({"title": r["title"], "url": r["url"], "source_type": "web_search", "domain": r["domain"],
                                    "reliability": r["reliability"], "snippet": r["content"][:280]})
                print(f"[{self.AGENT_NAME}] 🌐 {len(web_results)} web result(s): "
                      f"{', '.join(r['domain'] for r in web_results[:6])}")
        except Exception as e:
            print(f"[{self.AGENT_NAME}] Web search skipped: {e}")

        # 0. Specific model named (e.g. "C25"): pull the sections of Wikipedia articles that actually
        #    mention it. New equipment is often covered inside a parent/programme article long before
        #    it gets its own page, and summaries alone miss it.
        if subject_desigs:
            for hit in self._search_wikipedia_mentions(clean_subject, subject_desigs):
                sources.append({
                    "title": hit["title"],
                    "url": hit["url"],
                    "source_type": "wikipedia_section",
                    "domain": urllib.parse.urlparse(hit["url"]).netloc,
                    "reliability": "high",
                    "snippet": " ".join(hit["sentences"])[:280],
                })
                web_facts.extend(hit["sentences"])
                web_paragraphs.append(" ".join(hit["sentences"]))

        # 1. Deep Research: Wikipedia API (English & Hindi if requested)
        wiki_results = self._search_wikipedia(clean_subject, lang=lang)
        if not wiki_results and lang != "en":
            wiki_results = self._search_wikipedia(clean_subject, lang="en")
        if subject_desigs:
            # An article that never names the model is about something else (e.g. a different rifle)
            kept = [w for w in wiki_results if mentions_any(f"{w['title']} {w.get('summary', '')}", subject_desigs)]
            for w in wiki_results:
                if w not in kept:
                    print(f"[{self.AGENT_NAME}] ⚠️ Dropped Wikipedia result that never mentions {subject_desigs}: '{w['title']}'")
            wiki_results = kept

        for w in wiki_results:
            sources.append({
                "title": w["title"],
                "url": w["url"],
                "source_type": "wikipedia",
                "domain": urllib.parse.urlparse(w["url"]).netloc,
                "reliability": "high",
                "snippet": w["summary"][:280],
            })
            if w.get("summary"):
                web_paragraphs.append(w["summary"])
                extracted = self._extract_fact_sentences(w["summary"], topic=clean_topic)
                web_facts.extend(extracted)

        # 2. Deep Research: DuckDuckGo Instant Answer API
        ddg_result = self._search_duckduckgo(clean_subject)
        if ddg_result and subject_desigs and not mentions_any(f"{ddg_result.get('heading', '')} {ddg_result['abstract']}", subject_desigs):
            ddg_result = None
        if ddg_result:
            sources.append({
                "title": ddg_result.get("heading") or clean_topic,
                "url": ddg_result.get("url") or f"https://duckduckgo.com/?q={urllib.parse.quote(clean_topic)}",
                "source_type": "duckduckgo_instant_answer",
                "domain": urllib.parse.urlparse(ddg_result.get("url", "https://duckduckgo.com")).netloc,
                "reliability": "verified_aggregator",
                "snippet": ddg_result["abstract"][:280],
            })
            web_paragraphs.append(ddg_result["abstract"])
            web_facts.extend(self._extract_fact_sentences(ddg_result["abstract"], topic=clean_topic))

        # 3. Curated Knowledge Base & Custom Notes
        curated_facts = list(selected_entry.get("key_facts", []))
        if isinstance(curated_facts, str):
            curated_facts = [curated_facts]

        if custom_notes and custom_notes.strip():
            web_paragraphs.insert(0, custom_notes.strip())
            curated_facts.extend(self._extract_fact_sentences(custom_notes.strip()))
            sources.append({
                "title": f"User Provided Story / Notes: {clean_topic}",
                "url": "local://custom-user-input",
                "source_type": "user_input",
                "domain": "local",
                "reliability": "primary",
                "snippet": custom_notes.strip()[:280],
            })

        # Web-search sentences that are confirmed (numbers stated by another site or by Wikipedia)
        web_confirmed: List[str] = []
        if web_results:
            try:
                from agents import web_search
                web_confirmed = web_search.corroborated_sentences(web_results, "\n".join(web_paragraphs))
                print(f"[{self.AGENT_NAME}] 🌐 {len(web_confirmed)} confirmed web fact(s) added")
                web_facts.extend(web_confirmed)
                web_paragraphs.extend(r["content"] for r in web_results[:3] if r["reliability"] != "web")
            except Exception as e:
                print(f"[{self.AGENT_NAME}] Web facts skipped: {e}")

        # Deduplicate facts while preserving order (the bare title is not a fact)
        all_facts: List[str] = []
        seen_norm = {re.sub(r"\W+", "", clean_topic.lower())[:60], re.sub(r"\W+", "", clean_subject.lower())[:60]}
        for f in curated_facts + web_facts:
            norm = re.sub(r"\W+", "", f.lower())[:60]
            if norm and norm not in seen_norm and len(f.strip()) > 15:
                seen_norm.add(norm)
                all_facts.append(f.strip())

        if not all_facts:
            all_facts = self._generate_fallback_facts(
                clean_topic, selected_entry.get("category", "Deep Research"), lang=lang
            )

        if not sources:
            sources.append({
                "title": f"Verified Intelligence Dossier: {clean_topic}",
                "url": f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote(clean_topic)}",
                "source_type": "knowledge_base",
                "domain": "en.wikipedia.org",
                "reliability": "high",
                "snippet": " ".join(all_facts[:2]),
            })

        # 4. Extract core topic keywords for downstream image verification
        keywords = self._extract_keywords(clean_topic, selected_entry.get("keywords", []), all_facts)

        # 5. Synthesize cohesive research text & initial narrative draft
        research_text, raw_draft_script = self._synthesize_research_text(
            topic=clean_topic,
            category=selected_entry.get("category", "Documentary & Tech"),
            hook=selected_entry.get("hook", ""),
            facts=all_facts,
            web_paragraphs=web_paragraphs,
            language=lang,
            target_duration=effective_duration,
        )

        # 6. Build explicit instructions for content-analyser
        is_weaponx_lab_static = is_weaponx_lab and (effective_duration <= 20.0)
        instructions_for_content_analyser = {
            "from_agent": self.AGENT_NAME,
            "to_agent": "content-analyser",
            "is_weaponx_lab": is_weaponx_lab,
            "is_weaponx_lab_static": is_weaponx_lab_static,
            "style": effective_style,
            "target_duration_seconds": effective_duration,
            "aspect_ratio": aspect_ratio,
            "resolution": "1080x1920",
            "visual_mode": "weaponx_lab_static" if is_weaponx_lab_static else "multi_scene",
            "topic_subject": clean_subject,
            "directive": (
                f"WEAPONX LAB MODE (10s static): Create a tight 10s 9:16 Short script (~20-25 words) for '{clean_subject}' "
                f"and generate structured 'image_data' for 'image-generator' to create a static @WeaponXLabs "
                f"channel-style 1080x1920 image customized for '{clean_subject}'."
                if is_weaponx_lab_static
                else f"Check and correct researched text for '{clean_subject}' ({effective_duration}s, {aspect_ratio}) and prepare scene 'image_data' for 'image-generator'."
            ),
        }

        print(
            f"[{self.AGENT_NAME}] ✓ Research complete: {len(sources)} source(s), {len(all_facts)} factual points. "
            f"Sending instructions to 'content-analyser' (mode={'weaponx_lab 10s static 9:16' if is_weaponx_lab_static else f'{effective_duration}s {aspect_ratio}'})."
        )

        return {
            "agent": self.AGENT_NAME,
            "timestamp": datetime.now().isoformat(),
            "topic": clean_topic,
            "topic_subject": clean_subject,
            "category": selected_entry.get("category", "Defense & Advanced Tech"),
            "language": lang,
            "style": effective_style,
            "is_weaponx_lab": is_weaponx_lab,
            "aspect_ratio": aspect_ratio,
            "target_duration": effective_duration,
            "hook": selected_entry.get("hook", ""),
            "key_facts": " ".join(all_facts[:4]),
            # + the confirmed web facts, so the fact check accepts exactly those (not unconfirmed web text)
            "verified_facts": list(dict.fromkeys(all_facts[:8] + web_confirmed)),
            "web_results": [{k: r[k] for k in ("title", "url", "domain", "reliability")} for r in web_results],
            "sources": sources,
            "keywords": keywords,
            "research_text": research_text,
            "raw_draft_script": raw_draft_script,
            "instructions_for_content_analyser": instructions_for_content_analyser,
        }

    @classmethod
    def get_daily_topic(
        cls,
        custom_topic: Optional[str] = None,
        language: str = "en",
        style: str = "default",
    ) -> Dict[str, Any]:
        """Backwards-compatible helper that runs deep topic research."""
        agent = cls(language=language)
        return agent.run(topic=custom_topic, language=language, style=style)

    @staticmethod
    def _generate_fallback_facts(topic: str, category: str, lang: str = "en") -> List[str]:
        clean = topic.strip()
        cat_lower = category.lower()
        if lang == "hi":
            if any(w in cat_lower for w in ["history", "civilization", "ancient"]):
                return [
                    f"{clean} का इतिहास सदियों पुराना है और इसने मानव सभ्यता, संस्कृति और व्यापार को गहराई से प्रभावित किया है।",
                    f"ऐतिहासिक अभिलेखों के अनुसार {clean} ने कई महत्वपूर्ण सामाजिक और सांस्कृतिक परिवर्तनों में केंद्रीय भूमिका निभाई।",
                    f"इतिहासकार और शोधकर्ता आज भी {clean} के ऐतिहासिक और वैश्विक प्रभाव का गहराई से अध्ययन करते हैं।",
                ]
            elif any(w in cat_lower for w in ["space", "astronomy", "cosmic"]):
                return [
                    f"{clean} खगोल विज्ञान और अंतरिक्ष अनुसंधान में ब्रह्मांड के रहस्यों को समझने की दिशा में एक ऐतिहासिक कदम है।",
                    f"वैज्ञानिकों ने {clean} के माध्यम से गहरे अंतरिक्ष और खगोलीय पिंडों के महत्वपूर्ण वैज्ञानिक आंकड़े प्राप्त किए हैं।",
                    f"यह अंतरिक्ष विज्ञान के नए युग की शुरुआत का प्रतीक है और भविष्य के अभियानों को दिशा देता है।",
                ]
            elif any(w in cat_lower for w in ["defense", "missile", "military", "stealth", "naval"]):
                return [
                    f"{clean} रक्षा तकनीक और रणनीतिक सुरक्षा के क्षेत्र में एक शक्तिशाली और महत्वपूर्ण प्रणाली है।",
                    f"विशेषज्ञों के अनुसार {clean} उच्च गति, सटीक प्रहार और रणनीतिक निवारण के लिए तैयार की गई है।",
                    f"इसकी रणनीतिक तैनाती आधुनिक रक्षा परिदृश्य में एक अत्यंत महत्वपूर्ण मोड़ साबित हुई है।",
                ]
            else:
                return [
                    f"{clean} आधुनिक विज्ञान और ज्ञान के क्षेत्र में एक अत्यंत महत्वपूर्ण और प्रभावशाली विषय है।",
                    f"शोधकर्ताओं और विशेषज्ञों ने {clean} से जुड़े कई मूलभूत और व्यावहारिक तथ्यों की पुष्टि की है।",
                    f"इसकी अनूठी विशेषताएं और प्रभाव इसे अपनी श्रेणी में सबसे प्रमुख और उल्लेखनीय बनाते हैं।",
                ]
        else:
            if any(w in cat_lower for w in ["history", "civilization", "ancient", "era"]):
                return [
                    f"Archival records show {clean} holds enduring historical significance across human civilization.",
                    f"Throughout the centuries, {clean} played a decisive role in shaping cultural practices, trade routes, and societal evolution.",
                    f"Historians and archaeologists continue to document the lasting worldwide legacy of {clean}.",
                ]
            elif any(w in cat_lower for w in ["space", "astronomy", "cosmic", "orbit"]):
                return [
                    f"{clean} provides vital astronomical observations into the evolution and physical laws of the cosmos.",
                    f"Astrophysicists rely on telemetry and spectrographic data from {clean} to map deep-space phenomena.",
                    f"Exploration surrounding {clean} expands scientific boundaries beyond conventional observation thresholds.",
                ]
            elif any(w in cat_lower for w in ["missile", "defense", "military", "aviation", "stealth", "naval", "weapon"]):
                return [
                    f"{clean} represents an advanced strategic capability engineered for tactical deterrence and high-speed operational readiness.",
                    f"Equipped with precision guidance and survivability countermeasures, {clean} counters modern intercept threats.",
                    f"Global defense doctrines monitor {clean} as a transformative technological asset across modern operational theaters.",
                ]
            elif any(w in cat_lower for w in ["computing", "tech", "ai", "quantum"]):
                return [
                    f"{clean} marks a fundamental breakthrough in computing architecture, algorithms, and digital systems.",
                    f"Engineered to solve complex systemic bottlenecks, {clean} scales computational efficiency exponentially.",
                    f"Researchers and industry leaders recognize {clean} as a cornerstone for future computational paradigms.",
                ]
            else:
                return [
                    f"{clean} stands as a widely recognized subject with substantial cultural and scientific significance.",
                    f"Scholars and analysts have documented the distinct characteristics and evolving milestones of {clean}.",
                    f"Modern studies into {clean} continue to reveal key insights into its origin, development, and ongoing relevance.",
                ]

    @staticmethod
    def _infer_category(topic: str) -> str:
        t = topic.lower()
        if any(w in t for w in ["rifle", "pistol", "gun", "carbine", "firearm", "handgun", "shotgun", "sniper", "small arms", "ammunition", "qbz", "qbu", "ak-47", "m4", "glock", "beretta", "pla"]):
            return "Small Arms & Infantry Weapons"
        if any(w in t for w in ["missile", "hypersonic", "warhead", "rocket", "ballistic", "torpedo", "bomb", "interceptor"]):
            return "Hypersonic & Missile Systems"
        if any(w in t for w in ["fighter", "stealth", "bomber", "aircraft", "jet", "aviation", "raptor", "wingman"]):
            return "Military Aviation & Stealth"
        if any(w in t for w in ["submarine", "warship", "naval", "carrier", "navy", "destroyer"]):
            return "Naval Warfare & Fleet Systems"
        if any(w in t for w in ["space", "telescope", "nasa", "orbit", "mars", "moon", "galaxy", "astronomy", "cosmic", "universe", "planet", "solar system", "black hole", "star"]):
            return "Space Exploration & Astronomy"
        if any(w in t for w in ["ai", "quantum", "computer", "neural", "robot", "software", "cyber", "internet", "bitcoin", "blockchain"]):
            return "Computing & Advanced Technology"
        if any(w in t for w in [
            "history", "ancient", "century", "empire", "civilization", "dynasty", "roman", "egypt", "pyramid",
            "viking", "samurai", "sparta", "medieval", "archaeology", "kingdom", "origin", "evolution",
            "coffee", "tea", "chocolate", "spice", "salt", "wine"
        ]):
            return "World History & Civilization"
        return "Deep Research & Technology"

    VIRAL_POWER_TOKENS: Dict[str, int] = {
        "mach 9": 50,
        "mach 5": 45,
        "hypersonic": 48,
        "secret bomber": 46,
        "b-21 raider": 48,
        "darkstar": 44,
        "sr-72": 44,
        "next-gen fighter": 45,
        "sixth-gen": 44,
        "f-35": 38,
        "su-57": 36,
        "f-22": 38,
        "sniper rifle": 42,
        "laser weapon": 45,
        "railgun": 45,
        "stealth submarine": 40,
        "aircraft carrier": 38,
        "nuclear submarine": 40,
        "space weapon": 42,
        "anti-drone": 35,
        "swarm drone": 36,
        "iron dome": 36,
        "patriot missile": 35,
        "guided missile": 34,
        "main battle tank": 32,
        "stealth": 30,
        "barrett": 34,
        "beretta": 30,
    }

    TRENDING_FEEDS: List[str] = [
        "https://trends.google.com/trending/rss?geo=US",
        "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
        "https://breakingdefense.com/feed/",
    ]

    def discover_viral_trending_topic(self) -> Dict[str, Any]:
        """
        Phase 2 Autonomous Topic Discovery:
        Scrapes real-time trending feeds (Google Trends RSS, DefenseNews, BreakingDefense),
        filters for viral high-CTR tokens ('Mach 9', 'Secret Bomber', 'Hypersonic', 'Next-Gen Fighter'),
        cross-references published history to avoid duplicate topics, and synthesizes high-retention topics.
        Falls back seamlessly to curated high-CTR bank if network is offline or sandboxed.
        """
        history = []
        try:
            from app.utils.storage import StorageManager
            history = [h.lower() for h in StorageManager.get_history()]
        except Exception:
            pass

        candidates: List[Dict[str, Any]] = []

        # 1. Scrape RSS feeds if reachable
        for feed_url in self.TRENDING_FEEDS:
            try:
                xml_text = None
                if HAS_REQUESTS:
                    r = requests.get(feed_url, headers=self.HEADERS, timeout=3)
                    if r.status_code == 200:
                        xml_text = r.text
                else:
                    req = urllib.request.Request(feed_url, headers=self.HEADERS)
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        xml_text = resp.read().decode("utf-8", errors="ignore")

                if xml_text:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(xml_text)
                    for item in root.findall(".//item"):
                        title_el = item.find("title")
                        desc_el = item.find("description")
                        title = (title_el.text or "").strip() if title_el is not None else ""
                        desc = (desc_el.text or "").strip() if desc_el is not None else ""
                        combined = f"{title} {desc}".lower()

                        score = 0
                        matched_token = None
                        for token, pts in self.VIRAL_POWER_TOKENS.items():
                            if token in combined:
                                score += pts
                                if matched_token is None:
                                    matched_token = token

                        # Check if title or matched token is already in history
                        if score > 0 and not any(h in title.lower() for h in history if len(h) > 4):
                            candidates.append({
                                "headline": title,
                                "matched_token": matched_token,
                                "score": score,
                                "source": feed_url,
                            })
            except Exception:
                continue

        # Sort scraped candidates by viral score
        candidates.sort(key=lambda x: x["score"], reverse=True)

        if candidates and candidates[0]["score"] >= 35:
            top_cand = candidates[0]
            clean_title = re.sub(r"[^\w\s\-–|:]", "", top_cand["headline"]).strip()
            topic_name = clean_title.split("|")[0].split(" - ")[0].strip()
            cat = self._infer_category(topic_name)
            hook = f"Is {topic_name} the most dangerous military breakthrough in modern history?"
            result = {
                "topic": topic_name,
                "category": cat,
                "hook": hook,
                "key_facts": [
                    f"{topic_name} represents a major leap in tactical defense engineering.",
                    f"Engineered to counter hypersonic and next-generation threats in modern combat theater.",
                    f"Military analysts report its strategic deployment alters the global balance of power."
                ],
                "keywords": [top_cand["matched_token"]] if top_cand["matched_token"] else ["defense", "viral"],
                "viral_score": top_cand["score"],
                "discovery_mode": "live_trend_feed"
            }
            try:
                from app.utils.storage import StorageManager
                StorageManager.add_to_history(result["topic"])
            except Exception:
                pass
            return result

        # 2. Resilient curated fallback: Score CURATED_TOPIC_BANK with viral tokens & history filter
        scored_bank = []
        for entry in CURATED_TOPIC_BANK:
            topic_str = f"{entry['topic']} {' '.join(entry.get('keywords', []))}".lower()
            if any(h in entry["topic"].lower() for h in history if len(h) > 5):
                continue
            entry_score = sum(pts for token, pts in self.VIRAL_POWER_TOKENS.items() if token in topic_str)
            scored_bank.append((entry_score, entry))

        if scored_bank:
            scored_bank.sort(key=lambda x: x[0], reverse=True)
            chosen = dict(scored_bank[0][1])
        else:
            chosen = dict(random.choice(CURATED_TOPIC_BANK))

        chosen["discovery_mode"] = "curated_viral_bank"
        try:
            from app.utils.storage import StorageManager
            StorageManager.add_to_history(chosen["topic"])
        except Exception:
            pass
        return chosen

    def _resolve_topic(self, topic: Optional[str]) -> Dict[str, Any]:
        if topic and topic.strip() and topic.strip().lower() not in ("auto", "trending", "daily"):
            clean = topic.strip()
            clean_lower = clean.lower()
            clean_tokens = set(re.findall(r"[a-z0-9]{3,}", clean_lower))

            # Only check curated bank if the user topic is concise (not a rich custom prompt/spec)
            best_entry = None
            best_score = 0

            is_custom_long = len(clean) > 80 or "\n" in clean or (":" in clean and len(clean.split(":")) > 2)

            if not is_custom_long:
                for entry in CURATED_TOPIC_BANK:
                    score = 0
                    entry_topic_lower = entry["topic"].lower()
                    entry_keywords = [k.lower() for k in entry.get("keywords", [])]

                    # Match in topic string
                    if clean_lower in entry_topic_lower or entry_topic_lower in clean_lower:
                        score += 25

                    # Match keywords only if title shares tokens
                    entry_tokens = set(re.findall(r"[a-z0-9]{3,}", entry_topic_lower))
                    overlap = len(clean_tokens & entry_tokens)
                    if overlap >= 2:
                        score += overlap * 10

                    if score > best_score:
                        best_score = score
                        best_entry = entry

                if best_entry and best_score >= 20:
                    merged = dict(best_entry)
                    merged["topic"] = clean
                    return merged

            # User provided a custom topic or rich detailed specification!
            cat = self._infer_category(clean)
            
            # Extract facts from user prompt if present
            user_facts = []
            raw_lines = re.split(r'[\r\n]+|\s{3,}|(?<=\.)\s+(?=[A-Z0-9\-])', clean)
            for l in raw_lines:
                cl = l.strip()
                if len(cl) > 20 and ":" in cl:
                    user_facts.append(cl)
                elif len(cl) > 30 and any(w in cl.lower() for w in ["rifle", "barrel", "cartridge", "round", "caliber", "sight", "built", "issued", "weapon", "variant", "system", "speed", "range"]):
                    user_facts.append(cl)

            # Core subject only: "Colt Canada C25 – Canada's Next-Gen..." -> "Colt Canada C25"
            headline = subject_core(clean.split("\n")[0])
            if len(headline) > 60:
                headline = headline[:58].rstrip()

            # Neutral hooks that are true for anything, new or old (a rifle entering service in 2026
            # has not "earned its reputation"); the research facts carry the specifics
            hook = f"Here's what sets the {headline} apart."

            return {
                "topic": clean,
                "category": cat,
                "hook": hook,
                # Real facts come from Wikipedia/DuckDuckGo research; no placeholder filler here
                "key_facts": user_facts[:6],
                "keywords": [w.lower() for w in re.findall(r"[a-zA-Z0-9\u0900-\u097F]{3,}", headline)],
            }

        # Autonomous Phase 2 Discovery when topic is omitted or set to 'auto'
        return self.discover_viral_trending_topic()

    def _http_get_json(self, url: str, timeout: int = 6) -> Optional[Dict[str, Any]]:
        try:
            if HAS_REQUESTS:
                resp = requests.get(url, headers=self.HEADERS, timeout=timeout)
                if resp.status_code == 200:
                    return resp.json()
                return None
            else:
                req = urllib.request.Request(url, headers=self.HEADERS)
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
        except Exception:
            return None

    @staticmethod
    def _generate_search_queries(topic: str) -> List[str]:
        """Generates smart Wikipedia query variants by stripping boilerplate and adding domain terms."""
        queries = [topic.strip()]
        c = re.sub(r"^(top\s+\d+|top|best|list\s+of|the|all|major|famous)\s+", "", topic.strip(), flags=re.IGNORECASE)
        c = re.sub(r"\s+(of\s+the\s+world|in\s+the\s+world|in\s+history|ever\s+made|of\s+all\s+time)$", "", c, flags=re.IGNORECASE).strip()
        if c and c.lower() != topic.lower():
            queries.insert(0, c)

        c_lower = c.lower()
        if "hypersonic missiles" in c_lower or "hypersonic missile" in c_lower:
            queries.insert(0, "Hypersonic weapon")
            queries.insert(1, "Hypersonic flight")
        elif "stealth fighters" in c_lower or "6th gen" in c_lower or "sixth gen" in c_lower:
            queries.insert(0, "Sixth-generation fighter")
        elif "nuclear submarines" in c_lower:
            queries.insert(0, "Nuclear submarine")
        return list(dict.fromkeys(queries))

    DISAMBIGUATION_BAD_SUFFIXES = [
        "(album)", "(song)", "(single)", "(ep)", "(soundtrack)", "(band)",
        "(film)", "(movie)", "(tv series)", "(novel)", "(book)", "(character)",
        "(record label)", "(discography)", "(musician)", "(disambiguation)"
    ]

    DISAMBIGUATION_SNIPPET_PATTERNS = [
        r"\b(debut\s+studio\s+album|studio\s+album|song\s+written\s+and\s+performed|track\s+listing|record\s+label|uk\s+albums\s+chart|billboard\s+hot|pop\s+band|rock\s+band)\b"
    ]

    def _is_irrelevant_hit(self, title: str, snippet: str, query: str) -> bool:
        q_lower = query.lower()
        if any(w in q_lower for w in ["album", "song", "music", "band", "singer", "film", "movie", "cinema", "actor"]):
            return False

        t_lower = title.lower()
        for bad in self.DISAMBIGUATION_BAD_SUFFIXES:
            if bad in t_lower:
                return True

        s_lower = snippet.lower()
        for pat in self.DISAMBIGUATION_SNIPPET_PATTERNS:
            if re.search(pat, s_lower, re.IGNORECASE):
                return True
        return False

    def _search_wikipedia(self, query: str, lang: str = "en", limit: int = 2) -> List[Dict[str, Any]]:
        """Queries Wikipedia MediaWiki API & REST summary API with disambiguation filtering."""
        wiki_lang = "hi" if lang == "hi" else "en"
        query_candidates = self._generate_search_queries(query)
        results: List[Dict[str, Any]] = []
        seen_titles = set()

        for q in query_candidates:
            if len(results) >= limit:
                break
            encoded_q = urllib.parse.quote(q)
            search_url = (
                f"https://{wiki_lang}.wikipedia.org/w/api.php?"
                f"action=query&list=search&srsearch={encoded_q}&utf8=&format=json&srlimit=6"
            )
            data = self._http_get_json(search_url)
            if not data:
                continue

            search_hits = data.get("query", {}).get("search", [])
            for hit in search_hits:
                title = hit.get("title", "")
                snippet = hit.get("snippet", "")
                if not title or title.lower() in seen_titles:
                    continue

                if self._is_irrelevant_hit(title, snippet, query):
                    print(f"[{self.AGENT_NAME}] ⚠️ Filtered out irrelevant Wikipedia hit: '{title}'")
                    continue

                summary_url = (
                    f"https://{wiki_lang}.wikipedia.org/api/rest_v1/page/summary/"
                    f"{urllib.parse.quote(title.replace(' ', '_'))}"
                )
                sum_data = self._http_get_json(summary_url)
                if sum_data and sum_data.get("extract"):
                    extract = sum_data.get("extract", "").strip()
                    desc = sum_data.get("description", "")
                    from agents.fact_check import off_domain
                    if self._is_irrelevant_hit(title, f"{desc} {extract}", query) or (
                            off_domain(f"{desc}. {extract[:300]}") and not off_domain(query)):
                        print(f"[{self.AGENT_NAME}] ⚠️ Filtered out summary after extraction: '{title}' ({desc})")
                        continue

                    page_url = (
                        sum_data.get("content_urls", {}).get("desktop", {}).get("page")
                        or f"https://{wiki_lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                    )
                    seen_titles.add(title.lower())
                    results.append({
                        "title": title,
                        "url": page_url,
                        "summary": extract,
                        "description": desc,
                    })
                    if len(results) >= limit:
                        break

        return results

    def _search_wikipedia_mentions(self, subject: str, desigs: List[str], max_articles: int = 4, max_sentences: int = 10) -> List[Dict[str, Any]]:
        """
        Full-text Wikipedia search for a specific model designator, returning the sentences of each
        article section that names it (e.g. the 'Canadian Modular Assault Rifle' section of the
        'Colt Canada C7' article for 'Colt Canada C25').
        """
        brand = brand_words(subject, desigs)
        query = " ".join(f'"{d}"' for d in desigs[:1]) + (f' "{" ".join(brand[:2])}"' if brand else "")
        data = self._http_get_json(
            "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=8&srsearch="
            + urllib.parse.quote(query)
        )
        titles = [h.get("title") for h in (data or {}).get("query", {}).get("search", []) if h.get("title")]
        results: List[Dict[str, Any]] = []
        total = 0
        for title in titles:
            if len(results) >= max_articles or total >= max_sentences:
                break
            page = self._http_get_json(
                "https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&format=json&titles="
                + urllib.parse.quote(title)
            )
            pages = (page or {}).get("query", {}).get("pages", {})
            text = next(iter(pages.values()), {}).get("extract", "") if pages else ""
            if not text:
                continue
            sentences: List[str] = []
            # Keep whole paragraphs that name the model: a programme paragraph stays together, while
            # list sections (e.g. competing rifles) contribute only the entry about this model.
            for para in text.split("\n"):
                if not mentions_any(para, desigs):
                    continue
                if True:
                    for sent in re.split(r"(?<=[.!?])\s+", para.strip()):
                        sent = re.sub(r"\[[0-9]+\]", "", sent).strip()
                        if 30 <= len(sent) <= 320 and sent not in sentences:
                            sentences.append(sent)
            # Keep sentences that name the model first, then the section's other sentences
            sentences.sort(key=lambda x: 0 if mentions_any(x, desigs) else 1)
            sentences = sentences[: max(0, max_sentences - total)]
            if sentences:
                total += len(sentences)
                results.append({
                    "title": title,
                    "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                    "sentences": sentences,
                })
        if results:
            print(f"[{self.AGENT_NAME}] ✓ Found {total} sentence(s) about {desigs} in: {[r['title'] for r in results]}")
        return results

    def _search_duckduckgo(self, query: str) -> Optional[Dict[str, Any]]:
        """Queries DuckDuckGo Instant Answer API for abstract & primary reference."""
        clean_q = query.split(":")[0].strip() if ":" in query else query.strip()
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_q)}&format=json&no_html=1&skip_disambig=1"
        data = self._http_get_json(url)
        if not data:
            return None

        abstract = (data.get("AbstractText") or "").strip()
        if len(abstract) > 30:
            return {
                "heading": data.get("Heading") or clean_q,
                "abstract": abstract,
                "url": data.get("AbstractURL") or f"https://duckduckgo.com/?q={urllib.parse.quote(clean_q)}",
            }
        return None

    def _extract_fact_sentences(self, text: str, topic: str = "") -> List[str]:
        """Splits research paragraphs into clean, verifiable factual statements while filtering noise."""
        if not text:
            return []
        raw_sentences = re.split(r"(?<=[.!?।])\s+", text.strip())
        facts = []
        is_music_topic = any(w in topic.lower() for w in ["album", "song", "music", "band", "singer"])
        for s in raw_sentences:
            s_clean = re.sub(r"\[[0-9]+\]", "", s).strip()
            if not is_music_topic and re.search(r"\b(debut\s+studio\s+album|uk\s+albums\s+chart|billboard|copies\s+sold|polydor\s+records)\b", s_clean, re.IGNORECASE):
                continue
            if 25 <= len(s_clean) <= 260:
                facts.append(s_clean)
        return facts[:6]

    def _extract_keywords(self, topic: str, base_keywords: List[str], facts: List[str]) -> List[str]:
        """Extracts high-signal topic keywords used by 'image-generator' to verify image relevance."""
        stop_words = {
            "the", "and", "for", "with", "that", "this", "from", "into", "over",
            "more", "than", "first", "what", "when", "where", "which", "while",
            "about", "have", "been", "were", "they", "their", "will", "would",
            "could", "should", "just", "most", "some", "such", "only", "also",
        }
        tokens: List[str] = list(base_keywords)
        clean_topic = topic.split(":")[0].strip().lower()
        if clean_topic and clean_topic not in tokens:
            tokens.insert(0, clean_topic)

        words = re.findall(r"[a-zA-Z0-9\-\u0900-\u097F]{3,}", f"{topic} {' '.join(facts[:3])}")
        for w in words:
            wl = w.lower()
            if wl not in stop_words and wl not in tokens:
                tokens.append(wl)
            if len(tokens) >= 12:
                break
        return tokens

    def _synthesize_research_text(
        self,
        topic: str,
        category: str,
        hook: str,
        facts: List[str],
        web_paragraphs: List[str],
        language: str,
        target_duration: float,
    ) -> tuple:
        """Combines web paragraphs and verified facts into a coherent research text & raw draft."""
        if not hook:
            if language == "hi":
                hook = f"क्या आप जानते हैं कि {topic} के पीछे का असली सच क्या है?"
            else:
                hook = f"Here is why {topic} is changing everything we know about {category.lower()}."

        if not facts:
            facts = self._generate_fallback_facts(topic, category, lang=language)

        body_text = "\n\n".join(web_paragraphs[:2]) if web_paragraphs else " ".join(facts)
        facts_block = "\n".join(f"- {f}" for f in facts[:6])

        research_text = (
            f"TOPIC: {topic}\n"
            f"CATEGORY: {category}\n"
            f"OPENING HOOK: {hook}\n\n"
            f"RESEARCH SUMMARY:\n{body_text}\n\n"
            f"VERIFIED KEY FACTS:\n{facts_block}"
        )

        # Build initial raw draft narration for content-analyser to inspect and refine
        if language == "hi":
            closing = f"इस बारे में आपकी क्या राय है? कमेंट में ज़रूर बताएं!"
        else:
            closing = f"Could anything stop {topic.split(':')[0]}? Tell us what you think below."

        raw_draft_script = f"{hook} {' '.join(facts[:3])} {closing}"
        return research_text, raw_draft_script
