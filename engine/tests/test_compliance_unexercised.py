"""The H-1 rules no D-1 sample exercises still fire when they should (T-1034).

Of the 171 rules the presence engine cannot execute, 167 are decided on at
least one of the twelve samples by ``compliance_shapes`` /
``compliance_checks``.  The other four are written too, but no sample meets
their condition -- no GRM comparable carries an additional comparison row
(UAD1250), no subject unit has non-standard or unfinished area (UAD1777-
UAD1779) -- so the samples alone never show them firing.  Each is held here
to staying silent on the sample, firing on a copy broken the way the rule
describes, and falling silent again once the copy is mended.

Run:  python -m pytest -q engine/tests/test_compliance_unexercised.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, compliance, compliance_shapes as cs, templates

M = f"{{{bind.MISMO}}}"


def _rule(mid):
    return next(r for r in compliance.rules() if r.message_id == mid)


def test_every_rule_the_engine_cannot_execute_has_a_decider():
    """Every one of them is decided on some sample, or is one of the four
    held below."""
    roots = [templates.load(t.key).getroot() for t in templates.catalogue()]
    never = sorted(r.message_id for r in compliance.rules() if not r.executable
                   if all(cs.decide(root, r) is None for root in roots))
    assert never == ["UAD1250", "UAD1777", "UAD1778", "UAD1779"]


def _row(kind: str, ident: str) -> etree._Element:
    a = etree.Element(f"{M}COMPARABLE_ADJUSTMENT")
    etree.SubElement(a, f"{M}AdditionalComparisonLineItemIdentifier").text = ident
    etree.SubElement(a, f"{M}ComparableAdjustmentType").text = kind
    return a


def test_uad1250_a_grm_row_the_comparables_do_not_have():
    root = templates.load("2_to_4_unit_appraisal_v1_4").getroot()
    rule, kind = _rule("UAD1250"), "GrossRentMultiplierAdditionalNonAdjustableComparisonItem"
    assert cs.decide(root, rule) is None
    props = [p for p in root.iter(f"{M}PROPERTY")
             if p.get("ValuationUseType") in ("SubjectProperty", "GrossRentMultiplierComparable")]
    props[0].append(_row(kind, "Solar"))                 # the subject only
    assert cs.decide(root, rule) is True
    for p in props[1:]:
        p.append(_row(kind, "Solar"))                    # every GRM comparable too
    assert cs.decide(root, rule) is False


@pytest.mark.parametrize("mid, measure", [
    ("UAD1777", "UnitNonStandardBelowGradeFinishedAreaMeasure"),
    ("UAD1778", "UnitAboveGradeUnfinishedAreaMeasure"),
    ("UAD1779", "UnitNonStandardAboveGradeFinishedAreaMeasure"),
])
def test_an_area_the_subject_has_and_a_comparable_does_not(mid, measure):
    root = templates.load("sf1_appraisal_v1_4").getroot()
    rule = _rule(mid)
    assert cs.decide(root, rule) is None

    def give(prop, value):
        area = next(prop.iter(f"{M}PROPERTY_UNIT_AREA"))
        node = area.find(f"{M}{measure}")
        if node is None:
            node = etree.SubElement(area, f"{M}{measure}")
        node.text = value

    give(bind.subject(root), "120")
    assert cs.decide(root, rule) is True
    for p in root.iter(f"{M}PROPERTY"):
        if p.get("ValuationUseType") == "SalesComparable":
            give(p, "0")                                 # stated, even as none
    assert cs.decide(root, rule) is False
