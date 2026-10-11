"""Vehicle Storage saves, prints, and is typed where it prints (T-1071, brief §8).

B-1 13 draws a row for each vehicle storage: Storage (CarStorageType), Number
of Parking Spaces (ParkingSpacesCount -- with a project's
ProjectParkingSpaceAssignmentType, or a driveway's "10 or More") and Detail,
where CarStorageAttachmentType, ImprovedSurfaceMaterialType and
CarStorageAreaMeasure "display as stacked".  The grid's Type | Spaces | Detail
prints a line for each.  Every test here goes through the routes the editor
itself calls, and reads the result back from the delivered XML, the printed
report and the grid.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree
from lxml import html as lhtml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, templates  # noqa: E402
from uad.report import form  # noqa: E402

M = f"{{{bind.MISMO}}}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "RENDERER", None)
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        yield c
    store.conn.close()


def _case(client, template="sf1_appraisal_v1_4", blank=True) -> str:
    return client.post("/api/cases", json={"template": template, "blank": blank,
                                           "name": "storage"}).json()["case_id"]


def _editor(case: str):
    tree = api.store().tree(case)
    return lhtml.fromstring(form.galley_html(form.build(tree, folder=api.store().folder(case), edit=True),
                                             edit=True))


def _cells(doc, prefix=("13.001", "13.002", "13.003")):
    return [el for el in doc.iter() if isinstance(el.tag, str) and el.get("data-tf") in prefix]


def _send(client, case, el, value):
    return client.patch(f"/api/cases/{case}/cells/{el.get('data-tf')}",
                        json={"value": value, "key": el.get("data-tk") or "",
                              "data_point": el.get("data-tdp") or "", "new": bool(el.get("data-tnew")),
                              "scope": el.get("data-tscope") or ""})


def _delivered(client, case) -> list[etree._Element]:
    """The subject's CAR_STORAGE blocks in the XML that ships."""
    root = etree.fromstring(client.get(f"/api/cases/{case}/mismo.xml").content)
    holder = bind.subject(root).find(f"{M}CAR_STORAGES")
    return list(holder) if holder is not None else []


def _grid_row(client, case) -> dict:
    rows = client.get(f"/api/cases/{case}/comparables?kind=sales").json()["rows"]
    return next(r for r in rows if r["subject_fid"] == "22.13.01")


def test_a_garage_typed_in_the_section_saves_with_its_spaces_and_size(client):
    """The owner's case: a new report, a garage, its spaces and square feet."""
    case = _case(client)
    # the empty line asks for the storage first: what the other cells take
    # depends on it (a garage's area, a driveway's surface)
    line = [el for el in _cells(_editor(case)) if el.get("data-tnew")]
    assert [el.get("data-tf") for el in line] == ["13.001"]
    r = _send(client, case, line[0], "Garage")
    assert r.status_code == 200, r.text
    assert r.json()["relayout"] is True, "the row must be drawn again with a garage's inputs"

    row = {(el.get("data-tf"), el.get("data-tdp")): el for el in _cells(_editor(case)) if el.get("data-tk")}
    for want in (("13.002", "ParkingSpacesCount"), ("13.003", "CarStorageAttachmentType"),
                 ("13.003", "CarStorageAreaMeasure")):
        assert want in row, f"no input for {want}: {sorted(row)}"
    assert ("13.003", "ImprovedSurfaceMaterialType") not in row       # A-1: a driveway's
    for key, value in ((("13.002", "ParkingSpacesCount"), "2"),
                       (("13.003", "CarStorageAttachmentType"), "Attached"),
                       (("13.003", "CarStorageAreaMeasure"), "480")):
        r = _send(client, case, row[key], value)
        assert r.status_code == 200, (key, r.text)
    assert r.json()["value"] == "480 Sq. Ft."

    # the delivered XML: one storage, the first block, with its unit
    filled = [cs for cs in _delivered(client, case) if "".join(cs.itertext()).strip()]
    assert len(filled) == 1
    detail = filled[0].find(f"{M}CAR_STORAGE_DETAIL")
    assert detail.findtext(f"{M}CarStorageType") == "Garage"
    assert detail.findtext(f"{M}ParkingSpacesCount") == "2"
    assert detail.findtext(f"{M}CarStorageAttachmentType") == "Attached"
    area = detail.find(f"{M}CarStorageAreaMeasure")
    assert (area.text, area.get("AreaUnitOfMeasureType")) == ("480", "SquareFeet")
    root = api.store().tree(case).getroot()
    assert bind.read(root, bind.binding_for("13.000")) == ["Garage"], "13.000 reads the first storage"

    # printed: the report, the editor after a reload, and the grid
    printed = client.get(f"/api/cases/{case}/preview?screen=false").text
    assert "480 Sq. Ft." in printed and "Garage" in printed
    shown = {(el.get("data-tf"), el.get("data-tdp")): el.text_content() for el in _cells(_editor(case))}
    assert shown[("13.003", "CarStorageAreaMeasure")] == "480 Sq. Ft."
    assert shown[("13.002", "ParkingSpacesCount")] == "2"
    assert _grid_row(client, case)["subject"] == "Garage | 2 | Attached 480 Sq. Ft."


