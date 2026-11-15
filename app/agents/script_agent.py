import os
import json
from typing import Dict, Any, List
import config

class ScriptAgent:
    @staticmethod
    def generate_script(topic_info: Dict[str, Any], style: str = "default") -> Dict[str, Any]:
        """
        Generates a 20-25 second YouTube Shorts script broken into 5 scenes.
        Supports 'weaponx' style matching @WeaponXLabs high-retention military hooks.
        """
        openai_key = config.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                return ScriptAgent._generate_with_llm(topic_info, openai_key, style)
            except Exception as e:
                print(f"[ScriptAgent] LLM generation error: {e}. Falling back to procedural generator.")

        return ScriptAgent._generate_procedural(topic_info, style)

    @staticmethod
    def _generate_with_llm(topic_info: Dict[str, Any], api_key: str) -> Dict[str, Any]:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        prompt = f"""You are a master YouTube Shorts scriptwriter specializing in defense, military technology, and advanced weapons.
Create a high-retention 20-25 second YouTube Short about: {topic_info['topic']}.
Hook Angle: {topic_info.get('hook', '')}
Key Facts: {topic_info.get('key_facts', '')}

Requirements:
- Total voiceover word count MUST be between 50 and 65 words.
- Scene 1 (0-3s): Explosive 2-second hook that immediately stops scrolling.
- Scene 2-4 (3-20s): Technical superpower, how it works, why enemy defenses cannot stop it.
- Scene 5 (20-25s): Provocative question or closing call-to-action.
- For each scene, write a cinematic 9:16 vertical visual prompt suitable for AI image generation (e.g. photorealistic 8k, Unreal Engine 5 military render, cinematic lighting).

Return ONLY raw JSON in this exact structure:
{{
  "title": "Shocking Title with #Shorts",
  "description": "Short description with #Shorts #Military #DefenseTech #Warfare",
  "tags": ["military", "defensetech", "technology", "shorts", "aviation"],
  "scenes": [
    {{
      "scene_number": 1,
      "narration": "Narration text here.",
      "visual_prompt": "Cinematic vertical 9:16 shot of..."
    }}
  ]
}}
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content)

    @staticmethod
    def _generate_procedural(topic_info: Dict[str, Any], style: str = "default") -> Dict[str, Any]:
        topic = topic_info["topic"]
        clean_name = topic.split(":")[0] if ":" in topic else topic
        clean_name = clean_name.replace("The ", "").strip()
        topic_lower = topic.lower()

        # Check for specialized 15-second vertical takeoff / demo maneuver Short
        # Modeled on reference: https://www.youtube.com/shorts/DKWuJFZVaWU
        is_vertical_takeoff = any(kw in topic_lower for kw in ["vertical takeoff", "takeoff", "vertical climb", "demo team", "dkwujfzva"]) or ("f-22" in topic_lower and any(w in topic_lower for w in ["demo", "takeoff", "vertical"]))

        if is_vertical_takeoff:
            title = "F-22 Demo Team: Unrestricted Vertical Takeoff! 🚀🔥 #shorts"
            description = (
                "Watch the USAF F-22 Raptor Demonstration Team execute a maximum-performance unrestricted vertical climb!\n"
                "Twin Pratt & Whitney F119 afterburners unleash 70,000 lbs of thrust, shooting the stealth fighter straight up past 60,000 ft/min.\n\n"
                "#Shorts #F22 #F22Raptor #USAF #Aviation #FighterJet #Military #WeaponXLabs"
            )
            tags = ["f22 raptor", "f22 demo team", "vertical takeoff", "afterburner", "usaf", "aviation", "shorts", "fighter jet"]
            scenes = [
                {
                    "scene_number": 1,
                    "narration": "Watch this F-22 Raptor pull an unrestricted vertical takeoff!",
                    "visual_prompt": "USAF F-22 Raptor demonstration team rotating 90 degrees vertically off runway, twin Pratt and Whitney F119 afterburners glowing bright orange, heat distortion, 9:16 vertical"
                },
                {
                    "scene_number": 2,
                    "narration": "Twin afterburners unleash seventy thousand pounds of thrust, rocketing past sixty thousand feet per minute!",
                    "visual_prompt": "Extreme vertical angle of F-22 Raptor climbing pure vertical ninety degrees, glowing afterburner rings, shock diamonds, high G vapor over titanium wings, 9:16 vertical"
                },
                {
                    "scene_number": 3,
                    "narration": "Nothing on Earth matches the power of the Raptor. Is this the king of jets?",
                    "visual_prompt": "Epic vertical ascent of F-22 Raptor soaring into the clouds, glowing dusk horizon, cinematic military render, WeaponX Labs style, 9:16 vertical"
                }
            ]
            return {
                "title": title,
                "description": description,
                "tags": tags,
                "scenes": scenes
            }

        if style == "weaponx":
            hook = f"The next generation of military combat is officially here. Meet the {clean_name}."
            scenes = [
                {
                    "scene_number": 1,
                    "narration": hook,
                    "visual_prompt": f"Hyper-realistic 8k octane render of {clean_name} banking through dark storm clouds at dusk, glowing fiery amber afterburners, vapor cones, volumetric smoke, cinematic anamorphic lens flare, WeaponX Labs style, 9:16 vertical"
                },
                {
                    "scene_number": 2,
                    "narration": f"Engineered in complete secrecy, this weapon redefines battlefield dominance with cutting-edge lethal precision.",
                    "visual_prompt": f"Close-up technical view of {clean_name} weapons bay opening, hyper-detailed mechanical components, cold steel reflections, dramatic rim lighting, 9:16"
                },
                {
                    "scene_number": 3,
                    "narration": "It delivers catastrophic kinetic firepower before enemy radar networks can even identify the threat.",
                    "visual_prompt": f"Action shot of {clean_name} firing high-velocity payload over stormy ocean, supersonic shockwave, intense glowing muzzle flash, volumetric dusk lighting, 9:16"
                },
                {
                    "scene_number": 4,
                    "narration": "Equipped with advanced tactical telemetry, it outmaneuvers modern counter-battery and air defense systems.",
                    "visual_prompt": f"Tactical HUD telemetry targeting view locking onto coordinate data, glowing orange digital overlays, holographic wireframe of {clean_name}, cinematic dark military background, 9:16"
                },
                {
                    "scene_number": 5,
                    "narration": f"Is the {clean_name} the most dangerous weapon on Earth? Drop your verdict below.",
                    "visual_prompt": f"Hero silhouette of {clean_name} positioned on wet flight deck tarmac at night, glowing runway lights, armed tactical security team, epic scale, 9:16"
                }
            ]
            title = f"The Next Generation Is Here: {clean_name} 🚀🔥 #shorts"
            if len(title) > 95:
                title = f"{clean_name} Is Terrifying 🚀🔥 #shorts"
        else:
            hook = topic_info.get("hook", f"This classified military weapon changes global warfare forever.")
            scenes = [
                {
                    "scene_number": 1,
                    "narration": hook,
                    "visual_prompt": f"Cinematic photorealistic 8k vertical shot of {clean_name}, dramatic volumetric smoke, atmospheric orange and black lighting, military action, high octane, 9:16 vertical wallpaper, ultra-detailed Unreal Engine 5 render"
                },
                {
                    "scene_number": 2,
                    "narration": f"Meet the {clean_name}. Built for next-generation combat superiority.",
                    "visual_prompt": f"Close-up technical vertical view of {clean_name}, intricate mechanical armor plating, stealth coating texture, glowing radar avionics, futuristic military design, dramatic studio rim light, 9:16"
                },
                {
                    "scene_number": 3,
                    "narration": "Engineered with unmatched speed, stealth, and lethal precision to bypass traditional radar shields.",
                    "visual_prompt": f"Action shot of {clean_name} deployed in extreme combat environment, shockwaves, supersonic vapor cone, cinematic military documentary photography, vertical 9:16 ratio"
                },
                {
                    "scene_number": 4,
                    "narration": "It can detect, track, and eliminate strategic targets before enemy warning systems even trigger.",
                    "visual_prompt": f"Futuristic military command center heads-up display analyzing {clean_name}, glowing holographic target lock, tactical satellite map, cinematic vertical composition, 9:16"
                },
                {
                    "scene_number": 5,
                    "narration": f"Does this weapon make traditional defenses obsolete? Drop your thoughts in the comments.",
                    "visual_prompt": f"Silhouette of {clean_name} parked at a tactical airfield at dusk, ominous orange storm horizon, armed military guards, epic vertical cinematic scale, 9:16"
                }
            ]
            title = f"The Weapon Radar Can't Stop: {clean_name} 💥 #Shorts"
            if len(title) > 95:
                title = f"{clean_name} Exposed 💥 #Shorts"

        description = (
            f"Here is why the {topic} is redefining modern defense doctrine and military warfare.\n\n"
            f"#Shorts #Military #DefenseTech #Engineering #FutureWeapons #Aviation #Tech"
        )

        tags = [
            "military tech", "defense technology", "future weapons",
            clean_name.lower(), "us military", "shorts", "military history", "advanced tech"
        ]

        return {
            "title": title,
            "description": description,
            "tags": tags,
            "scenes": scenes
        }
