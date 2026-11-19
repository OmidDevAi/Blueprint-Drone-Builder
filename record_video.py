"""Render a real gameplay clip from the pygame build to PNG frames.

Run:  python record_video.py [outdir]
Then encode with ffmpeg at 30 fps.
"""
import os
import shutil
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import pygame

from config import W, H, PAINTS, FPS
from main import App, fit_std_airframe

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'rec_frames')

SAVE_EVERY = 2          # render at 60 Hz, keep 30 fps


class Recorder:
    def __init__(self, win):
        self.win = win
        self.i = 0
        self.buf = 0

    def tick(self, app, n=1):
        for _ in range(n):
            app.update(1.0 / FPS)
            app.draw(self.win)
            if self.buf % SAVE_EVERY == 0:
                pygame.image.save(self.win, os.path.join(OUT, 'f_%05d.png' % self.i))
                self.i += 1
            self.buf += 1


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    pygame.init()
    win = pygame.display.set_mode((W, H))
    pygame.display.set_caption('BLUEPRINT — capture')
    app = App(test=True)
    rec = Recorder(win)

    app.set_scene('hangar')
    hang = app.scene
    fit_std_airframe(hang)
    hang.apply_paint(PAINTS[4])
    rec.tick(app, 24)

    # slow turntable drag, like a player inspecting the build
    for k in range(110):
        hang.yaw_off = -0.4 + 1.1 * (k / 110.0)
        rec.tick(app, 1)

    # street circuit
    app.state['sector'] = 0
    app.set_scene('flight')
    street = app.scene
    rec.tick(app, int(9.0 * FPS))

    # forest run
    app.state['sector'] = 1
    app.set_scene('flight')
    forest = app.scene
    rec.tick(app, int(8.0 * FPS))

    print('frames:', rec.i, 'street z:', round(street.z), 'mode:', street.mode,
          '| forest z:', round(forest.z), 'mode:', forest.mode)
    pygame.quit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
