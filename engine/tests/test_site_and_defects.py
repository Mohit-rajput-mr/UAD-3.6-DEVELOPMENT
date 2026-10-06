"""Site and defect tables against the official D-1 PDFs (E-107..E-111).

Each check names what the official sample PDF prints, so a failure here is a
departure from the published report, not from our own earlier output.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, templates  # noqa: E402
from uad.report import form  # noqa: E402


def _text(key: str, section: str) -> str:
    blocks = form.build(templates.load(key))
    parts = []
    for b in blocks:
        if not b.visible or not b.section.startswith(section):
            continue
        if b.left or b.right:
            parts += [f"{i.label} {' '.join(i.values)}" for i in b.left + b.right if i.visible]
        else:
            parts.append(html.unescape(re.sub(r"<[^>]+>", " ", b.html or b.title)))
    return " ".join(" ".join(parts).split())


def test_commentary_categories_resolve_from_the_label():
    # a control character in the regex had stopped every label-derived category
    cats = bind.commentary_categories()
    assert cats["4.030"] == "SiteInfluences"
    assert cats["4.042"] == "SiteViews"
    # B-1 misspells the energy category; A-1's enumeration is what is written
    assert cats["6.016"] == "EnergyEfficientAndGreenFeatures"


def test_site_influence_and_view_commentary_print():
    site = _text("2_to_4_unit_appraisal_v1_4", "Site")
    assert "Site Influence Commentary Additional commentary" in site
    assert "View Commentary Additional commentary" in site


def test_site_influence_rows_carry_proximity_and_impact():
    site = _text("2_to_4_unit_appraisal_v1_4", "Site")
    assert "Busy Roadway Bordering Adverse Site fronts" in site
    # scenario 2 has two influences; the second keeps its own name
    two = _text("2_to_4_unit_scenario_2_appraisal_v1_2", "Site")
    assert "Residential Bordering Neutral" in two


def test_corner_unit_prints_no():
    unit = _text("condo1_appraisal_v1_4", "Unit Interior")
    assert "Corner Unit No" in unit


@pytest.mark.parametrize("key,heads", [
    ("2_to_4_unit_appraisal_v1_4", ["Dwelling Exterior - Building 1", "Unit Interior - Building 1 - Unit 1",
                                    "Dwelling Exterior - Building 2", "Unit Interior - Building 2 - Unit 2"]),
    ("mh1_appraisal_v1_4", ["Outbuilding - Barn"]),
    ("condo1_appraisal_v1_4", ["Unit Interior", "Subject Property Amenities"]),
])
def test_reconciliation_defects_group_by_structure_in_order(key, heads):
    text = _text(key, "Reconciliation")
    at = [text.find(h) for h in heads]
    assert all(a >= 0 for a in at), (heads, at)
    assert at == sorted(at)


def test_defect_rows_list_by_feature_then_location():
    text = _text("2_to_4_unit_appraisal_v1_4", "Reconciliation")
    unit1 = text[text.find("Unit Interior - Building 1 - Unit 1"):text.find("Dwelling Exterior - Building 2")]
    order = [unit1.find(w) for w in ("Appliances Kitchen", "Cabinetry Full Bathroom",
                                     "Cabinetry Kitchen", "Doors Full Bathroom", "Walls and Ceiling")]
    assert all(o >= 0 for o in order) and order == sorted(order), order
