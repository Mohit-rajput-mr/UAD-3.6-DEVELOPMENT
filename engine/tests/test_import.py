"""UAD 3.6 XML import, end to end, on a bundle harder than any sample.

Built from the official SF2 scenario and then stretched the way real files
are: more comparables than the form starts with, far more exhibit photographs
than it has boxes for, pictures arriving every way a producer sends them
(files beside the XML, a URL, a data: URI, base64 embedded in the IMAGE, and
one that is simply missing), values written loosely, an element the schema
does not know, and a very long narrative.
"""
from __future__ import annotations

import base64
import copy
import http.server
import io
import sys
import threading
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, importer, schema, templates  # noqa: E402
from uad.report import comparables, form  # noqa: E402

M = f"{{{bind.MISMO}}}"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _png(n: int) -> bytes:
    # distinct pictures: the same pixel with a different trailing chunk
    return PNG + f"tEXt{n}".encode()


@pytest.fixture(scope="module")
def server():
    """A local web server, so a picture named by URL can really be downloaded."""
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/photo.png"):
                body = _png(999)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _image(images, category: str, location: str, caption: str = "") -> etree._Element:
    img = etree.SubElement(images, f"{M}IMAGE")
    if caption:
        etree.SubElement(img, f"{M}ImageCaptionCommentDescription").text = caption
    etree.SubElement(img, f"{M}ImageCategoryType").text = category
    etree.SubElement(img, f"{M}ImageFileLocationIdentifier").text = location
    return img


def build_bundle(url_base: str) -> tuple[bytes, dict]:
    tpl = templates.get("sf2_appraisal_v1_4")
    tree = etree.parse(str(tpl.path))
    root = tree.getroot()
    files: dict[str, bytes] = {p.name: p.read_bytes() for p in tpl.images}
    # 1. three more comparables than the scenario has (8 in all)
    comps = comparables.properties(root, "SalesComparable")
    for extra in range(3):
        clone = copy.deepcopy(comps[extra])
        for node in clone.iter():
            label = node.get("{http://www.w3.org/1999/xlink}label") if isinstance(node.tag, str) else None
            if label:
                node.set("{http://www.w3.org/1999/xlink}label", f"{label}_X{extra}")
        addr = clone.find(f"{M}ADDRESS/{M}AddressLineText")
        if addr is not None:
            addr.text = f"{900 + extra} Import Test Way"
        comps[-1].addnext(clone)
        comps = comparables.properties(root, "SalesComparable")
    # 2. twenty-five more site exhibits than the form has boxes for
    subject = bind.subject(root)
    images = subject.find(f".//{M}INSPECTIONS/{M}INSPECTION/{M}IMAGES")
    for n in range(25):
        name = f"SiteExtra{n:02d}.png"
        _image(images, "SiteExhibit", f"\\Images\\{name}", f"Site exhibit {n + 1}")
        files[name] = _png(n)
    # 3. pictures arriving other ways
    _image(images, "SiteExhibit", f"{url_base}/photo.png", "By URL")
    _image(images, "SiteExhibit", "data:image/png;base64," + base64.b64encode(_png(501)).decode(), "By data URI")
    emb = _image(images, "SiteExhibit", "\\Images\\Embedded.png", "Embedded")
    etree.SubElement(emb, f"{M}EmbeddedContentXML").text = base64.b64encode(_png(502)).decode()
    _image(images, "SiteExhibit", "\\Images\\DoesNotExist.png", "Missing on purpose")
    # 4. values the way other software writes them
    def set_first(name, value):
        node = next(root.iter(f"{M}{name}"))
        node.text = value
        return node
    set_first("ValuationAssignmentType", "purchase")                    # case
    set_first("AppraisalReportEffectiveDate", "3/4/2026")                # US date
    set_first("SalesContractAmount", "$1,234,567.00")                    # money
    set_first("PropertyDataReportIndicator", "N")                        # Y/N
    unknown = etree.SubElement(subject, f"{M}NotARealMISMOElement")      # not in the subschema
    unknown.text = "kept in the report, not in the document"
    comment = next(root.iter(f"{M}ValuationCommentText"))
    comment.text = ("A long narrative. " * 1200).strip()                # ~21,000 characters
    xml = etree.tostring(tree, xml_declaration=True, encoding="utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Appraisal/appraisal.xml", xml)
        for name, data in files.items():
            zf.writestr(f"Appraisal/Images/{name}", data)
    return buf.getvalue(), {"comment": comment.text}


