"""Report Setup for a 2-4 unit report: ONE building with n units (CATALOG E-053).

A new report is 1 building / 1 unit.  "+ Living Unit" in single-family mode
adds a second *Dwelling*, and the importer collapses units (Woodycrest), so the
units are made the way the panel makes them:

    Report Setup -> Multi-Family half of the toggle (Dwelling 1 with 2 units)
    -> copy icon on the last unit row until n units (same dwelling)
    -> dwelling / unit identifiers typed -> "Include Unit in Rent Schedule"
    -> Save

All through real input (bridge/ui.py), never by setting checkbox state from
script.  Verified afterwards from the data: UNIT_EXCL_ADU == n and n
`interior-k` sections.
"""
from __future__ import annotations

import time

from . import formkit, ui

TOGGLE = "#report-type-toggle"
UNIT_ROW_COPY = ".report-setup-multi-dwelling-unit-copy"
UNIT_ID = "input[placeholder=\"Unit # or Description\"]"
DWELLING_ID = "input[placeholder=\"Dwelling # or Description\"]"
RENTED = "input.report-setup-multi-dwelling-unit-rented-listener"
SAVE = ".report-setup-save"


def _visible(page, sel: str) -> int:
    # getClientRects, not offsetParent: the setup panel is position:fixed, and
    # offsetParent is null for everything inside it (8 rows were made for 4)
    return page.evaluate(f"[...document.querySelectorAll('{sel}')].filter(e => e.getClientRects().length > 0).length") or 0


def state(report) -> dict:
    v = formkit.values(report, ["UNIT_EXCL_ADU"])
    return {"units": int(v.get("UNIT_EXCL_ADU#0") or 0),
            "interiors": len([k for k in report.sections() if k.startswith("interior-")])}


def set_units(report, n: int, rented: list[bool] | None = None, ids: list[str] | None = None,
              dwelling_id: str = "1") -> dict:
    """Make the open report ONE dwelling with `n` units.  Idempotent: a report
    already at n units is left alone.  Returns the verified state."""
    if not 2 <= n <= 4:
        raise ValueError("a 2-4 unit report has 2 to 4 units")
    if state(report) == {"units": n, "interiors": n}:
        return state(report)
    p = report.page
    report.goto("report-setup", settle=2.0)
    if not p.evaluate(f"document.querySelector('{TOGGLE}').checked"):
        ui.click_part(p, "label.report-setup-type-toggle", 0.75, 0.5, settle=1.5)
        if not p.evaluate(f"document.querySelector('{TOGGLE}').checked"):
            raise RuntimeError("Multi-Family toggle did not switch")
    guard = 0
    while _visible(p, UNIT_ID) < n and guard < 6:
        guard += 1
        before = _visible(p, UNIT_ID)
        if before == 0:
            raise RuntimeError("no unit rows found in the setup panel")
        ui.click(p, UNIT_ROW_COPY, "", _visible(p, UNIT_ROW_COPY) - 1, settle=1.2)
        if _visible(p, UNIT_ID) <= before:
            raise RuntimeError("the copy icon added no unit row")
    if _visible(p, UNIT_ID) != n:
        raise RuntimeError(f"setup shows {_visible(p, UNIT_ID)} unit rows, wanted {n} -- Cancel and check the panel")
    ui.type_into(p, DWELLING_ID, dwelling_id, 0)
    ids = ids or [str(i + 1) for i in range(n)]
    rented = rented if rented is not None else [True] * n
    for i in range(n):
        ui.type_into(p, UNIT_ID, ids[i], i)
        boxes = p.evaluate(f"[...document.querySelectorAll('{RENTED}')].filter(e => e.getClientRects().length > 0).map(e => e.checked)")
        if boxes[i] != bool(rented[i]):
            ui.click(p, RENTED, "", i, settle=0.6)
    ui.click(p, SAVE, "Save", 0, settle=3.0)
    time.sleep(1.0)
    got = state(report)
    if got["units"] != n or got["interiors"] != n:
        raise RuntimeError(f"after Save: {got}, wanted {n} units / {n} interiors")
    return got
