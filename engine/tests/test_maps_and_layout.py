"""Maps, image layout (Appendix E) and the data that does not print.

The map tests run without the network: tiles are stubbed, coordinates given.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import extra, maps, schema, templates  # noqa: E402
import app  # noqa: E402,F401
from uad.report import form  # noqa: E402


# ----------------------------------------------------------------- maps
@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(maps, "geocode", lambda address: None)


def _places():
    ps = [maps.Place("subject", "Subject", ["18 North Street"], "a", 0, 41.23797, -73.68852),
          maps.Place("sale", "Comparable Sale 1", ["15 South Beechwood Road"], "b", 1, 41.23151, -73.70578),
          maps.Place("sale", "Comparable Sale 3", ["46 Bedford Avenue"], "d", 3, 41.23767, -73.68951),
          maps.Place("listing", "Comparable Listing 4", ["27 Winding Lane"], "e", 4, 41.23790, -73.68747)]
    return ps


def test_distance_and_direction_from_the_subject(offline):
    ps = _places()
    assert maps.locate(ps) == []
    notes = {p.title: p.note for p in ps}
    assert notes["Comparable Sale 1"] == "1.00 miles SW"
    assert notes["Comparable Sale 3"] == "0.06 miles W"
    assert notes["Comparable Listing 4"] == "0.05 miles E"


def test_sample_coordinates_that_cannot_be_right_are_not_trusted(offline):
    """D-1's fictional coordinates sit in the Atlantic; they are not used."""
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    ps = maps.places(tree.getroot())
    assert ps[0].kind == "subject" and len(ps) >= 4
    assert not maps.plausible(ps[0], None)


def test_no_aerial_map_is_drawn_or_kept():
    """Appendix E / B-1 define the Sales Comparison Map and nothing aerial."""
    import app.mapper as mapper
    assert mapper.CAPTION == "Sales Comparison Map" and "Aerial Map" in mapper.RETIRED
    tool = (Path(__file__).resolve().parents[1] / "app" / "ui" / "map" / "index.html").read_text(encoding="utf-8")
    assert "#viewAer,#btnFrame,#pinbar{display:none" in tool
    assert "'Aerial Map'" not in tool


def test_the_tool_frames_the_map_at_the_appendix_e_page_frame():
    """45 x 48 picas less 6 pt each side = 528 x 564 pt = 704 x 752 CSS px."""
    tool = (Path(__file__).resolve().parents[1] / "app" / "ui" / "map" / "index.html").read_text(encoding="utf-8")
    assert "width:704px !important;height:752px !important" in tool


# ---------------------------------------------------------- image layout
def test_sketch_graph_and_sales_map_set_as_appendix_e_says():
    """SF2 carries a sketch, a price-trend graph and a sales comparison map:
    the sketch and map set full page (sketch in Sketch, map under its H1), the
    graph sets 45 x 20 picas."""
    tpl = templates.get("sf2_appraisal_v1_4")
    blocks = form.build(etree.parse(str(tpl.path)), folder=tpl.path.parent)
    by_section: dict[str, list[str]] = {}
    for b in blocks:
        if b.visible and b.kind == "exhibits":
            by_section.setdefault(b.section, []).append(b.html)
    assert any("ex full" in h for h in by_section.get("Sketch", [])), "the sketch does not print"
    assert any("ex graph" in h for h in by_section.get("Market", [])), "the graph is not 45 x 20 picas"
    sca = [b for b in blocks if b.section == "Sales Comparison Approach" and b.visible]
    titles = [b.title for b in sca if b.kind == "h1"]
    assert "Sales Comparison Map" in titles
    after = sca[[b.title for b in sca].index("Sales Comparison Map") + 1]
    assert after.kind == "exhibits" and "ex full" in after.html


def test_no_loose_grid_pieces_print_under_the_grid():
    tpl = templates.get("sf2_appraisal_v1_4")
    blocks = form.build(etree.parse(str(tpl.path)), folder=tpl.path.parent)
    sca = [b for b in blocks if b.section == "Sales Comparison Approach" and b.visible]
    texts = [b.html for b in sca if b.kind == "text"]
    assert not any("1 2 3" in t or t.strip().endswith("$0</div>") for t in texts), texts


# ------------------------------------------------ data that does not print
def test_extra_rows_come_from_a1_and_exclude_generated_data():
    names = {r.name for r in extra.rows()}
    assert {"CostApproachIndicator", "SalesComparisonApproachIndicator", "LatitudeIdentifier",
            "ReconsiderationOfValueIndicator", "CostToRepairType"} <= names
    assert not names & {"ImageFileLocationIdentifier", "ValuationSoftwareVendorName",
                        "PropertyOrdinalNumber", "RoomType", "AssociationChargeType"}


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_extra_reads_every_sample_and_writes_valid_xml(key):
    tree = etree.parse(str(templates.get(key).path))
    groups = extra.groups(tree.getroot())
    assert groups and groups[0]["title"] == "Scope of work and report"
    row = extra.by_uid("1000.0027")                  # CostApproachIndicator
    written = extra.write(tree, row, "true")
    assert extra.read(written.getroot(), row)[0]["value"] == "true"
    assert schema.validate(written) == []


def test_extra_refuses_what_a1_does_not_allow():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    with pytest.raises(ValueError):
        extra.write(tree, extra.by_uid("1000.0027"), "maybe")
    with pytest.raises(ValueError):
        extra.write(tree, extra.by_uid("0100.0015"), "north")


# ------------------------------------------- editor: map box and days wording
def test_the_editor_always_has_one_sales_comparison_map_box_with_its_controls():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    html = form.galley_html(form.build(tree, edit=True), edit=True)
    assert html.count("data-map='SalesComparableMap'") == 1
    assert "class='mapedit'" in html                    # pan, zoom and arrange in place
    assert "data-map='aerial'" in html                  # the Site exhibits' aerial map
    printed = form.galley_html(form.build(tree))
    assert "maploader" not in printed and "mapedit" not in printed


def test_a_time_in_days_prints_as_b1_describes():
    from uad import bind, edit
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    b = edit._binding_for("26.010")
    for typed, shown in (("30-60 days", "30-60 days"), ("45", "45 days"), ("120 to 90", "90-120 days")):
        edit.write(tree, "26.010", typed, binding=b)
        assert bind.display_value(bind.read_parts(tree.getroot(), b), b) == shown
    names = [n for n, _ in bind.read_parts(tree.getroot(), b)]
    assert "MarketingOrExposureDaysCount" not in names   # never a count and a range at once
    assert schema.validate(tree) == []
