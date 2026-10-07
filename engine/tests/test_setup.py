"""Report setup (uad/setup.py): the property type and the approaches, stated
first, decide the report's sections -- and a 2- to 4-unit report has its
Rental Information and Income Approach (owner, 2026-10-07)."""
import pytest

from uad import schema
from uad.report import form


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    from app import api
    from app.access import sign_in
    from app.cases import Store
    from app.main import app
    api.STORE = Store(tmp_path / "cases")
    api.RENDERER = None
    api.LAYOUTS = None
    with TestClient(app) as c:
        sign_in(c)
        yield c


def _tabs(cid):
    from app import api
    return [b.section for b in form.build(api.store().tree(cid), edit=True) if b.kind == "tab"]


@pytest.mark.parametrize("kind,units,approaches,want,unit_tabs", [
    ("single_family", 1, {}, set(), 1),
    ("two_to_four_unit", 3, {"rent": True, "income": True}, {"Rental Information", "Income Approach"}, 3),
    ("condominium", 1, {}, {"Project Information"}, 1),
    ("cooperative", 1, {}, {"Project Information"}, 1),
    ("manufactured", 1, {"cost": True}, {"Manufactured Home", "Cost Approach"}, 1),
])
def test_a_new_report_starts_as_the_kind_chosen(client, kind, units, approaches, want, unit_tabs):
    from app import api
    r = client.post("/api/cases", json={"blank": True, "setup": {
        "property_type": kind, "units": units, "approaches": approaches}})
    assert r.status_code == 200, r.text
    cid = r.json()["case_id"]
    got = client.get(f"/api/cases/{cid}/setup").json()
    assert got["property_type"] == kind and got["units"] == units
    tabs = _tabs(cid)
    optional = {"Rental Information", "Income Approach", "Cost Approach", "Project Information", "Manufactured Home"}
    assert {t for t in tabs if t in optional} == want
    assert sum(t.startswith("Unit Interior") for t in tabs) == unit_tabs
    assert not schema.validate(api.store().tree(cid))


def test_two_units_typed_in_a_single_family_report_bring_the_rental_sections(client):
    """The owner's case: a single-family report made multi-family by its unit
    count.  The 2-4 structure develops a rent schedule and income approach;
    the single-family report's "false" carried across switched them off."""
    cid = client.post("/api/cases", json={"blank": True}).json()["case_id"]
    r = client.patch(f"/api/cases/{cid}/fields/3.005", json={"value": "2"})
    assert r.status_code == 200 and r.json()["reshaped"]["property_type"] == "two_to_four_unit"
    tabs = _tabs(cid)
    assert "Rental Information" in tabs and "Income Approach" in tabs


def test_the_setup_switches_sections_on_and_off_in_an_open_report(client):
    cid = client.post("/api/cases", json={"blank": True}).json()["case_id"]
    r = client.put(f"/api/cases/{cid}/setup", json={"property_type": "two_to_four_unit", "units": 2,
                                                       "approaches": {"rent": True, "income": True}})
    assert r.status_code == 200 and r.json()["reshaped"]
    assert {"Rental Information", "Income Approach"} <= set(_tabs(cid))
    r = client.put(f"/api/cases/{cid}/setup", json={"property_type": "two_to_four_unit", "units": 2,
                                                       "approaches": {"rent": False, "income": False, "cost": True}})
    tabs = set(_tabs(cid))
    assert "Rental Information" not in tabs and "Income Approach" not in tabs and "Cost Approach" in tabs
    # back to single family: the co-op / project answers never linger
    client.put(f"/api/cases/{cid}/setup", json={"property_type": "cooperative"})
    client.put(f"/api/cases/{cid}/setup", json={"property_type": "single_family"})
    assert client.get(f"/api/cases/{cid}/setup").json()["property_type"] == "single_family"
    assert "Project Information" not in _tabs(cid)


