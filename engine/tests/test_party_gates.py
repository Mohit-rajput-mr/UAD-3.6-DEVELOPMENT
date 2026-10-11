"""A subsection B-1 shows only when its party exists is "+ Add ..." in the
editor until one is added (T-1074; the owner's brief: "Shows Supervisory
appraiser although not chosen").

B-1 p106: "If there is no Supervisory Appraiser, the subsection does not
display"; p396: Supervisory Appraiser Certifications "Display when
PartyRoleType = AppraiserSupervisor"; p108: Significant Real Property
Appraisal Assistance "displays when there are one or more contacts" in that
role.  The print already followed these; the editor showed the empty fields.

Run:  python -m pytest -q engine/tests/test_party_gates.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import schema, templates
from uad.report import form

SUPERVISOR_FIELDS = {f"2.0{n}" for n in range(32, 47)}          # 2.032-2.046, Supervisory Appraiser


def _fids(tree, section: str) -> set[str]:
    html = form.galley_html([b for b in form.build(tree, folder=None, edit=True) if b.section == section],
                            edit=True)
    return set(re.findall(r"data-fid='([\d.]+)'", html))


def _editor(tree) -> str:
    return form.galley_html(form.build(tree, folder=None, edit=True), edit=True)


def test_the_gates_are_read_from_b1():
    gates = json.loads((Path(form.SPEC) / "party_gates.json").read_text(encoding="utf-8"))["gates"]
    assert [(g["page"], g["subsection"], g["role"]) for g in gates] == [
        (106, "Supervisory Appraiser", "AppraiserSupervisor"),
        (108, "Significant Real Property Appraisal Assistance", "SignificantRealPropertyAppraisalAssistance")]


def test_no_supervisor_no_supervisor_fields():
    tree = templates.load("sf1_appraisal_v1_4", blank=True)
    html = _editor(tree)
    assert "+ Add Supervisory Appraiser" in html
    assert "+ Add Significant Real Property Appraisal Assistance" in html
    assert not (_fids(tree, "Assignment Information") & SUPERVISOR_FIELDS)
    assert "Supervisory Appraiser Certifications" not in html and "29.062" not in _fids(tree, "Certifications")
    printed = form.galley_html(form.build(tree, folder=None, edit=False), edit=False)
    assert "Supervisory" not in printed and "ptyadd" not in printed


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


def test_added_its_fields_follow_and_removed_they_go(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                          "name": "Sup"}).json()["case_id"]
    st = api.store()
    errors = len(schema.validate(st.tree(cid)))
    r = client.post(f"/api/cases/{cid}/parties", json={"role": "AppraiserSupervisor"})
    assert r.status_code == 200 and r.json()["relayout"]
    tree = st.tree(cid)
    assert len(schema.validate(tree)) == errors                     # adds no schema error
    assert SUPERVISOR_FIELDS <= _fids(tree, "Assignment Information")
    assert "29.062" in _fids(tree, "Certifications")                 # its certifications follow
    html = _editor(tree)
    assert "+ Add Supervisory Appraiser" not in html and "class='ptyx'" in html
    assert client.delete(f"/api/cases/{cid}/parties/AppraiserSupervisor").status_code == 200
    tree = st.tree(cid)
    assert not (_fids(tree, "Assignment Information") & SUPERVISOR_FIELDS)
    assert len(schema.validate(tree)) == errors
    assert client.delete(f"/api/cases/{cid}/parties/AppraiserSupervisor").status_code == 422
    assert client.post(f"/api/cases/{cid}/parties", json={"role": "Appraiser"}).status_code == 422
