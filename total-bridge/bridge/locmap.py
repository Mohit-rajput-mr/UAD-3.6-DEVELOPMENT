"""The Sales Comparison Approach location map (UAD-1283), from OpenStreetMap tiles.

H-1 requires an SCA boundary map image whenever the sales comparison approach
is developed.  When the case folder carries none, this draws one: OpenStreetMap
tiles, every property at its published coordinate, a legend, and the tile
attribution the licence requires.  It is placed in `GSU_MAP` (sales-comp).

    points = [("S", "Subject: 1 Main St", 40.92, -73.88, "subject"), ("1", "...", ...)]
    locmap.draw(points, "comparable_map.png")

A coordinate that is only street-level (no parcel coordinate published) must be
labelled so in its legend text -- the map must not claim more precision than
its source.  Always VIEW the result: it shows location differences (a parkway,
a park, a commercial strip between subject and a comparable) that the grid does
not, and those belong in front of the appraiser.
"""
from __future__ import annotations

import io
import math
import urllib.request
from pathlib import Path

ZOOM = 15
UA = "uad36-appraisal-map/1.0 (single report, low volume)"
COLOURS = {"subject": (200, 30, 30), "comp": (20, 70, 170)}


def _px(lat, lon, z=ZOOM):
    n = 256 * 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _tile(x, y, z=ZOOM):
    from PIL import Image
    req = urllib.request.Request(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png", headers={"User-Agent": UA})
    return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=20).read())).convert("RGB")


def draw(points: list[tuple], out: str | Path, pad: int = 110, zoom: int = ZOOM) -> Path:
    """points: (tag, legend text, lat, lon, "subject"|"comp")."""
    from PIL import Image, ImageDraw, ImageFont
    px = [_px(p[2], p[3], zoom) for p in points]
    x0, x1 = min(p[0] for p in px) - pad, max(p[0] for p in px) + pad
    y0, y1 = min(p[1] for p in px) - pad, max(p[1] for p in px) + pad
    tx0, tx1, ty0, ty1 = int(x0 // 256), int(x1 // 256), int(y0 // 256), int(y1 // 256)
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), "white")
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            canvas.paste(_tile(tx, ty, zoom), ((tx - tx0) * 256, (ty - ty0) * 256))
    img = canvas.crop((int(x0 - tx0 * 256), int(y0 - ty0 * 256), int(x1 - tx0 * 256), int(y1 - ty0 * 256)))
    d = ImageDraw.Draw(img)
    try:
        f, small = ImageFont.truetype("arialbd.ttf", 16), ImageFont.truetype("arial.ttf", 13)
    except OSError:
        f = small = ImageFont.load_default()
    for (tag, _l, _a, _o, kind), (x, y) in zip(points, px):
        cx, cy = x - x0, y - y0
        d.ellipse((cx - 13, cy - 13, cx + 13, cy + 13), fill=COLOURS.get(kind, COLOURS["comp"]),
                  outline="white", width=3)
        d.text((cx - d.textlength(tag, font=f) / 2, cy - 10), tag, fill="white", font=f)
    width = max(d.textlength(f"{p[0]}  {p[1]}", font=small) for p in points) + 20
    d.rectangle((8, 8, 8 + width, 20 + 18 * len(points)), fill="white", outline=(90, 90, 90))
    for i, p in enumerate(points):
        d.text((16, 14 + i * 18), f"{p[0]}  {p[1]}", fill=(20, 20, 20), font=small)
    note = "Map data (c) OpenStreetMap contributors"
    d.rectangle((img.width - 262, img.height - 22, img.width - 2, img.height - 2), fill="white")
    d.text((img.width - 256, img.height - 20), note, fill=(40, 40, 40), font=small)
    out = Path(out)
    img.save(out)
    return out


def miles_and_bearing(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, str]:
    """Great-circle miles and 8-point compass bearing from a to b."""
    R, p = 3958.8, math.radians
    h = (math.sin(p(b[0] - a[0]) / 2) ** 2
         + math.cos(p(a[0])) * math.cos(p(b[0])) * math.sin(p(b[1] - a[1]) / 2) ** 2)
    miles = 2 * R * math.asin(math.sqrt(h))
    y = math.sin(p(b[1] - a[1])) * math.cos(p(b[0]))
    x = math.cos(p(a[0])) * math.sin(p(b[0])) - math.sin(p(a[0])) * math.cos(p(b[0])) * math.cos(p(b[1] - a[1]))
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return round(miles, 2), ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((deg + 22.5) // 45) % 8]
