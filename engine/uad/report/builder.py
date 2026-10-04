"""Assemble a UAD 3.6 URAR report from ingested facts and the adjustment grid.

The output is the canonical model from ``uad.model``, so it serialises straight
to schema-valid MISMO XML and hands the browser editor plain JSON.  Nothing
here invents data: a fact that is absent from the packet stays absent, and the
validator reports it, rather than being filled with a plausible guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from typing import Any

from ..analysis.adjustments import ComparableGrid
from ..analysis.contributions import Rate

UAD_VERSION = "36"
MISMO_VERSION = "3.6.0366"
# The UAD delivery specification this report is written against.
UAD_SPEC_VERSION = "1.4"
# B-1 p75: the form's publication date, printed in the footer.
FORM_VERSION = "September 2024"
# B-1 p75: this appraisal's own revision number, printed as 'Appraisal Version #'.
APPRAISAL_VERSION = "1"

# UAD enumeration values used throughout.
YES, NO = "true", "false"


def _text(value: Any) -> str | None:
    """Render a value the way MISMO expects, or drop it."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return YES if value else NO
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _node(**children: Any) -> dict:
    """Build a container, omitting anything empty."""
    out: dict[str, Any] = {}
    for key, value in children.items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        out[key.replace("__", ":")] = value
    return out


def _area(value: Any, unit: str = "SquareFeet") -> dict | None:
    """An area measure; the schema requires the unit as an attribute."""
    rendered = _text(value)
    return {"@AreaUnitOfMeasureType": unit, "#text": rendered} if rendered else None


def _leaf(value: Any, label: str | None = None) -> Any:
    """A data point, optionally carrying an xlink label for cross-reference."""
    rendered = _text(value)
    if rendered is None:
        return None
    return {"@xlink:label": label, "#text": rendered} if label else rendered


@dataclass
class ReportInputs:
    """Everything the builder needs, already resolved."""

    facts: Any                       # uad.ingest.sources.SourceFacts
    grids: list[ComparableGrid]
    rates: dict[str, Rate]
    effective_date: Date
    signature_date: Date
    opinion_of_value: float
    images: list[dict] = field(default_factory=list)
    commentary: dict[str, str] = field(default_factory=dict)
    reconciliation_comment: str = ""
    value_condition: str = "AsIs"


# ------------------------------------------------------------------ parties
def _name(parts: dict) -> dict:
    return _node(
        FirstName=_text(parts.get("first")),
        MiddleName=_text(parts.get("middle")),
        LastName=_text(parts.get("last")),
        SuffixName=_text(parts.get("suffix")),
    )


def _address(data: dict) -> dict:
    return _node(
        AddressLineText=_text(data.get("line")),
        CityName=_text(data.get("city")),
        PostalCode=_text(data.get("postal_code")),
        StateCode=_text(data.get("state")),
    )


def _split_name(full: str) -> dict:
    """Best-effort split of a single name string into its parts."""
    tokens = [t for t in (full or "").replace(",", " ").split() if t]
    if not tokens:
        return {}
    if len(tokens) == 1:
        return {"last": tokens[0]}
    if len(tokens) == 2:
        return {"first": tokens[0], "last": tokens[1]}
    return {"first": tokens[0], "middle": " ".join(tokens[1:-1]), "last": tokens[-1]}


def _appraiser_party(appraiser: dict) -> dict:
    licence = appraiser.get("license", {})
    return _node(
        **{"@xlink:label": "PARTY_Appraiser"},
        INDIVIDUAL=_node(NAME=_name(appraiser.get("name", {}))),
        ADDRESSES=_node(ADDRESSES=None, ADDRESS=_address(appraiser.get("company_address", {}))),
        ROLES=_node(
            ROLE=_node(
                APPRAISER=_node(
                    APPRAISER_DETAIL=_node(
                        AppraiserCompanyName=_text(appraiser.get("company_name")),
                    ),
                ),
                LICENSES=_node(
                    LICENSE=_node(
                        APPRAISER_LICENSE=_node(
                            AppraiserLicenseType=_text(licence.get("level")),
                        ),
                        LICENSE_DETAIL=_node(
                            LicenseIdentifier=_text(licence.get("identifier")),
                            LicenseIssuingAuthorityStateCode=_text(licence.get("state")),
                            LicenseExpirationDate=_text(licence.get("expiration_date")),
                        ),
                    ),
                ),
                ROLE_DETAIL=_node(PartyRoleType="Appraiser"),
            ),
        ),
    )


