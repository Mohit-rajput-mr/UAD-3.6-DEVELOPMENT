"""The comparables editing view (DR §12, T-1084): the labels and the subject
stay put while the comparables scroll sideways, and rows nobody has answered
can be folded away while editing.

Run:  python -m pytest -q engine/tests/test_comps_view.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_kit import needs_browser, open_case, site  # noqa: E402,F401

pytestmark = needs_browser


def test_subject_stays_beside_the_labels_and_empty_rows_fold(site):
    page = site.page
    page.evaluate("localStorage.removeItem('uad-comp-hide')")
    cid = open_case(site, "sf1_appraisal_v1_4")
    for _ in range(3):                                 # enough columns to scroll
        assert page.request.post(f"{site.base}/api/cases/{cid}/comparables", data={"kind": "sales"}).ok
    page.click("#tabs >> text=Comparables")
    page.wait_for_selector("table.comps td.subj", timeout=60_000)
    before = page.evaluate("document.querySelector('table.comps td.subj').getBoundingClientRect().left")
    lbl = page.evaluate("document.querySelector('table.comps td.lbl').getBoundingClientRect().right")
    page.evaluate("document.querySelector('.gridwrap').scrollLeft=600")
    page.wait_for_function("document.querySelector('.gridwrap').scrollLeft>0")
    after = page.evaluate("document.querySelector('table.comps td.subj').getBoundingClientRect().left")
    assert abs(after - before) < 2 and abs(after - lbl) < 3, (before, after, lbl)
    # the new comparables are empty: rows only they lack are still shown (the
    # sample's comps answer them); a row nobody answered folds away
    rows = page.locator("table.comps tbody tr").count()
    empty = page.locator("table.comps tbody tr.unanswered").count()
    assert 0 < empty < rows
    page.check(".comp-hide input")
    page.wait_for_function("getComputedStyle(document.querySelector('table.comps tr.unanswered')).display==='none'")
    page.uncheck(".comp-hide input")
    page.evaluate("localStorage.removeItem('uad-comp-hide')")
    assert not site.errors, site.errors
