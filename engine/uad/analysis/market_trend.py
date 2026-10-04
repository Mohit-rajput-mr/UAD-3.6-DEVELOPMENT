"""Market-conditions analysis derived from the CMA sale list.

The 1004MC grid reports three median sale prices.  Taking the trend straight
from those medians is unreliable: a median moves when the *mix* of what sold
changes, not only when values change, and in this market the three medians
imply roughly 3% per month, which no paired sale would support.

The CMA behind the grid lists every sale individually with its price, its
closing date and its price per square foot.  Regressing price-per-square-foot
against closing date measures the trend with the size mix largely divided out,
across the whole sample rather than three summary points.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date as Date
from typing import Any

# A sale row: "$2,600,00" / "0" / "07/14/2026" ... "$580" / "7" / "07/27/2026".
# Prices wrap mid-number across the column, so the continuation digit is
# stitched back on before parsing.
_PRICE = re.compile(r"^\$([\d,]+)$")
_CONT = re.compile(r"^\d{1,2}$")
_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_PPSF = re.compile(r"^\$(\d{2,4})$")

PRICE_RANGE = (150_000, 20_000_000)
PPSF_RANGE = (100, 3_000)


@dataclass
class Sale:
    price: float
    sale_date: Date
    price_per_sqft: float

    @property
    def implied_gla(self) -> float:
        return self.price / self.price_per_sqft


@dataclass
class TrendResult:
    """Market-conditions trend with everything needed to defend it."""

    sales: list[Sale] = field(default_factory=list)
    monthly_rate: float = 0.0          # fractional change per month
    annual_rate: float = 0.0
    slope_ppsf_per_month: float = 0.0
    mean_ppsf: float = 0.0
    median_ppsf: float = 0.0
    r_squared: float = 0.0
    standard_error: float = 0.0
    t_statistic: float = 0.0
    p_value: float = 1.0
    confidence_low: float = 0.0        # 95% CI on the monthly rate
    confidence_high: float = 0.0
    quarterly_median_ppsf: list[tuple[str, float, int]] = field(default_factory=list)
    quarterly_monthly_rate: float = 0.0
    span_months: float = 0.0
    first_sale: Date | None = None
    last_sale: Date | None = None

    @property
    def count(self) -> int:
        return len(self.sales)

    @property
    def supported(self) -> bool:
        """Is the trend real enough to apply as a time adjustment?

        Raw price per square foot scatters widely because it carries quality,
        condition and location differences the regression cannot see, so r² is
        low even in a strongly trending market.  With a sample this size the
        question is whether the slope is distinguishable from zero, which is
        what the significance test answers; r² alone would wrongly reject it.
        """
        return self.count >= 20 and self.p_value < 0.05

    def as_dict(self) -> dict[str, Any]:
        return {
            "sale_count": self.count,
            "monthly_rate": round(self.monthly_rate, 5),
            "annual_rate": round(self.annual_rate, 4),
            "slope_ppsf_per_month": round(self.slope_ppsf_per_month, 2),
            "mean_ppsf": round(self.mean_ppsf, 2),
            "median_ppsf": round(self.median_ppsf, 2),
            "r_squared": round(self.r_squared, 4),
            "p_value": round(self.p_value, 6),
            "t_statistic": round(self.t_statistic, 3),
            "confidence_interval_monthly": [
                round(self.confidence_low, 5),
                round(self.confidence_high, 5),
            ],
            "quarterly_median_ppsf": [
                {"quarter": q, "median_ppsf": v, "sales": n}
                for q, v, n in self.quarterly_median_ppsf
            ],
            "quarterly_monthly_rate": round(self.quarterly_monthly_rate, 5),
            "recommended_monthly_rate": round(self.recommended_monthly_rate, 5),
            "span_months": round(self.span_months, 1),
            "first_sale": self.first_sale.isoformat() if self.first_sale else None,
            "last_sale": self.last_sale.isoformat() if self.last_sale else None,
            "supported": self.supported,
        }

    @property
    def significance_phrase(self) -> str:
        if self.p_value < 0.01:
            return f"statistically significant (p = {self.p_value:.4f})"
        if self.p_value < 0.05:
            return f"statistically significant at the 95% level (p = {self.p_value:.4f})"
        if self.p_value < 0.10:
            return (
                f"marginally significant (p = {self.p_value:.4f}), falling just outside "
                "the 95% confidence threshold"
            )
        return f"not statistically significant (p = {self.p_value:.4f})"

    def summary(self) -> str:
        direction = "increasing" if self.recommended_monthly_rate > 0 else "declining"
        quarters = "; ".join(
            f"{q} ${v:,.0f}/sf on {n} sales" for q, v, n in self.reliable_quarters
        )
        return (
            f"Analysis of {self.count} closed sales in the subject's market area "
            f"between {self.first_sale:%m/%d/%Y} and {self.last_sale:%m/%d/%Y} "
            f"indicates an {direction} market. Regression of sale price per square "
            f"foot against closing date indicates {self.monthly_rate * 100:+.2f}% per "
            f"month ({self.annual_rate * 100:+.1f}% annualized) from a median of "
            f"${self.median_ppsf:,.0f} per square foot; this trend is "
            f"{self.significance_phrase}. Individual sale prices per square foot vary "
            f"widely with quality, condition and location, so quarterly medians were "
            f"examined as a check and corroborate the direction: {quarters}, indicating "
            f"{self.quarterly_monthly_rate * 100:+.2f}% per month. A market conditions "
            f"adjustment of {self.recommended_monthly_rate * 100:+.2f}% per month was "
            f"applied, reflecting the more conservative of the two indications."
        )

    @property
    def reliable_quarters(self) -> list[tuple[str, float, int]]:
        """Quarters with enough sales for their median to mean anything."""
        return [q for q in self.quarterly_median_ppsf if q[2] >= 10]

    @property
    def recommended_monthly_rate(self) -> float:
        """The rate to apply: the more conservative of the two indications.

        Both methods measure the same market, so where they disagree the smaller
        magnitude is the supportable choice.  The appraiser can override it.
        """
        candidates = [self.monthly_rate]
        if self.quarterly_monthly_rate:
            candidates.append(self.quarterly_monthly_rate)
        return min(candidates, key=abs)


def parse_sales(text: str) -> list[Sale]:
    """Pull every (price, closing date, $/sf) triple out of the CMA listing."""
    lines = [ln.strip() for ln in text.splitlines()]
    sales: list[Sale] = []
    i = 0
    while i < len(lines):
        m = _PRICE.match(lines[i])
        if not m:
            i += 1
            continue

        digits = m.group(1)
        j = i + 1
        # A price split across the column wrap: "$2,600,00" + "0".
        if j < len(lines) and _CONT.match(lines[j]):
            digits += lines[j]
            j += 1

        if j >= len(lines) or not (dm := _DATE.match(lines[j])):
            i += 1
            continue

        price = float(digits.replace(",", ""))
        if not PRICE_RANGE[0] <= price <= PRICE_RANGE[1]:
            i += 1
            continue

        sale_date = Date(int(dm.group(3)), int(dm.group(1)), int(dm.group(2)))

        # The $/sf figure follows within the same row block.
        ppsf = None
        for k in range(j + 1, min(j + 9, len(lines))):
            if pm := _PPSF.match(lines[k]):
                candidate = float(pm.group(1))
                if PPSF_RANGE[0] <= candidate <= PPSF_RANGE[1]:
                    ppsf = candidate
                    break
        if ppsf is None:
            i = j + 1
            continue

        sales.append(Sale(price=price, sale_date=sale_date, price_per_sqft=ppsf))
        i = j + 1
    return sales


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Least-squares slope, intercept and r-squared."""
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, mean_y, 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    syy = sum((y - mean_y) ** 2 for y in ys)
    r2 = (sxy**2) / (sxx * syy) if syy else 0.0
    return slope, intercept, r2


