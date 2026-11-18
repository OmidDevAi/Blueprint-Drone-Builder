import math
import os

import pygame

from config import (FONT_DIR, FONTS, W, PANEL, PANEL_L, WHITE, SOFT, DIM,
                    TEAL, GOLD)
from render3d import clamp, mix

_FONT_CACHE = {}
_TEXT_CACHE = {}
_PANEL_CACHE = {}


def font(style, size):
    key = (style, size)
    f = _FONT_CACHE.get(key)
    if f is not None:
        return f
    names = (FONTS.get(style, 'segoeui.ttf'), 'segoeui.ttf', 'arial.ttf')
    f = None
    for name in names:
        path = os.path.join(FONT_DIR, name)
        if os.path.exists(path):
            try:
                f = pygame.font.Font(path, max(6, int(size)))
                break
            except Exception:
                pass
    if f is None:
        f = pygame.font.Font(None, max(6, int(size)))
    _FONT_CACHE[key] = f
    return f


def _render(s, size, style, col, track, alpha):
    key = (s, size, style, col, track, alpha)
    surf = _TEXT_CACHE.get(key)
    if surf is not None:
        return surf
    f = font(style, size)
    if track:
        widths = [f.size(ch)[0] for ch in s]
        total = sum(widths) + track * (len(s) - 1)
        surf = pygame.Surface((max(1, int(total) + 4), f.get_height() + 2),
                              pygame.SRCALPHA)
        x = 2.0
        for ch, w in zip(s, widths):
            glyph = f.render(ch, True, col)
            surf.blit(glyph, (int(x), 1))
            x += w + track
    else:
        surf = f.render(s, True, col)
    if alpha < 1.0:
        surf = surf.copy()
        surf.set_alpha(int(255 * clamp(alpha)))
    if len(_TEXT_CACHE) > 2200:
        _TEXT_CACHE.clear()
    _TEXT_CACHE[key] = surf
    return surf


def text(dst, x, y, s, size=16, style='mono', col=WHITE, align='l',
         track=0.0, alpha=1.0, shadow=None):
    if not s or alpha <= 0.01:
        return
    surf = _render(s, size, style, col, track, round(alpha, 2))
    w = surf.get_width()
    if align == 'c':
        x -= w / 2
    elif align == 'r':
        x -= w
    if shadow:
        sh = _render(s, size, style, shadow, track, round(alpha * 0.75, 2))
        dst.blit(sh, (int(x + 1), int(y + 1)))
    dst.blit(surf, (int(x), int(y)))


def set_cursor(hand):
    try:
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if hand
                                else pygame.SYSTEM_CURSOR_ARROW)
    except pygame.error:
        pass


def text_w(s, size=16, style='mono', track=0.0):
    if not s:
        return 0
    if not track:
        return font(style, size).size(s)[0]
    f = font(style, size)
    return int(sum(f.size(ch)[0] for ch in s) + track * (len(s) - 1))


def panel(dst, x0, y0, x1, y1, fill=PANEL, alpha=1.0, radius=12,
          outline=None, width=1):
    w, h = int(x1 - x0), int(y1 - y0)
    if w <= 0 or h <= 0:
        return
    if alpha >= 0.999:
        pygame.draw.rect(dst, fill, (int(x0), int(y0), w, h), border_radius=radius)
        if outline:
            pygame.draw.rect(dst, outline, (int(x0), int(y0), w, h),
                             width=width, border_radius=radius)
        if h > 8 and w > 16:
            pygame.draw.line(dst, mix(WHITE, fill, 0.88),
                             (int(x0) + radius, int(y0) + 1),
                             (int(x1) - radius, int(y0) + 1), 1)
        return
    key = (w, h, fill, round(alpha, 2), radius, outline, width)
    surf = _PANEL_CACHE.get(key)
    if surf is None:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (*fill, int(255 * clamp(alpha))),
                         (0, 0, w, h), border_radius=radius)
        if outline:
            pygame.draw.rect(surf, (*outline, int(255 * clamp(alpha))),
                             (0, 0, w, h), width=width, border_radius=radius)
        if h > 8 and w > 16:
            hl = mix(WHITE, fill, 0.86)
            pygame.draw.line(surf, (*hl, int(80 * clamp(alpha))),
                             (radius, 1), (w - radius, 1), 1)
        if len(_PANEL_CACHE) > 400:
            _PANEL_CACHE.clear()
        _PANEL_CACHE[key] = surf
    dst.blit(surf, (int(x0), int(y0)))


