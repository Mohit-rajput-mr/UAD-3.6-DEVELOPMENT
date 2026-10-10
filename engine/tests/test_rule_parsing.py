"""H-1 conditions parse as written (E-161).

Two faults kept eight required-field rules from ever checking a dwelling unit:

* the tokenizer let an atom swallow a structural ")" ('Indicator = "true"))'),
  so UAD1146's "(Dwelling or (Outbuilding ...)) and RoomType = (...)" parsed
  as "Dwelling or (... and RoomType)";
* ``selects`` -- written to repair UAD1145's genuine precedence slip --
  forced every unit-level condition onto every branch, so "(Dwelling) or
  (Outbuilding and AccessoryDwellingUnitIndicator = true)" governed ADUs only.

Each rule is shown firing on a copy of an official sample with its data point
removed; the samples themselves stay clean (validated elsewhere for all 12).

Run:  python -m pytest -q engine/tests/test_rule_parsing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import compliance, templates


def _shape(e) -> str:
    if e.op == "leaf":
        return str(e.condition)
    if e.op == "true":
        return "TRUE"
    return e.op.upper() + "(" + ", ".join(_shape(x) for x in e.children) + ")"


def _rule(mid):
    return next(r for r in compliance.rules() if r.message_id == mid)


def test_a_closing_parenthesis_after_a_value_closes_the_group():
    tokens = compliance._tokenise('(A = "1" or (B = "2" and C = "3")) and D = ("x" or "y")')
    assert [k for k, _ in tokens].count("(") == [k for k, _ in tokens].count(")")
    assert _shape(_rule("UAD1146").antecedent).startswith('AND(OR(ImprovementType = "Dwelling"')


def test_only_a_top_level_mix_of_and_and_or_is_repaired():
    assert compliance.mixed_precedence(_rule("UAD1145").logic)          # the genuine slip
    for mid in ("UAD1146", "UAD1159", "UAD1160", "UAD1161", "UAD1173", "UAD1174",
                "UAD1175", "UAD1176", "UAD1688"):
        assert not compliance.mixed_precedence(_rule(mid).logic), mid


def _subject(node):
    return any(a.get("ValuationUseType") == "SubjectProperty" for a in node.iterancestors("{*}PROPERTY"))


@pytest.mark.parametrize("mid,key,name", [
    ("UAD1159", "2_to_4_unit_appraisal_v1_4", "UnitIncludedInRentScheduleIndicator"),
    ("UAD1160", "sf1_appraisal_v1_4", "InteriorConditionRatingCode"),
    ("UAD1161", "sf1_appraisal_v1_4", "InteriorQualityRatingCode"),
    ("UAD1173", "sf1_appraisal_v1_4", "OverallBathroomsUpdateStatusType"),
    ("UAD1174", "sf1_appraisal_v1_4", "BedroomCount"),
    ("UAD1175", "sf1_appraisal_v1_4", "FullBathroomCount"),
    ("UAD1176", "sf1_appraisal_v1_4", "HalfBathroomCount"),
    ("UAD1688", "sf1_appraisal_v1_4", "UnitInteriorDefectsExistIndicator"),
])
def test_a_dwelling_unit_missing_its_value_is_caught(mid, key, name):
    tree = etree.parse(str(templates.get(key).path))
    assert not any(f.message_id == mid and f.status == compliance.FINDING
                   for f in compliance.evaluate(tree))
    node = next(n for n in tree.getroot().iter(f"{{*}}{name}") if _subject(n))
    node.getparent().remove(node)
    assert any(f.message_id == mid and f.status == compliance.FINDING
               for f in compliance.evaluate(tree))


def test_uad1146_asks_kitchens_and_baths_only():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    rooms = [r for r in tree.getroot().iter("{*}ROOM") if _subject(r)]
    kitchen = next(r for r in rooms if r.findtext(".//{*}RoomType") == "Kitchen"
                   and r.find(".//{*}RoomUpdateStatusType") is not None)
    status = kitchen.find(".//{*}RoomUpdateStatusType")
    status.getparent().remove(status)
    assert any(f.message_id == "UAD1146" and f.status == compliance.FINDING
               for f in compliance.evaluate(tree))
