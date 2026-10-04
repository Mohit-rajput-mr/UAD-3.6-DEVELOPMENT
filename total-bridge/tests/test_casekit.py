"""The case kit, tested without TOTAL.

The worked example (_work/rockland/case.json) is a finished report: FV 0,
schema 0, UAD 0 on 2026-09-29.  These tests pin what can be checked offline:

* the plan builds from a case file;
* every field key the plan writes exists in TOTAL's own extracted model
  (knowledge/total/builds/<build>/) -- a mistyped key would otherwise be
  "missed" silently at run time;
* the adjustment engine reproduces the nets TOTAL itself computed on that
  report after the E-038 re-sum: -33,830 / +26,780 / +9,150 / -36,150;
* the formats and the "stored^shown" pick-list rule (E-049).

The live proof is `bridge case --json _work/rockland/case.json --dry-run` with
the report open: it lists every field where the plan and the report differ.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from bridge import adjust, casekit, formkit

ROOT = Path(__file__).resolve().parents[2]
# the anonymised worked example ships with the folder; the owner's original stays in _work
CASE = ROOT / "knowledge" / "cases" / "worked_example_sf" / "case.json"
BUILDS = ROOT / "knowledge" / "total" / "builds"


def _universe() -> set[str]:
    build = sorted(p for p in BUILDS.iterdir() if p.is_dir())[-1]
    keys: set[str] = set()
    for name in ("datafields.json", "datamodel.json", "defaults.json", "fields.json", "validation_profile.json"):
        p = build / name
        if p.exists():
            keys |= set(re.findall(r'"([A-Z][A-Z0-9_\-]{2,})"', p.read_text(encoding="utf-8")))
    return keys


@pytest.fixture(scope="module")
def case():
    if not CASE.exists():
        pytest.skip("worked example not present")
    return casekit.load(CASE)


def test_plan_builds(case):
    steps = casekit.plan(case, Path(case["photos_base"]))
    assert any(s.kind == casekit.PUT for s in steps)
    assert any("comparable columns" in s.title for s in steps)


def test_every_key_exists_in_totals_model(case):
    known = _universe()
    steps = casekit.plan(case, Path(case["photos_base"]))
    unknown = set()
    for s in steps:
        for w in s.writes:
            k = w["field"]
            # columns past the build's default three are created at run time
            probe = re.sub(r"^GC[4-9]_", "GC1_", k)
            if probe not in known and k not in known:
                unknown.add(k)
    # keys proven live on 2026-09-29 that the static model files do not list
    proven_live = {"SUPERVISOR_TYPE", "SRPA_TYPE", "ORD_SRPA_CONTACT_TYPE", "ORD_HIDDEN_SUPERVISOR_COUNT",
                   "ORD_HIDDEN_SRPA_COUNT", "HIDDEN_PROPERTY_ENCROACHMENT_COUNT",
                   "HIDDEN_PRIOR-SALES-REVISION_COUNT", "HIDDEN_GROSSRENTALINCOME_COUNT",
                   "SSDE1_HIDDEN_CA-DWELLING-DEPRECIATION-COST-SECTION_COUNT",
                   "HIDDEN_CA-DWELLING-DEPRECIATION-COST-SECTION_COUNT", "HIDDEN_CA-DEPRECIATED-COST-DWELLING_COUNT",
                   "HIDDEN_CA-OUTBUILDING-DEPRECIATION-COST-SECTION_COUNT", "HIDDEN_CA-OUTBUILDING-DEPRECIATION-COST_COUNT",
                   "CHECK_COST_APPROACH_DISABLE"}
    assert unknown - proven_live == set(), sorted(unknown - proven_live)


def test_adjustments_reproduce_totals_nets(case):
    res = casekit.adjustments(case)
    assert {n: res.net(n) for n in res.table} == {1: -33830, 2: 26780, 3: 9150, 4: -36150}
    assert res.table[4]["SP_TO_LP_RATIO_ADJ"] == -15000          # 2 % of the $750,000 list
    assert res.table[3]["ST_SITSIZE_ADJ"] == 0                   # 435 sq ft: under the threshold
    assert res.table[1]["YR_BLT_ADJ"] == 7750                    # 31 years x $250


def test_reconciliation_value(case):
    text, value, adjusted = casekit.reconciliation_text(case, casekit.adjustments(case))
    assert value == 665000
    assert adjusted == {1: 581170, 2: 701780, 3: 684150, 4: 713850}


def test_eighteen_north_rates_from_its_grid():
    """The profile's rates are what the 18 North grid itself implies."""
    s = adjust.Property(gla=1703, site=0.22 * 43560, year=1960, beds=4, baths=1.5,
                        basement_finished=True, garage=1, outdoor=True)
    c1 = adjust.Property(gla=1378, site=0.5 * 43560, year=1956, beds=3, baths=1.0,
                         basement_finished=False, garage=2, outdoor=True)
    t = adjust.lines(s, c1)
    assert t["UNITS_SF_GLA_ADJ"] == 24375
    assert t["BEDS_ADJ"] == 10000 and t["BATHS_ADJ"] == 5000
    assert t["UNITS_SF_GLA_BELOW_GRD_ADJ"] == 10000 and t["VEHICLE_STORAGE_ADJ"] == -10000
    assert t["YR_BLT_ADJ"] == 0                                   # 4 years: under the threshold
    assert abs(t["ST_SITSIZE_ADJ"] - (-121830)) < 200             # 18 North: -121,830


