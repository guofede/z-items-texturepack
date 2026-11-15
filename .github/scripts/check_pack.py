"""Static checks for the zkraft pack. Changes nothing; exits 1 when something would break in game.

usage: python check_pack.py [ROOT] [--strict]
  ROOT      pack root (default: two folders up from this script)
  --strict  warnings fail too

ERROR   = the item would show the vanilla texture, purple/black, or not load in game.
WARNING = works, but is probably a mistake (orphan file, README missing the item, duplicate name ...).
Python standard library only, so it runs on GitHub Actions without installing anything.
"""
import json
import os
import re
import struct
import sys

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith('--')]
STRICT = '--strict' in sys.argv
ROOT = os.path.abspath(args[0] if args else os.path.join(HERE, '..', '..'))
CIT = os.path.join(ROOT, 'assets', 'minecraft', 'optifine', 'cit')
VANILLA = json.load(open(os.path.join(HERE, 'vanilla_items.json'), encoding='utf-8'))
ITEMS = set(VANILLA['items'])

errors, warnings = [], []
rel = lambda p: os.path.relpath(p, ROOT).replace('\\', '/')
err = lambda p, m: errors.append('%s: %s' % (rel(p), m))
warn = lambda p, m: warnings.append('%s: %s' % (rel(p), m))
used = set()                      # files reached from a .properties (directly or through a model)


def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', head[16:24])


