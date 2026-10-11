"""A saved case an older remover left invalid is repaired in one click (T-1201).

Before T-509 (CATALOG E-180) removing the last amenity of a category took its
AMENITIES too, leaving AMENITY_CATEGORY holding only its detail:
"AMENITY_CATEGORY_DETAIL is not expected. Expected is ( AMENITIES )".  The
removers are fixed; cases saved before still carry it, as an XSD fatal with
no field to go to.  ``uad/heal.py`` takes out such a holder when it states
nothing but its type, or puts back an empty container that is valid, and keeps
a repair only when the errors drop and every answer is still there.  The
Review Master offers it (``repair``) on exactly the items it clears.
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, heal, review, schema, setup, templates  # noqa: E402

M = f"{{{bind.MISMO}}}"
TWO_TO_FOUR = "2_to_4_unit_appraisal_v1_4"
SAMPLES = [t.key for t in templates.catalogue()]


def _broken():
    """A new 2-4 unit report with its comparables' amenities taken out the old
    way: the AMENITY, then its emptied AMENITIES (the owner's screenshot 04)."""
    tree = setup.apply(templates.load(TWO_TO_FOUR, blank=True), TWO_TO_FOUR,
                       "two_to_four_unit", 2, {})[0]
    before = {e.message for e in schema.validate(tree)}
    old = deepcopy(tree)
    for am in [a for p in old.getroot().iter(f"{M}PROPERTY")
               if p.get("ValuationUseType") == "SalesComparable" for a in p.iter(f"{M}AMENITY")]:
        holder = am.getparent()
        holder.remove(am)
        if not len(holder):
            holder.getparent().remove(holder)
    return old, before


def test_the_owners_amenity_fault_is_repaired_and_nothing_else_moves():
    old, before = _broken()
    faults = {e.message for e in schema.validate(old)} - before
    assert faults and all("Expected is ( {" in m and "AMENITIES" in m for m in faults)
    done = heal.heal(old)
    assert {e.message for e in schema.validate(done.tree)} <= before
    assert done.removed and set(done.removed) == {"AMENITY_CATEGORY"}
    assert not heal._answers(old.getroot()) - heal._answers(done.tree.getroot())
    assert {e.message for e in schema.validate(old)} - before == faults   # the original is untouched


@pytest.mark.parametrize("key", SAMPLES)
def test_a_valid_document_is_left_as_it_is(key):
    """Validate the validator: no official sample is touched."""
    done = heal.heal(templates.load(key))
    assert not done.changed and not done.removed and not done.restored


def test_the_review_offers_the_repair_and_the_route_makes_it(tmp_path, monkeypatch):
    from app.main import app
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "RENDERER", None)
    old, before = _broken()
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        cid = c.post("/api/cases", json={"template": TWO_TO_FOUR, "blank": True, "name": "old"}).json()["case_id"]
        store.save_tree(cid, old, allow_invalid=True)       # as a case saved before T-509
        items = [i for i in c.get(f"/api/cases/{cid}/review").json()["items"] if i["code"] == "XSD"]
        offered = [i for i in items if i.get("repair") == review.HEAL]
        assert not [i for i in items if i.get("fix")]       # never a field write the editor would send
        assert offered and all("AMENITIES" in i["message"] for i in offered)
        r = c.post(f"/api/cases/{cid}/heal")
        assert r.status_code == 200 and r.json()["after"] < r.json()["before"]
        left = [i for i in c.get(f"/api/cases/{cid}/review").json()["items"] if i["code"] == "XSD"]
        assert not [i for i in left if "AMENITIES" in i["message"]] and not [i for i in left if i.get("repair")]
        assert c.post(f"/api/cases/{cid}/heal").status_code == 422           # nothing more to do
    store.conn.close()
