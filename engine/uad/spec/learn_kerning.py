"""Learn the samples' letter spacing, pair by pair.

The GSE samples are set in InDesign with optical kerning: the space between two
glyphs depends on their shapes, not on the font's kerning table.  It is
deterministic -- the same two characters at the same size are always the same
distance apart (median spread 0.03 font units over 530k observations) -- so it
can be read back from the published PDFs and reproduced exactly.

For every (face, size, left char, right char) seen in the twelve D-1 samples and
in Appendix C-1, the advance beyond the glyph's own width is recorded in font
units (1000/em).  Pairs whose observations disagree (justified lines, overprint)
keep their median.  Output: ``engine/spec/d1_kerning.json``.
"""
from __future__ import annotations

import glob
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "engine"))
from uad.spec.measure_geometry import report_start  # noqa: E402

FACES = ("MyriadPro-Regular", "MyriadPro-Bold", "MyriadPro-It", "MyriadPro-BoldIt",
         "MyriadPro-Black")
# MyriadPro-Black is not part of the Acrobat font set, so its advances are read
# from the /Widths arrays the sample PDFs carry rather than from a font file.
WIDTHS = ROOT / "engine" / "spec" / "d1_font_widths.json"
OUT = ROOT / "engine" / "spec" / "d1_kerning.json"


def sources() -> list[tuple[Path, int]]:
    out = []
    _specs = Path(__import__("os").environ.get("UAD36_SPECS")
                  or Path(__file__).resolve().parents[3] / "specs" / "official")
    for p in sorted(set(glob.glob(str(_specs / "Appendix D-1 *" / "*.pdf")))):
        out.append((Path(p), report_start(pymupdf.open(p))))
    out.append((ROOT / "_ref" / "layout" / "Appendix C-1 URAR without Report Field IDs v1.3.pdf", 2))
    return out


def learn() -> dict:
    metrics = {}
    for face in FACES:
        path = ROOT / "engine" / "assets" / "fonts" / f"{face}.otf"
        if path.exists():
            f = TTFont(path)
            metrics[face] = (f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm)
    published = json.loads(WIDTHS.read_text(encoding="utf-8")) if WIDTHS.exists() else {}
    obs = defaultdict(list)
    spaces = defaultdict(list)
    for path, start in sources():
        doc = pymupdf.open(path)
        for pno in range(start, doc.page_count):
            for block in doc[pno].get_text("rawdict")["blocks"]:
                for line in block.get("lines", []):
                    for s in line["spans"]:
                        face = s["font"].split("+")[-1]
                        if face not in metrics and face not in published:
                            continue
                        if face in metrics:
                            cmap, hmtx, upm = metrics[face]
                            width_of = lambda ch: hmtx[cmap[ord(ch)]][0] / upm * 1000
                            known = lambda ch: ord(ch) in cmap
                        else:
                            table = published.get(face, {})
                            width_of = lambda ch: table[str(ord(ch))]
                            known = lambda ch: str(ord(ch)) in table
                        size = round(s["size"], 1)
                        chars = s["chars"]
                        for a, b in zip(chars, chars[1:]):
                            if abs(b["origin"][1] - a["origin"][1]) <= 0.3 and a["c"] == " ":
                                spaces[(face, size)].append(
                                    (b["origin"][0] - a["origin"][0]) / size * 1000)
                            if not known(a["c"]) or not known(b["c"]):
                                continue
                            # a space is never kerned in the samples; where one
                            # appears to be, the line was justified.
                            if a["c"].isspace() or b["c"].isspace():
                                continue
                            if abs(b["origin"][1] - a["origin"][1]) > 0.3:
                                continue
                            advance = (b["origin"][0] - a["origin"][0]) / size * 1000
                            width = width_of(a["c"])
                            obs[(face, size, a["c"], b["c"])].append(advance - width)
    table: dict = {}
    for (face, size, a, b), values in obs.items():
        value = round(statistics.median(values))
        if value == 0:
            continue
        table.setdefault(face, {}).setdefault(str(size), {})[a + b] = value
    # the word space is set differently at different sizes, so it is recorded
    # per size rather than taken from the font
    space: dict = {}
    for (face, size), values in spaces.items():
        if len(values) >= 3:
            space.setdefault(face, {})[str(size)] = round(statistics.median(values), 1)
    return {"source": "Appendix D-1 samples and Appendix C-1, glyph origins",
            "units": "1/1000 em beyond the glyph advance", "pairs": table,
            "space": space,
            "observations": sum(len(v) for v in obs.values())}


if __name__ == "__main__":
    data = learn()
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for face, sizes in data["pairs"].items():
        print(face, {s: len(p) for s, p in sizes.items()})
