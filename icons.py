import pygame

from render3d import clamp, mix

_CACHE = {}
_SS = 3  # supersample factor, downscaled for cheap antialiasing


def _poly(dst, pts, col):
    pygame.draw.polygon(dst, col, pts)


def _draw(dst, name, s, col, acc):
    """Draw one pictogram into an s*s supersampled surface."""
    def p(points):
        return [(px * s, py * s) for px, py in points]

    if name == 'mass':
        # weight plate: heavy block with a small collar on top
        _poly(dst, p([(0.20, 0.40), (0.80, 0.40), (0.80, 0.76), (0.20, 0.76)]), col)
        _poly(dst, p([(0.38, 0.22), (0.62, 0.22), (0.62, 0.40), (0.38, 0.40)]), acc)
    elif name == 'thrust':
        _poly(dst, p([(0.50, 0.16), (0.72, 0.42), (0.61, 0.42), (0.61, 0.56),
                      (0.39, 0.56), (0.39, 0.42), (0.28, 0.42)]), col)
        _poly(dst, p([(0.50, 0.52), (0.66, 0.74), (0.57, 0.74), (0.57, 0.84),
                      (0.43, 0.84), (0.43, 0.74), (0.34, 0.74)]), acc)
    elif name == 'drag':
        pygame.draw.line(dst, col, p([(0.16, 0.34), (0.62, 0.34)])[0],
                         p([(0.62, 0.34)])[0], max(1, int(0.10 * s)))
        pygame.draw.line(dst, acc, p([(0.28, 0.50), (0.84, 0.50)])[0],
                         p([(0.84, 0.50)])[0], max(1, int(0.10 * s)))
        pygame.draw.line(dst, col, p([(0.20, 0.66), (0.56, 0.66)])[0],
                         p([(0.56, 0.66)])[0], max(1, int(0.10 * s)))
        _poly(dst, p([(0.74, 0.62), (0.86, 0.66), (0.74, 0.70)]), col)
    elif name == 'speed':
        rect = pygame.Rect(int(0.14 * s), int(0.26 * s), int(0.72 * s), int(0.72 * s))
        pygame.draw.arc(dst, col, rect, 0.6, 2.55, max(1, int(0.09 * s)))
        pygame.draw.line(dst, acc, p([(0.50, 0.62), (0.72, 0.40)])[0],
                         p([(0.72, 0.40)])[0], max(1, int(0.09 * s)))
        _poly(dst, p([(0.46, 0.66), (0.54, 0.66), (0.50, 0.58)]), acc)
    elif name == 'agility':
        rect = pygame.Rect(int(0.18 * s), int(0.18 * s), int(0.64 * s), int(0.64 * s))
        pygame.draw.arc(dst, col, rect, 0.5, 5.3, max(1, int(0.09 * s)))
        _poly(dst, p([(0.78, 0.20), (0.90, 0.34), (0.70, 0.36)]), acc)
    elif name == 'boost':
        _poly(dst, p([(0.56, 0.12), (0.30, 0.56), (0.46, 0.56),
                      (0.40, 0.88), (0.70, 0.42), (0.52, 0.42),
                      (0.62, 0.12)]), col)
    elif name == 'fuel':
        _poly(dst, p([(0.50, 0.14), (0.74, 0.46), (0.74, 0.62), (0.66, 0.76),
                      (0.50, 0.84), (0.34, 0.76), (0.26, 0.62), (0.26, 0.46)]), col)
        _poly(dst, p([(0.50, 0.32), (0.60, 0.50), (0.54, 0.66), (0.46, 0.66),
                      (0.40, 0.50)]), acc)
    elif name == 'altitude':
        _poly(dst, p([(0.50, 0.12), (0.70, 0.32), (0.58, 0.32), (0.58, 0.58),
                      (0.42, 0.58), (0.42, 0.32), (0.30, 0.32)]), col)
        pygame.draw.line(dst, acc, p([(0.24, 0.74), (0.76, 0.74)])[0],
                         p([(0.76, 0.74)])[0], max(1, int(0.11 * s)))


def icon(dst, name, x, y, size, col, alpha=1.0):
    """Blit a cached pictogram whose box is ``size`` pixels at (x, y)."""
    a = round(clamp(alpha), 2)
    if a <= 0.02:
        return
    key = (name, int(size), tuple(col), a)
    surf = _CACHE.get(key)
    if surf is None:
        n = int(size) * _SS
        big = pygame.Surface((n, n), pygame.SRCALPHA)
        acc = mix(col, (8, 14, 26), 0.45)
        _draw(big, name, n, col, acc)
        surf = pygame.transform.smoothscale(big, (int(size), int(size)))
        if len(_CACHE) > 400:
            _CACHE.clear()
        _CACHE[key] = surf
    if a < 1.0:
        surf = surf.copy()
        surf.set_alpha(int(255 * a))
    dst.blit(surf, (int(x), int(y)))


def strip(win, x, y, names, size, col, gap=10, alpha=1.0):
    """Convenience: draw a horizontal row of icons; returns the right edge."""
    for n in names:
        icon(win, n, x, y, size, col, alpha)
        x += size + gap
    return x - gap
