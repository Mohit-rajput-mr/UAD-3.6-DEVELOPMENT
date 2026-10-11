"""What the editor leaves out by the report's own answers (T-1066; the owner's
brief §5 and DESKTOP_REBUILD_PLAN D5).

A field B-1's display rule rules out by another answer is left out, exactly as
the print does; an empty field A-1 says does not apply, by a gate the report
answers once, is left out too -- Zoning "Legal" leaves out Reasons Illegal,
no renewable energy component its type and ownership, not listed in the
previous year the listing's details, not in a project the Project
Information.  The gate question stays, so a changed answer brings them back.

Run:  python -m pytest -q engine/tests/test_edit_visibility.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, templates
from uad.report import form

KEYS = [t.key if hasattr(t, "key") else t for t in templates.catalogue()]


def _shown(tree) -> set[str]:
    html = form.galley_html(form.build(tree, folder=None, edit=True), edit=True)
    return set(re.findall(r"data-(?:fid|tf)='([\d.]+)'", html))


def _tree(key):
    return etree.parse(str(templates.get(key).path))


@pytest.mark.parametrize("key", KEYS)
def test_the_editor_never_hides_what_the_print_shows(key):
    """A field holding a value is left out only where the print leaves it
    out too (its B-1 display rule) -- so no answer a D-1 sample prints is
    ever out of the appraiser's reach."""
    root = _tree(key).getroot()
    ctx = form.Ctx(root, edit=True)
    for fid, entry in form._fields().items():
        if form.edit_hides(ctx, fid, has_value=True):
            assert form.field_rule_hides(form.Ctx(root), fid), (key, fid)


def test_the_owners_cases():
    sf1, condo1 = _shown(_tree("sf1_appraisal_v1_4")), _shown(_tree("condo1_appraisal_v1_4"))
    # Zoning Legal: no reasons illegal, no impact, no rebuild question
    assert not {"4.011", "4.012", "4.013"} & sf1
    # no renewable energy component, no green certification: their rows go
    assert not {"6.001", "6.002", "6.003", "6.005"} & sf1
    # an efficiency rating exists in SF1, not in Condo1
    assert "6.011" in sf1 and "6.011" not in condo1
    # listed within the previous year in SF1, not in Condo1
    assert {"19.002", "19.007", "19.009"} <= sf1 and not {"19.002", "19.007", "19.009"} & condo1
    # Project Information: the condominium's, not the single-family house's
    assert "18.004" in condo1 and "18.004" not in sf1


def test_a_changed_answer_brings_the_fields_back():
    tree = _tree("sf1_appraisal_v1_4")
    zoning = bind.subject(tree.getroot()).find(".//{*}SiteZoningComplianceType")
    assert zoning is not None and zoning.text == "Legal"
    zoning.text = "Illegal"
    shown = _shown(tree)
    assert {"4.011", "4.012"} <= shown


def test_a_block_gate_or_an_unasked_gate_decides_nothing():
    """SF1's one site influence is not a body of water, but another influence
    can be added: Frontage stays.  No field asks PrivateAccessIndicator (a
    water frontage row implies it): the Water Frontage fields stay.  The
    financing of a renewable energy component whose ownership is never asked
    -- there is no component -- goes."""
    sf1 = _shown(_tree("sf1_appraisal_v1_4"))
    assert {"4.034", "4.031", "4.032", "4.036", "4.037"} <= sf1
    assert form._point_repeats("SiteInfluenceType") and not form._point_repeats("SiteZoningComplianceType")
    assert "6.003" not in sf1


def test_a_field_that_is_its_own_gate_stays():
    """10.050 Accessibility: "Display when AccessibilityFeatureType <> None" --
    hidden, its answer could never be changed back."""
    read, own = form._gate_names("10.050")
    assert read & own
    root = _tree("sf1_appraisal_v1_4").getroot()
    assert not form.edit_hides(form.Ctx(root, edit=True), "10.050")


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import api
    from app.cases import Store
    monkeypatch.setenv("URAR_CLIENT_LAYOUT", "1")
    from app.main import app
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "RENDERER", None)
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        yield c
    store.conn.close()


def test_the_page_is_laid_out_again_when_an_answer_changes_what_shows(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False,
                                          "name": "Zoning"}).json()["case_id"]
    zoning = "4.008"                      # Site: Zoning Compliance (1.027 is the Summary's redisplay)
    assert any(dp.get("mismo") == "SiteZoningComplianceType"
               for dp in form._fields()[zoning]["data_points"])
    r = client.patch(f"/api/cases/{cid}/fields/{zoning}", json={"value": "Illegal"})
    assert r.status_code == 200 and r.json()["relayout"] is True        # the reasons come in
    r = client.patch(f"/api/cases/{cid}/fields/{zoning}", json={"value": "Illegal"})
    assert r.json()["relayout"] is False                                 # nothing changed
    r = client.patch(f"/api/cases/{cid}/fields/3.000", json={"value": "12 Main St"})
    assert r.json()["relayout"] is False                                 # not a gate
