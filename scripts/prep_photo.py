"""
Prepare the dp (a flat illustration) for clean ASCII conversion:
  1. isolate the subject (PNG alpha if present, else rembg)
  2. CLAHE for local contrast, then bilateral-smooth away the paper texture
     while keeping the drawn lines sharp
  3. stretch tones over the subject only
  4. sharpen the line work (difference-of-gaussians): dark strokes (eyelids,
     pupils, glasses frame, smile) are pushed darker and bright strands (hair
     highlights) lighter, so both survive ascii resolution
  5. crop square around the head and shoulders (the bottom of the hoodie is
     dropped so the face gets more of the frame)

Output: data/source-prepped.png, grayscale + alpha (the alpha keeps the
background blank in make_ascii_svg.py).

    python scripts/prep_photo.py [input.png] [output.png]
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
INP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "source-photo.png")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "data", "source-prepped.png")

CLAHE = 2.0           # local contrast clip limit
LINE_WEIGHT = 0.8     # how hard dark strokes are pushed toward black
HIGHLIGHT = 0.5       # how hard bright strands are pushed toward white
CROP = 0.88           # keep this fraction of the subject's height, from the top

# 1. cut out the subject
cut = Image.open(INP).convert("RGBA")
if np.array(cut.split()[-1]).min() > 250:        # no transparency -> remove bg
    from rembg import remove
    cut = remove(cut)
rgb = np.array(cut.convert("RGB"))
alpha = np.array(cut.split()[-1])                 # 0 = background
gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

# 2. local contrast, then smooth texture but keep edges
gray = cv2.createCLAHE(clipLimit=CLAHE, tileGridSize=(8, 8)).apply(gray)
smooth = gray
for _ in range(3):
    smooth = cv2.bilateralFilter(smooth, 9, 40, 9)

# 3. tone stretch over the subject only
lo, hi = np.percentile(smooth[alpha > 128], [3, 99])
tone = np.clip((smooth.astype(np.float32) - lo) / (hi - lo), 0, 1)

# 4. dark ridges -> darker, bright ridges -> brighter
fine = cv2.GaussianBlur(smooth, (0, 0), 1.5).astype(np.float32)
coarse = cv2.GaussianBlur(smooth, (0, 0), 6).astype(np.float32)
dark_lines = np.clip((coarse - fine) / 40.0, 0, 1)
bright_lines = np.clip((fine - coarse) / 30.0, 0, 1)
out = np.clip(tone - LINE_WEIGHT * dark_lines + HIGHLIGHT * bright_lines, 0, 1) * 255

# 5. square crop around head + shoulders
ys, xs = np.where(alpha > 20)
top = ys.min()
bot = int(top + (ys.max() - top) * CROP)
side = max(xs.max() - xs.min(), bot - top) + 40
cx, cy = (xs.min() + xs.max()) // 2, (top + bot) // 2
x0, y0 = cx - side // 2, cy - side // 2
sx0, sy0 = max(x0, 0), max(y0, 0)
sx1, sy1 = min(x0 + side, out.shape[1]), min(y0 + side, out.shape[0], bot)

img = np.zeros((side, side), np.uint8)
mask = np.zeros((side, side), np.uint8)
img[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = out[sy0:sy1, sx0:sx1].astype(np.uint8)
mask[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = alpha[sy0:sy1, sx0:sx1]

os.makedirs(os.path.dirname(OUT), exist_ok=True)
Image.fromarray(np.dstack([img, mask]), mode="LA").save(OUT)
print("wrote", OUT, img.shape)
