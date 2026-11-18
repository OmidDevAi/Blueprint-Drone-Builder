"""Animated 3D hangar bay behind the turntable.

Everything here is projected with a perspective camera that is independent of
the showcase camera: the ship orbits on its turntable while the bay stays put.
The corridor is drawn back to front, then props, lights and finally dust; the
ship scene is composited on top afterwards.
"""

import math
import random

import pygame

from config import SW, SH, SOFT, TEAL, CYAN, GOLD, RED, WHITE
from render3d import (make_cam, draw_glow, fill_alpha_poly, mix, clamp)
from ui import text

FLOOR_Y = -0.625
CEIL_Y = 1.55
HALF_W = 3.85
Z_BACK = -7.0
Z_NEAR = 4.6
DOOR_HX = 1.24
DOOR_TOP = 0.98

CAM_PITCH = 0.13
CAM_SCALE = 150.0
CAM_CY = 300.0

Z_SEGS = (-7.0, -5.7, -4.4, -3.1, -1.8, -0.5, 0.8, 2.1, 3.4, 4.6)

WALL_A = (18, 29, 49)
WALL_B = (21, 34, 56)
WALL_C = (24, 39, 63)
SEAM = (7, 13, 24)
DEEP = (10, 18, 31)
FLOOR_C = (12, 21, 38)
BEAM = (26, 41, 64)
BEAM_L = (41, 60, 92)
STEEL = (25, 39, 61)
STEEL_L = (40, 60, 92)
CRATE_F = (28, 43, 64)
CRATE_S = (20, 32, 50)
CRATE_T = (36, 52, 76)
EDGE = (8, 14, 26)
PAD_F = (22, 36, 56)
PAD_S = (17, 28, 45)
PAD_T = (30, 46, 70)

OUT_TOP = (4, 9, 18)
OUT_MID = (12, 36, 50)
OUT_LOW = (26, 78, 94)


def _make_proj(cam):
    cp, sp = math.cos(cam['pitch']), math.sin(cam['pitch'])
    cyaw, syaw = math.cos(cam['yaw']), math.sin(cam['yaw'])
    cr, sr = math.cos(cam['roll']), math.sin(cam['roll'])
    tx, ty, tz = cam['tx'], cam['ty'], cam['tz']
    camp, scale = cam['camp'], cam['scale']
    cx, cy = cam['cx'], cam['cy']

    def proj(p):
        x, y, z = p[0] - tx, p[1] - ty, p[2] - tz
        x, y = x * cr - y * sr, x * sr + y * cr
        y, z = y * cp - z * sp, y * sp + z * cp
        x, z = cyaw * x + syaw * z, -syaw * x + cyaw * z
        dep = camp - z
        if dep < 0.6:
            return None, dep
        f = scale * camp / dep
        return (cx + x * f, cy - y * f), dep

    return proj


def _quad(buf, proj, pts, col, edge=None, w=1):
    out = []
    dep = 0.0
    for p in pts:
        q, d = proj(p)
        if q is None:
            return None
        out.append(q)
        dep += d
    xs = [q[0] for q in out]
    ys = [q[1] for q in out]
    if (max(xs) < -64 or min(xs) > SW + 64 or
            max(ys) < -64 or min(ys) > SH + 64):
        return dep / len(pts)
    pygame.draw.polygon(buf, col, out)
    if edge is not None:
        pygame.draw.lines(buf, edge, True, out, w)
    return dep / len(pts)


def _line(buf, proj, a, b, col, w=1):
    qa, _ = proj(a)
    qb, _ = proj(b)
    if qa is None or qb is None:
        return
    if (max(qa[0], qb[0]) < -32 or min(qa[0], qb[0]) > SW + 32 or
            max(qa[1], qb[1]) < -32 or min(qa[1], qb[1]) > SH + 32):
        return
    pygame.draw.line(buf, col, qa, qb, w)


