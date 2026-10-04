"""The rent schedule's comparables (casekit.rental_comps, CATALOG E-060).

A 2-4 unit report left every rental comparable column empty because nothing
in the kit wrote them.  These tests pin the mechanism offline:

* the records (RP<k>) are written before the grid that links to them;
* every grid key RC<u>.<k>_<FIELD> is an instance of TOTAL's own template key
  RCX_<FIELD> in the extracted model, and every RP key exists for comparable 1;
* the header label is the form TOTAL offers in its own pick list,
  "#k^<address>, <unit>";
* proximity is computed from coordinates to two decimals with a compass
  bearing -- never typed;
* each unit gets its own comparison from the case, not a copy of unit 1's.
"""
import re
from pathlib import Path

from bridge import casekit

BUILDS = Path(__file__).resolve().parents[2] / "knowledge" / "total" / "builds"


def _universe() -> set[str]:
    build = sorted(p for p in BUILDS.iterdir() if p.is_dir())[-1]
    keys = set()
    for name in ("datafields.json", "datamodel.json", "defaults.json", "fields.json"):
        p = build / name
        if p.exists():
            keys |= set(re.findall(r'"([A-Z][A-Z0-9_.\-]{2,})"', p.read_text(encoding="utf-8")))
    return keys


def _case():
    comp = dict(city="Brooklyn", state="NY", zip="11214", rent=3000, beds=3, full_baths=2,
                half_baths=0, gla=1000, floor=1, grade="Above Grade", condition="C3",
                project="None", market_area="Bath Beach", data_source="Data Aggregator",
                source="listing", note="")
    return {
        "subject": {"lat": 40.599669, "lon": -74.0042564},
        "units": [{"id": "1"}, {"id": "2"}],
        "rental": {
            "comps": [dict(comp, address="42 Bay 25th St", unit="1", lat=40.6034349, lon=-73.9986243),
                      dict(comp, address="65 Bay 23rd St", unit="", lat=40.6036298, lon=-74.0001188)],
            "comparison": {
                "1": [dict(overall="Inferior", adjusted_rent=3750, weight="Most"),
                      dict(overall="Similar", adjusted_rent=3450, weight="Less")],
                "2": [dict(overall="Superior", adjusted_rent=3100, weight="Less"),
                      dict(overall="Similar", adjusted_rent=3400, weight="Most")],
            },
        },
    }


def _writes(steps):
    return {(w["field"], w["instance"]): w["value"] for s in steps for w in s.writes}


def test_records_come_before_the_grid():
    steps = casekit.rental_comps(_case())
    # columns first (a new 2-4 report may hold ONE rental-property column), then the records
    assert steps[0].kind == casekit.STRUCT and "columns" in steps[0].title
    assert "records" in steps[1].title
    assert len(steps) == 2 + 2                      # columns + records + one grid per unit
    assert all(w["field"].startswith("RP") for w in steps[1].writes)


def test_every_key_is_an_instance_of_totals_template():
    known = _universe()
    unknown = set()
    for s in casekit.rental_comps(_case()):
        for w in s.writes:
            k = w["field"]
            probe = re.sub(r"^RC\d\.\d_", "RCX_", k)
            probe = re.sub(r"^RP\d_", "RP1_", probe)
            if probe not in known:
                unknown.add(k)
    assert unknown == set(), sorted(unknown)


def test_header_label_stores_the_left_half_and_links_by_its_digits():
    v = _writes(casekit.rental_comps(_case()))
    # stored value = the left half of "#k^<address>, <unit>"; the exporter
    # keeps its digits to link the column to comparable k
    assert v[("RC1.1_HEADER_LABEL", 0)] == "#1"
    assert v[("RC2.2_HEADER_LABEL", 0)] == "#2"
    from bridge import formkit
    offered = ["#1^42 Bay 25th St, 1", "#2^65 Bay 23rd St"]
    assert formkit.stored_value(offered, "#1") == "#1"
    assert "".join(ch for ch in v[("RC1.1_HEADER_LABEL", 0)] if ch.isdigit()) == "1"


