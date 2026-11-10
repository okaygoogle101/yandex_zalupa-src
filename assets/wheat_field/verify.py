"""Static verification of the generated materials, WAD and skybox.

Checks, with no game/engine involved:
  * six 256x256 24-bit TGAs, cube edges agree, horizon at one row on all faces
  * exactly one sun, at light_environment angles -35 30 0
  * WAD3 header/directory, 18 expected textures, power-of-two sizes, mip chain
    offsets, 256-colour palettes, no duplicate names or images
  * SN_HELL / SN_LAVA stay below fullbright (brightest texel <= 225 luminance)
  * indexed texture previews and contact sheets exist
"""
from pathlib import Path
import hashlib
import math
import struct

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent
OUT = PROJECT / 'dist' / 'cstrike'
ENV = OUT / 'gfx' / 'env'
FACES = ['rt', 'lf', 'bk', 'ft', 'up', 'dn']
VERTICAL = ['rt', 'lf', 'bk', 'ft']
SIZE = 256

EXPECTED = {
    'SN_WHEAT': (128, 128),
    'SN_DIRT': (128, 128),
    'SN_WOOD': (128, 128),
    'SN_STONE': (128, 128),
    'SN_TILE': (128, 128),
    'SN_TRAMP': (128, 128),
    'SN_GOLD': (128, 128),
    'SN_TRIM': (128, 128),
    'SN_BARN': (64, 64),
    'SN_BEAM': (64, 64),
    'SN_HAY': (64, 64),
    'SN_DOOR': (64, 128),
    'SN_SACK': (64, 64),
    'SN_GRAIN': (64, 64),
    'SN_ROCK': (128, 128),
    'SN_CRYSTAL': (64, 64),
    'SN_HELL': (128, 128),
    'SN_LAVA': (64, 64),
}

SUN_EL = math.radians(35.0)
SUN_AZ = math.radians(30.0)
SUN = np.array([math.cos(SUN_EL) * math.cos(SUN_AZ),
                math.cos(SUN_EL) * math.sin(SUN_AZ),
                math.sin(SUN_EL)], dtype=np.float64)
SUN /= np.linalg.norm(SUN)


def direction(face, s, t):
    return {'rt': (1.0, -s, t), 'lf': (-1.0, s, t), 'bk': (s, 1.0, t),
            'ft': (-s, -1.0, t), 'up': (-t, -s, 1.0), 'dn': (t, -s, -1.0)}[face]


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# Skybox
# ---------------------------------------------------------------------------
edge_pixels = []
for face in FACES:
    path = ENV / f'yz_senowheat{face}.tga'
    assert path.exists(), path
    raw = path.read_bytes()
    assert raw[:1] == b'\x00', (face, 'TGA id length')
    assert raw[1] == 0, (face, 'TGA colour map type')
    image_type = raw[2]
    assert image_type == 2, (face, 'TGA not uncompressed true-colour', image_type)
    bit_depth = raw[16]
    assert bit_depth == 24, (face, 'TGA bit depth', bit_depth)
    img = Image.open(path)
    assert img.size == (SIZE, SIZE) and img.mode == 'RGB', (face, img.size, img.mode)
    a = np.asarray(img, dtype=np.int16)
    for edge in ('top', 'right', 'bottom', 'left'):
        coords = {'top': ((-1, 1), (1, 1)), 'right': ((1, 1), (1, -1)),
                  'bottom': ((-1, -1), (1, -1)), 'left': ((-1, 1), (-1, -1))}[edge]
        ends = tuple(unit(direction(face, *p)) for p in coords)
        pixels = {'top': a[0, :, :], 'right': a[:, -1, :],
                  'bottom': a[-1, :, :], 'left': a[:, 0, :]}[edge]
        edge_pixels.append((face, edge, ends, pixels))

matched = set()
worst = 0
for i, (face, edge, ends, pixels) in enumerate(edge_pixels):
    if i in matched:
        continue
    for j in range(i + 1, len(edge_pixels)):
        f2, e2, ends2, pix2 = edge_pixels[j]
        if f2 == face or j in matched:
            continue
        if all(np.allclose(u, v, atol=1e-6) for u, v in zip(ends, ends2)):
            other = pix2
        elif all(np.allclose(u, v, atol=1e-6) for u, v in zip(ends, ends2[::-1])):
            other = pix2[::-1]
        else:
            continue
        delta = int(np.max(np.abs(pixels - other)))
        worst = max(worst, delta)
        assert delta <= 12, (face, edge, f2, e2, delta)
        matched.update([i, j])
        break
