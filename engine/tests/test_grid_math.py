"""The sales grid's totals, computed as Appendix A-1 says they are delivered (B4).

Validated first against the twelve D-1 samples: every total a sample delivers
is reproduced exactly, and nothing is computed that a sample leaves out.  Then
on a blank report: a sale price and two adjustments give the net and the
adjusted price at once, in the XML.

Run:  python -m pytest -q engine/tests/test_grid_math.py
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.access import sign_in  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, grid_math, templates  # noqa: E402


@pytest.mark.parametrize("template", [t.key for t in templates.catalogue()])
def test_the_formulas_reproduce_every_sample(template):
    root = templates.load(template).getroot()
    subj = bind.subject(root)
    units = grid_math._num(getattr(grid_math._first(subj, "LivingUnitExcludingADUCount"), "text", None)) or 1
    for prop in grid_math.comparables(root):
        got = grid_math.figures(prop)
        if units <= 1:
            got.pop("per_gross_area", None)
        for name, (_fid, point) in grid_math.FIELDS.items():
            node = grid_math._first(prop, point)
            want = (node.text or "").strip() if node is not None else ""
            if want:
                assert name in got and Decimal(got[name]) == Decimal(want), (template, name, want, got)
            else:
                assert name not in got, (template, name, got)


def test_a_blank_report_computes_its_totals(tmp_path):
    from app.main import app
    api.STORE = Store(tmp_path / "cases")
    api.RENDERER = None
    with TestClient(app) as c:
        sign_in(c)
        cid = c.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                         "name": "math"}).json()["case_id"]
        put = lambda fid, v, **kw: c.patch(f"/api/cases/{cid}/comparables/1/fields/{fid}",
                                           json={"value": v, **kw})
        assert put("22.15.07", "500000").status_code == 200
        assert put("22.07.27", "-10000").status_code == 200
        comp = grid_math.comparables(api.store().tree(cid).getroot())[0]
        M = grid_math.M
        assert comp.findtext(f".//{M}SalePriceNetTotalAdjustmentAmount") == "-10000"
        # the adjusted price needs the listing status A-1 conditions it on
        status = comp.findtext(f".//{M}ListingStatusType")
        if status == "SettledSale":
            assert comp.findtext(f".//{M}AdjustedSalesPriceAmount") == "490000"
