"""The end-to-end cases the user listed, driven through the API.

Every check here goes through the REST API rather than the internals, because
the API is what the editor uses: if a route works here, the button wired to it
works too, and a task can be closed with something better than "it renders".

The cases: create and load, edit a field and read it back, add / remove /
reorder comparables, keep each comparable's photo with the comparable it
belongs to, the map's read and write, the review, the sign-off gate, and the
package.
"""
import io
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402

TEMPLATE = "sf1_appraisal_v1_4"


def png() -> bytes:
    """The smallest thing a browser will accept as an image."""
    import base64
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        b"z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The whole application, on a store of its own."""
    from app.main import app

    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        yield c
    store.conn.close()


@pytest.fixture
def case(client):
    r = client.post("/api/cases", json={"template": TEMPLATE, "blank": False,
                                        "name": "Workflow case"})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


def upload(client, case_id, *, comparable=0, section=22, caption="photo"):
    return client.post(
        f"/api/cases/{case_id}/media",
        params={"category": "comparable", "comparable": comparable,
                "section": section, "caption": caption},
        files={"file": ("photo.png", io.BytesIO(png()), "image/png")})


def comp_photos(client, case_id):
    """Which comparable each photo says it belongs to, by caption."""
    media = client.get(f"/api/cases/{case_id}/media").json()["media"]
    return {m["caption"]: m["comparable"]
            for m in media if m["category"] == "comparable"}


def addresses(client, case_id):
    grid = client.get(f"/api/cases/{case_id}/comparables").json()
    return [c["address"] for c in grid["comparables"]]


# ------------------------------------------------------------ create and load
def test_templates_are_offered_by_property_type(client):
    body = client.get("/api/templates").json()
    assert body["templates"], "no templates to start a report from"
    assert body["property_types"]


def test_a_new_case_loads_its_sections_and_fields(client, case):
    body = client.get(f"/api/cases/{case}/fields").json()
    assert body["sections"], "the form has no sections"
    assert any(s["fields"] for s in body["sections"])


def test_a_case_survives_being_reopened(client, case):
    before = client.get(f"/api/cases/{case}").json()
    after = client.get(f"/api/cases/{case}").json()
    assert before["case_id"] == after["case_id"] == case


# --------------------------------------------------------------- field edits
def test_an_edit_is_persisted_and_read_back(client, case):
    # 26.007 is where the opinion of market value is entered; the Summary
    # redisplays it (1.001) and refuses edits of its own.
    r = client.patch(f"/api/cases/{case}/fields/26.007", json={"value": "492000"})
    assert r.status_code == 200, r.text
    fields = {f["field_id"]: f
              for s in client.get(f"/api/cases/{case}/fields",
                                  params={"section": 1}).json()["sections"]
              for f in s["fields"]}
    assert fields["1.001"]["edit_value"] == "492000"


def test_the_summary_cannot_be_edited_directly(client, case):
    """B-1 chapter 01: every Summary value is a redisplay of its source."""
    r = client.patch(f"/api/cases/{case}/fields/1.001", json={"value": "492000"})
    assert r.status_code == 422
    assert "Summary" in r.json()["detail"]


def test_an_edit_that_cannot_be_read_back_is_refused(client, case):
    before = client.get(f"/api/cases/{case}/mismo.xml").content
    r = client.patch(f"/api/cases/{case}/fields/1.033",
                     json={"value": "Test defect"})
    assert r.status_code == 422
    assert client.get(f"/api/cases/{case}/mismo.xml").content == before


# --------------------------------------------------------------- comparables
def test_a_comparable_can_be_added_and_removed(client, case):
    start = len(addresses(client, case))
    assert client.post(f"/api/cases/{case}/comparables",
                       json={"kind": "sales"}).status_code == 200
    assert len(addresses(client, case)) == start + 1
    assert client.delete(f"/api/cases/{case}/comparables/{start + 1}",
                         params={"kind": "sales"}).status_code == 200
    assert len(addresses(client, case)) == start


def test_reordering_moves_the_comparable_not_just_the_number(client, case):
    before = addresses(client, case)
    if len(before) < 2:
        pytest.skip("this template has one comparable")
    order = [2, 1] + list(range(3, len(before) + 1))
    r = client.post(f"/api/cases/{case}/comparables/order",
                    json={"kind": "sales", "order": order})
    assert r.status_code == 200, r.text
    after = addresses(client, case)
    assert after[0] == before[1] and after[1] == before[0], (
        "the addresses did not follow the reorder")


def test_a_photo_stays_with_its_comparable_when_the_order_changes(client, case):
    """A comparable is identified by its number, so moving one must move its
    photo; otherwise comparable #1 prints the photo of a different property."""
    if len(addresses(client, case)) < 2:
        pytest.skip("this template has one comparable")
    assert upload(client, case, comparable=1, caption="first").status_code == 200
    assert upload(client, case, comparable=2, caption="second").status_code == 200

    n = len(addresses(client, case))
    client.post(f"/api/cases/{case}/comparables/order",
                json={"kind": "sales", "order": [2, 1] + list(range(3, n + 1))})

    moved = comp_photos(client, case)
    assert moved["first"] == 2, "the photo of comparable 1 did not follow it to 2"
    assert moved["second"] == 1, "the photo of comparable 2 did not follow it to 1"


