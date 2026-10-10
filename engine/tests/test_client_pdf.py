"""The PDF drawn from the browser's layout, on a host with no Chromium (B5).

The live site runs where no browser can be started, so the report could be
laid out only in the appraiser's own browser and the PDF -- and the
deliverable ZIP with it -- answered 503.  ``uad/report/pdfdraw.py`` closes
that: the browser reports where it drew everything (``DISPLAY_JS``) and the
server writes the PDF from that, with its own fonts and pictures, after
checking the words against its own pages.

Checked here:

* fidelity: on official D-1 samples the drawn PDF has Chromium's page count,
  the same characters on every page, every glyph within 0.05 pt across and
  0.25 pt down of where Chromium's own PDF puts it, and every picture;
* the extraction does not depend on how the page is shown (the preview
  scales its pages to the window);
* the server refuses a drawing whose words are not the report's, a drawing
  of an older version, and pictures that are not the case's own;
* end to end, with the server forced into the live site's no-Chromium mode:
  the editor draws the PDF, report.pdf serves it, and the ZIP comes down in
  parts with that same PDF inside.

Run:  python -m pytest -q engine/tests/test_client_pdf.py
"""
from __future__ import annotations

import collections
import io
import json
import socket
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import templates  # noqa: E402
from uad.report import browser, flow, pdfdraw  # noqa: E402

fitz = pytest.importorskip("pymupdf")
needs_browser = pytest.mark.skipif(not browser.AVAILABLE, reason=browser.MESSAGE)
SAMPLES = ["sf1_appraisal_v1_4", "condo2_appraisal_v1_4", "2_to_4_unit_appraisal_v1_4"]


def _display(html: str, *, viewport=(900, 1400), before: str = "") -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--font-render-hinting=none"])
        try:
            pg = b.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            pg.set_content(html, wait_until="load", timeout=120_000)
            pg.evaluate("document.fonts.ready")
            if before:
                pg.evaluate(before)
            pg.wait_for_timeout(200)
            return pg.evaluate(pdfdraw.DISPLAY_JS)
        finally:
            b.close()


def _chars(page) -> list[tuple[str, float, float]]:
    out = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                for c in span["chars"]:
                    if not c["c"].isspace():
                        out.append((c["c"], c["origin"][0], c["origin"][1]))
    return out


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    """Each sample: Chromium's own PDF of the print HTML, and ours from the
    same pages."""
    if not browser.AVAILABLE:
        pytest.skip(browser.MESSAGE)
    out = {}
    folder = tmp_path_factory.mktemp("pdf")
    for key in SAMPLES:
        tpl = templates.get(key)
        html = flow.build(etree.parse(str(tpl.path)), folder=tpl.path.parent, screen=False)
        theirs = folder / f"{key}.pdf"
        flow.to_pdf(html, theirs)
        out[key] = (html, theirs.read_bytes())
    for key in SAMPLES:
        html, theirs = out[key]
        display = _display(html)
        ours = pdfdraw.write(display, allow_data_uri=True, title=key)
        out[key] = (html, theirs, display, ours)
    return out


@needs_browser
@pytest.mark.parametrize("key", SAMPLES)
def test_the_drawn_pdf_matches_chromiums(drawn, key):
    _html, theirs, display, ours = drawn[key]
    a, b = fitz.open(stream=theirs), fitz.open(stream=ours.pdf)
    assert len(b) == len(a) == ours.pages
    assert not ours.missing_glyphs and not ours.missing_images
    dx, dy = [], []
    for n in range(len(a)):
        ca, cb = _chars(a[n]), _chars(b[n])
        assert collections.Counter(c[0] for c in cb) == collections.Counter(c[0] for c in ca), \
            f"page {n + 1}: different characters"
        where = collections.defaultdict(list)
        for c in ca:
            where[c[0]].append(c)
        for c in cb:
            best = min(where[c[0]], key=lambda q: abs(q[1] - c[1]) + abs(q[2] - c[2]))
            dx.append(abs(best[1] - c[1]))
            dy.append(abs(best[2] - c[2]))
        assert len(b[n].get_image_info()) == len(a[n].get_image_info()), f"page {n + 1}: pictures"
    assert max(dx) < 0.05 and max(dy) < 0.25, (max(dx), max(dy))


