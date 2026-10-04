"""Measure the URAR page from the official samples.

Appendix E states the page furniture in picas and percentages of black.  This
module does not take those numbers on trust -- it measures them off the twelve
Appendix D-1 sample reports, so the engine is built to what the GSEs actually
publish.  Every value written out carries the sample and page it came from.

Each sample is bound behind a specification wrapper whose length varies -- two
pages for most, three for Condo2 -- so the report's first page is found by its
footer rather than assumed.  Anything before it belongs to the wrapper, not the
form.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pymupdf

# UAD36_SPECS, else the folder's own specs/official (see engine/uad/spec/paths.py)
ROOT = Path(__import__("os").environ.get("UAD36_SPECS")
            or Path(__file__).resolve().parents[3] / "specs" / "official")
OUT = Path(__file__).resolve().parents[2] / "spec" / "page_geometry.json"
PT_PER_PICA = 12.0

# Each sample is bound behind a specification wrapper, and the wrapper is not
# always the same length: Condo2 runs to three pages where the others run to
# two.  So the report's first page is found rather than assumed -- it is the
# first page carrying the form's own footer.
WRAPPER_PAGES = 2                      # the usual case, kept for callers
FOOTER_MARK = "Fannie Mae | Freddie Mac"


def report_start(doc) -> int:
    for i in range(doc.page_count):
        pg = doc[i]
        for block in pg.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for s in line["spans"]:
                    if (s["bbox"][1] > pg.rect.height - 90
                            and FOOTER_MARK in s["text"]):
                        return i
    return WRAPPER_PAGES


def samples() -> list[Path]:
    """One copy of each D-1 sample, preferring the outer unzipped folder."""
    seen: dict[str, Path] = {}
    for p in sorted(ROOT.rglob("*_Appraisal_v1.*.pdf")):
        seen.setdefault(p.name, p)
    return list(seen.values())


def _round(x: float, q: float = 0.1) -> float:
    return round(round(x / q) * q, 4)


def _spans(page) -> list[dict]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for s in line["spans"]:
                text = s["text"].strip()
                if text:
                    out.append({
                        "text": text, "x0": s["bbox"][0], "y0": s["bbox"][1],
                        "x1": s["bbox"][2], "y1": s["bbox"][3],
                        "size": round(s["size"], 1),
                        "font": s["font"].split("+")[-1],
                        "colour": "#%06x" % s["color"],
                    })
    return out


def _fills(page) -> list[dict]:
    """Filled rectangles -- the section tabs and subsection bars."""
    out = []
    for d in page.get_drawings():
        if d["type"] not in ("f", "fs"):
            continue
        fill = d.get("fill")
        if fill is None:
            continue
        r = d["rect"]
        if r.width < 20 or r.height <= 0 or r.height > 40:
            continue
        out.append({
            "x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1,
            "w": r.width, "h": r.height,
            "colour": "#%02x%02x%02x" % tuple(round(c * 255) for c in fill),
        })
    return out


def _edge_report(values):
    c = Counter(values)
    total = sum(c.values()) or 1
    return [{"pt": v, "pica": round(v / PT_PER_PICA, 3), "count": n,
             "pct": round(100 * n / total, 1)} for v, n in c.most_common(12)]


def measure() -> dict:
    sizes = Counter()
    header_left, header_right, header_y = [], [], []
    footer_left, footer_right_label, footer_right_value = [], [], []
    pages_without_header = []
    tabs, bars = [], []
    text_x0, text_x1 = [], []
    files = []

    for pdf in samples():
        doc = pymupdf.open(pdf)
        start = report_start(doc)
        files.append({"file": pdf.name, "pdf_pages": doc.page_count,
                      "wrapper_pages": start,
                      "report_pages": doc.page_count - start})
        for pno in range(start, doc.page_count):
            page = doc[pno]
            H, W = page.rect.height, page.rect.width
            sizes[(round(W, 1), round(H, 1))] += 1
            rpage = pno - start + 1
            spans = _spans(page)

            top = [s for s in spans if s["y1"] < 60]
            if top:
                for s in top:
                    (header_left if s["x0"] < W / 2 else header_right).append(s)
                    header_y.append(_round(s["y0"]))
            else:
                pages_without_header.append((pdf.name, rpage))

            for s in spans:
                if s["y0"] > H - 90:
                    if s["x0"] < W / 2:
                        footer_left.append(s)
                    elif s["font"].endswith("Bold"):
                        footer_right_label.append(s)
                    else:
                        footer_right_value.append(s)
                elif s["y1"] >= 60:
                    text_x0.append(_round(s["x0"], 0.5))
                    text_x1.append(_round(s["x1"], 0.5))

            for f in _fills(page):
                (tabs if f["colour"] in ("#000000", "#231f20") else bars).append(f)
        doc.close()

    def summarise(spans):
        c = Counter((s["font"], s["size"], s["colour"]) for s in spans)
        return [{"font": f, "size": z, "colour": col, "count": n}
                for (f, z, col), n in c.most_common(6)]

    def edge(spans, which):
        return Counter(_round(s[which], 0.5) for s in spans).most_common(6)

    return {
        "source": "Appendix D-1 sample appraisal PDFs",
        "wrapper_pages": WRAPPER_PAGES,
        "samples": files,
        "page_size_pt": [{"w": w, "h": h, "pages": n}
                         for (w, h), n in sizes.most_common()],
        "header": {
            "pages_without_header": Counter(p for _, p in pages_without_header).most_common(),
            "left": summarise(header_left),
            "right": summarise(header_right),
            "left_x0": edge(header_left, "x0"),
            "right_x1": edge(header_right, "x1"),
            "baseline_y0": Counter(header_y).most_common(4),
        },
        "footer": {
            "left": summarise(footer_left),
            "left_x0": edge(footer_left, "x0"),
            "left_y0": Counter(_round(s["y0"]) for s in footer_left).most_common(6),
            "right_label": summarise(footer_right_label),
            "right_label_x1": edge(footer_right_label, "x1"),
            "right_value_x0": edge(footer_right_value, "x0"),
            "right_y0": Counter(_round(s["y0"]) for s in footer_right_label).most_common(6),
        },
        "body": {
            "left_edges": _edge_report(text_x0),
            "right_edges": _edge_report(text_x1),
        },
        "tabs": {
            "colours": Counter(t["colour"] for t in tabs).most_common(4),
            "heights": Counter(_round(t["h"]) for t in tabs).most_common(6),
            "widths": Counter(_round(t["w"], 0.5) for t in tabs).most_common(8),
            "x0": Counter(_round(t["x0"], 0.5) for t in tabs).most_common(6),
            "count": len(tabs),
        },
        "bars": {
            "colours": Counter(b["colour"] for b in bars).most_common(6),
            "heights": Counter(_round(b["h"]) for b in bars).most_common(6),
            "widths": Counter(_round(b["w"], 0.5) for b in bars).most_common(8),
            "x0": Counter(_round(b["x0"], 0.5) for b in bars).most_common(8),
            "count": len(bars),
        },
    }


def main() -> None:
    data = measure()
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"-> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    print(f"   samples measured ... {len(data['samples'])}")
    print(f"   page sizes ......... {data['page_size_pt']}")
    print(f"   header left ........ {data['header']['left'][:2]}")
    print(f"   header right ....... {data['header']['right'][:2]}")
    print(f"   header y ........... {data['header']['baseline_y0'][:3]}")
    print(f"   header left x0 ..... {data['header']['left_x0'][:3]}")
    print(f"   header right x1 .... {data['header']['right_x1'][:3]}")
    print(f"   pages w/o header ... {data['header']['pages_without_header']}")
    print(f"   footer left ........ {data['footer']['left'][:2]}")
    print(f"   footer left y ...... {data['footer']['left_y0']}")
    print(f"   footer label x1 .... {data['footer']['right_label_x1'][:3]}")
    print(f"   footer value x0 .... {data['footer']['right_value_x0'][:3]}")
    print(f"   tabs ............... {data['tabs']['count']} "
          f"h={data['tabs']['heights'][:3]} w={data['tabs']['widths'][:3]} "
          f"x0={data['tabs']['x0'][:3]} col={data['tabs']['colours']}")
    print(f"   bars ............... {data['bars']['count']} "
          f"colours={data['bars']['colours'][:4]} h={data['bars']['heights'][:3]} "
          f"w={data['bars']['widths'][:4]} x0={data['bars']['x0'][:4]}")
    print("   body left edges .... "
          f"{[(e['pt'], e['pica'], e['pct']) for e in data['body']['left_edges'][:6]]}")
    print("   body right edges ... "
          f"{[(e['pt'], e['pica'], e['pct']) for e in data['body']['right_edges'][:6]]}")


if __name__ == "__main__":
    main()
