import math
import random

import pygame

from config import (SW, SH, W, H, PANEL, WHITE, SOFT, DIM, TEAL,
                    GOLD, RED, CYAN, SECTORS, CLEAR_RATIO, GRADE_ORDER,
                    CAMPAIGN_BONUS)
from render3d import (make_cam, cam_proj, draw_glow, draw_parts, clamp, mix,
                      ease, smooth)
from scene_base import Scene
from ship import build_ship, compute_stats
from ui import panel, text, bar, Button, set_cursor
import audio

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
        self.bot_col = (6, 10, 22)
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

    def crash(self, reason):
        if self.mode != 'run':
            return
        self.mode = 'crash'
        self.crashed = True
        self.crash_reason = reason
        self.crash_t = 0.0
        self.shake = 1.0
        self.flash = 1.0
        audio.play('crash', 0.9)
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
        for _ in range(34):
            a = rng.uniform(0, 2 * math.pi)
            sp = rng.uniform(2.0, 8.0)
            self.sparks.append({
                'pos': [self.x, self.y, self.z],
                'vel': [math.cos(a) * sp, rng.uniform(-1.0, 6.0),
                        math.sin(a) * sp],
                'life': rng.uniform(0.45, 1.5),
                'col': GOLD if rng.random() < 0.62 else TEAL,
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
        self.draw_ridge(cam)
        self.draw_canyon(cam)
        self.draw_track(cam)
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

    def draw_sky_fx(self, cam):
        q, dep = cam_proj(cam, (-30.0, 7.0, self.z + 160.0))
        if q is not None:
            x, y = q
            draw_glow(self.buf, x, y, 360, (255, 186, 112), 0.30)
            draw_glow(self.buf, x, y, 150, (255, 224, 178), 0.34)
        hz, _ = cam_proj(cam, (0.0, 1.6, self.z + 160.0))
        if hz is not None:
            draw_glow(self.buf, SW * 0.5, hz[1], 520, self.sec['line'], 0.10)

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
            for i in range(-16, 17):
                x = i * 2.6
                h = (0.55 + 0.45 * math.sin(x * 0.31 + zf * 0.05)) * \
                    (0.60 + 0.40 * math.sin(x * 0.11 - zf * 0.03))
                p, _ = cam_proj(cam, (x, h * amp + lift, zf))
                if p is not None:
                    top.append((p[0], min(p[1], floor - 1)))
            if len(top) < 3:
                continue
            far = clamp((dist - 70.0) / 120.0)
            fill = mix(mix(base, (10, 17, 34), 0.18), self.top_col,
                       0.24 + 0.30 * far)
            poly = [(SW * -0.3, floor), (SW * 1.3, floor)]
            poly += list(reversed(top))
            pygame.draw.polygon(self.buf, fill, poly)
            pygame.draw.lines(self.buf, mix(fill, base, 0.22), False, top, 1)

    def draw_canyon(self, cam):
        base = self.sec['line']
        for side in (-1, 1):
            for i in range(12):
                z0 = self.z + 6.0 + i * 7.0
                z1 = z0 + 7.0
                h0 = 1.0 + 0.9 * (0.5 + 0.5 * math.sin(i * 0.9 + side * 1.7))
                h1 = 1.0 + 0.9 * (0.5 + 0.5 * math.sin((i + 1) * 0.9
                                                       + side * 1.7))
                x0 = side * (10.2 + 0.5 * math.sin(i * 0.5 + side))
                x1 = side * (10.2 + 0.5 * math.sin((i + 1) * 0.5 + side))
                a, _ = cam_proj(cam, (x0, FLOOR_Y, z0))
                b, _ = cam_proj(cam, (x0, h0, z0))
                c, _ = cam_proj(cam, (x1, h1, z1))
                d, _ = cam_proj(cam, (x1, FLOOR_Y, z1))
                if None in (a, b, c, d):
                    continue
                shade = 0.24 + 0.08 * ((i * 3 + (side > 0)) % 3)
                col = mix(base, (7, 12, 24), 1.0 - shade)
                pygame.draw.polygon(self.buf, col, [b, a, d, c])
                pygame.draw.line(self.buf, mix(base, (34, 52, 84), 0.62),
                                 b, c, 1)
                for fr in (0.28, 0.55, 0.78):
                    p0 = (a[0] + (d[0] - a[0]) * fr,
                          a[1] + (d[1] - a[1]) * fr)
                    p1 = (b[0] + (c[0] - b[0]) * fr,
                          b[1] + (c[1] - b[1]) * fr)
                    pygame.draw.line(self.buf, mix(col, (6, 10, 20), 0.55),
                                     p0, p1, 1)

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
        if self.crash_t < 0.4:
            q, dep = cam_proj(cam, (self.x, self.y, self.z))
            if q is not None:
                k = 1.0 - self.crash_t / 0.4
                draw_glow(self.buf, q[0], q[1], 120 + 420 * self.crash_t,
                          GOLD, 0.75 * k)
                draw_glow(self.buf, q[0], q[1], 90 + 260 * self.crash_t,
                          WHITE, 0.55 * k)
        for s in self.sparks:
            q, dep = cam_proj(cam, s['pos'])
            if q is None:
                continue
            k = clamp(s['life'] / 0.9)
            draw_glow(self.buf, q[0], q[1], clamp(340.0 / dep, 7, 40),
                      s['col'], 0.60 * k)

    def draw_ship_shadow(self, cam, bob):
        q, dep = cam_proj(cam, (self.x, FLOOR_Y, self.z))
        if q is None:
            return
        f = clamp(200.0 / max(6.0, dep), 0.5, 1.6)
        for i, k in enumerate((1.0, 0.72, 0.45)):
            c = mix((6, 10, 20), (26, 40, 62), 0.25 + 0.35 * i)
            w = 180 * k * f
            h = 42 * k * f
            pygame.draw.ellipse(self.buf, c, (int(q[0] - w), int(q[1] - h),
                                              int(2 * w), int(2 * h)))

    def draw_track(self, cam):
        line_col = self.sec['line']
        z0 = int(self.z) - 6
        z1 = int(self.z) + 72
        for k in range(z0 - (z0 % 4), z1, 4):
            s0, _ = cam_proj(cam, (-16, FLOOR_Y, k))
            s1, _ = cam_proj(cam, (16, FLOOR_Y, k))
            if s0 is None or s1 is None:
                continue
            dz = k - self.z
            a = clamp((70 - dz) / 55.0) * 0.42
            if a <= 0.01:
                continue
            pygame.draw.line(self.buf, mix(line_col, (10, 18, 34), a),
                             (s0[0], s0[1]), (s1[0], s1[1]), 1)
        for x in range(-16, 17, 2):
            s0, _ = cam_proj(cam, (x, FLOOR_Y, self.z + 2))
            s1, _ = cam_proj(cam, (x, FLOOR_Y, self.z + 70))
            if s0 is None or s1 is None:
                continue
            pygame.draw.line(self.buf, mix(line_col, (10, 18, 34), 0.34),
                             (s0[0], s0[1]), (s1[0], s1[1]), 1)
        # lane edge lights and pylons
        for k in range(z0 - (z0 % 8), z1, 8):
            dz = k - self.z
            if dz < 2:
                continue
            fade = clamp((72 - dz) / 40.0) * 0.8
            for sx in (-4.4, 4.4):
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
        k = self.boost_fx
        for i in range(14):
            a = self.t * 2.6 + i * 2.399
            r0 = 0.42 + (i % 4) * 0.06
            c, s = math.cos(a), math.sin(a)
            x0 = SW * 0.5 + c * SW * r0
            y0 = SH * 0.50 + s * SH * r0 * 0.8
            x1 = SW * 0.5 + c * SW * (r0 + 0.18)
            y1 = SH * 0.50 + s * SH * (r0 + 0.18) * 0.8
            pygame.draw.line(self.buf, mix(CYAN, (10, 18, 34), 0.62),
                             (x0, y0), (x1, y1), 1)

    # ---------- hud ----------
    def draw(self, win):
        self.draw_scene()
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
