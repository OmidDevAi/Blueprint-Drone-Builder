import math

from config import (GOLD, GOLD_D, TEAL, GLASS, HULL, HULL_L, HULL_D, DARKM,
                    MATERIALS, PAINTS)
from render3d import (circ, extrude, make_part, rrect, shift, clamp, mix)

PAINT_BY_ID = {p['id']: p for p in PAINTS}


def paint_scheme(state):
    pid = state.get('paint') if isinstance(state, dict) else None
    return PAINT_BY_ID.get(pid, PAINTS[0])



# ---------------- airframe geometry ----------------
def _quad(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def _hull_poly(w, l, nose=0.26, tail=0.20):
    hw, hl = w / 2, l / 2
    n = hw * nose
    t = hw * tail
    return [(-hw + t, -hl), (hw - t, -hl), (hw, -hl + n * 0.55),
            (hw, hl - n), (hw - n * 1.35, hl), (-hw + n * 1.35, hl),
            (-hw, hl - n), (-hw, -hl + n * 0.55)]


def _hull_manta(w, l):
    hw, hl = w / 2, l / 2
    return [(0.0, hl), (hw * 0.44, hl * 0.62), (hw * 0.80, hl * 0.20),
            (hw, -hl * 0.10), (hw * 0.82, -hl * 0.52), (hw * 0.40, -hl * 0.90),
            (0.0, -hl), (-hw * 0.40, -hl * 0.90), (-hw * 0.82, -hl * 0.52),
            (-hw, -hl * 0.10), (-hw * 0.80, hl * 0.20), (-hw * 0.44, hl * 0.62)]


def _hull_shape(style, w, l):
    hw, hl = w / 2, l / 2
    if style == 'atlas':
        return [(-hw * 0.88, -hl), (hw * 0.88, -hl), (hw, -hl * 0.66),
                (hw, hl * 0.60), (hw * 0.78, hl), (-hw * 0.78, hl),
                (-hw, hl * 0.60), (-hw, -hl * 0.66)]
    if style == 'velocity':
        return [(-hw * 0.34, -hl), (hw * 0.34, -hl), (hw * 0.90, -hl * 0.16),
                (hw * 0.30, hl * 0.54), (0.0, hl), (-hw * 0.30, hl * 0.54),
                (-hw * 0.90, -hl * 0.16)]
    if style == 'hornet':
        return [(-hw * 0.62, -hl), (hw * 0.62, -hl), (hw, -hl * 0.14),
                (hw * 0.40, hl), (0.0, hl * 1.06), (-hw * 0.40, hl),
                (-hw, -hl * 0.14)]
    if style == 'mule':
        return [(-hw * 0.92, -hl), (hw * 0.92, -hl), (hw, hl * 0.62),
                (hw * 0.74, hl * 1.02), (-hw * 0.74, hl * 1.02),
                (-hw, hl * 0.62)]
    if style == 'manta':
        return _hull_manta(w, l)
    return _hull_poly(w, l)


def _canopy_shape(style, cw, cl):
    if style == 'atlas':
        return [(-cw * 0.60, cl * 0.42), (cw * 0.60, cl * 0.42),
                (cw * 0.74, cl * 0.06), (cw * 0.54, -cl * 0.40),
                (-cw * 0.54, -cl * 0.40), (-cw * 0.74, cl * 0.06)]
    if style == 'velocity':
        return [(-cw * 0.26, cl * 0.88), (cw * 0.26, cl * 0.88),
                (cw * 0.54, cl * 0.22), (cw * 0.40, -cl * 0.58),
                (0.0, -cl * 0.84), (-cw * 0.40, -cl * 0.58),
                (-cw * 0.54, cl * 0.22)]
    if style == 'hornet':
        return [(-cw * 0.34, cl * 0.52), (cw * 0.34, cl * 0.52),
                (cw * 0.50, cl * 0.02), (cw * 0.26, -cl * 0.48),
                (0.0, -cl * 0.60), (-cw * 0.26, -cl * 0.48),
                (-cw * 0.50, cl * 0.02)]
    if style == 'mule':
        return [(-cw * 0.52, cl * 0.48), (cw * 0.52, cl * 0.48),
                (cw * 0.64, cl * 0.10), (cw * 0.48, -cl * 0.34),
                (-cw * 0.48, -cl * 0.34), (-cw * 0.64, cl * 0.10)]
    if style == 'manta':
        return [(-cw * 0.46, cl * 0.56), (cw * 0.46, cl * 0.56),
                (cw * 0.62, cl * 0.16), (cw * 0.36, -cl * 0.44),
                (0.0, -cl * 0.56), (-cw * 0.36, -cl * 0.44),
                (-cw * 0.62, cl * 0.16)]
    return [(-cw * 0.32, cl * 0.62), (cw * 0.32, cl * 0.62),
            (cw * 0.52, cl * 0.08), (cw * 0.40, -cl * 0.56),
            (0.0, -cl * 0.74), (-cw * 0.40, -cl * 0.56),
            (-cw * 0.52, cl * 0.08)]


def body_mesh(w, l, hull, deck, canopy_w=0.52, canopy_l=0.30, stripe=GOLD,
              style='scout'):
    ps = []
    ps.append(make_part('body', extrude(_hull_shape(style, w, l), 'y',
                                        -0.10, 0.10), hull))
    ps.append(make_part('body', extrude(_hull_shape(style, w * 0.86, l * 0.82),
                                        'y', 0.10, 0.126), deck))
    cw = w * canopy_w
    cl = l * canopy_l
    canopy = _canopy_shape(style, cw, cl)
    cz = {'atlas': 0.13, 'mule': 0.16, 'velocity': 0.16,
          'hornet': 0.20}.get(style, 0.18)
    glass = (30, 78, 108) if style == 'manta' else (40, 116, 148)
    ps.append(make_part('body', extrude(shift(canopy, 0, l * cz), 'y',
                                        0.122, 0.200),
                        glass, accent=GLASS, em=0.06, no_edge=True))
    rim = [(u * 1.14, v * 1.16) for u, v in canopy]
    ps.append(make_part('body', extrude(shift(rim, 0, l * cz), 'y',
                                        0.118, 0.126),
                        (58, 92, 128), no_edge=True))
    ps.append(make_part(
        'body',
        extrude(shift(_quad(w * 0.55, 0.20), 0, -l * 0.37), 'y', 0.10, 0.132),
        stripe, no_edge=True))
    ps.append(make_part(
        'body',
        extrude(shift(_quad(w * 0.22, 0.16), 0, l * 0.42), 'y', 0.10, 0.128),
        stripe, no_edge=True))
    nose_z = {'atlas': 0.36, 'velocity': 0.46, 'hornet': 0.46, 'mule': 0.44,
              'manta': 0.43}.get(style, 0.31)
    ps.append(make_part('body', extrude(circ(w * 0.075, 0, l * nose_z, 8), 'y',
                                        0.126, 0.150),
                        (18, 28, 44), accent=TEAL, em=0.85, no_edge=True))

    if style in ('scout', 'atlas', 'manta'):
        for s in (1, -1):
            vent = shift(_quad(w * 0.075, l * 0.26), s * w * 0.34, -l * 0.02)
            ps.append(make_part('body', extrude(vent, 'y', 0.126, 0.140),
                                (26, 38, 60), no_edge=True))
            ps.append(make_part('body', extrude(
                shift(_quad(w * 0.022, l * 0.19), s * w * 0.34, -l * 0.02),
                'y', 0.141, 0.144), TEAL, accent=TEAL, em=0.65, no_edge=True))

    if style == 'atlas':
        for s in (1, -1):
            pod = shift(_quad(w * 0.14, l * 0.44), s * w * 0.42, -l * 0.04)
            ps.append(make_part('body', extrude(pod, 'y', -0.02, 0.11), hull,
                                no_edge=True))
            rib = shift(_quad(w * 0.15, 0.045), s * w * 0.42, l * 0.08)
            ps.append(make_part('body', extrude(rib, 'y', 0.108, 0.134), stripe,
                                no_edge=True))
        for z in (-l * 0.24, -l * 0.02, l * 0.20):
            ps.append(make_part('body', extrude(
                shift(_quad(w * 0.46, 0.035), 0, z), 'y', 0.126, 0.146),
                (44, 66, 98), no_edge=True))
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.30, 0.05), 0, -l * 0.45), 'y', 0.02, 0.11),
            (24, 36, 54), no_edge=True))
    elif style == 'velocity':
        for s in (1, -1):
            canard = [(s * w * 0.10, l * 0.34), (s * w * 0.34, l * 0.23),
                      (s * w * 0.34, l * 0.15), (s * w * 0.10, l * 0.20)]
            ps.append(make_part('body', extrude(canard, 'y', 0.10, 0.132),
                                stripe, no_edge=True))
        fin = [(0.0, 0.03, -l * 0.30), (0.0, 0.03, -l * 0.49),
               (0.0, 0.15, -l * 0.49), (0.0, 0.10, -l * 0.34)]
        ps.append(make_part('body', [fin], stripe, closed=False))
    elif style == 'hornet':
        for s in (1, -1):
            intake = [(s * w * 0.18, l * 0.16), (s * w * 0.44, l * 0.05),
                      (s * w * 0.44, -l * 0.12), (s * w * 0.18, -l * 0.03)]
            ps.append(make_part('body', extrude(intake, 'y', 0.10, 0.152),
                                (30, 46, 70), no_edge=True))
            fin = [(s * w * 0.28, 0.0, -l * 0.35),
                   (s * w * 0.28, 0.0, -l * 0.53),
                   (s * w * 0.30, 0.15, -l * 0.53),
                   (s * w * 0.29, 0.09, -l * 0.38)]
            ps.append(make_part('body', [fin], stripe, closed=False))
    elif style == 'mule':
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.60, l * 0.38), 0, -l * 0.14), 'y', 0.126, 0.30),
            (54, 78, 116)))
        for z in (-l * 0.28, -l * 0.14, 0.0):
            ps.append(make_part('body', extrude(
                shift(_quad(w * 0.62, 0.035), 0, z), 'y', 0.296, 0.316),
                stripe, no_edge=True))
        for s in (1, -1):
            tank = shift(_quad(w * 0.11, l * 0.32), s * w * 0.46, l * 0.04)
            ps.append(make_part('body', extrude(tank, 'y', -0.01, 0.062),
                                (44, 68, 102), no_edge=True))
    elif style == 'manta':
        fin = [(0.0, 0.04, l * 0.16), (0.0, 0.04, -l * 0.30),
               (0.0, 0.17, -l * 0.38), (0.0, 0.20, -l * 0.12)]
        ps.append(make_part('body', [fin], stripe, closed=False))
        for s in (1, -1):
            strake = [(s * w * 0.16, l * 0.30), (s * w * 0.30, -l * 0.44),
                      (s * w * 0.25, -l * 0.44), (s * w * 0.13, l * 0.28)]
            ps.append(make_part('body', extrude(strake, 'y', 0.126, 0.140),
                                (20, 30, 48), no_edge=True))
    else:
        ps.append(make_part('body', extrude(
            shift(_quad(0.014, 0.014), 0, -l * 0.42), 'y', 0.126, 0.36),
            (116, 146, 186), no_edge=True))
        ps.append(make_part('body', extrude(
            shift(_quad(0.026, 0.026), 0, -l * 0.42), 'y', 0.355, 0.372),
            stripe, no_edge=True))
    return ps


