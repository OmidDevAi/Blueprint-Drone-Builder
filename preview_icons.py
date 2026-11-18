import os
import time

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from config import W, H, PANEL, SOFT, TEAL, GOLD, CYAN, DIM, WHITE
from hud import stat_row
from icons import icon, strip
from ui import panel, text

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'previews')

ROWS = (
    ('MASS', '218 KG', 0.64, SOFT, 'mass'),
    ('THRUST', '352', 0.84, TEAL, 'thrust'),
    ('DRAG', '5.40', 0.39, (255, 104, 104), 'drag'),
    ('TOP SPEED', '21 KM/H', 0.56, GOLD, 'speed'),
    ('AGILITY', '74', 0.74, CYAN, 'agility'),
    ('BOOST', '96', 0.80, TEAL, 'boost'),
)


def main():
    pygame.init()
    win = pygame.display.set_mode((W, H))
    win.fill((10, 17, 30))
    panel(win, 40, 40, 640, 480, PANEL, 0.95, radius=12, outline=(30, 46, 72))
    text(win, 60, 60, 'PERFORMANCE', 14, 'bold', SOFT, track=2.4)
    text(win, 660, 62, 'ICON PASS', 10, 'mono', TEAL, 'r', track=1.6)
    for i, (lab, val, frac, col, ico) in enumerate(ROWS):
        stat_row(win, 60, 660, 100 + i * 46, lab, val, frac, col, icon_name=ico)

    text(win, 60, 396, 'ICON SET', 10, 'bold', DIM, track=2.4)
    names = ['mass', 'thrust', 'drag', 'speed', 'agility', 'boost', 'fuel', 'altitude']
    strip(win, 60, 420, names, 22, WHITE, gap=16)
    strip(win, 60, 452, names, 32, GOLD, gap=14)

    os.makedirs(OUT, exist_ok=True)
    sheet = os.path.join(OUT, 'hud_icons.png')
    pygame.image.save(win, sheet)

    t0 = time.perf_counter()
    for _ in range(120):
        for i, (lab, val, frac, col, ico) in enumerate(ROWS):
            stat_row(win, 60, 660, 100 + i * 46, lab, val, frac, col, icon_name=ico)
        strip(win, 690, 100, names, 22, WHITE, gap=10)
    ms = (time.perf_counter() - t0) / 120 * 1000.0
    print(sheet)
    print('icon pass: {:.2f} ms/frame (cached)'.format(ms))


if __name__ == '__main__':
    main()
