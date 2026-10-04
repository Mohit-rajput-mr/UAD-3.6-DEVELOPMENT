"""The Market section's graphs, drawn from figures rather than pasted in.

Appendix B-1 gives the Market section five image categories, and the D-1
samples show exactly what each one looks like:

    PriceTrendGraph                 Median ListPrice and Median SalesPrice as
                                    grouped bars, Median SP%LP as a grey line
                                    on a second axis, its points labelled
    AbsorptionRateGraph             Count of Listings and Count of Contracts as
                                    grouped bars, Months of Housing Supply as a
                                    grey line on a second axis, labelled
    MedianDaysOnMarketGraph         one bar series under a dotted trend line
    PercentOfDistressedSalesGraph   the same shape as Median Days
    YearBuiltOfSalesGraph           a distribution, one bar per vintage

So the drawing here is not a house style: it is those charts, in their palette
(the Office blue, orange and grey the samples were built with), with their
gridlines, their legend inside the plot at the upper left, and their habit of
starting an axis near the data rather than at zero.  What changes between one
report and the next is the numbers.

The appraiser imports one file instead of pasting five screenshots; ``PROMPT``
is what they hand an assistant, along with the order and the MLS exports, to
get that file back.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

# Category -> (key in the import file, the caption the report prints).
CHARTS: dict[str, tuple[str, str]] = {
    "PriceTrendGraph": ("price_trend", "Price Trend"),
    "AbsorptionRateGraph": ("absorption_rate", "Absorption Rate"),
    "MedianDaysOnMarketGraph": ("median_days_on_market", "Median Days on Market"),
    "PercentOfDistressedSalesGraph": ("percent_of_distressed_sales",
                                      "Percent of Distressed Sales"),
    "YearBuiltOfSalesGraph": ("year_built_of_sales", "Year Built of Sales"),
}

# The palette the sample charts were drawn in.
BLUE = "#4472C4"
ORANGE = "#ED7D31"
GREY = "#A5A5A5"
SERIES_COLOURS = (BLUE, ORANGE, GREY, "#FFC000", "#5B9BD5")
GRID = "#D9D9D9"
AXIS_INK = "#595959"

W, H = 560.0, 280.0
PAD_L, PAD_R, PAD_T, PAD_B = 58.0, 58.0, 16.0, 34.0


class MarketDataError(ValueError):
    """The imported file is not one this can draw."""


@dataclass
class Plot:
    """One series on a chart."""
    name: str
    kind: str = "bar"          # bar | line
    values: list[float] = field(default_factory=list)
    axis: str = "left"         # left | right
    fmt: str = ""              # "", "0.00", "0.0%" -- labels the line's points
    dotted: bool = False
    colour: str = ""

    @property
    def line(self) -> bool:
        return self.kind == "line"


@dataclass
class Chart:
    key: str
    title: str
    periods: list[str]
    plots: list[Plot]
    left_fmt: str = ""
    right_fmt: str = ""

    def on(self, axis: str) -> list[Plot]:
        return [p for p in self.plots if p.axis == axis]


# ----------------------------------------------------------------- importing
def _number(value: Any, where: str) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace(",", "").replace("$", "")
                     .replace("%", "").strip())
    except (TypeError, ValueError):
        raise MarketDataError(f"{where}: {value!r} is not a number")


def _simple(key: str, block: dict) -> tuple[list[str], list[Plot]]:
    """The short form: one series written as points or bins."""
    points = block.get("points") or block.get("bins") or []
    if not isinstance(points, list) or not points:
        raise MarketDataError(f"'{key}' has no points to draw")
    periods, values = [], []
    for n, point in enumerate(points, start=1):
        if not isinstance(point, dict):
            raise MarketDataError(f"'{key}' point {n} must be a JSON object")
        label = point.get("period") or point.get("label") or point.get("bin")
        value = point.get("value", point.get("count"))
        if label is None or value is None:
            raise MarketDataError(
                f"'{key}' point {n} needs a period/label and a value/count")
        periods.append(str(label))
        values.append(_number(value, f"'{key}' point {n}"))
    return periods, [Plot(name=str(block.get("title") or ""), kind="bar",
                          values=values)]


def _full(key: str, block: dict) -> tuple[list[str], list[Plot]]:
    """The long form: named series over a shared set of periods."""
    periods = [str(p) for p in (block.get("periods") or [])]
    if not periods:
        raise MarketDataError(f"'{key}' has no 'periods' to plot against")
    plots = []
    for n, raw in enumerate(block.get("series") or [], start=1):
        if not isinstance(raw, dict):
            raise MarketDataError(f"'{key}' series {n} must be a JSON object")
        values = [_number(v, f"'{key}' series {n}")
                  for v in (raw.get("values") or [])]
        if not values:
            raise MarketDataError(f"'{key}' series {n} has no values")
        if len(values) != len(periods):
            raise MarketDataError(
                f"'{key}' series {n} has {len(values)} values for "
                f"{len(periods)} periods; they must line up")
        kind = str(raw.get("type") or "bar").lower()
        if kind not in ("bar", "line"):
            raise MarketDataError(
                f"'{key}' series {n}: type must be 'bar' or 'line'")
        axis = str(raw.get("axis") or "left").lower()
        if axis not in ("left", "right"):
            raise MarketDataError(
                f"'{key}' series {n}: axis must be 'left' or 'right'")
        plots.append(Plot(name=str(raw.get("name") or ""), kind=kind,
                          values=values, axis=axis,
                          fmt=str(raw.get("labels") or ""),
                          dotted=bool(raw.get("dotted"))))
    if not plots:
        raise MarketDataError(f"'{key}' has no series to draw")
    return periods, plots


def parse(data: dict | str | bytes) -> list[Chart]:
    """Read the import file into the charts this can draw.

    Every chart is optional: an appraiser with three of the five gets three
    rather than an error and none.
    """
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except ValueError as exc:
            raise MarketDataError(f"the file is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise MarketDataError("the file must be a JSON object")
    charts = data.get("market_charts", data)
    if not isinstance(charts, dict):
        raise MarketDataError("'market_charts' must be a JSON object")

    out: list[Chart] = []
    for _category, (key, caption) in CHARTS.items():
        block = charts.get(key)
        if block is None:
            continue
        if not isinstance(block, dict):
            raise MarketDataError(f"'{key}' must be a JSON object")
        if block.get("series"):
            periods, plots = _full(key, block)
        else:
            periods, plots = _simple(key, block)
        for i, plot in enumerate(plots):
            if not plot.colour:
                plot.colour = (GREY if plot.line and len(plots) > 1
                               else SERIES_COLOURS[i % len(SERIES_COLOURS)])
        out.append(Chart(key=key, title=str(block.get("title") or caption),
                         periods=periods, plots=plots,
                         left_fmt=str(block.get("unit") or block.get("left_unit") or ""),
                         right_fmt=str(block.get("right_unit") or "")))
    if not out:
        raise MarketDataError(
            "none of the five charts were found; expected at least one of "
            + ", ".join(k for k, _ in CHARTS.values()))
    return out


def category_of(chart: Chart) -> str:
    for category, (key, _caption) in CHARTS.items():
        if key == chart.key:
            return category
    return "MarketAnalysisExhibit"


# ------------------------------------------------------------------- drawing
def _scale(values: list[float]) -> tuple[float, float, float]:
    """A bottom, a top and a step, chosen the way the sample charts choose.

    Zero-based when the data is anywhere near zero, and drawn in around the
    data when it is not -- Price Trend runs 200,000 to 600,000 rather than
    starting at nought and wasting two thirds of the plot.
    """
    if not values:
        return 0.0, 1.0, 0.5
    low, high = min(values), max(values)
    if low == high:
        high = low + (abs(low) or 1.0)
    zero_based = low >= 0 and low <= high * 0.55
    bottom = 0.0 if zero_based else low
    span = high - bottom
    power = 10 ** math.floor(math.log10(span)) if span > 0 else 1.0
    for factor in (1, 2, 2.5, 5, 10):
        step = power * factor
        if span / step <= 6:
            break
    top = step * math.ceil(high / step)
    if not zero_based:
        bottom = step * math.floor(low / step)
    if top == bottom:
        top = bottom + step
    return bottom, top, step


def _tick(value: float, fmt: str) -> str:
    if fmt == "$":
        return f"${value:,.0f}"
    if fmt == "%":
        return f"{value:g}%"
    if fmt.endswith("%"):
        places = len(fmt.split(".")[1]) - 1 if "." in fmt else 0
        return f"{value:.{places}f}%"
    if "." in fmt:
        return f"{value:.{len(fmt.split('.')[1])}f}"
    return f"{value:,.0f}" if abs(value) >= 1000 else f"{value:g}"


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def svg(chart: Chart) -> str:
    """One chart, drawn as the sample draws it."""
    periods = chart.periods
    n = max(len(periods), 1)
    left = chart.on("left")
    right = chart.on("right")
    has_right = bool(right)

    pad_r = PAD_R if has_right else 16.0
    plot_w = W - PAD_L - pad_r
    plot_h = H - PAD_T - PAD_B
    slot = plot_w / n

    l_bottom, l_top, l_step = _scale([v for p in left for v in p.values])
    r_bottom, r_top, r_step = _scale([v for p in right for v in p.values]) \
        if has_right else (0.0, 1.0, 1.0)

    def y_left(value: float) -> float:
        return PAD_T + plot_h - (value - l_bottom) / (l_top - l_bottom) * plot_h

    def y_right(value: float) -> float:
        return PAD_T + plot_h - (value - r_bottom) / (r_top - r_bottom) * plot_h

    def y_of(plot: Plot, value: float) -> float:
        return y_right(value) if plot.axis == "right" else y_left(value)

    out = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{W:g}' height='{H:g}' "
        f"viewBox='0 0 {W:g} {H:g}' font-family='Calibri, Carlito, "
        f"\"Segoe UI\", sans-serif'>",
        f"<rect width='{W:g}' height='{H:g}' fill='#ffffff'/>",
    ]

    # gridlines and the left axis
    steps = max(1, int(round((l_top - l_bottom) / l_step)))
    for i in range(steps + 1):
        value = l_bottom + i * l_step
        y = y_left(value)
        out.append(f"<line x1='{PAD_L:.1f}' y1='{y:.2f}' x2='{W - pad_r:.1f}' "
                   f"y2='{y:.2f}' stroke='{GRID}' stroke-width='0.8'/>")
        out.append(f"<text x='{PAD_L - 6:.1f}' y='{y + 3.4:.2f}' font-size='9.5' "
                   f"text-anchor='end' fill='{AXIS_INK}'>"
                   f"{_esc(_tick(value, chart.left_fmt))}</text>")

    if has_right:
        rsteps = max(1, int(round((r_top - r_bottom) / r_step)))
        for i in range(rsteps + 1):
            value = r_bottom + i * r_step
            out.append(f"<text x='{W - pad_r + 6:.1f}' y='{y_right(value) + 3.4:.2f}' "
                       f"font-size='9.5' fill='{AXIS_INK}'>"
                       f"{_esc(_tick(value, chart.right_fmt))}</text>")

    # grouped bars, then the lines over them
    bars = [p for p in chart.plots if not p.line]
    if bars:
        group = slot * 0.62
        width = group / len(bars)
        for b, plot in enumerate(bars):
            for i, value in enumerate(plot.values[:n]):
                x = PAD_L + i * slot + (slot - group) / 2 + b * width
                y = y_of(plot, value)
                base = y_left(max(l_bottom, 0.0))
                out.append(f"<rect x='{x:.2f}' y='{min(y, base):.2f}' "
                           f"width='{width:.2f}' height='{abs(base - y):.2f}' "
                           f"fill='{plot.colour}'/>")

    for plot in chart.plots:
        if not plot.line:
            continue
        pts = [(PAD_L + i * slot + slot / 2, y_of(plot, v))
               for i, v in enumerate(plot.values[:n])]
        dash = " stroke-dasharray='2.5 2.5'" if plot.dotted else ""
        out.append("<polyline points='"
                   + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
                   + f"' fill='none' stroke='{plot.colour}' "
                     f"stroke-width='2'{dash} stroke-linejoin='round'/>")
        if plot.fmt:
            for (x, y), value in zip(pts, plot.values):
                out.append(f"<rect x='{x - 2.6:.2f}' y='{y - 2.6:.2f}' width='5.2' "
                           f"height='5.2' fill='{plot.colour}'/>")
                out.append(f"<text x='{x + 6:.2f}' y='{y + 4:.2f}' font-size='9.5' "
                           f"fill='{AXIS_INK}'>"
                           f"{_esc(_tick(value, plot.fmt))}</text>")

    # the period labels, thinned so they never collide
    every = max(1, math.ceil(n / 12))
    for i, label in enumerate(periods):
        if i % every and i != n - 1:
            continue
        out.append(f"<text x='{PAD_L + i * slot + slot / 2:.2f}' "
                   f"y='{H - PAD_B + 15:.1f}' font-size='9.5' "
                   f"text-anchor='middle' fill='{AXIS_INK}'>{_esc(label)}</text>")

    out.append(f"<line x1='{PAD_L:.1f}' y1='{y_left(max(l_bottom, 0.0)):.2f}' "
               f"x2='{W - pad_r:.1f}' y2='{y_left(max(l_bottom, 0.0)):.2f}' "
               f"stroke='{GRID}' stroke-width='1'/>")

    # the legend sits inside the plot at the upper left, as the samples set it
    named = [p for p in chart.plots if p.name]
    if len(named) > 1:
        x = PAD_L + slot * 0.6
        for row, plot in enumerate(named):
            y = PAD_T + 14 + row * 15
            if plot.line:
                out.append(f"<line x1='{x:.1f}' y1='{y - 3:.1f}' x2='{x + 26:.1f}' "
                           f"y2='{y - 3:.1f}' stroke='{plot.colour}' stroke-width='2'/>")
            else:
                out.append(f"<rect x='{x:.1f}' y='{y - 9:.1f}' width='26' height='9' "
                           f"fill='{plot.colour}'/>")
            out.append(f"<text x='{x + 32:.1f}' y='{y:.1f}' font-size='10.5' "
                       f"fill='{AXIS_INK}'>{_esc(plot.name)}</text>")

    out.append("</svg>")
    return "".join(out)


def point_image_at(tree, category: str, filename: str) -> bool:
    """Send the report's image of this chart to the drawing instead.

    A case started from one of the D-1 samples already carries the GSEs' own
    picture of each graph.  Adding the drawn one beside it prints both, so the
    existing IMAGE is repointed and the appraiser sees one chart, theirs.
    """
    from .bind import MISMO

    root = tree.getroot() if hasattr(tree, "getroot") else tree
    for image in root.iter(f"{{{MISMO}}}IMAGE"):
        kind = image.find(f"{{{MISMO}}}ImageCategoryType")
        if kind is None or (kind.text or "").strip() != category:
            continue
        location = image.find(f"{{{MISMO}}}ImageFileLocationIdentifier")
        if location is None:
            return False
        location.text = f"\\\\Images\\{filename}"
        return True
    return False


# ---------------------------------------------------------------- the prompt
PROMPT = """\
Read the appraisal order, the MLS exports and any market statistics supplied
with them, and return ONE JSON file describing the market charts of a UAD 3.6
Uniform Residential Appraisal Report. Return the JSON only -- no commentary
around it, no code fence.

