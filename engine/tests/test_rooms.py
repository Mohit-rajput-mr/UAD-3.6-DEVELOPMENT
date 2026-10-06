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


# ------------------------------------------------- the tables that follow
def _table_text(tree, start):
    import html, re
    for b in form.build(tree):
        t = " ".join(html.unescape(re.sub("<[^>]+>", " ", b.html or "")).split())
        # Unit Interior's Interior Features (Dwelling Exterior's table has the same heads)
        if b.visible and t.startswith(start) and (start != "Feature Detail Quality Comment" or "Flooring" in t):
            return t
    return ""


def test_every_kitchen_and_bath_prints_kitchens_first():
    """T-119: SF1 p8 lists the kitchen, three full baths and the half bath;
    the reader took only the first room (and printed the Wet Bar)."""
    text = _table_text(_sf1(), "Room Update Status")
    assert text.index("Kitchen Level 1") < text.index("Bath - Full") < text.index("Bath - Half Level B1")
    assert text.count("Bath - Full") == 3 and "Wet Bar" not in text
    assert "Corian Countertops, Double Oven, Hardwood floors." in text
    assert "5-10 years" in text                        # Time Frame of the updated half bath only


def test_every_flooring_type_prints_and_walls_and_ceiling_joins_its_values():
    text = _table_text(_sf1(), "Feature Detail Quality Comment")
    for f in ("Carpet", "Ceramic Tile", "Engineered Wood", "Hardwood"):
        assert f in text
    assert "8 Ft. | 9 Ft. | 10 or more feet | 2 or more stories | Cathedral | Coffered | Flat" in text


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_the_unit_tables_hold_every_room_and_floor_of_every_sample(key):
    tree = templates.load(key)
    root = tree.getroot()
    kb = sum(1 for d in root.iter(f"{M}ROOM_DETAIL")
             if d.findtext(f"{M}RoomType") in ("Kitchen", "FullBathroom", "HalfBathroom")
             and d.getparent().getparent().getparent().getparent().getparent() is not None)
    printed = "".join(
        b.html or "" for b in form.build(tree) if b.visible and "Room</span>" in (b.html or ""))
    rows = printed.count("<tr>")
    # each kitchen/bath of the subject's units prints one row (comparables have none)
    subject = bind.subject(root)
    want = sum(1 for d in subject.iter(f"{M}ROOM_DETAIL")
               if d.findtext(f"{M}RoomType") in ("Kitchen", "FullBathroom", "HalfBathroom")) if subject is not None else 0
    assert rows >= want


def test_a_flooring_type_is_added_and_removed(client):
    from app import api
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False}).json()["case_id"]
    tree = api.store().tree(cid)
    unit = tree.getpath(next(tree.getroot().iter(f"{M}PROPERTY_UNIT")))
    r = client.post(f"/api/cases/{cid}/flooring", json={"unit": unit, "type": "Vinyl"})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/cases/{cid}/flooring", json={"unit": unit, "type": "Vinyl"}).status_code == 422
    tree = api.store().tree(cid)
    assert "Vinyl" in _table_text(tree, "Feature Detail Quality Comment")
    fc = next(f for f in tree.getroot().iter(f"{M}FLOOR_COVERING") if f.findtext(f"{M}FlooringType") == "Vinyl")
    r = client.delete(f"/api/cases/{cid}/rows", params={"key": tree.getpath(fc), "tag": "FLOOR_COVERING"})
    assert r.status_code == 200, r.text
    assert "Vinyl" not in _table_text(api.store().tree(cid), "Feature Detail Quality Comment")
    assert client.delete(f"/api/cases/{cid}/rows", params={"key": "x", "tag": "PARTY"}).status_code == 400


def test_a_blank_unit_offers_flooring_and_points_to_rooms():
    tree = templates.load("sf1_appraisal_v1_4", blank=True)
    html_ = form.galley_html(form.build(tree, edit=True), edit=True)
    assert "data-floor-add" in html_ and "Kitchens and baths are added" in html_


def _amenities(tree):
    return _table_text(tree, "Amenity Category")


def test_an_amenity_is_added_in_its_category_and_removed(client):
    from app import api
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False}).json()["case_id"]
    r = client.patch(f"/api/cases/{cid}/cells/14.002",
                     json={"value": "Gazebo", "new": True, "data_point": "AmenityType"})
    assert r.status_code == 200, r.text
    tree = api.store().tree(cid)
    text = _amenities(tree)
    # B-1 14.002 files a Gazebo under Outdoor Living, after the Porch
    assert text.index("Outdoor Living") < text.index("Gazebo") < text.index("Whole Home")
    am = next(a for a in bind.subject(tree.getroot()).iter(f"{M}AMENITY")
              if a.findtext(f".//{M}AmenityType") == "Gazebo")
    r = client.delete(f"/api/cases/{cid}/rows", params={"key": tree.getpath(am), "tag": "AMENITY"})
    assert r.status_code == 200, r.text
    assert "Gazebo" not in _amenities(api.store().tree(cid))


