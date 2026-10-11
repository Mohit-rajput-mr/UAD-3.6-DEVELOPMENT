"""The Location Map reaches the report on every host (T-416, DR §8 / §13).

Owner, 2026-10-10: "Generate map" answered "unknown error" and "Save to report"
did nothing.  Two mechanisms were behind it:

* ``POST /maps`` could only draw with the server's own headless browser.  The
  live site (a serverless function) has none, and a server whose browser fails
  (a timeout, a tile host it cannot reach) let the exception out as a bare 500
  -- which the editor, reading only ``problems``, showed as "unknown error".
  Now a failure is always an answer in words, and a server that cannot draw
  answers ``state: "browser"``: the appraiser's browser draws the map with the
  same tool and posts the PNG to ``/maps/image`` (app/ui/map/draw.js).
* ``/maps/image`` is therefore how every map drawn in a browser lands.  Here it
  is checked end to end on all twelve D-1 samples: the media row, the galleys
  the live site lays out for the report, the preview and the PDF, the XML and
  Images/ of the package (one IMAGE whose ImageCategoryType is the A-1 value
  for the Sales Comparison Map, read from engine/spec), and a server restart.

The browser half (the editor's buttons and the map tool) is
tests/test_location_map_browser.py.

Run:  python -m pytest -q engine/tests/test_location_map.py
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import random
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, delivery, schema, templates  # noqa: E402
from uad.report import form  # noqa: E402

M = f"{{{bind.MISMO}}}"
SAMPLES = [t.key for t in templates.catalogue()]


def png(seed: int = 1, size: int = 96) -> bytes:
    """A real PNG, noisy enough to be served as an asset (> 4 KB of base64)."""
    from PIL import Image
    rnd = random.Random(seed)
    img = Image.new("RGB", (size, size))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(size * size)])
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from app import api
    from app.access import sign_in
    from app.cases import Store
    from app.main import app
    saved = (api.STORE, api.RENDERER, api.LAYOUTS, api.MAPPER, api.SERVER)
    api.STORE = Store(tmp_path / "cases")
    api.RENDERER = api.LAYOUTS = api.MAPPER = None
    api.SERVER = None                       # as on the live site: no map tool of the server's own
    with TestClient(app, raise_server_exceptions=False) as c:
        sign_in(c)
        yield c, api
    api.STORE, api.RENDERER, api.LAYOUTS, api.MAPPER, api.SERVER = saved


def _case(c, template="sf1_appraisal_v1_4", blank=False) -> str:
    r = c.post("/api/cases", json={"template": template, "blank": blank, "name": "map"})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


def _save(c, cid, image, **extra):
    return c.post(f"/api/cases/{cid}/maps/image", files={"file": ("SalesCompMap.png", image, "image/png")},
                  **extra)


def _sales_map_category() -> str:
    """The A-1 ImageCategoryType of the Sales Comparison Map, from the spec."""
    cats = form.image_categories()                       # engine/spec/enumerations.json
    value = form.media_category({"category": "map", "caption": "Sales Comparison Map"})
    assert value in cats, f"{value!r} is not an A-1 ImageCategoryType"
    return value


# --------------------------------------------------------- Generate map
def test_a_server_with_no_map_tool_hands_the_drawing_to_the_browser(client):
    c, _api = client
    cid = _case(c)
    for route in ("maps", "maps/aerial"):
        r = c.post(f"/api/cases/{cid}/{route}")
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "browser", (route, r.json())


def test_a_failing_server_map_tool_answers_in_words_never_a_bare_500(client, monkeypatch):
    """Its own browser timed out: the answer says so and hands the drawing on."""
    import app.mapper as mapper
    c, api = client
    api.SERVER = {"base": "http://127.0.0.1:9", "cookie": "c", "token": "t"}
    monkeypatch.setattr(mapper, "_has_browser", lambda: True, raising=False)

    def timeout(*_a, **_k):
        raise TimeoutError("Timeout 90000ms exceeded.\n=========================== logs ===")
    monkeypatch.setattr(mapper, "render", timeout)
    cid = _case(c)
    for route in ("maps", "maps/aerial"):
        r = c.post(f"/api/cases/{cid}/{route}")
        assert r.status_code == 200, (route, r.status_code, r.text)
        body = r.json()
        assert body["state"] == "browser", body
        assert body["problems"] == ["the server's map tool failed (Timeout 90000ms exceeded.)"], body
    status = c.get(f"/api/cases/{cid}/maps").json()
    assert status["state"] != "drawing", "the status was left saying the map is being drawn"


def test_the_map_tool_s_own_refusal_is_passed_on_word_for_word(client, monkeypatch):
    import app.mapper as mapper
    c, api = client
    api.SERVER = {"base": "http://127.0.0.1:9", "cookie": "c", "token": "t"}
    monkeypatch.setattr(mapper, "_has_browser", lambda: True, raising=False)
    said = 'the subject address "1 Nowhere Rd" was not found on the map, so nothing was placed'
    monkeypatch.setattr(mapper, "render", lambda *a, **k: {"error": said})
    cid = _case(c)
    body = c.post(f"/api/cases/{cid}/maps").json()
    assert body == {"state": "failed", "problems": [said]}


# ------------------------------------------------- Save to report, end to end
def _assert_in_report(c, api, cid, data):
    """The map is the report's Sales Comparison Map everywhere it is read."""
    category = _sales_map_category()
    maps = [m for m in c.get(f"/api/cases/{cid}/media").json()["media"] if m["category"] == "map"]
    assert len(maps) == 1 and maps[0]["caption"] == "Sales Comparison Map", maps
    name = maps[0]["filename"]
    # the galleys the live site lays out: the report being edited, and the
    # preview -- the PDF is printed from the preview's pages
    payload = base64.b64encode(data).decode("ascii")
    asset = f"/api/cases/{cid}/asset/{hashlib.sha1(payload.encode('ascii')).hexdigest()[:20]}.png"
    for kind in ("form", "preview"):
        r = c.get(f"/api/cases/{cid}/layout/{kind}/galley")
        assert r.status_code == 200, (kind, r.text[:200])
        assert asset in r.text, f"the saved map is not in the {kind}"
    assert c.get(asset).content == data
    # the package: one IMAGE of the A-1 category, its file in Images/
    built = api._delivery(cid)
    images = [i for i in built.tree.getroot().iter(f"{M}IMAGE")
              if i.findtext(f"{M}ImageCategoryType", "").strip() == category]
    assert len(images) == 1, [etree.tostring(i)[:200] for i in images]
    loc = images[0].findtext(f"{M}ImageFileLocationIdentifier", "").strip()
    assert delivery.name_of(loc) == name and built.images[name].read_bytes() == data
    assert name in c.get(f"/api/cases/{cid}/package/check").json()["images"]
    assert schema.validate(built.tree) == []


