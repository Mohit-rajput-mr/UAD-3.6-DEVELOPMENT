"""Measure the URAR's rules, columns and fills off the sample PDFs.

Where ``measure_geometry`` establishes the page and its furniture, this pass
looks at the lines and boxes the form is actually drawn with: the vertical
column boundaries, the horizontal rules between rows, their weights and
colours, and what the coloured fills in the samples really are.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

from measure_geometry import ROOT, WRAPPER_PAGES, samples  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "spec" / "page_rules.json"


def _hex(c) -> str:
    if c is None:
        return "none"
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in c)


def _q(x: float, step: float = 0.5) -> float:
    return round(round(x / step) * step, 3)


def scan(limit_samples: int | None = None) -> dict:
    vert: Counter = Counter()
    horiz_w: Counter = Counter()
    stroke_colour: Counter = Counter()
    fill_colour: Counter = Counter()
    fill_examples: dict[str, list] = defaultdict(list)
    tab_rows: list[dict] = []
    grid_cols: Counter = Counter()

    for pdf in samples()[:limit_samples]:
        doc = pymupdf.open(pdf)
        for pno in range(WRAPPER_PAGES, doc.page_count):
            page = doc[pno]
            W = page.rect.width
            for d in page.get_drawings():
                col = _hex(d.get("color"))
                fill = _hex(d.get("fill"))
                width = d.get("width") or 0
                r = d["rect"]
                if d["type"] in ("s", "fs") and d.get("color") is not None:
                    stroke_colour[(col, round(width, 2))] += 1
                if d["type"] in ("f", "fs") and d.get("fill") is not None:
                    if 0 <= r.x0 <= W and r.width > 4 and 0 < r.height <= 60:
                        fill_colour[(fill, _q(r.height, 0.1))] += 1
                        if len(fill_examples[fill]) < 4:
                            words = page.get_text("text", clip=r).strip()
                            fill_examples[fill].append({
                                "x0": _q(r.x0), "x1": _q(r.x1),
                                "w": _q(r.width), "h": _q(r.height, 0.1),
                                "page": pno - WRAPPER_PAGES + 1,
                                "file": pdf.name,
                                "text": " ".join(words.split())[:60],
                            })
                        if fill in ("#231f20", "#000000") and r.height > 10:
                            tab_rows.append({
                                "x0": _q(r.x0), "x1": _q(r.x1), "h": _q(r.height, 0.1),
                                "text": " ".join(page.get_text("text", clip=r).split())[:50],
                            })
                    # a rule drawn as a thin filled rectangle
                    if r.height <= 1.5 and r.width > 20:
                        horiz_w[(fill, _q(r.height, 0.05))] += 1
                    if r.width <= 1.5 and r.height > 6:
                        vert[_q(r.x0)] += 1

            # vertical strokes: the grid's column boundaries
            for d in page.get_drawings():
                for item in d["items"]:
                    if item[0] == "l":
                        p1, p2 = item[1], item[2]
                        if abs(p1.x - p2.x) < 0.6 and abs(p1.y - p2.y) > 5:
                            vert[_q(p1.x)] += 1
                        elif abs(p1.y - p2.y) < 0.6 and abs(p1.x - p2.x) > 20:
                            horiz_w[(_hex(d.get("color")), round(d.get("width") or 0, 2))] += 1

            for table in page.find_tables().tables:
                xs = sorted({_q(c) for c in _col_edges(table)})
                if len(xs) >= 4:
                    grid_cols[tuple(xs)] += 1
        doc.close()

    return {
        "source": "Appendix D-1 sample appraisal PDFs",
        "vertical_line_x": [{"x": x, "pica": round(x / 12, 3), "count": n}
                            for x, n in vert.most_common(24)],
        "horizontal_rules": [{"colour": c, "width": w, "count": n}
                             for (c, w), n in horiz_w.most_common(12)],
        "stroke_colours": [{"colour": c, "width": w, "count": n}
                           for (c, w), n in stroke_colour.most_common(12)],
        "fills": [{"colour": c, "height": h, "count": n}
                  for (c, h), n in fill_colour.most_common(16)],
        "fill_examples": {k: v for k, v in fill_examples.items()},
        "tab_widths": Counter((t["x0"], t["x1"]) for t in tab_rows).most_common(12),
        "tab_labels": Counter(t["text"] for t in tab_rows).most_common(40),
        "table_column_sets": [{"cols": list(cols), "count": n}
                              for cols, n in grid_cols.most_common(10)],
    }


def _col_edges(table) -> list[float]:
    edges: list[float] = []
    for cell in (table.header.cells if table.header else []):
        if cell:
            edges.extend([cell[0], cell[2]])
    for row in table.rows:
        for cell in row.cells:
            if cell:
                edges.extend([cell[0], cell[2]])
    return edges


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    data = scan(limit)
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"-> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    print("   vertical line x (pt, pica, n):")
    for v in data["vertical_line_x"][:14]:
        print(f"      {v['x']:>7} {v['pica']:>7}  x{v['count']}")
    print(f"   horizontal rules ... {data['horizontal_rules'][:6]}")
    print(f"   stroke colours ..... {data['stroke_colours'][:6]}")
    print(f"   fills .............. {data['fills'][:8]}")
    for colour, ex in list(data["fill_examples"].items())[:8]:
        print(f"      {colour}: {ex[:2]}")
    print(f"   tab x-extents ...... {data['tab_widths'][:6]}")
    print(f"   tab labels ......... {[t[0] for t in data['tab_labels'][:12]]}")
    for cs in data["table_column_sets"][:4]:
        print(f"   table cols x{cs['count']}: {cs['cols']}")


if __name__ == "__main__":
    main()
