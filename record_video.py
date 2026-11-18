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
    rec.tick(app, 30)

    # slow turntable drag, like a player inspecting the build
    for k in range(240):
        hang.yaw_off = -0.45 + 1.25 * (k / 240.0)
        rec.tick(app, 1)

    # editor: pull the silhouette sliders, then pick a material
    app.set_scene('editor')
    ed = app.scene
    ed.sliders[0].value = 0.30
    ed.sliders[1].value = 0.10
    ed.sliders[2].value = 7
    ed.sliders[3].value = 0.10
    ed.sliders[4].value = 0.018
    ed.rebuild()
    rec.tick(app, 150)
    for k in range(90):
        ed.sliders[0].value = 0.30 + 0.18 * (k / 90.0)
        ed.sliders[2].value = 7 + 2 * (k / 90.0)
        ed.rebuild()
        rec.tick(app, 1)
    ed.params['material'] = 'carbon'
    ed.rebuild()
    rec.tick(app, 30)

    # flight, autopilot, until the run is graded
    app.set_scene('flight')
    app.fade = 0.0
    fl = app.scene
    t = 0.0
    while fl.mode != 'result' and t < 40.0:
        rec.tick(app, 1)
        t += 1.0 / FPS
    rec.tick(app, 75)          # hold the result card

    print('frames:', rec.i, 'flight seconds:', round(t, 1), 'mode:', fl.mode)
    pygame.quit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
