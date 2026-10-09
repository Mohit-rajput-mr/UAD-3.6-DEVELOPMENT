"""Copy a comparable (WinTOTAL's "Copy Comp"; T-1055).

A copy is a new last comparable holding every value of the original, with
every identifier inside it minted afresh and every relationship that points
into it duplicated onto the copy (its data sources; for a rental or a 2-4
unit sale, the subject unit it is compared with).  It must leave the document
schema-valid and add no H-1 finding on any of the twelve official samples.

Run:  python -m pytest -q engine/tests/test_comparable_copy.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from lxml import etree
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import compliance, schema, templates
from uad.report import comparables

XLINK = "{http://www.w3.org/1999/xlink}"
ROLES = ("SalesComparable", "RentalComparable", "LandComparable", "GrossRentMultiplierComparable")


def _findings(tree) -> collections.Counter:
    return collections.Counter(f.message_id for f in compliance.evaluate(tree)
                               if f.status == compliance.FINDING)


def _rels(root, label):
    return sorted((r.get(f"{XLINK}arcrole"), r.get(f"{XLINK}from") == label)
                  for r in root.iter("{*}RELATIONSHIP")
                  if label in (r.get(f"{XLINK}from"), r.get(f"{XLINK}to")))


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_copying_each_kind_keeps_every_sample_valid(key):
    tree = etree.parse(str(templates.get(key).path))
    root = tree.getroot()
    before = _findings(tree)
    copied = 0
    for role in ROLES:
        found = comparables.properties(root, role)
        if not found:
            continue
        src_label = found[0].get(f"{XLINK}label")
        n = comparables.copy_property(tree, role, 1)
        now = comparables.properties(root, role)
        assert n == len(found) + 1 == len(now)
        dup = now[-1]
        # the same values, under new identifiers
        assert etree.tostring(dup).count(b"<") == etree.tostring(found[0]).count(b"<")
        new_label = dup.get(f"{XLINK}label")
        assert new_label and new_label != src_label
        assert _rels(root, new_label) == _rels(root, src_label)
        copied += 1
    assert copied
    labels = [e.get(f"{XLINK}label") for e in root.iter()
              if isinstance(e.tag, str) and e.get(f"{XLINK}label")]
    assert [l for l, k in collections.Counter(labels).items() if k > 1] == []
    assert schema.validate(tree) == []
    assert not (_findings(tree) - before), dict(_findings(tree) - before)


@pytest.fixture
def case(tmp_path, monkeypatch):
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    cid = store.create(template="sf1_appraisal_v1_4", blank=False).case_id
    yield store, cid
    store.conn.close()


def _request():
    return Request({"type": "http", "headers": []})


def test_the_endpoint_copies_and_refuses_what_it_cannot(case):
    store, cid = case
    out = api.copy_comparable(cid, 2, _request(), kind="sales")
    assert out == {"added": 4, "from": 2, "kind": "sales"}
    props = comparables.properties(store.tree(cid).getroot(), "SalesComparable")
    addr = [p.findtext(".//{*}ADDRESS/{*}AddressLineText") for p in props]
    assert addr[3] == addr[1]
    with pytest.raises(HTTPException) as e:
        api.copy_comparable(cid, 9, _request(), kind="sales")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        api.copy_comparable(cid, 1, _request(), kind="bogus")
    assert e.value.status_code == 400


def test_copy_stops_at_the_grid_limit(case):
    store, cid = case
    for _ in range(40):
        try:
            api.copy_comparable(cid, 1, _request(), kind="sales")
        except HTTPException as e:
            assert e.status_code == 409
            break
    else:
        pytest.fail("no limit was reached")
    assert comparables.limit_problem("sales", len(api._labels(store.tree(cid), "sales")) + 1)
