import math
import numpy as np
import pygame

from config import BG_MID, DARKM, TEAL, CYAN

CAMP = 9.0
LIGHT = np.array([0.42, 0.72, 0.55], float)
LIGHT /= np.linalg.norm(LIGHT)
RIM = np.array([-0.78, 0.10, -0.62], float)
RIM /= np.linalg.norm(RIM)


def mix(c1, c2, a):
    a = max(0.0, min(1.0, a))
    return (int(c1[0] * a + c2[0] * (1 - a)),
            int(c1[1] * a + c2[1] * (1 - a)),
            int(c1[2] * a + c2[2] * (1 - a)))


def clamp(x, a=0.0, b=1.0):
    return a if x < a else (b if x > b else x)


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 2


# ---------------- primitives ----------------
def circ(r, cu, cv, n=28):
    return [(cu + r * math.cos(2 * math.pi * i / n),
             cv + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rrect(w, h, r, n=5):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def shift(poly, du, dv):
    return [(u + du, v + dv) for u, v in poly]


def extrude(poly2d, axis, h0, h1):
    if axis == 'y':
        lo = [(u, h0, v) for u, v in poly2d]
        hi = [(u, h1, v) for u, v in poly2d]
    else:
        lo = [(u, v, h0) for u, v in poly2d]
        hi = [(u, v, h1) for u, v in poly2d]
    faces = [lo, hi]
    n = len(poly2d)
    for i in range(n):
        j = (i + 1) % n
        faces.append([lo[i], lo[j], hi[j], hi[i]])
    return faces


def make_part(name, faces, color, accent=TEAL, em=0.0, spin=False,
              face_colors=None, ctr=None, no_edge=False, closed=True):
    if ctr is None:
        vs = [v for f in faces for v in f]
        ctr = (sum(v[0] for v in vs) / len(vs), sum(v[1] for v in vs) / len(vs),
               sum(v[2] for v in vs) / len(vs))
    verts = []
    idx = []
    for f in faces:
        start = len(verts)
        verts.extend(f)
        idx.append(list(range(start, len(verts))))
    V = np.array(verts, float)
    lengths = np.array([len(i) for i in idx], int)
    starts = np.concatenate(([0], np.cumsum(lengths)[:-1]))
    normals = []
    cn = np.array(ctr, float)
    for i in idx:
        a = V[i[1]] - V[i[0]]
        b = V[i[2]] - V[i[0]]
        n = np.cross(a, b)
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            normals.append((0.0, 0.0, 1.0))
            continue
        n = n / ln
        if closed and np.dot(n, V[i].mean(axis=0) - cn) < 0:
            n = -n
        normals.append(n)
    return {
        'name': name, 'faces': faces, 'color': color, 'accent': accent,
        'em': em, 'spin': spin, 'ctr': ctr, 'face_colors': face_colors,
        'no_edge': no_edge, 'cull': closed,
        'rad': float(np.max(np.hypot(V[:, 0] - ctr[0], V[:, 2] - ctr[2]))),
        '_v': V, '_i': [np.array(i, int) for i in idx],
        '_starts': starts, '_counts': lengths,
        '_n': np.array(normals, float),
    }


# ---------------- camera ----------------
def make_cam(yaw, pitch, roll, scale, cx, cy, pos=(0.0, 0.0, 0.0)):
    return {'yaw': yaw, 'pitch': pitch, 'roll': roll, 'scale': scale,
            'cx': cx, 'cy': cy, 'tx': pos[0], 'ty': pos[1], 'tz': pos[2],
            'camp': CAMP}


def cam_matrix(cam):
    cr, sr = math.cos(cam['roll']), math.sin(cam['roll'])
    cp, sp = math.cos(cam['pitch']), math.sin(cam['pitch'])
    cy, sy = math.cos(cam['yaw']), math.sin(cam['yaw'])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], float)
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]], float)
    rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]], float)
    return ry @ rx @ rz


def cam_rot(cam, p):
    x, y, z = p[0] - cam['tx'], p[1] - cam['ty'], p[2] - cam['tz']
    cr, sr = math.cos(cam['roll']), math.sin(cam['roll'])
    x, y = x * cr - y * sr, x * sr + y * cr
    cp, sp = math.cos(cam['pitch']), math.sin(cam['pitch'])
    y, z = y * cp - z * sp, y * sp + z * cp
    cy, sy = math.cos(cam['yaw']), math.sin(cam['yaw'])
    x, z = cy * x + sy * z, -sy * x + cy * z
    return x, y, z