Use exactly this shape. Every chart is optional: leave one out rather than
inventing numbers for it. Never estimate, interpolate or carry a trend
forward; use only figures that appear in the documents.

{
  "market_charts": {
    "price_trend": {
      "periods": ["2017 Q3", "2017 Q4", "2018 Q1"],
      "left_unit": "$", "right_unit": "0.0%",
      "series": [
        {"name": "Median ListPrice",  "type": "bar",  "values": [530000, 425000, 474000]},
        {"name": "Median SalesPrice", "type": "bar",  "values": [535000, 420000, 480000]},
        {"name": "Median SP%LP", "type": "line", "axis": "right",
         "labels": "0.0%", "values": [101.0, 98.8, 99.2]}
      ]
    },
    "absorption_rate": {
      "periods": ["2017 Q3", "2017 Q4", "2018 Q1"],
      "right_unit": "0.00",
      "series": [
        {"name": "Count of Listings",  "type": "bar", "values": [3, 1, 6]},
        {"name": "Count of Contracts", "type": "bar", "values": [1, 1, 5]},
        {"name": "Months of Housing Supply", "type": "line", "axis": "right",
         "labels": "0.00", "values": [9.0, 3.0, 3.6]}
      ]
    },
    "median_days_on_market": {
      "periods": ["2017 Q3", "2017 Q4", "2018 Q1"],
      "series": [
        {"name": "Median Days on Market", "type": "bar", "values": [10, 37, 11]},
        {"name": "Trend", "type": "line", "dotted": true, "values": [12, 27, 33]}
      ]
    },
    "percent_of_distressed_sales": {
      "periods": ["2017 Q3", "2017 Q4", "2018 Q1"],
      "left_unit": "%",
      "series": [
        {"name": "Percent of Distressed Sales", "type": "bar", "values": [4.2, 3.5, 2.9]}
      ]
    },
    "year_built_of_sales": {
      "periods": ["Pre-1950", "1950-1979", "1980-1999", "2000-2019"],
      "series": [
        {"name": "Total", "type": "bar", "values": [9, 21, 17, 11]}
      ]
    }
  }
}