@pytest.fixture(scope="module")
def imported(tmp_path_factory, server):
    from app.main import app
    store = Store(tmp_path_factory.mktemp("cases"))
    api.STORE = store
    api.RENDERER = None
    bundle, expect = build_bundle(server)
    with TestClient(app) as c:
        c.post("/access", data={"code": "kech"})
        r = c.post("/api/import", files=[("files", ("bundle.zip", bundle, "application/zip"))])
        assert r.status_code == 200, r.text
        out = r.json()
        out["client"] = c
        out["store"] = store
        out["expect"] = expect
        yield out
    store.conn.close()


def test_all_eight_comparables_arrive_and_the_grid_grows(imported):
    api.STORE = imported["store"]            # other tests swap the global store
    st, case = imported["store"], imported["case"]["case_id"]
    root = st.tree(case).getroot()
    assert len(comparables.properties(root, "SalesComparable")) == 8
    grids = comparables.build(st.tree(case), "sales")
    assert len(grids) == 3                            # 3 + 3 + 2 columns
    assert "902 Import Test Way" in form.galley_html(form.build(st.tree(case)))


def test_every_picture_is_placed_however_it_arrived(imported):
    api.STORE = imported["store"]            # other tests swap the global store
    rep = imported["report"]
    sources = {p["source"] for p in rep["pictures_placed"]}
    assert {"bundle", "url", "embedded"} <= sources
    assert any(m["location"].endswith("DoesNotExist.png") for m in rep["pictures_missing"])
    assert len(rep["pictures_missing"]) == 1
    st, case = imported["store"], imported["case"]["case_id"]
    html = form.galley_html(form.build(st.tree(case), folder=st.folder(case), media=api._media_for_render(case)))
    for n in (1, 25):
        assert f"Site exhibit {n}" in html
    for caption in ("By URL", "By data URI", "Embedded"):
        assert caption in html
    # 25 + 3 more site pictures than the template had, each shown, none lost
    assert html.count("<img src='data:image/png") >= 28


def test_the_document_is_valid_and_the_embedded_content_is_gone(imported):
    api.STORE = imported["store"]            # other tests swap the global store
    st, case = imported["store"], imported["case"]["case_id"]
    tree = st.tree(case)
    # valid but for the narrative that is longer than UAD allows, which is kept
    # whole and reported, not cut
    errors = [e.message for e in schema.validate(tree)]
    assert len(errors) == 1 and "maximum length" in errors[0], errors[:3]
    assert any("longer than UAD 3.6 allows" in i[2] for i in imported["report"]["invalid"])
    assert not list(tree.getroot().iter(f"{M}EmbeddedContentXML"))
    assert not list(tree.getroot().iter(f"{M}NotARealMISMOElement"))
    assert any("NotARealMISMOElement" in d[0] for d in imported["report"]["dropped"])


def test_loose_values_are_put_in_uad_form(imported):
    api.STORE = imported["store"]            # other tests swap the global store
    root = imported["store"].tree(imported["case"]["case_id"]).getroot()
    assert next(root.iter(f"{M}ValuationAssignmentType")).text == "Purchase"
    assert next(root.iter(f"{M}AppraisalReportEffectiveDate")).text == "2026-03-04"
    assert next(root.iter(f"{M}SalesContractAmount")).text == "1234567"
    assert next(root.iter(f"{M}PropertyDataReportIndicator")).text == "false"
    assert [i for i in imported["report"]["invalid"] if "longer than" not in i[2]] == []


