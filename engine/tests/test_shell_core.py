"""The editor shell's core and its hooks in the editor (DR phase 2, S0a, T-1206).

_work/dr/PHASE2_SHELL_PLAN.md.  Driven in a real browser against the real
server (shell_kit), in the live site's mode:

* the shell is on by default (body.shell), ?shell=0 gives the classic editor
  (tabs and report toolbar, no body.shell) and the choice survives a reload,
  ?shell=1 brings the shell back; the served page carries the shell files'
  content digest in place of {{SHELLV}};
* the core's registries work: frames (pane 1 is #rf), commands (unknown ids
  tolerated), the one keymap (parent keydown and a frame's forwarded combo,
  combos pushed to the frame), panels (stub host at the top of #insp), state
  (clamped), the Esc stack, replay;
* CATALOG E-187: the masthead's counts follow every review -- after an edit
  that changes them, #stat == Sign-off == S.review.counts without a reload;
* CATALOG E-189: outlines survive a layout swap without a new review;
* a 'uad:review' event comes from each of the five review paths;
* CATALOG E-188: Export ZIP has one handler -- unsigned, the gate's dialog;
  signed on a host without server layout, exportZip() runs.

Run:  python -m pytest -q engine/tests/test_shell_core.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_kit import frame, measure_chrome, needs_browser, open_case, site, until  # noqa: E402,F401

CASE: dict = {}
MARKED = "()=>!!document.querySelector('.mk-fatal,.mk-warn')"


# ------------------------------------------------------------- no browser
def test_shell_digest_is_content_only_and_served():
    from app import main
    assert main.SHELLV == main.shell_digest() == main.shell_digest()
    assert len(main.SHELLV) == 12
    html = main.home().body.decode("utf-8")
    assert "{{SHELLV}}" not in html
    assert f"/ui/shell/core.js?v={main.SHELLV}" in html
    assert f"/ui/shell/shell.css?v={main.SHELLV}" in html


def test_shell_digest_changes_with_a_shell_file(tmp_path):
    from app import main
    copy = tmp_path / "shell"
    shutil.copytree(main.UI / "shell", copy)
    assert main.shell_digest(copy) == main.SHELLV
    f = copy / "split.js"
    f.write_text(f.read_text(encoding="utf-8") + "\n// changed\n", encoding="utf-8")
    assert main.shell_digest(copy) != main.SHELLV


# ---------------------------------------------------------------- browser
def _shell(page) -> bool:
    return page.evaluate("document.body.classList.contains('shell')")


@needs_browser
def test_kill_switch_and_the_shell_on_by_default(site):
    page = site.page
    site.goto("/?shell=0")
    page.wait_for_function("typeof UADShell!=='undefined'")
    assert not _shell(page) and page.evaluate("UADShell.enabled()") is False
    # the stored choice holds without the query, and across a reload
    cid = CASE["id"] = open_case(site, "sf1_appraisal_v1_4", blank=True)
    assert not _shell(page)
    assert page.is_visible("#tabs") and page.is_visible(".rf-bar")
    page.reload()
    page.wait_for_function(f"typeof S!=='undefined'&&S.caseId==='{cid}'&&S.formReady===true", timeout=300_000)
    assert not _shell(page)
    classic = measure_chrome(site)

    open_case(site, case_id=cid, query="?shell=1")
    assert _shell(page) and page.evaluate("document.body.classList.contains('shell-case')")
    assert page.evaluate("UADShell.enabled()") is True
    shell = measure_chrome(site)
    # the baseline the later steps are measured against (plan "Budget at 1280x720")
    print(f"\nchrome at 1280x720: classic {classic}\n                   shell   {shell}")
    assert classic["zoom"] > 0 and shell["zoom"] > 0
    assert shell["chrome"] <= classic["chrome"]

    # the launcher keeps its own look, and the default is the shell
    page.evaluate("showLaunch()")
    assert _shell(page) and not page.evaluate("document.body.classList.contains('shell-case')")
    page.evaluate("localStorage.removeItem('uad-shell')")
    site.goto("/")
    page.wait_for_function("typeof UADShell!=='undefined'")
    assert _shell(page)
    html = page.evaluate("fetch('/').then(r=>r.text())")
    from app import main
    assert "{{SHELLV}}" not in html and f"?v={main.SHELLV}" in html
    assert not site.errors, site.errors


@needs_browser
def test_core_registries(site):
    page = site.page
    open_case(site, case_id=CASE["id"])
    fr = frame(page)
    fr.evaluate("""()=>{window.__got=[]; addEventListener('message',e=>{
        if(e.data&&e.data.uad) window.__got.push(e.data);});}""")
    out = page.evaluate("""async()=>{
      const U=UADShell, out={};
      const rf=document.querySelector('#rf');
      out.panes=U.frames.all().map(f=>f.pane);
      out.of=U.frames.of(rf.contentWindow); out.ofSelf=U.frames.of(window);
      out.active=U.frames.activePane();
      out.unknown=U.commands.run('no.such.command');
      const ran=window.__ran=[];
      U.commands.register({id:'test.f9',label:'Test',keys:['f9'],run:c=>{ran.push(c.via+':'+(c.pane||0));}});
      out.key=U.keys.map()['F9'];
      out.combo=U.keys.combo('ctrl+shift+s');
      document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'F9',bubbles:true,cancelable:true}));
      // a plain character is never taken from a field
      U.commands.register({id:'test.q',label:'Q',keys:['Q'],run:()=>ran.push('q')});
      const inp=document.createElement('input'); document.body.appendChild(inp);
      inp.dispatchEvent(new KeyboardEvent('keydown',{key:'q',bubbles:true,cancelable:true}));
      inp.remove(); U.commands.unregister('test.q');
      await new Promise(r=>setTimeout(r,50));
      out.ran=ran.slice();
      // panels: the stub host mounts at the top of #insp, again after a rebuild
      const el=document.createElement('div'); el.textContent='hello';
      U.panels.register({id:'test',title:'Test panel',el});
      out.top1=document.querySelector('#insp').firstElementChild.id;
      document.querySelector('#insp').innerHTML=''; drawInsp();
      out.top2=document.querySelector('#insp').firstElementChild.id;
      out.signoff=!!document.querySelector('#insp #insp-sign');
      U.panels.unregister('test');
      out.gone=!document.querySelector('#shell-panel-test');
      // state is clamped and persisted
      U.state.set('left.w',99999); out.leftW=U.state.get('left.w');
      out.stored=JSON.parse(localStorage.getItem('uad-shell-v1')).left.w;
      U.state.reset();
      // Esc: a late item (focus mode) closes; never while the worksheet is open
      let open=true, closed=0;
      U.escape.register({id:'test.esc',order:7,open:()=>open,close:()=>{open=false;closed++;}});
      document.body.classList.add('ws-open');
      document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
      out.closedWhileWs=closed;
      document.body.classList.remove('ws-open');
      document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
      out.closed=closed;
      U.escape.register({id:'test.esc',order:7,open:()=>false,close:()=>{}});
      // kept messages reach every pane, and a replay
      U.frames.keep('test',{uad:'test-kept',n:1});
      U.frames.replay(rf.contentWindow);
      return out;}""")
    assert out["panes"] == [1] and out["of"] == 1 and out["ofSelf"] == 0 and out["active"] == 1
    assert out["unknown"] is False
    assert out["key"] == "test.f9" and out["combo"] == "Ctrl+Shift+S"
    assert out["ran"] == ["key:0"]
    assert out["top1"] == out["top2"] == "shell-panel-test" and out["signoff"] and out["gone"]
    assert out["stored"] == out["leftW"] < 99999
    assert out["closedWhileWs"] == 0 and out["closed"] == 1

    # the frame was given the keys, the kept message and a replay
    got = until(page, """()=>{const g=window.__got||[];
        const keys=g.filter(m=>m.uad==='shell-keys').pop();
        return keys&&keys.combos.includes('F9')&&g.some(m=>m.uad==='test-kept')
          &&g.some(m=>m.uad==='theme')&&g.some(m=>m.uad==='marks')?g.map(m=>m.uad):null;}""", timeout=10)
    assert "shell-keys" in got
    # a combo forwarded by the report frame runs the command, tagged with its pane
    fr.evaluate("()=>parent.postMessage({uad:'key',combo:'F9'},'*')")
    page.wait_for_function("window.__ran.includes('key:1')", timeout=10_000)
    page.evaluate("UADShell.commands.unregister('test.f9')")
    assert page.evaluate("Object.keys(UADShell.keys.map())") == []
    assert not site.errors, site.errors


@needs_browser
def test_e187_header_counts_follow_every_review(site):
    """E-187: only drawHead wrote the masthead's tally; a review after an edit
    (reviewSoon), saved-sections and the cached open left it behind Sign-off."""
    page = site.page
    cid = CASE["id"]
    before = page.evaluate("S.review.counts")
    page.evaluate("window.__whys=[]; document.addEventListener('uad:review',e=>window.__whys.push(e.detail.why))")
    status = page.evaluate(f"""fetch('/api/cases/{cid}/fields/3.000',{{method:'PATCH',
        headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{value:"123 Main St"}})}}).then(r=>r.status)""")
    assert status == 200
    # what the report frame says after each write: the editor asks the review again
    page.evaluate("window.postMessage({uad:'saved'},'*')")
    page.wait_for_function("window.__whys.includes('reviewSoon')", timeout=30_000)
    got = page.evaluate("""()=>({stat:[...document.querySelectorAll('#stat span b')].map(b=>+b.textContent),
        sign:[...document.querySelectorAll('#insp-sign .counts .count b')].map(b=>+b.textContent),
        counts:S.review.counts})""")
    c = got["counts"]
    assert c["fatal"] < before["fatal"]                   # the address was required
    assert got["stat"] == [c["fatal"], c["warning"], c["review"]]
    assert got["sign"] == [c["fatal"], c["warning"], c["review"], c["schema"]]
    assert not site.errors, site.errors


@needs_browser
def test_e189_outlines_survive_a_layout_swap(site):
    """E-189: a swapped-in layout was told the gaps and imported toggles but
    not the problem outlines, which vanished until the next review."""
    page = site.page
    if not page.is_checked("#rf-marks"):
        page.check("#rf-marks")
    until(page, MARKED, timeout=30)
    reviews: list[str] = []

    def seen(req):
        if req.url.split("?")[0].endswith("/review"):
            reviews.append(req.url)
    page.on("request", seen)
    try:
        frame(page).evaluate("()=>{window.__old=true;}")
        page.evaluate("swapFrame('form')")
        page.wait_for_function("""()=>{const f=document.querySelector('#rf');
            try{ return !S.swaps.form&&!!f&&!f.contentWindow.__old; }catch(e){ return false; }}""", timeout=300_000)
        until(page, MARKED, timeout=20)
    finally:
        page.remove_listener("request", seen)
    assert not reviews, reviews                  # no new review drew them
    assert not site.errors, site.errors


@needs_browser
def test_review_event_from_each_of_the_five_paths(site):
    page = site.page
    cid = CASE["id"]
    page.evaluate("window.__whys=[]; document.addEventListener('uad:review',e=>window.__whys.push(e.detail.why))")
    # the cached open answers first: the server's answer is held back a moment
    page.evaluate(f"""async()=>{{const real=window.api;
        window.api=(p,o)=>new Promise(r=>setTimeout(r,700)).then(()=>real(p,o));
        try{{ await openCase('{cid}'); }}finally{{ window.api=real; }}}}""")
    page.wait_for_function("window.__whys.includes('editor-cache')&&window.__whys.includes('refresh')", timeout=30_000)
    page.evaluate("window.postMessage({uad:'saved-sections',sections:[]},'*')")
    page.wait_for_function("window.__whys.includes('saved-sections')", timeout=30_000)
    page.evaluate("reviewSoon()")
    page.wait_for_function("window.__whys.includes('reviewSoon')", timeout=30_000)
    page.evaluate("S.autoResult={written:0,failed:[]}; autoFillDone()")
    page.wait_for_function("window.__whys.includes('autofill')", timeout=60_000)
    whys = page.evaluate("window.__whys")
    assert {"editor-cache", "refresh", "saved-sections", "reviewSoon", "autofill"} <= set(whys), whys
    page.wait_for_function("S.formReady===true&&!S.swaps.form", timeout=300_000)
    assert not site.errors, site.errors


@needs_browser
def test_e188_export_zip_has_one_handler(site):
    """E-188: fillSignoff assigned #zip's onclick twice; the second replaced
    the first, so where the server cannot lay out (Vercel) exportZip() never
    ran and the link was followed instead."""
    page = site.page
    cid = CASE["id"]
    page.evaluate("window.__zip=0; window.exportZip=()=>{window.__zip++;}; HOST={serverLayout:false}")
    page.click("#zip")                                     # a draft: the gate's dialog
    page.wait_for_selector(".uadd-back", timeout=10_000)
    assert "Sign the report before exporting it" in page.inner_text(".uadd-back")
    page.keyboard.press("Escape")
    page.wait_for_selector(".uadd-back", state="detached", timeout=10_000)
    assert page.evaluate("window.__zip") == 0

    for state in ("in_review", "signed"):
        site.api.store().transition(cid, state, "t", force=True)
    page.evaluate("refresh()")
    page.wait_for_function("S.case.state==='signed'", timeout=30_000)
    url = page.url
    page.evaluate("window.exportZip=()=>{window.__zip++;}; HOST={serverLayout:false}")
    page.click("#zip")
    page.wait_for_function("window.__zip===1", timeout=10_000)
    assert page.url == url and not page.query_selector(".uadd-back")
    assert not site.errors, site.errors