def cam_proj(cam, p):
    x, y, z = cam_rot(cam, p)
    dep = cam['camp'] - z
    if dep < 0.6:
        return None, dep
    f = cam['scale'] * cam['camp'] / dep
    return (cam['cx'] + x * f, cam['cy'] - y * f), dep


def band_shade(n):
    d_ = abs(float(np.dot(n, LIGHT)))
    if d_ > 0.82:
        return 1.10
    if d_ > 0.56:
        return 0.94
    if d_ > 0.28:
        return 0.74
    return 0.54


# ---------------- glow ----------------
_GLOW_CACHE = {}
_GLOW_N = 96


def _glow_base(col):
    n = _GLOW_N
    ys, xs = np.mgrid[0:n, 0:n].astype(float)
    d = np.sqrt((xs - n / 2 + 0.5) ** 2 + (ys - n / 2 + 0.5) ** 2) / (n / 2)
    a = np.clip(1.0 - d, 0, 1) ** 2.3
    rgb = np.stack([a * col[0], a * col[1], a * col[2]], -1)
    data = np.ascontiguousarray(np.clip(rgb, 0, 255), dtype=np.uint8)
    surf = pygame.image.frombuffer(data.tobytes(), (n, n), 'RGB')
    try:
        surf = surf.convert()
    except pygame.error:
        pass
    return surf


def draw_glow(dst, x, y, radius, col, strength):
    if strength <= 0.02 or radius <= 1:
        return
    strength = round(clamp(strength), 2)
    radius = max(4, int(round(radius / 6.0)) * 6)
    col = tuple(int(c * strength) for c in col)
    key = (col, radius)
    spr = _GLOW_CACHE.get(key)
    if spr is None:
        base = _glow_base(col)
        spr = pygame.transform.smoothscale(base, (radius, radius))
        if len(_GLOW_CACHE) > 900:
            _GLOW_CACHE.clear()
        _GLOW_CACHE[key] = spr
    dst.blit(spr, (int(x - radius / 2), int(y - radius / 2)),
             special_flags=pygame.BLEND_RGB_ADD)


# ---------------- model ----------------
_ALPHA_CACHE = {}


def fill_alpha_poly(dst, pts, col, alpha):
    if alpha <= 0.01 or len(pts) < 3:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = min(xs), min(ys)
    w = int(max(xs) - x0) + 3
    h = int(max(ys) - y0) + 3
    if w < 2 or h < 2 or w > 900 or h > 700:
        return
    bw = (w + 15) // 16 * 16
    bh = (h + 15) // 16 * 16
    surf = _ALPHA_CACHE.get((bw, bh))
    if surf is None:
        if len(_ALPHA_CACHE) > 48:
            _ALPHA_CACHE.clear()
        surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
        _ALPHA_CACHE[(bw, bh)] = surf
    surf.fill((0, 0, 0, 0))
    local = [(x - x0 + 1.0, y - y0 + 1.0) for x, y in pts]
    pygame.draw.polygon(surf, (int(col[0]), int(col[1]), int(col[2]),
                               int(alpha * 255)), local)
    dst.blit(surf, (int(x0) - 1, int(y0) - 1))


_PART_BATCH = {}
_BATCH_LIMIT = 8