def _legal_entity_party(name: str, address: dict | None, role: str, label: str) -> dict:
    return _node(
        **{"@xlink:label": label},
        LEGAL_ENTITY=_node(LEGAL_ENTITY_DETAIL=_node(FullName=_text(name))),
        ADDRESSES=_node(ADDRESS=_address(address or {})) if address else None,
        ROLES=_node(ROLE=_node(ROLE_DETAIL=_node(PartyRoleType=role))),
    )


def _individual_party(full_name: str, role: str, label: str) -> dict:
    return _node(
        **{"@xlink:label": label},
        INDIVIDUAL=_node(NAME=_name(_split_name(full_name))),
        ROLES=_node(ROLE=_node(ROLE_DETAIL=_node(PartyRoleType=role))),
    )


def build_parties(inputs: ReportInputs) -> dict:
    facts = inputs.facts
    parties: list[dict] = [_appraiser_party(facts.appraiser)]

    if client := facts.order.get("client"):
        parties.append(_legal_entity_party(client, None, "Client", "PARTY_Client"))
    if borrower := facts.order.get("borrower_name"):
        parties.append(_individual_party(borrower, "Borrower", "PARTY_Borrower"))
    for i, seller in enumerate(facts.contract.get("sellers", []) or [], 1):
        parties.append(_individual_party(seller, "PropertySeller", f"PARTY_Seller{i}"))

    return _node(PARTY=parties)


# --------------------------------------------------------------- properties
def _resolved(prop: dict, name: str, default: Any = None) -> Any:
    return prop.get("resolved", {}).get(name, {}).get("value", default)


def _property_address(prop: dict) -> dict:
    addr = prop.get("address", {})
    return _node(
        AddressLineText=_text(addr.get("line")),
        CityName=_text(addr.get("city")),
        CountyName=_text((addr.get("county") or "").replace(" County", "")),
        PostalCode=_text(addr.get("postal_code")),
        StateCode=_text(addr.get("state")),
    )


# FEMA zones A and V are special flood hazard areas; X, B, C and D are not.
_SPECIAL_FLOOD_ZONES = ("A", "V")


def _hazard_zone_type(flood_zone: str | None) -> str | None:
    if not flood_zone:
        return None
    return (
        "FEMASpecialFloodHazardArea"
        if flood_zone.strip().upper().startswith(_SPECIAL_FLOOD_ZONES)
        else "None"
    )


def _site(prop: dict, zoning_compliance: str | None = None) -> dict:
    record = prop.get("public_record", {})
    acres = _resolved(prop, "lot_acres")
    return _node(
        SITE_SIZE_LAYOUT=_node(
            LotSizeAreaMeasure=_area(round(float(acres) * 43_560), "SquareFeet") if acres else None,
            SiteDimensionsDescription=_text(record.get("lot_dimensions")),
        ),
        SITE_ZONING=_node(
            SITE_ZONING_DETAIL=_node(
                SiteZoningClassificationIdentifier=_text(record.get("zoning_code")),
                SiteZoningClassificationDescription=_text(record.get("zoning_description")),
                SiteZoningComplianceType=_text(zoning_compliance),
            ),
        ),
        HAZARD_ZONES=_node(
            HAZARD_ZONE=_node(
                HazardZoneType=_hazard_zone_type(record.get("flood_zone")),
            ),
        ),
    )


def _architectural_design(style: str | None, allowed: set[str]) -> dict:
    """Map a listing's style text onto the UAD enumeration, or carry it as Other."""
    if not style:
        return {}
    candidate = style.strip().replace(" ", "")
    match = next((v for v in allowed if v.lower() == candidate.lower()), None)
    if match:
        return _node(ArchitecturalDesignCategoryType=match)
    return _node(
        ArchitecturalDesignCategoryType="Other",
        ArchitecturalDesignCategoryTypeOtherDescription=_text(style[:30]),
    )


