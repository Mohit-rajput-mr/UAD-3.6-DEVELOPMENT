"""The Location Map, driven in a real browser as on the live site (T-416).

Owner, 2026-10-10 (DR §8): "Generate map" answered "unknown error"; "Save to
report" did nothing.  The server here runs as the live site does -- the
browser lays the report out and the server has no map tool of its own
(``api.SERVER`` is None, as on Vercel) -- and the browser fetches nothing from
the internet: the map tool's two libraries (Leaflet and MapLibre, which it
loads from cdnjs) are fetched once by this test and served to it, every map
tile is a stub, and WebGL is switched off so the tool draws raster tiles.

* Generate map is drawn by this browser with the same tool and lands in the
  report (before: "the map is drawn by the running server's map tool");
* a refusal is shown in the server's words (before: "unknown error");
* Save to report in the Location Map tab keeps the tool as it is (before: it
  was reloaded under the appraiser) and "Go to it" opens the report at a map
  that is the saved file;
* Save to report clicked while the tool is still reading the case waits for
  it (before: an empty map, "Nothing is placed on the map yet");
* the saved map is in the PDF and the ZIP the editor makes (DR §13);
* a map that cannot be made says why at once (before: 20 s, then "Could not
  save the map").

The server half is tests/test_location_map.py.

Run:  python -m pytest -q engine/tests/test_location_map_browser.py
"""
from __future__ import annotations

import hashlib
import io
import re
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad.report import browser  # noqa: E402

pytestmark = pytest.mark.skipif(not browser.AVAILABLE, reason=browser.MESSAGE)
TOOL = Path(__file__).resolve().parents[1] / "app" / "ui" / "map" / "index.html"
NO_WEBGL = """(()=>{const g=HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext=function(t,...a){return /webgl/i.test(String(t))?null:g.call(this,t,...a);};})()"""
TOASTS = """()=>{window.__toasts=[];new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{
  if(n.classList&&n.classList.contains('toast')) window.__toasts.push(n.textContent);}))).observe(document.body,{childList:true});}"""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _tile() -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (256, 256), (231, 235, 240)).save(out, "PNG")
    return out.getvalue()


@pytest.fixture(scope="module")
def libraries():
    """The map tool's libraries, exactly the files its page names (with their SRI)."""
    out = {}
    for url in sorted(set(re.findall(r"https://cdnjs\.cloudflare\.com/[^\"']+", TOOL.read_text(encoding="utf-8")))):
        try:
            out[url] = urllib.request.urlopen(url, timeout=30).read()
        except OSError as exc:
            pytest.skip(f"the map tool's libraries could not be fetched ({url}: {exc})")
    return out


@pytest.fixture(scope="module")
def site(tmp_path_factory, libraries):
    import uvicorn
    from playwright.sync_api import sync_playwright

    from app import api
    from app.access import COOKIE
    from app.cases import Store
    from app.main import ACCESS, app
    mp = pytest.MonkeyPatch()
    mp.setattr(browser, "server_layout", lambda: False)
    mp.setattr(api, "STORE", Store(tmp_path_factory.mktemp("map") / "cases"))
    for name in ("RENDERER", "LAYOUTS", "MAPPER", "SERVER"):
        mp.setattr(api, name, None)               # SERVER None: no map tool of the server's own
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    tile = _tile()

    def outside(route):
        url, kind = route.request.url, route.request.resource_type
        cors = {"Access-Control-Allow-Origin": "*"}
        if url in libraries:
            route.fulfill(body=libraries[url], headers=cors,
                          content_type="text/css" if url.endswith(".css") else "application/javascript")
        elif kind == "image":
            route.fulfill(body=tile, headers=cors, content_type="image/png")
        else:
            route.abort()

    pw = sync_playwright().start()
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1600, "height": 1000})
    ctx.add_cookies([{"name": COOKIE, "value": ACCESS.token, "url": base}])
    ctx.add_init_script(NO_WEBGL)
    ctx.route(re.compile(r"^https?://(?!127\.0\.0\.1[:/])"), outside)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/")
    try:
        yield base, page, api, errors
    finally:
        b.close()
        pw.stop()
        server.should_exit = True
        thread.join(10)
        mp.undo()


