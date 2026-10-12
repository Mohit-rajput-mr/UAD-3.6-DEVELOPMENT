"""Only what applies to the report counts (T-506; owner, 2026-10-10 section 4).

The owner opened an almost empty 2- to 4-unit report and the Review Master
said 143 fatal, "most on fields that should not exist".  Classified on a new
report made through the API (2-4: 160 fatal, single family: 143), four kinds
of finding were on something the report never shows, and none was a field the
appraiser could fill:

* **A block the new report claimed without the appraiser.**  A new report is
  a D-1 sample with its answers taken out (``templates.clear``).  The sample's
  defect rows, its "rights not included" row and -- on a single-family or
  2-4 report -- its HOA dues and special assessment survived as empty blocks.
  H-1 asks for the details of every defect, excluded right and charge that
  *exists* (UAD1710-1714, UAD1029, UAD1573-1575, UAD1613) and gates their
  existence on the answers that open them (a section's "defects exist?",
  "all rights included?" = No, the property in a project or PUD: UAD1689-1692,
  UAD1030, UAD1572/1577) -- answers a new report does not have, so the editor
  rightly shows no such row, and H-1 asked for one anyway.  ``_drop_bare_repeats``
  was meant to remove them; it named PROPERTY_DEFECT, which never sits in a
  plural wrapper, so it never matched -- and DEFECT alone cannot go, because
  the schema requires DEFECTS inside PROPERTY_DEFECT to hold one.
* **A link to something blanking removed** (UAD1719): the sample's
  relationships to its appraiser's ROLE and to the prior-sale indicators kept
  pointing at labels the new report no longer has.
* **A value the package writes itself** (UAD1211, UAD1270, UAD1750): the
  government-agency and reconsideration indicators and the PDF's file name
  are written by ``delivery`` into the file that ships.  The Review Master
  judged the editor's copy, so they could never be cleared -- a report made
  from blank could never be signed without forcing it.
* **A value left in a section B-1 takes out of the report** (a dues amount on
  a report that is not in a project or PUD): the Review Master now reads the
  report's own section visibility (``review.shown_in``), and such a finding
  is shown for a person to judge, never counted.

A report made before the fix carries the first two in its document: the file
that ships leaves them out (``templates.drop_unclaimed``), and the Review
Master judges that file, so it counts exactly what a new report counts.
Everything else is a field the report shows and asks for, and still counts.
The twelve D-1 samples keep exactly the findings they had.
"""
from __future__ import annotations

import re
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, compliance, delivery, review, schema, templates  # noqa: E402
from uad.report import form  # noqa: E402

M = f"{{{bind.MISMO}}}"
XL = "{http://www.w3.org/1999/xlink}"
SAMPLES = [t.key for t in templates.catalogue()]

#: what H-1 asks about an HOA charge (Project Information)
CHARGES = {"UAD1573", "UAD1574", "UAD1575", "UAD1613"}
#: what H-1 asked about blocks and links a new report never shows
UNSHOWN = {"UAD1710", "UAD1711", "UAD1712", "UAD1714", "UAD1715", "UAD1029",
           "UAD1718", "UAD1719"} | CHARGES


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


NEW = {
    "two_to_four_unit": {"property_type": "two_to_four_unit", "units": 2,
                         "approaches": {"rent": True, "income": True}},
    "single_family": {"property_type": "single_family"},
}


def _new(client, kind):
    from app import api
    r = client.post("/api/cases", json={"blank": True, "setup": NEW[kind]})
    assert r.status_code == 200, r.text
    cid = r.json()["case_id"]
    return cid, api.store().tree(cid), client.get(f"/api/cases/{cid}/review").json()


def _counted(items) -> set[str]:
    return {i["code"] for i in items if i["source"] == "compliance" and i["severity"] in ("Fatal", "Warning")}


def _off_sections(root, item) -> list[str]:
    """The sections H-1 places a finding in, when B-1 leaves every one of
    them out of this report -- read here straight from ``form``."""
    ctx = form.Ctx(root)
    names = [s.strip() for s in (item["section"] or "").split(";")
             if s.strip() and s.strip() != "Does Not Display"]
    return names if names and all(form.section_shown(ctx, s) is False for s in names) else []


def _dangling(root) -> list[str]:
    labels = {e.get(f"{XL}label") for e in root.iter() if isinstance(e.tag, str) and e.get(f"{XL}label")}
    return [f"{r.get(f'{XL}from')} -> {r.get(f'{XL}to')}" for r in root.iter(f"{M}RELATIONSHIP")
            if r.get(f"{XL}from") not in labels or r.get(f"{XL}to") not in labels]


def _made_before(monkeypatch, key):
    """The blank a new report started from before T-506: the sample's empty
    defect rows, excluded rights, HOA charges and dead links all kept."""
    with monkeypatch.context() as m:
        m.setattr(templates, "BARE_BLOCKS", ("COMPARABLE_ADJUSTMENT", "PROPERTY_DEFECT",
                                             "VALUATION_REPORT_ADDITIONAL_CERTIFICATION",
                                             "AMENITY", "SALES_HISTORY"))
        m.setattr(templates, "_drop_unshown_repeats", lambda root: 0)
        m.setattr(templates, "_drop_dangling", lambda root: 0)
        return templates.load(key, blank=True)