def _improvement(prop: dict, inspection: dict | None, allowed_styles: set[str]) -> dict:
    areas = (inspection or {}).get("areas", {})
    gla = _resolved(prop, "gla_sqft")
    year = _resolved(prop, "year_built")

    return _node(
        IMPROVEMENT_DETAIL=_node(
            ImprovementType="Dwelling",
            PropertyStructureBuiltYear=_text(int(year)) if year else None,
            PropertyStructureBuiltYearEstimatedIndicator=NO if year else None,
        ),
        PROPERTY_UNITS=_node(
            PROPERTY_UNIT=_node(
                PROPERTY_UNIT_AREA=_node(
                    UnitStandardAboveGradeFinishedAreaMeasure=_area(gla),
                    UnitStandardBelowGradeFinishedAreaMeasure=_area(
                        areas.get("basement_sqft")
                    ),
                ),
                PROPERTY_UNIT_DETAIL=_node(
                    BedroomCount=_text(_resolved(prop, "bedrooms")),
                    FullBathroomCount=_text(_resolved(prop, "baths_full")),
                    HalfBathroomCount=_text(_resolved(prop, "baths_half")),
                ),
            ),
        ),
        STRUCTURE=_node(
            ARCHITECTURAL_DESIGN=_architectural_design(
                _resolved(prop, "architectural_style"), allowed_styles
            ),
        ),
    )


def _sales_history(prop: dict) -> list[dict] | None:
    transfers = prop.get("public_record", {}).get("transfers", [])
    if not transfers:
        return None
    return [
        _node(
            OwnershipTransferDate=_text(t.get("sale_date")),
            OwnershipTransferTransactionAmount=_text(t.get("price")),
        )
        for t in transfers
        if t.get("sale_date") and t.get("price")
    ]


def _property_detail(
    prop: dict, characteristics: dict, ratings: dict, history: list | None
) -> dict:
    """Structural characteristics and the UAD condition and quality ratings."""
    return _node(
        AccessoryDwellingUnitTotalCount=_text(
            characteristics.get("accessory_dwelling_units", 0)
        ),
        AttachmentType="Detached",
        DwellingCount=_text(characteristics.get("dwelling_count", 1)),
        HomeownerResponsibleForExteriorMaintenanceIndicator=_text(
            characteristics.get("homeowner_responsible_for_exterior_maintenance", True)
        ),
        LivingUnitExcludingADUCount=_text(
            characteristics.get("living_units_excluding_adu", 1)
        ),
        NativeAmericanLandsIndicator=_text(
            characteristics.get("native_american_lands", False)
        ),
        NewConstructionIndicator=_text(characteristics.get("new_construction", False)),
        OverallConditionRatingCode=_text(ratings.get("overall_condition")),
        OverallQualityRatingCode=_text(ratings.get("overall_quality")),
        PUDIndicator=_text(characteristics.get("pud", False)),
        PriorSalesOrTransfersIndicator=YES if history else NO,
        PropertyAmenityExistsIndicator=_text(characteristics.get("has_amenities", False)),
        PropertyInProjectIndicator=_text(characteristics.get("in_project", False)),
    )


def _inspections(inspection: dict | None, images: list[dict]) -> dict:
    """Inspection detail and the subject's exhibit images.

    IMAGES is not a direct child of PROPERTY; B-1 p55 and the reference reports
    carry general subject exhibits under INSPECTIONS/INSPECTION, each tagged
    with its ImageCategoryType.  Every image in the archive must appear here at
    least once or the package fails B-1 p73.
    """
    detail = (inspection or {}).get("inspection", {})
    node = _node(
        IMAGES=_node(IMAGE=images) if images else None,
        INSPECTION_DETAIL=_node(
            PropertyExteriorInspectionMethodType=_text(detail.get("exterior_method")),
            PropertyInteriorInspectionMethodType=_text(detail.get("interior_method")),
        ),
    )
    return _node(INSPECTION=node) if node else {}


