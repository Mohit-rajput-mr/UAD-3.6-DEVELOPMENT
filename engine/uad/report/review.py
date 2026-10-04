"""The review document: what the appraiser sees, edits and signs.

One structure drives both the on-screen editor and the printed PDF, so what is
reviewed is exactly what ships.  Every editable value carries the path it came
from, and edits are written back to that path before the deliverable is built.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TEXT = "text"
NUMBER = "number"
MONEY = "money"
DATE = "date"
CHOICE = "choice"
LONG_TEXT = "long_text"
READ_ONLY = "read_only"
SUBHEADING = "subheading"
PHOTO = "photo"
CHECKBOX = "checkbox"


@dataclass
class Row:
    """One labelled value on the report."""

    label: str
    value: Any
    path: str | None = None          # dotted path into the editable state
    kind: str = TEXT
    options: list[str] = field(default_factory=list)
    note: str | None = None          # provenance or reasoning, shown on review
    flag: str | None = None          # "conflict", "derived", "warning"
    data_point: str | None = None    # UAD data point, for enumeration display text
    column: str = "left"             # page column, per Appendix E Part 2

    def display_for(self, value: Any) -> str:
        """The UAD display text for an enumeration value.

        The spec keeps the machine value ("FeeSimple") separate from what the
        form prints ("Fee Simple"); the XML carries the former and the report
        shows the latter.
        """
        from .. import spec_loader

        spec = spec_loader.load()
        # display_text echoes the value back when it knows no mapping, so check
        # that the data point really is enumerated before trusting it.
        if self.data_point and self.data_point in spec.enumerations:
            text = spec.display_text(self.data_point, str(value))
            if text and text != str(value):
                return text
        return _humanise(value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "path": self.path,
            "kind": self.kind,
            "options": self.options,
            "note": self.note,
            "flag": self.flag,
        }


@dataclass
class Table:
    """A columnar block inside a section, per Appendix E Part 2."""

    columns: list[str]
    rows: list[list[Any]]
    notes: list[str] = field(default_factory=list)
    name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"columns": self.columns, "rows": self.rows, "notes": self.notes}


@dataclass
class Section:
    title: str
    rows: list[Row] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    narrative: list[Row] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    comparison_grid: Any = None      # grid.ComparisonGrid, when this is the grid
    page_break: bool = False         # start this section on a fresh page

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "rows": [r.as_dict() for r in self.rows],
            "tables": [t.as_dict() for t in self.tables],
            "narrative": [r.as_dict() for r in self.narrative],
            "images": self.images,
            "findings": self.findings,
        }


def _humanise(value: Any) -> str:
    """Split a CamelCase enumeration into words as a last resort."""
    import re

    text = str(value)
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _resolved(prop: dict, name: str) -> Any:
    return prop.get("resolved", {}).get(name, {}).get("value")


def _source_of(prop: dict, name: str) -> str | None:
    return prop.get("resolved", {}).get(name, {}).get("source")


SOURCE_LABEL = {
    "inspection": "appraiser inspection",
    "mls": "MLS",
    "public_record": "public record",
}


def build(state: dict) -> list[Section]:
    """Every section of the report, in published order.

    The body is generated from the delivery specification rather than written
    by hand: Appendix A-1 says which fields belong to which section and
    subsection and in what order, so the report carries exactly those.  The
    sales comparison grid and the exhibits have their own renderers.
    """
    from . import grid as grid_mod
    from . import sections as sections_mod

    facts = state["facts"]
    model_data = state.get("model") or {}

    spec_sections = sections_mod.build(model_data) if model_data else []
    rendered: list[Section] = [_from_spec(s) for s in spec_sections]

    # The analysis the engine contributes is merged into the section the form
    # places it in, rather than added as a second section of the same name.
    _merge_into(rendered, "Market", _market_section(state["trend"], facts, state["rates"]))
    _merge_into(rendered, "Reconciliation",
                _reconciliation(state, state["grids"], facts["contract"]))
    _insert_after(
        rendered, "Prior Sale and Transfer History",
        _grid_section(state["grids"], state["rates"], facts["subject"], facts),
    )

    _attach_subject_photo(rendered, state)
    rendered.append(_photos(state))
    rendered.append(_findings_section(state["findings"]))
    return [s for s in rendered if s]


def _attach_subject_photo(sections: list[Section], state: dict) -> None:
    """Place the front photo of the subject in the Summary section.

    Appendix E p34 sets it on the right, level with Property Description, at a
    maximum of 22 picas by 13 picas 3 points.
    """
    front = next(
        (i for i in state.get("images", [])
         if i.get("category") == "DwellingFront"),
        None,
    )
    if front is None:
        return
    for section in sections:
        if section.title != "Summary":
            continue
        # Sits in the right column, level with Property Description.
        for index, row in enumerate(section.rows):
            if row.kind == SUBHEADING and row.label.startswith("Property Description"):
                section.rows.insert(
                    index + 1,
                    Row("", front["filename"], kind=PHOTO, column="right"),
                )
                return
        section.rows.append(Row("", front["filename"], kind=PHOTO, column="right"))
        return


def _from_spec(spec_section) -> Section:
    """Convert a specification-driven section into a renderable one."""
    section = Section(spec_section.title, page_break=spec_section.new_page)
    for table in getattr(spec_section, "tables", []):
        section.tables.append(Table(table.columns, table.rows,
                                    notes=[], name=table.name))
    for sub in spec_section.subsections:
        if sub.title:
            section.rows.append(Row(sub.title, "", kind=SUBHEADING))
        for f in sub.fields:
            section.rows.append(
                Row(
                    f.label,
                    f.value,
                    path=f"field.{f.field_id}",
                    kind=_kind_for(f.format_type),
                    note=None,
                    column=f.column,
                )
            )
    return section


def _kind_for(format_type: str) -> str:
    return {
        "Amount": MONEY, "Numeric": NUMBER, "Date": DATE,
        "Datetime": DATE, "Boolean": CHECKBOX,
    }.get(format_type, TEXT)


def _merge_into(sections: list[Section], title: str, extra: Section | None) -> None:
    """Fold generated analysis into the specification-driven section."""
    if extra is None:
        return
    for s in sections:
        if s.title == title:
            s.rows.extend(extra.rows)
            s.tables.extend(extra.tables)
            s.narrative.extend(extra.narrative)
            return
    sections.append(extra)


def _insert_after(sections: list[Section], title: str, new: Section | None) -> None:
    """Place a generated section immediately after the named one."""
    if new is None:
        return
    for i, s in enumerate(sections):
        if s.title == title:
            sections.insert(i + 1, new)
            return
    sections.append(new)


def _summary(state, subject, order, contract) -> Section:
    address = subject.get("address", {})
    return Section(
        "Summary",
        rows=[
            Row("Opinion of Market Value", _money(state["opinion_of_value"]),
                "opinion_of_value", MONEY,
                note="Weighted reconciliation of the closed comparable sales."),
            Row("Market Value Condition", "AsIs", "value_condition", CHOICE,
                options=["AsIs", "SubjectTo", "Hypothetical"],
                data_point="PropertyValuationConditionalConclusionType"),
            Row("Effective Date of Appraisal", state["effective_date"],
                "effective_date", DATE),
            Row("Property Address",
                f"{address.get('line', '')}, {address.get('city', '')}, "
                f"{address.get('state', '')} {address.get('postal_code', '')}",
                kind=READ_ONLY),
            Row("Assignment Reason", order.get("transaction_type", ""), kind=READ_ONLY),
            Row("Borrower", order.get("borrower_name", ""), kind=READ_ONLY),
            Row("Contract Price", _money(contract.get("purchase_price")), kind=READ_ONLY,
                note="Read from the scanned contract of sale, packet pages 14-16."),
            Row("Property Rights Appraised", "FeeSimple",
                "property_rights", CHOICE,
                options=["FeeSimple", "Leasehold", "OtherPropertyRights"],
                data_point="PropertyRightsAppraisedType"),
        ],
    )


def _assignment(order, contract, appraiser, facts) -> Section:
    licence = appraiser.get("license", {})
    inspection = (facts.get("inspection") or {}).get("inspection", {})
    return Section(
        "Assignment Information",
        rows=[
            Row("Client", order.get("client", ""), kind=READ_ONLY),
            Row("Client Address", order.get("client_address", ""), kind=READ_ONLY),
            Row("Loan Number", order.get("loan_number", ""), kind=READ_ONLY),
            Row("Order Number", order.get("order_number", ""), kind=READ_ONLY),
            Row("Appraiser Fee", _money(order.get("appraiser_fee")), kind=READ_ONLY),
            Row("Appraiser", appraiser.get("name", {}).get("full", ""), kind=READ_ONLY),
            Row("Company", appraiser.get("company_name", ""), kind=READ_ONLY),
            Row("Credential", f"{licence.get('level_display', '')} "
                              f"#{licence.get('identifier', '')} ({licence.get('state', '')})",
                kind=READ_ONLY),
            Row("Credential Expires", licence.get("expiration_date", ""), kind=READ_ONLY),
            Row("Exterior Inspection", inspection.get("exterior_method", ""), kind=READ_ONLY),
            Row("Interior Inspection", inspection.get("interior_method", ""), kind=READ_ONLY),
            Row("Sellers", ", ".join(contract.get("sellers", []) or []), kind=READ_ONLY),
            Row("Purchasers", ", ".join(contract.get("purchasers", []) or []), kind=READ_ONLY),
        ],
    )


def _subject_section(subject, facts) -> Section:
    record = subject.get("public_record", {})
    listing = subject.get("mls", {})
    inspection = facts.get("inspection") or {}
    areas = inspection.get("areas", {})
    ratings = inspection.get("ratings", {})

    def row(label, key, kind=TEXT, path=None):
        source = _source_of(subject, key)
        return Row(
            label, _resolved(subject, key), path, kind,
            note=f"Source: {SOURCE_LABEL.get(source, source)}" if source else None,
            flag="conflict" if _conflicted(facts, "subject", key) else None,
        )

    return Section(
        "Subject Property",
        rows=[
            row("Gross Living Area (sf)", "gla_sqft", NUMBER, "subject.gla_sqft"),
            Row("Measurement Standard", inspection.get("measurement_standard", ""),
                kind=READ_ONLY,
                note="Client instructions and Fannie Mae B4-1.3-05 require ANSI Z765-2021."),
            Row("Below-Grade Finished Area (sf)", areas.get("basement_sqft"),
                "subject.basement_sqft", NUMBER),
            row("Bedrooms", "bedrooms", NUMBER, "subject.bedrooms"),
            row("Full Bathrooms", "baths_full", NUMBER, "subject.baths_full"),
            row("Half Bathrooms", "baths_half", NUMBER, "subject.baths_half"),
            row("Year Built", "year_built", NUMBER, "subject.year_built"),
            row("Architectural Style", "architectural_style", TEXT, "subject.style"),
            row("Site Size (acres)", "lot_acres", NUMBER, "subject.lot_acres"),
            Row("Site Dimensions", record.get("lot_dimensions", ""), kind=READ_ONLY),
            Row("APN", record.get("apn", ""), kind=READ_ONLY),
            Row("Legal Description",
                f"Section {record.get('legal_section', '')}, Block {record.get('legal_block', '')}, "
                f"Lot {record.get('legal_lot', '')}, Nassau County, NY", kind=READ_ONLY),
            Row("Zoning", f"{record.get('zoning_code', '')} — "
                          f"{record.get('zoning_description', '')}", kind=READ_ONLY),
            Row("Zoning Compliance", "Legal", "subject.zoning_compliance", CHOICE,
                options=["Legal", "LegalNonConforming", "Illegal", "NoZoning"],
                data_point="SiteZoningComplianceType"),
            Row("FEMA Flood Zone", f"{record.get('flood_zone', '')} "
                                   f"(panel {record.get('flood_panel', '')}, "
                                   f"{record.get('flood_panel_date', '')})", kind=READ_ONLY),
            Row("Overall Condition", ratings.get("overall_condition"),
                "subject.condition", CHOICE, options=[f"C{i}" for i in range(1, 7)],
                note=ratings.get("_basis")),
            Row("Overall Quality", ratings.get("overall_quality"),
                "subject.quality", CHOICE, options=[f"Q{i}" for i in range(1, 7)]),
            Row("Annual Taxes", _money(listing.get("taxes_annual")), kind=READ_ONLY),
            Row("School District", listing.get("school_district", ""), kind=READ_ONLY),
        ],
    )


def _conflicted(facts, prop_label, field_name) -> bool:
    return any(
        c["property"] == prop_label and c["field"] == field_name
        for c in facts.get("conflicts", [])
    )


def _market_section(trend, facts, rates) -> Section:
    market = facts.get("market", {})
    quarters = trend.get("quarterly_median_ppsf", [])
    return Section(
        "Market",
        rows=[
            Row("Market Area", market.get("search_criteria", ""), kind=READ_ONLY),
            Row("Analysis Period", market.get("date_range", ""), kind=READ_ONLY),
            Row("Closed Sales Analysed", trend.get("sale_count"), kind=READ_ONLY),
            Row("Median Price per Sq Ft", _money(trend.get("median_ppsf")), kind=READ_ONLY),
            Row("Indicated Trend (per month)",
                f"{trend.get('monthly_rate', 0) * 100:+.2f}%", kind=READ_ONLY,
                note=f"p = {trend.get('p_value')}, R² = {trend.get('r_squared')}"),
            Row("Market Conditions Adjustment Applied",
                round(trend.get("recommended_monthly_rate", 0) * 100, 3),
                "market_conditions_rate_percent", NUMBER,
                note="Percent per month, applied to each comparable by time since sale.",
                flag="derived"),
            Row("Absorption Rate", market.get("absorption_rate_total"), kind=READ_ONLY),
            Row("Total Sales in Period", market.get("sales_total"), kind=READ_ONLY),
        ],
        tables=[
            Table(
                ["Quarter", "Median $/sf", "Sales"],
                [[q["quarter"], f"${q['median_ppsf']:,.0f}", q["sales"]] for q in quarters],
                notes=["Quarterly medians are an independent check on the regression."],
            )
        ],
        narrative=[
            Row("Market Conditions Commentary", trend.get("summary", ""),
                "commentary.market", LONG_TEXT),
        ],
    )


def _grid_section(grids, rates, subject, facts) -> Section:
    from . import grid as grid_mod

    def rate_row(label, key, unit="", note_key="derivation"):
        entry = rates.get(key, {})
        value = entry.get("value", 0)
        text = f"${value:,.2f}{unit}" if value < 100 else f"${value:,.0f}{unit}"
        return Row(
            label, text, f"rates.{key}", MONEY,
            note=entry.get(note_key),
            flag="derived" if entry.get("basis") == "derived" else None,
        )

    return Section(
        "Sales Comparison Approach",
        rows=[
            rate_row("Gross Living Area", "gla_per_sqft", "/sq ft"),
            rate_row("Site Size", "site_per_sqft", "/sq ft"),
            rate_row("Full Bathroom", "bathroom_full"),
            rate_row("Half Bathroom", "bathroom_half"),
            rate_row("Bedroom", "bedroom"),
            rate_row("Vehicle Storage", "garage_space", "/space"),
            rate_row("Below-Grade Finished", "basement_finished", "/sq ft"),
            rate_row("Effective Age", "age_per_year", "/year"),
            rate_row("Outdoor Living Amenity", "pool"),
        ],
        comparison_grid=grid_mod.build(grids, subject, facts),
        page_break=True,
    )


def _reconciliation(state, grids, contract) -> Section:
    closed = [g for g in grids if not g["is_active_listing"]]
    return Section(
        "Reconciliation",
        rows=[
            Row("Indicated Value Range",
                f"{_money(min(g['adjusted_price'] for g in closed))} – "
                f"{_money(max(g['adjusted_price'] for g in closed))}" if closed else "—",
                kind=READ_ONLY),
            Row("Contract Price", _money(contract.get("purchase_price")), kind=READ_ONLY),
            Row("Opinion of Market Value", _money(state["opinion_of_value"]),
                "opinion_of_value", MONEY),
        ],
        tables=[
            Table(
                ["Comparable", "Adjusted Value", "Gross Adj", "Weight"],
                [
                    [g["identifier"], _money(g["adjusted_price"]),
                     f"{g['gross_percent'] * 100:.1f}%",
                     f"{state['weights'].get(g['identifier'], 0) * 100:.0f}%"]
                    for g in closed
                ],
                notes=["Weight is inversely proportional to gross adjustment."],
            )
        ],
        narrative=[
            Row("Reconciliation Commentary", state["reconciliation_comment"],
                "reconciliation_comment", LONG_TEXT),
        ],
    )


def _certification(appraiser, state) -> Section:
    licence = appraiser.get("license", {})
    return Section(
        "Certification",
        rows=[
            Row("Appraiser", appraiser.get("name", {}).get("full", ""), kind=READ_ONLY),
            Row("Company", appraiser.get("company_name", ""), kind=READ_ONLY),
            Row("Telephone", appraiser.get("telephone", ""), kind=READ_ONLY),
            Row("Email", appraiser.get("email", ""), kind=READ_ONLY),
            Row("State Certification", f"{licence.get('identifier', '')} "
                                       f"({licence.get('state', '')})", kind=READ_ONLY),
            Row("Expires", licence.get("expiration_date", ""), kind=READ_ONLY),
            Row("Date of Signature and Report", state["signature_date"],
                "signature_date", DATE),
            Row("Effective Date of Appraisal", state["effective_date"],
                "effective_date", DATE),
        ],
        images=[{"filename": "SIGNATURE.png", "caption": "Appraiser signature",
                 "role": "signature"}],
    )


def _photos(state) -> Section:
    return Section("Exhibits", images=state.get("images", []), page_break=True)


def _findings_section(findings) -> Section:
    fatal = [f for f in findings if f.get("severity") == "Fatal"]
    warnings = [f for f in findings if f.get("severity") == "Warning"]
    return Section(
        "Compliance and Validation",
        rows=[
            Row("UAD Fatal Findings", len(fatal), kind=READ_ONLY,
                flag="warning" if fatal else None),
            Row("UAD Warnings", len(warnings), kind=READ_ONLY),
        ],
        findings=findings,
        page_break=True,
    )
