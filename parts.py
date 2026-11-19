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


def _shrink(poly, k):
    n = len(poly)
    cu = sum(p[0] for p in poly) / n
    cv = sum(p[1] for p in poly) / n
    return [((u - cu) * (1.0 - k) + cu, (v - cv) * (1.0 - k) + cv)
            for u, v in poly]


def bevel_extrude(poly, y0, y1, k=0.05, band=0.016):
    """Extrusion with chamfered top and bottom rims: the small angled band
    catches the key light and keeps hard prisms from reading as flat boxes."""
    inner = _shrink(poly, k)
    lo = [(u, y0, v) for u, v in inner]
    w0 = [(u, y0 + band, v) for u, v in poly]
    w1 = [(u, y1 - band, v) for u, v in poly]
    hi = [(u, y1, v) for u, v in inner]
    faces = [lo]
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        faces.append([lo[i], lo[j], w0[j], w0[i]])
        faces.append([w0[i], w0[j], w1[j], w1[i]])
        faces.append([w1[i], w1[j], hi[j], hi[i]])
    faces.append(hi)
    return faces


def _loft_y(poly, y0, y1, k=0.15, dz=0.0):
    """Tapered extrusion: the upper outline is shrunk and offset, which rakes
    the side walls instead of leaving a straight prism."""
    top = _shrink(poly, k)
    if dz:
        top = [(u, v + dz) for u, v in top]
    faces = []
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        faces.append([(poly[i][0], y0, poly[i][1]),
                      (poly[j][0], y0, poly[j][1]),
                      (top[j][0], y1, top[j][1]),
                      (top[i][0], y1, top[i][1])])
    faces.append([(u, y1, v) for u, v in top])
    return faces


def _can_faces(cu, cv, r, y0, y1, n=12, cap0=True, cap1=True):
    faces = []
    for i in range(n):
        a0 = 2 * math.pi * i / n
        a1 = 2 * math.pi * (i + 1) / n
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        faces.append([(cu + r * c0, y0, cv + r * s0),
                      (cu + r * c1, y0, cv + r * s1),
                      (cu + r * c1, y1, cv + r * s1),
                      (cu + r * c0, y1, cv + r * s0)])
    if cap0:
        faces.append([(cu + r * math.cos(2 * math.pi * i / n), y0,
                       cv + r * math.sin(2 * math.pi * i / n)) for i in range(n)])
    if cap1:
        faces.append([(cu + r * math.cos(2 * math.pi * i / n), y1,
                       cv + r * math.sin(2 * math.pi * i / n)) for i in range(n)])
    return faces


def _spinner_faces(cu, cv, r, y0, y1, n=10):
    faces = []
    for i in range(n):
        a0 = 2 * math.pi * i / n
        a1 = 2 * math.pi * (i + 1) / n
        faces.append([(cu + r * math.cos(a0), y0, cv + r * math.sin(a0)),
                      (cu + r * math.cos(a1), y0, cv + r * math.sin(a1)),
                      (cu, y1, cv)])
    return faces


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
    if style == 'fold':
        return [(-hw * 0.46, -hl), (hw * 0.46, -hl), (hw * 0.80, -hl * 0.62),
                (hw * 0.96, -hl * 0.02), (hw * 0.68, hl * 0.66),
                (hw * 0.24, hl), (-hw * 0.24, hl), (-hw * 0.68, hl * 0.66),
                (-hw * 0.96, -hl * 0.02), (-hw * 0.80, -hl * 0.62)]
    if style == 'tf':
        return [(-hw * 0.30, -hl), (hw * 0.30, -hl), (hw * 0.66, -hl * 0.30),
                (hw * 0.46, hl * 0.54), (hw * 0.26, hl), (-hw * 0.26, hl),
                (-hw * 0.46, hl * 0.54), (-hw * 0.66, -hl * 0.30)]
    if style == 'racer':
        return [(-hw * 0.36, -hl), (hw * 0.36, -hl), (hw, -hl * 0.24),
                (hw * 0.84, hl * 0.46), (0.0, hl), (-hw * 0.84, hl * 0.46),
                (-hw, -hl * 0.24)]
    if style == 'mini':
        return [(-hw * 0.42, -hl), (hw * 0.42, -hl), (hw * 0.94, -hl * 0.10),
                (hw * 0.66, hl * 0.66), (hw * 0.24, hl), (-hw * 0.24, hl),
                (-hw * 0.66, hl * 0.66), (-hw * 0.94, -hl * 0.10)]
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
    if style == 'fold':
        return [(-cw * 0.42, cl * 0.52), (cw * 0.42, cl * 0.52),
                (cw * 0.56, cl * 0.10), (cw * 0.34, -cl * 0.30),
                (0.0, -cl * 0.42), (-cw * 0.34, -cl * 0.30),
                (-cw * 0.56, cl * 0.10)]
    if style == 'tf':
        return [(-cw * 0.20, cl * 0.90), (cw * 0.20, cl * 0.90),
                (cw * 0.34, cl * 0.10), (cw * 0.20, -cl * 0.62),
                (-cw * 0.20, -cl * 0.62), (-cw * 0.34, cl * 0.10)]
    if style == 'racer':
        return [(-cw * 0.34, cl * 0.60), (cw * 0.34, cl * 0.60),
                (cw * 0.46, cl * 0.06), (cw * 0.22, -cl * 0.52),
                (-cw * 0.22, -cl * 0.52), (-cw * 0.46, cl * 0.06)]
    if style == 'mini':
        return [(-cw * 0.50, cl * 0.44), (cw * 0.50, cl * 0.44),
                (cw * 0.62, cl * 0.02), (cw * 0.40, -cl * 0.42),
                (-cw * 0.40, -cl * 0.42), (-cw * 0.62, cl * 0.02)]
    return [(-cw * 0.32, cl * 0.62), (cw * 0.32, cl * 0.62),
            (cw * 0.52, cl * 0.08), (cw * 0.40, -cl * 0.56),
            (0.0, -cl * 0.74), (-cw * 0.40, -cl * 0.56),
            (-cw * 0.52, cl * 0.08)]


