"""Every checkbox's box, tick and marks share one centre (T-125, DR brief §8).

The owner's screenshot (_work/owner/2026-10-10-desktop-rebuild/screenshots/
05-checkbox-misaligned.png): the problem outline round a Yes/No box sat up
and to the side of the box.  A Yes/No box is a Wingdings 2 glyph (Appendix E
CK), and the outline was drawn round the span holding the glyph, whose line
box is not the box the glyph draws.  Measured here on the pixels, in a real
browser, through the editor as the appraiser uses it (the server in the live
site's mode, the browser laying the report out), on sf1 and the 2-4 unit
sample:

* editor, "Mark what is unanswered" on: every glyph checkbox's problem
  outline ("Show problems", every checkbox faulted) and unanswered tint are
  centred on the box the glyph draws, within 0.5 px, and lie wholly round it;
* the box, ticked or not, is where the font file says (``form.box_glyph``) in
  the editor and in the preview, so the editor's boxes land where the printed
  ones do;
* every checkbox the editor draws as a box of its own (a tick cell, a rental
  pairing, a unit in the rent schedule): its tick's centre is the box's.

Run:  python -m pytest -q engine/tests/test_checkbox_centre.py
"""
from __future__ import annotations

import io
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad.report import browser, form  # noqa: E402

pytestmark = pytest.mark.skipif(not browser.AVAILABLE, reason=browser.MESSAGE)

DSF = 4          # device pixels per CSS pixel: a mark's edge is found to a quarter pixel
TOL = 0.5        # CSS px
PAD = 3.0        # CSS px round the box searched for its mark (the outline is 1.5 pt = 2 px)
SAMPLES = ("sf1_appraisal_v1_4", "2_to_4_unit_appraisal_v1_4")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """The real server in this process, laid out by the browser as on Vercel,
    and one high-density browser page signed in to it."""
    import uvicorn
    from playwright.sync_api import sync_playwright

    from app import api
    from app.access import COOKIE
    from app.cases import Store
    from app.main import ACCESS, app
    mp = pytest.MonkeyPatch()
    mp.setattr(browser, "server_layout", lambda: False)
    mp.setattr(api, "STORE", Store(tmp_path_factory.mktemp("ck") / "cases"))
    mp.setattr(api, "RENDERER", None)
    mp.setattr(api, "LAYOUTS", None)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    pw = sync_playwright().start()
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=DSF)
    ctx.add_cookies([{"name": COOKIE, "value": ACCESS.token, "url": base}])
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/")
    try:
        yield base, ctx, page, errors
    finally:
        b.close()
        pw.stop()
        server.should_exit = True
        thread.join(10)
        mp.undo()


def _frame(page):
    el = page.query_selector("#rf")
    return el.content_frame() if el else None


def _until(get, js: str, arg=None, timeout=180.0):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        fr = get()
        if fr is not None:
            try:
                last = fr.evaluate(js, arg)
                if last:
                    return last
            except Exception:
                pass
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {js[:80]!r} (last {last!r})")


# --------------------------------------------------------------- the pixels
def _image(png: bytes):
    from PIL import Image
    return Image.open(io.BytesIO(png)).convert("RGB")


def _bbox(img, kind: str):
    """The box, in CSS px from the clip's corner, of the pixels of one kind:
    ``ink`` the glyph (dark), ``red`` a fatal problem's outline, ``any``
    whatever is not white (the unanswered tint and the glyph inside it)."""
    from PIL import ImageChops
    r, g, b = img.split()
    if kind == "ink":
        mask = img.convert("L").point(lambda v: 255 if v < 128 else 0)
    elif kind == "red":
        mask = ImageChops.multiply(ImageChops.multiply(r.point(lambda v: 255 if v > 150 else 0),
                                                       g.point(lambda v: 255 if v < 120 else 0)),
                                   b.point(lambda v: 255 if v < 120 else 0))
    else:
        mask = ImageChops.darker(r, ImageChops.darker(g, b)).point(lambda v: 255 if v < 235 else 0)
    box = mask.getbbox()
    return None if box is None else tuple(v / DSF for v in box)


