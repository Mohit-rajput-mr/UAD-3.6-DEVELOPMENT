"""Which sections a report has follows from its data, as B-1 states it.

The rules are B-1's own "the section displays when ..." sentences
(spec/section_display.json, uad/spec/extract_section_display.py), evaluated
on the subject where the data points are the subject's.  Checked against the
GSE's own D-1 Sample Scenario Matrix: for every sample, Rental Information,
Income Approach, Cost Approach, outbuildings and PUD / project are exactly the
ones the matrix ticks.

Run:  python -m pytest -q engine/tests/test_section_display.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import templates  # noqa: E402
from uad.paths import SPEC_ROOT  # noqa: E402
from uad.report import form  # noqa: E402

openpyxl = pytest.importorskip("openpyxl")


def _matrix() -> dict[str, dict[str, str]]:
    path = next(SPEC_ROOT.rglob("Appendix D-1 URAR Sample Scenario Matrix v1.3.xlsx"))
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[[n for n in wb.sheetnames if n.startswith("Scenario Matrix")][0]]
    rows = [["" if c is None else " ".join(str(c).split()) for c in r] for r in ws.iter_rows(values_only=True)]
    head = next(r for r in rows if r and r[0].startswith("Sample Scenario"))
    out = {}
    for r in rows[rows.index(head) + 1:]:
        if r and r[0]:
            out[r[0]] = dict(zip(head, r))
    return out


def _key(scenario: str) -> str | None:
    m = re.search(r"\((\w+)\)", scenario)
    code = m.group(1).lower() if m else ""
    if scenario.startswith("2- to 4-Unit Scenario 2"):
        return "2_to_4_unit_scenario_2_appraisal_v1_2"
    if scenario.startswith("2- to 4-Unit"):
        return "2_to_4_unit_appraisal_v1_4"
    if "Scenario - A" in scenario:
        return None                          # SF5-A is SF5 set in Calibri
    hits = [t.key for t in templates.catalogue() if t.key.startswith(code + "_")]
    return hits[0] if hits else None


ROWS = [(k, s, row) for s, row in _matrix().items() if (k := _key(s))]


@pytest.mark.parametrize("key,scenario,row", ROWS, ids=[k for k, _s, _r in ROWS])
def test_sections_follow_the_scenario_matrix(key, scenario, row):
    ctx = form.Ctx(templates.load(key).getroot())
    tick = lambda col: "√" in row.get(col, "")                     # noqa: E731
    assert form.section_shown(ctx, "Rental Information") == tick("Rental Information"), scenario
    assert form.section_shown(ctx, "Income Approach") == tick("Income Approach"), scenario
    assert form.section_shown(ctx, "Cost Approach") == tick("Cost Approach"), scenario
    assert form.section_shown(ctx, "Outbuilding") == bool(row.get("Subject Has Outbuilding(s)")), scenario
    assert form.section_shown(ctx, "Project Information") == bool(row.get("PUD / Project")), scenario
    assert form.section_shown(ctx, "Manufactured Home") == ("Manufactured" in row.get("Construction Method", ""))
