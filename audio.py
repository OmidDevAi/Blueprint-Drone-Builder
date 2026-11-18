import numpy as np
import pygame

SR = 44100
enabled = False
muted = False
_sounds = {}
_amb_ch = None
_hum_ch = None


def _to_sound(x, vol=1.0):
    peak = float(np.max(np.abs(x))) or 1.0
    x = np.clip(x / peak * vol, -1.0, 1.0)
    data = (x * 32767).astype(np.int16)
    stereo = np.ascontiguousarray(np.stack([data, data], axis=-1))
    return pygame.sndarray.make_sound(stereo)


def _env(n, attack=0.006, decay=8.0):
    t = np.arange(n) / SR
    rise = np.clip(t / max(1e-4, attack), 0.0, 1.0)
    return rise * np.exp(-decay * t)


def _echo(x, delay=0.11, mix=0.22, feedback=0.18):
    d = int(SR * delay)
    out = x.copy()
    for i in range(1, 4):
        out[i * d:] += x[:-i * d] * (mix * feedback ** (i - 1))
    return out


def _soft_noise(n, passes=4, seed=11):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 0.5, n)
    for _ in range(passes):
        x = np.convolve(x, [0.2, 0.6, 0.2], mode='same')
    return x


def _pluck(freq, dur, vol=0.3, decay=14.0, attack=0.004, bright=0.22):
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR
    ph = 2 * np.pi * freq * t
    x = np.sin(ph) + bright * np.sin(2 * ph) + 0.07 * np.sin(3 * ph)
    x *= _env(n, attack, decay)
    x += np.random.default_rng(3).normal(0, 0.015, n) * _env(n, 0.001, 90.0)
    return _to_sound(x, vol)


def _bell(freq, dur, vol=0.3, decay=6.0, attack=0.004, fm=1.2, mix=0.18):
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR
    ph = 2 * np.pi * freq * t
    x = np.sin(ph + fm * np.sin(2 * np.pi * freq * 3.01 * t) *
               np.exp(-4.0 * t))
    x += np.sin(2.002 * ph) * 0.24 + np.sin(3.99 * ph) * 0.08
    x *= _env(n, attack, decay)
    return _to_sound(_echo(x, 0.09, mix, 0.22), vol)


def _arp(freqs, step=0.07, tail=0.6, vol=0.3, decay=4.5, shimmer=0.16,
         detune=0.004):
    n = int(SR * (step * (len(freqs) - 1) + tail))
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        s = int(SR * step * i)
        m = n - s
        t = np.arange(m) / SR
        ph = 2 * np.pi * f * t
        voice = (np.sin(ph) * 0.70 +
                 np.sin(ph * (1 + detune)) * 0.24 +
                 np.sin(2 * ph) * 0.16 +
                 np.sin(3 * ph) * 0.05)
        voice *= _env(m, 0.008, decay)
        if shimmer:
            voice += (np.sin(2 * np.pi * f * 3.02 * t) * shimmer *
                      _env(m, 0.002, 26.0))
        out[s:] += voice
    return _to_sound(_echo(out, 0.10, 0.20, 0.24), vol)


def _pickup(freq, vol=0.3):
    n = int(SR * 0.55)
    out = np.zeros(n)
    for f, off, amp, dec in ((freq, 0.0, 1.0, 5.5),
                             (freq * 1.5, 0.035, 0.72, 7.0),
                             (freq * 2.0, 0.07, 0.46, 8.5)):
        s = int(SR * off)
        m = n - s
        t = np.arange(m) / SR
        ph = 2 * np.pi * f * t
        v = np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)
        out[s:] += v * _env(m, 0.003, dec) * amp
    rng = np.random.default_rng(13)
    for _ in range(4):
        f = rng.uniform(2600, 4600)
        s = int(SR * rng.uniform(0.0, 0.12))
        m = n - s
        t = np.arange(m) / SR
        out[s:] += np.sin(2 * np.pi * f * t) * np.exp(-30 * t) * 0.12
    return _to_sound(_echo(out, 0.085, 0.20, 0.22), vol)


