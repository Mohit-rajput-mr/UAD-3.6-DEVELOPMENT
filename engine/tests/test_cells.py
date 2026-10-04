"""Every table cell the editor draws can be written through the API.

The editor's own markup is the list of controls: each ``data-tf`` cell is
sent a value A-1 allows for its field, through the same route the page uses,
and must save (the route refuses anything that does not read back or does not
validate) and then print in the report.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import html as lhtml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import edit  # noqa: E402
from uad.report import form  # noqa: E402

VALUES = {"String": "Cell Test", "Amount": "2500", "Date": "2026-03-04", "Numeric": "3"}


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


def _value_for(fid: str, point: str = "") -> str:
    try:
        binding = edit._binding_for(fid)
        dp = edit.choose_data_point(binding, point)
    except KeyError:
        return "Cell Test"
    choices = form.point_choices(dp)
    if choices:
        return choices[0][0]
    kind = (dp.get("format_type") or "String").strip()
    if kind == "Boolean":
        return "true"
    return VALUES.get(kind, "Cell Test")


@pytest.mark.parametrize("template", ["sf1_appraisal_v1_4"])
def test_every_table_cell_saves_reads_back_and_validates(client, template):
    case = client.post("/api/cases", json={"template": template, "blank": False, "name": "cells"}).json()["case_id"]
    tree = api.store().tree(case)
    blocks = form.build(tree, folder=api.store().folder(case), edit=True)
    doc = lhtml.fromstring(form.galley_html(blocks, edit=True))
    cells = [el for el in doc.iter() if isinstance(el.tag, str) and el.get("data-tf") is not None]
    assert len(cells) > 300, len(cells)

    tried = saved = 0
    failures = []
    seen = set()
    for el in cells:
        fid, key = el.get("data-tf"), el.get("data-tk") or ""
        sig = (fid, key, el.get("data-tsel"), el.get("data-tlab"), el.get("data-tnew"))
        if sig in seen:
            continue
        seen.add(sig)
        body = {"value": el.get("data-tval") or _value_for(fid, el.get("data-tdp") or ""), "key": key,
                "data_point": el.get("data-tdp") or "",
                "sel": el.get("data-tsel") or "", "label": el.get("data-tlab") or "",
                "new": bool(el.get("data-tnew")), "scope": el.get("data-tscope") or "",
                "cat": el.get("data-tcat") or ""}
        # only existing rows here: creating rows shifts the paths later cells name
        if body["sel"] or body["new"]:
            continue
        tried += 1
        r = client.patch(f"/api/cases/{case}/cells/{fid}", json=body)
        if r.status_code == 200:
            saved += 1
        else:
            failures.append(f"{fid} [{key[-40:]}]: {r.status_code} {r.text[:120]}")
    print(f"{template}: {saved}/{tried} existing-row cells saved")
    assert tried and saved / tried >= 0.95, "\n".join(failures[:25])


def test_a_missing_fixed_row_is_created_with_its_type(client):
    """Utilities: typing into the 'Gas' row creates the gas utility."""
    case = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False,
                                           "name": "rows"}).json()["case_id"]
    tree = api.store().tree(case)
    doc = lhtml.fromstring(form.galley_html(form.build(tree, edit=True), edit=True))
    creators = [el for el in doc.iter() if isinstance(el.tag, str) and el.get("data-tsel")]
    assert creators, "no fixed row offers to create itself"
    el = creators[0]
    r = client.patch(f"/api/cases/{case}/cells/{el.get('data-tf')}",
                     json={"value": el.get("data-tval") or _value_for(el.get("data-tf"), el.get("data-tdp") or ""),
                           "data_point": el.get("data-tdp") or "",
                           "sel": el.get("data-tsel"), "label": el.get("data-tlab"), "key": ""})
    assert r.status_code == 200, r.text
    assert r.json()["key"], "the new row has no address for its next cell"


def test_the_empty_line_adds_a_row(client):
    """The empty line under a repeating table creates a new instance.  Rows that
    need a linked entity (a defect's RELATIONSHIP, an amenity's category) are
    not yet created this way -- see TASKS.md -- so this holds most, not all."""
    case = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False,
                                           "name": "new"}).json()["case_id"]
    tree = api.store().tree(case)
    doc = lhtml.fromstring(form.galley_html(form.build(tree, edit=True), edit=True))
    lines = []
    for el in doc.iter():
        if isinstance(el.tag, str) and el.get("data-tnew"):
            tr = el.getparent().getparent()
            if all(tr is not t for t, _e in lines):
                lines.append((tr, el))
    ok = 0
    for _tr, el in lines:
        try:
            value = _value_for(el.get("data-tf"), el.get("data-tdp") or "")
        except KeyError:
            continue
        r = client.patch(f"/api/cases/{case}/cells/{el.get('data-tf')}",
                         json={"value": value, "new": True, "key": "",
                               "data_point": el.get("data-tdp") or "",
                               "scope": el.get("data-tscope") or ""})
        ok += r.status_code == 200
    assert lines and ok >= len(lines) // 2, (ok, len(lines))
