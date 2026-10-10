"""The legal description as an image (T-1060; B-1 pp121-122, A-1 3.031.1-2).

"The legal description is required either in text format or an image."  The
image is delivered with ImageCategoryType = "LegalDescription" and displays
within the subsection, below the gray bar.

Run:  python -m pytest -q engine/tests/test_legal_description_image.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import compliance, delivery, schema
from uad.report import form


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(buf, "PNG")
    return buf.getvalue()


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


def _uad1043(cid):
    return any(f.message_id == "UAD1043" and f.status == compliance.FINDING
               for f in compliance.evaluate(api.store().tree(cid)))


def _legal_images(tree):
    return [i for i in tree.getroot().iter("{*}IMAGE")
            if i.findtext("{*}ImageCategoryType") == "LegalDescription"]


def test_an_image_answers_for_the_text_and_prints_under_the_bar(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                          "name": "Legal"}).json()["case_id"]
    assert _uad1043(cid)                                  # neither text nor image yet
    st = api.store()
    kw = api.renderer().build_kwargs(cid, "form")
    edit = form.galley_html(form.build(st.tree(cid), folder=st.folder(cid), media=kw.get("media"),
                                       edit=True), edit=True)
    assert "class='ldadd'" in edit                        # the editor offers it

    r = client.post(f"/api/cases/{cid}/legal-description/photo",
                    files={"file": ("legal.png", _png(), "image/png")})
    assert r.status_code == 200
    tree = st.tree(cid)
    assert len(_legal_images(tree)) == 1 and schema.validate(tree) == []
    assert not _uad1043(cid)                              # the image answers for the text

    kw = api.renderer().build_kwargs(cid, "form")
    printed = form.galley_html(form.build(tree, folder=st.folder(cid), media=kw.get("media"),
                                          edit=False), edit=False)
    i = printed.find("Legal Description</span>")
    j = printed.find("Subject Property Commentary", i)
    assert "<img src='data:image/png" in printed[i:j]     # below the gray bar, in the subsection

    # a second one replaces the first
    client.post(f"/api/cases/{cid}/legal-description/photo",
                files={"file": ("legal2.png", _png(), "image/png")})
    assert len(_legal_images(st.tree(cid))) == 1

    # delivered as that IMAGE, pointing at the shipped file
    out = delivery.build(st.tree(cid), st.media(cid), st.media_dir(cid),
                         fills=api.get_prefs(cid).get("fills") or {})
    (image,) = _legal_images(out.tree)
    assert image.findtext("{*}ImageFileLocationIdentifier").endswith("legal2.png")
    assert schema.validate(out.tree) == []


def test_only_a_picture_is_taken(client):
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                          "name": "Legal"}).json()["case_id"]
    r = client.post(f"/api/cases/{cid}/legal-description/photo",
                    files={"file": ("notes.txt", b"lot 53", "text/plain")})
    assert r.status_code == 422
