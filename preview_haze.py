import os
import time

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from config import W, H
from main import App

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'previews')


def main():
    pygame.init()
    win = pygame.display.set_mode((W, H))
    app = App(test=True)
    app.set_scene('flight')
    app.fade = 0.0
    for _ in range(int(7.4 * 60)):
        app.update(1.0 / 60.0)
    app.draw(win)
    os.makedirs(OUT, exist_ok=True)
    a = os.path.join(OUT, 'flight_haze_a.png')
    pygame.image.save(win, a)

    for _ in range(int(3.0 * 60)):
        app.update(1.0 / 60.0)
    app.draw(win)
    b = os.path.join(OUT, 'flight_haze_b.png')
    pygame.image.save(win, b)

    t0 = time.perf_counter()
    for _ in range(40):
        app.update(1.0 / 60.0)
        app.draw(win)
    ms = (time.perf_counter() - t0) / 40 * 1000.0
    print(a)
    print(b)
    print('avg frame ms: %.2f' % ms)


if __name__ == '__main__':
    main()
