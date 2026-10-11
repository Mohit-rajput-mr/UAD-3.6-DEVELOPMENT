"""Rows the appraiser adds to a comparable grid (T-1070, DR §7).

B-1 gives each grid group an "[Additional Row]" (and "[Other Exterior /
Interior Feature]") the appraiser names; A-1 keeps the name against the
subject and every comparable.  The owner saw "Name this row" rows spawn by
themselves (screenshots 02, 03): the editor drew an empty named row under
every group -- and, on a 2-4 unit report, once per unit -- and a new one
appeared under each row named.  Now:

* a fresh report's grid has no row without a name; each group has a "+";
* naming the row the "+" opened adds exactly one row, once per grid (not per
  unit), for every property; the name is a text box and comes back on reload;
* a named row's cells write into that row, not into the group's first;
* the x removes the row and every element it made;
* a non-adjustable row keeps its own type; a renamed component keeps one name.

Run:  python -m pytest -q engine/tests/test_grid_rows.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import lxml.html
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, schema  # noqa: E402
from uad.report import comparables  # noqa: E402

M = f"{{{bind.MISMO}}}"
ADJUSTABLE = "SalesComparableAdditionalAdjustableComparisonItem"
NON_ADJUSTABLE = "SalesComparableAdditionalNonAdjustableComparisonItem"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app

    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        yield c
    store.conn.close()


def new_case(client, template: str, blank: bool) -> str:
    r = client.post("/api/cases", json={"template": template, "blank": blank, "name": "rows"})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


def name_row(client, cid, name, was="", container="COMPARABLE_ADJUSTMENT", line_type=ADJUSTABLE):
    return client.put(f"/api/cases/{cid}/comparables/lineitems",
                      json={"kind": "sales", "container": container, "adjust_type": line_type,
                            "was": was, "name": name})


def root_of(cid):
    return api.STORE.tree(cid).getroot()


def everywhere(root):
    subject = bind.subject(root)
    return [subject] + comparables.properties(root, "SalesComparable")


def items(prop, name):
    return [n for n in prop.iter(f"{M}COMPARABLE_ADJUSTMENT")
            if (n.findtext(f"{M}AdditionalComparisonLineItemIdentifier") or "") == name]


def page(html: str):
    return lxml.html.fromstring(html)


def name_boxes(html: str) -> list[str]:
    """The value of every row-name box the editor draws."""
    return [i.get("value", "") for i in page(html).xpath("//input[@class='liin']")]


def plus_buttons(html: str) -> list[str]:
    """The type each "+" adds a row under."""
    return [s.get("data-lit", "") for s in page(html).xpath("//span[@class='liaddbtn']")]


def blocks(cid) -> int:
    return len(comparables.build(root_of(cid), "sales", every_row=True))


@pytest.mark.parametrize("template", ["sf1_appraisal_v1_4", "sf3_appraisal_v1_4",
                                      "mh1_appraisal_v1_4", "2_to_4_unit_appraisal_v1_4"])
def test_a_fresh_report_has_no_row_without_a_name(client, template):
    cid = new_case(client, template, blank=True)
    html = client.get(f"/api/cases/{cid}/form").text
    assert "" not in name_boxes(html), "an empty named row was drawn by itself"
    assert not page(html).xpath("//*[@data-li and @contenteditable]"), "the old self-made name row is back"
    adds = plus_buttons(html)
    # the adjustable additional row is the property's, not a unit's: one "+"
    # per grid block on every report, a 2-4 unit and an ADU included
    assert adds.count(ADJUSTABLE) == blocks(cid), adds


def test_plus_adds_exactly_one_row_and_the_name_comes_back(client):
    cid = new_case(client, "2_to_4_unit_appraisal_v1_4", blank=True)
    assert name_row(client, cid, "Pool").status_code == 200
    root = root_of(cid)
    for prop in everywhere(root):
        got = items(prop, "Pool")
        assert len(got) == 1, "the name is kept once for every property"
        assert got[0].findtext(f"{M}ComparableAdjustmentType") == ADJUSTABLE
    html = client.get(f"/api/cases/{cid}/form").text
    # once per grid block -- before, once per unit of the 2-4 report, and a
    # fresh empty row under it
    assert name_boxes(html).count("Pool") == blocks(cid)
    assert "" not in name_boxes(html)
    assert name_row(client, cid, "Pool").status_code == 422, "a second row of the same name"
    assert not schema.validate(api.STORE.tree(cid))


def test_a_named_rows_cells_write_into_that_row(client):
    """D-1 SF1 has "Below Grade Exterior Access" ($2,000 on #1).  A second
    row's description was refused (its field is an adjustment's path) and its
    adjustment was written over the first row's."""
    cid = new_case(client, "sf1_appraisal_v1_4", blank=False)
    assert name_row(client, cid, "Pool").status_code == 200
    line = {"kind": "sales", "item_name": "Pool", "container": "COMPARABLE_ADJUSTMENT",
            "line_type": ADJUSTABLE}
    r = client.patch(f"/api/cases/{cid}/comparables/1/fields/22.07.44",
                     json={**line, "data_point": "AdditionalComparisonLineItemDescription",
                           "value": "In-ground"})
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "In-ground"
    r = client.patch(f"/api/cases/{cid}/comparables/1/fields/adjustment",
                     json={**line, "adjust_type": ADJUSTABLE, "value": "-5000"})
    assert r.status_code == 200, r.text
    comp = comparables.properties(root_of(cid), "SalesComparable")[0]
    pool, = items(comp, "Pool")
    assert pool.findtext(f"{M}AdditionalComparisonLineItemDescription") == "In-ground"
    assert pool.findtext(f"{M}ComparableAdjustmentAmount") == "-5000"
    first, = items(comp, "Below Grade Exterior Access")
    assert first.findtext(f"{M}ComparableAdjustmentAmount") == "2000", "the first row was overwritten"
    grid = comparables.build(root_of(cid), "sales")[0]
    row = next(r for r in grid.rows if r.label == "Pool")
    assert row.cells[0].text == "In-ground" and row.cells[0].adjustment
    assert not schema.validate(api.STORE.tree(cid))


