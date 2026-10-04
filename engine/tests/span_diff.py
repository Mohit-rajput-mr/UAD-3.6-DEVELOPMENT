"""Measure how far our PDF is from the GSE's, by glyph baselines.

    python engine/tests/span_diff.py <template-key> <our page> [-q]

Text is compared by where each run of glyphs actually sits -- the baseline
origin of its first character, and the advance to its last character -- which
is independent of the font file's ascender metrics.  (Comparing bounding boxes
was misleading: two builds of Myriad Pro report different box heights for the
same glyph at the same place.)

For every run on our page the same text is found on the GSE page and three
numbers are printed: dx, dy of the first glyph's origin, and dw, the
difference in the distance from the first glyph to the last (a tracking,
kerning or weight/width difference).  A run is exact when all three are
within 0.25 pt.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from uad import templates  # noqa: E402
from uad.spec.measure_geometry import report_start  # noqa: E402

TOL = 0.25


def runs(page) -> list[dict]:
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for line in b.get("lines", []):
            for s in line["spans"]:
                chars = [c for c in s["chars"] if c["c"].strip()]
                if not chars:
                    continue
                text = "".join(c["c"] for c in s["chars"]).strip()
                out.append({"text": text, "x": chars[0]["origin"][0], "y": chars[0]["origin"][1],
                            "w": chars[-1]["origin"][0] - chars[0]["origin"][0],
                            "size": s["size"], "font": s["font"].split("+")[-1],
                            "colour": s["color"]})
    return out


def compare(key: str, n: int, verbose: bool = True) -> dict:
    tpl = templates.get(key)
    ours = pymupdf.open(ROOT / "_work" / "form" / f"{key}.pdf")
    gse = pymupdf.open(tpl.pdf)
    a = runs(ours[n - 1])
    b = runs(gse[report_start(gse) + n - 1])
    pool = defaultdict(list)
    for r in b:
        pool[r["text"]].append(r)
    paired, missing = [], []
    for r in a:
        cands = pool.get(r["text"])
        if cands:
            g = min(cands, key=lambda q: abs(q["y"] - r["y"]) + abs(q["x"] - r["x"]))
            cands.remove(g)
            paired.append((r, g))
        else:
            missing.append(r)
    extra = [g for gs in pool.values() for g in gs]
    exact = 0
    lines = []
    for r, g in sorted(paired, key=lambda p: (p[1]["y"], p[1]["x"])):
        dx, dy, dw = r["x"] - g["x"], r["y"] - g["y"], r["w"] - g["w"]
        ok = abs(dx) <= TOL and abs(dy) <= TOL and abs(dw) <= TOL
        exact += ok
        fontnote = "" if r["font"] == g["font"] else f" font {r['font']}!={g['font']}"
        lines.append(f"{r['text'][:42]:42} @({g['x']:6.1f},{g['y']:6.1f}) "
                     f"dx={dx:+5.2f} dy={dy:+5.2f} dw={dw:+5.2f}{'' if ok else '  <--'}{fontnote}")
    result = {"paired": len(paired), "exact": exact, "ours_only": len(missing),
              "gse_only": len(extra)}
    if verbose:
        print("\n".join(lines))
        for r in missing:
            print(f"OURS ONLY  {r['text'][:60]:60} ({r['x']:.0f},{r['y']:.0f})")
        for g in extra:
            print(f"GSE ONLY   {g['text'][:60]:60} ({g['x']:.0f},{g['y']:.0f})")
    print(result)
    return result


if __name__ == "__main__":
    compare(sys.argv[1], int(sys.argv[2]), verbose="-q" not in sys.argv)