def _rf(page):
    el = page.query_selector("#rf")
    return el.content_frame() if el else None


def _until(page, get, timeout=240.0, what=""):
    """Wait for ``get()`` to be truthy.  The wait is Playwright's own, never
    time.sleep: the sync API runs this test's route handlers (the map tool's
    libraries, its tiles) only while Python is inside a Playwright call, so a
    plain sleep starves the browser of them and the map never draws."""
    end, last = time.time() + timeout, None
    while time.time() < end:
        try:
            last = get()
            if last:
                return last
        except Exception as exc:                  # a frame swapped mid-call
            last = repr(exc)
        page.wait_for_timeout(250)
    raise AssertionError(f"timed out waiting for {what} (last {last!r})")


def _open(site, template="sf1_appraisal_v1_4", blank=False) -> str:
    base, page, _api, _errors = site
    cid = page.evaluate("""async([t,b])=>{const r=await fetch('/api/cases',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({template:t,blank:b,name:'map'})});
        return (await r.json()).case_id;}""", [template, blank])
    page.goto(f"{base}/#/case/{cid}")
    page.wait_for_function("typeof S!=='undefined'&&S.caseId&&S.case&&document.querySelector('#rf-maps')",
                           timeout=120_000)
    page.evaluate(TOASTS)
    return cid


def _settled(page):
    """The report is laid out, its script listening, and no newer layout on its way."""
    _until(page, lambda: page.evaluate("S.formReady&&!(S.swaps&&S.swaps.form)&&!(S.checking&&S.checking.form)")
           and _rf(page).evaluate("!!document.querySelector(\".maploader[data-map='aerial']\")"), 240, "the report")
    page.wait_for_timeout(1000)


def _toast(page, *needles, timeout=200.0):
    return _until(page, lambda: next((t for t in page.evaluate("window.__toasts") if any(n in t for n in needles)), None),
                  timeout, f"a toast saying {needles}")


def _sales_map(api, cid):
    maps = [m for m in api.store().media(cid) if m.category == "map"]
    assert len(maps) == 1, maps
    return maps[0], (api.store().media_dir(cid) / maps[0].filename).read_bytes()


MAP_IN_REPORT = """async()=>{const b=document.querySelector("[data-map='SalesComparableMap']");
  const fig=b&&b.closest('figure'); const img=fig&&fig.querySelector('img');
  if(!img||!img.getAttribute('src')) return null;
  const buf=await (await fetch(img.src)).arrayBuffer();
  const h=await crypto.subtle.digest('SHA-1',buf);
  return Array.from(new Uint8Array(h)).map(x=>x.toString(16).padStart(2,'0')).join('');}"""


def _report_shows(page, data: bytes, timeout=240.0):
    want = hashlib.sha1(data).hexdigest()
    _until(page, lambda: _rf(page).evaluate(MAP_IN_REPORT) == want, timeout, "the saved map in the report")


def test_generate_map_is_drawn_in_this_browser_and_lands_in_the_report(site):
    """Clicked while the report's first layout is still on its way -- its
    galley read before the map existed, its pages held here until the map is
    saved.  (Before: that layout was shown and never caught up with.)"""
    base, page, api, errors = site
    held = []
    pages = re.compile(r"/api/cases/[^/]+/layout/form/pages$")
    page.route(pages, lambda route: held.append(route))
    try:
        cid = _open(site)
        _until(page, lambda: held, 120, "the report's first layout under way")
        page.click("#rf-maps")
        said = _toast(page, "Sales Comparison Map drawn", "could not be drawn")
        assert "Sales Comparison Map drawn" in said, said
    finally:
        for route in held:
            route.continue_()
        page.unroute(pages)
    _item, data = _sales_map(api, cid)
    assert data.startswith(b"\x89PNG")
    _report_shows(page, data)
    assert page.evaluate("document.querySelectorAll('iframe[title=\"Drawing the map\"]').length") == 0
    assert not errors, errors


