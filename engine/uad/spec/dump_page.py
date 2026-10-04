"""Print one sample page's complete anatomy: fills, rules, tables, text.

Used to answer questions the aggregate measurements cannot -- how a two-column
page is actually split, what inset a section tab gives its label, how tall a
grid row is.  Takes the sample name and the *report* page number, so page 1 is
the Summary, not the specification wrapper.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pymupdf

from measure_geometry import WRAPPER_PAGES, samples


def _hex(c) -> str:
    return "none" if c is None else "#%02x%02x%02x" % tuple(round(v * 255) for v in c)


def dump(name: str, rpage: int, what: str = "all") -> None:
    pdf = next(p for p in samples() if p.name.lower().startswith(name.lower()))
    doc = pymupdf.open(pdf)
    page = doc[rpage - 1 + WRAPPER_PAGES]
    print(f"== {pdf.name} report page {rpage} "
          f"({page.rect.width:.0f} x {page.rect.height:.0f} pt)")

    if what in ("all", "fills"):
        print("\n-- fills")
        for d in page.get_drawings():
            if d.get("fill") is None:
                continue
            r = d["rect"]
            if r.width < 3 or r.height < 3:
                continue
            txt = " ".join(page.get_text("text", clip=r).split())[:52]
            print(f"   {_hex(d['fill'])}  x {r.x0:7.1f}..{r.x1:7.1f} "
                  f"y {r.y0:7.1f}..{r.y1:7.1f}  w{r.width:6.1f} h{r.height:5.1f}  {txt}")

    if what in ("all", "rules"):
        print("\n-- vertical rules (x, y-extent, colour, width)")
        vs = []
        for d in page.get_drawings():
            for it in d["items"]:
                if it[0] == "l" and abs(it[1].x - it[2].x) < 0.6 and abs(it[1].y - it[2].y) > 4:
                    vs.append((round(it[1].x, 1), round(min(it[1].y, it[2].y), 1),
                               round(max(it[1].y, it[2].y), 1),
                               _hex(d.get("color")), round(d.get("width") or 0, 2)))
        for v in sorted(set(vs))[:40]:
            print(f"   x{v[0]:>7}  y {v[1]:>7}..{v[2]:<7}  {v[3]} {v[4]}pt")
        print(f"   ({len(set(vs))} distinct)")

    if what in ("all", "tables"):
        print("\n-- tables")
        for i, t in enumerate(page.find_tables().tables):
            b = t.bbox
            print(f"   [{i}] bbox x {b[0]:.1f}..{b[2]:.1f}  y {b[1]:.1f}..{b[3]:.1f}  "
                  f"rows={len(t.rows)} cols={t.col_count}")
            first = t.extract()[:2]
            for row in first:
                print(f"        {[ (c or '').replace(chr(10),' ')[:22] for c in row ]}")

    if what in ("all", "text"):
        print("\n-- text spans")
        rows = []
        for blk in page.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                for s in ln["spans"]:
                    t = s["text"].strip()
                    if t:
                        rows.append((round(s["bbox"][1], 1), round(s["bbox"][0], 1),
                                     round(s["bbox"][2], 1), round(s["size"], 1),
                                     s["font"].split("+")[-1], "#%06x" % s["color"], t[:46]))
        for r in sorted(rows)[:120]:
            print(f"   y{r[0]:>7} x {r[1]:>6}..{r[2]:<6} {r[3]:>4}pt {r[4]:<20} {r[5]} {r[6]}")
        print(f"   ({len(rows)} spans)")
        print("   line pitch:",
              Counter(round(b - a, 1) for a, b in
                      zip(sorted({r[0] for r in rows}), sorted({r[0] for r in rows})[1:])
                      if 0 < b - a < 40).most_common(8))
    doc.close()


if __name__ == "__main__":
    dump(sys.argv[1], int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "all")
