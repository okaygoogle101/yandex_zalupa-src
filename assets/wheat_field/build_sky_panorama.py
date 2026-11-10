import numpy as np, math, os
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, "assets", "wheat_field")
ENV = os.path.join(ROOT, "dist", "cstrike", "gfx", "env")
PREV = os.path.join(ASSETS, "skybox_preview")
SIZE = 256

# --- panorama: rotate so its sun sits at azimuth 30 deg --------------------
pano = Image.open(os.path.join(ASSETS, "sky_panorama_imagegen.png")).convert("RGB")
W0, H0 = pano.size
sun_frac = 1235.0 / 1774.0
shift = int(round((30.0 / 360.0 - sun_frac) * W0))
arr = np.roll(np.asarray(pano, dtype=np.float32), shift, axis=1)
pano = Image.fromarray(np.uint8(np.clip(arr, 0, 255)), "RGB").resize((2048, 1024), Image.LANCZOS)
PW, PH = pano.size
P = np.asarray(pano, dtype=np.float32)

# --- figure: soft silhouette + interior shading ----------------------------
DENS = np.load(os.path.join(ASSETS, "giant_density.npy"))
SHAPE = np.load(os.path.join(ASSETS, "giant_shape.npy"))
GH, GW = DENS.shape
GIANT_AZ = 2.20
EL_TOP, EL_BOT, DU_HALF = 0.56, -0.14, 0.62

def sample_pano(az, el):
    u = (az / (2.0 * np.pi)) % 1.0
    v = np.clip(0.5 - el / np.pi, 0.0, 1.0)
    x = u * (PW - 1); y = v * (PH - 1)
    x0 = np.floor(x).astype(np.int32); y0 = np.floor(y).astype(np.int32)
    x1 = (x0 + 1) % PW; y1 = np.minimum(y0 + 1, PH - 1)
    fx = (x - x0)[..., None]; fy = (y - y0)[..., None]
    c00 = P[y0, x0]; c10 = P[y0, x1]; c01 = P[y1, x0]; c11 = P[y1, x1]
    return (c00 * (1 - fx) + c10 * fx) * (1 - fy) + (c01 * (1 - fx) + c11 * fx) * fy

def sample_map(a, az, el):
    da = np.arctan2(np.sin(az - GIANT_AZ), np.cos(az - GIANT_AZ))
    du = np.cos(np.clip(el, -1.5, 1.5)) * da
    u = (du + DU_HALF) / (2.0 * DU_HALF) * (GW - 1)
    v = (EL_TOP - el) / (EL_TOP - EL_BOT) * (GH - 1)
    inside = (u >= 0) & (u <= GW - 1) & (v >= 0) & (v <= GH - 1)
    u = np.clip(u, 0, GW - 1.001); v = np.clip(v, 0, GH - 1.001)
    i0 = u.astype(np.int32); j0 = v.astype(np.int32)
    fu = u - i0; fv = v - j0
    s = ((a[j0, i0] * (1 - fu) + a[j0, i0 + 1] * fu) * (1 - fv)
         + (a[j0 + 1, i0] * (1 - fu) + a[j0 + 1, i0 + 1] * fu) * fv)
    uu = u / (GW - 1); vv = v / (GH - 1)
    fade = np.clip(np.minimum(np.minimum(uu, 1 - uu), np.minimum(vv, 1 - vv)) / 0.06, 0, 1)
    fade = fade * fade * (3 - 2 * fade)
    return np.where(inside, s * fade, 0.0)

def face_dirs(face):
    s, t = np.meshgrid(np.linspace(-1, 1, SIZE), np.linspace(1, -1, SIZE))
    one = np.ones_like(s)
    return {"rt": (one, -s, t), "lf": (-one, s, t), "bk": (s, one, t),
            "ft": (-s, -one, t), "up": (-t, -s, one), "dn": (t, -s, -one)}[face]

for face in ["rt", "lf", "ft", "bk", "up", "dn"]:
    x, y, z = (v.astype(np.float32) for v in face_dirs(face))
    n = np.sqrt(x * x + y * y + z * z)
    x, y, z = x / n, y / n, z / n
    az = np.arctan2(y, x); el = np.arcsin(np.clip(z, -1, 1))
    col = sample_pano(az, el)
    shape = np.clip(sample_map(SHAPE, az, el), 0.0, 1.0)
    dens = np.clip(sample_map(DENS, az, el), 0.0, 1.0)
    # solid warm-grey figure, lit from above and from the sun side
    t = np.clip((el + 0.08) / 0.62, 0.0, 1.0)
    lit = np.array([158.0, 140.0, 122.0], dtype=np.float32)
    shade = np.array([78.0, 70.0, 66.0], dtype=np.float32)
    body = shade * (1.0 - t)[..., None] + lit * t[..., None]
    body = body * (1.0 - 0.58 * (dens[..., None] ** 1.05))
    sun_dot = np.clip(x * 0.7094 + y * 0.4096 + z * 0.5736, -1.0, 1.0)
    prox = np.exp(-((np.arccos(sun_dot) / 0.55) ** 2))
    rim = np.clip(4.0 * shape * (1.0 - shape), 0.0, 1.0) * prox
    body = body + rim[..., None] * np.array([46.0, 30.0, 12.0], dtype=np.float32)
    _sb = np.asarray(Image.fromarray((shape * 255).astype(np.uint8), "L")
                     .filter(ImageFilter.GaussianBlur(4)), dtype=np.float32) / 255.0
    outline = np.clip(shape - _sb, 0.0, 1.0)
    body = body * (1.0 - 0.55 * outline[..., None])
    a = shape[..., None]
    col = col * (1.0 - a) + body * a
    im = Image.fromarray(np.uint8(np.clip(col, 0, 255)), "RGB")
    im.save(os.path.join(ENV, f"senowheat{face}.tga"), compression=None)
    im.save(os.path.join(PREV, f"senowheat{face}.png"))
print("sky written")