def test_the_report_s_own_map_buttons_draw_in_this_browser_too(site):
    """Load Location Map in the map's box, and Aerial Map among the Site exhibits."""
    base, page, api, errors = site
    cid = _open(site)
    _settled(page)
    _rf(page).evaluate("document.querySelector(\".maploader[data-map='SalesComparableMap']\").click()")
    _until(page, lambda: [m for m in api.store().media(cid) if m.category == "map"], 120, "the map saved")
    _item, data = _sales_map(api, cid)
    _report_shows(page, data)
    _settled(page)
    _rf(page).evaluate("document.querySelector(\".maploader[data-map='aerial']\").click()")
    aerial = _until(page, lambda: [m for m in api.store().media(cid) if m.caption == "Aerial Map"], 120, "the aerial view saved")
    assert len(aerial) == 1 and aerial[0].category == "other" and int(aerial[0].section) == 4, aerial
    assert not errors, errors


def test_a_refusal_is_shown_in_the_server_s_own_words(site):
    base, page, api, errors = site
    _open(site)
    answers = [(503, "application/json", '{"detail": "The map service is down for maintenance."}',
                "The map could not be drawn: The map service is down for maintenance."),
               (500, "text/plain", "Internal Server Error",
                "The map could not be drawn: the server answered 500: Internal Server Error")]
    def refusing(status, kind, body):
        return lambda route: route.fulfill(status=status, content_type=kind, body=body)
    for status, kind, body, shown in answers:
        page.route(re.compile(r"/api/cases/[^/]+/maps$"), refusing(status, kind, body))
        try:
            page.evaluate("window.__toasts=[]")
            page.click("#rf-maps")
            said = _toast(page, "could not be drawn", "drawn —", timeout=30)
            assert said == shown, said
            assert "unknown error" not in said
        finally:
            page.unroute(re.compile(r"/api/cases/[^/]+/maps$"))


TOOL_SAID = """()=>{window.__said=[];const t=document.querySelector('#toast');
  new MutationObserver(()=>window.__said.push(t.textContent)).observe(t,{childList:true,characterData:true,subtree:true});}"""


def _map_tab(page, read=True):
    """The Location Map tab's tool -- with ``read``, once it has read the case."""
    page.click("#tabs .tab:has-text('Location Map')")
    up = "!!(window.UADMap&&document.querySelector('#btnToReport'))"

    def ready():
        el = page.query_selector("#panel iframe")
        fr = el.content_frame() if el else None
        return fr if fr and fr.evaluate(
            up + ("&&!document.body.hasAttribute('data-seeding')" if read else "")) else None
    return _until(page, ready, 120, "the Location Map tool")


def test_save_to_report_keeps_the_tool_and_goes_to_the_saved_map(site):
    base, page, api, errors = site
    cid = _open(site)
    _until(page, lambda: _rf(page).evaluate("!!document.querySelector('.mapedit')"), 240, "the report")
    # Save is clicked while the tool is still reading the case: its look-up of
    # where each property sits is held until after the click.  (Before: it
    # exported an empty map and said "Nothing is placed on the map yet".)
    held = []
    places = re.compile(r"/api/cases/[^/]+/maps/places\b")
    page.route(places, lambda route: held.append(route))
    try:
        tool = _map_tab(page, read=False)
        _until(page, lambda: held, 60, "the tool reading the case")
        tool.evaluate(TOOL_SAID)
        tool.evaluate("window.__same=1")
        page.evaluate("window.__toasts=[]")
        tool.click("#btnToReport")
        page.wait_for_timeout(1500)
        assert tool.evaluate("document.body.getAttribute('data-seeding')") == "1", "the case was read already"
        held[0].continue_()
    finally:
        page.unroute(places)
    said = _toast(page, "Sales Comparison Map saved into the report", timeout=120)
    assert not [s for s in tool.evaluate("window.__said") if "not saved" in s], tool.evaluate("window.__said")
    assert said == "✓ Sales Comparison Map saved into the reportGo to it", said
    assert tool.evaluate("window.__same") == 1, "the map tool was reloaded under the appraiser"
    _item, data = _sales_map(api, cid)
    page.click(".toast .toast-act")
    assert page.evaluate("S.view") == "report"
    _report_shows(page, data)
    # "Go to it" opened the report at the map
    _until(page, lambda: _rf(page).evaluate("""()=>{const f=document.querySelector("[data-map='SalesComparableMap']").closest('figure');
        const r=f.getBoundingClientRect(); return r.bottom>0&&r.top<innerHeight;}"""), 60, "the map in view")
    assert not errors, errors


