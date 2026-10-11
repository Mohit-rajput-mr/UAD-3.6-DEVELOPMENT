"""The Market section's search results, counted from the appraiser's MLS export
(T-1075; the owner's desktop brief, DR section 8).

The Search Result Metrics (17.005-17.015) are arithmetic over a market
search, and A-1 defines each one exactly:

17.005  MarketInventoryCount, ActiveListings      "the number of properties in
                                                   the ... inventory category"
17.006  MarketInventoryMedianDaysOnMarketCount    "the median number of days on
                                                   market for all properties
                                                   listed for sale"
17.007-17.009  Lowest / Median / Highest ...PriceAmount of the active listings
17.010  MarketInventoryCount, PendingSales
17.011  MarketInventoryLookbackMonthsCount        "the number of months dated
                                                   back from the appraisal
                                                   effective date"
17.012  MarketInventoryCount, TotalSales          sold within those months
17.013-17.015  Lowest / Median / Highest sale price of those sales

So the appraiser exports the search from the MLS as CSV and the figures are
counted, never typed: a median of an even count is the mean of the middle
two (D-1 SF1: two listings at $435,000 and $445,000, median $440,000).
What each column means is read from its header -- MLS systems name them
differently, and the names below are the common ones, not a specification;
a file whose columns cannot be told apart is refused with the reason, not
guessed at.  Nothing is written until the appraiser has seen the figures
beside the ones the report holds (``POST /cases/{id}/market/search``).
"""
from __future__ import annotations

import csv
import io
import re
import statistics
from dataclasses import dataclass, field
from datetime import date

from . import bind

# column -> the header names MLS exports use for it (squashed: lower case,
# letters and digits only).  The first header found wins, in this order.
COLUMNS: dict[str, tuple[str, ...]] = {
    "status": ("status", "listingstatus", "standardstatus", "mlsstatus", "st", "stat"),
    "list_price": ("listprice", "currentprice", "currentlistprice", "lp", "askingprice",
                   "originallistprice", "olp"),
    "sale_price": ("soldprice", "saleprice", "closeprice", "closedprice", "sp", "salesprice"),
    "dom": ("dom", "daysonmarket", "listingdom", "adom", "cdom", "cumulativedaysonmarket"),
    "close_date": ("closedate", "solddate", "closingdate", "saledate", "settleddate", "coe",
                   "contractclosedate"),
}

# status text -> the inventory it counts in
ACTIVE = ("active", "a", "act", "new", "comingsoon", "backonmarket", "pricechange")
PENDING = ("pending", "p", "pnd", "undercontract", "uc", "contingent", "activeundercontract",
           "auc", "underagreement", "ua", "pendingcontinuetoshow")
SOLD = ("sold", "s", "closed", "cl", "cls", "settled", "closedsale")


class MarketSearchError(ValueError):
    """A file that cannot be counted, with the reason."""


@dataclass
class Metrics:
    active: int = 0
    active_dom: list[int] = field(default_factory=list)
    active_prices: list[float] = field(default_factory=list)
    pending: int = 0
    sold_prices: list[float] = field(default_factory=list)
    lookback_months: int = 12
    rows: int = 0
    skipped: list[str] = field(default_factory=list)

    def fields(self) -> dict[str, str]:
        """Report Field ID -> the value to write, as A-1 stores it."""
        out = {"17.005": str(self.active), "17.010": str(self.pending),
               "17.011": str(self.lookback_months), "17.012": str(len(self.sold_prices))}
        if self.active_dom:
            out["17.006"] = str(_whole(statistics.median(self.active_dom)))
        if self.active_prices:
            out.update({"17.007": _money(min(self.active_prices)),
                        "17.008": _money(statistics.median(self.active_prices)),
                        "17.009": _money(max(self.active_prices))})
        if self.sold_prices:
            out.update({"17.013": _money(min(self.sold_prices)),
                        "17.014": _money(statistics.median(self.sold_prices)),
                        "17.015": _money(max(self.sold_prices))})
        return out


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).casefold())


def _whole(value: float) -> int:
    return int(value + 0.5)          # half up, as a count is read


def _money(value: float) -> str:
    return str(_whole(value))        # A-1 Amount, whole dollars as the samples hold them


def _number(text: str) -> float | None:
    t = re.sub(r"[$,\s]", "", str(text or ""))
    try:
        return float(t) if t else None
    except ValueError:
        return None


def _date(text: str) -> date | None:
    t = str(text or "").strip()
    for pat, order in ((r"^(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"), (r"^(\d{1,2})/(\d{1,2})/(\d{2,4})", "mdy")):
        m = re.match(pat, t)
        if m:
            a, b, c = (int(x) for x in m.groups())
            y, mo, d = (a, b, c) if order == "ymd" else (c if c > 99 else 2000 + c, a, b)
            try:
                return date(y, mo, d)
            except ValueError:
                return None
    return None


def _months_before(effective: date, months: int) -> date:
    y, m = divmod(effective.year * 12 + effective.month - 1 - months, 12)
    m += 1
    day = min(effective.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28,
                              31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def columns(header: list[str]) -> dict[str, int]:
    """Which column holds what, by its header."""
    squashed = [_squash(h) for h in header]
    out: dict[str, int] = {}
    for key, names in COLUMNS.items():
        for name in names:
            if name in squashed:
                out[key] = squashed.index(name)
                break
    return out


def count(text: str, effective: date, lookback_months: int = 12) -> Metrics:
    """The search results of an MLS export, as of the effective date."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise MarketSearchError("The file has no listings: export the search as CSV with a header row.")
    where = columns(rows[0])
    missing = [k for k in ("status", "list_price") if k not in where]
    if missing:
        raise MarketSearchError(
            "The file does not say which column is the " + " and the ".join(
                {"status": "listing status", "list_price": "list price"}[k] for k in missing)
            + f" (headers: {', '.join(rows[0][:12])}).")
    since = _months_before(effective, lookback_months)
    out = Metrics(lookback_months=lookback_months)

    def cell(row, key):
        i = where.get(key)
        return row[i] if i is not None and i < len(row) else ""

    for n, row in enumerate(rows[1:], start=2):
        out.rows += 1
        status = _squash(cell(row, "status"))
        if status in ACTIVE:
            out.active += 1
            price = _number(cell(row, "list_price"))
            if price is not None:
                out.active_prices.append(price)
            dom = _number(cell(row, "dom"))
            if dom is not None:
                out.active_dom.append(int(dom))
        elif status in PENDING:
            out.pending += 1
        elif status in SOLD:
            closed = _date(cell(row, "close_date"))
            price = _number(cell(row, "sale_price"))
            if "close_date" not in where or "sale_price" not in where:
                raise MarketSearchError("The file has sales but no sold price or close date column.")
            if closed is None or price is None:
                out.skipped.append(f"row {n}: a sale without a close date or price")
            elif since < closed <= effective:
                out.sold_prices.append(price)
            else:
                out.skipped.append(f"row {n}: sold {closed.isoformat()}, outside the "
                                   f"{lookback_months} months before {effective.isoformat()}")
        else:
            out.skipped.append(f"row {n}: status {cell(row, 'status')!r} is neither active, pending nor sold")
    return out


def effective_date(root) -> date | None:
    return _date(next((e.text for e in root.iter(f"{{{bind.MISMO}}}AppraisalReportEffectiveDate")
                       if e.text), ""))