def chassis_mesh(w=0.54, l=1.12, accent=GOLD, reach=1.0, col=(36, 54, 82),
                 style='spar'):
    """Exposed frame with one arm per rotor socket. Everything the player
    bolts on sits on this skeleton, so the drone reads as a real build."""
    fw = w / 0.54
    fl = l / 1.12
    ps = []
    ps.append(make_part('body', extrude(_quad(w * 0.16, l * 0.92), 'y', -0.16, -0.10),
                        (16, 25, 42)))
    frame_faces = []
    stripe_faces = []
    tips = []
    tip_pts = []
    cycle = ((-1, 1), (1, 1), (1, -1), (-1, -1))
    for sx, sz in cycle:
        cx, cz = sx * 0.72 * fw * reach, sz * 0.60 * fl * reach
        tip_pts.append((cx, cz))
        ln = math.hypot(cx, cz) or 1.0
        ux, uz = cx / ln, cz / ln
        px, pz = -uz, ux
        arm = [(ux * 0.10 + px * 0.085, uz * 0.10 + pz * 0.085),
               (cx + px * 0.042, cz + pz * 0.042),
               (cx - px * 0.042, cz - pz * 0.042),
               (ux * 0.10 - px * 0.085, uz * 0.10 - pz * 0.085)]
        frame_faces.extend(extrude(arm, 'y', -0.150, -0.062))
        stripe_faces.append([(ux * 0.14 + px * 0.022, -0.059, uz * 0.14 + pz * 0.022),
                             (cx + px * 0.020, -0.059, cz + pz * 0.020),
                             (cx - px * 0.020, -0.059, cz - pz * 0.020),
                             (ux * 0.14 - px * 0.022, -0.059, uz * 0.14 - pz * 0.022)])
        r = 0.055 if style != 'h' else 0.072
        tips.append([(cx + gx * r, -0.148, cz + gz * r)
                     for gx, gz in ((1, 1), (-1, 1), (-1, -1), (1, -1))])

    if style == 'h':
        for s in (-1, 1):
            zz = s * 0.33 * fl * reach
            bar = [(-0.47 * fw * reach, zz - 0.024),
                   (0.47 * fw * reach, zz - 0.024),
                   (0.47 * fw * reach, zz + 0.024),
                   (-0.47 * fw * reach, zz + 0.024)]
            frame_faces.extend(extrude(bar, 'y', -0.146, -0.078))
            ps.append(make_part('body', extrude(
                [(u * 0.98, v) for u, v in bar], 'y', -0.077, -0.070),
                accent, accent=accent, em=0.18, no_edge=True))
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.10, l * 0.30), 0, -0.04 * fl), 'y', -0.10, -0.02),
            col, no_edge=True))
    elif style == 'ring':
        for i in range(4):
            x0, z0 = tip_pts[i]
            x1, z1 = tip_pts[(i + 1) % 4]
            dx, dz = x1 - x0, z1 - z0
            ln = math.hypot(dx, dz) or 1.0
            nx, nz = -dz / ln, dx / ln
            bw = 0.030
            band = [(x0 + nx * bw, z0 + nz * bw), (x1 + nx * bw, z1 + nz * bw),
                    (x1 - nx * bw, z1 - nz * bw), (x0 - nx * bw, z0 - nz * bw)]
            frame_faces.extend(extrude(band, 'y', -0.144, -0.080))
            ps.append(make_part('body', extrude(
                [(u * 1.0, v) for u, v in band], 'y', -0.079, -0.071),
                accent, accent=accent, em=0.14, no_edge=True))

    for s in (1, -1):
        skid = [(s * 0.30 * fw, 0.30 * fl), (s * 0.36 * fw, 0.24 * fl),
                (s * 0.36 * fw, -0.42 * fl), (s * 0.30 * fw, -0.48 * fl)]
        frame_faces.extend(extrude(skid, 'y', -0.215, -0.185))
    ps.append(make_part('body', frame_faces, col, no_edge=False))
    ps.append(make_part('body', stripe_faces, accent, accent=accent, em=0.10,
                        no_edge=True, closed=False))
    ps.append(make_part('body', tips, accent, accent=accent, no_edge=True,
                        em=0.18, closed=False))
    mast_h = 0.34 if style == 'h' else 0.34
    ps.append(make_part('body', extrude(shift(_quad(0.022, 0.022), 0, -0.42 * fl),
                                        'y', 0.10, mast_h),
                        (28, 42, 66), no_edge=True))
    ps.append(make_part('body', extrude(shift(_quad(0.05, 0.05), 0, -0.42 * fl),
                                        'y', mast_h - 0.005, mast_h + 0.015),
                        accent, accent=accent, em=0.7, no_edge=True))
    return ps


