import os

W, H = 1280, 720          # logical HUD resolution
SW, SH = 960, 540         # 3D scene buffer (upscaled to W,H)
FPS = 60

# ---------- palette (same language as the teaser) ----------
BG_TOP = (17, 28, 54)
BG_BOT = (7, 12, 24)
BG_MID = (13, 21, 40)
PANEL = (9, 16, 30)
PANEL_L = (16, 27, 48)
WHITE = (236, 244, 255)
SOFT = (152, 186, 228)
DIM = (98, 126, 172)
TEAL = (46, 232, 214)
CYAN = (92, 204, 255)
GOLD = (255, 197, 92)
GOLD_D = (186, 126, 44)
HULL = (72, 120, 182)
HULL_L = (112, 168, 228)
HULL_D = (44, 78, 128)
DARKM = (22, 34, 56)
GLASS = (98, 222, 250)
RED = (255, 104, 104)
GREEN = (122, 232, 160)

FONT_DIR = 'C:/Windows/Fonts'
FONTS = {
    'tech': 'bahnschrift.ttf',
    'mono': 'consola.ttf',
    'bold': 'consolab.ttf',
    'ui': 'segoeui.ttf',
}

# ---------- economy ----------
START_CREDITS = 1250
CRAFT_COST = 250
MAX_CUSTOM = 10
CAMPAIGN_BONUS = 500

# ---------- progression ----------
CLEAR_RATIO = 0.60          # B or better opens the next sector
GRADE_ORDER = ('F', 'C', 'B', 'A', 'S')
MATERIALS = (
    {'id': 'alloy', 'name': 'ALLOY', 'thrust': 1.00, 'mass': 1.00, 'cost': 0,
     'color': HULL_D, 'desc': 'BALANCED / CHEAP'},
    {'id': 'composite', 'name': 'COMPOSITE', 'thrust': 0.94, 'mass': 0.78, 'cost': 120,
     'color': (52, 112, 128), 'desc': 'LIGHT / SOFTER'},
    {'id': 'carbon', 'name': 'CARBON', 'thrust': 1.08, 'mass': 0.86, 'cost': 220,
     'color': (34, 44, 62), 'desc': 'STIFF / EXPENSIVE'},
)