def analyse(text: str) -> TrendResult:
    """Derive the market-conditions trend from the CMA sale list."""
    sales = parse_sales(text)
    result = TrendResult(sales=sales)
    if len(sales) < 3:
        return result

    result.first_sale = min(s.sale_date for s in sales)
    result.last_sale = max(s.sale_date for s in sales)
    result.span_months = (result.last_sale - result.first_sale).days / 30.44

    months = [(s.sale_date - result.first_sale).days / 30.44 for s in sales]
    ppsf = [s.price_per_sqft for s in sales]

    slope, intercept, r2 = _linear_fit(months, ppsf)
    result.slope_ppsf_per_month = slope
    result.mean_ppsf = sum(ppsf) / len(ppsf)
    result.median_ppsf = statistics.median(ppsf)
    result.r_squared = r2
    result.monthly_rate = slope / result.median_ppsf if result.median_ppsf else 0.0
    result.annual_rate = result.monthly_rate * 12

    # Is the slope distinguishable from zero?
    n = len(sales)
    mean_x = sum(months) / n
    sxx = sum((x - mean_x) ** 2 for x in months)
    residuals = [y - (intercept + slope * x) for x, y in zip(months, ppsf)]
    sse = sum(r**2 for r in residuals)
    if n > 2 and sxx > 0:
        result.standard_error = ((sse / (n - 2)) / sxx) ** 0.5
        if result.standard_error:
            result.t_statistic = slope / result.standard_error
            result.p_value = _two_sided_p(result.t_statistic)
            margin = 1.96 * result.standard_error / result.median_ppsf
            result.confidence_low = result.monthly_rate - margin
            result.confidence_high = result.monthly_rate + margin

    result.quarterly_median_ppsf = _quarterly_medians(sales)
    result.quarterly_monthly_rate = _quarterly_rate(result.reliable_quarters)
    return result


def _quarterly_rate(quarters: list[tuple[str, float, int]]) -> float:
    """Trend through the quarterly medians, each weighted by its sale count."""
    if len(quarters) < 3:
        return 0.0
    xs = [i * 3.0 for i in range(len(quarters))]  # quarter midpoints, in months
    ys = [median for _, median, _ in quarters]
    ws = [float(count) for _, _, count in quarters]

    total = sum(ws)
    mean_x = sum(w * x for w, x in zip(ws, xs)) / total
    mean_y = sum(w * y for w, y in zip(ws, ys)) / total
    sxx = sum(w * (x - mean_x) ** 2 for w, x in zip(ws, xs))
    if not sxx:
        return 0.0
    sxy = sum(w * (x - mean_x) * (y - mean_y) for w, x, y in zip(ws, xs, ys))
    return (sxy / sxx) / mean_y if mean_y else 0.0


def _two_sided_p(t: float) -> float:
    """Two-sided p-value, normal approximation (samples here are large)."""
    import math

    return math.erfc(abs(t) / math.sqrt(2))


def _quarterly_medians(sales: list[Sale]) -> list[tuple[str, float, int]]:
    """Median $/sf per calendar quarter, as an independent read on direction."""
    buckets: dict[str, list[float]] = {}
    for sale in sales:
        key = f"{sale.sale_date.year}Q{(sale.sale_date.month - 1) // 3 + 1}"
        buckets.setdefault(key, []).append(sale.price_per_sqft)
    return [
        (quarter, statistics.median(values), len(values))
        for quarter, values in sorted(buckets.items())
    ]
