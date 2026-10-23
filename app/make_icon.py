"""Uygulama simgesini (radar) üretir: app/icon.ico"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "icon.ico"


def main():
    s = 256
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, s - 8, s - 8), radius=56, fill=(17, 20, 24, 255))
    c = s // 2
    for r, w in ((92, 10), (62, 10), (32, 10)):
        d.ellipse((c - r, c - r, c + r, c + r), outline=(64, 72, 82, 255), width=w)
    d.pieslice((c - 92, c - 92, c + 92, c + 92), 250, 310, fill=(255, 176, 32, 210))
    d.ellipse((c + 34, c - 70, c + 58, c - 46), fill=(255, 176, 32, 255))
    img.save(OUT, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
