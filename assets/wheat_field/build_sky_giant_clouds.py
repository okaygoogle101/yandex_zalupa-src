"""Skybox from the panorama with the cloud giant rebuilt from the drawing.

The figure is not painted as a grey mass.  Light areas of the reference become a
dense warm-white cloud body, dark strokes (face, chain, folds) stay as crisp
graphics on top.  Both are masked by a soft polygon so the standing man and the
ground line never enter the sky.
"""
import numpy as np, math, os
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, "assets", "wheat_field")
ENV = os.path.join(ROOT, "dist", "cstrike", "gfx", "env")
PREV = os.path.join(ASSETS, "skybox_preview")
SIZE = 256

# --- panorama, rotated so its sun sits at azimuth 30 deg -------------------
pano = Image.open(os.path.join(ASSETS, "sky_panorama_imagegen.png")).convert("RGB")
W0, H0 = pano.size
sun_frac = 1235.0 / 1774.0
shift = int(round((30.0 / 360.0 - sun_frac) * W0))
arr = np.roll(np.asarray(pano, dtype=np.float32), shift, axis=1)
pano = Image.fromarray(np.uint8(np.clip(arr, 0, 255)), "RGB").resize((2048, 1024), Image.LANCZOS)
PW, PH = pano.size
P = np.asarray(pano, dtype=np.float32)

# --- the drawing -----------------------------------------------------------
ref = Image.open(os.path.join(ASSETS, "reference_giant.jpg")).convert("L").crop((10, 8, 721, 566))
L = np.asarray(ref, dtype=np.float32)
GH, GW = L.shape
poly = [(360,5),(435,35),(450,95),(520,140),(610,170),(700,190),(715,255),(640,285),
        (560,245),(540,300),(610,360),(630,450),(600,520),(500,555),(300,558),(170,540),
        (120,460),(150,360),(230,300),(210,250),(120,270),(30,250),(15,190),(120,150),
        (230,120),(290,60)]
pm = Image.new("L", (GW, GH), 0)
ImageDraw.Draw(pm).polygon(poly, fill=255)
pm = pm.filter(ImageFilter.GaussianBlur(6))
POLY = np.asarray(pm, dtype=np.float32) / 255.0
# remove the standing man and the ground line entirely
yy, xx = np.mgrid[0:GH, 0:GW]
_bottom = np.clip((520.0 - yy) / 70.0, 0.0, 1.0)
_bottom = _bottom * _bottom * (3.0 - 2.0 * _bottom)
POLY = POLY * _bottom
_man = np.sqrt((yy - 515.0) ** 2 + (xx - 560.0) ** 2)
POLY = POLY * np.clip((_man - 45.0) / 35.0, 0.0, 1.0)
POLY[(yy > 470) & (xx > 430)] = 0.0

# body: light cloud, alpha grows with brightness; detail: dark strokes on top
BODY = np.clip((L - 138.0) / 82.0, 0.0, 1.0) ** 0.85 * POLY
_b = Image.fromarray((np.clip(BODY, 0, 1) * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(2))
BODY = np.asarray(_b, dtype=np.float32) / 255.0
DETAIL = np.clip((128.0 - L) / 72.0, 0.0, 1.0) ** 0.80 * POLY

GIANT_AZ = 2.20
EL_TOP, EL_BOT, DU_HALF = 0.62, -0.12, 0.66

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
    body = np.clip(sample_map(BODY, az, el), 0.0, 1.0)
    detail = np.clip(sample_map(DETAIL, az, el), 0.0, 1.0)
    # body: warm white cumulus, slightly shaded by elevation
    t = np.clip((el + 0.10) / 0.72, 0.0, 1.0)
    cream = np.array([255.0, 249.0, 238.0], dtype=np.float32)
    shade = np.array([206.0, 204.0, 204.0], dtype=np.float32)
    body_col = shade * (1.0 - t)[..., None] + cream * t[..., None]
    body_col = body_col * (0.88 + 0.12 * body[..., None])
    a_body = (0.97 * body)[..., None]
    col = col * (1.0 - a_body) + body_col * a_body
    # graphics: dark strokes of the drawing, crisp and not blurred
    ink = np.array([58.0, 55.0, 58.0], dtype=np.float32)
    a_ink = (0.88 * detail)[..., None]
    col = col * (1.0 - a_ink) + ink * a_ink
    im = Image.fromarray(np.uint8(np.clip(col, 0, 255)), "RGB")
    im.save(os.path.join(ENV, f"yz_senowheat{face}.tga"), compression=None)
    im.save(os.path.join(PREV, f"yz_senowheat{face}.png"))
print("sky written")


