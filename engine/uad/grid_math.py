"""The sales grid's totals, computed the way Appendix A-1 says they are delivered.

The appraiser enters the sale price and the adjustments; the summary rows are
arithmetic, and A-1's Implementation Notes state each one exactly:

22.15.08  SalePriceNetTotalAdjustmentAmount   the sum of every ComparableAdjustmentAmount
          on the comparable, "even if the value is zero" (H-1 UAD1460, UAD1461)
22.15.13  AdjustedSalesPriceAmount            net + the most recent sale's
          OwnershipTransferTransactionAmount when ListingStatusType is SettledSale,
          otherwise net + FinalListPriceAmount (H-1 UAD1456)
22.15.09  AdjustedSalesPricePerUnitAmount     adjusted / LivingUnitExcludingADUCount,
          when that count > 1
22.15.10  AdjustedSalesPricePerBedroomAmount  adjusted / the sum of BedroomCount,
          when LivingUnitExcludingADUCount > 1
22.15.12  PricePerTotalStandardAboveGradeFinishedAreaAmount
          price / (standard + non-standard above-grade finished area), when
          LivingUnitExcludingADUCount = 1 and that area > 0
22.15.11  PricePerUnitOfMeasureTypeForTotalFinishedAreaOfAllLivingUnitsIncludingADUAmount
          price / TotalFinishedAreaOfAllLivingUnitsIncludingADUAreaMeasure
          (2-4 unit subject)

"price" for the per-area rows is the sale price when sold, else the contract
amount when known, else the final list price.  Nothing was computed before
(owner's section test B4); WinTOTAL recomputes on every change, and so does
this, after every grid write.  Each formula is checked against the values the
twelve D-1 samples deliver (engine/tests/test_grid_math.py).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from lxml import etree

from . import bind

M = f"{{{bind.MISMO}}}"

#: Report Field ID -> the data point it holds (the grid's own rows, B-1)
FIELDS = {
    "net": ("22.15.08", "SalePriceNetTotalAdjustmentAmount"),
    "adjusted": ("22.15.13", "AdjustedSalesPriceAmount"),
    "per_unit": ("22.15.09", "AdjustedSalesPricePerUnitAmount"),
    "per_bedroom": ("22.15.10", "AdjustedSalesPricePerBedroomAmount"),
    "per_gross_area": ("22.15.11",
                       "PricePerUnitOfMeasureTypeForTotalFinishedAreaOfAllLivingUnitsIncludingADUAmount"),
    "per_above_grade": ("22.15.12", "PricePerTotalStandardAboveGradeFinishedAreaAmount"),
}


def _num(text: str | None) -> Decimal | None:
    try:
        return Decimal(str(text).strip()) if text is not None and str(text).strip() else None
    except InvalidOperation:
        return None


def _all(prop: etree._Element, name: str) -> list[Decimal]:
    return [v for v in (_num(e.text) for e in prop.iter(f"{M}{name}")) if v is not None]


def _first(prop: etree._Element, name: str) -> etree._Element | None:
    return next(prop.iter(f"{M}{name}"), None)


def _whole(v: Decimal) -> str:
    return str(v.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _cents(v: Decimal) -> str:
    q = v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return str(q.quantize(Decimal(1))) if q == q.to_integral() else str(q)


def _sale_price(prop: etree._Element) -> Decimal | None:
    """The most recent sale's amount (by OwnershipTransferDate)."""
    sales = []
    for hist in prop.iter(f"{M}SALES_HISTORY"):
        amount = _num(hist.findtext(f".//{M}OwnershipTransferTransactionAmount"))
        if amount is not None:
            sales.append(((hist.findtext(f".//{M}OwnershipTransferDate") or "").strip(), amount))
    if not sales:
        return _num(getattr(_first(prop, "OwnershipTransferTransactionAmount"), "text", None))
    return max(sales, key=lambda s: s[0])[1]


def _status(prop: etree._Element) -> str:
    node = _first(prop, "ListingStatusType")
    return (node.text or "").strip() if node is not None else ""


def figures(prop: etree._Element) -> dict[str, str]:
    """name -> value as A-1 delivers it, for one SalesComparable PROPERTY;
    a figure whose inputs are missing (or whose condition fails) is absent."""
    out: dict[str, str] = {}
    adjustments = _all(prop, "ComparableAdjustmentAmount")
    net = sum(adjustments, Decimal(0))
    out["net"] = _whole(net)
    sold = _status(prop) == "SettledSale"
    sale = _sale_price(prop)
    listed = _num(getattr(_first(prop, "FinalListPriceAmount"), "text", None))
    contract = _num(getattr(_first(prop, "SalesContractAmount"), "text", None))
    base = sale if sold else listed
    if base is not None:
        adjusted = base + net
        out["adjusted"] = _cents(adjusted)
    else:
        adjusted = None
    units = _num(getattr(_first(prop, "LivingUnitExcludingADUCount"), "text", None))
    if adjusted is not None and units is not None and units > 1:
        out["per_unit"] = _whole(adjusted / units)
        bedrooms = sum(_all(prop, "BedroomCount"), Decimal(0))
        if bedrooms > 0:
            out["per_bedroom"] = _whole(adjusted / bedrooms)
    price = sale if sold and sale is not None else contract if contract is not None else listed
    if price is not None:
        above = sum(_all(prop, "UnitStandardAboveGradeFinishedAreaMeasure")
                    + _all(prop, "UnitNonStandardAboveGradeFinishedAreaMeasure"), Decimal(0))
        if units == 1 and above > 0:
            out["per_above_grade"] = _whole(price / above)
        gross = _num(getattr(_first(prop, "TotalFinishedAreaOfAllLivingUnitsIncludingADUAreaMeasure"), "text", None))
        if gross and gross > 0:
            out["per_gross_area"] = _whole(price / gross)
    return out


def comparables(root: etree._Element) -> list[etree._Element]:
    return [p for p in root.iter(f"{M}PROPERTY") if p.get("ValuationUseType") == "SalesComparable"]


def recompute(tree, *, subject_units: int | None = None) -> list[tuple[str, str, str]]:
    """Write every comparable's totals into the document.  Returns
    (comparable label, field id, value) for each value that changed."""
    from . import edit
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    if subject_units is None:
        subj = bind.subject(root)
        n = _num(getattr(_first(subj, "LivingUnitExcludingADUCount"), "text", None)) if subj is not None else None
        subject_units = int(n) if n is not None else 1
    changed = []
    for prop in comparables(root):
        got = figures(prop)
        if subject_units <= 1:
            got.pop("per_gross_area", None)   # A-1: only for a 2-4 unit subject
        for name, (fid, point) in FIELDS.items():
            node = _first(prop, point)
            old = (node.text or "").strip() if node is not None else ""
            new = got.get(name, "")
            if new == old or (not new and not old):
                continue
            if not new:
                continue                        # never remove what the appraiser entered
            edit.write(tree, fid, new, data_point=point, scope=prop)
            changed.append((prop.get(f"{{http://www.w3.org/1999/xlink}}label", ""), fid, new))
    return changed
