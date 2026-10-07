"""The rent schedule's totals, computed as B-1 defines them.

23.01.14 TotalMonthlyActualRentAmount   "Calculated: The sum of UnitMonthlyActualRentAmount
                                         (23.01.13) for all units in the Rental Information section"
23.01.17 TotalMonthlyActualAdditionalIncomeAmount   the sum of MonthlyActualAdditionalIncomeAmount
23.01.18 TotalMonthlyActualIncomeAmount  23.01.14 + 23.01.17
23.01.21 TotalMonthlyMarketRentAmount   the sum of UnitMonthlyMarketRentAmount (23.01.20)
23.01.24 TotalMonthlyEstimatedAdditionalIncomeAmount  the sum of MonthlyEstimatedAdditionalIncomeAmount
23.01.25 TotalMonthlyEstimatedIncomeAmount  23.01.21 + 23.01.24

They were stored values the appraiser could type and that went stale ($123 +
$13 shown with a Subtotal of $32, owner 2026-10-07).  Kept current on every
save, like the sales grid's totals (grid_math).  Each formula reproduces the
totals the three D-1 samples with a rent schedule deliver
(tests/test_setup.py).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from lxml import etree

from . import bind, edit

M = f"{{{bind.MISMO}}}"

FIELDS = {
    "TotalMonthlyActualRentAmount": "23.01.14",
    "TotalMonthlyActualAdditionalIncomeAmount": "23.01.17",
    "TotalMonthlyActualIncomeAmount": "23.01.18",
    "TotalMonthlyMarketRentAmount": "23.01.21",
    "TotalMonthlyEstimatedAdditionalIncomeAmount": "23.01.24",
    "TotalMonthlyEstimatedIncomeAmount": "23.01.25",
}


def _num(text: str | None) -> Decimal | None:
    try:
        return Decimal((text or "").strip().replace(",", "").replace("$", "")) if (text or "").strip() else None
    except InvalidOperation:
        return None


def _fmt(d: Decimal) -> str:
    return str(int(d)) if d == d.to_integral_value() else f"{d:.2f}"


def _units(subject: etree._Element) -> list[etree._Element]:
    units = list(subject.iter(f"{M}PROPERTY_UNIT"))
    marked = [u for u in units if (u.findtext(f".//{M}UnitIncludedInRentScheduleIndicator") or "").strip() == "true"]
    return marked or [u for u in units if u.find(f"{M}UNIT_RENT_SCHEDULE") is not None]


def figures(root: etree._Element) -> dict[str, str]:
    """The six totals, from what is entered ({} when nothing is)."""
    subject = bind.subject(root)
    if subject is None:
        return {}
    units = _units(subject)
    summary = next(subject.iter(f"{M}RENTAL_INFORMATION_SUMMARY"), None)
    others = list(summary.iter(f"{M}ADDITIONAL_RENTAL_INCOME")) if summary is not None else []

    def total(nodes: list[etree._Element], point: str) -> tuple[Decimal, bool]:
        vals = [_num(n.findtext(f".//{M}{point}")) for n in nodes]
        got = [v for v in vals if v is not None]
        return sum(got, Decimal(0)), bool(got)

    actual, a_any = total(units, "UnitMonthlyActualRentAmount")
    market, m_any = total(units, "UnitMonthlyMarketRentAmount")
    oth_a, oa_any = total(others, "MonthlyActualAdditionalIncomeAmount")
    oth_m, om_any = total(others, "MonthlyEstimatedAdditionalIncomeAmount")
    out = {}
    if a_any or oa_any:
        out["TotalMonthlyActualRentAmount"] = _fmt(actual)
        out["TotalMonthlyActualAdditionalIncomeAmount"] = _fmt(oth_a)
        out["TotalMonthlyActualIncomeAmount"] = _fmt(actual + oth_a)
    if m_any or om_any:
        out["TotalMonthlyMarketRentAmount"] = _fmt(market)
        out["TotalMonthlyEstimatedAdditionalIncomeAmount"] = _fmt(oth_m)
        out["TotalMonthlyEstimatedIncomeAmount"] = _fmt(market + oth_m)
    return out


def recompute(tree) -> list[tuple[str, str]]:
    """Write the totals that changed.  Returns (field id, value) for each."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    subject = bind.subject(root)
    got = figures(root)
    if not got or subject is None:
        return []
    summary = next(subject.iter(f"{M}RENTAL_INFORMATION_SUMMARY"), None)
    changed = []
    for point, value in got.items():
        node = summary.find(f".//{M}{point}") if summary is not None else None
        if node is not None and (node.text or "").strip() == value:
            continue
        if node is not None:
            node.text = value
        else:
            edit.write(tree, FIELDS[point], value, data_point=point,
                       scope=summary if summary is not None else None)
            summary = next(subject.iter(f"{M}RENTAL_INFORMATION_SUMMARY"), None)
        changed.append((FIELDS[point], value))
    return changed