def test_formats():
    assert formkit.money(-5100) == "$(5,100)"
    assert formkit.money(7750) == "$7,750"
    assert formkit.money(0) == "$0"
    assert formkit.area(1000) == "1,000 Sq. Ft."
    assert formkit.mdy("2025-12-08") == "12/08/2025"


def test_pick_lists_store_the_left_half():
    hz = ["No Hazard Zone Noted^None", "FEMA Special Flood Hazard Area"]
    assert formkit.stored_value(hz, "None") == "No Hazard Zone Noted"
    assert formkit.stored_value(hz, "No Hazard Zone Noted") == "No Hazard Zone Noted"
    assert formkit.stored_value(["Yes", "None^No"], "No") == "None"
    assert formkit.stored_value(["Yes", "None^No"], "Maybe") is None


def test_pending_comparable_carries_no_sale(case):
    rows = {w["field"]: w["value"] for w in casekit.comp_rows(case, case["comps"][3])}
    assert rows["GC4_LP_STATUS"] == "Pending"
    # no sale price, date or terms is written; they are cleared to null (E-048, E-055)
    assert not any(rows.get(f"GC4_{k}") for k in ("PR_SALEPR1", "DT_SALTIM1", "TRANSFER_TERMS"))
    gone = casekit.comp_absent(case, case["comps"][3])
    assert {"GC4_PR_SALEPR1", "GC4_DT_SALTIM1", "GC4_TRANSFER_TERMS", "GC4_SALE_PRICE"} <= set(gone)
    assert rows["GC4_PU_VEHICLE_STORAGE_DETAILS"] == "Concrete"        # driveway surface (E-048)
    assert rows["GC4_SITE_HAZARD_ZONE"] == "No Hazard Zone Noted"      # E-049


def test_rowhouse_is_ranked_as_attached():
    # 601 Euclid: subject "Rowhouse / Townhouse" vs semi-detached comparables
    assert casekit.design_of({"structure_design": "Rowhouse / Townhouse", "attachment": "Attached"}) == "Attached"
    assert casekit.design_of({"structure_design": "Semi-Detached", "attachment": "Attached"}) == "Semi-Detached"


def test_comments_accept_only_commentary_fields():
    import pytest
    assert casekit.comments({"comments": {"ASSIGNMENT_COMMENTARY": "x"}})[0].writes[0]["field"] == "ASSIGNMENT_COMMENTARY"
    with pytest.raises(ValueError):
        casekit.comments({"comments": {"REC_OPINION_MKT_VAL": "$1"}})