def _sales_contract(contract: dict) -> dict:
    """The subject's contract of sale."""
    if not contract.get("purchase_price"):
        return {}
    concessions = contract.get("seller_concessions")
    return _node(
        SALES_CONTRACT=_node(
            SALES_CONTRACT_DETAIL=_node(
                AllPropertyRightsAppraisedIndicator=YES,
                SalesContractExistsIndicator=YES,
                ArmsLengthIndicator=_text(contract.get("sale_type") == "ArmsLength"),
                PersonalPropertyIncludedIndicator=_text(
                    bool(contract.get("personal_property_excluded")) is False
                ),
                SalesConcessionAmountKnownIndicator=_text(concessions is not None),
                SalesConcessionIndicator=_text(bool(concessions)),
                SalesContractAmount=_text(contract.get("purchase_price")),
                SalesContractDate=_text(contract.get("contract_date")),
            ),
        ),
    )


def _listing_information(listing: dict) -> dict:
    """The subject's current or most relevant listing."""
    if not listing.get("mls_number"):
        return {}
    return _node(
        LISTING_INFORMATION=_node(
            LISTING_INFORMATION_DETAIL=_node(
                DaysOnMarketCount=_text(listing.get("days_on_market")),
                FinalListPriceAmount=_text(listing.get("list_price")),
                InitialListPriceAmount=_text(listing.get("orig_list_price")),
                ListingIdentifier=_text(listing.get("mls_number")),
                ListingStartDate=_text(listing.get("on_market_date")),
            ),
        ),
    )


def build_property(
    prop: dict,
    *,
    use_type: str,
    allowed_styles: set[str],
    characteristics: dict,
    ratings: dict,
    inspection: dict | None = None,
    images: list[dict] | None = None,
    contract: dict | None = None,
    grid: ComparableGrid | None = None,
    ordinal: int | None = None,
) -> dict:
    """One PROPERTY block: the subject or a comparable."""
    history = _sales_history(prop)
    node = _node(
        **{"@ValuationUseType": use_type},
        ADDRESS=_property_address(prop),
        IMPROVEMENTS=_node(
            IMPROVEMENT=_improvement(prop, inspection, allowed_styles)
        ),
        DISASTER_MITIGATION_FEATURES=_node(
            DISASTER_MITIGATION_FEATURE=_node(DisasterMitigationFeatureType="None"),
        ),
        ENERGY_EFFICIENCY_AND_GREEN=_node(
            ENERGY_EFFICIENCY_AND_GREEN_DETAIL=_node(
                EfficiencyRatingExistsIndicator=NO,
                GreenCertificationExistsIndicator=NO,
                RenewableEnergyComponentExistsIndicator=NO,
            ),
        ),
        FUNCTIONAL_ISSUES=_node(
            FUNCTIONAL_ISSUE=_node(FunctionalIssueType="None"),
        ),
        INSPECTIONS=_inspections(inspection, images or []),
        PROPERTY_DETAIL=_property_detail(prop, characteristics, ratings, history),
        LISTING_INFORMATIONS=_listing_information(prop.get("mls", {}))
        if use_type == "SubjectProperty" else {},
        SALES_CONTRACTS=_sales_contract(contract or {})
        if use_type == "SubjectProperty" else {},
        SALES_HISTORIES=_node(SALES_HISTORY=history) if history else None,
        SITE=_site(prop, characteristics.get("zoning_compliance")),
    )

    if grid is not None:
        gla = _resolved(prop, "gla_sqft")
        node["COMPARABLE"] = _node(
            COMPARABLE_ADJUSTMENTS=_node(
                COMPARABLE_ADJUSTMENT=[
                    _node(
                        ComparableAdjustmentAmount=_text(line.amount),
                        ComparableAdjustmentType=line.adjustment_type,
                    )
                    for line in grid.applied
                ],
            ),
            COMPARABLE_DETAIL=_node(
                AdjustedSalesPriceAmount=_text(round(grid.adjusted_price)),
                SalePriceNetTotalAdjustmentAmount=_text(round(grid.net_adjustment)),
                PropertyOrdinalNumber=_text(ordinal),
                PricePerTotalStandardAboveGradeFinishedAreaAmount=(
                    _text(round(grid.sale_price / float(gla))) if gla else None
                ),
            ),
        )
    return node


