"""Market-derived contributory values for the sales comparison grid.

An adjustment is only defensible if the market supports its size.  Where the
CMA sample is rich enough to measure a contribution we measure it; where it is
not, the rate falls back to a documented convention that the appraiser reviews
and can override.  Every rate carries the basis it came from so the report can
state how it was derived.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Any

from .market_trend import Sale, TrendResult

DERIVED = "derived"
CONVENTION = "convention"


@dataclass
class Rate:
    """One contributory rate and the evidence behind it."""

    name: str
    value: float
    unit: str
    basis: str
    derivation: str
    sample_size: int = 0
    r_squared: float | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "value": round(self.value, 4),
            "unit": self.unit,
            "basis": self.basis,
            "derivation": self.derivation,
        }
        if self.sample_size:
            out["sample_size"] = self.sample_size
        if self.r_squared is not None:
            out["r_squared"] = round(self.r_squared, 4)
        return out

    @property
    def derived(self) -> bool:
        return self.basis == DERIVED


def _weighted_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    n = len(xs)
    if n < 3:
        return 0.0, 0.0, 0.0
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if not sxx:
        return 0.0, mean_y, 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    syy = sum((y - mean_y) ** 2 for y in ys)
    slope = sxy / sxx
    return slope, mean_y - slope * mean_x, (sxy**2 / (sxx * syy) if syy else 0.0)


def gla_rate(trend: TrendResult, effective_date: Date) -> Rate:
    """Marginal dollars per square foot of gross living area.

    Sale prices are first brought to the effective date using the market
    conditions trend, so the size coefficient is not contaminated by the
    market's movement over the sample period.  The coefficient measures what an
    additional square foot actually contributed, which is materially less than
    the average price per square foot — the figure appraisers most often
    misapply here.
    """
    sales = [s for s in trend.sales if s.price_per_sqft > 0]
    if len(sales) < 20:
        return Rate(
            "gla_per_sqft", 0.0, "$/sf", CONVENTION,
            "Insufficient sales to derive a contributory rate.",
        )

    rate = trend.recommended_monthly_rate
    xs: list[float] = []
    ys: list[float] = []
    for sale in sales:
        months = (effective_date - sale.sale_date).days / 30.44
        xs.append(sale.implied_gla)
        ys.append(sale.price * (1 + rate * months))

    slope, _, r2 = _weighted_fit(xs, ys)
    mean_ppsf = sum(ys) / sum(xs)

    if slope <= 0 or r2 < 0.05:
        return Rate(
            "gla_per_sqft", round(mean_ppsf * 0.35, -1), "$/sf", CONVENTION,
            f"Regression of time-adjusted price on GLA was inconclusive "
            f"(R² = {r2:.3f}); a contributory rate of 35% of the ${mean_ppsf:,.0f} "
            f"average price per square foot was applied.",
            sample_size=len(sales), r_squared=r2,
        )

    return Rate(
        "gla_per_sqft", round(slope, -1), "$/sf", DERIVED,
        f"Linear regression of time-adjusted sale price on gross living area "
        f"across {len(sales)} closed sales indicates ${slope:,.0f} per square foot "
        f"of marginal contribution (R² = {r2:.3f}), against an average sale price "
        f"of ${mean_ppsf:,.0f} per square foot.",
        sample_size=len(sales), r_squared=r2,
    )


def site_rate(trend: TrendResult, gla: Rate) -> Rate:
    """Contributory value per square foot of site area."""
    return Rate(
        "site_per_sqft", 4.0, "$/sf of site", CONVENTION,
        "Site size contribution is not separable from the CMA data, which does "
        "not isolate lot value. A rate of $4 per square foot of excess site area "
        "was applied, consistent with the ratio of land to total value typical "
        "for the subject's market, and rounded adjustments were applied only "
        "where the difference is material.",
    )


DEFAULT_RATES: dict[str, tuple[float, str, str]] = {
    "bathroom_full": (
        15_000, "$ per full bath",
        "Full bathroom count difference, at a contributory value typical for "
        "the subject's price range and market.",
    ),
    "bathroom_half": (
        7_500, "$ per half bath",
        "Half bathroom count difference, at roughly half the contribution of a "
        "full bath.",
    ),
    "bedroom": (
        10_000, "$ per bedroom",
        "Bedroom count difference where it is not already captured by the gross "
        "living area adjustment.",
    ),
    "garage_space": (
        10_000, "$ per space",
        "Vehicle storage difference, measured per covered parking space.",
    ),
    "basement_finished": (
        40, "$/sf finished below grade",
        "Finished below-grade area, which contributes materially less per square "
        "foot than above-grade living area.",
    ),
    "basement_unfinished": (
        15, "$/sf unfinished below grade",
        "Unfinished below-grade area.",
    ),
    "pool": (
        35_000, "$ per pool",
        "In-ground pool, at its contributory rather than replacement value.",
    ),
    "age_per_year": (
        2_000, "$ per year of effective age",
        "Effective age difference, applied only where the gap is material and "
        "not already reflected in the condition rating.",
    ),
    "condition_step": (
        30_000, "$ per condition rating step",
        "Difference in UAD overall condition rating (C1-C6).",
    ),
    "quality_step": (
        35_000, "$ per quality rating step",
        "Difference in UAD overall quality rating (Q1-Q6).",
    ),
}


def default_rates() -> dict[str, Rate]:
    """Convention-based rates, each stated so the appraiser can revise it."""
    return {
        name: Rate(name, value, unit, CONVENTION, note)
        for name, (value, unit, note) in DEFAULT_RATES.items()
    }


def build(trend: TrendResult, effective_date: Date) -> dict[str, Rate]:
    """Every rate the grid needs, derived where the data allows."""
    rates = default_rates()
    gla = gla_rate(trend, effective_date)
    rates["gla_per_sqft"] = gla
    rates["site_per_sqft"] = site_rate(trend, gla)
    rates["market_conditions_monthly"] = Rate(
        "market_conditions_monthly",
        trend.recommended_monthly_rate,
        "fraction per month",
        DERIVED if trend.count >= 20 else CONVENTION,
        trend.summary(),
        sample_size=trend.count,
        r_squared=trend.r_squared,
    )
    return rates