def test_the_x_removes_the_row_and_every_element_it_made(client):
    cid = new_case(client, "sf1_appraisal_v1_4", blank=True)

    def shape():
        # what each property keeps of its adjustments (the totals the grid
        # math recalculates on any change are not the row's)
        # (an empty COMPARABLE a blank report starts with may be reused for
        # the row and leaves with it: edit.add_instance / remove_block, T-509)
        return [[(e.tag, (e.text or "").strip()) for held in p.iter(f"{M}COMPARABLE_ADJUSTMENTS")
                 for e in held.iter() if isinstance(e.tag, str)]
                + [len(c) for c in p.iter(f"{M}COMPARABLE") if len(c)]
                for p in everywhere(root_of(cid))]
    before = shape()
    assert name_row(client, cid, "Pool").status_code == 200
    assert name_row(client, cid, "Deck", was="Pool").status_code == 200      # renamed
    assert all(len(items(p, "Deck")) == 1 and not items(p, "Pool") for p in everywhere(root_of(cid)))
    r = name_row(client, cid, "", was="Deck")
    assert r.status_code == 200 and r.json()["removed"]
    assert not any(items(p, "Deck") for p in everywhere(root_of(cid)))
    assert shape() == before, "the containers made for the row were left behind"
    assert not [e for tag in ("COMPARABLE", "COMPARABLE_ADJUSTMENTS")
                for e in root_of(cid).iter(f"{M}{tag}") if not len(e)], "an empty container was left"
    assert "Deck" not in name_boxes(client.get(f"/api/cases/{cid}/form").text)

    # D-1 SF1's own row: the subject keeps nothing else under COMPARABLE, so
    # taking the row out must not leave an empty COMPARABLE_ADJUSTMENTS behind
    cid = new_case(client, "sf1_appraisal_v1_4", blank=False)
    assert name_row(client, cid, "", was="Below Grade Exterior Access").status_code == 200
    root = root_of(cid)
    assert not any(items(p, "Below Grade Exterior Access") for p in everywhere(root))
    assert not [e for tag in ("COMPARABLE", "COMPARABLE_ADJUSTMENTS")
                for e in root.iter(f"{M}{tag}") if not len(e)], "an empty container was left"
    assert "Below Grade Exterior Access" not in [
        r.label for g in comparables.build(root, "sales") for r in g.rows]
    assert not schema.validate(api.STORE.tree(cid))


