"""H-1 rules executed one by one (uad/compliance_checks.py).

Each check must leave every D-1 sample alone and fire on a copy of a sample
broken in exactly the way its rule describes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, compliance, compliance_checks as cc, templates  # noqa: E402

M = f"{{{bind.MISMO}}}"
X = "{http://www.w3.org/1999/xlink}"


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_no_check_faults_a_published_sample(key):
    root = templates.load(key).getroot()
    assert [mid for mid, fn in cc.BY_ID.items() if fn(root) is True] == []


def _subject(root):
    return bind.subject(root)


def _set(scope, name, value):
    for n in scope.iter(f"{M}{name}"):
        n.text = value
        return n
    raise AssertionError(f"{name} not in the sample")


def _drop(node):
    node.getparent().remove(node)


def _drop_all(root, name):
    for n in list(root.iter(f"{M}{name}")):
        _drop(n)


def _add(parent, name, value):
    from lxml import etree
    el = etree.SubElement(parent, f"{M}{name}")
    el.text = value
    return el


def _drop_arcs(root, arc):
    for r in list(root.iter(f"{M}RELATIONSHIP")):
        if r.get(f"{X}arcrole", "").endswith(arc):
            _drop(r)


def _defect(indicator, arc):
    def brk(root):
        _set(_subject(root), indicator, "true")
        _drop_arcs(root, arc)
    return brk


def _dup_arc(root):
    r = next(root.iter(f"{M}RELATIONSHIP"))
    from copy import deepcopy
    r.addnext(deepcopy(r))


def _bad_arc(end):
    def brk(root):
        next(root.iter(f"{M}RELATIONSHIP")).set(f"{X}{end}", "NO_SUCH_LABEL")
    return brk


def _second_condition(root):
    from copy import deepcopy
    c = next(root.iter(f"{M}VALUATION_CONDITION"))
    c.addnext(deepcopy(c))


def _image_category(root, old, new):
    for n in _subject(root).iter(f"{M}ImageCategoryType"):
        if n.text == old:
            n.text = new


def _comp_net(root):
    comp = next(p for p in root.iter(f"{M}PROPERTY") if p.get("ValuationUseType") == "SalesComparable")
    _set(comp, "SalePriceNetTotalAdjustmentAmount", "123456")


def _appraiser(root):
    return next(p for p in root.iter(f"{M}PARTY")
                if any(n.text == "Appraiser" for n in p.iter(f"{M}PartyRoleType")))


def _dues_quarterly(root):
    for c in root.iter(f"{M}ASSOCIATION_CHARGE"):
        if c.findtext(f".//{M}AssociationChargeType") == "AssociationDues":
            _set(c, "AssociationChargePeriodType", "Quarterly")
            return


def _no_dues(root):
    for c in list(root.iter(f"{M}ASSOCIATION_CHARGE")):
        if c.findtext(f".//{M}AssociationChargeType") == "AssociationDues":
            _drop(c)


def _project_incomplete(root):
    _set(next(root.iter(f"{M}PROJECT_COMPONENT")), "ProjectComponentCompletedIndicator", "true")


def _no_trend(root):
    _drop_all(root, "PriceTrendsAnalysisDescription")
    _image_category(root, "PriceTrendGraph", "Other")


def _exposure_both(root):
    d = next(root.iter(f"{M}VALUATION_RECONCILIATION_SUMMARY_DETAIL"))
    _add(d, "MarketingOrExposureLowRangeDaysCount", "30")


def _exposure_none(root):
    _drop_all(root, "MarketingOrExposureDaysCount")


def _structure_analysis(root):
    return next(_subject(root).iter(f"{M}STRUCTURE_ANALYSIS_DETAIL"))


def _age_both(root):
    d = _structure_analysis(root)
    if d.find(f"{M}EffectiveAgeYearsCount") is None:
        _add(d, "EffectiveAgeYearsCount", "10")
    if d.find(f"{M}EffectiveAgeRangeLowYearsCount") is None:
        _add(d, "EffectiveAgeRangeLowYearsCount", "5")


def _age_none(root):
    for name in ("EffectiveAgeYearsCount", "EffectiveAgeRangeLowYearsCount", "EffectiveAgeRangeHighYearsCount"):
        _drop_all(_structure_analysis(root), name)


def _no_label(root):
    from lxml import etree
    for d in root.iter(f"{M}DEFECT_DETAIL"):
        for n in list(d.iter(f"{M}DefectComponentLabelType")):
            _drop(n)
        if d.getparent().get(f"{X}label") not in {
                r.get(f"{X}from") for r in root.iter(f"{M}RELATIONSHIP")
                if r.get(f"{X}arcrole", "").endswith(("_AMENITY", "_CAR_STORAGE"))}:
            return
    raise AssertionError("no defect outside amenities")


def _rename(scope, name, old, new):
    for n in scope.iter(f"{M}{name}"):
        if n.text == old:
            n.text = new


def _client_alone(root):
    for party in root.iter(f"{M}PARTY"):
        roles = list(party.iter(f"{M}PartyRoleType"))
        if any(n.text == "Client" for n in roles):
            for n in roles:
                n.text = "Client"


def _one_comp_drops_the_row(root):
    comp = next(p for p in root.iter(f"{M}PROPERTY") if p.get("ValuationUseType") == "SalesComparable")
    for a in list(comp.iter(f"{M}COMPARABLE_ADJUSTMENT")):
        if a.findtext(f"{M}AdditionalComparisonLineItemIdentifier"):
            _drop(a)


def _trend_source_unnamed(root):
    froms = {r.get(f"{X}from") for r in root.iter(f"{M}RELATIONSHIP")
             if r.get(f"{X}arcrole", "").endswith("DATA_SOURCE_IsDataSourceFor_MARKET_TREND")}
    for d in root.iter(f"{M}DATA_SOURCE"):
        if d.get(f"{X}label") in froms:
            _drop_all(d, "DataSourceName")


def _appraiser_inspection(root):
    return next(i for i in root.iter(f"{M}INSPECTION") if i.get(f"{X}label") == "INSPECTION_Appraiser")


def _second_inspection_detail(root):
    from copy import deepcopy
    d = _appraiser_inspection(root).find(f"{M}INSPECTION_DETAIL")
    d.addnext(deepcopy(d))


# mid -> (sample, how to break it)
BREAKS = {
    "UAD1034": ("sf1_appraisal_v1_4", lambda r: _subject(r).attrib.pop("ValuationUseType")),
    "UAD1043": ("sf1_appraisal_v1_4", lambda r: (_drop_all(r, "ParcelsLegalDescription"),
                                                   _image_category(r, "LegalDescription", "Other"))),
    "UAD1051": ("sf1_appraisal_v1_4", lambda r: (_set(_subject(r), "NewConstructionIndicator", "true"),
                                                   _set(_subject(r), "PropertyStructureBuiltYear", "1990"))),
    "UAD1053": ("sf1_appraisal_v1_4", lambda r: _set(_subject(r), "PropertyStructureBuiltYear", "2090")),
    "UAD1179": ("sf1_appraisal_v1_4", lambda r: _drop(next(r.iter(f"{M}DataSourceType")))),
    "UAD1237": ("mh1_appraisal_v1_4", lambda r: (
        _add(next(r.iter(f"{M}IMPROVEMENT_DEPRECIATION")), "DepreciationTotalAmount", "1000")
        if next(r.iter(f"{M}DepreciationTotalAmount"), None) is None else
        _add(next(r.iter(f"{M}IMPROVEMENT_DEPRECIATION")), "DepreciationPhysicalAmount", "1000"))),
    "UAD1255": ("sf1_appraisal_v1_4", lambda r: _drop_all(r, "PropertyValuationConditionalConclusionType")),
    "UAD1256": ("condo1_appraisal_v1_4", _second_condition),
    "UAD1274": ("sf1_appraisal_v1_4", lambda r: _image_category(r, "PropertyAccess", "Other")),
    "UAD1283": ("sf1_appraisal_v1_4", lambda r: _image_category(r, "SalesComparableMap", "Other")),
    "UAD1461": ("sf1_appraisal_v1_4", _comp_net),
    "UAD1529": ("sf1_appraisal_v1_4", lambda r: _set(_appraiser(r), "LicenseExpirationDate", "2000-01-01")),
    "UAD1533": ("sf1_appraisal_v1_4", lambda r: _set(_appraiser(r), "LicenseIssuingAuthorityStateCode", "ZZ")),
    "UAD1572": ("condo1_appraisal_v1_4", _no_dues),
    "UAD1574": ("condo1_appraisal_v1_4", _dues_quarterly),
    "UAD1605": ("coop1_appraisal_v1_4", _project_incomplete),
    "UAD1611": ("coop1_appraisal_v1_4", lambda r: _set(r, "TaxAbatementsOrExemptionsExpirationDate", "2000-01")),
    "UAD1656": ("sf1_appraisal_v1_4", _no_trend),
    "UAD1658": ("sf1_appraisal_v1_4", lambda r: _drop_arcs(r, "DATA_SOURCE_IsDataSourceFor_MARKET_TREND")),
    "UAD1685": ("sf1_appraisal_v1_4", _defect("SubjectPropertyAmenitiesDefectsExistIndicator", "DEFECT_ContainsDefectOf_AMENITY")),
    "UAD1686": ("sf1_appraisal_v1_4", _defect("VehicleStorageDefectsExistIndicator", "DEFECT_ContainsDefectOf_CAR_STORAGE")),
    "UAD1689": ("sf1_appraisal_v1_4", _defect("DwellingExteriorDefectsExistIndicator", "DEFECT_ContainsDefectOf_IMPROVEMENT")),
    "UAD1690": ("sf1_appraisal_v1_4", _defect("SiteDefectsExistIndicator", "DEFECT_ContainsDefectOf_SITE")),
    "UAD1691": ("sf1_appraisal_v1_4", _defect("UnitInteriorDefectsExistIndicator", "DEFECT_ContainsDefectOf_PROPERTY_UNIT")),
    "UAD1692": ("mh1_appraisal_v1_4", _defect("OutbuildingDefectsExistIndicator", "DEFECT_ContainsDefectOf_IMPROVEMENT")),
    "UAD1693": ("sf1_appraisal_v1_4", lambda r: _set(_subject(r), "LivingUnitExcludingADUCount", "3")),
    "UAD1695": ("mh1_appraisal_v1_4", _age_both),
    "UAD1696": ("mh1_appraisal_v1_4", _age_none),
    "UAD1715": ("sf1_appraisal_v1_4", _no_label),
    "UAD1717": ("sf1_appraisal_v1_4", _dup_arc),
    "UAD1718": ("sf1_appraisal_v1_4", _bad_arc("from")),
    "UAD1719": ("sf1_appraisal_v1_4", _bad_arc("to")),
    "UAD1730": ("sf3_appraisal_v1_4", lambda r: _set(next(
        i for i in _subject(r).iter(f"{M}IMPROVEMENT")
        if i.findtext(f"{M}IMPROVEMENT_DETAIL/{M}ImprovementType") == "Outbuilding"
        and i.find(f".//{M}AccessoryDwellingUnitIndicator") is not None), "AccessoryDwellingUnitIndicator", "false")),
    "UAD1733": ("condo1_appraisal_v1_4", _exposure_both),
    "UAD1746": ("condo1_appraisal_v1_4", _exposure_none),
    "UAD1763": ("2_to_4_unit_appraisal_v1_4", lambda r: [
        _drop(c) for c in list(r.iter(f"{M}VALUATION_COMMENTARY"))
        if c.findtext(f".//{M}ValuationAnalysisCategoryType") == "ComparableRental"]),
    "UAD1143": ("sf1_appraisal_v1_4", lambda r: _rename(_subject(r), "RoomType", "Kitchen", "Other")),
    "UAD1138": ("sf1_appraisal_v1_4", lambda r: _drop_all(_subject(r), "ACCESSIBILITY_FEATURE")),
    "UAD1228": ("mh1_appraisal_v1_4", lambda r: _drop_all(r, "DepreciatedCostOutbuildingsTotalAmount")),
    "UAD1239": ("mh1_appraisal_v1_4", lambda r: _drop_all(r, "DataSourceEffectiveDate")),
    "UAD1657": ("sf1_appraisal_v1_4", _trend_source_unnamed),
    "UAD1278": ("mh1_appraisal_v1_4", lambda r: _rename(_subject(r), "ImageCategoryType", "WaterFrontage", "Other")),
    "UAD1339": ("mh1_appraisal_v1_4", lambda r: _drop_all(_subject(r), "WaterFrontageTotalLengthLinearMeasure")),
    "UAD1353": ("sf1_appraisal_v1_4", lambda r: _rename(_subject(r), "SiteUtilityOwnershipType", "Public", "Private")),
    "UAD1455": ("sf1_appraisal_v1_4", _one_comp_drops_the_row),
    "UAD1543": ("sf1_appraisal_v1_4", _client_alone),
    "UAD1575": ("condo1_appraisal_v1_4", lambda r: _drop_all(_subject(r), "AssociationChargeIncludesUtilityType")),
    "UAD1698": ("condo1_appraisal_v1_4", lambda r: _drop_all(_subject(r), "OwnershipTransferTransactionAmount")),
    "UAD1520": ("sf1_appraisal_v1_4", lambda r: _set(r, "PropertyDataReportIndicator", "true")),
    "UAD1747": ("sf1_appraisal_v1_4", lambda r: _drop_arcs(r, "INSPECTION_CompletedBy_ROLE")),
    "UAD1268": ("sf1_appraisal_v1_4", _second_inspection_detail),
    "UAD1535": ("sf1_appraisal_v1_4", lambda r: _drop_all(r, "ExecutionDate")),
    "UAD1516": ("sf1_appraisal_v1_4", lambda r: _set(r, "ValuationReportInspectionCertificationType", "Exterior")),
    "UAD1517": ("condo1_appraisal_v1_4", lambda r: _set(r, "ValuationReportInspectionCertificationType", "Exterior")),
    "UAD1518": ("sf1_appraisal_v1_4", lambda r: _set(_appraiser_inspection(r), "PropertyInteriorInspectionMethodType", "NoInspection")),
    "UAD1279": ("sf1_appraisal_v1_4", lambda r: [
        _drop_all(room, "IMAGE") for room in _subject(r).iter(f"{M}ROOM")
        if room.findtext(f".//{M}RoomType") == "Kitchen"]),
    "UAD1304": ("sf1_appraisal_v1_4", lambda r: _rename(_subject(r), "ParcelIdentificationType",
                                                          "AssessorUnformattedIdentifier", "AlternativePropertyIdentifier")),
    "UAD1468": ("sf1_appraisal_v1_4", lambda r: [
        _drop_all(d, "DataSourceIdentifier") for d in r.iter(f"{M}DATA_SOURCE")
        if d.get(f"{X}label") == "DATA_SOURCE_MLSSalesComp1"]),
    "UAD1470": ("2_to_4_unit_appraisal_v1_4", lambda r: _drop_arcs(r, "PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT")),
    "UAD1029": ("mh1_appraisal_v1_4", lambda r: _set(_subject(r), "AppraisedIndicator", "true")),
}

#: no D-1 sample adds a row to the GRM grid; the test below builds one
UNDECIDED_ON_SAMPLES = {"UAD1250", "UAD1777", "UAD1778", "UAD1779"}


@pytest.mark.parametrize("mid,measure", [
    ("UAD1777", "UnitNonStandardBelowGradeFinishedAreaMeasure"),
    ("UAD1778", "UnitAboveGradeUnfinishedAreaMeasure"),
    ("UAD1779", "UnitNonStandardAboveGradeFinishedAreaMeasure"),
])
def test_a_subject_area_must_be_given_for_the_compared_comparable_unit(mid, measure):
    # no D-1 subject has these areas above zero; SF3 pairs its units by arc
    root = templates.load("sf3_appraisal_v1_4").getroot()
    rule = next(r for r in compliance.rules() if r.message_id == mid)
    assert cc.decide(root, rule) is None
    units = {u.get(f"{X}label"): u for u in root.iter(f"{M}PROPERTY_UNIT")}
    _set(units["PROPERTY_UNIT_SUBJECT_Primary"], measure, "120")
    assert cc.decide(root, rule) is True
    for label in ("PROPERTY_UNIT_COMP1_Primary", "PROPERTY_UNIT_COMP2_Primary", "PROPERTY_UNIT_COMP3_Primary"):
        area = units[label].find(f"{M}PROPERTY_UNIT_AREA")
        _add(area, measure, "0")
    assert cc.decide(root, rule) is False


def test_a_grm_row_must_be_on_every_grm_comparable():
    from lxml import etree
    root = templates.load("2_to_4_unit_appraisal_v1_4").getroot()
    rule = next(r for r in compliance.rules() if r.message_id == "UAD1250")
    assert cc.decide(root, rule) is None
    grm = [p for p in root.iter(f"{M}PROPERTY") if p.get("ValuationUseType") == "GrossRentMultiplierComparable"]

    def add_row(prop):
        comp = prop.find(f"{M}COMPARABLE")
        if comp is None:
            comp = etree.SubElement(prop, f"{M}COMPARABLE")
        adjs = comp.find(f"{M}COMPARABLE_ADJUSTMENTS")
        if adjs is None:
            adjs = etree.SubElement(comp, f"{M}COMPARABLE_ADJUSTMENTS")
        a = etree.SubElement(adjs, f"{M}COMPARABLE_ADJUSTMENT")
        _add(a, "AdditionalComparisonLineItemIdentifier", "View")
        _add(a, "ComparableAdjustmentType", "GrossRentMultiplierAdditionalNonAdjustableComparisonItem")

    add_row(grm[0])
    assert cc.decide(root, rule) is True
    for p in grm[1:] + [_subject(root)]:
        add_row(p)
    assert cc.decide(root, rule) is False


def test_every_check_has_a_break():
    assert sorted(set(BREAKS) | UNDECIDED_ON_SAMPLES) == sorted(cc.BY_ID)


@pytest.mark.parametrize("mid", sorted(BREAKS))
def test_each_check_fires_on_a_broken_sample(mid):
    key, brk = BREAKS[mid]
    root = templates.load(key).getroot()
    rule = next(r for r in compliance.rules() if r.message_id == mid)
    assert cc.decide(root, rule) is False
    brk(root)
    assert cc.decide(root, rule) is True


def test_checks_run_inside_evaluate():
    root = templates.load("sf1_appraisal_v1_4").getroot()
    _comp_net(root)
    hit = [f for f in compliance.evaluate(root) if f.message_id == "UAD1461"]
    assert hit and hit[0].status == compliance.FINDING
