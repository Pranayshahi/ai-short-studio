"""
Procedural High-Resolution Sprite Generator for WeaponX Labs Charts
Generates authentic side-profile sprites for:
- Missiles & Hypersonic Gliders (missile_sprite_00 .. 11)
- Stealth Aircraft & Fighter Jets (jet_sprite_00 .. 05)
- Combat Pistols (pistol_sprite_00 .. 03)
- Main Battle Tanks (tank_sprite_00)
- Nuclear Submarines (sub_sprite_00)
All sprites are rendered at 650x130 with transparent/white background,
sharp tactical silhouettes, military panel details, radomes, intakes, and fins.
"""

from pathlib import Path
from PIL import Image, ImageDraw
import math

SPRITES_DIR = Path(__file__).resolve().parent.parent / "assets" / "sprites"
SPRITES_DIR.mkdir(parents=True, exist_ok=True)

W, H = 650, 130
CY = H // 2


def create_base_canvas():
    return Image.new("RGBA", (W, H), (255, 255, 255, 0))


# ---------------------------------------------------------------------------
# MISSILE SPRITES
# ---------------------------------------------------------------------------

def render_sm3_interceptor():
    """SM-3 Block IIA: 21-inch multi-stage ballistic missile interceptor."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Tail nozzle (x: 40..65)
    d.polygon([(65, CY - 14), (40, CY - 18), (40, CY + 18), (65, CY + 14)], fill=(35, 38, 42))
    # Mk 72 Booster (x: 65..190, r=20)
    d.rectangle([65, CY - 20, 190, CY + 20], fill=(230, 232, 235), outline=(90, 95, 100), width=2)
    # Tail steering fins (4 cruciform fins)
    d.polygon([(70, CY - 20), (50, CY - 46), (82, CY - 46), (95, CY - 20)], fill=(45, 48, 52), outline=(30, 32, 35))
    d.polygon([(70, CY + 20), (50, CY + 46), (82, CY + 46), (95, CY + 20)], fill=(45, 48, 52), outline=(30, 32, 35))
    # Interstage ring 1
    d.rectangle([190, CY - 21, 202, CY + 21], fill=(55, 58, 62), outline=(35, 38, 42))
    # Mk 104 Dual-Pulse Second Stage (x: 202..370, r=18)
    d.rectangle([202, CY - 18, 370, CY + 18], fill=(240, 242, 244), outline=(90, 95, 100), width=2)
    # Interstage ring 2
    d.rectangle([370, CY - 19, 382, CY + 19], fill=(55, 58, 62), outline=(35, 38, 42))
    # Mk 136 Third Stage & Attitude Control (x: 382..500, r=16)
    d.rectangle([382, CY - 16, 500, CY + 16], fill=(230, 232, 235), outline=(90, 95, 100), width=2)
    # Small mid-body guidance strakes
    d.polygon([(460, CY - 16), (440, CY - 28), (475, CY - 16)], fill=(60, 65, 70))
    d.polygon([(460, CY + 16), (440, CY + 28), (475, CY + 16)], fill=(60, 65, 70))
    # Kinetic Warhead Shroud & Ceramic Radome (x: 500..595)
    d.polygon([(500, CY - 16), (575, CY - 6), (595, CY), (575, CY + 6), (500, CY + 16)], fill=(40, 42, 45), outline=(20, 22, 25), width=2)
    # Warning stripe
    d.rectangle([230, CY - 18, 238, CY + 18], fill=(220, 40, 40))
    return img


def render_s400_sam():
    """S-400 Triumf 48N6DM Heavy Long-Range SAM with lattice grid tail fins."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Rocket nozzle
    d.polygon([(70, CY - 16), (45, CY - 21), (45, CY + 21), (70, CY + 16)], fill=(30, 32, 35))
    # Lattice Grid Fins at tail
    for oy in [-34, 34]:
        d.rectangle([60, CY + oy - 12, 105, CY + oy + 12], fill=(65, 70, 75), outline=(30, 32, 35), width=2)
        d.line([(60, CY + oy - 12), (105, CY + oy + 12)], fill=(40, 45, 50), width=2)
        d.line([(60, CY + oy + 12), (105, CY + oy - 12)], fill=(40, 45, 50), width=2)
    # Main heavy rocket body (x: 70..490, r=21)
    d.rectangle([70, CY - 21, 490, CY + 21], fill=(185, 190, 195), outline=(75, 80, 85), width=2)
    # 4 Long stabilizing strakes along midsection
    d.polygon([(220, CY - 21), (260, CY - 29), (420, CY - 29), (440, CY - 21)], fill=(55, 60, 65))
    d.polygon([(220, CY + 21), (260, CY + 29), (420, CY + 29), (440, CY + 21)], fill=(55, 60, 65))
    # Ogive pointed radome (x: 490..595)
    d.polygon([(490, CY - 21), (550, CY - 12), (595, CY), (550, CY + 12), (490, CY + 21)], fill=(45, 50, 55), outline=(25, 30, 35), width=2)
    # Russian defense markings
    d.rectangle([130, CY - 21, 142, CY + 21], fill=(210, 35, 35))
    d.rectangle([142, CY - 21, 154, CY + 21], fill=(240, 240, 240))
    d.rectangle([154, CY - 21, 166, CY + 21], fill=(30, 70, 160))
    return img


