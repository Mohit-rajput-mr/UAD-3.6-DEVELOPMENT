"""Regression coverage for raw form values and failed-edit isolation."""
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from lxml import etree
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import schema


@pytest.fixture
def sample(tmp_path, monkeypatch):
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    case = store.create(template="sf1_appraisal_v1_4", blank=False)
    yield store, case.case_id
    store.conn.close()


def request():
    return Request({"type": "http", "headers": []})


def test_form_exposes_raw_amount_and_iso_date(sample):
    _, case_id = sample
    fields = {f["field_id"]: f for s in api.case_fields(case_id, section=1, only_filled=False)["sections"]
              for f in s["fields"]}
    assert fields["1.001"]["edit_value"] == "491000"
    assert fields["1.001"]["value"] == "$491,000"
    assert fields["1.003"]["edit_value"] == "2019-09-20"
    points = {e["data_point"]: e for e in fields["1.005"]["editors"]}
    assert points["FirstName"]["value"] == "Betty"
    assert points["LastName"]["value"] == "Borrower"


def test_amount_edit_preserves_valid_xml_and_shared_value(sample):
    store, case_id = sample
    # entered where it comes from (26.007); the Summary's 1.001 redisplays it
    result = api.set_field(case_id, "26.007", request(), {"value": "492000"})
    assert result["value"] == "$492,000"
    assert schema.validate(store.tree(case_id)) == []
    assert store.tree(case_id).find(".//{*}OpinionOfValueAmount").text == "492000"


def test_unreadable_edit_does_not_modify_case(sample):
    store, case_id = sample
    before = store.xml_path(case_id).read_bytes()
    with pytest.raises(HTTPException) as failure:
        api.set_field(case_id, "1.033", request(), {"value": "Test defect"})
    assert failure.value.status_code == 422
    assert store.xml_path(case_id).read_bytes() == before


def test_an_edit_never_leaves_the_document_invalid(sample):
    """Setting Transfer Terms used to put PriorSalesOrTransfersIndicator inside
    SALES_HISTORY, which the subschema does not allow: one edit in the form and
    the whole case stopped validating.  A discriminator is written only where
    the schema accepts it."""
    store, case_id = sample
    assert schema.validate(store.tree(case_id)) == []
    try:
        api.set_field(case_id, "21.002", request(), {"value": "Sale"})
    except HTTPException as refused:
        # Refusing the edit is a fine answer; corrupting the document is not.
        assert refused.status_code == 422
    errors = schema.validate(store.tree(case_id))
    assert errors == [], [str(e) for e in errors[:3]]


@pytest.mark.parametrize("field_id", ["10.012", "21.000"])
@pytest.mark.parametrize("answer", ["true", "false"])
def test_a_yes_no_whose_container_carries_a_link_label_can_be_answered(sample, field_id, answer):
    """A-1 marks these indicators @xlink:label -- their container's identity,
    not a unit.  Answering Prior Sales or Transfers used to crash, because the
    writer took any attribute for a unit and lxml rejects a prefixed name."""
    from lxml import etree as _etree

    store, case_id = sample
    xl = "{http://www.w3.org/1999/xlink}label"
    before = sorted(n.get(xl) for n in store.tree(case_id).getroot().iter()
                    if isinstance(n.tag, str) and n.get(xl))
    api.set_field(case_id, field_id, request(), {"value": answer})
    tree = store.tree(case_id)
    after = sorted(n.get(xl) for n in tree.getroot().iter()
                   if isinstance(n.tag, str) and n.get(xl))
    assert before == after, "answering the question relabelled a container"
    assert schema.validate(tree) == []


def test_only_a_unit_of_measure_is_treated_as_a_unit():
    from uad import entry

    assert entry.unit_attribute({"attribute": "@AreaUnitOfMeasureType"}) == "AreaUnitOfMeasureType"
    assert entry.unit_attribute({"attribute": "@LinearUnitOfMeasureType"}) == "LinearUnitOfMeasureType"
    assert entry.unit_attribute({"attribute": "@xlink:label"}) == ""
    assert entry.unit_attribute({}) == ""


