"""The deliverable must satisfy Appendix B-1's file-structure rules.

These checks failed silently before: the archive shipped 37 images that the XML
never referenced, which schema validation and the compliance rules both pass
over.  They are pinned here so that cannot recur.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from uad.report import grid, package, style_spec  # noqa: E402

SPEC_DIR = ROOT / "engine" / "spec"


@pytest.fixture(scope="module")
def images(tmp_path_factory):
    folder = tmp_path_factory.mktemp("Images")
    (folder / "DWELLING_FRONT_1.jpg").write_bytes(b"x")
    return folder


def _xml(*names: str) -> bytes:
    refs = "".join(
        f"<IMAGE><ImageFileLocationIdentifier>\\\\Images\\{n}"
        f"</ImageFileLocationIdentifier></IMAGE>" for n in names
    )
    return f'<?xml version="1.0" encoding="utf-8"?><MESSAGE>{refs}</MESSAGE>'.encode()


def test_every_image_must_be_referenced(images):
    problems = package.verify(b"%PDF-1.7", _xml(), images)
    assert any("never referenced" in p for p in problems)


def test_referenced_image_must_exist(images):
    problems = package.verify(b"%PDF-1.7", _xml("DWELLING_FRONT_1.jpg", "GONE.jpg"), images)
    assert any("missing from the Images folder" in p for p in problems)


def test_conforming_package_reports_no_problems(images):
    assert package.verify(b"%PDF-1.7", _xml("DWELLING_FRONT_1.jpg"), images) == []


def test_archive_refuses_to_exceed_the_size_limit(images, monkeypatch):
    monkeypatch.setattr(package, "MAX_ZIP_BYTES", 10)
    with pytest.raises(ValueError, match="60 MB limit"):
        package.build(
            pdf_bytes=b"%PDF-1.7" + b"0" * 5000,
            xml_bytes=_xml("DWELLING_FRONT_1.jpg"),
            image_dir=images,
        )


# ----------------------------------------------------------- specification
def test_grid_definition_matches_the_published_supplement():
    """153 rows across 17 groups, per Appendix B-1's Comparable Grids sheet."""
    entries = grid.definition()
    groups = [e for e in entries if e["kind"] == "group"]
    rows = [e for e in entries if e["kind"] == "row"]
    assert len(groups) == 17
    assert len(rows) == 153


def test_grid_splits_into_blocks_of_three_comparables():
    """Appendix E p62 shows three comparables at a time."""
    columns = ["Subject Property"] + [f"Comparable #{i}" for i in range(1, 5)]
    built = grid.ComparisonGrid(columns=columns)
    built.groups = [
        grid.GridGroup("Site", [grid.GridRow("Site Size", "1 ac", [grid.Cell()] * 4)])
    ]
    blocks = built.blocks()
    assert [b.comparable_count for b in blocks] == [3, 1]
    assert all(b.columns[0] == "Subject Property" for b in blocks)


def test_style_spec_carries_the_published_measurements():
    assert (style_spec.PAGE_WIDTH_IN, style_spec.PAGE_HEIGHT_IN) == (8.5, 14.0)
    assert style_spec.FULL_WIDTH_PICAS == 45
    assert style_spec.resolve("TB-SCA_sub-H1")["fill"] == "#333333"
    assert style_spec.resolve("TB_sub-H1")["fill"] == "#999999"
    assert style_spec.resolve("H1")["fill"] == "#e6e6e6"
    assert len(style_spec.URAR_SECTIONS) == 29


def test_column_layout_was_extracted_from_the_style_guide():
    path = SPEC_DIR / "layout.json"
    assert path.exists(), "run engine/uad/report/extract_layout.py"
    layout = json.loads(path.read_text(encoding="utf-8"))
    assert len(layout) >= 27
    # Appendix E p33: the value opinion sets left, its condition right.
    summary = layout["Summary"]["columns"]
    assert summary["Opinion of Market Value"] == "left"
    assert summary["Market Value Condition"] == "right"


# ------------------------------------------------- property-type templates
def test_every_reference_scenario_classifies_to_its_property_type():
    """The kind of property is read from the data, not a form number."""
    import glob
    import os
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "engine"))
    from uad import model
    from uad.report import profiles

    expected = {
        "2- to 4-unit_Appraisal": "TwoToFourUnit",
        "2- to 4-unit_Scenario_2_Appraisal": "TwoToFourUnit",
        "Condo1_Appraisal": "Condominium",
        "Condo2_Appraisal": "Condominium",
        "Coop1_Appraisal": "Cooperative",
        "MH1_Appraisal": "ManufacturedHome",
        "MH2_Appraisal": "ManufacturedHome",
        "SF3_Appraisal": "SingleFamily",
        "SF4_Appraisal": "SingleFamily",
        "SF5_Appraisal": "SingleFamily",
    }
    for folder, kind in expected.items():
        matches = glob.glob(str(ROOT / "_ref/usecases" / folder / "*.xml"))
        if not matches:
            continue
        assert profiles.classify(model.parse(matches[0])) == kind, folder


def test_every_reference_scenario_exposes_its_properties():
    """A DEAL may carry an inspection service beside the valuation service."""
    import glob
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "engine"))
    from uad import model

    for path in glob.glob(str(ROOT / "_ref/usecases/*_Appraisal/*.xml")):
        data = model.parse(path)
        assert model.properties(data), path
        assert model.subject(data) is not None, path