def test_removing_a_comparable_takes_its_photo_and_closes_the_gap(client, case):
    if len(addresses(client, case)) < 2:
        pytest.skip("this template has one comparable")
    upload(client, case, comparable=1, caption="doomed")
    upload(client, case, comparable=2, caption="survivor")

    # the sales grid keeps at least three (B10): make room for the removal
    client.post(f"/api/cases/{case}/comparables", json={"kind": "sales"})
    r = client.delete(f"/api/cases/{case}/comparables/1", params={"kind": "sales"})
    assert r.status_code == 200, r.text
    left = comp_photos(client, case)
    assert "doomed" not in left, "the removed comparable's photo was orphaned"
    assert left["survivor"] == 1, "the surviving photo did not move up"


def test_a_comparable_is_identified_by_something_other_than_its_position(client, case):
    """The number is where a comparable sits; the identity is the property's
    own xlink:label, and a photograph is filed against that."""
    upload(client, case, comparable=1, caption="first")
    media = client.get(f"/api/cases/{case}/media").json()["media"]
    keyed = [m for m in media if m["caption"] == "first"]
    assert keyed and keyed[0]["comp_key"], "the photo records no durable identity"

    n = len(addresses(client, case))
    if n >= 2:
        client.post(f"/api/cases/{case}/comparables/order",
                    json={"kind": "sales", "order": [2, 1] + list(range(3, n + 1))})
        after = client.get(f"/api/cases/{case}/media").json()["media"]
        moved = [m for m in after if m["caption"] == "first"][0]
        assert moved["comp_key"] == keyed[0]["comp_key"], "the identity changed"
        assert moved["comparable"] == 2, "the number did not follow the order"


def test_a_newly_added_comparable_gets_a_durable_identity(client, case):
    start = len(addresses(client, case))
    client.post(f"/api/cases/{case}/comparables", json={"kind": "sales"})
    upload(client, case, comparable=start + 1, caption="fresh")
    media = client.get(f"/api/cases/{case}/media").json()["media"]
    fresh = [m for m in media if m["caption"] == "fresh"]
    assert fresh and fresh[0]["comp_key"], (
        "a comparable added in the editor has no identifier of its own")


# --------------------------------------------------------------- the grid
def grid(client, case_id, kind="sales"):
    return client.get(f"/api/cases/{case_id}/comparables",
                      params={"kind": kind}).json()


def test_a_comparable_cell_is_written_to_that_comparable(client, case):
    """The whole point of the grid: a value typed under comparable 2 belongs
    to comparable 2 and to nobody else."""
    before = addresses(client, case)
    if len(before) < 2:
        pytest.skip("this template has one comparable")
    subject_before = grid(client, case)["rows"]
    subject_row = [r for r in subject_before if r["label"] == "Property Address"][0]
    kept = subject_row["subject"]

    r = client.patch(f"/api/cases/{case}/comparables/2/fields/22.01.17",
                     json={"value": "500 Written Way", "kind": "sales",
                           "data_point": "AddressLineText"})
    assert r.status_code == 200, r.text

    after = grid(client, case)
    row = [x for x in after["rows"] if x["label"] == "Property Address"][0]
    assert "500 Written Way" in row["cells"][1]["value"]
    assert "500 Written Way" not in row["cells"][0]["value"]
    assert row["subject"] == kept, "writing a comparable changed the subject"


def test_the_subject_column_writes_to_the_subject(client, case):
    r = client.patch(f"/api/cases/{case}/comparables/0/fields/22.01.01",
                     json={"value": "9 Subject Row", "kind": "sales",
                           "data_point": "AddressLineText"})
    assert r.status_code == 200, r.text
    row = [x for x in grid(client, case)["rows"]
           if x["label"] == "Property Address"][0]
    assert "9 Subject Row" in row["subject"]


def test_a_comparable_added_in_the_editor_can_be_filled_in(client, case):
    """Adding a comparable is pointless if its address cannot be typed."""
    start = len(addresses(client, case))
    client.post(f"/api/cases/{case}/comparables", json={"kind": "sales"})
    r = client.patch(
        f"/api/cases/{case}/comparables/{start + 1}/fields/22.01.17",
        json={"value": "77 Brand New Way", "kind": "sales",
              "data_point": "AddressLineText"})
    assert r.status_code == 200, r.text
    assert "77 Brand New Way" in addresses(client, case)[start]


def test_an_adjustment_is_written_against_its_own_type(client, case):
    row = [r for r in grid(client, case)["rows"]
           if r.get("adjustable") and r.get("adjust_type")][0]
    r = client.patch(f"/api/cases/{case}/comparables/1/fields/adjustment",
                     json={"value": "-3500", "kind": "sales",
                           "adjust_type": row["adjust_type"]})
    assert r.status_code == 200, r.text
    again = [x for x in grid(client, case)["rows"]
             if x["label"] == row["label"]][0]
    assert again["cells"][0]["adjust_raw"] == "-3500"


