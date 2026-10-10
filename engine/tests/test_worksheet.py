"""Adjustment worksheets (DR §11; replaces SmartAdjust, owner 2026-10-10).

The arithmetic is the owner's own, ported from the WinTOTAL mod
(total-bridge/bridge/worksheet.py and adjust.py): (subject - comparable) x
rate, 0 at or under the threshold, rounded half up to the step. The 18 North
cases below are the ones the mod's adjust.py documents, read out of the
delivered 18 North grid.

Run:  python -m pytest -q engine/tests/test_worksheet.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import schema, templates, worksheet  # noqa: E402
from uad.report import comparables  # noqa: E402

N = worksheet.EIGHTEEN_NORTH


def amount(key, diff, rate=None, threshold=None, rounding=1, building=None):
    kind = worksheet.KINDS[key]
    p = worksheet.Params.of(kind, N, {"rate": rate, "threshold": threshold, "rounding": rounding})
    return worksheet.line_amount(kind, diff, p, building)[0]


def test_the_18_north_derivations():
    assert amount("gla", 325) == 24_375                   # $75 / sq ft
    assert amount("gla", 99) == 0                         # under the 100 sq ft threshold (owner 2026-10-07)
    assert amount("site", -12_197) == -121_970            # $10 / sq ft past 1,000
    assert amount("site", 871) == 0
    assert amount("age", 33) == 8_250                     # $250 / year past 5 years
    assert amount("age", 5) == 0
    assert amount("beds", 1) == 10_000
    assert amount("baths", 0.5) == 5_000                  # a half bath is half the full-bath rate
    assert amount("garage", -1) == -10_000
    assert amount("gla", 0) is None                       # nothing to write


def test_rounding_is_half_up_like_the_worksheet():
    assert amount("gla", -258, rounding=100) == -19_300   # -19,350 -> -193.5 steps -> -193
    assert amount("gla", 258, rounding=100) == 19_400
    assert worksheet._round(-0.5, 1) == 0 and worksheet._round(0.5, 1) == 1


def test_a_2_to_4_unit_report_gates_on_the_building():
    # each unit is 60 sq ft apart, the building 120: past the 100 sq ft threshold
    assert amount("gla", 60, rate=150, threshold=100, building=120) == 9_000
    assert amount("gla", 60, rate=150, threshold=100, building=80) == 0


def test_cells_are_read_as_the_grid_prints_them():
    k = worksheet.KINDS
    assert worksheet._parse(k["site"], "0.25 Acres") == 0.25 * 43_560
    assert worksheet._parse(k["baths"], "2 | 1") == 2.5
    assert worksheet._parse(k["garage"], "Garage | 2 | Attached\nDriveway | 4 | Asphalt") == 2
    assert worksheet._parse(k["garage"], "Carport | 2 | Attached") == 0
    assert worksheet._parse(k["outdoor"], "None") == 0 and worksheet._parse(k["outdoor"], "Deck") == 1
    assert worksheet._parse(k["design"], "Semi-Detached") == 1


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_adjust_all_keeps_every_sample_valid_and_reads_back(key):
    tree = etree.parse(str(templates.get(key).path))
    before = len(schema.validate(tree))
    out = worksheet.adjust_all(tree, worksheet.default_profile(tree))
    assert len(schema.validate(tree)) == before == 0
    # what was written is what the worksheet now reads as "in the grid"
    for a in out["applied"]:
        sheet = worksheet.sheet(tree, a["key"])
        for c in sheet["comparables"]:
            for ln in c["lines"]:
                if ln["amount"] is not None:
                    assert int(float(ln["current"] or 0)) == ln["amount"], (a["key"], c["number"], ln)


def test_per_unit_lines_are_positional_as_the_samples_keep_them():
    tree = etree.parse(str(templates.get("2_to_4_unit_appraisal_v1_4").path))
    worksheet.apply(tree, "beds", {"rate": 15_000}, overrides={"1_2": -1_234})
    root = tree.getroot()
    comp1 = comparables.properties(root, "SalesComparable")[0]
    assert worksheet._amounts(comp1, "LivingUnitBedroomCount")[1] == "-1234"
    assert len(schema.validate(tree)) == 0


def test_the_api_writes_all_comparables_and_never_a_signed_report():
    from fastapi.testclient import TestClient

    from app import api
    from app.access import sign_in
    from app.cases import Store
    from app.main import app
    api.STORE = Store(Path(tempfile.mkdtemp()) / "cases")
    api.RENDERER = None
    api.LAYOUTS = None
    with TestClient(app) as c:
        sign_in(c)
        cid = c.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False,
                                         "name": "ws"}).json()["case_id"]
        kinds = [k["key"] for k in c.get(f"/api/cases/{cid}/worksheets").json()["kinds"]]
        assert {"gla", "site", "age", "beds", "baths", "exposure"} <= set(kinds)
        r = c.post(f"/api/cases/{cid}/worksheets/gla", json={"rate": 80, "threshold": 0, "rounding": 1})
        assert r.status_code == 200 and r.json()["written"] == 3
        now = c.get(f"/api/cases/{cid}/worksheets/gla").json()
        assert [c_["lines"][0]["current"] for c_ in now["comparables"]] == ["-20640", "15840", "14880"]
        assert c.get(f"/api/cases/{cid}/worksheets/nope").status_code == 422
        for state in ("in_review", "signed"):
            api.store().transition(cid, state, "t", force=True)
        assert c.post(f"/api/cases/{cid}/worksheets/gla", json={"rate": 1}).status_code == 409


# ------------------------------------------------- in the grid (T-1085)
# Owner's addendum 2026-10-10 (_work/owner/2026-10-10-desktop-rebuild/
# ADDENDUM_11_WORKSHEET_IN_GRID.md): applied once, a worksheet follows the
# values it rests on; a value typed by hand is the appraiser's and is never
# overwritten; the preview, PDF, XML and ZIP carry what it wrote.
GLA = "LivingUnitStandardFinishedAreaAboveGrade"


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
        yield c, api


def _new(c, template="sf1_appraisal_v1_4"):
    return c.post("/api/cases", json={"template": template, "blank": False, "name": "ws"}).json()["case_id"]


def _gla(api, cid):
    props = comparables.properties(api.store().tree(cid).getroot(), "SalesComparable")
    return [comparables.nth_adjustment_value(p, GLA, 0) for p in props]


def test_an_applied_worksheet_follows_its_values_and_spares_a_typed_one(client):
    c, api = client
    cid = _new(c)
    assert c.post(f"/api/cases/{cid}/worksheets/gla", json={"rate": 80, "threshold": 0, "rounding": 1}).status_code == 200
    assert _gla(api, cid) == ["-20640", "15840", "14880"]
    marks = c.get(f"/api/cases/{cid}/worksheets/marks").json()
    assert marks["rows"][GLA] == {"kind": "gla", "title": "Finished Area Above Grade", "applied": True, "label": "$80/sf"}
    assert "× $80" in marks["cells"][f"{GLA}|1|0"]["basis"]

    # a comparable's area changes: its line is worked out again, and the
    # answer says so (the editor lays the page out again and flashes the cell)
    r = c.patch(f"/api/cases/{cid}/comparables/1/fields/22.07.30", json={"value": "3,100"})
    assert r.status_code == 200, r.text
    assert [(m["comp"], m["new"]) for m in r.json()["recalculated"]] == [(1, "-7840")]
    assert _gla(api, cid)[0] == "-7840"
    assert c.get(f"/api/cases/{cid}/worksheets/marks").json()["recalc"]["cells"] == [
        {"adjust_type": GLA, "comp": 1, "instance": 0}]

    # typed by hand: manual, kept through a re-apply and a value change
    r = c.patch(f"/api/cases/{cid}/comparables/2/fields/22.07.31", json={"value": "5000", "instance": 0})
    assert r.status_code == 200 and r.json()["recalculated"] == []
    assert c.get(f"/api/cases/{cid}/worksheets/marks").json()["cells"][f"{GLA}|2|0"]["manual"] is True
    c.post(f"/api/cases/{cid}/worksheets/gla", json={"rate": 90, "threshold": 0, "rounding": 1})
    assert _gla(api, cid)[1] == "5000"
    c.patch(f"/api/cases/{cid}/comparables/2/fields/22.07.30", json={"value": "2,000"})
    assert _gla(api, cid)[1] == "5000"
    sheet = c.get(f"/api/cases/{cid}/worksheets/gla?rate=90&threshold=0&rounding=1").json()
    assert sheet["comparables"][1]["lines"][0]["manual"] is True

    # "Use worksheet" hands it back
    c.post(f"/api/cases/{cid}/worksheets/gla", json={"rate": 90, "threshold": 0, "rounding": 1,
                                                    "release": [{"comp": 2, "instance": 0}]})
    assert _gla(api, cid)[1] != "5000"
    assert not c.get(f"/api/cases/{cid}/worksheets/marks").json()["cells"][f"{GLA}|2|0"]["manual"]


def test_a_value_typed_on_a_row_no_worksheet_filled_is_marked_manual(client):
    c, api = client
    cid = _new(c)
    c.patch(f"/api/cases/{cid}/comparables/3/fields/22.07.27", json={"value": "-2500", "instance": 0})
    cell = c.get(f"/api/cases/{cid}/worksheets/marks").json()["cells"]["LivingUnitBedroomCount|3|0"]
    assert cell["manual"] is True
    c.post(f"/api/cases/{cid}/worksheets/beds", json={"rate": 7000})
    props = comparables.properties(api.store().tree(cid).getroot(), "SalesComparable")
    assert comparables.nth_adjustment_value(props[2], "LivingUnitBedroomCount", 0) == "-2500"


def test_the_adu_row_reads_its_own_adjustment(client):
    """SF3: the ADU's lines are the second instance of each unit row's type
    (the k-th adjustment of a type is the k-th row drawn); the official PDF
    prints $(1,840), $18,560 and $(6,440) on the ADU's area row."""
    grids = comparables.build(etree.parse(str(templates.get("sf3_appraisal_v1_4").path)), "sales",
                              per_block=99, every_row=True)
    adu = [r for r in grids[0].rows if r.adjust_type == GLA and r.group.startswith("adu")]
    assert adu and [c.adjustment.strip() for c in adu[0].cells] == ["$(1,840)", "$18,560", "$(6,440)"]


