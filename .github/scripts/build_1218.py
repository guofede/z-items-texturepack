"""Adjust the 1.21.8 copy of the pack (argv[1] = its root folder).

Leather pieces hide the dye by pointing texture.leather_layer_N at an empty PNG and drawing the art in
texture.leather_layer_N_overlay. The CIT Resewn build for 1.21.8 does not draw the overlay, so those pieces were
invisible there. In the 1.21.8 copy the base key gets the art too: if the overlay works it covers the base exactly,
otherwise the base shows (tinted by the leather colour, but visible).
"""
import json
import os
import re
import sys

SKIP = ()                          # befana_helmet too: its overlay is the EMF hat atlas, so it must be on the base

root = sys.argv[1]
changed = 0
for folder, _, files in os.walk(os.path.join(root, 'assets', 'minecraft', 'optifine', 'cit')):
    if any(s in folder for s in SKIP):
        continue
    for name in files:
        if not name.endswith('.properties'):
            continue
        path = os.path.join(folder, name)
        text = open(path, encoding='utf-8').read()
        new = text
        for layer, art in re.findall(r'^texture\.leather_layer_(\d)_overlay=(.+)$', text, re.M):
            new = re.sub(r'^(texture\.leather_layer_%s=)(.*empty.*)$' % layer, lambda m: m.group(1) + art.strip(),
                          new, flags=re.M)
        if new != text:
            open(path, 'w', encoding='utf-8', newline='').write(new)
            changed += 1
            print('1.21.8 leather fix:', os.path.relpath(path, root))
print(changed, 'files changed')

# EMF: 1.21.9+ has one armor model per slot (player_helmet / player_chestplate), 1.21.8 only
# player_outer_armor (helmet + chestplate + boots). Merge the helmet and chestplate jems into it.
cem = os.path.join(root, 'assets', 'minecraft', 'emf', 'cem')
for prefix in ('player', 'player_slim'):
    helmet = os.path.join(cem, prefix + '_helmet.jem')
    chest = os.path.join(cem, prefix + '_chestplate.jem')
    if not (os.path.exists(helmet) and os.path.exists(chest)):
        continue
    h, c = json.load(open(helmet, encoding='utf-8')), json.load(open(chest, encoding='utf-8'))
    parts = {}
    for m in h['models'] + c['models']:
        if m['part'] in parts:                      # shared root: keep one copy, join the submodels
            p = parts[m['part']]
            p['submodels'] = p.get('submodels', []) + m.get('submodels', [])
            p['boxes'] = p.get('boxes', []) + m.get('boxes', [])
            if m.get('animations') and m['animations'] != p.get('animations'):
                p['animations'] = p.get('animations', []) + m['animations']
        else:
            parts[m['part']] = dict(m)
    merged = {'credit': 'zkraft - 1.21.8 outer armor (Befana hat + Eclipse spikes)', 'textureSize': h['textureSize'],
              'models': list(parts.values())}
    out = os.path.join(cem, prefix + '_outer_armor.jem')
    json.dump(merged, open(out, 'w', encoding='utf-8'), indent=1)
    print('EMF 1.21.8:', os.path.relpath(out, root), [m['part'] for m in merged['models']])
