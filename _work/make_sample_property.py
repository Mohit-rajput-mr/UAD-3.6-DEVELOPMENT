"""Build a complete sample UAD 3.6 package to test importing and filling with.

What comes out is a B-1 delivery bundle -- ``mismo.xml`` beside an ``Images``
folder, zipped -- for a property that does not exist, carrying every section
its scenario displays: the site and its utilities, the dwelling and its units,
amenities, defects, the sketch, the market graphs, the comparable grid with the
appraiser's own added row, the exhibits, the photographs and the comparable
map.

It is built *from* one of the GSE's own Appendix D-1 scenarios, because that
is the only way to be sure every section, rule and enumeration is exercised
exactly as the specification intends -- but nothing identifying is kept: the
address, the people, the parcel, the licence, the coordinates, the data
sources and every picture are this file's own.  The numbers are the
scenario's, so the arithmetic the report checks still adds up.

    python _work/make_sample_property.py sf3_appraisal_v1_4 "Maple Grove"
"""
from __future__ import annotations

import io
import math
import random
import shutil
import sys
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from uad import compliance, schema, templates  # noqa: E402

M = "{http://www.mismo.org/residential/2009/schemas}"
OUT = ROOT / "_work" / "sample_property"


# --------------------------------------------------------------- the property
class Property:
    """Everything about the sample that is not the scenario's own arithmetic."""

    def __init__(self) -> None:
        self.prefix = "MG"
        self.name = "Maple Grove"
        self.street = "418 Willowmere Ln"
        self.city = "Maple Grove"
        self.state = "OR"
        self.zip = "97042"
        self.county = "Cedar"
        self.parcel = "MG-4180-11"
        self.legal = "Willowmere Addition, Block 4, Lot 18, Cedar County"
        self.latitude = "45.362118"
        self.longitude = "-122.611904"
        # everyone the report names
        self.people = {
            ("Betty", "Borrower"): ("Nadia", "Fairweather"),
            ("Bob", "Borrower"): ("Marcus", "Fairweather"),
            ("Jane", "Doe"): ("Thomas", "Osei"),
            ("Agatha", "Appraiser"): ("Rowan", "Ellsworth"),
        }
        self.companies = {
            "Empty Bank": "Harbor Point Bank",
            "IDK Appraisal Management Company": "Northline Appraisal Management",
            "ABC Appraisal Co.": "Ellsworth Valuation LLC",
        }
        self.licences = {"XYZ12345": "OR-778-4412", "5419-2123.4": "OR-AMC-3310"}
        # the comparables, in the order the grid shows them
        self.comparables = [
            ("512 Larkspur Way", "Maple Grove", "OR", "97042"),
            ("287 Foxglove Ct", "Maple Grove", "OR", "97042"),
            ("96 Alder Creek Rd", "Cedar Falls", "OR", "97045"),
            ("1340 Chestnut Row", "Cedar Falls", "OR", "97045"),
            ("77 Quarry Bend", "Maple Grove", "OR", "97042"),
            ("655 Hollis Park Dr", "Maple Grove", "OR", "97042"),
        ]


