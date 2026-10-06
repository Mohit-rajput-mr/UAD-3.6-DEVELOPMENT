"""H-1 rules too particular for a sentence shape, executed one by one.

``compliance_shapes`` reads rules by the shape of their Logic sentence.  The
rules here are written once each in H-1 (a sum across instances, a date
against the effective date, a label that must resolve), so each gets a
small function keyed by its Message ID.  The rule's own text is quoted
above each function; the function reads nothing H-1 does not name.

Every function answers True (the rule fires), False (it holds) or None (the
document does not let it decide), and every one is held by
tests/test_compliance_shapes.py to leaving the twelve D-1 samples alone and
to firing on a copy broken the way the rule describes.
"""
from __future__ import annotations

from collections import Counter

from . import bind

M = f"{{{bind.MISMO}}}"
X = "{http://www.w3.org/1999/xlink}"
ARC = "urn:fdc:mismo.org:2009:residential/"


def _t(node) -> str:
    return (node.text or "").strip() if node is not None else ""


def _all(scope, name):
    return [_t(n) for n in scope.iter(f"{M}{name}") if _t(n)]


def _first(scope, name) -> str:
    return next(iter(_all(scope, name)), "")


def _subject(root):
    return next((p for p in root.iter(f"{M}PROPERTY")
                 if p.get("ValuationUseType") == "SubjectProperty"), None)