@pytest.mark.parametrize("field_id", ["4.044", "4.051", "4.055", "4.059", "4.063"])
def test_a_site_feature_table_detail_column_is_reachable(client, case, field_id):
    """Site's 'Non-Residential Property Use / Property Restriction / Easement
    / Encroachment / Site Characteristic' table packs the fixed row's own
    field and its 'Detail' sub-type into one printed cell; C-1's raw table
    data leaves the Detail column with no id of its own.  The redirect logic
    that finds it a home dropped everything after the row's first id, so
    Easement's own EasementType detail (4.055) and its siblings had no
    control at all -- confirmed by hand for each of them."""
    edit_html = client.get(f"/api/cases/{case}/form").text
    assert field_id in edit_html, f"{field_id}'s Detail column has no control"


def test_a_bracketed_placeholder_row_is_reachable_in_edit_mode_but_not_printed(client, case):
    """[Additional Row], [Other Exterior Feature] and [Other Interior Feature]
    are B-1's own row templates, and every one carries a real, writable
    Report Field ID -- but they were hidden from the editor unconditionally,
    the same as the printed report hides an empty optional row.  An appraiser
    could never describe an exterior feature the standard categories do not
    cover, because the row to type it into did not exist on the page.

    The assertion is on the capability, not on which Report Field ID happens
    to back the row: these rows are line items, so which instance's ID the
    grid resolves for them legitimately changes as the row mapping improves.
    Naming one here made the test fail for a change that had in fact made the
    row *more* editable, not less.  Since DR §7 the template is reached by the
    "+" under its group (a blank row of its own read as one more row nobody
    asked for), so the capability is that "+".
    """
    from uad.report import comparables

    grid = comparables.build(api.STORE.tree(case).getroot(), "sales",
                             every_row=True)[0]
    rows = [r for r in grid.rows if r.label.strip() == "[Other Exterior Feature]"]
    assert rows, "B-1's own template row is missing from the grid"
    fids = {f for r in rows for f in (r.comp_fid, r.subject_fid) if f}
    assert fids, "the template row carries no writable Report Field ID"

    edit_html = client.get(f"/api/cases/{case}/form").text
    assert re.search(r"class=[\"']liaddbtn[\"'][^>]*data-lic=[\"']STRUCTURE_COMPONENT", edit_html), (
        "[Other Exterior Feature] has no + to add one in edit mode")

    printed = client.get(f"/api/cases/{case}/preview").text
    assert "[Other Exterior Feature]" not in printed, (
        "an empty template row leaked into the printed report")


@pytest.mark.parametrize("kind", ["sales", "rental", "grm"])
def test_every_grid_binds_to_the_workbook_not_just_the_sales_one(kind):
    """Rental and GRM name their columns differently from Sales and number
    their fields 24.008 rather than 24.00.08; read by the Sales sheet's
    conventions they come back as labels with nothing behind them."""
    from uad.report import comparables

    rows = comparables.rows(kind)
    assert rows, f"the {kind} grid has no rows at all"
    bound = [r for r in rows if r.comp_fid]
    assert len(bound) > 10, f"the {kind} grid bound only {len(bound)} rows"
    assert any(r.data_point for r in rows), (
        f"no row of the {kind} grid names a MISMO data point")
    assert not all(r.heading for r in rows), (
        f"every row of the {kind} grid was taken for a heading")


def test_a_grid_cell_exposes_the_data_points_it_is_made_of(client, case):
    row = [r for r in grid(client, case)["rows"]
           if r["label"] == "Property Address"][0]
    names = [p["data_point"] for p in row["comp_points"]]
    assert "AddressLineText" in names and "CityName" in names


# ---------------------------------------------------------------------- media
def test_an_image_added_to_a_section_comes_back_for_that_section(client, case):
    r = client.post(f"/api/cases/{case}/media",
                    params={"category": "other", "section": 3, "caption": "front"},
                    files={"file": ("f.png", io.BytesIO(png()), "image/png")})
    assert r.status_code == 200, r.text
    media = client.get(f"/api/cases/{case}/media").json()["media"]
    assert any(m["caption"] == "front" and m["section"] == 3 for m in media)


# ------------------------------------------------------- the editor's layout
def test_column_widths_are_kept_with_the_report(client, case):
    """How the grid was arranged belongs to the case, not to one browser."""
    assert client.get(f"/api/cases/{case}/prefs").json() == {}
    client.put(f"/api/cases/{case}/prefs",
               json={"compWidths": {"sales|row": 260}})
    assert client.get(f"/api/cases/{case}/prefs").json() == {
        "compWidths": {"sales|row": 260}}


def test_preferences_merge_rather_than_replace(client, case):
    client.put(f"/api/cases/{case}/prefs", json={"compWidths": {"a": 1}})
    client.put(f"/api/cases/{case}/prefs", json={"openSubs": {"b": True}})
    kept = client.get(f"/api/cases/{case}/prefs").json()
    assert kept["compWidths"] == {"a": 1} and kept["openSubs"] == {"b": True}


