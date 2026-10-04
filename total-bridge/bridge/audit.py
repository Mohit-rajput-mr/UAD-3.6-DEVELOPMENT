"""Audit what TOTAL would DELIVER against the case file -- the errors certify misses.

Certify answers "does TOTAL / the schema / the UAD rules object?".  On 1965
20th Dr (2026-10-02) certify said READY while the export still carried:

* an adjusted sale price $20,000 off the grid's own net -- a hidden row
  (ATT_DET_ADJ) holding a value is left out of TOTAL's on-screen net but IS
  exported (CATALOG E-065, E-038);
* a reconciliation COMMENT that was only "$1,825,000" (REC_MARKET_VALUE is the
  comment, not an amount -- E-065);
* a comparable's days on market written by someone else with no source (DOM is
  Fatal-required -- UAD-1428).

So after certify, run `bridge audit --json <case.json>`: it reads the exported
MISMO once and checks it against what the kit computed.  Reads only; works on a
signed report too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Audit:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def __str__(self) -> str:
        head = "EXPORT AUDIT: " + ("clean" if self.ok else f"{len(self.problems)} problem(s)")
        return "\n".join([head, *("   !! " + p for p in self.problems), *("   .. " + n for n in self.notes)])


def _amounts(xml: str, tag: str) -> list[int]:
    return [int(float(v)) for v in re.findall(rf"<{tag}>([-\d.]+)</{tag}>", xml)]


def _text(xml: str, tag: str) -> list[str]:
    return re.findall(rf"<{tag}>([^<]*)</{tag}>", xml)


def money_figures(text: str) -> set[int]:
    return {int(m.replace(",", "")) for m in re.findall(r"\$\s?(\d{1,3}(?:,\d{3})+)", text)}


def check(xml: str, *, value: int, adjusted: dict[int, int] | None = None,
          comps_expected: int | None = None) -> Audit:
    """`value` = the concluded value; `adjusted` = {comp n: adjusted price} as the
    kit computed it (comparable order = export order)."""
    a = Audit()

    # 1. one value everywhere
    for tag in ("OpinionOfValueAmount", "ValueIndicatedBySalesComparisonAmount"):
        got = _amounts(xml, tag)
        if not got:
            a.problems.append(f"{tag} missing from the export")
        elif set(got) != {value}:
            a.problems.append(f"{tag} = {got}, concluded value is {value:,}")
    for tag in ("ValueIndicatedByIncomeApproachAmount", "ValueIndicatedByCostApproachAmount"):
        for v in _amounts(xml, tag):
            a.notes.append(f"{tag} = {v:,} (an approach indication; differs from the value by {v - value:+,})")

    # 2. the reconciliation comment is prose and names only the value
    comments = _text(xml, "ValuationReconciliationSummaryCommentDescription")
    if not comments:
        a.problems.append("reconciliation comment missing (UAD-1266)")
    for t in comments:
        if len(re.sub(r"[\s$,.\d]", "", t)) < 20:
            a.problems.append(f"reconciliation comment is not a comment: {t!r} (REC_MARKET_VALUE is text -- E-065)")
        elif value not in money_figures(t):
            a.problems.append(f"reconciliation comment does not state the value {value:,}: {t[:80]!r}")

    # 3. delivered adjusted prices = the kit's (a hidden row with a value shows here)
    got = _amounts(xml, "AdjustedSalesPriceAmount")
    if adjusted is not None:
        want = [adjusted[n] for n in sorted(adjusted)]
        if got != want:
            a.problems.append(f"exported adjusted prices {got} != kit {want} -- a hidden grid row holds a "
                              f"value TOTAL's net leaves out (E-065); read every *_ADJ row of the comparable")
    if got:
        lo, hi = min(got), max(got)
        if not lo <= value <= hi:
            a.problems.append(f"value {value:,} outside the adjusted range {lo:,}-{hi:,}")

    # 4. every sales comparable carries days on market (UAD-1428 is Fatal)
    dom = re.findall(r"<DaysOnMarketCount>([^<]*)</DaysOnMarketCount>", xml)
    n = comps_expected if comps_expected is not None else len(got)
    if n and len(dom) < n:
        a.problems.append(f"days on market on {len(dom)} of {n} comparables (UAD-1428)")
    a.notes.append(f"days on market exported: {dom} -- each must trace to a source in the case file")
    return a


def for_case(xml: str, case: dict) -> Audit:
    """The kit's own numbers for this case, then `check`."""
    from . import casekit
    res = casekit.adjustments(case)
    _, value, adjusted = casekit.reconciliation_text(case, res)
    a = check(xml, value=value, adjusted={n: int(v) for n, v in adjusted.items()},
              comps_expected=len(case["comps"]))
    sourced = {cp["n"]: cp.get("dom") for cp in case["comps"]}
    dom = re.findall(r"<DaysOnMarketCount>([^<]*)</DaysOnMarketCount>", xml)
    for (n, want), got in zip(sorted(sourced.items()), dom):
        if str(want or "") != got:
            a.problems.append(f"comparable {n}: exported days on market {got} but the case file has "
                              f"{want!r} -- someone else wrote it, or the case file is stale; source it")
    return a