def _num(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _effective(root) -> str:
    return _first(root, "AppraisalReportEffectiveDate")


def _arcs(root) -> list:
    return list(root.iter(f"{M}RELATIONSHIP"))


def _labels(root) -> set[str]:
    return {e.get(f"{X}label") for e in root.iter() if isinstance(e.tag, str) and e.get(f"{X}label")}


def _detail(block):
    return next((c for c in block if isinstance(c.tag, str) and c.tag.endswith("_DETAIL")), None)


def _improvements(prop, kind: str):
    for imp in prop.iter(f"{M}IMPROVEMENT"):
        d = imp.find(f"{M}IMPROVEMENT_DETAIL")
        if _t(d.find(f"{M}ImprovementType") if d is not None else None) == kind:
            yield imp, d


def _parties(root, *roles):
    for p in root.iter(f"{M}PARTY"):
        if any(r in roles for r in _all(p, "PartyRoleType")):
            yield p


# "If @ValuationUseType is not provided for one or more instances of PROPERTY"
# (its xPath: ../VALUATION_ANALYSIS/PROPERTIES/PROPERTY -- the inspection
# service's own PROPERTY carries no use type)
def uad1034(root):
    props = [p for a in root.iter(f"{M}VALUATION_ANALYSIS")
             for ps in a.findall(f"{M}PROPERTIES") for p in ps.findall(f"{M}PROPERTY")]
    return any(not p.get("ValuationUseType") for p in props) if props else None


# "If ImageCategoryType = "LegalDescription" is not provided in any instance of
# IMAGE, and ParcelsLegalDescription is not provided"
def uad1043(root):
    s = _subject(root)
    if s is None:
        return None
    return "LegalDescription" not in _all(root, "ImageCategoryType") and not _all(s, "ParcelsLegalDescription")


# "If NewConstructionIndicator = "true", and PropertyStructureBuiltYear is not
# the same year, or within 1 year of the AppraisalReportEffectiveDate, for one
# or more instances of IMPROVEMENT_DETAIL with ImprovementType = "Dwelling"."
def uad1051(root):
    s, eff = _subject(root), _effective(root)[:4]
    if s is None or not eff.isdigit():
        return None
    if _first(s, "NewConstructionIndicator") != "true":
        return False
    years = [_num(_first(imp, "PropertyStructureBuiltYear")) for imp, _ in _improvements(s, "Dwelling")]
    years = [y for y in years if y is not None]
    return any(abs(y - int(eff)) > 1 for y in years) if years else None


# "If ((ExteriorConditionRatingCode = "C1" and PropertyStructureBuiltYear >
# year of (AppraisalReportEffectiveDate) + 2 years) or (ExteriorConditionRatingCode
# <> "C1" and PropertyStructureBuiltYear > year of (AppraisalReportEffectiveDate))
# in a given instance of IMPROVEMENT_DETAIL with ImprovementType = "Dwelling""
def uad1053(root):
    s, eff = _subject(root), _effective(root)[:4]
    if s is None or not eff.isdigit():
        return None
    decided = False
    for imp, _ in _improvements(s, "Dwelling"):
        built = _num(_first(imp, "PropertyStructureBuiltYear"))
        if built is None:
            continue
        decided = True
        allowance = 2 if _first(imp, "ExteriorConditionRatingCode") == "C1" else 0
        if built > int(eff) + allowance:
            return True
    return False if decided else None


# "If at least one DataSourceType is not provided"
# The Price Trend Source is the exception: H-1 asks only its DataSourceName
# (UAD1657), and every D-1 sample gives it nothing else.
def uad1179(root):
    trend = {r.get(f"{X}from") for r in _arcs(root)
             if r.get(f"{X}arcrole") == ARC + "DATA_SOURCE_IsDataSourceFor_MARKET_TREND"}
    sources = [d for d in root.iter(f"{M}DATA_SOURCE") if d.get(f"{X}label") not in trend]
    return any(not _all(d, "DataSourceType") for d in sources) if sources else None


# "If DepreciationTotalAmount is provided, and (any of DepreciationExternalAmount,
# DepreciationFunctionalAmount, and DepreciationPhysicalAmount are also
# provided) in a given instance of IMPROVEMENT_COST_AND_DEPRECIATED_VALUE/
# IMPROVEMENT_DEPRECIATION"
def uad1237(root):
    blocks = list(root.iter(f"{M}IMPROVEMENT_DEPRECIATION"))
    if not blocks:
        return None
    parts = ("DepreciationExternalAmount", "DepreciationFunctionalAmount", "DepreciationPhysicalAmount")
    return any(_all(b, "DepreciationTotalAmount") and any(_all(b, p) for p in parts) for b in blocks)


# "If at least one instance of VALUATION_CONDITION is not provided or
# PropertyValuationConditionalConclusionType is not provided in a given
# instance of VALUATION_CONDITION"
def uad1255(root):
    conds = list(root.iter(f"{M}VALUATION_CONDITION"))
    return not conds or any(not _all(c, "PropertyValuationConditionalConclusionType") for c in conds)


# "If PropertyValuationConditionalConclusionType = "AsIs" and there are one or
# more additional instances of VALUATION_CONDITION"
def uad1256(root):
    conds = list(root.iter(f"{M}VALUATION_CONDITION"))
    if not conds:
        return None
    return any(_all(c, "PropertyValuationConditionalConclusionType") == ["AsIs"] for c in conds) and len(conds) > 1


# "If instances of IMAGE with ImageCategoryType = DwellingFront, PropertyAccess,
# and PropertyPhoto are not provided"
def uad1274(root):
    s = _subject(root)
    if s is None:
        return None
    held = set(_all(s, "ImageCategoryType"))
    return not {"DwellingFront", "PropertyAccess", "PropertyPhoto"} <= held


# "If SalesComparisonApproachIndicator = "true" and there is no instance of IMAGE
# with ImageCategoryType = "SalesComparableMap" in @ValuationUseType =
# "SubjectProperty""
def uad1283(root):
    s = _subject(root)
    if s is None:
        return None
    if _first(root, "SalesComparisonApproachIndicator") != "true":
        return False
    return "SalesComparableMap" not in _all(s, "ImageCategoryType")


def _adjustments_sum(comp) -> float:
    return sum(_num(v) or 0 for v in _all(comp, "ComparableAdjustmentAmount"))


# "If @ValuationUseType = "SalesComparable" and SalePriceNetTotalAdjustmentAmount
# does not equal the sum of ComparableAdjustmentAmount across all instances of
# COMPARABLE_ADJUSTMENT"
def uad1461(root):
    decided = False
    for p in root.iter(f"{M}PROPERTY"):
        if p.get("ValuationUseType") != "SalesComparable":
            continue
        net = _num(_first(p, "SalePriceNetTotalAdjustmentAmount"))
        if net is None:
            continue
        decided = True
        if abs(net - _adjustments_sum(p)) > 0.5:
            return True
    return False if decided else None


# "If LicenseExpirationDate for PartyRoleType = "Appraiser" and/or
# "AppraiserSupervisor" < AppraisalReportEffectiveDate"
def uad1529(root):
    eff = _effective(root)
    dates = [d for p in _parties(root, "Appraiser", "AppraiserSupervisor") for d in _all(p, "LicenseExpirationDate")]
    if not eff or not dates:
        return None
    return any(d < eff for d in dates)


# "If LicenseIssuingAuthorityStateCode for PartyRoleType = "Appraiser" or
# "AppraiserSupervisor" <> StateCode (PROPERTY/ADDRESS with @ValuationUseType =
# "SubjectProperty")"
def uad1533(root):
    s = _subject(root)
    addr = s.find(f"{M}ADDRESS") if s is not None else None
    state = _first(addr, "StateCode") if addr is not None else ""
    codes = [c for p in _parties(root, "Appraiser", "AppraiserSupervisor")
             for c in _all(p, "LicenseIssuingAuthorityStateCode")]
    if not state or not codes:
        return None
    return any(c != state for c in codes)


# "IF PropertyInProjectIndicator = "true" or PUDIndicator = "true", and there is
# no instance of ASSOCIATION_CHARGE with AssociationChargeType = "AssociationDues""
def uad1572(root):
    s = _subject(root)
    if s is None:
        return None
    if "true" not in (_first(s, "PropertyInProjectIndicator"), _first(s, "PUDIndicator")):
        return False
    return not any(_first(c, "AssociationChargeType") == "AssociationDues"
                   for c in s.iter(f"{M}ASSOCIATION_CHARGE"))


# "If AssociationChargeType = "AssociationDues", and AssociationChargePeriodType
# is either not provided, or not = "Monthly" in the given instance of
# ASSOCIATION_CHARGE"
def uad1574(root):
    dues = [c for c in root.iter(f"{M}ASSOCIATION_CHARGE") if _first(c, "AssociationChargeType") == "AssociationDues"]
    if not dues:
        return None
    return any(_first(c, "AssociationChargePeriodType") != "Monthly" for c in dues)


# "If ProjectCompletedIndicator = "false" and ProjectComponentCompletedIndicator
# is not = "false" in a given instance of PROJECT_COMPONENT"
def uad1605(root):
    if _first(root, "ProjectCompletedIndicator") != "false":
        return None if not _all(root, "ProjectCompletedIndicator") else False
    return any(_first(c, "ProjectComponentCompletedIndicator") != "false"
               for c in root.iter(f"{M}PROJECT_COMPONENT"))


# "If TaxAbatementsOrExemptionsExpirationDate < YYYY-MM of AppraisalReportEffectiveDate"
def uad1611(root):
    eff = _effective(root)[:7]
    dates = _all(root, "TaxAbatementsOrExemptionsExpirationDate")
    if not eff or not dates:
        return None
    return any(d[:7] < eff for d in dates)


# "If PriceTrendsAnalysisDescription is not provided, and ImageCategoryType =
# "PriceTrendGraph" is not provided in any instance of IMAGE"
def uad1656(root):
    return not _all(root, "PriceTrendsAnalysisDescription") and "PriceTrendGraph" not in _all(root, "ImageCategoryType")


# "If there is no instance of RELATIONSHIP with @xlink:arcrole =
# ".../DATA_SOURCE_IsDataSourceFor_MARKET_TREND" linking DATA_SOURCE to
# MARKET_TREND where @ValuationUseType = "SubjectProperty""
def uad1658(root):
    if next(root.iter(f"{M}MARKET_TREND"), None) is None:
        return None
    return not any(r.get(f"{X}arcrole") == ARC + "DATA_SOURCE_IsDataSourceFor_MARKET_TREND" for r in _arcs(root))


def _defect_arc(indicator: str, arc: str):
    def check(root):
        s = _subject(root)
        if s is None:
            return None
        if _first(s, indicator) != "true":
            return False
        return not any(r.get(f"{X}arcrole") == ARC + arc for r in _arcs(root))
    return check


# "If @ValuationUseType = "SubjectProperty" and <X>DefectsExistIndicator = "true",
# and there is no instance of RELATIONSHIP with @xlink:arcrole =
# ".../DEFECT_ContainsDefectOf_<Y>" linking DEFECT to <Y>"
uad1685 = _defect_arc("SubjectPropertyAmenitiesDefectsExistIndicator", "DEFECT_ContainsDefectOf_AMENITY")
uad1686 = _defect_arc("VehicleStorageDefectsExistIndicator", "DEFECT_ContainsDefectOf_CAR_STORAGE")
uad1689 = _defect_arc("DwellingExteriorDefectsExistIndicator", "DEFECT_ContainsDefectOf_IMPROVEMENT")
uad1690 = _defect_arc("SiteDefectsExistIndicator", "DEFECT_ContainsDefectOf_SITE")
uad1691 = _defect_arc("UnitInteriorDefectsExistIndicator", "DEFECT_ContainsDefectOf_PROPERTY_UNIT")
uad1692 = _defect_arc("OutbuildingDefectsExistIndicator", "DEFECT_ContainsDefectOf_IMPROVEMENT")


# "If AccessoryDwellingUnitTotalCount plus LivingUnitExcludingADUCount does not
# equal the sum of LivingUnitCount across all instances of STRUCTURE_DETAIL"
def uad1693(root):
    s = _subject(root)
    if s is None:
        return None
    adu, units = _num(_first(s, "AccessoryDwellingUnitTotalCount")), _num(_first(s, "LivingUnitExcludingADUCount"))
    counts = [_num(_first(d, "LivingUnitCount")) for d in s.iter(f"{M}STRUCTURE_DETAIL")]
    counts = [c for c in counts if c is not None]
    if adu is None or units is None or not counts:
        return None
    return adu + units != sum(counts)


def _effective_age(both: bool):
    def check(root):
        s = _subject(root)
        if s is None or _first(root, "CostApproachIndicator") != "true":
            return None if s is None else False
        decided = False
        for imp, _ in _improvements(s, "Dwelling"):
            for d in imp.iter(f"{M}STRUCTURE_ANALYSIS_DETAIL"):
                decided = True
                age = bool(_all(d, "EffectiveAgeYearsCount"))
                low, high = bool(_all(d, "EffectiveAgeRangeLowYearsCount")), bool(_all(d, "EffectiveAgeRangeHighYearsCount"))
                if both and age and (low or high):
                    return True
                if not both and not age and not (low and high):
                    return True
        return False if decided else None
    return check


# "If CostApproachIndicator = "true" and ImprovementType = "Dwelling" and
# EffectiveAgeYearsCount is provided, and (either or both of
# EffectiveAgeRangeLowYearsCount or EffectiveAgeRangeHighYearsCount is provided)
# in a given instance of STRUCTURE_ANALYSIS_DETAIL"
uad1695 = _effective_age(True)
# "... EffectiveAgeYearsCount is not provided, and (either
# EffectiveAgeRangeLowYearsCount or EffectiveAgeRangeHighYearsCount is not
# provided) in a given instance of STRUCTURE_ANALYSIS_DETAIL"
uad1696 = _effective_age(False)


def _exposure(both: bool):
    def check(root):
        blocks = [b for b in root.iter(f"{M}VALUATION_RECONCILIATION_SUMMARY_DETAIL")]
        if not blocks:
            return None
        for b in blocks:
            days = bool(_all(b, "MarketingOrExposureDaysCount"))
            low = bool(_all(b, "MarketingOrExposureLowRangeDaysCount"))
            high = bool(_all(b, "MarketingOrExposureHighRangeDaysCount"))
            if both and days and (low or high):
                return True
            if not both and not days and not (low and high):
                return True
        return False
    return check


# "If MarketingOrExposureDaysCount is provided, and (either or both of
# MarketingOrExposureLowRangeDaysCount or MarketingOrExposureHighRangeDaysCount
# is provided)"
uad1733 = _exposure(True)
# "If MarketingOrExposureDaysCount is not provided, and (either
# MarketingOrExposureLowRangeDaysCount or MarketingOrExposureHighRangeDaysCount
# is not provided)"
uad1746 = _exposure(False)


# "If DefectComponentLabelType is not provided in a given instance of
# DEFECT_DETAIL that is not associated with AMENTIY or CAR_STORAGE"
def uad1715(root):
    defects = list(root.iter(f"{M}DEFECT"))
    if not defects:
        return None
    exempt = {r.get(f"{X}from") for r in _arcs(root)
              if r.get(f"{X}arcrole") in (ARC + "DEFECT_ContainsDefectOf_AMENITY",
                                          ARC + "DEFECT_ContainsDefectOf_CAR_STORAGE")}
    for d in defects:
        if d.get(f"{X}label") in exempt:
            continue
        detail = d.find(f"{M}DEFECT_DETAIL")
        if detail is not None and not _all(detail, "DefectComponentLabelType"):
            return True
    return False


# "If the 'xlink:arcrole', 'xlink:from', and 'xlink:to' labels are not unique
# across all instances of RELATIONSHIP"
def uad1717(root):
    arcs = _arcs(root)
    if not arcs:
        return None
    seen = Counter((r.get(f"{X}arcrole"), r.get(f"{X}from"), r.get(f"{X}to")) for r in arcs)
    return any(n > 1 for n in seen.values())


def _resolves(end: str):
    def check(root):
        arcs = _arcs(root)
        if not arcs:
            return None
        labels = _labels(root)
        return any(r.get(f"{X}{end}") not in labels for r in arcs)
    return check


# "If the associated container does not have the xlink:from label specified in
# a given instance of RELATIONSHIP"
uad1718 = _resolves("from")
# "If the associated container or data element does not have the xlink:to label
# specified in a given instance of RELATIONSHIP"
uad1719 = _resolves("to")


# "If AccessoryDwellingUnitIndicator = "false" for a given instance of
# PROPERTY_UNIT_DETAIL in IMPROVEMENT with ImprovementType = "Outbuilding""
def uad1730(root):
    decided = False
    for p in root.iter(f"{M}PROPERTY"):
        for imp, _ in _improvements(p, "Outbuilding"):
            for d in imp.iter(f"{M}PROPERTY_UNIT_DETAIL"):
                v = _first(d, "AccessoryDwellingUnitIndicator")
                if v:
                    decided = True
                    if v == "false":
                        return True
    return False if decided else None


# "If RentScheduleIndicator = "true" and there is no instance of
# VALUATION_COMMENTARY with ValuationAnalysisCategoryType = "ComparableRental"
# and ValuationCommentText"
def uad1763(root):
    if _first(root, "RentScheduleIndicator") != "true":
        return None if not _all(root, "RentScheduleIndicator") else False
    return not any(_first(c, "ValuationAnalysisCategoryType") == "ComparableRental"
                   and _all(c, "ValuationCommentText") for c in root.iter(f"{M}VALUATION_COMMENTARY"))


def _living_improvements(prop):
    """Dwellings, and outbuildings that are real property holding an ADU --
    the improvements H-1 asks rooms and features of."""
    for imp in prop.iter(f"{M}IMPROVEMENT"):
        d = imp.find(f"{M}IMPROVEMENT_DETAIL")
        kind = _t(d.find(f"{M}ImprovementType")) if d is not None else ""
        if kind == "Dwelling":
            yield imp
        elif (kind == "Outbuilding" and _first(d, "OutbuildingRealPropertyIndicator") == "true"
              and "true" in _all(imp, "AccessoryDwellingUnitIndicator")):
            yield imp


# "If (ImprovementType = "Dwelling" or (ImprovementType = "Outbuilding" and
# OutbuildingRealPropertyIndicator = "true" and AccessoryDwellingUnitIndicator =
# "true")), and (at least one instance of ROOM_DETAIL with RoomType = "Kitchen"
# is not provided)"
def uad1143(root):
    s = _subject(root)
    imps = list(_living_improvements(s)) if s is not None else []
    if not imps:
        return None
    return any("Kitchen" not in _all(i, "RoomType") for i in imps)


# "... and If (at least one instance of ACCESSIBILITY_FEATURE is not provided or
# AccessibilityFeatureType is not provided in a given instance of
# ACCESSIBILITY_FEATURE)"
def uad1138(root):
    s = _subject(root)
    imps = list(_living_improvements(s)) if s is not None else []
    if not imps:
        return None
    for i in imps:
        feats = list(i.iter(f"{M}ACCESSIBILITY_FEATURE"))
        if not feats or any(not _all(f, "AccessibilityFeatureType") for f in feats):
            return True
    return False


# "If CostApproachIndicator = "true" and DepreciatedCostOutbuildingsTotalAmount
# is not provided when there are one or more instances of IMPROVEMENT_DETAIL with
# ImprovementType = "Outbuilding" and OutbuildingRealPropertyIndicator = "true""
def uad1228(root):
    s = _subject(root)
    if s is None:
        return None
    if _first(root, "CostApproachIndicator") != "true":
        return False
    real = [d for _, d in _improvements(s, "Outbuilding") if _first(d, "OutbuildingRealPropertyIndicator") == "true"]
    return bool(real) and not _all(root, "DepreciatedCostOutbuildingsTotalAmount")


def _linked_sources(root, arc: str) -> list:
    froms = {r.get(f"{X}from") for r in _arcs(root) if r.get(f"{X}arcrole") == ARC + arc}
    return [d for d in root.iter(f"{M}DATA_SOURCE") if d.get(f"{X}label") in froms]


# "If CostApproachIndicator = "true", and (DataSourceType = "BuilderOrDeveloper"
# or "CostService" or "CostSurvey" or "Other"), and DataSourceEffectiveDate is
# not provided in the instance of DATA_SOURCE that is related to cost approach"
def uad1239(root):
    if _first(root, "CostApproachIndicator") != "true":
        return None if not _all(root, "CostApproachIndicator") else False
    kinds = {"BuilderOrDeveloper", "CostService", "CostSurvey", "Other"}
    return any(_first(d, "DataSourceType") in kinds and not _all(d, "DataSourceEffectiveDate")
               for d in _linked_sources(root, "DATA_SOURCE_IsDataSourceFor_COST_APPROACH"))


# "If DataSourceName is not provided in a given instance of DATA_SOURCE that
# captures the Price Trend Source"
def uad1657(root):
    sources = _linked_sources(root, "DATA_SOURCE_IsDataSourceFor_MARKET_TREND")
    return any(not _all(d, "DataSourceName") for d in sources) if sources else None


def _private_water(root):
    s = _subject(root)
    if s is None:
        return None, []
    return s, [b for b in s.iter(f"{M}BODY_OF_WATER") if _first(b, "PrivateAccessIndicator") == "true"]


# "If PrivateAccessIndicator = "true" for any instance of BODY_OF_WATER where the
# SiteInfluenceType = "BodyOfWater" and there is no instance of IMAGE with
# ImageCategoryType = "WaterFrontage""
def uad1278(root):
    s, private = _private_water(root)
    if s is None:
        return None
    return bool(private) and "WaterFrontage" not in _all(s, "ImageCategoryType")


# "If PrivateAccessIndicator = "true" for one or more instances of BODY_OF_WATER
# and WaterFrontageTotalLengthLinearMeasure is not provided in a given instance
# of SITE_INFLUENCE_DETAIL with SiteInfluenceType = "BodyOfWater""
def uad1339(root):
    s, private = _private_water(root)
    if s is None:
        return None
    if not private:
        return False
    details = [d for d in s.iter(f"{M}SITE_INFLUENCE_DETAIL") if _first(d, "SiteInfluenceType") == "BodyOfWater"]
    return any(not _all(d, "WaterFrontageTotalLengthLinearMeasure") for d in details) if details else True


# "If there are no instances of SITE_UTILITY_DETAIL with UtilityType =
# "Electricity" and SiteUtilityOwnershipType = "Public""
def uad1353(root):
    s = _subject(root)
    details = list(s.iter(f"{M}SITE_UTILITY_DETAIL")) if s is not None else []
    if not details:
        return None
    return not any(_first(d, "UtilityType") == "Electricity" and _first(d, "SiteUtilityOwnershipType") == "Public"
                   for d in details)


def _matching_rows(kinds: set[str], use: str):
    def check(root):
        props = [p for p in root.iter(f"{M}PROPERTY") if p.get("ValuationUseType") in (use, "SubjectProperty")]
        def rows(p):
            return {(_first(a, "ComparableAdjustmentType"), _first(a, "AdditionalComparisonLineItemIdentifier"))
                    for a in p.iter(f"{M}COMPARABLE_ADJUSTMENT")
                    if _first(a, "ComparableAdjustmentType") in kinds}
        held = {p: rows(p) for p in props}
        every = set().union(*held.values()) if held else set()
        if not every:
            return None
        comps = [p for p in props if p.get("ValuationUseType") == use]
        if not comps:
            return None
        return any(held[p] != every for p in props)
    return check


# "For each combination of ComparableAdjustmentType =
# ("SalesComparableAdditionalAdjustableComparisonItem" or
# "SalesComparableAdditionalNonAdjustableComparisonItem") and
# AdditionalComparisonLineItemIdentifier, if there are not matching occurrences
# of COMPARABLE_ADJUSTMENT across all instances of PROPERTY with
# @ValuationUseType = "SalesComparable", and the instance of PROPERTY with
# @ValuationUseType = "SubjectProperty"."
uad1455 = _matching_rows({"SalesComparableAdditionalAdjustableComparisonItem",
                          "SalesComparableAdditionalNonAdjustableComparisonItem"}, "SalesComparable")
# the same for "GrossRentMultiplierAdditionalNonAdjustableComparisonItem"
uad1250 = _matching_rows({"GrossRentMultiplierAdditionalNonAdjustableComparisonItem"},
                         "GrossRentMultiplierComparable")


# "If PartyRoleType = "Client" and there is not a second instance of ROLE_DETAIL
# in the Client instance of PARTY with PartyRoleType = "Attorney" or "Investor"
# or "Lender" or "ManagementCompany" or "Other""
def uad1543(root):
    clients = list(_parties(root, "Client"))
    if not clients:
        return None
    second = {"Attorney", "Investor", "Lender", "ManagementCompany", "Other"}
    return any(not second & set(_all(p, "PartyRoleType")) for p in clients)


# "If AssociationChargeType = "AssociationDues" and (at least one instance of
# ASSOCIATION_CHARGE_INCLUDES_UTILITY is not provided or
# AssociationChargeIncludesUtilityType is not provided in the given instance of
# ASSOCIATION_CHARGE_INCLUDES_UTILITY)"
def uad1575(root):
    s = _subject(root)
    dues = [c for c in (s.iter(f"{M}ASSOCIATION_CHARGE") if s is not None else [])
            if _first(c, "AssociationChargeType") == "AssociationDues"]
    if not dues:
        return None
    for c in dues:
        utils = list(c.iter(f"{M}ASSOCIATION_CHARGE_INCLUDES_UTILITY"))
        if not utils or any(not _all(u, "AssociationChargeIncludesUtilityType") for u in utils):
            return True
    return False


# "If PriorSalesOrTransfersIndicator = "true" and ((OwnershipTransferTransactionAmount
# and OwnershipTransferAmountNotAvailableReasonType are not provided) or
# (OwnershipTransferTransactionAmount and OwnershipTransferAmountNotAvailableReasonType
# are provided))" -- one or the other, per SALES_HISTORY
def uad1698(root):
    s = _subject(root)
    if s is None:
        return None
    if _first(s, "PriorSalesOrTransfersIndicator") != "true":
        return False
    sales = list(s.iter(f"{M}SALES_HISTORY"))
    if not sales:
        return None
    return any(bool(_all(h, "OwnershipTransferTransactionAmount"))
               == bool(_all(h, "OwnershipTransferAmountNotAvailableReasonType")) for h in sales)


# "If PropertyDataReportIndicator = "true" and there is no instance of
# ROLE_DETAIL with PartyRoleType = "PropertyDataCollector" in SERVICE container
# with ServiceType = "Inspection""
def uad1520(root):
    if _first(root, "PropertyDataReportIndicator") != "true":
        return None if not _all(root, "PropertyDataReportIndicator") else False
    return not any("Inspection" in _all(svc, "ServiceType") and "PropertyDataCollector" in _all(svc, "PartyRoleType")
                   for svc in root.iter(f"{M}SERVICE"))


def _appraiser_roles(root, *kinds):
    kinds = kinds or ("Appraiser", "AppraiserSupervisor")
    return [r for r in root.iter(f"{M}ROLE") if set(_all(r, "PartyRoleType")) & set(kinds)]


def _linked(root, arc: str, label) -> list:
    """The labels linked by ``arc`` to the role labelled ``label``."""
    return [r.get(f"{X}from") for r in _arcs(root)
            if r.get(f"{X}arcrole") == ARC + arc and label and r.get(f"{X}to") == label]


def _labelled(root, tag: str) -> dict:
    return {e.get(f"{X}label"): e for e in root.iter(f"{M}{tag}") if e.get(f"{X}label")}


# "If PartyRoleType = "Appraiser" or "AppraiserSupervisor" and there is no
# instance of RELATIONSHIP provided for each role that links INSPECTION to the
# associated ROLE."
def uad1747(root):
    roles = _appraiser_roles(root)
    if not roles:
        return None
    return any(not _linked(root, "INSPECTION_CompletedBy_ROLE", r.get(f"{X}label")) for r in roles)


# "If PartyRoleType = "Appraiser" or "AppraiserSupervisor" and (no instance of
# INSPECTION_DETAIL is provided for each role or more than one instance of
# INSPECTION_DETAIL is provided for each role)"
def uad1268(root):
    roles = _appraiser_roles(root)
    if not roles:
        return None
    inspections = _labelled(root, "INSPECTION")
    for r in roles:
        linked = [inspections[l] for l in _linked(root, "INSPECTION_CompletedBy_ROLE", r.get(f"{X}label"))
                  if l in inspections]
        if sum(len(i.findall(f"{M}INSPECTION_DETAIL")) for i in linked) != 1:
            return True
    return False


# "If ExecutionDate is not provided for PartyRoleType = ("AppraiserSupervisor" or
# "Appraiser") or more than one instance of ExecutionDate is provided for
# PartyRoleType = ("AppraiserSupervisor" or "Appraiser")"
def uad1535(root):
    roles = _appraiser_roles(root)
    if not roles:
        return None
    signatories = _labelled(root, "SIGNATORY")
    for r in roles:
        linked = [signatories[l] for l in _linked(root, "SIGNATORY_IsAssociatedWith_ROLE", r.get(f"{X}label"))
                  if l in signatories]
        if sum(len(_all(sg, "ExecutionDate")) for sg in linked) != 1:
            return True
    return False


_REMOTE = {"Virtual", "NoInspection"}


def _certification(interior: set, exterior: set, certified: str):
    def check(root):
        cert = _first(root, "ValuationReportInspectionCertificationType")
        roles = _appraiser_roles(root, "Appraiser")
        if not cert or not roles:
            return None
        inspections = _labelled(root, "INSPECTION")
        decided = False
        for r in roles:
            for label in _linked(root, "INSPECTION_CompletedBy_ROLE", r.get(f"{X}label")):
                i = inspections.get(label)
                if i is None:
                    continue
                inside, outside = _first(i, "PropertyInteriorInspectionMethodType"), _first(i, "PropertyExteriorInspectionMethodType")
                if not inside or not outside:
                    continue
                decided = True
                if inside in interior and outside in exterior and cert != certified:
                    return True
        return False if decided else None
    return check


# "If PropertyInteriorInspectionMethodType = "Physical" and
# PropertyExteriorInspectionMethodType = "Physical" for PartyRoleType =
# "Appraiser", and ValuationReportInspectionCertificationType <> "InteriorAndExterior""
uad1516 = _certification({"Physical"}, {"Physical"}, "InteriorAndExterior")
# "If (PropertyInteriorInspectionMethodType = "Virtual" or "NoInspection" and
# PropertyExteriorInspectionMethodType = "Virtual" or "NoInspection" for
# PartyRoleType = "Appraiser"), and ValuationReportInspectionCertificationType <>
# "NoPhysicalInspection""
uad1517 = _certification(_REMOTE, _REMOTE, "NoPhysicalInspection")
# "If (PropertyInteriorInspectionMethodType = "Virtual" or "NoInspection" and
# PropertyExteriorInspectionMethodType = "Physical" for PartyRoleType =
# "Appraiser"), and ValuationReportInspectionCertificationType <> "Exterior""
uad1518 = _certification(_REMOTE, {"Physical"}, "Exterior")


# "If PropertyValuationMethodType <> "ExteriorAppraisal" and
# (NewConstructionIndicator <> "true" or PropertyValuationConditionalConclusionType
# <> "SubjectToCompletionPerPlans") and there is no instance of IMAGE in a given
# instance of ROOM with RoomType = ("Kitchen" or "HalfBathroom" or "FullBathroom")"
def uad1279(root):
    s = _subject(root)
    if s is None:
        return None
    if _first(root, "PropertyValuationMethodType") == "ExteriorAppraisal":
        return False
    if (_first(s, "NewConstructionIndicator") == "true"
            and "SubjectToCompletionPerPlans" in _all(root, "PropertyValuationConditionalConclusionType")):
        return False
    rooms = [r for r in s.iter(f"{M}ROOM")
             if _first(r, "RoomType") in ("Kitchen", "HalfBathroom", "FullBathroom")]
    if not rooms:
        return None
    return any(next(r.iter(f"{M}IMAGE"), None) is None for r in rooms)


# "If PropertyInProjectIndicator = "false" or (PropertyInProjectIndicator =
# "true" and ProjectLegalStructureType = "Condominium"), and at least one
# instance of PARCEL container with ParcelIdentificationType =
# "AssessorUnformattedIdentifier" is not provided ..."
def uad1304(root):
    s = _subject(root)
    if s is None:
        return None
    project = _first(s, "PropertyInProjectIndicator")
    if not project:
        return None
    if project == "true" and _first(s, "ProjectLegalStructureType") != "Condominium":
        return False
    return "AssessorUnformattedIdentifier" not in _all(s, "ParcelIdentificationType")


# "If DataSourceIdentifier is not provided in a given instance of DATA_SOURCE
# with DataSourceType = "MLS" that has arc role to PROPERTY container with
# @ValuationUseType <> ("SubjectProperty" or "PropertyAnalyzedNotUsed")"
def uad1468(root):
    labels = {e.get(f"{X}label"): e for e in root.iter()
              if isinstance(e.tag, str) and e.get(f"{X}label")}
    mls = {d.get(f"{X}label"): d for d in root.iter(f"{M}DATA_SOURCE")
           if _first(d, "DataSourceType") == "MLS" and d.get(f"{X}label")}
    decided = False
    for r in _arcs(root):
        src = mls.get(r.get(f"{X}from"))
        prop = labels.get(r.get(f"{X}to"))
        if src is None or prop is None or prop.tag != f"{M}PROPERTY":
            continue
        if prop.get("ValuationUseType") in ("SubjectProperty", "PropertyAnalyzedNotUsed"):
            continue
        decided = True
        if not _all(src, "DataSourceIdentifier"):
            return True
    return False if decided else None


def _multi_unit(prop) -> bool:
    units, adu = _num(_first(prop, "LivingUnitExcludingADUCount")), _num(_first(prop, "AccessoryDwellingUnitTotalCount"))
    return (units or 0) > 1 or (adu or 0) > 0


# "If (@ValuationUseType = "SubjectProperty" and (LivingUnitExcludingADUCount > 1
# or AccessoryDwellingUnitTotalCount > 0)) and (@ValuationUseType =
# "SalesComparable" and (...)), and there is not an instance of RELATIONSHIP
# with @xlink:arcrole = .../PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT"
def uad1470(root):
    s = _subject(root)
    if s is None:
        return None
    comps = [p for p in root.iter(f"{M}PROPERTY") if p.get("ValuationUseType") == "SalesComparable"]
    if not (_multi_unit(s) and any(_multi_unit(c) for c in comps)):
        return False
    return not any(r.get(f"{X}arcrole") == ARC + "PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT" for r in _arcs(root))


def _compared_area(measure: str):
    def check(root):
        s = _subject(root)
        if s is None:
            return None
        labels = {e.get(f"{X}label"): e for e in root.iter(f"{M}PROPERTY_UNIT") if e.get(f"{X}label")}
        pairs = [(labels.get(r.get(f"{X}from")), labels.get(r.get(f"{X}to"))) for r in _arcs(root)
                 if r.get(f"{X}arcrole") == ARC + "PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT"]
        pairs = [(c, u) for c, u in pairs if c is not None and u is not None]
        if not pairs:
            # one unit each: the comparable's unit is compared with the subject's
            units = list(s.iter(f"{M}PROPERTY_UNIT"))
            if len(units) != 1:
                return None
            pairs = [(cu, units[0]) for p in root.iter(f"{M}PROPERTY")
                     if p.get("ValuationUseType") == "SalesComparable"
                     for cu in list(p.iter(f"{M}PROPERTY_UNIT"))[:1]]
        decided = False
        for comp_unit, subject_unit in pairs:
            if (_num(_first(subject_unit, measure)) or 0) <= 0:
                continue
            decided = True
            if not _all(comp_unit, measure):
                return True
        return False if decided else None
    return check


# "... ((<measure> > 0 for @ValuationUseType = "SubjectProperty") and <measure>
# is not provided in the comparable instance of PROPERTY_UNIT_AREA that was
# compared with the subject unit)"
uad1777 = _compared_area("UnitNonStandardBelowGradeFinishedAreaMeasure")
uad1778 = _compared_area("UnitAboveGradeUnfinishedAreaMeasure")
uad1779 = _compared_area("UnitNonStandardAboveGradeFinishedAreaMeasure")


# "If AppraisedIndicator is not "false" in a given instance of
# REAL_PROPERTY_INTEREST" -- its Message Text: "Deliver this indicator as false
# for each ownership right that is not included in the appraisal" (the block
# lists the rights left out)
def uad1029(root):
    s = _subject(root)
    rights = list(s.iter(f"{M}REAL_PROPERTY_INTEREST")) if s is not None else []
    if not rights:
        return None
    return any(_first(r, "AppraisedIndicator") != "false" for r in rights)


BY_ID = {f"UAD{name[3:]}": fn for name, fn in list(globals().items())
         if name.startswith("uad") and name[3:].isdigit() and callable(fn)}


def decide(root, rule) -> bool | None | str:
    """The rule's own check, or the string "none" when it has none."""
    fn = BY_ID.get(rule.message_id)
    return fn(root) if fn else "none"