@pytest.mark.parametrize("details,typed,stored", [
    ("YYYY", "1998", "1998"),
    ("YYYY", "09/20/1998", "1998"),
    ("YYYY-MM", "09/2019", "2019-09"),
    ("YYYY-MM", "2019-09-17", "2019-09"),
    ("YYYY-MM-DD", "9/5/19", "2019-09-05"),
    ("YYYY-MM-DD", "2019-09", None),
    ("YYYY-MM-DD", "02/30/2019", None),
    ("YYYY-MM", "1998", None),
])
def test_a_date_is_stored_at_the_precision_a1_gives_it(details, typed, stored):
    """A bare year was never a date, so Year Built could not be saved; a full
    date in a month-only field was stored as typed and failed the schema."""
    from uad import entry

    assert entry._date(typed, details) == stored


def test_year_built_can_be_entered(sample):
    store, case_id = sample
    result = api.set_field(case_id, "8.010", request(), {"value": "1998"})
    assert result["written"]["new"] == "1998"
    assert schema.validate(store.tree(case_id)) == []


@pytest.mark.parametrize("field_id,structure", [
    ("3.011", "Condominium"), ("3.012", "Cooperative"), ("3.013", "Condop")])
def test_a_tick_on_a_legal_structure_row_stores_that_structure(sample, field_id, structure):
    """C-1 asks three Yes/No rows; A-1 stores one ProjectLegalStructureType.
    The tick itself ("true") is not a legal structure, so storing it made the
    document invalid and the question could not be answered."""
    store, case_id = sample
    api.set_field(case_id, field_id, request(), {"value": "true"})
    tree = store.tree(case_id)
    subject = tree.getroot().find(".//{*}PROJECT_DETAIL/{*}ProjectLegalStructureType")
    stored = {n.text for n in tree.getroot().iter("{*}ProjectLegalStructureType")}
    assert structure in stored and "true" not in stored
    assert schema.validate(tree) == []


def test_no_on_one_structure_leaves_a_different_structure_alone():
    from copy import deepcopy

    from lxml import etree as _etree

    from uad import edit, templates

    tree = _etree.parse(str(templates.get("condo1_appraisal_v1_4").path))
    edit.write(tree, "3.012", "true", binding=edit.field("3.012").binding)
    before = sorted(n.text for n in tree.getroot().iter("{*}ProjectLegalStructureType"))
    # No on Condominium says nothing when the project is a Cooperative
    edit.write(tree, "3.011", "false", binding=edit.field("3.011").binding)
    after = sorted(n.text for n in tree.getroot().iter("{*}ProjectLegalStructureType"))
    assert before == after


def test_each_value_gets_the_control_its_data_point_calls_for():
    from uad.report import form

    assert not form.choices_for("8.010"), "Year Built offered true/false instead of a year"
    assert not form.choices_for("18.009"), "Units Rented offered true/false instead of a count"
    assert [v for v, _ in form.choices_for("18.028")] == [
        "FirstLien", "FourthLien", "SecondLien", "ThirdLien"]
    assert form.choices_for("25.053"), "a closed code list should be picked"
    assert "data-pick" in (form._value_control(None, "20.002", "Yes") or ""), (
        "an arm's length Yes/No is a pair of boxes, not a text box")


def test_the_clients_second_role_can_be_changed(sample):
    """C-1's 'Client/[Party Role Type]' header is the client party's SECOND
    role -- Attorney, Lender, Investor -- beside the fixed 'Client' role that
    names the party at all.  A-1's own Additional Context for this field
    names the party by its Client role, which is right for finding *which*
    party and wrong for finding *which of its two roles* to write: scoping
    the write there meant the field tried to overwrite the very anchor it
    was found by, and a re-read by the same rule could not see what had just
    been saved."""
    store, case_id = sample
    result = api.set_field(case_id, "2.011", request(), {"value": "Attorney"})
    assert result["written"]["new"] == "Attorney"
    assert "Attorney" in result["value"]

    root = store.tree(case_id).getroot()
    roles = None
    for party in root.iter("{*}PARTY"):
        found = [d.findtext("{*}PartyRoleType") for d in party.iter("{*}ROLE_DETAIL")]
        if "Client" in found:
            roles = found
    assert roles is not None and "Client" in roles and "Attorney" in roles, roles
    assert schema.validate(store.tree(case_id)) == []

    # changing it again must not create a third role
    api.set_field(case_id, "2.011", request(), {"value": "Investor"})
    root = store.tree(case_id).getroot()
    for party in root.iter("{*}PARTY"):
        found = [d.findtext("{*}PartyRoleType") for d in party.iter("{*}ROLE_DETAIL")]
        if "Client" in found:
            assert sorted(x for x in found if x) == sorted(["Client", "Investor"]), found


