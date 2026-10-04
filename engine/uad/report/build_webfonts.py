"""Convert the licensed Myriad Pro faces to TrueType outlines for embedding.

Chromium embeds a TrueType web font into its PDF as a real Type0 font, but
turns a CFF/OpenType one into Type3 glyph procedures with no name at all.  A
Type3 PDF is not what a lender's checker expects and cannot be inspected with
``pdffonts``, so the faces are converted from cubic (CFF) to quadratic
(TrueType) outlines before they are used.

What must not change is the metrics.  Advance widths are copied across
untouched and then verified against the originals, because the pagination of
this report was measured from the sample PDFs and any width drift would move
every line break on every page.

This converts the machine's own licensed Adobe files in place under
``assets/fonts``; it neither downloads nor redistributes anything.
"""
from __future__ import annotations

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from . import fonts

MAX_ERROR = 0.5          # units per em; well under one PDF unit at any size
SUFFIX = ".ttf"


def convert(src: Path, dst: Path) -> dict:
    """Rewrite one OTF with quadratic outlines, keeping every metric."""
    font = TTFont(str(src))
    glyph_set = font.getGlyphSet()
    upem = font["head"].unitsPerEm
    glyph_order = font.getGlyphOrder()

    glyphs = {}
    for name in glyph_order:
        pen = TTGlyphPen(None)
        glyph_set[name].draw(Cu2QuPen(pen, MAX_ERROR * upem / 1000))
        glyphs[name] = pen.glyph()

    metrics = {name: font["hmtx"][name] for name in glyph_order}
    builder = FontBuilder(upem, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(font.getBestCmap())
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(
        ascent=font["hhea"].ascent, descent=font["hhea"].descent,
        lineGap=font["hhea"].lineGap)
    names = {}
    for rec in font["name"].names:
        try:
            names[str(rec.nameID)] = rec.toUnicode()
        except Exception:
            continue
    builder.setupNameTable({
        "familyName": names.get("1", src.stem),
        "styleName": names.get("2", "Regular"),
        "uniqueFontIdentifier": names.get("3", src.stem),
        "fullName": names.get("4", src.stem),
        "version": names.get("5", "Version 1.000"),
        "psName": names.get("6", src.stem),
    })
    builder.setupOS2(
        sTypoAscender=font["OS/2"].sTypoAscender,
        sTypoDescender=font["OS/2"].sTypoDescender,
        sTypoLineGap=font["OS/2"].sTypoLineGap,
        usWinAscent=font["OS/2"].usWinAscent,
        usWinDescent=font["OS/2"].usWinDescent,
        usWeightClass=font["OS/2"].usWeightClass,
        fsType=font["OS/2"].fsType,
        fsSelection=font["OS/2"].fsSelection,
        achVendID=font["OS/2"].achVendID,
    )
    builder.setupPost()
    builder.save(str(dst))

    # Metrics must survive the conversion exactly.
    check = TTFont(str(dst))
    same = sum(1 for n in glyph_order
               if check["hmtx"][n][0] == font["hmtx"][n][0])
    result = {"glyphs": len(glyph_order), "widths_identical": same,
              "upem_before": upem, "upem_after": check["head"].unitsPerEm,
              "fsType": check["OS/2"].fsType}
    check.close()
    font.close()
    return result


def main() -> None:
    made = []
    for name in fonts.FACES:
        src = fonts.ASSETS / f"{name}.otf"
        if not src.exists():
            print(f"  skip {name}: not installed")
            continue
        dst = fonts.ASSETS / f"{name}{SUFFIX}"
        info = convert(src, dst)
        ok = info["widths_identical"] == info["glyphs"]
        print(f"  {name:<22} {info['glyphs']:>5} glyphs  "
              f"widths {info['widths_identical']}/{info['glyphs']} "
              f"{'identical' if ok else 'CHANGED'}  "
              f"upem {info['upem_before']}->{info['upem_after']}  "
              f"fsType={info['fsType']}  -> {dst.name} "
              f"({dst.stat().st_size / 1024:.0f} KB)")
        made.append(ok)
    print(f"\n{sum(made)}/{len(made)} faces converted with metrics intact")


if __name__ == "__main__":
    main()
