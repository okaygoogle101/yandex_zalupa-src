"""Deterministic material + skybox generator for seno_field.

Outputs
-------
dist/cstrike/yz_seno_wheat.wad              18 textures, WAD3, 8-bit palettes
dist/cstrike/gfx/env/yz_senowheat{rt,lf,ft,bk,up,dn}.tga   256x256, 24-bit
assets/wheat_field/textures/*.png           indexed (P) previews/sources
assets/wheat_field/skybox_preview/*.png     RGB previews of the six faces
assets/wheat_field/texture_contact.png      contact sheet
assets/wheat_field/sky_contact.png          contact sheet

The sky is generated procedurally from a single 3D direction field, so
cube-face edges and the horizon are continuous by construction.  The sun
direction matches light_environment angles "-35 30 0" (elevation 35 deg,
azimuth 30 deg measured from +X toward +Y, Quake yaw convention).
"""
from pathlib import Path
import math, struct, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent
OUT = PROJECT / 'dist' / 'cstrike'
ENV = OUT / 'gfx' / 'env'
ENV.mkdir(parents=True, exist_ok=True)
(ROOT / 'textures').mkdir(parents=True, exist_ok=True)
(ROOT / 'skybox_preview').mkdir(parents=True, exist_ok=True)
random.seed(1857)

# ----------------------------------------------------------------------------
# Skybox
# ----------------------------------------------------------------------------
SKY_SIZE = 256
SUN_ELEVATION = 35.0
SUN_AZIMUTH = 30.0


def sun_vector():
    el = math.radians(SUN_ELEVATION)
    az = math.radians(SUN_AZIMUTH)
    v = np.array([math.cos(el) * math.cos(az),
                  math.cos(el) * math.sin(az),
                  math.sin(el)], dtype=np.float32)
    return v / np.linalg.norm(v)


SUN = sun_vector()


def _cloud_waves():
    """Deterministic set of plane waves with isotropic directions.

    Evaluating sum(a*sin(f*dot(dir,v)+phase)) gives a smooth 3D field that is
    identical on shared cube edges and looks like soft cumulus rather than
    the diagonal streaks a single sine lattice produces.
    """
    rng = np.random.default_rng(4242)
    waves = []
    amp = 1.0
    for octave in range(5):
        for _ in range(4):
            v = rng.normal(0.0, 1.0, 3)
            v /= np.linalg.norm(v)
            freq = 2.2 * (1.9 ** octave) * rng.uniform(0.8, 1.2)
            waves.append((v.astype(np.float32), np.float32(freq),
                          np.float32(rng.uniform(0.0, 2.0 * math.pi)), np.float32(amp)))
        amp *= 0.55
    norm = sum(w[3] for w in waves)
    return [(v, f, p, a / norm) for v, f, p, a in waves]


CLOUD_WAVES = _cloud_waves()


def cloud_field(x, y, z):
    n = np.zeros_like(x, dtype=np.float32)
    for v, f, phase, amp in CLOUD_WAVES:
        n += amp * np.sin(f * (x * v[0] + y * v[1] + z * v[2]) + phase)
    return n


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(a, b, t):
    t = t[:, :, None] if np.ndim(t) == 2 else t
    return a * (1.0 - t) + b * t


# ----------------------------------------------------------------------------
# The giant in the clouds
# ----------------------------------------------------------------------------
# A figure built entirely as a function of (azimuth, elevation) about one
# centre, so it is continuous across cube edges and across the +-pi meridian.
# It is deliberately placed at 126 deg, far from the sun at 30 deg.
GIANT_AZ = 2.20          # rad, centre of the figure
GIANT_EDGE = 0.085       # rad, width of the soft cloud edge

# --- image-derived cloud giant ---------------------------------------------
# The figure itself is taken from assets/wheat_field/reference_giant.jpg:
# build_giant_alpha.py turns its dark masses into a 0..1 density map, with the
# standing man and the ground removed.  The map is sampled in azimuth /
# elevation, corrected by cos(elevation) so the figure keeps its proportions
# near the zenith, and blended before the hills so it sinks into the horizon.
GIANT_EL_TOP = 0.70      # rad, top edge of the map in the sky
GIANT_EL_BOT = -0.14      # rad, bottom edge (just above the horizon)
GIANT_DU_HALF = 0.62     # cos(el)*azimuth half-width of the map
_GIANT_ALPHA = None


def _giant_alpha():
    global _GIANT_ALPHA
    if _GIANT_ALPHA is None:
        _GIANT_ALPHA = np.load(Path(__file__).with_name('giant_density.npy'))
    return _GIANT_ALPHA


def giant_coverage(da, el):
    """Bilinearly sample the reference density map in (azimuth, elevation)."""
    a = _giant_alpha()
    h, w = a.shape
    du = np.cos(np.clip(el, -1.5, 1.5)) * da
    u = (du + GIANT_DU_HALF) / (2.0 * GIANT_DU_HALF) * (w - 1)
    v = (GIANT_EL_TOP - el) / (GIANT_EL_TOP - GIANT_EL_BOT) * (h - 1)
    inside = (u >= 0.0) & (u <= w - 1) & (v >= 0.0) & (v <= h - 1)
    u = np.clip(u, 0.0, w - 1.001)
    v = np.clip(v, 0.0, h - 1.001)
    i0 = u.astype(np.int32)
    j0 = v.astype(np.int32)
    fu = u - i0
    fv = v - j0
    s = ((a[j0, i0] * (1.0 - fu) + a[j0, i0 + 1] * fu) * (1.0 - fv)
         + (a[j0 + 1, i0] * (1.0 - fu) + a[j0 + 1, i0 + 1] * fu) * fv)
    uu = u / max(w - 1, 1)
    vv = v / max(h - 1, 1)
    fade = np.clip(np.minimum(np.minimum(uu, 1.0 - uu),
                              np.minimum(vv, 1.0 - vv)) / 0.06, 0.0, 1.0)
    fade = fade * fade * (3.0 - 2.0 * fade)
    return np.where(inside, s * fade, 0.0).astype(np.float32)


def _ellipse_dist(du, dv, cu, cv, ru, rv):
    """Approximate signed distance (radians) to an ellipse in (da, el) space."""
    q = np.sqrt(((du - cu) / ru) ** 2 + ((dv - cv) / rv) ** 2)
    return (q - 1.0) * min(ru, rv)


def _capsule_dist(du, dv, au, av, bu, bv, radius):
    """Signed distance (radians) to a thick line segment in (da, el) space."""
    vu, vv = bu - au, bv - av
    t = np.clip(((du - au) * vu + (dv - av) * vv) / (vu * vu + vv * vv), 0.0, 1.0)
    return np.hypot(du - (au + t * vu), dv - (av + t * vv)) - radius


def _giant_body(da, el):
    """Union of the cloud figure's soft masses, as one signed distance field."""
    d = _ellipse_dist(da, el, 0.0, 0.28, 0.58, 0.52)              # belly
    d = np.minimum(d, _ellipse_dist(da, el, 0.0, 0.63, 0.52, 0.16))   # shoulders
    d = np.minimum(d, _capsule_dist(da, el, 0.0, 0.72, 0.0, 0.86, 0.10))  # neck
    d = np.minimum(d, _ellipse_dist(da, el, 0.0, 0.97, 0.22, 0.23))   # head
    d = np.minimum(d, _ellipse_dist(da, el, 0.0, 1.20, 0.10, 0.13))   # pompadour
    # swept crest: three shallow lobes so the top is a rounded hair wave
    d = np.minimum(d, _ellipse_dist(da, el, 0.0, 1.298, 0.105, 0.045))
    d = np.minimum(d, _ellipse_dist(da, el, -0.085, 1.283, 0.075, 0.048))
    d = np.minimum(d, _ellipse_dist(da, el, 0.085, 1.286, 0.070, 0.048))
    rise = math.atan2(0.98 - 0.64, 1.02 - 0.42)
    for side in (-1.0, 1.0):
        base = rise if side > 0 else math.pi - rise
        # arm from the shoulder to the open hand
        d = np.minimum(d, _capsule_dist(da, el, 0.42 * side, 0.64,
                                        1.02 * side, 0.98, 0.045))
        # palm
        d = np.minimum(d, _ellipse_dist(da, el, 1.06 * side, 1.02, 0.13, 0.10))
        # four splayed fingers, mirrored across the body
        for fan in (-0.62, -0.21, 0.20, 0.62):
            phi = base + side * fan
            au = 1.06 * side + 0.085 * math.cos(phi)
            av = 1.02 + 0.085 * math.sin(phi)
            bu = 1.06 * side + 0.155 * math.cos(phi)
            bv = 1.02 + 0.155 * math.sin(phi)
            d = np.minimum(d, _capsule_dist(da, el, au, av, bu, bv, 0.020))
    return d