def render_s500_prometey():
    """S-500 Prometey 77N6 Anti-Hypersonic Interceptor."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Nozzle
    d.polygon([(60, CY - 18), (35, CY - 24), (35, CY + 24), (60, CY + 18)], fill=(25, 28, 30))
    # Delta tail fins
    d.polygon([(65, CY - 22), (45, CY - 48), (85, CY - 48), (105, CY - 22)], fill=(45, 48, 52))
    d.polygon([(65, CY + 22), (45, CY + 48), (85, CY + 48), (105, CY + 22)], fill=(45, 48, 52))
    # Heavy Stage 1 booster (x: 60..260, r=23)
    d.rectangle([60, CY - 23, 260, CY + 23], fill=(215, 220, 225), outline=(80, 85, 90), width=2)
    # Interstage taper
    d.polygon([(260, CY - 23), (290, CY - 19), (290, CY + 19), (260, CY + 23)], fill=(50, 55, 60))
    # Stage 2 hypersonic body (x: 290..480, r=19)
    d.rectangle([290, CY - 19, 480, CY + 19], fill=(225, 230, 235), outline=(80, 85, 90), width=2)
    # Mid-body control vanes
    d.polygon([(440, CY - 19), (420, CY - 33), (460, CY - 19)], fill=(40, 45, 50))
    d.polygon([(440, CY + 19), (420, CY + 33), (460, CY + 19)], fill=(40, 45, 50))
    # Hypersonic biconic heat-shield nose (x: 480..600)
    d.polygon([(480, CY - 19), (550, CY - 9), (600, CY), (550, CY + 9), (480, CY + 19)], fill=(35, 38, 42), outline=(15, 18, 20), width=2)
    d.rectangle([340, CY - 19, 350, CY + 19], fill=(205, 35, 35))
    return img


def render_patriot_pac3():
    """Patriot PAC-3 MSE: Point-defense hit-to-kill interceptor."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Nozzle
    d.polygon([(75, CY - 12), (55, CY - 15), (55, CY + 15), (75, CY + 12)], fill=(30, 30, 30))
    # Tail fins (4 delta fins)
    d.polygon([(75, CY - 16), (55, CY - 36), (90, CY - 16)], fill=(50, 55, 60))
    d.polygon([(75, CY + 16), (55, CY + 36), (90, CY + 16)], fill=(50, 55, 60))
    # Dual-pulse motor fuselage (x: 75..460, r=16)
    d.rectangle([75, CY - 16, 460, CY + 16], fill=(240, 242, 245), outline=(90, 95, 100), width=2)
    # ACM (Attitude Control Motors) collar ring (180 micro thrusters)
    d.rectangle([460, CY - 17, 485, CY + 17], fill=(45, 50, 55), outline=(25, 30, 35))
    # Conical seeker nose with active Ka-band radar (x: 485..585)
    d.polygon([(485, CY - 16), (560, CY - 5), (585, CY), (560, CY + 5), (485, CY + 16)], fill=(225, 220, 210), outline=(85, 80, 75), width=2)
    d.rectangle([180, CY - 16, 190, CY + 16], fill=(180, 40, 40))
    return img


