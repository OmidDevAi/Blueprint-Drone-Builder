import argparse
import os
import sys
import time

os.environ.setdefault('SDL_VIDEO_CENTERED', '1')

import pygame

from config import (W, H, FPS, SAVE_PATH, SAVE_DIR, GOLD, START_CREDITS,
                    PAINTS)
from save import load_state, save_state, default_state
from scenes.hangar import Hangar
from scenes.editor import Editor
from scenes.flight import Flight
from ui import toast
from parts import (ROTORS, BODIES, FRAMES, MOTORS, WINGS, BOOSTERS, SOCKETS)
import audio


class App:
    def __init__(self, test=False):
        self.test = test
        self.save_path = os.path.join(SAVE_DIR, 'save_test.json') if test else SAVE_PATH
        self.state = default_state() if test else load_state(self.save_path)
        self.scene = None
        self.scene_name = ''
        self.toasts = []
        self.coin_spin = 0.0
        self.fade = 1.0
        self.frame_ms = 0.0
        self.fade_surf = pygame.Surface((W, H))
        self.fade_surf.fill((3, 5, 10))
        audio.set_mute(self.state.get('mute', False))
        self.set_scene('hangar')

    def save(self):
        save_state(self.state, self.save_path)

    def toggle_mute(self):
        self.state['mute'] = not self.state.get('mute', False)
        audio.set_mute(self.state['mute'])
        self.save()
        return self.state['mute']

    def toast(self, msg, sub='', col=GOLD):
        self.toasts.append({'msg': msg, 'sub': sub, 'col': col, 't': 0.0})

    def set_scene(self, name, **kw):
        if name == 'hangar':
            self.scene = Hangar(self)
        elif name == 'editor':
            self.scene = Editor(self)
        elif name == 'flight':
            self.scene = Flight(self, **kw)
        else:
            return
        self.scene_name = name
        self.scene.enter()
        self.fade = 1.0

    def update(self, dt):
        self.coin_spin += dt * 2.0
        for t in self.toasts:
            t['t'] += dt
        self.toasts = [t for t in self.toasts if t['t'] < 2.6]
        self.scene.update(dt)
        self.fade = max(0.0, self.fade - dt * 4.0)

    def draw(self, win):
        self.scene.draw(win)
        cx = 560 if self.scene_name == 'editor' else None
        for t in self.toasts:
            toast(win, t['msg'], t['sub'], t['t'] / 2.6, t['col'], cx)
        if self.fade > 0.002:
            if self.fade >= 0.995:
                # per-surface alpha 255 hits a slow SDL blit path on Windows
                self.fade_surf.set_alpha(None)
            else:
                self.fade_surf.set_alpha(max(1, min(254, int(255 * self.fade))))
            win.blit(self.fade_surf, (0, 0))


def fit(hang, slot, key, entry):
    hang.slot = slot
    hang.socket = (slot, key)
    hang.activate(entry)


def fit_std_airframe(hang, extras=True):
    fit(hang, 'body', 'c', BODIES[0])
    fit(hang, 'frame', 'c', FRAMES[0])
    keys = [k for k, _ in SOCKETS['rotor']]
    for k in keys:
        fit(hang, 'rotor', k, ROTORS[0])
    for k in keys:
        fit(hang, 'motor', k, MOTORS[0])
    if extras:
        for k, _ in SOCKETS['wing']:
            fit(hang, 'wing', k, WINGS[0])
        for k, _ in SOCKETS['booster']:
            fit(hang, 'booster', k, BOOSTERS[0])


