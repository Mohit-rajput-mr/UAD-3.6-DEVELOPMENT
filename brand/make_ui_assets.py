"""Cut the owner's brand files (this folder) into what the app serves.

    python brand/make_ui_assets.py

Writes engine/app/ui/brand/:
* mark-white.png / mark-black.png -- the hand, trimmed to its ink and 160 px
  tall, for the header and the sign-in page (white on the dark theme, black
  on the light one);
* app-icon-32.png / -64.png / -192.png / -512.png -- the tile icon for the
  browser tab, the window and the web app manifest.
The desktop installer takes brand/app-icon.ico as it is (desktop/build.py).
Deterministic: same inputs, same bytes (no timestamps in PNG).
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "engine" / "app" / "ui" / "brand"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for tone in ("white", "black"):
        img = Image.open(HERE / f"logo-{tone}.png").convert("RGBA")
        img = img.crop(img.getchannel("A").getbbox())
        h = 160
        img = img.resize((round(img.width * h / img.height), h), Image.LANCZOS)
        img.save(OUT / f"mark-{tone}.png", optimize=True)
    src = Image.open(HERE / "app-icon-1024.png").convert("RGBA")
    for size in (32, 64, 192, 512):
        src.resize((size, size), Image.LANCZOS).save(OUT / f"app-icon-{size}.png", optimize=True)


if __name__ == "__main__":
    main()
