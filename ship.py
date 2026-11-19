import math

from config import SECTORS
from parts import (SLOT_ORDER, SOCKETS, SOCKET_POS, CATALOG, entry_by_id,
                   unit_stats, chassis_mesh, body_mesh, rotor_pod_mesh,
                   wing_half_mesh, booster_unit_mesh, paint_scheme, value_of)
from render3d import clamp


def _tier_table():
    out = {}
    for slot, items in CATALOG.items():
        vals = [value_of(slot, e) for e in items]
        out[slot] = (min(vals), max(vals))
    return out


_TIERS = _tier_table()


def module_tier(slot, entry):
    lo, hi = _TIERS[slot]
    return clamp((value_of(slot, entry) - lo) / max(1e-6, hi - lo), 0.0, 1.0)


def layout(state):
    """Socket layout. A fresh airframe is empty; legacy states (forge preview,
    old saves) fall back to the flat per-slot selections."""
    b = state.get('build')
    out = {}
    if isinstance(b, dict):
        out['body'] = b.get('body')
        out['frame'] = b.get('frame')
        for slot in ('rotor', 'motor', 'wing', 'booster'):
            src = b.get(slot) if isinstance(b.get(slot), dict) else {}
            out[slot] = {k: src.get(k) for k, _ in SOCKETS[slot]}
    else:
        sel = state.get('selected', {})
        out['body'] = sel.get('body')
        out['frame'] = CATALOG['frame'][0]['id']
        for slot in ('rotor', 'motor', 'wing', 'booster'):
            if slot == 'motor':
                out[slot] = {k: CATALOG['motor'][0]['id']
                             for k, _ in SOCKETS[slot]}
            else:
                out[slot] = {k: sel.get(slot) for k, _ in SOCKETS[slot]}
    return out


def entry_at(state, lay, slot, key):
    if slot in ('body', 'frame'):
        pid = lay.get(slot)
    else:
        pid = lay[slot].get(key)
    if pid is None:
        return None
    return entry_by_id(slot, pid, state.get('custom', ()))


def body_scale(state, lay=None):
    lay = lay or layout(state)
    body = entry_at(state, lay, 'body', 'c')
    if body is None:
        return 1.0, 1.0
    g = body.get('geo', {})
    return g.get('w', 0.54) / 0.54, g.get('l', 1.12) / 1.12


def frame_reach(state, lay=None):
    lay = lay or layout(state)
    frame = entry_at(state, lay, 'frame', 'c')
    if frame is None:
        return 1.0
    return frame.get('geo', {}).get('reach', 1.0)


def socket_world(state, slot, key, fw=None, fl=None):
    if fw is None or fl is None:
        fw, fl = body_scale(state)
    x, z = SOCKET_POS[slot][key]
    if slot in ('rotor', 'motor'):
        r = frame_reach(state)
        x, z = x * r, z * r
    y = 0.18 if slot in ('rotor', 'motor') else (
        0.15 if slot == 'wing' else 0.02)
    return (x * fw, y, z * fl)


def build_ship(state):
    lay = layout(state)
    body = entry_at(state, lay, 'body', 'c')
    if body is None:
        return []
    scheme = paint_scheme(state)
    g = body.get('geo', {})
    w, l = g.get('w', 0.54), g.get('l', 1.12)
    fw, fl = w / 0.54, l / 1.12
    reach = frame_reach(state, lay)
    custom = state.get('custom', ())
    parts = body_mesh(w, l, scheme['hull'], scheme['deck'],
                      g.get('canopy_w', 0.52), g.get('canopy_l', 0.30),
                      scheme['accent'], g.get('style', 'scout'))
    for p in parts:
        p['name'] = 'body:c'

    frame = entry_at(state, lay, 'frame', 'c')
    if frame is not None:
        fg = frame.get('geo', {})
        fs = chassis_mesh(w, l, scheme['accent'],
                          reach=fg.get('reach', 1.0),
                          col=fg.get('col', (36, 54, 82)),
                          style=fg.get('style', 'spar'))
        for p in fs:
            p['name'] = 'frame:c'
        parts.extend(fs)

    for key, _ in SOCKETS['rotor']:
        eid = lay['rotor'].get(key)
        if eid is None:
            continue
        entry = entry_by_id('rotor', eid, custom)
        mid = lay['motor'].get(key)
        motor = entry_by_id('motor', mid, custom) if mid else None
        px, pz = SOCKET_POS['rotor'][key]
        ps = rotor_pod_mesh(entry['params'],
                            (px * fw * reach, pz * fl * reach),
                            motor=motor, paint=scheme['blade'])
        for p in ps:
            p['name'] = 'rotor:' + key
        parts.extend(ps)

    for slot in ('wing', 'booster'):
        for key, _ in SOCKETS[slot]:
            eid = lay[slot].get(key)
            if eid is None:
                continue
            entry = entry_by_id(slot, eid, custom)
            if slot == 'wing':
                ps = wing_half_mesh(entry['geo'], SOCKET_POS[slot][key][0],
                                    color=scheme['hull'],
                                    trim=scheme['accent'])
            else:
                ps = booster_unit_mesh(entry['geo'], SOCKET_POS[slot][key][0],
                                       z0=-0.24 * fl,
                                       accent=scheme['accent'])
            for p in ps:
                p['name'] = '{}:{}'.format(slot, key)
            parts.extend(ps)
    return parts