def render_thaad_interceptor():
    """THAAD: Slender single-stage kinetic hit-to-kill interceptor."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Flared thrust-vectoring skirt at rear (x: 60..100)
    d.polygon([(60, CY - 24), (100, CY - 15), (100, CY + 15), (60, CY + 24)], fill=(40, 45, 50), outline=(20, 25, 30), width=2)
    # Long slender booster tube (x: 100..470, r=15)
    d.rectangle([100, CY - 15, 470, CY + 15], fill=(245, 245, 248), outline=(90, 95, 100), width=2)
    # Interstage ring
    d.rectangle([470, CY - 16, 485, CY + 16], fill=(50, 55, 60))
    # Kinetic kill vehicle nose cone with IR seeker window (x: 485..590)
    d.polygon([(485, CY - 15), (565, CY - 5), (590, CY), (565, CY + 5), (485, CY + 15)], fill=(35, 40, 45), outline=(15, 20, 25), width=2)
    d.polygon([(540, CY - 9), (565, CY - 5), (555, CY - 1)], fill=(70, 160, 220)) # Sapphire seeker window
    d.rectangle([210, CY - 15, 218, CY + 15], fill=(210, 35, 35))
    return img


def render_df17_hypersonic_glide():
    """DF-17 / DF-ZF: Hypersonic Waverider Glide Vehicle mounted on rocket booster."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Cylindrical rocket booster (x: 50..270, r=22)
    d.rectangle([50, CY - 22, 270, CY + 22], fill=(205, 210, 215), outline=(75, 80, 85), width=2)
    # Booster delta fins
    d.polygon([(50, CY - 22), (25, CY - 46), (75, CY - 22)], fill=(45, 50, 55))
    d.polygon([(50, CY + 22), (25, CY + 46), (75, CY + 22)], fill=(45, 50, 55))
    # Adapter interstage
    d.polygon([(270, CY - 22), (300, CY - 16), (300, CY + 16), (270, CY + 22)], fill=(50, 55, 60))
    # Hypersonic Waverider Delta Lifting Body (x: 300..610)
    # Wedge-shaped flat-top lifting fuselage with sharp chines
    d.polygon([
        (300, CY - 16),
        (300, CY - 36), # Upper delta canted stabilizer
        (350, CY - 16),
        (610, CY),      # Ultra-sharp hypersonic leading nose
        (350, CY + 16),
        (300, CY + 36), # Lower delta stabilizer
        (300, CY + 16),
    ], fill=(30, 32, 35), outline=(15, 18, 20), width=2)
    # Carbon-composite heat-shield leading edge (reinforced carbon-carbon dark orange/grey)
    d.polygon([(540, CY - 8), (610, CY), (540, CY + 8)], fill=(20, 22, 25))
    d.line([(350, CY), (580, CY)], fill=(60, 65, 70), width=2)
    d.rectangle([130, CY - 22, 142, CY + 22], fill=(215, 35, 35))
    return img