def test_the_long_narrative_is_kept_whole(imported):
    api.STORE = imported["store"]            # other tests swap the global store
    root = imported["store"].tree(imported["case"]["case_id"]).getroot()
    texts = [n.text for n in root.iter(f"{M}ValuationCommentText")]
    assert imported["expect"]["comment"] in texts


def test_imported_values_stay_editable(imported):
    api.STORE = imported["store"]            # other tests swap the global store
    c, case = imported["client"], imported["case"]["case_id"]
    r = c.patch(f"/api/cases/{case}/fields/2.000", json={"value": "Refinance"})
    assert r.status_code == 200, r.text
    root = imported["store"].tree(case).getroot()
    assert next(root.iter(f"{M}ValuationAssignmentType")).text == "Refinance"
    # an imported comparable cell, through the grid's own route
    r = c.patch(f"/api/cases/{case}/comparables/7/fields/22.08.23",
                json={"kind": "sales", "value": "C2", "data_point": ""})
    assert r.status_code == 200, r.text


def test_the_package_ships_every_placed_picture(imported):
    api.STORE = imported["store"]            # other tests swap the global store
    c, case = imported["client"], imported["case"]["case_id"]
    r = c.get(f"/api/cases/{case}/package/check")
    assert r.status_code == 200
    names = set()
    pkg = api._delivery(case)
    names = {Path(p).name for p in pkg.images}
    placed = {p["name"] for p in imported["report"]["pictures_placed"]}
    assert placed <= names, placed - names


def test_a_failed_import_leaves_nothing(tmp_path):
    from app.main import app
    store = Store(tmp_path / "cases")
    api.STORE = store
    with TestClient(app) as c:
        c.post("/access", data={"code": "kech"})
        before = len(store.list())
        r = c.post("/api/import", files=[("files", ("x.xml", b"<notmismo/>", "text/xml"))])
        assert r.status_code == 422
        r = c.post("/api/import", files=[("files", ("x.txt", b"hello", "text/plain"))])
        assert r.status_code == 422
        assert len(store.list()) == before
    store.conn.close()


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_every_official_scenario_imports_clean(key, tmp_path):
    """Each D-1 scenario, XML plus its pictures, imports with nothing invalid,
    nothing missing and the document valid."""
    tpl = templates.get(key)
    report = importer.Report()
    files = [(tpl.path.name, tpl.path.read_bytes())] + [(p.name, p.read_bytes()) for p in tpl.images]
    name, xml, assets = importer.open_bundle(files)
    tree = importer.parse(xml)
    importer.normalise(tree, report)
    importer.repair_enumerations(tree, report)
    pics = importer.pictures(tree, assets, report, fetch=False)
    assert report.invalid == [] and report.dropped == []
    assert report.pictures_missing == [], report.pictures_missing[:3]
    assert schema.validate(tree) == []
    assert len(pics) == len(list(tree.getroot().iter(f"{M}IMAGE")))