def test_the_deliverables_carry_what_the_worksheet_wrote(client, monkeypatch):
    import io
    import zipfile

    from uad.report import browser
    c, api = client
    cid = _new(c)
    c.post(f"/api/cases/{cid}/worksheets/gla", json={"rate": 80, "threshold": 0, "rounding": 1})
    xml = c.get(f"/api/cases/{cid}/mismo.xml").content
    M = f"{{{comparables.bind.MISMO}}}"
    amounts = [a.findtext(f"{M}ComparableAdjustmentAmount")
               for a in etree.fromstring(xml).iter(f"{M}COMPARABLE_ADJUSTMENT")
               if a.findtext(f"{M}ComparableAdjustmentType") == GLA]
    assert amounts == ["-20640", "15840", "14880"]
    if not browser.AVAILABLE:
        pytest.skip(browser.MESSAGE)
    preview = c.get(f"/api/cases/{cid}/preview").text
    for shown in ("$(20,640)", "$15,840", "$14,880"):
        assert shown in preview
    fitz = pytest.importorskip("pymupdf")
    pdf = c.get(f"/api/cases/{cid}/report.pdf")
    assert pdf.status_code == 200
    text = "".join(p.get_text() for p in fitz.open(stream=pdf.content))
    for shown in ("$(20,640)", "$15,840", "$14,880"):
        assert shown in text
    real = api._export_verdict

    def verdict(case_id):
        built, _p, _b, _s = real(case_id)
        return built, [], [], True
    monkeypatch.setattr(api, "_export_verdict", verdict)
    for state in ("in_review", "signed"):
        api.store().transition(cid, state, "t", force=True)
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/cases/{cid}/package.zip").content))
    assert b"<ComparableAdjustmentAmount>-20640</ComparableAdjustmentAmount>" in z.read("mismo.xml")
    zipped = "".join(p.get_text() for p in fitz.open(stream=z.read("appraisal.pdf")))
    assert "$(20,640)" in zipped