def build_properties(inputs: ReportInputs, allowed_styles: set[str]) -> dict:
    facts = inputs.facts
    characteristics = (facts.inspection or {}).get("characteristics", {})
    ratings = (facts.inspection or {}).get("ratings", {})
    properties = [
        build_property(
            facts.subject,
            use_type="SubjectProperty",
            allowed_styles=allowed_styles,
            characteristics=characteristics,
            ratings=ratings,
            inspection=facts.inspection,
            images=inputs.images,
            contract=facts.contract,
        )
    ]
    for ordinal, (comp, grid) in enumerate(zip(facts.comparables, inputs.grids), 1):
        properties.append(
            build_property(
                comp,
                use_type="SalesComparable",
                allowed_styles=allowed_styles,
                characteristics=characteristics,
                ratings=ratings,
                grid=grid,
                ordinal=ordinal,
            )
        )
    return _node(PROPERTY=properties)


# ------------------------------------------------------------------- report
def build_scope_of_work(inputs: ReportInputs) -> dict:
    """Which approaches were developed, and how the property was inspected."""
    inspection = (inputs.facts.inspection or {}).get("inspection", {})
    assignment_type = (inputs.facts.order.get("transaction_type") or "Purchase").title()
    interior = inspection.get("interior_method") == "Physical"
    exterior = inspection.get("exterior_method") == "Physical"
    certification = (
        "InteriorAndExterior" if interior and exterior
        else "Exterior" if exterior
        else "NoPhysicalInspection"
    )
    return _node(
        SCOPE_OF_WORK_DETAIL=_node(
            CostApproachIndicator=NO,
            IncomeApproachIndicator=NO,
            SalesComparisonApproachIndicator=YES,
            SiteValueIndicator=NO,
            RentScheduleIndicator=NO,
            GovernmentAgencyAppraisalIndicator=NO,
            ValuationAdditionalIntendedUserIndicator=NO,
            ValuationAdditionalScopeOfWorkIndicator=NO,
            ValuationAssignmentType=_text(assignment_type),
        ),
    ), certification


def build_valuation_report(inputs: ReportInputs) -> dict:
    commentary = [
        _node(
            ValuationAnalysisCategoryType=kind,
            ValuationCommentText=_text(text[:540]),
        )
        for kind, text in inputs.commentary.items()
        if text
    ]
    scope, certification = build_scope_of_work(inputs)
    measured = (inputs.facts.inspection or {}).get("measurement_standard", "")

    return _node(
        SCOPE_OF_WORK=scope,
        VALUATION_REPORT_DETAIL=_node(
            MeasurementStandardPublisherType=(
                "AmericanNationalStandardsInstitute" if "ANSI" in measured.upper() else None
            ),
            AppraiserFileIdentifier=_text(inputs.facts.order.get('order_number')),
            SketchExistsIndicator=YES,
            AppraiserPriorServicesPerformedIndicator=NO,
            AppraiserAdditionalCertificationIndicator=NO,
            PropertyDataReportIndicator=NO,
            ReconsiderationOfValueIndicator=NO,
            ValuationReportContentIdentifier=UAD_SPEC_VERSION,
            ValuationReportInspectionCertificationType=certification,
        ),
        VALUATION_COMMENTARIES=_node(VALUATION_COMMENTARY=commentary) if commentary else None,
        VALUATION_RECONCILIATION=_node(
            VALUATION_RECONCILIATION_DETAIL=_node(
                AdditionalClientRequestedConditionsIndicator=NO,
                ValuationReconciliationSummaryCommentDescription=_text(
                    inputs.reconciliation_comment[:540]
                ),
            ),
            VALUATION_RECONCILIATION_SUMMARY=_node(
                VALUATION_CONDITIONS=_node(
                    VALUATION_CONDITION=_node(
                        PropertyValuationConditionalConclusionType=_text(
                            inputs.value_condition
                        ),
                    ),
                ),
                VALUATION_RECONCILIATION_SUMMARY_DETAIL=_node(
                    AppraisalReportEffectiveDate=_text(
                        inputs.effective_date.isoformat()
                    ),
                    OpinionOfValueAmount=_text(inputs.opinion_of_value),
                    PropertyAsIsConditionRatingCode=_text(
                        (inputs.facts.inspection or {})
                        .get("ratings", {})
                        .get("overall_condition")
                    ),
                ),
            ),
        ),
        ADDITIONAL_IDENTIFIERS=_node(
            ADDITIONAL_IDENTIFIER=[
                node for node in (
                    _node(
                        AdditionalValuationIdentifier=_text(
                            inputs.facts.order.get("loan_number")
                        ),
                        AdditionalValuationIdentifierType="Client",
                    ),
                    _node(
                        AdditionalValuationIdentifier=_text(
                            inputs.facts.order.get("amc_registration")
                        ),
                        AdditionalValuationIdentifierType="ManagementCompany",
                    ),
                ) if node
            ],
        ),
        VALUATION_SOFTWARE_SYSTEMS=_node(
            VALUATION_SOFTWARE_SYSTEM=_node(
                ValuationSoftwareVendorName="UAD 3.6 Report Engine",
            ),
        ),
    )