def _annulus_faces(cu, cv, r_in, r_out, y0, y1, n=12):
    faces = []
    for i in range(n):
        a0 = 2 * math.pi * i / n
        a1 = 2 * math.pi * (i + 1) / n
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        i0 = (cu + r_in * c0, y1, cv + r_in * s0)
        o0 = (cu + r_out * c0, y1, cv + r_out * s0)
        o1 = (cu + r_out * c1, y1, cv + r_out * s1)
        i1 = (cu + r_in * c1, y1, cv + r_in * s1)
        faces.append([i0, o0, o1, i1])
        faces.append([(cu + r_out * c0, y0, cv + r_out * s0),
                      (cu + r_out * c1, y0, cv + r_out * s1), o1, o0])
    return faces


def rotor_pod_mesh(params, pos, motor=None, paint=GOLD):
    """One lifting rotor at a single socket. Blade count, sweep and span all
    come from the installed part, so every socket can hold a different rotor.
    A fitted drive motor lights the hub; a bare pod stays dark."""
    span = params['span'] * 0.82
    chord = params['chord']
    blades = max(1, int(round(params['blades'])))
    sweep = params.get('sweep', 0.0)
    hub = params.get('hub', 0.076)
    guard_mode = params.get('guard', 'ring')
    rc = pos
    ps = []
    slice_a = 2 * math.pi / blades
    wid = min(slice_a * 0.60, chord / max(0.06, span * 0.5))
    r0 = hub * 0.92
    r1 = hub + span
    guard = r1 + 0.026
    blade_b = mix(paint, (255, 255, 255), 0.86)
    drive = motor.get('accent', GOLD) if motor else (64, 78, 104)

    skirt = [[(rc[0] + hub * 0.78 * math.cos(2 * math.pi * i / 10), 0.118,
               rc[1] + hub * 0.78 * math.sin(2 * math.pi * i / 10))
              for i in range(10)]]
    ps.append(make_part('rotor', skirt, (20, 31, 50), accent=paint, em=0.0,
                        no_edge=True, closed=False))
    hub_faces = [[(rc[0] + hub * 0.58 * math.cos(2 * math.pi * i / 8), 0.158,
                   rc[1] + hub * 0.58 * math.sin(2 * math.pi * i / 8))
                  for i in range(8)]]
    ps.append(make_part('rotor', hub_faces, DARKM, accent=drive, em=0.0,
                        no_edge=True, closed=False))
    ring = [[(rc[0] + hub * math.cos(2 * math.pi * i / 10), 0.168,
              rc[1] + hub * math.sin(2 * math.pi * i / 10)) for i in range(10)]]
    ps.append(make_part('rotor', ring, drive if motor else (46, 58, 82),
                        no_edge=True, closed=False))
    if motor:
        mstyle = motor.get('geo', {}).get('style', 'can')
        if mstyle == 'dome':
            for k, (f, yy) in enumerate(((0.68, 0.160), (0.54, 0.176),
                                          (0.36, 0.190))):
                shell = [[(rc[0] + hub * f * math.cos(2 * math.pi * i / 10), yy,
                           rc[1] + hub * f * math.sin(2 * math.pi * i / 10))
                          for i in range(10)]]
                ps.append(make_part('rotor', shell, drive, accent=drive,
                                    em=0.35 + 0.18 * k, no_edge=True,
                                    closed=False))
            cap = [[(rc[0] + hub * 0.20 * math.cos(2 * math.pi * i / 8), 0.198,
                     rc[1] + hub * 0.20 * math.sin(2 * math.pi * i / 8))
                    for i in range(8)]]
            ps.append(make_part('rotor', cap, mix(drive, (255, 255, 255), 0.55),
                                accent=drive, em=0.85, no_edge=True,
                                closed=False))
        elif mstyle == 'finned':
            can = extrude(circ(hub * 0.64, rc[0], rc[1], 8), 'y', 0.096, 0.166)
            ps.append(make_part('rotor', can, drive, accent=drive, em=0.24,
                                no_edge=True, closed=False))
            fins = []
            for i in range(4):
                a = math.pi * i / 2 + math.pi / 4
                ca, sa = math.cos(a), math.sin(a)
                r0f, r1f = hub * 0.58, hub * 0.92
                fins.append([(rc[0] + r0f * ca, 0.104, rc[1] + r0f * sa),
                             (rc[0] + r1f * ca, 0.104, rc[1] + r1f * sa),
                             (rc[0] + r1f * ca, 0.160, rc[1] + r1f * sa),
                             (rc[0] + r0f * ca, 0.160, rc[1] + r0f * sa)])
            ps.append(make_part('rotor', fins, (34, 44, 66), no_edge=True,
                                closed=False))
            for yy in (0.118, 0.152):
                band = [[(rc[0] + hub * 0.67 * math.cos(2 * math.pi * i / 10), yy,
                          rc[1] + hub * 0.67 * math.sin(2 * math.pi * i / 10))
                         for i in range(10)]]
                ps.append(make_part('rotor', band, mix(drive, (255, 255, 255),
                                                       0.25), accent=drive,
                                    em=0.6, no_edge=True, closed=False))
        elif mstyle == 'tall':
            can = extrude(circ(hub * 0.44, rc[0], rc[1], 8), 'y', 0.096, 0.190)
            ps.append(make_part('rotor', can, drive, accent=drive, em=0.26,
                                no_edge=True, closed=False))
            band = [[(rc[0] + hub * 0.50 * math.cos(2 * math.pi * i / 10), 0.164,
                      rc[1] + hub * 0.50 * math.sin(2 * math.pi * i / 10))
                     for i in range(10)]]
            ps.append(make_part('rotor', band, drive, accent=drive, em=0.7,
                                no_edge=True, closed=False))
        else:
            can = extrude(circ(hub * 0.54, rc[0], rc[1], 8), 'y', 0.096, 0.158)
            ps.append(make_part('rotor', can, drive, accent=drive, em=0.28,
                                no_edge=True, closed=False))
            led = [[(rc[0] + 0.020 * math.cos(2 * math.pi * i / 6), 0.176,
                     rc[1] + 0.020 * math.sin(2 * math.pi * i / 6))
                    for i in range(6)]]
            ps.append(make_part('rotor', led, drive, accent=drive, em=0.75,
                                no_edge=True, closed=False))

    # guard ring: narrow annulus band around the blade tips
    if guard_mode != 'open':
        bw = {'double': 0.024, 'shield': 0.034}.get(guard_mode, 0.018)
        top, bot = ((0.186, 0.128) if guard_mode == 'shield'
                    else (0.178, 0.136))
        faces = _annulus_faces(rc[0], rc[1], guard - bw, guard, bot, top, 12)
        ps.append(make_part('rotor', faces, (36, 54, 86), accent=paint,
                            em=0.0, no_edge=True, closed=False))
        if guard_mode == 'double':
            inner = guard - 0.042
            faces2 = _annulus_faces(rc[0], rc[1], inner - 0.013, inner,
                                    0.132, 0.170, 12)
            ps.append(make_part('rotor', faces2, (48, 66, 98), accent=paint,
                                no_edge=True, closed=False))
        elif guard_mode == 'cage':
            cap = _annulus_faces(rc[0], rc[1], guard - 0.016, guard,
                                 0.196, 0.204, 12)
            ps.append(make_part('rotor', cap, (30, 46, 74), accent=paint,
                                no_edge=True, closed=False))
            bars = []
            for i in range(6):
                a = 2 * math.pi * i / 6
                ca, sa = math.cos(a), math.sin(a)
                rr, bw2 = guard - 0.008, 0.010
                bars.append([
                    (rc[0] + rr * ca - sa * bw2, 0.178,
                     rc[1] + rr * sa + ca * bw2),
                    (rc[0] + rr * ca + sa * bw2, 0.178,
                     rc[1] + rr * sa - ca * bw2),
                    (rc[0] + rr * ca + sa * bw2, 0.200,
                     rc[1] + rr * sa - ca * bw2),
                    (rc[0] + rr * ca - sa * bw2, 0.200,
                     rc[1] + rr * sa + ca * bw2)])
            ps.append(make_part('rotor', bars, (44, 62, 96), no_edge=True,
                                closed=False))

    struts = []
    outer = guard if guard_mode != 'open' else r1
    for i in range(4):
        a = math.pi * i / 4 + math.pi / 4
        ca, sa = math.cos(a), math.sin(a)
        hw = 0.012
        struts.append([(rc[0] + hub * 0.5 * ca - sa * hw, 0.158,
                        rc[1] + hub * 0.5 * sa + ca * hw),
                       (rc[0] + outer * ca - sa * hw, 0.158,
                        rc[1] + outer * sa + ca * hw),
                       (rc[0] + outer * ca + sa * hw, 0.158,
                        rc[1] + outer * sa - ca * hw),
                       (rc[0] + hub * 0.5 * ca + sa * hw, 0.158,
                        rc[1] + hub * 0.5 * sa - ca * hw)])
    ps.append(make_part('rotor', struts, (52, 74, 112), no_edge=True,
                        closed=False))

    faces, cols = [], []
    for i in range(blades):
        a0 = 2 * math.pi * i / blades
        a1 = a0 + wid
        a0s = a0 + sweep
        a1s = a1 + sweep
        faces.append([
            (rc[0] + r0 * math.cos(a0), 0.152, rc[1] + r0 * math.sin(a0)),
            (rc[0] + r1 * math.cos(a0s), 0.152, rc[1] + r1 * math.sin(a0s)),
            (rc[0] + r1 * math.cos(a1s), 0.152, rc[1] + r1 * math.sin(a1s)),
            (rc[0] + r0 * math.cos(a1), 0.152, rc[1] + r0 * math.sin(a1)),
        ])
        cols.append(paint if i % 2 == 0 else blade_b)
    ps.append(make_part('rotor', faces, paint, accent=paint, em=0.14,
                        spin=True, face_colors=cols,
                        ctr=(rc[0], 0.152, rc[1]), no_edge=True, closed=False))
    return ps