def test_a_defect_added_in_a_units_table_is_that_units(client):
    """The owner's "dropdowns don't work": a defect row picked in a unit's (or
    a building's) own table was refused -- the DEFECT was built inside the
    unit.  It lives under the PROPERTY, tied to the unit by arcrole (D-1 2-4)."""
    import collections
    import re
    from app import api
    cid = client.post("/api/cases", json={"blank": True, "setup": {
        "property_type": "two_to_four_unit", "units": 2, "approaches": {"rent": True}}}).json()["case_id"]
    html = form.galley_html(form.build(api.store().tree(cid), edit=True), edit=True)
    for fid, value in (("10.057", "FullBathroom"), ("8.060", "Completion")):
        tag = next(t for t in re.findall(r"""<span class=["']v pick["'] data-tf=["']%s["'][^>]*>""" % re.escape(fid), html)
                   if "data-tnew" in t)
        attrs = dict(re.findall(r"""data-(\w+)=["']([^"']*)["']""", tag))
        r = client.patch(f"/api/cases/{cid}/cells/{fid}", json={
            "value": value, "key": "", "data_point": attrs["tdp"], "new": True, "scope": attrs["tscope"]})
        assert r.status_code == 200, r.text
    blocks = form.build(api.store().tree(cid))
    where = collections.Counter(b.section for b in blocks if b.visible and "Full Bathroom" in (b.html or ""))
    assert where == {"Unit Interior": 1, "Reconciliation": 1}, where
    assert not schema.validate(api.store().tree(cid))


def test_a_fixed_rows_second_answer_goes_in_the_row_its_first_made(client):
    """Dwelling Exterior features: Foundation's material creates the row; its
    condition, sent before the page has the row's key, goes in that row --
    it was refused ("the row could not be created") until the page reloaded."""
    import re
    from app import api
    cid = client.post("/api/cases", json={"blank": True, "setup": {"property_type": "condominium"}}).json()["case_id"]
    html = form.galley_html(form.build(api.store().tree(cid), edit=True), edit=True)
    cells = [dict(re.findall(r"""data-(\w+)=["']([^"']*)["']""", t))
             for t in re.findall(r"""<span class=["']v pick["'] data-tf=["']8\.0(?:29|31)["'][^>]*>""", html)]
    found = [a for a in cells if a.get("tlab") == "Foundation"]
    assert len(found) == 2
    for a in found:
        value = client.get(f"/api/fields/{a['tf']}/options", params={"dp": a["tdp"]}).json()["options"][0]["value"]
        r = client.patch(f"/api/cases/{cid}/cells/{a['tf']}", json={
            "value": value, "key": a.get("tk", ""), "data_point": a["tdp"], "sel": a["tsel"],
            "label": a["tlab"], "scope": a.get("tscope", "")})
        assert r.status_code == 200, r.text
    M = "{http://www.mismo.org/residential/2009/schemas}"
    comps = [c for c in api.store().tree(cid).getroot().iter(f"{M}STRUCTURE_COMPONENT")
             if (c.findtext(f".//{M}ImprovementComponentType") or "") == "Foundation"]
    assert len(comps) == 1


@pytest.mark.parametrize("sample,kind", [
    ("condo1_appraisal_v1_4", "single_family"),        # its own property data report SERVICE carried whole
    ("2_to_4_unit_appraisal_v1_4", "condominium"),     # into a structure with a separate inspection SERVICE
    ("sf1_appraisal_v1_4", "condominium"),
    ("coop1_appraisal_v1_4", "manufactured"),
])
def test_a_filled_report_changes_kind_and_stays_schema_valid(sample, kind):
    from uad import delivery, setup, shape, templates
    base = templates.load(sample)
    delivery.stamp_software(base.getroot())
    tree, _t, _n, failed = setup.apply(base, sample, kind, 1, {})
    assert shape.property_type(tree.getroot()) == kind
    assert not schema.validate(tree), [e.message[:120] for e in schema.validate(tree)]


def test_a_not_used_comparables_address_is_typed_whole_and_stored_as_parts(client):
    """Additional Properties Analyzed Not Used: the address column offered a
    "Unit" list (its first data point); it is one typed field, stored as the
    parts A-1 defines, and an empty cell is blank -- not "—" to type after."""
    import re
    from app import api
    cid = client.post("/api/cases", json={"blank": True, "setup": {"property_type": "single_family"}}).json()["case_id"]
    html = form.galley_html(form.build(api.store().tree(cid), edit=True), edit=True)
    tag = re.search(r"""<span class=["']v["'] data-tf=["']([\d.]+)["'] data-tk=["']([^"']+)["'] data-tdp=["']["'] data-k=["']text["']""", html)
    assert tag, "no whole-address cell"
    r = client.patch(f"/api/cases/{cid}/cells/{tag.group(1)}",
                     json={"value": "742 Evergreen Ter, Springfield, VA 22150", "key": tag.group(2)})
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "742 Evergreen Ter, Springfield, VA 22150"
    M = "{http://www.mismo.org/residential/2009/schemas}"
    root = api.store().tree(cid).getroot()
    assert "742 Evergreen Ter" in [e.text for e in root.iter(f"{M}AddressLineText")]
    assert "Springfield" in [e.text for e in root.iter(f"{M}CityName")]
    assert not schema.validate(api.store().tree(cid))