def _sweep(f0, f1, dur, vol=0.28, decay=3.0, attack=0.02, bright=0.12):
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR
    f = np.linspace(f0, f1, n)
    ph = np.cumsum(2 * np.pi * f / SR)
    x = (np.sin(ph) * 0.85 + np.sin(2 * ph) * bright +
         np.sin(3 * ph) * bright * 0.25)
    return _to_sound(x * _env(n, attack, decay), vol)


def _whoosh(f0, f1, dur, vol=0.3, rise=0.03, decay=3.0, seed=9):
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR
    noise = _soft_noise(n, 3, seed)
    f = np.linspace(f0, f1, n)
    ph = np.cumsum(2 * np.pi * f / SR)
    body = np.sin(ph) * 0.42 + np.sin(2 * ph) * 0.14
    x = noise * 0.80 + body
    x *= _env(n, rise, decay)
    x += np.sin(2 * np.pi * f0 * 0.45 * t) * 0.18 * _env(n, rise, decay * 0.7)
    return _to_sound(x, vol)


def _clank(vol=0.22, dur=0.45):
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f, a, d in ((523.25, 0.50, 18.0), (1274.0, 0.26, 26.0),
                    (1890.0, 0.12, 33.0), (392.0, 0.22, 12.0)):
        x += np.sin(2 * np.pi * f * t) * a * np.exp(-d * t)
    x += _soft_noise(n, 1, 17) * np.exp(-60 * t) * 0.9
    x *= np.clip(t / 0.002, 0.0, 1.0)
    return _to_sound(x, vol)


def _impact(vol=0.5):
    n = int(SR * 1.1)
    t = np.arange(n) / SR
    f = np.linspace(110, 32, n)
    ph = np.cumsum(2 * np.pi * f / SR)
    x = np.sin(ph) * np.exp(-3.4 * t)
    x += _soft_noise(n, 2, 23) * np.exp(-5.5 * t) * 0.9
    x += np.sin(2 * np.pi * 78 * t) * np.exp(-10.0 * t) * 0.40
    rng = np.random.default_rng(31)
    for _ in range(5):
        s = int(SR * rng.uniform(0.05, 0.5))
        m = n - s
        tt = np.arange(m) / SR
        x[s:] += (np.sin(2 * np.pi * rng.uniform(700, 2400) * tt) *
                  np.exp(-18 * tt) * 0.16)
    return _to_sound(x, vol)


def _fanfare(vol=0.34):
    n = int(SR * 1.6)
    out = np.zeros(n)
    freqs = [523.25, 659.25, 783.99, 1046.5]
    for i, f in enumerate(freqs):
        s = int(SR * 0.075 * i)
        m = n - s
        t = np.arange(m) / SR
        v = (np.sin(2 * np.pi * f * t) +
             0.30 * np.sin(4 * np.pi * f * t) +
             0.08 * np.sin(6 * np.pi * f * t))
        out[s:] += v * _env(m, 0.008, 3.0) * 0.45
    s = int(SR * 0.34)
    m = n - s
    t = np.arange(m) / SR
    chord = np.zeros(m)
    for f in (523.25, 659.25, 783.99, 1046.5, 1318.5):
        chord += np.sin(2 * np.pi * f * 1.001 * t)
        chord += np.sin(2 * np.pi * f * 0.999 * t)
    chord *= _env(m, 0.05, 1.9) * 0.14
    out[s:] += chord
    rng = np.random.default_rng(41)
    for _ in range(6):
        f = rng.uniform(2300, 4700)
        s = int(SR * rng.uniform(0.30, 0.65))
        m = n - s
        tt = np.arange(m) / SR
        out[s:] += np.sin(2 * np.pi * f * tt) * np.exp(-16 * tt) * 0.07
    kb = int(SR * 0.12)
    kt = np.arange(kb) / SR
    kick = np.sin(2 * np.pi * np.linspace(120, 45, kb) * kt) * np.exp(-22 * kt)
    out[:kb] += kick * 0.35
    return _to_sound(_echo(out, 0.13, 0.16, 0.28), vol)