def test_a_non_adjustable_row_keeps_its_own_type(client):
    """With no outbuilding the Outbuilding group is not drawn, so the type's
    template before it (Vehicle Storage) is where its "+" is; and the row is
    kept as non-adjustable -- the first template found made it adjustable."""
    cid = new_case(client, "sf1_appraisal_v1_4", blank=True)
    html = client.get(f"/api/cases/{cid}/form").text
    assert NON_ADJUSTABLE in plus_buttons(html)
    assert name_row(client, cid, "Carport Condition", line_type=NON_ADJUSTABLE).status_code == 200
    subject = bind.subject(root_of(cid))
    kept, = items(subject, "Carport Condition")
    assert kept.findtext(f"{M}ComparableAdjustmentType") == NON_ADJUSTABLE
    r = client.patch(f"/api/cases/{cid}/comparables/1/fields/22.13.03",
                     json={"kind": "sales", "item_name": "Carport Condition",
                           "container": "COMPARABLE_ADJUSTMENT", "line_type": NON_ADJUSTABLE,
                           "data_point": "AdditionalComparisonLineItemDescription", "value": "Good"})
    assert r.status_code == 200, r.text
    printed = [r.label for g in comparables.build(root_of(cid), "sales") for r in g.rows]
    assert "Carport Condition" in printed, "a described non-adjustable row was never printed"


def test_a_renamed_component_row_keeps_one_name(client):
    cid = new_case(client, "sf1_appraisal_v1_4", blank=True)
    for name, was in (("Solar Screens", ""), ("Shutters", "Solar Screens")):
        r = name_row(client, cid, name, was=was, container="STRUCTURE_COMPONENT", line_type="")
        assert r.status_code == 200, r.text
    subject = bind.subject(root_of(cid))
    names = [n.text for n in subject.iter(f"{M}ImprovementComponentTypeOtherDescription")]
    assert names == ["Shutters"], names
    assert not schema.validate(api.STORE.tree(cid))


def test_a_rental_row_kept_per_subject_unit(client):
    """D-1 2-4 Scenario 2 keeps "Amenities" once per subject unit each rental
    comparable is compared with (#1 against Unit A and against Unit B).  A
    rename reaches every one of them, and a value typed in Unit B's grid is
    Unit B's pairing's -- not the first one the property holds."""
    cid = new_case(client, "2_to_4_unit_scenario_2_appraisal_v1_2", blank=False)
    rental = "ADDITIONAL_RENTAL_COMPARISON_ITEM"

    def count(name):
        return sum(1 for n in root_of(cid).iter(f"{M}{rental}")
                   if n.findtext(f".//{M}AdditionalComparisonLineItemIdentifier") == name)
    held = count("Amenities")
    assert held > 4
    r = client.put(f"/api/cases/{cid}/comparables/lineitems",
                   json={"kind": "rental", "container": rental, "adjust_type": "",
                         "was": "Amenities", "name": "Outdoor Space"})
    assert r.status_code == 200, r.text
    assert (count("Amenities"), count("Outdoor Space")) == (0, held)

    def unit_row(label):
        grid = next(g for g in comparables.build(root_of(cid), "rental")
                    if g.subject_label.endswith(label))
        return grid, next(r for r in grid.rows if r.label == "Outdoor Space")
    _, row_a = unit_row("Unit A")
    grid_b, row_b = unit_row("Unit B")
    assert grid_b.numbers[0] == 1 and row_a.cells[0].text == row_b.cells[0].text == "Patio"
    r = client.patch(f"/api/cases/{cid}/comparables/1/fields/{row_b.comp_fid}",
                     json={"kind": "rental", "item_name": "Outdoor Space", "container": rental,
                           "line_type": "", "data_point": "AdditionalComparisonLineItemDescription",
                           "value": "Pool", "scope": row_b.cells[0].scope})
    assert r.status_code == 200, r.text
    _, row_a = unit_row("Unit A")
    _, row_b = unit_row("Unit B")
    assert (row_a.cells[0].text, row_b.cells[0].text) == ("Patio", "Pool")
    assert not schema.validate(api.STORE.tree(cid))