Rules:
* "periods" are the labels along the bottom: quarters ("2018 Q1"), months
  ("Mar 2025") or years. Use one kind throughout a chart, oldest first. For
  "year_built_of_sales" they are the vintage bands instead.
* Every series in a chart must have exactly as many "values" as there are
  "periods". Where a quarter has no figure, use 0.
* "values" are plain numbers -- no currency symbols, no commas, no percent
  signs. The unit says how they are printed.
* "left_unit" and "right_unit" are "$", "%", "0.00", "0.0%" or "" (a count).
* "type" is "bar" or "line". A line may sit on the second axis with
  "axis": "right", may label its points with "labels", and may be a dotted
  trend line with "dotted": true.
* Put the bars first and the line last, as the samples do.
* Cover the same period the appraisal's market analysis covers, and give at
  least three periods where the data allows.
* If two documents disagree, use the MLS export and say nothing about the other.
"""


def example() -> dict:
    """A file in the right shape, built from the SF1 sample's own figures."""
    periods = ["2017 Q3", "2017 Q4", "2018 Q1", "2018 Q2", "2018 Q3",
               "2018 Q4", "2019 Q1", "2019 Q2", "2019 Q3", "2019 Q4"]
    return {"market_charts": {
        "price_trend": {
            "periods": periods, "left_unit": "$", "right_unit": "0.0%",
            "series": [
                {"name": "Median ListPrice", "type": "bar",
                 "values": [530000, 425000, 474000, 490000, 465000, 470000,
                            474000, 520000, 489000, 440000]},
                {"name": "Median SalesPrice", "type": "bar",
                 "values": [535000, 420000, 480000, 485000, 455000, 465000,
                            474000, 507000, 473000, 0]},
                {"name": "Median SP%LP", "type": "line", "axis": "right",
                 "labels": "0.0%",
                 "values": [101.0, 98.8, 99.2, 99.0, 94.1, 100.5, 100.0,
                            100.0, 96.9, 0]}]},
        "absorption_rate": {
            "periods": periods, "right_unit": "0.00",
            "series": [
                {"name": "Count of Listings", "type": "bar",
                 "values": [3, 1, 6, 4, 3, 3, 10, 19, 3, 0]},
                {"name": "Count of Contracts", "type": "bar",
                 "values": [1, 1, 5, 5, 3, 4, 10, 13, 9, 1]},
                {"name": "Months of Housing Supply", "type": "line",
                 "axis": "right", "labels": "0.00",
                 "values": [9.0, 3.0, 3.6, 2.4, 3.0, 2.25, 3.0, 4.38, 1.0, 0.0]}]},
        "median_days_on_market": {
            "periods": periods,
            "series": [
                {"name": "Median Days on Market", "type": "bar",
                 "values": [10, 37, 11, 15, 104, 22, 12, 9, 47, 11]},
                {"name": "Trend", "type": "line", "dotted": True,
                 "values": [12, 27, 33, 38, 39, 38, 33, 26, 21, 18]}]},
        "percent_of_distressed_sales": {
            "periods": periods, "left_unit": "%",
            "series": [
                {"name": "Percent of Distressed Sales", "type": "bar",
                 "values": [4.2, 3.5, 2.9, 2.4, 3.1, 2.0, 1.6, 1.2, 0.9, 0.0]}]},
        "year_built_of_sales": {
            "periods": ["Pre-1950", "1950-1979", "1980-1999", "2000-2019", "2020-"],
            "series": [
                {"name": "Total", "type": "bar", "values": [9, 21, 17, 11, 3]}]},
    }}