def render_zircon_scramjet():
    """3M22 Zircon: Scramjet-powered Hypersonic Cruise Missile."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Tail rocket booster nozzle
    d.polygon([(65, CY - 16), (40, CY - 21), (40, CY + 21), (65, CY + 16)], fill=(25, 28, 30))
    # Tail cruciform control fins
    d.polygon([(65, CY - 19), (45, CY - 44), (90, CY - 19)], fill=(40, 45, 50))
    d.polygon([(65, CY + 19), (45, CY + 44), (90, CY + 19)], fill=(40, 45, 50))
    # Main low-drag hypersonic fuselage (x: 65..480, r=19)
    d.rectangle([65, CY - 19, 480, CY + 19], fill=(190, 195, 200), outline=(75, 80, 85), width=2)
    # Mid-fuselage waverider compression strakes
    d.polygon([(260, CY - 19), (320, CY - 27), (440, CY - 19)], fill=(45, 50, 55))
    d.polygon([(260, CY + 19), (320, CY + 27), (440, CY + 19)], fill=(45, 50, 55))
    # Scramjet Chin Intake Scoop (lower compression ramp)
    d.polygon([(400, CY + 19), (480, CY + 28), (490, CY + 19)], fill=(25, 28, 30))
    # Hypersonic Chisel Nose (x: 480..605)
    d.polygon([(480, CY - 19), (570, CY - 8), (605, CY), (560, CY + 12), (480, CY + 19)], fill=(35, 38, 42), outline=(15, 18, 20), width=2)
    d.rectangle([140, CY - 19, 152, CY + 19], fill=(215, 35, 35))
    return img


def render_brahmos2_scramjet():
    """BrahMos II: Hypersonic Scramjet Cruise Missile with axisymmetric shock cone."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Rocket booster & nozzle
    d.polygon([(65, CY - 17), (40, CY - 22), (40, CY + 22), (65, CY + 17)], fill=(25, 28, 30))
    # Delta fins
    d.polygon([(70, CY - 19), (50, CY - 44), (95, CY - 19)], fill=(45, 50, 55))
    d.polygon([(70, CY + 19), (50, CY + 44), (95, CY + 19)], fill=(45, 50, 55))
    # Titanium-alloy cylindrical fuselage (x: 65..480, r=19)
    d.rectangle([65, CY - 19, 480, CY + 19], fill=(225, 228, 232), outline=(85, 90, 95), width=2)
    # Long stabilizing chine
    d.line([(200, CY - 20), (450, CY - 20)], fill=(50, 55, 60), width=3)
    d.line([(200, CY + 20), (450, CY + 20)], fill=(50, 55, 60), width=3)
    # Annular Scramjet Intake Cowl & Shock Spike (x: 480..600)
    d.rectangle([480, CY - 19, 530, CY + 19], fill=(45, 50, 55), outline=(20, 25, 30), width=2)
    # Centerbody supersonic shock cone
    d.polygon([(510, CY - 14), (600, CY), (510, CY + 14)], fill=(20, 22, 25), outline=(10, 12, 15), width=2)
    # Indian tricolor band
    d.rectangle([150, CY - 19, 160, CY + 19], fill=(255, 120, 30))
    d.rectangle([160, CY - 19, 170, CY + 19], fill=(250, 250, 250))
    d.rectangle([170, CY - 19, 180, CY + 19], fill=(20, 140, 40))
    return img


def render_asat_nudol():
    """A-235 Nudol: Heavy Anti-Satellite Interceptor."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Large heavy booster stage (x: 50..280, r=24)
    d.rectangle([50, CY - 24, 280, CY + 24], fill=(210, 215, 220), outline=(80, 85, 90), width=2)
    # Heavy base fins
    d.polygon([(50, CY - 24), (25, CY - 50), (80, CY - 24)], fill=(40, 45, 50))
    d.polygon([(50, CY + 24), (25, CY + 50), (80, CY + 24)], fill=(40, 45, 50))
    # Flared interstage (x: 280..320)
    d.polygon([(280, CY - 24), (320, CY - 18), (320, CY + 18), (280, CY + 24)], fill=(45, 50, 55))
    # Stage 2 exo-atmospheric body (x: 320..490, r=18)
    d.rectangle([320, CY - 18, 490, CY + 18], fill=(225, 230, 235), outline=(80, 85, 90), width=2)
    # Kinetic kill payload shroud (x: 490..595)
    d.polygon([(490, CY - 18), (560, CY - 8), (595, CY), (560, CY + 8), (490, CY + 18)], fill=(35, 40, 45), outline=(15, 20, 25), width=2)
    d.rectangle([180, CY - 24, 192, CY + 24], fill=(200, 35, 35))
    return img


def render_arrow3_interceptor():
    """Arrow 3: Exo-Atmospheric Hypersonic Interceptor with thrust-vectoring kill vehicle."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Booster nozzle
    d.polygon([(65, CY - 16), (40, CY - 20), (40, CY + 20), (65, CY + 16)], fill=(30, 32, 35))
    # Tail fins
    d.polygon([(65, CY - 18), (45, CY - 40), (85, CY - 18)], fill=(50, 55, 60))
    d.polygon([(65, CY + 18), (45, CY + 40), (85, CY + 18)], fill=(50, 55, 60))
    # Booster tube (x: 65..360, r=18)
    d.rectangle([65, CY - 18, 360, CY + 18], fill=(235, 238, 240), outline=(85, 90, 95), width=2)
    # Second stage with pivoting thrust-vectoring nozzle
    d.rectangle([360, CY - 15, 470, CY + 15], fill=(215, 220, 225), outline=(85, 90, 95), width=2)
    # Exo-atmospheric kill vehicle with sensor optics (x: 470..590)
    d.polygon([(470, CY - 15), (550, CY - 6), (590, CY), (550, CY + 6), (470, CY + 15)], fill=(40, 45, 50), outline=(20, 25, 30), width=2)
    d.rectangle([200, CY - 18, 210, CY + 18], fill=(30, 80, 180))
    return img