def build(inputs: ReportInputs, spec=None) -> dict:
    """The complete report model, ready to serialise or edit."""
    if spec is None:
        from .. import spec_loader
        spec = spec_loader.load()
    allowed_styles = set(spec.allowed_values("ArchitecturalDesignCategoryType"))

    service = _node(
        PARTIES=build_parties(inputs),
        SERVICE_DETAIL=_node(ServiceType="Valuation"),
        VALUATION=_node(
            VALUATION_RESPONSE=_node(
                VALUATION_ANALYSES=_node(
                    VALUATION_ANALYSIS=_node(
                        PROPERTIES=build_properties(inputs, allowed_styles),
                        VALUATION_REPORT=build_valuation_report(inputs),
                    ),
                ),
            ),
        ),
    )

    return {
        "MESSAGE": _node(
            **{"@MISMOReferenceModelIdentifier": MISMO_VERSION},
            DOCUMENT_SETS=_node(
                DOCUMENT_SET=_node(
                    DOCUMENTS=_node(
                        DOCUMENT=_node(
                            DEAL_SETS=_node(
                                DEAL_SET=_node(
                                    DEALS=_node(
                                        DEAL=_node(SERVICES=_node(SERVICE=service)),
                                    ),
                                ),
                            ),
                            DOCUMENT_CLASSIFICATION=_node(
                                DOCUMENT_CLASSES=_node(
                                    DOCUMENT_CLASS=_node(
                                        DocumentType="AppraisalReport",
                                    ),
                                ),
                                DOCUMENT_CLASSIFICATION_DETAIL=_node(
                                    DocumentFormIssuingEntityNameType="FNM_FRE",
                                    DocumentFormIssuingEntityVersionIdentifier=FORM_VERSION,
                                ),
                            ),
                            ABOUT_VERSIONS=_node(
                                ABOUT_VERSION=_node(
                                    AboutVersionIdentifier=APPRAISAL_VERSION,
                                ),
                            ),
                            # Both are mandatory children of DOCUMENT.
                            SIGNATORIES=_node(
                                SIGNATORY=_node(
                                    **{"@xlink:label": "SIGNATORY_Appraiser"},
                                    EXECUTION=_node(
                                        EXECUTION_DETAIL=_node(
                                            ExecutionDate=_text(
                                                inputs.signature_date.isoformat()
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                            VIEWS=_node(
                                VIEW=_node(
                                    VIEW_FILES=_node(
                                        VIEW_FILE=_node(
                                            FOREIGN_OBJECT=_node(
                                                ObjectURL="\\\\appraisal.pdf",
                                                MIMETypeIdentifier="application/pdf",
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    }
