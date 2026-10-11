"""Rows the appraiser adds to a comparable grid, in a real browser (T-1070, DR §7).

The owner saw "Name this row" rows spawn by themselves in the grid
(screenshots 02, 03).  Driven through the editor as the appraiser uses it,
with the server in the live site's mode (the browser lays the report out):

* a fresh report's grid has no named row, only a "+" under each group;
* "+" puts exactly one row on the page, its name a text box with a
  placeholder; "+" again goes back to it; a row left without a name goes;
* the name saves (Enter), the report is laid out again with the row, and it
  is still there after a reload; a value typed in its cell is that row's;
* the x shows on hover only, asks, and takes the row and its XML away.

The server side is in test_grid_rows.py.

Run:  python -m pytest -q engine/tests/test_grid_rows_browser.py
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind  # noqa: E402
from uad.report import browser, comparables  # noqa: E402

pytestmark = pytest.mark.skipif(not browser.AVAILABLE, reason=browser.MESSAGE)
M = f"{{{bind.MISMO}}}"
ADJUSTABLE = "SalesComparableAdditionalAdjustableComparisonItem"
PLUS = f'.liaddbtn[data-lit="{ADJUSTABLE}"]'


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """The real server in this process, laid out by the browser as on Vercel,
    and one browser page signed in to it."""
    import uvicorn
    from playwright.sync_api import sync_playwright

    from app import api
    from app.access import COOKIE
    from app.cases import Store
    from app.main import ACCESS, app
    mp = pytest.MonkeyPatch()
    mp.setattr(browser, "server_layout", lambda: False)
    mp.setattr(api, "STORE", Store(tmp_path_factory.mktemp("rows") / "cases"))
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
    ctx = b.new_context(viewport={"width": 1600, "height": 1000})
    ctx.add_cookies([{"name": COOKIE, "value": ACCESS.token, "url": base}])
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


def _frame(page):
    el = page.query_selector("#rf")
    return el.content_frame() if el else None


def _until(page, js: str, arg=None, timeout=180.0):
    """Wait until ``js`` (a function of the report frame's document) is true;
    the frame is looked up afresh each time, since a new layout swaps it."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        fr = _frame(page)
        if fr is not None:
            try:
                last = fr.evaluate(js, arg)
                if last:
                    return last
            except Exception:
                pass
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {js[:80]!r} (last {last!r})")


NAMES = "()=>Array.from(document.querySelectorAll('input.liin')).map(i=>i.value)"
HAS = "(n)=>Array.from(document.querySelectorAll('input.liin')).some(i=>i.value===n)"


def _items(api, cid, name):
    root = api.STORE.tree(cid).getroot()
    props = [bind.subject(root)] + comparables.properties(root, "SalesComparable")
    return [[n for n in p.iter(f"{M}COMPARABLE_ADJUSTMENT")
             if n.findtext(f"{M}AdditionalComparisonLineItemIdentifier") == name] for p in props]


def test_plus_name_reload_type_and_remove(site):
    base, page, api, errors = site
    cid = page.evaluate("""async()=>{const r=await fetch('/api/cases',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({template:'sf1_appraisal_v1_4',blank:true,name:'grid rows'})});
        return (await r.json()).case_id;}""")
    page.goto(f"{base}/#/case/{cid}")
    page.wait_for_function("typeof S!=='undefined'&&S.caseId", timeout=60_000)
    _until(page, f"()=>!!document.querySelector('{PLUS}')", timeout=300)

    # a fresh report: no named row at all, so nothing spawned by itself
    assert _frame(page).evaluate(NAMES) == []

    # + puts one row on the page, its name a real text box, ready to type;
    # + again goes back to it rather than adding a second
    fr = _frame(page)
    fr.evaluate(f"()=>document.querySelector('{PLUS}').scrollIntoView({{block:'center'}})")
    fr.click(PLUS)
    fr.click(PLUS)
    new = fr.evaluate("""()=>{const r=document.querySelectorAll('tr.linew');
        const i=r.length&&r[0].querySelector('input.liin');
        return {rows:r.length, focused:document.activeElement===i, ph:i&&i.placeholder, type:i&&i.type};}""")
    assert new == {"rows": 1, "focused": True, "ph": "Name this row", "type": "text"}

    # left without a name, it goes again and nothing is saved
    page.keyboard.press("Escape")
    assert fr.evaluate("()=>document.querySelectorAll('tr.linew').length") == 0
    root = api.STORE.tree(cid).getroot()
    assert next(root.iter(f"{M}AdditionalComparisonLineItemIdentifier"), None) is None

    # named: Enter saves it for the subject and every comparable, the report
    # is laid out again with the row, and it is still there after a reload
    fr.click(PLUS)
    page.keyboard.type("Pool")
    page.keyboard.press("Enter")
    _until(page, HAS, "Pool", timeout=120)
    assert _until(page, "()=>document.querySelectorAll('tr.linew').length===0", timeout=30)
    assert [len(x) for x in _items(api, cid, "Pool")] == [1, 1, 1, 1]
    page.reload()
    page.wait_for_function("typeof S!=='undefined'&&S.caseId", timeout=60_000)
    _until(page, HAS, "Pool", timeout=300)
    assert _frame(page).evaluate(NAMES) == ["Pool"]

    # a value typed in the row's cell is that row's own
    fr = _frame(page)
    row = "Array.from(document.querySelectorAll('input.liin')).find(i=>i.value==='Pool').closest('tr')"
    fr.evaluate(f"()=>{row}.scrollIntoView({{block:'center'}})")
    fr.evaluate(f"()=>{row}.querySelector('td.v.comp[data-gc=\"1\"]').click()")
    page.keyboard.type("In-ground")
    page.keyboard.press("Enter")
    end = time.time() + 30
    while time.time() < end:
        pool = _items(api, cid, "Pool")[1]
        if pool and pool[0].findtext(f"{M}AdditionalComparisonLineItemDescription") == "In-ground":
            break
        time.sleep(0.25)
    else:
        raise AssertionError("the typed value did not reach the row it was typed in")

    # the x shows on hover only; it asks, then the row and its XML go
    fr = _frame(page)
    vis = f"()=>getComputedStyle({row}.querySelector('.lidrop')).visibility"
    page.mouse.move(1, 1)
    assert fr.evaluate(vis) == "hidden"
    fr.hover("td.lbl.liname")
    assert fr.evaluate(vis) == "visible"
    fr.click("td.lbl.liname .lidrop")
    page.wait_for_selector(".uadd .bar button.go", timeout=10_000)
    page.click(".uadd .bar button.go")
    _until(page, "()=>document.querySelectorAll('input.liin').length===0"
                 f"&&!!document.querySelector('{PLUS}')", timeout=120)
    assert not any(_items(api, cid, "Pool"))
    assert not errors, errors
