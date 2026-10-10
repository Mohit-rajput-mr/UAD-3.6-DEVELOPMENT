"""Rows B-1 prints whether or not they hold data (T-120).

B-1 p140: "Electricity, Sanitary Sewer, and Water always display as row
headers and in alphabetical order on the report."  Gas is not among them: D-1
2-4 has no gas and prints no Gas row.

Run:  python -m pytest -q engine/tests/test_row_headers.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, templates
from uad.report import form

SPEC = Path(__file__).resolve().parents[1] / "spec" / "row_headers.json"


def _utility_rows(tree) -> list[str]:
    html = form.galley_html(form.build(tree, folder=None, edit=False), edit=False)
    i = html.find("Utilities and Impact")
    seg = html[i:html.find("Apparent Defects", i)]
    rows = re.findall(r"<tr>(.*?)</tr>", seg, re.S)
    firsts = [re.sub(r"<[^>]+>", "", r.split("</td>")[0].split("</th>")[0]).strip() for r in rows]
    return [f for f in firsts if f and "Public" not in f]          # not the column heads


def test_the_rule_is_read_from_b1():
    rules = json.loads(SPEC.read_text(encoding="utf-8"))["tables"]
    assert [(r["page"], r["rows"]) for r in rules] == [(140, ["Electricity", "Sanitary Sewer", "Water"])]


def test_no_utility_answered_still_prints_the_three_headers():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    for u in list(bind.subject(tree.getroot()).iter("{*}SITE_UTILITY")):
        u.getparent().remove(u)
    assert _utility_rows(tree) == ["Electricity", "Sanitary Sewer", "Water"]   # alphabetical, no Gas


def test_samples_print_what_they_hold():
    two_four = etree.parse(str(templates.get("2_to_4_unit_appraisal_v1_4").path))
    assert _utility_rows(two_four) == ["Electricity", "Sanitary Sewer", "Water"]   # D-1: no gas
    sf1 = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    assert _utility_rows(sf1) == ["Electricity", "Gas", "Sanitary Sewer", "Water"]