# -- a row kept inside an IMPROVEMENT is each dwelling's / unit's own (T-1202)

def _components(block, container, name):
    return [n for n in block.iter(f"{M}{container}")
            if comparables._inside(n, "ImprovementComponentTypeOtherDescription") == name]


def _copy(root, name, fid, group):
    """The built row ``name`` in one copy of its group ("unit 2")."""
    grid = comparables.build(root, "sales", every_row=True)[0]
    return next(r for r in grid.rows
                if r.item_name == name and r.subject_fid == fid and r.group == group)


def test_an_interior_feature_is_named_written_and_read_per_unit(client):
    """B-1 22.09.08 "[Other Interior Feature]" is drawn under every unit of a
    2-4 report (D-1 2-4: Unit 1, Unit 2).  It was made in the first unit
    only, so the row drawn under Unit 2 wrote into Unit 1's block and read
    Unit 1's value back."""
    cid = new_case(client, "2_to_4_unit_appraisal_v1_4", blank=False)
    r = name_row(client, cid, "Wet Bar", container="INTERIOR_COMPONENT", line_type="")
    assert r.status_code == 200, r.text
    root = root_of(cid)
    for prop in everywhere(root):
        units = comparables._units(prop, False)
        assert len(units) == 2
        assert [len(_components(u, "INTERIOR_COMPONENT", "Wet Bar")) for u in units] == [1, 1], \
            "the row is kept once in every unit it is drawn under"

    one = _copy(root, "Wet Bar", "22.09.09", "unit 1")
    two = _copy(root, "Wet Bar", "22.09.09", "unit 2")
    assert two.subject_scope and two.cells[0].scope
    assert (one.subject_scope, one.cells[0].scope) != (two.subject_scope, two.cells[0].scope)
    # the editor names that block on the cell, so its write goes there
    html = client.get(f"/api/cases/{cid}/form").text
    drawn = set(page(html).xpath("//td[@data-gf='22.09.24' and @data-gc='1']/@data-gs"))
    assert {one.cells[0].scope, two.cells[0].scope} <= drawn

    line = {"kind": "sales", "item_name": "Wet Bar", "container": "INTERIOR_COMPONENT",
            "line_type": "", "data_point": "ImprovementComponentQualitySummaryDescription"}
    r = client.patch(f"/api/cases/{cid}/comparables/1/fields/22.09.24",
                     json={**line, "value": "Granite top", "scope": two.cells[0].scope})
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "Granite top"
    r = client.patch(f"/api/cases/{cid}/comparables/0/fields/22.09.09",
                     json={**line, "value": "Marble top", "scope": two.subject_scope})
    assert r.status_code == 200, r.text
    # the condition row (B-1 22.09.15) keeps its own value in the same block
    worn = _copy(root, "Wet Bar", "22.09.16", "unit 2")
    assert worn.cells[0].scope == two.cells[0].scope
    r = client.patch(f"/api/cases/{cid}/comparables/1/fields/22.09.30",
                     json={**line, "data_point": "ImprovementComponentConditionSummaryDescription",
                           "value": "Worn", "scope": worn.cells[0].scope})
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "Worn"

    root = root_of(cid)
    comp = comparables.properties(root, "SalesComparable")[0]
    first, second = (_components(u, "INTERIOR_COMPONENT", "Wet Bar")[0]
                     for u in comparables._units(comp, False))
    assert not comparables._inside(first, "ImprovementComponentQualitySummaryDescription"), \
        "Unit 2's value was written into Unit 1's block"
    assert comparables._inside(second, "ImprovementComponentQualitySummaryDescription") == "Granite top"
    assert comparables._inside(second, "ImprovementComponentConditionSummaryDescription") == "Worn", \
        "the condition was written as the quality"
    assert _copy(root, "Wet Bar", "22.09.16", "unit 2").cells[0].text == "Worn"
    one = _copy(root, "Wet Bar", "22.09.09", "unit 1")
    two = _copy(root, "Wet Bar", "22.09.09", "unit 2")
    assert (one.subject, one.cells[0].text) == ("", "")
    assert (two.subject, two.cells[0].text) == ("Marble top", "Granite top")

    # the cell editor opens on that unit's own value
    rows = client.get(f"/api/cases/{cid}/comparables", params={"kind": "sales"}).json()["rows"]
    row = next(x for x in rows if x["item_name"] == "Wet Bar" and x["subject_fid"] == "22.09.09")
    point = "ImprovementComponentQualitySummaryDescription"
    assert row["cells"][0]["blocks"][two.cells[0].scope] == {point: "Granite top"}
    assert row["cells"][0]["blocks"][one.cells[0].scope] == {}
    assert row["subject_blocks"][two.subject_scope] == {point: "Marble top"}

    # a rename and the x reach every unit's copy
    assert name_row(client, cid, "Bar", was="Wet Bar", container="INTERIOR_COMPONENT",
                    line_type="").status_code == 200
    root = root_of(cid)
    assert not any(_components(p, "INTERIOR_COMPONENT", "Wet Bar") for p in everywhere(root))
    assert all(len(_components(p, "INTERIOR_COMPONENT", "Bar")) == 2 for p in everywhere(root))
    assert not schema.validate(api.STORE.tree(cid))
    assert name_row(client, cid, "", was="Bar", container="INTERIOR_COMPONENT",
                    line_type="").status_code == 200
    assert not any(_components(p, "INTERIOR_COMPONENT", "Bar") for p in everywhere(root_of(cid)))
    assert not schema.validate(api.STORE.tree(cid))


