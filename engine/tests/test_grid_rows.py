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
