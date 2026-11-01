"""Adjust the 1.21.8 copy of the pack (argv[1] = its root folder).

Leather pieces hide the dye by pointing texture.leather_layer_N at an empty PNG and drawing the art in
texture.leather_layer_N_overlay. The CIT Resewn build for 1.21.8 does not draw the overlay, so those pieces were
invisible there. In the 1.21.8 copy the base key gets the art too: if the overlay works it covers the base exactly,
otherwise the base shows (tinted by the leather colour, but visible).
"""
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
