"""Render one official sample through the engine and compare it with the GSE PDF.

The sample's own XML is the input, so anything the engine draws differently
from the published PDF is the engine's difference, not the data's.  This prints
the two page counts, the fonts actually embedded, and where the header and
footer land -- the first four of the eight checks the build has to pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import templates  # noqa: E402
from uad.report import paginate, urar  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "_work" / "render"


def describe(pdf: Path) -> dict:
    doc = pymupdf.open(pdf)
    fonts, sizes = set(), set()
    header_pages, footer_pages = [], []
    for i in range(doc.page_count):
        pg = doc[i]
        sizes.add((round(pg.rect.width, 1), round(pg.rect.height, 1)))
        for f in pg.get_fonts():
            fonts.add(f[3].split("+")[-1])
        for b in pg.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    if not s["text"].strip():
                        continue
                    if s["bbox"][1] < 50:
                        header_pages.append(i + 1)
                    elif s["bbox"][1] > pg.rect.height - 90:
                        footer_pages.append(i + 1)
    count = doc.page_count
    doc.close()
    return {"pages": count, "sizes": sorted(sizes),
            "fonts": sorted(fonts), "header_pages": sorted(set(header_pages)),
            "footer_pages": sorted(set(footer_pages))}


def main(key: str = "sf1_appraisal_v1_4") -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tpl = templates.get(key)
    tree = etree.parse(str(tpl.path))

    sections = urar.build(tree)
    meta = urar.Meta.from_case(tree)
    lead = urar.summary_lead(tree)
    rows = sum(len(s.rows) for s in sections)
    print(f"{tpl.name}")
    print(f"  sections drawn ... {len(sections)}")
    print(f"  rows drawn ....... {rows}")
    print(f"  footer refs ...... {meta.references}")

    html = paginate.build(sections, meta, lead)
    html_path = OUT / f"{key}.html"
    html_path.write_text(html, encoding="utf-8")
    pdf_path = OUT / f"{key}.pdf"
    paginate.to_pdf(html, pdf_path)

    ours = describe(pdf_path)
    theirs = describe(tpl.pdf) if tpl.pdf else {}
    print(f"\n  -> {pdf_path.name}  ({pdf_path.stat().st_size / 1024:.0f} KB)")
    print(f"     ours   pages={ours['pages']} size={ours['sizes']}")
    print(f"            fonts={ours['fonts']}")
    print(f"            header on pages {ours['header_pages'][:6]}"
          f"{'...' if len(ours['header_pages']) > 6 else ''}")
    if theirs:
        wrapper = 2
        print(f"     GSE    pages={theirs['pages'] - wrapper} (excluding the "
              f"{wrapper}-page spec wrapper) size={theirs['sizes']}")
        print(f"            fonts={theirs['fonts']}")
    print(f"\n  header absent on page 1: "
          f"{'yes' if 1 not in ours['header_pages'] else 'NO -- E-1 requires it absent'}")
    print(f"  footer on every page:    "
          f"{'yes' if len(ours['footer_pages']) == ours['pages'] else 'no'}")
    only_licensed = all("Myriad" in f or "Calibri" in f for f in ours["fonts"])
    print(f"  fonts limited to Myriad Pro / Calibri: "
          f"{'yes' if only_licensed else 'NO -- ' + str(ours['fonts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:] or [])))
