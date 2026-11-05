# -*- coding: utf-8 -*-
"""
POCKET QUEST - a 2D pixel top-down monster-catching RPG
Made with pygame. Works on PC and on Android in Pydroid 3 (touch controls built in).

Everything (tiles, characters, monsters) is drawn with code - no image files needed.

HOW TO PLAY
  LANDSCAPE layout - turn your phone sideways (rotate / unlock auto-rotate).
  Touch: D-pad = move / menu cursor, A = talk / confirm, B (or L) = cancel / hold to RUN,
         START (or R) = pause menu
  Keyboard: Arrows/WASD move, Z/Enter/Space = A, X/Shift = B, Esc/Tab = menu
"""
import os, sys, json, math, random, time
from collections import deque
import pygame

# =====================================================================
#                      >>>  EDIT THESE  <<<
# =====================================================================
GAME_TITLE   = "POCKET QUEST"      # <- change the game name here
PLAYER_NAME  = "ASH"
RIVAL_NAME   = "BLAKE"
PROF_NAME    = "PROF. WILLOW"
LEADER_NAME  = "VOLTA"
BADGE_NAME   = "SPARK BADGE"
CURRENCY     = "$"
START_MONEY  = 500
ENCOUNTER_RATE   = 0.14    # chance per step in tall grass
WALK_SPEED       = 2.0     # pixels per frame (tile = 16px)
RUN_SPEED        = 3.2
DAY_CYCLE_SECONDS = 480    # length of one full day/night cycle
SAVE_FILE    = "pocket_quest_save.json"
# =====================================================================

pygame.init()
ANDROID = ('ANDROID_ROOT' in os.environ) or hasattr(sys, 'getandroidapilevel')
SW, SH = 512, 288          # logical screen (LANDSCAPE 16:9) - the whole screen is the game
LW, GAME_H = 320, 288      # size of the menu/battle panel (those screens are laid out for 320x288)
UX = (SW - LW) // 2        # x offset that centres that panel on the wide screen
VIEW_W, VIEW_H = 256, 144  # world render size (scaled 2x -> chunky pixels, shows more map)

if ANDROID:
    window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
else:
    window = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
pygame.display.set_caption(GAME_TITLE)
screen = pygame.Surface((SW, SH))
world = pygame.Surface((VIEW_W, VIEW_H))
DARK_OV = pygame.Surface((VIEW_W, VIEW_H)); DARK_OV.fill((12, 14, 60))
FADE_OV = pygame.Surface((SW, SH))
ui_base = pygame.Surface((LW, GAME_H))                 # battle / title panel
ui_over = pygame.Surface((LW, GAME_H), pygame.SRCALPHA)  # dialogue / pause menu panel
VIEW = (1.0, 0, 0)

try:
    SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), SAVE_FILE)
except Exception:
    SAVE_PATH = SAVE_FILE

FONT_S = pygame.font.Font(None, 17)
FONT_M = pygame.font.Font(None, 22)
FONT_L = pygame.font.Font(None, 30)
FONT_XL = pygame.font.Font(None, 52)

def clamp(v, a, b): return max(a, min(b, v))

TEXT_CACHE = {}
def text_img(s, font, col):
    k = (str(s), id(font), col)
    im = TEXT_CACHE.get(k)
    if im is None:
        if len(TEXT_CACHE) > 800: TEXT_CACHE.clear()
        im = TEXT_CACHE[k] = font.render(str(s), False, col)
    return im

def put(surf, s, x, y, font=FONT_M, col=(32, 32, 40), shadow=None, center=False, right=False):
    img = text_img(s, font, col)
    if center: x = x - img.get_width() // 2
    if right: x = x - img.get_width()
    if shadow:
        surf.blit(text_img(s, font, shadow), (x + 1, y + 1))
    surf.blit(img, (x, y))

def box(surf, r, fill=(250, 248, 240), border=(40, 40, 60)):
    r = pygame.Rect(r)
    pygame.draw.rect(surf, border, r)
    pygame.draw.rect(surf, fill, r.inflate(-4, -4))
    pygame.draw.rect(surf, (130, 130, 170), r.inflate(-4, -4), 1)

def wrap(txt, font, width):
    lines = []
    for para in str(txt).split('\n'):
        cur = ''
        for w in para.split(' '):
            t = (cur + ' ' + w).strip()
            if font.size(t)[0] <= width: cur = t
            else:
                lines.append(cur); cur = w
        lines.append(cur)
    return lines

def paginate(txt, width=288):
    lines = wrap(txt, FONT_M, width)
    return ['\n'.join(lines[i:i + 3]) for i in range(0, len(lines), 3)] or ['']

def draw_typed(surf, page, shown, x, y, lh=22, col=(32, 32, 40)):
    rem = int(shown)
    for ln in page.split('\n'):
        if rem <= 0: break
        put(surf, ln[:rem], x, y, FONT_M, col)
        rem -= len(ln) + 1
        y += lh

def draw_bar(surf, x, y, w, h, frac, col=None):
    frac = clamp(frac, 0, 1)
    pygame.draw.rect(surf, (40, 40, 56), (x - 1, y - 1, w + 2, h + 2))
    pygame.draw.rect(surf, (200, 200, 208), (x, y, w, h))
    if col is None:
        col = (80, 200, 80) if frac > 0.5 else (240, 200, 40) if frac > 0.2 else (230, 70, 60)
    pygame.draw.rect(surf, col, (x, y, int(w * frac), h))

# =====================================================================
#                       TILES (pixel art generated in code)
# =====================================================================
(GRASS, PATH, TREE, WATER, TALL, ROOF_R, ROOF_B, WALL, WINDOW, DOOR, FLOOR, IWALL,
 FLOWER, FENCE, SIGN, COUNTER, MAT, STONE, POT, BED, TABLE, HEAL, SHELF, GYMF,
 STATUE, LAMP, RUG, TV, BALLS) = range(29)
SOLID = {TREE, WATER, ROOF_R, ROOF_B, WALL, WINDOW, IWALL, FENCE, SIGN, COUNTER, POT, BED,
         TABLE, HEAL, SHELF, STATUE, LAMP, TV, BALLS}

def surf16(c):
    s = pygame.Surface((16, 16)); s.fill(c); return s

def sprinkle(s, cols, n, seed):
    r = random.Random(seed)
    for _ in range(n):
        s.set_at((r.randrange(16), r.randrange(16)), r.choice(cols))

