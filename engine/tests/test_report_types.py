"""The Restricted Appraisal Update Report and the Completion Report (T-1036).

Checked against the official D-2 / D-3 samples, the way the URAR is checked
against D-1: H-2 / H-3 find nothing wrong with them, every line the official
PDF prints is printed, nothing is printed that the PDF does not, and a report
derived from the D-1 URAR the sample updates carries what the two share.
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import compliance, report_types as rt, schema  # noqa: E402
from uad.report import form, rules  # noqa: E402

SAMPLES = [(k, p) for k in rt.KINDS for p in rt.samples(k)]
D1 = Path(__file__).resolve().parents[2] / "specs" / "official"
# D-1 URAR -> the D-2 / D-3 sample that updates or completes the same property
# (same address and appraiser file ID)
PAIRS = [("SF1", "update", 0), ("SF2", "completion", 0), ("SF4", "completion", 1)]


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9$]", "", t.lower())


def _render_text(tree) -> tuple[str, list[str]]:
    parts, values = [], []
    for b in form.build(tree):
        if not b.visible:
            continue
        if b.left or b.right:
            for i in b.left + b.right:
                if i.visible:
                    parts.append(i.label + " " + " ".join(i.values))
                    values += i.values
        else:
            text = html.unescape(re.sub("<[^>]+>", " ", b.html or b.title))
            parts.append(text)
            if b.html and "class='sg'" in b.html:
                # the composed signature block: each of its texts on its own
                values += [html.unescape(t) for t in re.findall(r">([^<>]+)<", b.html) if t.strip()]
            else:
                values.append(text)
    return html.unescape(" ".join(parts)), values


def _pdf_text(xml: Path) -> str:
    out = subprocess.run(["pdftotext", "-layout", str(xml.with_suffix(".pdf")), "-"],
                         capture_output=True, text=True).stdout
    return out[out.find("Page 1 of"):]


# what the page furniture, the photographs and C-2/C-3's own placeholder
# labels account for; and the one line D-3 CR2 words differently from B-3 /
# C-3 ("this appraisal report" for B-3 09.004's "this report")
FURNITURE = re.compile(r"^(Page \d+ of \d+|Fannie Mae \| Freddie Mac|September 2024|Restricted Appraisal "
                       r"Update Report|Completion Report|.*Version #\d+|Appraiser Reference ID|Client "
                       r"Reference ID|AMC Reference ID|Yes No|Yes|No|.*\(continued\)|This is where .*|"
                       r"\d{1,2}\. .*|[A-Z0-9-]*\d)$")
SAMPLE_WORDING = {"The intended user of this appraisal report is the lender/client.",
                  "The intended user of this report is the lender/client."}


@pytest.mark.parametrize("kind,path", SAMPLES, ids=[p.stem for _k, p in SAMPLES])
def test_the_document_says_which_report_it_is(kind, path):
    assert rt.kind_of(etree.parse(str(path))) == kind


@pytest.mark.parametrize("kind,path", SAMPLES, ids=[p.stem for _k, p in SAMPLES])
def test_h2_h3_find_nothing_wrong_with_the_official_samples(kind, path):
    found = [f for f in rt.evaluate(etree.parse(str(path))) if f.status == compliance.FINDING]
    assert found == [], [(f.message_id, f.data_point) for f in found]


@pytest.mark.parametrize("kind,path", SAMPLES, ids=[p.stem for _k, p in SAMPLES])
def test_every_line_of_the_official_report_is_printed(kind, path):
    mine, _ = _render_text(etree.parse(str(path)))
    have = _norm(mine)
    missing = []
    for line in _pdf_text(path).splitlines():
        for part in re.split(r"\s{3,}", line.strip()):
            part = part.strip()
            if part and not FURNITURE.match(part) and part not in SAMPLE_WORDING \
                    and _norm(part) not in have:
                missing.append(part)
    assert missing == []


@pytest.mark.parametrize("kind,path", SAMPLES, ids=[p.stem for _k, p in SAMPLES])
def test_nothing_is_printed_that_the_official_report_does_not_print(kind, path):
    pdf = _norm(_pdf_text(path))
    _, values = _render_text(etree.parse(str(path)))
    extra = []
    for v in values:
        v = " ".join(v.split())
        # a wrapped address or table and C-2's [Role] labels print differently
        if v.startswith(("[Role]", "[Contact Name]", "Feature ", "specifications?")) or "\n" in v \
                or "This is where" in v:           # an exhibit with no photo file here
            continue
        if _norm(v) and _norm(v) not in pdf and v not in SAMPLE_WORDING \
                and not any(_norm(w) in pdf for w in v.split("  ") if len(w) > 30):
            extra.append(v[:90])
    # company names and addresses wrap in the PDF's narrow column
    extra = [e for e in extra if not re.search(r"\d{5}$|Company$", e)]
    assert extra == []


def test_a_rule_names_the_data_point_the_guide_broke_or_misspelled():
    assert rules.rejoin("Display when AppraiserPriorServicesPerformedIn dicator = \"false\"") \
        == "Display when AppraiserPriorServicesPerformedIndicator = \"false\""
    assert rules.spelled("PersonalInspectoinPerformedIndicator") == "PersonalInspectionPerformedIndicator"
    assert rules.spelled("AppraiserFileIdentifier") == "AppraiserFileIdentifier"


@pytest.mark.parametrize("urar,kind,n", PAIRS, ids=[f"{u}-{k}" for u, k, _n in PAIRS])
def test_a_report_derived_from_its_urar_carries_what_they_share(urar, kind, n):
    src = etree.parse(str(D1 / f"Appendix D-1 {urar}_Appraisal" / f"{urar}_Appraisal_v1.4.xml"))
    tree, filled = rt.derive(src, kind)
    assert rt.kind_of(tree) == kind
    assert schema.validate(etree.tostring(tree)) == []
    got, ref = form.Ctx(tree.getroot()), form.Ctx(etree.parse(str(rt.samples(kind)[n])).getroot())
    # the subject's address, the original appraiser's file ID and lender are
    # the same in each pair
    for raw in ("01.001", "02.005", "02.006"):
        f = rt.fid(kind, raw)
        assert form.shown(got, f) == form.shown(ref, f), f
        assert f in filled
    # the new assignment's own facts are not carried
    for raw in ("04.017", "05.040") if kind == "update" else ("08.019", "09.027"):
        assert form.shown(got, rt.fid(kind, raw)) == []


def test_a_completion_report_lists_the_original_repairs_as_not_new():
    src = etree.parse(str(D1 / "Appendix D-1 SF2_Appraisal" / "SF2_Appraisal_v1.4.xml"))
    tree, _ = rt.derive(src, "completion")
    ctx = form.Ctx(tree.getroot())
    assert form.shown(ctx, "CR-03.003")[0].startswith("The hot water heater")
    assert form.shown(ctx, "CR-04.003") == []          # nothing new observed yet


def test_a_blank_report_holds_no_sample_content():
    for kind in rt.KINDS:
        tree = rt.blank(kind)
        text = etree.tostring(tree, encoding="unicode")
        for word in ("Falling Tree", "Anywhere Pl", "Something Rd", "Allan Appraiser", "Agatha"):
            assert word not in text


# ------------------------------------------------------------------- the API
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


def _urar(client):
    r = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False,
                                        "name": "123 Falling Tree Ct"})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


@pytest.mark.parametrize("kind,prefix", [("update", "RU"), ("completion", "CR")])
def test_an_appraiser_makes_an_update_or_completion_report_from_a_urar(client, kind, prefix):
    parent = _urar(client)
    r = client.post(f"/api/cases/{parent}/derive", json={"kind": kind})
    assert r.status_code == 200, r.text
    made = r.json()
    cid = made["case_id"]
    assert made["kind"] == kind and made["parent"] == parent
    assert f"{prefix}-01.001" in made["filled"]
    listed = {c["case_id"]: c for c in client.get("/api/cases").json()["cases"]}
    assert listed[cid]["kind"] == kind

    # its own sections and fields, read from the document
    secs = client.get(f"/api/cases/{cid}/fields").json()["sections"]
    assert [s["name"] for s in secs] == list(rt.spec(kind)["sections"].values())[:len(secs)]
    values = {f["field_id"]: f["value"] for s in secs for f in s["fields"]}
    assert values[f"{prefix}-01.001"].startswith("123 Falling Tree Ct")
    assert values[f"{prefix}-02.005"] == "AA12345"

    # a field is written through the same route as a URAR's
    date = f"{prefix}-03.001" if kind == "update" else f"{prefix}-09.027"
    if kind == "update":
        w = client.patch(f"/api/cases/{cid}/fields/{date}", json={"value": "2026-01-12"})
        assert w.status_code == 200, w.text
        secs = client.get(f"/api/cases/{cid}/fields").json()["sections"]
        values = {f["field_id"]: f["value"] for s in secs for f in s["fields"]}
        assert values[date] == "01/12/2026"

    # reviewed against its own rules (H-2 / H-3), not the URAR's
    review = client.get(f"/api/cases/{cid}/review").json()
    codes = {i["code"] for i in review["items"]}
    h = {r["Message ID"] for r in rt.spec(kind)["compliance_rules"]}
    assert codes - {"XSD"} <= h | {""}, sorted(codes - h)[:5]

    # the editor's page is the update / completion report
    g = client.get(f"/api/cases/{cid}/layout/form/galley")
    assert g.status_code == 200
    assert rt.title(kind) in g.text or "Subject Property" in g.text
    assert "Sales Comparison Approach" not in g.text

    # it keeps its own shape: no URAR structure, no reshaping
    assert client.post(f"/api/cases/{cid}/structure", json={"add": "dwelling"}).status_code == 409


def test_only_a_urar_is_derived_from(client):
    parent = _urar(client)
    child = client.post(f"/api/cases/{parent}/derive", json={"kind": "update"}).json()["case_id"]
    assert client.post(f"/api/cases/{child}/derive", json={"kind": "completion"}).status_code == 409
    assert client.post(f"/api/cases/{parent}/derive", json={"kind": "other"}).status_code == 400


def test_a_new_row_in_a_completion_table_belongs_to_that_table(client):
    """T-1038: the empty line under "New Observed Items for Repair" makes a
    DEFECT marked CompletionReportNewDefectIndicator = "true", so it prints
    there and not among the original repairs (and the reverse, B-3 p21)."""
    parent = client.post("/api/cases", json={"template": "sf2_appraisal_v1_4", "blank": False}).json()["case_id"]
    cid = client.post(f"/api/cases/{parent}/derive", json={"kind": "completion"}).json()["case_id"]
    r = client.patch(f"/api/cases/{cid}/cells/CR-04.003", json={"value": "Cracked tile in hall bath.", "new": True})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/cases/{cid}/cells/CR-03.003", json={"value": "Loose stair rail.", "new": True})
    assert r.status_code == 200, r.text
    from app import api
    tree = api.store().tree(cid)
    ctx = form.Ctx(tree.getroot())
    new_items = form.shown(ctx, "CR-04.003")
    repairs = form.shown(ctx, "CR-03.003")
    assert new_items == ["Cracked tile in hall bath."]
    assert "Loose stair rail." in repairs and "Cracked tile in hall bath." not in repairs
    flags = [d.findtext(f"{rt.M}CompletionReportNewDefectIndicator") for d in tree.getroot().iter(f"{rt.M}DEFECT_DETAIL")]
    assert flags.count("true") == 1 and None not in flags
