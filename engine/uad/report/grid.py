"""The sales comparison grid, driven by the published grid definition.

Appendix B-1's "Comparable Grids" supplement defines every row of the grid,
its order, its grouping and whether it carries an adjustment.  That definition
is extracted to ``engine/spec/comparable_grids.json`` and read here, so the
printed grid matches the form rather than a transcription of it.

Rows marked "always" print whether or not there is a value; the rest print only
when the report has something to say, which is what keeps a single-family grid
from carrying the co-op and manufactured-home rows.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

SPEC_FILE = Path(__file__).resolve().parent.parent.parent / "spec" / "comparable_grids.json"
SALES_SHEET = "Sales Comp Grid "

# The adjustment engine names its lines for the appraiser; the form names the
# same concepts differently.  This maps ours onto the published labels.
LINE_TO_ROW = {
    "Market Conditions (time)": "Sale Date",
    "Sale or Financing Date": "Sale Date",
    "Gross Living Area": "Finished Area Above Grade",
    "Below-Grade Finished Area": "Finished Area Below Grade",
    "Bedroom Count": "Bedrooms",
    "Bathroom Count": "Baths – Full | Half",
    "Year Built / Effective Age": "Year Built",
    "Site Size": "Site Size",
    "Vehicle Storage": "Type| Spaces | Detail",
    "Outdoor Living Amenity": "Outdoor Living",
    "Sales or Financing Concessions": "Sales Concessions",
    "Dwelling Style": "Dwelling Style",
}

EM_DASH = "—"


@dataclass
class Cell:
    value: Any = ""
    adjustment: float | None = None

    @property
    def adjustment_text(self) -> str:
        """Negative adjustments print in parentheses, as on the form."""
        if not self.adjustment:
            return ""
        amount = abs(self.adjustment)
        return f"$({amount:,.0f})" if self.adjustment < 0 else f"${amount:,.0f}"


@dataclass
class GridRow:
    label: str
    subject: Any = ""
    cells: list[Cell] = field(default_factory=list)
    emphasis: bool = False

    @property
    def subject_greyed(self) -> bool:
        """Subject cells the form greys out (Appendix E p61, cell Type 1)."""
        from .style_spec import SCA_SUBJECT_GRAYED_ROWS

        return self.label in SCA_SUBJECT_GRAYED_ROWS

    @property
    def adjustment_greyed(self) -> bool:
        """Adjustment cells the form greys out (Appendix E p62, cell Type 5)."""
        from .style_spec import SCA_COMPARABLE_GRAYED_ADJUSTMENT_ROWS

        return self.label in SCA_COMPARABLE_GRAYED_ADJUSTMENT_ROWS


@dataclass
class GridGroup:
    title: str
    rows: list[GridRow] = field(default_factory=list)
    band_style: str = "TB-SCA_sub-H1"


def _short(label: str) -> str:
    """The heading text as printed.

    Appendix E p63-65 prints each group heading in full, including its
    parenthetical, so the label is used verbatim.
    """
    return label.strip()


def _band_style(label: str) -> str:
    """Which of the three band treatments this group heading uses (E p63-65)."""
    from .style_spec import SCA_GROUP_BAND_STYLE

    for key, style in SCA_GROUP_BAND_STYLE.items():
        if label.startswith(key):
            return style
    return "TB-SCA_sub-H1"


@dataclass
class ComparisonGrid:
    columns: list[str]
    groups: list[GridGroup] = field(default_factory=list)
    totals: list[GridRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def comparable_count(self) -> int:
        return len(self.columns) - 1

    def blocks(self, per_block: int = 3) -> list["ComparisonGrid"]:
        """Split into blocks of three comparables.

        Appendix E p62: the grid shows three comparables at a time; beyond that
        the label and Subject Property columns repeat alongside the next set.
        """
        total = self.comparable_count
        if total <= per_block:
            return [self]

        out: list[ComparisonGrid] = []
        for start in range(0, total, per_block):
            span = slice(start, start + per_block)
            block = ComparisonGrid(
                columns=[self.columns[0]] + self.columns[1:][span],
                notes=self.notes if start == 0 else [],
            )
            for group in self.groups:
                rows = [
                    GridRow(r.label, r.subject, r.cells[span], r.emphasis)
                    for r in group.rows
                ]
                block.groups.append(GridGroup(group.title, rows, group.band_style))
            block.totals = [
                GridRow(t.label, t.subject, t.cells[span], t.emphasis)
                for t in self.totals
            ]
            out.append(block)
        return out


@lru_cache(maxsize=1)
def definition() -> list[dict]:
    """The published sales-comparison grid definition."""
    if not SPEC_FILE.exists():
        return []
    with open(SPEC_FILE, encoding="utf-8") as fh:
        return json.load(fh).get(SALES_SHEET, [])


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return EM_DASH


def _blank(value: Any) -> bool:
    return value in (None, "", EM_DASH)


def build(grids: list[dict], subject: dict, facts: dict) -> ComparisonGrid:
    """Render the adjustment results into the published grid layout."""
    columns = ["Subject Property"] + [
        f"Comparable #{i}" for i in range(1, len(grids) + 1)
    ]
    grid = ComparisonGrid(columns=columns)

    values = _values(grids, subject, facts)
    adjustments = _adjustments(grids)

    current: GridGroup | None = None
    for entry in definition():
        if entry["kind"] == "group":
            label = _short(entry["label"])
            current = GridGroup(label, band_style=_band_style(label))
            grid.groups.append(current)
            continue
        if current is None:
            continue

        label = entry["label"]
        row_values = values.get(label)
        row_adjust = adjustments.get(label)

        if row_values is None and row_adjust is None:
            if not entry.get("always"):
                continue  # optional row with nothing to report
            row_values = ("", [EM_DASH] * len(grids))

        subject_value, comp_values = row_values or ("", [""] * len(grids))
        cells = [
            Cell(comp_values[i] if i < len(comp_values) else "",
                 (row_adjust or [None] * len(grids))[i])
            for i in range(len(grids))
        ]
        current.rows.append(GridRow(label, subject_value, cells))

    grid.groups = [g for g in grid.groups if g.rows]
    grid.totals = _summary(grids)

    for g in grids:
        for warning in g.get("warnings", []):
            if warning not in grid.notes:
                grid.notes.append(warning)
    return grid


def _adjustments(grids: list[dict]) -> dict[str, list[float | None]]:
    """Adjustment amounts per published row label."""
    out: dict[str, list[float | None]] = {}
    for index, g in enumerate(grids):
        for line in g["all_lines"]:
            label = LINE_TO_ROW.get(line["label"], line["label"])
            amounts = out.setdefault(label, [None] * len(grids))
            amounts[index] = line["amount"] or None
    return {k: v for k, v in out.items() if any(a is not None for a in v)}


def _values(grids, subject, facts) -> dict[str, tuple[Any, list[Any]]]:
    """Subject and comparable values, keyed by published row label."""
    comps = facts.get("comparables", [])
    listings = [c.get("mls", {}) for c in comps]
    subject_mls = subject.get("mls", {})
    contract = facts.get("contract", {})
    inspection = facts.get("inspection", {}) or {}

    def resolved(prop, key, fmt=str):
        value = prop.get("resolved", {}).get(key, {}).get("value")
        return fmt(value) if value not in (None, "") else ""

    def address(listing):
        return (
            f"{listing.get('street', '')}\n{listing.get('city', '')}, "
            f"{listing.get('state', '')} {listing.get('postal_code', '')}"
        )

    def area(value):
        try:
            return f"{float(value):,.0f} sq ft"
        except (TypeError, ValueError):
            return ""

    rows: dict[str, tuple[Any, list[Any]]] = {
        "Comparable #": ("", [str(i + 1) for i in range(len(grids))]),
        "Property Address": (address(subject_mls), [address(m) for m in listings]),
        "Data Source": ("", [f"MLS# {m.get('mls_number', '')}" for m in listings]),
        "List Price": (_money(subject_mls.get("list_price")),
                       [_money(m.get("list_price")) for m in listings]),
        "Listing Status": (subject_mls.get("status", ""),
                           [m.get("status", "") for m in listings]),
        "Contract Price": (_money(contract.get("purchase_price")),
                           [EM_DASH for _ in listings]),
        "Sale Price": ("", [_money(g["sale_price"]) for g in grids]),
        "Contract Date": (contract.get("contract_date", ""),
                          [m.get("contract_date") or EM_DASH for m in listings]),
        "Sale Date": ("", [m.get("close_date") or EM_DASH for m in listings]),
        "Days on Market": (subject_mls.get("days_on_market", ""),
                           [m.get("days_on_market", "") for m in listings]),
        "Attached/Detached": ("Detached", ["Detached" for _ in listings]),
        "Property Rights Appraised": ("Fee Simple", ["Fee Simple" for _ in listings]),
        "All Rights Included": ("Yes", ["Yes" for _ in listings]),
        "Site Size": (resolved(subject, "lot_acres", lambda v: f"{v:.2f} Acres"),
                      [resolved(c, "lot_acres", lambda v: f"{v:.2f} Acres") for c in comps]),
        "Neighborhood Name": (subject_mls.get("village") or subject_mls.get("city", ""),
                              [m.get("village") or m.get("city", "") for m in listings]),
        "Zoning Compliance": ("Legal", ["Legal" for _ in listings]),
        "Year Built": (resolved(subject, "year_built", lambda v: f"{int(v)}"),
                       [resolved(c, "year_built", lambda v: f"{int(v)}") for c in comps]),
        "Construction Method": ("Site Built", ["Site Built" for _ in listings]),
        "Dwelling Style": (resolved(subject, "architectural_style"),
                           [resolved(c, "architectural_style") for c in comps]),
        "Heating": (subject_mls.get("heating", ""),
                    [m.get("heating", "") for m in listings]),
        "Cooling": (subject_mls.get("cooling", ""),
                    [m.get("cooling", "") for m in listings]),
        "Bedrooms": (resolved(subject, "bedrooms", lambda v: f"{int(v)}"),
                     [resolved(c, "bedrooms", lambda v: f"{int(v)}") for c in comps]),
        "Baths – Full | Half": (
            _baths(subject), [_baths(c) for c in comps]
        ),
        "Finished Area Above Grade": (
            area(subject.get("resolved", {}).get("gla_sqft", {}).get("value")),
            [area(c.get("resolved", {}).get("gla_sqft", {}).get("value")) for c in comps],
        ),
        "Finished Area Below Grade": (
            area((inspection.get("areas") or {}).get("basement_sqft")),
            [_basement(m) for m in listings],
        ),
        "Quality": (
            (inspection.get("ratings") or {}).get("overall_quality", ""),
            ["" for _ in listings],
        ),
        "Condition": (
            (inspection.get("ratings") or {}).get("overall_condition", ""),
            ["" for _ in listings],
        ),
        "Type| Spaces | Detail": (
            _garage(inspection), [_garage_mls(m) for m in listings]
        ),
    }
    return {k: v for k, v in rows.items() if not all(_blank(x) for x in v[1])}


def _baths(prop: dict) -> str:
    r = prop.get("resolved", {})
    full = r.get("baths_full", {}).get("value")
    half = r.get("baths_half", {}).get("value")
    if full is None:
        return ""
    return f"{int(full)} | {int(half or 0)}"


def _basement(listing: dict) -> str:
    text = (listing.get("basement") or "").lower()
    if "partial" in text:
        return "Partial"
    if "full" in text or "finished" in text:
        return "Full"
    return EM_DASH


def _garage(inspection: dict) -> str:
    garage = inspection.get("garage") or {}
    if not garage:
        return ""
    return f"{garage.get('type', '')} | {garage.get('spaces', '')}"


def _garage_mls(listing: dict) -> str:
    spaces = listing.get("garage_spaces")
    return f"Garage | {spaces:.0f}" if spaces else EM_DASH


def _summary(grids: list[dict]) -> list[GridRow]:
    """The Summary block the form closes the grid with."""
    return [
        GridRow("Net Adjustment Total", "", [
            Cell(f"{g['net_adjustment']:+,.0f}") for g in grids
        ], emphasis=True),
        GridRow("Gross Adjustment Total", "", [
            Cell(f"{g['gross_adjustment']:,.0f} ({g['gross_percent'] * 100:.1f}%)")
            for g in grids
        ], emphasis=True),
        GridRow("Adjusted Price", "", [
            Cell(_money(g["adjusted_price"])) for g in grids
        ], emphasis=True),
    ]
