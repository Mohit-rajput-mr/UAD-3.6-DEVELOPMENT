"""Additional certifications (29.053 appraiser, 29.062 supervisor; T-1061, E-159).

The field writer could not save them at all: both fields share one path and
the type that tells them apart is not on the form.  uad/certifications.py keeps
the list, each one's type and the two indicators; the editor numbers them,
keeps the next number open, and x removes one.

Run:  python -m pytest -q engine/tests/test_additional_certifications.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from lxml import etree
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import certifications, compliance, schema, templates
from uad.report import form


def _flag(root, by):
    return root.findtext(f".//{{*}}{certifications.INDICATOR[by]}")


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_add_edit_remove_on_every_sample(key):
    tree = etree.parse(str(templates.get(key).path))
    root = tree.getroot()
    supervisor = certifications.texts(root, "AppraiserSupervisor")
    before = {f.message_id for f in compliance.evaluate(tree) if f.status == compliance.FINDING}
    assert certifications.set_text(root, "Appraiser", 1, "One.") == 1
    assert certifications.set_text(root, "Appraiser", 2, "Two.") == 2
    certifications.set_text(root, "Appraiser", 1, "One, edited.")
    assert certifications.texts(root, "Appraiser") == ["One, edited.", "Two."]
    assert _flag(root, "Appraiser") == "true"
    assert certifications.texts(root, "AppraiserSupervisor") == supervisor   # never touched
    assert schema.validate(tree) == []
    after = {f.message_id for f in compliance.evaluate(tree) if f.status == compliance.FINDING}
    assert after <= before, after - before
    certifications.set_text(root, "Appraiser", 1, "")
    assert certifications.texts(root, "Appraiser") == ["Two."]
    certifications.set_text(root, "Appraiser", 1, "")
    assert certifications.texts(root, "Appraiser") == [] and _flag(root, "Appraiser") == "false"
    assert schema.validate(tree) == []


def test_limits_come_from_a1():
    root = etree.parse(str(templates.get("sf1_appraisal_v1_4").path)).getroot()
    assert certifications.max_length() == 360
    with pytest.raises(ValueError):
        certifications.set_text(root, "Appraiser", 1, "x" * 361)
    with pytest.raises(ValueError):
        certifications.set_text(root, "Appraiser", 3, "skips a number")
    with pytest.raises(ValueError):
        certifications.set_text(root, "Nobody", 1, "x")


def test_print_numbers_them_and_the_editor_keeps_the_next_open():
    tree = etree.parse(str(templates.get("mh1_appraisal_v1_4").path))
    root = tree.getroot()
    certifications.set_text(root, "Appraiser", 1, "First.")
    certifications.set_text(root, "Appraiser", 2, "Second.")
    printed = form.galley_html(form.build(tree, folder=None, edit=False), edit=False)
    i = printed.find("Additional Appraiser Certifications cannot")
    j = printed.find("Supervisory Appraiser Certifications", i)
    text = re.sub(r"<[^>]+>", " ", printed[i:j])
    assert re.search(r"1\.&nbsp;\s+First\.", text) and re.search(r"2\.&nbsp;\s+Second\.", text)
    edit = form.galley_html(form.build(tree, folder=None, edit=True), edit=True)
    lines = re.findall(r"data-route='certifications/Appraiser' data-ordinal='(\d+)'", edit)
    assert lines == ["1", "2", "3"]
    # the supervisor's own list is unchanged and separate (MH1 carries one)
    assert re.findall(r"data-route='certifications/AppraiserSupervisor' data-ordinal='(\d+)'", edit) == ["1", "2"]


def test_the_endpoint(tmp_path, monkeypatch):
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    cid = store.create(template="sf1_appraisal_v1_4", blank=False).case_id
    req = Request({"type": "http", "headers": []})
    out = api.set_certification(cid, "Appraiser", req, {"value": "I certify it.", "ordinal": 1})
    assert out["count"] == 1 and out["relayout"] is True
    out = api.set_certification(cid, "Appraiser", req, {"value": "I certify it, edited.", "ordinal": 1})
    assert out["relayout"] is False                    # same number of lines
    with pytest.raises(HTTPException) as e:
        api.set_certification(cid, "Appraiser", req, {"value": "x", "ordinal": 5})
    assert e.value.status_code == 422
    assert certifications.texts(store.tree(cid).getroot(), "Appraiser") == ["I certify it, edited."]
    store.conn.close()


def test_the_layout_never_measures_a_half_loaded_galley():
    """E-160: the measuring frame took the about:blank load and measured
    120 ms later whatever had been parsed.  srcdoc goes in before the frame is
    attached, only the srcdoc's own load counts, and a short measurement is
    measured again."""
    js = api.CLIENT_LAYOUT_HTML
    body = js[js.index("function frame(html)"):js.index("function run(")]
    assert body.index("f.srcdoc=html") < body.index("appendChild(f)")
    assert "about:srcdoc" in body
    assert "measured.length!==BLOCKS" in js