def read_properties(path):
    props, raw = {}, open(path, 'rb').read()
    if raw.startswith(b'\xef\xbb\xbf'):
        err(path, 'UTF-8 BOM at the start: the first key is not read')
    for n, line in enumerate(raw.decode('utf-8', 'replace').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith(('#', '!')):
            continue
        if '=' not in line and ':' not in line:
            err(path, 'line %d has no "=": %r' % (n, line)); continue
        key, value = re.split(r'\s*[=:]\s*', line.strip(), maxsplit=1) if '=' not in line else line.split('=', 1)
        key = key.strip()
        if value != value.rstrip():
            err(path, '%s has trailing spaces (Java keeps them, the file is not found)' % key)
        if key in props:
            err(path, 'key %s is set twice, only the last one counts' % key)
        props[key] = value.strip()
    return props


def resolve(base_dir, value, ext):
    """CIT Resewn/OptiFine path rules: plain name -> next to the .properties; with a slash -> from assets/minecraft."""
    v = value[2:] if value.startswith('./') else value
    if ':' in v:
        ns, v = v.split(':', 1)
        roots = [os.path.join(ROOT, 'assets', ns)]
    else:
        roots = [base_dir, os.path.join(ROOT, 'assets', 'minecraft')]
    if not v.endswith(ext):
        v += ext
    for r in roots:
        p = os.path.normpath(os.path.join(r, v))
        if os.path.isfile(p):
            return p
    return None


def check_png(path, animated_ok=True):
    size = png_size(path)
    if size is None:
        err(path, 'not a PNG'); return
    w, h = size
    meta = path + '.mcmeta'
    if os.path.isfile(meta):
        used.add(meta)
        try:
            anim = json.load(open(meta, encoding='utf-8')).get('animation')
        except ValueError as e:
            err(meta, 'invalid JSON: %s' % e); return
        if anim is None:
            return
        fw, fh = anim.get('width', w), anim.get('height', w if 'width' not in anim else h)
        if h % fh or w % fw:
            err(path, 'animated %dx%d does not split into %dx%d frames' % (w, h, fw, fh))
        frames = (h // fh) * (w // fw) if fh and fw else 0
        for f in anim.get('frames', []):
            i = f['index'] if isinstance(f, dict) else f
            if not 0 <= i < frames:
                err(meta, 'frame %d does not exist (the strip has %d)' % (i, frames))


def check_model(path, seen=()):
    if path in seen:
        return
    used.add(path)
    try:
        m = json.load(open(path, encoding='utf-8'))
    except ValueError as e:
        err(path, 'invalid JSON: %s' % e); return
    d = os.path.dirname(path)
    parent = m.get('parent', '')
    if parent and not re.match(r'^(minecraft:)?(item|block|builtin)/', parent):
        p = resolve(d, parent, '.json')
        if p:
            check_model(p, seen + (path,))
        else:
            err(path, 'parent %s not found' % parent)
    texvars = m.get('textures', {})
    for k, t in texvars.items():
        if t.startswith('#') or re.match(r'^(minecraft:)?(item|block|entity|misc)/', t):
            continue
        p = resolve(d, t, '.png')
        if p:
            used.add(p); check_png(p)
        else:
            err(path, 'texture %s = %s not found' % (k, t))
    for i, e in enumerate(m.get('elements', [])):
        name = e.get('name', '#%d' % i)
        for c in e.get('from', []) + e.get('to', []):
            if not -16 <= c <= 32:
                err(path, 'element %s goes outside -16..32 (the model does not load)' % name)
                break
        rot = e.get('rotation')
        if rot and not -45 <= rot.get('angle', 0) <= 45:
            err(path, 'element %s rotation %s is outside -45..45' % (name, rot.get('angle')))
        for side, face in e.get('faces', {}).items():
            ref = face.get('texture', '')
            if ref.startswith('#') and ref[1:] not in texvars and not parent:
                err(path, 'element %s face %s uses %s, which is not in "textures"' % (name, side, ref))
            if any(not 0 <= u <= 16 for u in face.get('uv', [])):
                warn(path, 'element %s face %s has uv outside 0..16' % (name, side))


def check_cit(path):
    p = read_properties(path)
    d = os.path.dirname(path)
    kind = p.get('type', 'item')
    if kind not in ('item', 'armor', 'elytra', 'enchantment'):
        err(path, 'unknown type=%s' % kind)
    ids = (p.get('items') or p.get('matchItems') or ('elytra' if kind == 'elytra' else '')).split()
    if not ids:
        err(path, 'no items= (the CIT never matches)')
    for i in ids:
        bare = i.split(':', 1)[1] if i.startswith('minecraft:') else i
        if bare not in ITEMS:
            err(path, 'item %s does not exist in vanilla' % i)
        else:
            for ver, missing in VANILLA['missing'].items():
                if bare in missing:
                    warn(path, 'item %s does not exist in %s' % (i, ver))
    name = p.get('nbt.display.Name')
    if name is None:
        warn(path, 'no nbt.display.Name: every %s gets this texture' % ' '.join(ids))
    else:
        m = re.match(r'^(i?pattern|regex|iregex):(.*)$', name)
        body = m.group(2) if m else name
        if m and m.group(1) == 'ipattern':
            warn(path, 'ipattern: also matches other capitalisations; the pack uses pattern:')
        if not m:
            warn(path, 'name without pattern: matches only the exact text "%s"' % name)
        if m and m.group(1).endswith('pattern') and '*' in body.rstrip('*'):
            err(path, 'the "*" must be only at the end of the name: %s' % name)
    tex_keys = [k for k in p if k == 'texture' or k.startswith('texture.')]
    model_keys = [k for k in p if k == 'model' or k.startswith('model.')]
    for k in tex_keys:
        f = resolve(d, p[k], '.png')
        if f:
            used.add(f); check_png(f)
        else:
            err(path, '%s=%s: file not found' % (k, p[k]))
    for k in model_keys:
        f = resolve(d, p[k], '.json')
        if f:
            check_model(f)
        elif not re.match(r'^(minecraft:)?item/', p[k]):
            err(path, '%s=%s: model not found' % (k, p[k]))
    if kind == 'item' and not tex_keys and not model_keys:
        f = os.path.join(d, os.path.splitext(os.path.basename(path))[0] + '.png')
        if os.path.isfile(f):
            used.add(f); check_png(f)
        else:
            err(path, 'no texture=/model= and no %s next to it' % os.path.basename(f))
    if kind == 'armor' and not any(k.startswith('texture.') for k in tex_keys):
        err(path, 'type=armor without texture.<material>_layer_N keys')
    return kind, ids, name, ('regex' in name.split(':', 1)[0] if name else False)


# --- run ---------------------------------------------------------------------------------------------------------
try:
    json.load(open(os.path.join(ROOT, 'pack.mcmeta'), encoding='utf-8'))['pack']
except (ValueError, KeyError, OSError) as e:
    err(os.path.join(ROOT, 'pack.mcmeta'), 'invalid: %s' % e)

names, readme_names = {}, {}
for folder, _, files in os.walk(CIT):
    for f in sorted(files):
        if f.endswith('.properties'):
            path = os.path.join(folder, f)
            kind, ids, name, is_regex = check_cit(path)
            if name:
                for i in ids:
                    names.setdefault((kind, i.replace('minecraft:', ''), name), []).append(path)
                if kind == 'item' and not is_regex and os.sep + 'armors' + os.sep not in path:
                    readme_names.setdefault(name, path)

for (kind, item, name), paths in sorted(names.items()):
    if len(paths) > 1:
        warn(paths[0], 'same type, item and name as %s (%s %s): only one of them shows'
             % (', '.join(rel(x) for x in paths[1:]), item, name))

for folder in ('assets', 'overlay_1_21_9'):
    for dirpath, _, files in os.walk(os.path.join(ROOT, folder)):
        for f in files:
            path = os.path.join(dirpath, f)
            if f.endswith(('.json', '.jem', '.mcmeta')):
                try:
                    json.load(open(path, encoding='utf-8'))
                except ValueError as e:
                    err(path, 'invalid JSON: %s' % e)
            if f == '.mcassetsroot':
                warn(path, 'Minecraft logs "Non-directory entry ... rejecting" for this file on every reload')
            if dirpath.startswith(CIT) and f.endswith(('.png', '.json', '.mcmeta')) and path not in used:
                warn(path, 'not used by any .properties or model')
            if dirpath.startswith(CIT) and f.endswith('.properties') is False and f.endswith('.png.mcmeta'):
                if not os.path.isfile(path[:-len('.mcmeta')]):
                    err(path, 'mcmeta without its PNG')

readme = os.path.join(ROOT, 'README.md')
if os.path.isfile(readme):
    text = open(readme, encoding='utf-8').read().lower()
    for name, path in sorted(readme_names.items()):      # items only: armour sets are listed by set name
        plain = re.sub(r'^[a-z]*:', '', name).rstrip('*').strip()
        if plain and plain.lower() not in text:
            warn(path, 'README.md does not mention "%s"' % plain)

for title, rows in (('ERROR', errors), ('WARNING', warnings)):
    for r in sorted(set(rows)):
        print('%s %s' % (title, r))
print('\n%d .properties checked, %d errors, %d warnings' % (
    sum(1 for _, _, fs in os.walk(CIT) for f in fs if f.endswith('.properties')), len(set(errors)), len(set(warnings))))
sys.exit(1 if errors or (STRICT and warnings) else 0)
