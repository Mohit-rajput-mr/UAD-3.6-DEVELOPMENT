"""Leaving an optional section out of the report, and bringing it back (T-1057;
WinTOTAL's Show / Hide), and the editor keeping its question (E-162).

B-1 prints Disaster Mitigation, Energy Efficient and Green Features and Sales
Contract only when their own question says so.  Leaving one out answers that
question and moves the rest of the section out of the MISMO document into the
case folder; the official samples that do not print the section show what the
file must then hold -- the question and nothing else (D-1 Condo1, MH1, SF5).

Run:  python -m pytest -q engine/tests/test_optional_sections.py
"""
from __future__ import annotations

import copy
import io
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import bind, compliance, delivery, optional_sections as opt, schema, templates
from uad.report import form

KEYS = [t.key if hasattr(t, "key") else t for t in templates.catalogue()]


def _plain(tree) -> bytes:
    t = copy.deepcopy(tree)
    for e in t.getroot().iter():
        if isinstance(e.tag, str):
            if e.text is not None and not e.text.strip():
                e.text = None
            if e.tail is not None and not e.tail.strip():
                e.tail = None
    return etree.tostring(t, method="c14n")


def _contract_date(tree) -> bool:
    """The subject's (the comparables have contract dates of their own)."""
    return bind.subject(tree.getroot()).find(f".//{opt.M}SalesContractDate") is not None


def _findings(tree) -> set[str]:
    return {f.message_id for f in compliance.evaluate(tree) if f.status == compliance.FINDING}


def _shape(root, section) -> list[str]:
    """The section's own answers left in the subject, where A-1 puts them,
    as name=value (a data point name alone is shared: ValueMarketabilityImpactType
    is asked in a dozen sections)."""
    out = set()
    for _fid, dp in opt._points(section):
        anchor, tail = opt._anchor(root, dp)
        if anchor is None or bind.is_commentary(dp) or anchor is not bind.subject(root):
            continue
        steps = [t for t in tail.split("/") if t] + [dp["mismo"]]
        for e in anchor.findall("./" + "/".join(f"{opt.M}{t}" for t in steps)):
            out.add(f"{dp['mismo']}={(e.text or '').strip()}")
    return sorted(out)


def test_the_three_sections_come_from_b1():
    assert opt.sections() == ["Disaster Mitigation", "Energy Efficient and Green Features", "Sales Contract"]
    assert form.switch_fields("Sales Contract") == ("20.000",)
    assert form.switch_fields("Disaster Mitigation") == ("5.000",)
    assert form.switch_fields("Energy Efficient and Green Features") == ("6.000", "6.004", "6.010")
    assert form.switch_fields("Revision History") == ()       # a revision cannot be held back
    # the question is the data point B-1 names, not the "Other" text beside it
    assert form.switch_points("Disaster Mitigation") == ("DisasterMitigationFeatureType",)


def test_an_other_description_comes_back_too():
    tree = etree.parse(str(templates.get("condo2_appraisal_v1_4").path))
    feature = bind.subject(tree.getroot()).find(f"{opt.M}DISASTER_MITIGATION_FEATURES/{opt.M}DISASTER_MITIGATION_FEATURE")
    feature.find(f"{opt.M}DisasterMitigationFeatureType").text = "Other"
    etree.SubElement(feature, f"{opt.M}DisasterMitigationFeatureTypeOtherDescription").text = "Safe room"
    assert schema.validate(tree) == []
    before, kept = _plain(tree), {}
    opt.set_shown(tree, "Disaster Mitigation", False, kept)
    assert "Safe room" not in etree.tostring(tree).decode() and schema.validate(tree) == []
    opt.set_shown(tree, "Disaster Mitigation", True, kept)
    assert _plain(tree) == before


@pytest.mark.parametrize("key", KEYS)
def test_leaving_out_and_bringing_back_on_every_sample(key):
    for section in opt.sections():
        tree = etree.parse(str(templates.get(key).path))
        if not form.section_prints(tree.getroot(), section):
            kept = {}
            opt.set_shown(tree, section, True, kept)
            assert schema.validate(tree) == [], (key, section)
            assert form.section_prints(tree.getroot(), section), (key, section)
            continue
        before, found = _plain(tree), _findings(tree)
        kept = {}
        opt.set_shown(tree, section, False, kept)
        root = tree.getroot()
        assert schema.validate(tree) == [], (key, section)
        assert not form.section_prints(root, section), (key, section)
        assert opt._found(root, section, asks=False) == [], (key, section)      # nothing else left
        # the shape of a D-1 sample that does not print the section
        hide = opt._hide_value(section)
        assert _shape(root, section) == sorted(
            f"{name}={hide}" for name in form.switch_points(section)), (key, section)
        assert _findings(tree) <= found, (key, section)       # leaving it out faults nothing
        assert opt._answered(kept[section]) > 0
        opt.set_shown(tree, section, True, kept)
        assert _plain(tree) == before, (key, section)         # back exactly as it was
        assert kept == {}


