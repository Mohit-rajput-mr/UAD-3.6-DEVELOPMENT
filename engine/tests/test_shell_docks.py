"""Every editor region is a window (owner 2026-10-11, T-1210; DR phase 2 S2).

The Sections window, the side-panels window, the top bar, the report and the
Sketch each minimize (to the tray), maximize, close and -- the side windows --
resize by dragging; the layout is the user's and survives a reload.  The
report frame is never reloaded by any of it.  ?shell=0 keeps the classic
editor.

Run:  python -m pytest -q engine/tests/test_shell_docks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_kit import frame, needs_browser, open_case, site, until  # noqa: E402,F401

pytestmark = needs_browser


def _box(page, sel):
    return page.evaluate(f"""()=>{{const e=document.querySelector({sel!r}); if(!e) return null;
        const r=e.getBoundingClientRect(); return {{x:r.x,y:r.y,w:r.width,h:r.height,
        vis:getComputedStyle(e).visibility}};}}""")


def _click(page, region, act):
    page.click(f'[data-win="{region}"][data-act="{act}"]:visible')


def _fresh(site):
    site.page.evaluate("localStorage.removeItem('uad-shell-v1')")


def test_side_windows_minimize_restore_and_survive_a_reload(site):
    page = site.page
    _fresh(site)
    cid = open_case(site, "sf1_appraisal_v1_4")
    page.wait_for_selector("#dock-l .winbar", timeout=60_000)
    rf0 = _box(page, "#rf")["w"]
    marker = page.evaluate("()=>{const w=document.getElementById('rf').contentWindow; w.__keep=1; return 1}")
    assert marker == 1

    _click(page, "left", "min")
    page.wait_for_function("document.body.classList.contains('win-left-min')")
    assert _box(page, "#dock-l")["w"] <= 1
    page.wait_for_function(f"document.getElementById('rf').getBoundingClientRect().width>{rf0}+100")
    page.wait_for_selector('#wintray .wchip[data-win="left"]')
    # the report frame was resized, never reloaded
    assert page.evaluate("document.getElementById('rf').contentWindow.__keep") == 1

    _click(page, "right", "closed")
    page.wait_for_function("document.body.classList.contains('win-right-closed')")
    assert _box(page, "#dock-r")["w"] <= 1

    # the layout is the user's: it survives a reload
    page.reload()
    page.wait_for_function("typeof S!=='undefined'&&S.caseId", timeout=60_000)
    page.wait_for_selector("#dock-l", state="attached", timeout=60_000)
    assert page.evaluate("document.body.classList.contains('win-left-min')")
    assert page.evaluate("document.body.classList.contains('win-right-closed')")

    # restore: the tray chip for a minimized one, the Windows list for a closed one
    page.click('#wintray .wchip[data-win="left"]')
    page.wait_for_function("!document.body.classList.contains('win-left-min')")
    page.click('#wintray [data-act="menu"]')
    page.click('#winmenu [data-win="right"][data-act="normal"]')
    page.wait_for_function("!document.body.classList.contains('win-right-closed')")
    assert _box(page, "#dock-l")["w"] > 150 and _box(page, "#dock-r")["w"] > 150
    assert not site.errors, site.errors


def test_a_side_window_resizes_by_dragging_and_resets_on_double_click(site):
    page = site.page
    _fresh(site)
    open_case(site, "sf1_appraisal_v1_4")
    page.wait_for_selector("#dock-r .dock-split", timeout=60_000)
    sp = _box(page, "#dock-r .dock-split")
    x, y = sp["x"] + sp["w"] / 2, sp["y"] + 200
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 80, y, steps=8)          # over the report frame: the drag must not be lost
    page.mouse.up()
    w = _box(page, "#dock-r")["w"]
    assert 410 <= w <= 430, w
    assert 410 <= page.evaluate("JSON.parse(localStorage.getItem('uad-shell-v1')).right.w") <= 430
    page.dblclick("#dock-r .dock-split")
    page.wait_for_function("Math.abs(document.getElementById('dock-r').getBoundingClientRect().width-340)<3")
    assert not site.errors, site.errors


def test_the_report_maximizes_and_everything_else_steps_aside(site):
    page = site.page
    _fresh(site)
    open_case(site, "sf1_appraisal_v1_4")
    page.wait_for_selector(".winctl-report [data-act='max']", timeout=60_000)
    page.click(".winctl-report [data-act='max']")
    page.wait_for_function("document.body.classList.contains('win-report-max')")
    vw = page.viewport_size["width"]
    rf = _box(page, "#rf")
    assert rf["w"] >= vw - 40, rf
    assert _box(page, "body > header")["h"] <= 1
    # Esc and the restore button both bring the others back
    page.keyboard.press("Escape")
    page.wait_for_function("!document.body.classList.contains('win-report-max')")
    page.click(".winctl-report [data-act='max']")
    page.click(".winctl-report [data-act='normal']")
    page.wait_for_function("!document.body.classList.contains('win-report-max')")
    assert _box(page, "body > header")["h"] >= 30
    assert not site.errors, site.errors


def test_the_top_bar_minimizes_to_the_tray(site):
    page = site.page
    _fresh(site)
    open_case(site, "sf1_appraisal_v1_4")
    page.wait_for_selector(".winctl-top [data-act='min']", timeout=60_000)
    rf0 = _box(page, "#rf")
    page.click(".winctl-top [data-act='min']")
    page.wait_for_function("document.body.classList.contains('win-top-min')")
    assert _box(page, "body > header")["h"] <= 1
    assert _box(page, "#rf")["y"] < rf0["y"]
    page.click('#wintray .wchip[data-win="top"]')
    page.wait_for_function("!document.body.classList.contains('win-top-min')")
    assert not site.errors, site.errors


def test_the_sketch_is_a_window(site):
    page = site.page
    _fresh(site)
    open_case(site, "sf1_appraisal_v1_4")
    page.click("#rf-sketch")
    page.wait_for_selector("#sketch-ov.win iframe", timeout=30_000)
    vp = page.viewport_size
    box = _box(page, "#sketch-ov")
    assert box["w"] >= vp["width"] - 1 and box["h"] >= vp["height"] - 1     # opens maximized
    # restore: a floating window, smaller, that can be moved by its bar
    page.click('#sketch-ov [data-win="sketch"][data-act="normal"]')
    page.wait_for_function("document.getElementById('sketch-ov').classList.contains('wnormal')")
    box = _box(page, "#sketch-ov")
    assert box["w"] < vp["width"] - 50 and box["h"] < vp["height"] - 50
    bar = _box(page, "#sketch-ov .winbar")
    page.mouse.move(bar["x"] + 60, bar["y"] + 12)
    page.mouse.down()
    page.mouse.move(bar["x"] + 160, bar["y"] + 72, steps=6)
    page.mouse.up()
    moved = _box(page, "#sketch-ov")
    assert abs(moved["x"] - box["x"] - 100) < 4 and abs(moved["y"] - box["y"] - 60) < 4
    # minimize to the tray and back
    page.click('#sketch-ov [data-win="sketch"][data-act="min"]')
    page.wait_for_function("document.getElementById('sketch-ov').classList.contains('wmin')")
    page.click('#wintray .wchip[data-win="sketch"]')
    page.wait_for_function("document.getElementById('sketch-ov').classList.contains('wnormal')")
    # close asks first
    page.click('#sketch-ov [data-win="sketch"][data-act="closed"]')
    page.wait_for_selector(".uadd-back button", timeout=5_000)
    page.click(".uadd-back .bar button:last-child")
    page.wait_for_function("!document.getElementById('sketch-ov')")
    assert not site.errors, site.errors


def _zoom(page):
    return until(page, "()=>{const p=document.querySelector('.page'); return p&&p.style.zoom?parseFloat(p.style.zoom):0}", timeout=30)


def test_the_report_grows_into_the_room_and_has_a_size_control(site):
    """Owner 2026-10-11: "report looks too small".  Fit (the default) fills
    the report window's width -- past actual size when the other windows give
    up their room -- and - / + set a fixed size, kept across a reload."""
    page = site.page
    _fresh(site)
    open_case(site, "sf1_appraisal_v1_4")
    page.wait_for_selector(".winctl-report .wz-v", timeout=60_000)
    z0 = _zoom(page)
    page.wait_for_function("document.querySelector('.winctl-report .wz-v').textContent.startsWith('Fit ')")
    _click(page, "left", "min")
    _click(page, "right", "min")
    page.wait_for_function("document.body.classList.contains('win-right-min')")
    until(page, f"()=>parseFloat(document.querySelector('.page').style.zoom)>{max(z0, 1.0)}+0.2", timeout=30)
    # - and + : a fixed size in 10 % steps, shown on the control and kept
    page.click(".winctl-report [data-act='zfit']")
    fit = _zoom(page)
    page.click(".winctl-report [data-act='zout']")
    want = round(round((fit - 0.1) * 20) / 20, 2)
    until(page, f"()=>Math.abs(parseFloat(document.querySelector('.page').style.zoom)-{want})<0.001", timeout=30)
    label = page.inner_text(".winctl-report .wz-v")
    assert label == f"{round(want * 100)}%", label
    page.reload()
    page.wait_for_function("typeof S!=='undefined'&&S.caseId", timeout=60_000)
    page.wait_for_function("S.formReady===true&&!!document.querySelector('#rf')", timeout=300_000)
    until(page, f"()=>Math.abs(parseFloat(document.querySelector('.page').style.zoom)-{want})<0.001", timeout=60)
    # Ctrl+0 fits the width again
    page.click(".winctl-report .wz-v")
    page.wait_for_function("document.querySelector('.winctl-report .wz-v').textContent.startsWith('Fit ')")
    assert abs(_zoom(page) - fit) < 0.01
    page.click(".winctl-report [data-act='zin']")
    page.wait_for_function("!document.querySelector('.winctl-report .wz-v').textContent.startsWith('Fit ')")
    page.keyboard.press("Control+0")
    page.wait_for_function("document.querySelector('.winctl-report .wz-v').textContent.startsWith('Fit ')")
    page.evaluate("localStorage.removeItem('uad-shell-v1')")
    assert not site.errors, site.errors


def test_the_classic_editor_has_no_window_chrome(site):
    page = site.page
    page.goto(site.base + "/?shell=0")
    try:
        cid = open_case(site, "sf1_appraisal_v1_4")
        page.wait_for_selector("#rail", timeout=60_000)
        assert page.evaluate("!document.getElementById('dock-l') && !document.querySelector('.winbar')")
        page.click("#rf-sketch")
        page.wait_for_selector("#sketch-ov iframe", timeout=30_000)
        box = _box(page, "#sketch-ov")
        assert box["w"] >= page.viewport_size["width"] - 1
        page.evaluate("document.getElementById('sketch-ov').remove()")
    finally:
        page.goto(site.base + "/?shell=1")
