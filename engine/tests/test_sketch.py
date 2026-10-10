"""The built-in sketch's engine (DR §9): geometry, the area table, Save to report.

Run:  python -m pytest -q engine/tests/test_sketch.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import schema, sketch, templates  # noqa: E402

M = "{http://www.mismo.org/residential/2009/schemas}"


def rect(x, y, w, h, **kw):
    return {"points": [{"x": x, "y": y}, {"x": x + w, "y": y}, {"x": x + w, "y": y + h},
                       {"x": x, "y": y + h}], **kw}


def test_area_of_straight_and_curved_walls():
    sq = rect(0, 0, 10, 10)["points"]
    assert sketch.polygon_area(sq) == 100
    assert sketch.polygon_area(list(reversed(sq))) == 100      # either way round
    bay = [dict(p) for p in sq]
    bay[3]["b"] = -1                                           # a half-round end bowing out
    assert sketch.polygon_area(bay) == pytest.approx(100 + math.pi * 25 / 2)
    bay[3]["b"] = 1                                            # bowing in
    assert sketch.polygon_area(bay) == pytest.approx(100 - math.pi * 25 / 2)
    assert sketch.wall_lengths(bay)[3] == pytest.approx(math.pi * 5)
    angled = [{"x": 0, "y": 0}, {"x": 5, "y": 5}, {"x": 0, "y": 10}]
    assert sketch.wall_lengths(angled)[0] == pytest.approx(7.0711, abs=1e-4)


def test_the_table_like_the_aci_reference():
    """ACI's example: First Floor with an attached garage inside the outline,
    a Second Floor with an atrium open to below (a deduction)."""
    page = {"id": "p1", "areas": [
        rect(0, 0, 54, 32, id="f1", name="First Floor", floor="LevelOne"),
        rect(37, 0, 17, 16, id="g", name="1 Car Attached", floor="LevelOne", kind="garage"),
        rect(0, 40, 54, 32, id="f2", name="Second Floor", floor="LevelTwo"),
        rect(5, 45, 15, 21, id="at", name="Atrium", floor="LevelTwo", subtract=True),
        rect(0, 80, 30, 20, id="b", name="Basement", floor="BelowGradeOne", grade="PartiallyBelowGrade"),
        rect(0, 80, 10, 20, id="bu", name="Storage", floor="BelowGradeOne", finished=False),
    ], "labels": [{"text": "Bedroom", "x": 10, "y": 10}, {"text": "Bath", "x": 20, "y": 10},
                  {"text": "Half Bath", "x": 25, "y": 50}, {"text": "Garage", "x": 40, "y": 5},
                  {"text": "Kitchen", "x": 30, "y": 20}]}
    t = sketch.table({"pages": [page]})
    by = {s["id"]: s for s in t["shapes"]}
    assert by["at"]["area"] == -315 and by["at"]["subtract"]
    assert by["g"]["living"] is False and by["g"]["gla"] is False
    (u,) = t["units"]
    # the garage is drawn inside the first-floor outline: it is vehicle storage,
    # not living area, so it comes off the outline (as the atrium does upstairs)
    assert u["standard_above"] == 54 * 32 - 272 + 54 * 32 - 315
    assert u["levels"]["LevelOne"]["finished"] == 54 * 32 - 272
    assert u["levels"]["LevelTwo"]["finished"] == 54 * 32 - 315
    assert u["standard_below"] == 600 and u["unfinished_below"] == 200
    assert u["levels"]["BelowGradeOne"] == {"finished": 600, "unfinished": 200,
                                            "grade": "PartiallyBelowGrade", "title": ""}
    assert (u["bedrooms"], u["full_baths"], u["half_baths"]) == (1, 1, 1)
    assert "Kitchen" in u["rooms"]["LevelOne"]


def test_room_words():
    assert sketch.room_type("Half Bath") == "HalfBathroom"
    assert sketch.room_type("Bath") == "FullBathroom"
    assert sketch.room_type("Bedroom 2") == "Bedroom"
    assert sketch.room_type("Washer / Dryer") == "LaundryRoom"
    assert sketch.room_type("Garage") is None and sketch.room_type("Hall") is None


def _one_floor(units=1):
    areas = [rect(i * 40, 0, 30, 30, id=f"u{i + 1}", name=f"Unit {i + 1}", floor="LevelOne", unit=i + 1)
             for i in range(units)]
    labels = [{"text": "Bedroom", "x": i * 40 + 5, "y": 5} for i in range(units)] + \
             [{"text": "Bath", "x": i * 40 + 20, "y": 20} for i in range(units)]
    return {"pages": [{"id": "p1", "areas": areas, "labels": labels}]}


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_save_to_report_writes_valid_units_on_every_sample(key):
    tree = etree.parse(str(templates.get(key).path))
    n = len(sketch.subject_units(tree.getroot()))
    first = sketch.subject_units(tree.getroot())[0]
    other_above = sum(int(lv.findtext(f"{M}LevelFinishedAreaMeasure") or 0)
                      for lv in first.findall(f"{M}LEVELS/{M}LEVEL")
                      if lv.findtext(f"{M}LevelType") in sketch.ABOVE[1:])
    out = sketch.apply(tree, _one_floor(max(1, min(n, 4))))
    assert schema.validate(tree) == []
    unit = sketch.subject_units(tree.getroot())[0]
    area = unit.find(f"{M}PROPERTY_UNIT_AREA")
    assert area.findtext(f"{M}UnitStandardAboveGradeFinishedAreaMeasure") == str(900 + other_above)
    level = [lv for lv in unit.findall(f"{M}LEVELS/{M}LEVEL") if lv.findtext(f"{M}LevelType") == "LevelOne"]
    assert len(level) == 1 and level[0].findtext(f"{M}LevelFinishedAreaMeasure") == "900"
    assert unit.findtext(f"{M}PROPERTY_UNIT_DETAIL/{M}BedroomCount") is not None
    # saving again changes nothing and adds no second room or level
    again = sketch.apply(tree, _one_floor(max(1, min(n, 4))))
    assert again["changes"] == [] or all(c["what"] in ("BedroomCount", "FullBathroomCount",
                                                         "HalfBathroomCount", "LevelCount")
                                         and c["old"] == "" for c in again["changes"])
    assert len([r for r in unit.findall(f"{M}ROOMS/{M}ROOM")
                if r.findtext(f"{M}ROOM_DETAIL/{M}LevelType") == "LevelOne"]) == 2


def test_floors_the_sketch_does_not_draw_still_count():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))   # B1 1300/230, L1 1470, L2 1532
    out = sketch.apply(tree, _one_floor(1))                              # draws Level 1 only: 900
    unit = sketch.subject_units(tree.getroot())[0]
    area = unit.find(f"{M}PROPERTY_UNIT_AREA")
    assert area.findtext(f"{M}UnitStandardAboveGradeFinishedAreaMeasure") == str(900 + 1532)
    assert area.findtext(f"{M}UnitStandardBelowGradeFinishedAreaMeasure") == "1300"
    assert area.findtext(f"{M}UnitBelowGradeUnfinishedAreaMeasure") == "230"
    assert len(out["kept"]) == 2


def test_a_unit_the_report_does_not_have_is_named_not_invented():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    out = sketch.apply(tree, _one_floor(2))
    assert out["skipped"] == ["Unit 2 is not in this report (it has 1 unit(s))"]


def test_check_refuses_nonsense():
    with pytest.raises(ValueError):
        sketch.check({"pages": [{"areas": [{"floor": "Attic", "points": []}]}]})
    with pytest.raises(ValueError):
        sketch.check({"pages": [{"areas": [{"points": [{"x": float("inf"), "y": 0}]}]}]})
    assert sketch.check({"pages": []})["version"] == 1
