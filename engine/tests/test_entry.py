"""Typing a bare number: the document stores it as A-1 defines it, with its
unit, and the report prints the unit and the symbols."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import bind, edit, entry, schema, templates  # noqa: E402
from uad.report import comparables  # noqa: E402


def dp_for(fid, kind):
    return next(d for d in edit._binding_for(fid).data_points if d["format_type"] == kind)


@pytest.mark.parametrize("fid,kind,typed,stored,unit", [
    ("22.07.13", "Numeric", "2352", "2352", "SquareFeet"),
    ("22.07.13", "Numeric", "2,352 sf", "2352", "SquareFeet"),
    ("22.07.13", "Numeric", "2,352 Sq. Ft.", "2352", "SquareFeet"),
    ("22.03.02", "Numeric", "1.5 acres", "1.5", "Acres"),
    ("22.03.02", "Numeric", "14950", "14950", "SquareFeet"),
    ("22.01.19", "Numeric", "0.19 mi", "0.19", "Miles"),
    ("22.01.23", "Amount", "$515k", "515000", ""),
    ("22.01.23", "Amount", "515,000", "515000", ""),
    ("22.01.23", "Amount", "(5,000)", "-5000", ""),
    ("22.01.30", "Date", "8/17/19", "2019-08-17", ""),
    ("22.01.30", "Date", "08/17/2019", "2019-08-17", ""),
])
def test_typing_is_stored_as_a1_defines_it(fid, kind, typed, stored, unit):
    assert entry.normalize(dp_for(fid, kind), typed) == (stored, unit)


def test_what_cannot_be_read_is_refused_rather_than_stored_invalid():
    # "$" alone in an amount made a real case invalid against the schema
    for typed in ("about half a million", "$"):
        with pytest.raises(ValueError, match="not an amount"):
            entry.normalize(dp_for("22.01.23", "Amount"), typed)


def test_a_bare_number_in_the_grid_prints_with_its_unit():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    root = tree.getroot()
    comp = comparables.properties(root, "SalesComparable")[0]
    fid = "22.07.40"                       # Unfinished Area Below Grade, comparable
    edit.write(tree, fid, "2352", scope=comp)
    node = bind.locate(root, edit._binding_for(fid), "UnitBelowGradeUnfinishedAreaMeasure", comp, 1)
    assert node.text == "2352" and node.get("AreaUnitOfMeasureType") == "SquareFeet"
    assert "2,352 Sq. Ft." in comparables.value_for(root, fid, comp)
    assert schema.validate(tree) == []


def test_a_write_that_would_break_the_schema_is_refused_by_the_store(tmp_path):
    from app.cases import SchemaRegression, Store
    store = Store(tmp_path / "cases")
    try:
        case = store.create(template="sf1_appraisal_v1_4", blank=False, name="guard")
        cid = case.case_id if hasattr(case, "case_id") else case
        tree = store.tree(cid)
        before = len(schema.validate(tree))
        node = next(tree.getroot().iter("{*}FinalListPriceAmount"))
        node.text = "$"                                   # what once reached a real case
        with pytest.raises(SchemaRegression):
            store.save_tree(cid, tree)
        assert len(schema.validate(store.tree(cid))) == before
    finally:
        store.conn.close()
