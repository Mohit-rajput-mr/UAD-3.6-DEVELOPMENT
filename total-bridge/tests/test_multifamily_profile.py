"""The owner's multi-family adjustment rates (adjust.MULTI_FAMILY, CATALOG E-063)."""
from bridge import adjust, casekit
from bridge.adjust import MULTI_FAMILY as MF, Property, Unit


def _p(**kw):
    base = dict(gla=2454, site=2024, year=1945, beds=8, baths=6, basement_finished=False,
                garage=0, outdoor=True, design="Semi-Detached", cooling=True)
    return Property(**{**base, **kw})


def test_thresholds_gate_the_whole_difference():
    t = adjust.lines(_p(), _p(gla=2554, site=3024, year=1915), MF)    # exactly at each threshold
    assert t["UNITS_SF_GLA_ADJ"] == 0 and t["ST_SITSIZE_ADJ"] == 0 and t["YR_BLT_ADJ"] == 0
    t = adjust.lines(_p(), _p(gla=2560, site=3999, year=1910), MF)
    assert t["UNITS_SF_GLA_ADJ"] == -106 * 150
    assert t["ST_SITSIZE_ADJ"] == -1975 * 20
    assert t["YR_BLT_ADJ"] == 35 * 250


def test_rooms_garage_basement_outdoor_and_listing():
    t = adjust.lines(_p(), _p(beds=7, baths=4.5, garage=1, basement_finished=True, outdoor=False,
                             price=2_000_000, listing=True), MF)
    assert t["BEDS_ADJ"] == 20_000
    assert t["BATHS_ADJ"] == 30_000                    # one full + one half
    assert t["VEHICLE_STORAGE_ADJ"] == -20_000
    assert t["UNITS_SF_GLA_BELOW_GRD_ADJ"] == -40_000
    assert t["AMENITY_OUTDOOR_LIVING_ADJ"] == 20_000
    assert t["SP_TO_LP_RATIO_ADJ"] == -40_000


def test_design_and_cooling():
    t = adjust.lines(_p(), _p(design="Detached", cooling=False), MF)
    assert t["DWELL_DESIGN_ADJ"] == -20_000            # detached is superior to semi-detached
    assert t["DWELL_COOL_ADJ"] == 20_000
    t = adjust.lines(_p(), _p(design="Attached"), MF)
    assert t["DWELL_DESIGN_ADJ"] == 20_000
    t = adjust.lines(_p(), _p(design=""), MF)          # unknown design -> no adjustment
    assert t["DWELL_DESIGN_ADJ"] == 0


def test_18_north_is_unchanged():
    t = adjust.lines(_p(), _p(gla=2500, design="Detached", cooling=False))
    assert t["UNITS_SF_GLA_ADJ"] == -46 * 75           # no GLA threshold
    assert "DWELL_DESIGN_ADJ" not in t and "DWELL_COOL_ADJ" not in t


def test_unit_rows_use_the_buildings_gla_threshold():
    su = [Unit(780, 3, 2), Unit(780, 2, 2), Unit(894, 3, 2)]
    small = [Unit(700, 3, 2), Unit(850, 2, 2), Unit(904, 3, 2)]     # building -0 sf, units differ
    t = adjust.multi_lines(_p(), _p(), su, small, MF)
    assert all(t[f"UNITS_SF_GLA_ADJ#{i}"] == 0 for i in range(3))
    big = [Unit(1320, 3, 1), Unit(660, 2, 1), Unit(660, 2, 1)]
    t = adjust.multi_lines(_p(), _p(gla=2640), su, big, MF)
    assert sum(t[f"UNITS_SF_GLA_ADJ#{i}"] for i in range(3)) == -186 * 150
    assert sum(t[f"BATHS_ADJ#{i}"] for i in range(3)) == 60_000


def test_a_2_4_unit_case_takes_the_multi_family_profile():
    assert casekit.profile({"subject": {}, "units": [{"id": 1}, {"id": 2}]}).name == "multi-family"
    assert casekit.profile({"subject": {}, "units": [{"id": 1}]}).name == "18 North"
    assert casekit.profile({"subject": {}, "units": [{"id": 1}, {"id": 2}], "adjustment_profile": "18 North"}).name == "18 North"


def test_reconciliation_lists_only_the_adjustments_made():
    res = adjust.Result(table={1: {"UNITS_SF_GLA_ADJ#0": -1500, "BEDS_ADJ#0": 0, "DWELL_COOL_ADJ": 20_000}})
    line = casekit.rates_used(res, MF)
    assert line.startswith("GLA $150/sq ft") and "cooling system $20,000" in line
    assert "bedroom" not in line


def test_same_design_leaves_the_design_row_blank():
    """E-063: TOTAL faults "$0" on a design row whose characteristics match."""
    c = casekit.load(r"C:\UAD 3.6 DEVELOPMENT\_work\bathbeach\case.json")
    res = casekit.adjustments(c)
    for cp in c["comps"]:
        same = casekit.design_of(cp) == casekit.design_of(c["subject"])
        assert ("DWELL_DESIGN_ADJ" in res.table[cp["n"]]) == (not same)
        absent = casekit.comp_absent(c, cp)
        assert (f"GC{cp['n']}_DWELL_DESIGN_ADJ" in absent) == same


def test_final_reconciliation_comment_is_text_carrying_the_same_value():
    """REC_MARKET_VALUE exports as the reconciliation COMMENT (UAD-1266); it held
    only "$1,825,000".  It must be prose, and name the one concluded value."""
    c = {"reconciliation": {"cost_excluded": "Not Necessary for Credible Results",
                            "income_excluded": "Insufficient Data"}}
    t = casekit.final_comment(c, 1_825_000)
    assert "Sales Comparison Approach" in t and t.endswith("$1,825,000 for the subject property.")
    assert "Income Approach was not developed (insufficient data)" in t
    import re
    assert set(re.findall(r"\$[\d,]+", t)) == {"$1,825,000"}
