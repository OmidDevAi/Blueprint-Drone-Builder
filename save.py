import json
import os

from config import SAVE_PATH, START_CREDITS, GOLD, PAINTS
from parts import CATALOG, SOCKETS

PAINT_IDS = {p['id'] for p in PAINTS}


def empty_build():
    build = {'body': None, 'frame': None}
    for slot in ('rotor', 'motor', 'wing', 'booster'):
        build[slot] = {k: None for k, _ in SOCKETS[slot]}
    return build


def _slot_ids(slot, customs=()):
    ids = {e['id'] for e in CATALOG[slot]}
    if slot == 'rotor':
        ids |= {e['id'] for e in customs}
    return ids


def _valid_id(pid, customs, slot=None):
    if not isinstance(pid, str):
        return False
    if slot is not None:
        return pid in _slot_ids(slot, customs)
    return any(pid in _slot_ids(s) for s in CATALOG) or any(
        e['id'] == pid for e in customs)


def default_state():
    return {
        'version': 4,
        'credits': START_CREDITS,
        'owned': ['body_scout', 'frame_std', 'rotor_std', 'motor_std',
                  'wing_std', 'boost_std'],
        'selected': {'body': 'body_scout', 'rotor': 'rotor_std',
                     'wing': 'wing_std', 'booster': 'boost_std'},
        'build': empty_build(),
        'paint': 'factory',
        'custom': [],
        'unlocked': [0],
        'sector': 0,
        'best': {},
        'cleared': {},
        'finished': False,
        'mute': False,
    }


def _derive_build(st):
    """Preview build for states without a socket build (forge preview)."""
    sel = st.get('selected', {})
    fallback = {slot: CATALOG[slot][0]['id'] for slot in CATALOG}
    body = sel.get('body') if _valid_id(sel.get('body'), (), 'body') \
        else fallback['body']
    out = {'body': body, 'frame': fallback['frame']}
    for slot in ('rotor', 'motor', 'wing', 'booster'):
        pid = sel.get(slot)
        if not _valid_id(pid, (), slot):
            pid = fallback[slot]
        out[slot] = {k: pid for k, _ in SOCKETS[slot]}
    return out


def _clean_build(raw, st):
    if not isinstance(raw, dict):
        return _derive_build(st)
    out = empty_build()
    body = raw.get('body')
    out['body'] = body if _valid_id(body, st['custom'], 'body') else None
    frame = raw.get('frame')
    out['frame'] = frame if _valid_id(frame, st['custom'], 'frame') else None
    for slot in ('rotor', 'motor', 'wing', 'booster'):
        src = raw.get(slot)
        src = src if isinstance(src, dict) else {}
        for key, _ in SOCKETS[slot]:
            pid = src.get(key)
            out[slot][key] = pid if _valid_id(pid, st['custom'], slot) else None
    return out


def load_state(path=SAVE_PATH):
    st = default_state()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return st
    if not isinstance(data, dict):
        return st
    for k, v in data.items():
        if k in st:
            st[k] = v
    if not isinstance(st['credits'], int):
        st['credits'] = START_CREDITS
    if not isinstance(st['custom'], list):
        st['custom'] = []
    clean = []
    for e in st['custom']:
        if (not isinstance(e, dict) or e.get('slot') != 'rotor'
                or not isinstance(e.get('params'), dict)
                or not isinstance(e.get('id'), str)):
            continue
        accent = e.get('accent', GOLD)
        if isinstance(accent, list):
            accent = tuple(accent)
        if (not isinstance(accent, tuple) or len(accent) != 3
                or not all(isinstance(c, int) for c in accent)):
            accent = GOLD
        e['accent'] = accent
        if not isinstance(e.get('name'), str):
            e['name'] = 'CUSTOM'
        clean.append(e)
    st['custom'] = clean
    if not isinstance(st['owned'], list):
        st['owned'] = default_state()['owned']
    if not isinstance(st['selected'], dict):
        st['selected'] = default_state()['selected']
    else:
        base = default_state()['selected']
        for slot, eid in base.items():
            if not _valid_id(st['selected'].get(slot), st['custom'], slot):
                st['selected'][slot] = eid
    if st.get('paint') not in PAINT_IDS:
        st['paint'] = 'factory'
    # v4 starts the player on an empty airframe; old saves keep their
    # credits, unlocks and records but rebuild from scratch.
    if int(data.get('version', 0) or 0) < 4:
        st['build'] = empty_build()
    else:
        st['build'] = _clean_build(data.get('build'), st)
    st['version'] = 4
    # Every free catalog part ships with the hangar.
    for slot, entries in CATALOG.items():
        for e in entries:
            if e.get('price', 0) == 0 and e['id'] not in st['owned']:
                st['owned'].append(e['id'])
    installed = [st['build']['body'], st['build']['frame']]
    for slot in ('rotor', 'motor', 'wing', 'booster'):
        installed.extend(st['build'][slot].values())
    for pid in installed:
        if pid and pid not in st['owned'] and not any(
                e['id'] == pid for e in st['custom']):
            st['owned'].append(pid)
    if not isinstance(st['best'], dict):
        st['best'] = {}
    if not isinstance(st['cleared'], dict):
        st['cleared'] = {}
    st['cleared'] = {str(k): v for k, v in st['cleared'].items()
                     if isinstance(v, str) and v in ('B', 'A', 'S')}
    if not isinstance(st['unlocked'], list):
        st['unlocked'] = [0]
    st['unlocked'] = sorted({int(s) for s in st['unlocked'] if isinstance(s, int)})
    if 0 not in st['unlocked']:
        st['unlocked'] = [0] + st['unlocked']
    if not isinstance(st['sector'], int) or st['sector'] not in st['unlocked']:
        st['sector'] = 0
    st['finished'] = bool(st.get('finished', False))
    st['mute'] = bool(st.get('mute', False))
    return st


def save_state(st, path=SAVE_PATH):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(st, f, indent=1)
        os.replace(tmp, path)
        return True
    except Exception:
        return False
