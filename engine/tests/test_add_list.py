"""The side panel's "Add to <section>" list (T-1056; WinTOTAL's per-section
"+ Add" buttons, done as one list of every place the report takes another
line).

The report frame names each Add control -- a row at the foot of a table, an
exhibit, a comparable, a room, the open certification line -- with the
section it sits in and the table it adds to, and goes to it on request: a
new row's first cell opens its list, as a click on it would.

Run:  python -m pytest -q engine/tests/test_add_list.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import templates
from uad.report import browser, flow

HOST = """<!doctype html><html><body>
<iframe id='rf' src='http://report.test/form?case=c1' style='width:900px;height:900px'></iframe>
<script>
window.ADDS=null;
addEventListener('message',function(e){ if(e.data&&e.data.uad==='adds') window.ADDS=e.data.items; });
</script></body></html>"""


@pytest.fixture(scope="module")
def edit_page():
    if not browser.AVAILABLE:
        pytest.skip(browser.MESSAGE)
    from lxml import etree
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    return flow.build(tree, screen=True, edit=True)


def test_each_add_is_named_by_its_table_and_opens_it(edit_page):
    from playwright.sync_api import sync_playwright

    def serve(route):
        url = route.request.url
        if url.startswith("http://report.test/form"):
            route.fulfill(status=200, content_type="text/html", body=edit_page)
        elif "/api/fields/" in url and "/options" in url:
            route.fulfill(status=200, content_type="application/json",
                          body='{"options":[{"value":"Residential","label":"Residential"}]}')
        elif url.startswith("http://report.test/"):
            route.fulfill(status=200, content_type="text/html", body=HOST)
        else:
            route.fulfill(status=404, body="")

    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            page = b.new_page()
            page.route("**/*", serve)
            page.goto("http://report.test/host")
            page.wait_for_function("window.ADDS!==null", timeout=30000)
            items = page.evaluate("window.ADDS")
            site = [x["label"] for x in items if x["secn"] == 4]
            assert site[:5] == ["Row: Site Influence",
                                "Row: Water Frontage with Private Access",
                                "Row: View and Impact to Value/Marketability",
                                "Row: Utilities and Impact to Value/Marketability",
                                "Row: Apparent Defects, Damages, Deficiencies (Site)"]
            assert site[5] == "Add Exhibit — Site Exhibits"
            assert all(x["label"] and x["label"] != "Row: table" for x in items)

            i = next(x["i"] for x in items if x["label"] == "Row: Site Influence")
            page.evaluate("i=>document.getElementById('rf').contentWindow.postMessage({uad:'add-go',i:i},'*')", i)
            frame = page.frame_locator("#rf")
            frame.locator(".picklist").wait_for(timeout=10000)   # the new row's list is open
            opened = page.frames[1].evaluate(
                "(()=>{var c=document.querySelector('.v.open');"
                "return !!(c&&c.closest('tr.newrow'))})()")
            assert opened
        finally:
            b.close()
