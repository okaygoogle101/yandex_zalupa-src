import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
im = Image.open(os.path.join(ROOT, "reference_giant.jpg")).convert("L").crop((10, 8, 721, 566))
L = np.asarray(im, dtype=np.float32); h, w = L.shape
poly = [(360,5),(435,35),(450,95),(520,140),(610,170),(700,190),(715,255),(640,285),
        (560,245),(540,300),(610,360),(630,450),(600,520),(500,555),(300,558),(170,540),
        (120,460),(150,360),(230,300),(210,250),(120,270),(30,250),(15,190),(120,150),
        (230,120),(290,60)]
pm = Image.new("L", (w,h), 0); ImageDraw.Draw(pm).polygon(poly, fill=255)
pm = pm.filter(ImageFilter.GaussianBlur(8))
P = np.asarray(pm, dtype=np.float32)/255.0
density = np.clip(1.0 - L/255.0, 0.0, 1.0) ** 1.15
density *= P
yy,xx = np.mgrid[0:h,0:w]
density[(yy>455)&(xx>480)] = 0.0   # the standing man
density[yy>548] = 0.0              # ground line
d_img = Image.fromarray((np.clip(density,0,1)*255).astype(np.uint8),"L").filter(ImageFilter.GaussianBlur(1.0))
density = np.asarray(d_img,dtype=np.float32)/255.0
np.save(os.path.join(ROOT,"giant_density.npy"), density)
np.save(os.path.join(ROOT,"giant_shape.npy"), P)
Image.fromarray((density*255).astype(np.uint8),"L").save(os.path.join(ROOT,"giant_density.png"))
print("mean", round(float(density.mean()),3), "max", round(float(density.max()),3))


