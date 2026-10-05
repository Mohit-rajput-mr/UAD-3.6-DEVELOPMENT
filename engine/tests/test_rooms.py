"""Rooms and levels edited where the report lists them (uad/rooms.py).

The owner asked to add rooms and levels on the report itself.  A room is a
ROOM on a level (B-1 10.029-10.033); the counts B-1 prints beside the table
(Levels in Unit 10.017, Total Bedrooms 10.023, Total Bathrooms 10.024/10.025)
follow from them, as the D-1 samples keep them equal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, rooms, schema, templates  # noqa: E402
from uad.report import form  # noqa: E402

M = f"{{{bind.MISMO}}}"


def _sf1():
    return templates.load("sf1_appraisal_v1_4")


def _level(tree, kind):
    return next(lv for lv in tree.getroot().iter(f"{M}LEVEL") if lv.findtext(f"{M}LevelType") == kind)


def _summary(tree):
    lv = _level(tree, "LevelTwo")
    holder = lv.getparent().getparent()
    return form.room_summary(holder.findall(f"{M}ROOMS/{M}ROOM"))["LevelTwo"]


def _detail(tree, name):
    return tree.getroot().find(f".//{M}PROPERTY_UNIT_DETAIL/{M}{name}").text


def test_the_d1_counts_already_equal_the_rooms():
    tree = _sf1()
    unit = _level(tree, "LevelOne").getparent().getparent()
    assert rooms.recount(unit) == {}          # SF1 is consistent: nothing to change


def test_a_room_added_and_removed_moves_the_counts_with_it():
    tree = _sf1()
    before = schema.validate(tree)
    lv = _level(tree, "LevelTwo")
    rooms.add_room(lv, "Bedroom")
    assert "5 - Bedroom" in _summary(tree) and _detail(tree, "BedroomCount") == "6"
    rooms.add_room(lv, "Other", "Sun Porch")
    assert "1 - Sun Porch" in _summary(tree)
    assert rooms.remove_room(lv, "Bedroom")
    assert "4 - Bedroom" in _summary(tree) and _detail(tree, "BedroomCount") == "5"
    assert rooms.remove_room(lv, "Other", "sun porch")
    assert not any("Sun Porch" in s for s in _summary(tree))
    assert len(schema.validate(tree)) == len(before)


def test_the_answered_room_survives_when_one_of_two_is_removed():
    tree = _sf1()
    lv = _level(tree, "LevelOne")
    rooms.add_room(lv, "Kitchen")                 # a second, unanswered kitchen
    rooms.remove_room(lv, "Kitchen")
    kitchens = [r for r in rooms.rooms_on(lv) if r.findtext(f"{M}ROOM_DETAIL/{M}RoomType") == "Kitchen"]
    assert len(kitchens) == 1
    assert kitchens[0].findtext(f"{M}ROOM_DETAIL/{M}RoomQualityDescription")    # the answered one


def test_removing_a_level_takes_its_rooms_and_the_count():
    tree = _sf1()
    gone = rooms.remove_level(_level(tree, "BelowGradeOne"))
    assert gone == 4
    assert _detail(tree, "LevelCount") == "2" and _detail(tree, "HalfBathroomCount") == "0"


def test_other_needs_its_description_and_a_level_its_type():
    tree = _sf1()
    with pytest.raises(ValueError):
        rooms.add_room(_level(tree, "LevelOne"), "Other", "")


def test_the_editor_draws_the_controls_and_the_print_does_not():
    tree = _sf1()
    edit_html = form.galley_html(form.build(tree, edit=True), edit=True)
    print_html = form.galley_html(form.build(tree), edit=False)
    assert "data-room-add" in edit_html and "data-level-del" in edit_html and "data-room-inc" in edit_html
    assert "data-room-add" not in print_html


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    from app import api
    from app.access import sign_in
    from app.cases import Store
    from app.main import app
    api.STORE = Store(tmp_path / "cases")
    api.RENDERER = None
    api.LAYOUTS = None
    with TestClient(app) as c:
        sign_in(c)
        yield c


def test_the_api_adds_and_removes_rooms_and_levels(client):
    from app import api
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False}).json()["case_id"]
    tree = api.store().tree(cid)
    key = tree.getpath(_level(tree, "LevelTwo"))
    r = client.post(f"/api/cases/{cid}/rooms", json={"level": key, "type": "Bedroom"})
    assert r.status_code == 200, r.text and r.json()["said"] == {"BedroomCount": "6"}
    assert _detail(api.store().tree(cid), "BedroomCount") == "6"
    r = client.delete(f"/api/cases/{cid}/rooms", params={"level": key, "type": "Bedroom"})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/cases/{cid}/rooms", json={"level": key, "type": "Other"}).status_code == 422
    r = client.delete(f"/api/cases/{cid}/levels", params={"level": key})
    assert r.status_code == 200 and r.json()["said"]["rooms_removed"] == 7
    assert _detail(api.store().tree(cid), "LevelCount") == "2"
