"""A fill puts each block of the source into the block that *is* it (T-925).

Filling a report writes every value of the source at the address it stood at.
An address names blocks by their place -- ``SERVICE[2]``, ``PROPERTY[5]`` --
and two reports of different shapes do not keep the same blocks in the same
places:

* A blank SF1 holds the subject, three sales comparables and five "not used"
  properties; SF2 holds the subject and five sales comparables.  The fill
  added comparables #4 and #5 after the last PROPERTY, then wrote SF2's
  PROPERTY[5] and PROPERTY[6] into SF1's first two "not used" properties,
  turning them into sales comparables: seven columns, two of them empty
  (T-925).
* D-1 Condo1 keeps the data collector's INSPECTION_SERVICE in SERVICE[1] and
  the VALUATION in SERVICE[2].  Filling any report from it wrote the
  inspection into the valuation's SERVICE and built a second SERVICE with a
  second VALUATION and a second subject; filling a Condo1-shaped report from
  any other wrote the valuation into the inspection's SERVICE (E-340).
* ``comparables.add_property`` added a comparable to the PROPERTIES of the
  first PROPERTY in the document, which on a Condo1-shaped report is the
  inspection's (E-341).

The blocks are now paired by what they are (``autofill.Aligned``): a SERVICE
by the service it holds, a PROPERTY by its @ValuationUseType and number, a
PARTY by its roles.  ``shape.reshape``
still carries all but parties by place (T-1250: its comparables and the new
structure's rental pairings need the same treatment together).
"""
from __future__ import annotations

import collections
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api, autofill  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, templates  # noqa: E402
from uad.report import comparables  # noqa: E402

M = f"{{{bind.MISMO}}}"
SAMPLES = [t.key for t in templates.catalogue()]
ROLES = {kind: role for kind, (_sheet, role, _section) in comparables.SHEETS.items()}


def _counts(root) -> dict[str, int]:
    return {kind: len(comparables.properties(root, role)) for kind, role in ROLES.items()}


def _values(root) -> collections.Counter:
    return collections.Counter(
        (etree.QName(n).localname, n.text.strip()) for n in root.iter()
        if isinstance(n.tag, str) and not len(n) and (n.text or "").strip())


def _fill(target_key: str, source_key: str):
    target = templates.load(target_key, blank=True)
    source = etree.parse(str(templates.get(source_key).path)).getroot()
    result = autofill.apply(target, autofill.plan(target, source), source=source)
    return target.getroot(), source, result


@pytest.mark.parametrize("target_key", ["sf1_appraisal_v1_4", "condo1_appraisal_v1_4"])
@pytest.mark.parametrize("source_key", SAMPLES)
def test_a_fill_lands_every_block_in_its_counterpart(target_key, source_key):
    root, source, result = _fill(target_key, source_key)
    assert not result["failed"], result["failed"][:3]
    # one valuation, about one subject, whatever SERVICE the source keeps it in
    assert len(root.findall(f".//{M}VALUATION")) == 1
    assert sum(p.get("ValuationUseType") == "SubjectProperty"
               for p in root.iter(f"{M}PROPERTY")) == 1
    # the data collector's report stays in a SERVICE of its own
    for service in root.iter(f"{M}SERVICE"):
        kinds = {etree.QName(c).localname for c in service} & {"VALUATION", "INSPECTION_SERVICE"}
        assert len(kinds) <= 1, kinds
    # every grid the source fills has exactly the source's columns
    mine, theirs = _counts(root), _counts(source)
    for kind, n in theirs.items():
        if n:
            assert mine[kind] == n, (kind, mine, theirs)
    # and every value the source holds is in the report
    lost = _values(source) - _values(root)
    assert not lost, list(lost.items())[:5]


@pytest.mark.parametrize("source_key", ["sf2_appraisal_v1_4", "condo1_appraisal_v1_4"])
def test_each_comparable_is_the_sources_comparable_of_that_number(source_key):
    """Comparable #n of the report is comparable #n of the source, value for
    value: nothing of another column, and no column left empty.  What else
    it holds is only what the blank keeps (which row is which)."""
    root, source, _result = _fill("sf1_appraisal_v1_4", source_key)
    kept = templates.structure_elements()
    for role in ROLES.values():
        for mine, theirs in zip(comparables.properties(root, role),
                                comparables.properties(source, role)):
            assert _values(theirs) <= _values(mine), role
            assert all(name in kept for name, _v in _values(mine) - _values(theirs)), role


def test_a_comparable_is_added_beside_the_subject():
    """E-341: on a report whose first SERVICE is the data collector's, a new
    comparable goes into the valuation's PROPERTIES, never the inspection's."""
    tree = templates.load("condo1_appraisal_v1_4")
    root = tree.getroot()
    holder = bind.subject(root).getparent()
    for role in ROLES.values():
        comparables.add_property(tree, role)
        assert comparables.properties(root, role)[-1].getparent() is holder, role
    inspection = root.find(f".//{M}INSPECTION_SERVICE")
    assert not [p for p in inspection.iter(f"{M}PROPERTY") if p.get("ValuationUseType")]


# ------------------------------------------------------------ the editor's route
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


@pytest.mark.parametrize("source_key, sales", [("sf2_appraisal_v1_4", 5),
                                               ("condo1_appraisal_v1_4", 4)])
def test_the_fill_route_adds_only_the_columns_it_fills(client, source_key, sales):
    """The route adds the comparables through the editor's own Add (and saves
    between), then writes: the grid has the source's columns, each filled."""
    case = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                           "name": "fill"}).json()["case_id"]
    assert client.post(f"/api/cases/{case}/autofill", json={"source": source_key}).status_code == 200
    for _ in range(1200):
        status = client.get(f"/api/cases/{case}/autofill").json()
        if not status["running"]:
            break
        time.sleep(0.05)
    assert not status["failed"], status["failed"][:3]
    root = api.store().tree(case).getroot()
    props = comparables.properties(root, ROLES["sales"])
    assert len(props) == sales
    source = etree.parse(str(templates.get(source_key).path)).getroot()
    for mine, theirs in zip(props, comparables.properties(source, ROLES["sales"])):
        assert _values(theirs) <= _values(mine)
    assert len(root.findall(f".//{M}VALUATION")) == 1