def _glow(buf, proj, p, radius, col, strength):
    q, _ = proj(p)
    if q is None:
        return
    if (q[0] < -radius or q[0] > SW + radius or
            q[1] < -radius or q[1] > SH + radius):
        return
    draw_glow(buf, q[0], q[1], radius, col, round(strength / 0.05) * 0.05)


def _box(buf, proj, cx, base, cz, sx, sy, sz, front, side, top, edge,
         stripe=None):
    x0, x1 = cx - sx * 0.5, cx + sx * 0.5
    y0, y1 = base, base + sy
    z0, z1 = cz - sz * 0.5, cz + sz * 0.5
    xs = x0 if cx > 0.0 else x1
    _quad(buf, proj, [(xs, y0, z0), (xs, y0, z1), (xs, y1, z1),
                      (xs, y1, z0)], side, edge)
    _quad(buf, proj, [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1),
                      (x0, y1, z1)], top, edge)
    _quad(buf, proj, [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1),
                      (x0, y1, z1)], front, edge)
    if stripe is not None:
        yy = y0 + sy * 0.62
        _quad(buf, proj, [(x0 + sx * 0.08, yy, z1 + 0.002),
                          (x1 - sx * 0.08, yy, z1 + 0.002),
                          (x1 - sx * 0.08, yy + 0.045, z1 + 0.002),
                          (x0 + sx * 0.08, yy + 0.045, z1 + 0.002)], stripe)
        _line(buf, proj, (x0 + sx * 0.20, y0 + 0.05, z1 + 0.003),
              (x0 + sx * 0.20, y1 - 0.05, z1 + 0.003), edge)