# ------------------------------------------------------------------ the owner's case
@pytest.mark.parametrize("kind", list(NEW))
def test_a_new_report_counts_only_what_it_shows(client, kind):
    cid, tree, rv = _new(client, kind)
    root = tree.getroot()
    counted = [i for i in rv["items"] if i["source"] == "compliance" and i["severity"] in ("Fatal", "Warning")]
    wrong = {i["code"]: _off_sections(root, i) for i in counted if _off_sections(root, i)}
    assert not wrong, wrong
    # nothing the report claims without the appraiser: no defect row, no
    # excluded right, no HOA charge on a property not in a project or PUD,
    # no relationship to nothing
    codes = {i["code"] for i in counted}
    assert not codes & UNSHOWN, codes & UNSHOWN
    assert not _dangling(root)
    assert not root.findall(f".//{M}DEFECT") and not root.findall(f".//{M}REAL_PROPERTY_INTEREST")
    # the fields the report does show still count
    must = {"UAD1001", "UAD1373", "UAD1683", "UAD1687", "UAD1688"}
    if kind == "two_to_four_unit":
        must |= {"UAD1170", "UAD1497", "UAD1242", "UAD1243"}
    assert must <= codes, must - codes
    assert rv["counts"]["fatal"] == sum(1 for i in rv["items"] if i["severity"] == "Fatal")


@pytest.mark.parametrize("kind", list(NEW))
def test_the_review_judges_the_file_that_ships(client, kind, tmp_path):
    """A finding the package resolves on its own (the PDF's file name, the
    indicators A-1 defines from the report) is nothing for the appraiser to
    do; one it cannot resolve is.  The Review Master and the delivered XML
    agree, so nothing that would reach a checker is left out of the count."""
    cid, tree, rv = _new(client, kind)
    built = delivery.build(tree, [], tmp_path)
    shipped = {f.message_id for f in compliance.evaluate(built.tree) if f.status == compliance.FINDING}
    counted = _counted(rv["items"])
    assert counted == shipped, (sorted(counted - shipped), sorted(shipped - counted))
    assert not {"UAD1211", "UAD1270", "UAD1750"} & counted
    assert not [i for i in rv["items"] if i["detail"].startswith(review.NOT_COUNTED)]


def test_the_income_approach_line_is_typed_into_on_the_page(client):
    """Total Monthly Market Rent x Gross Rent Multiplier = Indicated Value
    (24.022-24.024, UAD1242/UAD1243 Fatal on a 2-4 report with the income
    approach) was drawn only once it held a value -- so on a new report the
    two fields H-1 asks for had nowhere to be typed."""
    from app import api
    cid, tree, rv = _new(client, "two_to_four_unit")
    html = form.galley_html(form.build(api.store().tree(cid), edit=True), edit=True)
    for fid in ("24.022", "24.023", "24.024"):
        assert re.search(r"data-fid=['\"]%s['\"]" % re.escape(fid), html), fid
    # the printed report still leaves an empty line out
    printed = [b for b in form.build(api.store().tree(cid)) if "24.023" in (b.fids or [])]
    assert printed and not any(b.visible for b in printed)


def test_a_finding_on_a_section_the_report_leaves_out_is_not_counted(client):
    """A dues amount written on a single-family report that is in no project
    or PUD: B-1 shows no Project Information, so what H-1 asks about the
    charge (UAD1575, its utilities) is shown, not counted -- and counts again
    the moment the report says it is in a PUD and the section is back."""
    from app import api
    cid, _tree, _rv = _new(client, "single_family")
    assert client.patch(f"/api/cases/{cid}/fields/18.011", json={"value": "125"}).status_code == 200
    rv = client.get(f"/api/cases/{cid}/review").json()
    # the dues are not in the file that ships (T-1205, delivery.hidden_values),
    # so H-1 finds nothing there to count; at most the rule is listed for review
    aside = [i for i in rv["items"] if i["code"] == "UAD1575"]
    assert all(i["severity"] == "Review" for i in aside), aside
    assert "UAD1575" not in _counted(rv["items"])
    # the fields API marks a field exactly as the Review Master counts it
    fields = client.get(f"/api/cases/{cid}/fields", params={"section": 18}).json()["sections"]
    marked = {f["message_id"] for s in fields for row in s["fields"] for f in row["findings"]}
    assert "UAD1575" not in marked
    # in a PUD the section shows, and the same finding counts
    assert client.patch(f"/api/cases/{cid}/fields/3.010", json={"value": "true"}).status_code == 200
    assert form.section_shown(form.Ctx(api.store().tree(cid).getroot()), "Project Information")
    rv = client.get(f"/api/cases/{cid}/review").json()
    assert "UAD1575" in _counted(rv["items"])