def _pad():
    n = SR * 8
    t = np.arange(n) / SR
    lfo = 0.65 + 0.35 * np.sin(2 * np.pi * 0.125 * t)
    x = (np.sin(2 * np.pi * 110 * t) * 0.36 +
         np.sin(2 * np.pi * 165 * t) * 0.24 +
         np.sin(2 * np.pi * 220 * t) * 0.20 +
         np.sin(2 * np.pi * 275 * t) * 0.07 +
         np.sin(2 * np.pi * 330 * t) * 0.10 +
         np.sin(2 * np.pi * 440 * t) * 0.04)
    x *= 0.7 + 0.3 * np.sin(2 * np.pi * 0.25 * t)
    x = np.tanh(x * 0.55) * lfo
    return _to_sound(x, 0.5)


def _motor():
    n = SR * 4
    t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * 80 * t) * 0.55 +
         np.sin(2 * np.pi * 160 * t) * 0.16 +
         np.sin(2 * np.pi * 240 * t) * 0.06 +
         np.sin(2 * np.pi * 320 * t) * 0.025)
    x *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.5 * t)
    return _to_sound(x, 0.5)


def init():
    global enabled, _amb_ch, _hum_ch
    try:
        pygame.mixer.quit()
        pygame.mixer.init(frequency=SR, size=-16, channels=2, buffer=512)
        pygame.mixer.set_num_channels(16)
        _amb_ch = pygame.mixer.Channel(0)
        _hum_ch = pygame.mixer.Channel(1)
        _sounds['click'] = _pluck(660, 0.05, 0.055, 52.0, bright=0.30)
        _sounds['select'] = _arp([880.0, 1318.5], 0.045, 0.26, 0.17, 8.0,
                                 0.10)
        _sounds['coin'] = _arp([1046.5, 1318.5], 0.055, 0.34, 0.24, 7.0)
        _sounds['buy'] = _arp([523.25, 659.25, 783.99, 1046.5, 1318.5],
                              0.065, 0.85, 0.30, 3.6, 0.16)
        _sounds['error'] = _sweep(330, 220, 0.32, 0.20, 6.0, 0.015, 0.06)
        _sounds['core'] = _pickup(1174.7, 0.28)
        _sounds['core_hi'] = _pickup(1568.0, 0.28)
        _sounds['near'] = _whoosh(2100, 700, 0.30, 0.18, 0.01, 5.0, 19)
        _sounds['weld'] = _clank(0.15)
        _sounds['miss'] = _sweep(392, 262, 0.30, 0.18, 5.5, 0.02, 0.08)
        _sounds['boost'] = _whoosh(220, 760, 0.55, 0.30, 0.03, 3.0, 9)
        _sounds['hammer'] = _clank(0.20, 0.5)
        _sounds['complete'] = _fanfare(0.34)
        _sounds['crash'] = _impact(0.5)
        _sounds['ambient'] = _pad()
        _sounds['hum'] = _motor()
        enabled = True
    except Exception:
        enabled = False


def set_mute(value):
    global muted
    muted = bool(value)
    if muted:
        for ch in (_amb_ch, _hum_ch):
            if ch is not None and ch.get_busy():
                ch.stop()


def play(name, vol=1.0):
    if not enabled or muted:
        return
    s = _sounds.get(name)
    if s is not None:
        s.set_volume(vol)
        s.play()


def ambient(on=True, vol=0.10):
    if not enabled or muted or _amb_ch is None:
        return
    if on:
        if not _amb_ch.get_busy():
            _amb_ch.play(_sounds['ambient'], loops=-1)
        _amb_ch.set_volume(vol)
    else:
        _amb_ch.stop()


def hum(level):
    if not enabled or muted or _hum_ch is None:
        return
    if level <= 0.01:
        if _hum_ch.get_busy():
            _hum_ch.stop()
        return
    if not _hum_ch.get_busy():
        _hum_ch.play(_sounds['hum'], loops=-1)
    _hum_ch.set_volume(min(1.0, level) * 0.42)