@needs_browser
def test_the_drawn_pdf_is_text_in_the_reports_own_faces(drawn):
    _html, _theirs, _display_, ours = drawn["sf1_appraisal_v1_4"]
    doc = fitz.open(stream=ours.pdf)
    fonts = {f[3] for n in range(len(doc)) for f in doc[n].get_fonts(full=True)}
    assert fonts and all("+" in name for name in fonts)          # embedded subsets
    assert all(f[1] == "ttf" for n in range(len(doc)) for f in doc[n].get_fonts(full=True))
    assert "Uniform Residential Appraisal Report" in doc[0].get_text()
    assert doc.metadata["producer"] == "UAD 3.6 Form Filler"


@needs_browser
def test_a_scaled_preview_draws_the_same_pages():
    """The preview zooms each page to fit the window; the drawing must not care."""
    tpl = templates.get("sf1_appraisal_v1_4")
    tree = etree.parse(str(tpl.path))
    printed = flow.build(tree, folder=tpl.path.parent, screen=False)
    shown = flow.build(tree, folder=tpl.path.parent, screen=True)
    a = _display(printed)
    b = _display(shown, viewport=(560, 900))                 # FIT_JS zooms to ~0.66
    assert len(a["pages"]) == len(b["pages"])
    assert a["fonts"] == b["fonts"]
    for pa, pb in zip(a["pages"], b["pages"]):
        assert [t[4] for t in pa["t"]] == [t[4] for t in pb["t"]]
        for ta, tb in zip(pa["t"], pb["t"]):
            assert abs(ta[2] - tb[2]) < 0.06 and abs(ta[3] - tb[3]) < 0.06
        assert len(pa["r"]) == len(pb["r"])
        for ra, rb in zip(pa["r"], pb["r"]):
            assert all(abs(x - y) < 0.06 for x, y in zip(ra[:4], rb[:4]))


@needs_browser
def test_words_that_are_not_the_reports_are_refused(drawn):
    html, _theirs, display, _ours = drawn["sf1_appraisal_v1_4"]
    assert pdfdraw.check_text(display, html) >= 0
    forged = json.loads(json.dumps(display))
    run = next(t for t in forged["pages"][2]["t"] if len(t[4]) > 3)
    run[4] = run[4][:-1] + "9"
    with pytest.raises(pdfdraw.DisplayError):
        pdfdraw.check_text(forged, html)
    short = {**display, "pages": display["pages"][:-1]}
    with pytest.raises(pdfdraw.DisplayError):
        pdfdraw.check_text(short, html)


# ------------------------------------------------------------- the writer
def _one_page(**layers) -> dict:
    return {"v": 1, "w": 612, "h": 1008,
            "fonts": [{"family": "'UAD 9', Calibri", "weight": 400, "style": "normal", "size": 9}],
            "pages": [{"t": [], "r": [], "i": [], "s": [], **layers}]}


def test_a_run_whose_positions_do_not_match_its_text_is_refused():
    with pytest.raises(pdfdraw.DisplayError):
        pdfdraw.write(_one_page(t=[[0, "#000000", 36, 100, "abc", [500]]]))
    with pytest.raises(pdfdraw.DisplayError):
        pdfdraw.write(_one_page(t=[[3, "#000000", 36, 100, "a", []]]))


def test_a_character_the_face_lacks_comes_from_the_wide_face():
    # the kerned faces carry WinAnsi only; a check mark is not in it
    out = pdfdraw.write(_one_page(t=[[0, "#000000", 36, 100, "ok \u2713 \u2264", [450, 250, 250, 500, 300]]]))
    assert not out.missing_glyphs
    text = fitz.open(stream=out.pdf)[0].get_text()
    assert "\u2713" in text and "\u2264" in text