def test_the_saved_map_prints_in_the_pdf_and_ships_in_the_package(site, monkeypatch, tmp_path):
    """DR §13: the map saved from this browser is in the PDF and the ZIP, which
    on the live site are both made from this browser's own layout."""
    import zipfile

    from lxml import etree
    from PIL import Image

    from uad import bind, delivery
    from uad.report import form
    fitz = pytest.importorskip("pymupdf")
    base, page, api, errors = site
    cid = _open(site)
    res = page.evaluate("UADDrawMap(S.caseId)")
    assert res.get("ok") and res.get("media_id"), res
    item, data = _sales_map(api, cid)
    want = Image.open(io.BytesIO(data)).convert("RGB")

    def has_map(pdf: bytes) -> bool:
        doc = fitz.open(stream=pdf)
        for pg in doc:
            for x in pg.get_images(full=True):
                got = doc.extract_image(x[0])
                if (got["width"], got["height"]) == want.size and \
                        Image.open(io.BytesIO(got["image"])).convert("RGB").tobytes() == want.tobytes():
                    return True
        return False

    drawn = page.evaluate("drawPdf()")
    assert drawn.get("pages"), drawn
    pdf, _html = api._client_pdf(cid)
    assert has_map(pdf), "the saved map is not in the PDF"

    # the deliverable, with the gate's verdict stubbed (the sample's own
    # photographs are rightly refused for delivery), as test_client_pdf does
    real = api._export_verdict
    monkeypatch.setattr(api, "_export_verdict", lambda c: (*real(c)[:1], [], [], True))
    for state in ("in_review", "signed"):
        api.store().transition(cid, state, "test", force=True)
    with page.expect_download(timeout=180_000) as dl:
        page.evaluate("exportZip()")
    path = tmp_path / "package.zip"
    dl.value.save_as(path)
    category = form.media_category({"category": "map", "caption": "Sales Comparison Map"})
    assert category in form.image_categories()          # the A-1 value, from engine/spec
    with zipfile.ZipFile(path) as z:
        assert z.read(f"{delivery.IMAGES}/{item.filename}") == data
        assert has_map(z.read(delivery.PDF_NAME))
        root = etree.fromstring(z.read(delivery.XML_NAME))
    m = f"{{{bind.MISMO}}}"
    named = [i.findtext(f"{m}ImageCategoryType") for i in root.iter(f"{m}IMAGE")
             if delivery.name_of(i.findtext(f"{m}ImageFileLocationIdentifier", "")) == item.filename]
    assert named == [category], named
    assert not errors, errors


def test_a_map_that_cannot_be_made_says_why_at_once(site):
    base, page, api, errors = site
    cid = _open(site, blank=True)                  # no address yet: nothing to place
    tool = _map_tab(page)
    tool.evaluate(TOOL_SAID)
    t0 = time.time()
    tool.click("#btnToReport")
    said = _until(page, lambda: next((s for s in tool.evaluate("window.__said") if s.startswith("The map was not saved")), None),
                  60, "the reason the map was not saved")
    assert time.time() - t0 < 15, "the reason came only after the 20-second wait"
    assert "Nothing is placed on the map yet" in said, said
    assert not [m for m in api.store().media(cid) if m.category == "map"]
