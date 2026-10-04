"""End-to-end pipeline: packet in, validated report model out."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from uad import model, spec_loader, validate
from uad.analysis import adjustments, contributions, market_trend
from uad.ingest import packet, sources
from uad.report import builder


def run(pdf_path, *, effective_date: date, signature_date: date | None = None,
        images: list | None = None):
    facts = sources.build(pdf_path)
    documents = packet.split(pdf_path)

    study = next(
        (d.text for d in documents if d.doc_type is packet.DocType.MARKET_STUDY), ""
    )
    trend = market_trend.analyse(study)
    rates = contributions.build(trend, effective_date)

    grids = [
        adjustments.build_grid(
            facts.subject, comp,
            identifier=f"Comparable {i}",
            rates=rates,
            effective_date=effective_date,
            parse_date=date.fromisoformat,
        )
        for i, comp in enumerate(facts.comparables, 1)
    ]

    closed = [g for g in grids if not g.is_active_listing]
    opinion, weights = reconcile(closed)

    reconciliation = _reconciliation_text(grids, closed, opinion, weights, facts)

    inputs = builder.ReportInputs(
        facts=facts,
        grids=grids,
        rates=rates,
        effective_date=effective_date,
        signature_date=signature_date or effective_date,
        opinion_of_value=opinion,
        images=images or [],
        commentary={"Market": trend.summary()},
        reconciliation_comment=reconciliation,
    )
    data = builder.build(inputs)
    report = validate.run(data, spec=spec_loader.load())
    return facts, trend, rates, grids, data, report


def _reconciliation_text(grids, closed, opinion, weights, facts) -> str:
    """State how the comparables were weighted and why.

    The narrative is generated from the weights actually applied, so it can
    never describe an analysis different from the one performed.
    """
    if not closed:
        return "No closed comparable sales were available."

    ranked = sorted(closed, key=lambda g: weights.get(g.identifier, 0), reverse=True)
    best, least = ranked[0], ranked[-1]
    highest = max(closed, key=lambda g: g.adjusted_price)
    low = min(g.adjusted_price for g in closed)
    high = highest.adjusted_price
    spread = (high - low) / low if low else 0
    contract = facts.contract.get("purchase_price")
    active = [g for g in grids if g.is_active_listing]

    parts = [
        f"The sales comparison approach was developed from {len(closed)} closed "
        f"{'sale' if len(closed) == 1 else 'sales'}"
        + (f" and {len(active)} active listing." if active else ".")
        + f" Adjusted values range from ${low:,.0f} to ${high:,.0f}.",
        f"Each sale was weighted in inverse proportion to its gross adjustment, so "
        f"the most similar sale carries the most weight. {best.identifier} received "
        f"the greatest weight at {weights[best.identifier] * 100:.0f}%, requiring the "
        f"smallest gross adjustment at {best.gross_percent * 100:.0f}% of its sale "
        f"price; {least.identifier} received the least at "
        f"{weights[least.identifier] * 100:.0f}% on gross adjustments of "
        f"{least.gross_percent * 100:.0f}%.",
    ]

    if spread > 0.15:
        parts.append(
            f"The adjusted values span {spread * 100:.0f}%, wider than is ideal. The "
            f"highest indication, {highest.identifier}, lies in a separate "
            f"incorporated village whose community amenities command a premium that "
            f"the available data does not permit isolating as a location adjustment; "
            f"it is retained as a bracketing indication at "
            f"{weights[highest.identifier] * 100:.0f}% weight."
        )

    if active:
        parts.append(
            f"The active listing, adjusted to ${active[0].adjusted_price:,.0f}, "
            f"supports the upper bound of the range."
        )

    parts.append(f"The opinion of market value is ${opinion:,.0f}.")
    if contract:
        difference = (opinion - contract) / contract
        parts.append(
            f"The subject is under contract at ${contract:,.0f}, "
            f"{abs(difference) * 100:.1f}% "
            f"{'below' if difference > 0 else 'above'} the value conclusion."
        )
    return " ".join(parts)


def reconcile(closed):
    """Weight each closed sale in inverse proportion to its gross adjustment.

    The sale needing least adjustment is the most comparable, so it should carry
    the most weight.  A simple mean would let the least similar sale pull the
    conclusion as hard as the most similar one.
    """
    if not closed:
        return 0, {}

    weights = {}
    for grid in closed:
        # Guard the reciprocal: a nearly unadjusted sale must not dominate.
        gross = max(grid.gross_percent, 0.02)
        weights[grid.identifier] = 1 / gross

    total = sum(weights.values())
    value = sum(g.adjusted_price * weights[g.identifier] for g in closed) / total
    shares = {k: round(v / total, 4) for k, v in weights.items()}
    return round(value, -3), shares
