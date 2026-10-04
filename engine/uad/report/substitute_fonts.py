"""Open-licence stand-ins for the report faces, for a host without Myriad Pro.

Appendix E names Myriad Pro as the report face.  Myriad Pro is licensed for
embedding in documents but not for redistribution, so it is not in this
repository -- and without it the renderer used to stop dead (the kerned-font
builder opened ``MyriadPro-Regular.ttf`` and raised), which took the report
form, the preview and the PDF down with it on every fresh checkout and on
every deployment.

This module builds substitutes that are safe to ship:

* **Outlines** come from Adobe's *Source Sans 3*, a humanist sans released
  under the SIL Open Font License 1.1 (``engine/assets/substitute/OFL-SourceSans3.md``).
* **Advance widths** are Myriad Pro's own, read out of the ``/Widths`` arrays
  of the official D-1 sample PDFs (``engine/spec/d1_font_widths.json``).  Each
  glyph's outline is scaled horizontally to its Myriad width (clamped, so no
  letter is visibly distorted) and the remainder goes into the side bearings.
  A character the samples never set takes its face's median ratio.

So text set in the substitute occupies the same measure as the GSE samples and
breaks lines in the same places, while the letterforms are Source Sans' -- a
real, recorded difference from the published reports, not a match.  The OFL
reserves the name "Source", so the built faces are renamed "UAD Substitute".

The checkbox face is the other gap: Appendix E draws CK boxes in Wingdings 2,
which is Microsoft's and is not here either.  ``build_boxes`` draws the two
glyphs the form uses (U+F0A3 hollow box, U+F052 ticked box) into a tiny font
so a missing Wingdings never prints a literal "R" where a tick belongs.

Run ``python -m uad.report.substitute_fonts`` from ``engine/`` to rebuild;
the output in ``engine/assets/substitute/built`` is committed so a deployment
needs no build step.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ENGINE = Path(__file__).resolve().parents[2]
SOURCE = ENGINE / "assets" / "substitute" / "source"
BUILT = ENGINE / "assets" / "substitute" / "built"
WIDTHS = ENGINE / "spec" / "d1_font_widths.json"

# Myriad face -> (Source Sans 3 file, the Myriad face whose widths it takes)
FACES = {
    "MyriadPro-Regular":  ("SourceSans3-Regular", "MyriadPro-Regular"),
    "MyriadPro-Bold":     ("SourceSans3-Bold", "MyriadPro-Bold"),
    "MyriadPro-It":       ("SourceSans3-It", "MyriadPro-It"),
    "MyriadPro-BoldIt":   ("SourceSans3-BoldIt", "MyriadPro-BoldIt"),
    "MyriadPro-Semibold": ("SourceSans3-Semibold", "MyriadPro-Bold"),
    "MyriadPro-Black":    ("SourceSans3-Black", "MyriadPro-Black"),
}
FAMILY = "UAD Substitute"
# How far an outline may be squeezed or stretched to meet a Myriad width.
CLAMP = (0.86, 1.14)
SYMBOLS = [0x2013, 0x2014, 0x2018, 0x2019, 0x201A, 0x201C, 0x201D, 0x201E, 0x2020, 0x2021,
           0x2022, 0x2026, 0x2030, 0x2039, 0x203A, 0x20AC, 0x2122, 0x2190, 0x2191, 0x2192,
           0x2193, 0x2212, 0x2264, 0x2265, 0x2713, 0x00D7]


def _published() -> dict:
    return json.loads(WIDTHS.read_text(encoding="utf-8"))


def _rename(font: TTFont, style: str) -> None:
    for rec in font["name"].names:
        if rec.nameID in (1, 16):
            rec.string = FAMILY
        elif rec.nameID in (4,):
            rec.string = f"{FAMILY} {style}"
        elif rec.nameID in (6,):
            rec.string = f"UADSubstitute-{style.replace(' ', '')}"
        elif rec.nameID == 3:
            rec.string = f"UADSubstitute-{style.replace(' ', '')};built-from-SourceSans3"
    font["name"].setName(
        "Derived from Source Sans 3 (SIL OFL 1.1) by the UAD 3.6 platform: advance "
        "widths set to the values published in the GSE Appendix D-1 samples.", 10, 3, 1, 0x409)


def build_face(face: str, published: dict | None = None) -> Path:
    published = published or _published()
    src_name, width_face = FACES[face]
    font = TTFont(str(SOURCE / f"{src_name}.ttf"))
    upm = font["head"].unitsPerEm
    scale_units = upm / 1000.0                   # PDF /Widths are in 1/1000 em
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    glyf = font["glyf"]
    gset = font.getGlyphSet()
    table = published.get(width_face, {})

    targets: dict[str, float] = {}
    ratios = []
    for code, width in table.items():
        name = cmap.get(int(code))
        if name and hmtx[name][0]:
            targets[name] = width * scale_units
            ratios.append(targets[name] / hmtx[name][0])
    median = statistics.median(ratios) if ratios else 1.0

    for name in font.getGlyphOrder():
        adv, lsb = hmtx[name]
        if not adv:
            continue
        target = targets.get(name, adv * median)
        ratio = target / adv
        sx = min(max(ratio, CLAMP[0]), CLAMP[1])
        g = glyf[name]
        if g.numberOfContours == 0:                # space and other blanks
            hmtx[name] = (int(round(target)), lsb)
            continue
        # redraw the outline scaled by sx, shifted so the extra (or missing)
        # width is shared between the two side bearings
        rec = DecomposingRecordingPen(gset)
        gset[name].draw(rec)
        ink_old = adv * sx
        dx = (target - ink_old) / 2.0
        pen = TTGlyphPen(None)
        rec.replay(TransformPen(pen, (sx, 0, 0, 1, dx, 0)))
        new = pen.glyph()
        glyf[name] = new
        new.recalcBounds(glyf)
        hmtx[name] = (int(round(target)), int(getattr(new, "xMin", 0)))

    style = {"MyriadPro-Regular": "Regular", "MyriadPro-Bold": "Bold",
             "MyriadPro-It": "Italic", "MyriadPro-BoldIt": "Bold Italic",
             "MyriadPro-Semibold": "Semibold", "MyriadPro-Black": "Black"}[face]
    _rename(font, style)
    for tag in ("DSIG", "GPOS"):                 # kerning comes from kerned_fonts
        if tag in font and tag == "DSIG":
            del font[tag]
    # Latin-1 plus the punctuation a report prints: the full face is ~460 KB
    # and is inlined into every rendered page, the subset is a tenth of that
    from fontTools.subset import Options, Subsetter
    opts = Options()
    opts.layout_features = ["kern", "liga"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    sub = Subsetter(opts)
    sub.populate(unicodes=list(range(0x20, 0x7F)) + list(range(0xA0, 0x180)) + SYMBOLS)
    sub.subset(font)
    BUILT.mkdir(parents=True, exist_ok=True)
    out = BUILT / f"{face}.ttf"
    font.save(str(out))
    return out


def build_boxes() -> Path:
    """A two-glyph stand-in for the Wingdings 2 checkbox glyphs."""
    from fontTools.fontBuilder import FontBuilder
    upm = 1000
    fb = FontBuilder(upm, isTTF=True)
    order = [".notdef", "space", "boxempty", "boxtick"]
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x20: "space", 0xF0A3: "boxempty", 0xF052: "boxtick",
                          0xA3: "boxempty", 0x52: "boxtick"})

    def box(tick: bool):
        pen = TTGlyphPen(None)
        x0, y0, x1, y1, t = 80, -10, 760, 670, 55
        for (a, b, c, d) in ((x0, y0, x1, y1), (x0 + t, y0 + t, x1 - t, y1 - t)):
            # outer clockwise, inner counter-clockwise -> a frame
            pts = [(a, b), (a, d), (c, d), (c, b)] if (a, b) == (x0, y0) else \
                  [(a, b), (c, b), (c, d), (a, d)]
            pen.moveTo(pts[0])
            for p in pts[1:]:
                pen.lineTo(p)
            pen.closePath()
        if tick:
            for poly in (((190, 330), (250, 390), (370, 250), (370, 130)),
                         ((330, 170), (370, 130), (660, 560), (600, 600))):
                pen.moveTo(poly[0])
                for p in poly[1:]:
                    pen.lineTo(p)
                pen.closePath()
        return pen.glyph()

    empty = TTGlyphPen(None).glyph()
    fb.setupGlyf({".notdef": empty, "space": empty, "boxempty": box(False), "boxtick": box(True)})
    adv = 840
    fb.setupHorizontalMetrics({".notdef": (adv, 0), "space": (adv, 0),
                               "boxempty": (adv, 80), "boxtick": (adv, 80)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "UAD Boxes", "styleName": "Regular",
                       "psName": "UADBoxes-Regular", "uniqueFontIdentifier": "UADBoxes-Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    BUILT.mkdir(parents=True, exist_ok=True)
    out = BUILT / "Wingdings2.ttf"
    fb.save(str(out))
    return out


def build_all() -> list[Path]:
    published = _published()
    return [build_face(f, published) for f in FACES] + [build_boxes()]


if __name__ == "__main__":
    for p in build_all():
        print(p.relative_to(ENGINE), p.stat().st_size)
