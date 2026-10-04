"""Filling a report by itself.

The bar is not "most of it": a blank report filled from a case must end up
holding *everything* that case holds -- every list, every tick box, every
table row, every comparable-grid cell and every photograph -- and must not
raise a compliance finding the case it came from does not raise.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import compliance, templates  # noqa: E402
from uad.report import form  # noqa: E402

TEMPLATE = "sf1_appraisal_v1_4"
# one of each property kind, so the grids, the units and the rental sheet are
# all exercised rather than the single-family case alone
SCENARIOS = [TEMPLATE, "condo1_appraisal_v1_4", "mh1_appraisal_v1_4",
             "2_to_4_unit_appraisal_v1_4"]
WORD = re.compile(r"[A-Za-z0-9$,./%-]{3,}")


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


def _blank(client, template: str = TEMPLATE) -> str:
    return client.post("/api/cases", json={"template": template, "blank": True,
                                           "name": "autofill"}).json()["case_id"]


def _fill(client, case: str, source: str) -> tuple[dict, dict]:
    body = client.post(f"/api/cases/{case}/autofill", json={"source": source}).json()
    for _ in range(600):
        status = client.get(f"/api/cases/{case}/autofill").json()
        if not status["running"]:
            return body, status
        time.sleep(0.05)
    raise AssertionError("the fill did not finish")


def _words(tree, folder) -> set[str]:
    html = form.galley_html(form.build(tree, folder=folder, edit=False), edit=False)
    return set(WORD.findall(re.sub(r"<[^>]+>", " ", html)))


def _findings(tree) -> list:
    return [f for f in compliance.evaluate(tree) if f.status == compliance.FINDING]


M = "{http://www.mismo.org/residential/2009/schemas}"
PARTY_AT = re.compile(re.escape(f"{M}PARTY") + r"(?:\[(\d+)\])?")


def _by_role(root) -> dict[int, str]:
    """Each party of this document, by the role it holds rather than its place.

    A report lists whoever it happens to have: a blank one carrying only an
    appraiser puts the lender somewhere else than a full one does.  Where a
    party sits is not a fact about the report, so the comparison should not
    turn on it -- but *which* party holds a value certainly is, which is why
    the index is replaced by the party's roles rather than dropped.
    """
    out = {}
    for holder in {id(p.getparent()): p.getparent() for p in root.iter(f"{M}PARTY")}.values():
        for n, party in enumerate(holder.findall(f"{M}PARTY"), start=1):
            roles = "+".join(sorted((r.text or "").strip()
                                    for r in party.iter(f"{M}PartyRoleType")
                                    if (r.text or "").strip()))
            out[id(party)] = roles or f"#{n}"
    return out


def _values(tree) -> dict[str, str]:
    """Every value the document holds, by the address it holds it at."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    roles = _by_role(root)
    out = {}
    for node in root.iter():
        if not (isinstance(node.tag, str) and not len(node) and (node.text or "").strip()):
            continue
        path = root.getroottree().getelementpath(node)
        party = node
        while party is not None and etree.QName(party).localname != "PARTY":
            party = party.getparent()
        if party is not None and id(party) in roles:
            path = PARTY_AT.sub(f"{M}PARTY[{roles[id(party)]}]", path, count=1)
        out[path] = node.text.strip()
    return out


@pytest.mark.parametrize("template", SCENARIOS)
def test_a_blank_report_ends_up_holding_everything_the_case_holds(client, template):
    case = _blank(client, template)
    _body, status = _fill(client, case, template)
    assert status["failed"] == [], status["failed"][:5]

    tpl = templates.get(template)
    want = _values(etree.parse(str(tpl.path)))
    got = _values(api.store().tree(case))
    missing = {k: v for k, v in want.items() if got.get(k) != v}
    assert not missing, list(missing.items())[:10]


@pytest.mark.parametrize("template", SCENARIOS)
def test_the_filled_report_prints_what_the_case_prints(client, template):
    case = _blank(client, template)
    _fill(client, case, template)
    tpl = templates.get(template)
    want = _words(etree.parse(str(tpl.path)), tpl.path.parent)
    got = _words(api.store().tree(case), api.store().folder(case))
    assert want <= got, sorted(want - got)[:20]


@pytest.mark.parametrize("template", SCENARIOS)
def test_filling_raises_no_finding_the_case_did_not_raise(client, template):
    case = _blank(client, template)
    _fill(client, case, template)
    tpl = templates.get(template)
    before = {(f.message_id, f.field_id) for f in _findings(etree.parse(str(tpl.path)))}
    after = {(f.message_id, f.field_id) for f in _findings(api.store().tree(case))}
    assert after <= before, sorted(after - before)[:20]


def test_the_plan_is_in_report_order_and_says_how_each_value_is_entered(client):
    case = _blank(client)
    body, _status = _fill(client, case, TEMPLATE)
    steps = body["steps"]
    assert len(steps) > 800, len(steps)
    assert [s["secn"] for s in steps if s["secn"]] == sorted(
        s["secn"] for s in steps if s["secn"])
    kinds = {s["kind"] for s in steps}
    # a list, a tick box, typing, a table row, a grid cell and a photograph
    assert {"pick", "check", "text", "cell", "grid", "photo"} <= kinds, kinds
    assert all(s["path"] or s["kind"] in ("comp", "photo") for s in steps)


def test_the_comparables_are_created_before_their_grid_is_filled(client):
    case = _blank(client)
    body, _status = _fill(client, case, TEMPLATE)
    steps = body["steps"]
    # a comparable that has to be created is created before anything is
    # written into its column
    for made in [s for s in steps if s["kind"] == "comp"]:
        first = next(s for s in steps if s["kind"] == "grid"
                     and s["column"] == made["column"])
        assert made["n"] < first["n"], (made, first)
    grid = client.get(f"/api/cases/{case}/comparables?kind=sales").json()
    assert len(grid["comparables"]) == 3, grid["comparables"]
    # and every column the plan writes into is a column the grid really has
    columns = {s["column"] for s in steps if s["kind"] == "grid"}
    assert columns <= set(range(0, len(grid["comparables"]) + 1)), columns


def test_the_photographs_come_with_the_case(client):
    case = _blank(client)
    assert client.get(f"/api/cases/{case}/media").json()["media"] == []
    _fill(client, case, TEMPLATE)
    media = client.get(f"/api/cases/{case}/media").json()["media"]
    assert len(media) > 10
    folder = api.store().media_dir(case)
    assert all((folder / m["filename"]).exists() for m in media)


def test_a_field_of_several_data_points_is_written_whole(client):
    """A name is a first and a last: filling it writes both, not the first."""
    case = _blank(client)
    _fill(client, case, TEMPLATE)
    fields = {f["field_id"]: f["value"]
              for s in client.get(f"/api/cases/{case}/fields",
                                  params={"section": 2}).json()["sections"]
              for f in s["fields"]}
    assert fields["2.017"] == "Agatha Appraiser"


def test_an_unknown_source_is_refused(client):
    case = _blank(client)
    assert client.post(f"/api/cases/{case}/autofill",
                       json={"source": "nothing_like_this"}).status_code == 404
    assert client.post(f"/api/cases/{case}/autofill", json={}).status_code == 422