def test_a_rental_grid_per_unit_writes_into_that_units_pairing(client):
    from app import api
    from uad.report import comparables
    cid = client.post("/api/cases", json={"template": "2_to_4_unit_appraisal_v1_4", "blank": False}).json()["case_id"]
    grids = comparables.build(api.store().tree(cid), "rental")
    assert [g.subject_label for g in grids] == ["Subject Unit 1", "Subject Unit 2"]
    assert grids[1].comparables == ["Comparable #1", "Comparable #4", "Comparable #5"]
    adjusted = next(r for r in grids[1].rows if r.label == "Adjusted Rent")
    scope = adjusted.cells[0].scope
    assert scope
    r = client.patch(f"/api/cases/{cid}/comparables/1/fields/{adjusted.comp_fid}",
                     json={"kind": "rental", "value": "950", "scope": scope})
    assert r.status_code == 200, r.text
    again = comparables.build(api.store().tree(cid), "rental")
    rent = lambda g: next(r for r in g.rows if r.label == "Adjusted Rent").cells[0].text
    assert rent(again[1]) == "$950"
    assert rent(again[0]) == "$900"          # Unit 1's pairing with #1 is untouched


def test_a_cost_line_edited_under_its_outbuilding_lands_in_that_cost_block(client):
    """The Cost Approach draws a Depreciated Cost block per improvement, each
    reading the cost block its IsAssociatedWith arc ties to it; an edit in
    the Barn's block writes the Barn's cost, not the dwelling's or garage's."""
    import re
    from app import api
    from uad.report import form
    cid = client.post("/api/cases", json={"template": "mh1_appraisal_v1_4", "blank": False}).json()["case_id"]
    blocks = form.build(api.store().tree(cid), edit=True)
    i = next(n for n, b in enumerate(blocks) if b.kind == "h1" and b.title.endswith("Outbuilding - Barn"))
    table = next(b for b in blocks[i:] if b.kind == "table")
    cell = re.search(r"data-tf='25\.027' data-tk='([^']*)'[^>]*data-tscope='([^']*)'", table.html)
    assert cell, table.html[:400]
    r = client.patch(f"/api/cases/{cid}/cells/25.027",
                     json={"value": "16000", "key": cell.group(1), "scope": cell.group(2)})
    assert r.status_code == 200, r.text
    root = api.store().tree(cid).getroot()
    X = "{http://www.w3.org/1999/xlink}"
    amounts = {c.get(f"{X}label").rsplit("_", 1)[-1]: [e.text for e in c.iter(f"{M}ReplacementOrReproductionCostAmount")]
               for c in root.iter(f"{M}IMPROVEMENT_COST_AND_DEPRECIATED_VALUE")}
    assert amounts["BARN"] == ["16000"]
    assert amounts["DWELLING"] == ["149995"] and amounts["GARAGE"] == ["15554", "9446"]


def test_a_transfer_rows_data_source_is_written_tied_to_that_transfer(client):
    """Subject Transfer History: each row's Data Source (21.005) is the
    DATA_SOURCE tied to that SALES_HISTORY by arcrole (A-1's ArcRoles sheet),
    so the editor offers it on the row and the write lands on that row."""
    import re
    from app import api
    from uad.report import form
    assert form.data_source_target("21.005") == "SALES_HISTORY"
    assert form.data_source_target("21.001") == "PriorSalesOrTransfersIndicator"
    cid = client.post("/api/cases", json={"template": "sf2_appraisal_v1_4", "blank": False}).json()["case_id"]
    html = "".join(b.html for b in form.build(api.store().tree(cid), edit=True) if b.html)
    cell = re.search(r"data-tf='21\.005' data-tk='([^']*)'", html)
    assert cell
    r = client.patch(f"/api/cases/{cid}/cells/21.005",
                     json={"value": "Deed", "key": cell.group(1), "data_point": "DataSourceType"})
    assert r.status_code == 200, r.text
    tree = api.store().tree(cid)
    X = "{http://www.w3.org/1999/xlink}"
    root = tree.getroot()
    labels = {ds.get(f"{X}label") for ds in root.iter(f"{M}DATA_SOURCE")
              if (ds.findtext(f"{M}DataSourceType") or "") == "Deed"}
    tied = [rel.get(f"{X}to") for rel in root.iter(f"{M}RELATIONSHIP")
            if rel.get(f"{X}from") in labels and rel.get(f"{X}arcrole", "").endswith("IsDataSourceFor_SALES_HISTORY")]
    assert tied, "no Deed source tied to a transfer"
    again = "".join(b.html for b in form.build(tree, edit=True) if b.html)
    assert re.search(r"data-tf='21\.005'[^>]*>[^<]*Deed", again)


