"""Adjustment worksheets (DR §11; replaces SmartAdjust, owner 2026-10-10).

The arithmetic is the owner's own, ported from the WinTOTAL mod
(total-bridge/bridge/worksheet.py and adjust.py): (subject - comparable) x
rate, 0 at or under the threshold, rounded half up to the step. The 18 North
cases below are the ones the mod's adjust.py documents, read out of the
delivered 18 North grid.

Run:  python -m pytest -q engine/tests/test_worksheet.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import schema, templates, worksheet  # noqa: E402
from uad.report import comparables  # noqa: E402

N = worksheet.EIGHTEEN_NORTH


def amount(key, diff, rate=None, threshold=None, rounding=1, building=None):
    kind = worksheet.KINDS[key]
    p = worksheet.Params.of(kind, N, {"rate": rate, "threshold": threshold, "rounding": rounding})
    return worksheet.line_amount(kind, diff, p, building)[0]


def test_the_18_north_derivations():
    assert amount("gla", 325) == 24_375                   # $75 / sq ft
    assert amount("gla", 99) == 0                         # under the 100 sq ft threshold (owner 2026-10-07)
    assert amount("site", -12_197) == -121_970            # $10 / sq ft past 1,000
    assert amount("site", 871) == 0
    assert amount("age", 33) == 8_250                     # $250 / year past 5 years
    assert amount("age", 5) == 0
    assert amount("beds", 1) == 10_000
    assert amount("baths", 0.5) == 5_000                  # a half bath is half the full-bath rate
    assert amount("garage", -1) == -10_000
    assert amount("gla", 0) is None                       # nothing to write


def test_rounding_is_half_up_like_the_worksheet():
    assert amount("gla", -258, rounding=100) == -19_300   # -19,350 -> -193.5 steps -> -193
    assert amount("gla", 258, rounding=100) == 19_400
    assert worksheet._round(-0.5, 1) == 0 and worksheet._round(0.5, 1) == 1


def test_a_2_to_4_unit_report_gates_on_the_building():
    # each unit is 60 sq ft apart, the building 120: past the 100 sq ft threshold
    assert amount("gla", 60, rate=150, threshold=100, building=120) == 9_000
    assert amount("gla", 60, rate=150, threshold=100, building=80) == 0


def test_cells_are_read_as_the_grid_prints_them():
    k = worksheet.KINDS
    assert worksheet._parse(k["site"], "0.25 Acres") == 0.25 * 43_560
    assert worksheet._parse(k["baths"], "2 | 1") == 2.5
    assert worksheet._parse(k["garage"], "Garage | 2 | Attached\nDriveway | 4 | Asphalt") == 2
    assert worksheet._parse(k["garage"], "Carport | 2 | Attached") == 0
    assert worksheet._parse(k["outdoor"], "None") == 0 and worksheet._parse(k["outdoor"], "Deck") == 1
    assert worksheet._parse(k["design"], "Semi-Detached") == 1


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_adjust_all_keeps_every_sample_valid_and_reads_back(key):
    tree = etree.parse(str(templates.get(key).path))
    before = len(schema.validate(tree))
    out = worksheet.adjust_all(tree, worksheet.default_profile(tree))
    assert len(schema.validate(tree)) == before == 0
    # what was written is what the worksheet now reads as "in the grid"
    for a in out["applied"]:
        sheet = worksheet.sheet(tree, a["key"])
        for c in sheet["comparables"]:
            for ln in c["lines"]:
                if ln["amount"] is not None:
                    assert int(float(ln["current"] or 0)) == ln["amount"], (a["key"], c["number"], ln)


def test_per_unit_lines_are_positional_as_the_samples_keep_them():
    tree = etree.parse(str(templates.get("2_to_4_unit_appraisal_v1_4").path))
    worksheet.apply(tree, "beds", {"rate": 15_000}, overrides={"1_2": -1_234})
    root = tree.getroot()
    comp1 = comparables.properties(root, "SalesComparable")[0]
    assert worksheet._amounts(comp1, "LivingUnitBedroomCount")[1] == "-1234"
    assert len(schema.validate(tree)) == 0


def test_the_api_writes_all_comparables_and_never_a_signed_report():
    from fastapi.testclient import TestClient

    from app import api
    from app.access import sign_in
    from app.cases import Store
    from app.main import app
    api.STORE = Store(Path(tempfile.mkdtemp()) / "cases")
    api.RENDERER = None
    api.LAYOUTS = None
    with TestClient(app) as c:
        sign_in(c)
        cid = c.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False,
                                         "name": "ws"}).json()["case_id"]
        kinds = [k["key"] for k in c.get(f"/api/cases/{cid}/worksheets").json()["kinds"]]
        assert {"gla", "site", "age", "beds", "baths", "exposure"} <= set(kinds)
        r = c.post(f"/api/cases/{cid}/worksheets/gla", json={"rate": 80, "threshold": 0, "rounding": 1})
        assert r.status_code == 200 and r.json()["written"] == 3
        now = c.get(f"/api/cases/{cid}/worksheets/gla").json()
        assert [c_["lines"][0]["current"] for c_ in now["comparables"]] == ["-20640", "15840", "14880"]
        assert c.get(f"/api/cases/{cid}/worksheets/nope").status_code == 422
        for state in ("in_review", "signed"):
            api.store().transition(cid, state, "t", force=True)
        assert c.post(f"/api/cases/{cid}/worksheets/gla", json={"rate": 1}).status_code == 409