def test_the_editor_keeps_the_question_of_a_section_left_out():
    """E-162: Condo1 answers No to a sales contract and None to mitigation;
    the editor dropped both sections, question and all, so neither could be
    switched back on from the form."""
    tree = etree.parse(str(templates.get("condo1_appraisal_v1_4").path))
    edit = form.galley_html(form.build(tree, folder=None, edit=True), edit=True)
    for fid in ("20.000", "5.000", "6.000", "6.004", "6.010"):
        assert f"data-fid='{fid}'" in edit, fid
    for fid in ("20.005", "5.001", "6.014"):
        assert f"data-fid='{fid}'" not in edit, fid               # the rest waits
    assert edit.count("class='secoff'") == 3
    printed = form.galley_html(form.build(tree, folder=None, edit=False), edit=False)
    assert "data-fid='20.000'" not in printed and "secoff" not in printed


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


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(buf, "PNG")
    return buf.getvalue()


def test_the_switch_and_the_question_both_move_the_answers(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False, "name": "Opt"}).json()["case_id"]
    st = api.store()
    original = _plain(st.tree(cid))
    state = {s["section"]: s for s in client.get(f"/api/cases/{cid}/sections/optional").json()["sections"]}
    assert state["Sales Contract"]["printed"] and not state["Disaster Mitigation"]["printed"]

    # the side panel's switch
    r = client.put(f"/api/cases/{cid}/sections/optional/20", json={"on": False})
    assert r.status_code == 200 and r.json()["relayout"]
    sc = next(s for s in r.json()["sections"] if s["section"] == "Sales Contract")
    assert not sc["printed"] and sc["kept"] == 12
    assert (st.folder(cid) / opt.FILE).exists()
    assert not _contract_date(st.tree(cid))
    client.put(f"/api/cases/{cid}/sections/optional/20", json={"on": True})
    assert _plain(st.tree(cid)) == original and not (st.folder(cid) / opt.FILE).exists()

    # the question itself, answered in the form
    r = client.patch(f"/api/cases/{cid}/fields/20.000", json={"value": "false"})
    assert r.status_code == 200 and r.json()["relayout"] is True
    assert not _contract_date(st.tree(cid))
    r = client.patch(f"/api/cases/{cid}/fields/20.000", json={"value": "true"})
    assert r.json()["relayout"] is True
    assert _plain(st.tree(cid)) == original

    # a section B-1 always prints is not one the report can leave out
    assert client.put(f"/api/cases/{cid}/sections/optional/27", json={"on": False}).status_code == 422
    assert client.put(f"/api/cases/{cid}/sections/optional/13", json={"on": False}).status_code == 422


def test_what_is_kept_travels_with_the_case_and_never_ships(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False, "name": "Opt"}).json()["case_id"]
    st = api.store()
    r = client.post(f"/api/cases/{cid}/media?section=20&caption=Contract",
                    files={"file": ("contract.png", _png(), "image/png")})
    assert r.status_code in (200, 201), r.text
    name = next(m.filename for m in st.media(cid) if int(m.section or 0) == 20)
    client.put(f"/api/cases/{cid}/sections/optional/20", json={"on": False})

    with zipfile.ZipFile(io.BytesIO(st.bundle(cid))) as z:          # the case bundle keeps it
        assert any(n.endswith(opt.FILE) for n in z.namelist())

    out = delivery.build(st.tree(cid), st.media(cid), st.media_dir(cid))
    assert schema.validate(out.tree) == []
    assert not _contract_date(out.tree)
    assert name not in out.images                                   # no section, no exhibit
    assert any(f.code == "IMAGE-SECTION-OFF" for f in out.faults)

    client.put(f"/api/cases/{cid}/sections/optional/20", json={"on": True})
    out = delivery.build(st.tree(cid), st.media(cid), st.media_dir(cid))
    assert name in out.images