# ------------------------------------------------- the report, being filled in
def test_the_form_is_the_report_itself(client, case):
    """Not a page that resembles the URAR: the same renderer, with every
    printed value carrying the Report Field ID behind it."""
    html = client.get(f"/api/cases/{case}/form").text
    assert "contenteditable" in html, "no value on the report can be typed into"
    assert "data-fid=" in html, "the values carry no field identity"
    assert "Uniform Residential Appraisal Report" in html


def test_what_prints_carries_no_editing_apparatus(client, case):
    """The deliverable must not ship with the editor's markup in it."""
    printed = client.get(f"/api/cases/{case}/preview").text
    assert "contenteditable" not in printed
    assert "data-fid=" not in printed
    assert "data-pick=" not in printed


def test_a_blank_field_is_still_on_the_page_to_be_filled_in(client, case):
    """The report prints only what has been answered; an appraiser cannot
    answer a line that is not there, so the form keeps the empty ones."""
    from lxml import etree

    from uad.report import flow

    tree = etree.parse(str(api.store().xml_path(case)))
    printed = flow.build(tree, screen=True, edit=False)
    fillable = flow.build(tree, screen=True, edit=True)
    assert fillable.count("class=\"r ") > printed.count("class=\"r "), (
        "the form shows no more rows than the report prints")


def test_every_section_that_takes_images_offers_somewhere_to_put_one(client, case):
    """A section with no photographs yet still needs a place to drop one."""
    html = client.get(f"/api/cases/{case}/form").text
    assert html.count("class=\"exadd\"") > 5, "hardly any section can take an image"
    assert "data-section=" in html, "a dropped image would not know where it goes"
    printed = client.get(f"/api/cases/{case}/preview").text
    assert "exadd" not in printed, "the deliverable carries the editor's drop zones"


def test_an_enumerated_field_is_a_list_rather_than_a_text_box(client, case):
    """Typing 'Purchse' into Assignment Reason is a compliance finding waiting
    to happen; A-1 enumerates the field, so the form offers the list."""
    from uad.report import form

    assert form.choices_for("1.004"), "Assignment Reason has no choices"
    html = client.get(f"/api/cases/{case}/form").text
    assert "class='v pick'" in html or 'class="v pick"' in html

    # The list is fetched when it is opened, not written into the page: a
    # native <select> draws its popup without the page's transform, which came
    # up three times too big and covered half the report.
    assert "<select" not in html
    options = client.get("/api/fields/1.004/options").json()["options"]
    assert "Purchase" in [o["value"] for o in options]

    printed = client.get(f"/api/cases/{case}/preview").text
    # the page itself, not the scripts that keep it current
    printed = re.sub(r"<script.*?</script>", "", printed, flags=re.S)
    assert "pick" not in printed and "<select" not in printed


def test_everything_unanswered_is_marked_before_a_word_is_typed(client, case):
    """An appraiser should see the whole of what is left from the top of the
    page -- empty values, empty lists and untouched tick boxes alike."""
    html = client.get(f"/api/cases/{case}/form").text
    assert "show-gaps" in html, "nothing marks the unanswered fields"
    assert "untouched" in html, "an unanswered yes/no is not marked"
    assert "show-gaps" not in client.get(f"/api/cases/{case}/preview").text


def test_a_value_typed_on_the_report_reaches_the_document(client, case):
    """The form posts to the same route as everything else, so a value typed
    on the page lands where a value set anywhere else would.  Opinion of
    Market Value is entered in Reconciliation (26.007); the Summary (1.001)
    redisplays it (B-1 chapter 01)."""
    html = client.get(f"/api/cases/{case}/form").text
    assert 'data-fid="26.007"' in html
    r = client.patch(f"/api/cases/{case}/fields/26.007", json={"value": "494750"})
    assert r.status_code == 200, r.text
    assert "494750" in client.get(f"/api/cases/{case}/mismo.xml").text
    assert html.count(">$494,750<") == 0
    assert client.get(f"/api/cases/{case}/form").text.count(">$494,750<") >= 2, (
        "the Summary did not redisplay the Reconciliation value")


def _q(html: str) -> str:
    """The page with one quoting style, however it was serialised."""
    return html.replace("'", '"')


def _section_html(html: str, number: int) -> str:
    """Everything the editor stamped as belonging to one section -- up to the
    next section's piece or the next page, whose running footer (the
    reference IDs, typed where they print: T-919) is page furniture, not the
    section's."""
    import re
    html = _q(html)
    return "".join(m.group(0) for m in re.finditer(
        r'<div data-secn="%d"[^>]*>.*?(?=<div data-secn=|<div class="page"|$)' % number, html, re.S))


