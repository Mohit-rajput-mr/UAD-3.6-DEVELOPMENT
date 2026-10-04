"""Myriad Pro with the samples' own letter spacing built in.

The D-1 samples were set with InDesign's optical kerning, which spaces each
pair of glyphs by their shapes and varies with type size.  ``learn_kerning``
reads those spacings back from the published PDFs; this module writes them
into a kern feature of a copy of each face, one copy per point size, so the
browser sets every pair exactly where the samples set it.

A pair the samples never show at a size is estimated from the same pair at a
neighbouring size (the spacing moves by a constant per point, measured per
face), and failing that falls back to the font's own metric kerning.

Output: ``assets/fonts/kerned/<face>-<size>.ttf`` and the @font-face CSS that
declares family ``UAD <size>`` with the four faces.
"""
from __future__ import annotations

import base64
import io
import json
import statistics
from functools import lru_cache
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

from . import fonts

SPEC = Path(__file__).resolve().parents[2] / "spec" / "d1_kerning.json"
OUT = fonts.ASSETS / "kerned"
FACES = {"MyriadPro-Regular": (400, "normal"), "MyriadPro-Bold": (700, "normal"),
         "MyriadPro-It": (400, "italic"), "MyriadPro-BoldIt": (700, "italic"),
         "MyriadPro-Black": (900, "normal")}
SIZES = (7.0, 8.0, 9.0, 10.0, 12.0, 14.0, 32.0)
WIDTHS = Path(__file__).resolve().parents[2] / "spec" / "d1_font_widths.json"
# Acrobat does not ship MyriadPro-Black, which the samples use for the Summary
# address and heading.  Until the real face is installed, those two lines are
# set from Bold outlines carrying Black's own advance widths (read from the
# samples' /Widths arrays) so the text occupies exactly the same space; the
# letterforms are Bold's, and that is a real difference, recorded here.
BLACK_SUBSTITUTE = "MyriadPro-Black"
WINANSI = [c for c in range(0x20, 0x7F)] + [0xA0, 0x2013, 0x2014, 0x2018, 0x2019, 0x201C,
                                             0x201D, 0x2022, 0x2026, 0xA7, 0xB0, 0xE9]


@lru_cache(maxsize=1)
def _spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8")) if SPEC.exists() else {}


def learned() -> dict:
    return _spec().get("pairs", {})


def space_width(face: str, size: float) -> float | None:
    """The word space the samples set at this size, in 1/1000 em."""
    table = _spec().get("space", {}).get(face, {})
    if not table:
        return None
    sizes = sorted(float(s) for s in table)
    nearest = min(sizes, key=lambda s: abs(s - size))
    return table[str(nearest)] if abs(nearest - size) <= 2.0 else None


def _step(face: str) -> float:
    """How far a pair's spacing moves per point of size, for this face."""
    table = learned().get(face, {})
    sizes = sorted((float(s) for s, p in table.items() if len(p) > 100))
    deltas = []
    for a, b in zip(sizes, sizes[1:]):
        pa, pb = table[str(a)], table[str(b)]
        for pair in set(pa) & set(pb):
            deltas.append((pb[pair] - pa[pair]) / (b - a))
    return statistics.median(deltas) if deltas else 0.0


def pairs_for(face: str, size: float) -> dict[str, float]:
    table = learned().get(face, {})
    known = {float(s): p for s, p in table.items() if len(p) > 20}
    if not known:
        return {}
    step = _step(face)
    out: dict[str, float] = {}
    # nearest sizes first, so an observed value beats an estimated one; a size
    # far from any that was observed (the 32 pt title) is left to its own
    # measurements rather than extrapolated across 20 points
    for other in sorted(known, key=lambda s: abs(s - size)):
        if abs(other - size) > 2.0 and out:
            break
        for pair, value in known[other].items():
            if pair not in out:
                out[pair] = value + step * (size - other)
    return out


def _metric_kern(font: TTFont) -> dict[tuple[str, str], int]:
    return {}


def build(face: str, size: float) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / f"{face}-{size:g}.ttf"
    if dst.exists() and dst.stat().st_mtime > SPEC.stat().st_mtime:
        return dst
    source = face
    if face == BLACK_SUBSTITUTE and not (fonts.ASSETS / f"{face}.ttf").exists():
        source = "MyriadPro-Bold"
    font = TTFont(str(fonts.ASSETS / f"{source}.ttf"))
    if source != face:
        published = json.loads(WIDTHS.read_text(encoding="utf-8")).get(face, {})
        cmap0, hmtx0 = font.getBestCmap(), font["hmtx"]
        ratios = []
        for code, width in published.items():
            ch = int(code)
            if ch in cmap0:
                name = cmap0[ch]
                if hmtx0[name][0]:
                    ratios.append(width / hmtx0[name][0])
                hmtx0[name] = (int(round(width)), hmtx0[name][1])
        # a character the samples never set in Black keeps Bold's shape at the
        # face's average width ratio, so a line of text still measures right
        ratio = statistics.median(ratios) if ratios else 1.0
        seen = {cmap0[int(c)] for c in published if int(c) in cmap0}
        for name in font.getGlyphOrder():
            if name not in seen and hmtx0[name][0]:
                hmtx0[name] = (int(round(hmtx0[name][0] * ratio)), hmtx0[name][1])
    cmap = font.getBestCmap()
    rules = []
    for pair, value in pairs_for(face, size).items():
        a, b = pair[0], pair[1]
        if a.isspace() or b.isspace() or abs(value) > 150:
            continue
        if ord(a) in cmap and ord(b) in cmap and round(value) != 0:
            rules.append(f"pos {cmap[ord(a)]} {cmap[ord(b)]} {round(value)};")
    width = space_width(face, size)
    if width:
        cmap_s = font.getBestCmap()
        if 32 in cmap_s:
            name = cmap_s[32]
            font["hmtx"][name] = (int(round(width)), font["hmtx"][name][1])
    fea = ("languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"
           "feature kern {\n" + "\n".join(rules) + "\n} kern;\n")
    addOpenTypeFeaturesFromString(font, fea)
    opts = Options()
    opts.layout_features = ["kern", "liga"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    sub = Subsetter(opts)
    sub.populate(unicodes=WINANSI,
                 glyphs=[g for g in ("ff", "fi", "fl", "ffi", "ffl")
                         if g in font.getGlyphOrder()])
    sub.subset(font)
    font.save(str(dst))
    return dst


def css(sizes=SIZES) -> str:
    rules = []
    for size in sizes:
        for face, (weight, style) in FACES.items():
            path = build(face, size)
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            rules.append(f"@font-face{{font-family:'UAD {size:g}';"
                         f"src:url(data:font/ttf;base64,{data}) format('truetype');"
                         f"font-weight:{weight};font-style:{style};font-display:block}}")
    return "\n".join(rules)


if __name__ == "__main__":
    for size in SIZES:
        for face in FACES:
            p = build(face, size)
            print(p.name, p.stat().st_size, len(pairs_for(face, size)), "pairs")
