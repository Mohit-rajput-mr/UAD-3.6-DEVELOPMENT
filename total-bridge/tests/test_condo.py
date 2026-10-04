"""Condominium steps of the case kit (CATALOG E-066, E-067)."""
import json
from pathlib import Path

from bridge import casekit

CASE = Path(__file__).resolve().parents[2] / "_work" / "w57" / "case.json"


def _case():
    return json.loads(CASE.read_text(encoding="utf-8"))


def _writes(steps):
    return {(w["field"], w["instance"]): w["value"] for s in steps for w in s.writes}


def test_subject_is_a_condominium_unit_with_common_site():
    v = _writes(casekit.subject_site(_case()))
    assert v[("CONDO_YES", 0)] == "X" and v[("CONDO_NO", 0)] == ""
    assert v[("PUD_NO", 0)] == "X" and v[("COOP_NO", 0)] == "X"
    assert v[("SITOWNEDCOMMON_YES", 0)] == "X" and v[("HORESPMAINT_NO", 0)] == "X"
    assert v[("SUBPROJNAME", 0)] == "Metropolitan Tower Condominium"
    assert v[("SUBUNITNO", 0)] == "44C"


def test_high_rise_floor_corner_and_floors_in_building():
    c = _case()
    d = _writes(casekit.dwelling(c))
    assert d[("DE1_STRUCTURE_DESIGN_TYPE", 0)] == "High-rise" and d[("DE1_FLOORS", 0)] == "67"
    i = _writes(casekit.interior(c))
    assert i[("UI1_FLOOR_NUMBER", 0)] == "44" and i[("UI1_CORNER_UNIT", 0)] == "Yes"


def test_project_information_is_written_from_the_case():
    v = _writes(casekit.project_info(_case()))
    assert v[("PRJ_CONDO_YES", 0)] == "X"
    assert v[("PI_TOTAL_UNITS", 0)] == "241"
    assert v[("PI_MONTHLY_AMOUNT", 0)] == "$2,055"
    assert v[("PU_UNITS_RENTED_ESTIMATED", 0)] == "Yes"     # estimate is flagged, with its reason
    assert v[("PI_REASONS_UNITS_RENTED", 0)].startswith("No condominium questionnaire")
    assert v[("PU_UNIT_TRANSFER_FEES_DETAIL", 0)] == "None"      # stored half of None^No (E-049)
    assert casekit.project_info({"subject": {}}) == []


def test_contract_never_touches_a_no_box_and_is_one_click_step():
    """E-067: a change event on SC_CONTRACT_NO resets the whole contract."""
    c = _case()
    fields = dict(casekit.contract_fields(c["contract"]))
    assert not any(f.endswith("_NO") or f == "CHECK_SC_DISABLE" for f in fields)
    assert fields["SC_CONTRACT_SALES_PRICE"] == "$1,380,000"
    assert "SC_CONTRACT_DATE" not in fields            # blank in the contract: never written
    steps = casekit.sales_contract(c)
    assert len(steps) == 1 and steps[0].kind == casekit.STRUCT and not steps[0].writes


def test_condo_comparable_carries_project_floor_and_fee():
    c = _case()
    rows = {w["field"]: w["value"] for w in casekit.comp_rows(c, c["comps"][0])}
    assert rows["GC1_PROJ_NAME"] == "Metropolitan Tower Condominium"
    assert rows["GC1_PU_SAME_PROJECT_AS_SUBJECT"] == "X"
    assert rows["GC1_FLOOR_NUM"] == "39" and rows["GC1_PROJ_MONTHLY_FEE"] == "$1,794"
    rows3 = {w["field"]: w["value"] for w in casekit.comp_rows(c, c["comps"][2])}
    assert "GC3_PU_SAME_PROJECT_AS_SUBJECT" not in rows3        # "" is not written