def body_mesh(w, l, hull, deck, canopy_w=0.52, canopy_l=0.30, stripe=GOLD,
              style='scout'):
    ps = []
    ps.append(make_part('body', bevel_extrude(_hull_shape(style, w, l),
                                              -0.10, 0.10, 0.035, 0.018), hull))
    ps.append(make_part('body', bevel_extrude(_hull_shape(style, w * 0.86, l * 0.82),
                                              0.10, 0.128, 0.03, 0.008), deck))
    cw = w * canopy_w
    cl = l * canopy_l
    canopy = _canopy_shape(style, cw, cl)
    cz = {'atlas': 0.13, 'mule': 0.16, 'velocity': 0.16,
          'hornet': 0.20, 'fold': 0.13, 'tf': 0.20, 'racer': 0.24,
          'mini': 0.15}.get(style, 0.18)
    glass = {'manta': (30, 78, 108), 'racer': (26, 70, 100),
             'mini': (34, 96, 128)}.get(style, (40, 116, 148))
    ps.append(make_part('body', _loft_y(shift(canopy, 0, l * cz),
                                        0.118, 0.198, 0.22, -l * 0.045),
                        glass, accent=GLASS, em=0.06, no_edge=True))
    rim = [(u * 1.14, v * 1.16) for u, v in canopy]
    ps.append(make_part('body', extrude(shift(rim, 0, l * cz), 'y',
                                        0.118, 0.126),
                        (58, 92, 128), no_edge=True))
    vmax = max(v for _, v in canopy)
    vmin = min(v for _, v in canopy)
    bv = vmax - (vmax - vmin) * 0.24
    bow = [(-cw * 0.40, bv), (cw * 0.40, bv),
           (cw * 0.36, bv + cl * 0.10), (-cw * 0.36, bv + cl * 0.10)]
    ps.append(make_part('body', extrude(shift(bow, 0, l * cz), 'y',
                                        0.201, 0.207),
                        (34, 44, 64), no_edge=True))
    for u in (-0.26, 0.04, 0.32):
        seam = shift(_quad(w * 0.60, 0.012), 0, u * l)
        ps.append(make_part('body', extrude(seam, 'y', 0.128, 0.131),
                            (22, 32, 50), no_edge=True))
    ps.append(make_part(
        'body',
        extrude(shift(_quad(w * 0.55, 0.20), 0, -l * 0.37), 'y', 0.10, 0.132),
        stripe, no_edge=True))
    ps.append(make_part(
        'body',
        extrude(shift(_quad(w * 0.22, 0.16), 0, l * 0.42), 'y', 0.10, 0.128),
        stripe, no_edge=True))
    nose_z = {'atlas': 0.36, 'velocity': 0.46, 'hornet': 0.46, 'mule': 0.44,
              'manta': 0.43, 'fold': 0.26, 'tf': 0.30, 'racer': 0.24,
              'mini': 0.30}.get(style, 0.31)
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
    elif style == 'fold':
        # Folding camera quad: hinge drums at all four corners, battery pack
        # on the spine and a gimbal ball slung under the nose.
        pods = []
        for s in (1, -1):
            for t in (1, -1):
                pods.extend(_can_faces(s * w * 0.34, t * l * 0.30, 0.036,
                                       0.126, 0.152, 8))
        ps.append(make_part('body', pods, (30, 40, 60), accent=stripe,
                            em=0.0, no_edge=True))
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.40, l * 0.24), 0, -l * 0.26), 'y', 0.128, 0.170),
            (46, 62, 92)))
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.30, 0.030), 0, -l * 0.26), 'y', 0.171, 0.178),
            stripe, no_edge=True))
        ps.append(make_part('body', _can_faces(0.0, l * 0.33, w * 0.095,
                                               -0.085, -0.018, 10),
                            (24, 32, 48), accent=TEAL, em=0.40, no_edge=True))
    elif style == 'tf':
        # Cinema T-frame: arm shoulders sweep off the deck corners and the
        # camera ball hangs under the nose.
        for s in (1, -1):
            root = [(s * w * 0.10, l * 0.06), (s * w * 0.48, -l * 0.24),
                    (s * w * 0.48, -l * 0.10), (s * w * 0.12, l * 0.16)]
            ps.append(make_part('body', extrude(root, 'y', 0.124, 0.152),
                                (34, 46, 68), no_edge=True))
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.34, l * 0.22), 0, -l * 0.14), 'y', 0.128, 0.200),
            (44, 60, 90)))
        ps.append(make_part('body', _can_faces(0.0, l * 0.35, w * 0.105,
                                               -0.092, -0.020, 10),
                            (22, 30, 46), accent=GLASS, em=0.35, no_edge=True))
    elif style == 'racer':
        # FPV race plate: exposed board stack, battery strap and a tilted
        # camera block on the nose.
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.44, l * 0.36), 0, l * 0.04), 'y', 0.126, 0.198),
            (30, 40, 58)))
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.46, 0.034), 0, l * 0.04), 'y', 0.199, 0.206),
            stripe, no_edge=True))
        tilt = [(-w * 0.17, 0.10, l * 0.34), (w * 0.17, 0.10, l * 0.34),
                (w * 0.17, 0.23, l * 0.24), (-w * 0.17, 0.23, l * 0.24)]
        ps.append(make_part('body', [tilt], (26, 34, 50), accent=stripe,
                            em=0.0, closed=False))
        ps.append(make_part('body', extrude(circ(w * 0.058, 0, l * 0.33, 8),
                                            'y', 0.150, 0.214),
                            (16, 24, 40), accent=TEAL, em=0.85, no_edge=True))
    elif style == 'mini':
        # Micro selfie quad: rounded shell with a battery hatch and two
        # forward sensor eyes.
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.54, l * 0.32), 0, -l * 0.08), 'y', 0.128, 0.188),
            (52, 68, 100)))
        for s in (1, -1):
            ps.append(make_part('body', extrude(
                circ(w * 0.046, s * w * 0.22, l * 0.24, 8), 'y', 0.128, 0.146),
                (20, 28, 44), accent=TEAL, em=0.9, no_edge=True))
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
    mount_faces = []
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
        frame_faces.extend(bevel_extrude(arm, -0.150, -0.062, 0.16, 0.010))
        mount_faces.extend(_can_faces(cx, cz, 0.052, -0.070, -0.046, 10))
        mount_faces.extend(_can_faces(cx, cz, 0.038, -0.046, -0.026, 10))
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
    elif style == 'tf':
        # Cine rail frame: twin longitudinal rails tied by cross tubes.
        for s in (1, -1):
            rail = [(s * 0.085 * fw, -0.46 * fl), (s * 0.160 * fw, -0.46 * fl),
                    (s * 0.160 * fw, 0.46 * fl), (s * 0.085 * fw, 0.46 * fl)]
            frame_faces.extend(extrude(rail, 'y', -0.150, -0.088))
        for zz in (-0.34 * fl * reach, 0.34 * fl * reach):
            cross = [(-0.15 * fw, zz - 0.026), (0.15 * fw, zz - 0.026),
                     (0.15 * fw, zz + 0.026), (-0.15 * fw, zz + 0.026)]
            frame_faces.extend(extrude(cross, 'y', -0.142, -0.098))
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.20, l * 0.26), 0, 0.0), 'y', -0.098, -0.060),
            col, no_edge=True))
    elif style == 'fold':
        # Folding arms: each arm pivots on a hinge drum near the hub.
        for sx, sz in cycle:
            hx = sx * 0.22 * fw * reach
            hz = sz * 0.20 * fl * reach
            frame_faces.extend(_can_faces(hx, hz, 0.044, -0.156, -0.058, 8))
            lock = [(hx - 0.014, hz - 0.014), (hx + 0.014, hz - 0.014),
                    (hx + 0.014, hz + 0.014), (hx - 0.014, hz + 0.014)]
            ps.append(make_part('body', extrude(lock, 'y', -0.057, -0.044),
                                accent, accent=accent, em=0.35, no_edge=True))
        ps.append(make_part('body', extrude(
            shift(_quad(w * 0.24, l * 0.34), 0, -0.02 * fl), 'y',
            -0.096, -0.052), (44, 58, 86), no_edge=True))
    elif style == 'racer':
        # Stacked carbon race plates with standoffs between them.
        for yy, pc in ((-0.048, (34, 44, 62)), (-0.152, (20, 28, 42))):
            plate = [(-0.21 * fw * reach, yy, -0.21 * fl * reach),
                     (0.21 * fw * reach, yy, -0.21 * fl * reach),
                     (0.21 * fw * reach, yy, 0.21 * fl * reach),
                     (-0.21 * fw * reach, yy, 0.21 * fl * reach)]
            ps.append(make_part('body', [plate], pc, no_edge=False,
                                closed=False))
        stand = []
        for sx in (1, -1):
            for sz in (1, -1):
                stand.extend(_can_faces(sx * 0.15 * fw * reach,
                                        sz * 0.15 * fl * reach, 0.015,
                                        -0.152, -0.048, 6))
        ps.append(make_part('body', stand, (46, 56, 76), accent=accent,
                            em=0.20, no_edge=True))
    elif style == 'truss':
        # Woven truss: paired members braced in a zig-zag along every arm.
        for sx, sz in cycle:
            cx0, cz0 = sx * 0.16 * fw * reach, sz * 0.16 * fl * reach
            cx1, cz1 = sx * 0.72 * fw * reach, sz * 0.60 * fl * reach
            ln = math.hypot(cx1 - cx0, cz1 - cz0) or 1.0
            px, pz = -(cz1 - cz0) / ln, (cx1 - cx0) / ln
            for off in (-0.030, 0.030):
                bar = [(cx0 + px * (off - 0.012), cz0 + pz * (off - 0.012)),
                       (cx1 + px * (off - 0.012), cz1 + pz * (off - 0.012)),
                       (cx1 + px * (off + 0.012), cz1 + pz * (off + 0.012)),
                       (cx0 + px * (off + 0.012), cz0 + pz * (off + 0.012))]
                frame_faces.extend(extrude(bar, 'y', -0.152, -0.090))
            for k in range(3):
                t0, t1 = k / 3.0, (k + 1) / 3.0
                ax, az = cx0 + (cx1 - cx0) * t0, cz0 + (cz1 - cz0) * t0
                bx, bz = cx0 + (cx1 - cx0) * t1, cz0 + (cz1 - cz0) * t1
                o0, o1 = (-0.030, 0.030) if k % 2 == 0 else (0.030, -0.030)
                brace = [(ax + px * (o0 - 0.009), az + pz * (o0 - 0.009)),
                         (bx + px * (o1 - 0.009), bz + pz * (o1 - 0.009)),
                         (bx + px * (o1 + 0.009), bz + pz * (o1 + 0.009)),
                         (ax + px * (o0 + 0.009), az + pz * (o0 + 0.009))]
                frame_faces.extend(extrude(brace, 'y', -0.142, -0.114))

    for s in (1, -1):
        skid = [(s * 0.30 * fw, 0.30 * fl), (s * 0.36 * fw, 0.24 * fl),
                (s * 0.36 * fw, -0.42 * fl), (s * 0.30 * fw, -0.48 * fl)]
        frame_faces.extend(extrude(skid, 'y', -0.215, -0.185))
    ps.append(make_part('body', frame_faces, col, no_edge=False))
    ps.append(make_part('body', mount_faces, (46, 56, 76), no_edge=True))
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
    wid = min(slice_a * 0.72, chord / max(0.06, span * 0.5))
    r0 = hub * 0.92
    r1 = hub + span
    guard = r1 + 0.026
    blade_c = mix((34, 40, 52), paint, 0.9)
    tip_c = mix((176, 184, 198), paint, 0.8)
    drive = motor.get('accent', GOLD) if motor else (64, 78, 104)

    # pylon from the arm tip up to the hub plane
    mast = _can_faces(rc[0], rc[1], 0.027, -0.176, 0.128, 8, cap0=False)
    mast.extend(_can_faces(rc[0], rc[1], 0.041, 0.110, 0.130, 8))
    ps.append(make_part('rotor', mast, (27, 34, 46), no_edge=True))
    collar = _can_faces(rc[0], rc[1], 0.045, 0.131, 0.143, 8)
    ps.append(make_part('rotor', collar, mix((52, 60, 76), paint, 0.74),
                        accent=paint, em=0.0, no_edge=True))

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
    # spinner cone: reads as a machined hub instead of a flat lid
    if not motor:
        cone = _spinner_faces(rc[0], rc[1], hub * 0.60, 0.168, 0.209, 10)
        ps.append(make_part('rotor', cone, mix(drive, (255, 255, 255), 0.16),
                            accent=drive, no_edge=True))
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
        bw = {'double': 0.024, 'shield': 0.034,
              'duct': 0.030}.get(guard_mode, 0.018)
        top, bot = ((0.230, 0.098) if guard_mode == 'duct' else
                    (0.186, 0.128) if guard_mode == 'shield' else (0.178, 0.136))
        faces = _annulus_faces(rc[0], rc[1], guard - bw, guard, bot, top, 10)
        ps.append(make_part('rotor', faces, (30, 38, 52), accent=paint,
                            em=0.0, no_edge=True, closed=False))
        if guard_mode == 'duct':
            lip = _annulus_faces(rc[0], rc[1], guard - bw, guard + 0.012,
                                 0.224, 0.234, 12)
            ps.append(make_part('rotor', lip, mix((34, 42, 58), paint, 0.35),
                                accent=paint, em=0.30, no_edge=True,
                                closed=False))
            vanes = []
            for i in range(4):
                a = math.pi * i / 2 + math.pi / 4
                ca, sa = math.cos(a), math.sin(a)
                r_in, r_out = hub * 0.62, guard - bw
                vanes.append([(rc[0] + r_in * ca - sa * 0.010, 0.104,
                               rc[1] + r_in * sa + ca * 0.010),
                              (rc[0] + r_out * ca - sa * 0.010, 0.104,
                               rc[1] + r_out * sa + ca * 0.010),
                              (rc[0] + r_out * ca + sa * 0.010, 0.104,
                               rc[1] + r_out * sa - ca * 0.010),
                              (rc[0] + r_in * ca + sa * 0.010, 0.104,
                               rc[1] + r_in * sa - ca * 0.010)])
            ps.append(make_part('rotor', vanes, (36, 44, 60), no_edge=True,
                                closed=False))
        if guard_mode == 'double':
            inner = guard - 0.042
            faces2 = _annulus_faces(rc[0], rc[1], inner - 0.013, inner,
                                    0.132, 0.170, 12)
            ps.append(make_part('rotor', faces2, (40, 48, 64), accent=paint,
                                no_edge=True, closed=False))
        elif guard_mode == 'cage':
            cap = _annulus_faces(rc[0], rc[1], guard - 0.016, guard,
                                 0.196, 0.204, 12)
            ps.append(make_part('rotor', cap, (26, 33, 45), accent=paint,
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
            ps.append(make_part('rotor', bars, (38, 46, 62), no_edge=True,
                                closed=False))

    struts = []
    outer = guard if guard_mode != 'open' else r1
    for i in range(4):
        a = math.pi * i / 4 + math.pi / 4
        ca, sa = math.cos(a), math.sin(a)
        hw = 0.012
        struts.append([(rc[0] + hub * 0.5 * ca - sa * hw, 0.126,
                        rc[1] + hub * 0.5 * sa + ca * hw),
                       (rc[0] + outer * ca - sa * hw, 0.126,
                        rc[1] + outer * sa + ca * hw),
                       (rc[0] + outer * ca + sa * hw, 0.126,
                        rc[1] + outer * sa - ca * hw),
                       (rc[0] + hub * 0.5 * ca + sa * hw, 0.126,
                        rc[1] + hub * 0.5 * sa - ca * hw)])
    ps.append(make_part('rotor', struts, (44, 54, 72), no_edge=True,
                        closed=False))

    faces, cols = [], []
    y_r, y_t = 0.150, 0.157
    rs = r1 - span * 0.20
    ts = (rs - r0) / max(1e-6, r1 - r0)
    for i in range(blades):
        a0 = 2 * math.pi * i / blades
        a1 = a0 + wid
        am = a0 + (a1 - a0) * 0.45

        def station(t, rad):
            base = y_r + (y_t - y_r) * t
            sw = sweep * t
            cam = 0.0065 * (1.0 - 0.55 * t)
            b0 = (rad * math.cos(a0 + sw), rad * math.sin(a0 + sw))
            bm = (rad * math.cos(am + sw), rad * math.sin(am + sw))
            b1 = (rad * math.cos(a1 + sw), rad * math.sin(a1 + sw))
            le = (rc[0] + b0[0], base + 0.002 * (1 - t), rc[1] + b0[1])
            rd = (rc[0] + bm[0], base + cam, rc[1] + bm[1])
            te = (rc[0] + b1[0], base - 0.003 * (1 - t), rc[1] + b1[1])
            return le, rd, te

        le0, rd0, te0 = station(0.0, r0)
        les, rds, tes = station(ts, rs)
        le1, rd1, te1 = station(1.0, r1)
        # continuous cambered blade: root camber in two quads, painted tip band
        # spans the full chord so it never reads as a floating wedge
        faces.append([le0, les, rds, rd0])
        faces.append([rd0, rds, tes, te0])
        faces.append([les, le1, te1, tes])
        cols.extend((blade_c, blade_c, tip_c))
    ps.append(make_part('rotor', faces, blade_c, accent=tip_c, em=0.0,
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
    elif style == 'split':
        # Split-tip blade pair: two short fins splayed off the trailing edge.
        for k, dz in ((0, 0.010), (1, 0.060)):
            tip = [(s * (x1 + dz * 0.4), (-0.03 + 0.05 * k) * c + sweep),
                   (s * (x1 + dz + 0.02), -0.15 * c + sweep),
                   (s * (x1 + dz + 0.05), -0.15 * c + sweep),
                   (s * (x1 + dz * 0.4 + 0.022), (-0.03 + 0.05 * k) * c + sweep)]
            ps.append(make_part('wing', extrude(tip, 'y', y1 + 0.018 * k,
                                                y1 + 0.150 + 0.018 * k), color))
            ps.append(make_part('wing', extrude(tip, 'y', y1 + 0.150 + 0.018 * k,
                                                y1 + 0.164 + 0.018 * k),
                                trim, no_edge=True))
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
    elif style == 'ducted':
        # Shrouded fan: a fat duct barrel with a glowing face grille.
        ps.append(make_part('booster', extrude(
            circ(rad * 1.34, x, -0.075, 12), 'z', z0, z1 + 0.018),
            mix(col, (255, 255, 255), 0.08)))
        ps.append(make_part('booster', extrude(
            circ(rad * 1.40, x, -0.075, 12), 'z', z0 + 0.010, z0 + 0.030),
            accent, accent=accent, em=0.50, no_edge=True))
        face = extrude(circ(rad * 1.04, x, -0.075, 12), 'z',
                       z1 + 0.014, z1 + 0.024)
        ps.append(make_part('booster', face, DARKM, accent=accent, em=0.95,
                            no_edge=True))
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
    {'id': 'body_courier', 'slot': 'body', 'name': 'COURIER', 'price': 760,
     'desc': 'LONG RANGE HAULER', 'accent': (120, 168, 220),
     'stats': {'mass': 60, 'thrust': 0, 'drag': 1.20, 'lift': 1, 'agility': 2, 'energy': 0},
     'geo': {'w': 0.66, 'l': 1.38, 'hull': (52, 88, 140), 'deck': (88, 132, 184),
             'canopy_w': 0.48, 'canopy_l': 0.28, 'style': 'atlas'}},
    {'id': 'body_needle', 'slot': 'body', 'name': 'NEEDLE', 'price': 980,
     'desc': 'STRIP BUILD SPRINTER', 'accent': (255, 196, 110),
     'stats': {'mass': 30, 'thrust': 0, 'drag': 0.55, 'lift': 2, 'agility': 16, 'energy': 0},
     'geo': {'w': 0.40, 'l': 1.26, 'hull': (70, 120, 186), 'deck': (126, 178, 236),
             'canopy_w': 0.64, 'canopy_l': 0.24, 'stripe': (255, 196, 110),
             'style': 'hornet'}},
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
    {'id': 'frame_truss', 'slot': 'frame', 'name': 'TRUSS RIG', 'price': 620,
     'desc': 'HEAVY WIDE STANCE', 'accent': (150, 178, 210),
     'stats': {'mass': 26, 'thrust': 0, 'drag': 0.52, 'lift': 0, 'agility': -7,
               'energy': 0},
     'geo': {'reach': 1.24, 'col': (48, 62, 92), 'style': 'h'}},
    {'id': 'frame_needle', 'slot': 'frame', 'name': 'NEEDLE HUB', 'price': 460,
     'desc': 'TIGHT LIGHT HUB', 'accent': (132, 226, 214),
     'stats': {'mass': 7, 'thrust': 0, 'drag': 0.14, 'lift': 0, 'agility': 9,
               'energy': 0},
     'geo': {'reach': 0.82, 'col': (28, 42, 66), 'style': 'ring'}},
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
    {'id': 'rotor_gale', 'slot': 'rotor', 'name': 'GALE', 'price': 700,
     'desc': 'EIGHT-BLADE GUST', 'accent': (150, 236, 214),
     'params': {'span': 0.40, 'chord': 0.095, 'blades': 8, 'sweep': 0.06,
                'thickness': 0.015, 'material': 'composite', 'guard': 'cage',
                'hub': 0.080}},
    {'id': 'rotor_whisper', 'slot': 'rotor', 'name': 'WHISPER', 'price': 820,
     'desc': 'QUIET LOW DRAG SET', 'accent': (186, 214, 236),
     'params': {'span': 0.28, 'chord': 0.072, 'blades': 18, 'sweep': 0.10,
                'thickness': 0.008, 'material': 'carbon', 'guard': 'ring',
                'hub': 0.070}},
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
    {'id': 'motor_pulse', 'slot': 'motor', 'name': 'PULSE CORE', 'price': 520,
     'desc': 'BURST OUTPUT SET', 'accent': (255, 170, 110),
     'stats': {'mass': 44, 'thrust': 138, 'drag': 0.48, 'lift': 0, 'agility': -1,
               'energy': 26},
     'geo': {'style': 'finned'}},
    {'id': 'motor_micro', 'slot': 'motor', 'name': 'MICRO DRIVE', 'price': 480,
     'desc': 'TINY FAST RESPONSE', 'accent': (150, 230, 220),
     'stats': {'mass': 22, 'thrust': 84, 'drag': 0.16, 'lift': 0, 'agility': 8,
               'energy': 40},
     'geo': {'style': 'tall'}},
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
    {'id': 'wing_saber', 'slot': 'wing', 'name': 'SABER', 'price': 760,
     'desc': 'SWEPT FANG WINGS', 'accent': GOLD,
     'stats': {'mass': 14, 'thrust': 0, 'drag': 1.35, 'lift': 18, 'agility': 16, 'energy': 0},
     'geo': {'span_s': 1.02, 'sweep': 0.12, 'chord': 0.96, 'color': (58, 92, 150),
             'trim': GOLD, 'style': 'delta'}},
    {'id': 'wing_kite', 'slot': 'wing', 'name': 'KITE', 'price': 560,
     'desc': 'HIGH ASPECT LIFT', 'accent': (130, 236, 200),
     'stats': {'mass': 20, 'thrust': 0, 'drag': 1.05, 'lift': 32, 'agility': 6, 'energy': 0},
     'geo': {'span_s': 1.18, 'sweep': -0.02, 'chord': 1.08,
             'trim': (130, 236, 200), 'style': 'glide'}},
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
    {'id': 'boost_dart', 'slot': 'booster', 'name': 'DART', 'price': 520,
     'desc': 'SHORT PUNCH BURN', 'accent': TEAL,
     'stats': {'mass': 14, 'thrust': 84, 'drag': 0.60, 'lift': 0, 'agility': 0, 'energy': 66},
     'geo': {'rad': 0.066, 'length': 0.36, 'accent': TEAL, 'col': (44, 66, 104),
             'style': 'long'}},
    {'id': 'boost_nova', 'slot': 'booster', 'name': 'NOVA', 'price': 860,
     'desc': 'WIDE PLASMA BELL', 'accent': (200, 150, 255),
     'stats': {'mass': 36, 'thrust': 124, 'drag': 1.20, 'lift': 0, 'agility': 0, 'energy': 106},
     'geo': {'rad': 0.115, 'length': 0.46, 'accent': (200, 150, 255),
             'col': (58, 48, 92), 'style': 'bell'}},
)

# ---------------- extended inventory ----------------
# Thirty modules per slot: budget, mid-range and elite hardware behind the
# original starters. Rows stay one line each so the spread is easy to audit.

def _body(slug, name, desc, price, accent, w, l, style, mass, drag, lift,
          agility, extra=None):
    g = {'w': w, 'l': l, 'hull': accent,
         'deck': mix(accent, (255, 255, 255), 0.55), 'style': style}
    if extra:
        g.update(extra)
    return {'id': 'body_' + slug, 'slot': 'body', 'name': name, 'price': price,
            'desc': desc, 'accent': accent,
            'stats': {'mass': mass, 'thrust': 0, 'drag': drag, 'lift': lift,
                      'agility': agility, 'energy': 0},
            'geo': g}


def _frame(slug, name, desc, price, accent, reach, style, mass, drag,
           agility, col):
    return {'id': 'frame_' + slug, 'slot': 'frame', 'name': name,
            'price': price, 'desc': desc, 'accent': accent,
            'stats': {'mass': mass, 'thrust': 0, 'drag': drag, 'lift': 0,
                      'agility': agility, 'energy': 0},
            'geo': {'reach': reach, 'col': col, 'style': style}}


def _rotor(slug, name, desc, price, accent, span, chord, blades, sweep,
           thick, mat, guard, hub):
    p = {'span': span, 'chord': chord, 'blades': blades, 'sweep': sweep,
         'thickness': thick, 'material': mat, 'guard': guard, 'hub': hub}
    return {'id': 'rotor_' + slug, 'slot': 'rotor', 'name': name,
            'price': price, 'desc': desc, 'accent': accent,
            'params': p, 'stats': rotor_stats(**p)}


def _motor(slug, name, desc, price, accent, style, mass, thrust, drag,
           agility, energy):
    return {'id': 'motor_' + slug, 'slot': 'motor', 'name': name,
            'price': price, 'desc': desc, 'accent': accent,
            'stats': {'mass': mass, 'thrust': thrust, 'drag': drag, 'lift': 0,
                      'agility': agility, 'energy': energy},
            'geo': {'style': style}}


def _wing(slug, name, desc, price, accent, span_s, sweep, chord, lift,
          agility, mass, drag, style):
    return {'id': 'wing_' + slug, 'slot': 'wing', 'name': name,
            'price': price, 'desc': desc, 'accent': accent,
            'stats': {'mass': mass, 'thrust': 0, 'drag': drag, 'lift': lift,
                      'agility': agility, 'energy': 0},
            'geo': {'span_s': span_s, 'sweep': sweep, 'chord': chord,
                    'trim': accent, 'style': style}}


def _booster(slug, name, desc, price, accent, style, rad, length, mass,
             thrust, drag, energy):
    return {'id': 'booster_' + slug, 'slot': 'booster', 'name': name,
            'price': price, 'desc': desc, 'accent': accent,
            'stats': {'mass': mass, 'thrust': thrust, 'drag': drag, 'lift': 0,
                      'agility': 0, 'energy': energy},
            'geo': {'rad': rad, 'length': length, 'accent': accent,
                    'col': mix(accent, (30, 40, 60), 0.30), 'style': style}}


BODIES += tuple(_body(*row[:12], extra=(row[12] if len(row) > 12 else None))
                for row in (
    ('talon', 'TALON', 'NIMBLE INTERCEPTOR', 1100, (150, 190, 240),
     0.42, 1.16, 'velocity', 34, 0.58, 2, 15,
     {'canopy_w': 0.60, 'canopy_l': 0.32}),
    ('bastion', 'BASTION', 'ARMORED LIFT HULL', 1240, (90, 130, 190),
     0.74, 1.36, 'atlas', 76, 1.68, 0, -8),
    ('skiff', 'SKIFF', 'COMPACT PATROL HULL', 260, (110, 160, 214),
     0.50, 1.10, 'scout', 40, 0.95, 0, 7),
    ('york', 'YORK', 'CONVOY CARGO HULL', 1350, (96, 136, 188),
     0.80, 1.44, 'mule', 90, 1.95, 0, -11, {'canopy_w': 0.44}),
    ('drifter', 'DRIFTER', 'STABLE CRUISER HULL', 340, (112, 172, 226),
     0.58, 1.20, 'scout', 48, 1.10, 1, 5),
    ('razorback', 'RAZORBACK', 'LOW SPLIT HULL', 1480, (120, 214, 236),
     0.60, 1.32, 'manta', 50, 0.56, 5, 9, {'canopy_w': 0.46}),
    ('wasp', 'WASP', 'STING SPRINT HULL', 900, (255, 196, 110),
     0.42, 1.14, 'hornet', 30, 0.60, 1, 15,
     {'canopy_w': 0.62, 'canopy_l': 0.24, 'stripe': (255, 196, 110)}),
    ('goliath', 'GOLIATH', 'SIEGE CARRIER HULL', 2200, (84, 120, 172),
     0.82, 1.48, 'mule', 90, 1.98, 0, -12, {'canopy_w': 0.44}),
    ('zephyr', 'ZEPHYR', 'GLIDE RECON HULL', 980, (138, 196, 240),
     0.56, 1.28, 'velocity', 42, 0.72, 3, 11),
    ('osprey', 'OSPREY', 'DOUBLE DECK HULL', 720, (104, 154, 208),
     0.64, 1.30, 'atlas', 58, 1.30, 1, 3, {'canopy_w': 0.50}),
    ('kestrel', 'KESTREL', 'SCOUT SPRINT HULL', 520, (128, 180, 232),
     0.46, 1.12, 'scout', 36, 0.82, 1, 10),
    ('halcyon', 'HALCYON', 'QUIET GLIDE SHELL', 1650, (90, 196, 214),
     0.60, 1.34, 'manta', 54, 0.52, 5, 7, {'canopy_w': 0.46}),
    ('nomad', 'NOMAD', 'FIELD HAULER HULL', 640, (116, 158, 206),
     0.68, 1.36, 'atlas', 64, 1.42, 0, 0),
    ('comet', 'COMET', 'FEATHER RACER HULL', 1320, (255, 206, 128),
     0.38, 1.22, 'hornet', 28, 0.52, 3, 17,
     {'canopy_w': 0.62, 'canopy_l': 0.26}),
    ('colossus', 'COLOSSUS', 'DEEP LIFT PLATFORM', 2400, (80, 112, 160),
     0.84, 1.50, 'mule', 90, 2.00, 0, -12, {'canopy_w': 0.44}),
    ('vector', 'VECTOR', 'PRECISION HULL', 1080, (124, 182, 238),
     0.48, 1.26, 'velocity', 39, 0.66, 2, 13),
    ('bulwark', 'BULWARK', 'HEAVY ARMOR HULL', 1560, (88, 126, 182),
     0.72, 1.34, 'atlas', 74, 1.60, 0, -7),
    ('ghost', 'GHOST', 'RADAR ELUDER HULL', 1980, (120, 196, 220),
     0.58, 1.32, 'manta', 52, 0.50, 5, 8, {'canopy_w': 0.46}),
    ('swallow', 'SWALLOW', 'LIGHT COURIER HULL', 300, (118, 168, 220),
     0.52, 1.12, 'scout', 41, 0.98, 0, 8),
    ('lancer', 'LANCER', 'STRIKE HULL', 1160, (255, 186, 104),
     0.44, 1.20, 'hornet', 33, 0.64, 2, 14,
     {'canopy_w': 0.62, 'canopy_l': 0.24}),
    ('foundry', 'FOUNDRY', 'WORKSHOP SHELL', 1740, (100, 140, 192),
     0.70, 1.42, 'atlas', 68, 1.52, 1, 1),
    ('obsidian', 'OBSIDIAN', 'BLACKOUT HULL', 2600, (60, 72, 96),
     0.62, 1.36, 'manta', 56, 0.54, 6, 10, {'canopy_w': 0.46}),
    # Heritage airframes: shells shaped after the well-known commercial
    # archetypes — folding camera quad, cine T-frame, FPV plate, micro quad.
    ('lens', 'LENS', 'FOLDING CAMERA QUAD', 1020, (128, 178, 228),
     0.50, 1.10, 'fold', 42, 0.92, 1, 9, {'canopy_w': 0.50, 'canopy_l': 0.22}),
    ('mast', 'MAST', 'CINE T-FRAME QUAD', 1180, (116, 168, 222),
     0.46, 1.28, 'tf', 36, 0.70, 2, 12, {'canopy_w': 0.36, 'canopy_l': 0.30}),
    ('blitz', 'BLITZ', 'FPV RACE PLATE', 900, (255, 186, 104),
     0.44, 1.06, 'racer', 28, 0.56, 0, 16, {'canopy_w': 0.56, 'canopy_l': 0.22}),
    ('pocket', 'POCKET', 'MICRO SELFIE QUAD', 420, (150, 206, 238),
     0.40, 0.96, 'mini', 26, 0.68, 0, 13, {'canopy_w': 0.54, 'canopy_l': 0.24}),
))

FRAMES += tuple(_frame(*row) for row in (
    ('pylon', 'PYLON', 'TALL MOUNT SPAR', 260, GOLD, 1.02, 'spar',
     13, 0.22, 1, (40, 58, 88)),
    ('splay', 'SPLAY', 'WIDE SPLAY RIG', 300, (132, 226, 214), 1.08, 'fold',
     16, 0.32, -2, (42, 60, 90)),
    ('lattice', 'LATTICE', 'CROSS BRACED FRAME', 580, (150, 178, 210),
     1.18, 'truss', 22, 0.46, -5, (50, 64, 94)),
    ('nest', 'NEST', 'TIGHT RING FRAME', 240, (120, 220, 206), 0.84, 'ring',
     8, 0.16, 7, (30, 46, 72)),
    ('hub', 'HUB', 'STOCK RING FRAME', 180, (110, 160, 220), 0.88, 'ring',
     10, 0.20, 5, (32, 48, 76)),
    ('outrig', 'OUTRIG', 'FAR SPAN RIG', 640, (160, 190, 220), 1.22, 'h',
     24, 0.50, -6, (52, 68, 100)),
    ('gantry', 'GANTRY', 'HEAVY SPAN FRAME', 700, (150, 184, 214), 1.28,
     'truss', 26, 0.54, -8, (54, 70, 102)),
    ('scaffold', 'SCAFFOLD', 'MAX SPAN FRAME', 820, (168, 196, 226), 1.30,
     'truss', 28, 0.55, -8, (56, 72, 104)),
    ('spine', 'SPINE', 'LONG BACKBONE SPAR', 420, GOLD, 1.06, 'spar',
     15, 0.27, 0, (42, 60, 92)),
    ('bowspar', 'BOWSPAR', 'FORWARD SPAR RIG', 480, (255, 205, 108), 1.12,
     'spar', 17, 0.31, -2, (44, 62, 94)),
    ('tripod', 'TRIPOD', 'THREE POINT RING', 620, (140, 214, 204), 0.90,
     'ring', 12, 0.26, 4, (34, 50, 78)),
    ('halo', 'HALO', 'CIRCULAR RING FRAME', 560, (110, 226, 196), 0.96,
     'ring', 11, 0.24, 5, (36, 52, 80)),
    ('dart', 'DART', 'MINI HUB FRAME', 340, (150, 230, 220), 0.80, 'racer',
     7, 0.14, 10, (28, 44, 68)),
    ('rail', 'RAIL', 'SLIM PARALLEL RIG', 380, (124, 182, 238), 0.98,
     'tf', 12, 0.23, 3, (40, 56, 86)),
    ('brace', 'BRACE', 'TRIANGULATED SPAR', 460, (150, 178, 210), 1.04,
     'truss', 14, 0.26, 1, (42, 58, 88)),
    ('cage', 'CAGE', 'ENCLOSED RING FRAME', 740, (160, 200, 228), 0.94,
     'ring', 13, 0.30, 2, (38, 54, 82)),
    ('cantilever', 'CANTILEVER', 'OFFSET MOUNT RIG', 600, (156, 186, 216),
     1.14, 'tf', 20, 0.42, -4, (48, 64, 96)),
    ('boom', 'BOOM', 'EXTENDED SPAR RIG', 520, (140, 172, 204), 1.10,
     'fold', 16, 0.29, 0, (44, 60, 90)),
    ('aframe', 'A-FRAME', 'LIGHT TRUSS FRAME', 440, (168, 196, 224), 1.06,
     'truss', 15, 0.28, 2, (46, 62, 92)),
    ('torii', 'TORII', 'WIDE GATE FRAME', 880, (176, 204, 232), 1.26, 'tf',
     25, 0.52, -7, (58, 74, 106)),
    ('puck', 'PUCK', 'FLAT RING HUB', 200, (128, 190, 214), 0.82, 'racer',
     6, 0.12, 9, (26, 42, 66)),
    ('wishbone', 'WISHBONE', 'FORKED SPAR FRAME', 500, GOLD, 1.00, 'truss',
     13, 0.24, 4, (40, 58, 86)),
    ('ladder', 'LADDER', 'BOXED RING RIG', 680, (150, 196, 222), 0.98,
     'ring', 14, 0.32, 1, (38, 54, 84)),
    ('monocoque', 'MONOCOQUE', 'SMOOTH SHELL SPAR', 940, (120, 170, 226),
     1.18, 'spar', 19, 0.38, -3, (48, 64, 96)),
    ('keel', 'KEEL', 'LOW CENTER SPAR', 760, (110, 166, 222), 1.14,
     'spar', 18, 0.33, -1, (46, 62, 94)),
    ('foldarm', 'FOLDARM', 'HINGED FOLDING ARMS', 460, (132, 226, 214),
     0.96, 'fold', 11, 0.20, 5, (34, 52, 82)),
    ('carbonx', 'CARBON X', 'STACKED RACE PLATES', 420, (150, 178, 210),
     0.90, 'racer', 8, 0.15, 9, (26, 36, 56)),
    ('twinrail', 'TWIN RAIL', 'CINE RAIL FRAME', 640, (124, 182, 238),
     1.18, 'tf', 18, 0.38, -3, (44, 60, 92)),
    ('weave', 'WEAVE', 'WOVEN TRUSS ARMS', 560, (160, 190, 220),
     1.10, 'truss', 17, 0.34, 0, (48, 64, 96)),
))

ROTORS += tuple(_rotor(*row) for row in (
    ('whirl', 'WHIRL', 'TEN BLADE ALL ROUND', 320, GOLD,
     0.30, 0.085, 10, 0.03, 0.012, 'alloy', 'ring', 0.072),
    ('scythe', 'SCYTHE', 'HEAVY SWEPT SET', 940, (255, 212, 128),
     0.36, 0.095, 7, 0.20, 0.013, 'carbon', 'open', 0.078),
    ('quad', 'QUAD', 'FOUR BLADE LIFT', 880, (255, 190, 110),
     0.42, 0.115, 6, -0.02, 0.020, 'alloy', 'double', 0.090),
    ('breeze', 'BREEZE', 'LIGHT GUST SET', 360, (150, 236, 214),
     0.28, 0.078, 9, 0.05, 0.010, 'composite', 'open', 0.068),
    ('tempest', 'TEMPEST', 'STORM LIFT SET', 1280, (132, 226, 210),
     0.44, 0.105, 13, 0.02, 0.017, 'carbon', 'shield', 0.086),
    ('mica', 'MICA', 'THIN FAST DISC', 560, (186, 214, 236),
     0.26, 0.068, 14, 0.12, 0.008, 'carbon', 'ring', 0.066),
    ('drone', 'DRONE', 'SERVICE ROTOR SET', 120, GOLD,
     0.26, 0.075, 8, 0.0, 0.012, 'alloy', 'ring', 0.066),
    ('fury', 'FURY', 'AGGRESSIVE SPAN SET', 1180, (255, 168, 120),
     0.40, 0.100, 12, 0.10, 0.014, 'carbon', 'double', 0.082),
    ('serene', 'SERENE', 'QUIET CIVIL SET', 420, (170, 206, 230),
     0.30, 0.080, 16, 0.04, 0.009, 'composite', 'shield', 0.070),
    ('stiletto', 'STILETTO', 'NEEDLE THIN BLADES', 760, (255, 236, 190),
     0.24, 0.060, 18, 0.16, 0.008, 'carbon', 'open', 0.062),
    ('mistral', 'MISTRAL', 'COLD AIR SET', 660, (150, 220, 236),
     0.32, 0.090, 12, -0.06, 0.012, 'composite', 'cage', 0.074),
    ('boreas', 'BOREAS', 'NORTH WIND LIFT', 1120, (120, 200, 240),
     0.38, 0.095, 15, 0.06, 0.013, 'carbon', 'cage', 0.084),
    ('sirocco', 'SIROCCO', 'DESERT DUST ROTOR', 900, (255, 196, 132),
     0.34, 0.088, 11, 0.14, 0.015, 'alloy', 'double', 0.078),
    ('monsoon', 'MONSOON', 'HEAVY RAIN DISCS', 1460, (110, 190, 220),
     0.42, 0.108, 14, 0.02, 0.016, 'carbon', 'shield', 0.088),
    ('draft', 'DRAFT', 'LIGHT SHORT SET', 280, (160, 226, 214),
     0.26, 0.072, 10, 0.08, 0.010, 'composite', 'open', 0.064),
    ('vane', 'VANE', 'PITCHED BLADE SET', 540, (200, 222, 238),
     0.28, 0.082, 12, 0.22, 0.010, 'carbon', 'ring', 0.068),
    ('gust', 'GUST', 'HIGH FLOW SET', 820, (150, 236, 214),
     0.34, 0.096, 10, 0.06, 0.014, 'alloy', 'open', 0.076),
    ('rune', 'RUNE', 'SYMMETRIC DISC SET', 1240, (196, 166, 255),
     0.36, 0.092, 16, -0.02, 0.012, 'carbon', 'shield', 0.080),
    ('flurry', 'FLURRY', 'FAST LIGHT SET', 480, (176, 222, 240),
     0.28, 0.074, 13, 0.10, 0.009, 'composite', 'ring', 0.066),
    ('hail', 'HAIL', 'HARD HIT ROTOR SET', 1360, (150, 200, 226),
     0.40, 0.112, 12, 0.0, 0.018, 'alloy', 'double', 0.086),
    ('shade', 'SHADE', 'STEALTH ROTOR SET', 1680, (104, 132, 180),
     0.30, 0.086, 14, 0.18, 0.010, 'carbon', 'open', 0.070),
    ('tide', 'TIDE', 'SMOOTH PULL SET', 720, (140, 210, 224),
     0.32, 0.086, 11, -0.04, 0.012, 'composite', 'cage', 0.076),
    ('ducted', 'DUCTED', 'SHROUDED FAN SET', 880, (150, 214, 238),
     0.34, 0.095, 10, 0.02, 0.014, 'alloy', 'duct', 0.080),
))

MOTORS += tuple(_motor(*row) for row in (
    ('coil', 'COIL DRIVE', 'TIDY QUAD SET', 180, GOLD, 'can',
     32, 92, 0.28, 1, 22),
    ('twin', 'TWIN DRIVE', 'DUAL SHAFT SET', 360, (150, 220, 214), 'tall',
     32, 100, 0.26, 4, 30),
    ('hammer', 'HAMMER DRIVE', 'BRUTE LIFT SET', 560, (255, 150, 90),
     'finned', 56, 158, 0.58, -2, 10),
    ('sharp', 'SHARP DRIVE', 'FAST THROTTLE SET', 620, (255, 170, 120),
     'tall', 30, 112, 0.20, 6, 38),
    ('arc', 'ARC DRIVE', 'CLEAN ARC SET', 700, GLASS, 'dome',
     36, 120, 0.22, 2, 70),
    ('flux', 'FLUX CORE', 'VARIABLE FLUX SET', 760, (178, 132, 255), 'dome',
     38, 132, 0.20, 1, 76),
    ('spark', 'SPARK DRIVE', 'QUICK BURST SET', 420, (150, 230, 220), 'tall',
     26, 96, 0.18, 7, 44),
    ('anvil', 'ANVIL DRIVE', 'DEAD LIFT SET', 820, (255, 140, 84), 'finned',
     60, 172, 0.64, -3, 12),
    ('waft', 'WAFT DRIVE', 'SOFT SPIN SET', 300, (170, 210, 230), 'can',
     30, 88, 0.24, 3, 24),
    ('span', 'SPAN DRIVE', 'BALANCED SET', 480, (124, 182, 238), 'can',
     38, 118, 0.30, 0, 28),
    ('kite', 'KITE DRIVE', 'LIGHT TORQUE SET', 340, (160, 230, 214), 'tall',
     24, 90, 0.16, 8, 42),
    ('cobalt', 'COBALT DRIVE', 'COOL RUN SET', 540, (110, 190, 240), 'can',
     34, 110, 0.24, 3, 34),
    ('ember', 'EMBER DRIVE', 'HOT BURN SET', 660, (255, 160, 96), 'finned',
     46, 144, 0.46, -1, 22),
    ('prism', 'PRISM CORE', 'LIGHTWEIGHT CORE', 880, (200, 160, 255), 'dome',
     32, 128, 0.18, 4, 86),
    ('gyro', 'GYRO DRIVE', 'STEADY SPIN SET', 600, (150, 214, 236), 'tall',
     30, 108, 0.20, 5, 36),
    ('titanus', 'TITAN DRIVE', 'MAX LIFT SET', 980, (255, 150, 90), 'finned',
     58, 178, 0.60, -3, 8),
    ('nano', 'NANO DRIVE', 'MICRO CORE SET', 720, (150, 236, 220), 'tall',
     18, 86, 0.14, 10, 48),
    ('duct', 'DUCT DRIVE', 'MASKED THRUST SET', 520, (140, 196, 236), 'can',
     36, 116, 0.26, 2, 30),
    ('stator', 'STATOR DRIVE', 'LOW VIBE SET', 440, (160, 206, 232), 'can',
     34, 104, 0.22, 4, 32),
    ('helios', 'HELIOS CORE', 'SOLAR RELAY SET', 1200, (255, 220, 140),
     'dome', 40, 140, 0.16, 0, 96),
    ('bore', 'BORE DRIVE', 'HIGH TORQUE SET', 660, (255, 158, 96), 'finned',
     52, 152, 0.52, -1, 16),
    ('volt', 'VOLT DRIVE', 'SNAP RESPONSE SET', 580, (255, 230, 84), 'tall',
     28, 106, 0.18, 7, 52),
    ('torus', 'TORUS CORE', 'RING MOTOR SET', 1040, (140, 220, 255), 'dome',
     38, 136, 0.20, 1, 82),
    ('wraith', 'WRAITH CORE', 'SILENT RUN SET', 860, (150, 180, 214), 'can',
     30, 112, 0.18, 6, 58),
))

WINGS += tuple(_wing(*row) for row in (
    ('fin', 'FIN', 'SHORT CORNER WINGS', 300, (150, 220, 206),
     0.90, 0.06, 0.90, 15, 14, 12, 1.70, 'canard'),
    ('sweep', 'SWEEP', 'CLEAN SWEPT SET', 420, (124, 182, 238),
     1.00, 0.08, 0.98, 20, 12, 16, 1.45, 'delta'),
    ('lark', 'LARK', 'LIGHT GLIDE PAIR', 340, (130, 236, 200),
     1.10, -0.02, 1.06, 28, 6, 20, 1.10, 'glide'),
    ('hawk', 'HAWK', 'FALCON LIFT SET', 680, (255, 190, 110),
     1.16, -0.06, 1.14, 34, 5, 24, 1.00, 'glide'),
    ('blade', 'BLADE', 'THIN CUT WINGS', 760, GOLD,
     0.92, 0.18, 0.90, 12, 20, 10, 1.55, 'delta'),
    ('moth', 'MOTH', 'BROAD SOFT WINGS', 560, (160, 206, 236),
     1.20, -0.08, 1.18, 36, 3, 26, 0.95, 'manta'),
    ('dagger', 'DAGGER', 'AGILE DAGGER PAIR', 820, (255, 178, 96),
     0.88, 0.14, 0.86, 11, 22, 9, 1.50, 'delta'),
    ('crane', 'CRANE', 'LONG SPAN WINGS', 600, (140, 222, 214),
     1.22, -0.04, 1.12, 38, 4, 28, 1.05, 'glide'),
    ('ledge', 'LEDGE', 'STUBBY LIFT WINGS', 380, (150, 200, 228),
     0.94, 0.02, 0.92, 18, 8, 14, 1.25, 'panel'),
    ('trident', 'TRIDENT', 'TRIPLE FIN SET', 900, (110, 226, 196),
     1.06, 0.06, 1.00, 22, 14, 18, 1.20, 'twin'),
    ('wisp', 'WISP', 'FEATHER WINGS', 440, (180, 214, 238),
     0.98, -0.02, 0.94, 16, 16, 10, 1.15, 'panel'),
    ('sabre', 'SABRE', 'CUTTING EDGE PAIR', 880, (255, 206, 128),
     1.02, 0.14, 0.96, 17, 18, 13, 1.35, 'delta'),
    ('gull', 'GULL', 'HIGH LIFT ARCH', 700, (130, 216, 230),
     1.18, -0.10, 1.10, 36, 6, 25, 1.10, 'glide'),
    ('stub', 'STUB', 'TINY CONTROL FINS', 220, (150, 190, 220),
     0.86, 0.04, 0.84, 9, 24, 8, 1.90, 'canard'),
    ('leap', 'LEAP', 'SPRINT WING PAIR', 520, (150, 236, 214),
     0.96, 0.10, 0.92, 15, 20, 12, 1.40, 'canard'),
    ('feather', 'FEATHER', 'WIDE GLIDE PAIR', 780, (124, 200, 244),
     1.24, -0.06, 1.20, 40, 4, 27, 0.90, 'manta'),
    ('flare', 'FLARE', 'UPSWEPT TIPS', 640, (255, 170, 120),
     1.04, 0.02, 1.02, 22, 12, 17, 1.25, 'twin'),
    ('skid', 'SKID', 'GROUND HUG FINS', 260, (140, 180, 214),
     0.90, 0.0, 0.88, 12, 10, 11, 1.60, 'panel'),
    ('claw', 'CLAW', 'GRIP LIFT WINGS', 740, (255, 190, 110),
     1.08, 0.08, 1.04, 24, 11, 19, 1.20, 'twin'),
    ('nimbus', 'NIMBUS', 'CLOUD GLIDE SET', 960, (110, 200, 240),
     1.26, -0.12, 1.22, 42, 3, 29, 0.95, 'manta'),
    ('arrow', 'ARROW', 'STRAIGHT SPEED FINS', 500, GOLD,
     0.94, 0.12, 0.90, 13, 22, 10, 1.50, 'delta'),
    ('siren', 'SIREN', 'TWIN CUT WINGS', 840, (196, 166, 255),
     1.10, 0.06, 1.06, 26, 13, 21, 1.15, 'twin'),
    ('fork', 'FORK', 'SPLIT TIP WINGS', 660, (150, 226, 206),
     1.04, 0.10, 0.98, 22, 12, 16, 1.30, 'split'),
))

BOOSTERS += tuple(_booster(*row) for row in (
    ('sprint', 'SPRINT', 'LIGHT FAST BURN', 260, TEAL, 'long',
     0.062, 0.30, 12, 74, 0.55, 62),
    ('forge', 'FORGE', 'HEAVY BURN CAN', 640, (255, 148, 84), 'fin',
     0.105, 0.44, 28, 112, 1.25, 74),
    ('vega', 'VEGA', 'BALANCED JET PAIR', 480, (140, 210, 240), 'twin',
     0.072, 0.36, 17, 90, 0.82, 74),
    ('orbit', 'ORBIT', 'ROUND ION BELL', 740, GLASS, 'bell',
     0.095, 0.42, 24, 96, 0.90, 104),
    ('cinder', 'CINDER', 'HOT SHORT BURN', 360, (255, 140, 84), 'fin',
     0.080, 0.32, 18, 88, 0.95, 58),
    ('aburn', 'ABURN', 'TAPERED RAMJET', 820, GOLD, 'ram',
     0.070, 0.56, 18, 104, 0.70, 112),
    ('pair', 'PAIR', 'TWIN SMALL SET', 340, (150, 220, 214), 'twin',
     0.060, 0.30, 13, 78, 0.70, 64),
    ('flame', 'FLAME', 'WIDE EXHAUST BELL', 700, (255, 160, 90), 'bell',
     0.105, 0.40, 26, 108, 1.15, 88),
    ('cold', 'COLD', 'LOW HEAT ENGINE', 680, (150, 220, 250), 'long',
     0.078, 0.50, 19, 92, 0.72, 108),
    ('beat', 'BEAT', 'PUNCHY SHORT CAN', 420, (255, 170, 110), 'fin',
     0.085, 0.34, 20, 96, 1.00, 66),
    ('lance', 'LANCE', 'LONG AXIAL BURN', 860, (140, 210, 244), 'ram',
     0.066, 0.62, 16, 98, 0.65, 118),
    ('surge', 'SURGE', 'BURST BELL SET', 560, (140, 200, 255), 'bell',
     0.100, 0.40, 25, 102, 1.05, 82),
    ('quill', 'QUILL', 'THIN QUAD JETS', 300, TEAL, 'twin',
     0.058, 0.28, 11, 72, 0.62, 58),
    ('ash', 'ASH', 'QUIET LOW PULL', 580, (150, 180, 214), 'long',
     0.072, 0.46, 17, 80, 0.68, 92),
    ('lux', 'LUX', 'CLEAN WHITE BURN', 960, (220, 236, 255), 'long',
     0.070, 0.54, 15, 94, 0.62, 124),
    ('vent', 'VENT', 'SLOTTED FIN CAN', 400, (150, 230, 220), 'fin',
     0.090, 0.36, 22, 98, 1.10, 64),
    ('blast', 'BLAST', 'BIG BORE BELL', 1120, (255, 190, 130), 'bell',
     0.120, 0.48, 36, 126, 1.30, 100),
    ('spur', 'SPUR', 'SHORT SPUR JET', 380, (255, 196, 132), 'ram',
     0.064, 0.34, 14, 86, 0.66, 68),
    ('mite', 'MITE', 'TINY JET PAIR', 200, TEAL, 'twin',
     0.054, 0.26, 9, 64, 0.55, 52),
    ('haze', 'HAZE', 'ION MIST DRIVE', 1080, GLASS, 'bell',
     0.098, 0.46, 24, 100, 0.80, 128),
    ('spike', 'SPIKE', 'NEEDLE NOZZLE JET', 660, GOLD, 'long',
     0.060, 0.58, 13, 90, 0.60, 116),
    ('dusk', 'DUSK', 'DIM BURN DRIVE', 780, (150, 150, 220), 'ram',
     0.072, 0.52, 18, 96, 0.72, 106),
    ('edf', 'EDF', 'SHROUDED FAN JET', 900, (150, 220, 240), 'ducted',
     0.095, 0.38, 20, 98, 0.70, 88),
))

CATALOG = {'body': BODIES, 'frame': FRAMES, 'rotor': ROTORS, 'motor': MOTORS,
           'wing': WINGS, 'booster': BOOSTERS}
SLOT_ORDER = ('body', 'frame', 'rotor', 'motor', 'wing', 'booster')


# ---------------- economy ----------------
# Prices follow a module's stat value instead of the row it sits on, so the
# long catalog can never hide a cheap part that beats a costly one. The
# starter module of every slot stays free; the rest are ranked by value and
# spread across a per-slot band with a steep top end.
_PRICE_BAND = {'body': (240, 1500), 'frame': (140, 760), 'rotor': (110, 1000),
               'motor': (160, 850), 'wing': (150, 760), 'booster': (140, 820)}


def value_of(slot, entry):
    s = entry['stats']
    if slot == 'body':
        return (s['agility'] * 40 + s['lift'] * 70 - s['drag'] * 180
                + s['mass'] * 10)
    if slot == 'frame':
        g = entry.get('geo', {})
        return (g.get('reach', 1.0) * 320 + s['agility'] * 22
                - s['drag'] * 210 - s['mass'] * 4)
    if slot == 'rotor':
        return (s['thrust'] * 3.0 - s['mass'] * 4 - s['drag'] * 35
                + s['agility'] * 10)
    if slot == 'motor':
        return (s['thrust'] * 2.2 + s['energy'] * 2.5 - s['mass'] * 5
                - s['drag'] * 150 + s['agility'] * 10)
    if slot == 'wing':
        return (s['lift'] * 12 + s['agility'] * 22 - s['mass'] * 6
                - s['drag'] * 140)
    return (s['thrust'] * 2.0 + s['energy'] * 2.2 - s['mass'] * 4
            - s['drag'] * 140)


def _reprice():
    for slot, items in CATALOG.items():
        lo, hi = _PRICE_BAND[slot]
        rest = sorted(items[1:], key=lambda e: (value_of(slot, e), e['id']))
        n = max(1, len(rest) - 1)
        for i, e in enumerate(rest):
            t = i / n
            e['price'] = int(round((lo + (hi - lo) * t ** 1.55) / 10.0) * 10)
        items[0]['price'] = 0


_reprice()
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