def test_the_summary_is_never_editable(client, case):
    """B-1: the Summary "is redisplayed from other sections of the report", so
    the editor shows it but takes no value typed into it -- each value points
    at the field it comes from instead."""
    html = client.get(f"/api/cases/{case}/form").text
    summary = _section_html(html, 1)
    assert summary, "the editor does not mark which pieces are the Summary"
    assert "contenteditable" not in summary
    assert 'class="v pick"' not in summary
    assert "data-pick" not in summary
    assert 'data-derived="26.007"' in summary, "Opinion of Market Value does not point at its source"
    assert 'data-derived="2.000"' in summary, "Assignment Reason does not point at its source"


def test_every_section_on_the_report_can_be_navigated_to(client, case):
    """The rail goes to a section by number, whatever its tab prints."""
    import re
    html = _q(client.get(f"/api/cases/{case}/form").text)
    stamped = {int(n) for n in re.findall(r'data-secn="(\d+)"', html)}
    assert {1, 2, 3, 8, 10, 22, 26, 29} <= stamped, sorted(stamped)
    assert "data-secn" not in client.get(f"/api/cases/{case}/preview").text


def test_photo_slots_take_a_photo_and_it_redisplays(client, case):
    """The front of the dwelling is entered once (8.000.1) and redisplays in
    the Summary (1.000.1) and as the grid's subject thumbnail; a comparable's
    thumbnail takes its own photo and prints in its own column."""
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    html = _q(client.get(f"/api/cases/{case}/form").text)
    assert 'data-category="subject"' in html and 'data-comparable="2"' in html

    for n in range(2):          # a second photo replaces the first
        r = client.post(f"/api/cases/{case}/media?category=subject&section=8",
                        files={"file": (f"front{n}.png", png, "image/png")})
        assert r.status_code == 200, r.text
    r = client.post(f"/api/cases/{case}/media?category=comparable&section=22&comparable=2",
                    files={"file": ("comp2.png", png, "image/png")})
    assert r.status_code == 200, r.text
    media = client.get(f"/api/cases/{case}/media").json()["media"]
    assert sum(1 for m in media if m["category"] == "subject") == 1

    printed = client.get(f"/api/cases/{case}/preview").text
    marker = base64.b64encode(png).decode()
    assert printed.count(marker) >= 4, "the photos did not reach the Summary, Dwelling Exterior and the grid"
    assert "photodrop" not in printed


def test_an_added_exhibit_prints_with_its_caption_and_can_be_removed(client, case):
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    r = client.post(f"/api/cases/{case}/media?category=other&section=4&caption=Drainage%20Swale",
                    files={"file": ("swale.png", png, "image/png")})
    assert r.status_code == 200, r.text
    media_id = r.json()["media_id"]
    form = _q(client.get(f"/api/cases/{case}/form").text)
    assert "Drainage Swale" in form and f'data-media="{media_id}"' in form
    assert "Drainage Swale" in client.get(f"/api/cases/{case}/preview").text
    client.delete(f"/api/cases/{case}/media/{media_id}")
    assert "Drainage Swale" not in client.get(f"/api/cases/{case}/preview").text


# ----------------------------------- properties analyzed but not used
def test_properties_analyzed_not_used_is_a_real_grid_kind(client, case):
    """A-1 gives this its own six field IDs (22.17.01-06); it prints in the
    official Condo1, Coop1, SF1 and SF5 samples as a short list of rejected
    comparables, but had no editor, no API kind and no way to add or remove a
    row -- it simply did not exist as a feature, though a template case
    already carries five of these properties, fully populated."""
    body = grid(client, case, kind="not_used")
    assert body["rows"], "the not-used list has no rows at all"
    labels = [r["label"] for r in body["rows"]]
    assert labels == ["#", "Property Address", "Sale Date", "Status",
                      "Reason Not Used", "Comment"]
    # SF1's template already carries five real rejected comparables
    assert len(body["comparables"]) == 5
    addresses_ = [c["address"] for c in body["comparables"]]
    assert any("Somewhere" in a for a in addresses_)


def test_a_not_used_property_can_be_added_and_removed(client, case):
    before = len(grid(client, case, kind="not_used")["comparables"])
    r = client.post(f"/api/cases/{case}/comparables", json={"kind": "not_used"})
    assert r.status_code == 200, r.text
    assert len(grid(client, case, kind="not_used")["comparables"]) == before + 1
    r = client.delete(f"/api/cases/{case}/comparables/{before + 1}",
                      params={"kind": "not_used"})
    assert r.status_code == 200, r.text
    assert len(grid(client, case, kind="not_used")["comparables"]) == before


def test_a_not_used_property_field_is_editable_and_scoped(client, case):
    """Editing the second rejected property's comment must not touch the
    first."""
    before = grid(client, case, kind="not_used")
    row = [r for r in before["rows"] if r["label"] == "Comment"][0]
    kept = row["cells"][0]["value"]

    r = client.patch(f"/api/cases/{case}/comparables/2/fields/22.17.06",
                     json={"value": "Edited for the test", "kind": "not_used"})
    assert r.status_code == 200, r.text

    after = grid(client, case, kind="not_used")
    row2 = [r for r in after["rows"] if r["label"] == "Comment"][0]
    assert row2["cells"][1]["value"] == "Edited for the test"
    assert row2["cells"][0]["value"] == kept, "editing #2 changed #1"