def render_kinzhal_missile():
    """Kh-47M2 Kinzhal: Air-launched hypersonic aero-ballistic missile."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Exhaust nozzle
    d.polygon([(65, CY - 17), (40, CY - 22), (40, CY + 22), (65, CY + 17)], fill=(25, 28, 30))
    # 4 Aerodynamic delta control fins at base
    d.polygon([(65, CY - 20), (40, CY - 46), (85, CY - 20)], fill=(45, 50, 55))
    d.polygon([(65, CY + 20), (40, CY + 46), (85, CY + 20)], fill=(45, 50, 55))
    # Cylindrical solid rocket motor body (x: 65..440, r=20)
    d.rectangle([65, CY - 20, 440, CY + 20], fill=(210, 215, 220), outline=(80, 85, 90), width=2)
    # Mid-body dorsal cable conduit fairing
    d.rectangle([120, CY - 23, 400, CY - 20], fill=(60, 65, 70))
    # Long conical ogive nose cone (Mach 10 heat-resistant) (x: 440..605)
    d.polygon([(440, CY - 20), (550, CY - 9), (605, CY), (550, CY + 9), (440, CY + 20)], fill=(35, 38, 42), outline=(15, 18, 20), width=2)
    d.rectangle([180, CY - 20, 192, CY + 20], fill=(215, 35, 35))
    return img


def render_avangard_glider():
    """Avangard: Hypersonic Glide Vehicle (Mach 27 lifting body)."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Heavy booster stage (x: 50..250, r=23)
    d.rectangle([50, CY - 23, 250, CY + 23], fill=(200, 205, 210), outline=(75, 80, 85), width=2)
    # Tail fins
    d.polygon([(50, CY - 23), (25, CY - 48), (75, CY - 23)], fill=(40, 45, 50))
    d.polygon([(50, CY + 23), (25, CY + 48), (75, CY + 23)], fill=(40, 45, 50))
    # Avangard Waverider Glider (sharp delta lifting body with trailing control flaps)
    d.polygon([
        (250, CY - 20),
        (250, CY - 38), # Upper stabilizing winglet
        (330, CY - 18),
        (615, CY),      # Ultra-sharp tungsten-alloy nose
        (330, CY + 18),
        (250, CY + 38), # Lower stabilizing winglet
        (250, CY + 20),
    ], fill=(25, 28, 30), outline=(10, 12, 15), width=2)
    # Thermal protection tiles
    d.line([(320, CY), (570, CY)], fill=(50, 55, 60), width=2)
    d.rectangle([120, CY - 23, 132, CY + 23], fill=(215, 35, 35))
    return img


# ---------------------------------------------------------------------------
# FIGHTER JET / COMBAT AIRCRAFT SPRITES
# ---------------------------------------------------------------------------