@pytest.mark.parametrize("key", SAMPLES)
def test_a_map_saved_from_the_browser_is_in_the_report_preview_and_package(client, key):
    c, api = client
    cid = _case(c, key)
    data = png()
    r = _save(c, cid, data)
    assert r.status_code == 200, r.text
    assert r.json()["media_id"]
    _assert_in_report(c, api, cid, data)


def test_a_new_report_takes_the_map_as_its_sales_comparison_map(client):
    """A blank report has no IMAGE of its own for the map: it gains one."""
    c, api = client
    cid = _case(c, blank=True)
    data = png(2)
    assert _save(c, cid, data).status_code == 200
    _assert_in_report(c, api, cid, data)


def test_saving_again_replaces_the_map_and_it_survives_a_restart(client, tmp_path):
    from app.cases import Store
    c, api = client
    cid = _case(c)
    _save(c, cid, png(3))
    data = png(4)
    _save(c, cid, data)
    _assert_in_report(c, api, cid, data)                       # one map, the newer
    api.STORE = Store(tmp_path / "cases")                      # the server started again
    api.RENDERER = api.LAYOUTS = api.MAPPER = None
    _assert_in_report(c, api, cid, data)


def test_where_the_map_placed_a_property_is_written_back_where_the_document_has_none(client):
    c, api = client
    cid = _case(c, blank=True)
    state = {"subject": {"lat": 41.237970, "lng": -73.688520}, "comps": [{"lat": None, "lng": None}]}
    assert _save(c, cid, png(5), data={"state": json.dumps(state)}).status_code == 200
    tree = api.store().tree(cid)
    geo = bind.subject(tree.getroot()).find(f".//{M}GEOSPATIAL_INFORMATION")
    assert geo is not None, "the subject's position was not written"
    assert geo.findtext(f"{M}LatitudeIdentifier") == "41.237970"
    assert geo.findtext(f"{M}LongitudeIdentifier") == "-73.688520"
    assert schema.validate(tree) == []


def test_the_aerial_view_is_a_site_exhibit(client):
    c, api = client
    cid = _case(c, blank=True)
    data = png(6)
    r = _save(c, cid, data, params={"aerial": "true"})
    assert r.status_code == 200, r.text
    site = [m for m in c.get(f"/api/cases/{cid}/media").json()["media"] if m["caption"] == "Aerial Map"]
    assert len(site) == 1 and int(site[0]["section"]) == 4, site
    assert not [m for m in api.store().media(cid) if m.category == "map"], "filed as the comparables' map"
    built = api._delivery(cid)
    cats = {i.findtext(f"{M}ImageCategoryType") for i in built.tree.getroot().iter(f"{M}IMAGE")
            if delivery.name_of(i.findtext(f"{M}ImageFileLocationIdentifier", "")) == site[0]["filename"]}
    assert cats == {"SiteExhibit"} and "SiteExhibit" in form.image_categories()


def test_what_is_not_a_map_is_refused_with_a_reason(client):
    c, _api = client
    cid = _case(c)
    r = _save(c, cid, b"GIF89a not a png")
    assert r.status_code == 422 and "PNG" in r.json()["detail"]
