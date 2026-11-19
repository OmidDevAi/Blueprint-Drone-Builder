import math

import pygame

from config import (SW, SH, W, H, PANEL, PANEL_L, WHITE, SOFT, DIM, TEAL, GOLD,
                    RED, CYAN, SECTORS, PAINTS)
from parts import (CATALOG, SLOT_ORDER, SLOT_LABEL, SOCKETS, SOCKET_LABEL,
                   entry_stats, unit_stats, paint_scheme)
from hud import topbar, stat_row
from render3d import (make_cam, cam_proj, draw_parts,
                      draw_model_glow, draw_glow, clamp, mix)
from scene_base import Scene
from scenes.bay import HangarBay
from ship import (build_ship, compute_stats, layout, socket_world, body_scale,
                  entry_at)
from ui import (panel, text, coin, bar, Button, ICONS, icon_lock,
                set_cursor, text_w)
import audio

LEFT_X0, LEFT_X1 = 16, 300
RX0, RX1 = 976, 1264
CARD_X0, CARD_X1 = 26, 290
TABS = SLOT_ORDER + ('paint',)
TAB_CELLS = TABS + ('forge',)
TAB_LABEL = dict(SLOT_LABEL, paint='PAINT', forge='FORGE')
CARD_Y0, CARD_H, CARD_GAP = 214, 92, 8
CARD_VISIBLE = 4
PAINT_COLS = 2
PAINT_ROWS = 4
PAINT_GAP = 8
PAINT_CW = (CARD_X1 - CARD_X0 - PAINT_GAP) // 2
PAINT_H = 76
PERF_Y0, PERF_Y1 = 68, 432
CARD_AREA = pygame.Rect(CARD_X0, CARD_Y0, CARD_X1 - CARD_X0,
                        CARD_VISIBLE * (CARD_H + CARD_GAP) - CARD_GAP)
VIEW_X0, VIEW_Y0, VIEW_X1, VIEW_Y1 = 306, 60, 968, 620

# label, stat key, lo, hi, value format, higher-is-better
STAT_ROWS = {
    'body': (('MASS', 'mass', 0.0, 90.0, '{:.0f}', False),
             ('DRAG', 'drag', 0.0, 2.0, '{:.2f}', False),
             ('AGILITY', 'agility', -12.0, 18.0, '{:.0f}', True),
             ('LIFT', 'lift', 0.0, 6.0, '{:.0f}', True)),
    'frame': (('MASS', 'mass', 0.0, 28.0, '{:.0f}', False),
              ('DRAG', 'drag', 0.0, 0.55, '{:.2f}', False),
              ('REACH', 'reach', 0.8, 1.3, 'x{:.2f}', True),
              ('AGILITY', 'agility', -8.0, 10.0, '{:.0f}', True)),
    'rotor': (('THRUST', 'thrust', 0.0, 360.0, '{:.0f}', True),
              ('MASS', 'mass', 0.0, 55.0, '{:.0f}', False),
              ('DRAG', 'drag', 0.0, 5.5, '{:.2f}', False),
              ('AGILITY', 'agility', 0.0, 17.0, '{:.0f}', True)),
    'motor': (('THRUST', 'thrust', 0.0, 180.0, '{:.0f}', True),
              ('ENERGY', 'energy', 0.0, 100.0, '{:.0f}', True),
              ('MASS', 'mass', 0.0, 60.0, '{:.0f}', False),
              ('DRAG', 'drag', 0.0, 0.65, '{:.2f}', False)),
    'wing': (('LIFT', 'lift', 0.0, 44.0, '{:.0f}', True),
             ('AGILITY', 'agility', 0.0, 24.0, '{:.0f}', True),
             ('MASS', 'mass', 0.0, 30.0, '{:.0f}', False),
             ('DRAG', 'drag', 0.0, 2.0, '{:.2f}', False)),
    'booster': (('THRUST', 'thrust', 0.0, 128.0, '{:.0f}', True),
                ('BOOST', 'energy', 0.0, 130.0, '{:.0f}', True),
                ('MASS', 'mass', 0.0, 38.0, '{:.0f}', False),
                ('DRAG', 'drag', 0.0, 1.4, '{:.2f}', False)),
}