def render_f22_raptor():
    """F-22 Raptor side profile: chined stealth nose, bubble canopy, twin canted rudders."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # 2D Thrust-vectoring exhaust nozzle (x: 50..85)
    d.polygon([(50, CY - 10), (85, CY - 14), (85, CY + 14), (50, CY + 10)], fill=(30, 32, 35))
    # Twin canted vertical stabilizers
    d.polygon([(85, CY - 14), (120, CY - 52), (180, CY - 52), (210, CY - 14)], fill=(90, 95, 100), outline=(40, 45, 50), width=2)
    # Main stealth fuselage & horizontal stabilizer
    d.polygon([
        (85, CY - 14),
        (180, CY - 16),
        (280, CY - 14),
        (360, CY - 24), # Bubble cockpit canopy
        (430, CY - 24),
        (510, CY - 8),  # Chined stealth nose
        (580, CY),      # Pitot nose tip
        (510, CY + 8),
        (380, CY + 16), # Engine air intake
        (260, CY + 16),
        (85, CY + 14),
    ], fill=(130, 135, 142), outline=(50, 55, 60), width=2)
    # Cockpit canopy glass (gold-tinted radar reflective)
    d.polygon([(365, CY - 15), (380, CY - 22), (425, CY - 22), (445, CY - 15)], fill=(180, 150, 60, 220))
    # Air intake scoop
    d.polygon([(340, CY + 16), (380, CY + 16), (360, CY + 24), (320, CY + 24)], fill=(40, 45, 50))
    return img


def render_f35_lightning():
    """F-35 Lightning II stealth multirole fighter profile."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Single engine nozzle with serrated low-observable petals
    d.polygon([(55, CY - 11), (90, CY - 14), (90, CY + 14), (55, CY + 11)], fill=(30, 32, 35))
    # Vertical stabilizer
    d.polygon([(90, CY - 14), (130, CY - 50), (180, CY - 50), (210, CY - 14)], fill=(85, 90, 96), outline=(40, 45, 50), width=2)
    # Fuselage & canopy
    d.polygon([
        (90, CY - 14),
        (260, CY - 16),
        (340, CY - 26),
        (420, CY - 26),
        (500, CY - 7),
        (575, CY),
        (500, CY + 7),
        (370, CY + 18),
        (240, CY + 18),
        (90, CY + 14),
    ], fill=(120, 125, 130), outline=(45, 50, 55), width=2)
    # Gold-tinted canopy
    d.polygon([(345, CY - 16), (360, CY - 24), (410, CY - 24), (430, CY - 16)], fill=(185, 155, 70, 220))
    return img