# --------------------------------------------------------- the market graphs
def test_imported_figures_become_the_market_exhibits(client, case):
    """Five charts drawn from one file, rather than five screenshots pasted in."""
    from uad import market

    r = client.post(f"/api/cases/{case}/market/charts", json=market.example())
    assert r.status_code == 200, r.text
    assert len(r.json()["drawn"]) == len(market.CHARTS)

    # Each chart either repoints the sample's own IMAGE or is added as an
    # exhibit of its own -- either way it reaches the report exactly once.
    xml = client.get(f"/api/cases/{case}/mismo.xml").text
    media = client.get(f"/api/cases/{case}/media").json()["media"]
    captions = {m["caption"] for m in media if m["section"] == 17}
    for key, caption in market.CHARTS.values():
        drawing = f"market-{key.replace('_', '-')}.svg"
        assert drawing in xml or caption in captions, caption

    html = client.get(f"/api/cases/{case}/preview").text
    assert "Price Trend" in html, "the drawn charts never reached the report"


def test_the_drawing_replaces_the_samples_own_picture_of_the_chart(client, case):
    """A case started from a D-1 sample already carries the GSEs' picture of
    each graph; the drawn one must take its place, not print beside it."""
    from uad import market

    body = client.post(f"/api/cases/{case}/market/charts",
                       json=market.example()).json()
    assert any(d["replaced"] for d in body["drawn"]), (
        "no sample image was repointed, so the report shows both")

    xml = client.get(f"/api/cases/{case}/mismo.xml").text
    assert "market-price-trend.svg" in xml
    assert "SF1_PriceTrends" not in xml, "the sample's own chart is still referenced"


def test_importing_twice_redraws_rather_than_stacks(client, case):
    from uad import market

    client.post(f"/api/cases/{case}/market/charts", json=market.example())
    first = client.get(f"/api/cases/{case}/media").json()["media"]
    client.post(f"/api/cases/{case}/market/charts", json=market.example())
    again = client.get(f"/api/cases/{case}/media").json()["media"]
    assert len([m for m in again if m["section"] == 17]) == \
        len([m for m in first if m["section"] == 17])


def test_a_file_that_cannot_be_read_is_refused_with_a_reason(client, case):
    r = client.post(f"/api/cases/{case}/market/charts",
                    content=b"{\"market_charts\": {}}")
    assert r.status_code == 422
    assert "five charts" in r.json()["detail"]


def test_the_prompt_is_served_with_a_worked_example(client):
    body = client.get("/api/market/prompt").json()
    assert "market_charts" in body["prompt"]
    assert len(body["charts"]) == 5
    from uad import market
    assert len(market.parse(body["example"])) == 5


# ------------------------------------------------------------------ the map
def test_the_map_is_served_and_reads_the_case(client, case):
    """The map page loads, and the two calls it seeds itself from answer."""
    assert client.get("/ui/map/index.html").status_code == 200
    assert client.get(f"/api/cases/{case}/comparables",
                      params={"kind": "sales"}).status_code == 200
    assert client.get(f"/api/cases/{case}/fields",
                      params={"section": 3, "only_filled": True}).status_code == 200


def test_a_saved_map_becomes_an_exhibit_in_the_report(client, case):
    r = client.post(f"/api/cases/{case}/media",
                    params={"category": "map", "section": 22,
                            "caption": "Sales Comparison Map"},
                    files={"file": ("map.png", io.BytesIO(png()), "image/png")})
    assert r.status_code == 200, r.text
    html = client.get(f"/api/cases/{case}/preview").text
    assert "Sales Comparison Map" in html, "the saved map never reached the report"


# --------------------------------------------------------------- review master
def test_the_review_reports_every_finding_with_its_provenance(client, case):
    body = client.get(f"/api/cases/{case}/review").json()
    assert "counts" in body and "items" in body
    for item in body["items"][:50]:
        assert item["code"], "a finding with no rule identifier"
        assert item["severity"] in ("Fatal", "Warning", "Review")


def test_the_review_groups_findings_by_section(client, case):
    body = client.get(f"/api/cases/{case}/review").json()
    assert isinstance(body["by_section"], dict)


# ------------------------------------------------------------- the sign-off
def test_an_unsigned_case_cannot_be_exported(client, case):
    r = client.get(f"/api/cases/{case}/package.zip")
    assert r.status_code == 409
    assert r.json()["reasons"], "refused the export without saying why"


def test_a_sample_photograph_blocks_the_signature(client, case):
    """A case opened from a GSE scenario carries their photographs; they are
    not the appraiser's work and must not ship as if they were."""
    body = client.get(f"/api/cases/{case}/integrity").json()
    codes = [f["code"] for f in body["findings"]]
    assert "SAMPLE-ASSET" in codes, "the GSEs' own images were not noticed"
    assert any("sample case" in b for b in
               client.get(f"/api/cases/{case}").json()["blockers"])