# ---------- paint ----------
PAINTS = (
    {'id': 'factory', 'name': 'FACTORY', 'desc': 'BLUE / GOLD · STOCK FINISH',
     'hull': HULL, 'deck': HULL_L, 'accent': GOLD, 'blade': GOLD},
    {'id': 'royal', 'name': 'ROYAL', 'desc': 'DEEP BLUE / WARM GOLD',
     'hull': (54, 88, 164), 'deck': (88, 130, 208), 'accent': (255, 205, 108),
     'blade': (255, 214, 130)},
    {'id': 'crimson', 'name': 'CRIMSON', 'desc': 'BLOOD RED / EMBER TRIM',
     'hull': (122, 40, 50), 'deck': (172, 62, 74), 'accent': (255, 158, 122),
     'blade': (255, 184, 150)},
    {'id': 'jade', 'name': 'JADE', 'desc': 'GREEN / MINT LIGHTS',
     'hull': (30, 92, 82), 'deck': (54, 138, 118), 'accent': (150, 244, 206),
     'blade': (176, 248, 216)},
    {'id': 'stealth', 'name': 'STEALTH', 'desc': 'GUNMETAL / ICE TRIM',
     'hull': (36, 44, 60), 'deck': (60, 72, 96), 'accent': (124, 202, 255),
     'blade': (154, 222, 255)},
    {'id': 'solar', 'name': 'SOLAR', 'desc': 'AMBER / CREAM EDGE',
     'hull': (158, 98, 32), 'deck': (212, 144, 56), 'accent': (255, 234, 158),
     'blade': (255, 238, 176)},
    {'id': 'violet', 'name': 'VIOLET', 'desc': 'PURPLE / NEON LILAC',
     'hull': (74, 56, 122), 'deck': (112, 88, 176), 'accent': (206, 168, 255),
     'blade': (218, 186, 255)},
    {'id': 'arctic', 'name': 'ARCTIC', 'desc': 'PALE STEEL / CYAN LIGHT',
     'hull': (144, 168, 194), 'deck': (188, 210, 232), 'accent': (92, 204, 255),
     'blade': (132, 225, 255)},
    {'id': 'copper', 'name': 'COPPER', 'desc': 'BURNT COPPER / CREAM EDGE',
     'hull': (146, 74, 42), 'deck': (198, 110, 62), 'accent': (255, 206, 142),
     'blade': (255, 220, 170)},
    {'id': 'magma', 'name': 'MAGMA', 'desc': 'DARK ROCK / LAVA TRIM',
     'hull': (78, 30, 26), 'deck': (128, 48, 38), 'accent': (255, 128, 44),
     'blade': (255, 164, 74)},
    {'id': 'obsidian', 'name': 'OBSIDIAN', 'desc': 'BLACK GLASS / RED LIGHT',
     'hull': (22, 24, 32), 'deck': (40, 44, 58), 'accent': (255, 74, 90),
     'blade': (255, 120, 120)},
    {'id': 'toxic', 'name': 'TOXIC', 'desc': 'SWAMP GREEN / ACID EDGE',
     'hull': (44, 64, 26), 'deck': (78, 110, 38), 'accent': (196, 255, 72),
     'blade': (220, 255, 120)},
    {'id': 'coral', 'name': 'CORAL', 'desc': 'SALMON SHELL / PEARL TRIM',
     'hull': (168, 74, 92), 'deck': (214, 108, 124), 'accent': (255, 214, 198),
     'blade': (255, 228, 214)},
    {'id': 'sand', 'name': 'SAND', 'desc': 'DESERT TAN / TURQUOISE',
     'hull': (152, 130, 88), 'deck': (198, 174, 118), 'accent': (66, 206, 196),
     'blade': (132, 240, 226)},
    {'id': 'indigo', 'name': 'INDIGO', 'desc': 'NIGHT BLUE / COBALT GLOW',
     'hull': (44, 44, 110), 'deck': (74, 76, 164), 'accent': (122, 160, 255),
     'blade': (164, 190, 255)},
    {'id': 'ember', 'name': 'EMBER', 'desc': 'SOOT CHARCOAL / FIRE ORANGE',
     'hull': (58, 42, 36), 'deck': (96, 64, 48), 'accent': (255, 142, 52),
     'blade': (255, 176, 92)},
    {'id': 'rose', 'name': 'ROSE', 'desc': 'MAGENTA SHELL / PINK LIGHT',
     'hull': (150, 58, 110), 'deck': (198, 96, 148), 'accent': (255, 200, 228),
     'blade': (255, 214, 236)},
    {'id': 'phantom', 'name': 'PHANTOM', 'desc': 'SLATE GREY / LIME SCAN',
     'hull': (58, 66, 72), 'deck': (86, 98, 104), 'accent': (180, 255, 120),
     'blade': (204, 255, 154)},
    {'id': 'aurora', 'name': 'AURORA', 'desc': 'DEEP TEAL / MINT CURTAIN',
     'hull': (24, 54, 78), 'deck': (38, 96, 112), 'accent': (140, 255, 198),
     'blade': (172, 255, 218)},
    {'id': 'voltage', 'name': 'VOLTAGE', 'desc': 'MIDNIGHT / ELECTRIC YELLOW',
     'hull': (32, 38, 58), 'deck': (48, 58, 88), 'accent': (255, 230, 84),
     'blade': (255, 240, 144)},
)

# ---------- sectors ----------
SECTORS = (
    {'name': 'SECTOR 01', 'sub': 'STREET CIRCUIT', 'price': 0, 'cores': 8,
     'mines': 3, 'pads': 4,
     'xr': 1.8, 'yr': 0.9, 'gap': 22.0, 'reward': 1.00,
     'wind': 0.45, 'turb': 0.0,
     'challenge': 'OPEN ROAD', 'brief': 'DAYLIGHT STREET · MIND THE SIGN GANTRIES',
     'sky': (40, 54, 126), 'sky2': (146, 116, 164), 'sky3': (255, 198, 136),
     'line': (255, 206, 130)},
    {'name': 'SECTOR 02', 'sub': 'FOREST RUN', 'price': 260, 'cores': 12,
     'mines': 7, 'pads': 5,
     'xr': 2.4, 'yr': 1.4, 'gap': 23.0, 'reward': 1.35,
     'wind': 1.0, 'turb': 0.25,
     'challenge': 'TREELINE', 'brief': 'SIDE GUSTS BETWEEN THE TRUNKS',
     'sky': (36, 74, 132), 'sky2': (128, 148, 176), 'sky3': (255, 208, 152),
     'line': (255, 214, 142)},
    {'name': 'SECTOR 03', 'sub': 'ORBITAL REEF', 'price': 700, 'cores': 16,
     'mines': 10, 'pads': 6,
     'xr': 2.9, 'yr': 1.75, 'gap': 24.0, 'reward': 1.80,
     'wind': 1.5, 'turb': 0.6,
     'challenge': 'GRAV STORM', 'brief': 'HEAVY TURBULENCE · TRIM IS EVERYTHING',
     'sky': (10, 34, 48), 'sky2': (3, 8, 16), 'line': (64, 170, 170)},
)

SAVE_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'Blueprint')
SAVE_PATH = os.path.join(SAVE_DIR, 'save.json')
