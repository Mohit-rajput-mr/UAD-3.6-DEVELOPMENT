"""Shared kit for the editor shell's browser tests (DR phase 2, S0a).

The live-server pattern of test_worksheet_grid.py, made shared: the real
server runs in this process with the browser laying the report out (the
live site's mode), one Chromium page is signed in to it (cookie =
app.main.ACCESS.token) at 1600 x 1000, and every page error is collected.

    from shell_kit import site, open_case, frame, until, measure_chrome  # noqa: F401

    def test_something(site):
        cid = open_case(site, "sf1_appraisal_v1_4")
        assert not site.errors, site.errors

``site`` is a module-scoped fixture; a test module that imports it gets one
server and one page for all its tests.  Not a test module itself.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad.report import browser  # noqa: E402

VIEWPORT = {"width": 1600, "height": 1000}
LAPTOP = {"width": 1280, "height": 720}       # the owner's laptop at 150 %
needs_browser = pytest.mark.skipif(not browser.AVAILABLE, reason=browser.MESSAGE)


@dataclass
class Site:
    base: str
    page: Any
    api: Any
    errors: list = field(default_factory=list)
    context: Any = None

    def goto(self, path: str = "/") -> None:
        self.page.goto(self.base + path)


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
    if not browser.AVAILABLE:
        pytest.skip(browser.MESSAGE)
    import uvicorn
    from playwright.sync_api import sync_playwright

    from app import api
    from app.access import COOKIE
    from app.cases import Store
    from app.main import ACCESS, app
    mp = pytest.MonkeyPatch()
    mp.setattr(browser, "server_layout", lambda: False)
    mp.setattr(api, "STORE", Store(tmp_path_factory.mktemp("shell") / "cases"))
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
    ctx = b.new_context(viewport=dict(VIEWPORT))
    ctx.add_cookies([{"name": COOKIE, "value": ACCESS.token, "url": base}])
    page = ctx.new_page()
    s = Site(base=base, page=page, api=api, context=ctx)
    page.on("pageerror", lambda e: s.errors.append(str(e)))
    page.goto(base + "/")
    try:
        yield s
    finally:
        b.close()
        pw.stop()
        server.should_exit = True
        thread.join(10)
        mp.undo()


def frame(page, sel: str = "#rf"):
    """The report frame's Playwright frame (looked up afresh: a swap replaces it)."""
    el = page.query_selector(sel)
    return el.content_frame() if el else None


def until(page, js: str, arg=None, timeout: float = 180.0, sel: str = "#rf"):
    """Wait until ``js`` (a function of the report frame's document) is truthy
    and return its value; the frame is looked up afresh each time."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        fr = frame(page, sel)
        if fr is not None:
            try:
                last = fr.evaluate(js, arg)
                if last:
                    return last
            except Exception:
                pass
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {js[:80]!r} (last {last!r})")


def new_case(site: Site, template: str, *, blank: bool = False, name: str = "shell test") -> str:
    """A new case from a template, through the API the editor uses (the
    context's own request client: independent of whatever the page is doing)."""
    r = site.context.request.post(site.base + "/api/cases",
                                  data={"template": template, "blank": blank, "name": name})
    assert r.ok, r.text()
    return r.json()["case_id"]


def open_case(site: Site, template: str | None = None, *, case_id: str | None = None,
              blank: bool = False, query: str = "", ready: bool = True) -> str:
    """Open a case in the editor (a new one from ``template`` unless
    ``case_id`` is given) and, with ``ready``, wait until the report frame has
    said it is ready.  ``query`` (e.g. "?shell=0") goes before the route."""
    cid = case_id or new_case(site, template, blank=blank)
    site.page.goto(f"{site.base}/{query}#/case/{cid}")
    site.page.wait_for_function(f"typeof S!=='undefined'&&S.caseId==='{cid}'&&!!S.review", timeout=60_000)
    if ready:
        site.page.wait_for_function("S.formReady===true&&!!document.querySelector('#rf')", timeout=300_000)
    return cid


def measure_chrome(site: Site, viewport: dict | None = None) -> dict:
    """At 1280 x 720 (the owner's laptop at 150 %): how far down the report
    frame starts (the chrome above it), how wide it is, and the zoom the
    report's pages are drawn at.  The viewport is put back afterwards."""
    page = site.page
    vp = viewport or LAPTOP
    before = page.viewport_size
    page.set_viewport_size(vp)
    try:
        page.wait_for_timeout(400)               # the frame refits on resize
        until(page, "()=>document.querySelector('.page')&&document.querySelector('.page').style.zoom", timeout=60)
        box = page.evaluate("""()=>{const r=document.querySelector('#rf').getBoundingClientRect();
            const h=document.querySelector('header').getBoundingClientRect();
            return {top:r.top,left:r.left,width:r.width,height:r.height,header:h.height,
                    shell:document.body.classList.contains('shell')};}""")
        zoom = float(frame(page).evaluate("()=>document.querySelector('.page').style.zoom") or 0)
        return {"viewport": f"{vp['width']}x{vp['height']}", "chrome": round(box["top"], 1),
                "header": round(box["header"], 1), "frame_width": round(box["width"], 1),
                "frame_height": round(box["height"], 1), "zoom": round(zoom, 4), "shell": box["shell"]}
    finally:
        if before:
            page.set_viewport_size(before)