def test_an_svg_path_becomes_pdf_path_operators():
    ops = pdfdraw._path_ops("M1 5 L4 8 L9 1")
    assert ops == "1 5 m 4 8 l 9 1 l"
    assert pdfdraw._path_ops("m1 1 h2 v2 h-2 z") == "1 1 m 3 1 l 3 3 l 1 3 l h"
    assert pdfdraw._path_ops("M0 0 Q5 10 10 0").endswith(" c")
    assert pdfdraw._path_ops("E5 5 2 2").count(" c") == 4


def test_pictures_go_in_the_way_the_browser_shows_them():
    from PIL import Image
    # a PNG that needs no decoding passes straight through
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (200, 10, 10)).save(buf, "PNG")
    assert pdfdraw._png_passthrough(buf.getvalue())[:3] == (40, 20, 3)
    # a photograph turned by its EXIF orientation is turned in the PDF too
    img = Image.new("RGB", (60, 30), (10, 120, 10))
    exif = img.getexif()
    exif[0x0112] = 6                                       # rotate 90 on display
    jpg = io.BytesIO()
    img.save(jpg, "JPEG", exif=exif.tobytes())
    w = pdfdraw._Writer()
    oid = pdfdraw._image_object(w, jpg.getvalue())
    assert b"/Width 30 /Height 60" in w.objects[oid]
    # a picture with transparency keeps it
    rgba = io.BytesIO()
    Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(rgba, "PNG")
    oid = pdfdraw._image_object(w, rgba.getvalue())
    assert b"/SMask" in w.objects[oid]


def test_a_picture_the_server_cannot_read_is_reported():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(buf, "PNG")
    page = _one_page(i=[{"x": 36, "y": 100, "w": 100, "h": 80, "clip": [36, 100, 100, 80],
                         "src": "https://example.test/x.jpg"}])
    out = pdfdraw.write(page, resolve=lambda src: None)
    assert out.missing_images == ["https://example.test/x.jpg"]
    # the browser's raster stands in only for an SVG picture the caller accepts
    pixel = "data:image/png;base64," + __import__("base64").b64encode(buf.getvalue()).decode()
    photo = {"x": 0, "y": 0, "w": 10, "h": 10, "clip": None, "png": pixel}
    out = pdfdraw.write(_one_page(i=[{**photo, "src": "https://h/api/cases/c/asset/a.jpg"}]),
                        resolve=lambda src: None)
    assert out.missing_images                               # not for a photograph
    out = pdfdraw.write(_one_page(i=[{**photo, "src": "https://h/api/cases/c/asset/a.svg"}]),
                        raster_ok=lambda src: src.endswith("a.svg"))
    assert not out.missing_images
    out = pdfdraw.write(_one_page(i=[{**photo, "src": "https://h/api/cases/c/asset/b.svg"}]),
                        raster_ok=lambda src: src.endswith("a.svg"))
    assert out.missing_images                               # not for someone else's picture
    # a data URI is read only when the caller allows it
    out = pdfdraw.write(_one_page(i=[{"x": 0, "y": 0, "w": 1, "h": 1, "clip": None,
                                      "src": "data:image/png;base64,AAAA"}]))
    assert out.missing_images


# ------------------------------------------------------------- end to end
def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def live(tmp_path, monkeypatch):
    """The real server in this process, laid out by the browser as on Vercel."""
    if not browser.AVAILABLE:
        pytest.skip(browser.MESSAGE)
    import uvicorn

    from app import api
    from app.access import COOKIE
    from app.cases import Store
    from app.main import ACCESS, app
    monkeypatch.setattr(browser, "server_layout", lambda: False)
    monkeypatch.setattr(api, "STORE", Store(tmp_path / "cases"))
    monkeypatch.setattr(api, "RENDERER", None)
    monkeypatch.setattr(api, "LAYOUTS", None)
    monkeypatch.setattr(api, "PART", 400_000)               # several parts, as on Vercel
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", COOKIE, ACCESS.token, api
    finally:
        server.should_exit = True
        thread.join(10)


