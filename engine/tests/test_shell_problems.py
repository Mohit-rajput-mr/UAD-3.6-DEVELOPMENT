"""The Problems side panel (DR phase 2 S4, T-505): every problem beside the
report, never over it -- counted for the whole report, filtered by severity
and words, grouped by section, one click (or F8) from its field.

Run:  python -m pytest -q engine/tests/test_shell_problems.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_kit import frame, needs_browser, open_case, site, until  # noqa: E402,F401

pytestmark = needs_browser


def test_the_panel_counts_filters_and_takes_you_to_the_field(site):
    page = site.page
    page.evaluate("localStorage.removeItem('uad-shell-v1')")
    open_case(site, "sf1_appraisal_v1_4", blank=True)
    page.wait_for_selector("#shell-panel-problems .prb-row", timeout=60_000)
    # the chips count the whole report, as the review does
    want = page.evaluate("""()=>{const n={Fatal:0,Warning:0};
        (S.review.items||[]).forEach(i=>{ if(!/^not counted/.test(i.detail||'')&&n[i.severity]!==undefined) n[i.severity]++; });
        return n;}""")
    got = page.evaluate("""()=>Object.fromEntries([...document.querySelectorAll('#shell-panel-problems .prb-chip')]
        .map(c=>[c.dataset.sev, Number(c.querySelector('b').textContent)]))""")
    assert got["Fatal"] == want["Fatal"] and got["Warning"] == want["Warning"], (got, want)
    assert want["Fatal"] > 0
    # it sits beside the report, never over it
    panel = page.evaluate("document.getElementById('shell-panel-problems').getBoundingClientRect().left")
    rf = page.evaluate("document.getElementById('rf').getBoundingClientRect().right")
    assert panel >= rf - 1

    # a severity switched off leaves only the others
    page.click("#shell-panel-problems .prb-chip[data-sev='Warning']")
    assert "Warning" not in page.evaluate("JSON.parse(localStorage.getItem('uad-shell-v1')).problems.sev")
    rows = page.evaluate("[...document.querySelectorAll('#shell-panel-problems .prb-row')].map(r=>r.className)")
    assert rows and not [c for c in rows if "Warning" in c]
    page.click("#shell-panel-problems .prb-chip[data-sev='Warning']")
    # words narrow the list, and clearing them brings it back
    n0 = page.locator("#shell-panel-problems .prb-row").count()
    code = page.evaluate("document.querySelector('#shell-panel-problems .prb-row .prb-c').textContent.split(' ')[0]")
    page.fill("#shell-panel-problems .prb-q", code)
    page.wait_for_function(f"document.querySelectorAll('#shell-panel-problems .prb-row').length<={n0}")
    assert all(code in t for t in page.locator("#shell-panel-problems .prb-row .prb-c").all_inner_texts())
    page.fill("#shell-panel-problems .prb-q", "")

    # a click takes the report to the field (it flashes there)
    fid = page.evaluate("""()=>{const r=[...document.querySelectorAll('#shell-panel-problems .prb-row.go')]
        .find(r=>{const f=r.querySelector('.prb-c').textContent.split(' · ')[1];
                  return f&&document.getElementById('rf').contentDocument.querySelector('[data-fid="'+f+'"]');});
        if(!r) return ''; r.click(); return r.querySelector('.prb-c').textContent.split(' · ')[1];}""")
    assert fid, "no problem row whose field is on the page"
    until(page, "(f)=>!!document.querySelector('[data-fid=\"'+f+'\"].found')", fid, timeout=30)
    # F8 steps to the next problem
    page.keyboard.press("F8")
    page.wait_for_selector("#shell-panel-problems .prb-row.at")
    # "Show problems" outlines each field and says, with the H-1 id, what is wrong (T-507)
    page.check("#rf-marks")
    tip = until(page, "()=>{const x=document.querySelector('.mk-fatal[title],.mk-warn[title]'); return x&&x.title;}", timeout=30)
    assert tip.startswith(("Fatal ", "Warning ")) and ": " in tip, tip
    page.uncheck("#rf-marks")
    page.evaluate("localStorage.removeItem('uad-shell-v1')")
    page.evaluate("localStorage.removeItem('uad-marks')")
    assert not site.errors, site.errors