def _centre(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


GLYPH = r"""([sel, i])=>{
  const b=document.querySelectorAll(sel)[i];
  b.scrollIntoView({block:'center'});
  const t=[...b.childNodes].find(n=>n.nodeType===3)||b.firstChild;
  const r=document.createRange(); r.setStart(t,0); r.setEnd(t,1);
  const q=r.getBoundingClientRect(), wd=b.closest('.wd');
  const run=wd.closest('.bxs'), pg=b.closest('.page');
  return {x:q.left, y:q.top, w:q.width, h:q.height, size:parseFloat(getComputedStyle(wd).fontSize),
          zoom:parseFloat(getComputedStyle(pg).zoom)||1,
          ticked:t.data.charCodeAt(0)===0xF052, fid:b.dataset.fid||'',
          run:[...document.querySelectorAll('.wd')].indexOf(wd),
          untouched:!!(run&&run.classList.contains('untouched'))};
}"""


def _offset(page, frame_sel: str | None):
    if not frame_sel:
        return 0.0, 0.0
    return tuple(page.evaluate(f"""()=>{{const f=document.querySelector('{frame_sel}');
        const r=f.getBoundingClientRect(); return [r.left+f.clientLeft, r.top+f.clientTop];}}"""))


def _glyph_at(page, doc, frame_sel, sel: str, i: int) -> dict:
    g = doc.evaluate(GLYPH, [sel, i])
    ox, oy = _offset(page, frame_sel)
    g["x"] += ox
    g["y"] += oy
    return g


def _shot(page, x0, y0, x1, y1):
    return _image(page.screenshot(clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}))


def _boxes_where_the_font_says(page, doc, frame_sel, sel: str, where: str) -> list[dict]:
    """Every glyph checkbox under ``sel``: the box it draws, measured, and
    checked against the box the font file gives (``form.box_glyph``)."""
    geo = form.box_glyph()
    assert geo is not None, "no Wingdings 2 file to read the box from"
    n = doc.evaluate("(s)=>document.querySelectorAll(s).length", sel)
    assert n > 0, f"no checkbox in the {where}"
    out = []
    for i in range(n):
        g = _glyph_at(page, doc, frame_sel, sel, i)
        # the glyph's own cell: its advance, never the letter spacing after it
        adv = geo["advance"] * g["size"] * g["zoom"]
        ink = _bbox(_shot(page, g["x"], g["y"], g["x"] + adv, g["y"] + g["h"]), "ink")
        assert ink is not None, (where, i, g)
        ink = (ink[0] + g["x"], ink[1] + g["y"], ink[2] + g["x"], ink[3] + g["y"])
        em = g["size"] * g["zoom"]
        want_w, want_h = geo["width"] * em, geo["height"] * em
        # the box, ticked or not, is the font's box: the tick stays inside it
        assert abs((ink[2] - ink[0]) - want_w) <= 1.0 and abs((ink[3] - ink[1]) - want_h) <= 1.0, \
            (where, i, g, ink, want_w, want_h)
        # ...and sits in its cell where the font puts it
        want_cx = g["x"] + (geo["left"] + geo["width"] / 2) * em
        assert abs(_centre(ink)[0] - want_cx) <= TOL, (where, i, g, ink, want_cx)
        out.append(dict(g, ink=ink, i=i))
    return out


def _marks_round(page, doc, frame_sel, sel, boxes, kind: str, where: str) -> None:
    """Each box's mark of ``kind`` is centred on the box and wholly inside
    the searched margin round it (a mark cut off by the margin is off)."""
    bad = []
    for b in boxes:
        g = _glyph_at(page, doc, frame_sel, sel, b["i"])     # scrolled back into view
        dx, dy = g["x"] - b["x"], g["y"] - b["y"]
        x0, y0 = b["ink"][0] + dx - PAD, b["ink"][1] + dy - PAD
        x1, y1 = b["ink"][2] + dx + PAD, b["ink"][3] + dy + PAD
        img = _shot(page, x0, y0, x1, y1)
        mark = _bbox(img, kind)
        if mark is None:
            bad.append((b["fid"], b["i"], "no mark"))
            continue
        w, h = x1 - x0, y1 - y0
        if mark[0] <= 0 or mark[1] <= 0 or mark[2] >= w or mark[3] >= h:
            bad.append((b["fid"], b["i"], "the mark runs past the box", mark, (w, h)))
            continue
        cx, cy = _centre(mark)
        ix, iy = _centre((b["ink"][0] + dx - x0, b["ink"][1] + dy - y0,
                          b["ink"][2] + dx - x0, b["ink"][3] + dy - y0))
        if abs(cx - ix) > TOL or abs(cy - iy) > TOL:
            bad.append((b["fid"], b["i"], f"off centre by ({cx - ix:+.2f}, {cy - iy:+.2f}) px"))
        if kind == "any":
            # the tint fills the box: its middle is tinted, not white
            px = img.getpixel((int(cx * DSF), int(cy * DSF)))
            if min(px) >= 235 and not b["ticked"]:
                bad.append((b["fid"], b["i"], "no tint inside the box", px))
    assert not bad, (where, kind, bad[:8], len(bad))


# --------------------------------------------------------------- the report
def _open(site, template: str) -> str:
    base, _ctx, page, _errors = site
    cid = page.evaluate("""async(t)=>{const r=await fetch('/api/cases',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({template:t,blank:false,name:'boxes'})});
        return (await r.json()).case_id;}""", template)
    page.goto(f"{base}/#/case/{cid}")
    page.wait_for_function("typeof S!=='undefined'&&S.caseId&&S.review", timeout=120_000)
    _until(lambda: _frame(page), "()=>document.querySelectorAll('.page .bx[data-pick]').length>0", timeout=300)
    return cid


