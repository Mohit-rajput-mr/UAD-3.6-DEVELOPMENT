"""The footer's reference IDs, typed where they print (T-919).

A-1 places HF.005 Appraiser Reference ID (R), HF.006 Agency Case File ID (FHA
/ VA), HF.007 Client Reference ID and HF.008 AMC Reference ID in every page's
footer; the field index has no binding for them, so nothing could set them.

Run:  python -m pytest -q engine/tests/test_footer_references.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import references, schema, templates
from uad.report import flow, urar

KEYS = [t.key if hasattr(t, "key") else t for t in templates.catalogue()]


def test_read_from_a1_and_agreeing_with_the_footer():
    assert [s["field"] for s in references.specs()] == ["HF.005", "HF.006", "HF.007", "HF.008"]
    assert {s["field"]: s["type"] for s in references.specs() if s["type"]} == urar.REFERENCE_TYPES
    for key in KEYS:
        root = etree.parse(str(templates.get(key).path)).getroot()
        for f in ("HF.005", "HF.006", "HF.007", "HF.008"):
            assert references.read(root, f) == urar._reference(root, f), (key, f)
        # what A-1 asks for here: the appraiser's always, the client's (every
        # sample has a client), never the agency's (no FHA / VA sample)
        offered = [e["field"] for e in references.editable(root)]
        assert offered[:2] == ["HF.005", "HF.007"] and "HF.006" not in offered, key


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("URAR_CLIENT_LAYOUT", "1")
    from app.main import app
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "RENDERER", None)
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        yield c
    store.conn.close()


def test_typed_in_the_footer_written_where_a1_puts_it(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                          "name": "Refs"}).json()["case_id"]
    st = api.store()
    for field, value in (("HF.005", "AF-2026-118"), ("HF.007", "CL-77"), ("HF.008", "AMC-9")):
        r = client.patch(f"/api/cases/{cid}/references/{field}", json={"value": value})
        assert r.status_code == 200 and r.json() == {**r.json(), "value": value, "relayout": True}
    tree = st.tree(cid)
    assert schema.validate(tree) == []
    meta = flow.Meta.from_case(tree)
    assert meta.references == [("Appraiser Reference ID", "AF-2026-118"),
                               ("Client Reference ID", "CL-77"), ("AMC Reference ID", "AMC-9")]
    # the editor's footer: each typed where it prints; the report's: plain
    edit = flow._furniture(meta, 2, 20, edit=True)
    assert "data-route='references/HF.005'" in edit and ">CL-77</span>" in edit
    assert "contenteditable" not in flow._furniture(meta, 2, 20)
    # cleared, it goes -- the container too
    client.patch(f"/api/cases/{cid}/references/HF.008", json={"value": ""})
    client.patch(f"/api/cases/{cid}/references/HF.007", json={"value": ""})
    tree = st.tree(cid)
    assert references.read(tree.getroot(), "HF.007") == "" and schema.validate(tree) == []
    assert client.patch(f"/api/cases/{cid}/references/HF.009", json={"value": "x"}).status_code == 422