def _giant_holes(da, el):
    """Light gaps: the laughing mouth, the eyes and the chain on the chest."""
    d = _ellipse_dist(da, el, 0.0, 0.90, 0.10, 0.06)             # open mouth
    d = np.minimum(d, _ellipse_dist(da, el, -0.075, 1.02, 0.025, 0.018))
    d = np.minimum(d, _ellipse_dist(da, el, 0.075, 1.02, 0.025, 0.018))
    for k in range(9):
        u = -0.20 + 0.40 * k / 8.0
        v = 0.575 + 0.055 * (u / 0.20) ** 2
        d = np.minimum(d, _ellipse_dist(da, el, u, v, 0.012, 0.017))
    return d


def _soft_mask(sd, width):
    """1 inside, 0 outside, smoothstep transition of *width* radians."""
    return smooth((0.5 * width - sd) / width)


def _grid(size):
    s, t = np.meshgrid(np.linspace(-1, 1, size), np.linspace(1, -1, size))
    one = np.ones_like(s)
    dirs = {
        'rt': (one, -s, t),
        'lf': (-one, s, t),
        'bk': (s, one, t),
        'ft': (-s, -one, t),
        'up': (-t, -s, one),
        'dn': (t, -s, -one),
    }
    return dirs, s, t


def sky(face, size=SKY_SIZE):
    """One skybox face. Every colour is a function of the 3D view direction,
    therefore faces agree at shared edges and the horizon is continuous."""
    dirs, _, _ = _grid(size)
    x, y, z = (v.astype(np.float32) for v in dirs[face])
    norm = np.sqrt(x * x + y * y + z * z)
    x, y, z = x / norm, y / norm, z / norm
    az = np.arctan2(y, x)
    el = np.arcsin(np.clip(z, -1.0, 1.0))

    # --- warm late-afternoon sky gradient -----------------------------------
    h = smooth(z / 0.62)
    horizon = np.array([252.0, 204.0, 154.0], dtype=np.float32)
    zenith = np.array([88.0, 131.0, 174.0], dtype=np.float32)
    col = mix(horizon, zenith, h)

    # warm band hugging the horizon
    band = np.exp(-(el / 0.17) ** 2)
    col = mix(col, np.array([255.0, 193.0, 126.0], dtype=np.float32), 0.26 * band)

    # --- soft cumulus -------------------------------------------------------
    n = cloud_field(x, y, z)
    # sample the same field slightly toward the sun for directional shading
    lift = np.float32(0.055)
    n_lit = cloud_field(x + SUN[0] * lift, y + SUN[1] * lift, z + SUN[2] * lift)
    dens = smooth((n - 0.08) / 0.30)
    # clouds live in the sky only; thin out near the horizon and zenith
    dens *= smooth((el - 0.055) / 0.13)
    dens *= 1.0 - 0.30 * smooth((el - 0.75) / 0.25)
    shade = np.clip(0.50 + 2.4 * (n - n_lit), 0.0, 1.0)
    cloud_shadow = np.array([188.0, 162.0, 160.0], dtype=np.float32)
    cloud_lit = np.array([255.0, 234.0, 206.0], dtype=np.float32)
    ccol = mix(cloud_shadow, cloud_lit, shade)
    # warm sun-side tint on the cloud tops
    ccol = mix(ccol, np.array([255.0, 219.0, 172.0], dtype=np.float32),
               0.35 * np.exp(-(np.arccos(np.clip(x * SUN[0] + y * SUN[1] + z * SUN[2], -1, 1)) / 0.55) ** 2))
    col = mix(col, ccol, 0.90 * dens)

    # --- single sun ---------------------------------------------------------
    cosang = np.clip(x * SUN[0] + y * SUN[1] + z * SUN[2], -1.0, 1.0)
    ang = np.arccos(cosang)
    halo = 0.55 * np.exp(-(ang / 0.24) ** 2) + 0.45 * np.exp(-(ang / 0.075) ** 2)
    col = mix(col, np.array([255.0, 211.0, 146.0], dtype=np.float32),
              np.clip(halo, 0.0, 0.92))
    disk = smooth((0.0185 - ang) / 0.005)
    col = mix(col, np.array([255.0, 250.0, 232.0], dtype=np.float32), disk)

    # --- the giant in the clouds --------------------------------------------
    # A dark cumulus figure: broad belly, spread arms with open hands, tall
    # pompadour, laughing mouth and a chain on the chest.  Built in
    # (azimuth, elevation) about GIANT_AZ, so it stays continuous through the
    # +-pi meridian and across cube edges.  Its lower body is painted before
    # the hills and the field, so it sinks behind the horizon instead of
    # floating above the wheat.  The cloud field wobbles the boundary and
    # modulates the interior, so the mass reads as cloud, not as a sticker.
    da = np.arctan2(np.sin(az - GIANT_AZ), np.cos(az - GIANT_AZ))
    dens = np.clip(giant_coverage(da, el) * (0.90 + 0.10 * n), 0.0, 1.0)
    col = col * (1.0 - 0.85 * dens)[:, :, None]



    # --- distant hills just above the horizon -------------------------------
    ridge = (0.019
             + 0.0070 * np.sin(3.0 * az + 0.7)
             + 0.0040 * np.sin(7.0 * az - 1.3)
             + 0.0020 * np.sin(17.0 * az + 0.2))
    ridge = np.clip(ridge, 0.006, 0.032)
    hill = smooth((ridge - el) / 0.0016) * smooth((el + 0.002) / 0.002)
    hill_col = np.array([99.0, 106.0, 68.0], dtype=np.float32)
    hill_col = mix(hill_col, np.array([150.0, 148.0, 108.0], dtype=np.float32),
                   0.30 + 0.28 * np.sin(2.1 * az + 0.4))
    # a pale far ridge line on top of the nearer hills
    far_ridge = ridge + 0.006 + 0.003 * np.sin(5.0 * az - 0.9)
    far_hill = smooth((far_ridge - el) / 0.0014) * smooth((ridge + 0.004 - el) / 0.0012)
    col = mix(col, np.array([167.0, 168.0, 132.0], dtype=np.float32), 0.55 * far_hill)
    col = mix(col, hill_col, 0.92 * hill)

    # --- golden wheat field below the horizon -------------------------------
    depth = np.clip(-el, 0.0, 1.6)
    near = np.array([199.0, 159.0, 83.0], dtype=np.float32)
    far = np.array([224.0, 194.0, 133.0], dtype=np.float32)
    field = mix(far, near, smooth(depth / 0.55))
    # golden patchiness of a mature wheat field; fades toward the nadir so the
    # down face never shows a radial moire
    near_fade = 1.0 - smooth((depth - 0.55) / 0.45)
    field = field * (1.0 + ((0.035 * np.sin(13.0 * az + 8.0 * depth)
                             + 0.022 * np.sin(31.0 * az - 5.0 * depth)) * near_fade)[:, :, None])
    # ploughed rows, horizontal on the vertical faces; fade them out near nadir
    rows = ((0.038 * np.sin(74.0 * depth + 5.0 * np.sin(3.0 * az))
             + 0.018 * np.sin(157.0 * depth + 2.0 * az)) * near_fade)
    field = field * (1.0 + rows[:, :, None])
    # fine straw break-up so the field is not flat
    field = field * (1.0 + (0.022 * np.sin(211.0 * depth + 17.0 * az) * near_fade)[:, :, None])
    # haze so the horizon line is soft, never a stair step
    haze = np.exp(-(el / 0.014) ** 2)
    field = mix(field, np.array([234.0, 206.0, 160.0], dtype=np.float32), 0.55 * haze)
    ground = smooth((0.007 - el) / 0.009)
    col = mix(col, field, ground)

    return Image.fromarray(np.uint8(np.clip(col, 0, 255)), 'RGB')


def make_sky():
    for face in ['rt', 'lf', 'ft', 'bk', 'up', 'dn']:
        im = sky(face)
        im.save(ENV / f'yz_senowheat{face}.tga', compression=None)
        im.save(ROOT / 'skybox_preview' / f'yz_senowheat{face}.png')


# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
def noisy(base, seed, variation=10, size=(128, 128)):
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, variation, (size[1], size[0], 1))
    pix = np.clip(np.array(base)[None, None, :] + noise, 0, 255).astype('uint8')
    return Image.fromarray(pix, 'RGB')


def _wrap_line(d, x0, y0, x1, y1, fill, width, w, h):
    """Draw a line plus wrapped copies so the tile stays seamless."""
    for dx in (-w, 0, w):
        for dy in (-h, 0, h):
            d.line((x0 + dx, y0 + dy, x1 + dx, y1 + dy), fill=fill, width=width)


def _periodic_field(size, terms, seed):
    """Smooth field that is exactly seamless in both axes.

    ``terms`` are ``(kx, ky, amplitude)`` integer frequencies; a sum of cosines
    with those periods repeats every ``size`` pixels, so no edge blend is needed.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    acc = np.zeros((size, size), np.float32)
    for kx, ky, amp in terms:
        acc += amp * np.cos(2.0 * math.pi * (kx * xx + ky * yy) / size
                            + rng.uniform(0.0, 2.0 * math.pi))
    lo, hi = float(acc.min()), float(acc.max())
    return (acc - lo) / max(hi - lo, 1e-6)


def _periodic_noise(size, rng, octaves=4, base=3, persistence=0.5):
    """Seamless fractal value noise in 0..1.

    Each octave is a small lattice of random values sampled with smooth
    (smoothstep) interpolation; lattice indices wrap, so the field repeats
    exactly at ``size`` on both axes.  Bilinear sampling keeps it cheap for
    128x128 sheets.
    """
    acc = np.zeros((size, size), np.float32)
    amp, norm, cells = 1.0, 0.0, base
    for _ in range(octaves):
        cells = min(cells, size)
        grid = rng.random((cells, cells)).astype(np.float32)
        u = np.arange(size, dtype=np.float32) * cells / size
        i0 = np.floor(u).astype(np.int32) % cells
        i1 = (i0 + 1) % cells
        f = u - np.floor(u)
        f = f * f * (3.0 - 2.0 * f)
        rows = grid[i0, :] * (1.0 - f[:, None]) + grid[i1, :] * f[:, None]
        acc += amp * (rows[:, i0] * (1.0 - f[None, :]) + rows[:, i1] * f[None, :])
        norm += amp
        amp *= persistence
        cells *= 2
    return acc / norm


def _voronoi(size, count, rng):
    """Toroidal Voronoi diagram: per-pixel nearest and second distance, owner.

    Random sites on a wrap-around square produce irregular angular facets with
    no lattice rhythm, which is exactly the read wanted for broken rock,
    crystal prisms and crust plates.  ``d2 - d1`` is ~0 on a facet boundary,
    so it doubles as a crack/facet-edge mask.
    """
    pts = rng.random((count, 2)).astype(np.float32) * size
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d1 = np.full((size, size), np.float32(1e6))
    d2 = np.full((size, size), np.float32(1e6))
    owner = np.zeros((size, size), np.int32)
    for i in range(count):
        px, py = pts[i]
        dx = np.abs(xx - px)
        dx = np.minimum(dx, size - dx)
        dy = np.abs(yy - py)
        dy = np.minimum(dy, size - dy)
        dist = np.sqrt(dx * dx + dy * dy)
        nearer = dist < d1
        d2 = np.where(nearer, d1, np.minimum(d2, dist))
        d1 = np.where(nearer, dist, d1)
        owner = np.where(nearer, np.int32(i), owner)
    return d1, d2, owner, pts


def _shade(height, strength, light=(-0.45, -0.65, 0.62)):
    """Diffuse term from a heightfield, with wrap-around gradients.

    Returns roughly -1 (facing away) .. +1 (facing the light).  A per-facet
    height step therefore reads as a chipped plane: dark on one side, pale on
    the other, with no drawn seams needed.
    """
    hx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5 * strength
    hy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5 * strength
    nx, ny, nz = -hx, -hy, np.ones_like(height)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + 1.0)
    lx, ly, lz = light
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    return (nx * lx + ny * ly + nz * lz) * inv / ln


def _facet_ramp(size, owner, pts, rr):
    """Per-facet linear ramp -1..1 along a random direction (flat-facet sheen)."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    ramp = np.zeros((size, size), np.float32)
    radius = size / math.sqrt(len(pts)) * 0.8
    for i, (px, py) in enumerate(pts):
        mask = owner == i
        if not mask.any():
            continue
        ang = rr.uniform(0.0, 2.0 * math.pi)
        dx = (xx - px + size / 2.0) % size - size / 2.0
        dy = (yy - py + size / 2.0) % size - size / 2.0
        u = (dx * math.cos(ang) + dy * math.sin(ang)) / radius
        ramp[mask] = np.clip(u[mask], -1.0, 1.0)
    return ramp


def _wrapped_point(d, x, y, colour, size):
    """Draw a one-pixel point plus wrapped copies (keeps the tile seamless)."""
    for ox in (-size, 0, size):
        for oy in (-size, 0, size):
            d.point((x + ox, y + oy), fill=colour)


def wheat():
    source = ROOT / 'wheat_imagegen.png'
    if source.exists():
        arr = np.array(Image.open(source).convert('RGB').resize((128, 128), Image.Resampling.LANCZOS), dtype=np.float32)
        for d in range(16):
            w = (16 - d) / 16
            avg = (arr[:, d, :] + arr[:, 127 - d, :]) / 2
            arr[:, d, :] = arr[:, d, :] * (1 - w) + avg * w
            arr[:, 127 - d, :] = arr[:, 127 - d, :] * (1 - w) + avg * w
        for d in range(16):
            w = (16 - d) / 16
            avg = (arr[d, :, :] + arr[127 - d, :, :]) / 2
            arr[d, :, :] = arr[d, :, :] * (1 - w) + avg * w
            arr[127 - d, :, :] = arr[127 - d, :, :] * (1 - w) + avg * w
        # Halve the grain: the seamless 128x128 sheet is downsampled by exactly
        # two and tiled back to 128x128, so stalks/motifs span half the world
        # distance at the map's 1.0 scale.  Colour and drawing style are
        # unchanged; the result stays seamless because the source is periodic.
        sheet = Image.fromarray(np.uint8(np.clip(arr, 0, 255)), 'RGB')
        half = np.array(sheet.resize((64, 64), Image.Resampling.LANCZOS),
                        dtype=np.uint8)
        arr = np.tile(half, (2, 2, 1)).astype(np.float32)
        return Image.fromarray(np.uint8(np.clip(arr, 0, 255)), 'RGB')
    im = noisy((151, 125, 67), 11, 11)
    d = ImageDraw.Draw(im)
    rr = random.Random(19)
    for _ in range(700):
        x, y = rr.randrange(128), rr.randrange(128)
        length = rr.randrange(3, 13)
        c = rr.choice([(205, 172, 83), (221, 187, 99), (180, 146, 70), (239, 205, 124), (127, 111, 61)])
        for dx in (-128, 0, 128):
            for dy in (-128, 0, 128):
                xx, yy = x + dx, y + dy
                d.line((xx, yy, xx + rr.choice([-2, -1, 0, 1, 2]), yy - length), fill=c, width=1)
    return im


def wood():
    im = noisy((132, 92, 52), 21, 7)
    d = ImageDraw.Draw(im)
    rr = random.Random(22)
    for y in range(0, 128, 32):
        d.rectangle((0, y, 127, y + 2), fill=(72, 49, 30))
        d.line((0, y + 3, 127, y + 3), fill=(183, 138, 81))
        for _ in range(13):
            yy = y + rr.randrange(5, 29)
            x = rr.randrange(128)
            length = rr.randrange(12, 55)
            for off in (-128, 0, 128):
                d.line((x + off, yy, x + off + length, yy + rr.choice([-1, 0, 1])),
                       fill=rr.choice([(105, 70, 41), (164, 116, 68), (116, 78, 45)]), width=1)
    return im