BX = ".page .bx[data-pick]"


@pytest.mark.parametrize("template", SAMPLES)
def test_every_checkbox_shares_one_centre(site, template):
    base, ctx, page, errors = site
    cid = _open(site, template)
    fr = _frame(page)

    # the boxes alone: "Mark what is unanswered" off, no problem shown
    page.uncheck("#rf-gaps")
    _until(lambda: _frame(page), "()=>!document.body.classList.contains('show-gaps')", timeout=10)
    boxes = _boxes_where_the_font_says(page, fr, "#rf", BX, f"{template} editor")
    assert any(b["ticked"] for b in boxes) and any(not b["ticked"] for b in boxes)

    # "Mark what is unanswered" on, the way the report opens
    page.check("#rf-gaps")
    _until(lambda: _frame(page), "()=>document.body.classList.contains('show-gaps')", timeout=10)
    waiting = [b for b in boxes if b["untouched"]]
    assert waiting, "the sample leaves no Yes/No unanswered to mark"
    _marks_round(page, fr, "#rf", BX, waiting, "any", f"{template} unanswered")

    # every checkbox faulted, as "Show problems" outlines an H-1 finding
    fids = sorted({b["fid"] for b in boxes})
    fr.evaluate("(items)=>window.postMessage({uad:'marks',items,on:true},'*')",
                [[f, "Fatal", "T-125"] for f in fids])
    _until(lambda: _frame(page), f"()=>document.querySelectorAll('{BX}.mk-fatal').length==={len(boxes)}",
           timeout=10)
    _marks_round(page, fr, "#rf", BX, boxes, "red", f"{template} problems")
    assert fr.evaluate(f"()=>document.querySelectorAll('{BX}.mk-fatal').length") == len(boxes)
    fr.evaluate("()=>window.postMessage({uad:'marks',items:[],on:false},'*')")

    # boxes of their own: the tick's centre is the box's -- a tick cell ticked
    # by a click (the editor's script draws that tick), and every one ticked
    cell = "td.tickcell"
    if fr.evaluate(f"()=>document.querySelectorAll('{cell}').length"):
        fr.evaluate(f"()=>document.querySelector('{cell}:not(:has(svg))').scrollIntoView({{block:'center'}})")
        fr.click(f"{cell}:not(:has(svg))")
        _until(lambda: _frame(page), f"()=>document.querySelectorAll('{cell} svg.tick').length>0", timeout=30)
    fr = _frame(page)
    ticks = fr.evaluate("""()=>[...document.querySelectorAll(
        'td.tickcell > span, .rpairs .rpx, .rsinc .rsu > i')].filter(b=>b.querySelector('svg.tick path')).map(b=>{
        const r=b.getBoundingClientRect(), t=b.querySelector('svg.tick path').getBoundingClientRect();
        return {kind:b.className||b.tagName, box:[(r.left+r.right)/2,(r.top+r.bottom)/2],
                tick:[(t.left+t.right)/2,(t.top+t.bottom)/2]};})""")
    assert ticks, "no ticked box of its own to measure"
    for t in ticks:
        assert abs(t["box"][0] - t["tick"][0]) <= TOL and abs(t["box"][1] - t["tick"][1]) <= TOL, t
    if template.startswith("2_to_4"):
        assert {"rpx on", "I"} <= {t["kind"] for t in ticks}
    # nothing in the editor ticks with a character of some fallback face
    assert not fr.evaluate("""()=>[...document.querySelectorAll('.rpairs .rpx, .rsinc .rsu > i, td.tickcell > span')]
        .some(b=>b.textContent.trim())""")

    # the preview the PDF is drawn from: the same boxes, where the font says
    prev = ctx.new_page()
    try:
        prev.goto(f"{base}/api/cases/{cid}/preview")
        _until(lambda: prev.main_frame, "()=>document.querySelectorAll('.page .wd').length>0", timeout=300)
        # each glyph of a run in a plain span of its own (nothing moves), so
        # the same measuring applies
        prev.evaluate("""()=>document.querySelectorAll('.page .wd').forEach(w=>{
            if(w.querySelector('.bx')) return;
            w.innerHTML=[...w.textContent].map(c=>'<span class="pvbx">'+c+'</span>').join('');})""")
        printed = _boxes_where_the_font_says(prev, prev.main_frame, None, ".page .wd .pvbx", f"{template} preview")
        # a pair's boxes share their middle line: the tick does not move a box
        rows: dict[int, list[float]] = {}
        for b in printed:
            rows.setdefault(b["run"], []).append(_centre(b["ink"])[1])
        for ys in rows.values():
            assert max(ys) - min(ys) <= TOL, ys
        assert any(b["ticked"] for b in printed) and any(not b["ticked"] for b in printed)
    finally:
        prev.close()
    assert not errors, errors
