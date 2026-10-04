"""Tables whose rows are told apart by a label read their own block of the case.

Found by laying our report beside the official D-1 SF1 and MH1 pages (see
``knowledge/errors/CATALOG.md`` E-071 and E-072): every row of the Exterior
Features table printed the wall's condition comment, and the Utilities table
printed the water comment against Electricity and Gas.  Nothing here names a
case -- the samples are only where the shape comes from.
"""
import json
import re
import sys
from pathlib import Path

import pytest
from lxml import etree, html as lhtml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import templates  # noqa: E402
from uad.report import form  # noqa: E402


def _tables(key: str) -> list:
    tpl = templates.get(key)
    tree = etree.parse(str(tpl.path))
    doc = lhtml.fromstring(form.galley_html(form.build(tree, folder=tpl.path.parent)))
    return doc.xpath("//table[contains(@class,'tbl')]")


def _rows(table) -> dict[str, list[str]]:
    out = {}
    for tr in table.xpath(".//tr"):
        cells = [" ".join(td.text_content().split()) for td in tr.xpath("./td")]
        if cells and cells[0]:
            out[cells[0]] = cells
    return out


def _table_with(key: str, label: str):
    for table in _tables(key):
        if label in _rows(table):
            return table
    raise AssertionError(f"no table with a row {label!r} in {key}")


# ---------------------------------------------------------------- clipped IDs
def test_c1_ids_clipped_by_the_pdf_are_completed():
    """C-1's text layer keeps "4.06" for 4.069 where a table runs to the page
    edge.  Each is completed to the one A-1 ID it can only be."""
    raw = json.loads((form.SPEC / "c1_form.json").read_text(encoding="utf-8"))
    changed = dict(form._complete_clipped_ids(raw))
    assert changed == {"4.00": "4.009", "4.05": "4.058", "4.06": "4.069", "20.00": "20.009"}


def test_a_completed_id_is_the_field_the_row_is_named_for():
    fields = form._fields()
    for fid, label in (("4.009", "Classification Code"), ("4.058", "Encroachment"),
                       ("20.009", "Total Sales Concessions")):
        assert any(loc.get("label") == label for loc in fields[fid]["locations"]), fid
    assert any(dp.get("mismo") == "UtilityType" for dp in fields["4.069"]["data_points"])


def test_no_c1_id_is_left_clipped_when_a_unique_completion_exists():
    fields = form._fields()
    for pg in form.form()["pages"]:
        for el in pg["elements"]:
            ids = list(el.get("ids") or [])
            for row in el.get("rows") or []:
                for cell in row.get("cells") or []:
                    ids += cell.get("ids") or []
            for fid in ids:
                if fid not in fields and form.CLIPPED_ID.match(fid):
                    assert not [k for k in fields if len(k) == len(fid) + 1 and k.startswith(fid)
                                and any(loc.get("label") == el.get("text") for loc in fields[k]["locations"])], fid


# ------------------------------------------------------------ component rows
SF1 = "sf1_appraisal_v1_4"


def test_each_exterior_feature_row_carries_its_own_comment():
    rows = _rows(_table_with(SF1, "Exterior Walls and Trim"))
    assert rows["Exterior Walls and Trim"][1:] == [
        "Vinyl", "", "Typical Wear and Tear", "Minor cracks to vinyl typical for age."]
    assert rows["Foundation"][1:] == ["Poured Concrete | Basement", "", "Typical Wear and Tear", ""]
    assert rows["Roof"][3:] == ["Typical Wear and Tear",
                                "Reported condition is subject to repair; see defects table and commentary below."]
    assert rows["Windows"][1:] == [
        "Vinyl Double Hung - Thermal Pane", "Double Thermal Pane contributes to Energy Efficiency.",
        "Typical Wear and Tear", "Windows same age as house."]


def test_a_comment_is_never_printed_against_a_row_it_does_not_belong_to():
    rows = _rows(_table_with(SF1, "Exterior Walls and Trim"))
    text = [c for r in rows.values() for c in r]
    assert text.count("Minor cracks to vinyl typical for age.") == 1


MH1 = "mh1_appraisal_v1_4"


def test_utility_rows_read_their_own_utility():
    table = _table_with(MH1, "Gas")
    rows = _rows(table)
    water = "Public water is available at the street."
    mentions = [name for name, cells in rows.items() if any(water in c for c in cells)]
    assert mentions == ["Water"]
    assert any("Propane is typical to the market." in c for c in rows["Gas"])
    # no electricity in the case: the row holds nothing, not another row's values
    assert not any(c for c in rows.get("Electricity", ["Electricity"])[1:])


def test_a_label_naming_a_family_of_rows_still_reads_its_own_cells():
    """"Property Restriction" is not one of EncumbranceType's values (A-1 says
    "Property Restrictions"): the row must keep printing what its cells hold."""
    rows = _rows(_table_with("coop1_appraisal_v1_4", "Property Restriction"))
    assert any("Historic Preservation" in c for c in rows["Property Restriction"])
    assert any("Historic Designation" in c for c in rows["Property Restriction"])