def bar(dst, x, y, w, h, frac, col, bg=(20, 32, 54), alpha=1.0):
    frac = clamp(frac)
    r = h // 2
    panel(dst, x, y, x + w, y + h, bg, alpha=alpha, radius=r)
    if frac > 0.02:
        panel(dst, x, y, x + max(h, w * frac), y + h, col, alpha=alpha, radius=r)


def chip(dst, x, y, w, h, label, col=SOFT, fill=None, size=10, style='mono',
         track=1.2, alpha=1.0, radius=6):
    if fill:
        panel(dst, x, y, x + w, y + h, fill, alpha=alpha, radius=radius)
    text(dst, x + w / 2, y + h / 2 - size * 0.62, label, size, style, col,
         'c', track, alpha)


def coin(dst, cx, cy, r, spin=0.0, col=GOLD):
    w = r * (0.42 + 0.58 * abs(math.cos(spin)))
    pygame.draw.ellipse(dst, mix(col, (60, 40, 10), 0.55),
                        (int(cx - w), int(cy - r), int(2 * w), int(2 * r)))
    pygame.draw.ellipse(dst, col,
                        (int(cx - w * 0.80), int(cy - r * 0.80),
                         int(1.6 * w), int(1.6 * r)))
    if w > r * 0.62:
        pygame.draw.polygon(dst, mix(col, (120, 78, 18), 0.55), [
            (cx, cy - r * 0.40), (cx + w * 0.34, cy),
            (cx, cy + r * 0.40), (cx - w * 0.34, cy)])


def star(dst, cx, cy, r, col, a=1.0, rot=-math.pi / 2):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.44
        ang = rot + math.pi * i / 5
        pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
    pygame.draw.polygon(dst, mix(col, PANEL, a), pts)


def bolt(dst, cx, cy, s, col):
    pygame.draw.polygon(dst, col, [
        (cx + s * 0.18, cy - s), (cx - s * 0.42, cy + s * 0.12),
        (cx - s * 0.02, cy + s * 0.12), (cx - s * 0.18, cy + s),
        (cx + s * 0.46, cy - s * 0.18), (cx + s * 0.04, cy - s * 0.18)])


# ---------------- icons ----------------
def icon_body(dst, cx, cy, r, col, lw=2):
    pygame.draw.rect(dst, col, (int(cx - r * 0.44), int(cy - r * 0.7),
                                int(r * 0.88), int(r * 1.4)),
                     width=lw, border_radius=int(r * 0.32))
    pygame.draw.polygon(dst, col, [(cx - r * 0.22, cy - r * 0.7),
                                   (cx, cy - r * 1.05),
                                   (cx + r * 0.22, cy - r * 0.7)])


def icon_rotor(dst, cx, cy, r, col, lw=2):
    pygame.draw.circle(dst, col, (int(cx), int(cy)), int(r * 0.95), lw)
    pygame.draw.circle(dst, col, (int(cx), int(cy)), int(r * 0.22), lw)
    for i in range(4):
        a = math.pi * i / 2 + math.pi / 4
        pygame.draw.line(dst, col, (cx + math.cos(a) * r * 0.24, cy + math.sin(a) * r * 0.24),
                         (cx + math.cos(a) * r * 0.9, cy + math.sin(a) * r * 0.9), lw)


def icon_wing(dst, cx, cy, r, col, lw=2):
    pygame.draw.polygon(dst, col, [(cx - r, cy + r * 0.42), (cx + r, cy - r * 0.1),
                                   (cx + r * 0.86, cy - r * 0.5),
                                   (cx - r * 0.96, cy + r * 0.02)], lw)