def test_the_storage_question_draws_the_row_it_starts(client):
    """13.000 Storage is the first control in the section: a garage picked
    there is a garage row with its inputs, not a value the table never shows."""
    case = _case(client)
    r = client.patch(f"/api/cases/{case}/fields/13.000", json={"value": "Garage"})
    assert r.status_code == 200, r.text
    assert r.json()["relayout"] is True
    row = {(el.get("data-tf"), el.get("data-tdp")) for el in _cells(_editor(case)) if el.get("data-tk")}
    assert ("13.003", "CarStorageAreaMeasure") in row and ("13.002", "ParkingSpacesCount") in row


def test_the_grid_edits_each_storage_line_and_adds_one(client):
    """SF1 has a driveway and a garage: the grid edits the garage's line, not
    the first, and a carport is added as a line of its own."""
    case = _case(client, blank=False)
    lines = _grid_row(client, case)["subject_lines"]
    assert [ln["parts"]["CarStorageType"] for ln in lines] == ["Driveway", "Garage"]
    url = f"/api/cases/{case}/comparables/0/fields/22.13.01"
    r = client.patch(url, json={"kind": "sales", "data_point": "CarStorageAreaMeasure",
                                "value": "480", "line": lines[1]["line"]})
    assert r.status_code == 200, r.text
    r = client.patch(url, json={"kind": "sales", "data_point": "CarStorageType", "value": "Carport", "new": True})
    assert r.status_code == 200, r.text
    added = r.json()["line"]
    assert added and added not in (lines[0]["line"], lines[1]["line"])
    r = client.patch(url, json={"kind": "sales", "data_point": "ParkingSpacesCount", "value": "1", "line": added})
    assert r.status_code == 200, r.text

    kept = [{etree.QName(e).localname: e.text for e in cs.find(f"{M}CAR_STORAGE_DETAIL")}
            for cs in _delivered(client, case)]
    assert kept[0] == {"CarStorageType": "Driveway", "ImprovedSurfaceMaterialType": "Asphalt",
                       "ParkingSpacesCount": "2", "TenOrMoreParkingSpacesIndicator": "false"}
    assert kept[1]["CarStorageType"] == "Garage" and kept[1]["CarStorageAreaMeasure"] == "480"
    assert kept[2] == {"CarStorageType": "Carport", "ParkingSpacesCount": "1"}
    assert _grid_row(client, case)["subject"].split("\n") == [
        "Driveway | 2 | Asphalt", "Garage | 2 | Built-in 480 Sq. Ft.", "Carport | 1"]


FILL = """(() => {
  const groups = {}; let cur = null;
  for (const el of document.querySelector('.gedit').children) {
    if (el.classList.contains('gl')) { cur = el.textContent; groups[cur] = {}; continue; }
    const l = el.querySelector && el.querySelector('label');
    if (cur && l) groups[cur][l.title] = el;
  }
  const set = (g, dp, v) => {
    const w = groups[g][dp], hidden = w.querySelector('input[type=hidden]');
    if (hidden) {
      w.querySelector('.gpick [data-value="' + v + '"]').dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
      return hidden.value;
    }
    w.querySelector('input').value = v; return v;
  };
  return [set('Line 2', 'CarStorageAreaMeasure', '480'), set('Add a line', 'CarStorageType', 'Carport'),
          set('Add a line', 'ParkingSpacesCount', '1')];
})()"""


ADDING = """(() => {
  const out = []; let on = false;
  for (const el of document.querySelector('.gedit').children) {
    if (el.classList.contains('gl')) { on = el.textContent === 'Add a line'; continue; }
    const l = el.querySelector && el.querySelector('label');
    if (on && l && !el.hidden) out.push(l.title);
  }
  return out;
})()"""