def compute_stats(state):
    lay = layout(state)
    total = {'mass': 0.0, 'thrust': 0.0, 'drag': 0.0, 'lift': 0.0,
             'agility': 0.0, 'energy': 0.0}
    fw, fl = body_scale(state, lay)
    reach = frame_reach(state, lay)
    units = {}
    mass_x = 0.0
    rotor_mass_z = 0.0
    rotor_thrust = rotor_x = rotor_z = 0.0
    count = {slot: 0 for slot in SLOT_ORDER}
    powered = 0
    for slot in SLOT_ORDER:
        if slot in ('body', 'frame'):
            entries = (('c', entry_at(state, lay, slot, 'c')),)
        else:
            entries = tuple((k, entry_at(state, lay, slot, k))
                            for k, _ in SOCKETS[slot])
        for key, entry in entries:
            if entry is None:
                continue
            us = unit_stats(entry)
            units[(slot, key)] = us
            live = 1.0
            if slot == 'rotor' and not lay['motor'].get(key):
                live = 0.25
            elif slot == 'rotor':
                # a small drive on a big rotor loses blade speed
                dg = (module_tier('rotor', entry)
                      - module_tier('motor', entry_at(state, lay, 'motor', key)))
                if dg > 0.0:
                    live *= clamp(1.0 - dg * 0.45, 0.55, 1.0)
            if slot == 'motor' and not lay['rotor'].get(key):
                live = 0.0
            if live > 0.0:
                total['thrust'] += us.get('thrust', 0.0) * live
                total['energy'] += us.get('energy', 0.0) * live
            total['mass'] += us.get('mass', 0.0)
            total['drag'] += us.get('drag', 0.0)
            total['lift'] += us.get('lift', 0.0)
            total['agility'] += us.get('agility', 0.0)
            if slot in ('body', 'frame'):
                px = pz = 0.0
            else:
                px = SOCKET_POS[slot][key][0] * fw
                pz = SOCKET_POS[slot][key][1] * fl
                if slot in ('rotor', 'motor'):
                    px, pz = px * reach, pz * reach
                count[slot] += 1
            mass_x += us['mass'] * px
            if slot == 'rotor':
                rotor_mass_z += us['mass'] * pz
                rotor_thrust += us['thrust'] * live
                rotor_x += us['thrust'] * live * px
                rotor_z += us['thrust'] * live * pz
                if lay['motor'].get(key):
                    powered += 1

    mass = 60.0 + total['mass']
    thrust = max(1.0, total['thrust'])
    drag = max(0.6, total['drag'])
    top = 5.0 + 5.2 * math.sqrt(thrust / (drag + 0.08 * mass))
    cog_x = mass_x / mass
    cog_z = rotor_mass_z / mass
    tbx = rotor_x / rotor_thrust if rotor_thrust > 0.5 else 0.0
    tbz = rotor_z / rotor_thrust if rotor_thrust > 0.5 else 0.0

    # Mirrored pairs should match; odd counts or mismatched parts on one side
    # are what actually make a build pull to one side.
    def pair_pen(a, b):
        ua, ub = units.get(a), units.get(b)
        if ua is None and ub is None:
            return 0.0
        if ua is None or ub is None:
            return 14.0
        pen = 0.0
        for k, w in (('thrust', 10.0), ('lift', 7.0), ('mass', 8.0)):
            va, vb = ua.get(k, 0.0), ub.get(k, 0.0)
            den = abs(va) + abs(vb)
            if den > 1e-6:
                pen += abs(va - vb) / den * w
        return pen

    symmetry = (pair_pen(('rotor', 'fl'), ('rotor', 'fr'))
                + pair_pen(('rotor', 'rl'), ('rotor', 'rr'))
                + pair_pen(('motor', 'fl'), ('motor', 'fr'))
                + pair_pen(('motor', 'rl'), ('motor', 'rr'))
                + pair_pen(('wing', 'l'), ('wing', 'r'))
                + pair_pen(('booster', 'l'), ('booster', 'r')))
    imbalance = (abs(cog_x) * 1.15 + abs(tbx)
                 + abs(cog_z) * 0.75 + abs(tbz) * 0.55)
    balance = clamp(100.0 - imbalance * 130.0 - symmetry, 0.0, 100.0)
    agi = clamp(30.0 + 1.5 * total['lift'] + total['agility']
                - 0.12 * mass - (100.0 - balance) * 0.12, 5.0, 100.0)
    hull_ok = entry_at(state, lay, 'body', 'c') is not None
    frame_ok = entry_at(state, lay, 'frame', 'c') is not None

    # ---- compatibility ----------
    # Not every module belongs on every airframe. Three mismatches are
    # modelled: discs that overlap, a rotor outrunning its drive, and a heavy
    # hull sitting on a light spar. Each one costs performance first and can
    # bring the craft down when it is severe.
    drive_gap = 0.0
    max_span = 0.0
    for key, _ in SOCKETS['rotor']:
        rotor = entry_at(state, lay, 'rotor', key)
        motor = entry_at(state, lay, 'motor', key)
        if rotor is not None:
            max_span = max(max_span, rotor.get('params', {}).get('span', 0.32))
            if motor is not None:
                drive_gap = max(drive_gap, module_tier('rotor', rotor)
                                - module_tier('motor', motor))
    body_e = entry_at(state, lay, 'body', 'c')
    frame_e = entry_at(state, lay, 'frame', 'c')
    load = 0.0
    if body_e is not None and frame_e is not None:
        load = body_e['stats']['mass'] / max(1.0, frame_e['stats']['mass'])
    margin = min(1.44 * fw * reach, 1.20 * fl * reach) - 2.0 * max_span

    risk = 0.0
    fault = None
    if count['rotor']:
        if margin < 0.05:
            risk += 0.45 + max(0.0, 0.05 - margin) * 5.0
            if margin < 0.0:
                fault = ('BLADE CLASH', 1.0)
        if drive_gap > 0.28:
            risk += min(0.9, (drive_gap - 0.28) * 1.7)
            if drive_gap > 0.50 and fault is None:
                fault = ('DRIVE STALL', clamp((drive_gap - 0.5) / 0.4, 0.0, 1.0))
    if load > 5.5:
        risk += min(0.9, (load - 5.5) * 0.11)
        if load > 7.5 and fault is None:
            fault = ('FRAME SNAP', 1.0)
    if balance < 42.0:
        risk += min(0.8, (42.0 - balance) * 0.02)
        if balance < 25.0 and fault is None:
            fault = ('TRIM FAILURE', clamp((42.0 - balance) / 40.0, 0.0, 1.0))
    risk = clamp(risk, 0.0, 1.6)

    return {
        'mass': round(mass, 1),
        'thrust': round(thrust, 1),
        'drag': round(drag, 2),
        'lift': round(total['lift'], 1),
        'top': round(top, 2),
        'agility': round(agi, 1),
        'energy': round(max(30.0, total['energy']), 1),
        'kmh': int(round(top * 8.4)),
        'rotors': count['rotor'],
        'motors': count['motor'],
        'powered': powered,
        'wings': count['wing'],
        'boosters': count['booster'],
        'hull': hull_ok,
        'frame': frame_ok,
        'cog_x': round(cog_x, 3),
        'cog_z': round(cog_z, 3),
        'balance': round(balance, 1),
        'bias_x': round(clamp(-(cog_x * 1.8 + tbx * 1.5), -0.9, 0.9), 3),
        'bias_y': round(clamp(-(cog_z * 5.0 + tbz * 1.0), -0.6, 0.6), 3),
        'risk': round(risk, 2),
        'fault': fault,
        'airworthy': bool(hull_ok and frame_ok and count['rotor'] >= 3
                          and powered >= 3),
    }


def ship_for_sector(state):
    return compute_stats(state), SECTORS[max(0, min(2, int(state.get('sector', 0))))]