def test_the_editor_draws_the_pdf_and_exports_the_zip_in_parts(live, monkeypatch, tmp_path):
    from playwright.sync_api import sync_playwright
    base, cookie, token, api = live
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            ctx = b.new_context(accept_downloads=True)
            ctx.add_cookies([{"name": cookie, "value": token, "url": base}])
            page = ctx.new_page()
            page.goto(base + "/")
            made = page.evaluate("""async()=>{const r=await fetch('/api/cases',{method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({template:'sf1_appraisal_v1_4',blank:false,name:'PDF test'})});
                return await r.json();}""")
            case_id = made["case_id"]
            before = page.evaluate(f"fetch('/api/cases/{case_id}/report.pdf').then(r=>r.status)")
            assert before == 409                              # nothing drawn yet
            page.goto(f"{base}/#/case/{case_id}")
            page.wait_for_function("typeof S!=='undefined'&&S.caseId", timeout=60_000)
            assert page.evaluate("hostInfo()")["serverLayout"] is False

            res = page.evaluate("drawPdf()")
            assert res["pages"] == 20 and res["parts"] >= 3 and not res["missing_glyphs"]
            got = page.evaluate(f"""fetchParts('/api/cases/{case_id}/report.pdf',{res['parts']},{res['size']},
                'application/pdf').then(b=>b.arrayBuffer()).then(a=>Array.from(new Uint8Array(a)))""")
            pdf = bytes(got)
            doc = fitz.open(stream=pdf)
            assert len(doc) == 20
            kept_html = next((api.store().folder(case_id) / "_render" / "pdf").glob("*.html")).read_text()
            server_pages = pdfdraw.page_texts(kept_html)
            for n in range(len(doc)):
                drawn = "".join(doc[n].get_text().split())
                assert collections.Counter(drawn) <= collections.Counter(server_pages[n])

            # the words are checked: one changed character is refused
            forged = page.evaluate(f"""async()=>{{
                const fr=await pdfFrame('{case_id}');
                const src=await fetch('/api/report/display.js').then(r=>r.text());
                const d=fr.f.contentWindow.eval('('+src+')()'); fr.f.remove();
                const run=d.pages[1].t.find(t=>t[4].length>3); run[4]=run[4].slice(0,-1)+'9';
                const r=await fetch('/api/cases/{case_id}/report.pdf',{{method:'POST',
                  headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{key:fr.key,display:d}})}});
                const old=await fetch('/api/cases/{case_id}/report.pdf',{{method:'POST',
                  headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{key:'0000000000000000',display:d}})}});
                return [r.status, old.status];}}""")
            assert forged == [422, 409]
            # ...and a refusal never reads as "stale" to the case vault, which
            # would restore the case over this server's copy (and its PDF)
            assert list((api.store().folder(case_id) / "_render" / "pdf").glob("*.pdf"))

            # the deliverable, with the gate's verdict stubbed (the sample's own
            # photographs are rightly refused for delivery)
            real = api._export_verdict

            def verdict(cid):
                built, _problems, _blockers, _signed = real(cid)
                return built, [], [], True
            monkeypatch.setattr(api, "_export_verdict", verdict)
            for state in ("in_review", "signed"):
                api.store().transition(case_id, state, "test", force=True)
            with page.expect_download(timeout=180_000) as dl:
                page.evaluate("exportZip()")
            path = tmp_path / "package.zip"
            dl.value.save_as(path)
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                assert "appraisal.pdf" in names and "mismo.xml" in names
                assert z.read("appraisal.pdf") == pdf
            assert api.store().get(case_id).state == "exported"
        finally:
            b.close()
