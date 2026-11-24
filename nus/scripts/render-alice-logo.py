from math import hypot
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
SIZE = 768
C = SIZE / 2

base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse((84, 84, SIZE-84, SIZE-84), fill=(18, 216, 230, 135))
glow = glow.filter(ImageFilter.GaussianBlur(38))
base.alpha_composite(glow)

disc = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
pix = disc.load()
for y in range(SIZE):
    for x in range(SIZE):
        dx, dy = x - C, y - C
        r = hypot(dx, dy)
        if r <= 326:
            light = max(0.0, 1 - hypot(x-250, y-210) / 600)
            pix[x, y] = (int(4 + 5*light), int(17 + 32*light), int(26 + 39*light), 255)
base.alpha_composite(disc)

draw = ImageDraw.Draw(base)
draw.ellipse((C-328, C-328, C+328, C+328), outline=(48, 222, 232, 245), width=9)
draw.ellipse((C-276, C-276, C+276, C+276), outline=(121, 245, 242, 110), width=3)

mark_glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
mg = ImageDraw.Draw(mark_glow)
mg.line([(252, 522), (384, 228), (516, 522)], fill=(91, 248, 250, 210), width=38, joint="curve")
mg.line([(307, 425), (461, 425)], fill=(91, 248, 250, 210), width=34)
base.alpha_composite(mark_glow.filter(ImageFilter.GaussianBlur(24)))
draw = ImageDraw.Draw(base)
draw.line([(252, 522), (384, 228), (516, 522)], fill=(185, 255, 255, 255), width=29, joint="curve")
draw.line([(307, 425), (461, 425)], fill=(185, 255, 255, 255), width=26)
draw.ellipse((369, 369, 399, 399), fill=(226, 255, 255, 240))

logo = base.resize((512, 512), Image.Resampling.LANCZOS)
logo.save(OUT / "alice-mark.png", optimize=True)
logo.save(OUT / "alice.ico", format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
logo.save(ROOT / "companion" / "renderer" / "logo.png", optimize=True)
logo.save(ROOT / "companion" / "tray-icon.png", optimize=True)
