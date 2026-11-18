import pygame

from config import W, PANEL, PANEL_L, WHITE, SOFT, DIM, TEAL, GOLD, GOLD_D
from render3d import mix
from ui import panel, text, coin


def topbar(win, credits, spin, sector=None, alpha=1.0):
    panel(win, 0, 0, W, 56, (9, 15, 29), 0.94 * alpha, radius=0)
    pygame.draw.line(win, (20, 34, 58), (0, 56), (W, 56), 1)
    pygame.draw.line(win, mix(GOLD, (9, 15, 29), 0.82), (26, 55), (250, 55), 1)

    cx, cy = 31, 28
    pygame.draw.polygon(win, GOLD, [(cx, cy - 12), (cx + 10, cy), (cx, cy + 12), (cx - 10, cy)])
    pygame.draw.polygon(win, mix(GOLD_D, (9, 15, 29), 0.35),
                        [(cx, cy - 6), (cx + 5, cy), (cx, cy + 6), (cx - 5, cy)])
    text(win, 50, 13, 'BLUEPRINT', 20, 'tech', WHITE, track=3.4, alpha=alpha)
    text(win, 52, 36, 'AIRFRAME LAB', 9, 'mono', mix(DIM, (9, 15, 29), 0.55),
         track=2.6, alpha=alpha)

    if sector:
        panel(win, 838, 10, 1014, 46, PANEL_L, 0.85 * alpha, radius=8,
              outline=(38, 58, 88))
        pygame.draw.circle(win, TEAL, (854, 28), 3)
        pygame.draw.circle(win, mix(TEAL, PANEL_L, 0.6), (854, 28), 6, 1)
        text(win, 868, 13, sector[0], 14, 'tech', WHITE, track=1.8, alpha=alpha)
        text(win, 869, 32, sector[1], 9, 'mono', mix(DIM, PANEL_L, 0.6),
             track=1.4, alpha=alpha)

    panel(win, 1030, 10, 1264, 46, PANEL_L, 0.85 * alpha, radius=8,
          outline=(46, 66, 96))
    coin(win, 1048, 28, 9, spin)
    text(win, 1249, 16, '{:,}'.format(int(credits)), 16, 'tech', GOLD, 'r',
         track=0.6, alpha=alpha)
    text(win, 1249, 34, 'CREDITS', 8, 'mono', mix(DIM, PANEL_L, 0.55), 'r',
         track=1.8, alpha=alpha)


def section(win, x, y, label, col=SOFT, size=10, track=2.2, alpha=1.0):
    text(win, x, y, label, size, 'bold', col, track=track, alpha=alpha)
    w = win.get_width()
    return w


def stat_row(win, x0, x1, y, label, value, frac, col, alpha=1.0):
    from ui import bar
    text(win, x0, y, label, 10, 'mono', mix(SOFT, PANEL, 0.62), track=1.4, alpha=alpha)
    text(win, x1, y - 2, value, 13, 'mono', col, 'r', alpha=alpha)
    bar(win, x0, y + 16, x1 - x0, 3, frac, col, bg=(22, 36, 58), alpha=alpha)