def test_an_exterior_feature_is_kept_per_dwelling(client):
    """B-1 22.08.07 "[Other Exterior Feature]" is drawn per dwelling (D-1
    2-4: Building 1, Building 2).  A choice (22.08.28, a condition status)
    made under Building 2 is Building 2's, and its editor opens on it; a
    comparable with one building has no Building 2 to keep it in, so that
    cell takes no value (written, it landed in Building 1)."""
    cid = new_case(client, "2_to_4_unit_appraisal_v1_4", blank=True)
    r = name_row(client, cid, "Solar Panels", container="STRUCTURE_COMPONENT", line_type="")
    assert r.status_code == 200, r.text
    root = root_of(cid)
    for prop in everywhere(root):
        dwellings = comparables._dwellings(prop)
        assert [len(_components(d, "STRUCTURE_COMPONENT", "Solar Panels")) for d in dwellings] \
            == [1] * len(dwellings)

    two = _copy(root, "Solar Panels", "22.08.15", "dwelling 2")
    assert two.cells[0].scope and not two.cells[2].scope, "comparable #3 has one building"
    html = client.get(f"/api/cases/{cid}/form").text
    assert page(html).xpath(f"//td[@data-gf='22.08.28' and @data-gs='{two.cells[0].scope}']")
    assert not page(html).xpath("//td[@data-gf='22.08.28' and @data-gc='3' and not(@data-gs)]"), \
        "a cell with no building to keep its value is still written"

    r = client.patch(f"/api/cases/{cid}/comparables/1/fields/22.08.28",
                     json={"kind": "sales", "item_name": "Solar Panels",
                           "container": "STRUCTURE_COMPONENT", "line_type": "",
                           "data_point": "ImprovementComponentConditionStatusType",
                           "value": "NewOrLikeNew", "scope": two.cells[0].scope})
    assert r.status_code == 200, r.text
    root = root_of(cid)
    one = _copy(root, "Solar Panels", "22.08.15", "dwelling 1")
    two = _copy(root, "Solar Panels", "22.08.15", "dwelling 2")
    assert not one.cells[0].text and two.cells[0].text == "New or Like New"
    rows = client.get(f"/api/cases/{cid}/comparables", params={"kind": "sales"}).json()["rows"]
    row = next(x for x in rows if x["item_name"] == "Solar Panels" and x["subject_fid"] == "22.08.15")
    point = "ImprovementComponentConditionStatusType"
    assert row["cells"][0]["blocks"][two.cells[0].scope] == {point: "NewOrLikeNew"}
    assert row["cells"][0]["blocks"][one.cells[0].scope] == {}
    assert row["cells"][0]["parts"] == {}, "the editor offered another building's value"
