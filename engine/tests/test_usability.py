"""B-1 Usability supplement items 6 and 10 as Review Master warnings
(T-909, T-910; tests the checks in uad/usability.py).

Every check is held to two things: the twelve D-1 samples raise nothing, and
a copy broken the way the supplement describes raises exactly the finding,
on the field that fixes it.

Run:  python -m pytest -q engine/tests/test_usability.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, review, templates, usability

M = f"{{{bind.MISMO}}}"
KEYS = [t.key if hasattr(t, "key") else t for t in templates.catalogue()]


def _tree(key):
    return etree.parse(str(templates.get(key).path))


def test_read_from_the_supplement():
    s = usability.spec()
    assert s["addendum"]["phrases"] == ["See attached addendum", "See Addenda"]
    a = s["as_is"]
    assert (a["action_point"], a["actions"], a["condition_point"], a["not"]) == (
        "DefectItemRecommendedActionType", ["Completion", "Inspection", "Repair"],
        "PropertyValuationConditionalConclusionType", "AsIs")
    assert a["condition_fids"][0] == "26.009"            # entered in Reconciliation, not the Summary
    r = s["ratings"][0]
    assert (r["rating_fid"], r["rating_point"], r["rating"]) == ("15.005", "OverallConditionRatingCode", "C1")
    assert r["display_fids"] == ["22.11.02", "1.031"]     # one data point, entered once
    assert [(q["fid"], q["point"], q["value"], q["rooms"]) for q in r["requires"]] == [
        ("3.017", "NewConstructionIndicator", "true", []),
        ("10.041", "RoomConditionStatusType", "NewOrLikeNew", ["Kitchen", "FullBathroom", "HalfBathroom"]),
        ("10.038", "RoomUpdateStatusType", "FullyUpdated", ["Kitchen", "FullBathroom", "HalfBathroom"]),
        ("10.043", "OverallBathroomsUpdateStatusType", "FullyUpdated", [])]


@pytest.mark.parametrize("key", KEYS)
def test_no_published_sample_is_faulted(key):
    assert usability.check(_tree(key)) == []


@pytest.mark.parametrize("text, hit", [
    ("See attached addendum.", True),
    ("See Addenda", True),
    ("Please see the attached addendum for the roof.", True),
    ("see addendum page 2", True),
    ("Roof replaced in 2021 per the seller; no addendum needed.", False),
    ("The seeded lawn is new.", False),
])
def test_item_6_see_addendum(text, hit):
    tree = _tree("sf1_appraisal_v1_4")
    note = next(n for n in tree.getroot().iter(M + "ValuationCommentText"))
    note.text = text
    found = usability.check(tree)
    assert bool(found) is hit
    if hit:
        assert found[0].code == "U6" and found[0].field_id == usability.field_of(note) != ""


def test_item_10_1_as_is_with_a_repair():
    tree = _tree("sf1_appraisal_v1_4")             # a Repair defect, Subject to Repair
    for n in tree.getroot().iter(M + "PropertyValuationConditionalConclusionType"):
        n.text = "AsIs"
    found = usability.check(tree)
    assert [(f.code, f.field_id) for f in found] == [("U10.1", "26.009")]
    assert "Repair" in found[0].message and "As Is" in found[0].message
    tree = _tree("sf1_appraisal_v1_4")
    for n in tree.getroot().iter(M + "DefectItemRecommendedActionType"):
        n.text = "None"
    for n in tree.getroot().iter(M + "PropertyValuationConditionalConclusionType"):
        n.text = "AsIs"
    assert usability.check(tree) == []              # no action needed: As Is stands


def test_item_10_2_c1_needs_its_support():
    tree = _tree("mh1_appraisal_v1_4")              # C1, new, every kitchen and bath new
    subject = bind.subject(tree.getroot())
    next(subject.iter(M + "NewConstructionIndicator")).text = "false"
    kitchen = next(d for d in subject.iter(M + "ROOM_DETAIL") if d.findtext(M + "RoomType") == "Kitchen")
    kitchen.find(M + "RoomUpdateStatusType").text = "PartiallyUpdated"
    found = usability.check(tree)
    assert [(f.code, f.field_id) for f in found] == [("U10.2", "3.017"), ("U10.2", "10.038")]
    assert "Kitchen" in found[1].message and "Partially Updated" in found[1].message
    next(subject.iter(M + "OverallConditionRatingCode")).text = "C2"
    assert usability.check(tree) == []              # C2 asks none of it


def test_warnings_in_the_review_master_never_block():
    tree = _tree("mh1_appraisal_v1_4")
    next(bind.subject(tree.getroot()).iter(M + "NewConstructionIndicator")).text = "false"
    report = review.build(tree)
    items = [i for i in report.items if i.source == review.USABILITY]
    assert [(i.code, i.severity, i.field_id, i.section) for i in items] == [
        ("U10.2", "Warning", "3.017", "Subject Property")]
    assert not any(i in report.fatal for i in items)    # an alert, never a block on signing


def test_a_warning_with_one_answer_offers_it():
    """T-510: "Subject to Repair" for a repair defect under "As Is"; "Yes" for
    New Construction under C1; nothing for a room (set in its own row) or for
    defects calling for two different actions."""
    tree = _tree("sf1_appraisal_v1_4")
    for n in tree.getroot().iter(M + "PropertyValuationConditionalConclusionType"):
        n.text = "AsIs"
    (f,) = usability.check(tree)
    assert f.fix == {"field_id": "26.009", "value": "SubjectToRepair",
                     "label": "Make it “Subject to Repair”"}
    acts = list(tree.getroot().iter(M + "DefectItemRecommendedActionType"))
    acts[0].text, acts[-1].text = "Repair", "Inspection"
    (f,) = usability.check(tree)
    assert f.fix is None
    tree = _tree("mh1_appraisal_v1_4")
    subject = bind.subject(tree.getroot())
    next(subject.iter(M + "NewConstructionIndicator")).text = "false"
    next(d for d in subject.iter(M + "ROOM_DETAIL")
         if d.findtext(M + "RoomType") == "Kitchen").find(M + "RoomUpdateStatusType").text = "NotUpdated"
    found = {f.field_id: f.fix for f in usability.check(tree)}
    assert found["3.017"] == {"field_id": "3.017", "value": "true", "label": "Make it “Yes”"}
    assert found["10.038"] is None
    assert any(i.fix for i in review.build(tree).items if i.source == review.USABILITY)
