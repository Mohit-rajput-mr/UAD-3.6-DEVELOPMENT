"""tools/preflight.py finds what it claims to find, on small hand-broken packages.

(The other half of validating it -- no error on the twelve D-1 samples -- is
recorded in knowledge/total/preflight/.)
"""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import preflight  # noqa: E402

NS = 'xmlns="http://www.mismo.org/residential/2009/schemas" xmlns:xlink="http://www.w3.org/1999/xlink"'
PNG_A = base64.b64encode(b"picture-a").decode()
PNG_B = base64.b64encode(b"picture-b").decode()


def _image(cat, name, data):
    return (f"<IMAGE><ImageCategoryType>{cat}</ImageCategoryType>"
            f"<ImageFileLocationIdentifier>\\\\Images\\{name}</ImageFileLocationIdentifier>"
            f"<EXTENSION><OTHER><EmbeddedFile>{data}</EmbeddedFile></OTHER></EXTENSION></IMAGE>")


def _doc(comp_rows="", net="-5000", adjusted="195000", utilities="", links="", subject_photo=PNG_A):
    return f"""<MESSAGE {NS}><PROPERTIES>
<PROPERTY ValuationUseType="SubjectProperty" xlink:label="SUBJ">
 <IMPROVEMENTS><IMPROVEMENT><IMPROVEMENT_DETAIL><ImprovementType>Dwelling</ImprovementType></IMPROVEMENT_DETAIL>
  <STRUCTURE><STRUCTURE_DETAIL><StructureIdentifier>1</StructureIdentifier></STRUCTURE_DETAIL></STRUCTURE></IMPROVEMENT></IMPROVEMENTS>
 <SITE><SITE_UTILITIES>{utilities}</SITE_UTILITIES></SITE>
 <INSPECTIONS><INSPECTION><IMAGES>{_image('PropertyPhoto', 's.png', subject_photo)}{_image('DwellingFront', 'f.png', PNG_A)}</IMAGES></INSPECTION></INSPECTIONS>
</PROPERTY>
<PROPERTY ValuationUseType="SalesComparable"><ADDRESS><AddressLineText>1 Main St</AddressLineText></ADDRESS>
 <COMPARABLE><COMPARABLE_ADJUSTMENTS>
  <COMPARABLE_ADJUSTMENT><ComparableAdjustmentType>SiteSize</ComparableAdjustmentType><ComparableAdjustmentAmount>-2000</ComparableAdjustmentAmount></COMPARABLE_ADJUSTMENT>
  <COMPARABLE_ADJUSTMENT><ComparableAdjustmentType>View</ComparableAdjustmentType><ComparableAdjustmentAmount>-3000</ComparableAdjustmentAmount></COMPARABLE_ADJUSTMENT>
  {comp_rows}
 </COMPARABLE_ADJUSTMENTS><COMPARABLE_DETAIL><AdjustedSalesPriceAmount>{adjusted}</AdjustedSalesPriceAmount>
  <SalePriceNetTotalAdjustmentAmount>{net}</SalePriceNetTotalAdjustmentAmount></COMPARABLE_DETAIL></COMPARABLE>
 <SALES_HISTORIES><SALES_HISTORY><OwnershipTransferTransactionAmount>200000</OwnershipTransferTransactionAmount></SALES_HISTORY></SALES_HISTORIES>
</PROPERTY></PROPERTIES>{links}</MESSAGE>"""


UTIL_OK = ("<SITE_UTILITY><SiteUtilityOwnershipType>Public</SiteUtilityOwnershipType><UtilityType>Electricity</UtilityType></SITE_UTILITY>"
           "<SITE_UTILITY><SiteUtilityOwnershipType>NonPublic</SiteUtilityOwnershipType><UtilityType>Electricity</UtilityType>"
           "<ElectricitySourceType>Solar</ElectricitySourceType></SITE_UTILITY>")


def _run(tmp_path, xml):
    f = tmp_path / "p.xml"
    f.write_text(xml, encoding="utf-8")
    return [(x["severity"], x["rule"]) for x in preflight.run(f)]


def test_clean_package_has_no_error(tmp_path):
    assert [x for x in _run(tmp_path, _doc(utilities=UTIL_OK)) if x[0] == "error"] == []


def test_net_not_the_sum_of_rows(tmp_path):
    assert ("error", "P23") in _run(tmp_path, _doc(net="-3000", adjusted="197000"))


def test_adjusted_price_not_price_plus_net(tmp_path):
    assert ("error", "P23") in _run(tmp_path, _doc(adjusted="190000"))


def test_typeless_and_empty_rows(tmp_path):
    rows = ("<COMPARABLE_ADJUSTMENT><ComparableAdjustmentAmount>0</ComparableAdjustmentAmount></COMPARABLE_ADJUSTMENT>"
            "<COMPARABLE_ADJUSTMENT><ComparableAdjustmentType>Age</ComparableAdjustmentType></COMPARABLE_ADJUSTMENT>")
    assert _run(tmp_path, _doc(comp_rows=rows)).count(("error", "P3")) == 2


def test_described_row_without_amount_is_fine(tmp_path):
    row = ("<COMPARABLE_ADJUSTMENT><ComparableAdjustmentType>SalesComparableAdditionalAdjustableComparisonItem</ComparableAdjustmentType>"
           "<AdditionalComparisonLineItemDescription>Walk Out</AdditionalComparisonLineItemDescription></COMPARABLE_ADJUSTMENT>")
    assert ("error", "P3") not in _run(tmp_path, _doc(comp_rows=row))


def test_utilities(tmp_path):
    dup = UTIL_OK + "<SITE_UTILITY><SiteUtilityOwnershipType>Public</SiteUtilityOwnershipType><UtilityType>Electricity</UtilityType></SITE_UTILITY>"
    assert ("error", "P4") in _run(tmp_path, _doc(utilities=dup))
    no_owner = "<SITE_UTILITY><UtilityType>Water</UtilityType></SITE_UTILITY>"
    assert ("error", "P4") in _run(tmp_path, _doc(utilities=no_owner))


def test_dangling_link(tmp_path):
    rel = ('<RELATIONSHIPS><RELATIONSHIP xlink:from="SUBJ" xlink:to="ROLE_Supervisor" '
           'xlink:arcrole="urn:x"/></RELATIONSHIPS>')
    assert ("error", "P2") in _run(tmp_path, _doc(links=rel))


def test_subject_photo_not_front_photo(tmp_path):
    assert ("warning", "P22") in _run(tmp_path, _doc(subject_photo=PNG_B))
    assert ("warning", "P22") not in _run(tmp_path, _doc())


def _official(name):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine"))
    from uad.spec.paths import specs_root
    for p in sorted(specs_root().rglob("*_Appraisal_v1.*.xml")):
        if p.name.split("_Appraisal_")[0] == name:
            return p
    return None


def test_defect_pictures_need_a_caption_p27():
    # measured on web engine 0.0.1.3855: TOTAL flagged exactly these pictures'
    # exhibits (DE1/DE2 exterior on 2-4, the amenity exhibit on Condo1, the
    # outbuilding exhibit on MH1) and none on SF1
    counts = {name: sum(1 for f in preflight.run(_official(name)) if f["rule"] == "P27")
              for name in ("2- to 4-unit", "Condo1", "MH1", "SF1")}
    assert counts == {"2- to 4-unit": 2, "Condo1": 1, "MH1": 1, "SF1": 0}
