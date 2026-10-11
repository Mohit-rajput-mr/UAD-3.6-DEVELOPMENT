"""A dropdown and a Yes/No picked in the editor itself save (T-1072, brief section 8).

The server side is tests/test_every_choice_saves.py; this drives the page's
own script (flow.EDIT_JS) in a real browser, with the server in the live
site's mode (the browser lays the report out):

* Subject Listing's Data Source (19.001): its list opens, "MLS" is picked,
  and it is in the delivered XML tied to the subject's listing, and on the
  page after a reload;
* on a new 2-4 unit report, the ADU box of Unit 2's Unit Interior is ticked:
  it lands in Unit 2, not in Unit 1 -- the box carries its unit's address
  (data-iscope) and the script sends it.

Run:  python -m pytest -q engine/tests/test_choice_saves_browser.py
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
from uad.report import browser  # noqa: E402

pytestmark = pytest.mark.skipif(not browser.AVAILABLE, reason=browser.MESSAGE)
M = f"{{{bind.MISMO}}}"
X = "{http://www.w3.org/1999/xlink}"


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
    mp.setattr(api, "STORE", Store(tmp_path_factory.mktemp("choices") / "cases"))
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


def _saved(check, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return True
        time.sleep(0.2)
    return False


def _open(page, base, template):
    cid = page.evaluate("""async(t)=>{const r=await fetch('/api/cases',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({template:t,blank:true,name:'choices'})});
        return (await r.json()).case_id;}""", template)
    page.goto(f"{base}/#/case/{cid}")
    page.wait_for_function("typeof S!=='undefined'&&S.caseId", timeout=60_000)
    return cid


def _listing_sources(api, cid):
    root = api.STORE.tree(cid).getroot()
    summary = next(bind.subject(root).iter(f"{M}LISTING_INFORMATION_SUMMARY"), None)
    if summary is None:
        return []
    tied = {r.get(f"{X}from") for r in root.iter(f"{M}RELATIONSHIP")
            if r.get(f"{X}to") == summary.get(f"{X}label")
            and r.get(f"{X}arcrole", "").endswith("IsDataSourceFor_LISTING_INFORMATION_SUMMARY")}
    return [ds.findtext(f"{M}DataSourceType") for ds in root.iter(f"{M}DATA_SOURCE")
            if ds.get(f"{X}label") in tied]


PICK = '.v.pick[data-fid="19.001"]'


def test_the_listing_data_source_is_picked_in_the_page(site):
    base, page, api, errors = site
    cid = _open(page, base, "sf1_appraisal_v1_4")
    _until(page, f"()=>!!document.querySelector('{PICK}')", timeout=300)
    fr = _frame(page)
    fr.evaluate(f"()=>document.querySelector('{PICK}').scrollIntoView({{block:'center'}})")
    fr.click(PICK)
    _until(page, "()=>!!document.querySelector('.picklist div[data-pv=\"MLS\"]')")
    # typed into the list's own find box and taken with Enter (a click that
    # scrolls the page closes the list, as any scroll does)
    fr = _frame(page)
    find = fr.locator(".picklist input.pfind")
    find.type("MLS")
    find.press("Enter")
    assert _saved(lambda: _listing_sources(api, cid) == ["MLS"]), _listing_sources(api, cid)
    # no red outline, and the value is there after the report is drawn again
    assert not _frame(page).evaluate(f"()=>document.querySelector('{PICK}').classList.contains('failed')")
    page.reload()
    page.wait_for_function("typeof S!=='undefined'&&S.caseId", timeout=60_000)
    shown = _until(page, "()=>Array.from(document.querySelectorAll('[data-fid=\"19.001\"],[data-tf=\"19.001\"]'))"
                         ".map(e=>e.textContent.trim()).filter(Boolean).join('|')", timeout=300)
    assert shown == "MLS"
    assert not errors, errors


# a Yes box every unit's Unit Interior draws on a new report ("Unit Interior
# Defects Exist?"; the ADU question waits for an ADU count, T-1066)
BOX = '.bx[data-fid="10.055"][data-pick="true"]'


def test_a_box_in_unit_2_is_unit_2s(site):
    base, page, api, errors = site
    cid = _open(page, base, "2_to_4_unit_appraisal_v1_4")
    _until(page, f"()=>document.querySelectorAll('{BOX}').length===2", timeout=300)
    fr = _frame(page)
    assert fr.evaluate(f"()=>Array.from(document.querySelectorAll('{BOX}')).map(b=>!!b.dataset.iscope)") \
        == [True, True]
    fr.evaluate(f"()=>document.querySelectorAll('{BOX}')[1].scrollIntoView({{block:'center'}})")
    fr.locator(BOX).nth(1).click()

    def units():
        root = api.STORE.tree(cid).getroot()
        return [u.findtext(f"{M}PROPERTY_UNIT_DETAIL/{M}UnitInteriorDefectsExistIndicator")
                for u in bind.subject(root).iter(f"{M}PROPERTY_UNIT")]
    assert _saved(lambda: units()[1:2] == ["true"]), units()
    assert units()[0] != "true", units()
    assert not errors, errors