# ------------------------------------------------------------------ the data
def rewrite(root: etree._Element, prop: Property) -> dict:
    """Give the scenario a new identity, keeping its numbers intact."""
    counts: dict[str, int] = {}

    def bump(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    # addresses: the subject's first, then one per comparable, by the order
    # they stand in the document
    streets: dict[str, str] = {}
    next_comp = iter(prop.comparables)
    for node in root.iter(f"{M}AddressLineText"):
        was = (node.text or "").strip()
        if not was:
            continue
        if was not in streets:
            if not streets:
                streets[was] = prop.street          # the subject
            else:
                streets[was] = next(next_comp, ("Elsewhere", "", "", ""))[0]
        node.text = streets[was]
        bump("address")

    where = {s: c for s, c in zip(list(streets.values()),
                                  [(prop.city, prop.state, prop.zip)]
                                  + [(c[1], c[2], c[3]) for c in prop.comparables])}
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        name = etree.QName(node).localname
        text = (node.text or "").strip()
        if not text:
            continue
        if name == "CityName":
            sibling = node.getparent().findtext(f"{M}AddressLineText", "").strip()
            node.text = where.get(sibling, (prop.city, prop.state, prop.zip))[0]
            bump("city")
        elif name == "StateCode":
            sibling = node.getparent().findtext(f"{M}AddressLineText", "").strip()
            node.text = where.get(sibling, (prop.city, prop.state, prop.zip))[1]
            bump("state")
        elif name == "PostalCode":
            sibling = node.getparent().findtext(f"{M}AddressLineText", "").strip()
            node.text = where.get(sibling, (prop.city, prop.state, prop.zip))[2]
            bump("zip")
        elif name == "CountyName":
            node.text = prop.county
            bump("county")
        elif name == "ParcelsLegalDescription":
            node.text = prop.legal
            bump("legal")
        elif name == "ParcelIdentifier":
            node.text = f"{prop.parcel}-{counts.get('parcel', 0) + 1}"
            bump("parcel")
        elif name == "LicenseIdentifier":
            node.text = prop.licences.get(text, f"OR-{abs(hash(text)) % 9000 + 1000}")
            bump("licence")
        elif name == "FullName":
            node.text = prop.companies.get(text, text)
            bump("company")
        elif name == "LatitudeIdentifier":
            node.text = _near(prop.latitude, text, 0.004)
            bump("latitude")
        elif name == "LongitudeIdentifier":
            node.text = _near(prop.longitude, text, 0.006)
            bump("longitude")
        elif name == "DataSourceIdentifier" and text.isdigit():
            node.text = str(700000 + int(text) % 90000)
            bump("data source")

    # people: a first name and a last name are written apart, so the pair is
    # matched on the NAME block they share
    for block in root.iter(f"{M}NAME"):
        first = block.find(f"{M}FirstName")
        last = block.find(f"{M}LastName")
        key = ((first.text or "").strip() if first is not None else "",
               (last.text or "").strip() if last is not None else "")
        if key in prop.people:
            new_first, new_last = prop.people[key]
            if first is not None:
                first.text = new_first
            if last is not None:
                last.text = new_last
            bump("person")
    return counts


def _near(base: str, was: str, spread: float) -> str:
    """A coordinate near the sample property, keeping each one distinct."""
    seed = abs(hash(was)) % 1000 / 1000.0
    return f"{float(base) + (seed - 0.5) * spread:.6f}"


# ---------------------------------------------------------------- the images
INK = (35, 31, 32)
PAPER = (247, 246, 243)


def _font(size: int):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _caption(img: Image.Image, text: str, sub: str = "") -> None:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    draw.rectangle([0, h - 88, w, h], fill=(255, 255, 255, 235))
    draw.line([0, h - 88, w, h - 88], fill=INK, width=2)
    draw.text((28, h - 74), text, font=_font(34), fill=INK)
    if sub:
        draw.text((28, h - 36), sub, font=_font(20), fill=(110, 108, 104))
    mark = "SAMPLE IMAGE - not a photograph of a real property"
    draw.text((w - 24 - draw.textlength(mark, font=_font(18)), h - 32), mark,
              font=_font(18), fill=(150, 148, 144))


def _sky(w: int, h: int, warm: bool = False) -> Image.Image:
    img = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(img)
    top = (198, 214, 232) if not warm else (232, 218, 198)
    for y in range(h):
        t = y / h
        draw.line([0, y, w, y], fill=(int(top[0] + (250 - top[0]) * t),
                                      int(top[1] + (248 - top[1]) * t),
                                      int(top[2] + (240 - top[2]) * t)))
    return img


def house_photo(text: str, sub: str, seed: int, w: int = 1200, h: int = 900) -> Image.Image:
    """A front/rear elevation, drawn: roof, walls, windows, a door, planting."""
    rnd = random.Random(seed)
    img = _sky(w, h)
    draw = ImageDraw.Draw(img)
    ground = h - 150
    draw.rectangle([0, ground, w, h], fill=(150, 168, 132))
    draw.rectangle([0, ground, w, ground + 26], fill=(138, 158, 122))
    left, right = int(w * 0.16), int(w * 0.84)
    eaves, ridge = int(h * 0.46), int(h * 0.22)
    body = (222, 220, 212) if seed % 2 else (204, 210, 206)
    draw.polygon([(left - 34, eaves), (right + 34, eaves), ((left + right) // 2, ridge)],
                 fill=(92, 86, 84))
    draw.rectangle([left, eaves, right, ground], fill=body, outline=(120, 116, 112))
    door = ((left + right) // 2 - 45, ground - 190, (left + right) // 2 + 45, ground)
    draw.rectangle(door, fill=(86, 70, 58))
    draw.ellipse([door[2] - 26, door[1] + 88, door[2] - 14, door[1] + 100], fill=(210, 190, 140))
    for i in range(4):
        x = left + 60 + i * ((right - left - 120) // 3)
        if abs(x - (left + right) // 2) < 90:
            continue
        draw.rectangle([x, eaves + 70, x + 96, eaves + 190], fill=(150, 176, 196),
                       outline=(240, 240, 238), width=5)
    for i in range(6):
        bx = rnd.randint(30, w - 30)
        by = ground + rnd.randint(-10, 40)
        size = rnd.randint(30, 70)
        draw.ellipse([bx - size, by - size, bx + size, by + size // 2],
                     fill=(112, 142, 104))
    img = img.filter(ImageFilter.SMOOTH)
    _caption(img, text, sub)
    return img


def room_photo(text: str, sub: str, seed: int, w: int = 1200, h: int = 900) -> Image.Image:
    """An interior: a back wall, a floor, a window and a piece of furniture."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (236, 232, 226))
    draw = ImageDraw.Draw(img)
    horizon = int(h * 0.58)
    draw.rectangle([0, horizon, w, h], fill=(188, 164, 132))
    for i in range(14):
        y = horizon + int((h - horizon) * (i / 14) ** 1.6)
        draw.line([0, y, w, y], fill=(176, 152, 122), width=2)
    draw.rectangle([int(w * 0.08), int(h * 0.14), int(w * 0.34), int(h * 0.48)],
                   fill=(206, 222, 234), outline=(250, 250, 248), width=8)
    piece = rnd.choice(["counter", "table", "tub"])
    if piece == "counter":
        draw.rectangle([int(w * 0.42), horizon - 150, int(w * 0.92), horizon - 110],
                       fill=(60, 58, 56))
        draw.rectangle([int(w * 0.44), horizon - 110, int(w * 0.90), horizon + 40],
                       fill=(226, 220, 210), outline=(190, 184, 176), width=3)
    elif piece == "table":
        draw.rectangle([int(w * 0.40), horizon - 60, int(w * 0.86), horizon - 24],
                       fill=(122, 92, 66))
        for x in (int(w * 0.44), int(w * 0.82)):
            draw.rectangle([x, horizon - 24, x + 16, horizon + 120], fill=(104, 78, 56))
    else:
        draw.rounded_rectangle([int(w * 0.44), horizon - 80, int(w * 0.88), horizon + 90],
                               radius=26, fill=(248, 248, 246), outline=(206, 204, 200), width=4)
    img = img.filter(ImageFilter.SMOOTH_MORE)
    _caption(img, text, sub)
    return img


def sketch(prop: Property, w: int = 1500, h: int = 1100) -> Image.Image:
    """The improvement sketch: rooms, walls, dimensions and an area schedule."""
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    f, small = _font(26), _font(20)
    x0, y0, x1, y1 = 120, 150, w - 420, h - 220
    draw.rectangle([x0, y0, x1, y1], outline=INK, width=6)
    mid_x = x0 + int((x1 - x0) * 0.56)
    mid_y = y0 + int((y1 - y0) * 0.52)
    draw.line([mid_x, y0, mid_x, mid_y], fill=INK, width=4)
    draw.line([x0, mid_y, x1, mid_y], fill=INK, width=4)
    draw.line([mid_x + 180, mid_y, mid_x + 180, y1], fill=INK, width=4)
    for box, name in (((x0, y0, mid_x, mid_y), "Living"),
                      ((mid_x, y0, x1, mid_y), "Kitchen / Dining"),
                      ((x0, mid_y, mid_x + 180, y1), "Bedrooms 1-3"),
                      ((mid_x + 180, mid_y, x1, y1), "Bath / Utility")):
        cx = (box[0] + box[2]) // 2
        cy = (box[1] + box[3]) // 2
        draw.text((cx - draw.textlength(name, font=f) / 2, cy - 14), name, font=f, fill=INK)
    draw.text((x0, y0 - 54), "Improvement Sketch - first floor", font=_font(34), fill=INK)
    draw.text(((x0 + x1) // 2 - 40, y1 + 24), "48'-0\"", font=f, fill=INK)
    draw.text((x0 - 96, (y0 + y1) // 2), "34'-0\"", font=f, fill=INK)
    draw.line([x0, y1 + 16, x1, y1 + 16], fill=INK, width=2)
    draw.line([x0 - 16, y0, x0 - 16, y1], fill=INK, width=2)
    sx = x1 + 50
    draw.text((sx, y0 - 4), "Area schedule", font=_font(30), fill=INK)
    rows = [("First floor", "1,632 sq ft"), ("Second floor", "1,272 sq ft"),
            ("Finished basement", "640 sq ft"), ("Garage (2 car)", "462 sq ft"),
            ("Covered porch", "148 sq ft"), ("Accessory unit", "560 sq ft")]
    for i, (label, value) in enumerate(rows):
        y = y0 + 54 + i * 44
        draw.text((sx, y), label, font=small, fill=INK)
        draw.text((w - 60 - draw.textlength(value, font=small), y), value, font=small, fill=INK)
        draw.line([sx, y + 30, w - 60, y + 30], fill=(210, 208, 204), width=1)
    draw.text((sx, y0 + 54 + len(rows) * 44 + 18), "Sketch drawn to scale, 1/8\" = 1'",
              font=_font(18), fill=(120, 118, 114))
    _caption(img, f"{prop.street} - improvement sketch", "Gross living area 2,904 sq ft")
    return img


def comp_map(prop: Property, w: int = 1400, h: int = 1000) -> Image.Image:
    """The comparable map: the subject, the comparables and a scale."""
    img = Image.new("RGB", (w, h), (240, 238, 232))
    draw = ImageDraw.Draw(img)
    rnd = random.Random(7)
    for i in range(9):
        y = 80 + i * ((h - 200) // 8)
        draw.line([40, y, w - 40, y], fill=(218, 216, 210), width=rnd.choice([6, 10]))
    for i in range(10):
        x = 60 + i * ((w - 140) // 9)
        draw.line([x, 60, x, h - 120], fill=(218, 216, 210), width=rnd.choice([6, 10]))
    draw.ellipse([w // 2 - 260, h // 2 - 170, w // 2 + 260, h // 2 + 170],
                 outline=(200, 214, 198), width=14)
    points = [(w // 2, h // 2, "Subject", (35, 31, 32)),
              (w // 2 - 300, h // 2 - 120, "1", (176, 122, 20)),
              (w // 2 + 250, h // 2 - 190, "2", (176, 122, 20)),
              (w // 2 + 170, h // 2 + 190, "3", (176, 122, 20))]
    for x, y, label, colour in points:
        draw.ellipse([x - 26, y - 26, x + 26, y + 26], fill=colour, outline=(255, 255, 255), width=5)
        text = label if label != "Subject" else "S"
        draw.text((x - draw.textlength(text, font=_font(26)) / 2, y - 16), text,
                  font=_font(26), fill=(255, 255, 255))
        if label != "Subject":
            draw.text((x + 34, y - 14), f"Comparable #{label}", font=_font(24), fill=INK)
        else:
            draw.text((x + 34, y - 14), prop.street, font=_font(24), fill=INK)
    draw.line([60, h - 150, 260, h - 150], fill=INK, width=5)
    draw.text((60, h - 142), "0.25 mile", font=_font(22), fill=INK)
    _caption(img, "Sales comparable map", f"{prop.city}, {prop.state}")
    return img


def graph(title: str, kind: str, w: int = 1200, h: int = 760) -> Image.Image:
    """One of B-1's market graphs, drawn from a plausible series."""
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    left, right, top, bottom = 120, w - 60, 120, h - 190
    draw.text((left, 54), title, font=_font(34), fill=INK)
    draw.line([left, bottom, right, bottom], fill=INK, width=3)
    draw.line([left, top, left, bottom], fill=INK, width=3)
    months = ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]
    series = {"absorption": [6.2, 6.0, 5.4, 4.8, 4.4, 4.9, 5.6, 6.4, 7.1, 7.6, 7.2, 6.8],
              "days": [41, 44, 48, 52, 55, 50, 44, 38, 33, 29, 31, 34],
              "price": [548, 551, 553, 556, 559, 563, 570, 578, 586, 592, 596, 601]}[kind]
    lo, hi = min(series) * 0.92, max(series) * 1.06
    step = (right - left) / (len(series) - 1)
    points = [(left + i * step, bottom - (v - lo) / (hi - lo) * (bottom - top))
              for i, v in enumerate(series)]
    if kind == "days":
        for (x, y), value in zip(points, series):
            draw.rectangle([x - 26, y, x + 26, bottom], fill=(176, 122, 20))
            draw.text((x - draw.textlength(str(value), font=_font(20)) / 2, y - 30),
                      str(value), font=_font(20), fill=INK)
    else:
        draw.line(points, fill=(35, 31, 32), width=5, joint="curve")
        for (x, y), value in zip(points, series):
            draw.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(176, 122, 20))
            draw.text((x - draw.textlength(f"{value:g}", font=_font(19)) / 2, y - 34),
                      f"{value:g}", font=_font(19), fill=INK)
    for (x, _y), label in zip(points, months):
        draw.text((x - draw.textlength(label, font=_font(20)) / 2, bottom + 14),
                  label, font=_font(20), fill=(110, 108, 104))
    unit = {"absorption": "sales per month", "days": "median days on market",
            "price": "median sale price ($000)"}[kind]
    draw.text((left, bottom + 58), f"{unit}, twelve months to August",
              font=_font(22), fill=(110, 108, 104))
    _caption(img, title, "Drawn from the market data in this report")
    return img


def document(title: str, lines: list[str], w: int = 1000, h: int = 720) -> Image.Image:
    """A licence, a certificate, a score sheet: a document, not a photograph."""
    img = Image.new("RGB", (w, h), (252, 251, 248))
    draw = ImageDraw.Draw(img)
    draw.rectangle([30, 30, w - 30, h - 30], outline=(176, 122, 20), width=6)
    draw.text((70, 84), title, font=_font(38), fill=INK)
    draw.line([70, 140, w - 70, 140], fill=(200, 198, 194), width=2)
    for i, line in enumerate(lines):
        draw.text((70, 180 + i * 46), line, font=_font(26), fill=INK)
    draw.ellipse([w - 220, h - 250, w - 80, h - 110], outline=(176, 122, 20), width=5)
    draw.text((w - 202, h - 190), "SAMPLE", font=_font(28), fill=(176, 122, 20))
    _caption(img, title, "Issued for demonstration only")
    return img


def scene(text: str, sub: str, seed: int, w: int = 1200, h: int = 900) -> Image.Image:
    """Outdoors that is not the dwelling: a street, a view, a site influence."""
    rnd = random.Random(seed)
    img = _sky(w, h, warm=seed % 3 == 0)
    draw = ImageDraw.Draw(img)
    horizon = int(h * 0.62)
    draw.rectangle([0, horizon, w, h], fill=(146, 164, 128))
    for i in range(5):
        y = horizon - 40 - i * 26
        draw.polygon([(rnd.randint(-100, w // 2), y), (rnd.randint(w // 3, w + 100), y),
                      (rnd.randint(0, w), y - rnd.randint(40, 120))],
                     fill=(158 - i * 8, 170 - i * 6, 150 - i * 6))
    if seed % 2:
        draw.polygon([(int(w * 0.30), h), (int(w * 0.44), horizon),
                      (int(w * 0.56), horizon), (int(w * 0.78), h)], fill=(96, 94, 92))
        for i in range(6):
            y = horizon + 20 + i * ((h - horizon) // 5)
            draw.line([w // 2 - 6, y, w // 2 + 6, y + 18], fill=(238, 236, 230), width=6)
    img = img.filter(ImageFilter.SMOOTH)
    _caption(img, text, sub)
    return img


def picture_for(category: str, caption: str, filename: str, prop: Property,
                seed: int) -> Image.Image:
    """The picture that belongs behind one IMAGE of the report."""
    name = filename.lower()
    if category == "SubjectPropertyImprovementSketch" or "sketch" in name:
        return sketch(prop)
    if category.endswith("Map") or "map" in name:
        return comp_map(prop)
    if category == "AbsorptionRateGraph" or "absorption" in name:
        return graph("Absorption rate", "absorption")
    if category == "MedianDaysOnMarketGraph" or "daysonmarket" in name:
        return graph("Median days on market", "days")
    if category in ("PriceTrendGraph", "MedianSalePriceGraph") or "pricetrend" in name:
        return graph("Median sale price trend", "price")
    if "license" in name or category == "AssignmentExhibit":
        return document("Appraiser certification",
                        ["Rowan Ellsworth", "Certified Residential Appraiser",
                         "Licence OR-778-4412", "State of Oregon",
                         "Expires 31 December 2027"])
    if "resnet" in name or "doe" in name or "score" in name:
        return document("Home energy score",
                        ["418 Willowmere Ln, Maple Grove OR 97042",
                         "HERS Index: 58", "Assessed 14 March 2026",
                         "Verifier: Cedar Energy Ratings"])
    label = caption or _from_name(filename)
    if any(word in name for word in ("front", "rear", "dwellingfront", "adufront",
                                     "aduback", "side")):
        return house_photo(f"{prop.street} - {label}", f"{prop.city}, {prop.state}", seed)
    if any(word in name for word in ("comp", "subject")):
        return house_photo(label, f"{prop.city}, {prop.state}", seed)
    if any(word in name for word in ("street", "access", "view", "influence", "site",
                                     "pool", "deck", "patio", "porch", "yard")):
        return scene(label, f"{prop.street}", seed)
    return room_photo(label, f"{prop.street}", seed)


def _from_name(filename: str) -> str:
    stem = Path(filename).stem
    for prefix in ("SF1_", "SF2_", "SF3_", "SF4_", "SF5_", "MH1_", "MH2_",
                   "Condo1_", "Condo2_", "Coop1_"):
        stem = stem.replace(prefix, "")
    out = []
    for ch in stem:
        if ch.isupper() and out and out[-1] not in " ":
            out.append(" ")
        out.append(ch)
    return "".join(out).replace("_", " ").strip()


# ----------------------------------------------------------------- the bundle
def build(scenario: str, prop: Property) -> Path:
    tpl = templates.get(scenario)
    tree = etree.parse(str(tpl.path))
    root = tree.getroot()
    counts = rewrite(root, prop)

    folder = OUT / prop.name.replace(" ", "_")
    images = folder / "Images"
    if folder.exists():
        shutil.rmtree(folder)
    images.mkdir(parents=True)

    made: dict[str, str] = {}
    for seed, node in enumerate(root.iter(f"{M}IMAGE"), start=1):
        loc = node.find(f"{M}ImageFileLocationIdentifier")
        if loc is None or not (loc.text or "").strip():
            continue
        old = (loc.text or "").strip().split("\\")[-1]
        category = node.findtext(f"{M}ImageCategoryType", "") or ""
        caption = node.findtext(f"{M}ImageCaptionCommentDescription", "") or ""
        if old not in made:
            new_name = f"{prop.prefix}_{_from_name(old).replace(' ', '')}.png"
            picture = picture_for(category, caption, old, prop, seed)
            picture.save(images / new_name, "PNG", optimize=True)
            made[old] = new_name
        loc.text = f"\\\\Images\\{made[old]}"

    xml_path = folder / "mismo.xml"
    tree.write(str(xml_path), encoding="UTF-8", xml_declaration=True)

    problems = schema.validate(tree)
    findings = [f for f in compliance.evaluate(tree)
                if f.status == compliance.FINDING and f.severity == "Fatal"]
    bundle = OUT / f"Sample_{prop.name.replace(' ', '_')}_UAD36.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(xml_path, "mismo.xml")
        for picture in sorted(images.iterdir()):
            zf.write(picture, f"Images/{picture.name}")
    print(f"scenario      {scenario}")
    print(f"rewritten     {counts}")
    print(f"images        {len(made)} drawn")
    print(f"schema        {len(problems)} problem(s)")
    print(f"compliance    {len(findings)} fatal")
    print(f"bundle        {bundle}  ({bundle.stat().st_size / 1e6:.1f} MB)")
    return bundle


if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else "sf3_appraisal_v1_4"
    sample = Property()
    if len(sys.argv) > 2:
        sample.name = sys.argv[2]
    build(scenario, sample)