def wing_half_mesh(geo, side, y0=0.055, color=None, trim=None):
    """One half of a wing pair as a dihedral panel. The panels rise through the
    gap between the front and rear rotors, so they stay visible from every
    camera angle instead of hiding under the discs."""
    s = 1 if side > 0 else -1
    c = geo.get('chord', 1.0)
    span_s = geo.get('span_s', 1.0)
    sweep = geo.get('sweep', 0.0)
    color = color or geo.get('color', HULL)
    trim = trim or geo.get('trim', GOLD)
    x0 = 0.24
    x1 = 0.84 * span_s
    y1 = y0 + 0.20 * span_s
    t = 0.034
    p1 = (s * x0, y0, 0.13 * c)
    p2 = (s * x1, y1, -0.10 * c + sweep)
    p3 = (s * (x1 + 0.05 * span_s), y1, -0.24 * c + sweep)
    p4 = (s * x0, y0, -0.11 * c)
    ps = [make_part('wing', [[p1, p2, p3, p4],
                             [(v[0], v[1] - t, v[2]) for v in (p4, p3, p2, p1)]],
                    color)]
    # leading-edge trim, slightly proud of the panel
    tf = (p1[0], p1[1] + 0.004, p1[2] + 0.050)
    tr = (p2[0], p2[1] + 0.004, p2[2] + 0.050)
    trim_face = [p1, p2, tr, tf]
    if s < 0:
        trim_face.reverse()
    ps.append(make_part('wing', [trim_face], trim, no_edge=True,
                        closed=False))
    # luminous control strip
    a = (s * 0.28, y0 + 0.031, 0.055)
    b = (s * 0.66 * span_s, y0 + 0.031 + 0.20 * span_s * 0.72, -0.015)
    strip = [a, b, (b[0], b[1], b[2] - 0.045), (a[0], a[1], a[2] - 0.045)]
    if s < 0:
        strip.reverse()
    ps.append(make_part('wing', [strip], trim, accent=trim, em=0.5,
                        no_edge=True, closed=False))
    fin = [(s * 0.30, -0.34), (s * 0.30, -0.50),
           (s * 0.33, -0.53), (s * 0.33, -0.34)]
    ps.append(make_part('wing', extrude(fin, 'y', y0 + 0.010, y0 + 0.210),
                        color))
    # winglet at the tip
    fin2 = [(s * x1, -0.05 * c + sweep), (s * (x1 + 0.03), -0.16 * c + sweep),
            (s * (x1 + 0.055), -0.16 * c + sweep),
            (s * (x1 + 0.025), -0.05 * c + sweep)]
    ps.append(make_part('wing', extrude(fin2, 'y', y1, y1 + 0.15), color))
    ps.append(make_part('wing', extrude(shift(fin2, 0, 0.0), 'y',
                                        y1 + 0.15, y1 + 0.165), trim,
                        no_edge=True))

    style = geo.get('style', 'panel')
    if style == 'twin':
        fin_b = [(s * 0.54, -0.29), (s * 0.54, -0.46),
                 (s * 0.57, -0.49), (s * 0.57, -0.29)]
        ps.append(make_part('wing', extrude(fin_b, 'y', y0 + 0.010,
                                            y0 + 0.165), color))
    elif style == 'glide':
        strake = [(s * x1 * 0.72, -0.05 * c + sweep),
                  (s * (x1 * 0.72 + 0.03), -0.16 * c + sweep),
                  (s * (x1 * 0.72 + 0.055), -0.16 * c + sweep),
                  (s * (x1 * 0.72 + 0.02), -0.05 * c + sweep)]
        ps.append(make_part('wing', extrude(strake, 'y', y1 - 0.012,
                                            y1 + 0.008), trim, no_edge=True))
    elif style == 'delta':
        tri = [(s * 0.28, -0.10 * c), (s * (x1 + 0.035), -0.25 * c + sweep),
               (s * (x1 + 0.035), -0.07 * c + sweep)]
        ps.append(make_part('wing', extrude(tri, 'y', y0 - 0.004,
                                            y0 + 0.024), color, no_edge=True))
    elif style == 'manta':
        fin_b = [(s * x1, -0.06 * c + sweep),
                 (s * (x1 + 0.05), -0.22 * c + sweep),
                 (s * (x1 + 0.085), -0.22 * c + sweep),
                 (s * (x1 + 0.032), -0.05 * c + sweep)]
        ps.append(make_part('wing', extrude(fin_b, 'y', y1 - 0.02,
                                            y1 + 0.185), color))
        ps.append(make_part('wing', extrude(fin_b, 'y', y1 + 0.185,
                                            y1 + 0.200), trim, no_edge=True))
    elif style == 'canard':
        can = [(s * 0.22, 0.30 * c), (s * 0.50, 0.24 * c),
               (s * 0.50, 0.17 * c), (s * 0.22, 0.22 * c)]
        ps.append(make_part('wing', extrude(can, 'y', y0 - 0.050,
                                            y0 - 0.028), color))
        trim_c = [(s * 0.22, 0.30 * c), (s * 0.50, 0.24 * c),
                  (s * 0.50, 0.225 * c), (s * 0.22, 0.285 * c)]
        ps.append(make_part('wing', extrude(trim_c, 'y', y0 - 0.027,
                                            y0 - 0.020), trim, no_edge=True))
    return ps


