import random
from typing import Dict, Any, List
from app.utils.storage import StorageManager
import config

# Curated high-CTR defense & military tech topics with verified hook angles
DEFENSE_TOPIC_BANK = [
    {
        "topic": "The Dark Eagle Hypersonic Weapon (LRHW)",
        "category": "Hypersonic Missiles",
        "hook": "The US military just fielded a weapon that travels at Mach 17.",
        "key_facts": "Flies at 13,000 mph, maneuvers in upper atmosphere to dodge radar, strikes anywhere in minutes."
    },
    {
        "topic": "B-21 Raider: The First 6th-Gen Stealth Bomber",
        "category": "Aviation & Stealth",
        "hook": "This bomber is so stealthy, radar sees it as a small bird.",
        "key_facts": "Open software architecture, flying wing stealth, designed to penetrate modern air defenses undetected."
    },
    {
        "topic": "Iron Beam: Israel's 100kW Laser Defense System",
        "category": "Directed Energy Weapons",
        "hook": "This laser weapon destroys drones for just two dollars per shot.",
        "key_facts": "Fiber laser interceptor, speed-of-light engagement, unlimited magazine as long as power flows."
    },
    {
        "topic": "Ghost Bat: The Autonomous AI Loyal Wingman",
        "category": "Autonomous Combat & AI",
        "hook": "Fighter pilots will soon enter combat with an AI swarm protecting them.",
        "key_facts": "MQ-28 Ghost Bat flies alongside human jets, scouts ahead, absorbs enemy missiles, uses neural nets."
    },
    {
        "topic": "Columbia-Class: The $130 Billion Nuclear Ghost Submarine",
        "category": "Naval Warfare",
        "hook": "This submarine can hide underwater for 42 years without refueling.",
        "key_facts": "Electric-drive propulsion, completely silent acoustic signature, carries Trident II D5 nuclear missiles."
    },
    {
        "topic": "Quantum Radar: The End of Stealth Aircraft",
        "category": "Advanced Sensor Tech",
        "hook": "Is stealth obsolete? Quantum radar uses entangled photons to break stealth cloaking.",
        "key_facts": "Splits entangled light particles; reflections cannot be tricked by radar-absorbent paint or jamming."
    },
    {
        "topic": "Hypervelocity Railguns: Firing Projectiles at Mach 7",
        "category": "Kinetic Energy Weapons",
        "hook": "No gunpowder, no explosives—just sheer electromagnetic fury at 5,400 mph.",
        "key_facts": "Uses Lorentz force, kinetic energy alone penetrates reinforced bunkers and armor."
    },
    {
        "topic": "Combat Exoskeletons: The Super Soldiers of Tomorrow",
        "category": "Infantry Technology",
        "hook": "Soldiers carrying 150-pound backpacks without feeling fatigue.",
        "key_facts": "Titanium frames, battery-powered hydraulic actuators, increases endurance by 400%."
    },
    {
        "topic": "NGAD: America's Secret 6th-Generation Fighter",
        "category": "Aviation",
        "hook": "The F-22 Raptor is being replaced by something terrifying.",
        "key_facts": "Next Generation Air Dominance, operates as a mothership controlling autonomous drone fleets."
    },
    {
        "topic": "Anti-Satellite EMP Missiles: The Threat of Kessler Syndrome",
        "category": "Space Defense",
        "hook": "One direct hit in low Earth orbit could blind global GPS forever.",
        "key_facts": "Kinetic ASAT weapons create cascading space debris rings disabling satellites worldwide."
    }
]

class ResearchAgent:
    @staticmethod
    def get_daily_topic(custom_topic: str = None) -> Dict[str, Any]:
        """
        Selects a fresh topic for today.
        If custom_topic is given, uses it; otherwise picks an unused high-impact topic.
        """
        history = StorageManager.get_history()

        if custom_topic:
            StorageManager.add_to_history(custom_topic)
            return {
                "topic": custom_topic,
                "category": "Custom Defense Tech",
                "hook": f"Here is why the {custom_topic} is changing military warfare forever.",
                "key_facts": "Cutting-edge military development."
            }

        # Filter out previously covered topics
        available_topics = [t for t in DEFENSE_TOPIC_BANK if t["topic"] not in history]

        if not available_topics:
            # If all were used once, reset history cycle
            available_topics = DEFENSE_TOPIC_BANK

        selected = random.choice(available_topics)
        StorageManager.add_to_history(selected["topic"])
        return selected