def test_a_blank_case_carries_no_borrowed_assets(client):
    fresh = client.post("/api/cases", json={"template": TEMPLATE, "blank": True,
                                            "name": "Clean"}).json()["case_id"]
    body = client.get(f"/api/cases/{fresh}/integrity").json()
    assert "SAMPLE-ASSET" not in [f["code"] for f in body["findings"]]


def test_one_document_feeds_the_form_the_preview_and_the_xml(client, case):
    """There is no second copy of the case: a value set in the form is the
    value the report prints and the value the XML delivers."""
    client.patch(f"/api/cases/{case}/fields/26.007", json={"value": "493500"})

    xml = client.get(f"/api/cases/{case}/mismo.xml").text
    assert "493500" in xml

    fields = {f["field_id"]: f
              for s in client.get(f"/api/cases/{case}/fields",
                                  params={"section": 1}).json()["sections"]
              for f in s["fields"]}
    assert fields["1.001"]["edit_value"] == "493500"

    html = client.get(f"/api/cases/{case}/preview").text
    assert "$493,500" in html, "the report does not print what the form holds"


def test_signing_is_refused_while_anything_blocks_it(client, case):
    blockers = client.get(f"/api/cases/{case}").json()["blockers"]
    if not blockers:
        pytest.skip("this case has nothing blocking a signature")
    client.post(f"/api/cases/{case}/state", json={"state": "in_review"})
    r = client.post(f"/api/cases/{case}/state", json={"state": "signed"})
    assert r.status_code == 409


# ------------------------------------------------ exhibit boxes and more comps
_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def test_add_exhibit_puts_an_empty_box_in_the_form_not_the_report(client, case):
    """"+ Add Exhibit" adds the report's own grey box, with a name typed above
    it; it lives with the editor until a picture goes in, and never prints."""
    r = client.put(f"/api/cases/{case}/prefs",
                   json={"exhibitSlots": [{"id": "xtest1", "section": 4, "caption": "Drainage Swale"}]})
    assert r.status_code == 200
    form = _q(client.get(f"/api/cases/{case}/form").text)
    assert 'data-slot="xtest1"' in form
    assert "This is where the Drainage Swale photo would display." in form
    assert 'data-ph="Exhibit Name"' in form
    assert "Drainage Swale" not in client.get(f"/api/cases/{case}/preview").text


def test_a_photo_can_replace_a_sample_exhibit_box_and_be_renamed(client, case):
    import base64
    png = base64.b64decode(_PNG)
    form = _q(client.get(f"/api/cases/{case}/form").text)
    import re
    location = re.search(r'data-fill="([^"]+)"', form)
    assert location, "the document's own exhibit boxes do not take a photo"
    r = client.post(f"/api/cases/{case}/media?category=other&section=4&caption=Street",
                    files={"file": ("street.png", png, "image/png")})
    media_id = r.json()["media_id"]
    import html as _h
    client.put(f"/api/cases/{case}/prefs", json={"fills": {_h.unescape(location.group(1)): media_id}})
    printed = client.get(f"/api/cases/{case}/preview").text
    assert base64.b64encode(png).decode() in printed, "the replacement photo did not print"
    r = client.patch(f"/api/cases/{case}/media/{media_id}", json={"caption": "Street Scene"})
    assert r.status_code == 200 and r.json()["caption"] == "Street Scene"
    client.delete(f"/api/cases/{case}/media/{media_id}")
    assert not client.get(f"/api/cases/{case}/prefs").json().get("fills")


def test_a_fourth_comparable_opens_its_own_block_as_the_samples_do(client, case):
    """Appendix E p62 and D-1 SF2 p15: past three comparables the label and
    Subject columns repeat on the following page, the block is only as wide as
    its columns, and it carries its own photos."""
    r = client.post(f"/api/cases/{case}/comparables", json={"kind": "sales"})
    assert r.status_code == 200, r.text
    printed = _q(client.get(f"/api/cases/{case}/preview").text)
    assert "Comparable #4" in printed
    assert 'class="grid" style="width:323.00pt"' in printed, "the second block is not narrowed to its columns"
    assert "This is where the Comparable 4 photo would display." in printed
    form = _q(client.get(f"/api/cases/{case}/form").text)
    assert "+ Add Comparable #5" in form and 'data-compmenu="4"' in form
    assert 'data-gc="4"' in form, "comparable #4's cells cannot be edited on the report"
    assert "compadd" not in printed and "data-gc" not in printed


