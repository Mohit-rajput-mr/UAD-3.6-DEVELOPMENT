"""A defect entered in one unit's table opens that unit's gate (T-1204).

A defect is kept at property level (PROPERTY_DEFECT) and tied to the unit,
building or garage it is in by DEFECT_ContainsDefectOf_<it> (D-1 2-4).  Its
data points wait on that one's "defects exist?" answer (A-1: IF
UnitInteriorDefectsExistIndicator = "true"), and writing the defect answers
it.  The gate was walked down its own A-1 path from the top of the document,
so a defect entered in Unit 2's table opened *Unit 1's* gate.  Unit 2's
question then read unanswered beside an answered one, the editor's
visibility (T-1066) left Unit 2's whole table out, and the row just added
vanished on the next draw.  ``edit._gate_anchor`` walks the gate from the
block the row stands for.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import html as lhtml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind  # noqa: E402
from uad.report import form  # noqa: E402

M = f"{{{bind.MISMO}}}"
X = "{http://www.w3.org/1999/xlink}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "RENDERER", None)
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        yield c
    store.conn.close()


def _editor(case: str):
    st = api.store()
    return lhtml.fromstring(form.galley_html(
        form.build(st.tree(case), folder=st.folder(case), edit=True), edit=True))


def _empty_lines(doc, fid: str) -> list:
    return [e for e in doc.iter() if e.get("data-tf") == fid and e.get("data-tnew")]


def _drawn_in(doc, fid: str) -> list[str]:
    """The unit each drawn row of this column belongs to, by its copy's scope."""
    return [e.get("data-tscope") for e in doc.iter() if e.get("data-tf") == fid and e.get("data-tk")]


@pytest.mark.parametrize("copy", [0, 1])
def test_a_units_defect_opens_that_units_gate_and_stays_in_its_table(client, copy):
    case = client.post("/api/cases", json={"template": "2_to_4_unit_appraisal_v1_4", "blank": True,
                                           "name": "defects"}).json()["case_id"]
    lines = _empty_lines(_editor(case), "10.056")
    assert len(lines) == 2                         # one table per unit (D-1 2-4: two buildings)
    line = lines[copy]
    unit_path = line.get("data-tscope")
    r = client.patch(f"/api/cases/{case}/cells/10.056", json={
        "value": "Flooring", "key": "", "data_point": line.get("data-tdp"), "sel": "", "label": "",
        "new": True, "scope": unit_path, "cat": ""})
    assert r.status_code == 200, r.text
    root = api.store().tree(case).getroot()
    unit = bind.find_path(root, unit_path)
    # the gate answered is this unit's own, and no other unit's
    opened = [u for u in root.iter(f"{M}PROPERTY_UNIT")
              if (u.findtext(f".//{M}UnitInteriorDefectsExistIndicator") or "") == "true"]
    assert opened == [unit]
    # tied to this unit, and drawn in this unit's table after the reload
    label = unit.get(f"{X}label")
    assert any(rel.get(f"{X}to") == label and "DEFECT_ContainsDefectOf_PROPERTY_UNIT" in rel.get(f"{X}arcrole", "")
               for rel in root.iter(f"{M}RELATIONSHIP"))
    assert _drawn_in(_editor(case), "10.056") == [unit_path]