def _cone_z(cx, cy, r0, r1, z0, z1, n=10):
    faces = []
    for i in range(n):
        a0 = 2 * math.pi * i / n
        a1 = 2 * math.pi * (i + 1) / n
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        faces.append([(cx + r0 * c0, cy + r0 * s0, z0),
                      (cx + r0 * c1, cy + r0 * s1, z0),
                      (cx + r1 * c1, cy + r1 * s1, z1),
                      (cx + r1 * c0, cy + r1 * s0, z1)])
    faces.append([(cx + r0 * math.cos(2 * math.pi * i / n),
                   cy + r0 * math.sin(2 * math.pi * i / n), z0)
                  for i in range(n)])
    faces.append([(cx + r1 * math.cos(2 * math.pi * i / n),
                   cy + r1 * math.sin(2 * math.pi * i / n), z1)
                  for i in range(n)])
    return faces


def booster_unit_mesh(geo, side, z0=-0.24, accent=None, col=None):
    """A single thruster mounted on one rear socket."""
    x = (1 if side > 0 else -1) * 0.36
    rad = geo.get('rad', 0.088)
    length = geo.get('length', 0.42)
    accent = accent or geo.get('accent', TEAL)
    col = col or geo.get('col', HULL_D)
    style = geo.get('style', 'basic')
    z1 = z0 - length
    ps = []

    def nozzle(rr, z):
        nf = extrude(circ(rr * 0.84, x, -0.075, 8), 'z', z, z - 0.025)
        return make_part('booster', nf, DARKM, accent=accent, em=0.85,
                         no_edge=True)

    if style == 'twin':
        for dx in (-0.048, 0.048):
            xx = x + dx * (1 if side > 0 else -1)
            rr = rad * 0.60
            ps.append(make_part('booster', extrude(
                circ(rr, xx, -0.075, 8), 'z', z0, z1), col))
            ps.append(make_part('booster', extrude(
                circ(rr * 0.80, xx, -0.075, 8), 'z', z1, z1 - 0.022),
                DARKM, accent=accent, em=0.85, no_edge=True))
    elif style == 'bell':
        ps.append(make_part('booster', _cone_z(
            x, -0.075, rad * 0.68, rad * 1.18, z0, z1, 10), col))
        ps.append(make_part('booster', extrude(
            circ(rad * 1.02, x, -0.075, 8), 'z', z1, z1 - 0.020),
            DARKM, accent=accent, em=0.9, no_edge=True))
        ps.append(make_part('booster', extrude(
            circ(rad * 0.74, x, -0.075, 10), 'z',
            z0 - length * 0.42, z0 - length * 0.42 - 0.020),
            accent, accent=accent, em=0.55, no_edge=True))
    elif style == 'ram':
        ps.append(make_part('booster', extrude(
            circ(rad, x, -0.075, 10), 'z', z0, z1), col))
        ps.append(make_part('booster', extrude(
            circ(rad * 1.12, x, -0.075, 10), 'z', z0 - 0.008, z0 - 0.034),
            mix(col, (255, 255, 255), 0.12), no_edge=True))
        ps.append(make_part('booster', _cone_z(
            x, -0.075, rad * 0.24, 0.0015, z0 - 0.034, z0 - 0.15, 6),
            accent, accent=accent, em=0.35, no_edge=True))
        ps.append(nozzle(rad, z1))
    elif style == 'long':
        ps.append(make_part('booster', extrude(
            circ(rad, x, -0.075, 10), 'z', z0, z1), col))
        ps.append(make_part('booster', extrude(
            circ(rad * 1.08, x, -0.075, 10), 'z',
            z0 - length * 0.52, z0 - length * 0.52 - 0.018),
            accent, accent=accent, em=0.6, no_edge=True))
        ps.append(nozzle(rad, z1))
    elif style == 'fin':
        ps.append(make_part('booster', extrude(
            circ(rad, x, -0.075, 10), 'z', z0, z1), col))
        fins = []
        for i in range(4):
            a = math.pi * i / 2 + math.pi / 4
            ca, sa = math.cos(a), math.sin(a)
            r1f = rad * 1.55
            fins.append([(x + rad * 0.92 * ca, -0.075 + rad * 0.92 * sa,
                          z1 + 0.10),
                         (x + r1f * ca, -0.075 + r1f * sa, z1 + 0.10),
                         (x + r1f * ca, -0.075 + r1f * sa, z1 + 0.020),
                         (x + rad * 0.92 * ca, -0.075 + rad * 0.92 * sa,
                          z1 + 0.020)])
        ps.append(make_part('booster', fins, accent, no_edge=True,
                            closed=False))
        ps.append(nozzle(rad, z1))
    else:
        ps.append(make_part('booster', extrude(
            circ(rad, x, -0.075, 10), 'z', z0, z1), col))
        ps.append(nozzle(rad, z1))
    return ps


def wing_mesh(span_s=1.0, sweep=0.0, chord=1.0, color=HULL, trim=GOLD, fin=True):
    ps = []
    c = chord
    for s in (1, -1):
        pts = [(s * 0.20, 0.14 * c), (s * 0.78 * span_s, -0.16 * c + sweep),
               (s * 0.84 * span_s, -0.02 * c + sweep), (s * 0.20, 0.26 * c)]
        ps.append(make_part('wing', extrude(pts, 'y', -0.010, 0.030), color))
        trim_pts = [(s * 0.20, 0.14 * c), (s * 0.78 * span_s, -0.16 * c + sweep),
                    (s * 0.84 * span_s, -0.02 * c + sweep),
                    (s * 0.80 * span_s, -0.055 * c + sweep), (s * 0.20, 0.175 * c)]
        ps.append(make_part('wing', extrude(trim_pts, 'y', 0.030, 0.042), trim, no_edge=True))
        if fin:
            fin_pts = [(s * 0.26, -0.34), (s * 0.26, -0.50),
                       (s * 0.29, -0.53), (s * 0.29, -0.34)]
            ps.append(make_part('wing', extrude(fin_pts, 'y', 0.0, 0.20), color))
    return ps


def booster_mesh(rad=0.088, length=0.42, accent=TEAL, col=HULL_D):
    ps = []
    for s in (1, -1):
        faces = extrude(circ(rad, s * 0.32, -0.03, 10), 'z', -0.24, -0.24 - length)
        ps.append(make_part('booster', faces, col))
        nf = extrude(circ(rad * 0.84, s * 0.32, -0.03, 8), 'z',
                     -0.24 - length, -0.24 - length - 0.025)
        ps.append(make_part('booster', nf, DARKM, accent=accent, em=0.85, no_edge=True))
    return ps