# -------------------------------------------------------- the delivery package
def test_the_package_is_exactly_what_b1_allows(client, case, monkeypatch, tmp_path):
    """B-1 pp 69-73: one XML, one PDF, an Images folder and nothing else; the
    PDF referenced by ObjectURL; every image referenced by an IMAGE; the
    software named by this product, not a sample's."""
    import json as _json
    import zipfile
    from lxml import etree
    from uad import bind, delivery, schema

    (tmp_path / "vendor.json").write_text(_json.dumps(
        {"vendor_name": "Test Vendor", "product_name": "Test Product"}))
    monkeypatch.setattr(delivery, "CONFIG", tmp_path)
    M = f"{{{bind.MISMO}}}"
    st = api.store()

    # the sample's pictures are reported before anything is built
    check = client.get(f"/api/cases/{case}/package/check").json()
    assert any(f["code"] == "SAMPLE-IMAGE" for f in check["faults"]) and not check["ready"]

    # the appraiser's own work: sample pictures out, a front photo in
    tree = st.tree(case)
    for image in list(tree.getroot().iter(f"{M}IMAGE")):
        image.getparent().remove(image)
    for images in list(tree.getroot().iter(f"{M}IMAGES")):
        if not len(images):
            images.getparent().remove(images)
    st.save_tree(case, tree)
    for m in st.media(case):
        st.remove_media(case, m.media_id)
    r = client.post(f"/api/cases/{case}/media?category=subject&section=8",
                    files={"file": ("front.png", io.BytesIO(png()), "image/png")})
    assert r.status_code == 200
    check = client.get(f"/api/cases/{case}/package/check").json()
    # the delivery rules and the schema are satisfied; only the sign-off is
    # left, and "ready" means the export would answer (B12)
    assert not [f for f in check["faults"] if f["severity"] == "Fatal"] and not check["schema"], check
    assert not check["signed_off"] and not check["ready"]
    assert check["images"] == ["front.png"]

    st.transition(case, "in_review", "test")
    st.transition(case, "signed", "test", force=True)
    assert client.get(f"/api/cases/{case}/package/check").json()["ready"]
    r = client.get(f"/api/cases/{case}/package.zip")
    assert r.status_code == 200, r.text
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(zf.namelist()) == ["Images/front.png", "appraisal.pdf", "mismo.xml"]
    xml = zf.read("mismo.xml")
    root = etree.fromstring(xml)
    assert schema.validate(root) == []
    assert root.find(f".//{M}ObjectURL").text == "\\\\appraisal.pdf"
    assert root.findtext(f".//{M}ValuationSoftwareVendorName") == "Test Vendor"
    refs = {i.findtext(f"{M}ImageCategoryType"): i.findtext(f"{M}ImageFileLocationIdentifier")
            for i in root.iter(f"{M}IMAGE")}
    assert refs == {"PropertyPhoto": "\\\\Images\\front.png", "DwellingFront": "\\\\Images\\front.png"}
    assert zf.read("appraisal.pdf").startswith(b"%PDF")


def test_an_area_cell_is_typed_not_picked():
    """Owner 2026-10-08: 'Finished Area Above Grade (Nonstandard)' opened a
    list holding only 'Sq. Ft.'.  The area is a number whose unit sits in
    @AreaUnitOfMeasureType; the unit's one-item enumeration was offered as the
    cell's choices and the number itself had no input."""
    from uad.report import comparables
    for fid in ("22.07.30", "22.07.32", "22.07.36", "22.14.17", "22.05.25"):
        pts = comparables.points_for(fid)
        assert len(pts) == 1 and not pts[0]["options"], fid
        assert comparables.options_for(fid) == [], fid
        assert comparables.typed_in_place(fid) == pts[0]["data_point"]
    # several parts, or a real list, keep the cell editor
    assert comparables.typed_in_place("22.01.17") == ""      # address
    assert comparables.typed_in_place("22.08.19") == ""      # foundation list


def test_an_area_typed_in_the_grid_is_stored_in_square_feet(client, case):
    r = client.patch(f"/api/cases/{case}/comparables/1/fields/22.07.30",
                     json={"value": "1850", "kind": "sales",
                           "data_point": "UnitStandardAboveGradeFinishedAreaMeasure"})
    assert r.status_code == 200, r.text
    assert r.json()["value"].startswith("1,850")
    xml = client.get(f"/api/cases/{case}/mismo.xml").text
    assert re.search(r'<UnitStandardAboveGradeFinishedAreaMeasure AreaUnitOfMeasureType="SquareFeet">1850<', xml)


def test_grid_cells_of_one_typed_value_are_typed_in_place(client, case):
    html = client.get(f"/api/cases/{case}/layout/form/galley").text
    assert "data-gin='UnitStandardAboveGradeFinishedAreaMeasure'" in html
    assert "data-gin='adjustment'" in html
    # the address cell is six parts: it keeps its editor
    assert not re.search(r"data-gf='22\.01\.17'[^>]*data-gin", html)


def test_a_saved_adjustment_comes_back_as_the_report_prints_it(client, case):
    row = [r for r in grid(client, case)["rows"]
           if r.get("adjustable") and r.get("adjust_type")][0]
    r = client.patch(f"/api/cases/{case}/comparables/1/fields/adjustment",
                     json={"value": "-2500", "kind": "sales",
                           "adjust_type": row["adjust_type"]})
    assert r.status_code == 200, r.text
    again = [x for x in grid(client, case)["rows"] if x["label"] == row["label"]][0]
    assert r.json()["value"] == again["cells"][0]["adjustment"]
    assert "2,500" in r.json()["value"]
