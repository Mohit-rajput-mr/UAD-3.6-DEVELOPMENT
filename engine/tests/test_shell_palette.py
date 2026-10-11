"""The command palette (DR phase 2 S5, T-277): Ctrl+K lists every command and
section, filters as you type, Enter runs, Esc closes.

Run:  python -m pytest -q engine/tests/test_shell_palette.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_kit import needs_browser, open_case, site  # noqa: E402,F401

pytestmark = needs_browser


def test_ctrl_k_finds_and_runs_a_command_and_goes_to_a_section(site):
    page = site.page
    page.evaluate("localStorage.removeItem('uad-shell-v1')")
    open_case(site, "sf1_appraisal_v1_4")
    page.keyboard.press("Control+k")
    page.wait_for_selector("#palette input")
    assert page.locator("#palette .pal-row").count() > 20
    # Esc closes it
    page.keyboard.press("Escape")
    page.wait_for_selector("#palette", state="detached")
    # a section, by its name
    page.keyboard.press("Control+k")
    page.fill("#palette input", "go to site")
    assert page.inner_text("#palette .pal-row.on .pal-l") == "Go to Site"
    page.keyboard.press("Enter")
    page.wait_for_function("S.section===4")
    # a report-bar button, adopted: Enter does what its click does
    page.keyboard.press("Control+k")
    page.fill("#palette input", "sketch")
    assert page.inner_text("#palette .pal-row.on .pal-l") == "Open the Sketch"
    page.keyboard.press("Enter")
    page.wait_for_selector("#sketch-ov iframe", timeout=30_000)
    page.evaluate("document.getElementById('sketch-ov').remove()")
    page.evaluate("localStorage.removeItem('uad-shell-v1')")
    assert not site.errors, site.errors