def test_proximity_is_computed_not_typed():
    v = _writes(casekit.rental_comps(_case()))
    assert re.fullmatch(r"\d+\.\d\d", v[("RC1.1_PU_DISTANCE", 0)])
    assert v[("RC1.1_PU_DIRECTION", 0)] in {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}
    assert v[("RC1.1_PU_DISTANCE", 0)] == v[("RC2.1_PU_DISTANCE", 0)]   # same comp, same distance


def test_each_unit_gets_its_own_comparison():
    v = _writes(casekit.rental_comps(_case()))
    assert v[("RC1.1_SMRY_OVRL_COMP_TO_SUB", 0)] == "Inferior"
    assert v[("RC2.1_SMRY_OVRL_COMP_TO_SUB", 0)] == "Superior"
    assert v[("RC1.2_SMRY_COMP_WEIGHT", 0)] == "Less"
    assert v[("RC2.2_SMRY_COMP_WEIGHT", 0)] == "Most"


def test_no_comparables_means_no_steps():
    c = _case()
    c["rental"]["comps"] = []
    assert casekit.rental_comps(c) == []


def test_subject_unit_rent_row_carries_view_grade_and_storage():
    """Each subject unit's own rent-grid column: view, grade level, floor and
    vehicle storage come from facts the case already states (E-060)."""
    c = {
        "subject": {"occupancy": "Tenant", "view": "Residential",
                    "garage": {"type": "None", "spaces": 0}},
        "units": [
            {"id": "1", "levels": [{"level": "Level B1", "grade": "Below Grade", "finished": 0},
                                   {"level": "Level 1", "grade": "Above Grade", "finished": 780}],
             "rent": {"actual": 3650, "market": 3650}},
            {"id": "2", "levels": [{"level": "Level 2", "grade": "Above Grade", "finished": 780}],
             "rent": {"actual": 3400, "market": 3400}},
        ],
        "rental": {"commentary": "", "rent_control_commentary": ""},
    }
    v = _writes(casekit.rent_schedule(c))
    assert v[("RS1_GRADE_LEVEL", 0)] == "Above Grade"
    assert v[("RS1_FLOOR_NUM", 0)] == "1"            # the living level, not the basement
    assert v[("RS2_FLOOR_NUM", 0)] == "2"
    assert v[("RS2_UNIT_VIEW", 0)] == "Residential"
    assert v[("RS2_PU_VEHICLE_STORAGE", 0)] == "None"
    assert ("RS2_PU_VEHICLE_STORAGE_SPACES", 0) not in v   # no spaces to state


def test_bathroom_rows_use_the_bathroom_scale():
    """E-061: 'Partially Updated' is a kitchen word; on a bathroom row TOTAL
    exports it as an element the GSE schema does not define."""
    assert casekit.bath_update("Partially Updated") == "Moderately Updated"
    for ok in ("Fully Updated", "Significantly Updated", "Moderately Updated", "Not Updated"):
        assert casekit.bath_update(ok) == ok


def test_subject_wall_material_is_written_when_the_case_states_it():
    """E-062 (UAD-1080): the dwelling step left DE1_EXTEXTWALLS empty."""
    s = dict(style="Contemporary", year_built=1945, front_door_elevation="Ground Level",
             heat_system="Baseboard", heat_fuel="Natural Gas", cooling="Individual",
             effective_age=2, exterior_walls="Brick",
             exterior_walls_comment="Brick; rear ground floor stucco")
    v = _writes(casekit.dwelling({"subject": s, "units": [{"id": "1"}]}))
    assert v[("DE1_EXTEXTWALLS", 0)] == "Brick"
    assert v[("DE1_EXT_FEAT_QUALITY_COMMENT", 0)].startswith("Brick")
    s.pop("exterior_walls"); s.pop("exterior_walls_comment")
    v = _writes(casekit.dwelling({"subject": s, "units": [{"id": "1"}]}))
    assert ("DE1_EXTEXTWALLS", 0) not in v