def run_shots(app, win):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots')
    os.makedirs(out, exist_ok=True)

    def settle(n=22):
        for _ in range(n):
            app.update(1.0 / 60.0)

    app.set_scene('hangar')
    settle()
    app.draw(win)
    pygame.image.save(win, os.path.join(out, '01_hangar_empty.png'))

    hang = app.scene
    hang.slot = 'paint'
    hang.scroll = 0
    settle(3)
    app.draw(win)
    pygame.image.save(win, os.path.join(out, '02_paint.png'))

    fit_std_airframe(hang)
    hang.slot = 'rotor'
    hang.socket = ('rotor', 'fl')
    hang.apply_paint(PAINTS[2])
    settle(170)
    app.draw(win)
    pygame.image.save(win, os.path.join(out, '03_hangar_built.png'))

    app.set_scene('editor')
    ed = app.scene
    ed.sliders[0].value = 0.41
    ed.sliders[1].value = 0.112
    ed.sliders[2].value = 9
    ed.sliders[3].value = 0.12
    ed.sliders[4].value = 0.021
    ed.params['material'] = 'carbon'
    ed.rebuild()
    settle()
    app.draw(win)
    pygame.image.save(win, os.path.join(out, '04_editor.png'))

    app.set_scene('flight')
    app.fade = 0.0
    for _ in range(int(7.4 * 60)):
        app.update(1.0 / 60.0)
    app.draw(win)
    pygame.image.save(win, os.path.join(out, '05_flight.png'))

    for _ in range(int(14 * 60)):
        app.update(1.0 / 60.0)
    app.draw(win)
    pygame.image.save(win, os.path.join(out, '06_result.png'))

    app.set_scene('flight')
    app.fade = 0.0
    for _ in range(int(3.4 * 60)):
        app.update(1.0 / 60.0)
    app.scene.crash('MINE STRIKE')
    for _ in range(int(0.42 * 60)):
        app.update(1.0 / 60.0)
        app.draw(win)
    pygame.image.save(win, os.path.join(out, '07_crash.png'))

    app.set_scene('flight')
    app.fade = 0.0
    for _ in range(int(2.2 * 60)):
        app.update(1.0 / 60.0)
    app.scene.paused = True
    for _ in range(10):
        app.update(1.0 / 60.0)
    app.draw(win)
    pygame.image.save(win, os.path.join(out, '08_pause.png'))
    print('shots written to', out)