def icon_booster(dst, cx, cy, r, col, lw=2):
    pygame.draw.rect(dst, col, (int(cx - r * 0.7), int(cy - r * 0.38),
                                int(r * 1.1), int(r * 0.76)), width=lw, border_radius=int(r * 0.2))
    pygame.draw.polygon(dst, col, [(cx + r * 0.4, cy - r * 0.38),
                                   (cx + r * 0.9, cy - r * 0.56),
                                   (cx + r * 0.9, cy + r * 0.56),
                                   (cx + r * 0.4, cy + r * 0.38)], lw)


def icon_frame(dst, cx, cy, r, col, lw=2):
    pygame.draw.line(dst, col, (cx - r * 0.82, cy - r * 0.82),
                     (cx + r * 0.82, cy + r * 0.82), lw)
    pygame.draw.line(dst, col, (cx - r * 0.82, cy + r * 0.82),
                     (cx + r * 0.82, cy - r * 0.82), lw)
    pygame.draw.rect(dst, col, (int(cx - r * 0.24), int(cy - r * 0.24),
                                int(r * 0.48), int(r * 0.48)), lw, border_radius=2)


def icon_motor(dst, cx, cy, r, col, lw=2):
    pygame.draw.circle(dst, col, (int(cx), int(cy)), int(r * 0.62), lw)
    pygame.draw.circle(dst, col, (int(cx), int(cy)), int(r * 0.18), lw)
    for i in range(3):
        a = math.pi * 2 * i / 3 - math.pi / 2
        pygame.draw.line(dst, col,
                         (cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62),
                         (cx + math.cos(a) * r * 0.96, cy + math.sin(a) * r * 0.96), lw)


def icon_paint(dst, cx, cy, r, col, lw=2):
    pygame.draw.rect(dst, col, (int(cx - r * 0.85), int(cy - r * 0.62),
                                int(r * 1.7), int(r * 1.24)), lw,
                     border_radius=int(r * 0.24))
    pygame.draw.rect(dst, col, (int(cx - r * 0.52), int(cy - r * 0.3),
                                int(r * 0.44), int(r * 0.6)))
    pygame.draw.rect(dst, col, (int(cx + 0.08 * r), int(cy - r * 0.3),
                                int(r * 0.44), int(r * 0.6)))


def icon_lock(dst, cx, cy, r, col, lw=2):
    pygame.draw.rect(dst, col, (int(cx - r * 0.62), int(cy - r * 0.08),
                                int(r * 1.24), int(r * 0.9)), width=lw, border_radius=3)
    pygame.draw.arc(dst, col, (int(cx - r * 0.42), int(cy - r * 0.78),
                               int(r * 0.84), int(r * 0.9)), 0.05, 3.09, lw)


def icon_forge(dst, cx, cy, r, col, lw=2):
    pygame.draw.circle(dst, col, (int(cx), int(cy)), int(r * 0.42), lw)
    for i in range(8):
        a = math.pi * i / 4
        pygame.draw.line(dst, col, (cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55),
                         (cx + math.cos(a) * r * 0.92, cy + math.sin(a) * r * 0.92), lw)


ICONS = {'body': icon_body, 'frame': icon_frame, 'rotor': icon_rotor,
         'motor': icon_motor, 'wing': icon_wing, 'booster': icon_booster,
         'paint': icon_paint}