def test_each_lien_column_writes_its_own_blanket_financing(client):
    """Project Blanket Financing: B-1 displays 18.029-18.063 "for each
    LienPriorityType", a column per lien.  A Second Lien value is written to
    the SecondLien block (created with its priority), never over the first."""
    import re
    from app import api
    from uad.report import form
    cid = client.post("/api/cases", json={"template": "coop1_appraisal_v1_4", "blank": True}).json()["case_id"]
    html = "".join(b.html for b in form.build(api.store().tree(cid), edit=True) if b.html)

    def cell(fid):
        m = re.search(rf"data-tf='{re.escape(fid)}' data-tk='([^']*)'([^>]*)", html)
        assert m, fid
        sel = re.search(r"data-tsel='([^']*)' data-tlab='([^']*)'", m.group(2))
        return {"key": m.group(1), **({"sel": sel.group(1), "label": sel.group(2)} if sel else {})}

    for fid, value in (("18.029", "100000"), ("18.038", "50000")):
        r = client.patch(f"/api/cases/{cid}/cells/{fid}", json={"value": value, **cell(fid)})
        assert r.status_code == 200, r.text
        html = "".join(b.html for b in form.build(api.store().tree(cid), edit=True) if b.html)
    root = api.store().tree(cid).getroot()
    liens = {(f.findtext(f"{M}LienPriorityType") or "").strip(): (f.findtext(f"{M}UPBAmount") or "")
             for f in root.iter(f"{M}PROJECT_BLANKET_FINANCING")}
    assert liens.get("SecondLien") == "50000", liens
    assert "100000" in liens.values(), liens
    # the priority fields are not offered as loose pickers under the table
    assert "data-fid='18.037'" not in html and "data-fid='18.028'" not in html


def test_a_lien_payment_typed_marks_the_payment_available(client):
    import re
    from app import api
    from uad.report import form
    cid = client.post("/api/cases", json={"template": "coop1_appraisal_v1_4", "blank": True}).json()["case_id"]
    html = "".join(b.html for b in form.build(api.store().tree(cid), edit=True) if b.html)
    m = re.search(r"data-tf='18\.033' data-tk='([^']*)' data-tdp='([^']*)' data-k='([^']*)'", html)
    assert m and m.group(2) == "TotalPaymentAmount" and m.group(3) == "amount", m and m.groups()
    r = client.patch(f"/api/cases/{cid}/cells/18.033", json={"value": "6364", "key": m.group(1),
                                                              "data_point": m.group(2)})
    assert r.status_code == 200, r.text
    root = api.store().tree(cid).getroot()
    pbf = next(f for f in root.iter(f"{M}PROJECT_BLANKET_FINANCING") if f.findtext(f"{M}TotalPaymentAmount"))
    assert pbf.findtext(f"{M}PaymentAmountAvailableIndicator") == "true"


def test_an_outbuilding_area_cell_writes_its_measure(client):
    """12.013 Total Area holds one data point, carried with its unit
    attribute: the cell is a number and writes the measure."""
    import re
    from app import api
    from uad.report import form
    cid = client.post("/api/cases", json={"template": "mh1_appraisal_v1_4", "blank": False}).json()["case_id"]
    html = form.galley_html(form.build(api.store().tree(cid), edit=True), edit=True)
    m = re.search(r"""data-tf=["']12\.013["'] data-tk=["']([^"']*)["'] data-tdp=["']([^"']*)["'] data-k=["']([^"']*)["'][^>]*?data-tscope=["']([^"']*)["']""", html)
    assert m and m.group(2) == "StructureExcludingVehicleStorageAndADUUnfinishedAreaMeasure" and m.group(3) == "number", m and m.groups()
    r = client.patch(f"/api/cases/{cid}/cells/12.013", json={"value": "130", "key": m.group(1),
                                                              "data_point": m.group(2), "scope": m.group(4) or ""})
    assert r.status_code == 200, r.text
    root = api.store().tree(cid).getroot()
    assert "130" in [e.text for e in root.iter(f"{M}StructureExcludingVehicleStorageAndADUUnfinishedAreaMeasure")]