def rotor_mesh(span=0.32, chord=0.085, blades=12, sweep=0.0, hub=0.085,
               blade_col=GOLD, arm_col=HULL_D):
    """Four lifting rotors. Blades are flat wedges: cheap to draw and they read
    as a spinning turbine from the hangar camera."""
    ps = []
    slice_a = 2 * math.pi / max(1, blades)
    wid = min(slice_a * 1.02, chord / max(0.06, span * 0.5))
    r0 = hub * 0.52
    r1 = hub + span

    for sx, sz in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        arc_x, arc_z = sx / math.sqrt(2), sz / math.sqrt(2)
        pvx, pvz = -arc_z, arc_x
        arm = [(sx * 0.14 + pvx * 0.09, sz * 0.14 + pvz * 0.09),
               (sx * 0.82 + pvx * 0.055, sz * 0.82 + pvz * 0.055),
               (sx * 0.82 - pvx * 0.055, sz * 0.82 - pvz * 0.055),
               (sx * 0.14 - pvx * 0.09, sz * 0.14 - pvz * 0.09)]
        faces = [[(x, 0.028, z) for x, z in arm]]
        ps.append(make_part('rotor', faces, arm_col, no_edge=True, closed=False))

        rc = (0.86 * sx, 0.86 * sz)
        hub_faces = [[(rc[0] + hub * 0.55 * math.cos(2 * math.pi * i / 8), 0.150,
                       rc[1] + hub * 0.55 * math.sin(2 * math.pi * i / 8))
                      for i in range(8)]]
        ps.append(make_part('rotor', hub_faces, DARKM, accent=GOLD, em=0.22,
                            no_edge=True, closed=False))
        ring = [[(rc[0] + hub * math.cos(2 * math.pi * i / 8), 0.148,
                  rc[1] + hub * math.sin(2 * math.pi * i / 8)) for i in range(8)]]
        ps.append(make_part('rotor', ring, GOLD_D, no_edge=True, closed=False))

        faces, cols = [], []
        for i in range(blades):
            a0 = 2 * math.pi * i / blades
            a1 = a0 + wid
            a0s = a0 + sweep
            a1s = a1 + sweep
            faces.append([
                (rc[0] + r0 * math.cos(a0), 0.162, rc[1] + r0 * math.sin(a0)),
                (rc[0] + r1 * math.cos(a0s), 0.162, rc[1] + r1 * math.sin(a0s)),
                (rc[0] + r1 * math.cos(a1s), 0.162, rc[1] + r1 * math.sin(a1s)),
                (rc[0] + r0 * math.cos(a1), 0.162, rc[1] + r0 * math.sin(a1)),
            ])
            cols.append(GOLD if i % 2 == 0 else (246, 188, 84))
        ps.append(make_part('rotor', faces, GOLD, accent=GOLD, em=0.30,
                            spin=True, face_colors=cols,
                            ctr=(rc[0], 0.162, rc[1]), no_edge=True, closed=False))
    return ps


# ---------------- stat maths ----------------
def _mat(mid):
    for m in MATERIALS:
        if m['id'] == mid:
            return m
    return MATERIALS[0]


def rotor_stats(span=0.32, chord=0.085, blades=12, sweep=0.0, thickness=0.014,
                material='alloy', hub=0.076, guard=None):
    m = _mat(material)
    a_disc = span * chord * blades
    area = 4 * a_disc
    thrust = 130.0 * area * m['thrust'] * (1.0 + 0.10 * sweep)
    mass = 4.0 * (6.0 + 14.0 * a_disc) * m['mass']
    drag = 4.0 * (0.30 + 1.7 * span + 6.0 * thickness * (1.0 + 4.0 * span))
    agility = clamp(20.0 - 20.0 * a_disc, 4.0, 20.0)
    return {
        'mass': round(mass, 1),
        'thrust': round(thrust, 1),
        'drag': round(drag, 2),
        'lift': 0.0,
        'agility': round(agility, 1),
        'energy': 0.0,
    }


def craft_cost(material='alloy'):
    return 250 + _mat(material)['cost']


# ---------------- catalog ----------------
BODIES = (
    {'id': 'body_scout', 'slot': 'body', 'name': 'SCOUT', 'price': 0,
     'desc': 'LIGHT RECON HULL', 'accent': HULL_L,
     'stats': {'mass': 45, 'thrust': 0, 'drag': 1.05, 'lift': 0, 'agility': 6, 'energy': 0},
     'geo': {'w': 0.54, 'l': 1.12, 'hull': HULL, 'deck': HULL_L,
             'style': 'scout'}},
    {'id': 'body_atlas', 'slot': 'body', 'name': 'ATLAS', 'price': 420,
     'desc': 'HEAVY LIFT HULL', 'accent': (96, 148, 206),
     'stats': {'mass': 70, 'thrust': 0, 'drag': 1.55, 'lift': 0, 'agility': -6, 'energy': 0},
     'geo': {'w': 0.70, 'l': 1.34, 'hull': (60, 98, 154), 'deck': (96, 148, 206),
             'style': 'atlas'}},
    {'id': 'body_velocity', 'slot': 'body', 'name': 'VELOCITY', 'price': 680,
     'desc': 'AERO RACING HULL', 'accent': (132, 184, 240),
     'stats': {'mass': 38, 'thrust': 0, 'drag': 0.68, 'lift': 2, 'agility': 12, 'energy': 0},
     'geo': {'w': 0.46, 'l': 1.24, 'hull': (86, 140, 206), 'deck': (132, 184, 240),
             'canopy_w': 0.58, 'canopy_l': 0.34, 'style': 'velocity'}},
    {'id': 'body_hornet', 'slot': 'body', 'name': 'HORNET', 'price': 540,
     'desc': 'COMPACT SPRINT HULL', 'accent': (255, 178, 96),
     'stats': {'mass': 32, 'thrust': 0, 'drag': 0.62, 'lift': 1, 'agility': 14, 'energy': 0},
     'geo': {'w': 0.44, 'l': 1.18, 'hull': (92, 150, 210), 'deck': (150, 196, 244),
             'canopy_w': 0.62, 'canopy_l': 0.24, 'stripe': (255, 178, 96),
             'style': 'hornet'}},
    {'id': 'body_mule', 'slot': 'body', 'name': 'MULE', 'price': 500,
     'desc': 'WIDE CARGO HULL', 'accent': (110, 150, 200),
     'stats': {'mass': 88, 'thrust': 0, 'drag': 1.90, 'lift': 0, 'agility': -10, 'energy': 0},
     'geo': {'w': 0.78, 'l': 1.42, 'hull': (58, 86, 132), 'deck': (98, 132, 186),
             'canopy_w': 0.44, 'canopy_l': 0.26, 'style': 'mule'}},
    {'id': 'body_manta', 'slot': 'body', 'name': 'MANTA', 'price': 860,
     'desc': 'STEALTH LIFT HULL', 'accent': (84, 190, 214),
     'stats': {'mass': 52, 'thrust': 0, 'drag': 0.60, 'lift': 4, 'agility': 8, 'energy': 0},
     'geo': {'w': 0.62, 'l': 1.30, 'hull': (40, 60, 96), 'deck': (74, 108, 150),
             'canopy_w': 0.46, 'canopy_l': 0.26, 'stripe': (84, 190, 214),
             'style': 'manta'}},
)

