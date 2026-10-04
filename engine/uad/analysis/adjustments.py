"""Build the sales comparison grid.

Each line records what the subject has, what the comparable has, the dollar
adjustment and the reasoning that produced it, so the grid can be rendered for
review, written into the XML, and defended afterwards.

Sign convention follows the form: the adjustment is applied *to the
comparable*.  A comparable superior to the subject is adjusted downward.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from typing import Any

from .contributions import Rate

# UAD ComparableAdjustmentType values used by this grid.
SALE_DATE = "SaleDate"
GLA_ABOVE = "LivingUnitStandardFinishedAreaAboveGrade"
GLA_BELOW = "LivingUnitStandardFinishedAreaBelowGrade"
SITE_SIZE = "SiteSize"
BEDROOMS = "LivingUnitBedroomCount"
BATHROOMS = "LivingUnitBathroomCount"
VEHICLE_STORAGE = "VehicleStorage"
YEAR_BUILT = "YearBuilt"
CONDITION = "OverallConditionRating"
QUALITY = "OverallQualityRating"
OUTDOOR_AMENITY = "OutdoorLivingAmenity"
DWELLING_STYLE = "DwellingStyle"
CONCESSIONS = "SalesConcessions"

# Adjustments below this are noise; the market cannot support them.
MATERIALITY = 2_500

# Effective-age adjustments stop compounding past this many years.
AGE_ADJUSTMENT_CAP_YEARS = 20


@dataclass
class Line:
    """One row of the grid."""

    adjustment_type: str
    label: str
    subject: Any
    comparable: Any
    amount: float
    reasoning: str
    rate: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.adjustment_type,
            "label": self.label,
            "subject": self.subject,
            "comparable": self.comparable,
            "amount": round(self.amount),
            "reasoning": self.reasoning,
            "rate": self.rate,
        }


@dataclass
class ComparableGrid:
    identifier: str
    address: str
    sale_price: float
    is_active_listing: bool
    lines: list[Line] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def applied(self) -> list[Line]:
        return [ln for ln in self.lines if round(ln.amount)]

    @property
    def net_adjustment(self) -> float:
        return sum(ln.amount for ln in self.lines)

    @property
    def gross_adjustment(self) -> float:
        return sum(abs(ln.amount) for ln in self.lines)

    @property
    def adjusted_price(self) -> float:
        return self.sale_price + self.net_adjustment

    @property
    def net_percent(self) -> float:
        return self.net_adjustment / self.sale_price if self.sale_price else 0.0

    @property
    def gross_percent(self) -> float:
        return self.gross_adjustment / self.sale_price if self.sale_price else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "address": self.address,
            "sale_price": round(self.sale_price),
            "is_active_listing": self.is_active_listing,
            "lines": [ln.as_dict() for ln in self.applied],
            "all_lines": [ln.as_dict() for ln in self.lines],
            "net_adjustment": round(self.net_adjustment),
            "gross_adjustment": round(self.gross_adjustment),
            "net_percent": round(self.net_percent, 4),
            "gross_percent": round(self.gross_percent, 4),
            "adjusted_price": round(self.adjusted_price),
            "warnings": self.warnings,
        }


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolved(prop: dict, name: str, default: Any = None) -> Any:
    return prop.get("resolved", {}).get(name, {}).get("value", default)


def _acres_to_sqft(acres: float) -> float:
    return acres * 43_560


def _round_to(value: float, step: int = 500) -> float:
    return round(value / step) * step


def build_grid(
    subject: dict,
    comparable: dict,
    *,
    identifier: str,
    rates: dict[str, Rate],
    effective_date: Date,
    parse_date,
) -> ComparableGrid:
    """Produce every adjustment line for one comparable."""
    comp_mls = comparable.get("mls", {})
    sale_price = _num(comp_mls.get("close_price") or comp_mls.get("sale_price"))
    is_active = not sale_price
    if is_active:
        sale_price = _num(comp_mls.get("list_price"))

    grid = ComparableGrid(
        identifier=identifier,
        address=comp_mls.get("street") or comparable.get("address", {}).get("line", ""),
        sale_price=sale_price,
        is_active_listing=is_active,
    )

    _sale_date_line(grid, comp_mls, rates, effective_date, parse_date, is_active)
    _gla_line(grid, subject, comparable, rates)
    _site_line(grid, subject, comparable, rates)
    _bath_lines(grid, subject, comparable, rates)
    _bedroom_line(grid, subject, comparable, rates)
    _basement_line(grid, subject, comparable, rates)
    _garage_line(grid, subject, comparable, rates)
    _age_line(grid, subject, comparable, rates)
    _pool_line(grid, subject, comparable, rates)
    _concession_line(grid, comp_mls)

    _check_reliability(grid, subject, comparable)
    return grid


# ------------------------------------------------------------------- lines
def _add(grid: ComparableGrid, line: Line) -> None:
    if abs(line.amount) < MATERIALITY:
        line.amount = 0.0
    grid.lines.append(line)


def _sale_date_line(grid, comp_mls, rates, effective_date, parse_date, is_active):
    rate = rates["market_conditions_monthly"]
    close = comp_mls.get("close_date") or comp_mls.get("contract_date")
    if is_active or not close:
        _add(grid, Line(
            SALE_DATE, "Sale or Financing Date",
            effective_date.isoformat(), "Active listing", 0.0,
            "Active listing; no market conditions adjustment applied. The list "
            "price is treated as the upper bound of value.",
        ))
        return

    closed = parse_date(close)
    months = (effective_date - closed).days / 30.44
    amount = grid.sale_price * rate.value * months
    _add(grid, Line(
        SALE_DATE, "Market Conditions (time)", effective_date.isoformat(), close,
        _round_to(amount, 500),
        f"Closed {months:.1f} months before the effective date. "
        f"{rate.value * 100:+.2f}% per month applied to the ${grid.sale_price:,.0f} "
        f"sale price.",
        rate=f"{rate.value * 100:+.2f}%/month",
    ))


def _gla_line(grid, subject, comparable, rates):
    rate = rates["gla_per_sqft"]
    subject_gla = _num(_resolved(subject, "gla_sqft"))
    comp_gla = _num(_resolved(comparable, "gla_sqft"))
    if not (subject_gla and comp_gla):
        return
    difference = subject_gla - comp_gla
    _add(grid, Line(
        GLA_ABOVE, "Gross Living Area", f"{subject_gla:,.0f} sf", f"{comp_gla:,.0f} sf",
        _round_to(difference * rate.value, 500),
        f"{abs(difference):,.0f} sf {'larger' if difference > 0 else 'smaller'} than "
        f"the comparable at ${rate.value:,.0f} per square foot of contributory value.",
        rate=f"${rate.value:,.0f}/sf",
    ))


def _site_line(grid, subject, comparable, rates):
    rate = rates["site_per_sqft"]
    subject_acres = _num(_resolved(subject, "lot_acres"))
    comp_acres = _num(_resolved(comparable, "lot_acres"))
    if not (subject_acres and comp_acres):
        return
    difference = _acres_to_sqft(subject_acres - comp_acres)
    _add(grid, Line(
        SITE_SIZE, "Site Size", f"{subject_acres:.2f} ac", f"{comp_acres:.2f} ac",
        _round_to(difference * rate.value, 1_000),
        f"{abs(difference):,.0f} sf {'larger' if difference > 0 else 'smaller'} site "
        f"at ${rate.value:,.2f} per square foot.",
        rate=f"${rate.value:,.2f}/sf",
    ))


def _bath_lines(grid, subject, comparable, rates):
    full_rate, half_rate = rates["bathroom_full"], rates["bathroom_half"]
    subject_full = _num(_resolved(subject, "baths_full"))
    subject_half = _num(_resolved(subject, "baths_half"))
    comp_full = _num(_resolved(comparable, "baths_full"))
    comp_half = _num(_resolved(comparable, "baths_half"))

    amount = (subject_full - comp_full) * full_rate.value + (
        subject_half - comp_half
    ) * half_rate.value
    _add(grid, Line(
        BATHROOMS, "Bathroom Count",
        f"{subject_full:.0f} full / {subject_half:.0f} half",
        f"{comp_full:.0f} full / {comp_half:.0f} half",
        amount,
        f"${full_rate.value:,.0f} per full bath and ${half_rate.value:,.0f} per half "
        f"bath of difference in above-grade bathroom count.",
        rate=f"${full_rate.value:,.0f} full / ${half_rate.value:,.0f} half",
    ))


def _bedroom_line(grid, subject, comparable, rates):
    rate = rates["bedroom"]
    subject_beds = _num(_resolved(subject, "bedrooms"))
    comp_beds = _num(_resolved(comparable, "bedrooms"))
    if not (subject_beds and comp_beds):
        return
    _add(grid, Line(
        BEDROOMS, "Bedroom Count", f"{subject_beds:.0f}", f"{comp_beds:.0f}",
        (subject_beds - comp_beds) * rate.value,
        f"${rate.value:,.0f} per bedroom of difference, over and above the gross "
        f"living area adjustment.",
        rate=f"${rate.value:,.0f}/bedroom",
    ))


def _basement_line(grid, subject, comparable, rates):
    rate = rates["basement_finished"]
    subject_area = _num(_resolved(subject, "basement_sqft"))
    comp_basement = (comparable.get("mls", {}).get("basement") or "").lower()
    if not subject_area:
        return

    if "partial" in comp_basement:
        comp_area, described = subject_area * 0.5, "partial basement"
    elif "full" in comp_basement or "finished" in comp_basement:
        comp_area, described = subject_area, "full basement"
    elif not comp_basement or "no" in comp_basement:
        comp_area, described = 0.0, "no basement reported"
    else:
        comp_area, described = subject_area, "basement reported"

    difference = subject_area - comp_area
    _add(grid, Line(
        GLA_BELOW, "Below-Grade Finished Area",
        f"{subject_area:,.0f} sf finished", described,
        _round_to(difference * rate.value, 1_000),
        f"Below-grade finished area differs by approximately {abs(difference):,.0f} sf "
        f"at ${rate.value:,.0f} per square foot. Comparable basement detail is taken "
        f"from the listing, which does not state finished area precisely.",
        rate=f"${rate.value:,.0f}/sf",
    ))


def _garage_line(grid, subject, comparable, rates):
    rate = rates["garage_space"]
    subject_spaces = _num((subject.get("inspection_garage") or {}).get("spaces"), 0) or 2.0
    comp_spaces = _num(comparable.get("mls", {}).get("garage_spaces"))
    if not comp_spaces:
        return
    _add(grid, Line(
        VEHICLE_STORAGE, "Vehicle Storage",
        f"{subject_spaces:.0f} spaces", f"{comp_spaces:.0f} spaces",
        (subject_spaces - comp_spaces) * rate.value,
        f"${rate.value:,.0f} per covered parking space of difference.",
        rate=f"${rate.value:,.0f}/space",
    ))


def _age_line(grid, subject, comparable, rates):
    rate = rates["age_per_year"]
    subject_year = _num(_resolved(subject, "year_built"))
    comp_year = _num(_resolved(comparable, "year_built"))
    if not (subject_year and comp_year):
        return
    difference = subject_year - comp_year
    capped = max(-AGE_ADJUSTMENT_CAP_YEARS, min(AGE_ADJUSTMENT_CAP_YEARS, difference))
    note = (
        f"{abs(difference):.0f} years "
        f"{'newer' if difference > 0 else 'older'} than the comparable at "
        f"${rate.value:,.0f} per year, reflecting effective rather than chronological "
        f"age."
    )
    if capped != difference:
        note += (
            f" The adjustment is capped at {AGE_ADJUSTMENT_CAP_YEARS} years: beyond "
            f"that, age differences are reflected in the condition and quality "
            f"ratings rather than compounded year by year."
        )
    _add(grid, Line(
        YEAR_BUILT, "Year Built / Effective Age",
        f"{subject_year:.0f}", f"{comp_year:.0f}",
        _round_to(capped * rate.value, 1_000),
        note,
        rate=f"${rate.value:,.0f}/year",
    ))


def _pool_line(grid, subject, comparable, rates):
    rate = rates["pool"]
    comp_pool = (comparable.get("mls", {}).get("pool") or "").lower()
    comp_has_pool = comp_pool.startswith("yes")
    if not comp_has_pool:
        return
    _add(grid, Line(
        OUTDOOR_AMENITY, "Outdoor Living Amenity", "No pool", "In-ground pool",
        -rate.value,
        f"Comparable has an in-ground pool the subject lacks; ${rate.value:,.0f} "
        f"contributory value removed.",
        rate=f"${rate.value:,.0f}",
    ))


def _concession_line(grid, comp_mls):
    concessions = _num(comp_mls.get("seller_concessions"))
    _add(grid, Line(
        CONCESSIONS, "Sales or Financing Concessions",
        "None known", f"${concessions:,.0f}" if concessions else "None reported",
        -concessions,
        "Seller concessions reported in the listing are removed from the sale price."
        if concessions else
        "No seller concessions were reported in the listing.",
    ))


# -------------------------------------------------------------- reliability
def _check_reliability(grid, subject, comparable):
    """Flag anything that would weaken reliance on this comparable."""
    if grid.gross_percent > 0.25:
        grid.warnings.append(
            f"Gross adjustments total {grid.gross_percent * 100:.0f}% of the sale "
            f"price, above the 25% guideline; support in the narrative is required."
        )
    if abs(grid.net_percent) > 0.15:
        grid.warnings.append(
            f"Net adjustment is {grid.net_percent * 100:+.0f}% of the sale price, "
            f"above the 15% guideline."
        )

    subject_source = subject.get("resolved", {}).get("gla_sqft", {}).get("source")
    comp_gla_source = comparable.get("mls", {}).get("gla_source", "")
    if subject_source == "inspection" and "public" in comp_gla_source.lower():
        grid.warnings.append(
            "Subject gross living area is ANSI-measured while comparable areas come "
            "from public record. Public record overstates the subject by 445 sf, so "
            "comparable areas may be similarly overstated and the size adjustments "
            "correspondingly overstated. Comparable areas were not independently "
            "measured; this is disclosed rather than adjusted for."
        )
