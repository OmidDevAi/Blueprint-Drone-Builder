"""Screen-space bloom for the anime grade. C-level blends only."""

import pygame

from config import SW, SH

_SMALL = None
_TINY = None
_THRESH = None
_GAIN = {}
_WRAP = None


def _solid(size, col):
    s = pygame.Surface(size).convert()
    s.fill(col)
    return s


def light_wrap(buf, warm=(255, 228, 180), cool=(120, 164, 230),
               warm_a=24, cool_a=14):
    global _WRAP
    if _WRAP is None:
        _WRAP = pygame.Surface((SW, SH)).convert()
        for x in range(SW):
            w = 1.0 - x / (SW - 1)
            c = tuple(int(warm[i] * w * warm_a / 255.0 +
                          cool[i] * (1.0 - w) * cool_a / 255.0)
                      for i in range(3))
            pygame.draw.line(_WRAP, c, (x, 0), (x, SH))
    buf.blit(_WRAP, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def _ensure():
    global _SMALL, _TINY, _THRESH
    w, h = SW // 4, SH // 4
    if _SMALL is None:
        _SMALL = pygame.Surface((w, h)).convert()
        _TINY = pygame.Surface((w // 3, h // 3)).convert()
        _THRESH = _solid((w, h), (186, 186, 186))


def bloom(buf, strength=0.95):
    _ensure()
    small = pygame.transform.smoothscale(buf, _SMALL.get_size(), _SMALL)
    small.blit(_THRESH, (0, 0), special_flags=pygame.BLEND_RGB_SUB)

    tiny = pygame.transform.smoothscale(small, _TINY.get_size(), _TINY)
    pygame.transform.smoothscale(tiny, small.get_size(), small)

    k = max(0, min(255, int(255 * strength)))
    gain = _GAIN.get(k)
    if gain is None:
        gain = _solid(small.get_size(), (k, k, k))
        _GAIN[k] = gain
    small.blit(gain, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    big = pygame.transform.smoothscale(small, (SW, SH))
    buf.blit(big, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def finish(buf):
    light_wrap(buf)
    bloom(buf)