def test_an_amenity_is_written_to_its_own_category(sample):
    """A-1 groups amenities by category (Water Features, Outdoor Accessories,
    Whole Home...) in AMENITY_CATEGORY blocks picked by AmenityCategoryType,
    not by position, so a data point with no explicit "requires" (like
    Water Features -> Ingroun Pool) has nowhere else to say which category it
    belongs to except its own Additional Context.  Writing it used to grab
    whichever AMENITY_CATEGORY the document already had first -- here,
    Outdoor Accessories -- so an inground pool was silently filed as a fence
    and never read back."""
    from uad import bind

    store, case_id = sample
    result = api.set_field(case_id, "22.12.03", request(), {"value": "IngroundPool"})
    assert result["value"], "the amenity did not read back where it was written"

    root = store.tree(case_id).getroot()
    by_category = {}
    for cat in root.iter("{*}AMENITY_CATEGORY"):
        kind = cat.findtext(".//{*}AmenityCategoryType")
        by_category[kind] = [a.findtext(".//{*}AmenityType")
                             for a in cat.iter("{*}AMENITY")]
    assert "IngroundPool" in by_category.get("WaterFeatures", []), by_category
    assert "IngroundPool" not in by_category.get("OutdoorAccessories", []), by_category
    assert schema.validate(store.tree(case_id)) == []


def test_an_unmarked_field_outside_a_discriminated_container_is_untouched(sample):
    """The discriminator fallback that fixed the amenity write must not fire
    for an ordinary field just because its free-text A-1 context happens to
    match some other field's category name -- that collision once wrote
    "Unit" into a subject's address while editing a comparable's."""
    from uad import edit

    pf = edit.field("22.01.17")  # a comparable's Property Address
    dp = edit.choose_data_point(pf.binding)
    assert edit._marks(dp, "22.01.17") == {}, (
        "an ordinary field outside AMENITY/AMENITY_CATEGORY/PARTY picked up "
        "a discriminator from an unrelated field with a matching context string")


def test_a_second_cost_approach_block_does_not_swallow_the_rest_of_the_document(sample):
    """Depreciated Cost - Dwelling packs two different repeating containers
    at different nesting levels under the same subsection (a Cost New line
    inside REPLACEMENT_REPRODUCTION_COSTS; Physical/Functional/External
    Depreciation inside the outer IMPROVEMENT_COST_AND_DEPRECIATED_VALUE
    itself), so entering Cost New and then a depreciation figure asks
    _make_instance for a second repeat of the OUTER container while sitting
    on an existing instance of it.  It treated that existing instance as the
    document root and re-created the entire rest of the message as its
    child -- DOCUMENT_SETS and everything below it -- rather than adding a
    plain sibling."""
    store, case_id = sample
    api.set_field(case_id, "25.009", request(), {"value": "200000"})
    api.set_field(case_id, "25.011", request(), {"value": "30000"})
    tree = store.tree(case_id)
    root = tree.getroot()

    for block in root.iter("{*}IMPROVEMENT_COST_AND_DEPRECIATED_VALUE"):
        assert block.find("{*}DOCUMENT_SETS") is None, (
            "a Cost Approach block swallowed the rest of the document")
    assert len(root.findall(".//{*}DOCUMENT_SETS")) == 1
    assert schema.validate(tree) == []


def test_a_cost_approach_total_can_be_entered_directly(sample):
    """C-1 draws a 'Total' bar under Depreciated Cost - Dwelling; A-1 gives
    it its own plain Amount data point (ImprovementEstimatedTotalCostAmount,
    25.018) exactly like the lines above it, so the appraiser enters it the
    same way as any other Amount field."""
    store, case_id = sample
    result = api.set_field(case_id, "25.018", request(), {"value": "165000"})
    assert result["written"]["new"] == "165000"
    tree = store.tree(case_id)
    assert tree.getroot().findtext(".//{*}ImprovementEstimatedTotalCostAmount") == "165000"
    assert schema.validate(tree) == []


def test_failed_batch_item_cannot_leak_mutations(sample):
    store, case_id = sample
    result = api.set_fields(case_id, request(), {"fields": [
        {"field_id": "1.033", "value": "Test defect"},
        {"field_id": "26.007", "value": "492000"},
    ]})
    assert len(result["failed"]) == len(result["written"]) == 1
    assert b"Test defect" not in etree.tostring(store.tree(case_id))
    assert schema.validate(store.tree(case_id)) == []
