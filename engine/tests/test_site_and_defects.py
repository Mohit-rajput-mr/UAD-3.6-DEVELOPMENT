"""Site and defect tables against the official D-1 PDFs (E-107..E-111).

Each check names what the official sample PDF prints, so a failure here is a
departure from the published report, not from our own earlier output.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, templates  # noqa: E402
from uad.report import form  # noqa: E402


def _text(key: str, section: str) -> str:
    blocks = form.build(templates.load(key))
    parts = []
    for b in blocks:
        if not b.visible or not b.section.startswith(section):
            continue
        if b.left or b.right:
            parts += [html.unescape(re.sub(r"<[^>]+>", " ", i.html)) if i.kind == "table"
                      else f"{i.label} {' '.join(i.values)} {i.suffix}" for i in b.left + b.right if i.visible]
        else:
            parts.append(html.unescape(re.sub(r"<[^>]+>", " ", b.html or b.title)))
    return " ".join(" ".join(parts).split())


def test_commentary_categories_resolve_from_the_label():
    # a control character in the regex had stopped every label-derived category
    cats = bind.commentary_categories()
    assert cats["4.030"] == "SiteInfluences"
    assert cats["4.042"] == "SiteViews"
    # B-1 misspells the energy category; A-1's enumeration is what is written
    assert cats["6.016"] == "EnergyEfficientAndGreenFeatures"


def test_site_influence_and_view_commentary_print():
    site = _text("2_to_4_unit_appraisal_v1_4", "Site")
    assert "Site Influence Commentary Additional commentary" in site
    assert "View Commentary Additional commentary" in site


def test_site_influence_rows_carry_proximity_and_impact():
    site = _text("2_to_4_unit_appraisal_v1_4", "Site")
    assert "Busy Roadway Bordering Adverse Site fronts" in site
    # scenario 2 has two influences; the second keeps its own name
    two = _text("2_to_4_unit_scenario_2_appraisal_v1_2", "Site")
    assert "Residential Bordering Neutral" in two


def test_corner_unit_prints_no():
    unit = _text("condo1_appraisal_v1_4", "Unit Interior")
    assert "Corner Unit No" in unit


@pytest.mark.parametrize("key,heads", [
    ("2_to_4_unit_appraisal_v1_4", ["Dwelling Exterior - Building 1", "Unit Interior - Building 1 - Unit 1",
                                    "Dwelling Exterior - Building 2", "Unit Interior - Building 2 - Unit 2"]),
    ("mh1_appraisal_v1_4", ["Outbuilding - Barn"]),
    ("condo1_appraisal_v1_4", ["Unit Interior", "Subject Property Amenities"]),
])
def test_reconciliation_defects_group_by_structure_in_order(key, heads):
    text = _text(key, "Reconciliation")
    at = [text.find(h) for h in heads]
    assert all(a >= 0 for a in at), (heads, at)
    assert at == sorted(at)


def test_defect_rows_list_by_feature_then_location():
    text = _text("2_to_4_unit_appraisal_v1_4", "Reconciliation")
    unit1 = text[text.find("Unit Interior - Building 1 - Unit 1"):text.find("Dwelling Exterior - Building 2")]
    order = [unit1.find(w) for w in ("Appliances Kitchen", "Cabinetry Full Bathroom",
                                     "Cabinetry Kitchen", "Doors Full Bathroom", "Walls and Ceiling")]
    assert all(o >= 0 for o in order) and order == sorted(order), order


def _tabs(key: str) -> list[str]:
    return [b.title for b in form.build(templates.load(key)) if b.kind == "tab" and b.visible]


def test_each_dwelling_is_followed_by_its_units():
    tabs = [t for t in _tabs("2_to_4_unit_appraisal_v1_4") if t.startswith(("Dwelling", "Unit"))]
    assert tabs == ["Dwelling Exterior - Building 1", "Unit Interior - Building 1 - Unit 1",
                    "Dwelling Exterior - Building 2", "Unit Interior - Building 2 - Unit 2"]


def test_dwelling_exhibits_hold_rear_and_defect_photos():
    text = _text("2_to_4_unit_appraisal_v1_4", "Dwelling Exterior")
    assert text.count("Dwelling Rear") >= 2           # one per building
    assert "Apparent Defects, Damages, Deficiencies - Roof" in text
    sf1 = _text("sf1_appraisal_v1_4", "Dwelling Exterior")
    # the caption is part of the title, printed once
    assert "Roof - Damaged Flashing Damaged Flashing" not in sf1
    assert "Apparent Defects, Damages, Deficiencies - Roof - Damaged Flashing" in sf1


@pytest.mark.parametrize("key,walls", [("sf5_appraisal_v1_2", "Brick | Wood"),
                                       ("mh2_appraisal_v1_4", "Aluminum | Synthetic Stone")])
def test_every_wall_material_prints(key, walls):
    assert walls in _text(key, "Dwelling Exterior")


def test_noncontinuous_area_and_caption_dash():
    text = _text("condo2_appraisal_v1_4", "Dwelling Exterior")
    assert "1 - Family Room" in text                  # B-1 p175 Count - Room Type
    assert "Noncontinuous Area - Bonus Room" in text


def test_market_graph_lists_only_graphs():
    text = _text("sf1_appraisal_v1_4", "Market")
    assert "Absorption Rate" in text and "Year Built of Sales" in text
    graph = text[text.find("Graph"):text.find("Graph") + 120]
    assert "Dwelling Front" not in graph and "Property Photo" not in graph


def test_unit_rules_read_outside_the_unit():
    # 10.026 is gated on the project's LandOwnedInCommonIndicator
    assert "Non-Residential Use in Unit No" in _text("condo1_appraisal_v1_4", "Unit Interior")
    assert "Non-Residential Use in Unit" not in _text("sf1_appraisal_v1_4", "Unit Interior")


@pytest.mark.parametrize("key,shown", [("condo1_appraisal_v1_4", False), ("sf1_appraisal_v1_4", True)])
def test_accessibility_follows_its_rule(key, shown):
    # B-1 p204: displays when AccessibilityFeatureType <> "None"
    assert ("Accessibility Features for Individuals" in _text(key, "Unit Interior")) is shown


@pytest.mark.parametrize("key,shown", [("condo1_appraisal_v1_4", False), ("sf3_appraisal_v1_4", True)])
def test_adu_checkbox_follows_the_adu_count(key, shown):
    blocks = form.build(templates.load(key))
    adu = [i for b in blocks for i in b.left + b.right if i.label == "ADU" and i.visible]
    assert bool(adu) is shown


@pytest.mark.parametrize("key,want", [
    ("sf1_appraisal_v1_4", "Outdoor Accessories Fence Outdoor Living Deck Wood 400 Sq. Ft. Porch Concrete "
                           "351 Sq. Ft. Whole Home Indoor Fireplace Total Number - 1 Miscellaneous Media Room Wet Bar"),
    ("mh1_appraisal_v1_4", "Outdoor Living Deck Wood 100 Sq. Ft. Not Attached to Manufactured Home Wood "
                           "100 Sq. Ft. Not Attached to Manufactured Home Whole Home Indoor Fireplace Total Number - 1"),
    ("sf3_appraisal_v1_4", "Water Features Inground Pool Concrete Heated"),
])
def test_amenities_print_as_the_samples_do(key, want):
    assert want in _text(key, "Subject Property Amenities")


@pytest.mark.parametrize("key,want", [
    ("sf1_appraisal_v1_4", "1 Typically Motivated 09/01/2018 $430,000 MLS 2 None MLS 3 None MLS"),
    ("mh1_appraisal_v1_4", "1 None MLS 2 Short Sale 03/28/2018 $332,000 MLS 3 None MLS"),
    ("condo1_appraisal_v1_4", "3 Typically Motivated 12/31/2018 $750,000 Assessor Record MLS "
                              "Typically Motivated 09/15/2018 $725,000 Assessor Record MLS 4 None MLS"),
])
def test_comparable_transfer_history_rows(key, want):
    # B-1 p286: a line per comparable, "None" or each prior transfer newest first
    assert want in _text(key, "Prior Sale and Transfer History")


def test_subject_transfer_history():
    sf1 = _text("sf1_appraisal_v1_4", "Prior Sale and Transfer History")
    assert "Prior Sales or Transfers None Data Source MLS Analysis" in sf1     # only the indicator's source
    sf2 = _text("sf2_appraisal_v1_4", "Prior Sale and Transfer History")
    assert "Typically Motivated 08/16/2016 $750,000 Assessor Record" in sf2
    assert "Prior Sales or Transfers" not in sf2


def test_rent_schedule_lists_every_unit_with_subtotals():
    text = _text("2_to_4_unit_appraisal_v1_4", "Rental Information")
    assert "Unit 1 Yes Tenant $875 Yes No No No No Unit 2 No Owner $0 No" in text
    assert ("Actual Income (Monthly) Rent Unit 1 $875 Unit 2 $0 Subtotal $875 Other Real Property Rental "
            "Income None $0 Subtotal $0 Total $875") in text
    assert "Opinion of Market Income (Monthly) Rent Unit 1 $875 Unit 2 $925 Subtotal $1,800" in text
    assert "[Unit Identifier]" not in text


def test_rental_comparables_strip_and_a_grid_per_unit():
    text = _text("2_to_4_unit_appraisal_v1_4", "Rental Information")
    assert "Comparable #1 8275 Youngish St Surfside, HI 12345 Data Source: MLS 142332 Lease Start Date: 09/2019 Actual Rent: $925" in text
    # two units to a line (C-1 p33): Unit 1 with #1-#3, Unit 2 with #1, #4, #5
    assert "Subject Comparables Subject Comparables Unit 1 #1 #2 #3 Unit 2 #1 #4 #5" in text
    # Unit 2 is not rented: its own answers, not Unit 1's
    assert "Furnished No No No No — No No No" in text


def test_grm_grid_and_formula_as_the_sample_prints():
    from uad.report import comparables
    tree = templates.load("2_to_4_unit_appraisal_v1_4")
    g = comparables.build(tree, "grm")[0]
    rows = {r.label: [c.text for c in r.cells] for r in g.rows}
    assert rows["Sale Date"] == ["02/24/2019", "05/31/2019", "08/30/2019"]   # the subject's condition dropped
    assert rows["Gross Monthly Rent"][0] == "~$2,300"                       # the estimate mark leads
    assert "Accessory Dwelling Units" not in rows                            # 0 everywhere: not applicable
    text = _text("2_to_4_unit_appraisal_v1_4", "Income Approach")
    assert ("Total Monthly Market Rent × Gross Rent Multiplier = Indicated Value by Income Approach "
            "$1,800 110 $198,000") in text


def test_rental_and_grm_exhibits_are_each_comparables_photo():
    rent = _text("2_to_4_unit_appraisal_v1_4", "Rental Information")
    assert "Comparable #5 This is where the Rental Comparable 5 photo would display." in rent
    grm = _text("2_to_4_unit_appraisal_v1_4", "Income Approach")
    assert "Comparable #3 This is where the GRM Comparable 3 photo would display." in grm
    assert "[Photo Caption Displays Here]" not in grm


@pytest.mark.parametrize("section", ["Site", "Cost Approach"])
def test_land_comparables_a_line_each(section):
    text = _text("mh1_appraisal_v1_4", section)
    assert ("1 123 Water Front Dr Some City, VA 20141 Alpine MLS 238183040 555666999000111 4 Acres "
            "01/01/2018 $200,000 2 Lot: 123 Block: 321") in text


def test_data_sources_tied_by_the_arcrole_sheet():
    assert "Project Information Data Source Condominium Questionnaire Total Units" in _text(
        "condo1_appraisal_v1_4", "Project Information")
    cost = _text("mh1_appraisal_v1_4", "Cost Approach")
    assert "Cost Data Source Marshall & Swift" in cost and "Quality Rating Good" in cost


def test_every_revision_prints():
    text = _text("2_to_4_unit_appraisal_v1_4", "Revision History")
    assert "10/07/2019 Assignment Information Corrected borrower name 10/12/2019 Site Added comment" in text


def _grid(key, kind="sales"):
    from uad.report import comparables
    return comparables.build(templates.load(key), kind)[0]


def test_sales_grid_topography_and_no_adu_rows_without_adus():
    g = _grid("sf1_appraisal_v1_4")
    labels = [r.label.strip() for r in g.rows]
    assert "Topography" in labels and "Site Characteristics" not in labels
    assert "Location of ADU" not in labels and not any(l.startswith("ADU Interior") for l in labels)
    assert not any(l.startswith("Outbuilding (") for l in labels)       # no stray dwelling Cooling


def test_sales_grid_outbuildings_by_position():
    g = _grid("mh1_appraisal_v1_4")
    obs = [(r.subject, [c.text for c in r.cells], [c.adjustment for c in r.cells])
           for r in g.rows if r.label.strip() == "Outbuilding Type"]
    assert obs[0][:2] == ("Barn", ["Barn", "Shed", "Workshop"])
    assert obs[1][0] == "Rec Room/Garage" and obs[1][1][0] == "Workshop" and obs[1][2][0] == "$(10,000)"
    g3 = _grid("sf3_appraisal_v1_4")
    ob3 = [r for r in g3.rows if r.label.strip() == "Outbuilding Type"]
    assert len(ob3) == 1 and [c.text for c in ob3[0].cells] == ["Stable", "Pool House", "Studio"]


def test_sales_grid_repeats_units_dwellings_and_adus():
    g = _grid("2_to_4_unit_appraisal_v1_4")
    ids = [r.subject for r in g.rows if r.label.strip() == "Structure ID | Unit ID"]
    assert ids == ["Building 1 | Unit 1", "Building 2 | Unit 2"] * 2     # Unit(s), then Interior
    assert [r.subject for r in g.rows if r.label.strip() == "Structure ID"] == ["Building 1", "Building 2"]
    walls = [r for r in g.rows if r.label.strip() == "Walls and Ceiling"]
    assert walls and walls[0].cells[2].text.startswith("Standard Dry Wall")
    g3 = _grid("sf3_appraisal_v1_4")
    loc = [r for r in g3.rows if r.label.strip() == "Location of ADU"]
    assert loc[0].subject == "Standalone ADU" and [c.text for c in loc[0].cells] == ["Dwelling", "Dwelling", "ADU/Garage"]
    beds = [r.subject for r in g3.rows if r.label.strip() == "Bedrooms"]
    assert beds == ["5", "0"]                      # the dwelling's, then the ADU's own
    flooring = next(r for r in g3.rows if r.label.strip() == "Walls and Ceiling")
    assert flooring.subject.startswith("Standard 8-9 Ft.")             # not the flooring text


def test_the_sketch_table_takes_only_sketches_and_floor_plans():
    # SF1 holds no sketch: its RESNET exhibit's caption must not print as one
    printed = _text("sf1_appraisal_v1_4", "Sketch")
    assert "RESNET" not in printed
    # A-1 narrows the table's category column to these two
    assert form._image_categories("7.002.2") == {"FloorPlan", "SubjectPropertyImprovementSketch"}


@pytest.mark.parametrize("key,expected", [
    ("sf1_appraisal_v1_4", "Residential Full Neutral"),                       # one view: no "(Primary)"
    ("coop1_appraisal_v1_4", "Parking Lot (Primary) Full Neutral City Street"),  # primary first, marked after
])
def test_the_primary_view_follows_b1(key, expected):
    assert expected in _text(key, "Site")


def _sections(key):
    return {b.section.split(" - ")[0] for b in form.build(templates.load(key)) if b.kind == "tab" and b.visible}


@pytest.mark.parametrize("key,energy,disaster", [
    # what each D-1 PDF prints (validated on all 12 against the official tabs)
    ("sf1_appraisal_v1_4", True, False),
    ("condo1_appraisal_v1_4", False, False),            # all three indicators false
    ("condo2_appraisal_v1_4", True, True),
    ("2_to_4_unit_appraisal_v1_4", False, True),         # comparable 2's "None" is not the subject's
])
def test_self_gated_sections_print_by_their_b1_rule(key, energy, disaster):
    tabs = _sections(key)
    assert ("Energy Efficient and Green Features" in tabs) is energy
    assert ("Disaster Mitigation" in tabs) is disaster


@pytest.mark.parametrize("key,section,present,absent", [
    # B-1 p279: the note prints only when personal property is conveyed
    ("sf1_appraisal_v1_4", "Sales Contract", ["Personal property is not included", "Known Sales Concessions Yes"], []),
    ("sf2_appraisal_v1_4", "Sales Contract", [], ["Personal property is not included"]),
    # B-1 p82: defects exist, none needing action -> the sentence, not "None"
    ("condo1_appraisal_v1_4", "Summary", ["There are no apparent defects"], []),
    ("mh1_appraisal_v1_4", "Summary", ["There are no apparent defects"], []),
    ("condo2_appraisal_v1_4", "Summary", [], ["There are no apparent defects"]),
    # B-1 p370: a cooperative's value and note
    ("coop1_appraisal_v1_4", "Reconciliation", ["$548,999 (Cooperative Interest)",
                                                "The market value represents the cooperative interest"], []),
    # A-1 per-location text: 4.017 prints "false" as "None"
    ("sf1_appraisal_v1_4", "Site", ["Non-Residential Use None"], []),
    # the appraiser's own inspection date (A-1 context shares PartyRoleType)
    ("sf1_appraisal_v1_4", "Assignment Information", ["Inspection Date 09/20/2019"], []),
    # the listing table's caption and the analysis label (C-1 ID under the label)
    ("sf1_appraisal_v1_4", "Subject Listing Information",
     ["minimum 1 year look back", "Analysis of Subject Property Listing History The only listing"], []),
])
def test_static_notes_and_labels_follow_b1(key, section, present, absent):
    text = _text(key, section)
    for p in present:
        assert p in text, p
    for a in absent:
        assert a not in text, a


def test_outbuildings_print_by_name():
    tabs = [t for t in _tabs("mh1_appraisal_v1_4") if t.startswith("Outbuilding")]
    assert tabs == ["Outbuilding - Barn", "Outbuilding - Rec Room/Garage"]


@pytest.mark.parametrize("key,expected", [
    ("sf1_appraisal_v1_4", None),          # no transfer fee block: no row (D-1 SF1 prints none)
    ("condo1_appraisal_v1_4", "None"),     # indicator false
    ("coop1_appraisal_v1_4", "$3,000"),    # the fee's own block, not the dues
])
def test_unit_transfer_fees_read_their_own_charge(key, expected):
    text = _text(key, "Project Information")
    m = re.search(r"Unit Transfer Fees (\S+)", text)
    assert (m.group(1) if m else None) == expected
