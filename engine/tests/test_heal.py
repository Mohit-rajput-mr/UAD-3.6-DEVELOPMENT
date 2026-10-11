"""A document saved before E-180 still carries the schema error an earlier
remover left ("AMENITY_CATEGORY_DETAIL is not expected; expected AMENITIES"),
and nothing typed repairs it.  The Review Master offers "Repair the
structure", which puts the containers back and changes no value (T-1201)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import schema  # noqa: E402

M = "{http://www.mismo.org/residential/2009/schemas}"


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


def _values(root):
    return sorted((e.text or "").strip() for e in root.iter()
                  if isinstance(e.tag, str) and not len(e) and (e.text or "").strip())


def test_the_review_offers_a_repair_and_it_clears_the_error_without_touching_a_value(client):
    cid = client.post("/api/cases", json={"template": "2_to_4_unit_appraisal_v1_4", "name": "heal"}).json()["case_id"]
    st = api.store()
    tree = st.tree(cid)
    cats = [c for c in tree.getroot().iter(f"{M}AMENITY_CATEGORY") if c.find(f"{M}AMENITIES") is not None][:2]
    for cat in cats:                     # what the pre-E-180 remover left behind
        cat.remove(cat.find(f"{M}AMENITIES"))
    st.save_tree(cid, tree, allow_invalid=True)
    before = _values(st.tree(cid).getroot())
    assert schema.validate(st.tree(cid))

    items = client.get(f"/api/cases/{cid}/review").json()["items"]
    xsd = [i for i in items if i["source"] == "schema"]
    assert xsd and all(i["fix"] and i["fix"]["route"] == "heal" for i in xsd), xsd

    r = client.post(f"/api/cases/{cid}/heal").json()
    assert r["before"] >= 2 and r["after"] == 0, r
    assert not schema.validate(st.tree(cid))
    assert _values(st.tree(cid).getroot()) == before
    assert not [i for i in client.get(f"/api/cases/{cid}/review").json()["items"] if i["source"] == "schema"]


def test_a_valid_document_is_left_alone(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "name": "ok"}).json()["case_id"]
    r = client.post(f"/api/cases/{cid}/heal").json()
    assert r == {"before": 0, "after": 0, "restored": 0, "removed": 0}
