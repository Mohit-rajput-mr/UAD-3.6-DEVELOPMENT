"""Render a D-1 sample through the C-1 form engine and compare it with the GSE PDF.

    python engine/tests/render_form.py sf1_appraisal_v1_4 [pages...]

Writes ``_work/form/<key>.pdf`` and side-by-side PNGs (ours | GSE) for the
requested report pages, so the two can be read against each other.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pymupdf
from lxml import etree
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from uad import templates  # noqa: E402
from uad.report import flow  # noqa: E402
from uad.spec.measure_geometry import report_start  # noqa: E402

OUT = ROOT / "_work" / "form"


def main(key: str, pages: list[int]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tpl = templates.get(key)
    tree = etree.parse(str(tpl.path))
    t0 = time.time()
    html = flow.build(tree, folder=tpl.path.parent)
    (OUT / f"{key}.html").write_text(html, encoding="utf-8")
    pdf = OUT / f"{key}.pdf"
    flow.to_pdf(html, pdf)
    ours = pymupdf.open(pdf)
    gse = pymupdf.open(tpl.pdf)
    start = report_start(gse)
    print(f"{key}: ours {ours.page_count} pages, GSE {gse.page_count - start} "
          f"({time.time() - t0:.1f}s)")
    for n in pages:
        if n > ours.page_count:
            continue
        a = ours[n - 1].get_pixmap(dpi=72)
        ia = Image.frombytes("RGB", (a.width, a.height), a.samples)
        if start + n - 1 < gse.page_count:
            b = gse[start + n - 1].get_pixmap(dpi=72)
            ib = Image.frombytes("RGB", (b.width, b.height), b.samples)
        else:
            ib = Image.new("RGB", ia.size, "white")
        im = Image.new("RGB", (ia.width + ib.width + 12, max(ia.height, ib.height)), "#c00")
        im.paste(ia, (0, 0))
        im.paste(ib, (ia.width + 12, 0))
        im.save(OUT / f"{key}_p{n}.png")


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "sf1_appraisal_v1_4"
    pages = [int(x) for x in sys.argv[2:]] or [1, 2, 3]
    main(key, pages)
