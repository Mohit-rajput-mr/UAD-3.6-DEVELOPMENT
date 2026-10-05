"""One "New report" that takes the shape of the property, and opens at once.

* POST /api/cases needs no template: every new report starts from the same
  document (api.NEW_REPORT), and the appraiser's answers shape it.
* An answer that changes the kind of property (units, ADUs, condominium,
  co-op, manufactured) rebuilds the report on the closest official D-1
  structure with every value carried (uad/shape.py), checked here on the API.
* A report whose content was laid out before -- every new report has the same
  content -- is served from the shared layouts (app/layouts.py), and the
  hidden warm-up report is never listed.

Run:  python -m pytest -q engine/tests/test_one_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.access import sign_in  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, shape, templates  # noqa: E402


@pytest.fixture
def client(tmp_path):
    from app.main import app
    api.STORE = Store(tmp_path / "cases")
    api.RENDERER = None
    api.LAYOUTS = None
    with TestClient(app) as c:
        sign_in(c)
        yield c


def new(client):
    r = client.post("/api/cases", json={"name": "123 Main St"})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


@pytest.mark.parametrize("fid,value,kind", [
    ("3.011", "Condominium", "condominium"),
    ("3.012", "Cooperative", "cooperative"),
    ("3.005", "2", "two_to_four_unit"),
    ("3.005", "4", "two_to_four_unit"),
    ("3.006", "1", "single_family"),
])
def test_an_answer_shapes_the_report(client, fid, value, kind):
    cid = new(client)
    assert client.patch(f"/api/cases/{cid}/fields/3.000",
                        json={"value": "186 8th St # 2B, Brooklyn, NY 11215"}).status_code == 200
    r = client.patch(f"/api/cases/{cid}/fields/{fid}", json={"value": value})
    assert r.status_code == 200, r.text
    info = r.json()["reshaped"]
    assert info and info["property_type"] == kind, info
    root = api.store().tree(cid).getroot()
    assert shape.property_type(root) == kind
    # what was entered before is still there
    assert bind.subject(root).findtext(f".//{{{bind.MISMO}}}AddressLineText") == "186 8th St"
    case = client.get(f"/api/cases/{cid}").json()
    assert case["property_type"] == kind and case["template"] == info["template"]
    # an answer that does not change the shape does not rebuild anything
    again = client.patch(f"/api/cases/{cid}/fields/3.000", json={"value": "1 Main St, Austin, TX 78701"})
    assert again.json()["reshaped"] is None


def test_every_d1_shape_is_reachable():
    """Each property type the samples cover is the best shape for its own answers."""
    for t in templates.catalogue():
        best = shape.best_template(t.determinants)
        assert templates.get(best).property_type == t.property_type, (t.key, best)


def test_a_new_report_opens_from_the_shared_layout(client):
    from app.layouts import TOKEN
    warm = client.post("/api/warm", json={}).json()
    assert not warm["ready"]["form"]
    # the warm-up report is laid out once (here the server's own layout pass
    # stands in for the browser's) and kept by content key
    key = api.renderer().key(warm["case_id"], "form")
    api.layouts().put(key, "form", f"<html><head></head><body><img src='/api/cases/{TOKEN}/asset/x.png'>"
                                    "<div class='page'>p1</div></body></html>")
    assert client.post("/api/warm", json={}).json()["ready"]["form"]
    cid = new(client)
    assert api.renderer().key(cid, "form") == key            # same content, same layout
    page = client.get(f"/api/cases/{cid}/form", headers={"accept": "text/html"})
    assert page.status_code == 200 and "class='page'" in page.text
    assert f"/api/cases/{cid}/asset/x.png" in page.text and TOKEN not in page.text
    assert client.get(f"/api/cases/{cid}/render/form").json()["ready"]
    listed = [c["case_id"] for c in client.get("/api/cases").json()["cases"]]
    assert cid in listed and warm["case_id"] not in listed


def test_an_unnamed_report_is_named_by_its_address(client):
    cid = client.post("/api/cases", json={}).json()["case_id"]
    assert client.get(f"/api/cases/{cid}").json()["name"] == "New report"
    client.patch(f"/api/cases/{cid}/fields/3.000", json={"value": "186 8th St # 2B, Brooklyn, NY 11215"})
    assert client.get(f"/api/cases/{cid}").json()["name"] == "186 8th St # 2B, Brooklyn, NY 11215"