def _part_batch(parts):
    """Pack a parts list into flat arrays once, so each frame is a handful of
    vector ops instead of one numpy pass per part."""
    key = id(parts)
    ent = _PART_BATCH.get(key)
    if ent is not None and ent[0] is parts:
        return ent[1]

    vs, vpart, fstart, fcount, nrm, fpart = [], [], [], [], [], []
    base, fem, facc = [], [], []
    ctrs, cols, rads = [], [], []
    spins, culls, noes, names = [], [], [], []
    off = 0
    for pi, p in enumerate(parts):
        V = p['_v']
        vs.append(V)
        vpart.append(np.full(len(V), pi, np.int32))
        fstart.append(p['_starts'] + off)
        fcount.append(p['_counts'])
        nrm.append(p['_n'])
        nf = len(p['_i'])
        fpart.append(np.full(nf, pi, np.int32))
        fc = p['face_colors']
        if fc is not None:
            base.append(np.asarray(fc, float))
        else:
            b = np.empty((nf, 3), float)
            b[:] = p['color']
            base.append(b)
        fem.append(np.full(nf, float(p['em'])))
        facc.append(np.full((nf, 3), p['accent'], float))
        ctrs.append(p['ctr'])
        cols.append(p['color'])
        rads.append(p['rad'])
        spins.append(bool(p['spin']))
        culls.append(bool(p['cull']))
        noes.append(bool(p['no_edge']))
        names.append(p['name'])
        off += len(V)

    if not vs:
        return None

    data = {
        'V': np.concatenate(vs, axis=0),
        'vpart': np.concatenate(vpart),
        'fstart': np.concatenate(fstart),
        'fcount': np.concatenate(fcount),
        'N': np.concatenate(nrm, axis=0),
        'fpart': np.concatenate(fpart),
        'base': np.concatenate(base, axis=0),
        'fem': np.concatenate(fem),
        'facc': np.concatenate(facc, axis=0),
        'ctr': np.array(ctrs, float),
        'color': np.array(cols, float),
        'rad': np.array(rads, float),
        'spin': np.array(spins, bool),
        'cull': np.array(culls, bool),
        'noedge': np.array(noes, bool),
        'names': names,
    }
    if len(_PART_BATCH) >= _BATCH_LIMIT:
        _PART_BATCH.pop(next(iter(_PART_BATCH)))
    _PART_BATCH[key] = (parts, data)
    return data


