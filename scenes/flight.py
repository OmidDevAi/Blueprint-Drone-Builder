import math
import random

import pygame

from config import (SW, SH, W, H, PANEL, WHITE, SOFT, DIM, TEAL,
                    GOLD, RED, CYAN, SECTORS, CLEAR_RATIO, GRADE_ORDER,
                    CAMPAIGN_BONUS)
from render3d import (make_cam, cam_proj, cam_rot, draw_glow, draw_parts,
                      clamp, mix, ease, smooth, fill_alpha_poly)
from scene_base import Scene, sky_surface
from ship import build_ship, compute_stats
from ui import panel, text, bar, Button, set_cursor
import audio
import postfx

FLOOR_Y = -1.35
CORE_COLLECT = 0.92
CORE_PULL = 1.55
MINE_HIT = 0.88
MINE_NEAR = 1.70
PAD_HIT = 1.05


def _rot(tilt, v):
    tp, tr = tilt
    cp, sp = math.cos(tp), math.sin(tp)
    x, y, z = v
    y, z = cp * y - sp * z, sp * y + cp * z
    cr, sr = math.cos(tr), math.sin(tr)
    return (cr * x - sr * y, sr * x + cr * y, z)


def _ell(cx, cy, rx, ry, n=14):
    return [(cx + rx * math.cos(2 * math.pi * i / n),
             cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _clip_project(cam, pts):
    """Project a world polygon, clipping it against the camera near plane.

    Large floor quads are much bigger than the near plane; dropping them
    whole when one corner slips behind the camera leaves sky showing at the
    bottom of the screen during hard turns.
    """
    near = 0.6
    cam_pts = []
    for p in pts:
        x, y, z = cam_rot(cam, p)
        cam_pts.append((x, y, cam['camp'] - z))
    out = []
    n = len(cam_pts)
    for i in range(n):
        ax, ay, ad = cam_pts[i]
        bx, by, bd = cam_pts[(i + 1) % n]
        ain, bin_ = ad >= near, bd >= near
        if ain:
            out.append((ax, ay, ad))
        if ain != bin_:
            k = (near - ad) / (bd - ad)
            out.append((ax + (bx - ax) * k, ay + (by - ay) * k, near))
    if len(out) < 3:
        return None
    f0 = cam['scale'] * cam['camp']
    return [(cam['cx'] + x * f0 / d, cam['cy'] - y * f0 / d)
            for x, y, d in out]


def _mul(col, k):
    return (max(0, min(255, int(col[0] * k))),
            max(0, min(255, int(col[1] * k))),
            max(0, min(255, int(col[2] * k))))


_SKY3 = {}


def _sky_grad(stops):
    key = tuple(stops)
    s = _SKY3.get(key)
    if s is not None:
        return s
    s = pygame.Surface((SW, SH))
    n = max(1, len(stops) - 1)
    for y in range(SH):
        t = y / max(1, SH - 1) * n
        i = min(n - 1, int(t))
        pygame.draw.line(s, mix(stops[i + 1], stops[i], t - i),
                         (0, y), (SW, y))
    if len(_SKY3) > 12:
        _SKY3.clear()
    _SKY3[key] = s
    return s


def _sky3(top, mid, bot):
    return _sky_grad((top, mid, bot))


def _dome(cx, base, rx, ry, n=14):
    pts = [(cx - rx, base)]
    for i in range(n + 1):
        a = math.pi - math.pi * i / n
        pts.append((cx + math.cos(a) * rx, base - math.sin(a) * ry))
    pts.append((cx + rx, base))
    return pts


_GROUND_KEYS = ((6.0, 0.95), (30.0, 0.87), (51.0, 0.79), (74.0, 0.71),
                (99.0, 0.63), (127.0, 0.55), (160.0, 0.47), (199.0, 0.39),
                (244.0, 0.31))


def _ground_k(dep):
    if dep <= _GROUND_KEYS[0][0]:
        return _GROUND_KEYS[0][1]
    for i in range(len(_GROUND_KEYS) - 1):
        d0, k0 = _GROUND_KEYS[i]
        d1, k1 = _GROUND_KEYS[i + 1]
        if dep <= d1:
            return k0 + (k1 - k0) * (dep - d0) / (d1 - d0)
    return _GROUND_KEYS[-1][1]


class Flight(Scene):
    def __init__(self, app, autopilot=True):
        super().__init__(app)
        self.autopilot = True
        self.sector_i = int(clamp(app.state.get('sector', 0), 0, 2))
        self.sec = SECTORS[self.sector_i]
        self.stats = compute_stats(app.state)
        self.parts = build_ship(app.state)
        self.x, self.y, self.z = 0.0, 1.0, 0.0
        self.vx = self.vy = 0.0
        self.speed = 0.0
        self.energy = self.stats['energy']
        self.max_energy = max(1.0, self.stats['energy'])
        self.time = 0.0
        self.score = 0
        self.streak = 0
        self.combo = 1.0
        self.core_i = 0
        self.hits = 0
        self.dodges = 0
        self.mode = 'intro'
        self.intro_t = 0.0
        self.outro_t = 0.0
        self.result_t = 0.0
        self.reward = 0
        self.grade = 'C'
        self.new_best = False
        self.best = int(app.state.get('best', {}).get(str(self.sector_i), 0))
        self.cores = []
        self.mines = []
        self.pads = []
        self.finish_z = 120.0
        self.popups = []
        self.miss_t = 0.0
        self.boost_fx = 0.0
        self.pad_fx = 0.0
        self.cleared_now = False
        self.unlocked_now = None
        self.campaign_done = False
        self.campaign_bonus = 0
        self.paused = False
        self.pause_t = 0.0
        self.held = set()
        self.frame_dt = 1.0 / 60.0
        self.rng = random.Random(1000 + self.sector_i * 17)
        self.camx = 0.0
        self.camy = 1.0
        self.cam = None
        self.crashed = False
        self.crash_reason = ''
        self.crash_t = 0.0
        self.debris = []
        self.sparks = []
        self.fire = []
        self.boom = 1.0
        self.fault = self.stats.get('fault')
        self.fault_t = 0.0
        self.fault_done = False
        if self.fault:
            frng = random.Random(4242 + self.sector_i * 31)
            self.fault_t = frng.uniform(4.0, 7.5)
        self.trail = []
        self.shake = 0.0
        self.flash = 0.0
        self.flash_surf = pygame.Surface((W, H))
        self.flash_surf.fill((255, 208, 150))
        self.spawn_course()
        self.dust = [{'a': self.rng.uniform(0, 2 * math.pi),
                      'r': self.rng.uniform(0.15, 1.0),
                      'v': self.rng.uniform(0.22, 0.62),
                      'z': self.rng.uniform(0.0, 1.0),
                      's': self.rng.uniform(0.5, 1.4)}
                     for _ in range(34)]
        self.top_col = self.sec['sky']
        self.bot_col = self.sec.get('sky2', (6, 10, 22))
        self.theme = ('street', 'forest', 'canyon')[self.sector_i]
        self.sun_col = (255, 236, 198)
        if self.theme == 'canyon':
            self.fog_col = mix(self.sec['sky'], (10, 15, 28), 0.30)
            self.haze_c = mix(self.sec['sky'], (44, 74, 86), 0.55)
            self.sky_stops = (self.top_col, self.bot_col)
        else:
            hor = self.sec.get('sky3', self.sun_col)
            self.fog_col = mix(hor, self.sec['sky'], 0.62)
            self.sky_stops = (self.top_col, self.sec['sky2'], hor,
                              mix(hor, self.sun_col, 0.55))
        self.blds = []
        self.lamps = []
        self.gantries = []
        self.trees = []
        self.bushes = []
        self.flies = []
        self.birds = []
        self.clouds = []
        self.cars = []
        self.mv_cars = []
        self.peds = []
        self.leaves = []
        self.grass = []
        self.rocks = []
        self.mist = []
        self.dapple = []
        self.isles = []
        self.slabs = []
        self.sun_xy = None
        self._build_props()
        self.again_btn = Button('again', (350, 470, 290, 52), 'FLY AGAIN',
                                'gold', 15, 'mono', 2.4)
        self.home_btn = Button('home', (660, 470, 270, 52), 'HANGAR',
                               'ghost', 14, 'mono', 2.4)
        self.next_btn = Button('next', (548, 470, 200, 52), 'NEXT SECTOR',
                               'gold', 14, 'mono', 2.0)
        self.resume_btn = Button('resume', (450, 344, 380, 54), 'RESUME',
                                 'gold', 16, 'mono', 2.6)
        self.abort_btn = Button('abort', (450, 412, 380, 46), 'ABORT · HANGAR',
                                'ghost', 13, 'mono', 2.2)
        self.mute_btn = Button('mute', (450, 470, 380, 44), 'SOUND ON',
                               'ghost', 12, 'mono', 2.0)

    # ---------- setup ----------
    def _build_props(self):
        rng = random.Random(7300 + self.sector_i * 53)
        self.clouds = []
        for _ in range(9):
            self.clouds.append({
                'x': rng.uniform(-0.1, 1.1), 'y': rng.uniform(0.02, 0.22),
                'w': rng.uniform(100, 210), 'h': rng.uniform(20, 46),
                'k': rng.uniform(0.35, 1.0), 'v': rng.uniform(0.5, 1.5)})

        if self.theme == 'street':
            for side in (-1, 1):
                z = -8.0
                while z < self.finish_z + 54:
                    w = rng.uniform(5.0, 8.4)
                    h = rng.uniform(4.4, 13.0)
                    cols = max(2, int(w / 1.9))
                    rows = max(2, int((h - 2.2) / 1.6))
                    panes = [[rng.random() < 0.62 for _ in range(cols)]
                             for _ in range(rows)]
                    self.blds.append({
                        'side': side, 'z0': z, 'z1': z + w,
                        'x': rng.uniform(8.7, 10.3),
                        'd': rng.uniform(2.4, 4.6),
                        'h': h, 'tone': rng.uniform(0.0, 1.0),
                        'cols': cols, 'rows': rows, 'panes': panes,
                        'neon': rng.random() < 0.42,
                        'neon_col': rng.choice(((226, 74, 104), (64, 178, 226),
                                                (240, 172, 72), (118, 214, 132)))})
                    z += w + rng.uniform(0.6, 2.6)
            self.blds.sort(key=lambda b: -b['z0'])
            self.lamps = list(range(-10, int(self.finish_z) + 58, 15))
            self.gantries = list(range(10, int(self.finish_z) + 24, 46))
            for i in range(6):
                self.birds.append({'x': rng.uniform(0.0, 1.0),
                                   'y': rng.uniform(0.05, 0.30),
                                   'v': rng.uniform(0.8, 1.8),
                                   'ph': rng.uniform(0, 6.28)})

            car_cols = ((186, 62, 58), (58, 92, 148), (214, 186, 96),
                        (228, 228, 222), (64, 112, 88), (140, 142, 152),
                        (92, 74, 112), (46, 50, 62))
            z = 4.0
            while z < self.finish_z + 42:
                side = rng.choice((-1, 1))
                clear = (min([abs(k - z) for k in self.lamps] or [99]) > 3.0
                         and min([abs(g - z) for g in self.gantries]
                                 or [99]) > 3.5)
                if clear and rng.random() < 0.62:
                    self.cars.append({
                        'side': side, 'x': side * rng.uniform(4.50, 4.62),
                        'z': z, 'ln': rng.uniform(3.8, 4.4),
                        'h': rng.uniform(1.26, 1.42),
                        'col': rng.choice(car_cols),
                        'own': 0.0, 'ph': rng.uniform(0, 6.28)})
                z += rng.uniform(6.0, 11.0)
            for lane in (-1, 1):
                for i in range(2):
                    self.mv_cars.append({
                        'side': lane, 'x': lane * 2.55,
                        'z': rng.uniform(10.0, 92.0),
                        'ln': rng.uniform(3.9, 4.4),
                        'h': rng.uniform(1.30, 1.40),
                        'col': rng.choice(car_cols),
                        'own': (-1 if lane < 0 else 1) * rng.uniform(7.0, 11.0),
                        'ph': rng.uniform(0, 6.28)})
            ped_cols = ((54, 62, 84), (92, 72, 66), (140, 144, 152),
                        (72, 96, 80), (150, 120, 90), (60, 60, 66),
                        (166, 84, 84), (96, 84, 120))
            for _ in range(38):
                side = rng.choice((-1, 1))
                self.peds.append({
                    'side': side, 'x': side * rng.uniform(7.0, 8.55),
                    'z': rng.uniform(-3.0, self.finish_z + 46.0),
                    'ph': rng.uniform(0, 6.28), 'ph2': rng.uniform(0, 6.28),
                    'sp': rng.uniform(0.8, 1.5),
                    'pace': rng.uniform(2.5, 6.5),
                    'h': rng.uniform(1.55, 1.85),
                    'col': rng.choice(ped_cols)})

        if self.theme == 'forest':
            for side in (-1, 1):
                z = -9.0
                while z < self.finish_z + 62:
                    h = rng.uniform(4.0, 9.0)
                    self.trees.append({
                        'side': side, 'z': z,
                        'x': side * rng.uniform(6.4, 17.5),
                        'h': h, 'kind': 0 if rng.random() < 0.62 else 1,
                        'ph': rng.uniform(0, 6.28),
                        'tone': rng.uniform(0.0, 1.0)})
                    z += rng.uniform(3.4, 6.8)
            self.trees.sort(key=lambda t: -t['z'])
            for _ in range(90):
                self.bushes.append({'x': rng.choice((-1, 1))
                                    * rng.uniform(7.6, 19.0),
                                    'z': rng.uniform(-6.0, self.finish_z + 50),
                                    'r': rng.uniform(0.25, 0.9),
                                    'tone': rng.uniform(0.0, 1.0)})
            for _ in range(46):
                self.flies.append({'x': rng.uniform(-14.0, 14.0),
                                   'z': rng.uniform(4.0, self.finish_z + 30),
                                   'h': rng.uniform(0.25, 2.4),
                                   'ph': rng.uniform(0, 6.28)})
            for _ in range(7):
                self.birds.append({'x': rng.uniform(0.0, 1.0),
                                   'y': rng.uniform(0.06, 0.34),
                                   'v': rng.uniform(1.1, 2.4),
                                   'ph': rng.uniform(0, 6.28)})
            leaf_cols = ((206, 170, 74), (188, 122, 54), (150, 178, 74),
                         (214, 198, 122), (170, 96, 60))
            for _ in range(34):
                self.leaves.append({'x': rng.uniform(-10.0, 10.0),
                                    'z': rng.uniform(0.0, 74.0),
                                    'ph': rng.uniform(0, 6.28),
                                    'sp': rng.uniform(0.7, 1.5),
                                    'col': rng.choice(leaf_cols)})
            for _ in range(220):
                side = rng.choice((-1, 1))
                self.grass.append({'x': side * rng.uniform(5.35, 7.7),
                                   'z': rng.uniform(-4.0, self.finish_z + 34),
                                   'ph': rng.uniform(0, 6.28),
                                   'h': rng.uniform(0.20, 0.36),
                                   'tone': rng.uniform(0.0, 1.0)})
            for _ in range(14):
                side = rng.choice((-1, 1))
                self.rocks.append({'x': side * rng.uniform(5.6, 7.4),
                                   'z': rng.uniform(-2.0, self.finish_z + 30),
                                   'r': rng.uniform(0.16, 0.42),
                                   'tone': rng.uniform(0.0, 1.0)})
            for _ in range(26):
                side = rng.choice((-1, 1))
                self.mist.append({'x': side * rng.uniform(8.5, 24.0),
                                  'z': rng.uniform(0.0, self.finish_z + 40),
                                  'r': rng.uniform(2.4, 5.2),
                                  'ph': rng.uniform(0, 6.28)})
            for _ in range(7):
                self.dapple.append({'x': rng.uniform(-4.0, 4.0),
                                    'z': rng.uniform(6.0, self.finish_z - 4),
                                    'r': rng.uniform(1.0, 1.8),
                                    'ph': rng.uniform(0, 6.28)})

        if self.theme == 'canyon':
            z0 = -14.0
            while z0 < self.finish_z + 58.0:
                x0 = -9.5
                while x0 < 9.5:
                    w = rng.uniform(2.6, 4.4)
                    d = rng.uniform(2.4, 4.0)
                    pts = []
                    ph = rng.uniform(0, 6.28)
                    for s in range(5):
                        ang = 2 * math.pi * s / 5 + ph
                        rr = rng.uniform(0.42, 0.58)
                        pts.append((math.cos(ang) * w * rr,
                                    math.sin(ang) * d * rr))
                    self.slabs.append({
                        'x': x0 + w * 0.5, 'z': z0 + d * 0.5, 'pts': pts,
                        'tone': rng.uniform(0.0, 1.0)})
                    x0 += w + rng.uniform(0.2, 0.55)
                z0 += rng.uniform(3.2, 4.2)
            for _ in range(14):
                side = rng.choice((-1, 1))
                self.isles.append({
                    'x': side * rng.uniform(8.9, 10.6),
                    'y': rng.uniform(3.0, 4.6),
                    'z': rng.uniform(12.0, self.finish_z + 46.0),
                    'r': rng.uniform(0.5, 1.1),
                    'ph': rng.uniform(0, 6.28),
                    'tone': rng.uniform(0.0, 1.0)})
            for _ in range(5):
                self.isles.append({
                    'x': rng.uniform(-3.0, 3.0),
                    'y': rng.uniform(5.2, 6.6),
                    'z': rng.uniform(18.0, self.finish_z + 20.0),
                    'r': rng.uniform(0.55, 1.0),
                    'ph': rng.uniform(0, 6.28),
                    'tone': rng.uniform(0.0, 1.0)})
            self.isles.sort(key=lambda i: -i['z'])
            for _ in range(30):
                self.rocks.append({'x': rng.choice((-1, 1))
                                   * rng.uniform(9.4, 13.5),
                                   'z': rng.uniform(-4.0, self.finish_z + 60),
                                   'r': rng.uniform(0.20, 0.55),
                                   'tone': rng.uniform(0.0, 1.0)})

    def spawn_course(self):
        rng = self.rng
        xr, yr = self.sec['xr'], self.sec['yr']
        z = 0.0
        for i in range(self.sec['cores']):
            z += self.sec['gap'] + rng.uniform(-2.0, 5.0)
            if i == 0:
                cx, cy = rng.uniform(-0.7, 0.7), 1.0 + rng.uniform(-0.3, 0.3)
            else:
                prev = self.cores[-1]
                cx = clamp(prev['x'] + rng.uniform(-1.9, 1.9), -xr, xr)
                cy = clamp(prev['y'] + rng.uniform(-0.9, 0.9),
                           0.05 - yr * 0.2, 2.35)
            self.cores.append({'x': cx, 'y': cy, 'z': z, 'done': False,
                               'got': False})
        self.finish_z = z + 20.0

        # mines sit between cores and are pushed off the core line
        tries = 0
        while len(self.mines) < self.sec['mines'] and tries < 400:
            tries += 1
            mz = rng.uniform(14.0, self.finish_z - 8.0)
            mx = rng.uniform(-xr - 0.5, xr + 0.5)
            my = rng.uniform(0.05, 2.35)
            if min(abs(c['z'] - mz) for c in self.cores) < 4.0:
                continue
            if abs(mx) < 1.0 and abs(my - 1.0) < 0.6:
                mx += 1.4 if mx >= 0 else -1.4
            self.mines.append({'x': mx, 'y': my, 'z': mz,
                               'amp': rng.uniform(0.30, 0.85),
                               'sp': rng.uniform(0.65, 1.35),
                               'ph': rng.uniform(0, 2 * math.pi),
                               'tilt': rng.uniform(0, 2 * math.pi),
                               'near': False, 'done': False})

        for _ in range(self.sec['pads']):
            pz = rng.uniform(16.0, self.finish_z - 10.0)
            px = rng.uniform(-2.7, 2.7)
            self.pads.append({'x': px, 'z': pz, 'done': False})

    def total_cores(self):
        return len(self.cores)

    def next_core(self):
        for c in self.cores:
            if not c['done']:
                return c
        return None

    def mine_pos(self, m):
        return (m['x'] + m['amp'] * math.sin(self.t * m['sp'] + m['ph']),
                m['y'] + 0.12 * math.sin(self.t * m['sp'] * 1.7 + m['ph']))

    def _traffic(self, dt):
        for c in self.mv_cars:
            c['z'] += c['own'] * dt
            rel = c['z'] - self.z
            if rel < -7.0:
                c['z'] += 104.0
            elif rel > 97.0:
                c['z'] -= 104.0

    # ---------- input ----------
    def handle(self, e):
        if e.type == pygame.KEYUP:
            self.held.discard(e.key)
            return
        if e.type == pygame.WINDOWFOCUSLOST:
            self.held.clear()
            return
        if e.type == pygame.KEYDOWN:
            if self.paused:
                if e.key == pygame.K_ESCAPE:
                    self.paused = False
                    audio.play('click')
                elif e.key == pygame.K_m:
                    self.toggle_mute()
                return
            if e.key == pygame.K_ESCAPE:
                if self.mode in ('run', 'intro'):
                    self.paused = True
                    self.pause_t = 0.0
                    self.held.clear()
                    audio.play('click')
                else:
                    self.abort()
                return
            if e.key == pygame.K_m:
                self.toggle_mute()
                return
            if self.mode == 'result' and e.key in (pygame.K_r, pygame.K_RETURN):
                audio.play('select')
                self.app.set_scene('flight')
                return
            if (self.mode == 'result' and e.key == pygame.K_n
                    and self.next_ready()):
                self.go_next()
                return

        if e.type != pygame.MOUSEBUTTONDOWN or e.button != 1:
            return
        if self.paused:
            if self.resume_btn.hit(e.pos):
                self.paused = False
                audio.play('click')
            elif self.abort_btn.hit(e.pos):
                self.abort()
            elif self.mute_btn.hit(e.pos):
                self.toggle_mute()
            return
        if self.mode == 'result':
            if self.again_btn.hit(e.pos):
                audio.play('select')
                self.app.set_scene('flight')
            elif self.next_ready() and self.next_btn.hit(e.pos):
                self.go_next()
            elif self.home_btn.hit(e.pos):
                audio.play('click')
                self.app.set_scene('hangar')

    def abort(self):
        audio.play('click')
        self.app.toast('RUN ABORTED', 'NO CREDITS EARNED', RED)
        self.app.set_scene('hangar')

    def toggle_mute(self):
        on = not self.app.toggle_mute()
        self.app.toast('SOUND ON' if on else 'SOUND OFF',
                       'PRESS M TO TOGGLE', GOLD if on else DIM)

    def next_ready(self):
        if self.unlocked_now is None:
            return False
        st = self.app.state
        nxt = self.unlocked_now
        return (nxt in st['unlocked']
                or st['credits'] >= SECTORS[nxt]['price'])

    def go_next(self):
        nxt = self.unlocked_now
        if nxt is None:
            return
        st = self.app.state
        sec = SECTORS[nxt]
        if nxt not in st['unlocked']:
            if st['credits'] < sec['price']:
                audio.play('error')
                self.app.toast('NOT ENOUGH CREDITS', 'NEED {:,} MORE'.format(
                    sec['price'] - st['credits']), RED)
                return
            st['credits'] -= sec['price']
            st['unlocked'].append(nxt)
        st['sector'] = nxt
        self.app.save()
        audio.play('buy')
        self.app.set_scene('flight')

    def add_popup(self, x, y, z, label, sub, col):
        self.popups.append({'x': x, 'y': y, 'z': z, 'text': label,
                            'sub': sub, 'age': 0.0, 'col': col})

    # ---------- simulation ----------
    def update(self, dt):
        if self.paused:
            self.pause_t = min(1.0, self.pause_t + dt * 7.0)
            return
        self.pause_t = max(0.0, self.pause_t - dt * 7.0)
        self.frame_dt = dt
        self.t += dt
        self._traffic(dt)
        self.miss_t = max(0.0, self.miss_t - dt)
        self.pad_fx = max(0.0, self.pad_fx - dt * 2.2)
        for p in self.popups:
            p['age'] += dt
        self.popups = [p for p in self.popups if p['age'] < 1.4]
        for p in self.trail:
            p['age'] += dt
        self.trail = [p for p in self.trail if p['age'] < 0.7]

        if self.mode == 'intro':
            self.intro_t += dt
            self.x *= 0.9
            if self.intro_t > 1.35:
                self.mode = 'run'
            return

        if self.mode == 'crash':
            self.crash_t += dt
            self.update_debris(dt)
            self.speed *= max(0.0, 1.0 - dt * 2.6)
            self.boost_fx = max(0.0, self.boost_fx - dt * 3.0)
            self.shake = max(0.0, self.shake - dt * 1.15)
            self.flash = max(0.0, self.flash - dt * 6.5)
            if self.crash_t > 2.4:
                self.finish(crashed=True)
            return

        if self.mode == 'outro':
            self.outro_t += dt
            self.speed += (self.stats['top'] * 0.9 - self.speed) * min(1, dt * 2)
            self.z += self.speed * dt
            if self.outro_t > 1.5:
                self.finish()
            return

        if self.mode == 'result':
            self.result_t += dt
            if self.crashed:
                self.update_debris(dt)
                self.flash = max(0.0, self.flash - dt * 3.4)
            return

        self.time += dt
        if self.fault and not self.fault_done and self.time >= self.fault_t:
            self.fault_done = True
            kind = self.fault[0]
            self.add_popup(self.x, self.y + 0.4, self.z, kind,
                           'STRUCTURAL FAILURE', RED)
            self.crash(kind, boom=1.5 if kind == 'BLADE CLASH' else 1.3)
            return

        ax = ay = 0.0
        boosting = self.energy > 34

        ng = self.next_core()
        if ng:
            lead = clamp(0.55 + (ng['z'] - self.z) * 0.02, 0.55, 1.0)
            ax = clamp((ng['x'] - self.x) * lead * 0.95, -1, 1)
            ay = clamp((ng['y'] - self.y) * lead * 0.85, -1, 1)
            for m in self.mines:
                dz = m['z'] - self.z
                if m['done'] or dz <= 0.2 or dz > 8.0:
                    continue
                mx, my = self.mine_pos(m)
                dx, dy = self.x - mx, self.y - my
                d = math.hypot(dx, dy) + 1e-3
                if d < 2.1:
                    push = (2.1 - d) / 2.1 * clamp((8.0 - dz) / 8.0)
                    ax = clamp(ax + dx / d * push * 2.6, -1, 1)
                    ay = clamp(ay + dy / d * push * 2.6, -1, 1)
        else:
            ax = clamp(-self.x * 0.6, -1, 1)
            ay = clamp((1.0 - self.y) * 0.6, -1, 1)

        # sector challenge: steady crosswind plus turbulence, and the build's
        # own trim bias. A clean airframe fights it on its own.
        wind = self.sec.get('wind', 0.0)
        turb = self.sec.get('turb', 0.0)
        ax = clamp(ax + wind * 0.10 * math.sin(self.z * 0.055 + self.t * 0.8)
                   + turb * 0.42 * math.sin(self.t * 1.85 + self.z * 0.05)
                   + self.stats['bias_x'] * 0.9, -1.35, 1.35)
        ay = clamp(ay + turb * 0.34 * math.sin(self.t * 2.35 + self.z * 0.07 + 1.3)
                   + self.stats['bias_y'] * 0.9, -1.35, 1.35)
        risk = self.stats.get('risk', 0.0)
        if risk > 0.0:
            ax = clamp(ax + risk * 0.22 * math.sin(self.t * 2.1 + 0.7),
                       -1.4, 1.4)
            ay = clamp(ay + risk * 0.16 * math.sin(self.t * 2.7), -1.4, 1.4)

        if boosting:
            self.energy = max(0.0, self.energy - 27 * dt)
            self.boost_fx = min(1.0, self.boost_fx + dt * 5)
        else:
            self.energy = min(self.max_energy, self.energy + 9 * dt)
            self.boost_fx = max(0.0, self.boost_fx - dt * 4)

        target = self.stats['top'] * (0.70 + 0.30 * min(1.0, self.time / 2.4))
        if boosting:
            target *= 1.32
        if self.pad_fx > 0.0:
            target *= 1.0 + 0.30 * self.pad_fx
        target *= 1.0 - 0.12 * risk
        self.speed += (target - self.speed) * min(1.0, dt * 1.9)
        self.z += self.speed * dt

        lat = 3.2 + self.stats['agility'] * 0.050
        ver = 2.6 + self.stats['agility'] * 0.036
        self.vx += (ax * lat - self.vx) * min(1.0, dt * 7.0)
        self.vy += (ay * ver - self.vy) * min(1.0, dt * 7.0)
        self.x = clamp(self.x + self.vx * dt, -3.5, 3.5)
        self.y = clamp(self.y + self.vy * dt, -1.0, 2.6)
        if self.y <= -0.995:
            self.crash('GROUND IMPACT')
            return

        # street level: a low pass through the moving lanes can clip a car
        if self.theme == 'street' and self.y < 0.02:
            for c in self.mv_cars:
                if (abs(c['z'] - self.z) < c['ln'] * 0.5 + 0.9
                        and abs(c['x'] - self.x) < 1.25):
                    self.crash('CAR STRIKE', boom=2.0)
                    return

        if self.boost_fx > 0.12:
            self.spawn_trail()

        # energy cores: magnet, collect, miss
        for c in self.cores:
            if c['done']:
                continue
            dz = c['z'] - self.z
            if -0.4 < dz < 2.2:
                dx, dy = self.x - c['x'], self.y - c['y']
                d = math.hypot(dx, dy)
                if d < CORE_PULL:
                    k2 = min(1.0, dt * 6.0)
                    c['x'] += dx * k2 * 0.9
                    c['y'] += dy * k2 * 0.9
            if self.z < c['z']:
                continue
            c['done'] = True
            d = math.hypot(self.x - c['x'], self.y - c['y'])
            if d <= CORE_COLLECT:
                c['got'] = True
                self.hits += 1
                self.core_i = min(self.total_cores(), self.core_i + 1)
                self.streak += 1
                self.combo = min(2.0, 1.0 + self.streak * 0.08)
                near = 1.0 - d / CORE_COLLECT
                pts = int((110 + 70 * near) * self.combo)
                self.score += pts
                self.energy = min(self.max_energy, self.energy + 8)
                audio.play('core_hi' if self.streak >= 4 else 'core',
                           0.70 + 0.05 * min(5, self.streak))
                self.add_popup(c['x'], c['y'], c['z'],
                               '+{}'.format(pts),
                               'PERFECT' if near > 0.55 else 'CORE', GOLD)
            else:
                self.streak = 0
                self.combo = 1.0
                self.core_i = min(self.total_cores(), self.core_i + 1)
                self.miss_t = 1.0
                audio.play('miss', 0.6)
                self.add_popup(c['x'], c['y'], c['z'], 'MISSED', '', RED)

        # mines: hit or clean dodge
        for m in self.mines:
            if m['done']:
                continue
            dz = m['z'] - self.z
            if dz < -1.6:
                m['done'] = True
                continue
            if dz > 1.4:
                continue
            mx, my = self.mine_pos(m)
            d = math.hypot(self.x - mx, self.y - my)
            if d <= MINE_HIT:
                self.crash('MINE STRIKE')
                return
            if d <= MINE_NEAR and not m['near']:
                m['near'] = True
                self.dodges += 1
                pts = int(45 * self.combo)
                self.score += pts
                self.energy = min(self.max_energy, self.energy + 4)
                audio.play('near', 0.8)
                self.add_popup(mx, my + 0.5, m['z'], '+{}'.format(pts),
                               'NEAR MISS', CYAN)

        # boost pads
        for p in self.pads:
            if p['done']:
                continue
            dz = p['z'] - self.z
            if dz < -1.8:
                p['done'] = True
                continue
            if dz > 1.8:
                continue
            if abs(self.x - p['x']) <= PAD_HIT and self.y < 0.25:
                p['done'] = True
                self.energy = min(self.max_energy, self.energy + 26)
                self.pad_fx = 1.0
                audio.play('boost', 0.75)
                self.add_popup(p['x'], 0.4, p['z'], 'TURBO', 'ENERGY +26', TEAL)

        if self.z >= self.finish_z:
            self.mode = 'outro'
            self.outro_t = 0.0
        elif self.time > 90.0:
            self.mode = 'outro'
            self.outro_t = 0.0

    def spawn_trail(self):
        if int(self.t * 60.0) % 2:
            return
        for s in (1, -1):
            self.trail.append({'x': self.x + s * 0.32,
                               'y': self.y - 0.03,
                               'z': self.z - 0.95,
                               'age': 0.0})

    def ship_tilt(self):
        s = self.stats
        bank = clamp(-self.vx * 0.10 + s['cog_x'] * 0.45, -0.26, 0.26)
        pitch = (-0.075 - self.vy * 0.035
                 + 0.02 * math.sin(self.t * 2.4) + 0.02 * self.boost_fx
                 + clamp(s['cog_z'] * 0.35, -0.09, 0.09))
        return (pitch, bank)

    def crash(self, reason, boom=1.0):
        if self.mode != 'run':
            return
        self.mode = 'crash'
        self.crashed = True
        self.crash_reason = reason
        self.crash_t = 0.0
        self.boom = boom
        self.shake = min(1.35, boom)
        self.flash = min(1.25, boom)
        audio.play('crash', min(1.0, 0.78 * boom))
        rng = self.rng
        tilt = self.ship_tilt()
        self.debris = []
        for p in self.parts:
            c = p['ctr']
            rc = _rot(tilt, c)
            dx, dz = c[0], c[2]
            ln = math.hypot(dx, dz)
            if ln < 0.2:
                a = rng.uniform(0, 2 * math.pi)
                dx, dz, ln = math.cos(a), math.sin(a), 1.0
            dx, dz = dx / ln, dz / ln
            sp = rng.uniform(1.1, 3.6)
            self.debris.append({
                'p': p, 'c': c,
                'pos': [self.x + rc[0], self.y + rc[1], self.z + rc[2]],
                'vel': [dx * sp * 0.55 + self.vx * 0.30,
                        rng.uniform(1.4, 3.0),
                        dz * sp * 0.30 - self.speed * rng.uniform(0.010, 0.028)],
                'tilt': [tilt[0] + rng.uniform(-0.15, 0.15),
                         tilt[1] + rng.uniform(-0.15, 0.15)],
                'avel': [rng.uniform(-8.0, 8.0), rng.uniform(-8.0, 8.0)],
                'spin': rng.uniform(10.0, 26.0),
            })
        self.sparks = []
        for _ in range(int(30 * boom)):
            a = rng.uniform(0, 2 * math.pi)
            sp = rng.uniform(2.0, 8.0) * (0.82 + 0.30 * boom)
            self.sparks.append({
                'pos': [self.x, self.y, self.z],
                'vel': [math.cos(a) * sp, rng.uniform(-1.0, 6.0) * boom,
                        math.sin(a) * sp],
                'life': rng.uniform(0.45, 1.5) * (0.8 + 0.3 * boom),
                'col': ((255, 172, 92) if rng.random() < 0.72
                        else (255, 92, 64) if rng.random() < 0.6 else TEAL),
            })
        self.fire = []
        for _ in range(int(9 * boom)):
            self.fire.append({
                'pos': [self.x + rng.uniform(-0.42, 0.42),
                        self.y + rng.uniform(-0.15, 0.5),
                        self.z + rng.uniform(-0.42, 0.42)],
                'vel': [rng.uniform(-0.7, 0.7), rng.uniform(0.5, 2.2),
                        rng.uniform(-0.7, 0.7)],
                'age': 0.0, 'life': rng.uniform(0.7, 1.5) * (0.85 + 0.2 * boom),
                'size': rng.uniform(0.35, 0.85) * (0.70 + 0.40 * boom),
            })

    def update_debris(self, dt):
        for d in self.debris:
            v = d['vel']
            v[1] -= 8.5 * dt
            pos = d['pos']
            pos[0] += v[0] * dt
            pos[1] += v[1] * dt
            pos[2] += v[2] * dt
            if pos[1] < FLOOR_Y + 0.22:
                pos[1] = FLOOR_Y + 0.22
                v[1] = -v[1] * 0.34 if v[1] < -0.5 else 0.0
                v[0] *= 0.78
                v[2] *= 0.78
                d['avel'][0] *= 0.82
                d['avel'][1] *= 0.82
            d['tilt'][0] += d['avel'][0] * dt
            d['tilt'][1] += d['avel'][1] * dt
        for s in self.sparks:
            s['life'] -= dt
            s['vel'][1] -= 9.0 * dt
            for i in range(3):
                s['pos'][i] += s['vel'][i] * dt
        self.sparks = [s for s in self.sparks if s['life'] > 0]
        for f in self.fire:
            f['age'] += dt
            f['vel'][1] += 0.9 * dt
            for i in range(3):
                f['pos'][i] += f['vel'][i] * dt
            f['vel'][0] *= max(0.0, 1.0 - dt * 1.2)
            f['vel'][2] *= max(0.0, 1.0 - dt * 1.2)
        self.fire = [f for f in self.fire if f['age'] < f['life']]

    def finish(self, crashed=False):
        if self.mode == 'result':
            return
        self.held.clear()
        self.mode = 'result'
        self.result_t = 0.0
        n = max(1, self.total_cores())
        st = self.app.state
        if crashed:
            self.grade = 'F'
            self.reward = int(round(self.score * 0.03 * self.sec['reward']))
            if self.score > 0:
                self.reward = max(5, self.reward)
            self.best = int(st['best'].get(str(self.sector_i), self.score))
        else:
            ratio = self.hits / n
            if ratio >= 0.95:
                self.grade = 'S'
            elif ratio >= 0.80:
                self.grade = 'A'
            elif ratio >= 0.60:
                self.grade = 'B'
            else:
                self.grade = 'C'
            self.reward = int(round(self.score * 0.09 * self.sec['reward']))
            if self.hits >= n * 0.8:
                self.reward += 100
            self.reward = max(20, self.reward)
            key = str(self.sector_i)
            if self.score > int(st['best'].get(key, 0)):
                st['best'][key] = int(self.score)
                self.new_best = True
            self.best = int(st['best'].get(key, self.score))
            if ratio >= CLEAR_RATIO:
                self.cleared_now = True
                cleared = st.setdefault('cleared', {})
                prev = cleared.get(key)
                if prev is None or (GRADE_ORDER.index(self.grade)
                                    > GRADE_ORDER.index(prev)):
                    cleared[key] = self.grade
                nxt = self.sector_i + 1
                if nxt < len(SECTORS) and nxt not in st['unlocked']:
                    self.unlocked_now = nxt
                if all(str(i) in cleared for i in range(len(SECTORS))):
                    self.campaign_done = True
                    if not st.get('finished'):
                        st['finished'] = True
                        self.campaign_bonus = CAMPAIGN_BONUS
                        self.reward += CAMPAIGN_BONUS
            audio.play('complete', 0.8)
        st['credits'] += self.reward
        self.app.save()

    # ---------- render ----------
    def camera(self):
        sh = self.shake * self.shake
        sx = math.sin(self.t * 71.0) * 16.0 * sh
        sy = math.cos(self.t * 53.0) * 12.0 * sh
        pitch = -0.160 - self.vy * 0.008 + math.sin(self.t * 61.0) * 0.035 * sh
        scale = 150.0
        cy = SH * 0.615 + sy
        if self.crashed:
            k = clamp(self.crash_t / 0.55)
            pitch -= 0.085 * k
            scale -= 34.0 * k
            cy -= 20.0 * k
        cam = make_cam(math.pi + self.vx * 0.018, pitch,
                       -self.vx * 0.045 + math.sin(self.t * 47.0) * 0.06 * sh,
                       scale, SW * 0.50 + sx, cy,
                       (self.camx, self.camy, self.z))
        return cam

    def base_sky(self):
        if self.theme == 'canyon':
            self.buf.blit(sky_surface(self.top_col, self.bot_col, True), (0, 0))
        else:
            self.buf.blit(_sky_grad(self.sky_stops), (0, 0))

    def _fog(self, col, dep):
        k = clamp((dep - 14.0) / 130.0)
        return mix(col, self.fog_col, 1.0 - 0.74 * k)

    def _quad(self, cam, pts):
        out = []
        for p in pts:
            q, _ = cam_proj(cam, p)
            if q is None:
                return None
            out.append(q)
        return out

    def draw_clouds(self, cam):
        if self.theme == 'canyon':
            return
        shade_c = mix((178, 142, 168), self.fog_col, 0.22)
        body_c = (255, 248, 236)
        rim_c = (255, 228, 186)
        puffs = ((-0.33, 0.20, 0.44), (-0.12, 0.27, 0.78),
                 (0.10, 0.24, 0.62), (0.30, 0.18, 0.36),
                 (0.00, 0.31, 0.52))
        for c in self.clouds:
            x = (c['x'] + self.t * 0.006 * c['v']) % 1.4 - 0.2
            cx = x * SW
            base = c['y'] * SH * 0.86 + c['h'] * 1.1
            w = c['w'] * (0.9 + 0.35 * c['k'])
            h = c['h'] * (1.5 + 0.7 * c['k'])
            for ox, rx, ry in puffs:
                pygame.draw.polygon(
                    self.buf, shade_c,
                    _dome(cx + ox * w, base + h * 0.20, rx * w * 1.02,
                          ry * h * 1.05))
            for ox, rx, ry in puffs:
                pygame.draw.polygon(
                    self.buf, body_c,
                    _dome(cx + ox * w, base, rx * w, ry * h))
            fill_alpha_poly(self.buf,
                            _ell(cx, base - h * 0.06, w * 0.44, h * 0.22, 14),
                            shade_c, 0.5)
            for ox, rx, ry in puffs[1:3]:
                pygame.draw.polygon(
                    self.buf, rim_c,
                    _dome(cx + ox * w - w * 0.05, base - h * 0.16,
                          rx * w * 0.62, ry * h * 0.5))
            pygame.draw.line(self.buf, mix(shade_c, WHITE, 0.55),
                             (cx - w * 0.50, base), (cx + w * 0.48, base), 1)

    def draw_sky_fx(self, cam):
        if self.theme == 'canyon':
            q, dep = cam_proj(cam, (-30.0, 7.0, self.z + 160.0))
            if q is not None:
                x, y = q
                draw_glow(self.buf, x, y, 360, (255, 186, 112), 0.30)
                draw_glow(self.buf, x, y, 150, (255, 224, 178), 0.34)
            hz, _ = cam_proj(cam, (0.0, 1.6, self.z + 160.0))
            if hz is not None:
                draw_glow(self.buf, SW * 0.5, hz[1], 520, self.sec['line'], 0.10)
            # ringed planet low on the horizon
            pc, _ = cam_proj(cam, (30.0, 10.5, self.z + 320.0))
            pe, _ = cam_proj(cam, (30.0 + 2.2, 10.5, self.z + 320.0))
            if pc is not None and pe is not None:
                px, py = pc
                pr = max(16.0, abs(pe[0] - px))
                body = mix((108, 124, 152), self.top_col, 0.74)
                pygame.draw.polygon(self.buf, body, _ell(px, py, pr, pr, 26))
                fill_alpha_poly(self.buf, _ell(px - pr * 0.34, py - pr * 0.22,
                                               pr * 0.92, pr * 0.90, 26),
                                (10, 16, 30), 0.62)
                fill_alpha_poly(self.buf, _ell(px + pr * 0.46, py - pr * 0.06,
                                               pr * 0.36, pr * 0.74, 16),
                                (255, 214, 162), 0.18)
                fill_alpha_poly(self.buf,
                                _ell(px, py + pr * 0.26, pr * 0.94,
                                     pr * 0.10, 18),
                                (150, 166, 192), 0.14)
                fill_alpha_poly(self.buf, _ell(px, py, pr * 1.05, pr * 1.05, 26),
                                (140, 206, 212), 0.05)
            return
        q, dep = cam_proj(cam, (-19.0, 8.6, self.z + 172.0))
        self.sun_xy = q
        if q is not None:
            draw_glow(self.buf, q[0], q[1], 300, (255, 246, 214), 0.30)
            draw_glow(self.buf, q[0], q[1], 90, (255, 255, 248), 0.55)
        hz, _ = cam_proj(cam, (0.0, 1.0, self.z + 168.0))
        if hz is not None:
            draw_glow(self.buf, SW * 0.5, hz[1], 460, (255, 238, 208), 0.18)
            draw_glow(self.buf, SW * 0.5, hz[1], 190, (255, 250, 235), 0.14)

    def draw_skyline(self, cam):
        hz, _ = cam_proj(cam, (0.0, 0.0, self.z + 166.0))
        if hz is None:
            return
        floor = hz[1] + 2
        for li, (dist, amp, tone) in enumerate(((86.0, 0.8, 0.86),
                                                (128.0, 1.5, 0.55),
                                                (176.0, 2.4, 0.28))):
            zf = self.z + dist
            col = mix(mix((74, 62, 118), self.fog_col, 0.86),
                      self.fog_col, tone)
            i = -15
            while i <= 15:
                bw = 2.2 + 1.6 * abs(math.sin(i * 2.13 + li * 4.1
                                             + zf * 0.011))
                h = amp * (1.0 + 1.6 * abs(math.sin(i * 1.71 + li * 2.3)))
                q = self._quad(cam, ((i * 2.2, FLOOR_Y, zf),
                                     (i * 2.2 + bw, FLOOR_Y, zf),
                                     (i * 2.2 + bw, FLOOR_Y + h, zf),
                                     (i * 2.2, FLOOR_Y + h, zf)))
                if q is not None:
                    pygame.draw.polygon(self.buf, col, q)
                    top = min(q[2][1], q[3][1])
                    if top < floor:
                        pygame.draw.line(self.buf, mix(col, WHITE, 0.82),
                                         q[3], q[2], 1)
                i += bw * 0.85 + 1.0

    def draw_ground(self, cam):
        zc = self.z
        if self.theme == 'street':
            wide, road = (150, 132, 140), (50, 54, 70)
            edge = 6.4
        else:
            wide, road = (74, 128, 66), (168, 132, 88)
            edge = 5.2
        bands = ((-8.0, 12.0, 0.95), (12.0, 26.0, 0.90), (26.0, 38.0, 0.855),
                 (38.0, 50.0, 0.81), (50.0, 64.0, 0.765), (64.0, 78.0, 0.72),
                 (78.0, 94.0, 0.675), (94.0, 112.0, 0.63),
                 (112.0, 132.0, 0.585), (132.0, 156.0, 0.54),
                 (156.0, 184.0, 0.49), (184.0, 216.0, 0.44),
                 (216.0, 244.0, 0.385), (244.0, 268.0, 0.33))
        for z0, z1, k in reversed(bands):
            z0, z1 = zc + z0, zc + z1
            c_all = mix(wide, self.fog_col, k)
            c_rd = mix(road, self.fog_col, k)
            self._ground_quad(cam, -120.0, -edge, z0, z1, c_all)
            self._ground_quad(cam, edge, 120.0, z0, z1, c_all)
            self._ground_quad(cam, -edge, edge, z0, z1, c_rd)
            if self.theme != 'street':
                c_sh = mix(mix(road, (96, 74, 54), 0.55), self.fog_col, k)
                c_gr = mix((56, 102, 52), self.fog_col, k)
                self._ground_quad(cam, -edge - 0.65, -edge, z0, z1, c_sh)
                self._ground_quad(cam, edge, edge + 0.65, z0, z1, c_sh)
                self._ground_quad(cam, -edge - 2.6, -edge - 0.65, z0, z1, c_gr)
                self._ground_quad(cam, edge + 0.65, edge + 2.6, z0, z1, c_gr)

    def _ground_quad(self, cam, x0, x1, z0, z1, col):
        q = _clip_project(cam, ((x0, FLOOR_Y, z0), (x1, FLOOR_Y, z0),
                                (x1, FLOOR_Y, z1), (x0, FLOOR_Y, z1)))
        if q is not None:
            pygame.draw.polygon(self.buf, col, q)

    def draw_shadows(self, cam):
        zc = self.z
        for b in self.blds:
            if b['side'] > 0:
                continue
            z0, z1 = b['z0'], b['z1']
            if z1 < zc - 10.0 or z0 > zc + 74.0:
                continue
            h = b['h']
            x0 = -b['x']
            push = 0.46 * h
            dz = -0.24 * h
            q = _clip_project(cam, ((x0, FLOOR_Y + 0.01, z0),
                                    (x0 + push, FLOOR_Y + 0.01, z0 + dz),
                                    (x0 + push, FLOOR_Y + 0.01, z1 + dz),
                                    (x0, FLOOR_Y + 0.01, z1)))
            if q is not None:
                base = mix((50, 54, 70), self.fog_col,
                           _ground_k(z0 - zc))
                pygame.draw.polygon(self.buf, mix((34, 26, 70), base, 0.66),
                                    q)

    def draw_city(self, cam):
        zc = self.z
        for b in self.blds:
            if b['z0'] > zc + 168.0 or b['z1'] < zc + 2.0:
                continue
            z0 = max(b['z0'], zc + 2.2)
            z1 = b['z1']
            side = b['side']
            x = side * b['x']
            xo = side * (b['x'] + b['d'])
            top = FLOOR_Y + b['h']
            dep = z0 - zc
            tone = b['tone']
            if side < 0:
                inner_c = mix(_mul(mix((178, 146, 150), (238, 212, 196),
                                       tone), 0.80), (58, 56, 112), 0.66)
                front_c = mix(_mul(mix((152, 124, 134), (212, 188, 176),
                                       tone), 0.76), (54, 52, 106), 0.66)
            else:
                inner_c = mix(_mul(mix((178, 146, 150), (238, 212, 196),
                                       tone), 0.98), (255, 208, 146), 0.52)
                front_c = mix(_mul(mix((152, 124, 134), (212, 188, 176),
                                       tone), 0.92), (255, 202, 140), 0.48)
            inner = self._fog(inner_c, dep)
            front = self._fog(front_c, dep)
            ink = self._fog((22, 16, 40), dep)
            warm = self._fog((255, 226, 176), dep)
            fq = self._quad(cam, ((x, FLOOR_Y, z0), (xo, FLOOR_Y, z0),
                                  (xo, top, z0), (x, top, z0)))
            iq = self._quad(cam, ((x, FLOOR_Y, z0), (x, FLOOR_Y, z1),
                                  (x, top, z1), (x, top, z0)))
            if iq is not None:
                pygame.draw.polygon(self.buf, inner, iq)
                pygame.draw.lines(self.buf, ink, True, iq,
                                  3 if dep < 16.0 else (2 if dep < 42.0 else 1))
            if fq is not None:
                pygame.draw.polygon(self.buf, front, fq)
                pygame.draw.line(self.buf, ink, fq[0], fq[1], 1)
                for fr in (0.34, 0.60, 0.84):
                    l0, _ = cam_proj(cam, (x, FLOOR_Y + b['h'] * fr, z0))
                    l1, _ = cam_proj(cam, (xo, FLOOR_Y + b['h'] * fr, z0))
                    if l0 is not None and l1 is not None:
                        pygame.draw.line(self.buf,
                                         mix(front, (58, 64, 74), 0.72),
                                         l0, l1, 1)
            if iq is None or dep > 92:
                continue
            pygame.draw.line(self.buf, warm, iq[3], iq[2],
                             2 if dep < 34.0 else 1)

            # window grid on the track-facing facade
            zlen = z1 - z0
            rows, cols = b['rows'], b['cols']
            for r in range(rows):
                for c in range(cols):
                    if not b['panes'][r][c]:
                        continue
                    step = (b['h'] - 2.4) / rows
                    ya = FLOOR_Y + 2.1 + r * step
                    yb = ya + step * 0.60
                    za = z0 + zlen * (c + 0.20) / cols
                    zb = min(z1, za + zlen * 0.60 / cols)
                    wq = self._quad(cam, ((x, ya, za), (x, yb, za),
                                          (x, yb, zb), (x, ya, zb)))
                    if wq is None:
                        continue
                    glass = ((92, 140, 196), (162, 190, 220),
                             (226, 226, 232), (124, 160, 208))[(r + c) % 4]
                    if side > 0:
                        glass = mix(glass, (255, 212, 154), 0.58)
                    else:
                        glass = mix(glass, (92, 80, 142), 0.34)
                    pygame.draw.polygon(self.buf, self._fog(glass, dep), wq)

            # storefront band at street level, split into individual shops
            shops = ((232, 198, 148), (198, 92, 74), (92, 146, 172),
                     (216, 178, 88), (126, 156, 124), (176, 120, 168))
            for c in range(cols):
                za = z0 + zlen * (c + 0.08) / cols
                zb = za + zlen * 0.84 / cols
                sc = b['neon_col'] if b['neon'] else \
                    shops[(c + int(b['tone'] * 5)) % len(shops)]
                sc = self._fog(mix(sc, (26, 22, 46), 0.74), dep)
                glass = self._fog(mix(sc, (22, 28, 38), 0.30), dep)
                for ya, yb, ccol in ((FLOOR_Y + 0.12, FLOOR_Y + 1.45, glass),
                                     (FLOOR_Y + 1.45, FLOOR_Y + 1.95, sc)):
                    sq = self._quad(cam, ((x, ya, za), (x, ya, zb),
                                          (x, yb, zb), (x, yb, za)))
                    if sq is None:
                        continue
                    pygame.draw.polygon(self.buf, ccol, sq)
                if c % 2 == 0:
                    a = clamp((92 - dep) / 60.0)
                    draw_glow(self.buf, sum(p[0] for p in sq) * 0.25,
                              sum(p[1] for p in sq) * 0.25, 26, sc,
                              0.16 * a)

            aq = self._quad(cam, ((x, FLOOR_Y, z0), (x, FLOOR_Y, z1),
                                  (x, FLOOR_Y + 0.85, z1),
                                  (x, FLOOR_Y + 0.85, z0)))
            if aq is not None:
                fill_alpha_poly(self.buf, aq, (16, 20, 28), 0.16)

            if b['neon']:
                nq = self._quad(cam, ((x, top - 1.6, z0 + zlen * 0.20),
                                      (x, top - 1.6, z0 + zlen * 0.80),
                                      (x, top - 0.35, z0 + zlen * 0.80),
                                      (x, top - 0.35, z0 + zlen * 0.20)))
                if nq is not None:
                    nc = self._fog(mix(b['neon_col'], (30, 34, 46), 0.85),
                                   dep)
                    pygame.draw.polygon(self.buf, nc, nq)
                    pygame.draw.lines(self.buf, self._fog(b['neon_col'], dep),
                                      True, nq, 1)
                    a = clamp((110 - dep) / 70.0)
                    draw_glow(self.buf, sum(p[0] for p in nq) * 0.25,
                              sum(p[1] for p in nq) * 0.25, 52,
                              b['neon_col'], 0.30 * a)

            if dep < 62.0 and b['h'] > 5.6:
                ax = x + side * b['d'] * 0.55
                amid = z0 + zlen * 0.5
                a0, _ = cam_proj(cam, (ax, top, amid))
                a1, _ = cam_proj(cam, (ax, top + 1.25, amid))
                if a0 is not None and a1 is not None:
                    pygame.draw.line(self.buf, self._fog((46, 52, 62), dep),
                                     a0, a1, 1)
                    if b['neon']:
                        bl = 0.5 + 0.5 * math.sin(self.t * 2.4 + b['z0'] * 0.7)
                        draw_glow(self.buf, a1[0], a1[1], 8, (255, 82, 74),
                                  0.38 * bl)

    def draw_lamps(self, cam):
        for k in self.lamps:
            dep = k - self.z
            if dep < 2.0 or dep > 130.0:
                continue
            a = clamp((130.0 - dep) / 80.0)
            for side in (-1, 1):
                x = side * 5.9
                p0, _ = cam_proj(cam, (x, FLOOR_Y, k))
                p1, _ = cam_proj(cam, (x, FLOOR_Y + 3.2, k))
                p2, _ = cam_proj(cam, (x - side * 1.6, FLOOR_Y + 3.2, k))
                if None in (p0, p1, p2):
                    continue
                pygame.draw.line(self.buf, self._fog((52, 58, 68), dep),
                                 p0, p1, 2)
                pygame.draw.line(self.buf, self._fog((58, 64, 74), dep),
                                 p1, p2, 2)
                draw_glow(self.buf, p2[0], p2[1], 18, (255, 238, 196),
                          0.55 * a)
                g, _ = cam_proj(cam, (x - side * 1.7, FLOOR_Y + 0.02, k))
                if g is not None:
                    draw_glow(self.buf, g[0], g[1], 58, (255, 226, 168),
                              0.22 * a)

    def draw_gantries(self, cam):
        for gz in self.gantries:
            dep = gz - self.z
            if dep < 2.0 or dep > 132.0:
                continue
            a = clamp((132.0 - dep) / 90.0)
            post = self._fog((64, 72, 84), dep)
            for p0, p1 in (((-6.1, FLOOR_Y, gz), (-6.1, 4.1, gz)),
                           ((6.1, FLOOR_Y, gz), (6.1, 4.1, gz)),
                           ((-6.1, 4.1, gz), (6.1, 4.1, gz)),
                           ((-6.1, 3.35, gz), (6.1, 3.35, gz))):
                q0, _ = cam_proj(cam, p0)
                q1, _ = cam_proj(cam, p1)
                if q0 is not None and q1 is not None:
                    pygame.draw.line(self.buf, post, q0, q1, 3)
            if dep < 16.0:
                continue
            bq = self._quad(cam, ((-4.6, 3.40, gz), (4.6, 3.40, gz),
                                  (4.6, 4.05, gz), (-4.6, 4.05, gz)))
            if bq is None:
                continue
            pygame.draw.polygon(self.buf, self._fog((26, 46, 80), dep), bq)
            pygame.draw.lines(self.buf, self._fog((228, 182, 92), dep),
                              True, bq, 1)
            cx = sum(p[0] for p in bq) * 0.25
            cy = sum(p[1] for p in bq) * 0.25
            size = 7 + int(6 * a)
            text(self.buf, cx, cy - size * 0.62, 'DIMA CIRCUIT', size,
                 'mono', mix(WHITE, self.fog_col, 1.0 - a), 'c', 2.0,
                 0.92 * a)

    def draw_hills(self, cam):
        hz, _ = cam_proj(cam, (0.0, 0.0, self.z + 166.0))
        if hz is None:
            return
        floor = hz[1] + 2
        for dist, amp, lift, tone in ((72.0, 1.7, 0.02, 0.82),
                                      (112.0, 3.6, 0.05, 0.52),
                                      (162.0, 6.2, 0.10, 0.24)):
            zf = self.z + dist
            top = []
            for i in range(-20, 21):
                x = i * 2.4
                h = (0.55 + 0.45 * math.sin(x * 0.23 + zf * 0.04)) * \
                    (0.60 + 0.40 * math.sin(x * 0.07 - zf * 0.021))
                p, _ = cam_proj(cam, (x, FLOOR_Y + h * amp + lift, zf))
                if p is not None:
                    top.append((p[0], min(p[1], floor - 1)))
            if len(top) < 3:
                continue
            col = mix(mix((44, 88, 80), self.fog_col, 0.88),
                      self.fog_col, tone)
            poly = [(SW * -0.3, floor), (SW * 1.3, floor)]
            poly += list(reversed(top))
            pygame.draw.polygon(self.buf, col, poly)

    def draw_trees(self, cam):
        zc = self.z
        for tr in self.trees:
            dep = tr['z'] - zc
            if dep < 7.2 or dep > 142.0:
                continue
            h = tr['h']
            wf = 0.88 + 0.30 * tr['tone']
            x = tr['x'] + math.sin(self.t * 1.15 + tr['ph']) * 0.035 * h
            f = 1350.0 / dep
            ink = self._fog((14, 20, 40), dep)
            inkw = 2 if dep < 34.0 else 1
            if dep < 82.0:
                c, _ = cam_proj(cam, (x - h * 0.10, FLOOR_Y + 0.01,
                                      tr['z'] - h * 0.12))
                if c is not None:
                    rx = min(172.0, h * 0.17 * f)
                    ry = rx * 0.20
                    if rx > 1.5:
                        base_c = ((168, 132, 88) if abs(x) < 5.6
                                  else (74, 128, 66))
                        base_c = mix(base_c, self.fog_col, _ground_k(dep))
                        pygame.draw.polygon(self.buf,
                                            mix((46, 50, 80), base_c, 0.30),
                                            _ell(c[0] - rx * 0.12, c[1],
                                                 rx * 1.02, ry * 1.10, 12))
                        pygame.draw.polygon(self.buf,
                                            mix((36, 40, 72), base_c, 0.50),
                                            _ell(c[0] - rx * 0.05, c[1],
                                                 rx * 0.74, ry * 0.80, 12))
            p0, _ = cam_proj(cam, (x, FLOOR_Y, tr['z']))
            p1, _ = cam_proj(cam, (x, FLOOR_Y + h * 0.50, tr['z']))
            if p0 is None or p1 is None:
                continue
            tw = max(1.0, 0.011 * h * f)
            trunk = self._fog((62, 46, 36), dep)
            trunk_l = self._fog((110, 82, 56), dep)
            pygame.draw.polygon(self.buf, trunk,
                                ((p0[0] - tw * 1.45, p0[1]),
                                 (p0[0] + tw * 1.45, p0[1]),
                                 (p1[0] + tw * 0.55, p1[1]),
                                 (p1[0] - tw * 0.55, p1[1])))
            pygame.draw.polygon(self.buf, trunk_l,
                                ((p0[0] + tw * 0.30, p0[1]),
                                 (p0[0] + tw * 1.45, p0[1]),
                                 (p1[0] + tw * 0.55, p1[1]),
                                 (p1[0] + tw * 0.20, p1[1])))
            if tr['kind'] == 0:
                col = mix((16, 54, 46), (58, 126, 86), tr['tone'])
                tiers = 4 if h > 5.6 else 3
                shL = self._fog(mix(col, (6, 26, 24), 0.50), dep)
                shR = self._fog(mix(col, (190, 222, 140), 0.70), dep)
                rim = self._fog(mix(shR, (255, 248, 206), 0.55), dep)
                shade_u = self._fog(mix(col, (8, 28, 22), 0.40), dep)
                for i in range(tiers):
                    cy = FLOOR_Y + h * (0.29 + 0.152 * i)
                    hw = h * (0.315 - 0.052 * i) * wf
                    th = h * 0.275
                    ql = self._quad(cam, ((x - hw, cy, tr['z']),
                                          (x, cy + th, tr['z']),
                                          (x, cy, tr['z'])))
                    qr = self._quad(cam, ((x, cy, tr['z']),
                                          (x, cy + th, tr['z']),
                                          (x + hw, cy, tr['z'])))
                    if ql is None or qr is None:
                        continue
                    pygame.draw.polygon(self.buf, shL, ql)
                    pygame.draw.polygon(self.buf, mix(shR, (255, 244, 208),
                                                      0.92 + 0.02 * i), qr)
                    if dep < 56.0:
                        jb = h * 0.034
                        ub = self._quad(cam, (
                            (x - hw, cy + jb * 0.25, tr['z']),
                            (x - hw * 0.55, cy - jb, tr['z']),
                            (x, cy + jb * 0.45, tr['z']),
                            (x + hw * 0.55, cy - jb, tr['z']),
                            (x + hw, cy + jb * 0.25, tr['z'])))
                        if ub is not None:
                            pygame.draw.polygon(self.buf, shade_u, ub)
                            if dep < 34.0:
                                pygame.draw.lines(self.buf, ink, False, ub, 1)
                    pygame.draw.lines(self.buf, ink, True,
                                      (ql[0], ql[1], qr[2]), inkw)
                    if dep < 60.0:
                        pygame.draw.line(self.buf, rim, qr[1], qr[2],
                                         max(1, int(0.035 * f)))
            else:
                col = mix((16, 54, 44), (74, 138, 62), tr['tone'])
                tip0, _ = cam_proj(cam, (x - h * 0.16, FLOOR_Y + h * 0.66,
                                         tr['z']))
                tip1, _ = cam_proj(cam, (x + h * 0.16, FLOOR_Y + h * 0.70,
                                         tr['z']))
                if tip0 is not None and tip1 is not None:
                    pygame.draw.line(self.buf, trunk, p1, tip0,
                                     max(1, int(tw * 0.9)))
                    pygame.draw.line(self.buf, trunk, p1, tip1,
                                     max(1, int(tw * 0.9)))
                uc, _ = cam_proj(cam, (x, FLOOR_Y + h * 0.70, tr['z']))
                if uc is not None and dep > 13.0:
                    urx = 0.235 * h * f * wf
                    if urx > 2.0:
                        pygame.draw.polygon(
                            self.buf,
                            self._fog(mix(col, (8, 32, 26), 0.46), dep),
                            _ell(uc[0], uc[1] + urx * 0.10,
                                 urx, urx * 0.36, 12))
                blobs = ((-0.20, 0.72, 0.235), (0.19, 0.74, 0.220),
                         (-0.01, 0.87, 0.190))
                clumps = []
                for bi, (ox, oy, rr) in enumerate(blobs):
                    c, _ = cam_proj(cam, (x + ox * h * wf,
                                          FLOOR_Y + oy * h, tr['z']))
                    if c is None:
                        continue
                    rad = rr * h * f
                    if rad >= 1.5:
                        clumps.append((c, rad, bi))
                for c, rad, bi in clumps:
                    pygame.draw.polygon(self.buf,
                                        self._fog(mix(col, (10, 36, 28),
                                                      0.50 - 0.02 * bi),
                                                  dep),
                                        _ell(c[0], c[1], rad, rad * 0.90, 12))
                if dep < 52.0:
                    for c, rad, bi in clumps:
                        mid = self._fog(mix(col, (176, 212, 114),
                                            0.74 - 0.02 * bi), dep)
                        pygame.draw.polygon(self.buf, mid,
                                            _ell(c[0] + rad * 0.08,
                                                 c[1] - rad * 0.12,
                                                 rad * 0.90, rad * 0.80, 12))
                        pygame.draw.polygon(self.buf,
                                            mix(mid, (240, 248, 180), 0.62),
                                            _ell(c[0] + rad * (0.20 + 0.06 * bi),
                                                 c[1] - rad * (0.30 + 0.05 * bi),
                                                 rad * 0.42, rad * 0.27, 10))
                if dep < 46.0:
                    for c, rad, bi in clumps:
                        if bi > 2:
                            continue
                        pygame.draw.lines(self.buf, ink, True,
                                          _ell(c[0], c[1], rad, rad * 0.90, 12),
                                          2 if dep < 16.0 else 1)
                if dep < 24.0:
                    for li in range(5):
                        ang = 0.8 + li * 1.35 + tr['ph']
                        lr = (0.20 + 0.06 * li) * h * f * wf
                        lx, ly = x, FLOOR_Y + h * (0.76 + 0.03 * li)
                        c, _ = cam_proj(cam, (lx + math.cos(ang) * lr * 0.9 / f,
                                              ly + math.sin(ang) * lr * 0.5 / f,
                                              tr['z'] - 0.05))
                        if c is None:
                            continue
                        tone_c = self._fog(mix(col, (86, 156, 70)
                                               if li % 2 else (10, 38, 30),
                                               0.45), dep)
                        pygame.draw.polygon(self.buf, tone_c,
                                            _ell(c[0], c[1], lr * 0.34,
                                                 lr * 0.26, 9))

    def draw_bushes(self, cam):
        for bu in self.bushes:
            dep = bu['z'] - self.z
            if dep < 1.5 or dep > 48.0:
                continue
            f = 1350.0 / dep
            rad = bu['r'] * f
            if rad < 1.5:
                continue
            x = bu['x'] + math.sin(self.t * 1.6 + bu['z']) * 0.04
            c, _ = cam_proj(cam, (x, FLOOR_Y + bu['r'] * 0.55, bu['z']))
            if c is None:
                continue
            col = mix((20, 60, 50), (86, 148, 74), bu['tone'])
            b0, _ = cam_proj(cam, (x, FLOOR_Y + 0.01, bu['z']))
            if b0 is not None:
                gbase = mix((74, 128, 66), self.fog_col, _ground_k(dep))
                pygame.draw.polygon(self.buf,
                                    mix((42, 46, 78), gbase, 0.34),
                                    _ell(b0[0] + rad * 0.10, b0[1],
                                         rad * 1.10, rad * 0.24, 10))
            ink = self._fog((14, 20, 40), dep)
            parts = ((-0.34, 0.26, 0.62), (0.02, 0.54, 0.84))
            for pi_, (ox, oy, rr) in enumerate(parts):
                c2, _ = cam_proj(cam, (x + ox * bu['r'],
                                       FLOOR_Y + oy * bu['r'], bu['z']))
                if c2 is None:
                    continue
                r2 = rr * rad
                if r2 < 1.5:
                    continue
                sh = self._fog(mix(col, (12, 40, 30), 0.52 + 0.06 * pi_), dep)
                pts = _ell(c2[0], c2[1] + r2 * 0.08, r2, r2 * 0.78, 10)
                pygame.draw.polygon(self.buf, sh, pts)
                if dep < 26.0:
                    pygame.draw.lines(self.buf, ink, True, pts, 1)
                pygame.draw.polygon(self.buf,
                                    mix(sh, (226, 242, 158), 0.78),
                                    _ell(c2[0] + r2 * 0.24,
                                         c2[1] - r2 * 0.36,
                                         r2 * 0.40, r2 * 0.24, 8))

    def draw_flies(self, cam):
        for fl in self.flies:
            dep = fl['z'] - self.z
            if dep < 1.5 or dep > 66.0:
                continue
            a = clamp((66.0 - dep) / 38.0)
            fx = fl['x'] + math.sin(self.t * 0.8 + fl['ph']) * 0.6
            fy = fl['h'] + math.sin(self.t * 1.6 + fl['ph'] * 2.0) * 0.25
            q, _ = cam_proj(cam, (fx, fy, fl['z']))
            if q is None:
                continue
            tw = 0.5 + 0.5 * math.sin(self.t * 2.3 + fl['ph'])
            draw_glow(self.buf, q[0], q[1], 11, (206, 255, 146),
                      0.55 * a * (0.35 + 0.65 * tw))

    def draw_birds(self, cam):
        for b in self.birds:
            x = ((b['x'] + self.t * 0.012 * b['v']) % 1.25) - 0.10
            y = b['y'] * SH + math.sin(self.t * 0.9 + b['ph']) * 6.0
            px = x * SW
            w = 4.5 + 3.0 * b['v']
            flap = math.sin(self.t * 7.0 + b['ph']) * 3.4
            col = mix((42, 56, 72), self.fog_col, 0.42)
            pygame.draw.line(self.buf, col, (px - w, y + flap), (px, y), 2)
            pygame.draw.line(self.buf, col, (px, y), (px + w, y - flap * 0.8),
                             2)

    def draw_peds(self, cam):
        for p in self.peds:
            z = p['z'] + math.sin(self.t * 0.30 * p['sp'] + p['ph']) * p['pace']
            dep = z - self.z
            if dep < 2.0 or dep > 88.0:
                continue
            f = 1350.0 / dep
            x = p['x']
            swing = math.sin(self.t * 5.2 * p['sp'] + p['ph2'])
            feet0, _ = cam_proj(cam, (x, FLOOR_Y, z + swing * 0.15))
            feet1, _ = cam_proj(cam, (x, FLOOR_Y, z - swing * 0.15))
            hip, _ = cam_proj(cam, (x, FLOOR_Y + p['h'] * 0.48, z))
            head, _ = cam_proj(cam, (x, FLOOR_Y + p['h'] * 0.94, z))
            if None in (feet0, feet1, hip, head):
                continue
            if dep < 52.0:
                sh = _ell(feet0[0], (feet0[1] + feet1[1]) * 0.5,
                          0.26 * f, 0.08 * f, 10)
                fill_alpha_poly(self.buf, sh, (26, 30, 36), 0.20)
            col = self._fog(p['col'], dep)
            leg_w = max(1, min(6, int(0.05 * f)))
            pygame.draw.line(self.buf, self._fog(mix(p['col'], (24, 28, 34),
                                                     0.55), dep),
                             hip, feet0, leg_w)
            pygame.draw.line(self.buf, self._fog(mix(p['col'], (24, 28, 34),
                                                     0.55), dep),
                             hip, feet1, leg_w)
            pygame.draw.line(self.buf, col, hip, head,
                             max(1, min(14, int(0.14 * f))))
            if dep < 46.0:
                hand, _ = cam_proj(cam, (x, FLOOR_Y + p['h'] * 0.58,
                                         z - swing * 0.22))
                shld, _ = cam_proj(cam, (x, FLOOR_Y + p['h'] * 0.80, z))
                if hand is not None and shld is not None:
                    pygame.draw.line(self.buf, col, shld, hand,
                                     max(1, min(5, int(0.05 * f))))
            pygame.draw.circle(self.buf, self._fog((224, 186, 156), dep),
                               (int(head[0]), int(head[1])),
                               max(1, min(10, int(0.088 * f))))

    def draw_cars(self, cam):
        for c in self.cars + self.mv_cars:
            dep = c['z'] - self.z
            if dep < 1.8 or dep > 118.0:
                continue
            side = c['side']
            xi = c['x']
            xo = xi + side * 1.84
            L = c['ln']
            z0, z1 = c['z'] - L * 0.5, c['z'] + L * 0.5
            H = c['h']
            y_lo = FLOOR_Y + 0.44
            y_b = FLOOR_Y + H * 0.66
            y_r = FLOOR_Y + H
            col = c['col']
            col_f = self._fog(col, dep)
            body = mix(col_f, (46, 50, 74), 0.84)
            body_d = mix(col_f, (28, 30, 44), 0.52)
            body_l = mix(col_f, (255, 248, 232), 0.86)
            roof_c = self._fog(mix(col, (255, 238, 202), 0.88), dep)
            deck_c = mix(roof_c, (150, 148, 162), 0.86)
            glass = self._fog(mix(col, (44, 56, 80), 0.10), dep)
            ink = self._fog((22, 18, 34), dep)
            if side < 0:
                body = mix(body, (255, 214, 158), 0.86)
                body_d = mix(body_d, (255, 202, 144), 0.88)
                body_l = mix(body_l, (255, 232, 186), 0.88)
            else:
                body = mix(body, (104, 108, 150), 0.86)
                body_d = mix(body_d, (92, 96, 140), 0.88)
                glass = mix(glass, (60, 60, 100), 0.86)

            sh = self._quad(cam, ((xi - side * 0.10, FLOOR_Y + 0.008, z0 - 0.22),
                                  (xo + side * 0.14, FLOOR_Y + 0.008, z0 - 0.22),
                                  (xo + side * 0.14, FLOOR_Y + 0.008, z1 + 0.22),
                                  (xi - side * 0.10, FLOOR_Y + 0.008, z1 + 0.22)))
            if sh is not None:
                base = mix((50, 54, 70), self.fog_col, _ground_k(dep))
                so = None
                if dep < 62.0:
                    so = self._quad(cam,
                                    ((xi - side * 0.02, FLOOR_Y + 0.006, z0 - 0.42),
                                     (xo + side * 0.34, FLOOR_Y + 0.006, z0 - 0.42),
                                     (xo + side * 0.34, FLOOR_Y + 0.006, z1 + 0.42),
                                     (xi - side * 0.02, FLOOR_Y + 0.006, z1 + 0.42)))
                if so is not None:
                    pygame.draw.polygon(self.buf,
                                        mix((30, 34, 70), base, 0.76), so)
                pygame.draw.polygon(self.buf, mix((26, 30, 66), base, 0.56), sh)

            pa, _ = cam_proj(cam, (xi, FLOOR_Y, c['z']))
            pb, _ = cam_proj(cam, (xi, FLOOR_Y + 1.0, c['z']))
            if pa is None or pb is None:
                continue
            f = abs(pa[1] - pb[1])
            if f < 4.0:
                continue

            # wheels tucked under the body
            wheels = []
            for wz in (z0 + L * 0.195, z1 - L * 0.195):
                wq, _ = cam_proj(cam, (xi - side * 0.03, FLOOR_Y + 0.33, wz))
                if wq is None:
                    continue
                rad = max(2, int(0.35 * f))
                wheels.append((int(wq[0]), int(wq[1]), rad))
                pygame.draw.circle(self.buf, self._fog((28, 28, 34), dep),
                                   (int(wq[0]), int(wq[1])), rad)
                pygame.draw.circle(self.buf, self._fog((118, 116, 116), dep),
                                   (int(wq[0]), int(wq[1])),
                                   max(1, int(rad * 0.34)))

            prof = ((z0, y_lo), (z1, y_lo), (z1, y_lo + (y_b - y_lo) * 0.95),
                    (z1 - L * 0.08, y_b), (z1 - L * 0.26, y_b),
                    (z1 - L * 0.36, y_r), (z0 + L * 0.26, y_r),
                    (z0 + L * 0.11, y_b), (z0, y_b))
            pts = []
            for zz, yy in prof:
                q, _ = cam_proj(cam, (xi, yy, zz))
                if q is None:
                    pts = None
                    break
                pts.append(q)
            if pts is None:
                continue

            hb = y_b - y_lo
            fq = self._quad(cam, ((xi, y_lo, z0), (xo, y_lo, z0),
                                  (xo, y_lo + hb * 0.93, z0),
                                  (xo - side * 0.18, y_lo + hb * 0.99, z0),
                                  (xi + side * 0.18, y_lo + hb * 0.99, z0),
                                  (xi, y_lo + hb * 0.93, z0)))
            if fq is not None:
                pygame.draw.polygon(self.buf, body_d, fq)
                bmp = self._quad(cam, ((xi, y_lo, z0 - 0.01), (xo, y_lo, z0 - 0.01),
                                       (xo, y_lo + 0.20, z0 - 0.01),
                                       (xi, y_lo + 0.20, z0 - 0.01)))
                if bmp is not None:
                    pygame.draw.polygon(self.buf,
                                        self._fog(mix(col, (28, 30, 38), 0.30),
                                                  dep), bmp)
                plq = self._quad(cam, ((xi + side * 0.62, y_lo + 0.20, z0 - 0.01),
                                       (xo - side * 0.62, y_lo + 0.20, z0 - 0.01),
                                       (xo - side * 0.62, y_lo + 0.33, z0 - 0.01),
                                       (xi + side * 0.62, y_lo + 0.33, z0 - 0.01)))
                if plq is not None:
                    pygame.draw.polygon(self.buf, self._fog((214, 214, 200), dep),
                                        plq)
                if dep < 60.0:
                    for lxa in (0.12, 1.38):
                        tq_ = self._quad(cam,
                                         ((xi + side * lxa,
                                           y_lo + hb * 0.50, z0 - 0.01),
                                          (xi + side * (lxa + 0.38),
                                           y_lo + hb * 0.50, z0 - 0.01),
                                          (xi + side * (lxa + 0.38),
                                           y_lo + hb * 0.78, z0 - 0.01),
                                          (xi + side * lxa,
                                           y_lo + hb * 0.78, z0 - 0.01)))
                        if tq_ is not None:
                            pygame.draw.polygon(
                                self.buf, self._fog((126, 42, 46), dep), tq_)
            pygame.draw.polygon(self.buf, body, pts)
            for sx, sy, rad in wheels:
                pygame.draw.arc(self.buf, ink,
                                pygame.Rect(sx - rad, sy - rad, rad * 2, rad * 2),
                                0.18, math.pi - 0.18, max(2, int(0.055 * f)))

            ri = y_r - y_b
            gq = self._quad(cam, ((xi + side * 0.22, y_b, z0 + L * 0.11),
                                  (xo - side * 0.22, y_b, z0 + L * 0.11),
                                  (xo - side * 0.30, y_r, z0 + L * 0.26),
                                  (xi + side * 0.30, y_r, z0 + L * 0.26)))
            if gq is not None:
                pygame.draw.polygon(self.buf, glass, gq)
                gs = self._quad(cam,
                                ((xi + side * 0.24, y_b + ri * 0.78,
                                  z0 + L * 0.173),
                                 (xo - side * 0.24, y_b + ri * 0.78,
                                  z0 + L * 0.173),
                                 (xo - side * 0.30, y_r, z0 + L * 0.26),
                                 (xi + side * 0.30, y_r, z0 + L * 0.26)))
                if gs is not None:
                    pygame.draw.polygon(self.buf,
                                        mix(glass, self.sun_col, 0.84), gs)
                gp0, _ = cam_proj(cam, (xi + side * 0.30, y_b + ri * 0.10,
                                        z0 + L * 0.118))
                gp1, _ = cam_proj(cam, (xi + side * 0.30, y_r,
                                        z0 + L * 0.26))
                gp2, _ = cam_proj(cam, (xo - side * 0.30, y_r,
                                        z0 + L * 0.26))
                gp3, _ = cam_proj(cam, (xo - side * 0.30, y_b + ri * 0.10,
                                        z0 + L * 0.118))
                if None not in (gp0, gp1, gp2, gp3):
                    pygame.draw.polygon(self.buf, body_l,
                                        (gp0, gp1, gp2, gp3), max(1, int(0.03 * f)))
                if dep < 54.0:
                    pygame.draw.polygon(self.buf, ink, gq,
                                        2 if dep < 20.0 else 1)
                lid = self._quad(cam, ((xi + side * 0.08, y_b, z0 + L * 0.075),
                                       (xo - side * 0.08, y_b, z0 + L * 0.075),
                                       (xo - side * 0.20, y_b, z0 + L * 0.12),
                                       (xi + side * 0.20, y_b, z0 + L * 0.12)))
                if lid is not None:
                    pygame.draw.polygon(self.buf, ink, lid, 1)
            rq = self._quad(cam, ((xi + side * 0.30, y_r, z0 + L * 0.26),
                                  (xo - side * 0.30, y_r, z0 + L * 0.26),
                                  (xo - side * 0.20, y_r, z0 + L * 0.34),
                                  (xo - side * 0.20, y_r, z1 - L * 0.36),
                                  (xi + side * 0.20, y_r, z1 - L * 0.36),
                                  (xi + side * 0.20, y_r, z0 + L * 0.34)))
            if rq is not None:
                pygame.draw.polygon(self.buf, roof_c, rq)
            wsq = self._quad(cam, ((xi + side * 0.12, y_b, z1 - L * 0.25),
                                   (xo - side * 0.12, y_b, z1 - L * 0.25),
                                   (xo - side * 0.20, y_r, z1 - L * 0.36),
                                   (xi + side * 0.20, y_r, z1 - L * 0.36)))
            if wsq is not None:
                pygame.draw.polygon(self.buf,
                                    mix(glass, self.fog_col, 0.80), wsq)
                ws = self._quad(cam,
                                ((xi + side * 0.14, y_b + ri * 0.72,
                                  z1 - L * 0.294),
                                 (xo - side * 0.14, y_b + ri * 0.72,
                                  z1 - L * 0.294),
                                 (xo - side * 0.20, y_r, z1 - L * 0.36),
                                 (xi + side * 0.20, y_r, z1 - L * 0.36)))
                if ws is not None:
                    pygame.draw.polygon(self.buf,
                                        mix(glass, self.sun_col, 0.86), ws)
            hq = self._quad(cam, ((xi, y_b, z1 - L * 0.25), (xo, y_b, z1 - L * 0.25),
                                  (xo, y_b, z1 - L * 0.06), (xi, y_b, z1 - L * 0.06)))
            if hq is not None:
                pygame.draw.polygon(self.buf, deck_c, hq)
            tq = self._quad(cam, ((xi, y_b, z0), (xo, y_b, z0),
                                  (xo, y_b, z0 + L * 0.10), (xi, y_b, z0 + L * 0.10)))
            if tq is not None:
                pygame.draw.polygon(self.buf, deck_c, tq)

            wq = []
            for zz, yy in ((z1 - L * 0.275, y_b + 0.05),
                           (z1 - L * 0.345, y_r - 0.10),
                           (z0 + L * 0.255, y_r - 0.10),
                           (z0 + L * 0.175, y_b + 0.05)):
                q, _ = cam_proj(cam, (xi + side * 0.10, yy, zz))
                if q is None:
                    wq = None
                    break
                wq.append(q)
            if wq is not None:
                pygame.draw.polygon(self.buf, glass, wq)
                if dep < 40.0:
                    pygame.draw.polygon(self.buf, ink, wq, 1)
                zm = (z0 + z1) * 0.5
                d0, _ = cam_proj(cam, (xi + side * 0.105, y_b + 0.05, zm))
                d1, _ = cam_proj(cam, (xi + side * 0.105, y_r - 0.10, zm))
                if d0 is not None and d1 is not None:
                    pygame.draw.line(self.buf, body, d0, d1,
                                     max(2, int(0.06 * f)))
                if dep < 42.0:
                    s0, _ = cam_proj(cam, (xi - side * 0.02, y_lo + 0.05, zm))
                    s1, _ = cam_proj(cam, (xi - side * 0.02, y_b - 0.10, zm))
                    if s0 is not None and s1 is not None:
                        pygame.draw.line(self.buf,
                                         self._fog(mix(col, (26, 24, 40), 0.55),
                                                   dep), s0, s1, 1)

            ow = 3 if dep < 18.0 else (2 if dep < 46.0 else 1)
            pygame.draw.polygon(self.buf, ink, pts, ow)
            b0, _ = cam_proj(cam, (xi - side * 0.02, y_b, z0 + L * 0.02))
            b1, _ = cam_proj(cam, (xi - side * 0.02, y_b, z1 - L * 0.02))
            if b0 is not None and b1 is not None:
                pygame.draw.line(self.buf, body_l, b0, b1,
                                 max(1, int(0.035 * f)))

            if c['own'] != 0.0 and dep < 66.0:
                rear = c['own'] > 0
                lcol = (240, 66, 56) if rear else (255, 242, 204)
                lz = z0 - 0.02 if rear else z1 + 0.02
                for lx in (xi + side * 0.34, xi + side * 1.12):
                    lq, _ = cam_proj(cam, (lx, y_lo + hb * 0.62, lz))
                    if lq is None:
                        continue
                    hw = max(2, int(0.15 * f))
                    hh = max(1, int(0.07 * f))
                    pygame.draw.rect(self.buf, lcol,
                                     (int(lq[0] - hw), int(lq[1] - hh),
                                      hw * 2, hh * 2))
                    draw_glow(self.buf, lq[0], lq[1],
                              clamp(130.0 / dep, 3, 13), lcol,
                              0.34 * clamp((66.0 - dep) / 40.0))

    def draw_grass(self, cam):
        for g in self.grass:
            dep = g['z'] - self.z
            if dep < 1.5 or dep > 46.0:
                continue
            f = 1350.0 / dep
            if f < 12.0:
                continue
            sway = math.sin(self.t * 2.0 + g['ph']) * 0.10
            base = self._fog(mix((58, 104, 48), (110, 158, 76), g['tone']), dep)
            tipc = self._fog(mix((86, 146, 66), (136, 188, 96), g['tone']), dep)
            for j in (-1, 0, 1):
                x = g['x'] + j * 0.07
                p0, _ = cam_proj(cam, (x, FLOOR_Y, g['z']))
                p1, _ = cam_proj(cam, (x + sway * (1.0 + 0.2 * j) + j * 0.05,
                                       FLOOR_Y + g['h'] * (1.0 - 0.20 * abs(j)),
                                       g['z']))
                if p0 is None or p1 is None:
                    continue
                pygame.draw.line(self.buf, tipc if j == 0 else base, p0, p1,
                                 max(1, int(0.02 * f)))

    def draw_rocks(self, cam):
        for rk in self.rocks:
            dep = rk['z'] - self.z
            if dep < 1.5 or dep > 34.0:
                continue
            f = 1350.0 / dep
            rad = rk['r'] * f
            if rad < 1.2:
                continue
            c, _ = cam_proj(cam, (rk['x'], FLOOR_Y + rk['r'] * 0.35, rk['z']))
            if c is None:
                continue
            col = self._fog(mix((126, 124, 116), (96, 100, 100), rk['tone']),
                            dep)
            pygame.draw.polygon(self.buf, col,
                                _ell(c[0], c[1], rad, rad * 0.66, 9))
            pygame.draw.polygon(self.buf, mix(col, WHITE, 0.78),
                                _ell(c[0] - rad * 0.22, c[1] - rad * 0.28,
                                     rad * 0.40, rad * 0.22, 8))

    def draw_mist(self, cam):
        for mi in self.mist:
            dep = mi['z'] - self.z
            if dep < 6.0 or dep > 90.0:
                continue
            a = clamp((90.0 - dep) / 60.0) * 0.055
            if a <= 0.012:
                continue
            x = mi['x'] + math.sin(self.t * 0.25 + mi['ph']) * 0.6
            c, _ = cam_proj(cam, (x, FLOOR_Y + 0.35, mi['z']))
            if c is None:
                continue
            f = 1350.0 / dep
            rx = mi['r'] * f
            ry = mi['r'] * 0.22 * f
            if rx > 300.0:
                continue
            fill_alpha_poly(self.buf, _ell(c[0], c[1], rx, ry, 12),
                            mix(WHITE, self.fog_col, 0.30), a)

    def draw_leaves(self, cam):
        for lf in self.leaves:
            z = self.z + 3.0 + ((lf['z'] - self.t * 2.4 * lf['sp']) % 74.0)
            dep = z - self.z
            y = FLOOR_Y + 3.1 - ((self.t * 0.55 * lf['sp'] + lf['ph']) % 3.4)
            x = lf['x'] + math.sin(self.t * 1.4 + lf['ph']) * 0.45
            q, _ = cam_proj(cam, (x, y, z))
            if q is None:
                continue
            r = clamp(120.0 / dep, 1.2, 5.5)
            ang = self.t * 1.3 + lf['ph']
            pts = []
            for k in range(4):
                a = ang + k * math.pi / 2
                rr = r if k % 2 == 0 else r * 0.42
                pts.append((q[0] + math.cos(a) * rr, q[1] + math.sin(a) * rr))
            pygame.draw.polygon(self.buf, self._fog(lf['col'], dep), pts)

    def draw_rays(self, cam):
        if self.sun_xy is None:
            return
        sx, sy = self.sun_xy
        sx = clamp(sx, -120.0, SW + 120.0)
        col = (255, 246, 208)
        for i in range(6):
            a = 1.02 + i * 0.135 + math.sin(self.t * 0.11 + i * 1.7) * 0.02
            wob = 0.5 + 0.5 * math.sin(self.t * 0.23 + i * 2.1)
            alpha = 0.028 + 0.026 * wob
            hw0 = 6.0 + 5.0 * wob
            hw1 = 44.0 + 34.0 * wob
            dx, dy = math.cos(a), math.sin(a)
            px, py = -dy, dx
            d = 34.0
            for _ in range(2):
                d1 = d + 300.0
                w0 = hw0 + (hw1 - hw0) * (d - 34.0) / 620.0
                w1 = hw0 + (hw1 - hw0) * (d1 - 34.0) / 620.0
                pts = [(sx + dx * d + px * w0, sy + dy * d + py * w0),
                       (sx + dx * d1 + px * w1, sy + dy * d1 + py * w1),
                       (sx + dx * d1 - px * w1, sy + dy * d1 - py * w1),
                       (sx + dx * d - px * w0, sy + dy * d - py * w0)]
                fill_alpha_poly(self.buf, pts, col, alpha)
                d = d1 - 2.0

    def draw_dapple(self, cam):
        for d in self.dapple:
            dep = d['z'] - self.z
            if dep < 8.0 or dep > 42.0:
                continue
            a = clamp((42.0 - dep) / 22.0) * 0.10
            if a <= 0.015:
                continue
            x = d['x'] + math.sin(self.t * 0.4 + d['ph']) * 0.25
            c, _ = cam_proj(cam, (x, FLOOR_Y + 0.03, d['z']))
            if c is None:
                continue
            f = 1350.0 / dep
            fill_alpha_poly(self.buf,
                            _ell(c[0], c[1], d['r'] * f, d['r'] * f * 0.30, 12),
                            (255, 246, 206), a)

    def draw_scene(self):
        self.base_sky()
        follow = min(1.0, self.frame_dt * 6.0)
        self.camx += (self.x * 0.84 - self.camx) * follow
        if self.crashed and self.debris:
            ty = sum(d['pos'][1] for d in self.debris) / len(self.debris)
            self.camy += (ty - 0.12 - self.camy) * min(1.0, self.frame_dt * 3.0)
        else:
            self.camy += (self.y * 0.80 - self.camy) * follow
        cam = self.camera()
        self.cam = cam

        self.draw_sky_fx(cam)
        self.draw_clouds(cam)
        if self.theme == 'street':
            self.draw_skyline(cam)
            self.draw_ground(cam)
            self.draw_shadows(cam)
            self.draw_road(cam)
            self.draw_city(cam)
            self.draw_lamps(cam)
            self.draw_gantries(cam)
            self.draw_peds(cam)
            self.draw_birds(cam)
        elif self.theme == 'forest':
            self.draw_hills(cam)
            self.draw_ground(cam)
            self.draw_road(cam)
            self.draw_trees(cam)
            self.draw_bushes(cam)
            self.draw_grass(cam)
            self.draw_rocks(cam)
            self.draw_mist(cam)
            self.draw_leaves(cam)
            self.draw_flies(cam)
            self.draw_rays(cam)
            self.draw_birds(cam)
        else:
            self.draw_ridge(cam)
            self.draw_haze(cam)
            self.draw_reef_floor(cam)
            self.draw_track(cam)
            self.draw_canyon(cam)
            self.draw_isles(cam)
            self.draw_reef_mist(cam)
        if self.theme == 'street':
            self.draw_cars(cam)
        elif self.theme == 'forest':
            self.draw_dapple(cam)
        self.draw_beacon(cam)
        self.draw_pads(cam)
        self.draw_pickups(cam)
        self.draw_dust(cam)

        bob = 0.03 * math.sin(self.t * 3.2)
        if not self.crashed:
            self.draw_ship_shadow(cam, bob)
            self.draw_trail(cam)
        if self.crashed:
            self.draw_debris(cam)
            self.draw_sparks(cam)
            return
        off = (self.x, self.y + bob, self.z)
        pulse = 0.85 + 0.15 * math.sin(self.t * 3.4)
        draw_parts(self.buf, cam, self.parts, spin=self.t * 22.0, pulse=pulse,
                   offset=off, tilt=self.ship_tilt(), blur=1.0)
        for s in (1, -1):
            pt, _ = cam_proj(cam, (self.x + s * 0.32, self.y + bob - 0.02,
                                   self.z - 0.86))
            if pt:
                draw_glow(self.buf, pt[0], pt[1], 24 + 32 * self.boost_fx,
                          TEAL, 0.26 + 0.20 * self.boost_fx)
                draw_glow(self.buf, pt[0], pt[1], 9, WHITE, 0.18 +
                          0.14 * self.boost_fx)
        if self.boost_fx > 0.05:
            self.draw_streaks()

    def draw_ridge(self, cam):
        hz, _ = cam_proj(cam, (0.0, 0.0, self.z + 160.0))
        if hz is None:
            return
        base = self.sec['line']
        floor = hz[1] + 2
        for dist, amp, lift in ((85.0, 0.34, 0.03), (125.0, 0.58, 0.07),
                                (175.0, 0.86, 0.12)):
            zf = self.z + dist
            top = []
            for i in range(-32, 33):
                x = i * 1.3
                h = (0.55 + 0.45 * math.sin(x * 0.31 + zf * 0.05)) * \
                    (0.60 + 0.40 * math.sin(x * 0.11 - zf * 0.03))
                p, _ = cam_proj(cam, (x, h * amp + lift, zf))
                if p is not None:
                    top.append((p[0], min(p[1], floor - 1)))
            if len(top) < 3:
                continue
            far = clamp((dist - 70.0) / 120.0)
            fill = mix((50, 66, 80), self.haze_c, 0.30 + 0.40 * far)
            poly = [(SW * -0.3, floor), (SW * 1.3, floor)]
            poly += list(reversed(top))
            pygame.draw.polygon(self.buf, fill, poly)
            pygame.draw.lines(self.buf, mix(fill, self.haze_c, 0.45),
                              False, top, 1)

    def draw_haze(self, cam):
        hz, _ = cam_proj(cam, (0.0, 0.0, self.z + 160.0))
        if hz is None:
            return
        base = self.sec['line']
        floor = hz[1] + 1
        for dist, lift, depth in ((74.0, 0.008, 16), (108.0, 0.030, 22),
                                  (148.0, 0.062, 28)):
            zf = self.z + dist
            top = []
            for i in range(-18, 19):
                x = i * 2.4
                h = (0.55 * math.sin(x * 0.13 + zf * 0.03) +
                     0.45 * math.sin(x * 0.05 - zf * 0.02))
                p, _ = cam_proj(cam, (x, h * depth * 0.01 + lift, zf))
                if p is not None:
                    top.append((p[0], min(p[1], floor - 1)))
            if len(top) < 3:
                continue
            far = clamp((dist - 70.0) / 110.0)
            col = mix((30, 42, 54), self.haze_c, 0.45 - 0.25 * far)
            poly = [(SW * -0.3, floor), (SW * 1.3, floor)]
            poly += list(reversed(top))
            pygame.draw.polygon(self.buf, col, poly)
            pygame.draw.lines(self.buf, mix(col, self.haze_c, 0.55),
                              False, top, 1)

    def draw_reef_floor(self, cam):
        zc = self.z
        near_c = (33, 41, 57)
        bands = ((-10.0, 12.0, 0.97), (12.0, 26.0, 0.94), (26.0, 40.0, 0.91),
                 (40.0, 56.0, 0.88), (56.0, 74.0, 0.85), (74.0, 94.0, 0.81),
                 (94.0, 118.0, 0.78), (118.0, 146.0, 0.74),
                 (146.0, 180.0, 0.70), (180.0, 220.0, 0.65),
                 (220.0, 268.0, 0.60), (268.0, 320.0, 0.55))
        for z0, z1, k in reversed(bands):
            self._ground_quad(cam, -150.0, 150.0, zc + z0, zc + z1,
                              mix(near_c, self.haze_c, k))

        # fractured rock slabs inside the reef channel
        for s in self.slabs:
            dz = s['z'] - zc
            if dz < 1.2 or dz > 88.0:
                continue
            k = clamp((dz - 2.0) / 130.0)
            sun = 1.0 if s['x'] < 0 else 0.0
            tone = clamp(0.22 + 0.42 * s['tone'] + (0.0 if sun else 0.12))
            col = mix(mix((58, 70, 92), (27, 33, 47), tone), self.haze_c,
                      0.97 - 0.62 * k)
            poly = [(s['x'] + px, FLOOR_Y + 0.006, s['z'] + pz)
                    for px, pz in s['pts']]
            q = _clip_project(cam, poly)
            if q is None:
                continue
            if dz < 42.0:
                pygame.draw.polygon(self.buf, mix(col, (8, 12, 20), 0.70),
                                    [(x, y + 2) for x, y in q])
            pygame.draw.polygon(self.buf, col, q)
            if dz < 34.0:
                pygame.draw.lines(self.buf, mix(col, (12, 18, 30), 0.74),
                                  True, q, 1)
                if tone > 0.5:
                    pygame.draw.lines(self.buf,
                                      mix(col, (126, 178, 188), 0.62), False,
                                      [q[1], q[2]], 1)
                if tone > 0.90:
                    vx = (q[0][0] + q[2][0]) * 0.5
                    vy = (q[0][1] + q[2][1]) * 0.5
                    pygame.draw.line(self.buf,
                                     mix(col, self.sec['line'], 0.55),
                                     (vx - 7, vy), (vx + 8, vy - 2), 1)

        # channel curbs with a lit top edge
        edge = 9.6
        for side in (-1, 1):
            x0, x1 = side * edge, side * (edge + 0.85)
            for za, zb in ((zc + 1.0, zc + 34.0), (zc + 34.0, zc + 86.0)):
                k = clamp((za - zc) / 140.0)
                top = mix((52, 66, 86), self.haze_c, 0.92 - 0.50 * k)
                face = mix((26, 33, 46), self.haze_c, 0.92 - 0.50 * k)
                self._ground_quad(cam, x0, x1, za, zb, top)
                fq = _clip_project(cam, ((x0, FLOOR_Y + 0.001, za),
                                         (x0, FLOOR_Y + 0.001, zb),
                                         (x0, FLOOR_Y - 0.26, zb),
                                         (x0, FLOOR_Y - 0.26, za)))
                if fq is not None:
                    pygame.draw.polygon(self.buf, face, fq)
                q0, _ = cam_proj(cam, (x0, FLOOR_Y + 0.014, za))
                q1, _ = cam_proj(cam, (x0, FLOOR_Y + 0.014, zb))
                if q0 is not None and q1 is not None:
                    pygame.draw.line(self.buf,
                                     mix(self.sec['line'], self.haze_c,
                                         0.85 - 0.42 * k),
                                     q0, q1, 1)

    def draw_canyon(self, cam):
        zc = self.z
        base = self.sec['line']
        seg = 6.4
        j0 = int((zc + 1.0) // seg) - 1

        # distant ridge behind the cliff walls
        for side in (-1, 1):
            xw = side * 17.5
            for j in range(j0, j0 + 18):
                za, zb = j * seg, (j + 1) * seg
                if zb < zc + 4.0:
                    continue
                if za - zc > 150.0:
                    break
                h = 3.4 + 3.6 * (0.5 + 0.5 * math.sin(j * 0.83 + side * 2.4)) \
                    * (0.6 + 0.4 * math.sin(j * 2.11))
                a = _clip_project(cam, ((xw, FLOOR_Y, za), (xw, FLOOR_Y, zb),
                                        (xw, FLOOR_Y + h, zb + 1.2),
                                        (xw, FLOOR_Y + h, za + 1.2)))
                if a is None:
                    continue
                k = clamp((za - zc) / 150.0)
                col = mix((14, 22, 34), self.haze_c, 0.55 - 0.28 * k)
                pygame.draw.polygon(self.buf, col, a)
                pygame.draw.lines(self.buf, mix(col, self.haze_c, 0.72),
                                  False, [a[2], a[3]], 1)

        for side in (-1, 1):
            for j in range(j0, j0 + 16):
                za, zb = j * seg, (j + 1) * seg
                if zb < zc + 2.0:
                    continue
                if za - zc > 96.0:
                    break
                jag = 0.60 * math.sin(j * 7.13 + side * 3.1)
                h0 = 3.1 + 0.9 * (0.5 + 0.5 * math.sin(j * 0.63 + side * 1.1))
                h1 = 3.1 + 0.9 * (0.5 + 0.5 * math.sin((j + 1) * 0.63
                                                       + side * 1.1))
                x0 = side * (10.1 + 0.55 * math.sin(j * 0.47 + side))
                x1 = side * (10.1 + 0.55 * math.sin((j + 1) * 0.47 + side))
                k = clamp((za - zc) / 150.0)
                fog = 0.94 - 0.50 * k
                tone = 0.5 + 0.5 * math.sin(j * 0.35 + side * 1.3)
                rock = mix((54, 66, 88), (30, 38, 52), tone)
                if side < 0:
                    rock = mix(rock, (96, 84, 72), 0.30)
                    hi_c = (214, 168, 118)
                else:
                    rock = mix(rock, (32, 52, 68), 0.28)
                    hi_c = (112, 154, 172)
                so = 0.05 * math.sin(j * 2.7 + side * 0.7)
                strata = ((-0.06, 0.18 + so, (10, 14, 24), 0.30),
                          (0.18 + so, 0.60 + so, hi_c, 0.06),
                          (0.60 + so, 1.06, hi_c, 0.26))
                for lo, hi, tint, wg in strata:
                    hl0 = h0 * lo + jag * (1.0 - lo) * 0.5
                    hl1 = h1 * lo + jag * (1.0 - lo) * 0.5
                    hh0 = h0 * hi + jag * (1.0 - hi) * 0.5
                    hh1 = h1 * hi + jag * (1.0 - hi) * 0.5
                    p0, _ = cam_proj(cam, (x0, FLOOR_Y + hl0, za))
                    p1_, _ = cam_proj(cam, (x1, FLOOR_Y + hl1, zb))
                    p2, _ = cam_proj(cam, (x1, FLOOR_Y + hh1, zb))
                    p3, _ = cam_proj(cam, (x0, FLOOR_Y + hh0, za))
                    if None in (p0, p1_, p2, p3):
                        continue
                    c = mix(rock, tint, wg)
                    c = mix(c, self.haze_c, 1.0 - fog)
                    pygame.draw.polygon(self.buf, c, [p0, p1_, p2, p3])
                b, _ = cam_proj(cam, (x0, FLOOR_Y + h0 + jag * 0.0, za))
                c, _ = cam_proj(cam, (x1, FLOOR_Y + h1, zb))
                if b is not None and c is not None:
                    lit = (255, 212, 158) if x0 < 0 else (126, 186, 190)
                    pygame.draw.line(self.buf,
                                     mix(mix(rock, lit, 0.55),
                                         self.haze_c, 1.0 - fog), b, c, 1)
                seam = mix(mix(rock, (8, 12, 20), 0.50),
                           self.haze_c, 1.0 - fog)
                for u in (0.26 + so, 0.57 + so):
                    s0, _ = cam_proj(cam, (x0, FLOOR_Y + h0 * u, za))
                    s1, _ = cam_proj(cam, (x1, FLOOR_Y + h1 * u, zb))
                    if s0 is not None and s1 is not None:
                        pygame.draw.line(self.buf, seam, s0, s1, 1)
                if j % 3 == 1:
                    ja, _ = cam_proj(cam, (x0, FLOOR_Y, za))
                    jb, _ = cam_proj(cam, (x0, FLOOR_Y + h0, za))
                    if ja is not None and jb is not None:
                        pygame.draw.line(self.buf,
                                         mix(mix(rock, (10, 14, 24), 0.45),
                                             self.haze_c, 1.0 - fog), ja, jb, 1)
                if (j * 3 + (side > 0)) % 5 == 0:
                    ca, _ = cam_proj(cam, (x0 - side * 0.06,
                                           FLOOR_Y + h0 * 0.15, za + 1.1))
                    cb, _ = cam_proj(cam, (x0 - side * 0.04,
                                           FLOOR_Y + h0 * 0.62, za + 1.7))
                    if ca is not None and cb is not None:
                        pygame.draw.line(self.buf,
                                         mix(mix(self.sec['line'],
                                                 (124, 242, 228), 0.35),
                                             self.haze_c, 1.0 - fog),
                                         ca, cb, 1)

    def draw_isles(self, cam):
        for i in self.isles:
            dep = i['z'] - self.z
            if dep < 7.0 or dep > 92.0:
                continue
            bob = 0.12 * math.sin(self.t * 0.55 + i['ph'])
            f = 1350.0 / dep
            r = i['r']
            top, _ = cam_proj(cam, (i['x'], i['y'] + bob, i['z']))
            foot, _ = cam_proj(cam, (i['x'], i['y'] + bob - r * 0.95, i['z']))
            if top is None or foot is None:
                continue
            k = clamp((dep - 4.0) / 120.0)
            rx = r * f
            if rx > 84.0:
                continue
            cy = (top[1] + foot[1]) * 0.5
            ry = max(2.0, (foot[1] - top[1]) * 0.22 + rx * 0.26)
            body = mix(mix((40, 50, 68), (21, 27, 39), i['tone']),
                       self.haze_c, 0.90 - 0.55 * k)
            pygame.draw.polygon(self.buf, mix(body, (8, 12, 22), 0.38),
                                [(top[0] - rx * 0.80, top[1] + ry * 0.4),
                                 (top[0] + rx * 0.80, top[1] + ry * 0.4),
                                 (top[0] + rx * 0.12, foot[1])])
            plate = []
            n = 7
            for s in range(n):
                ang = 2 * math.pi * s / n
                jr = 0.76 + 0.24 * abs(math.sin(s * 2.3 + i['ph']))
                plate.append((top[0] + math.cos(ang) * rx * 0.95 * jr,
                              top[1] + math.sin(ang) * ry * jr))
            pygame.draw.polygon(self.buf, mix(body, (98, 142, 154),
                                              0.34 - 0.12 * k), plate)
            lit = (255, 210, 160) if i['x'] < 0 else (150, 208, 210)
            pygame.draw.lines(self.buf, mix(body, lit, 0.58 - 0.16 * k),
                              True, plate, 1)
            if dep < 60.0:
                draw_glow(self.buf, foot[0], foot[1] + 2,
                          int(clamp(rx * 0.9, 6, 34)), self.sec['line'],
                          0.22 * (1.0 - k))

    def draw_reef_mist(self, cam):
        zc = self.z
        for idx, (za, sx, rx, al) in enumerate(((30.0, 8.6, 1.3, 0.08),
                                                (46.0, -8.8, 1.5, 0.08),
                                                (64.0, 9.0, 1.7, 0.07),
                                                (86.0, -9.0, 1.9, 0.06),
                                                (110.0, 8.6, 2.2, 0.05))):
            drift = 1.4 * math.sin(self.t * 0.16 + idx * 1.9)
            q, dep = cam_proj(cam, (sx + drift, FLOOR_Y + 0.05, zc + za))
            if q is None or dep < 4.0:
                continue
            f = 1350.0 / dep
            col = (255, 212, 166) if sx < 0 else (146, 198, 214)
            fill_alpha_poly(self.buf, _ell(q[0], q[1], rx * f,
                                           0.30 * rx * f, 16),
                            mix(col, self.haze_c, 0.34), al)


    def draw_dust(self, cam):
        sp = clamp(self.speed / 22.0)
        if sp < 0.05:
            return
        for i, p in enumerate(self.dust):
            a = p['a'] + self.t * p['v'] * 0.25
            r = (p['r'] + (self.t * p['v'] * 0.35 + p['z']) % 1.0) % 1.0
            x = SW * 0.5 + math.cos(a) * r * SW * 0.55
            y = SH * 0.52 + math.sin(a) * r * SH * 0.50
            if 8 < x < SW - 8 and 8 < y < SH - 8:
                k = 0.06 * (1.0 - r) * sp
                draw_glow(self.buf, x, y, int(6 + p['s'] * 8), (168, 206, 255),
                          k)

    def draw_debris(self, cam):
        for d in self.debris:
            r = _rot(d['tilt'], d['c'])
            off = (d['pos'][0] - r[0], d['pos'][1] - r[1], d['pos'][2] - r[2])
            draw_parts(self.buf, cam, [d['p']], offset=off,
                       tilt=(d['tilt'][0], d['tilt'][1]),
                       spin=self.crash_t * d['spin'])

    def draw_sparks(self, cam):
        q, dep = cam_proj(cam, (self.x, self.y, self.z))
        if q is not None and self.crash_t < 1.1:
            k = clamp(self.crash_t / 1.1)
            rad = (34 + 150 * k) * (0.55 + 0.55 * self.boom)
            for i in range(4):
                fr = 1.0 - i * 0.21
                fill_alpha_poly(self.buf,
                                _ell(q[0], q[1], rad * fr, rad * fr * 0.82, 22),
                                (255, 128 + i * 28, 50 + i * 34),
                                (0.20 + i * 0.055) * (1.0 - k))
            draw_glow(self.buf, q[0], q[1], rad * 1.9, (255, 118, 48),
                      0.42 * (1.0 - k))
        if self.crash_t < 0.4:
            q, dep = cam_proj(cam, (self.x, self.y, self.z))
            if q is not None:
                k = 1.0 - self.crash_t / 0.4
                draw_glow(self.buf, q[0], q[1],
                          120 + 420 * self.crash_t * self.boom,
                          (255, 150, 62), 0.80 * k)
                draw_glow(self.buf, q[0], q[1],
                          60 + 220 * self.crash_t * self.boom,
                          (255, 236, 190), 0.50 * k)
        for s in self.sparks:
            q, dep = cam_proj(cam, s['pos'])
            if q is None:
                continue
            k = clamp(s['life'] / 0.9)
            draw_glow(self.buf, q[0], q[1],
                      clamp(340.0 / dep, 7, 46) * self.boom ** 0.5,
                      s['col'], 0.60 * k)
        for f in self.fire:
            q, dep = cam_proj(cam, f['pos'])
            if q is None:
                continue
            k = clamp(f['age'] / f['life'])
            rad = f['size'] * (0.55 + 2.1 * k) * clamp(300.0 / dep, 1.0, 30.0)
            hot = mix(WHITE, (255, 128, 52), clamp(k * 1.8))
            draw_glow(self.buf, q[0], q[1], max(4.0, rad * 1.5), hot,
                      0.62 * (1.0 - k) ** 0.7)
            draw_glow(self.buf, q[0], q[1], max(2.0, rad * 0.7),
                      (255, 236, 190), 0.38 * (1.0 - k))
            if k > 0.22:
                smoke = clamp((k - 0.22) / 0.78)
                fill_alpha_poly(self.buf,
                                _ell(q[0], q[1] - rad * 0.35 * k,
                                     max(2.0, rad * 1.05),
                                     max(1.5, rad * 0.72), 12),
                                (34, 32, 36), 0.34 * smoke)

    def draw_ship_shadow(self, cam, bob):
        q, dep = cam_proj(cam, (self.x, FLOOR_Y, self.z))
        if q is None:
            return
        f = clamp(200.0 / max(6.0, dep), 0.5, 1.6)
        lift = clamp(1.05 - 0.14 * (self.y - FLOOR_Y), 0.22, 1.0)
        for k, a in ((1.0, 0.16), (0.7, 0.20), (0.42, 0.24)):
            fill_alpha_poly(self.buf, _ell(q[0], q[1], 92 * k * f,
                                           24 * k * f, 16),
                            (14, 18, 26), a * lift)

    def draw_track(self, cam):
        line_col = self.sec['line']
        if self.theme != 'canyon':
            return
        z0 = int(self.z) - 6
        z1 = int(self.z) + 84
        # glowing seams across the reef channel
        for k in range(z0 - (z0 % 8), z1, 8):
            dz = k - self.z
            if dz < 1.5:
                continue
            a = clamp((84 - dz) / 62.0) * 0.36
            if a <= 0.01:
                continue
            s0, _ = cam_proj(cam, (-9.6, FLOOR_Y + 0.02, k))
            s1, _ = cam_proj(cam, (9.6, FLOOR_Y + 0.02, k))
            if s0 is None or s1 is None:
                continue
            pygame.draw.line(self.buf, mix(line_col, (9, 16, 30), 1.0 - a),
                             (s0[0], s0[1]), (s1[0], s1[1]), 1)
        # lane pylons
        for k in range(z0 - (z0 % 12), z1, 12):
            dz = k - self.z
            if dz < 2:
                continue
            fade = clamp((72 - dz) / 40.0) * 0.8
            for sx in (-6.2, 6.2):
                q, _ = cam_proj(cam, (sx, FLOOR_Y + 0.02, k))
                if q is None:
                    continue
                draw_glow(self.buf, q[0], q[1], 12, self.sec['line'],
                          0.30 * fade)
                q0, _ = cam_proj(cam, (sx, FLOOR_Y, k))
                q1, _ = cam_proj(cam, (sx, FLOOR_Y + 0.95, k))
                if q0 and q1:
                    pygame.draw.line(self.buf, mix(line_col, (14, 24, 44),
                                                   0.35 + 0.35 * fade),
                                     q0, q1, 1)

    def draw_road(self, cam):
        line_col = self.sec['line']
        zc = self.z
        edge = 6.4 if self.theme == 'street' else 5.2

        curb = mix((226, 222, 208), self.fog_col, 0.85)
        for sx in (-edge, edge):
            q0, _ = cam_proj(cam, (sx, FLOOR_Y + 0.015, zc + 1.4))
            q1, _ = cam_proj(cam, (sx, FLOOR_Y + 0.015, zc + 62.0))
            if q0 is not None and q1 is not None:
                pygame.draw.line(self.buf, curb, q0, q1, 2)

        sheen = (255, 232, 194) if self.theme == 'street' else (255, 228, 186)
        for za, r, al in ((34.0, 150, 0.10), (58.0, 210, 0.09),
                          (90.0, 280, 0.08), (130.0, 340, 0.07)):
            c, _ = cam_proj(cam, (0.0, FLOOR_Y + 0.02, zc + za))
            if c is not None:
                draw_glow(self.buf, c[0], c[1], r, sheen, al)

        k = int(zc // 6) * 6
        while k < zc + 76:
            if k > zc + 2.0:
                dz = k - zc
                a = clamp((76.0 - dz) / 48.0)
                q0, _ = cam_proj(cam, (0.0, FLOOR_Y + 0.02, k))
                q1, _ = cam_proj(cam, (0.0, FLOOR_Y + 0.02, k + 2.8))
                if q0 is not None and q1 is not None:
                    pygame.draw.line(self.buf,
                                     mix((232, 220, 180), self.fog_col, 1.0 - a),
                                     q0, q1, 2)
            k += 6

        if self.theme != 'street':
            for sx in (-1.55, 1.55):
                for za, zb, al in ((2.0, 22.0, 0.30), (22.0, 70.0, 0.15)):
                    q = _clip_project(cam,
                                      ((sx - 0.30, FLOOR_Y + 0.014, zc + za),
                                       (sx + 0.30, FLOOR_Y + 0.014, zc + za),
                                       (sx + 0.36, FLOOR_Y + 0.014, zc + zb),
                                       (sx - 0.36, FLOOR_Y + 0.014, zc + zb)))
                    if q is not None:
                        fill_alpha_poly(self.buf, q, (88, 74, 50), al)

        if self.theme == 'street':
            for gz in self.gantries:
                dz = gz - zc
                if dz < 10.0 or dz > 74.0:
                    continue
                a = clamp((dz - 10.0) / 8.0) * clamp((74.0 - dz) / 30.0)
                if a <= 0.03:
                    continue
                for j in range(7):
                    za = gz - 5.2 + j * 0.62
                    q = self._quad(cam, ((-4.9, FLOOR_Y + 0.02, za),
                                         (4.9, FLOOR_Y + 0.02, za),
                                         (4.9, FLOOR_Y + 0.02, za + 0.36),
                                         (-4.9, FLOOR_Y + 0.02, za + 0.36)))
                    if q is not None:
                        pygame.draw.polygon(
                            self.buf,
                            mix((240, 240, 232), self.fog_col, 1.0 - a), q)

        for k in range(int(zc // 9) * 9, int(zc) + 82, 9):
            dz = k - zc
            if dz < 2:
                continue
            fade = clamp((82.0 - dz) / 48.0) * 0.85
            for sx in (-4.4, 4.4):
                q, _ = cam_proj(cam, (sx, FLOOR_Y + 0.02, k))
                if q is not None:
                    draw_glow(self.buf, q[0], q[1], 12, line_col,
                              0.32 * fade)
                q0, _ = cam_proj(cam, (sx, FLOOR_Y, k))
                q1, _ = cam_proj(cam, (sx, FLOOR_Y + 0.85, k))
                if q0 is not None and q1 is not None:
                    pygame.draw.line(self.buf,
                                     mix(line_col, self.fog_col, 1.0 - fade),
                                     q0, q1, 1)

    def draw_beacon(self, cam):
        dz = self.finish_z - self.z
        if dz < -4 or dz > 95:
            return
        base, _ = cam_proj(cam, (0.0, FLOOR_Y, self.finish_z))
        top, _ = cam_proj(cam, (0.0, 4.6, self.finish_z))
        if base is None or top is None:
            return
        k = clamp((95 - dz) / 55.0) * clamp(dz / 6.0)
        for wdt, col, a in ((16, (24, 74, 86), 0.30), (7, (46, 200, 196), 0.45),
                            (3, (186, 255, 246), 0.75)):
            c = mix(col, (12, 22, 40), 1.0 - a * k)
            pygame.draw.line(self.buf, c, top, base, wdt)
        q, _ = cam_proj(cam, (0.0, 2.4, self.finish_z))
        if q:
            draw_glow(self.buf, q[0], q[1], 150, TEAL, 0.34 * k)
        if dz < 32:
            text(self.buf, top[0], top[1] - 24, 'FINISH', 11, 'mono',
                 mix(WHITE, TEAL, 0.3), 'c', 2.4, 0.9 * k)

    def draw_pads(self, cam):
        for p in self.pads:
            if p['done']:
                continue
            dz = p['z'] - self.z
            if dz < 1.2 or dz > 70:
                continue
            fade = clamp((70 - dz) / 40.0) * clamp(dz / 6.0)
            q, dep = cam_proj(cam, (p['x'], FLOOR_Y + 0.015, p['z']))
            if q is None:
                continue
            rx = 0.78
            rz = 1.45
            pts = []
            ok = True
            for i in range(20):
                a = 2 * math.pi * i / 20
                pt, _ = cam_proj(cam, (p['x'] + rx * math.cos(a),
                                       FLOOR_Y + 0.015,
                                       p['z'] + rz * math.sin(a)))
                if pt is None:
                    ok = False
                    break
                pts.append(pt)
            if not ok:
                continue
            pygame.draw.polygon(self.buf, mix((10, 40, 46), (12, 22, 40),
                                             1 - 0.6 * fade), pts)
            pygame.draw.lines(self.buf, mix(TEAL, (12, 22, 40), 1 - 0.8 * fade),
                              True, pts, 2)
            draw_glow(self.buf, q[0], q[1], 60, TEAL, 0.30 * fade)
            for j in (-1, 0, 1):
                a0, _ = cam_proj(cam, (p['x'] - 0.4, FLOOR_Y + 0.016,
                                       p['z'] + j * 0.5))
                a1, _ = cam_proj(cam, (p['x'], FLOOR_Y + 0.016,
                                       p['z'] + j * 0.5 - 0.4))
                a2, _ = cam_proj(cam, (p['x'] + 0.4, FLOOR_Y + 0.016,
                                       p['z'] + j * 0.5))
                if a0 and a1 and a2:
                    pygame.draw.lines(self.buf, mix(TEAL, WHITE, 0.5), False,
                                      [a0, a1, a2], 2)

    def draw_pickups(self, cam):
        items = []
        for c in self.cores:
            if c['done']:
                continue
            dz = c['z'] - self.z
            if dz < 1.0 or dz > 82.0:
                continue
            q, dep = cam_proj(cam, (c['x'], c['y'], c['z']))
            if q is None:
                continue
            items.append((dep, 'core', c, q))
        for m in self.mines:
            if m['done']:
                continue
            dz = m['z'] - self.z
            if dz < 1.0 or dz > 82.0:
                continue
            mx, my = self.mine_pos(m)
            q, dep = cam_proj(cam, (mx, my, m['z']))
            if q is None:
                continue
            items.append((dep, 'mine', m, q))
        items.sort(key=lambda it: -it[0])
        nxt = self.next_core()
        for dep, kind, obj, q in items:
            if kind == 'core':
                self.draw_core(cam, obj, q, dep, obj is nxt)
            else:
                self.draw_mine(cam, obj, q, dep)

    def draw_core(self, cam, c, q, dep, is_next):
        x, y = q
        r = clamp(300.0 / dep, 4.0, 30.0)
        fade = clamp((82.0 - (c['z'] - self.z)) / 46.0) * clamp(
            (c['z'] - self.z) / 5.0)
        if fade <= 0.02:
            return
        spin = self.t * 1.7 + c['z'] * 0.4
        col = GOLD if is_next else (150, 206, 226)
        glow_col = GOLD if is_next else TEAL
        draw_glow(self.buf, x, y, int(r * 6.5), glow_col,
                  (0.36 if is_next else 0.20) * fade)
        w = r * 0.66
        h = r * 1.08
        pts = [(x, y - h), (x + w, y), (x, y + h), (x - w, y)]
        pygame.draw.polygon(self.buf, mix(col, (12, 22, 40), 0.25 * (1 - fade)),
                            pts)
        core = [(x, y - h * 0.52), (x + w * 0.48, y), (x, y + h * 0.52),
                (x - w * 0.48, y)]
        pygame.draw.polygon(self.buf, mix(mix(WHITE, col, 0.45), col,
                                          0.55 + 0.3 * math.sin(self.t * 5.0)),
                            core)
        pygame.draw.lines(self.buf, mix(WHITE, col, 0.25), True, pts, 1)
        for k in range(2):
            a = spin + k * math.pi
            sx = x + math.cos(a) * r * 1.18
            sy = y + math.sin(a) * r * 0.5
            shard = [(sx, sy - r * 0.26), (sx + r * 0.14, sy),
                     (sx, sy + r * 0.26), (sx - r * 0.14, sy)]
            pygame.draw.polygon(self.buf, mix(col, (12, 22, 40), 0.15), shard)
        if is_next:
            pulse = 0.5 + 0.5 * math.sin(self.t * 4.2)
            pygame.draw.circle(self.buf, mix(TEAL, (10, 20, 36), 0.3),
                               (int(x), int(y)), int(r * (1.9 + 0.25 * pulse)),
                               1)
            # floor marker under the next core
            fq, fdep = cam_proj(cam, (c['x'], FLOOR_Y + 0.01, c['z']))
            if fq is not None:
                pygame.draw.line(self.buf, mix(TEAL, (10, 20, 36), 0.55),
                                 (x, y + r), fq, 1)
                draw_glow(self.buf, fq[0], fq[1], 26, TEAL, 0.20 * fade)

    def draw_mine(self, cam, m, q, dep):
        x, y = q
        r = clamp(330.0 / dep, 5.0, 34.0)
        fade = clamp((82.0 - (m['z'] - self.z)) / 46.0) * clamp(
            (m['z'] - self.z) / 5.0)
        if fade <= 0.02:
            return
        near = not m['done'] and not m['near'] and abs(m['z'] - self.z) < 6.0
        pulse = 0.55 + 0.45 * math.sin(self.t * 6.0 + m['ph'])
        ang = self.t * 1.4 + m['tilt']
        for k in range(6):
            a = ang + k * math.pi / 3
            pygame.draw.line(self.buf, mix((92, 44, 58), (16, 24, 40), 0.35),
                             (x + math.cos(a) * r * 0.75,
                              y + math.sin(a) * r * 0.75),
                             (x + math.cos(a) * r * (1.55 + 0.1 * pulse),
                              y + math.sin(a) * r * (1.55 + 0.1 * pulse)), 2)
        pygame.draw.circle(self.buf, mix((34, 22, 38), (10, 16, 30), 0.25),
                           (int(x), int(y)), int(r))
        pygame.draw.circle(self.buf, mix(RED, (30, 12, 22), 0.55),
                           (int(x), int(y)), int(r * 0.62))
        pygame.draw.circle(self.buf, mix(WHITE, RED, 0.35),
                           (int(x), int(y)), max(2, int(r * 0.24)))
        draw_glow(self.buf, x, y, int(r * 5.2), RED,
                  (0.26 + 0.20 * pulse) * fade)
        if near:
            pygame.draw.circle(self.buf, mix(RED, (12, 20, 36), 0.35),
                               (int(x), int(y)), int(r * (2.0 + 0.35 * pulse)),
                               1)

    def draw_trail(self, cam):
        for p in self.trail:
            q, dep = cam_proj(cam, (p['x'], p['y'], p['z']))
            if q is None:
                continue
            k = 1.0 - p['age'] / 0.7
            draw_glow(self.buf, q[0], q[1], clamp(26 + 26 * k, 10, 52),
                      mix(TEAL, WHITE, 0.25), 0.32 * k)

    def draw_streaks(self):
        if self.theme == 'canyon':
            col = mix(CYAN, (10, 18, 34), 0.62)
        else:
            col = mix(WHITE, self.fog_col, 0.48)
        for i in range(14):
            a = self.t * 2.6 + i * 2.399
            r0 = 0.42 + (i % 4) * 0.06
            c, s = math.cos(a), math.sin(a)
            x0 = SW * 0.5 + c * SW * r0
            y0 = SH * 0.50 + s * SH * r0 * 0.8
            x1 = SW * 0.5 + c * SW * (r0 + 0.18)
            y1 = SH * 0.50 + s * SH * (r0 + 0.18) * 0.8
            pygame.draw.line(self.buf, col, (x0, y0), (x1, y1), 1)

    # ---------- hud ----------
    def draw(self, win):
        self.draw_scene()
        postfx.finish(self.buf)
        self.blit(win)
        if self.flash > 0.01:
            self.flash_surf.set_alpha(int(85 * self.flash))
            win.blit(self.flash_surf, (0, 0))
        self.draw_hud(win)
        if self.mode == 'result':
            self.draw_result(win)
        if self.flash > 0.01:
            self.flash_surf.set_alpha(int(85 * self.flash))
            win.blit(self.flash_surf, (0, 0))
        if self.paused:
            self.draw_pause(win)
        mouse = pygame.mouse.get_pos()
        hand = False
        if self.paused:
            hand = any(b.hit(mouse) for b in (self.resume_btn, self.abort_btn,
                                              self.mute_btn))
        elif self.mode == 'result':
            hand = (self.again_btn.hit(mouse) or self.home_btn.hit(mouse)
                    or (self.next_ready() and self.next_btn.hit(mouse)))
        set_cursor(hand)

    def draw_hud(self, win):
        sec = self.sec
        n = self.total_cores()

        text(win, 28, 64, 'CORE RUN', 9, 'mono', mix(DIM, PANEL, 0.55),
             track=2.2)
        text(win, 28, 77, '{} · {}'.format(sec['name'], sec['sub']), 16, 'tech',
             WHITE, track=1.8)
        text(win, 28, 102, 'T+ {:05.1f}'.format(self.time), 10, 'mono', TEAL,
             track=1.4)
        text(win, 28, 118, sec['challenge'], 10, 'mono', GOLD, track=1.6)
        if self.streak > 1:
            text(win, 28, 134, 'STREAK {}'.format(self.streak), 9, 'mono',
                 GOLD, track=1.2)

        text(win, W / 2, 58, 'SCORE', 9, 'bold', mix(SOFT, PANEL, 0.55), 'c',
             track=3.2)
        text(win, W / 2, 71, '{:,}'.format(self.score), 32, 'tech', GOLD, 'c',
             track=1.2)
        if self.combo > 1.02:
            text(win, W / 2, 113, 'COMBO  ×{:.1f}'.format(self.combo), 10,
                 'mono', TEAL, 'c', track=1.6)

        text(win, 1252, 65, 'CORE {:02d} / {:02d}'.format(
            min(self.core_i + (0 if self.mode == 'outro' else 1), n), n),
             11, 'mono', SOFT, 'r', track=1.4)
        bar(win, 1130, 86, 122, 3, self.core_i / max(1, n), GOLD)
        text(win, 1252, 97, 'BEST {:,}'.format(max(self.best, self.score)), 9,
             'mono', mix(DIM, PANEL, 0.5), 'r', track=1.2)

        panel(win, 22, 604, 236, 692, PANEL, 0.72, radius=8,
              outline=(30, 46, 72))
        text(win, 36, 613, 'TELEMETRY', 9, 'bold', mix(SOFT, PANEL, 0.5),
             track=1.8)
        text(win, 36, 634, 'SPEED', 9, 'mono', mix(DIM, PANEL, 0.5), track=1.2)
        text(win, 196, 627, '{}'.format(int(self.speed * 8.4)), 16, 'tech',
             WHITE, 'r')
        text(win, 201, 631, 'KM/H', 8, 'mono', mix(DIM, PANEL, 0.5))
        text(win, 36, 658, 'ALT', 9, 'mono', mix(DIM, PANEL, 0.5), track=1.2)
        text(win, 196, 651, '{:.0f}'.format((self.y + 1.5) * 24), 14, 'tech',
             SOFT, 'r')
        text(win, 201, 655, 'M', 8, 'mono', mix(DIM, PANEL, 0.5))
        tb = self.stats['balance']
        text(win, 36, 678, 'TRIM', 8.5, 'mono', mix(DIM, PANEL, 0.5), track=1.2)
        text(win, 196, 673, '{:.0f}%'.format(tb), 9, 'mono',
             GOLD if tb < 99.5 else mix(SOFT, PANEL, 0.35), 'r', track=0.8)
        if tb < 99.5:
            text(win, 232, 678, 'DRIFT', 7.5, 'mono',
                 mix(GOLD, PANEL, 0.35), 'r', track=0.8)

        panel(win, 244, 650, 420, 700, PANEL, 0.72, radius=8,
              outline=(30, 46, 72))
        text(win, 258, 658, 'AUTOPILOT ENGAGED', 8.5, 'mono',
             mix(SOFT, PANEL, 0.55), track=1.2)
        text(win, 258, 671, sec['challenge'], 10, 'mono', GOLD, track=1.2)
        text(win, 258, 687, 'WIND {:.1f}  ·  TURB {:.0f}%'.format(
            sec.get('wind', 0.0), 100 * sec.get('turb', 0.0)), 8, 'mono',
             mix(DIM, PANEL, 0.55), track=0.8)

        panel(win, 430, 646, 850, 700, PANEL, 0.72, radius=8,
              outline=(30, 46, 72))
        text(win, 446, 655, 'BOOST', 9, 'bold',
             TEAL if self.boost_fx > 0.1 else mix(SOFT, PANEL, 0.5), track=2.0)
        bar(win, 446, 674, 388, 6, self.energy / self.max_energy, TEAL,
            bg=(22, 36, 58))
        text(win, 446, 683, 'AUTO BURN  ·  TEAL PADS REFILL  ·  TRIM SETS DRIFT',
             8.5, 'mono', mix(DIM, PANEL, 0.5), track=1.0)
        text(win, 834, 683, '{:.0f}%'.format(100 * self.energy / self.max_energy),
             9, 'mono', SOFT, 'r', track=0.8)

        text(win, 1252, 689, 'ESC ABORT', 9, 'mono', mix(DIM, PANEL, 0.35),
             'r', track=1.2)

        if self.mode == 'intro':
            k = smooth(clamp(self.intro_t / 0.35)) * smooth(
                clamp((1.35 - self.intro_t) / 0.35))
            text(win, W / 2, 250, sec['name'], 40, 'tech', WHITE, 'c', 8.0, k)
            text(win, W / 2, 302, '{}  ·  {} CORES  ·  {} MINES  ·  {}'.format(
                sec['sub'], sec['cores'], sec['mines'], sec['challenge']), 11,
                'mono', TEAL, 'c', 3.0, k)
            text(win, W / 2, 328, 'AUTOPILOT ENGAGED  ·  YOUR TRIM IS THE TEST',
                 10, 'mono', mix(SOFT, PANEL, 0.45), 'c', 2.0, k * 0.9)
            if self.fault:
                text(win, W / 2, 352,
                     'AIRFRAME RISK  ·  {}  ·  STRUCTURAL FAILURE LIKELY'
                     .format(self.fault[0]), 10, 'mono', GOLD, 'c', 2.2, k)

        if self.miss_t > 0:
            a = clamp(self.miss_t / 1.0)
            text(win, W / 2, 560, 'CORE MISSED', 13, 'mono', RED, 'c', 2.4, a)

        if self.mode == 'crash':
            k = clamp(1.0 - self.crash_t / 2.2)
            draw_glow(win, W / 2, 296, 260, RED, 0.16 * k)
            text(win, W / 2, 268, 'IMPACT', 30, 'tech', RED, 'c', 8.0, k)
            text(win, W / 2, 312, self.crash_reason, 11, 'mono',
                 mix(RED, PANEL, 0.30), 'c', 3.4, k)

        for p in self.popups:
            if self.cam is None:
                continue
            q, _ = cam_proj(self.cam, (p['x'], p['y'], p['z']))
            if q is None:
                continue
            k = 1.0 - clamp(p['age'] / 1.4)
            hx = q[0] / SW * W
            hy = q[1] / SH * H - p['age'] * 40
            col = p['col']
            draw_glow(win, hx, hy, 60, col, 0.22 * k)
            text(win, hx, hy - 20, p['text'], 16, 'tech', col, 'c', 2.0, k)
            if p['sub']:
                text(win, hx, hy, p['sub'], 9, 'mono', mix(col, PANEL, 0.4),
                     'c', 2.0, k)

        if self.mode == 'outro':
            k = ease(clamp(self.outro_t / 0.4))
            glowk = 0.22 * k
            draw_glow(win, W / 2, H * 0.44, 300, WHITE, glowk)
            panel(win, W / 2 - 235, H * 0.44 - 31, W / 2 + 235, H * 0.44 + 31,
                  (9, 16, 30), 0.96 * k, radius=8,
                  outline=mix(TEAL, (9, 16, 30), 0.55))
            pygame.draw.rect(win, mix(TEAL, (9, 16, 30), 0.55),
                             (int(W / 2 - 223), int(H * 0.44 - 23), 3, 46),
                             border_radius=2)
            text(win, W / 2 + 6, H * 0.44 - 20, 'TEST COMPLETE', 22, 'tech',
                 WHITE, 'c', 5.0, k)
            text(win, W / 2 + 6, H * 0.44 + 10, 'SECTOR {:02d}  ·  SCORE LOCKED'.format(
                self.sector_i + 1), 10, 'mono', mix(TEAL, (9, 16, 30), 0.6),
                 'c', 3.0, k)

    def draw_result(self, win):
        a = ease(clamp(self.result_t / 0.35))
        panel(win, 0, 0, W, H, (5, 9, 18), 0.74 * a, radius=0)
        x0, y0, x1, y1 = 320, 140, 960, 580
        yoff = (1 - a) * 24
        panel(win, x0, y0 + yoff, x1, y1 + yoff, PANEL, 0.97, radius=14,
              outline=(48, 68, 102))
        accent = RED if self.crashed else GOLD
        pygame.draw.rect(win, mix(accent, PANEL, 0.5), (x0 + 1, y0 + yoff + 22, 3, 46),
                         border_radius=2)
        text(win, W / 2, y0 + 24 + yoff,
             'AIRFRAME LOST' if self.crashed else 'TEST COMPLETE', 28, 'tech',
             WHITE, 'c', 5.0, a)
        sub = self.crash_reason if self.crashed else self.sec['sub']
        text(win, W / 2, y0 + 62 + yoff, '{}  ·  {}  ·  {}'.format(
            self.sec['name'], sub, self.sec['challenge']), 10, 'mono',
             mix(DIM, PANEL, 0.4), 'c', 2.4, a)
        pygame.draw.line(win, (34, 52, 80), (x0 + 40, y0 + 88 + yoff),
                         (x1 - 40, y0 + 88 + yoff), 1)
        msg, mcol = self.status_line()
        if msg:
            text(win, W / 2, y0 + 95 + yoff, msg, 10.5, 'mono', mcol, 'c', 1.8, a)

        grade_col = {'S': GOLD, 'A': TEAL, 'B': CYAN, 'C': SOFT,
                     'F': RED}[self.grade]
        cx, cy = x0 + 130, y0 + 205 + yoff
        pygame.draw.circle(win, mix(grade_col, PANEL, 0.75), (cx, cy), 52)
        pygame.draw.circle(win, grade_col, (cx, cy), 52, 2)
        text(win, cx, cy - 34, self.grade, 56, 'tech', grade_col, 'c', 0)
        text(win, cx, cy + 60, 'RATING', 9, 'mono', mix(DIM, PANEL, 0.4), 'c',
             track=2.0)

        rows = (
            ('CORES COLLECTED', '{:02d} / {:02d}'.format(
                self.hits, self.total_cores()), WHITE),
            ('NEAR MISSES', '{:02d}'.format(self.dodges), CYAN),
            ('SCORE', '{:,}'.format(self.score), GOLD),
            ('BEST', '{:,}'.format(self.best), SOFT),
            ('CREDITS EARNED', '+{:,}'.format(self.reward), TEAL),
        )
        for i, (lab, val, col) in enumerate(rows):
            yy = y0 + 118 + i * 36 + yoff
            lcol = mix(DIM, PANEL, 0.5)
            if i == 3 and self.new_best:
                lab = 'BEST  ·  NEW RECORD'
                lcol = GOLD
            text(win, x0 + 250, yy, lab, 10, 'mono', lcol,
                 track=1.8, alpha=a)
            text(win, x1 - 40, yy - 4, val, 17, 'tech', col, 'r', alpha=a)
            pygame.draw.line(win, (24, 38, 60), (x0 + 250, yy + 24),
                             (x1 - 40, yy + 24), 1)

        mouse = pygame.mouse.get_pos()
        show_next = self.next_ready()
        if show_next:
            self.again_btn.rect = pygame.Rect(340, 470, 196, 52)
            self.next_btn.rect = pygame.Rect(548, 470, 200, 52)
            self.home_btn.rect = pygame.Rect(760, 470, 190, 52)
        else:
            self.again_btn.rect = pygame.Rect(350, 470, 290, 52)
            self.home_btn.rect = pygame.Rect(660, 470, 270, 52)
        self.again_btn.draw(win, self.again_btn.hit(mouse), True, a)
        if show_next:
            nxt = SECTORS[self.unlocked_now]
            price = nxt['price']
            self.next_btn.label = 'NEXT · {:02d}'.format(self.unlocked_now + 1)
            self.next_btn.sub = '{:,} CR'.format(price)
            self.next_btn.draw(win, self.next_btn.hit(mouse), True, a)
        self.home_btn.draw(win, self.home_btn.hit(mouse), True, a)
        hint = ('R RETRY  ·  N NEXT SECTOR  ·  ESC HANGAR' if show_next
                else 'PRESS R TO FLY AGAIN  ·  ESC FOR HANGAR')
        text(win, W / 2, y1 - 28 + yoff, hint,
             9, 'mono', mix(DIM, PANEL, 0.45), 'c', track=1.4, alpha=a)

    def status_line(self):
        if self.crashed:
            return '', GOLD
        if self.unlocked_now is not None:
            nxt = self.unlocked_now
            price = SECTORS[nxt]['price']
            if self.app.state['credits'] >= price:
                return 'SECTOR {:02d} READY · {:,} CR'.format(nxt + 1, price), GOLD
            return 'SECTOR {:02d} UNLOCKED · {:,} CR IN HANGAR'.format(
                nxt + 1, price), GOLD
        if self.campaign_done:
            return 'CAMPAIGN COMPLETE · +{:,} CR BONUS'.format(
                self.campaign_bonus), GOLD
        if self.cleared_now:
            return 'SECTOR CLEARED', TEAL
        return '', GOLD

    def draw_pause(self, win):
        a = ease(clamp(self.pause_t))
        panel(win, 0, 0, W, H, (5, 9, 18), 0.72 * a, radius=0)
        x0, y0, x1, y1 = 400, 232, 880, 548
        panel(win, x0, y0, x1, y1, PANEL, 0.97, radius=14, outline=(48, 68, 102))
        text(win, W / 2, y0 + 26, 'PAUSED', 26, 'tech', WHITE, 'c', 6.0, a)
        text(win, W / 2, y0 + 64, '{}  ·  {}'.format(self.sec['name'], self.sec['sub']),
             10, 'mono', mix(SOFT, PANEL, 0.55), 'c', 2.2, a)
        text(win, W / 2, y0 + 84, 'SCORE {:,}  ·  CORE {:02d} / {:02d}'.format(
            self.score, self.core_i, self.total_cores()), 10, 'mono',
            mix(SOFT, PANEL, 0.45), 'c', 1.4, a)
        mouse = pygame.mouse.get_pos()
        self.resume_btn.draw(win, self.resume_btn.hit(mouse), True, a)
        self.abort_btn.draw(win, self.abort_btn.hit(mouse), True, a)
        self.mute_btn.label = 'SOUND OFF  ·  M' if audio.muted else 'SOUND ON  ·  M'
        self.mute_btn.draw(win, self.mute_btn.hit(mouse), True, a)
        text(win, W / 2, y1 - 30, 'ESC RESUME  ·  M SOUND', 9, 'mono',
             mix(DIM, PANEL, 0.45), 'c', 1.4, a)
