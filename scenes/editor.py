import math

import pygame

from config import (SW, SH, PANEL, PANEL_L, WHITE, SOFT, DIM, TEAL, GOLD,
                    RED, CYAN, MATERIALS, MAX_CUSTOM)
from parts import ROTORS, rotor_stats, craft_cost
from hud import topbar
from render3d import (make_cam, draw_floor, draw_shadow, draw_parts,
                      draw_model_glow, mix)
from scene_base import Scene
from ship import build_ship, compute_stats
from ui import panel, text, coin, bar, Button, Slider, set_cursor
import audio

RX0, RX1 = 780, 1264
DEFAULTS = {'span': 0.32, 'chord': 0.085, 'blades': 12, 'sweep': 0.0,
            'thickness': 0.014, 'material': 'alloy'}


class Editor(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.params = dict(DEFAULTS)
        self.sliders = [
            Slider('span', 'SPAN', 0.24, 0.46, self.params['span'], '{:.2f}', 0.005),
            Slider('chord', 'CHORD', 0.05, 0.13, self.params['chord'], '{:.3f}', 0.002),
            Slider('blades', 'BLADES', 3, 12, self.params['blades'], '{:.0f}', 1),
            Slider('sweep', 'SWEEP', -0.25, 0.25, self.params['sweep'], '{:+.2f}', 0.01),
            Slider('thickness', 'THICKNESS', 0.008, 0.030, self.params['thickness'],
                   '{:.3f}', 0.001),
        ]
        for i, s in enumerate(self.sliders):
            s.place(796, 168 + i * 52, RX1 - 796 - 16)
        self.mat_rects = []
        self.back_btn = Button('back', (32, 660, 118, 40), 'BACK', 'ghost', 11,
                               'mono', 2.0)
        self.reset_btn = Button('reset', (158, 660, 118, 40), 'RESET', 'ghost',
                                11, 'mono', 2.0)
        self.publish_btn = Button('publish', (796, 546, RX1 - 796 - 16, 56),
                                  'FABRICATE', 'gold', 16, 'mono', 2.6)
        self.material = MATERIALS[0]
        self.parts = []
        self.stats = {}
        self.rstats = {}
        self.rebuild()

    def next_index(self):
        mx = 0
        for e in self.app.state['custom']:
            try:
                mx = max(mx, int(str(e['id']).rsplit('_', 1)[1]))
            except (IndexError, ValueError):
                pass
        return mx + 1

    def rotor_name(self):
        return 'MK-{:02d}'.format(self.next_index())

    def rebuild(self):
        for s in self.sliders:
            self.params[s.key] = s.value
        self.params['blades'] = int(round(self.params['blades']))
        self.rstats = rotor_stats(**self.params)
        self.entry = {
            'id': 'preview', 'slot': 'rotor', 'name': self.rotor_name(),
            'price': 0, 'desc': 'CUSTOM ROTOR SET', 'accent': GOLD,
            'params': dict(self.params), 'stats': self.rstats, 'custom': True,
        }
        tmp = {'selected': dict(self.app.state['selected']), 'custom': [self.entry],
               'paint': self.app.state.get('paint', 'factory')}
        tmp['selected']['rotor'] = 'preview'
        self.parts = build_ship(tmp)
        self.stats = compute_stats(tmp)

    def cost(self):
        return craft_cost(self.params['material'])

    def enter(self):
        self.rebuild()

    # ---------- input ----------
    def handle(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                audio.play('click')
                self.app.set_scene('hangar')
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.publish()
            return

        changed = False
        for s in self.sliders:
            if s.handle(e):
                changed = True
                break
        if changed:
            self.rebuild()
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.mat_rects):
                if r.collidepoint(e.pos):
                    if self.params['material'] != MATERIALS[i]['id']:
                        self.params['material'] = MATERIALS[i]['id']
                        audio.play('click')
                        self.rebuild()
                    return
            if self.back_btn.hit(e.pos):
                audio.play('click')
                self.app.set_scene('hangar')
                return
            if self.reset_btn.hit(e.pos):
                for s in self.sliders:
                    s.value = DEFAULTS[s.key]
                self.params['material'] = 'alloy'
                audio.play('click')
                self.rebuild()
                return
            if self.publish_btn.hit(e.pos):
                self.publish()

    def publish(self):
        st = self.app.state
        if len(st['custom']) >= MAX_CUSTOM:
            audio.play('error')
            self.app.toast('FORGE FULL', 'SCRAP A CUSTOM ROTOR IN THE HANGAR', RED)
            return
        cost = self.cost()
        if st['credits'] < cost:
            audio.play('error')
            self.app.toast('NOT ENOUGH CREDITS', 'NEED {:,} MORE'.format(
                cost - st['credits']), RED)
            return
        for s in self.sliders:
            self.params[s.key] = s.value
        self.params['blades'] = int(round(self.params['blades']))
        n = self.next_index()
        entry = {
            'id': 'custom_{}'.format(n), 'slot': 'rotor',
            'name': 'MK-{:02d}'.format(n), 'price': 0,
            'desc': 'CUSTOM ROTOR SET', 'accent': GOLD,
            'params': dict(self.params), 'stats': rotor_stats(**self.params),
            'custom': True,
        }
        st['custom'].append(entry)
        st['credits'] -= cost
        st['selected']['rotor'] = entry['id']
        self.app.save()
        audio.play('hammer')
        self.app.toast('ROTOR FABRICATED',
                       '{} READY · BOLT IN BAY 07  ·  -{:,} CR'.format(
                           entry['name'], cost),
                       GOLD)
        self.app.set_scene('hangar')

    # ---------- draw ----------
    def draw_scene(self):
        self.base_sky()
        yaw = 0.66 + 0.20 * math.sin(self.t * 0.30)
        cam = make_cam(yaw, 0.38, 0.0, 208, SW * 0.305, SH * 0.54)
        draw_floor(self.buf, cam, pad=1.0, t=self.t)
        draw_shadow(self.buf, cam, r=1.05, a=0.8)
        pulse = 0.85 + 0.15 * math.sin(self.t * 3.0)
        draw_parts(self.buf, cam, self.parts, spin=self.t * 9.0, pulse=pulse)
        draw_model_glow(self.buf, cam, self.parts, None, pulse=pulse)

    def draw(self, win):
        self.draw_scene()
        self.blit(win)
        st = self.app.state
        sec = self.app.state.get('sector', 0)
        topbar(win, st['credits'], self.app.coin_spin)
        self.draw_left(win)
        self.draw_panel(win)
        mouse = pygame.mouse.get_pos()
        hand = (self.back_btn.hit(mouse) or self.reset_btn.hit(mouse)
                or self.publish_btn.hit(mouse)
                or any(r.collidepoint(mouse) for r in self.mat_rects)
                or any(s.rect.inflate(12, 18).collidepoint(mouse)
                       for s in self.sliders))
        set_cursor(hand)

    def draw_left(self, win):
        mouse = pygame.mouse.get_pos()
        text(win, 32, 74, 'ROTOR FORGE', 21, 'tech', WHITE, track=3.4)
        text(win, 32, 101, 'PARAMETRIC DESIGN  ·  QUAD SET ×4', 9.5, 'mono',
             mix(DIM, PANEL, 0.55), track=1.8)

        panel(win, 32, 120, 190, 150, (14, 38, 42), 0.9, radius=6,
              outline=mix(TEAL, PANEL, 0.45))
        pygame.draw.circle(win, TEAL, (46, 135), 3)
        text(win, 56, 126, 'LIVE PREVIEW', 9, 'mono', TEAL, track=1.4)

        text(win, 32, 164, self.rotor_name(), 18, 'tech', GOLD, track=2.2)
        text(win, 32, 188, 'CUSTOM QUAD LIFT SET  ·  {}'.format(
            self.material['name']), 9.5, 'mono', mix(SOFT, PANEL, 0.45),
            track=1.4)

        text(win, 32, 636, 'SLIDE TO RESHAPE THE MESH — STATS UPDATE LIVE',
             9, 'mono', mix(DIM, PANEL, 0.45), track=1.0)
        self.back_btn.draw(win, self.back_btn.hit(mouse), True)
        self.reset_btn.draw(win, self.reset_btn.hit(mouse), True)

        text(win, 300, 690, 'ESC / BACK TO HANGAR', 9, 'mono',
             mix(DIM, PANEL, 0.4), track=1.2)

    def draw_panel(self, win):
        st = self.app.state
        mouse = pygame.mouse.get_pos()
        panel(win, RX0, 68, RX1, 652, PANEL, 0.90, radius=12,
              outline=(34, 52, 80))
        text(win, 796, 79, 'FORGE PARAMETERS', 13, 'bold', SOFT, track=2.2)
        text(win, RX1 - 16, 80, 'ROTOR ONLY', 9, 'mono', mix(DIM, PANEL, 0.5),
             'r', track=1.4)

        text(win, 796, 104, 'MATERIAL', 10, 'bold', mix(SOFT, PANEL, 0.55),
             track=1.8)
        self.mat_rects = []
        for i, m in enumerate(MATERIALS):
            r = pygame.Rect(796 + i * 152, 120, 144, 34)
            self.mat_rects.append(r)
            sel = self.params['material'] == m['id']
            hov = r.collidepoint(mouse)
            if sel:
                panel(win, r.x, r.y, r.right, r.bottom, (16, 38, 42), 0.95,
                      radius=6, outline=TEAL)
            else:
                panel(win, r.x, r.y, r.right, r.bottom, PANEL_L,
                      0.9 if hov else 0.6, radius=6,
                      outline=(58, 86, 124) if hov else (34, 50, 76))
            text(win, r.x + 9, r.y + 4, m['name'], 10, 'mono',
                 TEAL if sel else (SOFT if hov else mix(DIM, PANEL, 0.35)),
                 track=1.0)
            text(win, r.x + 9, r.y + 20, m['desc'], 8, 'mono',
                 mix(DIM, PANEL, 0.45), track=0.8)

        for s in self.sliders:
            s.draw(win, 1.0, TEAL if s.key != 'sweep' else CYAN)

        text(win, 796, 425, 'LIVE OUTPUT  ·  ONE ROTOR SET', 10, 'bold',
             mix(SOFT, PANEL, 0.45), track=1.8)
        rs = self.rstats
        std = ROTORS[0]['stats']
        cells = (
            ('THRUST', rs['thrust'], std['thrust'], 300.0, TEAL, 'higher'),
            ('MASS', rs['mass'], std['mass'], 90.0, SOFT, 'lower'),
            ('DRAG', rs['drag'], std['drag'], 8.0, RED, 'lower'),
            ('AGILITY', rs['agility'], std['agility'], 25.0, CYAN, 'higher'),
        )
        for i, (lab, val, base, cap, col, good) in enumerate(cells):
            x = 796 + (i % 2) * 232
            y = 446 + (i // 2) * 34
            text(win, x, y, lab, 9, 'mono', mix(DIM, PANEL, 0.55), track=1.2)
            text(win, x + 200, y - 2, '{:.1f}'.format(val), 12.5, 'mono', col, 'r')
            delta = val - base
            if abs(delta) > 0.05:
                dcol = col if ((delta > 0) == (good == 'higher')) else RED
                text(win, x + 62, y + 1, '{:+.1f}'.format(delta), 8.5, 'mono',
                     dcol, track=0.6)
            bar(win, x, y + 16, 200, 3, val / cap, col, bg=(22, 36, 58))

        cost = self.cost()
        text(win, 796, 514, 'CRAFT COST', 10, 'mono', mix(SOFT, PANEL, 0.55),
             track=1.6)
        afford = st['credits'] >= cost
        coin(win, 1146, 522, 7, self.app.coin_spin)
        text(win, 1248, 511, '{:,}'.format(cost), 16, 'tech',
             GOLD if afford else RED, 'r')
        text(win, 796, 532, 'BALANCE {:,}'.format(st['credits']), 8.5, 'mono',
             mix(DIM, PANEL, 0.45), 'l', track=0.8)

        self.publish_btn.label = 'FABRICATE  ·  ' + self.rotor_name()
        self.publish_btn.sub = '{}  ·  {} CREDITS'.format(
            self.material['name'], cost)
        self.publish_btn.draw(win, self.publish_btn.hit(mouse) and afford,
                              afford, 1.0)
        text(win, 796, 611,
             'MORE BLADE AREA = MORE LIFT, BUT MASS + DRAG RISE TOO',
             9, 'mono', mix(DIM, PANEL, 0.42), track=0.9)