def draw_parts(dst, cam, parts, vis=None, spin=0.0, pulse=1.0,
               ghost=0.0, spin_mult=1.0, offset=(0.0, 0.0, 0.0), tilt=None,
               blur=0.0):
    b = _part_batch(parts)
    if b is None:
        return
    vis = vis or {}
    M = cam_matrix(cam)
    camp = cam['camp']
    scale = cam['scale']
    cx, cy = cam['cx'], cam['cy']
    ox, oy, oz = offset
    Rt = None
    if tilt:
        tp, tr = tilt
        cp, sp = math.cos(tp), math.sin(tp)
        cr, sr = math.cos(tr), math.sin(tr)
        Rt = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]], float) @ \
            np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]], float)

    names = b['names']
    nparts = len(names)
    ap = np.fromiter((vis.get(nm, 1.0) for nm in names), float, nparts)
    active = ap > 0.004
    if not active.any():
        return
    ap = np.clip(ap, 0.0, 1.0)
    sc_p = 0.84 + 0.16 * (1.0 - (1.0 - ap) ** 3)
    dy_p = (1.0 - ap) * 0.22

    ang_p = np.zeros(nparts)
    if spin and spin_mult:
        ang_p[b['spin']] = spin * spin_mult
        cs_p = np.cos(ang_p)
        sn_p = np.sin(ang_p)
    else:
        cs_p = sn_p = None

    V_all = b['V']
    vpart = b['vpart']
    ctr = b['ctr']
    V = (V_all - ctr[vpart]) * sc_p[vpart][:, None] + ctr[vpart]
    if cs_p is not None:
        cs_v = cs_p[vpart]
        sn_v = sn_p[vpart]
        ctr_v = ctr[vpart]
        dx = V[:, 0] - ctr_v[:, 0]
        dz = V[:, 2] - ctr_v[:, 2]
        V[:, 0] = ctr_v[:, 0] + dx * cs_v - dz * sn_v
        V[:, 2] = ctr_v[:, 2] + dx * sn_v + dz * cs_v
    if Rt is not None:
        V = V @ Rt.T
    V[:, 0] += ox
    V[:, 1] += oy + dy_p[vpart]
    V[:, 2] += oz

    tvec = np.array([cam['tx'], cam['ty'], cam['tz']], float)
    Vc = (V - tvec) @ M.T
    dep_v = camp - Vc[:, 2]
    keep = dep_v >= 0.7
    f = scale * camp / np.maximum(dep_v, 0.7)
    px = cx + Vc[:, 0] * f
    py = cy - Vc[:, 1] * f
    pxl, pyl = px.tolist(), py.tolist()

    fstart = b['fstart']
    fcount = b['fcount']
    fpart = b['fpart']
    face_dep = np.add.reduceat(dep_v, fstart) / fcount
    ok = None
    if not keep.all():
        ok = np.add.reduceat(keep.astype(np.int32), fstart) == fcount

    N = b['N']
    if cs_p is not None:
        cs_f = cs_p[fpart]
        sn_f = sn_p[fpart]
        Nr = np.empty_like(N)
        Nr[:, 0] = N[:, 0] * cs_f - N[:, 2] * sn_f
        Nr[:, 1] = N[:, 1]
        Nr[:, 2] = N[:, 0] * sn_f + N[:, 2] * cs_f
        N = Nr
    if Rt is not None:
        N = N @ Rt.T
    Nc = N @ M.T

    cen = np.add.reduceat(Vc, fstart, axis=0) / fcount[:, None]
    cull_f = b['cull'][fpart]
    facing = np.ones(len(fstart), bool)
    if cull_f.any():
        fr = (Nc[:, 2] * (camp - cen[:, 2]) - Nc[:, 0] * cen[:, 0]
              - Nc[:, 1] * cen[:, 1]) > 0.0
        facing[cull_f] = fr[cull_f]

    # Smooth lambert + view-dependent rim and a tight specular lobe.
    Lc = LIGHT @ M.T
    Lc = Lc / max(1e-6, float(np.linalg.norm(Lc)))
    vx_ = -cen[:, 0]
    vy_ = -cen[:, 1]
    vz_ = camp - cen[:, 2]
    vn_ = np.sqrt(vx_ * vx_ + vy_ * vy_ + vz_ * vz_) + 1e-6
    ndl = Nc[:, 0] * Lc[0] + Nc[:, 1] * Lc[1] + Nc[:, 2] * Lc[2]
    lam = 0.36 + 0.64 * np.clip(ndl, 0, 1) + 0.09 * np.clip(-Nc[:, 1], 0, 1)
    hx_ = Lc[0] + vx_ / vn_
    hy_ = Lc[1] + vy_ / vn_
    hz_ = Lc[2] + vz_ / vn_
    hn_ = np.sqrt(hx_ * hx_ + hy_ * hy_ + hz_ * hz_) + 1e-6
    ndh = (Nc[:, 0] * hx_ + Nc[:, 1] * hy_ + Nc[:, 2] * hz_) / hn_
    spc = np.clip(ndh, 0, 1) ** 26.0
    ndv = (Nc[:, 0] * vx_ + Nc[:, 1] * vy_ + Nc[:, 2] * vz_) / vn_
    rimm = np.clip(1.0 - np.abs(ndv), 0, 1) ** 2.2
    bnc = np.clip(-Nc[:, 1], 0, 1)

    add = np.empty((len(fstart), 3), float)
    add[:, 0] = spc * 30.0 + rimm * 12.6 + bnc * 9.0
    add[:, 1] = spc * 30.0 + rimm * 18.0 + bnc * 14.0
    add[:, 2] = spc * 30.0 + rimm * 27.0 + bnc * 21.0
    c_arr = np.clip(b['base'] * lam[:, None] + add, 0, 255)
    fem = b['fem']
    if (fem > 0.0).any():
        k = (0.55 * np.clip(fem * pulse, 0, 1))[:, None]
        c_arr = c_arr * (1 - k) + b['facc'] * k
    ap_f = ap[fpart]
    if (ap_f < 0.999).any():
        m = np.array(BG_MID, float)
        c_arr = c_arr * ap_f[:, None] + m * (1 - ap_f[:, None])
    if isinstance(ghost, dict):
        gp = np.fromiter((ghost.get(nm, 0.0) for nm in names), float, nparts)
    else:
        gp = np.full(nparts, float(ghost))
    gp_f = gp[fpart]
    if (gp_f > 0.0).any():
        g = np.clip(gp_f * 1.15, 0, 1)[:, None]
        c_arr = np.array((26, 66, 96), float) * (1 - g) + c_arr * g
    cols = c_arr.astype(np.uint8).tolist()
    dark = np.array(DARKM, float)
    edge_arr = c_arr * 0.42 + dark * 0.58
    hi = gp > 0.5
    if hi.any():
        sel = hi[fpart]
        cue = np.array((64, 168, 214), float)
        edge_arr[sel] = cue * 0.55 + c_arr[sel] * 0.45
    edges = edge_arr.astype(np.uint8).tolist()

    items = []
    if blur > 0.0 and cs_p is not None:
        glow_parts = np.nonzero(b['spin'] & active)[0]
        for pi in glow_parts:
            c0 = ctr[pi]
            rad = b['rad'][pi]
            s_p = sc_p[pi]
            ring_ang = np.arange(20) * (2 * math.pi / 20)
            D = np.empty((20, 3), float)
            D[:, 0] = c0[0] + rad * np.cos(ring_ang) * s_p
            D[:, 1] = c0[1]
            D[:, 2] = c0[2] + rad * np.sin(ring_ang) * s_p
            if Rt is not None:
                D = D @ Rt.T
            D[:, 0] += ox
            D[:, 1] += oy + dy_p[pi]
            D[:, 2] += oz
            Dc = (D - tvec) @ M.T
            dd = camp - Dc[:, 2]
            if dd.min() < 0.7:
                continue
            ds = scale * camp / dd
            # just in front of every blade face: the wash mutes crisp spokes
            dep = min(float(dd.mean()) - 0.05,
                      float(face_dep[fpart == pi].min()) - 0.05)
            items.append((dep, -1,
                          [(float(cx + Dc[i, 0] * ds[i]),
                            float(cy - Dc[i, 1] * ds[i])) for i in range(20)],
                          mix(tuple(b['color'][pi].astype(int)), (255, 232, 170), 0.45),
                          0.48 * clamp(blur)))

    draw_ok = active[fpart] & facing & (face_dep >= 0.75)
    if ok is not None:
        draw_ok &= ok
    dep_l = face_dep.tolist()
    ok_l = draw_ok.tolist()
    for fi in range(len(dep_l)):
        if ok_l[fi]:
            items.append((dep_l[fi], fi, None, None, None))

    items.sort(key=lambda z: -z[0])
    fs_l = fstart.tolist()
    fc_l = fcount.tolist()
    noedge_l = b['noedge'][fpart].tolist()
    for dep, fi, ring, wcol, walpha in items:
        if fi < 0:
            fill_alpha_poly(dst, ring, wcol, walpha)
            continue
        s = fs_l[fi]
        e = s + fc_l[fi]
        pts = list(zip(pxl[s:e], pyl[s:e]))
        pygame.draw.polygon(dst, cols[fi], pts)
        if not noedge_l[fi]:
            pygame.draw.lines(dst, edges[fi], True, pts, 1)


