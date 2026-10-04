"""The Import Module's pre-import preparation (no TOTAL needed).

    python -m pytest -q total-bridge/tests
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge.total import prepare_for_total, without_schema_location   # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _specs() -> Path:
    env = os.environ.get("UAD36_SPECS")
    if env:
        return Path(env)
    here = REPO / "specs" / "official"
    return here if here.exists() else Path(r"C:\3.6 uad zips\_UNZIPPED_ALL")


def _samples():
    return sorted(_specs().glob("Appendix D-1 */*.xml"))


def test_samples_found():
    assert len(_samples()) == 12


def test_schema_location_removed_and_still_wellformed():        # CATALOG E-028
    for xml in _samples():
        text = xml.read_text(encoding="utf-8")
        out = without_schema_location(text)
        assert "schemaLocation" not in out
        etree.fromstring(out.encode("utf-8"))


def test_rental_units_relabelled_for_total():                    # CATALOG E-032
    XL = "{http://www.w3.org/1999/xlink}"
    for xml in _samples():
        out = prepare_for_total(xml.read_text(encoding="utf-8"))
        root = etree.fromstring(out.encode("utf-8"))
        labels = {e.get(XL + "label") for e in root.iter() if isinstance(e.tag, str) and e.get(XL + "label")}
        for rel in root.iter("{*}RELATIONSHIP"):
            if (rel.get(XL + "arcrole") or "").endswith("RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION"):
                to = rel.get(XL + "to")
                assert re.search(r"_I\d+$", to), (xml.name, to)
                assert to in labels, (xml.name, "dangling", to)
                assert rel.get(XL + "from") in labels, (xml.name, "dangling from")


def test_nothing_else_changes():
    """Only labels change: every element and every text value is the same."""
    for xml in _samples():
        a = etree.fromstring(without_schema_location(xml.read_text(encoding="utf-8")).encode("utf-8"))
        b = etree.fromstring(prepare_for_total(xml.read_text(encoding="utf-8")).encode("utf-8"))
        ta = [(e.tag, (e.text or "").strip()) for e in a.iter() if isinstance(e.tag, str)]
        tb = [(e.tag, (e.text or "").strip()) for e in b.iter() if isinstance(e.tag, str)]
        assert ta == tb, xml.name


def test_data_source_targets_in_totals_convention():             # CATALOG E-036
    """TOTAL resolves a data source's comparable by role name + _P<n>, and a
    unit area by _P<unit>; every such target must follow that and exist."""
    XL = "{http://www.w3.org/1999/xlink}"
    for xml in _samples():
        root = etree.fromstring(prepare_for_total(xml.read_text(encoding="utf-8")).encode("utf-8"))
        labels = {e.get(XL + "label"): e for e in root.iter() if isinstance(e.tag, str) and e.get(XL + "label")}
        for rel in root.iter("{*}RELATIONSHIP"):
            arc = rel.get(XL + "arcrole") or ""
            to = rel.get(XL + "to")
            if arc.endswith("DATA_SOURCE_IsDataSourceFor_PROPERTY"):
                prop = labels.get(to)
                assert prop is not None, (xml.name, "dangling", to)
                role = prop.get("ValuationUseType") or ""
                if role and role != "SubjectProperty":
                    assert role in to and re.search(r"_P\d+$", to), (xml.name, to)
            if arc.endswith("DATA_SOURCE_IsDataSourceFor_PROPERTY_UNIT_AREA"):
                assert re.search(r"_P\d+$", to), (xml.name, to)


def test_comparable_functional_issue_also_where_total_reads_it():
    # CATALOG E-045: TOTAL's sales-grid importer reads a comparable's
    # functional issue only inside its dwelling IMPROVEMENT
    from lxml import etree
    from bridge.total import prepare_for_total
    ns = "http://www.mismo.org/residential/2009/schemas"
    xml = (f'<MESSAGE xmlns="{ns}"><PROPERTIES><PROPERTY ValuationUseType="SalesComparable">'
           '<FUNCTIONAL_ISSUES><FUNCTIONAL_ISSUE><FunctionalIssueType>None</FunctionalIssueType>'
           '</FUNCTIONAL_ISSUE></FUNCTIONAL_ISSUES><IMPROVEMENTS><IMPROVEMENT/></IMPROVEMENTS>'
           '</PROPERTY></PROPERTIES></MESSAGE>')
    root = etree.fromstring(prepare_for_total(xml).encode("utf-8"))
    m = {"m": ns}
    assert root.xpath("//m:PROPERTY/m:FUNCTIONAL_ISSUES/m:FUNCTIONAL_ISSUE/m:FunctionalIssueType/text()", namespaces=m) == ["None"]
    assert root.xpath("//m:IMPROVEMENT/m:FUNCTIONAL_ISSUES/m:FUNCTIONAL_ISSUE/m:FunctionalIssueType/text()", namespaces=m) == ["None"]
