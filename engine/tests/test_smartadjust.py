"""SmartAdjust (T-1059): suggestions from the owner's rate profiles.

The 18 North rates were read out of the delivered 18 North grid; the cases
that derivation rests on (uad/smartadjust.py docstring) are reproduced here on
a grid built for them, and every official sample takes every suggestion and
stays schema-valid.

Run:  python -m pytest -q engine/tests/test_smartadjust.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi import HTTPException
from lxml import etree
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import schema, smartadjust, templates
from uad.report import comparables


@dataclass
class _Cell:
    text: str = ""
    adjustment: str = ""


@dataclass
class _Row:
    label: str
    adjust_type: str
    subject: str
    cells: list = field(default_factory=list)
    adjustable: bool = True


@dataclass
class _Grid:
    comparables: list
    rows: list


def _grid(rows):
    """[(label, adjust_type, subject, comp)] -> a one-comparable grid."""
    return _Grid(["Comparable #1"], [_Row(l, t, s, [_Cell(c)]) for l, t, s, c in rows])


def _amounts(monkeypatch, rows, profile=smartadjust.EIGHTEEN_NORTH):
    monkeypatch.setattr(smartadjust, "_rows", lambda tree: _grid(rows))
    (col,) = smartadjust.suggest(None, profile)
    return {ln.adjust_type: ln.amount for ln in col.lines}


@pytest.mark.parametrize("rows,want", [
    # 325 sq ft -> +24,375 (the 18 North grid)
    ([("Finished Area Above Grade", "LivingUnitStandardFinishedAreaAboveGrade", "1,825 Sq. Ft.", "1,500 Sq. Ft.")],
     {"LivingUnitStandardFinishedAreaAboveGrade": 24_375}),
    # an 871 sq ft site difference was left unadjusted; 12,197 was not
    ([("Site Size", "SiteSize", "10,871 Sq. Ft.", "10,000 Sq. Ft.")], {"SiteSize": 0}),
    ([("Site Size", "SiteSize", "10,000 Sq. Ft.", "22,197 Sq. Ft.")], {"SiteSize": -121_970}),
    ([("Site Size", "SiteSize", "1 Acres", "33,560 Sq. Ft.")], {"SiteSize": 100_000}),
    # 33 years -> +8,250; 4-5 years -> 0
    ([("Year Built", "YearBuilt", "1990", "1957")], {"YearBuilt": 8_250}),
    ([("Year Built", "YearBuilt", "1990", "1985")], {"YearBuilt": 0}),
    # 4 vs 3 bedrooms -> +10,000; 1.5 vs 1.0 baths -> +5,000
    ([("Bedrooms", "LivingUnitBedroomCount", "4", "3")], {"LivingUnitBedroomCount": 10_000}),
    ([("Baths", "LivingUnitBathroomCount", "1 | 1", "1 | 0")], {"LivingUnitBathroomCount": 5_000}),
    # a finished basement, both ways
    ([("Finished Area Below Grade", "LivingUnitStandardFinishedAreaBelowGrade", "0 Sq. Ft.", "600 Sq. Ft.")],
     {"LivingUnitStandardFinishedAreaBelowGrade": -10_000}),
    # outdoor living: none vs porch -> +10,000 the other way round
    ([("Outdoor Living", "OutdoorLivingAmenity", "", "Porch")], {"OutdoorLivingAmenity": -10_000}),
    ([("Outdoor Living", "OutdoorLivingAmenity", "Deck", "Patio")], {"OutdoorLivingAmenity": 0}),
])
def test_the_18_north_derivation(monkeypatch, rows, want):
    assert _amounts(monkeypatch, rows) == want


def test_garage_spaces_and_market_exposure(monkeypatch):
    rows = [("Vehicle Storage", "VehicleStorage", "", ""),
            ("Type| Spaces | Detail", "", "Garage | 1 | Attached", "Garage | 2 | Attached\nDriveway | 4 | Pavers"),
            ("Listing Status", "", "", "Active"),
            ("List Price", "", "", "$500,000"),
            ("Sale Price", "", "", ""),
            ("Sale to List Price Ratio", "SaleToListPriceRatio", "", "")]
    got = _amounts(monkeypatch, rows)
    assert got == {"VehicleStorage": -10_000, "SaleToListPriceRatio": -10_000}


def test_the_multi_family_profile_gates_on_its_thresholds(monkeypatch):
    mf = smartadjust.MULTI_FAMILY
    rows = [("Finished Area Above Grade", "LivingUnitStandardFinishedAreaAboveGrade", "900 Sq. Ft.", "820 Sq. Ft."),
            ("Year Built", "YearBuilt", "1990", "1965"),
            ("Attached/Detached", "AttachedOrDetached", "Detached", "Semi-Detached"),
            ("Cooling", "CoolingSystem", "Centralized", "None")]
    got = _amounts(monkeypatch, rows, mf)
    assert got == {"LivingUnitStandardFinishedAreaAboveGrade": 0,      # 80 sq ft <= 100
                   "YearBuilt": 0,                                     # 25 years <= 30
                   "AttachedOrDetached": 20_000, "CoolingSystem": 20_000}


def test_a_row_the_grid_lacks_is_never_suggested(monkeypatch):
    rows = [("Year Built", "", "1990", "1950")]                       # no adjustment row
    assert _amounts(monkeypatch, rows) == {}


def test_rates_are_overridden_per_report():
    p = smartadjust.profile_for(etree.parse(str(templates.get("sf1_appraisal_v1_4").path)),
                                "", {"gla": "100", "bogus": 1, "site": "x"})
    assert p.name == "18 North" and p.gla == 100 and p.site == 10
    mf = smartadjust.profile_for(etree.parse(str(templates.get("2_to_4_unit_appraisal_v1_4").path)))
    assert mf.name == "Multi-family"


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_every_sample_takes_every_suggestion(key, tmp_path, monkeypatch):
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    cid = store.create(template=key, blank=False).case_id
    out = api.smartadjust_suggest(cid, profile="", rates="")
    allowed = {r.adjust_type for r in comparables.rows("sales") if r.adjust_type and r.adjust_fid}
    picks = [{"comparable": c["number"], "adjust_type": ln["adjust_type"], "amount": ln["amount"]}
             for c in out["comparables"] for ln in c["lines"]]
    assert {p["adjust_type"] for p in picks} <= allowed
    api.smartadjust_apply(cid, Request({"type": "http", "headers": []}), {"picks": picks})
    assert schema.validate(store.tree(cid)) == []
    again = api.smartadjust_suggest(cid, profile="", rates="")
    for c in again["comparables"]:
        for ln in c["lines"]:
            # what was accepted is what the grid now holds
            assert ln["current"].replace("$", "").replace(",", "").replace("(", "-").rstrip(")") in (
                str(ln["amount"]), ""), (c["number"], ln)
    store.conn.close()


def test_apply_refuses_what_is_not_a_suggestion(tmp_path, monkeypatch):
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    cid = store.create(template="sf1_appraisal_v1_4", blank=False).case_id
    req = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as e:
        api.smartadjust_apply(cid, req, {"picks": [{"comparable": 1, "adjust_type": "Nonsense", "amount": 1}]})
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        api.smartadjust_apply(cid, req, {"picks": [{"comparable": 9, "adjust_type": "SiteSize", "amount": 1}]})
    assert e.value.status_code == 422          # a 404 would send the editor home
    store.conn.close()
