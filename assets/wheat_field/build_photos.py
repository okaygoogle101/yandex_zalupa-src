"""Append meme photos and a credits plaque to the map WAD as 8-bit textures."""
import os, struct, math, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# project root is two levels above assets/wheat_field
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# photos are not shipped with the repository; pass a folder or use assets/photos
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "photos")
WAD = os.path.join(ROOT, "dist", "cstrike", "yz_seno_wheat.wad")
SIZE = 256
LETTERBOX = (18, 16, 16)


def read_wad(path):
    b = open(path, "rb").read()
    assert b[:4] == b"WAD3"
    n, off = struct.unpack_from("<ii", b, 4)
    lumps = []
    for i in range(n):
        fp, ds, sz, typ, comp, pad, name = struct.unpack_from("<iiiBBH16s", b, off + i * 32)
        lumps.append((name.split(b"\x00")[0].decode("ascii"), b[fp:fp + ds]))
    return lumps


def make_mips(rgb):
    p = rgb.convert("P", palette=Image.ADAPTIVE, colors=256)
    mips = [rgb]
    for s in (128, 64, 32):
        mips.append(rgb.resize((s, s), Image.LANCZOS))
    data = [np.asarray(p, dtype=np.uint8).tobytes()]
    for m in mips[1:]:
        q = m.quantize(palette=p, dither=Image.Dither.NONE)
        data.append(np.asarray(q, dtype=np.uint8).tobytes())
    pal = p.getpalette()[:768]
    pal += [0] * (768 - len(pal))
    return data, pal


def lump(name, rgb):
    data, pal = make_mips(rgb)
    offsets = []
    pos = 40
    for d in data:
        offsets.append(pos)
        pos += len(d)
    head = name.encode("ascii").ljust(16, b"\x00")
    head += struct.pack("<ii", SIZE, SIZE)
    head += struct.pack("<4i", *offsets)
    body = b"".join(data)
    return head + body + struct.pack("<H", 256) + bytes(pal)


def fit_photo(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(SIZE / w, SIZE / h)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (SIZE, SIZE), LETTERBOX)
    canvas.paste(im, ((SIZE - nw) // 2, (SIZE - nh) // 2))
    return canvas


def credits():
    # dark stone plaque with a double gold frame, warm serif lettering
    rng = np.random.default_rng(7)
    base = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    base[:] = (38, 33, 30)
    noise = rng.normal(0, 6, (SIZE, SIZE, 1))
    base += noise
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    vig = np.clip(1.0 - (((xx - 128) ** 2 + (yy - 128) ** 2) ** 0.5) / 210.0, 0.55, 1.0)
    base *= vig[..., None]
    im = Image.fromarray(np.uint8(np.clip(base, 0, 255)), "RGB")
    d = ImageDraw.Draw(im)
    gold = (198, 160, 92)
    pale = (238, 226, 198)
    d.rectangle([6, 6, 249, 249], outline=gold, width=3)
    d.rectangle([13, 13, 242, 242], outline=(120, 96, 56), width=1)
    font_path = r"C:\Windows\Fonts\georgiab.ttf"
    if not os.path.exists(font_path):
        font_path = r"C:\Windows\Fonts\timesbd.ttf"
    if not os.path.exists(font_path):
        font_path = r"C:\Windows\Fonts\arialbd.ttf"

    def fit_font(text, max_w, start):
        size = start
        while size > 9:
            f = ImageFont.truetype(font_path, size)
            box = d.textbbox((0, 0), text, font=f)
            if box[2] - box[0] <= max_w:
                return f
            size -= 1
        return ImageFont.truetype(font_path, size)

    lines = [("MAP BY", 20, (206, 186, 146)),
             ("okay_google", 40, pale),
             ("& DeepSeek", 28, pale),
             ("V4.1 Flash", 28, pale)]
    total = 0
    rendered = []
    for text, start, colour in lines:
        f = fit_font(text, 206, start)
        box = d.textbbox((0, 0), text, font=f)
        h = box[3] - box[1]
        rendered.append((text, f, colour, h))
        total += h + 10
    y = (SIZE - total) // 2 + 6
    for text, f, colour, h in rendered:
        d.text((SIZE // 2, y), text, font=f, fill=colour, anchor="ma")
        y += h + 10
    d.text((SIZE // 2, 226), "yandex_zalupa", font=ImageFont.truetype(font_path, 14),
           fill=(150, 132, 100), anchor="ma")
    return im


def main():
    lumps = read_wad(WAD)
    have = {n for n, _ in lumps}
    photos = sorted([f for f in os.listdir(SRC) if os.path.isfile(os.path.join(SRC, f))],
                    key=lambda s: int("".join(c for c in s if c.isdigit())))
    assert len(photos) == 21, photos
    for i, f in enumerate(photos, 1):
        name = f"YZ_PHOTO_{i:02d}"
        if name in have:
            continue
        lumps.append((name, lump(name, fit_photo(os.path.join(SRC, f)))))
    if "YZ_CREDITS" not in have:
        lumps.append(("YZ_CREDITS", lump("YZ_CREDITS", credits())))

    out = bytearray(b"WAD3")
    out += struct.pack("<ii", len(lumps), 0)
    entries = []
    for name, data in lumps:
        while len(out) % 4:
            out += b"\x00"
        pos = len(out)
        out += data
        entries.append((pos, len(data), name))
    while len(out) % 4:
        out += b"\x00"
    diroff = len(out)
    for pos, size, name in entries:
        out += struct.pack("<iiiBBH16s", pos, size, size, 0x43, 0, 0,
                           name.encode("ascii").ljust(16, b"\x00"))
    struct.pack_into("<ii", out, 4, len(lumps), diroff)
    open(WAD, "wb").write(out)
    print("wad written", len(lumps), "textures", len(out), "bytes")
    for name, _ in lumps[-6:]:
        print(" ", name)


if __name__ == "__main__":
    main()
