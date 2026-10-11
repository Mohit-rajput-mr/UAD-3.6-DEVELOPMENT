"""The adjustment worksheet inside the comparable grid, in a real browser (T-1085).

Owner's addendum 2026-10-10 (_work/owner/2026-10-10-desktop-rebuild/
ADDENDUM_11_WORKSHEET_IN_GRID.md).  Driven through the editor as the appraiser
uses it, with the server in the live site's mode (the browser lays the report
out):

* every adjustable row of the sales grid carries the (+), on a single-family,
  a condominium and a 2-4 unit report, every unit's line included, and still
  after a comparable and a unit are added and after the grid is drawn again;
* the (+) opens the worksheet in a drawer beside the report (never over it);
  its live preview is the server's arithmetic; OK fills every comparable and
  the row's (+) turns into a tick with the rate; each cell's title is its
  arithmetic; Esc closes; Ctrl+J in a row opens that row's worksheet;
* a comparable's value changing recalculates the row in the grid;
* a signed report opens the worksheet read only.

Run:  python -m pytest -q engine/tests/test_worksheet_grid.py
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad.report import browser  # noqa: E402

GLA = "LivingUnitStandardFinishedAreaAboveGrade"
pytestmark = pytest.mark.skipif(not browser.AVAILABLE, reason=browser.MESSAGE)


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
    mp.setattr(api, "STORE", Store(tmp_path_factory.mktemp("ws") / "cases"))
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


def _open(site, template: str) -> str:
    base, page, _api, _errors = site
    cid = page.evaluate("""async(t)=>{const r=await fetch('/api/cases',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({template:t,blank:false,name:'ws grid'})});
        return (await r.json()).case_id;}""", template)
    page.goto(f"{base}/#/case/{cid}")
    page.wait_for_function("typeof S!=='undefined'&&S.caseId", timeout=60_000)
    _until(page, "()=>document.querySelectorAll('.wsi').length>0", timeout=300)
    return cid


ICONS = """()=>{const out=[];document.querySelectorAll('table.grid[data-gk="sales"] tbody tr').forEach(tr=>{
  const a=tr.querySelector('td.v.adj[data-ga]'); if(!a) return;
  const i=tr.querySelector('td.lbl .wsi');
  out.push({type:a.dataset.ga, inst:a.dataset.gai||'', icon:!!i, kind:i?i.dataset.kind:'',
            comps:Array.from(tr.querySelectorAll('td.v.adj[data-ga]')).map(td=>td.dataset.gc)});});return out;}"""


def _rows(page, api, cid):
    marks = page.evaluate(f"fetch('/api/cases/{cid}/worksheets/marks').then(r=>r.json())")
    rows = _until(page, ICONS)
    return marks, rows


def _assert_every_row_iconed(marks, rows):
    want = set(marks["rows"])
    assert want, "the grid offers no worksheet at all"
    for r in rows:
        assert r["icon"] == (r["type"] in want), r
    assert want <= {r["type"] for r in rows if r["icon"]}


def test_single_family_row_icons_drawer_apply_recalc_and_keys(site):
    base, page, api, errors = site
    cid = _open(site, "sf1_appraisal_v1_4")
    marks, rows = _rows(page, api, cid)
    _assert_every_row_iconed(marks, rows)
    iconed = {r["type"] for r in rows if r["icon"]}
    assert {GLA, "LivingUnitBedroomCount", "LivingUnitBathroomCount", "SiteSize", "YearBuilt",
            "OutdoorLivingAmenity", "CoolingSystem"} <= iconed

    # drawn again in place (what a re-render does): the (+) comes back
    _frame(page).evaluate("()=>document.querySelectorAll('.wsi').forEach(i=>i.remove())")
    _until(page, f"()=>!!document.querySelector('.wsi[data-type=\"{GLA}\"]')", timeout=10)

    # the (+) opens the drawer beside the report, never over it
    fr = _frame(page)
    fr.evaluate(f"()=>document.querySelector('.wsi[data-type=\"{GLA}\"]').scrollIntoView({{block:'center'}})")
    fr.click(f'.wsi[data-type="{GLA}"]')
    page.wait_for_selector("#wsdock .wsd-amt", timeout=30_000)
    assert page.inner_text("#wsd-title") == "Finished Area Above Grade"
    rf, dock = page.query_selector("#rf").bounding_box(), page.query_selector("#wsdock").bounding_box()
    assert rf["x"] + rf["width"] <= dock["x"] + 0.5

    # the live preview is the server's arithmetic
    page.fill("#wsd-rate", "80")
    page.fill("#wsd-thr", "0")
    page.select_option("#wsd-round", "1")
    shown = page.eval_on_selector_all("#wsdock .wsd-amt", "els=>els.map(e=>e.value)")
    server = page.evaluate(f"fetch('/api/cases/{cid}/worksheets/gla?rate=80&threshold=0&rounding=1')"
                           ".then(r=>r.json())")
    assert shown == [str(c["lines"][0]["amount"]) for c in server["comparables"]] == ["-20640", "15840", "14880"]

    # Esc writes nothing
    page.keyboard.press("Escape")
    page.wait_for_function("!document.body.classList.contains('ws-open')", timeout=5_000)
    assert "20,640" not in _frame(page).inner_text(f'td.v.adj[data-ga="{GLA}"]')

    # OK fills every comparable; the (+) becomes a tick with the rate
    _frame(page).click(f'.wsi[data-type="{GLA}"]')
    page.wait_for_selector("#wsdock .wsd-amt", timeout=30_000)
    page.fill("#wsd-rate", "80")
    page.fill("#wsd-thr", "0")
    page.select_option("#wsd-round", "1")
    page.click("#wsd-ok")
    page.wait_for_function("!document.body.classList.contains('ws-open')", timeout=30_000)
    cells = _until(page, f"""()=>{{const t=Array.from(document.querySelectorAll('td.v.adj[data-ga="{GLA}"]'));
        return t.length&&t[0].innerText.includes('20,640')?t.map(td=>[td.innerText.trim(),td.title]):null;}}""", timeout=120)
    assert [c[0] for c in cells] == ["$(20,640)", "$15,840", "$14,880"]
    assert all("× $80" in c[1] for c in cells)
    assert _until(page, f"()=>{{const i=document.querySelector('.wsi[data-type=\"{GLA}\"]');"
                        "return i&&i.classList.contains('on')?i.textContent:''}") == "✓ $80/sf"

    # a comparable's area changes: the row is worked out again in the grid
    r = page.evaluate(f"""fetch('/api/cases/{cid}/comparables/1/fields/22.07.30',{{method:'PATCH',
        headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{value:'3,100'}})}}).then(r=>r.json())""")
    assert [(m["comp"], m["new"]) for m in r["recalculated"]] == [(1, "-7840")]
    page.evaluate("checkFresh('form')")
    _until(page, f"()=>document.querySelector('td.v.adj[data-ga=\"{GLA}\"]').innerText.includes('7,840')", timeout=120)

    # Ctrl+J in a row opens that row's worksheet
    fr = _frame(page)
    fr.locator('tr:has(td.v.adj[data-ga="LivingUnitBedroomCount"]) td.lbl').first.click()
    page.keyboard.press("Control+j")
    page.wait_for_function("document.querySelector('#wsd-title')&&document.querySelector('#wsd-title').textContent==='Bedrooms'",
                           timeout=30_000)
    page.keyboard.press("Escape")
    page.wait_for_function("!document.body.classList.contains('ws-open')", timeout=5_000)

    # signed: shown, never written
    for state in ("in_review", "signed"):
        api.store().transition(cid, state, "t", force=True)
    page.click("#rf-sadj")
    page.wait_for_selector("#wsdock .wsd-row", timeout=30_000)
    page.click('#wsdock .wsd-row[data-k="gla"]')
    page.wait_for_selector("#wsdock .wsd-amt", timeout=30_000)
    assert page.is_disabled("#wsd-ok")
    assert page.get_attribute("#wsdock .wsd-amt", "readonly") is not None
    page.keyboard.press("Escape")
    assert not errors, errors


def test_condominium_rows_carry_the_icon(site):
    base, page, api, errors = site
    cid = _open(site, "condo1_appraisal_v1_4")
    marks, rows = _rows(page, api, cid)
    _assert_every_row_iconed(marks, rows)
    assert GLA in {r["type"] for r in rows if r["icon"]}
    assert not errors, errors


def test_every_unit_line_and_new_comps_and_units_carry_the_icon(site):
    base, page, api, errors = site
    cid = _open(site, "2_to_4_unit_appraisal_v1_4")
    marks, rows = _rows(page, api, cid)
    _assert_every_row_iconed(marks, rows)
    gla = [r for r in rows if r["type"] == GLA]
    insts = {r["inst"] for r in gla}
    comps = {c for r in gla for c in r["comps"]}
    assert len(insts) >= 2                               # one area line per unit

    # one more comparable, one more unit
    assert page.evaluate(f"""fetch('/api/cases/{cid}/comparables',{{method:'POST',
        headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{kind:'sales'}})}}).then(r=>r.status)""") == 200
    from uad import worksheet
    n_units = worksheet.subject_units(api.store().tree(cid))
    status = page.evaluate(f"""fetch('/api/cases/{cid}/fields/3.005',{{method:'PATCH',
        headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{value:'{n_units + 1}',confirm:true}})}})
        .then(r=>r.status)""")
    assert status == 200
    page.evaluate("checkFresh('form')")
    _until(page, f"""()=>{{const t=Array.from(document.querySelectorAll('td.v.adj[data-ga="{GLA}"]'));
        return new Set(t.map(td=>td.dataset.gai||'0')).size>{len(insts)}&&new Set(t.map(td=>td.dataset.gc)).size>{len(comps)};}}""",
           timeout=240)
    marks, rows = _rows(page, api, cid)
    _assert_every_row_iconed(marks, rows)
    gla = [r for r in rows if r["type"] == GLA]
    assert gla and all(r["icon"] for r in gla)
    assert len({r["inst"] for r in gla}) == len(insts) + 1
    assert len({c for r in gla for c in r["comps"]}) == len(comps) + 1
    assert not errors, errors


def test_the_sketch_panel_fills_the_window(site):
    """The Sketch button opens the sketch tool over the whole window (its
    overlay rules were lost once with a stylesheet edit: the tool showed as a
    small box in a corner -- owner's screenshot 2026-10-11)."""
    base, page, api, errors = site
    _open(site, "sf1_appraisal_v1_4")
    page.click("#rf-sketch")
    page.wait_for_selector("#sketch-ov iframe", timeout=30_000)
    box = page.query_selector("#sketch-ov").bounding_box()
    view = page.viewport_size
    assert box["x"] == 0 and box["y"] == 0
    assert box["width"] >= view["width"] - 1 and box["height"] >= view["height"] - 1
    frame = page.query_selector("#sketch-ov iframe").bounding_box()
    assert frame["width"] >= view["width"] - 1 and frame["height"] >= view["height"] - 1
    page.evaluate("document.getElementById('sketch-ov').remove()")