FRAMES = (
    {'id': 'frame_std', 'slot': 'frame', 'name': 'STOCK SPAR', 'price': 0,
     'desc': 'BALANCED QUAD FRAME', 'accent': GOLD,
     'stats': {'mass': 14, 'thrust': 0, 'drag': 0.25, 'lift': 0, 'agility': 0,
               'energy': 0},
     'geo': {'reach': 1.0, 'col': (36, 54, 82), 'style': 'spar'}},
    {'id': 'frame_long', 'slot': 'frame', 'name': 'LONG ARMS', 'price': 380,
     'desc': 'WIDE STANCE · STABLE', 'accent': (255, 205, 108),
     'stats': {'mass': 20, 'thrust': 0, 'drag': 0.45, 'lift': 0, 'agility': -4,
               'energy': 0},
     'geo': {'reach': 1.16, 'col': (44, 64, 94), 'style': 'h'}},
    {'id': 'frame_compact', 'slot': 'frame', 'name': 'COMPACT SPAR', 'price': 300,
     'desc': 'SHORT ARMS · LIGHT', 'accent': TEAL,
     'stats': {'mass': 9, 'thrust': 0, 'drag': 0.18, 'lift': 0, 'agility': 6,
               'energy': 0},
     'geo': {'reach': 0.86, 'col': (30, 46, 72), 'style': 'ring'}},
)

ROTORS = (
    {'id': 'rotor_std', 'slot': 'rotor', 'name': 'STANDARD', 'price': 0,
     'desc': 'TWELVE-BLADE QUAD SET', 'accent': GOLD,
     'params': {'span': 0.32, 'chord': 0.085, 'blades': 12, 'sweep': 0.0,
                'thickness': 0.014, 'material': 'alloy', 'guard': 'ring'}},
    {'id': 'rotor_titan', 'slot': 'rotor', 'name': 'TITAN', 'price': 620,
     'desc': 'WIDE LIFT DISCS', 'accent': GOLD,
     'params': {'span': 0.40, 'chord': 0.105, 'blades': 12, 'sweep': -0.02,
                'thickness': 0.020, 'material': 'alloy', 'guard': 'double',
                'hub': 0.084}},
    {'id': 'rotor_swift', 'slot': 'rotor', 'name': 'SWIFT', 'price': 460,
     'desc': 'LIGHT AGILE SET', 'accent': GOLD,
     'params': {'span': 0.30, 'chord': 0.090, 'blades': 8, 'sweep': 0.16,
                'thickness': 0.010, 'material': 'alloy', 'guard': 'open'}},
    {'id': 'rotor_cyclone', 'slot': 'rotor', 'name': 'CYCLONE', 'price': 520,
     'desc': 'HIGH BLADE COUNT', 'accent': (132, 226, 210),
     'params': {'span': 0.34, 'chord': 0.072, 'blades': 16, 'sweep': 0.04,
                'thickness': 0.012, 'material': 'alloy', 'guard': 'cage',
                'hub': 0.072}},
    {'id': 'rotor_halo', 'slot': 'rotor', 'name': 'HALO', 'price': 760,
     'desc': 'WIDE SIX-BLADE DISC', 'accent': (110, 226, 196),
     'params': {'span': 0.44, 'chord': 0.110, 'blades': 6, 'sweep': -0.06,
                'thickness': 0.018, 'material': 'composite', 'guard': 'shield',
                'hub': 0.088}},
    {'id': 'rotor_razor', 'slot': 'rotor', 'name': 'RAZOR', 'price': 640,
     'desc': 'SWEPT CARBON SET', 'accent': (255, 212, 128),
     'params': {'span': 0.28, 'chord': 0.075, 'blades': 10, 'sweep': 0.24,
                'thickness': 0.009, 'material': 'carbon', 'guard': 'open',
                'hub': 0.068}},
)

for _r in ROTORS:
    _r['stats'] = rotor_stats(**_r['params'])

MOTORS = (
    {'id': 'motor_std', 'slot': 'motor', 'name': 'STANDARD DRIVE', 'price': 0,
     'desc': 'QUAD BRUSHLESS SET', 'accent': GOLD,
     'stats': {'mass': 36, 'thrust': 86, 'drag': 0.30, 'lift': 0, 'agility': 0,
               'energy': 18},
     'geo': {'style': 'can'}},
    {'id': 'motor_torque', 'slot': 'motor', 'name': 'TORQUE DRIVE', 'price': 420,
     'desc': 'HEAVY LIFT MOTORS', 'accent': (255, 150, 90),
     'stats': {'mass': 54, 'thrust': 150, 'drag': 0.55, 'lift': 0, 'agility': -2,
               'energy': 8},
     'geo': {'style': 'finned'}},
    {'id': 'motor_servo', 'slot': 'motor', 'name': 'SERVO DRIVE', 'price': 360,
     'desc': 'FAST RESPONSE SET', 'accent': TEAL,
     'stats': {'mass': 28, 'thrust': 104, 'drag': 0.22, 'lift': 0, 'agility': 5,
               'energy': 34},
     'geo': {'style': 'tall'}},
    {'id': 'motor_ion', 'slot': 'motor', 'name': 'ION DRIVE', 'price': 600,
     'desc': 'EFFICIENT ION SET', 'accent': GLASS,
     'stats': {'mass': 40, 'thrust': 126, 'drag': 0.18, 'lift': 0, 'agility': 0,
               'energy': 82},
     'geo': {'style': 'dome'}},
)

WINGS = (
    {'id': 'wing_std', 'slot': 'wing', 'name': 'STANDARD', 'price': 0,
     'desc': 'BALANCED CONTROL SURFACE', 'accent': HULL_L,
     'stats': {'mass': 16, 'thrust': 0, 'drag': 1.4, 'lift': 18, 'agility': 5, 'energy': 0},
     'geo': {'span_s': 1.0, 'sweep': 0.0, 'chord': 1.0, 'style': 'panel'}},
    {'id': 'wing_glide', 'slot': 'wing', 'name': 'GLIDE', 'price': 380,
     'desc': 'LONG LIFT WINGS', 'accent': (84, 190, 170),
     'stats': {'mass': 22, 'thrust': 0, 'drag': 1.1, 'lift': 30, 'agility': 2, 'energy': 0},
     'geo': {'span_s': 1.14, 'sweep': -0.04, 'chord': 1.12,
             'trim': (110, 226, 196), 'style': 'glide'}},
    {'id': 'wing_edge', 'slot': 'wing', 'name': 'EDGE', 'price': 620,
     'desc': 'SHORT RESPONSE WINGS', 'accent': GOLD,
     'stats': {'mass': 12, 'thrust': 0, 'drag': 1.9, 'lift': 14, 'agility': 18, 'energy': 0},
     'geo': {'span_s': 0.86, 'sweep': 0.10, 'chord': 0.88, 'trim': GOLD,
             'style': 'canard'}},
    {'id': 'wing_delta', 'slot': 'wing', 'name': 'DELTA', 'price': 700,
     'desc': 'KNIFE-EDGE DELTA', 'accent': (255, 178, 96),
     'stats': {'mass': 10, 'thrust': 0, 'drag': 1.5, 'lift': 10, 'agility': 22, 'energy': 0},
     'geo': {'span_s': 0.94, 'sweep': 0.16, 'chord': 0.92, 'color': (72, 112, 168),
             'trim': (255, 178, 96), 'style': 'delta'}},
    {'id': 'wing_twin', 'slot': 'wing', 'name': 'TWIN', 'price': 520,
     'desc': 'TWIN-FIN LIFT SET', 'accent': (110, 226, 196),
     'stats': {'mass': 18, 'thrust': 0, 'drag': 1.25, 'lift': 24, 'agility': 10, 'energy': 0},
     'geo': {'span_s': 1.06, 'sweep': 0.04, 'chord': 1.04,
             'trim': (110, 226, 196), 'style': 'twin'}},
    {'id': 'wing_manta', 'slot': 'wing', 'name': 'MANTA', 'price': 820,
     'desc': 'WIDE GLIDE SURFACE', 'accent': (86, 190, 214),
     'stats': {'mass': 26, 'thrust': 0, 'drag': 0.95, 'lift': 38, 'agility': 4, 'energy': 0},
     'geo': {'span_s': 1.24, 'sweep': -0.10, 'chord': 1.20, 'color': (40, 60, 96),
             'trim': (86, 190, 214), 'style': 'manta'}},
)