def draw_model_glow(dst, cam, parts, vis, pulse=1.0, flame=0.0):
    vis = vis or {}
    if flame > 0.02:
        for s in (1, -1):
            pt, _ = cam_proj(cam, (s * 0.32, -0.03, -0.76))
            if pt:
                draw_glow(dst, pt[0], pt[1], 44 * flame + 10, TEAL, 0.55 * flame)
    for p in parts:
        if p['em'] < 0.5 or vis.get(p['name'], 1.0) <= 0.05:
            continue
        pt, _ = cam_proj(cam, p['ctr'])
        if pt:
            r = 30 if p['em'] > 0.8 else 40
            st = round(0.4 * vis.get(p['name'], 1.0) * pulse, 1)
            draw_glow(dst, pt[0], pt[1], r, p['accent'], st)


# ---------------- floor ----------------
def draw_floor(dst, cam, pad=0.0, t=0.0, fade=1.0, y=-0.62,
               x_max=7.0, z0=-6.0, z1=5.0, line_col=(88, 138, 196)):
    if fade <= 0.01:
        return
    for k in range(int(z0), int(z1) + 1):
        s0, _ = cam_proj(cam, (-x_max, y, k))
        s1, _ = cam_proj(cam, (x_max, y, k))
        if s0 is None or s1 is None:
            continue
        a = clamp((z1 - k) / 8.0) * 0.5 * fade
        pygame.draw.line(dst, mix(line_col, BG_MID, a),
                         (int(s0[0]), int(s0[1])), (int(s1[0]), int(s1[1])), 1)
    for k in range(-7, 8):
        s0, _ = cam_proj(cam, (k, y, z0))
        s1, _ = cam_proj(cam, (k, y, z1))
        if s0 is None or s1 is None:
            continue
        pygame.draw.line(dst, mix(line_col, BG_MID, 0.42 * fade),
                         (int(s0[0]), int(s0[1])), (int(s1[0]), int(s1[1])), 1)

    if pad <= 0:
        return
    n = 64
    for rad, col, w in ((1.52, mix(TEAL, BG_MID, 0.30 * pad), 2),
                        (1.36, mix(CYAN, BG_MID, 0.14 * pad), 1)):
        pts = []
        ok = True
        for i in range(n):
            a = 2 * math.pi * i / n
            q, _ = cam_proj(cam, (rad * math.cos(a), y + 0.002, rad * math.sin(a)))
            if q is None:
                ok = False
                break
            pts.append((q[0], q[1]))
        if not ok:
            continue
        if rad > 1.4:
            pygame.draw.polygon(dst, mix((23, 37, 62), BG_MID, 0.95 * pad), pts)
        pygame.draw.lines(dst, col, True, pts, w)

    for i in range(48):
        a = 2 * math.pi * i / 48
        r0 = 1.30 if i % 6 == 0 else (1.40 if i % 2 == 0 else 1.44)
        q0, _ = cam_proj(cam, (r0 * math.cos(a), y + 0.002, r0 * math.sin(a)))
        q1, _ = cam_proj(cam, (1.52 * math.cos(a), y + 0.002, 1.52 * math.sin(a)))
        if q0 is None or q1 is None:
            continue
        c = mix(TEAL, BG_MID, (0.55 if i % 6 == 0 else 0.30) * pad)
        pygame.draw.line(dst, c, q0, q1, 1)

    ang0 = (t * 1.45) % (2 * math.pi)
    arc = []
    for i in range(15):
        a = ang0 + 0.85 * i / 14
        q, _ = cam_proj(cam, (1.585 * math.cos(a), y + 0.003, 1.585 * math.sin(a)))
        if q is not None:
            arc.append(q)
    if len(arc) > 2:
        pygame.draw.lines(dst, mix(TEAL, BG_MID, 0.85 * pad), False, arc, 2)
        draw_glow(dst, arc[-1][0], arc[-1][1], 30, TEAL, 0.55 * pad)