def test_the_grid_editor_saves_each_line_into_its_own_storage(client):
    """The grid's own editor, in the page: a group of inputs for each line and
    one to add a line; Save writes each into its own CAR_STORAGE."""
    from uad.report import browser, flow
    if not browser.AVAILABLE:
        pytest.skip(browser.MESSAGE)
    from playwright.sync_api import sync_playwright
    case = _case(client, blank=False)
    page_html = flow.build(api.store().tree(case), folder=api.store().folder(case), screen=True, edit=True)

    def serve(route):
        req = route.request
        if req.url.startswith("http://report.test/form"):
            return route.fulfill(status=200, content_type="text/html", body=page_html)
        if req.url.startswith("http://report.test/api/"):
            # the page's own requests, answered by the routes themselves
            r = client.request(req.method, req.url[len("http://report.test"):], content=req.post_data_buffer,
                               headers={"Content-Type": req.headers.get("content-type", "application/json")})
            return route.fulfill(status=r.status_code, body=r.content,
                                 content_type=r.headers.get("content-type", "application/json"))
        route.fulfill(status=404, body="")

    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            page = b.new_page()
            page.route("**/*", serve)
            page.goto(f"http://report.test/form?case={case}")
            page.locator("td[data-gc='0'][data-gf='22.13.01']").first.click()
            page.locator(".gedit .gl").first.wait_for(timeout=20000)
            assert page.locator(".gedit .gl").all_inner_texts() == ["Line 1", "Line 2", "Add a line"]
            # a new line asks its type first, then only that type's inputs (T-1203)
            assert page.evaluate(ADDING) == ["CarStorageType"]
            assert page.evaluate(FILL) == ["480", "Carport", "1"]
            assert page.evaluate(ADDING) == ["CarStorageType", "CarStorageAreaMeasure",
                                             "CarStorageAttachmentType", "ParkingSpacesCount"]
            page.locator(".gedit .go").click()
            page.wait_for_function("!document.querySelector('.gedit')"
                                   " || document.querySelector('.gedit .err').textContent", timeout=20000)
            assert page.locator(".gedit").count() == 0, page.locator(".gedit .err").inner_text()
            shown = page.locator("td[data-gc='0'][data-gf='22.13.01']").first.inner_text()
        finally:
            b.close()
    assert shown.split("\n") == ["Driveway | 2 | Asphalt", "Garage | 2 | Built-in 480 Sq. Ft.", "Carport | 1"]
    kept = [{etree.QName(e).localname: e.text for e in cs.find(f"{M}CAR_STORAGE_DETAIL")}
            for cs in _delivered(client, case)]
    assert [k["CarStorageType"] for k in kept] == ["Driveway", "Garage", "Carport"]
    assert kept[0]["ImprovedSurfaceMaterialType"] == "Asphalt" and kept[1]["CarStorageAreaMeasure"] == "480"
    assert kept[2] == {"CarStorageType": "Carport", "ParkingSpacesCount": "1"}


def test_a_blank_value_creates_no_storage(client):
    """The grid's Save sends every input, the empty "Other" descriptions too;
    each used to leave a CAR_STORAGE of type Other behind."""
    case = _case(client)

    def storages():
        return etree.tostring(bind.subject(api.store().tree(case).getroot()).find(f"{M}CAR_STORAGES"))
    before = storages()
    url = f"/api/cases/{case}/comparables/0/fields/22.13.01"
    for point in ("CarStorageTypeOtherDescription", "ImprovedSurfaceMaterialTypeOtherDescription"):
        r = client.patch(url, json={"kind": "sales", "data_point": point, "value": ""})
        assert r.status_code == 200, r.text
        r = client.patch(url, json={"kind": "sales", "data_point": point, "value": "", "new": True})
        assert r.status_code == 200, r.text
    assert storages() == before
    assert not any("".join(cs.itertext()).strip() for cs in _delivered(client, case))


@pytest.mark.parametrize("template", [t.key for t in templates.catalogue()])
def test_every_storage_value_in_the_samples_has_its_own_input(client, template):
    """Validate the editor against the twelve D-1 samples: every value a
    vehicle storage row holds is typed where it prints, and writing it back as
    it stands is accepted (an "Other" description is asked for by its list)."""
    case = _case(client, template, blank=False)
    root = api.store().tree(case).getroot()
    holder = bind.subject(root).find(f"{M}CAR_STORAGES")
    storages = [cs for cs in (holder if holder is not None else []) if "".join(cs.itertext()).strip()]
    by_row: dict[str, dict[str, etree._Element]] = {}
    for el in _cells(_editor(case)):
        if el.get("data-tk"):
            by_row.setdefault(el.get("data-tk"), {})[el.get("data-tdp")] = el
    for cs in storages:
        # the row's values (its photos are the section's exhibits)
        held = {etree.QName(e).localname: (e.text or "").strip() for e in cs.find(f"{M}CAR_STORAGE_DETAIL")
                if isinstance(e.tag, str) and (e.text or "").strip()}
        row = by_row.get(bind.stable_path(cs), {})
        missing = [n for n in held if not n.endswith("OtherDescription") and n not in row]
        assert not missing, f"{template}: {held.get('CarStorageType')} has no input for {missing}"
        for name, el in row.items():
            if name in held:
                r = _send(client, case, el, held[name])
                assert r.status_code == 200, f"{template} {name}: {r.text}"
