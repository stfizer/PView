"""Generate the P view app icon (Win11 style rounded square with a P)."""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets")
os.makedirs(OUT, exist_ok=True)


def make(size: int) -> Image.Image:
    S = 4  # supersample
    n = size * S
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # gradient background (deep blue -> lighter azure)
    top = (31, 100, 255)
    bot = (0, 153, 241)
    grad = Image.new("RGBA", (n, n))
    gd = ImageDraw.Draw(grad)
    for y in range(n):
        t = y / max(1, n - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        gd.line([(0, y), (n, y)], fill=(r, g, b, 255))
    # rounded mask
    mask = Image.new("L", (n, n), 0)
    md = ImageDraw.Draw(mask)
    radius = int(n * 0.22)
    md.rounded_rectangle([0, 0, n - 1, n - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)
    # letter P
    font = None
    for fp in (r"C:\Windows\Fonts\segoeuib.ttf",
               r"C:\Windows\Fonts\segoeui.ttf",
               r"C:\Windows\Fonts\arialbd.ttf"):
        if os.path.exists(fp):
            font = ImageFont.truetype(fp, int(n * 0.62))
            break
    if font is None:
        font = ImageFont.load_default()
    text = "P"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (n - tw) / 2 - bbox[0]
    y = (n - th) / 2 - bbox[1] - n * 0.02
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = {s: make(s) for s in sizes}
ico_path = os.path.join(OUT, "pview.ico")
imgs[256].save(ico_path, format="ICO",
               sizes=[(s, s) for s in sizes])
imgs[256].save(os.path.join(OUT, "pview.png"), format="PNG")
print("icon written:", ico_path)