def run_selftest(app, win):
    t_start = time.perf_counter()
    frame_times = []

    def frames(n, draw=True):
        for _ in range(n):
            app.update(1.0 / 60.0)
            if draw:
                t0 = time.perf_counter()
                app.draw(win)
                frame_times.append((time.perf_counter() - t0) * 1000)

    frames(30)
    assert app.scene_name == 'hangar'
    hang = app.scene
    st = app.state
    assert st['build']['body'] is None and st['build']['frame'] is None, \
        'fresh save must start on an empty airframe'
    assert 'frame_std' in st['owned'] and 'motor_std' in st['owned']
    assert not hang.stats['airworthy'], 'empty airframe must be grounded'
    assert hang.grounded_reason() == 'FIT A HULL FIRST'
    hang.try_fly()
    assert app.scene_name == 'hangar', 'empty airframe launched'

    # build order: hull, frame, rotors, then a motor per rotor
    fit(hang, 'frame', 'c', FRAMES[0])
    assert st['build']['frame'] is None, 'frame fitted without a hull'
    fit(hang, 'rotor', 'fl', ROTORS[0])
    assert st['build']['rotor']['fl'] is None, 'rotor fitted without a frame'

    fit(hang, 'body', 'c', BODIES[0])
    assert st['build']['body'] == 'body_scout'
    fit(hang, 'frame', 'c', FRAMES[0])
    assert st['build']['frame'] == 'frame_std'
    for k in ('fl', 'fr', 'rl'):
        fit(hang, 'rotor', k, ROTORS[0])
    assert hang.stats['rotors'] == 3 and hang.stats['powered'] == 0
    assert not hang.stats['airworthy'], 'unpowered rotors must stay grounded'
    assert hang.grounded_reason() == 'FIT A DRIVE MOTOR TO EACH ROTOR'
    fit(hang, 'motor', 'rr', MOTORS[0])
    assert st['build']['motor']['rr'] is None, 'motor fitted without a rotor'
    fit(hang, 'rotor', 'rr', ROTORS[0])
    for k, _ in SOCKETS['motor']:
        fit(hang, 'motor', k, MOTORS[0])
    assert hang.stats['airworthy'], 'standard quad should be airworthy'
    assert hang.stats['balance'] >= 99.0, 'symmetric build should trim at 100'
    frames(3)

    # paint recolors every mesh without touching the stats
    mass_before = hang.stats['mass']
    hang.apply_paint(PAINTS[2])
    assert st['paint'] == 'crimson', 'paint not stored'
    assert hang.parts, 'painted airframe lost its parts'
    assert hang.stats['mass'] == mass_before, 'paint changed the stats'

    # a mismatched rotor costs trim
    swift = ROTORS[2]
    fit(hang, 'rotor', 'fl', swift)
    assert swift['id'] in st['owned'], 'buy failed'
    assert st['build']['rotor']['fl'] == 'rotor_swift', 'swift not bolted'
    assert st['credits'] == START_CREDITS - swift['price']
    assert hang.stats['balance'] < 100.0, 'mismatched rotor should cost trim'
    frames(4)

    # removing a rotor must pull its drive motor too
    hang.slot, hang.socket = 'rotor', ('rotor', 'fl')
    hang.remove_socket_part()
    assert st['build']['rotor']['fl'] is None
    assert st['build']['motor']['fl'] is None, 'orphan motor left on the frame'
    fit(hang, 'rotor', 'fl', ROTORS[0])
    assert hang.stats['airworthy'], 'restored build should fly'

    # the frame cannot be pulled while rotors hang off it
    hang.slot, hang.socket = 'frame', ('frame', 'c')
    hang.remove_socket_part()
    assert st['build']['frame'] == 'frame_std', 'loaded frame was removed'

    app.set_scene('editor')
    ed = app.scene
    ed.sliders[0].value = 0.40
    ed.sliders[2].value = 10
    ed.params['material'] = 'composite'
    ed.rebuild()
    frames(5)
    before = st['credits']
    ed.publish()
    assert len(st['custom']) == 1, 'custom rotor not stored'
    assert st['credits'] == before - (250 + 120), 'craft cost wrong'
    assert app.scene_name == 'hangar'
    frames(5)

    app.set_scene('flight')
    fl = app.scene
    for _ in range(int(45 * 60)):
        app.update(1.0 / 60.0)
        if app.scene is not fl:
            break
    assert fl.mode == 'result', 'run did not finish: ' + fl.mode
    assert fl.hits >= 1, 'autopilot collected no cores'
    assert fl.reward > 0, 'no reward'
    frames(10)

    app.set_scene('flight')
    fl2 = app.scene
    for _ in range(int(2.0 * 60)):
        app.update(1.0 / 60.0)
    assert fl2.mode == 'run', 'autopilot should be running'
    fl2.crash('GROUND IMPACT')
    assert fl2.mode == 'crash', 'crash did not start'
    for _ in range(int(3.0 * 60)):
        app.update(1.0 / 60.0)
    assert fl2.mode == 'result' and fl2.grade == 'F', 'crash did not resolve'
    frames(6)

    assert '0' in st['cleared'], 'sector 1 not cleared'
    assert fl.unlocked_now == 1, 'sector 2 not offered after clear'
    assert 1 not in st['unlocked'], 'sector 2 unlocked without purchase'

    st['credits'] = 5000
    app.set_scene('hangar')
    hang2 = app.scene
    hang2.pick_sector(2)
    assert 2 not in st['unlocked'], 'sector 3 bought before sector 2 clear'
    assert st['sector'] == 0
    frames(3)
    hang2.pick_sector(1)
    assert 1 in st['unlocked'] and st['sector'] == 1, \
        'sector 2 not purchasable after clear'

    app.set_scene('flight')
    paused = app.scene
    for _ in range(100):
        app.update(1.0 / 60.0)
    assert paused.mode == 'run'
    paused.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert paused.paused, 'escape did not pause'
    t_before = paused.time
    for _ in range(10):
        app.update(1.0 / 60.0)
    assert paused.time == t_before, 'simulation advanced while paused'
    paused.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert not paused.paused, 'escape did not resume'
    frames(3)

    # flight is autopilot only: movement keys must not steer the craft
    app.set_scene('flight')
    manual = app.scene
    manual.mode = 'run'
    manual.intro_t = 1.5
    manual.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d))
    x_start = manual.x
    for _ in range(40):
        app.update(1.0 / 60.0)
    assert manual.held == set(), 'steering keys should be ignored'
    manual.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert manual.paused, 'pause did not work'
    manual.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    app.set_scene('hangar')
    hang3 = app.scene
    cid = st['custom'][0]['id']
    st['build']['rotor']['rr'] = cid
    st['selected']['rotor'] = cid
    hang3.rebuild()
    hang3.remove_custom(cid)
    assert cid not in [e['id'] for e in st['custom']], 'rotor not scrapped'
    assert st['selected']['rotor'] == 'rotor_std', 'scrap did not fall back'
    assert st['build']['rotor']['rr'] is None, \
        'scrapped rotor left a hole in the build'

    st['credits'] = 5000
    for si in (1, 2):
        st['sector'] = si
        if si not in st['unlocked']:
            st['unlocked'].append(si)
        app.set_scene('flight')
        f = app.scene
        f.hits = f.total_cores()
        f.score = 1800 + si * 200
        f.finish()
        assert f.mode == 'result' and f.cleared_now, 'sector did not clear'
    assert st['finished'], 'campaign not completed'
    assert st['sector'] == 2
    frames(6)

    # old v3 saves keep progress but rebuild from an empty airframe
    import json
    tmp = os.path.join(SAVE_DIR, 'migrate_test.json')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'version': 3, 'credits': 777, 'paint': 'royal',
                   'build': {'body': 'body_scout',
                             'rotor': {'fl': 'rotor_std'}}}, f)
    old = load_state(tmp)
    os.remove(tmp)
    assert old['version'] == 4 and old['credits'] == 777
    assert old['build']['body'] is None and old['build']['frame'] is None, \
        'v3 build was not reset'
    assert old['paint'] == 'royal', 'paint lost in migration'
    assert 'frame_std' in old['owned'] and 'motor_std' in old['owned']

    if frame_times:
        avg = sum(frame_times) / len(frame_times)
        print('frames drawn: {}  avg {:.1f} ms  ({:.0f} fps)'.format(
            len(frame_times), avg, 1000.0 / max(0.1, avg)))
    print('selftest OK in {:.1f}s  credits={}  custom={}  score={}  reward={}'.format(
        time.perf_counter() - t_start, st['credits'],
        len(st['custom']), fl.score, fl.reward))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--shots', action='store_true', help='write preview PNGs')
    ap.add_argument('--selftest', action='store_true', help='headless logic test')
    ap.add_argument('--smoke', type=int, default=0,
                    help='run the real window for N frames then quit')
    args = ap.parse_args(argv)

    headless = args.shots or args.selftest
    if headless:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'

    pygame.init()
    try:
        if headless:
            win = pygame.display.set_mode((W, H))
        else:
            win = pygame.display.set_mode((W, H), pygame.SCALED | pygame.DOUBLEBUF)
    except pygame.error:
        win = pygame.display.set_mode((W, H))
    pygame.display.set_caption('BLUEPRINT — Airframe Lab')
    audio.init()
    app = App(test=headless)
    clock = pygame.time.Clock()

    if args.shots:
        run_shots(app, win)
        return 0
    if args.selftest:
        return run_selftest(app, win)

    audio.ambient(True, 0.14)
    running = True
    frames = 0
    while running:
        dt = clock.tick(FPS) / 1000.0
        dt = min(dt, 0.05)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            else:
                app.scene.handle(e)
        app.update(dt)
        app.draw(win)
        pygame.display.flip()
        frames += 1
        if args.smoke and frames >= args.smoke:
            running = False
    audio.ambient(False)
    pygame.quit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
