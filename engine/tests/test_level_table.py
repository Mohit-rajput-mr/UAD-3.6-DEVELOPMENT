"""Unit Interior "Level and Room Detail" prints every level, as B-1 10.029-10.033 says.

One row per level, lowest grade first; "Finished" / "Unfinished" lines only when
that area is above zero; the room summary counted per RoomType per LevelType
("1 - Bath - Half").  Checked against the published D-1 PDFs (T-119).

Run:  python -m pytest -q engine/tests/test_level_table.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from lxml import etree, html as lhtml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad.report import form  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "specs" / "official"
SAMPLES = sorted(p for p in ROOT.glob("Appendix D-1 *_Appraisal/*_Appraisal_v1.4.xml"))


def _rows(xml: Path) -> list[list[str]]:
    doc = lhtml.fromstring(form.galley_html(form.build(etree.parse(str(xml))), edit=False))
    out = []
    for tb in doc.iter("table"):
        if "Level in Unit" in tb.text_content():
            for tr in tb.iter("tr"):
                out.append([" / ".join(t.strip() for t in td.itertext() if t.strip())
                            for td in tr if isinstance(td.tag, str)])
    return out


def test_sf1_matches_the_published_table():
    rows = _rows(next(p for p in SAMPLES if p.name.startswith("SF1_")))
    assert rows[1] == ["Level B1", "Partially Below Grade / Interior and Exterior Access / Walk Out",
                       "Finished", "1,300 Sq. Ft.",
                       "1 - Bath - Half / 1 - Media Room / 1 - Recreation Room / 1 - Wet Bar"]
    assert rows[2] == ["", "", "Unfinished", "230 Sq. Ft.", ""]
    assert rows[3][:4] == ["Level 1", "Above Grade", "Finished", "1,470 Sq. Ft."]
    assert rows[4][0] == "Level 2" and rows[4][4] == "2 - Bath - Full / 4 - Bedroom / 1 - Laundry Room"
    assert len(rows) == 5, rows      # no Unfinished line where the area is 0


def test_level_order_is_lowest_grade_first():
    order = ["BelowGradeTwo", "BelowGradeOne", "LevelOne", "LevelTwo", "LevelTen"]
    assert sorted(reversed(order), key=form.level_rank) == order


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="pdftotext is not installed")
@pytest.mark.parametrize("xml", SAMPLES, ids=lambda p: p.stem)
def test_every_printed_cell_is_in_the_published_pdf(xml):
    text = subprocess.run(["pdftotext", "-layout", str(next(xml.parent.glob("*.pdf"))), "-"],
                          capture_output=True, text=True).stdout
    flat = re.sub(r"\s+", " ", text)
    for row in _rows(xml)[1:]:
        for cell in row:
            for part in filter(None, cell.split(" / ")):
                assert part in flat, (xml.stem, part)