def draw_shadow(dst, cam, r=0.95, a=1.0, y=-0.615):
    q, _ = cam_proj(cam, (0.0, y, 0.0))
    if q is None:
        return
    for i, f in enumerate((1.0, 0.78, 0.56, 0.34)):
        c = mix((8, 13, 24), (28, 42, 66), 0.25 + 0.5 * (1 - f))
        w = 155 * f * (r / 0.95)
        h = 42 * f * (r / 0.95)
        pygame.draw.ellipse(dst, c, (int(q[0] - w), int(q[1] - h),
                                     int(2 * w), int(2 * h)))


def gradient_bg(w, h, top, bot):
    surf = pygame.Surface((w, h))
    for y in range(h):
        k = y / max(1, h - 1)
        c = mix(bot, top, 1 - k)
        pygame.draw.line(surf, c, (0, y), (w, y))
    return surf


_VIGNETTE = {}


def vignette(w, h, strength=0.5):
    """Cached multiply-map for the 3D layer. Cheaper than an alpha overlay
    at full window size and keeps the eye on the ship."""
    key = (w, h, round(strength, 2))
    s = _VIGNETTE.get(key)
    if s is not None:
        return s
    ys, xs = np.mgrid[0:h, 0:w].astype(float)
    nx = (xs - w / 2) / (w / 2)
    ny = (ys - h / 2) / (h / 2)
    d = np.sqrt(nx * nx + ny * ny) / math.sqrt(2.0)
    k = np.clip((d - 0.40) / 0.60, 0, 1) ** 1.7
    v = (255.0 - k * 255.0 * strength).astype(np.uint8)
    rgb = np.dstack([v, v, v])
    surf = pygame.image.frombuffer(
        np.ascontiguousarray(rgb).tobytes(), (w, h), 'RGB')
    try:
        surf = surf.convert()
    except pygame.error:
        pass
    _VIGNETTE[key] = surf
    return surf
