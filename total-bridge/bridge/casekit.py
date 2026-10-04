"""Fill a single-family UAD 3.6 URAR in TOTAL from one case file.

    python -m bridge.cli case  --json case.json            # fill, then certify
    python -m bridge.cli case  --json case.json --dry-run  # compare only, writes nothing

`case.json` is written by the agent after reading the case folder (see
knowledge/PLAYBOOK.md and total-bridge/case_template.json).  Every value in it
has a source; this module decides nothing about the property.  What it owns is
**how** a value gets into TOTAL so that it stays there, exports, and passes all
three gates -- field keys, order of operations, formats, and the structural
moves, each one learned on a real report and recorded in
knowledge/errors/CATALOG.md:

    order   guard -> parties -> AMC block -> subject / site -> dwelling
            -> levels + rooms (rows first) -> garage / amenity -> market
            -> listing -> comparable columns -> grid -> adjustments
            -> reconciliation -> gates (cost / income / revision / supervisor)
            -> photos (after rooms: categories need them) -> map -> certify
    formats money "$(5,100)", area "1,000 Sq. Ft.", dates mm/dd/yyyy (UAD-1643)
    picks   "stored^shown" -> write the stored half (E-049)
    rows    comparable columns, exhibit rows, levels, rooms, AMC (E-046)
    gates   exposure days need their checkbox; an unlisted subject needs its
            empty listing row removed; a pending comparable carries no sale
            price, terms or sale date (E-048, E-050)
    nets    re-show rows with values, re-sum through TOTAL (E-038)
    certify every section rendered, neutral section, FV -> schema x2 -> UAD (E-051)

Dry-run reads the open report and lists, per field, where it differs from the
plan -- used to prove this module against a finished report.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import adjust, certify, exhibits, formkit, locmap, reconcile, rtv
from .formkit import area, money

# ---------------------------------------------------------------- the plan
PUT, STRUCT = "put", "struct"


@dataclass
class Step:
    kind: str
    title: str
    writes: list = field(default_factory=list)
    action: object = None            # callable(report) for STRUCT steps


def w(key, value, instance=0):
    return {"field": key, "instance": instance, "value": "" if value is None else str(value)}


def _yn(b):
    return "Yes" if b else "No"


def _money_or_blank(v):
    return "" if v in (None, "") else money(v)


#: The grid rates a kitchen and a bathroom on DIFFERENT update scales.  Kitchen:
#: Fully / Partially / Not Updated.  Bathroom: Fully / Significantly /
#: Moderately / Not Updated.  A kitchen word on a bathroom row is accepted by the
#: form, but TOTAL exports it as OverallBathroomsUpdateStatusType=Other plus an
#: ...OtherDescription element the GSE schema does not define -- one schema
#: error per comparable unit (12 on a 4-comparable 3-family).  CATALOG E-061.
#: "Partially" sits in the middle of the bathroom scale: Moderately Updated, the
#: value the official 2-4 unit sample uses.
BATH_SCALE = {"Partially Updated": "Moderately Updated"}


def bath_update(value):
    return BATH_SCALE.get(value, value)


def load(path: str | Path) -> dict:
    case = json.loads(Path(path).read_text(encoding="utf-8"))
    ap = case.get("appraiser")
    if isinstance(ap, str):                       # a path to a profile
        p = Path(ap)
        if not p.is_absolute():
            p = Path(path).resolve().parent / p
        if not p.exists():
            p = Path(__file__).resolve().parents[2] / ap
        case["appraiser"] = json.loads(p.read_text(encoding="utf-8"))
    return case


# ---------------------------------------------------------------- sections
def parties(c) -> list[Step]:
    o, ap, s = c["order"], c["appraiser"], c["subject"]
    lender = o["lender"]
    steps = [Step(PUT, "assignment and parties", [
        w("ASSIGN_REASON", o["reason"]),
        w("ASSIGN_BORROWER", o["borrower"]["full"]),
        w("BORROWER_FIRST_NAME", o["borrower"]["first"]), w("BORROWER_LAST_NAME", o["borrower"]["last"]),
        w("SUBCUROWNER", o["owner"]["full"]),
        # an owner with no first name is a legal entity (LLC, trust): the
        # entity name goes in FULL_NAME and the individual's name parts stay empty
        *([w("SUBCUROWNER_TYPE", "Legal Entity"), w("SUBCUROWNER_FULL_NAME", o["owner"]["full"])]
          if not o["owner"].get("first") else
          [w("SUBCUROWNER_FIRST_NAME", o["owner"]["first"]), w("SUBCUROWNER_LAST_NAME", o["owner"]["last"])]),
        w("CONTACT_FULL_NAME", lender["name"], 0),
        w("CONTACT_ADDRESS", lender["address"], 0), w("CONTACT_ADDR", lender["address"], 0),
        w("CONTACT_CITY", lender["city"], 0), w("CONTACT_STATE", lender["state"], 0),
        w("CONTACT_ZIP", lender["zip"], 0),
        w("CONTACT_APPRAISER_REFERENCE_ID", o["order_number"]),
        w("APPRAISER_SPI_EXTERIOR", o.get("inspection", "Physical")),
        w("APPRAISER_SPI_INTERIOR", o.get("inspection_interior", o.get("inspection", "Physical"))),
        w("APPRAISER_SPI_DATE", o["inspection_date"]),
        w("APPRAISER_EMPLOYEEMENT_TYPE", ap.get("employment", "Independent Fee Appraiser")),
        w("APPRAISER_NAME", ap["name"]), w("APPRAISER_FIRST_NAME", ap["first"]),
        w("APPRAISER_LAST_NAME", ap["last"]),
        w("APPRAISER_COMPANY_NAME", ap["company"]),
        w("APPRAISER_COMPANY_ADDR", ap["address"]), w("APPRAISER_ADDRESS", ap["address"]),
        w("APPRAISER_CITY", ap["city"]), w("APPRAISER_STATE", ap["state"]), w("APPRAISER_ZIP", ap["zip"]),
        w("APPRAISER_LEVEL", ap["level"]),
        w("APPRAISER_DESIGNATION", ap.get("designation", "")),
        w("ORD_APPRAISER_DESIGNATION", ap.get("designation", "")),
        w("APPRAISER_CRED_ID", ap["credential_id"]), w("APPRAISER_CRED_STATE", ap["credential_state"]),
        w("APPRAISER_CRED_EXPIRES", ap["credential_expires"]),
        w("ORD_APPRAISER_CRED_ID", ap["credential_id"]), w("ORD_APPRAISER_CRED_STATE", ap["credential_state"]),
        w("ORD_APPRAISER_CRED_EXPIRES", ap["credential_expires"]),
    ])]
    amc = o.get("amc")
    if amc:
        def add_amc(r):
            # "+ AMC" creates contact block #1 (party role ManagementCompany)
            if formkit.count(r, "CONTACT_FULL_NAME") < 2:
                formkit.add_rows(r, "assignment", "+ AMC", "CONTACT_FULL_NAME", 2, settle=2.0)
        steps.append(Step(STRUCT, "AMC contact block (+ AMC)", action=add_amc))
        steps.append(Step(PUT, "AMC", [
            w("CONTACT_FULL_NAME", amc["name"], 1), w("CONTACT_AMC_REFERENCE_ID", amc.get("order", ""), 1),
            w("CONTACT_ADDRESS", amc["address"], 1), w("CONTACT_ADDR", amc["address"], 1),
            w("CONTACT_CITY", amc["city"], 1), w("CONTACT_STATE", amc["state"], 1),
            w("CONTACT_ZIP", amc["zip"], 1),
            w("CONTACT_CRED_ID", amc.get("licence", ""), 1), w("CONTACT_CRED_STATE", amc.get("licence_state", ""), 1),
            w("CONTACT_CRED_EXP", amc.get("licence_expires", ""), 1),
        ]))
    return steps


def subject_site(c) -> list[Step]:
    s = c["subject"]
    st = s["street"]
    writes = [
        w("SUBCOUNTY", s["county"]), w("ATTACHMENT_TYPE", s.get("attachment", "Detached")),
        w("SPECIAL_TAX_ASSESSMENTS", _yn(s.get("special_assessments", False))),
        w("NEWCONST_NO", "" if s.get("new_construction") else "X"),
        w("HORESPMAINT_NO", "" if s.get("hoa") else "X"),
        w("SUBLEGALDESCRIP", s["legal"]), w("PROPRIGHTSAPPR", s.get("estate", "Fee Simple")),
        w("SITSITEAREA", area(s["site_sqft"])), w("PARCEL_SIZE", area(s["site_sqft"])),
        w("APN", s["apn"]), w("PU_APN_DESC", s.get("apn_desc", "Land with Dwelling")),
        w("PARCELSCONTIGUOUS", "Yes"),
        w("SIT_PRIMACCESS", st.get("primary_access", "Public Street")),
        w("SIT_TYPICAL_MKT", "Yes"),
        w("SIT_STREET_TYPE_SURFACE", f"Public / {st['surface']}"),
        w("PU_STREET_TYPE", st["type"]), w("PU_SURFACE_TYPE", st["surface"]),
        w("SIT_CLASSCODE", s["zoning_code"]), w("SIT_CLASSCODE_DESC", s["zoning_desc"]),
        w("SIT_COMPLIANCE", s.get("zoning_compliance", "Legal")),
        w("SIT_INFL_INFL", s.get("influence", "Residential")),
        w("ALIAS_SIT_INFL_PROX", s.get("influence_proximity", "Bordering")),
        w("SIT_INFL_IMP", s.get("influence_impact", "Neutral")),
        w("SIT_INFL_WTR_FRNTG_FEAT", "None"),
        w("SIT_VWIMP_VIEW", s["view"]), w("SIT_VWIMP_RNGVW", s.get("view_range", "Full")),
        w("SIT_VWIMP_IMP", s.get("view_impact", "Neutral")),
        # E-049: the stored half of "No Hazard Zone Noted^None"
        w("SIT_FEAT_HZRD_ZONE_DTL", s.get("hazard_zone_stored", "No Hazard Zone Noted")),
        w("SIT_FEAT_HZRD_ZONE_IMP", "Neutral"),
        w("PU_SITE_FEAT_SITCHAR", "None"), w("SIT_FEAT_SITCHAR_IMP", "Neutral"),
        w("SIT_FEAT_SITCHAR_DTL", "None observed at inspection"),
        w("SIT_FEATURE_COMMENTARY", s["site_features_commentary"]),
        w("SIT_UTLIMP_BRDBD_AVAIL", s.get("broadband", "Yes")),
        w("EXT_SIT_UTIL", s["utilities_text"]),
        w("SIT_VALUATION_METHOD", s.get("site_method", "Allocation")),
        w("SIT_VALUE_OPINION", money(s["site_value"])),
    ]
    for u in s.get("utilities_public", []):
        writes.append(w(f"SIT_UTLIMP_{u}_PUBLIC", "X"))
    r = s.get("restriction")
    if r:
        writes += [w("SIT_FEAT_RSTRCTN", "Property Restriction"), w("SIT_FEAT_RSTRCTN_DTL", r["detail"]),
                   w("SIT_FEAT_RSTRCTN_IMP", r.get("impact", "Neutral"))]
    pj = c.get("project")
    if pj:
        # a unit in a project (CATALOG E-066): the type checkboxes are Yes/No
        # pairs; the condominium -- not the owner -- keeps up the exterior
        kind = pj.get("legal_structure", "Condominium")
        for key, name in (("PUD", "PUD"), ("CONDO", "Condominium"), ("COOP", "Cooperative"), ("CONDOP", "Condop")):
            yes = kind == name
            writes += [w(f"{key}_YES", "X" if yes else ""), w(f"{key}_NO", "" if yes else "X")]
        common = s.get("site_owned_in_common", True)
        writes += [w("SITOWNEDCOMMON_YES", "X" if common else ""), w("SITOWNEDCOMMON_NO", "" if common else "X"),
                   w("HORESPMAINT_YES", ""), w("HORESPMAINT_NO", "X"),
                   w("SUBPROJNAME", pj["name"]), w("SUBUNITNO", s.get("unit", ""))]
    if s.get("special_assessments") and s.get("special_assessments_desc"):
        writes.append(w("SPECIAL_TAX_ASSESSMENTS_DESC", s["special_assessments_desc"]))
    steps = [Step(PUT, "subject and site", writes)]
    if not s.get("encroachment"):
        # an encroachment row nobody observed must not exist (UAD-1291/1292)
        steps.append(Step(PUT, "no encroachment row", [
            w("HIDDEN_PROPERTY_ENCROACHMENT_COUNT", "0"), w("SIT_FEAT_ENCROACH", ""),
            w("SIT_FEAT_ENCROACH_DTL", ""), w("SIT_FEAT_ENCROACH_IMP", "")]))
    return steps


def units(c) -> list[dict]:
    """The subject's living units, each merged over the subject's own answers.

    A 2-4 unit case lists them in ``c["units"]`` (unit n -> section
    ``interior-n``, fields ``UI<n>_``); the report must already hold that many
    unit interiors in ONE building (Report Setup -> Multi-Family, CATALOG
    E-053).  A one-unit case is the subject itself."""
    s = c["subject"]
    return [{**s, **u} for u in c["units"]] if c.get("units") else [s]


def dwelling(c) -> list[Step]:
    s = c["subject"]
    return [Step(PUT, "dwelling exterior", [
        w("DE1_STYLE", s["style"]), w("DE1_PJIYRBUILT", s["year_built"]),
        w("DE1_PUIYRBUILT", s["year_built"]), w("DE1_PUIYRBUILT_ESTIMATED", "No"),
        w("DE1_CONST_METHOD", s.get("construction", "Site Built")),
        w("DE1_FRONT_DOOR_ELEV", s["front_door_elevation"]),
        w("DE1_HEAT_SYSTEM", s["heat_system"]), w("DE1_HEAT_DETAIL", s["heat_fuel"]),
        w("DE1_COOL_SYSTEM", s["cooling"]),
        w("DE1_HEAT_BELOW_GRADE_YES", "X" if s.get("heated_below_grade") else ""),
        w("DE1_HEAT_BELOW_GRADE_NO", "" if s.get("heated_below_grade") else "X"),   # one of the pair, always
        *([w("DE1_STRUCTURE_DESIGN_TYPE", s["structure_design"])] if s.get("structure_design") else []),
        # a Rowhouse / Townhouse design asks three more questions (FV, 601 Euclid)
        *([w("DE1_TOWNHOUSE_END_UNIT", _yn(s.get("townhouse", {}).get("end_unit", False))),
           w("DE1_TOWNHOUSE_BACK2BACK", _yn(s.get("townhouse", {}).get("back_to_back", False))),
           w("DE1_UNITS_ABOVE_OR_BELOW", _yn(s.get("townhouse", {}).get("units_above_below", False)))]
          if s.get("structure_design") == "Rowhouse / Townhouse" else []),
        # floors in the building are asked only of a mid- or high-rise (E-066)
        *([w("DE1_FLOORS", s["floors_in_building"])] if s.get("floors_in_building") else []),
        *([w("DE1_UNITS_ABOVE_OR_BELOW", "Yes")]
          if s.get("structure_design") in ("High-rise", "Mid-rise", "Low-rise") else []),
        w("DE1_UNIT_NUMS", str(len(units(c)))),   # "Units in Structure" (8.001), UAD-1085/1086/1693
        # STRUCTURE_COMPONENT_DETAIL is mandatory in the XSD; TOTAL emits it
        # only when the wall component carries a condition
        w("DE1_EXT_FEAT_COND_STATUS", s.get("exterior_condition_status", "Typical Wear and Tear")),
        # UAD-1080: the wall material is required whenever the homeowner keeps
        # up the exterior (every dwelling but a condo unit) -- E-062
        *([w("DE1_EXTEXTWALLS", s["exterior_walls"])] if s.get("exterior_walls") else []),
        *([w("DE1_EXT_FEAT_QUALITY_COMMENT", s["exterior_walls_comment"])]
          if s.get("exterior_walls_comment") else []),
        w("DE1_EFFECTIVE_AGE_PRECISE_ENABLE", "X"), w("DE1_EFFECTIVE_AGE_PRECISE", s["effective_age"]),
        w("DE1_EFFECTIVE_AGE", s["effective_age"]),
        w("SKT_MEASURE_STD", s.get("measurement_standard", "ANSI")),  # UAD-1677
    ])]


def interior(c) -> list[Step]:
    s = c["subject"]
    steps = []
    multi = len(units(c)) > 1
    for n, u in enumerate(units(c), 1):
        p, sec = f"UI{n}_", f"interior-{n}"
        # E-058: TOTAL's below-grade-access rule reads LEVEL_GRADE_TYPE of row 0
        # only; a below-grade level in row 0 makes the access required on every
        # level.  Above-grade levels go first (stable order otherwise).
        levels = sorted(u["levels"], key=lambda lv: lv["grade"] != "Above Grade")
        rooms = u["rooms"]

        def rows(r, p=p, sec=sec, nl=len(levels), nr=len(rooms)):
            formkit.add_rows(r, sec, "+ Add Level", p + "LEVEL_IN_UNIT", nl)
            formkit.add_rows(r, sec, "+ Add Room", p + "ROOM_ROOM_TYPE", nr, settle=0.9)

        writes = [
            w(p + "OCCUPANCY", u["occupancy"]), w(p + "AREA_DATA_SOURCE_TYPE", u.get("area_source", "Physical Measurement")),
            w(p + "QC_INT_QUAL_RATING", u["quality"]), w(p + "QC_INT_COND_RATING", u["condition"]),
            w(p + "INTFEAT_DETAIL_FLOORING", u["flooring"]),
            w(p + "INTFEAT_QUAL_STATUS_FLOORING", u.get("flooring_status", "Typical Wear and Tear")),
            w(p + "OVERALL_UPD_STATUS_BATHS", bath_update(u["baths_update"])),
            w(p + "OVERALL_UPD_STATUS_FLOORING", u.get("flooring_update", "Not Updated")),
            w(p + "ACCESSFEAT_FEATURE", "None"),
            w(p + "PU_INTFEAT_DETAIL_WALLS_CEILING_STYLE_TYPE", u["walls_ceiling"]["style"]),
            w(p + "PU_INTFEAT_DETAIL_WALLS_CEILING_HEIGHT", u["walls_ceiling"]["height"]),
            w(p + "INTFEAT_QUAL_STATUS_WALLS_CEILING", u["walls_ceiling"]["status"]),
            w(p + "PU_INTFEAT_QUAL_STATUS_WALLS_CEILING", u["walls_ceiling"]["status"]),
        ]
        # an "other" interior feature (e.g. in-unit laundry): it also becomes an
        # exhibit category -- interior exhibits always need one (E-059)
        for i, f in enumerate(u.get("other_features", [])[:1]):
            writes += [w(p + "INTFEAT_FEATURE", f["feature"], i), w(p + "INTFEAT_DETAIL", f["detail"], i),
                       w(p + "INTFEAT_QUAL_STATUS", f.get("status", "Typical Wear and Tear"), i)]
        if c.get("project"):             # site owned in common: these two are required (E-069)
            writes += [w(p + "NON_RES_USE", _yn(u.get("non_residential_use", False))),
                       w(p + "LIVE_WORK_SPACE", _yn(u.get("live_work_space", False)))]
        if u.get("floor_number"):        # floor + corner: asked of a low/mid/high-rise unit (E-066)
            writes += [w(p + "FLOOR_NUMBER", u["floor_number"]),
                       w(p + "CORNER_UNIT", _yn(u.get("corner_unit", False)))]
        if multi:                       # asked of each unit of a 2-4 unit report
            writes += [w(p + "UTILS_SEP_METERED", _yn(u.get("utilities_separately_metered", True))),
                       w(p + "UTILS_OPERATING", _yn(u.get("utilities_operating", True)))]
        below = [i for i, lv in enumerate(levels) if lv["grade"] != "Above Grade"]
        if below:
            writes.append(w(p + "BELOW_GRADE_CMP_ABOVE", u.get("below_grade_vs_above", "Similar")))
        for i, lv in enumerate(levels):
            writes += [w(p + "LEVEL_IN_UNIT", lv["level"], i), w(p + "LEVEL_GRADE_TYPE", lv["grade"], i),
                       w(p + "LEVEL_FINISHED_AREA", area(lv["finished"]), i),
                       w(p + "LEVEL_UNFINISHED_AREA", lv.get("unfinished", 0), i)]
            if lv["grade"] != "Above Grade":
                writes += [w(p + "LEVEL_BELOW_GRADE_ACCESS", lv.get("access", u.get("below_grade_access", "Interior and Exterior Access")), i),
                           w(p + "LEVEL_BELOW_GRADE_EXTERIOR_ACCESS", lv.get("exterior_access", u.get("below_grade_exterior_access", "Walk Out")), i)]
        for i, (lvl, typ) in enumerate(rooms):
            writes += [w(p + "ROOM_LEVEL", lvl, i), w(p + "ROOM_ROOM_TYPE", typ, i)]
            key = {"Kitchen": "kitchen", "Bath - Full": "bath", "Bath - Half": "half_bath"}.get(typ)
            if key and u.get(key):                                   # UAD-1145/1146/1147
                k = u[key]
                writes += [w(p + "ROOM_CONDITION_STATUS", k["condition"], i),
                           w(p + "ROOM_UPDATE_STATUS", k["update"], i),
                           w(p + "ROOM_TIME_FRAME", k.get("timeframe", ""), i)]
        steps += [Step(STRUCT, f"unit {n}: levels and rooms (+ Add Level / + Add Room)", action=rows),
                  Step(PUT, f"unit {n} interior", writes)]
    steps.append(Step(PUT, "overall quality and condition", [
        w("OQC_OVERALL_QUAL", s["quality"]), w("OQC_OVERALL_COND", s["condition"]),
        w("REC_OF_OVERRAL_QC", s["overall_qc_commentary"])]))
    return steps


def rent_schedule(c) -> list[Step]:
    """A 2-4 unit report's rent schedule: each subject unit's lease and the
    opinion of market rent (section rental-information; instance = unit - 1)."""
    if not c.get("units"):
        return []
    writes = []
    for i, u in enumerate(c["units"]):
        n, rent = i + 1, u["rent"]
        actual = rent.get("actual")
        writes += [
            w("RENT_SCH_CURRENTLY_RENTED", _yn(actual is not None), i),
            w("RENT_SCH_OCCUPANCY", u.get("occupancy", c["subject"]["occupancy"]), i),
            w("RENT_SCH_MONTHLY_RENT", _money_or_blank(actual), i),
            w("RENT_SCH_MONTH_TO_MONTH", rent.get("month_to_month", ""), i),
            w("RENT_SCH_LEASE_START", rent.get("lease_start", ""), i),
            w("RENT_SCH_RENT_CONTROL", _yn(rent.get("rent_control", False)), i),
            w("RENT_SCH_RENT_CONC", _yn(rent.get("concessions", False)), i),
            w("RENT_SCH_UTILS_INCLUDED", _yn(rent.get("utilities_included", False)), i),
            w("RENT_SCH_FURNISHED", _yn(rent.get("furnished", False)), i),
            w("RI_ACT_INC_MONTHLY_RENT", _money_or_blank(actual), i),
            w("RI_OPN_INC_MONTHLY_RENT", money(rent["market"]), i),
            w(f"RS{n}_SMRY_ACT_RENT", _money_or_blank(actual)),
            w(f"RS{n}_SMRY_OPN_MKT_RENT", money(rent["market"])),
        ]
        # The subject unit's own column in the rental grid.  Nothing wrote it, so
        # every unit left view, grade level and vehicle storage empty (CATALOG
        # E-060).  Each is a fact the case already states: the unit's living
        # level (the first level with finished area above grade), the subject's
        # view, and the subject's car storage through its popup.
        living = next((lv for lv in u.get("levels", [])
                       if lv.get("grade") == "Above Grade" and lv.get("finished")), None)
        if living:
            writes += [w(f"RS{n}_GRADE_LEVEL", "Above Grade"),
                       w(f"RS{n}_FLOOR_NUM", re.sub(r"\D", "", living["level"]))]
        s = c["subject"]
        if s.get("view"):
            writes.append(w(f"RS{n}_UNIT_VIEW", s["view"]))
        g = s.get("garage") or {}
        if g.get("type"):
            writes.append(w(f"RS{n}_PU_VEHICLE_STORAGE", g["type"]))
            if g.get("spaces"):
                writes.append(w(f"RS{n}_PU_VEHICLE_STORAGE_SPACES", g["spaces"]))
    ri = c.get("rental", {})
    writes += [w("RENTAL_ANALYSIS_COMMENTARY", ri.get("commentary", "")),
               w("RENT_IMPACT_TO_VALUE", ri.get("rent_control_commentary", ""))]
    return [Step(PUT, "rent schedule (subject units)", writes)]


def rental_comps(c) -> list[Step]:
    """The rent schedule's comparables: the records (RP<k>) and, for every
    subject unit, the comparison grid against each of them (RC<u>.<k>).

    ``rent_schedule`` writes each subject unit's own lease; nothing wrote the
    comparables, so a 2-4 unit report kept every rental comparable column empty
    -- 28 required cells per column, units x comps columns (286 findings on the
    3-family at 1965 20th Dr).  CATALOG E-060.

    The same comparables serve every unit (TOTAL's grid links each column to a
    record through its header label, "#k^<address>, <unit>"); what differs per
    unit is the comparison -- overall, adjusted rent, weight and the
    Superior/Similar/Inferior rows -- which the case states in
    ``rental.comparison[<unit>][k-1]``.  Proximity is computed from the
    coordinates, never typed: the rule is geocode it, two decimals.
    """
    rc = (c.get("rental") or {}).get("comps") or []
    if not rc or not c.get("units"):
        return []
    from .locmap import miles_and_bearing
    s = c["subject"]
    here = (float(s["lat"]), float(s["lon"]))
    records = []
    for k, cp in enumerate(rc, 1):
        records += [
            w(f"RP{k}_AD_ADDR1", cp["address"]), w(f"RP{k}_DB_UNITNO", cp.get("unit", "")),
            w(f"RP{k}_DB_CITY", cp["city"]), w(f"RP{k}_DB_STATE", cp["state"]),
            w(f"RP{k}_DB_ZIP", cp["zip"]), w(f"RP{k}_ACTUAL_RENT", money(cp["rent"])),
            w(f"RP{k}_PU_DATA_SOURCE", cp["data_source"]),
            w(f"RP{k}_SC_SOURCE1", cp["source"]),
            w(f"RP{k}_RENTAL_COMP_QUICKNOTE", cp.get("note", "")),
        ]
    def columns(r, n=len(rc)):
        # a new 2-4 report may hold ONE rental-property column (601 Euclid):
        # RP2/RP3 do not exist until TOTAL's own AddComp makes them
        formkit.add_comparables(r, n, grid="rentalprop")
    steps = [Step(STRUCT, f"rental property columns -> {len(rc)} (CompManagers.AddComp)", action=columns),
             Step(PUT, f"rental comparables: {len(rc)} records", records)]
    comparison = (c.get("rental") or {}).get("comparison") or {}
    for u, unit in enumerate(c["units"], 1):
        rows = comparison.get(str(unit.get("id", u))) or comparison.get(str(u)) or []
        writes = []
        for k, cp in enumerate(rc, 1):
            col = f"RC{u}.{k}_"
            dist, bearing = miles_and_bearing(here, (float(cp["lat"]), float(cp["lon"])))
            cmpk = rows[k - 1] if k - 1 < len(rows) else {}
            # The pick list offers "#k^<address>, <unit>" and, like every
            # "display^value" list, stores the LEFT half (formkit.stored_value).
            # TOTAL's exporter keeps only the digits of the stored label to link
            # the column to comparable k: the whole token reads as 142251 and
            # links nothing, so every comparable's unit exported empty (21 H-1
            # findings, CATALOG E-060).
            writes += [
                w(col + "HEADER_LABEL", f"#{k}"),
                w(col + "PU_DISTANCE", f"{dist:.2f}"), w(col + "PU_MILES", "X"),
                w(col + "PU_DIRECTION", bearing),
                w(col + "MARKETAREA", cp.get("market_area", "")),
                w(col + "PROJ_NAME", cp.get("project", "None")),
                w(col + "FLOOR_NUM", cp.get("floor", "")),
                w(col + "GRADE_LEVEL", cp.get("grade", "Above Grade")),
                w(col + "INT_COND_CONDITION", cp.get("condition", "")),
                w(col + "BEDS", cp["beds"]),
                w(col + "PU_FULL_BATHS", cp["full_baths"]),
                w(col + "PU_HALF_BATHS", cp.get("half_baths", 0)),
                w(col + "SF_GLA", cp["gla"]),
                w(col + "FURNISHED", _yn(cp.get("furnished", False))),
                w(col + "SITE_OWNED_IN_COMMON", _yn(cp.get("site_owned_in_common", False))),
                w(col + "UTILS_INCLUDED", _yn(cp.get("utilities_included", False))),
                w(col + "RENT_CONTROL", _yn(cp.get("rent_control", False))),
                w(col + "RENT_CONC", _yn(cp.get("concessions", False))),
                w(col + "SITE_INFLUENCE_COMP", cmpk.get("site", "Similar")),
                w(col + "UNIT_VIEW_COMP", cmpk.get("view", "Similar")),
                w(col + "PROJ_AMENITIES_COMP", cmpk.get("amenities", "Similar")),
                w(col + "VEHICLE_STORAGE_COMP", cmpk.get("vehicle", "Similar")),
                w(col + "SMRY_ACT_RENT", money(cp["rent"])),
                w(col + "SMRY_OVRL_COMP_TO_SUB", cmpk.get("overall", "")),
                w(col + "SMRY_ADJ_RENT", money(cmpk["adjusted_rent"]) if cmpk.get("adjusted_rent") else ""),
                w(col + "SMRY_COMP_WEIGHT", cmpk.get("weight", "")),
            ]
        steps.append(Step(PUT, f"unit {u}: rental comparison grid ({len(rc)} columns)", writes))
    return steps


def _pair(key, b):
    """A Yes/No checkbox pair: one ticked, the other cleared."""
    return [w(f"{key}_YES", "X" if b else ""), w(f"{key}_NO", "" if b else "X")]


def project_info(c) -> list[Step]:
    """Project Information for a unit in a condominium (CATALOG E-066).
    Counts no source states are left empty and listed on the handback."""
    pj = c.get("project")
    if not pj:
        return []
    kind = pj.get("legal_structure", "Condominium")
    flag = {"Condominium": "PRJ_CONDO_YES", "Cooperative": "PRJ_COOP_YES",
            "Condop": "PRJ_CONDOP_YES", "PUD": "PRJ_PUD_YES"}[kind]
    writes = [w(flag, "X"), w("PI_PROJ_NAME", pj["name"]), w("PI_DATA_SOURCE", pj.get("data_source", "Data Aggregator")),
              w("PI_TOTAL_UNITS", pj["total_units"]), w("PI_UNITS_SOLD", pj.get("units_sold", "")),
              w("PI_UNITS_FOR_SALE", pj.get("units_for_sale", "")),
              w("PI_MONTHLY_AMOUNT", money(pj["monthly_fee"])), w("PU_MONTHLY_AMOUNT", money(pj["monthly_fee"])),
              w("PI_AMENITIES_SERVICES_INCLUDED", ", ".join(pj.get("amenities", []))),
              w("PU_AMENITIES_SERVICES_INCLUDED", "|".join(pj.get("amenities", []))),
              w("PI_UTILS_INCLUDED", ", ".join(pj.get("utilities_included", ["None"]))),
              *_pair("PI_DEFICIENCY_OBSVERVED", pj.get("deficiency", False)),
              *_pair("PI_UNITS_COMPLETE", pj.get("complete", True)),
              *_pair("PI_SUBJ_PROP_COMPLETE", pj.get("complete", True)),
              *_pair("PI_CONVERT_PAST_3YRS", pj.get("converted_3yrs", False)),
              *_pair("PI_GROUND_RENT", pj.get("ground_rent", False)),
              w("PI_DEVELOPER_IN_CONTROL_DETAIL", _yn(pj.get("developer_control", False))),
              w("PU_COMMERCIAL_SPACE_DETAIL", _yn(pj.get("commercial_space", False))),
              w("PI_KWN_LEGAL_ACTIONS_DETAIL", "Yes" if pj.get("legal_actions") else "None"),
              w("PI_PROJECT_INFO_COMMENTARY", pj.get("commentary", ""))]
    if pj.get("units_rented") is not None:
        est = pj.get("units_rented_estimated", False)
        writes += [w("PI_UNITS_RENTED", pj["units_rented"]), w("PU_UNITS_RENTED", pj["units_rented"]),
                   w("PU_UNITS_RENTED_ESTIMATED", _yn(est))]
        if est:
            writes.append(w("PI_REASONS_UNITS_RENTED", pj["units_rented_reason"]))
    # the monthly charge is known (UAD-1572/1573)
    writes.append(w("PU_ASSOCIATION_CHARGE_TYPE_AD", "Yes"))
    sa = pj.get("special_assessment")
    if sa:
        writes += [w("PU_UNIT_SPECIAL_ASSESSMENTS_DETAIL", sa["detail"]),
                   w("PU_UNIT_SPECIAL_ASSESSMENTS_AMNT", money(sa["amount"])),
                   w("PI_UNIT_SPECIAL_ASSESSMENTS_DETAIL", money(sa["amount"])),
                   w("PI_UNIT_SPECIAL_ASSESSMENTS_IMPACT", pj.get("special_assessment_impact", "Neutral")),
                   w("PI_UNIT_SPECIAL_ASSESSMENTS_COMMENT", pj.get("special_assessment_comment", ""))]
    # UAD-1609: the most units one entity owns (a condominium)
    if pj.get("single_entity_units") is not None:
        writes += [w("PI_SINGLE_OWN_UNITS_DETAIL", pj["single_entity_units"]),
                   w("PI_SINGLE_OWN_UNITS_IMPACT", pj.get("single_entity_impact", "Neutral")),
                   w("PI_SINGLE_OWN_UNITS_COMMENT", pj.get("single_entity_comment", ""))]
    # UAD-1594/1595: commercial space and its share
    if pj.get("commercial_space"):
        writes += [w("PU_COMMERCIAL_SPACE_PERCENTAGE", pj.get("commercial_pct", "")),
                   w("PI_COMMERCIAL_SPACE_DETAIL", f"{pj.get('commercial_pct', '')}%"),
                   w("PI_COMMERCIAL_SPACE_IMPACT", pj.get("commercial_impact", "Neutral")),
                   w("PI_COMMERCIAL_SPACE_COMMENT", pj.get("commercial_comment", ""))]
    # UAD-1579 transfer fee; tax abatement; project line of credit -- stored
    # halves of "None^No" (E-049)
    tf, tx = pj.get("transfer_fee"), pj.get("tax_abatement")
    # no fee: TOTAL's own calc puts "None" in BOTH the amount and the detail,
    # and its rule needs both filled (bundle 9850 / 5486, E-069)
    writes += [w("PU_UNIT_TRANSFER_FEES_DETAIL", "Yes" if tf else "None"),
               w("PU_UNIT_TRANSFER_FEES_AMNT", money(tf) if tf else "$0"),     # "None" is cleared (numeric)
               w("PI_UNIT_TRANSFER_FEES_DETAIL", money(tf) if tf else "None"),
               w("PU_UNIT_TAX_DETAIL", "Yes" if tx else "None"),
               w("PI_UNIT_TAX_DETAIL", money(tx) if tx else "$0"),
               w("PI_LINE_LIEN_CREDIT", _yn(pj.get("line_of_credit", False)))]
    return [Step(PUT, f"project information ({kind})", writes)]


def contract_fields(k: dict) -> list[tuple[str, str]]:
    """The contract as (field, value) in the order a person fills it.  Only
    "_YES" boxes are ever ticked: any change event on SC_CONTRACT_NO makes TOTAL
    hide the section and reset the contract (E-067)."""
    out = [("CHECK_SC_ENABLE", "X"), ("SC_CONTRACT_YES", "X")]
    if k.get("analyzed", True):
        out.append(("SC_ANALYZED_YES", "X"))
    if k.get("arms_length", True):
        out.append(("SC_ARMS_LENGTH_YES", "X"))
    out.append(("SC_CONTRACT_SALES_PRICE", money(k["price"])))
    if k.get("date"):
        out.append(("SC_CONTRACT_DATE", k["date"]))
    out += [("SC_TRANSFER_TERMS", k.get("terms", "Typically Motivated")),
            ("SC_PERSONAL_PROPERTY_INC_INCLUDE_INDICATOR", _yn(k.get("personal_property", False))),
            ("SC_KWN_CONCESSIONS", _yn(k.get("concessions", False)))]
    if k.get("concessions"):
        out += [("SC_TOTAL_CONCESSIONS", money(k["concession_amount"])),
                ("SC_CONCESSIONS_TYPICAL", _yn(k.get("concessions_typical", True)))]
    out.append(("SC_ANALYSIS", k["analysis"]))
    return out


def alive(report, timeout: float = 15.0) -> bool:
    """Does the page still answer?  A frozen page is never written to again."""
    try:
        return report.page.evaluate("1+1") == 2
    except Exception:
        return False


def sales_contract(c) -> list[Step]:
    """A purchase: the contract the appraiser analysed (section sales-contract).

    E-067: committing these fields through the data layer froze TOTAL three
    times.  Each control is set on the rendered page, the way a person would,
    one at a time; after each the page must still answer, or the step stops."""
    k = c.get("contract")
    if not k:
        return []

    def fill(r, fields=contract_fields(k)):
        r.goto("sales-contract", settle=2.0)
        have = formkit.values(r, [f for f, _ in fields])
        for f, v in fields:
            if have.get(f + "#0") == v:
                continue
            res = r.set(f, v) if f.startswith(("CHECK_", "SC_CONTRACT_YES", "SC_ANALYZED", "SC_ARMS")) \
                or f in ("SC_CONTRACT_SALES_PRICE", "SC_CONTRACT_DATE", "SC_ANALYSIS") else r.pick(f, v)
            if not alive(r):
                raise RuntimeError(f"TOTAL stopped answering after {f} -- stop, do not retry (E-067)")
            print(f"      {f} <- {v!r}: {res}")
    return [Step(STRUCT, "sales contract (one control at a time, E-067)", action=fill)]


def storage_amenity(c) -> list[Step]:
    s = c["subject"]
    g = s["garage"]
    amen = s.get("amenities") or ([s["amenity"]] if s.get("amenity") else [])
    steps = [Step(PUT, "vehicle storage", [
        w("VS_PU_CAR_STORAGE_TYPE", g["type"]), w("VS_CAR_STORAGE", g["spaces"]),
        w("VS_NUM_PARK_SPACES", g["spaces"]), w("VS_STORAGE_DETAIL", g["text"]),
        w("VS_PU_STORAGE_NUMBER_SPACES_NUM", g["spaces"]), w("VS_PU_STORAGE_TYPE_DETAIL", g.get("detail", "")),
        w("VS_PU_STORAGE_SPACE_SQUARE_FEET", g.get("sqft", "")),
    ])]
    if not amen:
        def off(r):
            r.goto("amenities", settle=1.5)
            if formkit.values(r, ["CHECK_SUB_PROP_AMENITY_DISABLE"]).get("CHECK_SUB_PROP_AMENITY_DISABLE#0") != "X":
                r.set("CHECK_SUB_PROP_AMENITY_DISABLE", "X")
        steps.append(Step(STRUCT, "no amenities: section off (click)", action=off))
    if len(amen) > 1:
        def rows(r, n=len(amen)):
            formkit.add_rows(r, "amenities", "+ Add Amenity", "PU_SPA_AMENITY_CATEGORY", n)
        steps.append(Step(STRUCT, f"amenity rows -> {len(amen)}", action=rows))
    for i, a in enumerate(amen):
        # the category first: the type list is only offered once it is set
        steps += [Step(PUT, f"amenity {i + 1} category", [w("PU_SPA_AMENITY_CATEGORY", a["category"], i)]),
                  Step(PUT, f"amenity {i + 1} {a['type']}", [
                      w("SPA_AMENITY_CATEGORY", a["category"], i), w("PU_SPA_AMENITY_TYPE", a["type"], i),
                      w("SPA_AMENITY", a["type"], i), w("PU_SPA_AMENITY_DETAIL_AREA", a.get("sqft", ""), i),
                      w("PU_SPA_AMENITY_TOTALNUM", a.get("count", 1), i),
                      w("SPA_AMENITY_MATERIAL", a["material"], i), w("PU_SPA_AMENITY_MATERIAL", a["material"], i)])]
    return steps


def market_listing_history(c) -> list[Step]:
    m, s = c["market"], c["subject"]
    steps = [Step(PUT, "market", [
        w("HBU_LEGAL", "Yes"), w("HBU_PHY_POSSIBLE", "Yes"), w("HBU_FIN_FEASIBL", "Yes"),
        w("HBU_MAX_PROD", "Yes"), w("HBU_YES", "X"),
        w("MKT_PAST_SALES_MONTHS", m["sales_12_months"]), w("MKT_DEMAND_SUPPLY", m["demand_supply"]),
        w("MKT_MARKETING_TIME", m["marketing_time"]), w("MKT_DISTRESSED_MKT_COMP", "No"),
        w("MKT_PRICE_TREND_SOURCE", m["source_short"]), w("MKT_SEARCH_CRT_DESC", m["search"]),
        w("MKT_LOWEST_SALE_PRICE", money(m["low"])), w("MKT_MEDIAN_SALE_PRICE", money(m["median"])),
        w("MKT_HIGHEST_SALE_PRICE", money(m["high"])),
        w("MKT_LOWEST_LIST_PRICE", money(m.get("list_low", m["low"]))),
        w("MKT_MEDIAN_LIST_PRICE", money(m.get("list_median", m["median"]))),
        w("MKT_HIGHEST_LIST_PRICE", money(m.get("list_high", m["high"]))),
        w("MKT_PRICE_TREND_COMMENTARY", m["trend_commentary"]), w("MKT_BOUNDARY", m["boundary"]),
        w("MKT_ACTVE_LISTINGS", m["active_listings"]), w("MKT_PENDING_SALES", m["pending_sales"]),
        w("MKT_MEDIAN_DAYS_ON_MKT", m["median_dom"]),
    ])]
    if s.get("listed_within_year"):
        steps.append(Step(PUT, "subject listing (listed)", [w("SLI_LISTINGS", "Yes")]
                          + [w(k, v) for k, v in s.get("listing_fields", {}).items()]))
    else:
        # UAD-1204/1208: a status on an unlisted subject CREATES a listing record
        steps.append(Step(PUT, "subject not listed", [
            w("SLI_LISTINGS", "None"), w("SUM_LISTING_STATUS", ""), w("SLI_LIST_STATUS", ""),
            w("SLI_LIST_CUR_OR_FINAL_LP", ""), w("SLI_DATA_SOURCE", s.get("listing_search_source", "MLS")),
            w("SLI_ANALYSIS_HISTORY", s["listing_analysis"])]))

        def drop_row(r):
            if formkit.values(r, ["HIDDEN_SUBJ-LISTING-HISTORY-ROW_COUNT"]).get(
                    "HIDDEN_SUBJ-LISTING-HISTORY-ROW_COUNT#0", "0") != "0":
                formkit.remove_row_group(r, "subj-listing-history-row", 0)
        steps.append(Step(STRUCT, "remove the empty listing-history row (E-050)", action=drop_row))
    pt = s.get("prior_transfer")
    hist = [w("PSH_SUB_ANALYSIS", s["prior_analysis"]), w("PSH_COMP_ANALYSIS", c["comp_prior_analysis"]),
            w("GSU_TRANSFER_HISTORY_PRESENT", _yn(bool(pt))),
            w("GSU_TRANSFER_HISTORY_SOURCE", s.get("prior_transfer_source", "Assessor Record"))]
    if pt:   # the Prior Sale section is read-only labels; values live in the grid's subject column
        hist += [w("GSU_TRANSFER_HISTORY_DATE", pt["date"]),
                 w("GSU_DFE_TRANSFER_HISTORY_AMOUNT_VALUE", money(pt["amount"])),
                 w("GSU_TRANSFER_HISTORY_TERMS", pt.get("terms", "Typically Motivated"))]
    steps.append(Step(PUT, "transfer history", hist))
    return steps


# ---------------------------------------------------------------- the grid
ZERO_ROWS = [
    "DP_FINTYP1_ADJ", "DT_SALTIM1_ADJ", "SP_TO_LP_RATIO_ADJ", "ATT_DET_ADJ", "ALL_RIGHTS_INCLUDED_ADJ",
    "SITE_OWNED_IN_COMMON_ADJ", "ST_SITSIZE_ADJ", "SITE_HAZARD_ZONE_ADJ", "SITE_PRIMARY_ACCESS_ADJ",
    "SITE_CHARACTERISTICS_ADJ", "SITE_INFLUENCE_ADJ", "ST_VIEW_ADJ", "YR_BLT_ADJ", "DWELL_CONST_METHOD_ADJ",
    "DWELL_FUNC_ISSUES_ADJ", "DWELL_HEAT_ADJ", "DWELL_COOL_ADJ", "LEVELS_ADJ", "UNITS_SF_GLA_ADJ",
    "UNITS_SF_GLA_BELOW_GRD_ADJ", "VEHICLE_STORAGE_ADJ", "EX_CONCAMT_ADJ", "TRANSFER_TERMS_ADJ",
    "QUALITY_ADJ", "CONDITION_ADJ", "BEDS_ADJ", "BATHS_ADJ", "PROP_APPRAISER_RIGHTS_ADJ", "MARKETAREA_ADJ",
    "SITE_ZONE_COMPLIANCE_ADJ", "SITE_STREET_TYPE_ADJ", "SITE_TOPOGRAPHY_ADJ", "SITE_ENV_COND_ADJ",
    "DWELL_TH_ENDUNIT_ADJ", "DWELL_TH_BACKTOBACK_ADJ", "DWELL_TOTAL_VOLUME_ADJ", "DWELL_WINDOW_AREA_ADJ",
    "DWELL_DISASTER_MIT_ADJ", "UNITS_SF_GLA_NONSTD_ADJ", "UNITS_SF_GLA_UNFIN_ADJ",
    "UNITS_SF_GLA_BELOW_GRD_NONSTD_ADJ", "UNITS_SF_GLA_BELOW_GRD_UNFIN_ADJ", "DISABILITY_FEATURES_ADJ",
    "DWELL_TH_LOC_ADJ", "AMENITY_OUTDOOR_LIVING_ADJ",
]


def comp_rows(c, comp) -> list[dict]:
    """Every grid cell for one comparable.  Held-equal rows come from the case's
    `held_equal` block (the subject's own answers), never invented per comparable."""
    n, he = comp["n"], c["held_equal"]
    p = f"GC{n}_"
    rows = {
        "AD_ADDR1": comp["addr"], "DB_CITY": comp["city"], "DB_STATE": comp.get("state", "NY"), "DB_ZIP": comp["zip"],
        "PROX1": f"{comp['proximity']:.2f}", "PU_DISTANCE": f"{comp['proximity']:.2f}", "PU_DIRECTION": comp["direction"],
        "SC_SOURCE1": comp["source_label"], "PU_DATA_SOURCE": comp.get("data_source", "MLS"),
        "PU_DATA_SOURCE_MLS_NUM": comp.get("mls", ""),
        "ATT_DET": comp.get("attachment", he.get("ATT_DET", "Detached")),
        **({"PU_STRUCTURE_DESIGN": comp["structure_design"], "DWELL_DESIGN": comp["structure_design"]}
           if comp.get("structure_design") else {}),
        "LIST_PRICE": comp["list_price"], "LP_PRICE": comp["list_price"], "EX_DOM": comp["dom"],
        "LP_STATUS": comp["status"],
        "UNITS_SF_GLA": comp["gla"], "SF_FINISHED_AREA": comp["gla"], "YR_BLT": comp["year"],
        "PU_YR_BLT": comp["year"], "PU_YR_BLT_EST": "No", "BEDS": comp["beds"],
        "PU_FULL_BATHS": comp["baths_full"], "PU_HALF_BATHS": comp["baths_half"], "ST_SITSIZE": comp["site"],
        "LEVELS": comp["levels"], "PU_DWELL_HEAT_SYSTEM": comp["heat"], "DWELL_HEAT": comp["heat"],
        "PU_DWELL_COOL": comp["cooling"], "DWELL_COOL": comp["cooling"], "PU_CONT_DATE": comp.get("contract_date", ""),
        "EXT_QUAL_EXT_WALLS_TRIM": comp["walls"], "EXT_QUAL_FOUNDATION": comp["foundation"],
        "INT_COND_KITCHEN": comp.get("kitchen_update", he["INT_COND_KITCHEN"]),
        "UNITS_SF_GLA_BELOW_GRD": 0, "NETADJ_COMP_WEIGHT_ADJ": comp["weight"],
        "PU_VEHICLE_STORAGE": comp["vehicle_type"], "VEHICLE_STORAGE": comp["vehicle_spaces"],
        "SITE_HAZARD_ZONE": "No Hazard Zone Noted",                       # E-049
        "DP_FINTYP1": "Conventional",
    }
    if comp["vehicle_type"] in ("Driveway", "Shared Driveway"):
        rows["PU_VEHICLE_STORAGE_SPACES"] = comp["vehicle_spaces"]         # E-048
        rows["PU_VEHICLE_STORAGE_SPACES_NUM"] = comp["vehicle_spaces"]
        rows["PU_VEHICLE_STORAGE_DETAILS"] = comp["driveway_surface"]
    else:
        rows["PU_VEHICLE_STORAGE_SPACES_NUM"] = comp["vehicle_spaces"]
        rows["PU_VEHICLE_STORAGE_DETAILS"] = comp.get("garage_detail", "")
    if comp.get("project"):
        # a condominium comparable (E-066): unit, project, fee, floor, corner
        rows.update({"DB_UNITNO": comp.get("unit", ""), "PROJ_NAME": comp["project"],
                     "PU_PROJECT_NAME": comp["project"],
                     "PU_SAME_PROJECT_AS_SUBJECT": "X" if comp.get("same_project") else "",
                     "SITE_PROJECT_TYPE": (c.get("project") or {}).get("legal_structure", "Condominium"),
                     "PROJ_MONTHLY_FEE": money(comp["monthly_fee"]) if comp.get("monthly_fee") else "",
                     "PROJ_AMENITIES": "|".join(comp.get("amenities", [])),
                     "PROJ_SPECIAL_ASSESSMENTS": comp.get("special_assessments", "None"),
                     "FLOOR_NUM": comp.get("floor", ""), "CORNER_UNIT": _yn(comp.get("corner", False))})
    for row, differs in condo_differences(c, comp).items():
        if differs:
            rows[row] = "$0"
    if comp["status"] == "Settled Sale":
        rows.update({"PR_SALEPR1": comp["price"], "SALE_PRICE": comp["price"],
                     "DT_SALTIM1": comp["close_date"], "TRANSFER_TERMS": comp.get("terms", "Typically Motivated")})
    else:
        # a pending sale / listing has no settled price, terms or sale date
        rows.update({"PR_SALEPR1": "", "SALE_PRICE": "", "DT_SALTIM1": "", "TRANSFER_TERMS": ""})
    # "_"-prefixed keys are notes in the case file, never fields
    rows.update({k: v for k, v in he.items() if k not in rows and not k.startswith("_")})
    for k in list(rows):
        if k.endswith("INT_COND_BATHS"):
            rows[k] = bath_update(rows[k])                                 # E-061
    per_unit = []
    if comp.get("units"):
        # 2-4 unit grid: a comparable's unit row exists once its UNIT_ID
        # ("structure | unit") is set (TOTAL: IsMultiFamilyReport ->
        # UNIT_ID non-empty); the building's gross finished area is SF_GLA
        for k in ("BEDS", "PU_FULL_BATHS", "PU_HALF_BATHS", "UNITS_SF_GLA", "UNITS_SF_GLA_BELOW_GRD"):
            rows.pop(k, None)
        rows["SF_GLA"] = sum(u["gla"] for u in comp["units"])
        for i, u in enumerate(comp["units"]):
            per_unit += [w(p + "UNIT_ID", f"1 | {i + 1}", i), w(p + "INT_QUAL_STRUCTURE_ID", f"1 | {i + 1}", i),
                         w(p + "UNITS_IS_AN_ADU", "No", i),
                         w(p + "BEDS", u["beds"], i), w(p + "PU_FULL_BATHS", u["baths_full"], i),
                         w(p + "PU_HALF_BATHS", u.get("baths_half", 0), i),
                         w(p + "UNITS_SF_GLA", u["gla"], i),
                         w(p + "UNITS_SF_GLA_BELOW_GRD", u.get("below_finished", 0), i),
                         w(p + "UNITS_SF_GLA_BELOW_GRD_UNFIN", u.get("below_unfinished", 0), i)]
    if comp.get("units"):
        su = units(c)
        for i, u in enumerate(comp["units"]):
            if i:   # unit 1's row takes the building-level values above
                per_unit += [w(p + k, rows[k], i) for k in UNIT_HELD if k in rows]
                per_unit += [w(p + k, "$0", i) for k in UNIT_ZERO]
            s_levels = len([lv for lv in su[i]["levels"] if lv["grade"] == "Above Grade"]) if i < len(su) else 1
            per_unit.append(w(p + "LEVELS", u.get("levels", 1), i))
            if u.get("levels", 1) != s_levels:          # differs -> an entry ($0); same -> left blank
                per_unit.append(w(p + "LEVELS_ADJ", "$0", i))
        rows.pop("LEVELS", None)
    # empty facts are not written: "" makes TOTAL validate them (E-055); they
    # are unset to null by `comp_absent()` instead
    out = [w(p + k, v) for k, v in rows.items() if str(v) != ""] + per_unit
    out += [w(p + k, "$0") for k in ZERO_ROWS]
    if comp.get("units"):
        out.append(w(p + "SF_GLA_ADJ", "$0"))
        if design_of(comp) != design_of(c["subject"]):
            out.append(w(p + "DWELL_DESIGN_ADJ", "$0"))   # differs -> an entry; same -> blank
    return out


#: held-equal grid rows a 2-4 unit report repeats on every unit's row
UNIT_HELD = ("INT_QUAL_QUALITY", "INT_QUAL_KITCHEN", "INT_QUAL_BATHS", "INT_QUAL_FLOORS", "INT_QUAL_WALLS_CEILINGS",
             "INT_COND_CONDITION", "INT_COND_KITCHEN", "INT_COND_BATHS", "INT_COND_FLOORS", "INT_COND_WALLS_CEILINGS",
             "UNITS_SF_GLA_NONSTD", "UNITS_SF_GLA_UNFIN", "UNITS_SF_GLA_BELOW_GRD_NONSTD",
             "DISABILITY_FEATURES")
UNIT_ZERO = ("UNITS_SF_GLA_NONSTD_ADJ", "UNITS_SF_GLA_UNFIN_ADJ", "UNITS_SF_GLA_BELOW_GRD_NONSTD_ADJ",
             "UNITS_SF_GLA_BELOW_GRD_UNFIN_ADJ", "DISABILITY_FEATURES_ADJ")


def condo_differences(c, comp) -> dict[str, bool]:
    """Condo grid rows TOTAL wants an adjustment entry on when subject and
    comparable differ: floor, corner unit, project information (name, fee,
    amenities, special assessment).  {} for a comparable not in a project."""
    pj, s = c.get("project"), c["subject"]
    if not (pj and comp.get("project")):
        return {}
    sa = "Existing" if pj.get("special_assessment") else "None"
    return {
        "FLOOR_NUM_ADJ": str(comp.get("floor", "")) != str(s.get("floor_number", "")),
        "CORNER_UNIT_ADJ": bool(comp.get("corner")) != bool(s.get("corner_unit")),
        "PROJINFO_OVERALL_ADJ": (comp["project"] != pj["name"]
                                 or round(comp.get("monthly_fee") or 0) != round(pj.get("monthly_fee") or 0)
                                 or sorted(comp.get("amenities", [])) != sorted(pj.get("amenities", []))
                                 or comp.get("special_assessments", "None") != sa),
    }


def comp_absent(c, comp) -> list[str]:
    """Grid fields that do not exist for this comparable -> back to null (E-055)."""
    p = f"GC{comp['n']}_"
    keys = [p + k for k in ("PU_NATIVE_AM_LANDS_TYPE", "SITE_EASEMENT", "SITE_DRAINAGE",
                            "PU_SITE_INFLUENCE_WATER_TYPE", "PU_AMENITY_OUTDOOR_ACCESSORIES",
                            "PU_LOC_ADU_TYPE", "PU_LOC_ADU_DESC", "LOC_ADU")]
    for k, v in (("PU_CONT_DATE", comp.get("contract_date")), ("EX_DOM", comp.get("dom"))):
        if v in (None, ""):
            keys.append(p + k)
    if comp["status"] != "Settled Sale":
        # a pending sale / listing has no transfer (E-048, UAD-1439): cleared,
        # not blanked, so nothing is exported and nothing is validated
        keys += [p + k for k in ("PR_SALEPR1", "SALE_PRICE", "DT_SALTIM1", "TRANSFER_TERMS")]
    keys += [p + row for row, differs in condo_differences(c, comp).items() if not differs]
    if comp.get("units") and design_of(comp) == design_of(c["subject"]):
        keys.append(p + "DWELL_DESIGN_ADJ")
    return keys


def grid(c) -> list[Step]:
    comps = c["comps"]

    def columns(r):
        formkit.add_comparables(r, len(comps))
    s = c["subject"]
    subj = []
    for i, u in enumerate(units(c)):        # one interior-QC row per unit in a 2-4 grid
        subj += [w("GSU_INT_QUAL_KITCHEN", u["quality"], i), w("GSU_INT_QUAL_BATHS", u["quality"], i),
                 w("GSU_INT_QUAL_FLOORS", u["quality"], i), w("GSU_INT_QUAL_WALLS_CEILINGS", u["quality"], i),
                 w("GSU_INT_COND_WALLS_CEILINGS", u["walls_ceiling"]["status"], i)]
    subj += [w("GSU_ST_SITSIZE", s["site_sqft"]), w("GSU_ALL_RIGHTS_INCLUDED", "Yes"),
            w("GSU_SITE_PRIMARY_ACCESS", "Public Street"), w("GSU_DISABILITY_FEATURES", "None"),
            w("GSU_EXT_QUAL_STRUCTURE_ID", "1"), w("GSU_SITE_HAZARD_ZONE", "No Hazard Zone Noted"),
            w("GSU_PU_NATIVE_AM_LANDS_NO", "X")]
    steps = [Step(STRUCT, f"comparable columns -> {len(comps)} (CompManagers.AddComp)", action=columns),
             Step(PUT, "grid subject column", subj)]
    for comp in comps:
        steps.append(Step(PUT, f"comparable {comp['n']} {comp['addr']}", comp_rows(c, comp)))

        def popup(r, n=comp["n"]):
            formkit.fire(r, f"GC{n}_VEHICLE_STORAGE", formkit.HIDE_POPUP)   # the rule listens to HidePopup
        steps.append(Step(STRUCT, f"comparable {comp['n']} vehicle-storage popup closed", action=popup))

        def absent(r, keys=comp_absent(c, comp)):
            formkit.unset(r, keys)
        steps.append(Step(STRUCT, f"comparable {comp['n']}: rows that do not exist -> null (E-055)", action=absent))
    return steps


def to_property(d: dict, price=0, listing=False, design="", cooling="") -> adjust.Property:
    return adjust.Property(gla=d["gla"], site=d["site"], year=d["year"], beds=d["beds"],
                           baths=d["baths_full"] + 0.5 * d["baths_half"],
                           basement_finished=bool(d["basement_finished"]), garage=int(d["garage_spaces"]),
                           outdoor=bool(d["outdoor"]), price=price, listing=listing,
                           design=design, cooling=bool(cooling) and cooling != "None")


def profile(c) -> adjust.Profile:
    """The rate profile: the case may name one; a 2-4 unit report takes the
    owner's multi-family rates (2026-10-02), anything else 18 North."""
    name = c.get("adjustment_profile") or ("multi-family" if len(units(c)) > 1 else "18 North")
    return adjust.PROFILES[name]


def design_of(d: dict) -> str:
    """Semi-detached is a structure design; `attachment` alone says attached/detached.
    A design the rate profile does not rank (Rowhouse / Townhouse, Low-rise ...)
    is judged by its attachment -- a rowhouse is attached (601 Euclid, 2026-10-02:
    the semi-detached comparables otherwise got no design adjustment)."""
    sd = d.get("structure_design")
    return sd if sd in adjust.DESIGN_RANK else d.get("attachment", "")


def subject_units(c) -> list[adjust.Unit]:
    """The subject's units as the grid sees them, from the case's own levels and rooms."""
    out = []
    for u in units(c):
        above = sum(lv["finished"] for lv in u["levels"] if lv["grade"] == "Above Grade")
        below_fin = sum(lv["finished"] for lv in u["levels"] if lv["grade"] != "Above Grade")
        types = [t for _, t in u["rooms"]]
        out.append(adjust.Unit(gla=above, beds=types.count("Bedroom"),
                               baths=types.count("Bath - Full") + 0.5 * types.count("Bath - Half"),
                               basement_finished=below_fin > 0))
    return out


def comp_units(cp) -> list[adjust.Unit]:
    return [adjust.Unit(gla=u["gla"], beds=u["beds"], baths=u["baths_full"] + 0.5 * u.get("baths_half", 0),
                        basement_finished=bool(u.get("below_finished"))) for u in cp.get("units", [])]


def adjustments(c) -> adjust.Result:
    s, p = c["subject"], profile(c)
    subj = to_property(s["grid"], design=design_of(s), cooling=s.get("cooling", ""))
    su = subject_units(c)
    res = adjust.Result()
    for cp in c["comps"]:
        prop = to_property({**cp, "garage_spaces": cp["garage_spaces"]},
                           price=cp["price"] if cp["status"] == "Settled Sale" else cp["list_price"],
                           listing=cp["status"] != "Settled Sale",
                           design=design_of(cp), cooling=cp.get("cooling", ""))
        cu = comp_units(cp)
        # 2-4 units: GLA, bedrooms, baths and finished basement go on the unit rows
        t = (adjust.multi_lines(subj, prop, su, cu, p) if len(su) > 1 and cu
             else adjust.lines(subj, prop, p))
        if t.get("DWELL_DESIGN_ADJ") == 0:
            # same design: TOTAL wants the row left blank, not "$0" (E-063);
            # comp_absent() nulls it
            del t["DWELL_DESIGN_ADJ"]
        if len(su) <= 1 and "DWELL_DESIGN_ADJ" in t:
            t["ATT_DET_ADJ"] = t.pop("DWELL_DESIGN_ADJ")      # a 1-unit grid's design row
        res.table[cp["n"]] = t
    return res


#: how each adjustment row is named in the reconciliation's closing line
RATE_TEXT = {
    "UNITS_SF_GLA_ADJ": lambda p: f"GLA {money(p.gla)}/sq ft" + (
        f" (differences over {p.gla_threshold:,.0f} sq ft)" if p.gla_threshold else ""),
    "ST_SITSIZE_ADJ": lambda p: f"site {money(p.site)}/sq ft (differences over {p.site_threshold:,.0f} sq ft)",
    "YR_BLT_ADJ": lambda p: f"age {money(p.age)}/year (differences over {p.age_threshold:,.0f} years)",
    "BEDS_ADJ": lambda p: f"bedroom {money(p.bedroom)}",
    "BATHS_ADJ": lambda p: f"full bath {money(2 * p.half_bath)}, half bath {money(p.half_bath)}",
    "DWELL_DESIGN_ADJ": lambda p: f"semi-detached vs attached/detached design {money(p.design)}",
    "ATT_DET_ADJ": lambda p: f"semi-detached vs attached/detached design {money(p.design)}",
    "DWELL_COOL_ADJ": lambda p: f"cooling system {money(p.cooling)}",
    "VEHICLE_STORAGE_ADJ": lambda p: f"garage {money(p.garage)} per space",
    "UNITS_SF_GLA_BELOW_GRD_ADJ": lambda p: f"finished basement {money(p.basement)}",
    "AMENITY_OUTDOOR_LIVING_ADJ": lambda p: f"deck/patio/porch/balcony {money(p.outdoor)}",
    "SP_TO_LP_RATIO_ADJ": lambda p: f"list-to-sale ratio {p.exposure:.0%} of list price on a listing",
}


def rates_used(res: adjust.Result, p: adjust.Profile) -> str:
    """'Adjustments: ...' naming only the rows that moved a comparable, in grid order."""
    used = {row.partition("#")[0] for t in res.table.values() for row, v in t.items() if v}
    return "; ".join(f(p) for row, f in RATE_TEXT.items() if row in used)


def reconciliation_text(c, res: adjust.Result) -> tuple[str, int, dict]:
    comps = {cp["n"]: cp for cp in c["comps"]}
    adjusted = {n: (cp["price"] if cp["status"] == "Settled Sale" else cp["list_price"]) + res.net(n)
                for n, cp in comps.items()}
    weights = {int(k): v for k, v in c["reconciliation"]["weights"].items()}
    ind, value = adjust.weighted(adjusted, weights, c["reconciliation"].get("round_to", 5000))
    value = c["reconciliation"].get("value", value)
    parts = " + ".join(f"{weights[n]:.2f} x {adjusted[n]:,.0f}" for n in sorted(weights))
    lo, hi = min(adjusted.values()), max(adjusted.values())
    rc = c["reconciliation"]
    if rc.get("summary") and not rc.get("text"):
        # the owner's form (2026-10-02): a short weighting summary, the value,
        # and the adjustments made listed at the bottom
        text = (rc["summary"].rstrip() + f" After the market adjustments the comparables indicate "
                f"{money(lo)} to {money(hi)}; the appraiser has concluded a market value of "
                f"{money(value)} for the subject property.\nAdjustments: "
                + rates_used(res, profile(c)) + ".")
        return text, value, adjusted
    text = c["reconciliation"].get("text") or (
        c["reconciliation"].get("narrative", "Comparables adjusted on the "
                                  f"{profile(c).name} parameters.").rstrip() + " Adjusted prices: "
        + "; ".join(f"comparable {n} {money(adjusted[n])} (gross {res.gross(n) / (adjusted[n] - res.net(n)):.1%})"
                    for n in sorted(adjusted))
        + f". Weighted: {parts} = {money(ind)}, reconciled to {money(value)}, within the "
          f"{money(lo)} to {money(hi)} range of the adjusted prices.")
    return text, value, adjusted


def final_comment(c, value: int) -> str:
    """The final reconciliation comment: which approach carries the value,
    why the others were not developed, and the value -- short (owner 2026-10-02)."""
    rc = c["reconciliation"]
    if rc.get("final_comment"):
        return rc["final_comment"]
    why = {"Not Necessary for Credible Results": "not necessary for credible results",
           "Insufficient Data": "insufficient data"}
    parts = ["Most emphasis is given to the value indicated by the Sales Comparison Approach, "
             "which is well supported by the comparable sales and listings analysed."]
    cost = rc.get("cost_excluded", "Not Necessary for Credible Results")
    parts.append(f"The Cost Approach was not developed ({why.get(cost, cost.lower())}).")
    if not c.get("income"):
        inc = rc.get("income_excluded", "Not Necessary for Credible Results")
        parts.append(f"The Income Approach was not developed ({why.get(inc, inc.lower())}).")
    parts.append(f"The appraiser has concluded a final market value of {money(value)} for the subject property.")
    return " ".join(parts)


def closing(c) -> list[Step]:
    rc = c["reconciliation"]
    res = adjustments(c)
    text, value, _ = reconciliation_text(c, res)

    def write_adj(r):
        adjust.write(r, res)
    steps = [Step(STRUCT, f"adjustments on the {profile(c).name} profile + net re-sum", action=write_adj)]
    steps.append(Step(PUT, "reconciliation", [
        w("GSU_SCMINDVALUE2", money(value)), w("SA_RECONCILE", text),
        w("REC_MKT_VAL_COND", rc.get("condition", "As Is")),
        # REC_MARKET_VALUE is NOT an amount: TOTAL exports it as the
        # reconciliation comment (26.019 -> ValuationReconciliationSummaryComment
        # Description, UAD-1266) -- a bare "$1,825,000" there was the whole comment
        w("REC_MARKET_VALUE", final_comment(c, value)), w("REC_OPINION_MKT_VAL", money(value)),
        w("REC_REASONABLE_EXPOSURE_TIME", rc["exposure_days"]),
        w("PU_REC_REASONABLE_EXPOSURE_TIME_PRECISE", "X"),                 # UAD-1746
        w("REC_REASONABLE_EXPOSURE_TIME_PRECISE", rc["exposure_days"]),
        *([] if c.get("income") else
          [w("REC_REASON_FOR_EXCLUSION_INCOME_APPROACH", rc.get("income_excluded", "Not Necessary for Credible Results"))]),
        w("REC_REASON_FOR_EXCLUSION_COST_APPROACH", rc.get("cost_excluded", "Not Necessary for Credible Results")),
    ]))
    s = c["subject"]
    income_gates = [] if c.get("income") else [
        *[w(f"GR{n}_{k}", "0") for n in (1, 2, 3) for k in ("ADU", "GBFA")],
        w("HIDDEN_GROSSRENTALINCOME_COUNT", "0")]
    steps.append(Step(PUT, "gates: cost, income, revision, supervisor", [
        w("CHECK_COST_APPROACH_DISABLE", "X"),
        w("SSDE1_HIDDEN_CA-DWELLING-DEPRECIATION-COST-SECTION_COUNT", "0"),
        w("HIDDEN_CA-DWELLING-DEPRECIATION-COST-SECTION_COUNT", "0"),
        w("HIDDEN_CA-DEPRECIATED-COST-DWELLING_COUNT", "0"),
        w("HIDDEN_CA-OUTBUILDING-DEPRECIATION-COST-SECTION_COUNT", "0"),
        w("HIDDEN_CA-OUTBUILDING-DEPRECIATION-COST_COUNT", "0"),
        w("SSDE1_CA_EFFECTIVE_AGE", s["effective_age"]), w("SSDE1_CA_EFFECTIVE_AGE_PRECISE", s["effective_age"]),
        w("SSDE1_CA_REMAINING_ECONOMIC_LIFE", s["remaining_life"]),
        w("SSDE1_CA_DWELL_PHYSICAL_DEPRECIATION", "0"), w("SSDE1_CA_DWELL_FUNCTIONAL_DEPRECIATION", "0"),
        w("SSDE1_CA_DWELL_EXTERNAL_DEPRECIATION", "0"),
        *income_gates,
        w("RN_REC_VAL_TYPE", ""), w("HIDDEN_PRIOR-SALES-REVISION_COUNT", "0"),
        # no supervisor and no second appraiser: EMPTY, not "None" -- "None"
        # re-requires the whole block (E-003/E-034)
        w("SUPERVISOR_TYPE", ""), w("SRPA_TYPE", ""), w("ORD_SRPA_CONTACT_TYPE", ""),
        w("ORD_HIDDEN_SUPERVISOR_COUNT", "0"), w("ORD_HIDDEN_SRPA_COUNT", "0"),
        w("SUPERVISOR_LEVEL", ""), w("SRPA_LEVEL", ""), w("SRPA_DESC", ""),
    ]))
    steps.append(Step(STRUCT, "clear a phantom supervisor", action=reconcile.clear_phantom_supervisor))

    def absent(r):
        # E-055: what does not exist on this property goes back to null --
        # never a field that should hold a value
        groups = ["supervisor", "srpa", "reconsideration-of-value",
                  "table-site-feature-easement", "table-site-feature-encroach"]
        if not s.get("restriction"):
            groups.append("table-site-feature-restrict")
        keys = ["ELEM_DIV_PARCELS", "PU_SITE_INFL_WTR_DTL_TYPE"]
        if c.get("units") and not c.get("rental", {}).get("other_income"):
            keys += ["RI_ACT_INC_OTHER_MONTHLY_RENT", "RI_OPN_INC_OTHER_MONTHLY_RENT", "RI_ACT_INC_OTHER_DESC",
                     "RI_OPN_INC_OTHER_DESC"]
        formkit.unset(r, keys, groups)
    steps.append(Step(STRUCT, "blocks that do not exist -> null (E-055)", action=absent))
    return steps


REPO = Path(__file__).resolve().parents[2]


def assignment_exhibits(c) -> tuple[list[dict], list[str]]:
    """The owner's standing rule: Assignment Information exhibits are the
    appraiser's licence and E&O declaration from the profile -- never the
    engagement letter.  Returns (manifest rows, missing files)."""
    ex = (c.get("appraiser") or {}).get("assignment_exhibits") or {}
    rows, missing = [], []
    for key, desc in (("licence", "Appraiser licence"), ("eo_insurance", "E&O insurance declaration")):
        path = ex.get(key)
        if not path:
            continue
        p = Path(path) if Path(path).is_absolute() else REPO / path
        if p.exists():
            rows.append({"section": "assignment", "file": str(p), "description": desc})
        else:
            missing.append(str(p))
    return rows, missing


def media(c, base: Path) -> list[Step]:
    photos = [p for p in c.get("photos", []) if p.get("section") != "assignment"
              and p.get("slot") != "ASSIGNMENT_EXHIBIT_PHOTO"]
    rows, missing = assignment_exhibits(c)
    # exhibits whose picture was not taken: labelled rows after the section's
    # real pictures, each carrying a "photograph not available" card -- TOTAL
    # rejects an interior exhibit with no image (E-059)
    cards = []
    for i, m in enumerate(c.get("missing_photos", [])):
        label = m.get("label") or m["description"].split(" -- ")[0]
        card = exhibits.not_available_card(label, base / "_uad36_not_available" / f"missing_{i + 1}.png")
        cards.append({**{k: v for k, v in m.items() if k != "file"}, "file": str(card)})
    photos = photos + cards + rows
    if missing:
        print("!! MISSING appraiser documents for the Assignment exhibits (standing rule: licence + E&O):",
              *missing, sep="\n   ")

    def place_photos(r):
        res = exhibits.place_manifest(r, photos, base)
        print(f"      photos placed {res['placed']}, failed {res['failed']}")

    def place_map(r):
        s = c["subject"]
        pts = [("S", f"Subject: {s['address']}", s["lat"], s["lon"], "subject")]
        for cp in c["comps"]:
            note = " (street-level location)" if cp.get("street_level") else ""
            pend = " (pending)" if cp["status"] == "Pending" else ""
            pts.append((str(cp["n"]), f"Comp {cp['n']}: {cp['addr']}{pend}{note}", cp["lat"], cp["lon"], "comp"))
        out = locmap.draw(pts, base / "_uad36_comparable_map.png") if not c.get("map_file") else base / c["map_file"]
        exhibits.drop(r, "sales-comp", "GSU_MAP", 0, out, "Comparable location map")
    return [Step(STRUCT, f"photographs ({len(photos)}) -- after rooms, categories need them", action=place_photos),
            Step(STRUCT, "SCA location map (UAD-1283)", action=place_map)]


def comments(c) -> list[Step]:
    """Section commentary the case states (``"comments": {FIELD: text}``) --
    the reviewer-facing explanations an AMC asks for (occupancy vs the order,
    the GLA basis, smoke/CO, why an approach was not developed).  Only keys
    ending in COMMENTARY are accepted, so it cannot carry data values."""
    cm = c.get("comments") or {}
    bad = [k for k in cm if not k.endswith("COMMENTARY") and not k.startswith("_")]
    if bad:
        raise ValueError(f"comments: only *COMMENTARY fields are allowed, not {bad}")
    writes = [w(k, v) for k, v in cm.items() if not k.startswith("_")]
    return [Step(PUT, f"commentary ({len(writes)} fields)", writes)] if writes else []


def plan(c: dict, base: Path) -> list[Step]:
    return (parties(c) + subject_site(c) + dwelling(c) + interior(c) + rent_schedule(c) + rental_comps(c)
            + storage_amenity(c) + project_info(c)
            # sales_contract(c) is NOT in the automatic plan: its writes froze
            # TOTAL three times on 146 W 57th St (E-067) -- cause not found yet
            + market_listing_history(c) + grid(c) + closing(c) + comments(c) + media(c, base))


# ---------------------------------------------------------------- guard
def guard(report, c) -> list[str]:
    """Refuse to write into the wrong report."""
    problems = []
    if getattr(report, "signed", False):
        problems.append("the report is signed -- unsign it in TOTAL first")
    v = formkit.values(report, ["ORD_SUBPROPADDRESS", "ORD_SUBZIP", "UNIT_EXCL_ADU"])
    want = re.sub(r"\W", "", c["subject"]["street_address"]).lower()
    have = re.sub(r"\W", "", v.get("ORD_SUBPROPADDRESS#0", "")).lower()
    if not have or (want not in have and have not in want):
        problems.append(f"the open report's subject is {v.get('ORD_SUBPROPADDRESS#0')!r}, "
                        f"the case is {c['subject']['street_address']!r} -- open the right report")
    if c["subject"].get("zip") and v.get("ORD_SUBZIP#0") and v["ORD_SUBZIP#0"] != c["subject"]["zip"]:
        problems.append(f"ZIP differs: report {v['ORD_SUBZIP#0']}, case {c['subject']['zip']}")
    return problems


# ---------------------------------------------------------------- run
def _norm(v: str) -> str:
    v = str(v or "").strip().lower()
    v = re.sub(r"\s*sq\.?\s*ft\.?", "", v)
    v = re.sub(r"[$,\s]", "", v)
    if re.fullmatch(r"\(\d+(\.\d+)?\)", v):
        v = "-" + v[1:-1]
    return v


def dry_run(report, c: dict, base: Path) -> dict:
    """Compare the plan with what the open report holds.  Writes nothing."""
    steps = plan(c, base)
    keys = [x["field"] for s in steps if s.kind == PUT for x in s.writes]
    have = formkit.values(report, keys)
    diffs, same, absent = [], 0, []
    for s in steps:
        if s.kind != PUT:
            continue
        for x in s.writes:
            k = f"{x['field']}#{x['instance']}"
            if k not in have:
                absent.append(k)
                continue
            if _norm(have[k]) == _norm(x["value"]):
                same += 1
            else:
                diffs.append((s.title, k, have[k][:60], x["value"][:60]))
    res = adjustments(c)
    return {"same": same, "diffs": diffs, "absent": absent,
            "structural": [s.title for s in steps if s.kind == STRUCT],
            "adjustments": {n: {"net": res.net(n), "lines": {k: v for k, v in t.items() if v}}
                            for n, t in res.table.items()}}


def run(report, c: dict, base: Path, log=print) -> certify.Verdict:
    problems = guard(report, c)
    if problems:
        raise RuntimeError("refusing to fill: " + "; ".join(problems))
    for i, s in enumerate(plan(c, base), 1):
        if not alive(report):
            raise RuntimeError(f"TOTAL stopped answering before step {i} ({s.title}) -- stop (E-067)")
        if s.kind == PUT:
            out = rtv.put(report, s.writes)
            miss = out.get("missed") or []
            log(f"[{i:02}] {s.title}: {len(out.get('written') or [])} written"
                + (f", MISSED {miss}" if miss else ""))
        else:
            log(f"[{i:02}] {s.title}")
            s.action(report)
        save(report)                         # E-064/E-067: never lose a section again
    formkit.settle_neutral(report)
    save(report)
    return certify.run(report)


def save(report) -> bool:
    """Save the report through WinTOTAL's own host method (CefConnector.save),
    reached over the debugging port -- no desktop control.  Owner 2026-10-02:
    save after every section.  E-064: rtv.put alone persists nothing."""
    try:
        return bool(report.page.evaluate(
            "Promise.resolve(typeof CefConnector!=='undefined' && CefConnector.save()).then(v=>!!v)",
            await_promise=True))
    except Exception:
        return False