def stone(tile=False):
    im = noisy((149, 126, 96) if not tile else (164, 146, 117), 32 if not tile else 33, 7)
    d = ImageDraw.Draw(im)
    for y in range(0, 128, 32):
        d.line((0, y, 127, y), fill=(91, 75, 60), width=2)
        shift = 32 if (y // 32) % 2 else 0
        for x in range(-64 + shift, 192, 64):
            d.line((x, y, x, y + 31), fill=(95, 77, 60), width=2)
    return im


def trim():
    im = noisy((103, 72, 39), 42, 6)
    d = ImageDraw.Draw(im)
    for y in (0, 30, 64, 94, 127):
        d.line((0, y, 127, y), fill=(224, 184, 104), width=3)
    for x in range(0, 128, 32):
        d.polygon([(x, 32), (x + 12, 48), (x, 62), (x - 12, 48)], outline=(207, 170, 98), width=2)
        d.ellipse((x - 2, 46, x + 2, 50), fill=(249, 214, 133))
    return im


def tramp():
    im = noisy((49, 78, 87), 53, 5)
    d = ImageDraw.Draw(im)
    for x in range(0, 128, 8):
        d.line((x, 10, x, 118), fill=(65, 101, 107))
    for y in range(0, 128, 8):
        d.line((10, y, 118, y), fill=(35, 65, 72))
    d.rectangle((1, 1, 126, 126), outline=(237, 187, 80), width=9)
    d.rectangle((10, 10, 117, 117), outline=(86, 61, 34), width=2)
    for i in range(20, 110, 18):
        for x, y in [(i, 5), (i, 122), (5, i), (122, i)]:
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(244, 220, 165))
    return im


def gold():
    im = noisy((192, 153, 77), 61, 6)
    d = ImageDraw.Draw(im)
    for y in range(0, 128, 32):
        for x in range(0, 128, 32):
            d.rectangle((x, y, x + 31, y + 31), outline=(122, 87, 42), width=2)
            d.rectangle((x + 3, y + 3, x + 28, y + 28), outline=(235, 199, 120), width=1)
            d.polygon([(x + 16, y + 7), (x + 23, y + 16), (x + 16, y + 25), (x + 9, y + 16)],
                      outline=(247, 219, 153), width=1)
    return im


def barn():
    """SN_BARN: dark barn timber, vertical board cladding, 64x64.

    Boards are 8 units wide at the map's 1.0 scale.  Grain is deliberately
    sparse (three broken strokes per board) and each board carries a small
    tonal offset, so a wall reads as boarding instead of a fine pinstripe grid.
    """
    w = h = 64
    board = 8
    rr = random.Random(102)
    arr = np.array(noisy((74, 51, 32), 101, 6, (w, h)), dtype=np.float32)
    for i, x0 in enumerate(range(0, w, board)):
        arr[:, x0:x0 + board, :] += rr.uniform(-6.0, 6.0)
    im = Image.fromarray(np.uint8(np.clip(arr, 0, 255)), 'RGB')
    d = ImageDraw.Draw(im)
    for x0 in range(0, w, board):
        # dark seam + lit edge, wrapping at x=0/63
        d.line((x0, 0, x0, h - 1), fill=(40, 27, 16), width=1)
        d.line((x0 + 1, 0, x0 + 1, h - 1), fill=(103, 73, 45), width=1)
        # sparse vertical grain, differing per board
        for _ in range(3):
            gx = x0 + rr.randrange(2, board - 1)
            y = rr.randrange(0, 12)
            while y < h:
                run = rr.randrange(12, 30)
                nx = gx + rr.choice([-1, 0, 0, 0, 1])
                _wrap_line(d, gx, y, nx, min(y + run, h), rr.choice([(58, 39, 23), (96, 67, 40), (111, 79, 47)]), 1, w, h)
                y += run + rr.randrange(8, 20)
        # nails top and bottom of each board
        for ny in (4, h - 4):
            d.rectangle((x0 + 3, ny, x0 + 4, ny + 1), fill=(126, 104, 72))
            d.point((x0 + 3, ny), fill=(42, 36, 28))
    # narrow damp streaks and a few small knots, wrapped
    for _ in range(5):
        x = rr.randrange(w)
        y0 = rr.randrange(h)
        length = rr.randrange(10, 26)
        _wrap_line(d, x, y0, x, y0 + length, (63, 43, 27), 1, w, h)
        if rr.random() < 0.5:
            _wrap_line(d, x + 1, y0, x + 1, y0 + length, (90, 63, 38), 1, w, h)
    for _ in range(3):
        x = rr.randrange(w)
        y = rr.randrange(h)
        d.ellipse((x - 1, y - 2, x + 1, y + 2), fill=(50, 34, 21))
        d.point((x, y), fill=(114, 81, 48))
    return im


def beam():
    """SN_BEAM: dark structural beam, pronounced longitudinal grain, 64x64.

    Grain runs along U so a horizontally-aligned beam reads correctly.
    """
    w = h = 64
    im = noisy((69, 48, 30), 111, 6, (w, h))
    d = ImageDraw.Draw(im)
    rr = random.Random(112)
    # deep longitudinal grooves
    for gy in (7, 21, 35, 49):
        for x in range(-w, 2 * w, 8):
            yy = gy + rr.choice([-1, 0, 0, 1])
            _wrap_line(d, x, gy, x + 8, yy, (39, 26, 15), 2, w, h)
            _wrap_line(d, x, gy + 2, x + 8, yy + 2, (107, 76, 45), 1, w, h)
    # fine grain
    for _ in range(34):
        y = rr.randrange(1, h - 1)
        x = rr.randrange(w)
        length = rr.randrange(14, 40)
        _wrap_line(d, x, y, x + length, y + rr.choice([-1, 0, 0, 1]),
                   rr.choice([(53, 35, 21), (92, 64, 39), (119, 85, 50), (45, 30, 18)]), 1, w, h)
    # two knots
    for kx, ky in ((18, 28), (47, 45)):
        d.ellipse((kx - 4, ky - 2, kx + 4, ky + 2), fill=(39, 26, 15))
        d.ellipse((kx - 2, ky - 1, kx + 2, ky + 1), fill=(86, 59, 35))
        d.point((kx, ky), fill=(118, 84, 49))
    # chipped highlight along the upper edge
    d.line((0, 0, w - 1, 0), fill=(97, 70, 43))
    d.line((0, h - 1, w - 1, h - 1), fill=(44, 30, 18))
    return im


def hay():
    """SN_HAY: pressed straw, 64x64.

    A warm yellow-beige straw mass covered with individual stems.  Every fibre
    follows one relaxed diagonal with wide per-strand jitter and varied length
    and brightness; there are no horizontal strata, twine lines or block seams,
    so at 1 texel per unit it reads as hay on the cart load and in the room-2
    bales instead of masonry.
    """
    w = h = 64
    rr = random.Random(1221)
    rng = np.random.default_rng(1221)

    # clumping of the packed mass: two smooth, already seamless scales
    clump = _periodic_field(w, [(1, 2, 0.55), (2, 1, 0.45), (1, 1, 0.35),
                                (3, 2, 0.25), (2, 3, 0.22), (4, 1, 0.16),
                                (1, 4, 0.15), (5, 3, 0.09), (3, 5, 0.09)], 3101)
    tuft = _periodic_field(w, [(6, 4, 0.12), (4, 6, 0.12), (7, 2, 0.08),
                               (2, 7, 0.08), (9, 5, 0.05)], 3102)
    t = 0.32 + 0.50 * clump + 0.18 * tuft
    t += rng.normal(0.0, 0.035, (h, w)).astype(np.float32)
    t = np.clip(t, 0.0, 1.0)[:, :, None]
    dark = np.array([150.0, 110.0, 54.0], np.float32)
    light = np.array([232.0, 200.0, 138.0], np.float32)
    im = Image.fromarray(np.uint8(np.clip(dark * (1.0 - t) + light * t, 0, 255)), 'RGB')
    d = ImageDraw.Draw(im)

    dominant = 0.42  # radians: relaxed diagonal, never parallel to face edges

    def stroke(x, y, length, angle, colour, width):
        x1 = x + length * math.cos(angle)
        y1 = y + length * math.sin(angle)
        bend = rr.uniform(-2.6, 2.6)
        mx = (x + x1) / 2.0 - bend * math.sin(angle)
        my = (y + y1) / 2.0 + bend * math.cos(angle)
        _wrap_line(d, x, y, mx, my, colour, width, w, h)
        _wrap_line(d, mx, my, x1, y1, colour, width, w, h)

    # three passes: shaded under-straw, the bulk, then lit stems on top
    layers = [
        ([(126, 90, 44), (142, 104, 52), (158, 120, 60), (172, 134, 68)],
         160, (1, 1, 2)),
        ([(180, 142, 74), (196, 158, 88), (210, 175, 104), (188, 150, 80)],
         340, (1, 1, 1, 2)),
        ([(222, 190, 124), (234, 204, 142), (244, 218, 162), (208, 173, 106)],
         160, (1, 1)),
    ]
    for colours, count, widths in layers:
        for _ in range(count):
            x, y = rr.randrange(w), rr.randrange(h)
            if rr.random() < 0.18:
                angle = rr.uniform(0.0, 2.0 * math.pi)
            else:
                angle = dominant + max(-1.2, min(1.2, rr.gauss(0.0, 0.50)))
            if rr.random() < 0.90:
                length = rr.uniform(8.0, 27.0)
            else:
                length = rr.uniform(26.0, 40.0)
            stroke(x, y, length, angle, rr.choice(colours), rr.choice(widths))
    # cut ends and pale tips catch the light
    for _ in range(45):
        x, y = rr.randrange(w), rr.randrange(h)
        c = rr.choice([(243, 220, 166), (230, 200, 140), (250, 232, 186)])
        _wrap_line(d, x, y, x + rr.choice([-1, 0, 1]), y + rr.choice([-1, 0, 1]), c, 1, w, h)
    return im