# ---------------- widgets ----------------
class Button:
    def __init__(self, key, rect, label, kind='gold', size=15, style='mono',
                 track=2.2, sub=None):
        self.key = key
        self.rect = pygame.Rect(*[int(v) for v in rect])
        self.label = label
        self.kind = kind
        self.size = size
        self.style = style
        self.track = track
        self.sub = sub

    def hit(self, pos):
        return self.rect.collidepoint(pos)

    def draw(self, dst, hover=False, enabled=True, alpha=1.0):
        x, y, w, h = self.rect
        if self.kind == 'gold':
            base = GOLD if enabled else (86, 84, 78)
            if hover and enabled:
                base = (255, 218, 140)
            panel(dst, x, y, x + w, y + h, base, alpha, radius=8)
            tcol = (20, 16, 8) if enabled else (52, 50, 46)
        elif self.kind == 'teal':
            base = TEAL if enabled else (70, 92, 92)
            if hover and enabled:
                base = (120, 255, 240)
            panel(dst, x, y, x + w, y + h, base, alpha, radius=8)
            tcol = (8, 24, 22)
        else:
            base = PANEL_L
            panel(dst, x, y, x + w, y + h, PANEL_L,
                  alpha * (0.95 if hover else 0.75), radius=8,
                  outline=(70, 104, 146) if enabled else (44, 56, 72))
            tcol = (SOFT if enabled else (70, 86, 108))
            if hover and enabled:
                tcol = WHITE
        dy = 0
        if self.sub:
            dy = -6
        text(dst, x + w / 2, y + h / 2 - self.size * 0.62 + dy, self.label,
             self.size, self.style, tcol, 'c', self.track, alpha)
        if self.sub:
            text(dst, x + w / 2, y + h / 2 + 9, self.sub, 10, 'mono',
                 mix(tcol, base, 0.55), 'c', 1.4, alpha)


class Slider:
    def __init__(self, key, label, lo, hi, value, fmt='{:.2f}', step=0.001):
        self.key = key
        self.label = label
        self.lo = lo
        self.hi = hi
        self.value = value
        self.fmt = fmt
        self.step = step
        self.rect = pygame.Rect(0, 0, 100, 44)
        self.dragging = False

    def place(self, x, y, w):
        self.rect = pygame.Rect(int(x), int(y), int(w), 44)

    def _apply(self, mx):
        frac = clamp((mx - self.rect.x - 10) / max(1.0, self.rect.w - 20))
        v = self.lo + frac * (self.hi - self.lo)
        if self.step:
            v = round(v / self.step) * self.step
        self.value = clamp(v, self.lo, self.hi)

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            zone = pygame.Rect(self.rect.x - 6, self.rect.y + 18,
                               self.rect.w + 12, 34)
            if zone.collidepoint(e.pos):
                self.dragging = True
                self._apply(e.pos[0])
                return True
        elif e.type == pygame.MOUSEMOTION and self.dragging:
            self._apply(e.pos[0])
            return True
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            was = self.dragging
            self.dragging = False
            return was
        return False

    def draw(self, dst, alpha=1.0, accent=TEAL):
        x, y, w = self.rect.x, self.rect.y, self.rect.w
        text(dst, x, y, self.label, 12, 'bold', SOFT, track=1.6, alpha=alpha)
        text(dst, x + w, y, self.fmt.format(self.value), 12, 'mono', accent,
             'r', alpha=alpha)
        ty = y + 26
        pygame.draw.line(dst, (34, 52, 80), (x + 4, ty), (x + w - 4, ty), 3)
        frac = (self.value - self.lo) / max(1e-9, self.hi - self.lo)
        kx = x + 10 + (w - 20) * frac
        pygame.draw.line(dst, accent, (x + 4, ty), (kx, ty), 3)
        pygame.draw.circle(dst, (10, 18, 32), (int(kx), int(ty)), 7)
        pygame.draw.circle(dst, accent, (int(kx), int(ty)), 5)


def toast(dst, msg, sub, k, col=GOLD, cx=None):
    if k <= 0.0:
        return
    a = smooth_in_out(k)
    w, h = 430, 56
    x, y = (W / 2 if cx is None else cx) - w / 2, 74
    glow_col = col
    panel(dst, x, y, x + w, y + h, (9, 16, 30), a * 0.94, radius=9,
          outline=mix(glow_col, (9, 16, 30), 0.55))
    pygame.draw.rect(dst, mix(glow_col, (9, 16, 30), 0.5),
                     (int(x + 2), int(y + 8), 3, h - 16), border_radius=2)
    text(dst, x + 22, y + 10, msg, 15, 'bold', WHITE, track=1.6, alpha=a)
    if sub:
        text(dst, x + 22, y + 33, sub, 11, 'mono', mix(glow_col, DIM, 0.5),
             track=1.2, alpha=a)


def smooth_in_out(k):
    k = clamp(k)
    if k < 0.12:
        return k / 0.12
    if k > 0.85:
        return (1 - k) / 0.15
    return 1.0
