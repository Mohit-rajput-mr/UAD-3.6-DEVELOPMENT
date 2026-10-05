"""Grids stay within their limits (owner's section test B10).

Sales 3-24, rental 1-24, GRM 3-24 (WinTOTAL's measured limits, kept at the
owner's request; the GSE appendices state no count).  A limit must not fault a
published sample, so every D-1 sample is checked against them first.

Run:  python -m pytest -q engine/tests/test_comparable_limits.py
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
from uad import templates  # noqa: E402
from uad.report import comparables  # noqa: E402


@pytest.mark.parametrize("template", [t.key for t in templates.catalogue()])
def test_every_sample_is_inside_the_limits(template):
    root = templates.load(template).getroot()
    for kind in comparables.LIMITS:
        n = len(comparables.labels(root, comparables.SHEETS[kind][1]))
        assert not comparables.limit_problem(kind, n), (template, kind, n)


@pytest.fixture
def client(tmp_path):
    from app.main import app
    api.STORE = Store(tmp_path / "cases")
    api.RENDERER = None
    with TestClient(app) as c:
        sign_in(c)
        yield c


def test_sales_grid_keeps_three(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                          "name": "limits"}).json()["case_id"]
    n = client.get(f"/api/cases/{cid}/comparables").json()
    count = len(comparables.labels(api.store().tree(cid).getroot(), "SalesComparable"))
    assert count == 3, n
    r = client.delete(f"/api/cases/{cid}/comparables/3")
    assert r.status_code == 409 and "at least 3" in r.json()["detail"]
    assert client.post(f"/api/cases/{cid}/comparables", json={"kind": "sales"}).status_code == 200
    assert client.delete(f"/api/cases/{cid}/comparables/4").status_code == 200


def test_grid_stops_at_twenty_four(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                          "name": "max"}).json()["case_id"]
    for _ in range(21):
        assert client.post(f"/api/cases/{cid}/comparables", json={"kind": "sales"}).status_code == 200
    r = client.post(f"/api/cases/{cid}/comparables", json={"kind": "sales"})
    assert r.status_code == 409 and "24" in r.json()["detail"]


def test_package_check_agrees_with_the_export(client):
    """B12: the check says ready exactly when package.zip would answer."""
    cid = client.post("/api/cases", json={"template": "2_to_4_unit_appraisal_v1_4", "blank": True,
                                          "name": "pkg"}).json()["case_id"]
    check = client.get(f"/api/cases/{cid}/package/check").json()
    export = client.get(f"/api/cases/{cid}/package.zip")
    assert check["ready"] is False and check["blockers"]
    assert export.status_code == 409
    assert export.json()["reasons"] == check["blockers"]


def test_an_adjustment_goes_under_its_own_type(client):
    """B13: 22.07.27 is the bedroom-count adjustment (B-1 grid); written without
    adjust_type it is filed as LivingUnitBedroomCount, not the first type."""
    from uad import bind
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                          "name": "adj"}).json()["case_id"]
    r = client.patch(f"/api/cases/{cid}/comparables/1/fields/22.07.27", json={"value": "-10000"})
    assert r.status_code == 200, r.text
    M = f"{{{bind.MISMO}}}"
    comp = [p for p in api.store().tree(cid).getroot().iter(f"{M}PROPERTY")
            if p.get("ValuationUseType") == "SalesComparable"][0]
    kinds = {a.findtext(f"{M}ComparableAdjustmentType"): a.findtext(f"{M}ComparableAdjustmentAmount")
             for a in comp.iter(f"{M}COMPARABLE_ADJUSTMENT")}
    assert kinds.get("LivingUnitBedroomCount") == "-10000", kinds