def build_tiles():
    T = {}
    def grass(seed=1):
        s = surf16((96, 172, 64)); sprinkle(s, [(84, 156, 56), (112, 188, 78)], 26, seed); return s
    def floor():
        s = surf16((206, 160, 104))
        for y in range(0, 16, 4): pygame.draw.line(s, (176, 130, 80), (0, y), (15, y))
        for (x, y) in ((4, 1), (11, 6), (6, 9), (13, 13)): s.set_at((x, y), (176, 130, 80))
        return s
    def stone():
        s = surf16((178, 178, 188))
        pygame.draw.line(s, (150, 150, 162), (0, 7), (15, 7)); pygame.draw.line(s, (150, 150, 162), (7, 0), (7, 7))
        pygame.draw.line(s, (150, 150, 162), (12, 8), (12, 15)); sprinkle(s, [(196, 196, 204)], 10, 5)
        return s
    T[GRASS] = grass()
    p = surf16((218, 194, 134)); sprinkle(p, [(204, 178, 118), (232, 210, 152)], 22, 2); T[PATH] = p
    s = grass(3)
    pygame.draw.rect(s, (110, 72, 40), (6, 10, 4, 6))
    pygame.draw.circle(s, (34, 100, 44), (8, 7), 7)
    pygame.draw.circle(s, (54, 138, 58), (6, 5), 4)
    pygame.draw.circle(s, (80, 170, 76), (5, 4), 2)
    T[TREE] = s
    def water(f):
        s = surf16((52, 116, 208))
        for y in (3, 9, 14):
            for x in range(16):
                if (x + y * 3 + f * 4) % 8 < 3: s.set_at((x, y), (130, 184, 255))
        return s
    T[WATER] = [water(0), water(1)]
    s = surf16((72, 148, 52))
    for x in (2, 6, 10, 14):
        pygame.draw.line(s, (36, 104, 36), (x, 15), (x - 1, 7)); pygame.draw.line(s, (36, 104, 36), (x, 15), (x + 2, 8))
        s.set_at((x - 1, 7), (140, 220, 96)); s.set_at((x + 2, 8), (140, 220, 96))
    T[TALL] = s
    for tid, c1, c2 in ((ROOF_R, (196, 60, 52), (148, 40, 40)), (ROOF_B, (62, 100, 190), (40, 68, 146))):
        s = surf16(c1)
        for y in range(0, 16, 4):
            pygame.draw.line(s, c2, (0, y + 3), (15, y + 3))
            for x in range(((y // 4) % 2) * 4, 16, 8): pygame.draw.line(s, c2, (x, y), (x, y + 2))
        T[tid] = s
    wall = surf16((242, 228, 192)); pygame.draw.line(wall, (206, 190, 150), (0, 15), (15, 15)); T[WALL] = wall
    s = wall.copy(); pygame.draw.rect(s, (90, 60, 40), (3, 3, 10, 9)); pygame.draw.rect(s, (110, 180, 236), (4, 4, 8, 7))
    pygame.draw.line(s, (90, 60, 40), (8, 4), (8, 10)); pygame.draw.line(s, (90, 60, 40), (4, 7), (11, 7)); T[WINDOW] = s
    s = wall.copy(); pygame.draw.rect(s, (110, 66, 32), (3, 1, 10, 15)); pygame.draw.rect(s, (150, 94, 48), (4, 2, 8, 13))
    pygame.draw.rect(s, (250, 220, 60), (10, 9, 2, 2)); T[DOOR] = s
    T[FLOOR] = floor()
    s = surf16((150, 130, 172)); pygame.draw.rect(s, (112, 92, 134), (0, 11, 16, 5)); pygame.draw.line(s, (180, 160, 200), (0, 0), (15, 0)); T[IWALL] = s
    s = grass(4)
    for (x, y, c) in ((3, 3, (240, 70, 70)), (10, 4, (250, 220, 60)), (6, 10, (255, 255, 255)), (12, 12, (240, 130, 200))):
        pygame.draw.rect(s, c, (x, y, 2, 2)); s.set_at((x, y), (250, 240, 120))
    T[FLOWER] = s
    s = grass(5)
    for y in (5, 10): pygame.draw.rect(s, (166, 112, 62), (0, y, 16, 2))
    for x in (1, 7, 13): pygame.draw.rect(s, (130, 84, 44), (x, 3, 2, 12))
    T[FENCE] = s
    s = grass(6); pygame.draw.rect(s, (120, 80, 40), (7, 9, 2, 7)); pygame.draw.rect(s, (210, 160, 96), (2, 2, 12, 8))
    pygame.draw.rect(s, (110, 72, 36), (2, 2, 12, 8), 1); pygame.draw.line(s, (110, 72, 36), (4, 5), (11, 5)); pygame.draw.line(s, (110, 72, 36), (4, 7), (9, 7)); T[SIGN] = s
    s = surf16((140, 90, 50)); pygame.draw.rect(s, (214, 154, 92), (0, 0, 16, 7)); pygame.draw.line(s, (100, 62, 32), (0, 7), (15, 7)); T[COUNTER] = s
    s = floor(); pygame.draw.rect(s, (200, 60, 60), (1, 4, 14, 8)); pygame.draw.rect(s, (244, 200, 60), (1, 4, 14, 8), 1); T[MAT] = s
    T[STONE] = stone()
    s = floor(); pygame.draw.rect(s, (160, 100, 60), (4, 9, 8, 6)); pygame.draw.circle(s, (50, 150, 60), (8, 6), 4)
    pygame.draw.circle(s, (90, 200, 90), (6, 5), 2); T[POT] = s
    s = floor(); pygame.draw.rect(s, (60, 50, 70), (1, 0, 14, 16)); pygame.draw.rect(s, (214, 72, 72), (2, 5, 12, 10))
    pygame.draw.rect(s, (255, 255, 255), (3, 1, 10, 4)); T[BED] = s
    s = floor(); pygame.draw.rect(s, (110, 70, 40), (2, 6, 2, 9)); pygame.draw.rect(s, (110, 70, 40), (12, 6, 2, 9))
    pygame.draw.rect(s, (176, 118, 68), (1, 3, 14, 6)); pygame.draw.rect(s, (210, 150, 96), (1, 3, 14, 2)); T[TABLE] = s
    s = T[COUNTER].copy(); pygame.draw.rect(s, (240, 240, 252), (2, 0, 12, 12)); pygame.draw.rect(s, (60, 60, 90), (2, 0, 12, 12), 1)
    pygame.draw.rect(s, (230, 60, 70), (7, 2, 2, 7)); pygame.draw.rect(s, (230, 60, 70), (5, 4, 6, 3)); T[HEAL] = s
    s = floor(); pygame.draw.rect(s, (130, 88, 50), (0, 0, 16, 16))
    r = random.Random(9)
    for y in (2, 8):
        pygame.draw.line(s, (90, 58, 30), (0, y + 5), (15, y + 5))
        for x in range(1, 15, 3): pygame.draw.rect(s, r.choice([(230, 80, 80), (80, 140, 230), (240, 210, 70), (90, 200, 110)]), (x, y, 2, 5))
    T[SHELF] = s
    s = surf16((98, 118, 164))
    pygame.draw.rect(s, (84, 104, 150), (0, 0, 8, 8)); pygame.draw.rect(s, (84, 104, 150), (8, 8, 8, 8)); T[GYMF] = s
    s = stone(); pygame.draw.rect(s, (96, 96, 108), (3, 12, 10, 3)); pygame.draw.rect(s, (130, 130, 144), (5, 3, 6, 10))
    pygame.draw.circle(s, (150, 150, 164), (8, 4), 3); T[STATUE] = s
    s = stone(); pygame.draw.rect(s, (60, 60, 70), (7, 4, 2, 11)); pygame.draw.circle(s, (250, 230, 120), (8, 3), 3); T[LAMP] = s
    s = floor(); pygame.draw.rect(s, (60, 90, 172), (1, 2, 14, 12)); pygame.draw.rect(s, (230, 210, 120), (1, 2, 14, 12), 1); T[RUG] = s
    s = floor(); pygame.draw.rect(s, (50, 50, 60), (2, 3, 12, 10)); pygame.draw.rect(s, (110, 200, 230), (3, 4, 10, 7))
    pygame.draw.line(s, (200, 240, 255), (4, 5), (7, 5)); T[TV] = s
    s = T[TABLE].copy(); pygame.draw.circle(s, (220, 50, 50), (8, 6), 4); pygame.draw.rect(s, (250, 250, 250), (4, 6, 9, 2))
    pygame.draw.circle(s, (40, 40, 50), (8, 6), 4, 1); T[BALLS] = s
    return T

TILES = build_tiles()

# =====================================================================
#                         CHARACTER & MONSTER SPRITES
# =====================================================================
def outline(src, col=(28, 26, 40)):
    w, h = src.get_size(); out = src.copy()
    for y in range(h):
        for x in range(w):
            if src.get_at((x, y)).a == 0:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and src.get_at((nx, ny)).a > 0:
                        out.set_at((x, y), col); break
    return out

def L(hair, shirt, pants, skin=(244, 200, 160), cap=None):
    return dict(hair=hair, shirt=shirt, pants=pants, skin=skin, cap=cap)

LOOKS = {
    'player': L((90, 50, 30), (220, 60, 60), (50, 70, 150), cap=(220, 40, 40)),
    'rival': L((210, 170, 60), (60, 120, 210), (70, 70, 80)),
    'prof': L((205, 205, 205), (250, 250, 250), (110, 80, 50)),
    'mom': L((150, 80, 40), (240, 140, 170), (90, 70, 120)),
    'nurse': L((240, 150, 180), (250, 250, 250), (240, 150, 180)),
    'clerk': L((60, 40, 30), (70, 130, 220), (60, 60, 70), cap=(70, 130, 220)),
    'kid': L((40, 30, 30), (240, 200, 60), (60, 100, 60), cap=(240, 60, 60)),
    'woman': L((120, 60, 120), (180, 90, 200), (70, 70, 100)),
    'man': L((70, 50, 40), (90, 160, 90), (80, 80, 90)),
    'old': L((230, 230, 230), (160, 140, 110), (90, 80, 70)),
    'hiker': L((120, 70, 30), (200, 130, 60), (100, 80, 60), cap=(160, 100, 50)),
    'lass': L((250, 200, 80), (240, 100, 140), (230, 230, 240)),
    'cadet': L((40, 40, 60), (60, 60, 160), (50, 50, 70), cap=(60, 60, 160)),
    'leader': L((250, 230, 60), (250, 200, 40), (60, 60, 80)),
}

def make_char(look, d, frame):
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    R = lambda c, x, y, w, h: s.fill(c, (x, y, w, h))
    skin, hair, shirt, pants = look['skin'], look['hair'], look['shirt'], look['pants']
    shoe = (60, 40, 30)
    ly, ry = 12, 12
    if frame == 1: ly = 11
    if frame == 2: ry = 11
    R(pants, 5, ly, 2, 3 - (ly - 11) * 0 if False else 2); R(shoe, 5, ly + 2, 2, 2)
    R(pants, 9, ry, 2, 2); R(shoe, 9, ry + 2, 2, 2)
    R(shirt, 5, 7, 6, 5); R(shirt, 4, 8, 1, 3); R(shirt, 11, 8, 1, 3)
    R(skin, 4, 11, 1, 1); R(skin, 11, 11, 1, 1)
    R(skin, 5, 1, 6, 6)
    eye = (30, 30, 50)
    if d == 0:
        R(hair, 5, 1, 6, 5)
    elif d == 2:
        R(hair, 5, 1, 6, 2); R(hair, 5, 3, 1, 1); R(hair, 10, 3, 1, 1)
        s.set_at((6, 4), eye); s.set_at((9, 4), eye)
    elif d == 1:
        R(hair, 5, 1, 6, 2); R(hair, 5, 3, 2, 3); s.set_at((9, 4), eye)
    else:
        R(hair, 5, 1, 6, 2); R(hair, 9, 3, 2, 3); s.set_at((6, 4), eye)
    if look.get('cap'):
        c = look['cap']; R(c, 5, 1, 6, 2)
        if d == 2: R(c, 5, 3, 6, 1)
        elif d == 1: R(c, 9, 3, 3, 1)
        elif d == 3: R(c, 4, 3, 3, 1)
    return outline(s)

CHAR_CACHE = {}
def char_img(look, d, frame):
    k = (look['hair'], look['shirt'], look['pants'], look['skin'], look['cap'], d, frame)
    im = CHAR_CACHE.get(k)
    if im is None:
        im = make_char(look, d, frame); CHAR_CACHE[k] = im
    return im

TYPE_COL = {'fire': (228, 92, 52), 'water': (64, 128, 226), 'grass': (84, 176, 72),
            'electric': (238, 200, 40), 'normal': (196, 170, 140), 'rock': (150, 132, 112)}

def make_mon_img(key):
    sp = SPECIES[key]; r = random.Random(sp['seed']); stage = sp['stage']
    var = r.randint(-18, 18)
    base = tuple(clamp(c + var, 30, 255) for c in TYPE_COL[sp['type']])
    light = tuple(clamp(c + 55, 0, 255) for c in base); dark = tuple(clamp(c - 55, 0, 255) for c in base)
    N = 16; g = [[0] * N for _ in range(N)]
    top = 4 - (stage - 1); bot = 13
    widths = {}
    for y in range(top, bot + 1):
        t = (y - top) / (bot - top)
        w = int(2 + 4.5 * math.sin(math.pi * (0.1 + 0.8 * t))) + (1 if stage > 1 else 0) + r.choice((0, 0, 1))
        w = clamp(w, 2, 8); widths[y] = w
        for x in range(8 - w, 8): g[y][x] = 1
    ex = r.randint(2, 4)
    for dy in (1, 2):
        if top - dy >= 0: g[top - dy][8 - ex] = 1
    if stage > 1:
        for dy in (1, 2, 3):
            if top - dy >= 0: g[top - dy][7] = 1
    mid = (top + bot) // 2
    if r.random() < 0.6: g[mid][max(0, 8 - widths[mid] - 1)] = 1
    wb = widths[bot]
    for x in (8 - wb, 9 - wb): g[14][x] = 1
    for y in range(mid, bot - 1):
        for x in range(5, 8):
            if g[y][x] == 1 and r.random() < 0.85: g[y][x] = 3
    for y in range(top, bot + 1):
        for x in range(0, 8):
            if g[y][x] == 1:
                if y >= bot - 1: g[y][x] = 2
                elif r.random() < 0.07: g[y][x] = 2
    ey = top + 2
    g[ey][5] = 4; g[ey][6] = 5
    for y in range(N):
        for x in range(8): g[y][15 - x] = g[y][x]
    for y in range(N):
        g[y][10] = g[y][5] if g[y][5] in (4, 5) else g[y][10]
        g[y][9] = g[y][6] if g[y][6] in (4, 5) else g[y][9]
    cols = {1: base, 2: dark, 3: light, 4: (20, 20, 30), 5: (255, 255, 255)}
    s = pygame.Surface((N, N), pygame.SRCALPHA)
    for y in range(N):
        for x in range(N):
            if g[y][x]: s.set_at((x, y), cols[g[y][x]])
    return outline(s)

MON_CACHE = {}
def mon_img(key, scale):
    k = (key, scale)
    if k not in MON_CACHE:
        if (key, 1) not in MON_CACHE: MON_CACHE[(key, 1)] = make_mon_img(key)
        MON_CACHE[k] = pygame.transform.scale(MON_CACHE[(key, 1)], (16 * scale, 16 * scale))
    return MON_CACHE[k]

# =====================================================================
#                           MONSTER DATA
# =====================================================================
MOVES = {
    'Struggle': ('normal', 35, 100, 1), 'Scratch': ('normal', 40, 100, 35), 'Tackle': ('normal', 40, 100, 35),
    'Quick Attack': ('normal', 40, 100, 30), 'Bite': ('normal', 60, 100, 25), 'Body Slam': ('normal', 85, 90, 15),
    'Ember': ('fire', 40, 100, 25), 'Fire Fang': ('fire', 65, 95, 15), 'Flare Storm': ('fire', 90, 85, 10),
    'Water Gun': ('water', 40, 100, 25), 'Bubble Beam': ('water', 65, 100, 20), 'Tidal Crash': ('water', 90, 85, 10),
    'Vine Whip': ('grass', 45, 100, 25), 'Razor Leaf': ('grass', 55, 95, 25), 'Leaf Storm': ('grass', 90, 85, 10),
    'Thunder Shock': ('electric', 40, 100, 30), 'Spark': ('electric', 65, 100, 20), 'Volt Crash': ('electric', 90, 85, 10),
    'Rock Throw': ('rock', 50, 90, 15), 'Rock Slam': ('rock', 75, 90, 10),
}
MOVE_INFO = {k: dict(type=v[0], pow=v[1], acc=v[2], pp=v[3]) for k, v in MOVES.items()}

def sp(t, hp, atk, df, spd, xp, rate, seed, moves, evo=None, stage=1):
    return dict(type=t, hp=hp, atk=atk, df=df, spd=spd, xp=xp, rate=rate, seed=seed, moves=moves, evo=evo, stage=stage)

SPECIES = {
    'Flamlet': sp('fire', 44, 52, 43, 65, 62, 45, 11, [(1, 'Scratch'), (1, 'Ember'), (7, 'Quick Attack'), (12, 'Bite'), (15, 'Fire Fang')], (16, 'Blazerus')),
    'Blazerus': sp('fire', 68, 84, 66, 88, 140, 45, 12, [(1, 'Scratch'), (1, 'Ember'), (1, 'Fire Fang'), (20, 'Body Slam'), (26, 'Flare Storm')], None, 2),
    'Aquabit': sp('water', 50, 48, 65, 43, 62, 45, 21, [(1, 'Tackle'), (1, 'Water Gun'), (7, 'Quick Attack'), (12, 'Bubble Beam')], (16, 'Tidalor')),
    'Tidalor': sp('water', 74, 70, 90, 60, 140, 45, 22, [(1, 'Tackle'), (1, 'Water Gun'), (1, 'Bubble Beam'), (20, 'Body Slam'), (26, 'Tidal Crash')], None, 2),
    'Leafkin': sp('grass', 45, 49, 49, 45, 62, 45, 31, [(1, 'Tackle'), (1, 'Vine Whip'), (7, 'Quick Attack'), (12, 'Razor Leaf')], (16, 'Verdantis')),
    'Verdantis': sp('grass', 70, 70, 80, 60, 140, 45, 32, [(1, 'Tackle'), (1, 'Vine Whip'), (1, 'Razor Leaf'), (20, 'Body Slam'), (26, 'Leaf Storm')], None, 2),
    'Ratling': sp('normal', 35, 46, 35, 60, 45, 255, 41, [(1, 'Tackle'), (3, 'Quick Attack'), (9, 'Bite')], (14, 'Ratlord')),
    'Ratlord': sp('normal', 60, 76, 60, 82, 95, 127, 42, [(1, 'Tackle'), (1, 'Quick Attack'), (1, 'Bite'), (18, 'Body Slam')], None, 2),
    'Skywing': sp('normal', 42, 50, 40, 70, 50, 200, 51, [(1, 'Scratch'), (1, 'Quick Attack'), (10, 'Bite'), (16, 'Body Slam')]),
    'Crawlet': sp('grass', 40, 35, 55, 30, 45, 225, 61, [(1, 'Tackle'), (1, 'Vine Whip'), (10, 'Razor Leaf')]),
    'Voltip': sp('electric', 40, 44, 38, 72, 60, 190, 71, [(1, 'Quick Attack'), (1, 'Thunder Shock'), (11, 'Spark')], (18, 'Voltrix')),
    'Voltrix': sp('electric', 66, 72, 60, 95, 130, 75, 72, [(1, 'Quick Attack'), (1, 'Thunder Shock'), (1, 'Spark'), (20, 'Body Slam'), (24, 'Volt Crash')], None, 2),
    'Pebblo': sp('rock', 50, 58, 70, 25, 60, 180, 81, [(1, 'Tackle'), (1, 'Rock Throw'), (12, 'Bite'), (18, 'Rock Slam')], (22, 'Boulderon')),
    'Boulderon': sp('rock', 78, 86, 100, 35, 130, 90, 82, [(1, 'Tackle'), (1, 'Rock Throw'), (1, 'Rock Slam'), (26, 'Body Slam')], None, 2),
}

EFF = {('fire', 'grass'): 2, ('fire', 'water'): .5, ('fire', 'fire'): .5, ('fire', 'rock'): .5,
       ('water', 'fire'): 2, ('water', 'rock'): 2, ('water', 'water'): .5, ('water', 'grass'): .5,
       ('grass', 'water'): 2, ('grass', 'rock'): 2, ('grass', 'fire'): .5, ('grass', 'grass'): .5,
       ('electric', 'water'): 2, ('electric', 'grass'): .5, ('electric', 'electric'): .5,
       ('rock', 'fire'): 2, ('rock', 'electric'): 2}
def type_eff(a, d): return EFF.get((a, d), 1)
def xp_for(level): return 5 * level * level

class Mon:
    def __init__(s, key, level):
        s.key = key; s.level = level; s.xp = xp_for(level)
        s.recalc(); s.hp = s.maxhp
        learn = []
        for lv, mv in SPECIES[key]['moves']:
            if lv <= level and mv not in learn: learn.append(mv)
        s.moves = [[m, MOVE_INFO[m]['pp']] for m in learn[-4:]]
    @property
    def name(s): return s.key
    @property
    def type(s): return SPECIES[s.key]['type']
    def recalc(s):
        b = SPECIES[s.key]; L_ = s.level
        s.maxhp = (2 * b['hp'] * L_) // 100 + L_ + 10
        s.atk = (2 * b['atk'] * L_) // 100 + 5
        s.df = (2 * b['df'] * L_) // 100 + 5
        s.spd = (2 * b['spd'] * L_) // 100 + 5
    def heal(s):
        s.hp = s.maxhp
        for m in s.moves: m[1] = MOVE_INFO[m[0]]['pp']
    def add_xp(s, n):
        s.xp += n; msgs = []
        while s.level < 50 and s.xp >= xp_for(s.level + 1):
            s.level += 1; old = s.maxhp; s.recalc()
            if s.hp > 0: s.hp += s.maxhp - old
            msgs.append(f"{s.name} grew to level {s.level}!")
            for lv, mv in SPECIES[s.key]['moves']:
                if lv == s.level and mv not in [m[0] for m in s.moves]:
                    if len(s.moves) >= 4: s.moves.pop(0)
                    s.moves.append([mv, MOVE_INFO[mv]['pp']]); msgs.append(f"{s.name} learned {mv}!")
        return msgs
    def check_evolve(s):
        e = SPECIES[s.key]['evo']
        return e[1] if e and s.level >= e[0] else None
    def evolve(s):
        tgt = s.check_evolve(); old = s.maxhp; s.key = tgt; s.recalc()
        s.hp += s.maxhp - old
        names = [m[0] for m in s.moves]
        for lv, mv in SPECIES[s.key]['moves']:
            if lv <= s.level and mv not in names and len(s.moves) < 4:
                s.moves.append([mv, MOVE_INFO[mv]['pp']]); names.append(mv)
    def to_dict(s): return dict(k=s.key, l=s.level, x=s.xp, h=s.hp, m=s.moves)
    @staticmethod
    def from_dict(d):
        m = Mon(d['k'], d['l']); m.xp = d['x']; m.hp = d['h']; m.moves = [list(x) for x in d['m']]; return m

# =====================================================================
#                             INPUT (touch + keys)
# =====================================================================
DPAD_C = (74, 208)
A_C, B_C = (468, 190), (422, 240)
BTN_R = 30
MENU_R = pygame.Rect(SW // 2 - 36, 262, 72, 20)
L_R = pygame.Rect(2, 58, 56, 26)
R_R = pygame.Rect(SW - 58, 58, 56, 26)

class Input:
    def __init__(s):
        s.touches = {}; s.keys = set(); s.held = set(); s.prev = set(); s.pressed = set()
    def to_logical(s, x, y):
        sc, ox, oy = VIEW
        return (x - ox) / sc, (y - oy) / sc
    def button_at(s, lx, ly):
        if math.hypot(lx - A_C[0], ly - A_C[1]) < BTN_R + 6: return 'a'
        if math.hypot(lx - B_C[0], ly - B_C[1]) < BTN_R + 6: return 'b'
        if MENU_R.inflate(14, 14).collidepoint(lx, ly): return 'start'
        if L_R.inflate(10, 10).collidepoint(lx, ly): return 'b'
        if R_R.inflate(10, 10).collidepoint(lx, ly): return 'start'
        dx, dy = lx - DPAD_C[0], ly - DPAD_C[1]
        if math.hypot(dx, dy) < 70 and math.hypot(dx, dy) > 10:
            if abs(dx) > abs(dy): return 'right' if dx > 0 else 'left'
            return 'down' if dy > 0 else 'up'
        return None
    def event(s, e):
        t = e.type
        if t == pygame.MOUSEBUTTONDOWN and e.button == 1: s.touches['m'] = e.pos
        elif t == pygame.MOUSEMOTION and 'm' in s.touches and e.buttons[0]: s.touches['m'] = e.pos
        elif t == pygame.MOUSEBUTTONUP and e.button == 1: s.touches.pop('m', None)
        elif hasattr(pygame, 'FINGERDOWN') and t in (pygame.FINGERDOWN, pygame.FINGERMOTION):
            ww, wh = pygame.display.get_surface().get_size()
            s.touches[e.finger_id] = (e.x * ww, e.y * wh)
        elif hasattr(pygame, 'FINGERUP') and t == pygame.FINGERUP:
            s.touches.pop(e.finger_id, None)
        elif t == pygame.KEYDOWN or t == pygame.KEYUP:
            km = {pygame.K_UP: 'up', pygame.K_w: 'up', pygame.K_DOWN: 'down', pygame.K_s: 'down',
                  pygame.K_LEFT: 'left', pygame.K_a: 'left', pygame.K_RIGHT: 'right', pygame.K_d: 'right',
                  pygame.K_z: 'a', pygame.K_RETURN: 'a', pygame.K_SPACE: 'a',
                  pygame.K_x: 'b', pygame.K_LSHIFT: 'b', pygame.K_BACKSPACE: 'b',
                  pygame.K_ESCAPE: 'start', pygame.K_TAB: 'start'}
            b = km.get(e.key)
            if b:
                if t == pygame.KEYDOWN: s.keys.add(b)
                else: s.keys.discard(b)
    def update(s):
        h = set(s.keys)
        for (x, y) in s.touches.values():
            lx, ly = s.to_logical(x, y)
            b = s.button_at(lx, ly)
            if b: h.add(b)
        s.pressed = h - s.prev; s.prev = h; s.held = h

CTL_CACHE = {}
def draw_controls(surf, held):
    k = frozenset(held)
    im = CTL_CACHE.get(k)
    if im is None:
        im = CTL_CACHE[k] = render_controls(k)
    surf.blit(im, (0, 0))

def render_controls(held):
    """Translucent on-screen gamepad drawn on top of the game (like a handheld emulator)."""
    L = pygame.Surface((SW, SH), pygame.SRCALPHA)
    cx, cy = DPAD_C
    on, off, edge = (255, 255, 255, 120), (70, 70, 80, 95), (20, 20, 28, 140)
    arms = {'up': (cx - 19, cy - 58, 38, 40), 'down': (cx - 19, cy + 18, 38, 40),
            'left': (cx - 58, cy - 19, 40, 38), 'right': (cx + 18, cy - 19, 40, 38)}
    for k, r in arms.items():
        pygame.draw.rect(L, on if k in held else off, r, border_radius=6)
        pygame.draw.rect(L, edge, r, 2, border_radius=6)
    pygame.draw.rect(L, off, (cx - 19, cy - 19, 38, 38))
    for name, c in (('a', A_C), ('b', B_C)):
        pygame.draw.circle(L, on if name in held else off, c, BTN_R)
        pygame.draw.circle(L, edge, c, BTN_R, 3)
        put(L, name.upper(), c[0], c[1] - 10, FONT_L, (235, 235, 240), center=True)
    for rect, label, key in ((L_R, 'L', 'b'), (R_R, 'R', 'start')):
        pygame.draw.rect(L, on if key in held else off, rect, border_radius=8)
        put(L, label, rect.centerx, rect.y + 5, FONT_L, (235, 235, 240), center=True)
    pygame.draw.rect(L, on if 'start' in held else off, MENU_R, border_radius=10)
    put(L, "START", MENU_R.centerx, MENU_R.y + 4, FONT_S, (245, 245, 250), center=True)
    return L

def blit_panel(scr, u):
    """Put a 320x288 panel in the middle of the wide screen and stretch its edge columns to fill the sides."""
    scr.blit(u, (UX, 0))
    scr.blit(pygame.transform.scale(u.subsurface((0, 0, 1, GAME_H)), (UX, GAME_H)), (0, 0))
    rw = SW - UX - LW
    scr.blit(pygame.transform.scale(u.subsurface((LW - 1, 0, 1, GAME_H)), (rw, GAME_H)), (UX + LW, 0))

# =====================================================================
#                          MAPS, NPCs, WORLD DATA
# =====================================================================
DIRS = [(0, -1), (1, 0), (0, 1), (-1, 0)]   # up, right, down, left

class Actor:
    def __init__(s, x, y, look, d=2):
        s.x, s.y, s.dir, s.look = x, y, d, look
        s.moving = False; s.prog = 0.0; s.tx = x; s.ty = y; s.leg = 0; s.bubble = 0
    def start_move(s, d):
        s.dir = d; s.moving = True; s.prog = 0.0
        s.tx, s.ty = s.x + DIRS[d][0], s.y + DIRS[d][1]
    def update_move(s, speed):
        s.prog += speed
        if s.prog >= 16:
            s.x, s.y = s.tx, s.ty; s.moving = False; s.prog = 0.0; s.leg ^= 1
            return True
        return False
    def pixel(s):
        x, y = s.x * 16, s.y * 16
        if s.moving:
            x += DIRS[s.dir][0] * s.prog; y += DIRS[s.dir][1] * s.prog
        return x, y
    def img(s):
        fr = 0
        if s.moving: fr = 1 + ((int(s.prog) // 8 + s.leg) % 2)
        return char_img(s.look, s.dir, fr)

class NPC(Actor):
    def __init__(s, x, y, look, d=2, text=None, kind='talk', name='', **kw):
        Actor.__init__(s, x, y, LOOKS[look] if isinstance(look, str) else look, d)
        s.text = text or ["..."]; s.kind = kind; s.name = name or 'TRAINER'
        s.team = kw.get('team', []); s.reward = kw.get('reward', 0); s.after = kw.get('after', ["..."])
        s.hide_flag = kw.get('hide_flag'); s.show_flag = kw.get('show_flag')
        s.wander = kw.get('wander', False); s.radius = kw.get('radius', 2); s.sight = kw.get('sight', 4)
        s.fixed = kw.get('fixed', kind in ('nurse', 'clerk', 'mom', 'prof', 'rival', 'leader'))
        s.gift = kw.get('gift'); s.home = (x, y); s.id = ''
    def visible(s, g):
        if s.hide_flag and s.hide_flag in g.flags: return False
        if s.show_flag and s.show_flag not in g.flags: return False
        return True

class GameMap:
    def __init__(s, name, title, w, h, fill, indoor=False):
        s.name, s.title, s.w, s.h, s.indoor = name, title, w, h, indoor
        s.t = [[fill] * w for _ in range(h)]
        s.warps = {}; s.npcs = []; s.objs = {}; s.wild = []; s.mat = None; s.spawn = None
    def rect(s, x, y, w, h, t):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if 0 <= xx < s.w and 0 <= yy < s.h: s.t[yy][xx] = t
    def tile(s, x, y):
        return s.t[y][x] if 0 <= x < s.w and 0 <= y < s.h else TREE
    def add(s, npc):
        npc.id = f"{s.name}:{npc.x},{npc.y}"; s.npcs.append(npc); return npc
    def sign(s, x, y, txt, tile=SIGN):
        s.t[y][x] = tile; s.objs[(x, y)] = ('sign', txt)

MAPS = {}
LINKS = []

def border(m, th=1):
    m.rect(0, 0, m.w, th, TREE); m.rect(0, m.h - th, m.w, th, TREE)
    m.rect(0, 0, th, m.h, TREE); m.rect(m.w - th, 0, th, m.h, TREE)

def building(m, x, y, w, roof, door_dx, inner):
    for i in range(w):
        m.t[y][x + i] = roof; m.t[y + 1][x + i] = roof
        m.t[y + 2][x + i] = WALL if i == door_dx else WINDOW
        m.t[y + 3][x + i] = WALL
    door = (x + door_dx, y + 3); m.t[door[1]][door[0]] = DOOR
    LINKS.append((m.name, door, inner))

def interior(name, title, w, h, floor=FLOOR):
    m = GameMap(name, title, w, h, floor, True)
    m.rect(0, 0, w, 1, IWALL); m.rect(0, h - 1, w, 1, IWALL); m.rect(0, 0, 1, h, IWALL); m.rect(w - 1, 0, 1, h, IWALL)
    m.mat = (w // 2, h - 1); m.t[h - 1][w // 2] = MAT; m.spawn = (w // 2, h - 2)
    MAPS[name] = m; return m

def scatter_trees(m, count, seed, avoid=(PATH, STONE), margin=2):
    r = random.Random(seed)
    for _ in range(count):
        x, y = r.randrange(2, m.w - 2), r.randrange(2, m.h - 2)
        if m.t[y][x] != GRASS: continue
        near = False
        for dy in range(-margin, margin + 1):
            for dx in range(-margin, margin + 1):
                if m.tile(x + dx, y + dy) in avoid + (DOOR,): near = True
        if not near: m.t[y][x] = TREE

def build_world():
    # ---------------- TOWN ----------------
    t = GameMap('town', 'Brookvale Town', 36, 30, GRASS); MAPS['town'] = t
    border(t)
    t.rect(17, 0, 1, 4, TREE); t.rect(19, 0, 1, 4, TREE)
    scatter_trees(t, 40, 3)
    t.rect(21, 11, 9, 1, FENCE)
    t.rect(3, 23, 7, 1, FENCE); t.rect(3, 24, 6, 4, WATER)
    for (x, y, w, h) in ((2, 16, 3, 2), (30, 17, 3, 2), (10, 17, 2, 2), (27, 24, 4, 2), (2, 4, 3, 2)): t.rect(x, y, w, h, FLOWER)
    t.rect(1, 14, 34, 2, PATH); t.rect(17, 4, 3, 24, PATH); t.rect(18, 0, 1, 4, PATH)
    for x in (6, 13, 25): t.rect(x, 10, 1, 4, PATH)
    for x in (6, 13, 24, 30): t.rect(x, 16, 1, 7, PATH)
    building(t, 4, 6, 5, ROOF_R, 2, 'town_home')
    building(t, 11, 6, 5, ROOF_B, 2, 'town_rival')
    building(t, 22, 6, 7, ROOF_B, 3, 'town_lab')
    building(t, 4, 18, 5, ROOF_R, 2, 'town_center')
    building(t, 12, 18, 4, ROOF_B, 1, 'town_mart')
    building(t, 22, 18, 5, ROOF_R, 2, 'town_h3')
    building(t, 29, 18, 4, ROOF_B, 1, 'town_h4')
    t.sign(23, 10, "PROF. WILLOW'S LAB\nMonster research")
    t.sign(8, 22, "MONSTER CENTER\nHeal your team for free!")
    t.sign(15, 22, "MONSTER MART\nBalls and potions!")
    t.sign(16, 16, f"BROOKVALE TOWN\nWhere {GAME_TITLE} begins!")
    t.warps[(18, 0)] = ('route1', 18, 42, 0)
    t.add(NPC(18, 2, 'man', 2, ["Hold on! Wild monsters live beyond this point.", f"Go see {PROF_NAME} at the lab first. He will give you a partner!"], 'guard', hide_flag='starter'))
    t.add(NPC(21, 17, 'kid', 2, ["Tall grass hides wild monsters!", "Weaken them first, then throw a Capture Ball."], wander=True, radius=3))
    t.add(NPC(10, 16, 'woman', 1, ["Brookvale is the biggest town around... until you see Sunport City up north!"], wander=True, radius=3))
    t.add(NPC(28, 15, 'old', 3, ["The pond is lovely at night. This world has a day and night cycle, you know."], wander=True, radius=2))
    t.add(NPC(32, 22, 'kid', 3, ["I want to be a Monster Trainer, just like you!"], wander=True, radius=2))
    # ---------------- ROUTE 1 ----------------
    r = GameMap('route1', 'Route 1', 36, 44, GRASS); MAPS['route1'] = r
    r.rect(0, 0, 36, 2, TREE); r.rect(0, 42, 36, 2, TREE); r.rect(0, 0, 3, 44, TREE); r.rect(33, 0, 3, 44, TREE)
    r.rect(17, 2, 3, 40, PATH); r.rect(18, 0, 1, 2, PATH); r.rect(18, 42, 1, 2, PATH)
    for (x, y, w, h) in ((4, 30, 9, 7), (21, 26, 9, 7), (4, 12, 10, 8), (22, 8, 9, 8), (21, 35, 8, 5), (5, 3, 8, 5)): r.rect(x, y, w, h, TALL)
    scatter_trees(r, 90, 7, margin=1)
    for (x, y, d, nm, look, team, rew, txt, aft) in (
            (14, 33, 1, 'YOUNGSTER JOEY', 'kid', [('Ratling', 5), ('Ratling', 6)], 80, ["My Ratling is the best! Let's battle!"], ["Wow, you're strong!"]),
            (22, 24, 3, 'LASS MIA', 'lass', [('Crawlet', 7), ('Skywing', 7)], 120, ["Our eyes met! That means a battle!"], ["I need to train more..."]),
            (15, 12, 1, 'HIKER GUS', 'hiker', [('Pebblo', 9), ('Pebblo', 10)], 200, ["I've been hiking all day. Battle me!"], ["My rocks crumbled. Good fight!"])):
        r.t[y][x] = GRASS
        r.add(NPC(x, y, look, d, txt, 'trainer', nm, team=team, reward=rew, after=aft))
    r.wild = [('Ratling', 3, 6, 30), ('Skywing', 3, 7, 25), ('Crawlet', 4, 7, 20), ('Pebblo', 5, 8, 15), ('Voltip', 5, 7, 10)]
    r.sign(16, 40, "ROUTE 1\nBrookvale Town <-> Sunport City")
    r.sign(16, 4, "SUNPORT CITY AHEAD\nGym Leader: " + LEADER_NAME)
    r.warps[(18, 0)] = ('city', 24, 38, 0); r.warps[(18, 43)] = ('town', 18, 1, 2)
    # ---------------- CITY ----------------
    c = GameMap('city', 'Sunport City', 48, 40, GRASS); MAPS['city'] = c
    c.rect(0, 0, 48, 2, TREE); c.rect(0, 38, 48, 2, TREE); c.rect(0, 0, 2, 40, TREE); c.rect(46, 0, 2, 40, TREE)
    scatter_trees(c, 70, 5)
    c.rect(3, 31, 12, 6, WATER); c.rect(3, 30, 12, 1, FENCE)
    c.rect(22, 12, 5, 26, STONE); c.rect(24, 38, 1, 2, PATH); c.rect(2, 18, 44, 3, STONE)
    for x in (8, 13, 31, 38): c.rect(x, 12, 1, 6, STONE)
    for x in (7, 14, 33, 40): c.rect(x, 21, 1, 8, STONE)
    c.rect(23, 15, 3, 2, WATER)
    for (x, y, w, h) in ((16, 22, 4, 2), (28, 22, 4, 2), (3, 22, 3, 2), (42, 12, 3, 2), (17, 13, 3, 2)): c.rect(x, y, w, h, FLOWER)
    for x in (10, 17, 21, 27, 30, 36): c.t[21][x] = LAMP
    building(c, 20, 8, 9, ROOF_B, 4, 'city_gym')
    building(c, 6, 8, 5, ROOF_R, 2, 'city_center')
    building(c, 36, 8, 5, ROOF_B, 2, 'city_mart')
    building(c, 12, 8, 4, ROOF_R, 1, 'city_h1')
    building(c, 30, 8, 4, ROOF_R, 1, 'city_h2')
    building(c, 5, 24, 5, ROOF_B, 2, 'city_h3')
    building(c, 13, 24, 4, ROOF_R, 1, 'city_h4')
    building(c, 31, 24, 5, ROOF_B, 2, 'city_h5')
    building(c, 39, 24, 4, ROOF_R, 1, 'city_h6')
    c.sign(19, 12, f"SUNPORT GYM\nLeader: {LEADER_NAME}\nElectric-type specialist")
    c.sign(10, 12, "MONSTER CENTER"); c.sign(35, 12, "MONSTER MART")
    c.sign(21, 22, f"SUNPORT CITY\nThe city of sun and sea")
    c.warps[(24, 39)] = ('route1', 18, 1, 2)
    c.add(NPC(23, 25, 'kid', 2, ["Wow, the plaza is huge!"], wander=True, radius=3))
    c.add(NPC(16, 19, 'woman', 1, ["Sunport City never sleeps. The lamps glow all night!"], wander=True, radius=4))
    c.add(NPC(34, 19, 'man', 3, ["I came here to challenge the Gym, but I'm not ready yet..."], wander=True, radius=4))
    c.add(NPC(26, 30, 'old', 0, ["Long ago, trainers sailed from this very bay."], wander=True, radius=2))
    c.add(NPC(40, 16, 'kid', 2, ["Did you know? Stronger monsters evolve at certain levels!"], wander=True, radius=2))

    # ---------------- INTERIORS ----------------
    h = interior('town_home', 'Your House', 8, 7)
    h.t[1][1] = BED; h.t[1][5] = TV; h.t[1][3] = SHELF; h.t[1][6] = POT; h.t[3][5] = TABLE; h.rect(2, 3, 2, 2, RUG)
    def mom_text(g):
        if 'starter' in g.flags: return [f"{{p}}! Take good care of your monster. Rest here anytime to heal!"]
        return ["{p}! Good morning!", f"{PROF_NAME} was looking for you. His lab is the big building in town.", "Use the D-pad to walk and A to talk or interact!"]
    h.add(NPC(3, 3, 'mom', 2, mom_text, 'mom'))
    h.objs[(5, 1)] = ('sign', "A TV. A show about monster training is on.")
    h.objs[(1, 1)] = ('sign', "Your bed. Nice and cozy!")
    lab = interior('town_lab', f"{PROF_NAME}'s Lab", 10, 8)
    lab.rect(1, 1, 4, 1, SHELF); lab.rect(6, 1, 3, 1, SHELF)
    for i, k in enumerate(('Flamlet', 'Aquabit', 'Leafkin')):
        lab.t[2][3 + i] = BALLS; lab.objs[(3 + i, 2)] = ('starter', k)
    lab.t[3][8] = TV; lab.rect(3, 5, 4, 1, RUG)
    lab.add(NPC(7, 3, 'prof', 2, ["..."], 'prof', PROF_NAME))
    lab.add(NPC(2, 4, 'rival', 0, ["..."], 'rival', RIVAL_NAME))
    ce = interior('town_center', 'Monster Center', 10, 8)
    ce.rect(3, 2, 4, 1, COUNTER); ce.t[2][4] = HEAL; ce.t[1][1] = POT; ce.t[1][8] = POT; ce.rect(3, 4, 4, 1, RUG)
    ce.add(NPC(4, 1, 'nurse', 2, ["..."], 'nurse', 'NURSE'))
    ce.add(NPC(7, 5, 'man', 3, ["Free healing! This place saves so many trainers."], wander=True, radius=1))
    ma = interior('town_mart', 'Monster Mart', 8, 7)
    ma.rect(2, 2, 3, 1, COUNTER); ma.rect(1, 1, 1, 1, SHELF); ma.rect(5, 1, 2, 1, SHELF); ma.rect(6, 3, 1, 2, SHELF)
    ma.add(NPC(3, 1, 'clerk', 2, ["..."], 'clerk', 'CLERK'))
    ma.add(NPC(5, 4, 'woman', 3, ["Potions heal 30 HP. I always carry a few!"]))
    def house(name, title, w, hh, items, npc):
        m = interior(name, title, w, hh)
        for (x, y, tl) in items: m.t[y][x] = tl
        m.add(npc); return m
    house('town_rival', "Rival's House", 7, 6, [(1, 1, BED), (4, 1, SHELF), (5, 1, SHELF), (3, 3, TABLE)], NPC(5, 3, 'mom', 3, [f"{RIVAL_NAME} already left. He is always so impatient!"]))
    house('town_h3', 'Cozy House', 7, 6, [(1, 1, SHELF), (2, 1, SHELF), (5, 1, TV), (4, 3, TABLE), (1, 3, POT)], NPC(2, 3, 'old', 1, ["Tall grass hides wild monsters.", "Weaken a monster before throwing a Capture Ball!"]))
    house('town_h4', 'Blue House', 7, 6, [(1, 1, BED), (5, 1, POT), (3, 3, RUG)], NPC(4, 3, 'woman', 2, ["Hold B while walking to RUN!"]))
    house('city_h1', 'Sunny House', 7, 6, [(1, 1, SHELF), (5, 1, TV), (3, 3, TABLE)], NPC(4, 4, 'kid', 3, [f"{LEADER_NAME}'s monsters are ELECTRIC.", "ROCK-types hit them hard! Pebblo lives on Route 1."]))
    house('city_h2', 'Seaview House', 7, 6, [(1, 1, BED), (5, 1, SHELF), (5, 3, POT)], NPC(3, 3, 'man', 2, ["The sea breeze here is great for training."]))
    house('city_h3', 'Brick House', 7, 6, [(1, 1, SHELF), (2, 1, SHELF), (4, 3, TABLE)], NPC(2, 4, 'old', 1, ["Save your game from the MENU button!"]))
    house('city_h4', 'Garden House', 7, 6, [(1, 1, POT), (5, 1, POT), (3, 3, RUG)], NPC(4, 3, 'woman', 2, ["Monsters heal at a Monster Center, or at your mom's!"]))
    house('city_h5', 'Corner House', 7, 6, [(1, 1, BED), (5, 1, TV), (3, 3, TABLE)], NPC(5, 4, 'kid', 3, ["Super effective hits do double damage!", "Fire > Grass > Water > Fire. Water & Grass > Rock."]))
    house('city_h6', 'Lucky House', 7, 6, [(1, 1, SHELF), (5, 1, POT)], NPC(3, 3, 'man', 2, ["Welcome, trainer! Take these potions!"], 'gift', gift=('potion', 3, 'gift_potion')))
    cc = interior('city_center', 'Monster Center', 10, 8)
    cc.rect(3, 2, 4, 1, COUNTER); cc.t[2][4] = HEAL; cc.t[1][1] = POT; cc.t[1][8] = POT; cc.rect(3, 4, 4, 1, RUG)
    cc.add(NPC(4, 1, 'nurse', 2, ["..."], 'nurse', 'NURSE'))
    cc.add(NPC(2, 5, 'kid', 1, ["Gym battles are tough. Heal up first!"], wander=True, radius=1))
    cm = interior('city_mart', 'Monster Mart', 8, 7)
    cm.rect(2, 2, 3, 1, COUNTER); cm.rect(1, 1, 1, 1, SHELF); cm.rect(5, 1, 2, 1, SHELF); cm.rect(6, 3, 1, 2, SHELF)
    cm.add(NPC(3, 1, 'clerk', 2, ["..."], 'clerk', 'CLERK'))
    gy = interior('city_gym', 'Sunport Gym', 11, 14, GYMF)
    for (x, y) in ((2, 3), (8, 3), (2, 11), (8, 11), (2, 7), (8, 7)): gy.t[y][x] = STATUE
    gy.rect(4, 6, 3, 1, FLOOR)
    gy.add(NPC(5, 2, 'leader', 2, ["..."], 'leader', LEADER_NAME,
               team=[('Voltip', 13), ('Skywing', 13), ('Voltrix', 16)], reward=1200,
               after=["Hmm, you've already earned the " + BADGE_NAME + "!", "Keep on training!"]))
    gy.add(NPC(2, 9, 'cadet', 1, ["I'm a Gym Cadet! Prove yourself!"], 'trainer', 'CADET RAI',
               team=[('Voltip', 10), ('Pebblo', 10)], reward=250, after=["Impressive... go on ahead."], sight=5))
    gy.add(NPC(8, 5, 'cadet', 3, ["Nobody passes without a fight!"], 'trainer', 'CADET LIN',
               team=[('Skywing', 11), ('Voltip', 11)], reward=300, after=["Powerful! Go meet the leader."], sight=5))
    for (outer, door, inner) in LINKS:
        o = MAPS[outer]; i = MAPS[inner]
        o.warps[door] = (inner, i.spawn[0], i.spawn[1], 0)
        i.warps[i.mat] = (outer, door[0], door[1] + 1, 2)

# =====================================================================
#                            DIALOGUE
# =====================================================================
class Dialogue:
    def __init__(s, pages, choices=None):
        s.pages = []
        for p in pages: s.pages += paginate(p)
        s.i = 0; s.shown = 0.0; s.choices = choices; s.sel = 0
        s.asking = False; s.done = False; s.result = None
    def update(s, inp):
        p = inp.pressed; page = s.pages[s.i]
        if s.asking:
            n = len(s.choices)
            if 'up' in p: s.sel = (s.sel - 1) % n
            if 'down' in p: s.sel = (s.sel + 1) % n
            if 'a' in p: s.result = s.sel; s.done = True
            return
        if s.shown < len(page):
            s.shown += 1.5
            if 'a' in p: s.shown = len(page)
        elif 'a' in p:
            if s.i + 1 < len(s.pages): s.i += 1; s.shown = 0.0
            elif s.choices: s.asking = True
            else: s.done = True
    def draw(s, surf):
        box(surf, (4, 206, 312, 78))
        draw_typed(surf, s.pages[s.i], s.shown if not s.asking else 999, 14, 214)
        if s.asking:
            n = len(s.choices); h = n * 22 + 14
            box(surf, (316 - 150, 206 - h - 2, 150, h))
            for k, c in enumerate(s.choices):
                put(surf, ("> " if k == s.sel else "  ") + c, 316 - 140, 206 - h + 5 + k * 22)
        elif s.shown >= len(s.pages[s.i]) and (pygame.time.get_ticks() // 350) % 2 == 0:
            pygame.draw.polygon(surf, (200, 60, 60), [(288, 270), (298, 270), (293, 278)])

# =====================================================================
#                              BATTLE
# =====================================================================
def draw_party(surf, party, sel, mark=None, title='PARTY', detail=True):
    surf.fill((72, 104, 168), (0, 0, LW, GAME_H))
    put(surf, title, 12, 6, FONT_L, (255, 255, 255), (30, 40, 80))
    for i, m in enumerate(party):
        r = pygame.Rect(8, 30 + i * 36, 304, 33)
        box(surf, r, (255, 238, 190) if i == sel else (250, 250, 250), (210, 60, 60) if i == mark else (40, 40, 60))
        surf.blit(mon_img(m.key, 1) if False else pygame.transform.scale(mon_img(m.key, 1), (26, 26)), (12, r.y + 3))
        put(surf, f"{m.name}", 44, r.y + 3, FONT_M)
        put(surf, f"Lv{m.level}", 44, r.y + 18, FONT_S, (90, 90, 110))
        draw_bar(surf, 150, r.y + 12, 90, 7, m.hp / m.maxhp)
        put(surf, "FNT" if m.hp <= 0 else f"{m.hp}/{m.maxhp}", 306, r.y + 9, FONT_S, (60, 60, 80), right=True)
    if detail and party and 0 <= sel < len(party):
        m = party[sel]
        box(surf, (4, 250 if len(party) > 5 else 250, 312, 34))
        put(surf, "  ".join(f"{a} {b}/{MOVE_INFO[a]['pp']}" for a, b in m.moves[:2]), 12, 254, FONT_S)
        put(surf, "  ".join(f"{a} {b}/{MOVE_INFO[a]['pp']}" for a, b in m.moves[2:4]), 12, 268, FONT_S)

class Battle:
    def __init__(s, g, foes, wild=True, trainer='', reward=0):
        s.g = g; s.foes = foes; s.wild = wild; s.trainer = trainer; s.reward = reward
        s.em = foes[0]; s.pm = next(m for m in g.party if m.hp > 0); s.parts = [s.pm]
        s.disp_p = s.pm.hp; s.disp_e = s.em.hp
        s.q = deque(); s.text = ''; s.shown = 0.0; s.tim = 0; s.waiting = 0; s.active_text = False
        s.phase = 'msgs'; s.sel = 0; s.fsel = 0; s.bsel = 0; s.psel = 0; s.pmode = 'switch'
        s.show_p = True; s.show_e = True; s.in_ball = False
        s.rid = 0; s.need_switch = False; s.end = None; s.finished = False; s.result = None
        s.shake = {'p': 0, 'e': 0}; s.t = 0
        if wild: s.q.append(f"A wild {s.em.name} appeared!")
        else:
            s.q.append(f"{trainer} wants to battle!"); s.q.append(f"{trainer} sent out {s.em.name}!")
        s.q.append(f"Go, {s.pm.name}!")
    def label(s, m): return m.name if m is not s.em else (f"Wild {m.name}" if s.wild else f"Foe {m.name}")
    # ---- queue ----
    def set_text(s, t): s.text = t; s.shown = 0.0; s.tim = 0; s.active_text = True
    def next_item(s):
        while s.q:
            it = s.q.popleft()
            if isinstance(it, str): s.set_text(it); return
            if it[0] == 'call':
                r = it[1]()
                if r:
                    for x in reversed(r): s.q.appendleft(x)
            elif it[0] == 'wait': s.waiting = it[1]; return
        s.on_empty()
    def on_empty(s):
        if s.end: s.finished = True; s.result = s.end; return
        if s.need_switch:
            s.phase = 'party'; s.pmode = 'forced'
            s.psel = next(i for i, m in enumerate(s.g.party) if m.hp > 0); return
        s.phase = 'menu'
    def say_back(s, t): s.phase = 'msgs'; s.q.append(t)
    # ---- update ----
    def update(s, inp):
        s.t += 1; p = inp.pressed
        for k, hp, dv in (('p', s.pm.hp, 'disp_p'), ('e', s.em.hp, 'disp_e')):
            cur = getattr(s, dv)
            if abs(cur - hp) < 0.6: cur = hp
            else: cur += (hp - cur) * 0.12 + (0.5 if hp > cur else -0.5)
            setattr(s, dv, cur)
            if s.shake[k] > 0: s.shake[k] -= 1
        if s.phase == 'msgs': s.upd_msgs(p)
        elif s.phase == 'menu':
            if 'up' in p or 'down' in p: s.sel ^= 2
            if 'left' in p or 'right' in p: s.sel ^= 1
            if 'a' in p: s.menu_pick()
        elif s.phase == 'fight':
            n = len(s.pm.moves)
            for d, x in (('up', 2), ('down', 2), ('left', 1), ('right', 1)):
                if d in p and (s.fsel ^ x) < n: s.fsel ^= x
            if 'b' in p: s.phase = 'menu'
            if 'a' in p:
                if s.pm.moves[s.fsel][1] <= 0: s.say_back("No PP left for that move!")
                else: s.start_round(('move', s.fsel))
        elif s.phase == 'bag':
            if 'up' in p: s.bsel = (s.bsel - 1) % 3
            if 'down' in p: s.bsel = (s.bsel + 1) % 3
            if 'b' in p: s.phase = 'menu'
            if 'a' in p: s.bag_pick()
        elif s.phase == 'party':
            n = len(s.g.party)
            if 'up' in p: s.psel = (s.psel - 1) % n
            if 'down' in p: s.psel = (s.psel + 1) % n
            if 'b' in p and s.pmode == 'switch': s.phase = 'menu'
            if 'a' in p: s.party_pick()
    def upd_msgs(s, p):
        if s.waiting > 0: s.waiting -= 1; return
        bars = abs(s.disp_p - s.pm.hp) < 1 and abs(s.disp_e - s.em.hp) < 1
        if s.active_text:
            if s.shown < len(s.text):
                s.shown += 1.4
                if 'a' in p: s.shown = len(s.text)
                return
            s.tim += 1
            if bars and ('a' in p or s.tim > 75): s.active_text = False
            return
        if bars: s.next_item()
    # ---- menus ----
    def menu_pick(s):
        if s.sel == 0:
            if all(m[1] <= 0 for m in s.pm.moves): s.start_round(('move', -1))
            else: s.phase = 'fight'; s.fsel = 0
        elif s.sel == 1: s.phase = 'bag'; s.bsel = 0
        elif s.sel == 2: s.phase = 'party'; s.pmode = 'switch'; s.psel = s.g.party.index(s.pm)
        else:
            if not s.wild: s.say_back("You can't run from a trainer battle!")
            else: s.start_round(('run',))
    def bag_pick(s):
        b = s.g.bag
        if s.bsel == 2: s.phase = 'menu'
        elif s.bsel == 0:
            if b['potion'] <= 0: s.say_back("You have no Potions!")
            elif s.pm.hp >= s.pm.maxhp: s.say_back("It won't have any effect.")
            else: s.start_round(('potion',))
        else:
            if b['ball'] <= 0: s.say_back("You have no Capture Balls!")
            elif not s.wild: s.say_back("You can't catch another trainer's monster!")
            else: s.start_round(('ball',))
    def party_pick(s):
        m = s.g.party[s.psel]
        if s.pmode == 'switch':
            if m is s.pm: s.say_back(f"{m.name} is already out!")
            elif m.hp <= 0: s.say_back(f"{m.name} has no energy left!")
            else: s.start_round(('switch', s.psel))
        else:
            if m.hp <= 0: s.say_back(f"{m.name} has no energy left!"); return
            s.need_switch = False; s.phase = 'msgs'
            s.q.extend([('call', lambda: s.do_switch(m)), f"Go, {m.name}!"])
    def do_switch(s, new):
        s.pm = new; s.disp_p = new.hp; s.show_p = True
        if new not in s.parts: s.parts.append(new)
    # ---- rounds ----
    def pick_enemy_move(s):
        mv = s.em.moves
        sc = [(MOVE_INFO[m[0]]['pow'] * type_eff(MOVE_INFO[m[0]]['type'], s.pm.type), m) for m in mv]
        if random.random() < 0.6: return max(sc, key=lambda x: x[0])[1]
        return random.choice(mv)
    def start_round(s, action):
        s.phase = 'msgs'; rid = s.rid; pm = s.pm; em = s.em; emove = s.pick_enemy_move(); items = []
        enemy = ('call', lambda: s.attack('e', emove, rid))
        k = action[0]
        if k == 'move':
            mv = pm.moves[action[1]] if action[1] >= 0 else ['Struggle', 1]
            first_p = pm.spd > em.spd or (pm.spd == em.spd and random.random() < 0.5)
            order = [('p', mv), ('e', emove)] if first_p else [('e', emove), ('p', mv)]
            for who, m in order: items.append(('call', lambda who=who, m=m: s.attack(who, m, rid)))
        elif k == 'switch':
            new = s.g.party[action[1]]
            items = [f"Come back, {pm.name}!", ('call', lambda: s.do_switch(new)), f"Go, {new.name}!", enemy]
        elif k == 'potion':
            items = [('call', lambda: s.use_potion()), f"{pm.name} recovered HP!", enemy]
        elif k == 'ball':
            items = [('call', lambda: s.throw_ball(rid, enemy))]
        elif k == 'run':
            items = [('call', lambda: s.try_run(enemy))]
        s.q.extend(items)
    def use_potion(s):
        s.g.bag['potion'] -= 1; s.pm.hp = min(s.pm.maxhp, s.pm.hp + 30)
        return [f"{PLAYER_NAME} used a Potion!"]
    def try_run(s, enemy):
        p = clamp(0.5 + (s.pm.spd - s.em.spd) / 60.0, 0.3, 0.95)
        if random.random() < p:
            s.end = 'run'; return ["Got away safely!"]
        return ["Can't escape!", enemy]
    def throw_ball(s, rid, enemy):
        s.g.bag['ball'] -= 1; em = s.em
        a = (3 * em.maxhp - 2 * em.hp) * SPECIES[em.key]['rate'] / (3 * em.maxhp)
        ok = random.random() < min(0.98, (a + 25) / 255 * 1.6)
        shakes = 3 if ok else random.choice([0, 1, 2])
        items = [f"{PLAYER_NAME} threw a Capture Ball!", ('call', lambda: s.set_ball(True))]
        items += [('wait', 36)] * (shakes + 1)
        if ok: items += [f"Gotcha! {em.name} was caught!", ('call', lambda: s.caught(em))]
        else: items += [('call', lambda: s.set_ball(False)), f"{em.name} broke free!", enemy]
        return items
    def set_ball(s, v): s.in_ball = v; s.show_e = not v
    def caught(s, m):
        s.rid += 1; s.end = 'caught'; m.hp = max(1, m.hp)
        if len(s.g.party) < 6: s.g.party.append(m); return None
        s.g.box.append(m); return [f"{m.name} was sent to the box."]
    def calc(s, att, dfn, mv):
        d = MOVE_INFO[mv[0]]; L_ = att.level
        base = ((2 * L_ / 5 + 2) * d['pow'] * att.atk / max(1, dfn.df)) / 50 + 2
        stab = 1.5 if d['type'] == att.type else 1
        eff = type_eff(d['type'], dfn.type); crit = random.random() < 1 / 16
        dmg = int(base * stab * eff * (1.5 if crit else 1) * random.uniform(0.85, 1))
        return max(1, dmg), eff, crit
    def attack(s, who, mv, rid):
        if s.rid != rid: return []
        att, dfn = (s.pm, s.em) if who == 'p' else (s.em, s.pm)
        if att.hp <= 0 or dfn.hp <= 0: return []
        if who == 'p' and mv[0] != 'Struggle': mv[1] -= 1
        out = [f"{s.label(att)} used {mv[0]}!"]
        if random.random() * 100 > MOVE_INFO[mv[0]]['acc']:
            out.append("But it missed!"); return out
        dmg, eff, crit = s.calc(att, dfn, mv)
        out.append(('call', lambda: s.hit(dfn, dmg, eff, crit, rid)))
        return out
    def hit(s, dfn, dmg, eff, crit, rid):
        dfn.hp = max(0, dfn.hp - dmg); s.shake['e' if dfn is s.em else 'p'] = 12
        items = []
        if crit: items.append("A critical hit!")
        if eff > 1: items.append("It's super effective!")
        elif eff < 1: items.append("It's not very effective...")
        if dfn.hp <= 0: items.append(('call', lambda: s.faint(dfn)))
        return items
    def faint(s, dfn):
        s.rid += 1; items = []
        if dfn is s.em:
            s.show_e = False; items.append(f"{s.label(dfn)} fainted!")
            xp = int(SPECIES[dfn.key]['xp'] * dfn.level / 4 * (1 if s.wild else 1.5))
            for m in list(s.parts):
                if m.hp > 0:
                    items.append(f"{m.name} gained {xp} XP!")
                    items.append(('call', lambda m=m: m.add_xp(xp)))
            nxt = [f for f in s.foes if f.hp > 0]
            if nxt:
                ne = nxt[0]
                items += [('call', lambda: s.send_foe(ne)), f"{s.trainer} sent out {ne.name}!"]
            else:
                s.end = 'win'
                if not s.wild: items.append(f"You defeated {s.trainer}!")
        else:
            s.show_p = False; items.append(f"{dfn.name} fainted!")
            if any(m.hp > 0 for m in s.g.party): s.need_switch = True
            else: s.end = 'lose'; items.append(f"{PLAYER_NAME} is out of usable monsters!")
        return items
    def send_foe(s, ne):
        s.em = ne; s.disp_e = ne.hp; s.show_e = True; s.parts = [s.pm]
    # ---- drawing ----
    def draw(s, surf):
        surf.fill((150, 206, 250), (0, 0, LW, GAME_H))
        for i in range(0, 120, 6): surf.fill((166 + i // 6, 214 + i // 12, 250), (0, i, LW, 6))
        pygame.draw.rect(surf, (132, 196, 104), (0, 120, LW, 90))
        for yy in range(124, 206, 10): pygame.draw.line(surf, (116, 180, 92), (0, yy), (LW, yy))
        pygame.draw.ellipse(surf, (96, 160, 76), (176, 102, 124, 34)); pygame.draw.ellipse(surf, (110, 176, 88), (182, 106, 112, 26))
        pygame.draw.ellipse(surf, (96, 160, 76), (22, 182, 124, 34)); pygame.draw.ellipse(surf, (110, 176, 88), (28, 186, 112, 26))
        if s.show_e:
            ox = random.randint(-3, 3) if s.shake['e'] > 0 and s.shake['e'] % 2 == 0 else 0
            surf.blit(mon_img(s.em.key, 4), (206 + ox, 54))
        if s.in_ball or (not s.show_e and s.phase == 'msgs' and s.in_ball):
            bx = 238 + int(math.sin(s.t * 0.4) * 5); by = 100
            pygame.draw.circle(surf, (230, 50, 50), (bx, by), 11); pygame.draw.rect(surf, (250, 250, 250), (bx - 11, by, 22, 11))
            pygame.draw.circle(surf, (30, 30, 40), (bx, by), 11, 2); pygame.draw.circle(surf, (250, 250, 250), (bx, by), 4)
        if s.show_p:
            ox = random.randint(-3, 3) if s.shake['p'] > 0 and s.shake['p'] % 2 == 0 else 0
            surf.blit(mon_img(s.pm.key, 5), (44 + ox, 116))
        box(surf, (8, 10, 160, 46))
        put(surf, s.em.name, 16, 15, FONT_M); put(surf, f"Lv{s.em.level}", 160, 17, FONT_S, (90, 90, 110), right=True)
        put(surf, "HP", 16, 36, FONT_S, (200, 80, 60)); draw_bar(surf, 36, 38, 120, 8, s.disp_e / s.em.maxhp)
        box(surf, (156, 142, 158, 58))
        put(surf, s.pm.name, 164, 147, FONT_M); put(surf, f"Lv{s.pm.level}", 308, 149, FONT_S, (90, 90, 110), right=True)
        put(surf, "HP", 164, 168, FONT_S, (200, 80, 60)); draw_bar(surf, 184, 170, 120, 8, s.disp_p / s.pm.maxhp)
        put(surf, f"{int(s.disp_p)}/{s.pm.maxhp}", 306, 181, FONT_S, (60, 60, 80), right=True)
        lo, hi = xp_for(s.pm.level), xp_for(s.pm.level + 1)
        draw_bar(surf, 164, 191, 140, 4, (s.pm.xp - lo) / max(1, hi - lo), (80, 140, 240))
        if s.phase == 'party': draw_party(surf, s.g.party, s.psel, None, 'CHOOSE A MONSTER', False); return
        box(surf, (4, 206, 312, 78))
        if s.phase == 'msgs': draw_typed(surf, '\n'.join(wrap(s.text, FONT_M, 290)), s.shown, 14, 214)
        else:
            if s.phase == 'menu':
                put(surf, f"What will\n{s.pm.name} do?".split('\n')[0], 14, 218); put(surf, f"{s.pm.name} do?", 14, 240)
                box(surf, (156, 206, 160, 78))
                for i, nm in enumerate(('FIGHT', 'BAG', 'MONSTERS', 'RUN')):
                    x = 176 + (i % 2) * 74; y = 220 + (i // 2) * 28
                    put(surf, ("> " if i == s.sel else "  ") + nm if nm != 'MONSTERS' else ("> " if i == s.sel else "  ") + 'TEAM', x - 14, y)
            elif s.phase == 'fight':
                for i, (nm, pp) in enumerate(s.pm.moves):
                    x = 14 + (i % 2) * 150; y = 216 + (i // 2) * 30
                    put(surf, ("> " if i == s.fsel else "  ") + nm, x, y)
                    put(surf, f"{MOVE_INFO[nm]['type'].upper()} {pp}/{MOVE_INFO[nm]['pp']}", x + 14, y + 14, FONT_S, (110, 110, 130))
            elif s.phase == 'bag':
                for i, nm in enumerate((f"Potion  x{s.g.bag['potion']}", f"Capture Ball  x{s.g.bag['ball']}", "Back")):
                    put(surf, ("> " if i == s.bsel else "  ") + nm, 20, 214 + i * 22)

# =====================================================================
#                           PAUSE MENU
# =====================================================================
class PauseMenu:
    def __init__(s, g):
        s.g = g; s.mode = 'main'; s.sel = 0; s.done = False
        s.items = ['PARTY', 'BAG', 'CARD', 'SAVE', 'CLOSE']; s.msg = ''; s.swap = None
    def update(s, inp):
        p = inp.pressed; g = s.g
        def nav(n):
            if 'up' in p: s.sel = (s.sel - 1) % n
            if 'down' in p: s.sel = (s.sel + 1) % n
        if s.mode == 'main':
            nav(len(s.items)); s.msg = s.msg if not p else ''
            if 'b' in p or 'start' in p: s.done = True
            if 'a' in p:
                it = s.items[s.sel]
                if it == 'CLOSE': s.done = True
                elif it == 'SAVE': s.msg = 'Game saved!' if g.save() else 'Could not save.'
                else: s.mode = it.lower(); s.sel = 0; s.swap = None
        elif s.mode == 'party':
            if not g.party: s.mode = 'main'; return
            nav(len(g.party))
            if 'b' in p:
                if s.swap is not None: s.swap = None
                else: s.mode = 'main'; s.sel = 0
            if 'a' in p:
                if s.swap is None: s.swap = s.sel
                else:
                    g.party[s.swap], g.party[s.sel] = g.party[s.sel], g.party[s.swap]; s.swap = None
        elif s.mode == 'bag':
            nav(3)
            if 'b' in p: s.mode = 'main'; s.sel = 1
            if 'a' in p:
                if s.sel == 0 and g.bag['potion'] > 0 and g.party: s.mode = 'potion'; s.sel = 0
                elif s.sel == 1: s.msg = "Capture Balls are used in battle."
                elif s.sel == 2: s.mode = 'main'; s.sel = 1
        elif s.mode == 'potion':
            nav(len(g.party))
            if 'b' in p: s.mode = 'bag'; s.sel = 0
            if 'a' in p:
                m = g.party[s.sel]
                if 0 < m.hp < m.maxhp:
                    m.hp = min(m.maxhp, m.hp + 30); g.bag['potion'] -= 1
                    s.msg = f"{m.name} recovered HP!"
                    if g.bag['potion'] <= 0: s.mode = 'bag'; s.sel = 0
                else: s.msg = "It won't have any effect."
        elif s.mode == 'card':
            if 'b' in p or 'a' in p: s.mode = 'main'; s.sel = 2
    def draw(s, surf):
        g = s.g
        if s.mode == 'main':
            box(surf, (190, 8, 122, 20 + len(s.items) * 26))
            for i, it in enumerate(s.items): put(surf, ("> " if i == s.sel else "  ") + it, 198, 18 + i * 26)
            put(surf, f"{CURRENCY}{g.money}", 198, 28 + len(s.items) * 26 + 4, FONT_M, (255, 255, 255), (0, 0, 0))
            if s.msg:
                box(surf, (4, 240, 312, 40)); put(surf, s.msg, 14, 252)
        elif s.mode in ('party', 'potion'):
            draw_party(surf, g.party, s.sel, s.swap, 'PARTY (A: swap)' if s.mode == 'party' else 'USE POTION on...')
            if s.msg and s.mode == 'potion': box(surf, (60, 100, 200, 30)); put(surf, s.msg, 70, 108)
        elif s.mode == 'bag':
            surf.fill((72, 104, 168), (0, 0, LW, GAME_H)); put(surf, "BAG", 12, 6, FONT_L, (255, 255, 255))
            box(surf, (20, 40, 280, 120))
            for i, nm in enumerate((f"Potion  x{g.bag['potion']}", f"Capture Ball  x{g.bag['ball']}", "Back")):
                put(surf, ("> " if i == s.sel else "  ") + nm, 40, 56 + i * 30)
            if s.msg: box(surf, (4, 240, 312, 40)); put(surf, s.msg, 14, 252)
        elif s.mode == 'card':
            surf.fill((72, 104, 168), (0, 0, LW, GAME_H)); box(surf, (20, 30, 280, 200))
            put(surf, f"TRAINER CARD", 160, 42, FONT_L, (40, 40, 80), center=True)
            put(surf, f"Name:   {PLAYER_NAME}", 40, 82); put(surf, f"Money:  {CURRENCY}{g.money}", 40, 106)
            put(surf, f"Badges: {1 if 'badge1' in g.flags else 0}", 40, 130)
            put(surf, f"Team:   {len(g.party)}   Box: {len(g.box)}", 40, 154)
            t = int(g.playtime); put(surf, f"Time:   {t // 3600}:{(t // 60) % 60:02d}:{t % 60:02d}", 40, 178)

# =====================================================================
#                              GAME
# =====================================================================
class Game:
    def __init__(s):
        s.inp = Input(); s.state = 'title'; s.dlg = None; s.dlg_result = None; s.task = None
        s.battle = None; s.menu = None; s.fade_a = 0; s.fade_col = (0, 0, 0)
        s.title_sel = 0; s.banner = ('', 0); s.map = None; s.pl = None
        s.has_save = os.path.exists(SAVE_PATH); s.playtime = 0.0; s.new_data()
    def new_data(s):
        s.party = []; s.box = []; s.bag = {'potion': 3, 'ball': 5}; s.money = START_MONEY; s.flags = set()
        s.respawn = ('town', 6, 22, 2)
    # ---------- save / load ----------
    def save(s):
        try:
            d = dict(map=s.map.name, x=s.pl.x, y=s.pl.y, dir=s.pl.dir, party=[m.to_dict() for m in s.party],
                     box=[m.to_dict() for m in s.box], bag=s.bag, money=s.money, flags=list(s.flags),
                     respawn=list(s.respawn), time=s.playtime)
            with open(SAVE_PATH, 'w') as f: json.dump(d, f)
            s.has_save = True; return True
        except Exception:
            return False
    def load(s):
        try:
            with open(SAVE_PATH) as f: d = json.load(f)
            s.party = [Mon.from_dict(x) for x in d['party']]; s.box = [Mon.from_dict(x) for x in d['box']]
            s.bag = d['bag']; s.money = d['money']; s.flags = set(d['flags']); s.respawn = tuple(d['respawn'])
            s.playtime = d.get('time', 0)
            s.pl = Actor(d['x'], d['y'], LOOKS['player'], d['dir'])
            s.set_map(d['map'], d['x'], d['y'], d['dir']); return True
        except Exception:
            return False
    def start_new(s):
        s.new_data(); s.playtime = 0
        s.pl = Actor(4, 5, LOOKS['player'], 0)
        s.set_map('town_home', 4, 5, 0); s.state = 'world'
        s.task = s.task_intro()
    def set_map(s, name, x, y, d):
        old = s.map.title if s.map else ''
        s.map = MAPS[name]; s.pl.x, s.pl.y = x, y; s.pl.dir = d; s.pl.moving = False; s.pl.prog = 0
        for n in s.map.npcs: n.moving = False; n.prog = 0
        if s.map.title != old: s.banner = (s.map.title, 110)
    # ---------- helpers ----------
    def say(s, *pages, choices=None):
        s.dlg = Dialogue([p.replace('{p}', PLAYER_NAME) for p in pages], choices); s.dlg_result = None
        while s.dlg is not None: yield
        return s.dlg_result
    def fade(s, to, frames=10):
        start = s.fade_a
        for i in range(1, frames + 1):
            s.fade_a = int(start + (to - start) * i / frames); yield
    def wait(s, n):
        for _ in range(n): yield
    def npc_at(s, x, y):
        for n in s.map.npcs:
            if n.visible(s) and ((n.x, n.y) == (x, y) or (n.moving and (n.tx, n.ty) == (x, y))): return n
        return None
    def blocked(s, x, y, ignore=None):
        if s.map.tile(x, y) in SOLID: return True
        if s.npc_at(x, y) not in (None, ignore): return True
        pl = s.pl
        if ignore is not pl and ((pl.x, pl.y) == (x, y) or (pl.moving and (pl.tx, pl.ty) == (x, y))): return True
        return False
    def alive(s): return any(m.hp > 0 for m in s.party)
    # ---------- tasks (cutscenes written as generators) ----------
    def task_intro(s):
        yield from s.say(f"Welcome to the world of {GAME_TITLE}!", "Here, people and monsters live and train side by side.",
                         f"Your name is {PLAYER_NAME}. Today, your adventure begins!")
    def task_warp(s, dest):
        yield from s.fade(255, 6)
        name, x, y, d = dest
        s.set_map(name, x, y, d)
        yield from s.fade(0, 6)
    def task_wild(s):
        pool = s.map.wild; tot = sum(p[3] for p in pool); r = random.uniform(0, tot)
        for sp_, lo, hi, w in pool:
            r -= w
            if r <= 0: break
        mon = Mon(sp_, random.randint(lo, hi))
        yield from s.flash()
        res = yield from s.run_battle(Battle(s, [mon], True))
        yield from s.after_battle(res)
    def flash(s):
        s.fade_col = (255, 255, 255)
        for _ in range(2):
            yield from s.fade(190, 3); yield from s.fade(0, 3)
        s.fade_col = (0, 0, 0)
        yield from s.fade(255, 5)
    def run_battle(s, b):
        s.fade_col = (0, 0, 0)
        s.battle = b; s.state = 'battle'
        yield from s.fade(0, 8)
        while not b.finished: yield
        yield from s.fade(255, 8)
        s.battle = None; s.state = 'world'
        yield from s.fade(0, 8)
        return b.result
    def after_battle(s, res):
        if res == 'lose':
            yield from s.blackout(); return
        for m in s.party:
            if m.hp > 0 and m.check_evolve():
                old = m.name
                yield from s.say(f"What? {old} is evolving!")
                m.evolve()
                yield from s.say(f"{old} evolved into {m.name}!")
    def blackout(s):
        yield from s.say("You are out of usable monsters!", "You rushed to the nearest Monster Center...")
        yield from s.fade(255, 12)
        for m in s.party: m.heal()
        s.money -= s.money // 10
        n, x, y, d = s.respawn; s.set_map(n, x, y, d)
        yield from s.fade(0, 12)
        yield from s.say("Your team has been restored. Don't give up!")
    def sees(s, n):
        if n.kind not in ('trainer',) or n.id in s.flags: return False
        pl = s.pl; dx, dy = pl.x - n.x, pl.y - n.y
        if dx != 0 and dy != 0: return False
        d = (0 if dy < 0 else 2) if dx == 0 else (1 if dx > 0 else 3)
        if d != n.dir: return False
        dist = abs(dx) + abs(dy)
        if dist > n.sight: return False
        for k in range(1, dist):
            tx, ty = n.x + DIRS[d][0] * k, n.y + DIRS[d][1] * k
            if s.map.tile(tx, ty) in SOLID: return False
        return True
    def on_step_end(s):
        pl = s.pl; m = s.map
        if (pl.x, pl.y) in m.warps: s.task = s.task_warp(m.warps[(pl.x, pl.y)]); return
        for n in m.npcs:
            if n.visible(s) and s.sees(n): s.task = s.task_trainer(n, True); return
        if m.tile(pl.x, pl.y) == TALL and m.wild and s.alive() and random.random() < ENCOUNTER_RATE:
            s.task = s.task_wild()
    def interact(s):
        pl = s.pl; m = s.map; dx, dy = DIRS[pl.dir]
        for k in (1, 2):
            tx, ty = pl.x + dx * k, pl.y + dy * k
            n = s.npc_at(tx, ty)
            if n and not n.moving: s.task = s.task_talk(n); return
            o = m.objs.get((tx, ty))
            if o: s.task = s.task_object(o); return
            if m.tile(tx, ty) not in (COUNTER, HEAL): break
    def task_object(s, o):
        if o[0] == 'sign': yield from s.say(o[1])
        elif o[0] == 'starter': yield from s.task_starter(o[1])
    def task_starter(s, key):
        if 'starter' in s.flags:
            yield from s.say("Those are the other starters. You already have a partner!"); return
        info = SPECIES[key]
        c = yield from s.say(f"{key}, the {info['type'].upper()}-type monster.", "Choose this one?", choices=['YES', 'NO'])
        if c != 0: return
        s.party.append(Mon(key, 5)); s.flags.add('starter')
        yield from s.say(f"{PLAYER_NAME} received {key}!")
        s.bag['ball'] += 5; s.bag['potion'] += 2
        yield from s.say(f"{PROF_NAME}: Take these too! 5 Capture Balls and 2 Potions.",
                         "Weaken wild monsters, then throw a Ball to catch them!")
        rival = next(n for n in s.map.npcs if n.kind == 'rival')
        yield from s.task_trainer(rival, False)
    def rival_team(s):
        c = {'Flamlet': 'Aquabit', 'Aquabit': 'Leafkin', 'Leafkin': 'Flamlet'}
        mine = s.party[0].key if s.party else 'Flamlet'
        for k in c:
            if 'start_' + k in s.flags: mine = k
        return [(c.get(mine, 'Aquabit'), 5)]
    def task_talk(s, n):
        if not n.fixed: n.dir = (s.pl.dir + 2) % 4
        k = n.kind
        if k == 'nurse':
            c = yield from s.say("Welcome to the Monster Center!", "Shall I heal your team?", choices=['YES', 'NO'])
            if c == 0:
                yield from s.fade(255, 8); yield from s.wait(15)
                for m in s.party: m.heal()
                s.respawn = s.map.warps[s.map.mat]
                yield from s.fade(0, 8)
                yield from s.say("Your team is fully healed!", "We hope to see you again!")
            else: yield from s.say("Come back anytime!")
        elif k == 'clerk': yield from s.t_mart()
        elif k == 'mom':
            if 'starter' in s.flags and callable(n.text):
                yield from s.say(*n.text(s))
                for m in s.party: m.heal()
                yield from s.say("...Your monsters feel refreshed!")
            else:
                yield from s.say(*(n.text(s) if callable(n.text) else n.text))
        elif k == 'prof':
            if 'starter' in s.flags: yield from s.say(f"{PROF_NAME}: Go see the world! Sunport City is north, past Route 1.")
            else: yield from s.say(f"{PROF_NAME}: {{p}}! Welcome. Choose one of the three monsters on the table.", "Walk up to a ball and press A!")
        elif k == 'gift':
            item, qty, flag = n.gift
            if flag in s.flags: yield from s.say("Good luck on your journey!")
            else:
                yield from s.say(*n.text); s.flags.add(flag); s.bag[item] += qty
                yield from s.say(f"{PLAYER_NAME} received {qty} {item}s!")
        elif k in ('trainer', 'leader', 'rival'):
            if k == 'rival' and 'starter' not in s.flags:
                yield from s.say(f"{RIVAL_NAME}: Hey, {PROF_NAME} said I can pick first, but I'll wait for you."); return
            yield from s.task_trainer(n, False)
        else:
            yield from s.say(*(n.text(s) if callable(n.text) else n.text))
    def t_mart(s):
        yield from s.say("Welcome to the Monster Mart!")
        while True:
            c = yield from s.say(f"What would you like? ({CURRENCY}{s.money})", choices=[f"Potion {CURRENCY}50", f"Capture Ball {CURRENCY}30", "Leave"])
            if c == 2 or c is None: break
            item, price = (('potion', 50), ('ball', 30))[c]
            if s.money >= price:
                s.money -= price; s.bag[item] += 1
                yield from s.say(f"Here you go! You now have {s.bag[item]}.")
            else: yield from s.say("You don't have enough money.")
        yield from s.say("Please come again!")
    def task_trainer(s, n, spotted):
        pl = s.pl
        if n.id in s.flags:
            yield from s.say(*n.after); return
        if n.kind == 'rival' and 'starter' not in s.flags: return
        if spotted:
            n.bubble = 40
            for _ in range(40): yield
            n.bubble = 0
            while abs(n.x - pl.x) + abs(n.y - pl.y) > 1:
                if n.x == pl.x: d = 2 if pl.y > n.y else 0
                else: d = 1 if pl.x > n.x else 3
                n.start_move(d)
                while n.moving:
                    n.update_move(2.0); yield
            pl.dir = (n.dir + 2) % 4
        if n.kind == 'rival':
            yield from s.say(f"{RIVAL_NAME}: So you picked one too? Let's see who's stronger!")
            team = s.rival_team()
        else:
            yield from s.say(*[t.replace('{p}', PLAYER_NAME) for t in n.text])
            team = n.team
        foes = [Mon(k, l) for k, l in team]
        reward = n.reward if n.kind != 'rival' else 150
        yield from s.flash()
        res = yield from s.run_battle(Battle(s, foes, False, n.name, reward))
        if res == 'win':
            s.flags.add(n.id); s.money += reward
            yield from s.say(f"{PLAYER_NAME} got {CURRENCY}{reward} for winning!")
            if n.kind == 'rival':
                yield from s.say(f"{RIVAL_NAME}: What?! I lost... I'll train harder. See you around!")
                n.after = [f"{RIVAL_NAME}: I'll beat you next time!"]
            elif n.kind == 'leader':
                s.flags.add('badge1')
                yield from s.say(f"{LEADER_NAME}: Incredible! You earned the {BADGE_NAME}!",
                                 f"{PLAYER_NAME} received the {BADGE_NAME}!",
                                 f"Congratulations! You beat the first Gym of {GAME_TITLE}.",
                                 "More adventures await. Keep exploring, catching, and training!")
            else: yield from s.say(*n.after)
        yield from s.after_battle(res)
    # ---------- update ----------
    def update(s):
        s.inp.update(); inp = s.inp
        if s.state == 'title': s.update_title(inp); return
        s.playtime += 1 / 60.0
        ran = False
        if s.menu:
            s.menu.update(inp); ran = True
            if s.menu.done: s.menu = None
        if s.dlg:
            s.dlg.update(inp); ran = True
            if s.dlg.done: s.dlg_result = s.dlg.result; s.dlg = None
        if s.state == 'battle' and s.battle and not s.battle.finished: s.battle.update(inp)
        if s.task:
            ran = True
            try: next(s.task)
            except StopIteration: s.task = None
        if s.banner[1] > 0: s.banner = (s.banner[0], s.banner[1] - 1)
        if s.state != 'world' or ran: s.update_npcs(False); return
        s.update_npcs(True)
        pl = s.pl; held = inp.held; p = inp.pressed
        if pl.moving:
            if pl.update_move(RUN_SPEED if 'b' in held else WALK_SPEED): s.on_step_end()
            return
        if 'start' in p: s.menu = PauseMenu(s); return
        if 'a' in p: s.interact(); return
        d = None
        for k, nm in enumerate(('up', 'right', 'down', 'left')):
            if nm in p: d = k
        if d is None:
            for k, nm in enumerate(('up', 'right', 'down', 'left')):
                if nm in held: d = k; break
        if d is not None:
            pl.dir = d
            tx, ty = pl.x + DIRS[d][0], pl.y + DIRS[d][1]
            if not s.blocked(tx, ty): pl.start_move(d)
    def update_npcs(s, wander):
        for n in s.map.npcs:
            if n.moving: n.update_move(1.0)
            elif wander and n.wander and n.visible(s) and random.random() < 0.012:
                d = random.randrange(4); tx, ty = n.x + DIRS[d][0], n.y + DIRS[d][1]
                if abs(tx - n.home[0]) <= n.radius and abs(ty - n.home[1]) <= n.radius and not s.blocked(tx, ty, n) \
                        and s.map.tile(tx, ty) not in (DOOR, MAT) and (tx, ty) not in s.map.warps:
                    n.start_move(d)
            if n.bubble > 0 and not s.task: n.bubble = 0
    def update_title(s, inp):
        p = inp.pressed
        n = 2 if s.has_save else 1
        if 'up' in p or 'down' in p: s.title_sel = (s.title_sel + 1) % n
        if 'a' in p or 'start' in p:
            if s.title_sel == 0 and not (s.has_save and s.title_sel == 1):
                s.start_new()
            elif s.title_sel == 1 and s.has_save:
                if s.load(): s.state = 'world'
    # ---------- draw ----------
    def draw(s):
        scr = screen; scr.fill((0, 0, 0))
        if s.state == 'title':
            ui_base.fill((0, 0, 0)); s.draw_title(ui_base); blit_panel(scr, ui_base)
        else:
            if s.state == 'battle' and s.battle:
                ui_base.fill((0, 0, 0)); s.battle.draw(ui_base); blit_panel(scr, ui_base)
            else: s.draw_world(scr)
            if s.fade_a > 0:
                FADE_OV.fill(s.fade_col); FADE_OV.set_alpha(clamp(s.fade_a, 0, 255)); scr.blit(FADE_OV, (0, 0))
            if s.menu or s.dlg:
                ui_over.fill((0, 0, 0, 0))
                if s.menu: s.menu.draw(ui_over)
                if s.dlg: s.dlg.draw(ui_over)
                if ui_over.get_at((0, 0))[3] == 255 and ui_over.get_at((LW - 1, GAME_H - 1))[3] == 255:
                    blit_panel(scr, ui_over)       # full-screen menu page (party / bag / card)
                else:
                    scr.blit(ui_over, (UX, 0))     # small overlay (dialogue box, pause list)
        draw_controls(scr, s.inp.held)
    def draw_title(s, scr):
        for i in range(0, GAME_H, 4):
            scr.fill((110 + i // 4, 180 + i // 8, 250 - i // 6), (0, i, LW, 4))
        t = pygame.time.get_ticks() / 1000.0
        for i in range(0, LW, 16):
            h = 40 + int(14 * math.sin(i * 0.05 + 1.0)); pygame.draw.rect(scr, (90, 168, 70), (i, GAME_H - h, 16, h))
            pygame.draw.rect(scr, (70, 140, 56), (i, GAME_H - h, 16, 4))
        put(scr, GAME_TITLE, LW // 2, 50, FONT_XL, (255, 220, 60), (120, 40, 20), center=True)
        put(scr, "A Pixel Monster Adventure", LW // 2, 100, FONT_M, (255, 255, 255), (40, 60, 120), center=True)
        for k, key in enumerate(('Flamlet', 'Aquabit', 'Leafkin')):
            scr.blit(mon_img(key, 4), (40 + k * 84, 130 + int(math.sin(t * 3 + k) * 4)))
        opts = ['NEW GAME'] + (['CONTINUE'] if s.has_save else [])
        for i, o in enumerate(opts):
            put(scr, ("> " if i == s.title_sel else "  ") + o, LW // 2, 214 + i * 24, FONT_L, (255, 255, 255), (30, 30, 60), center=True)
        put(scr, "Press A to start", LW // 2, 268, FONT_S, (255, 255, 255), center=True)
    def draw_world(s, scr):
        m = s.map; pl = s.pl; w = world
        ppx, ppy = pl.pixel()
        cx = int(ppx + 8 - VIEW_W / 2); cy = int(ppy + 8 - VIEW_H / 2)
        mw, mh = m.w * 16, m.h * 16
        cx = (mw - VIEW_W) // 2 if mw <= VIEW_W else clamp(cx, 0, mw - VIEW_W)
        cy = (mh - VIEW_H) // 2 if mh <= VIEW_H else clamp(cy, 0, mh - VIEW_H)
        w.fill((18, 16, 28))
        anim = int(time.time() * 2) % 2
        bg = getattr(m, '_bg', None)
        if bg is None:
            bg = pygame.Surface((mw, mh)); bg.fill((18, 16, 28)); water = []
            for ty in range(m.h):
                for tx in range(m.w):
                    img = TILES[m.t[ty][tx]]
                    if isinstance(img, list): water.append((tx * 16, ty * 16))
                    else: bg.blit(img, (tx * 16, ty * 16))
            m._bg = bg; m._water = water
        w.blit(bg, (-cx, -cy))
        wt = TILES[WATER][anim]
        for (wx, wy) in m._water:
            if -16 < wx - cx < VIEW_W and -16 < wy - cy < VIEW_H: w.blit(wt, (wx - cx, wy - cy))
        actors = [n for n in m.npcs if n.visible(s)] + [pl]
        actors.sort(key=lambda a: a.pixel()[1])
        for a in actors:
            x, y = a.pixel()
            w.blit(a.img(), (int(x - cx), int(y - cy) - 2))
            if a.bubble > 0:
                bx, by = int(x - cx) + 5, int(y - cy) - 14
                pygame.draw.rect(w, (255, 255, 255), (bx, by, 7, 11)); pygame.draw.rect(w, (30, 30, 40), (bx, by, 7, 11), 1)
                pygame.draw.rect(w, (220, 40, 40), (bx + 3, by + 2, 1, 5)); pygame.draw.rect(w, (220, 40, 40), (bx + 3, by + 8, 1, 1))
        if not m.indoor:
            ph = (time.time() / DAY_CYCLE_SECONDS) % 1.0
            dark = max(0.0, -math.sin(ph * 2 * math.pi))
            if dark > 0.02:
                DARK_OV.set_alpha(int(dark * 120) // 4 * 4); w.blit(DARK_OV, (0, 0))
        scr.blit(pygame.transform.scale(w, (SW, SH)), (0, 0))
        if s.banner[1] > 0 and s.banner[0]:
            a = min(1.0, s.banner[1] / 25.0)
            if a > 0.2:
                box(scr, (SW // 2 - 80, 6, 160, 26)); put(scr, s.banner[0], SW // 2, 12, FONT_M, center=True)

# =====================================================================
#                              MAIN LOOP
# =====================================================================
_last_win = [None]
def present():
    global VIEW, window
    window = pygame.display.get_surface()
    ww, wh = window.get_size()
    sc = min(ww / SW, wh / SH)
    w, h = max(1, int(SW * sc)), max(1, int(SH * sc))
    ox, oy = (ww - w) // 2, (wh - h) // 2
    VIEW = (sc, ox, oy)
    if _last_win[0] != (ww, wh):
        window.fill((0, 0, 0)); _last_win[0] = (ww, wh)
    elif ox or oy:
        window.fill((0, 0, 0))
    if (w, h) == (SW, SH):
        window.blit(screen, (ox, oy))
    else:
        try:
            pygame.transform.scale(screen, (w, h), window.subsurface((ox, oy, w, h)))
        except Exception:
            window.blit(pygame.transform.scale(screen, (w, h)), (ox, oy))
    pygame.display.flip()

def main():
    build_world()
    g = Game(); clock = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.VIDEORESIZE and not hasattr(pygame, 'WINDOWRESIZED') and not ANDROID:
                pygame.display.set_mode(e.size, pygame.RESIZABLE)
            g.inp.event(e)
        g.update(); g.draw(); present()
        clock.tick(60)

if __name__ == '__main__':
    main()