def _thread_bands(size, rng, lo=3, hi=6):
    """Irregular band widths that sum to *size* (deliberately not a grid)."""
    bands = []
    left = size
    while left > 0:
        if left <= hi:
            step = left
        else:
            step = int(rng.integers(lo, hi + 1))
            step = min(step, left - lo)
        bands.append(step)
        left -= step
    return bands


def _band_maps(bands):
    """Per-pixel band index and 0..1 position inside that band."""
    size = sum(bands)
    idx = np.empty(size, np.int32)
    pos = np.empty(size, np.float32)
    start = 0
    for i, b in enumerate(bands):
        idx[start:start + b] = i
        pos[start:start + b] = (np.arange(b, dtype=np.float32) + 0.5) / b
        start += b
    return idx, pos


def sack():
    """SN_SACK: coarse burlap sacking, 64x64.

    Plain weave of 2..7 px thread bands, but the bands are not a grid: their
    widths never repeat in a fixed rhythm and every thread wanders a pixel or
    two as it crosses the tile.  Warp and weft tones differ only slightly;
    the weave is carried by rounded profiles, one-pixel seams, slub brightness
    running along each yarn and a scatter of nubs.  Diagonal folds, crease
    ridges, pale abrasion and a few stains finish it.  On 48-64 unit sacks it
    reads as woven cloth, not as a checkerboard.
    """
    w = h = 64
    rr = random.Random(2201)
    rng = np.random.default_rng(2201)

    cols = _thread_bands(w, rng, lo=2, hi=7)
    rows = _thread_bands(h, rng, lo=2, hi=7)
    ci, cpos = _band_maps(cols)
    ri, rpos = _band_maps(rows)

    Y, X = np.mgrid[0:h, 0:w]
    # periodic wander of the warp (along y) and weft (along x); seamless
    dx = np.round(1.7 * np.sin(2.0 * math.pi * 2.0 * Y / w + 0.4)
                  + 1.1 * np.sin(2.0 * math.pi * 5.0 * Y / w + 2.0)).astype(np.int32)
    dy = np.round(1.7 * np.sin(2.0 * math.pi * 3.0 * X / w + 1.3)
                  + 1.0 * np.sin(2.0 * math.pi * 6.0 * X / w + 4.1)).astype(np.int32)
    cidx = ci[(X + dx) % w]
    cpos_m = cpos[(X + dx) % w]
    ridx = ri[(Y + dy) % h]
    rpos_m = rpos[(Y + dy) % h]

    def tones(n, base, spread, seed):
        r = np.random.default_rng(seed)
        out = np.empty((n, 3), np.float32)
        for i in range(n):
            out[i] = (np.array(base, np.float32) * r.uniform(1.0 - spread, 1.0 + spread)
                      + r.normal(0.0, 2.5, 3))
        return out

    warp = tones(len(cols), (151.0, 127.0, 98.0), 0.070, 2202)
    weft = tones(len(rows), (161.0, 136.0, 106.0), 0.065, 2203)

    def slub(n, length, seed):
        """Seamless brightness wobble along each yarn (slubs, thin spots)."""
        r = np.random.default_rng(seed)
        t = np.linspace(0.0, 2.0 * math.pi, length, endpoint=False, dtype=np.float32)
        out = np.empty((n, length), np.float32)
        for i in range(n):
            f = r.integers(3, 8)
            out[i] = (0.060 * np.sin(f * t + r.uniform(0.0, 2.0 * math.pi))
                      + 0.042 * np.sin((f + 3) * t + r.uniform(0.0, 2.0 * math.pi))
                      + r.normal(0.0, 0.015, length).astype(np.float32))
        return out

    warp_sl = slub(len(cols), h, 2204)
    weft_sl = slub(len(rows), w, 2205)

    def profile(pos):
        # gentle rounded thread with a narrow dark seam at each boundary
        edge = 0.5 - np.abs(pos - 0.5)
        seam = np.exp(-edge / 0.055)
        return (0.955 + 0.045 * np.sin(np.pi * pos)) * (1.0 - 0.19 * seam)

    warp_img = (warp[cidx] * (1.0 + warp_sl[cidx, Y])[:, :, None]
                * profile(cpos_m)[:, :, None])
    weft_img = (weft[ridx] * (1.0 + weft_sl[ridx, X])[:, :, None]
                * profile(rpos_m)[:, :, None])

    over = (cidx + ridx) % 2 == 0        # weft passes over
    col = np.where(over[:, :, None], weft_img, warp_img)

    # soft diagonal folds; periodic, therefore seamless
    fold = _periodic_field(w, [(1, 1, 0.55), (2, 1, 0.35), (1, 2, 0.30),
                               (3, 2, 0.14), (2, 3, 0.13), (1, 4, 0.08)], 2206)
    col *= (0.935 + 0.11 * fold)[:, :, None]

    # crease ridges: shadow crest plus a lit side one offset away
    for a, b, phase, amp in ((1, 2, 0.8, 0.10), (-2, 1, 2.3, 0.08),
                             (2, 3, 4.1, 0.07)):
        arg = 2.0 * math.pi * (a * X + b * Y) / w
        ridge = np.exp(-(1.0 - np.cos(arg + phase)) / 0.055)
        col *= (1.0 - amp * ridge)[:, :, None]
        lit = np.exp(-(1.0 - np.cos(arg + phase + 0.55)) / 0.09)
        col *= (1.0 + 0.06 * lit)[:, :, None]

    def patch(cx, cy, rx, ry):
        """Seamless elliptical mask around (cx, cy)."""
        dxm = np.abs((X - cx + w // 2) % w - w // 2)
        dym = np.abs((Y - cy + h // 2) % h - h // 2)
        return np.clip(1.0 - (dxm / rx) ** 2 - (dym / ry) ** 2, 0.0, 1.0) ** 0.7

    # pale rub-through where the sacks are dragged
    abrasion = np.zeros((h, w), np.float32)
    for cx, cy, rx, ry, s in ((14, 18, 13, 9, 0.26), (44, 33, 10, 12, 0.21),
                              (30, 54, 15, 7, 0.17), (52, 8, 8, 6, 0.15)):
        abrasion = np.maximum(abrasion, s * patch(cx, cy, rx, ry))
    pale = np.array([188.0, 171.0, 143.0], np.float32)
    col = col * (1.0 - abrasion[:, :, None]) + pale * abrasion[:, :, None]

    # damp / dirty stains, low contrast so the weave stays legible
    stain = np.zeros((h, w), np.float32)
    for cx, cy, rx, ry, s in ((8, 40, 7, 6, 0.20), (38, 58, 9, 6, 0.16),
                              (57, 26, 5, 8, 0.14)):
        stain = np.maximum(stain, s * patch(cx, cy, rx, ry))
    smudge = np.array([108.0, 91.0, 68.0], np.float32)
    col = col * (1.0 - stain[:, :, None]) + smudge * stain[:, :, None]

    col += rng.normal(0.0, 2.0, (h, w, 1))

    im = Image.fromarray(np.uint8(np.clip(col, 0, 255)), 'RGB')
    d = ImageDraw.Draw(im)
    # yarn nubs and loose fibres, low contrast
    for _ in range(46):
        x, y = rr.randrange(w), rr.randrange(h)
        ang = rr.uniform(0.0, 2.0 * math.pi)
        ln = rr.uniform(1.5, 6.0)
        _wrap_line(d, x, y, x + ln * math.cos(ang), y + ln * math.sin(ang),
                   rr.choice([(166, 148, 120), (132, 114, 89), (174, 156, 128),
                              (140, 121, 95)]), rr.choice((1, 1, 2)), w, h)
    return im


def grain():
    """SN_GRAIN: loose spilled grain, 64x64.

    Hundreds of soft rotated-ellipse kernels at random angles in one narrow
    golden-brown range; each carries a shallow contact shadow and a lit sliver.
    The only large-scale structure is a gentle periodic mottling, so a 48 unit
    pile reads as loose grain from any side with no big contrasting blotches,
    and the tile is seamless by construction.
    """
    w = h = 64
    rr = random.Random(2303)
    rng = np.random.default_rng(2303)

    mottle = _periodic_field(w, [(2, 1, 0.50), (1, 3, 0.34), (3, 2, 0.24),
                                 (4, 1, 0.14), (1, 5, 0.12), (5, 4, 0.07)], 2301)
    t = 0.44 + 0.30 * mottle + rng.normal(0.0, 0.030, (h, w)).astype(np.float32)
    t = np.clip(t, 0.0, 1.0)[:, :, None]
    dark = np.array([100.0, 77.0, 36.0], np.float32)
    mid = np.array([138.0, 110.0, 56.0], np.float32)
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    arr = np.broadcast_to(dark * (1.0 - t) + mid * t, (h, w, 3)).copy()

    def splat(cx, cy, a, b, ang, colour, alpha):
        """Soft rotated ellipse, seamless across the tile edges."""
        dxm = (X - cx + w / 2.0) % w - w / 2.0
        dym = (Y - cy + h / 2.0) % h - h / 2.0
        ca, sa = math.cos(ang), math.sin(ang)
        u = ca * dxm + sa * dym
        v = -sa * dxm + ca * dym
        m = np.clip(1.0 - (u / a) ** 2 - (v / b) ** 2, 0.0, 1.0) ** 0.55
        mask = m * alpha
        arr[:] = arr * (1.0 - mask[:, :, None]) + np.array(colour, np.float32) * mask[:, :, None]

    shadows = [(94, 71, 32), (108, 81, 38)]
    bodies = [(148, 116, 56), (164, 130, 64), (180, 144, 74), (134, 102, 48),
              (194, 158, 84)]
    lights = [(208, 174, 96), (222, 190, 112), (200, 164, 88)]

    # contact shadows, shallow: nothing may read as a large blotch
    for _ in range(360):
        cx, cy = rr.randrange(w), rr.randrange(h)
        ang = rr.uniform(0.0, math.pi)
        a, b = rr.uniform(1.2, 2.4), rr.uniform(0.7, 1.1)
        splat(cx + 0.8, cy + 0.8, a, b, ang, rr.choice(shadows), 0.40)
    # kernel bodies, all inside one narrow golden-brown range
    for _ in range(560):
        cx, cy = rr.randrange(w), rr.randrange(h)
        ang = rr.uniform(0.0, math.pi)
        a, b = rr.uniform(1.1, 2.6), rr.uniform(0.7, 1.2)
        splat(cx, cy, a, b, ang, rr.choice(bodies), 0.90)
    # a lit sliver on the upper-left of some kernels
    for _ in range(250):
        cx, cy = rr.randrange(w), rr.randrange(h)
        ang = rr.uniform(0.0, math.pi)
        a, b = rr.uniform(0.8, 1.8), rr.uniform(0.35, 0.55)
        splat(cx - 0.5 * math.sin(ang), cy - 0.5 * math.cos(ang),
              a, b, ang, rr.choice(lights), 0.55)
    # a few pale glume slivers lying on the heap
    for _ in range(22):
        cx, cy = rr.randrange(w), rr.randrange(h)
        ang = rr.uniform(0.0, math.pi)
        splat(cx, cy, rr.uniform(2.2, 3.4), 0.45, ang, (214, 184, 116), 0.45)
    return Image.fromarray(np.uint8(np.clip(arr, 0, 255)), 'RGB')


def door():
    """SN_DOOR: plank door with rails, diagonal brace and iron hardware, 64x128."""
    w, h = 64, 128
    im = noisy((97, 64, 38), 131, 7, (w, h))
    d = ImageDraw.Draw(im)
    rr = random.Random(132)
    # vertical planks (4 x 16 px)
    for x0 in range(0, w, 16):
        d.line((x0, 0, x0, h - 1), fill=(45, 28, 15), width=1)
        d.line((x0 + 1, 0, x0 + 1, h - 1), fill=(130, 89, 52), width=1)
        for _ in range(9):
            gx = x0 + rr.randrange(2, 15)
            y = rr.randrange(h)
            run = rr.randrange(10, 26)
            _wrap_line(d, gx, y, gx + rr.choice([-1, 0, 1]), y + run,
                       rr.choice([(78, 49, 27), (117, 78, 45), (141, 99, 58)]), 1, w, h)
    # diagonal brace behind the rails
    for i in range(7):
        d.line((6 + i, 100, 58 + i, 34), fill=(38, 24, 13))
    for i in range(6):
        d.line((6 + i, 98, 58 + i, 32), fill=(112, 75, 43))
    for i in range(5):
        d.line((6 + i, 97, 58 + i, 31), fill=(138, 97, 56))
    # horizontal rails
    for ry in (20, 98):
        d.rectangle((0, ry, w - 1, ry + 11), fill=(93, 61, 35))
        d.line((0, ry, w - 1, ry), fill=(154, 110, 64))
        d.line((0, ry + 1, w - 1, ry + 1), fill=(126, 87, 49))
        d.line((0, ry + 10, w - 1, ry + 10), fill=(48, 30, 16))
        d.line((0, ry + 11, w - 1, ry + 11), fill=(36, 22, 12))
        for nx in (5, 21, 37, 53):
            d.rectangle((nx, ry + 5, nx + 1, ry + 6), fill=(36, 34, 31))
            d.point((nx, ry + 5), fill=(146, 142, 132))
    # door frame shadow at the very edge
    d.rectangle((0, 0, w - 1, h - 1), outline=(58, 38, 22), width=1)
    # iron hinge straps on the left
    for hy in (24, 102):
        d.rectangle((0, hy, 15, hy + 4), fill=(45, 43, 41))
        d.line((1, hy + 1, 14, hy + 1), fill=(106, 103, 96))
        d.rectangle((2, hy + 1, 5, hy + 3), fill=(66, 64, 60))
        d.point((7, hy + 2), fill=(137, 133, 124))
    # handle / latch plate on the right
    d.rectangle((47, 58, 56, 71), fill=(48, 46, 43))
    d.rectangle((48, 59, 55, 70), fill=(70, 68, 63))
    d.ellipse((49, 61, 54, 66), fill=(31, 30, 28))
    d.ellipse((50, 62, 53, 65), fill=(122, 117, 106))
    d.line((55, 64, 62, 64), fill=(40, 38, 35), width=2)
    d.line((62, 64, 62, 70), fill=(40, 38, 35), width=2)
    d.point((62, 70), fill=(118, 113, 102))
    return im


def rock():
    """SN_ROCK: cave rock, 128x128, grey-brown.

    Irregular fracture facets (toroidal Voronoi) carry a per-facet height step,
    so each plane is lit on one side and falls into shadow on the other; the
    facet boundary itself is a dark crack.  Fractal noise roughens the planes,
    a little cool damp tint and a few drawn jagged cracks keep it readable at
    wall distance.  There is deliberately no masonry grid.
    """
    size = 128
    rng = np.random.default_rng(4101)
    rr = random.Random(4101)

    d1, d2, owner, pts = _voronoi(size, 26, rng)
    facet_h = rng.random(len(pts)).astype(np.float32)
    facet_tint = rng.normal(0.0, 11.0, (len(pts), 1)).astype(np.float32)
    plate = _periodic_noise(size, rng, octaves=5, base=4)
    height = facet_h[owner] * 1.80 + (plate - 0.5) * 0.65
    shade = _shade(height, 2.8)

    tone = _periodic_noise(size, rng, octaves=3, base=2)
    damp = _periodic_noise(size, rng, octaves=3, base=3)

    dark = np.array([64.0, 59.0, 53.0], np.float32)
    lite = np.array([132.0, 119.0, 100.0], np.float32)
    warm = np.array([112.0, 88.0, 68.0], np.float32)
    col = mix(dark, lite, 0.15 + 0.78 * tone)
    col = mix(col, warm, 0.32 * smooth((tone - 0.48) / 0.28))
    # every plane carries its own mineral tint
    col = col + facet_tint[owner]
    # per-plane relief
    col *= (0.74 + 0.52 * shade)[:, :, None]
    # crack network where two facets meet
    crack = np.exp(-(d2 - d1) / 1.35)
    col *= (1.0 - 0.55 * crack)[:, :, None]
    # slightly damp/cool patches, cave air
    col = mix(col, np.array([84.0, 90.0, 88.0], np.float32),
              0.18 * smooth((damp - 0.55) / 0.28))
    # fine mineral grain; low amplitude so the planes stay smooth
    col += rng.normal(0.0, 4.0, (size, size, 1))

    im = Image.fromarray(np.uint8(np.clip(col, 0, 255)), 'RGB')
    d = ImageDraw.Draw(im)
    # a few long jagged cracks continuing the facet seams, wrapped
    for _ in range(4):
        x, y = float(rr.randrange(size)), float(rr.randrange(size))
        ang = rr.uniform(0.0, 2.0 * math.pi)
        segments = rr.randrange(3, 6)
        step = rr.uniform(18.0, 34.0)
        for _ in range(segments):
            ang += rr.uniform(-0.9, 0.9)
            nx = x + step * math.cos(ang)
            ny = y + step * math.sin(ang)
            _wrap_line(d, x, y, nx, ny, (46, 41, 36), 2, size, size)
            _wrap_line(d, x + 2, y + 2, nx + 2, ny + 2, (92, 84, 71), 1, size, size)
            x, y = nx, ny
    # loose gravel and chipped highlights
    for _ in range(230):
        x, y = rr.randrange(size), rr.randrange(size)
        c = rr.choice([(134, 124, 108), (96, 89, 78), (146, 132, 112),
                       (70, 66, 60), (120, 104, 85)])
        d.rectangle((x, y, x + rr.choice((0, 0, 1)), y + rr.choice((0, 1))), fill=c)
    return im


def crystal():
    """SN_CRYSTAL: faceted pale blue/turquoise crystal, 64x64.

    Small irregular facets (about 10 px) each get their own flat cyan tone and
    a directional sheen; facet boundaries are a dark teal line plus a narrow
    near-white edge, so a crop of the sheet always reads as cut crystal rather
    than a cloud.  A handful of angular chips sit on top.  The scale is chosen
    for the 2..20 unit prisms used by the cave druses.
    """
    size = 64
    rng = np.random.default_rng(4201)
    rr = random.Random(4201)

    d1, d2, owner, pts = _voronoi(size, 26, rng)
    tones = np.array([[198, 232, 238], [160, 212, 224], [124, 186, 202],
                      [94, 160, 182], [70, 132, 156], [214, 242, 246],
                      [40, 88, 112], [140, 198, 214]], np.float32)
    pick = rng.integers(0, len(tones), len(pts))
    light = 0.72 + 0.48 * rng.random(len(pts)).astype(np.float32)
    col = tones[pick][owner].astype(np.float32) * light[owner][:, :, None]
    ramp = _facet_ramp(size, owner, pts, rr)
    col *= (0.88 + 0.20 * ramp)[:, :, None]

    edge = d2 - d1
    seam = np.exp(-edge / 0.50)
    col = mix(col, np.array([44.0, 84.0, 104.0], np.float32), 0.52 * seam)
    hi = np.exp(-edge / 0.95)
    col = mix(col, np.array([230.0, 249.0, 252.0], np.float32), 0.66 * hi)
    col += rng.normal(0.0, 3.0, (size, size, 1))

    im = Image.fromarray(np.uint8(np.clip(col, 0, 255)), 'RGB')
    d = ImageDraw.Draw(im)
    # two sparse cleavage families, low contrast: growth planes, not scratches
    for ang in (0.32, 1.92):
        for _ in range(2):
            x = rr.uniform(0, size)
            y = rr.uniform(0, size)
            length = rr.uniform(16.0, 26.0)
            x2 = x + length * math.cos(ang)
            y2 = y + length * math.sin(ang)
            _wrap_line(d, x, y, x2, y2, (92, 144, 164), 1, size, size)
            _wrap_line(d, x + 1, y + 1, x2 + 1, y2 + 1, (178, 214, 226), 1, size, size)
    # a few pale chipped faces: planes, not specks
    for _ in range(5):
        cx, cy = rr.uniform(0, size), rr.uniform(0, size)
        rad = rr.uniform(3.6, 6.0)
        ang = rr.uniform(0.0, 2.0 * math.pi)
        tri = [(cx + rad * math.cos(ang + k * 2.0 * math.pi / 3.0),
                cy + rad * math.sin(ang + k * 2.0 * math.pi / 3.0)) for k in range(3)]
        fill = rr.choice([(212, 240, 246), (196, 230, 240), (224, 246, 250)])
        for ox in (-size, 0, size):
            for oy in (-size, 0, size):
                d.polygon([(x + ox, y + oy) for x, y in tri], fill=fill,
                          outline=(116, 168, 188))
    return im


def hell():
    """SN_HELL: dark red baked rock, 128x128.

    Charred red-brown crust over black fracture cracks, with a few smouldering
    orange veins that follow the crack network only where a low-frequency gate
    allows.  Nothing is painted as a bright fill: the hottest vein is about
    (206, 108, 28), so the surface still depends on the map's light and never
    looks like an unlit fullbright panel.
    """
    size = 128
    rng = np.random.default_rng(4301)
    rr = random.Random(4301)

    d1, d2, owner, pts = _voronoi(size, 22, rng)
    crust_h = rng.random(len(pts)).astype(np.float32)
    grit = _periodic_noise(size, rng, octaves=5, base=4)
    height = crust_h[owner] * 1.10 + (grit - 0.5) * 0.40
    shade = _shade(height, 3.0)

    tone = _periodic_noise(size, rng, octaves=4, base=2)
    soot = _periodic_noise(size, rng, octaves=4, base=6)

    dark = np.array([30.0, 15.0, 14.0], np.float32)
    red = np.array([104.0, 36.0, 26.0], np.float32)
    crust = np.array([48.0, 26.0, 23.0], np.float32)
    col = mix(dark, red, 0.18 + 0.74 * tone)
    col = mix(col, crust, 0.35 * smooth((soot - 0.50) / 0.25))
    col *= (0.72 + 0.50 * shade)[:, :, None]

    crack = np.exp(-(d2 - d1) / 1.70)
    col *= (1.0 - 0.78 * crack)[:, :, None]

    gate = _periodic_noise(size, rng, octaves=4, base=3)
    glow_mask = smooth((gate - 0.42) / 0.15)
    glow = np.exp(-(d2 - d1) / 1.05) * glow_mask
    hot = mix(np.array([152.0, 58.0, 16.0], np.float32),
              np.array([208.0, 112.0, 30.0], np.float32),
              smooth((grit - 0.35) / 0.55))
    col = col * (1.0 - 0.92 * glow)[:, :, None] + hot * (0.92 * glow)[:, :, None]
    # a thin hotter core inside the veins; still far below white
    filament = np.exp(-(d2 - d1) / 0.45) * glow_mask
    col = (col * (1.0 - 0.85 * filament)[:, :, None]
           + np.array([224.0, 126.0, 36.0], np.float32) * (0.85 * filament)[:, :, None])
    col += rng.normal(0.0, 2.6, (size, size, 1))

    im = Image.fromarray(np.uint8(np.clip(col, 0, 255)), 'RGB')
    d = ImageDraw.Draw(im)
    # embers inside the crust and a little pale ash
    for _ in range(70):
        x, y = rr.randrange(size), rr.randrange(size)
        c = rr.choice([(176, 74, 20), (150, 58, 16), (120, 44, 14)])
        _wrapped_point(d, x, y, c, size)
    for _ in range(45):
        x, y = rr.randrange(size), rr.randrange(size)
        _wrapped_point(d, x, y, rr.choice([(86, 74, 66), (70, 60, 54)]), size)
    return im


def lava():
    """SN_LAVA: molten orange mass under a dark crust, 64x64.

    Dark crust plates are separated by glowing seams: the seam core is
    yellow-orange (up to 238, 180, 64) and falls off into orange and then the
    crust, with a second, finer fracture network inside each plate.  Peak
    values are capped below white; the glow belongs to the map lights, the
    texture only supplies hot colour.
    """
    size = 64
    rng = np.random.default_rng(4401)
    rr = random.Random(4401)

    d1, d2, owner, pts = _voronoi(size, 13, rng)
    plate_h = rng.random(len(pts)).astype(np.float32)
    fbm = _periodic_noise(size, rng, octaves=5, base=4)
    height = plate_h[owner] * 1.30 + (fbm - 0.5) * 0.45
    shade = _shade(height, 3.4)

    tone = _periodic_noise(size, rng, octaves=4, base=2)
    crust = mix(np.array([40.0, 24.0, 21.0], np.float32),
                np.array([82.0, 44.0, 31.0], np.float32), 0.22 + 0.62 * tone)
    crust = mix(crust, np.array([28.0, 18.0, 17.0], np.float32),
                0.40 * smooth((fbm - 0.55) / 0.25))
    crust *= (0.78 + 0.45 * shade)[:, :, None]

    edge = d2 - d1
    # the seam width is not constant: some cracks are wide molten channels,
    # others are thin cooling lines, so the network never reads as a net
    gate = _periodic_noise(size, rng, octaves=3, base=2)
    gate_s = smooth((gate - 0.15) / 0.55)
    width = 1.7 + 3.2 * gate_s
    molten = smooth((width - edge) / np.maximum(width, 0.8))
    core = np.exp(-edge / (0.55 + 1.10 * gate_s))
    hot = mix(np.array([188.0, 78.0, 14.0], np.float32),
              np.array([238.0, 180.0, 64.0], np.float32),
              smooth((core - 0.10) / 0.75))
    col = crust * (1.0 - molten)[:, :, None] + hot * molten[:, :, None]

    # finer fractures inside the plates, dark and mostly cooled
    d1b, d2b, owner_b, _ = _voronoi(size, 34, rng)
    frac = np.exp(-(d2b - d1b) / 0.70) * (1.0 - molten)
    col *= (1.0 - 0.45 * frac)[:, :, None]
    # dying ember patches inside the crust
    ember = 0.30 * smooth((fbm - 0.62) / 0.18) * (1.0 - molten)
    col = mix(col, np.array([132.0, 52.0, 18.0], np.float32), ember)

    col += rng.normal(0.0, 2.2, (size, size, 1))
    # never reach paper-white; the room lighting supplies the brightness
    col = np.minimum(col, np.float32(238.0))

    im = Image.fromarray(np.uint8(np.clip(col, 0, 255)), 'RGB')
    d = ImageDraw.Draw(im)
    # a few bright spatter points on the molten channels
    for _ in range(26):
        x, y = rr.randrange(size), rr.randrange(size)
        _wrapped_point(d, x, y, rr.choice([(236, 192, 84), (228, 152, 44),
                                           (238, 204, 100)]), size)
    return im


def quantize(im, colors=256):
    idx = im.convert('RGB').quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                                     dither=Image.Dither.NONE)
    # normalise to a full 768-byte palette so PNG and WAD carry the same table
    pal = (idx.getpalette() or [])[:768]
    pal += [0] * (768 - len(pal))
    idx.putpalette(pal)
    return idx


def index_name(name):
    """Filesystem-safe preview name ('{' is illegal on Windows)."""
    return name.replace('{', '(')


TEXTURES = [
    ('SN_WHEAT', wheat()),
    ('SN_DIRT', noisy((133, 109, 70), 17, 13)),
    ('SN_WOOD', wood()),
    ('SN_STONE', stone()),
    ('SN_TILE', stone(True)),
    ('SN_TRAMP', tramp()),
    ('SN_GOLD', gold()),
    ('SN_TRIM', trim()),
    ('SN_BARN', barn()),
    ('SN_BEAM', beam()),
    ('SN_HAY', hay()),
    ('SN_DOOR', door()),
    ('SN_SACK', sack()),
    ('SN_GRAIN', grain()),
    ('SN_ROCK', rock()),
    ('SN_CRYSTAL', crystal()),
    ('SN_HELL', hell()),
    ('SN_LAVA', lava()),
]

INDEXED = {}
for name, im in TEXTURES:
    idx = quantize(im)
    INDEXED[name] = idx
    idx.save(ROOT / 'textures' / f'{index_name(name)}.png')


# ----------------------------------------------------------------------------
# WAD3
# ----------------------------------------------------------------------------
def wad3(textures, filename):
    data = bytearray(b'WAD3' + struct.pack('<ii', len(textures), 0))
    entries = []
    for name, idx in textures.items():
        w, h = idx.size
        pal = (idx.getpalette() or [])[:768]
        pal += [0] * (768 - len(pal))
        mips = []
        for level in range(4):
            mw, mh = w >> level, h >> level
            if mw < 1 or mh < 1:
                break
            reduced = idx.convert('RGB').resize((mw, mh), Image.Resampling.LANCZOS)
            mapped = np.array(reduced.quantize(palette=idx, dither=Image.Dither.NONE),
                              dtype=np.uint8)
            mips.append(mapped.tobytes())
        offsets = []
        cursor = 40
        for mip in mips:
            offsets.append(cursor)
            cursor += len(mip)
        raw = struct.pack('<16s6I', name.encode('ascii'), w, h, *offsets)
        raw += b''.join(mips) + struct.pack('<H', 256) + bytes(pal) + b'\0\0'
        offset = len(data)
        data.extend(raw)
        entries.append((offset, len(raw), name))
    directory = len(data)
    for offset, length, name in entries:
        data.extend(struct.pack('<iiiBBBB16s', offset, length, length, 0x43, 0, 0, 0,
                                name.encode('ascii')))
    struct.pack_into('<i', data, 8, directory)
    filename.write_bytes(data)


# ----------------------------------------------------------------------------
# Contact sheets
# ----------------------------------------------------------------------------
def _label(d, xy, text):
    try:
        font = ImageFont.truetype('arial.ttf', 12)
    except OSError:
        font = ImageFont.load_default()
    d.text(xy, text, fill=(245, 245, 240), font=font)


def texture_contact():
    cell_w, cell_h, label_h = 150, 170, 18
    cols = 4
    rows = (len(TEXTURES) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell_w, rows * cell_h), (34, 30, 26))
    d = ImageDraw.Draw(sheet)
    for i, (name, idx) in enumerate(INDEXED.items()):
        cx = (i % cols) * cell_w
        cy = (i // cols) * cell_h
        rgb = idx.convert('RGB')
        scale = min(128 / rgb.width, 128 / rgb.height)
        tw, th = max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale))
        rgb = rgb.resize((tw, th), Image.Resampling.NEAREST)
        sheet.paste(rgb, (cx + (cell_w - tw) // 2, cy + label_h + (128 - th) // 2))
        _label(d, (cx + 6, cy + 3), f'{name} {idx.width}x{idx.height}')
    sheet.save(ROOT / 'texture_contact.png')


def sky_contact():
    order = ['rt', 'bk', 'lf', 'ft', 'up', 'dn']
    sheet = Image.new('RGB', (3 * 256, 2 * 256), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, face in enumerate(order):
        im = Image.open(ROOT / 'skybox_preview' / f'yz_senowheat{face}.png').convert('RGB')
        sheet.paste(im, ((i % 3) * 256, (i // 3) * 256))
        _label(d, ((i % 3) * 256 + 6, (i // 3) * 256 + 4), face)
    sheet.save(ROOT / 'sky_contact.png')


make_sky()
wad3({name: INDEXED[name] for name, _ in TEXTURES}, OUT / 'yz_seno_wheat.wad')
texture_contact()
sky_contact()

print('WAD:', OUT / 'yz_seno_wheat.wad', 'textures:', len(TEXTURES), ', '.join(n for n, _ in TEXTURES))
print('Skybox:', ENV / 'yz_senowheat{rt,lf,ft,bk,up,dn}.tga')
print('Sun direction (elevation %.1f deg, azimuth %.1f deg): (%.4f, %.4f, %.4f)'
      % (SUN_ELEVATION, SUN_AZIMUTH, *SUN))





