"""A whole address typed into a report address field is stored as the parts
A-1 defines -- street, unit, city, state, ZIP -- and prints back as one.

It used to be refused ("could not be saved to its matching report field"):
the plain value went to the field's one enumerated data point, the unit
designator, which can only hold "Unit".  Owner's case: 186 8th St # 2B,
Brooklyn, NY 11215 at 40.671292, -73.989409.

Run:  python -m pytest -q engine/tests/test_address_entry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import api  # noqa: E402
from app.access import sign_in  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, edit  # noqa: E402

B = edit.field("3.000").binding


@pytest.mark.parametrize("typed,want", [
    ("186 8th St # 2B, Brooklyn, NY 11215",
     {"AddressLineText": "186 8th St", "AddressUnitIdentifier": "2B", "AddressUnitDesignatorType": "Unit",
      "CityName": "Brooklyn", "StateCode": "NY", "PostalCode": "11215"}),
    ("186 8th St, Apt. 2B, Brooklyn, NY 11215-1234",
     {"AddressLineText": "186 8th St", "AddressUnitIdentifier": "2B", "PostalCode": "11215-1234"}),
    ("1 Main St Suite 300, Austin, TX 78701",
     {"AddressLineText": "1 Main St", "AddressUnitIdentifier": "300", "CityName": "Austin"}),
    ("123 Anywhere St, Somecity, TN 12345",
     {"AddressLineText": "123 Anywhere St", "AddressUnitIdentifier": "", "AddressUnitDesignatorType": ""}),
])
def test_split(typed, want):
    got = edit.split_address(typed, B)
    assert got is not None
    for k, v in want.items():
        assert got[k] == v, (k, got)


@pytest.mark.parametrize("typed", ["186 8th St", "Brooklyn NY 11215", ""])
def test_not_a_whole_address(typed):
    assert edit.split_address(typed, B) is None


def test_plain_value_goes_to_the_street_not_the_designator():
    assert edit.choose_data_point(B)["mismo"] == "AddressLineText"


def test_typed_address_saves_validates_and_places_the_pin(tmp_path):
    from app.main import app
    api.STORE = Store(tmp_path / "cases")
    with TestClient(app) as c:
        sign_in(c)
        cid = c.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                         "name": "address entry"}).json()["case_id"]
        r = c.patch(f"/api/cases/{cid}/fields/3.000", json={"value": "186 8th St # 2B, Brooklyn, NY 11215"})
        assert r.status_code == 200, r.text
        assert "Unit 2B" in r.json()["value"]
        root = api.STORE.tree(cid).getroot()
        stored = dict(p for g in bind.read_groups(root, B) for p in g)
        assert stored["AddressUnitDesignatorType"] == "Unit" and stored["AddressUnitIdentifier"] == "2B"
        # a unit removed later is removed, not left behind
        c.patch(f"/api/cases/{cid}/fields/3.000", json={"value": "186 8th St, Brooklyn, NY 11215"})
        stored = dict(p for g in bind.read_groups(api.STORE.tree(cid).getroot(), B) for p in g)
        assert not stored.get("AddressUnitIdentifier") and not stored.get("AddressUnitDesignatorType")
        # coordinates where A-1 keeps them; the map takes them as they are
        c.patch(f"/api/cases/{cid}/extra/0100.0015", json={"value": "40.671292"})
        c.patch(f"/api/cases/{cid}/extra/0100.0016", json={"value": "-73.989409"})
        subject = [p for p in c.get(f"/api/cases/{cid}/maps/places").json()["places"] if p["kind"] == "subject"][0]
        assert (subject["lat"], subject["lon"]) == (40.671292, -73.989409)
        assert c.get(f"/api/cases/{cid}/review").json()["counts"]["schema"] == 0