def test_a_condominium_still_asks_for_its_dues(client):
    """The HOA charges a single-family report never shows are the ones a
    condominium asks for: they stay, and are still asked for."""
    from app import api
    r = client.post("/api/cases", json={"blank": True, "setup": {"property_type": "condominium"}})
    cid = r.json()["case_id"]
    root = api.store().tree(cid).getroot()
    charges = [c.findtext(f".//{M}AssociationChargeType") for c in bind.subject(root).iter(f"{M}ASSOCIATION_CHARGE")]
    assert "AssociationDues" in charges
    assert "UAD1573" in _counted(client.get(f"/api/cases/{cid}/review").json()["items"])
    # and a single-family report that becomes a PUD gets them back on writing
    cid, _tree, _rv = _new(client, "single_family")
    assert not list(bind.subject(api.store().tree(cid).getroot()).iter(f"{M}ASSOCIATION_CHARGE"))
    assert client.patch(f"/api/cases/{cid}/fields/3.010", json={"value": "true"}).status_code == 200
    assert client.patch(f"/api/cases/{cid}/fields/18.011", json={"value": "125"}).status_code == 200
    root = api.store().tree(cid).getroot()
    dues = [c for c in bind.subject(root).iter(f"{M}ASSOCIATION_CHARGE")
            if c.findtext(f".//{M}AssociationChargeType") == "AssociationDues"]
    assert dues and dues[0].findtext(f".//{M}AssociationChargeAmount") == "125"
    assert not schema.validate(api.store().tree(cid))


# -------------------------------------------------------- every new report's source
@pytest.mark.parametrize("key", SAMPLES)
def test_a_blank_claims_no_block_its_report_does_not_show(key):
    """Every new report starts from one of the twelve D-1 structures."""
    tree = templates.load(key, blank=True)
    root = tree.getroot()
    rep = review.build(tree)
    codes = {i.code for i in rep.fatal + rep.warnings if i.source == review.COMPLIANCE}
    # a condominium's or co-op's dues are asked for: its Project Information shows
    asked = CHARGES if form.section_shown(form.Ctx(root), "Project Information") else set()
    assert not codes & (UNSHOWN - asked), codes & (UNSHOWN - asked)
    wrong = {i.code: _off_sections(root, i.to_json()) for i in rep.fatal + rep.warnings
             if i.source == review.COMPLIANCE and _off_sections(root, i.to_json())}
    assert not wrong, wrong
    assert not _dangling(root), _dangling(root)[:5]
    # and it is no worse a document for it, nor the file that ships
    assert len(schema.validate(tree)) <= 1
    assert not schema.validate(delivery.as_delivered(tree))


@pytest.mark.parametrize("key", SAMPLES)
def test_a_report_made_before_counts_what_a_new_one_counts(key, monkeypatch):
    """The owner's own report was made before the fix: the sample's empty
    defect rows, excluded rights, HOA charges and dead links are in its
    document.  The file that ships leaves them out, so the Review Master
    counts for it exactly what it counts for a report made today -- and the
    file is no worse against the schema for it."""
    old = _made_before(monkeypatch, key)
    assert _dangling(old.getroot())                    # it does carry them
    new = templates.load(key, blank=True)

    def counted(tree):
        rep = review.build(tree)
        return sorted(i.code for i in rep.fatal + rep.warnings if i.source == review.COMPLIANCE)
    assert counted(old) == counted(new)
    shipped = delivery.as_delivered(old)
    assert not _dangling(shipped.getroot())
    assert len(schema.validate(shipped)) <= len(schema.validate(old))


@pytest.mark.parametrize("key", SAMPLES)
def test_a_d1_sample_keeps_exactly_its_findings(key):
    """The official samples are complete reports: judging the file that ships
    adds and removes nothing for them, and none of the checks above faults one
    (a check that faults a published sample is a broken check)."""
    tpl = templates.get(key)
    tree = etree.parse(str(tpl.path))
    rep = review.build(tree)
    direct = sorted(f.message_id for f in compliance.evaluate(tree)
                    if f.status in (compliance.FINDING, compliance.REVIEW))
    assert sorted(i.code for i in rep.items if i.source == review.COMPLIANCE) == direct
    assert rep.counts["fatal"] == rep.counts["warning"] == rep.counts["schema"] == 0
    assert not _dangling(tree.getroot())
    # what the delivered file leaves out, a published sample does not have
    assert templates.drop_unclaimed(deepcopy(tree.getroot())) == 0


@pytest.mark.parametrize("key", SAMPLES)
def test_no_rule_a_d1_sample_answers_sits_on_a_section_it_leaves_out(key):
    """Validate the validator: every presence rule a published sample meets
    -- its condition holds and the value is there -- is on a section B-1
    shows for that sample.  Were one on a section left out, ``shown_in``
    would set aside a finding that applies."""
    tree = etree.parse(str(templates.get(key).path))
    shown = review.shown_in(tree)
    presence = {r.message_id for r in compliance.rules()
                if r.executable and r.kind == compliance.PRESENCE}
    met = [f for f in compliance.evaluate(tree, include_ok=True)
           if f.status == compliance.OK and f.message_id in presence]
    assert len(met) > 100
    assert not [f.message_id for f in met if not shown(f)]
