import os

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
    app.set_scene('hangar')
    app.fade = 0.0
    for _ in range(90):
        app.update(1.0 / 60.0)
    app.draw(win)
    os.makedirs(OUT, exist_ok=True)
    full = os.path.join(OUT, 'hangar_icons_full.png')
    pygame.image.save(win, full)
    crop = win.subsurface(pygame.Rect(960, 56, 320, 392)).copy()
    crop = pygame.transform.scale(crop, (640, 784))
    crop_path = os.path.join(OUT, 'hangar_perf_panel.png')
    pygame.image.save(crop, crop_path)
    print(full)
    print(crop_path)


if __name__ == '__main__':
    main()