class Hangar(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.socket = ('body', 'c')
        self.slot = 'body'
        self.scroll = 0
        self.yaw_off = 0.0
        self.dragging = False
        self.drag_x = 0
        self.tab_rects = []
        self.card_rects = []
        self.sector_rects = []
        self.del_rects = []
        self.socket_hits = []
        self.del_arm = (None, 0.0)
        self.hover_info = None
        self.picks = {}
        self.fly_btn = Button('fly', (RX0, 444, RX1 - RX0, 58), 'AUTO FLY',
                              'gold', 17, 'mono', 2.8,
                              sub='SECTOR 01 · 8 CORES')
        self.forge_btn = Button('forge', (RX0, 510, RX1 - RX0, 46),
                                'PART CREATOR', 'ghost', 13, 'mono', 2.4,
                                sub='CUSTOM ROTOR FORGE')
        self.remove_btn = Button('remove', (846, 84, 76, 26), 'REMOVE',
                                 'ghost', 9, 'mono', 1.4)
        self.parts = []
        self.stats = {}
        self.lay = {}
        self.build_prog = {}
        self.installed_keys = set()
        self.sparks_fx = []
        self.assy_done_t = 0.0
        self.cam = None
        self.bay = HangarBay()
        self.rebuild()

    # ---------- data ----------
    def rebuild(self):
        self.parts = build_ship(self.app.state)
        self.stats = compute_stats(self.app.state)
        self.lay = layout(self.app.state)
        keys = set()
        for slot in ('body', 'frame'):
            if self.lay.get(slot):
                keys.add((slot, 'c'))
        for slot in ('rotor', 'motor', 'wing', 'booster'):
            for key, _ in SOCKETS[slot]:
                if self.lay[slot].get(key):
                    keys.add((slot, key))
        for k in list(self.build_prog):
            if k not in keys:
                del self.build_prog[k]
        for k in keys:
            self.build_prog.setdefault(k, 1.0)
        self.installed_keys = keys

    def enter(self):
        self.rebuild()
        self.focus_default()
        self.reveal_selected()
        self.start_assembly()

    def focus_default(self):
        if self.lay.get('body') is None:
            self.slot, self.socket = 'body', ('body', 'c')
        elif self.lay.get('frame') is None:
            self.slot, self.socket = 'frame', ('frame', 'c')
        elif self.slot not in TABS:
            self.slot = 'rotor'
            self.socket = ('rotor', self.first_open('rotor'))

    def start_assembly(self):
        order = []
        for slot in ('body', 'frame', 'rotor', 'motor', 'wing', 'booster'):
            if slot in ('body', 'frame'):
                if (slot, 'c') in self.installed_keys:
                    order.append((slot, 'c'))
                continue
            for key, _ in SOCKETS[slot]:
                if (slot, key) in self.installed_keys:
                    order.append((slot, key))
        for i, k in enumerate(order):
            self.build_prog[k] = -0.10 - 0.13 * i
        self.sparks_fx = []
        self.assy_done_t = 0.0

    def bolt(self, slot, key):
        self.build_prog[(slot, key)] = 0.0

    def assembling(self):
        return any(v < 1.0 for v in self.build_prog.values())

    def installed(self, slot, key):
        if slot in ('body', 'frame'):
            return self.lay.get(slot) is not None
        return bool(self.lay.get(slot, {}).get(key))

    def update(self, dt):
        super().update(dt)
        was = self.assembling()
        for k, v in list(self.build_prog.items()):
            if v < 1.0:
                nv = min(1.0, v + dt / 0.42)
                self.build_prog[k] = nv
                if nv >= 1.0:
                    self.sparks_fx.append({'slot': k[0], 'key': k[1],
                                           'age': 0.0,
                                           'seed': len(self.sparks_fx)})
                    audio.play('weld', 0.45)
        if was and not self.assembling():
            self.assy_done_t = 0.0
        elif not self.assembling():
            self.assy_done_t += dt
        for sp in self.sparks_fx:
            sp['age'] += dt
        self.sparks_fx = [sp for sp in self.sparks_fx if sp['age'] < 0.9]

    def items(self):
        return self.slot_items(self.slot)

    def sector(self):
        return SECTORS[int(clamp(self.app.state.get('sector', 0), 0, 2))]

    def cleared(self, i):
        return str(i) in self.app.state.get('cleared', {})

    def eligible(self, i):
        return i == 0 or self.cleared(i - 1)

    def objective_text(self):
        st = self.app.state
        if st.get('finished'):
            return 'CAMPAIGN COMPLETE · ALL SECTORS CLEARED'
        for i in range(len(SECTORS)):
            if i not in st['unlocked']:
                if i > 0 and not self.cleared(i - 1):
                    return 'CLEAR SECTOR {:02d} (B+) TO OPEN SECTOR {:02d}'.format(
                        i, i + 1)
                return 'SECTOR {:02d} AVAILABLE · {:,} CR TO UNLOCK'.format(
                    i + 1, SECTORS[i]['price'])
        return 'ALL SECTORS OPEN · BUY YOUR GEAR'

    def max_scroll(self):
        if self.slot == 'paint':
            rows = (len(PAINTS) + PAINT_COLS - 1) // PAINT_COLS
            return max(0, rows - PAINT_ROWS)
        return max(0, len(self.items()) - CARD_VISIBLE)

    def socket_entry(self):
        slot, key = self.socket
        return entry_at(self.app.state, self.lay, slot, key)

    def reveal_selected(self):
        slot, key = self.socket
        if slot == 'paint':
            return
        if slot in ('body', 'frame'):
            pid = self.lay.get(slot)
        else:
            pid = self.lay[slot].get(key)
        if not pid:
            self.scroll = 0
            return
        for i, e in enumerate(self.items()):
            if e['id'] == pid:
                self.scroll = int(clamp(i - (CARD_VISIBLE - 1), 0,
                                        self.max_scroll()))
                return

    def first_open(self, slot):
        if slot in ('body', 'frame'):
            return 'c'
        keys = [k for k, _ in SOCKETS[slot]]
        if slot == 'motor':
            for k in keys:
                if self.lay['rotor'].get(k) and not self.lay['motor'].get(k):
                    return k
        for k in keys:
            if not self.installed(slot, k):
                return k
        return keys[0]

    def next_open(self, slot, current):
        keys = [k for k, _ in SOCKETS[slot]]
        if current not in keys:
            return None
        i = keys.index(current)
        for k in keys[i + 1:] + keys[:i]:
            if slot == 'motor':
                if self.lay['rotor'].get(k) and not self.lay['motor'].get(k):
                    return k
            elif not self.installed(slot, k):
                return k
        return None

    def prereq(self, slot, key):
        """Build order: hull, then frame, then rotors, then one drive motor
        per rotor. Wings and boosters unlock with the frame."""
        if slot == 'body':
            return None
        if self.lay.get('body') is None:
            return 'FIT A HULL FIRST'
        if slot != 'frame' and self.lay.get('frame') is None:
            return 'FIT A FRAME FIRST'
        if slot == 'motor' and not self.lay['rotor'].get(key):
            return 'FIT A ROTOR HERE FIRST'
        return None

    def prereq_short(self, slot, key):
        block = self.prereq(slot, key)
        if not block:
            return ''
        if slot == 'motor':
            return 'NEED ROTOR'
        return 'FIT HULL' if self.lay.get('body') is None else 'FIT FRAME'

    def select_socket(self, slot, key):
        self.socket = (slot, key)
        self.slot = slot
        self.reveal_selected()
        audio.play('click')

    # ---------- input ----------
    def handle(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            elif e.key == pygame.K_m:
                on = not self.app.toggle_mute()
                self.app.toast('SOUND ON' if on else 'SOUND OFF',
                               'PRESS M TO TOGGLE', GOLD if on else DIM)
            elif e.key in (pygame.K_a, pygame.K_LEFT):
                self.yaw_off -= 0.16
            elif e.key in (pygame.K_d, pygame.K_RIGHT):
                self.yaw_off += 0.16
            elif e.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                self.remove_socket_part()
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_f):
                self.try_fly()
            elif e.key == pygame.K_c:
                audio.play('select')
                self.app.set_scene('editor')
            return

        if e.type == pygame.MOUSEWHEEL:
            if CARD_AREA.collidepoint(pygame.mouse.get_pos()):
                self.scroll = int(clamp(self.scroll - e.y, 0, self.max_scroll()))
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            pos = e.pos
            if self.installed(*self.socket) \
                    and self.socket[0] not in ('body', 'frame') \
                    and self.remove_btn.hit(pos):
                self.remove_socket_part()
                return
            for slot, key, r in self.socket_hits:
                if r.collidepoint(pos):
                    self.select_socket(slot, key)
                    return
            for eid, r in self.del_rects:
                if r.collidepoint(pos):
                    armed = self.del_arm[0] == eid and self.t - self.del_arm[1] < 2.5
                    if armed:
                        self.remove_custom(eid)
                    else:
                        self.del_arm = (eid, self.t)
                        audio.play('click')
                    return
            for i, r in enumerate(self.tab_rects):
                if r.collidepoint(pos):
                    tab = TAB_CELLS[i]
                    if tab == 'forge':
                        audio.play('select')
                        self.app.set_scene('editor')
                        return
                    self.slot = tab
                    if tab != 'paint':
                        self.socket = (tab, self.first_open(tab))
                    self.reveal_selected()
                    self.scroll = 0
                    audio.play('click')
                    return
            for idx, r in self.card_rects:
                if r.collidepoint(pos):
                    self.activate(self.items()[idx])
                    return
            for i, r in enumerate(self.sector_rects):
                if r.collidepoint(pos):
                    self.pick_sector(i)
                    return
            if self.fly_btn.hit(pos):
                self.try_fly()
                return
            if self.forge_btn.hit(pos):
                audio.play('select')
                self.app.set_scene('editor')
                return
            self.dragging = True
            self.drag_x = pos[0]
            return

        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.dragging = False
            return

        if e.type == pygame.MOUSEMOTION and self.dragging:
            self.yaw_off += (e.pos[0] - self.drag_x) * 0.009
            self.drag_x = e.pos[0]

    def grounded_reason(self):
        s = self.stats
        if not s.get('hull'):
            return 'FIT A HULL FIRST'
        if not s.get('frame'):
            return 'FIT A FRAME TO OPEN THE HARDPOINTS'
        if s.get('rotors', 0) < 3:
            return 'FIT AT LEAST 3 ROTORS'
        if s.get('powered', 0) < 3:
            return 'FIT A DRIVE MOTOR TO EACH ROTOR'
        return ''

    def try_fly(self):
        if not self.stats.get('airworthy'):
            audio.play('error')
            self.app.toast('AIRFRAME GROUNDED', self.grounded_reason(), RED)
            return
        fault = self.stats.get('fault')
        if fault:
            self.app.toast('FLIGHT RISK', '{} · GOING UP ANYWAY'.format(fault[0]),
                           GOLD)
        audio.play('select')
        self.app.set_scene('flight')

    def apply_paint(self, entry):
        st = self.app.state
        if st.get('paint') == entry['id']:
            audio.play('click')
            return
        st['paint'] = entry['id']
        self.app.save()
        self.rebuild()
        audio.play('select')
        self.app.toast('PAINT APPLIED', '{} · {}'.format(entry['name'],
                                                         entry['desc']), TEAL)

    def activate(self, entry):
        st = self.app.state
        slot = entry['slot'] if 'slot' in entry else 'paint'
        if slot == 'paint':
            self.apply_paint(entry)
            return
        if self.socket[0] != slot:
            self.slot = slot
            self.socket = (slot, self.first_open(slot))
        key = self.socket[1]
        block = self.prereq(slot, key)
        if block:
            audio.play('error')
            self.app.toast('BUILD ORDER', block, RED)
            return
        owned = bool(entry.get('custom')) or entry['id'] in st['owned']
        bought = False
        if owned:
            audio.play('select')
        else:
            price = int(entry['price'])
            if st['credits'] < price:
                audio.play('error')
                self.app.toast('NOT ENOUGH CREDITS',
                               'NEED {:,} MORE'.format(price - st['credits']),
                               RED)
                return
            st['credits'] -= price
            st['owned'].append(entry['id'])
            bought = True
        if slot in ('body', 'frame'):
            st['build'][slot] = entry['id']
        else:
            st['build'][slot][key] = entry['id']
        if slot != 'paint':
            st['selected'][slot] = entry['id']
        self.app.save()
        self.rebuild()
        self.bolt(slot, key)
        if bought:
            audio.play('buy')
            self.app.toast('PART ACQUIRED',
                           '{} · {} CR'.format(entry['name'], entry['price']),
                           GOLD)
        else:
            audio.play('weld', 0.5)
            self.app.toast('PART BOLTED',
                           '{} → {}'.format(entry['name'],
                                            SOCKET_LABEL[slot][key]), TEAL)
        if slot == 'body' and self.lay.get('frame') is None:
            self.slot, self.socket = 'frame', ('frame', 'c')
            self.reveal_selected()
            self.scroll = 0
            return
        if slot == 'frame' and not any(self.lay['rotor'].values()):
            self.slot, self.socket = 'rotor', ('rotor', 'fl')
            self.reveal_selected()
            self.scroll = 0
            return
        if slot in ('rotor', 'motor'):
            nxt = self.next_open(slot, key)
            if nxt:
                self.socket = (slot, nxt)
                self.reveal_selected()

    def remove_socket_part(self):
        slot, key = self.socket
        st = self.app.state
        if slot == 'body':
            audio.play('error')
            self.app.toast('HULL IS FIXED', 'SWAP IT BY FITTING ANOTHER HULL',
                           RED)
            return
        if slot == 'frame':
            if any(self.lay['rotor'].values()) or any(self.lay['motor'].values()):
                audio.play('error')
                self.app.toast('FRAME IS LOADED', 'UNBOLT ROTORS FIRST', RED)
                return
            st['build']['frame'] = None
            self.app.save()
            self.rebuild()
            audio.play('click')
            self.app.toast('FRAME REMOVED', 'THE HARDPOINTS ARE CLOSED', RED)
            return
        if not self.installed(slot, key):
            audio.play('click')
            return
        st['build'][slot][key] = None
        if slot == 'rotor':
            st['build']['motor'][key] = None
        self.app.save()
        self.rebuild()
        audio.play('click')
        self.app.toast('PART REMOVED', SOCKET_LABEL[slot][key] + ' EMPTY', RED)

    def pick_sector(self, i):
        st = self.app.state
        sec = SECTORS[i]
        if i in st['unlocked']:
            st['sector'] = i
            self.app.save()
            audio.play('select')
            return
        if not self.eligible(i):
            audio.play('error')
            self.app.toast('SECTOR LOCKED', 'CLEAR SECTOR {:02d} WITH RATING B+'.format(i),
                           RED)
            return
        if st['credits'] >= sec['price']:
            st['credits'] -= sec['price']
            st['unlocked'].append(i)
            st['sector'] = i
            self.app.save()
            audio.play('buy')
            self.app.toast('SECTOR UNLOCKED', sec['name'] + ' · ' + sec['sub'],
                           GOLD)
            self.rebuild()
        else:
            audio.play('error')
            self.app.toast('NOT ENOUGH CREDITS',
                           'NEED {:,} MORE'.format(sec['price'] - st['credits']),
                           RED)

    def remove_custom(self, eid):
        st = self.app.state
        st['custom'] = [e for e in st['custom'] if e['id'] != eid]
        if st['selected'].get('rotor') == eid:
            st['selected']['rotor'] = 'rotor_std'
        for key, pid in list(st['build']['rotor'].items()):
            if pid == eid:
                st['build']['rotor'][key] = None
                st['build']['motor'][key] = None
                self.bolt('rotor', key)
        self.del_arm = (None, 0.0)
        self.app.save()
        self.rebuild()
        audio.play('click')
        self.app.toast('ROTOR SCRAPPED', 'NO REFUND · CUSTOM LIST CLEANED', RED)

    # ---------- scene ----------
    def draw_scene(self):
        self.base_sky()
        cam = make_cam(0.58 + self.yaw_off, 0.58, 0.0, 164, SW * 0.50, SH * 0.55)
        self.cam = cam
        self.bay.draw(self.buf, self.t)
        self.draw_turntable(cam)
        self.draw_floor_light(cam)
        vis = {'{}:{}'.format(s, k): clamp(v)
               for (s, k), v in self.build_prog.items()}
        pulse = 0.85 + 0.15 * math.sin(self.t * 2.4)
        draw_parts(self.buf, cam, self.parts, spin=self.t * 7.0, pulse=pulse,
                   vis=vis)
        draw_model_glow(self.buf, cam, self.parts, vis, pulse=pulse)
        for sp in self.sparks_fx:
            q, _ = cam_proj(cam, socket_world(self.app.state, sp['slot'], sp['key']))
            if q is None:
                continue
            k = 1.0 - clamp(sp['age'] / 0.9)
            draw_glow(self.buf, q[0], q[1], 46 + 20 * k, GOLD, 0.55 * k)
            for i in range(6):
                a = sp['seed'] * 1.3 + i * math.pi / 3 + sp['age'] * 5.0
                r0 = 9 + 26 * clamp(sp['age'] * 1.6)
                r1 = r0 + 10 * k
                pygame.draw.line(self.buf, mix(GOLD, (12, 22, 40), 0.25),
                                 (q[0] + math.cos(a) * r0,
                                  q[1] + math.sin(a) * r0 * 0.7),
                                 (q[0] + math.cos(a) * r1,
                                  q[1] + math.sin(a) * r1 * 0.7), 1)

    def draw_turntable(self, cam):
        """Flat pad under the airframe. Screen-space ellipses read cleaner
        than the projected world ring at this camera pitch."""
        b = self.buf
        q, _ = cam_proj(cam, (0.0, -0.618, 0.0))
        if q is None:
            return
        cx, cy = SW // 2, int(q[1]) + 6
        for k, a in ((2.05, 0.30), (1.55, 0.26), (1.15, 0.22)):
            draw_glow(b, cx, cy, int(240 * k), (26, 66, 92), a * 0.55)
        pygame.draw.ellipse(b, (14, 24, 41), (cx - 196, cy - 62, 392, 124))
        pygame.draw.ellipse(b, (30, 48, 74), (cx - 196, cy - 62, 392, 124), 1)
        for rx, ry, col, w in ((176, 55, mix(TEAL, PANEL, 0.32), 1),
                               (160, 50, mix(CYAN, PANEL, 0.12), 1)):
            pygame.draw.ellipse(b, col, (cx - rx, cy - ry, rx * 2, ry * 2), w)
        pygame.draw.ellipse(b, (22, 37, 58), (cx - 118, cy - 37, 236, 74), 1)
        for f in (1.0, 0.78, 0.56, 0.34):
            c = mix((8, 13, 24), (28, 42, 66), 0.25 + 0.5 * (1 - f))
            w = int(186 * f)
            h = int(52 * f)
            pygame.draw.ellipse(b, c, (cx - w, cy - 12 - h, 2 * w, 2 * h))
        for i in range(44):
            a = 2 * math.pi * i / 44
            r0 = 1.0 if i % 4 else 0.93
            x0 = cx + math.cos(a) * 176 * r0
            y0 = cy + math.sin(a) * 55 * r0
            x1 = cx + math.cos(a) * 176
            y1 = cy + math.sin(a) * 55
            col = mix(TEAL, PANEL, 0.45 if i % 4 else 0.20)
            pygame.draw.line(b, col, (x0, y0), (x1, y1), 1)
        ang = (self.t * 1.1) % (2 * math.pi)
        arc = []
        for i in range(16):
            a = ang + 0.74 * i / 15
            arc.append((cx + math.cos(a) * 160, cy + math.sin(a) * 50))
        if len(arc) > 2:
            pygame.draw.lines(b, mix(TEAL, PANEL, 0.10), False, arc, 2)
            draw_glow(b, arc[-1][0], arc[-1][1], 34, TEAL, 0.55)

    def draw_floor_light(self, cam):
        """Fake polished-floor reflection: soft light pools under each rotor."""
        fw, fl = body_scale(self.app.state, self.lay)
        for slot, keys in (('rotor', ('fl', 'fr', 'rl', 'rr')),):
            for key in keys:
                if not self.installed(slot, key):
                    continue
                pos = socket_world(self.app.state, slot, key, fw, fl)
                q, _ = cam_proj(cam, (pos[0] * 1.02, -0.615, pos[2] * 1.02))
                if q is None:
                    continue
                draw_glow(self.buf, q[0], q[1], 130, (28, 70, 96), 0.30)
                draw_glow(self.buf, q[0], q[1], 64, GOLD, 0.10)
        q, _ = cam_proj(cam, (0.0, -0.615, 0.1))
        if q is not None:
            draw_glow(self.buf, q[0], q[1], 260, (22, 52, 78), 0.28)

    def draw(self, win):
        self.draw_scene()
        self.blit(win)
        self.draw_gantry(win)
        st = self.app.state
        sec = self.sector()
        topbar(win, st['credits'], self.app.coin_spin, (sec['name'], sec['sub']))
        self.draw_sockets(win)
        self.draw_socket_panel(win)
        self.draw_left(win)
        self.draw_right(win)
        self.draw_assembly(win)
        text(win, 316, 692, 'CLICK SOCKET   ·   CLICK CARD TO BOLT   ·   DEL REMOVE   ·   A / D ORBIT   ·   M SOUND',
             9.5, 'mono', mix(DIM, PANEL, 0.55), track=1.1)
        cfg = ('BUILD  ·  {} ROTORS  /  {} MOTORS  /  {} WINGS  ·  TRIM {:.0f}%'
               .format(self.stats['rotors'], self.stats['motors'],
                       self.stats['wings'], self.stats['balance']))
        text(win, 316, 670, cfg, 10, 'mono', mix(SOFT, PANEL, 0.5), track=1.4)
        mouse = pygame.mouse.get_pos()
        hand = (self.fly_btn.hit(mouse) or self.forge_btn.hit(mouse)
                or (self.installed(*self.socket)
                    and self.socket[0] not in ('body', 'frame')
                    and self.remove_btn.hit(mouse))
                or any(r.collidepoint(mouse) for _, _, r in self.socket_hits)
                or any(r.collidepoint(mouse) for _, r in self.card_rects)
                or any(r.collidepoint(mouse) for r in self.tab_rects)
                or any(r.collidepoint(mouse) for r in self.sector_rects)
                or any(r.collidepoint(mouse) for _, r in self.del_rects))
        set_cursor(hand)

    def draw_gantry(self, win):
        """Hangar gantry framing the schematic view. Screen-space so it stays
        crisp over the upscaled 3D buffer."""
        steel = (13, 22, 38)
        steel_l = (24, 38, 60)
        for x in (VIEW_X0 + 10, VIEW_X1 - 18):
            pygame.draw.rect(win, steel, (x, VIEW_Y0, 8, VIEW_Y1 - VIEW_Y0))
            pygame.draw.line(win, steel_l, (x + 1, VIEW_Y0),
                             (x + 1, VIEW_Y1), 1)
            for y in range(VIEW_Y0 + 24, VIEW_Y1, 96):
                pygame.draw.line(win, (18, 30, 48), (x + 8, y),
                                 (x - 26, y + 46), 1)
                pygame.draw.line(win, (18, 30, 48), (x + 8, y + 46),
                                 (x - 26, y), 1)
        pygame.draw.rect(win, steel, (VIEW_X0, VIEW_Y0, VIEW_X1 - VIEW_X0, 8))
        pygame.draw.line(win, steel_l, (VIEW_X0, VIEW_Y0 + 1),
                         (VIEW_X1, VIEW_Y0 + 1), 1)
        for cx in (VIEW_X0 + 148, VIEW_X1 - 156):
            pygame.draw.line(win, (34, 50, 76), (cx, VIEW_Y0 + 8), (cx, 190), 1)
            pygame.draw.circle(win, (60, 84, 122), (cx, 198), 9, 1)
            pygame.draw.circle(win, mix(GOLD, PANEL, 0.35), (cx, 198), 3)
        for i in range(6):
            x = VIEW_X0 + 40 + i * 26
            pygame.draw.line(win, mix(GOLD, PANEL, 0.72), (x, VIEW_Y0 + 8),
                             (x + 12, VIEW_Y0 + 8), 2)
            x = VIEW_X1 - 40 - i * 26
            pygame.draw.line(win, mix(GOLD, PANEL, 0.72), (x, VIEW_Y0 + 8),
                             (x - 12, VIEW_Y0 + 8), 2)
        paint = paint_scheme(self.app.state)
        text(win, VIEW_X0 + 8, VIEW_Y1 - 18, 'BAY 07  ·  {}'.format(
            paint['name']), 8.5, 'mono', mix(DIM, PANEL, 0.5), track=1.4)

    def draw_core_socket(self, win, slot, key, pos, label):
        q, _ = cam_proj(self.cam, pos)
        if q is None:
            return
        x, y = q[0] * W / SW, q[1] * H / SH
        selected = self.socket == (slot, key)
        col = mix(GOLD, PANEL, 0.15)
        pulse = 0.5 + 0.5 * math.sin(self.t * 4.0)
        for r, a in ((34, 0.35), (22, 0.6)):
            pygame.draw.circle(win, mix(GOLD, PANEL, 1.0 - a),
                               (int(x), int(y)), int(r + 4 * pulse), 1)
        pygame.draw.circle(win, col, (int(x), int(y)), 6)
        pygame.draw.circle(win, mix(GOLD, WHITE, pulse * 0.6),
                           (int(x), int(y)), 13, 1)
        text(win, x + 46, y - 12, 'FIT ' + label, 10, 'mono', GOLD, track=1.4)
        text(win, x + 46, y + 1, 'CLICK TO OPEN THE BIN', 8.5, 'mono',
             mix(SOFT, PANEL, 0.2), track=1.0)
        self.socket_hits.append(
            (slot, key, pygame.Rect(int(x - 26), int(y - 26), 52, 52)))

    def draw_sockets(self, win):
        self.socket_hits = []
        if self.lay.get('body') is None:
            self.draw_core_socket(win, 'body', 'c', (0.0, 0.12, 0.0), 'A HULL')
            return
        if self.lay.get('frame') is None:
            self.draw_core_socket(win, 'frame', 'c', (0.0, 0.02, 0.0), 'FRAME')
            return
        fw, fl = body_scale(self.app.state, self.lay)
        for slot in ('rotor', 'wing', 'booster'):
            for key, label in SOCKETS[slot]:
                pos = socket_world(self.app.state, slot, key, fw, fl)
                q, _ = cam_proj(self.cam, pos)
                if q is None:
                    continue
                x, y = q[0] * W / SW, q[1] * H / SH
                filled = self.installed(slot, key)
                selected = self.socket == (slot, key)
                r = 10 if not selected else 12
                col = TEAL if filled else mix(GOLD, PANEL, 0.2)
                pygame.draw.circle(win, mix(col, PANEL, 0.35),
                                   (int(x), int(y)), r + 3, 1)
                if selected:
                    pulse = 0.5 + 0.5 * math.sin(self.t * 4.0)
                    pygame.draw.circle(win, mix(GOLD, WHITE, pulse * 0.5),
                                       (int(x), int(y)), r + 6, 1)
                    pygame.draw.circle(win, WHITE, (int(x), int(y)), r + 2, 1)
                if filled:
                    pygame.draw.circle(win, col, (int(x), int(y)), 4)
                else:
                    for i in range(8):
                        a0 = i * math.pi / 4 + self.t * 0.35
                        pygame.draw.line(win, col,
                                         (x + math.cos(a0) * (r - 3),
                                          y + math.sin(a0) * (r - 3)),
                                         (x + math.cos(a0) * (r + 2),
                                          y + math.sin(a0) * (r + 2)), 1)
                    pygame.draw.line(win, col, (x - 3, y), (x + 3, y), 1)
                    pygame.draw.line(win, col, (x, y - 3), (x, y + 3), 1)
                short = {'rotor': {'fl': 'FL', 'fr': 'FR', 'rl': 'RL',
                                   'rr': 'RR'},
                         'wing': {'l': 'WL', 'r': 'WR'},
                         'booster': {'l': 'BL', 'r': 'BR'}}[slot][key]
                tcol = WHITE if selected else (SOFT if filled else DIM)
                text(win, x + r + 6, y - 7, short, 8.5, 'mono', tcol, track=0.6)
                if slot == 'rotor':
                    powered = bool(self.lay['motor'].get(key))
                    pygame.draw.circle(win, TEAL if powered else mix(GOLD, PANEL, 0.3),
                                       (int(x + r + 8), int(y + 5)), 3,
                                       0 if powered else 1)
                if selected:
                    text(win, x + r + 6, y + 3, label, 7.5, 'mono',
                         mix(GOLD, PANEL, 0.15), track=0.8)
                self.socket_hits.append(
                    (slot, key, pygame.Rect(int(x - r - 10), int(y - r - 10),
                                            int(2 * r + 20), int(2 * r + 20))))

    def draw_socket_panel(self, win):
        x0, x1 = 344, 936
        panel(win, x0, 66, x1, 126, PANEL, 0.88, radius=10,
              outline=(34, 54, 84))
        if self.slot == 'paint':
            p = paint_scheme(self.app.state)
            text(win, x0 + 16, 75, 'PAINT · LIVE SCHEME', 9, 'mono', GOLD,
                 track=1.8)
            text(win, x0 + 16, 88, p['name'], 18, 'tech', WHITE, track=2.2)
            text(win, x0 + 16, 110, p['desc'] + '  ·  NO STAT EFFECT', 9,
                 'mono', mix(SOFT, PANEL, 0.4), track=1.2)
            for i, (lab, col) in enumerate(
                    (('HULL', p['hull']), ('DECK', p['deck']),
                     ('TRIM', p['accent']), ('BLADE', p['blade']))):
                bx = x0 + 366 + i * 56
                pygame.draw.rect(win, col, (bx, 96, 18, 12), border_radius=2)
                text(win, bx, 82, lab, 8, 'mono', mix(DIM, PANEL, 0.5),
                     track=0.8)
            return

        slot, key = self.socket
        text(win, x0 + 16, 75, 'SOCKET · ' + SOCKET_LABEL[slot][key], 9, 'mono',
             GOLD, track=1.8)
        entry = self.socket_entry()
        if entry:
            text(win, x0 + 16, 88, entry['name'], 18, 'tech', WHITE, track=2.2)
            us = unit_stats(entry)
            if slot == 'rotor':
                info = '{:.0f} THRUST · {:.1f} KG'.format(us['thrust'], us['mass'])
            elif slot == 'motor':
                info = '{:.0f} THRUST · {:.0f} ENERGY'.format(us['thrust'],
                                                              us['energy'])
            elif slot == 'wing':
                info = '{:.0f} LIFT · {:.1f} KG'.format(us['lift'], us['mass'])
            elif slot == 'booster':
                info = '{:.0f} THRUST · {:.0f} ENERGY'.format(us['thrust'],
                                                              us['energy'])
            elif slot == 'frame':
                reach = entry.get('geo', {}).get('reach', 1.0)
                info = 'x{:.2f} REACH · {:.0f} KG'.format(reach, us['mass'])
            else:
                info = 'HULL · {:.0f} KG · DRAG {:.2f}'.format(us['mass'],
                                                               us['drag'])
            text(win, x0 + 16, 110, info + '  ·  PER MODULE', 9, 'mono',
                 mix(SOFT, PANEL, 0.4), track=1.2)
        else:
            text(win, x0 + 16, 88, 'EMPTY SOCKET', 18, 'tech',
                 mix(DIM, PANEL, 0.3), track=2.2)
            block = self.prereq(slot, key)
            hint = ('BUILD ORDER · ' + block if block
                    else 'PICK A PART TO BOLT IT HERE')
            text(win, x0 + 16, 110, hint, 9, 'mono',
                 mix(RED if block else GOLD, PANEL, 0.3), track=1.2)
        text(win, x0 + 152, 76, '{} MODULES BOLTED'.format(
            len(self.installed_keys)), 8.5, 'mono', mix(DIM, PANEL, 0.45),
             track=1.2)
        if entry and slot not in ('body', 'frame'):
            mouse = pygame.mouse.get_pos()
            self.remove_btn.draw(win, self.remove_btn.hit(mouse), True)

    def draw_assembly(self, win):
        if self.assembling():
            prog = (sum(clamp(self.build_prog.get(k, 1.0))
                        for k in self.installed_keys)
                    / max(1, len(self.installed_keys)))
            panel(win, 430, 596, 850, 644, PANEL, 0.90, radius=9,
                  outline=(40, 62, 94))
            text(win, 442, 605, 'ASSEMBLING AIRFRAME', 10, 'mono', GOLD,
                 track=1.8)
            text(win, 838, 605, '{:.0f}%'.format(prog * 100), 11, 'mono',
                 mix(GOLD, WHITE, 0.4), 'r', track=1.0)
            bar(win, 442, 624, 396, 5, prog, GOLD, bg=(22, 36, 58))
            done = sum(1 for k in self.installed_keys
                       if self.build_prog.get(k, 1.0) >= 1.0)
            text(win, 442, 633, 'BOLTED {} / {} MODULES'.format(
                done, len(self.installed_keys)), 8, 'mono',
                mix(DIM, PANEL, 0.45), track=1.0)
        elif self.assy_done_t < 1.8 and self.installed_keys:
            a = 1.0 - self.assy_done_t / 1.8
            text(win, W / 2, 610, 'AIRFRAME ASSEMBLED  ·  {} MODULES'.format(
                len(self.installed_keys)), 11, 'mono',
                mix(TEAL, PANEL, 0.25), 'c', track=2.0, alpha=a)
            text(win, W / 2, 626, 'MATCH THE PAIRS · KEEP THE TRIM GREEN', 9,
                 'mono', mix(DIM, PANEL, 0.4), 'c', track=1.4, alpha=a * 0.8)

    def slot_items(self, slot):
        if slot == 'paint':
            return list(PAINTS)
        items = list(CATALOG[slot])
        if slot == 'rotor':
            items.extend(self.app.state['custom'])
        return items

    def owned_count(self, slot):
        if slot == 'paint':
            n = len(PAINTS)
            return n, n
        st = self.app.state
        items = self.slot_items(slot)
        n = sum(1 for e in items
                if e.get('custom') or e['id'] in st['owned'])
        return n, len(items)

    def stat_rows(self, slot, e):
        st = entry_stats(e)
        out = []
        for lab, key, lo, hi, fmt, higher in STAT_ROWS[slot]:
            v = (e.get('geo', {}).get('reach', 1.0) if key == 'reach'
                 else st.get(key, 0.0))
            out.append((lab, key, v, clamp((v - lo) / max(1e-9, hi - lo)),
                        fmt, higher))
        return out

    def top_pick(self, slot):
        st = self.app.state
        best, bs = None, -1.0
        for e in self.slot_items(slot):
            if not (e.get('custom') or e['id'] in st['owned']):
                continue
            rows = self.stat_rows(slot, e)
            sc = sum(r[3] if r[5] else 1.0 - r[3] for r in rows[:2])
            if sc > bs:
                best, bs = e['id'], sc
        return best

    @staticmethod
    def star(win, cx, cy, r, col):
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * 0.45
            a = -math.pi / 2 + math.pi * i / 5
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        pygame.draw.polygon(win, col, pts)

    def draw_left(self, win):
        st = self.app.state
        mouse = pygame.mouse.get_pos()
        self.hover_info = None
        panel(win, LEFT_X0, 68, LEFT_X1, 660, PANEL, 0.82, radius=12,
              outline=(30, 46, 72))
        pygame.draw.rect(win, mix(GOLD, PANEL, 0.5), (LEFT_X0 + 16, 82, 3, 14),
                         border_radius=2)
        text(win, LEFT_X0 + 26, 78, 'PARTS BIN', 19, 'tech', WHITE, track=2.8)
        text(win, LEFT_X0 + 26, 101, 'FIT ANY SOCKET', 9, 'mono',
             mix(DIM, PANEL, 0.6), track=1.4)
        own, total = self.owned_count(self.slot)
        text(win, LEFT_X1 - 22, 101, '{} / {} OWNED'.format(own, total), 9,
             'mono', mix(TEAL, PANEL, 0.4), 'r', track=1.0)

        self.tab_rects = []
        for i, tab in enumerate(TAB_CELLS):
            row, col = divmod(i, 4)
            x = 24 + col * 66
            y = 114 + row * 46
            r = pygame.Rect(x, y, 64, 42)
            self.tab_rects.append(r)
            sel = tab == self.slot
            hov = r.collidepoint(mouse)
            forge = tab == 'forge'
            if sel:
                panel(win, x, y, x + 64, y + 42, TEAL, 0.94, radius=7)
                col_t = (9, 24, 30)
            elif forge:
                panel(win, x, y, x + 64, y + 42, (30, 25, 14),
                      0.95 if hov else 0.6, radius=7,
                      outline=mix(GOLD, PANEL, 0.3 if hov else 0.55))
                col_t = GOLD if hov else mix(GOLD, DIM, 0.55)
            else:
                panel(win, x, y, x + 64, y + 42, PANEL_L,
                      0.95 if hov else 0.7, radius=7,
                      outline=(64, 94, 134) if hov else (40, 58, 86))
                col_t = SOFT if hov else DIM
            ICONS[tab](win, x + 32, y + 15, 9, col_t, 2)
            text(win, x + 32, y + 27, TAB_LABEL[tab][:5], 8, 'mono', col_t,
                 'c', track=0.5)
            if forge:
                continue
            n, o = self.owned_count(tab)
            pygame.draw.rect(win, (14, 44, 44) if sel else (24, 40, 62),
                             (x + 8, y + 37, 48, 2))
            if o:
                pygame.draw.rect(win, (8, 76, 72) if sel else mix(TEAL, PANEL, 0.25),
                                 (x + 8, y + 37,
                                  max(2, int(48 * o / max(1, n))), 2))

        items = self.items()
        self.card_rects = []
        self.del_rects = []
        paint = self.slot == 'paint'
        self.picks = {} if paint else {self.slot: self.top_pick(self.slot)}
        row0 = 0
        rows = 0
        if paint:
            rows = (len(items) + PAINT_COLS - 1) // PAINT_COLS
            row0 = min(self.scroll, max(0, rows - PAINT_ROWS))
            for r in range(PAINT_ROWS):
                for c in range(PAINT_COLS):
                    idx = (row0 + r) * PAINT_COLS + c
                    if idx >= len(items):
                        break
                    x = CARD_X0 + c * (PAINT_CW + PAINT_GAP)
                    y = CARD_Y0 + r * (PAINT_H + PAINT_GAP)
                    self.card_rects.append(
                        (idx, pygame.Rect(x, y, PAINT_CW, PAINT_H)))
                    self.draw_paint_chip(win, x, y, items[idx])
        else:
            visible = items[self.scroll:self.scroll + CARD_VISIBLE]
            for i, e in enumerate(visible):
                y = CARD_Y0 + i * (CARD_H + CARD_GAP)
                self.card_rects.append(
                    (self.scroll + i,
                     pygame.Rect(CARD_X0, y, CARD_X1 - CARD_X0, CARD_H)))
                self.draw_card(win, y, e)

        if self.hover_info and not paint:
            nm, tag, colr = self.hover_info
            text(win, LEFT_X0 + 18, 640, nm, 9, 'mono',
                 mix(SOFT, PANEL, 0.35), track=1.0)
            text(win, LEFT_X0 + 18 + text_w(nm, 9, 'mono', 1.0) + 8, 640,
                 tag, 9, 'mono', colr, track=0.8)
        else:
            hint = ('CLICK A FINISH TO RECOLOR THE WHOLE BUILD' if paint
                    else 'BAR = PART   ·   TICK = FITTED NOW')
            text(win, LEFT_X0 + 18, 640, hint, 9, 'mono',
                 mix(SOFT, PANEL, 0.55), track=0.9)
        total = len(items)
        if (rows if paint else total) > (PAINT_ROWS if paint else CARD_VISIBLE):
            text(win, LEFT_X0 + 18, 652, 'SCROLL  ▾', 9, 'mono',
                 mix(DIM, PANEL, 0.5), track=1.4)
            if paint:
                shown = min(total, (row0 + PAINT_ROWS) * PAINT_COLS)
                label = '{}-{} OF {}'.format(row0 * PAINT_COLS + 1, shown, total)
            else:
                label = '{}-{} OF {}'.format(
                    self.scroll + 1,
                    min(total, self.scroll + CARD_VISIBLE), total)
            text(win, LEFT_X1 - 24, 652, label, 9, 'mono',
                 mix(DIM, PANEL, 0.6), 'r', track=1.0)
            track = pygame.Rect(LEFT_X1 - 10, CARD_Y0, 3, CARD_AREA.h)
            pygame.draw.rect(win, (22, 36, 58), track, border_radius=2)
            frac = self.scroll / max(1, self.max_scroll())
            th = (max(26, int(CARD_AREA.h * PAINT_ROWS / max(1, rows)))
                  if paint else
                  max(26, int(CARD_AREA.h * CARD_VISIBLE / total)))
            ty = CARD_Y0 + int((CARD_AREA.h - th) * frac)
            pygame.draw.rect(win, mix(TEAL, PANEL, 0.45), (track.x, ty, 3, th),
                             border_radius=2)
        else:
            text(win, LEFT_X0 + 18, 652, 'ALL VARIANTS VISIBLE', 9, 'mono',
                 mix(DIM, PANEL, 0.42), track=1.2)

    def fit_count(self, slot, eid):
        if slot in ('body', 'frame'):
            return 1 if self.lay.get(slot) == eid else 0
        return sum(1 for k, _ in SOCKETS[slot] if self.lay[slot].get(k) == eid)

    def draw_card(self, win, y, e):
        st = self.app.state
        mouse = pygame.mouse.get_pos()
        x0, x1 = CARD_X0, CARD_X1
        rect = pygame.Rect(x0, y, x1 - x0, CARD_H)
        owned = bool(e.get('custom')) or e['id'] in st['owned']
        slot = e['slot']
        key = (self.socket[1] if self.socket[0] == slot
               else self.first_open(slot))
        block = self.prereq(slot, key)
        if slot in ('body', 'frame'):
            here = self.lay.get(slot) == e['id']
        else:
            here = self.lay[slot].get(key) == e['id']
        fitted = self.fit_count(slot, e['id'])
        hov = rect.collidepoint(mouse)
        top = self.picks.get(slot) == e['id'] and not here

        if here:
            panel(win, x0, y, x1, y + CARD_H, (17, 36, 54), 0.96, radius=8,
                  outline=TEAL)
            pygame.draw.rect(win, TEAL, (x0, y + 10, 3, CARD_H - 20),
                             border_radius=2)
        else:
            panel(win, x0, y, x1, y + CARD_H, (12, 22, 38),
                  0.92 if hov else 0.78, radius=8,
                  outline=(64, 98, 140) if hov else (32, 48, 74))

        acc = e.get('accent', GOLD)
        icon_col = acc if owned else mix(acc, PANEL, 0.45)
        ICONS[slot](win, x0 + 22, y + 28, 10, icon_col, 1)
        nx = x0 + 38
        if top:
            self.star(win, x0 + 44, y + 16, 5, GOLD)
            nx = x0 + 54
        text(win, nx, y + 7, e['name'], 14, 'tech',
             WHITE if owned else mix(WHITE, PANEL, 0.55), track=1.5)
        desc = e.get('desc', '')
        if e.get('custom'):
            mat = e['params'].get('material', 'alloy').upper()
            desc = 'CUSTOM · ' + mat
        text(win, x0 + 38, y + 25, desc, 9, 'mono',
             mix(DIM, PANEL, 0.5 if owned else 0.75), track=0.8)

        if not owned:
            price = int(e['price'])
            pw = int(text_w('{:,}'.format(price), 10.5, 'mono')) + 30
            pill = pygame.Rect(x1 - 8 - pw, y + 6, pw, 18)
            afford = st['credits'] >= price
            if afford:
                panel(win, pill.x, pill.y, pill.right, pill.bottom, (34, 27, 14),
                      0.95, radius=5, outline=mix(GOLD, PANEL, 0.45))
                pcol = GOLD
            else:
                panel(win, pill.x, pill.y, pill.right, pill.bottom, (19, 24, 32),
                      0.95, radius=5, outline=(48, 60, 78))
                pcol = mix(DIM, PANEL, 0.35)
            coin(win, pill.x + 11, pill.y + 9, 5, self.app.coin_spin,
                 GOLD if afford else mix(DIM, PANEL, 0.45))
            text(win, pill.right - 7, y + 8, '{:,}'.format(price),
                 10.5, 'mono', pcol, 'r', track=0.4)
        elif here:
            pill = pygame.Rect(x1 - 94, y + 6, 86, 18)
            panel(win, pill.x, pill.y, pill.right, pill.bottom, (16, 44, 48),
                  0.95, radius=5, outline=TEAL)
            text(win, pill.centerx, y + 9, 'IN SOCKET', 8.5, 'mono', TEAL,
                 'c', track=1.2)
        elif block:
            pill = pygame.Rect(x1 - 92, y + 6, 84, 18)
            panel(win, pill.x, pill.y, pill.right, pill.bottom, (34, 22, 14),
                  0.95, radius=5, outline=mix(RED, PANEL, 0.55))
            text(win, pill.centerx, y + 9, self.prereq_short(slot, key), 8.5,
                 'mono', mix(RED, SOFT, 0.35), 'c', track=0.8)
        elif fitted:
            pill = pygame.Rect(x1 - 84, y + 6, 76, 18)
            panel(win, pill.x, pill.y, pill.right, pill.bottom, (14, 34, 48),
                  0.95, radius=5, outline=mix(TEAL, PANEL, 0.5))
            text(win, pill.centerx, y + 9, 'FITTED ×{}'.format(fitted), 8.5,
                 'mono', mix(TEAL, SOFT, 0.3), 'c', track=0.9)
        else:
            pill = pygame.Rect(x1 - 64, y + 6, 56, 18)
            panel(win, pill.x, pill.y, pill.right, pill.bottom, PANEL_L,
                  0.95 if hov else 0.6, radius=5,
                  outline=TEAL if hov else (58, 92, 132))
            text(win, pill.centerx, y + 9, 'BOLT', 8.5, 'mono',
                 TEAL if hov else mix(SOFT, PANEL, 0.4), 'c', track=1.2)

        rows = self.stat_rows(slot, e)
        cur = entry_at(self.app.state, self.lay, slot, key)
        craw = ({r[1]: r[3] for r in self.stat_rows(slot, cur)}
                if cur is not None and cur['id'] != e['id'] else None)
        vcol = mix(SOFT, PANEL, 0.35) if owned else mix(SOFT, PANEL, 0.62)
        for i, (lab, skey, v, frac, fmt, higher) in enumerate(rows):
            lx = x0 + 42 + (i % 2) * 114
            vx = x0 + 144 + (i % 2) * 110
            wbar = 102 if i % 2 == 0 else 98
            yy = y + 42 + (i // 2) * 23
            text(win, lx, yy, lab, 8.5, 'mono', mix(DIM, PANEL, 0.55),
                 track=1.0)
            text(win, vx, yy - 1, fmt.format(v), 10, 'mono', vcol, 'r')
            bar(win, lx, yy + 12, wbar, 3, frac,
                acc if owned else mix(acc, PANEL, 0.55),
                bg=(22, 36, 58), alpha=0.9)
            if craw is not None and abs(frac - craw[skey]) > 0.02:
                tx = lx + int(wbar * clamp(craw[skey]))
                pygame.draw.rect(win, (226, 240, 255), (tx, yy + 9, 1, 8))

        if e.get('custom'):
            armed = self.del_arm[0] == e['id'] and self.t - self.del_arm[1] < 2.5
            r = pygame.Rect(x1 - 22, y + 26, 14, 14)
            self.del_rects.append((e['id'], r))
            c = RED if armed else mix(DIM, PANEL, 0.3)
            pygame.draw.rect(win, c, r, 1, border_radius=3)
            pygame.draw.line(win, c, (r.x + 4, r.y + 4),
                             (r.right - 4, r.bottom - 4), 1)
            pygame.draw.line(win, c, (r.right - 4, r.y + 4),
                             (r.x + 4, r.bottom - 4), 1)
            if armed:
                text(win, x1 - 28, y + 26, 'SCRAP?', 8.5, 'mono', RED, 'r',
                     track=0.8)

        if hov:
            if block:
                self.hover_info = (e['name'], block, mix(RED, SOFT, 0.4))
            elif not owned:
                price = int(e['price'])
                if st['credits'] >= price:
                    self.hover_info = (
                        e['name'], 'COST {:,} CR · CLICK TO BUY'.format(price),
                        GOLD)
                else:
                    self.hover_info = (
                        e['name'], '{:,} CR SHORT'.format(price - st['credits']),
                        RED)
            elif here:
                self.hover_info = (e['name'], 'INSTALLED IN THIS SOCKET', TEAL)
            else:
                tag = 'TOP PICK · ' if top else ''
                self.hover_info = (e['name'], tag + 'OWNED · CLICK TO BOLT',
                                   TEAL)

    def draw_paint_chip(self, win, x, y, p):
        st = self.app.state
        mouse = pygame.mouse.get_pos()
        w, h = PAINT_CW, PAINT_H
        rect = pygame.Rect(x, y, w, h)
        hov = rect.collidepoint(mouse)
        here = st.get('paint') == p['id']
        if here:
            panel(win, x, y, x + w, y + h, (17, 36, 54), 0.96, radius=8,
                  outline=TEAL)
            pygame.draw.rect(win, TEAL, (x + 1, y + 9, 3, h - 18),
                             border_radius=2)
        else:
            panel(win, x, y, x + w, y + h, (12, 22, 38),
                  0.92 if hov else 0.78, radius=8,
                  outline=(64, 98, 140) if hov else (32, 48, 74))

        sx, sy, sw = x + 12, y + 9, 18
        sh = h - 18
        cy = sy
        for frac, col in ((0.46, p['hull']), (0.26, p['deck']),
                          (0.16, p['accent']), (0.12, p['blade'])):
            shh = max(3, int(sh * frac))
            pygame.draw.rect(win, col, (sx, cy, sw, shh))
            cy += shh
        pygame.draw.rect(win, mix(WHITE, PANEL, 0.6), (sx, sy, sw, sh), 1,
                         border_radius=2)

        text(win, x + 38, y + 7, p['name'], 11.5, 'tech',
             WHITE if (here or hov) else SOFT, track=1.2)
        for i, (lab, col) in enumerate((('H', p['hull']),
                                        ('T', p['accent']),
                                        ('B', p['blade']))):
            bx = x + 38 + i * 27
            pygame.draw.rect(win, col, (bx, y + 26, 9, 9), border_radius=2)
            text(win, bx + 11, y + 26, lab, 7.5, 'mono',
                 mix(DIM, PANEL, 0.55), track=0.4)

        desc = p['desc']
        cut = desc.rfind(' ', 0, 20)
        line1 = desc[:cut if cut > 8 else 20]
        line2 = desc[cut + 1:] if cut > 8 else ''
        text(win, x + 38, y + 42, line1, 7.5, 'mono',
             mix(DIM, PANEL, 0.55 if here else 0.7), track=0.3)
        if line2:
            text(win, x + 38, y + 52, line2, 7.5, 'mono',
                 mix(DIM, PANEL, 0.55 if here else 0.7), track=0.3)

        if here:
            pygame.draw.circle(win, TEAL, (x + w - 13, y + 13), 3)
        else:
            pygame.draw.circle(win, mix(DIM, PANEL, 0.45),
                               (x + w - 13, y + 13), 3, 1)

    def draw_right(self, win):
        st = self.app.state
        s = self.stats
        sec = self.sector()
        mouse = pygame.mouse.get_pos()
        sector_i = int(clamp(st.get('sector', 0), 0, 2))

        panel(win, RX0, PERF_Y0, RX1, PERF_Y1, PANEL, 0.82, radius=12,
              outline=(30, 46, 72))
        text(win, RX0 + 16, 78, 'PERFORMANCE', 12, 'bold', SOFT, track=2.4)
        text(win, RX1 - 16, 80, 'LIVE', 9, 'mono', TEAL, 'r', track=1.6)
        rows = (
            ('MASS', '{:.0f} KG'.format(s['mass']), s['mass'] / 340.0, SOFT, 'mass'),
            ('THRUST', '{:.0f}'.format(s['thrust']), s['thrust'] / 420.0, TEAL, 'thrust'),
            ('DRAG', '{:.2f}'.format(s['drag']), s['drag'] / 14.0, RED, 'drag'),
            ('TOP SPEED', '{} KM/H'.format(s['kmh']), (s['top'] - 12) / 16.0, GOLD, 'speed'),
            ('AGILITY', '{:.0f}'.format(s['agility']), s['agility'] / 100.0, CYAN, 'agility'),
            ('BOOST', '{:.0f}'.format(s['energy']), s['energy'] / 120.0, TEAL, 'boost'),
        )
        for i, (lab, val, frac, col, ico) in enumerate(rows):
            stat_row(win, RX0 + 16, RX1 - 16, 112 + i * 38, lab, val, frac, col,
                     icon_name=ico)

        pygame.draw.line(win, (26, 42, 68), (RX0 + 16, 340), (RX1 - 16, 340), 1)
        text(win, RX0 + 16, 348, 'BUILD INTEGRITY', 10, 'bold',
             mix(SOFT, PANEL, 0.3), track=1.8)
        fault = s.get('fault')
        if not s['airworthy']:
            stat_label, stat_col = 'GROUNDED', RED
        elif fault:
            stat_label, stat_col = 'RISKY', GOLD
        elif s['balance'] < 55:
            stat_label, stat_col = 'AIRWORTHY', GOLD
        else:
            stat_label, stat_col = 'AIRWORTHY', TEAL
        good = s['airworthy'] and not fault and s['balance'] >= 55
        text(win, RX1 - 16, 350, stat_label, 9, 'mono', stat_col, 'r',
             track=1.4)
        text(win, RX0 + 16, 368,
             'HULL {}  ·  FRAME {}  ·  ROTORS {}/4  ·  MOTORS {}/4'.format(
                 'OK' if s['hull'] else '--', 'OK' if s['frame'] else '--',
                 s['rotors'], s['motors']), 8.5, 'mono',
             mix(SOFT, PANEL, 0.45), track=0.8)
        bcol = TEAL if good else (GOLD if s['balance'] >= 55 else RED)
        text(win, RX0 + 16, 386, 'TRIM', 9, 'mono', mix(DIM, PANEL, 0.6), track=1.4)
        text(win, RX0 + 96, 386, '{:.0f}%'.format(s['balance']), 11, 'mono',
             bcol, 'r', track=0.6)
        bar(win, RX0 + 16, 402, RX1 - RX0 - 88, 4, s['balance'] / 100.0, bcol,
            bg=(22, 36, 58))

        # centre-of-gravity crosshair
        gx, gy = RX1 - 32, 396
        pygame.draw.circle(win, (30, 48, 74), (gx, gy), 14, 1)
        pygame.draw.line(win, (24, 38, 60), (gx - 14, gy), (gx + 14, gy), 1)
        pygame.draw.line(win, (24, 38, 60), (gx, gy - 14), (gx, gy + 14), 1)
        dx = clamp(s['cog_x'] * 160.0, -10.0, 10.0)
        dz = clamp(-s['cog_z'] * 160.0, -10.0, 10.0)
        pygame.draw.circle(win, bcol, (int(gx + dx), int(gy + dz)), 3)
        text(win, gx, gy + 18, 'CG', 7.5, 'mono', mix(DIM, PANEL, 0.5), 'c',
             track=1.0)
        if not s['hull']:
            tip = 'STEP 1 · FIT A HULL'
        elif not s['frame']:
            tip = 'STEP 2 · FIT A FRAME'
        elif s['rotors'] < 3:
            tip = 'STEP 3 · FIT 3+ ROTORS'
        elif s['powered'] < 3:
            tip = 'STEP 4 · MOTOR FOR EACH ROTOR'
        elif fault:
            tip = 'RISK · {} · MAY CRASH IN FLIGHT'.format(fault[0])
        elif s.get('risk', 0.0) >= 0.30:
            tip = 'WARN · CLEARANCE / DRIVE MATCH'
        elif s['balance'] < 55:
            tip = 'TRIM CRITICAL · CRAFT PULLS'
        else:
            tip = 'READY · MATCH OPPOSITE SOCKETS'
        text(win, RX0 + 16, 412, tip, 8.5, 'mono',
             RED if (not good and s['airworthy']) or fault else
             (mix(DIM, PANEL, 0.45) if good else RED), track=1.1)

        self.fly_btn.sub = ('{} · {} CORES'.format(sec['name'], sec['cores'])
                            if s['airworthy'] else self.grounded_reason())
        self.fly_btn.draw(win, self.fly_btn.hit(mouse), s['airworthy'], 1.0)
        self.forge_btn.draw(win, self.forge_btn.hit(mouse), True, 1.0)

        panel(win, RX0, 566, RX1, 660, PANEL, 0.72, radius=12,
              outline=(30, 46, 72))
        text(win, RX0 + 16, 575, 'SECTORS', 10, 'bold', mix(SOFT, PANEL, 0.35),
             track=2.0)
        self.sector_rects = []
        cleared = st.get('cleared', {})
        for i, sc in enumerate(SECTORS):
            r = pygame.Rect(984 + i * 94, 590, 86, 40)
            self.sector_rects.append(r)
            unl = i in st['unlocked']
            sel = i == sector_i
            hov = r.collidepoint(mouse)
            if sel:
                panel(win, r.x, r.y, r.right, r.bottom, (20, 44, 48), 0.95,
                      radius=6, outline=TEAL)
            else:
                panel(win, r.x, r.y, r.right, r.bottom, PANEL_L,
                      0.9 if hov else 0.6, radius=6,
                      outline=(60, 90, 130) if hov else (34, 50, 76))
            tcol = TEAL if sel else (SOFT if unl else mix(DIM, PANEL, 0.4))
            text(win, r.x + 8, r.y + 4, 'SECTOR {:02d}'.format(i + 1), 9,
                 'mono', tcol, track=0.8)
            grade = cleared.get(str(i))
            if grade:
                text(win, r.right - 7, r.y + 2, grade, 10, 'mono', GOLD, 'r',
                     track=0.4)
            if unl:
                text(win, r.x + 8, r.y + 21, sc['challenge'], 8.5,
                     'mono', TEAL if sel else mix(SOFT, PANEL, 0.55), track=0.3)
            elif self.eligible(i):
                coin(win, r.x + 12, r.y + 25, 5, self.app.coin_spin)
                text(win, r.x + 21, r.y + 20, str(sc['price']), 10, 'mono',
                     mix(GOLD, PANEL, 0.35), track=0.4)
            else:
                icon_lock(win, r.x + 12, r.y + 26, 5, mix(DIM, PANEL, 0.35))
                text(win, r.x + 22, r.y + 20, 'LOCKED', 8.5, 'mono',
                     mix(DIM, PANEL, 0.35), track=0.8)
        done = st.get('finished')
        text(win, RX0 + 16, 640, self.objective_text(), 9, 'mono',
             mix(GOLD if done else SOFT, PANEL, 0.55), track=0.8)
