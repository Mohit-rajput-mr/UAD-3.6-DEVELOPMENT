"""bridge.audit: what certify passes but the delivered XML gets wrong (E-065)."""
from bridge import audit

GOOD = """<x><OpinionOfValueAmount>1825000</OpinionOfValueAmount>
<ValueIndicatedBySalesComparisonAmount>1825000</ValueIndicatedBySalesComparisonAmount>
<ValuationReconciliationSummaryCommentDescription>Most emphasis is given to the Sales Comparison
Approach. The appraiser has concluded a final market value of $1,825,000.</ValuationReconciliationSummaryCommentDescription>
<DaysOnMarketCount>155</DaysOnMarketCount><AdjustedSalesPriceAmount>1812100</AdjustedSalesPriceAmount>
<DaysOnMarketCount>40</DaysOnMarketCount><AdjustedSalesPriceAmount>1699600</AdjustedSalesPriceAmount>
<DaysOnMarketCount>324</DaysOnMarketCount><AdjustedSalesPriceAmount>1934580</AdjustedSalesPriceAmount></x>"""
KIT = {1: 1812100, 2: 1699600, 3: 1934580}


def test_a_clean_export_passes():
    assert audit.check(GOOD, value=1825000, adjusted=KIT).ok


def test_a_hidden_row_shows_as_an_adjusted_price_off_the_kit():
    bad = GOOD.replace("1699600", "1679600")
    a = audit.check(bad, value=1825000, adjusted=KIT)
    assert any("hidden grid row" in p for p in a.problems)


def test_a_bare_amount_is_not_a_reconciliation_comment():
    bad = GOOD.replace(GOOD[GOOD.find("Most"):GOOD.find("</Valuation")], "$1,825,000")
    assert any("not a comment" in p for p in audit.check(bad, value=1825000, adjusted=KIT).problems)


def test_values_must_agree():
    bad = GOOD.replace("<OpinionOfValueAmount>1825000", "<OpinionOfValueAmount>1830000")
    assert any("OpinionOfValueAmount" in p for p in audit.check(bad, value=1825000).problems)


def test_missing_days_on_market_is_caught():
    bad = GOOD.replace("<DaysOnMarketCount>40</DaysOnMarketCount>", "")
    assert any("UAD-1428" in p for p in audit.check(bad, value=1825000, adjusted=KIT).problems)


def test_a_value_outside_the_adjusted_range_is_caught():
    a = audit.check(GOOD, value=1825000, adjusted=KIT)
    assert a.ok
    assert any("outside the adjusted range" in p for p in audit.check(GOOD.replace("1934580", "1800000"),
                                                                    value=1825000).problems)
