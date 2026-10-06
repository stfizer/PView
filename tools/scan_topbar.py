"""Scan topbar button positions in click_0_initial.png (bright pixel columns)."""
from PIL import Image

im = Image.open(r"F:\workbuddy空间任务\图片查看器\PView\docs\verify_out\click_0_initial.png").convert("L")
w, h = im.size
print("size", w, h)
px = im.load()

# topbar occupies PNG y in [8, 54] (8px invisible top border + CAPTION_H 46)
# scan a horizontal band around button-icon rows
for y in (24, 28, 31, 34):
    runs = []
    start = None
    for x in range(w - 1, w - 400, -1):
        bright = px[x, y] > 120
        if bright and start is None:
            start = x
        elif not bright and start is not None:
            runs.append((start, x))
            start = None
    print(f"y={y}: bright runs (from right): {runs[:14]}")
