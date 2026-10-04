"""Offline checks of the E&O reader (CATALOG E-027) and the value-affecting
comparison (E-038) -- no TOTAL needed."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge import compare, review  # noqa: E402


class _Page:
    def __init__(self, items):
        self.items = items

    def evaluate(self, expression, await_promise=False):
        if "GetEandOItemMapForTesting" in expression:
            return json.dumps(self.items)
        return None


class _Report:
    def __init__(self, items):
        self.page = _Page(items)


def test_field_validation_items():
    found = review.run(_Report({"err-1": {"fieldName": "GC1_PU_LEVELS", "instance": 0, "sectionKey": "sxs-section-key",
                                          "sectionFriendlyName": "Sales Comparison", "description": "Required"}}),
                       settle=0)
    assert [(f.field, f.section, f.rule, f.is_error) for f in found] == [("GC1_PU_LEVELS", "sxs-section-key", "", True)]


def test_uad_rule_items_are_not_blank_findings():
    # once field validation is clean the map holds UAD rule results (E-027)
    items = {"a": {"RuleId": "UAD-1091", "Severity": "Fatal", "DataPointName": "StructureIdentifier",
                   "MessageText": "Structure identifier is required"},
             "b": {"RuleId": "UAD-1394", "Severity": "Warning", "DataPointName": "MortgageType", "MessageText": "w"}}
    found = review.run(_Report(items), settle=0)
    assert {(f.rule, f.severity, f.field, f.is_error) for f in found} == {
        ("UAD-1091", "Fatal", "StructureIdentifier", True), ("UAD-1394", "Warning", "MortgageType", False)}
    assert all(f.description for f in found)
    assert "1 error(s), 1 warning(s)" in review.summarise(found)


_DOC = """<MESSAGE xmlns="http://www.mismo.org/residential/2009/schemas"><PROPERTY ValuationUseType="SalesComparable">
<ADDRESS><AddressLineText>1 Main St</AddressLineText></ADDRESS>
<SALES_COMPARISON><SalePriceNetTotalAdjustmentAmount>{net}</SalePriceNetTotalAdjustmentAmount></SALES_COMPARISON>
<SITE><SiteAreaNumber>{area}</SiteAreaNumber></SITE></PROPERTY></MESSAGE>"""


def test_value_affecting_rows_are_singled_out():
    src = _DOC.format(net="-84200", area="5000").encode()
    tot = _DOC.format(net="-82200", area="5001").encode()
    diff = compare.compare(src, tot)
    assert diff["changed"] == 2
    vd = compare.value_diffs(diff)
    assert [(r["scope"], r["data_point"], r["file"], r["total"]) for r in vd] == [
        ("SalesComparable@1 MAIN ST", "SalePriceNetTotalAdjustmentAmount", ["-84200"], ["-82200"])]


def test_no_value_rows_when_totals_agree():
    doc = _DOC.format(net="-84200", area="5000").encode()
    assert compare.value_diffs(compare.compare(doc, doc)) == []