BOOSTERS = (
    {'id': 'boost_std', 'slot': 'booster', 'name': 'STANDARD', 'price': 0,
     'desc': 'TWIN CHEM THRUSTERS', 'accent': TEAL,
     'stats': {'mass': 22, 'thrust': 70, 'drag': 0.9, 'lift': 0, 'agility': 0, 'energy': 60},
     'geo': {'rad': 0.088, 'length': 0.42, 'style': 'basic'}},
    {'id': 'boost_pulse', 'slot': 'booster', 'name': 'PULSE', 'price': 300,
     'desc': 'HIGH OUTPUT BURN', 'accent': (255, 148, 84),
     'stats': {'mass': 30, 'thrust': 105, 'drag': 1.3, 'lift': 0, 'agility': 0, 'energy': 75},
     'geo': {'rad': 0.100, 'length': 0.46, 'accent': (255, 148, 84),
             'col': (86, 66, 52), 'style': 'fin'}},
    {'id': 'boost_ion', 'slot': 'booster', 'name': 'ION', 'price': 700,
     'desc': 'LONG BURN ION DRIVE', 'accent': GLASS,
     'stats': {'mass': 18, 'thrust': 88, 'drag': 0.7, 'lift': 0, 'agility': 0, 'energy': 100},
     'geo': {'rad': 0.080, 'length': 0.52, 'accent': GLASS, 'col': (44, 70, 106),
             'style': 'long'}},
    {'id': 'boost_twin', 'slot': 'booster', 'name': 'TWINJET', 'price': 450,
     'desc': 'PAIRED LIGHT THRUSTERS', 'accent': TEAL,
     'stats': {'mass': 16, 'thrust': 92, 'drag': 0.8, 'lift': 0, 'agility': 0, 'energy': 70},
     'geo': {'rad': 0.070, 'length': 0.34, 'accent': TEAL, 'col': (40, 64, 100),
             'style': 'twin'}},
    {'id': 'boost_plasma', 'slot': 'booster', 'name': 'PLASMA', 'price': 780,
     'desc': 'VIOLET PLASMA BURN', 'accent': (178, 132, 255),
     'stats': {'mass': 34, 'thrust': 118, 'drag': 1.3, 'lift': 0, 'agility': 0, 'energy': 85},
     'geo': {'rad': 0.110, 'length': 0.44, 'accent': (178, 132, 255),
             'col': (52, 44, 86), 'style': 'bell'}},
    {'id': 'boost_scram', 'slot': 'booster', 'name': 'SCRAM', 'price': 900,
     'desc': 'LONG CANNON RAMJET', 'accent': GOLD,
     'stats': {'mass': 20, 'thrust': 100, 'drag': 0.75, 'lift': 0, 'agility': 0, 'energy': 120},
     'geo': {'rad': 0.075, 'length': 0.60, 'accent': GOLD, 'col': (56, 60, 96),
             'style': 'ram'}},
)

CATALOG = {'body': BODIES, 'frame': FRAMES, 'rotor': ROTORS, 'motor': MOTORS,
           'wing': WINGS, 'booster': BOOSTERS}
SLOT_ORDER = ('body', 'frame', 'rotor', 'motor', 'wing', 'booster')
SLOT_LABEL = {'body': 'HULL', 'frame': 'FRAME', 'rotor': 'ROTOR',
              'motor': 'MOTOR', 'wing': 'WING', 'booster': 'BOOST'}

# Every socket is a hardpoint on the chassis. Rotors need four points to be
# stable, wings and thrusters are mounted in mirrored pairs, and every rotor
# socket carries its own drive motor.
SOCKETS = {
    'body': (('c', 'HULL CORE'),),
    'frame': (('c', 'FRAME CORE'),),
    'rotor': (('fl', 'FRONT LEFT'), ('fr', 'FRONT RIGHT'),
              ('rl', 'REAR LEFT'), ('rr', 'REAR RIGHT')),
    'motor': (('fl', 'FRONT LEFT DRIVE'), ('fr', 'FRONT RIGHT DRIVE'),
              ('rl', 'REAR LEFT DRIVE'), ('rr', 'REAR RIGHT DRIVE')),
    'wing': (('l', 'LEFT WING'), ('r', 'RIGHT WING')),
    'booster': (('l', 'LEFT THRUSTER'), ('r', 'RIGHT THRUSTER')),
}
SOCKET_LABEL = {slot: dict(entries) for slot, entries in SOCKETS.items()}

# top-down offsets (x, z) from the chassis centre. Multiplied by the hull
# scale in ship.py so wide hulls get wider mounts. The frame reach scales the
# rotor and drive mounts only.
SOCKET_POS = {
    'body': {'c': (0.0, 0.0)},
    'frame': {'c': (0.0, 0.0)},
    'rotor': {'fl': (-0.72, 0.60), 'fr': (0.72, 0.60),
              'rl': (-0.72, -0.60), 'rr': (0.72, -0.60)},
    'motor': {'fl': (-0.72, 0.60), 'fr': (0.72, 0.60),
              'rl': (-0.72, -0.60), 'rr': (0.72, -0.60)},
    'wing': {'l': (-0.50, 0.05), 'r': (0.50, 0.05)},
    'booster': {'l': (-0.36, -0.70), 'r': (0.36, -0.70)},
}


def unit_stats(entry):
    """Stats of one installed module. Rotor, motor, wing and booster catalog
    numbers describe a full set, so they are split across their sockets."""
    s = entry_stats(entry)
    slot = entry['slot']
    if slot in ('body', 'frame'):
        f = 1.0
    elif slot in ('rotor', 'motor'):
        f = 4.0
    else:
        f = 2.0
    return {k: float(v) / f for k, v in s.items()}


def entry_mesh(entry):
    slot = entry['slot']
    if slot == 'body':
        g = entry['geo']
        return body_mesh(g['w'], g['l'], g['hull'], g['deck'],
                         g.get('canopy_w', 0.52), g.get('canopy_l', 0.30),
                         g.get('stripe', GOLD), g.get('style', 'scout'))
    if slot == 'frame':
        g = entry['geo']
        return chassis_mesh(0.54, 1.12, entry.get('accent', GOLD),
                            g.get('reach', 1.0), g.get('col', (36, 54, 82)),
                            g.get('style', 'spar'))
    if slot == 'motor':
        return []
    if slot == 'rotor':
        p = entry['params']
        return rotor_mesh(p['span'], p['chord'], int(round(p['blades'])), p['sweep'])
    if slot == 'wing':
        g = entry['geo']
        return wing_mesh(g['span_s'], g['sweep'], g['chord'],
                         color=g.get('color', HULL),
                         trim=g.get('trim', GOLD))
    g = entry['geo']
    return booster_mesh(g['rad'], g['length'], g.get('accent', TEAL),
                        g.get('col', HULL_D))


def entry_by_id(slot, eid, customs=()):
    for e in CATALOG[slot]:
        if e['id'] == eid:
            return e
    for e in customs:
        if e['id'] == eid:
            return e
    return CATALOG[slot][0]


def entry_stats(entry):
    return entry.get('stats') or rotor_stats(**entry['params'])