class HangarBay:
    def __init__(self):
        rng = random.Random(23)
        self.dust = [(rng.uniform(-3.3, 3.3), rng.uniform(-0.35, 1.35),
                      rng.uniform(Z_BACK + 0.4, Z_NEAR), rng.uniform(0, 6.28),
                      rng.uniform(0.6, 1.7)) for _ in range(34)]
        self.stars = [(rng.uniform(-1.1, 1.1), rng.uniform(0.05, 0.86),
                       rng.uniform(0, 6.28), rng.uniform(0.7, 2.2))
                      for _ in range(22)]

    def draw(self, buf, t):
        cam = make_cam(0.018 * math.sin(t * 0.17),
                       CAM_PITCH + 0.007 * math.sin(t * 0.23), 0.0,
                       CAM_SCALE, SW * 0.5 + 3.5 * math.sin(t * 0.13),
                       CAM_CY + 3.0 * math.sin(t * 0.19))
        proj = _make_proj(cam)
        self._back_wall(buf, proj, t)
        self._side_walls(buf, proj, t)
        self._floor(buf, proj, t)
        self._ceiling(buf, proj, t)
        self._searchlight(buf, proj, t)
        self._props(buf, proj, t)
        self._drone(buf, proj, t)
        self._dust(buf, proj, t)

    # ---------- shell ----------
    def _back_wall(self, buf, proj, t):
        F, C, W, Z = FLOOR_Y, CEIL_Y, HALF_W, Z_BACK
        hx, top = DOOR_HX, DOOR_TOP

        _quad(buf, proj, [(-W, F, Z), (W, F, Z), (W, C, Z), (-W, C, Z)],
              WALL_A, SEAM)
        for y in (-0.18, 0.32, 0.68, 1.18):
            _line(buf, proj, (-W, y, Z + 0.002), (W, y, Z + 0.002), DEEP)
        for x in (-3.10, -2.55, -1.95, 1.95, 2.55, 3.10):
            _line(buf, proj, (x, F, Z + 0.002), (x, C, Z + 0.002), DEEP)

        # what is visible through the door slit: night sky and a low horizon
        _quad(buf, proj, [(-hx, F, Z - 0.02), (hx, F, Z - 0.02),
                          (hx, top, Z - 0.02), (-hx, top, Z - 0.02)], OUT_TOP)
        _quad(buf, proj, [(-hx, F, Z - 0.015), (hx, F, Z - 0.015),
                          (hx, F + 0.20, Z - 0.015),
                          (-hx, F + 0.20, Z - 0.015)], OUT_LOW)
        _quad(buf, proj, [(-hx, F + 0.20, Z - 0.015),
                          (hx, F + 0.20, Z - 0.015),
                          (hx, F + 0.44, Z - 0.015),
                          (-hx, F + 0.44, Z - 0.015)], OUT_MID)
        for sx, sy, ph, spd in self.stars:
            tw = 0.5 + 0.5 * math.sin(t * spd + ph)
            _glow(buf, proj, (sx, F + sy, Z - 0.01), 6, (130, 178, 226),
                  0.10 + 0.20 * tw)
        # light leak in the door seam, drawn under the leaves
        _quad(buf, proj, [(-0.022, F, Z + 0.001), (0.022, F, Z + 0.001),
                          (0.022, top - 0.06, Z + 0.001),
                          (-0.022, top - 0.06, Z + 0.001)], (96, 152, 200))

        gap = 0.072 + 0.080 * (0.5 + 0.5 * math.sin(t * 0.31)) \
            + 0.010 * math.sin(t * 1.9)
        for a, b in ((-hx, -gap), (gap, hx)):
            _quad(buf, proj, [(a, F, Z + 0.04), (b, F, Z + 0.04),
                              (b, top, Z + 0.04), (a, top, Z + 0.04)],
                  (23, 37, 59), EDGE)
            yy = F + 0.10
            while yy < top - 0.04:
                _line(buf, proj, (a + 0.02, yy, Z + 0.045),
                      (b - 0.02, yy, Z + 0.045), (9, 16, 28))
                yy += 0.115
            _line(buf, proj, (a + 0.018, F + 0.03, Z + 0.046),
                  (a + 0.018, top - 0.02, Z + 0.046), (8, 14, 25), 2)
            _line(buf, proj, (b - 0.018, F + 0.03, Z + 0.046),
                  (b - 0.018, top - 0.02, Z + 0.046), (8, 14, 25), 2)
            inner = b if b < 0 else a
            _line(buf, proj, (inner, F + 0.03, Z + 0.047),
                  (inner, top - 0.02, Z + 0.047), (66, 122, 166), 1)

        _quad(buf, proj, [(-hx - 0.13, F, Z + 0.05),
                          (hx + 0.13, F, Z + 0.05),
                          (hx + 0.13, F + 0.055, Z + 0.05),
                          (-hx - 0.13, F + 0.055, Z + 0.05)],
              mix(GOLD, (46, 34, 20), 0.55))

        for s in (-1, 1):
            x0, x1 = s * hx, s * (hx + 0.13)
            _quad(buf, proj, [(x0, F, Z + 0.05), (x1, F, Z + 0.05),
                              (x1, top + 0.18, Z + 0.05),
                              (x0, top + 0.18, Z + 0.05)], STEEL, EDGE)
            _line(buf, proj, (x0 - s * 0.012, F + 0.03, Z + 0.052),
                  (x0 - s * 0.012, top + 0.15, Z + 0.052),
                  mix(GOLD, STEEL, 0.45), 1)

        _quad(buf, proj, [(-hx - 0.13, top, Z + 0.05),
                          (hx + 0.13, top, Z + 0.05),
                          (hx + 0.13, top + 0.18, Z + 0.05),
                          (-hx - 0.13, top + 0.18, Z + 0.05)], STEEL, EDGE)
        for i in range(10):
            xa = -hx - 0.10 + i * 0.266
            col = mix(GOLD, (40, 32, 20), 0.55) if i % 2 == 0 \
                else (16, 24, 38)
            _quad(buf, proj, [(xa, top + 0.025, Z + 0.052),
                              (xa + 0.155, top + 0.025, Z + 0.052),
                              (xa + 0.225, top + 0.155, Z + 0.052),
                              (xa + 0.070, top + 0.155, Z + 0.052)], col)

        pulse = 0.5 + 0.5 * math.sin(t * 2.1)
        for s in (-1, 1):
            bx = s * (hx + 0.30)
            _glow(buf, proj, (bx, top + 0.08, Z + 0.06), 34, RED,
                  0.12 + 0.24 * pulse)
            _glow(buf, proj, (bx, top + 0.08, Z + 0.06), 10, WHITE,
                  0.08 + 0.14 * pulse)

        # pipes and a vent either side of the door
        for s in (-1, 1):
            x = s * 2.72
            _quad(buf, proj, [(x - 0.035, F, Z + 0.01),
                              (x + 0.035, F, Z + 0.01),
                              (x + 0.035, C, Z + 0.01),
                              (x - 0.035, C, Z + 0.01)], (16, 27, 45), EDGE)
            for yy in (F + 0.34, F + 0.86, F + 1.36):
                _line(buf, proj, (x - 0.07, yy, Z + 0.012),
                      (x + 0.07, yy, Z + 0.012), STEEL_L)

        vx0, vx1 = -3.20, -2.42
        vy0, vy1 = 0.26, 0.64
        _quad(buf, proj, [(vx0, vy0, Z + 0.008), (vx1, vy0, Z + 0.008),
                          (vx1, vy1, Z + 0.008), (vx0, vy1, Z + 0.008)],
              (9, 16, 27), (31, 48, 73))
        for k in range(4):
            yy = vy0 + 0.07 + k * 0.075
            _line(buf, proj, (vx0 + 0.06, yy, Z + 0.012),
                  (vx1 - 0.06, yy, Z + 0.012), (24, 38, 60))

        q, _ = proj((2.45, 0.60, Z + 0.02))
        if q is not None and 0 < q[0] < SW and 0 < q[1] < SH:
            text(buf, q[0], q[1], '07', 26, 'tech',
                 mix(GOLD, WALL_A, 0.34), 'c', 3.4)
        q, _ = proj((0.0, top + 0.26, Z + 0.02))
        if q is not None and 0 < q[0] < SW and 0 < q[1] < SH:
            text(buf, q[0], q[1], 'BAY 07', 10, 'mono',
                 mix(SOFT, WALL_A, 0.42), 'c', 2.6)

        _glow(buf, proj, (0.0, F + 0.42, Z + 0.07), 30, (86, 146, 204),
              0.16 + 0.08 * pulse)

    def _side_walls(self, buf, proj, t):
        F, C, W = FLOOR_Y, CEIL_Y, HALF_W
        for i in range(len(Z_SEGS) - 1):
            z0, z1 = Z_SEGS[i], Z_SEGS[i + 1]
            for s in (-1, 1):
                x = s * W
                col = WALL_B if i % 2 else WALL_A
                _quad(buf, proj, [(x, F, z0), (x, C, z0), (x, C, z1),
                                  (x, F, z1)], col, SEAM)
                # recessed panel band above the ship
                _quad(buf, proj, [(x, 0.52, z0 + 0.22), (x, 0.52, z1 - 0.22),
                                  (x, 1.34, z1 - 0.22),
                                  (x, 1.34, z0 + 0.22)],
                      WALL_C if i % 2 else WALL_B, DEEP)
                xr = s * (W - 0.09)
                _quad(buf, proj, [(xr, F, z0), (xr, C, z0),
                                  (xr, C, z0 + 0.15),
                                  (xr, F, z0 + 0.15)], (21, 34, 55), SEAM)
                _line(buf, proj, (x - s * 0.004, -0.28, z0 + 0.03),
                      (x - s * 0.004, -0.28, z1 - 0.03),
                      mix(GOLD, (28, 22, 12), 0.42), 1)
                _line(buf, proj, (x - s * 0.004, 0.44, z0 + 0.03),
                      (x - s * 0.004, 0.44, z1 - 0.03), DEEP)
                zm = (z0 + z1) * 0.5
                for li, (yy, acc) in enumerate(((0.66, TEAL),
                                                (1.02, GOLD))):
                    _quad(buf, proj, [(x - s * 0.02, yy - 0.05, zm - 0.07),
                                      (x - s * 0.02, yy - 0.05, zm + 0.07),
                                      (x - s * 0.02, yy + 0.05, zm + 0.07),
                                      (x - s * 0.02, yy + 0.05, zm - 0.07)],
                          (34, 52, 80), EDGE)
                    a = 0.5 + 0.5 * math.sin(t * 1.7 + i * 1.3
                                             + s * 0.9 + li * 1.1)
                    _glow(buf, proj, (x - s * 0.03, yy, zm), 18, acc,
                          0.06 + 0.20 * a)

    def _floor(self, buf, proj, t):
        F, W = FLOOR_Y, HALF_W
        _quad(buf, proj, [(-W, F, Z_NEAR), (W, F, Z_NEAR),
                          (W, F, Z_BACK), (-W, F, Z_BACK)],
              FLOOR_C, SEAM)
        z = Z_BACK + 0.6
        while z < Z_NEAR:
            _line(buf, proj, (-W, F, z), (W, F, z), (16, 27, 44), 1)
            z += 1.4
        for x in (-2.85, -1.95, -1.0, 1.0, 1.95, 2.85):
            _line(buf, proj, (x, F, Z_BACK), (x, F, Z_NEAR),
                  (15, 25, 41), 1)
        for s in (-1, 1):
            x0, x1 = s * 1.54, s * 1.72
            _quad(buf, proj, [(x0, F, Z_BACK), (x1, F, Z_BACK),
                              (x1, F, Z_NEAR), (x0, F, Z_NEAR)],
                  (17, 28, 47), (29, 45, 69))
            _line(buf, proj, (s * 1.72, F, Z_BACK), (s * 1.72, F, Z_NEAR),
                  mix(TEAL, (16, 27, 44), 0.82), 1)

        for k, zc in enumerate((-6.0, -4.8)):
            a = 0.5 + 0.5 * math.sin(t * 1.8 - k * 1.4)
            col = mix(GOLD, (18, 28, 46), 0.34 + 0.26 * a)
            _line(buf, proj, (-0.92, F, zc), (0.0, F, zc - 0.52), col, 2)
            _line(buf, proj, (0.0, F, zc - 0.52), (0.92, F, zc), col, 2)

        span = Z_NEAR - Z_BACK
        for s in (-1, 1):
            for k in range(5):
                z = Z_BACK + ((t * 1.6 + k * 2.4) % span)
                _glow(buf, proj, (s * 1.63, F + 0.004, z), 16, TEAL, 0.22)
                _quad(buf, proj, [(s * 1.63 - 0.035, F + 0.004, z - 0.06),
                                  (s * 1.63 + 0.035, F + 0.004, z - 0.06),
                                  (s * 1.63 + 0.035, F + 0.004, z + 0.06),
                                  (s * 1.63 - 0.035, F + 0.004, z + 0.06)],
                      (48, 126, 128))

    def _ceiling(self, buf, proj, t):
        C, W = CEIL_Y, HALF_W
        _quad(buf, proj, [(-W, C, Z_NEAR), (W, C, Z_NEAR),
                          (W, C, Z_BACK), (-W, C, Z_BACK)],
              (7, 12, 23), (15, 23, 40))
        for z in Z_SEGS:
            _quad(buf, proj, [(-W, C - 0.16, z - 0.09),
                              (W, C - 0.16, z - 0.09),
                              (W, C - 0.16, z + 0.09),
                              (-W, C - 0.16, z + 0.09)], BEAM, BEAM_L)
            _line(buf, proj, (-W, C - 0.165, z + 0.09),
                  (W, C - 0.165, z + 0.09), (9, 16, 29))
        for s in (-1, 1):
            x0, x1 = s * 2.75 - 0.09, s * 2.75 + 0.09
            _quad(buf, proj, [(x0, C - 0.18, Z_BACK),
                              (x1, C - 0.18, Z_BACK),
                              (x1, C - 0.18, Z_NEAR),
                              (x0, C - 0.18, Z_NEAR)], (20, 32, 50),
                  (33, 50, 76))

        for z in (-6.0, -3.5, -1.0):
            _quad(buf, proj, [(-0.82, C - 0.22, z - 0.10),
                              (0.82, C - 0.22, z - 0.10),
                              (0.82, C - 0.22, z + 0.10),
                              (-0.82, C - 0.22, z + 0.10)],
                  (96, 150, 190), (170, 210, 240))
            _line(buf, proj, (-0.72, C - 0.226, z),
                  (0.72, C - 0.226, z), WHITE, 2)
            _glow(buf, proj, (0.0, C - 0.26, z), 84, (90, 150, 210), 0.20)
            self._cone(buf, proj, z)

    def _cone(self, buf, proj, z):
        ql, _ = proj((0.0, CEIL_Y - 0.22, z))
        if ql is None:
            return
        pts = [ql]
        tz = z + 0.55
        for i in range(12):
            a = 2 * math.pi * i / 12
            q, _ = proj((1.32 * math.cos(a), FLOOR_Y + 0.005,
                         tz + 0.9 * math.sin(a)))
            if q is None:
                return
            pts.append(q)
        fill_alpha_poly(buf, pts, (50, 96, 140), 0.05)
        _glow(buf, proj, (0.0, FLOOR_Y + 0.006, tz), 132,
              (30, 70, 110), 0.16)

    def _searchlight(self, buf, proj, t):
        lamp = (2.25, CEIL_Y - 0.12, -4.6)
        tx = 2.35 * math.sin(t * 0.33)
        tz = -4.0 + 0.55 * math.sin(t * 0.21 + 1.0)
        target = (tx, FLOOR_Y + 0.006, tz)
        ql, _ = proj(lamp)
        q0, _ = proj((tx - 0.34, FLOOR_Y + 0.006, tz + 0.16))
        q1, _ = proj((tx + 0.34, FLOOR_Y + 0.006, tz + 0.16))
        if ql is not None and q0 is not None and q1 is not None:
            fill_alpha_poly(buf, [ql, q0, q1], (60, 170, 190), 0.07)
        _glow(buf, proj, target, 72, CYAN, 0.20)
        _glow(buf, proj, lamp, 34, CYAN, 0.24)
        _quad(buf, proj, [(2.14, CEIL_Y - 0.20, -4.72),
                          (2.36, CEIL_Y - 0.20, -4.72),
                          (2.36, CEIL_Y - 0.14, -4.48),
                          (2.14, CEIL_Y - 0.14, -4.48)], (30, 46, 70), EDGE)

    # ---------- props ----------
    def _props(self, buf, proj, t):
        F = FLOOR_Y
        _box(buf, proj, -2.55, F, -6.15, 0.95, 0.66, 0.72,
             CRATE_F, CRATE_S, CRATE_T, EDGE, GOLD)
        _box(buf, proj, -2.55, F + 0.66, -6.15, 0.72, 0.46, 0.56,
             CRATE_F, CRATE_S, CRATE_T, EDGE, None)
        _box(buf, proj, 2.58, F, -6.35, 0.82, 0.92, 0.62,
             CRATE_F, CRATE_S, CRATE_T, EDGE, TEAL)
        _box(buf, proj, 2.32, F, -5.45, 0.46, 0.36, 0.46,
             CRATE_F, CRATE_S, CRATE_T, EDGE, None)

        self._cart(buf, proj, t, 1.62, -4.90, 0.0, CYAN)
        self._crane(buf, proj, t)
        self._cart(buf, proj, t, -1.72, -2.70, 1.7, TEAL)

    def _cart(self, buf, proj, t, x0, z0, ph, accent):
        F = FLOOR_Y
        bob = 0.026 * math.sin(t * 1.35 + ph)
        x = x0 + 0.11 * math.sin(t * 0.23 + ph)
        z = z0 + 0.10 * math.sin(t * 0.17 + ph + 1.2)
        y = F + 0.15 + bob
        _glow(buf, proj, (x, y - 0.10, z), 66, accent, 0.26)
        _box(buf, proj, x, y, z, 0.64, 0.10, 0.48,
             PAD_F, PAD_S, PAD_T, EDGE, None)
        _box(buf, proj, x, y + 0.10, z, 0.36, 0.29, 0.32,
             CRATE_F, CRATE_S, CRATE_T, EDGE, accent)
        for sx in (-0.26, 0.26):
            _glow(buf, proj, (x + sx, y + 0.02, z + 0.24), 8, accent, 0.30)

    def _crane(self, buf, proj, t):
        C = CEIL_Y
        z = -3.4
        _box(buf, proj, 0.0, C - 0.40, z, 5.4, 0.09, 0.15,
             BEAM, (16, 26, 42), BEAM_L, EDGE, None)
        tx = 2.0 * math.sin(t * 0.17)
        ty = C - 0.50
        _box(buf, proj, tx, ty, z, 0.30, 0.17, 0.26,
             (39, 56, 82), (25, 38, 58), (48, 66, 94), EDGE, None)
        blink = 0.5 + 0.5 * math.sin(t * 4.2)
        _glow(buf, proj, (tx, ty + 0.20, z + 0.13), 22, GOLD,
              0.12 + 0.32 * blink)
        sway = 0.035 * math.sin(t * 0.8)
        pod_base = 0.60 + 0.03 * math.sin(t * 1.1)
        _line(buf, proj, (tx, ty + 0.12, z),
              (tx + sway, pod_base + 0.22, z), (58, 78, 108), 1)
        _box(buf, proj, tx + sway, pod_base, z, 0.26, 0.22, 0.24,
             (33, 48, 70), (23, 35, 53), (42, 58, 84), EDGE, TEAL)
        _glow(buf, proj, (tx + sway, pod_base + 0.10, z + 0.13), 14,
              TEAL, 0.24)

    def _drone(self, buf, proj, t):
        a = t * 0.42
        x = 2.55 * math.sin(a)
        z = -4.3 + 1.9 * math.cos(a)
        y = 0.70 + 0.12 * math.sin(t * 1.3)
        prev = None
        for j in (4, 3, 2, 1):
            aa = a - j * 0.07
            px = 2.55 * math.sin(aa)
            pz = -4.3 + 1.9 * math.cos(aa)
            py = 0.70 + 0.12 * math.sin(t * 1.3 - j * 0.12)
            q, _ = proj((px, py, pz))
            if q is None:
                prev = None
                continue
            if prev is not None:
                col = mix(TEAL, (16, 28, 46), 0.48 - j * 0.09)
                pygame.draw.line(buf, col, prev, q, 1)
            prev = q
        _box(buf, proj, x, y - 0.05, z, 0.15, 0.10, 0.15,
             (34, 50, 74), (24, 36, 56), (42, 60, 88), EDGE, None)
        _glow(buf, proj, (x, y, z), 14, TEAL, 0.30)
        _glow(buf, proj, (x, y - 0.05, z), 30, (20, 90, 96), 0.12)

    def _dust(self, buf, proj, t):
        for x0, y0, z0, ph, spd in self.dust:
            x = x0 + 0.22 * math.sin(t * 0.21 * spd + ph)
            y = y0 + 0.10 * math.sin(t * 0.17 * spd + ph * 1.7)
            z = z0 + 0.45 * math.sin(t * 0.11 * spd + ph * 0.6)
            a = 0.05 + 0.05 * (0.5 + 0.5 * math.sin(t * 1.3 + ph))
            _glow(buf, proj, (x, y, z), 6 + int(4 * spd),
                  (150, 196, 240), a)