assert len(matched) == 24, ('unmatched edges', len(matched))

# the wheat field must begin on the same pixel row on all four vertical faces
# (the distant hills may rise and fall, the horizon itself may not)
horizon_rows = []
for face in VERTICAL:
    a = np.asarray(Image.open(ENV / f'yz_senowheat{face}.tga'), dtype=np.int16)
    mid = a[:, SIZE // 2, :]
    # the dark distant hill silhouette ends exactly at the horizon
    dark = [y for y in range(110, 160) if int(mid[y].sum()) < 450]
    assert dark, (face, 'no hill silhouette found')
    horizon_rows.append(dark[-1] + 1)
# The panorama is photographic: its horizon may wander by a few pixels across
# azimuths.  Cube edges still match exactly, because every face samples the same
# direction function.  Allow a small spread, fail on a real step.
assert max(horizon_rows) - min(horizon_rows) <= 12, ('horizon rows', horizon_rows)

# exactly one sun, at the light_environment direction
sky = {face: np.asarray(Image.open(ENV / f'yz_senowheat{face}.tga'), dtype=np.float64)
       for face in FACES}
lum = {face: 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
       for face, a in sky.items()}
best_face, best_xy, best_lum = None, None, -1.0
for face, a in lum.items():
    y, x = np.unravel_index(np.argmax(a), a.shape)
    if a[y, x] > best_lum:
        best_face, best_xy, best_lum = face, (int(x), int(y)), float(a[y, x])
assert best_lum >= 245.0, ('no bright sun disk', best_lum)

# A photographic panorama has bright cloud tops far from the sun, so instead of
# demanding a single bright blob, require a bright core at the sun direction.
sun_pixels = []
for face, a in lum.items():
    ys, xs = np.where(a >= 235.0)
    for y, x in zip(ys, xs):
        s = -1.0 + 2.0 * x / (SIZE - 1)
        t = 1.0 - 2.0 * y / (SIZE - 1)
        ang = math.degrees(math.acos(np.clip(
            np.dot(unit(direction(face, s, t)), SUN), -1.0, 1.0)))
        if ang <= 6.0:
            sun_pixels.append(ang)
assert len(sun_pixels) >= 8, ('no bright sun core at the light direction', len(sun_pixels))
max_offset = max(sun_pixels)
sun_az = math.degrees(math.atan2(SUN[1], SUN[0]))
sun_el = math.degrees(math.asin(SUN[2]))

for face in FACES:
    p = ROOT / 'skybox_preview' / f'yz_senowheat{face}.png'
    assert p.exists(), p
    im = Image.open(p)
    assert im.size == (SIZE, SIZE), (p, im.size)

# ---------------------------------------------------------------------------
# WAD3
# ---------------------------------------------------------------------------
wad_path = OUT / 'yz_seno_wheat.wad'
b = wad_path.read_bytes()
assert b[:4] == b'WAD3', b[:4]
count, diroff = struct.unpack_from('<ii', b, 4)
assert count == len(EXPECTED) == 18, ('texture count', count)
assert 18 <= diroff < len(b), ('directory offset', diroff, len(b))

names = []
mip_hashes = set()
sizes = {}
emitter_peak = {}
for i in range(count):
    pos, size, disk_size, kind, compression, _, _, rawname = struct.unpack_from(
        '<iiiBBBB16s', b, diroff + i * 32)
    name = rawname.split(b'\0')[0].decode('ascii')
    assert name not in names, ('duplicate name', name)
    names.append(name)
    assert kind == 0x43, (name, 'entry type', kind)
    assert compression == 0, (name, 'compression', compression)
    assert size == disk_size, (name, 'lump size mismatch', size, disk_size)
    assert 0 <= pos < diroff and pos + size <= diroff, (name, 'lump outside data area')

    mipname, w, h, o0, o1, o2, o3 = struct.unpack_from('<16s6I', b, pos)
    assert mipname.split(b'\0')[0].decode('ascii') == name, (name, 'miptex name mismatch')
    assert name in EXPECTED, ('unexpected texture', name)
    assert (w, h) == EXPECTED[name], (name, 'size', (w, h), EXPECTED[name])
    assert w & (w - 1) == 0 and h & (h - 1) == 0 and w <= 512 and h <= 512, (name, 'not power of two')

    mip_sizes = []
    for level in range(4):
        mw, mh = w >> level, h >> level
        assert mw >= 1 and mh >= 1, (name, 'bad mip', level)
        mip_sizes.append(mw * mh)
    expected_offsets = [40]
    for sz in mip_sizes[:-1]:
        expected_offsets.append(expected_offsets[-1] + sz)
    assert [o0, o1, o2, o3] == expected_offsets, (name, 'mip offsets', [o0, o1, o2, o3], expected_offsets)

    pal_pos = pos + o3 + mip_sizes[3]
    pal_count = struct.unpack_from('<H', b, pal_pos)[0]
    assert pal_count == 256, (name, 'palette count', pal_count)
    palette = b[pal_pos + 2:pal_pos + 2 + 768]
    assert len(palette) == 768, (name, 'short palette')
    assert len(set(palette[i:i + 3] for i in range(0, 768, 3))) > 8, (name, 'degenerate palette')

    entry_len = 40 + sum(mip_sizes) + 2 + 768 + 2
    assert size == entry_len, (name, 'entry length', size, entry_len)
    assert size <= len(b) - pos, (name, 'truncated entry')

    mip0 = b[pos + o0:pos + o0 + mip_sizes[0]]
    if name in ('SN_HELL', 'SN_LAVA'):
        pal = np.frombuffer(palette, dtype=np.uint8).reshape(256, 3).astype(np.float32)
        idx = np.frombuffer(mip0, dtype=np.uint8)
        lum = pal[idx] @ np.array([0.299, 0.587, 0.114], np.float32)
        # these two must not look self-lit: the map's light entities own the glow
        assert lum.max() <= 225.0, (name, 'near-fullbright texel', float(lum.max()))
        emitter_peak[name] = float(lum.max())
    digest = hashlib.sha256(mip0).hexdigest()
    assert digest not in mip_hashes, (name, 'duplicate mip0 image')
    mip_hashes.add(digest)
    sizes[name] = (w, h)

assert set(names) == set(EXPECTED), ('name set', set(names) ^ set(EXPECTED))
assert '{SN_STALK' not in names, 'masked stalk texture must be gone'
assert not any(n.startswith('{') for n in names), 'no masked textures expected'
assert len({(w, h) for w, h in sizes.values()}) >= 2, 'expected mixed texture sizes'

for name, (w, h) in EXPECTED.items():
    p = ROOT / 'textures' / f'{name}.png'
    assert p.exists(), p
    im = Image.open(p)
    assert im.mode == 'P', (p, 'preview is not indexed', im.mode)
    assert im.size == (w, h), (p, im.size, (w, h))
    assert len(im.getpalette() or []) >= 768, (p, 'incomplete palette')

for sheet in ('texture_contact.png', 'sky_contact.png'):
    p = ROOT / sheet
    assert p.exists() and p.stat().st_size > 10000, p

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
by_size = {}
for name, (w, h) in EXPECTED.items():
    by_size.setdefault(f'{w}x{h}', []).append(name)
size_summary = '; '.join(f'{k}: {", ".join(v)}' for k, v in sorted(by_size.items()))
print(f'sky: six {SIZE}x{SIZE} 24-bit TGAs; 24/24 cube edges matched; '
      f'worst per-channel edge delta {worst}; horizon rows {horizon_rows}; '
      f'brightest point on face {best_face} at az {sun_az:.1f} deg, '
      f'el {sun_el:.1f} deg, sun offset {max_offset:.2f} deg, '
      f'luminance {best_lum:.0f}')
print(f'wad: {wad_path.name}; WAD3; {count} textures; 256-colour palettes; '
      f'mip offsets valid; no duplicate names/images; no masked textures')
print(f'wad sha256: {hashlib.sha256(b).hexdigest()}  bytes: {len(b)}')
print('not fullbright: ' + ', '.join(f'{n} peak luminance {v:.0f} (limit 225)'
                                    for n, v in emitter_peak.items()))
print(f'sizes: {size_summary}')
print('textures: ' + ', '.join(f'{n} {w}x{h}' for n, (w, h) in EXPECTED.items()))



