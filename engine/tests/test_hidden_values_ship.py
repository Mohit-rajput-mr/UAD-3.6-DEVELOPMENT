"""What the Review Master counts and what the package ships agree (T-1205).

A value left in a section B-1 takes out of the report -- HOA dues on a
single-family report in no project or PUD -- is shown by the Review Master as
"not counted" (T-506), but ``delivery`` still ships it in mismo.xml, where H-1
runs on it as a checker would: UAD1575 is Fatal there.  So ``ready`` could be
True for a package a checker rejects.  Found by epic-brahmagupta's challenge of
T-506; the fix (the shipped copy leaves hidden values aside, as DESKTOP_REBUILD
_PLAN D5 says, and the review stops demoting) is sleepy-hypatia's T-1205.

Strict xfail until then: the day the fix lands this XPASSes, fails, and the
marker must come off with it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import compliance, delivery  # noqa: E402


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


@pytest.mark.xfail(strict=True, reason="T-1205 (sleepy-hypatia): hidden values still ship")
def test_a_finding_the_review_does_not_count_is_not_in_the_shipped_file(client, tmp_path):
    cid = client.post("/api/cases", json={"name": "hidden"}).json()["case_id"]
    # HOA dues on a single-family report in no project or PUD (B-1 hides
    # Project Information)
    assert client.patch(f"/api/cases/{cid}/fields/18.011", json={"value": "125"}).status_code == 200
    review = client.get(f"/api/cases/{cid}/review").json()
    counted = {i["code"] for i in review["items"]
               if i["source"] == "compliance" and i["severity"] in ("Fatal", "Warning")}
    built = delivery.build(api.store().tree(cid), [], tmp_path / "out")
    shipped = {f.message_id for f in compliance.evaluate(built.tree)
               if f.status == compliance.FINDING and f.severity in ("Fatal", "Warning")}
    assert "UAD1575" not in counted
    assert shipped <= counted, sorted(shipped - counted)