def test_one_portable_xml_restores_the_whole_report(tmp_path):
    """Import the official SF2 delivery zip, export the one portable XML, then
    import only that file: the same report, every picture, the editor state."""
    import glob
    import re
    from lxml import html as lhtml
    from app.main import app
    # the official D-1 zips ship in the folder's root
    _root = Path(__file__).resolve().parents[2]
    zips = glob.glob(str(_root / "Appendix D-1 SF2_Appraisal.zip"))
    if not zips:
        pytest.skip("the D-1 zips are not on this machine")
    store = Store(tmp_path / "cases")
    api.STORE = store
    api.RENDERER = None

    def page(case):
        h = form.galley_html(form.build(store.tree(case), folder=store.folder(case),
                                        media=api._media_for_render(case)))
        doc = lhtml.fromstring(h)
        for bad in doc.xpath("//script|//style"):
            bad.getparent().remove(bad)
        return " ".join(doc.text_content().split()), len(re.findall(r"<img src='data:", h))

    with TestClient(app) as c:
        c.post("/access", data={"code": "kech"})
        first = c.post("/api/import", files=[("files", ("sf2.zip", open(zips[0], "rb").read(), "application/zip"))]).json()
        case1 = first["case"]["case_id"]
        api.set_prefs(case1, {"mapState": {"userView": {"lat": 39.1, "lng": -77.2, "zoom": 15}}})
        r = c.get(f"/api/cases/{case1}/portable.xml")
        assert r.status_code == 200
        portable = r.content
        assert int(r.headers["X-Embedded-Pictures"]) == len(first["report"]["pictures_placed"])
        # the one file validates against the GSE subschema, pictures and all
        assert schema.validate(etree.fromstring(portable).getroottree()) == []
        second = c.post("/api/import", files=[("files", ("one.xml", portable, "application/xml"))]).json()
        case2 = second["case"]["case_id"]
        assert second["report"]["pictures_missing"] == []
        assert len(second["report"]["pictures_placed"]) == len(first["report"]["pictures_placed"])
        text1, shown1 = page(case1)
        text2, shown2 = page(case2)
        assert text1 == text2
        assert shown1 == shown2
        assert api.get_prefs(case2)["mapState"]["userView"]["zoom"] == 15
        # the imported working document carries no embedded payload
        assert b"EmbeddedFile" not in store.xml_path(case2).read_bytes()
    store.conn.close()


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_the_editor_shows_everything_the_preview_prints(key):
    """Preview and editor are the same document drawn twice: every value the
    printed report shows is in the editable report too (layout-only marks --
    the tick-box glyphs, the "Client/" heading split around its picker -- aside)."""
    from collections import Counter
    from lxml import html as lhtml
    tpl = templates.get(key)
    tree = etree.parse(str(tpl.path))

    def words(edit):
        h = form.galley_html(form.build(tree, folder=tpl.path.parent, edit=edit), edit=edit)
        doc = lhtml.fromstring(h)
        # scripts, and the "None" printed in place of a table with no rows
        # (the editor shows the empty table itself, ready for its first row)
        for bad in doc.xpath("//script|//style|//div[contains(concat(' ', @class, ' '), ' none ')]"):
            bad.getparent().remove(bad)
        return Counter(w.strip(",.;:()") for t in doc.itertext() for w in t.split() if w.strip(",.;:()"))
    printed, edited = words(False), words(True)
    missing = {w: n - edited[w] for w, n in printed.items() if n > edited[w]
               and not set(w) <= {"", ""} and not w.startswith("Client/")
               # a Yes/No the report prints as a word is a pair of tick boxes to answer
               and w not in ("Yes", "No")}
    assert not missing, sorted(missing.items())[:20]


def test_an_imported_exhibit_is_named_and_removed_in_place(imported):
    api.STORE = imported["store"]            # other tests swap the global store
    c, st, case = imported["client"], imported["store"], imported["case"]["case_id"]
    from lxml import html as lhtml
    doc = lhtml.fromstring(form.galley_html(form.build(st.tree(case), folder=st.folder(case),
                                                       media=api._media_for_render(case), edit=True), edit=True))
    caps = [e for e in doc.iter() if e.get("data-image") and "capedit" in (e.get("class") or "")]
    assert len(caps) >= 25
    key = caps[0].get("data-image")
    r = c.patch(f"/api/cases/{case}/images", json={"key": key, "caption": "Renamed On Import"})
    assert r.status_code == 200, r.text
    assert "Renamed On Import" in form.galley_html(form.build(st.tree(case)))       # the preview follows
    before = len(list(st.tree(case).getroot().iter(f"{M}IMAGE")))
    r = c.delete(f"/api/cases/{case}/images", params={"key": key})
    assert r.status_code == 200, r.text
    assert len(list(st.tree(case).getroot().iter(f"{M}IMAGE"))) == before - 1
    assert "Renamed On Import" not in form.galley_html(form.build(st.tree(case)))
    assert schema.validate(st.tree(case)) == [] or all("maximum length" in e.message
                                                        for e in schema.validate(st.tree(case)))
