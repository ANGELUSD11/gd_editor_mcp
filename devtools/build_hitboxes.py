"""Builds src/physics/hitboxes.json: the collision box and kind of every object the cube simulator knows.

Hitbox sizes come from the object data of the gdclone project (Geometry Dash 2.1 objects); the kind of each object
(solid, hazard, pad, orb, portal...) is derived from its texture and ID.

Usage: python devtools/build_hitboxes.py [--source PATH_OR_URL]
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True

SOURCE = 'https://raw.githubusercontent.com/Opstic/gdclone/main/assets/data/object.json'
OUT = Path(__file__).resolve().parents[1] / 'src' / 'physics' / 'hitboxes.json'

SOLID_TEXTURES = ('blockOutline', 'lightsquare', 'square', 'plank', 'smallOutline', 'invisibleOutline', 'invis_square',
                  'invis_plank', 'colorPlank', 'colorSquare', 'triangle', 'lighttriangle', 'invis_triangle')
HAZARD_TEXTURES = ('spike', 'invis_spike', 'colorSpike', 'iceSpike', 'pit', 'sawblade', 'darkblade', 'blackCogwheel',
                   'blade', 'lightBlade', 'spinBlade', 'bladeTrap', 'fireball')
BY_ID = {
    35: 'yellow_pad', 140: 'pink_pad', 1332: 'red_pad', 67: 'blue_pad',
    36: 'yellow_orb', 141: 'pink_orb', 1333: 'red_orb', 84: 'blue_orb', 1022: 'green_orb', 1330: 'black_orb',
    1704: 'dash_orb', 1751: 'dash_orb',
    200: 'speed_0.5x', 201: 'speed_1x', 202: 'speed_2x', 203: 'speed_3x', 1334: 'speed_4x',
    12: 'cube_portal', 13: 'portal', 47: 'portal', 111: 'portal', 660: 'portal', 745: 'portal', 1331: 'portal',
    10: 'portal', 11: 'portal', 99: 'portal', 101: 'portal', 45: 'portal', 46: 'portal', 286: 'portal', 287: 'portal',
    34: 'ignore', 1329: 'ignore', 1816: 'ignore',
}


def kind_of(oid: int, texture: str, shape: str) -> str:
    if oid in BY_ID:
        return BY_ID[oid]
    base = re.sub(r'(_\d+)+(_001)?\.png$', '', texture)
    if base.startswith(HAZARD_TEXTURES):
        return 'hazard_slope' if shape == 'Slope' else 'hazard'
    if base.startswith(SOLID_TEXTURES):
        return 'slope' if shape == 'Slope' else 'solid'
    return 'unknown'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', default=SOURCE)
    args = ap.parse_args()
    if re.match(r'https?://', args.source):
        with urllib.request.urlopen(args.source, timeout=60) as r:
            data = json.loads(r.read().decode('utf-8'))
    else:
        data = json.loads(Path(args.source).read_text(encoding='utf-8'))

    table = {}
    for key, obj in sorted(data.items(), key=lambda kv: int(kv[0])):
        hb = obj.get('hitbox')
        if not hb:
            continue
        oid = int(key)
        texture = obj['texture']
        if texture == 'emptyFrame.png' and obj.get('children'):
            texture = obj['children'][0]['texture']
        entry = {'kind': kind_of(oid, texture, hb['type'])}
        if hb['type'] == 'Circle':
            entry.update(shape='circle', r=hb['radius'])
        else:
            entry.update(shape='slope' if hb['type'] == 'Slope' else 'box', w=hb['width'], h=hb['height'],
                         x=hb.get('x', 0.0), y=hb.get('y', 0.0))
        table[str(oid)] = entry

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({'source': args.source, 'objects': table}, indent=0), encoding='utf-8')
    counts = {}
    for e in table.values():
        counts[e['kind']] = counts.get(e['kind'], 0) + 1
    print('%s: %d objects' % (OUT, len(table)))
    for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print('  %-12s %d' % (k, n))


if __name__ == '__main__':
    main()