def render_b2_spirit():
    """B-2 Spirit / B-21 Raider: Flying wing stealth strategic bomber profile."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Ultra-low profile blended wing-body (slender horizontal profile)
    d.polygon([
        (50, CY),
        (120, CY - 10),
        (240, CY - 14), # Exhaust trough
        (340, CY - 20), # Cockpit hump
        (420, CY - 20),
        (510, CY - 10),
        (585, CY),      # Rounded stealth leading edge nose
        (510, CY + 10),
        (340, CY + 14),
        (120, CY + 10),
        (50, CY),
    ], fill=(45, 48, 52), outline=(20, 22, 25), width=2)
    # Narrow cockpit windows
    d.polygon([(380, CY - 14), (405, CY - 18), (430, CY - 14)], fill=(120, 140, 160))
    return img


# ---------------------------------------------------------------------------
# PISTOL SPRITES
# ---------------------------------------------------------------------------

def render_m1911_pistol():
    """Colt M1911 classic .45 ACP authentic handgun silhouette with proper proportions."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Slide (x: 235..420, y: 18..54)
    d.rounded_rectangle([235, 18, 420, 54], radius=3, fill=(42, 45, 48), outline=(20, 22, 24), width=2)
    # Muzzle bushing & barrel
    d.rectangle([420, 24, 425, 48], fill=(30, 32, 34))
    # Sights
    d.polygon([(406, 18), (414, 18), (412, 12), (408, 12)], fill=(20, 22, 24))
    d.polygon([(242, 18), (252, 18), (250, 12), (244, 12)], fill=(20, 22, 24))
    # Slide serrations
    for sx in range(252, 286, 4):
        d.line([(sx, 24), (sx, 48)], fill=(28, 30, 32), width=2)
    # Ejection port
    d.rectangle([325, 20, 360, 32], fill=(24, 26, 28))

    # Frame & trigger guard
    d.polygon([(240, 54), (410, 54), (405, 68), (345, 68), (345, 92), (300, 92), (292, 70), (240, 70)], fill=(38, 40, 42), outline=(20, 22, 24))
    d.polygon([(300, 70), (338, 70), (334, 86), (306, 86)], fill=(255, 255, 255, 0))
    # Trigger
    d.line([(316, 72), (320, 82), (314, 82)], fill=(160, 165, 170), width=3)
    # Beavertail & Hammer
    d.polygon([(240, 54), (220, 48), (236, 68)], fill=(35, 38, 40))
    d.polygon([(236, 32), (224, 26), (232, 42)], fill=(50, 54, 58))

    # Grip
    d.polygon([(242, 68), (294, 68), (268, 124), (216, 124)], fill=(120, 70, 35), outline=(20, 22, 24), width=2)
    for gy in range(74, 120, 5):
        d.line([(242 - (gy-70)//4, gy), (288 - (gy-70)//3, gy)], fill=(100, 58, 28), width=1)
    return img


def render_glock_pistol():
    """Glock 17 / tactical polymer striker-fired pistol profile."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Squared Tenifer slide (x: 230..425, y: 16..52)
    d.rounded_rectangle([230, 16, 425, 52], radius=2, fill=(30, 32, 35), outline=(15, 16, 18), width=2)
    # Sights
    d.rectangle([412, 11, 418, 16], fill=(220, 220, 220))
    d.rectangle([238, 11, 246, 16], fill=(220, 220, 220))
    # Rear slide serrations
    for sx in range(244, 280, 4):
        d.line([(sx, 22), (sx, 46)], fill=(18, 20, 22), width=2)
    # Ejection port
    d.rectangle([320, 18, 355, 30], fill=(20, 22, 24))

    # Polymer frame with accessory rail
    d.polygon([(236, 52), (420, 52), (418, 66), (348, 66), (346, 90), (298, 90), (290, 68), (236, 68)], fill=(36, 38, 42), outline=(15, 16, 18))
    d.polygon([(298, 68), (340, 68), (336, 84), (304, 84)], fill=(255, 255, 255, 0))
    # Safe action trigger
    d.line([(316, 70), (320, 80), (315, 80)], fill=(20, 22, 24), width=3)
    # Grip with finger grooves
    d.polygon([(238, 68), (292, 68), (270, 124), (218, 124)], fill=(32, 34, 38), outline=(15, 16, 18), width=2)
    # Grip texturing
    for gy in range(74, 120, 4):
        d.line([(240 - (gy-70)//4, gy), (286 - (gy-70)//3, gy)], fill=(22, 24, 26), width=2)
    return img


# ---------------------------------------------------------------------------
# TANK & SUBMARINE SPRITES
# ---------------------------------------------------------------------------

def render_tank_mbt():
    """Modern Main Battle Tank (M1A2 / T-90) horizontal side profile."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Continuous track assembly (x: 140..480, y: CY+18..CY+48)
    d.rectangle([140, CY + 18, 480, CY + 48], fill=(40, 42, 45), outline=(20, 22, 25), width=2)
    # Road wheels
    for wx in range(165, 465, 50):
        d.ellipse([wx - 18, CY + 22, wx + 18, CY + 44], fill=(65, 68, 72), outline=(25, 28, 30), width=2)
    # Armored hull with side skirts
    d.polygon([(120, CY + 18), (140, CY - 4), (470, CY - 4), (495, CY + 18)], fill=(115, 120, 105), outline=(45, 50, 40), width=2)
    # Low-profile turret
    d.polygon([(220, CY - 4), (245, CY - 28), (380, CY - 28), (410, CY - 4)], fill=(105, 110, 95), outline=(40, 45, 35), width=2)
    # 120mm Smoothbore Gun Barrel with bore evacuator (x: 380..590)
    d.rectangle([380, CY - 18, 580, CY - 12], fill=(85, 90, 80), outline=(35, 40, 30), width=2)
    d.rectangle([470, CY - 21, 510, CY - 9], fill=(65, 70, 60)) # Bore evacuator
    return img


def render_submarine_nuclear():
    """Nuclear Ballistic Missile Submarine (Ohio / Borei class) profile."""
    img = create_base_canvas()
    d = ImageDraw.Draw(img)
    # Pump-jet propulsor at tail
    d.polygon([(70, CY - 14), (45, CY - 20), (45, CY + 20), (70, CY + 14)], fill=(30, 32, 35))
    # Cruciform stern dive planes
    d.polygon([(65, CY - 18), (40, CY - 36), (75, CY - 18)], fill=(45, 48, 52))
    d.polygon([(65, CY + 18), (40, CY + 36), (75, CY + 18)], fill=(45, 48, 52))
    # Teardrop hydrodynamic hull (x: 70..560, r=26)
    d.polygon([
        (70, CY - 16),
        (180, CY - 24),
        (380, CY - 24),
        (510, CY - 18),
        (565, CY),      # Rounded acoustic sonar dome
        (510, CY + 18),
        (380, CY + 24),
        (180, CY + 24),
        (70, CY + 16),
    ], fill=(42, 45, 48), outline=(20, 22, 25), width=2)
    # Sail / Conning tower with fairwater dive planes
    d.polygon([(360, CY - 24), (370, CY - 50), (420, CY - 50), (430, CY - 24)], fill=(35, 38, 42), outline=(15, 18, 20), width=2)
    d.line([(385, CY - 42), (415, CY - 42)], fill=(70, 75, 80), width=3) # Fairwater dive plane
    # Red anti-fouling lower waterline
    d.polygon([(180, CY + 16), (380, CY + 16), (500, CY + 12), (380, CY + 24), (180, CY + 24)], fill=(160, 40, 40))
    return img


# ---------------------------------------------------------------------------
# MAIN REGISTRY AND BUILD DISPATCH
# ---------------------------------------------------------------------------

ALL_SPRITE_BUILDERS = {
    "missile_sprite_00.png": render_sm3_interceptor,
    "missile_sprite_01.png": render_s400_sam,
    "missile_sprite_02.png": render_s500_prometey,
    "missile_sprite_03.png": render_patriot_pac3,
    "missile_sprite_04.png": render_thaad_interceptor,
    "missile_sprite_05.png": render_df17_hypersonic_glide,
    "missile_sprite_06.png": render_zircon_scramjet,
    "missile_sprite_07.png": render_brahmos2_scramjet,
    "missile_sprite_08.png": render_asat_nudol,
    "missile_sprite_09.png": render_arrow3_interceptor,
    "missile_sprite_10.png": render_kinzhal_missile,
    "missile_sprite_11.png": render_avangard_glider,
    # Aircraft
    "jet_sprite_00.png": render_f22_raptor,
    "jet_sprite_01.png": render_f35_lightning,
    "jet_sprite_02.png": render_b2_spirit,
    # Handguns
    "pistol_sprite_00.png": render_m1911_pistol,
    "pistol_sprite_01.png": render_glock_pistol,
    # Armor & Naval
    "tank_sprite_00.png": render_tank_mbt,
    "sub_sprite_00.png": render_submarine_nuclear,
}


def build_all_sprites():
    created = 0
    for fname, func in ALL_SPRITE_BUILDERS.items():
        out_path = SPRITES_DIR / fname
        img = func()
        img.save(out_path, "PNG")
        created += 1
        print(f"   [Sprite Generator] ✓ Built {fname} ({out_path.stat().st_size} bytes)")
    print(f"\n[Sprite Generator] Successfully generated {created} authentic tactical weapon sprites in {SPRITES_DIR}!")


if __name__ == "__main__":
    build_all_sprites()

