import random

import pygame

from config import SW, SH, W, H, BG_TOP, BG_BOT
from render3d import mix, gradient_bg, vignette

_SKY = {}


def sky_surface(top, bot, stars=True):
    key = (top, bot, stars)
    s = _SKY.get(key)
    if s is not None:
        return s
    s = gradient_bg(SW, SH, top, bot)
    if stars:
        rnd = random.Random(11)
        for _ in range(80):
            x = rnd.uniform(0, SW)
            y = rnd.uniform(0, SH * 0.62)
            r = rnd.choice((0.6, 0.8, 1.0, 1.3))
            c = mix((36, 54, 88), (190, 214, 250), rnd.uniform(0.08, 0.6))
            pygame.draw.circle(s, c, (int(x), int(y)), max(1, int(r)))
    _SKY[key] = s
    return s


class Scene:
    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.buf = pygame.Surface((SW, SH)).convert()
        self.top_col = BG_TOP
        self.bot_col = BG_BOT

    def enter(self):
        pass

    def handle(self, e):
        pass

    def update(self, dt):
        self.t += dt

    def draw(self, win):
        pass

    def base_sky(self):
        self.buf.blit(sky_surface(self.top_col, self.bot_col), (0, 0))

    def blit(self, win):
        self.buf.blit(vignette(SW, SH, 0.5), (0, 0),
                      special_flags=pygame.BLEND_RGB_MULT)
        pygame.transform.smoothscale(self.buf, (W, H), win)
