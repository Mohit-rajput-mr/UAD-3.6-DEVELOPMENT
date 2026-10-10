"""Which units the rent schedule lists (T-1058; WinTOTAL's "Include Unit in
Rent Schedule").  A-1 UnitIncludedInRentScheduleIndicator on each subject unit,
not printed; H-1 UAD1159 (Fatal) asks for it once there is a rent schedule.

Run:  python -m pytest -q engine/tests/test_rent_schedule_units.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import bind, compliance, rent_math, rentals, schema, templates
from uad.report import form


def test_the_schedule_follows_the_answers():
    tree = etree.parse(str(templates.get("2_to_4_unit_scenario_2_appraisal_v1_2").path))
    root = tree.getroot()
    subject = bind.subject(root)
    assert [r["included"] for r in rentals.included(root)] == [True] * 4
    rentals.set_included(root, 2, False)
    assert len(rent_math._units(subject)) == 3
    for n in (1, 3, 4):
        rentals.set_included(root, n, False)
    # every unit taken out leaves the schedule empty, not full again
    assert rent_math._units(subject) == []
    assert schema.validate(tree) == []
    with pytest.raises(ValueError):
        rentals.set_included(root, 9, True)


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


def test_setup_includes_every_unit_and_the_switch_takes_one_out(client):
    cid = client.post("/api/cases", json={
        "blank": True, "name": "MF",
        "setup": {"property_type": "two_to_four_unit", "units": 3, "approaches": {"income": True}},
    }).json()["case_id"]
    tree = api.store().tree(cid)
    assert [r["included"] for r in rentals.included(tree.getroot())] == [True, True, True]
    assert not any(f.message_id == "UAD1159" and f.status == compliance.FINDING
                   for f in compliance.evaluate(tree))
    r = client.put(f"/api/cases/{cid}/rentals/included", json={"unit": 2, "on": False})
    assert r.status_code == 200 and [u["included"] for u in r.json()["units"]] == [True, False, True]
    edit_html = form.galley_html(form.build(api.store().tree(cid), folder=None, edit=True), edit=True)
    assert re.findall(r"class='rsu (\w+)'[^>]*data-rsunit='(\d)'", edit_html) == [
        ("on", "1"), ("off", "2"), ("on", "3")]
    printed = form.galley_html(form.build(api.store().tree(cid), folder=None, edit=False), edit=False)
    assert "rsinc" not in printed                       # the switch is the editor's, never printed
    assert client.put(f"/api/cases/{cid}/rentals/included", json={"unit": 9, "on": True}).status_code == 422
