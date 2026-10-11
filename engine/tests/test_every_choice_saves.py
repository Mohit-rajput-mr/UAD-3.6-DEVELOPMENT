"""Every dropdown and every Yes/No saves and reloads (T-1072, owner brief section 8).

The owner picked a Data Source in Subject Listing (19.001) and nothing was
selected.  The pick was refused: A-1 ties that source to what it sources by
arcrole (DATA_SOURCE_IsDataSourceFor_LISTING_INFORMATION_SUMMARY, D-1 SF5 /
MH2 / Condo1), and ``uad/sources.py`` wrote it so -- but the API read it back
where it sits, as the first DATA_SOURCE in the valuation's list (an empty one
on a new report), and answered "could not be saved to its matching report
field".  17.018 Price Trend Source and 10.009 Area Data Source were refused the
same way.  Once a source was saved, the editor draws the field as a list keyed
by each DATA_SOURCE (form.repeats_as_list), and changing, adding or removing
one looked for the listing inside the DATA_SOURCE and was refused too.

The rest is the check the owner asked for: on a new single-family and a new
2-4 unit report, every dropdown (``.v.pick``), every Yes/No box (``.bx``) and
every Public/Private tick is picked through the route the editor's own script
sends it to (flow.EDIT_JS ``sendNow``: PATCH /fields/{fid}, or /cells/{fid}
with the row's key, scope and fixed-row label), on the blank as the appraiser
opens it, then the report is drawn again and the value must be in the stored
document and shown where it was picked -- in its own copy of a section drawn
per dwelling or unit.  It found, besides the sources:

* a Yes B-1 prints nothing for (Current or Relevant Listings, Known Renewable
  Energy Components, Prior Sales or Transfers) saved, and the editor showed
  the line blank again after every reload;
* every dropdown and box in Building 2's Dwelling Exterior and Unit 2's Unit
  Interior wrote into Building 1 and Unit 1: the controls carried the field ID
  alone (~40 choices on the 2-4 blank);
* a conditioned answer (Townhouse End Unit: IF StructuralDesignType =
  "RowhouseTownhouse") made a second IMPROVEMENT carrying the condition.

Picks are tried a section at a time (one choice from each section per pass, on
a fresh blank; a choice that fails there is tried again alone), because one
full redraw per choice takes three minutes.  A refusal that names the answer to
give first ("Answer ADU (10.011) with Yes first") is followed: that answer is
given in the same copy of the section, and the choice must then save.

Run:  python -m pytest -q engine/tests/test_every_choice_saves.py
"""
from __future__ import annotations

import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree
from lxml import html as lhtml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.access import sign_in  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, edit, schema, templates  # noqa: E402
from uad.report import form  # noqa: E402

M = f"{{{bind.MISMO}}}"
X = "{http://www.w3.org/1999/xlink}"
TICK = "\uF052"                # the ticked box glyph the report font draws
TEMPLATES = ("sf1_appraisal_v1_4", "2_to_4_unit_appraisal_v1_4")

# Choices that still do not save on a new report, each for a reason of its own
# (none is a source tied by arcrole, nor a copy of a section writing into the
# first).  A key is a field, or a field and the choice ("3.011 box false").
# The test fails when one of them starts to save, so the list cannot go stale.
KNOWN = {
    # C-1 asks Condominium / Cooperative / Condop as three Yes/No rows and A-1
    # stores the answer once, as ProjectLegalStructureType: a No on one row of
    # a report with no project type has nothing to store (edit._is_it_this,
    # by design), so the box is empty again after the reload
    "3.011 box false": "No on an 'is it this?' row stores nothing",
    "3.012 box false": "No on an 'is it this?' row stores nothing",
    "3.013 box false": "No on an 'is it this?' row stores nothing",
    # B-1 shows the value only when another answer is given (4.044 / 4.045:
    # PropertyMixedUsageIndicator = "true"); written without it, the page
    # hides it and the save does not say so
    "4.044": "display gate: saved, hidden until Non-Residential Property Use = Yes",
    "4.045": "display gate: saved, hidden until Non-Residential Property Use = Yes",
    # the empty line of a table makes a block from one column alone, a block
    # the table does not draw as a row: the Reconciliation's defect list (26),
    # a utility with no type (4.096 Detail "No").  (13 / 14: the row is made
    # tied to the garage / amenity it is in, api._defect_owner, T-1204)
    "26.058": "defect row made without its component", "26.064": "defect row made without its component",
    "4.096 pick false": "utility row made from its Detail alone",
    # ... and on a 2-4 unit report a Unit Interior defect is made at the
    # subject's PROPERTY_DEFECT with no tie to its unit, so the unit's table
    # (drawn per unit) does not draw it (T-1204)
    "10.058": "unit defect row made without its unit",
    # the empty line of a table whose rows are conditioned on another value
    # (SiteInfluenceType = BodyOfWater; IncomeApproachIndicator = false):
    # refused, without naming the answer it waits for
    "4.034": "row condition: refused, 'could not be saved to this row'",
    "26.003": "row condition: refused, 'could not be saved to this row'",
    # one data point at two placements: the Walls and Ceiling row's condition
    # is written to the flooring placement (ImprovementComponentType = Flooring)
    "10.047": "two placements of one data point: refused",
    # the empty line offers a component type the table already has a fixed
    # row for: a second block of that type is made and the table prints one
    "8.041": "a second block of a fixed row's type",
}


# entries that hold on one report only (the single-family blank answers
# IncomeApproachIndicator, so its exclusion reason row saves there)
KNOWN_ON = {"26.003": ("2_to_4_unit_appraisal_v1_4",),
            "10.058": ("2_to_4_unit_appraisal_v1_4",)}


def _known(name: str, template: str) -> str:
    return next((k for k in KNOWN if (name == k or name.startswith(k + " "))
                 and template in KNOWN_ON.get(k, TEMPLATES)), "")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from app.main import app
    kept = api.STORE, api.RENDERER
    api.STORE = Store(tmp_path_factory.mktemp("cases"))
    api.RENDERER = None
    with TestClient(app) as c:
        sign_in(c)
        yield c
    api.STORE, api.RENDERER = kept


def _case(client, template: str) -> str:
    return client.post("/api/cases", json={"template": template, "blank": True,
                                           "name": "choices"}).json()["case_id"]


def _editor(case: str):
    """The report as the editor loads it after every reload."""
    st = api.store()
    return lhtml.fromstring(form.galley_html(form.build(st.tree(case), folder=st.folder(case), edit=True),
                                             edit=True))


def _send(client, case: str, el, value: str):
    """What flow.EDIT_JS ``sendNow`` sends for this control."""
    body = {"value": value}
    url = f"/api/cases/{case}/fields/{el.get('data-fid')}"
    if el.get("data-ordinal"):
        body["ordinal"] = int(el.get("data-ordinal"))
    if el.get("data-tf") is None and el.get("data-tdp"):
        body["data_point"] = el.get("data-tdp")
    if el.get("data-tf") is None and el.get("data-iscope"):
        body["scope"] = el.get("data-iscope")      # the dwelling or unit this copy is for
    if el.get("data-route"):
        url = f"/api/cases/{case}/{el.get('data-route')}"
    if el.get("data-tf") is not None:
        url = f"/api/cases/{case}/cells/{el.get('data-tf')}"
        body.update(key=el.get("data-tk") or "", data_point=body.get("data_point") or el.get("data-tdp") or "",
                    sel=el.get("data-tsel") or "", label=el.get("data-tlab") or "",
                    new=bool(el.get("data-tnew")), scope=el.get("data-tscope") or "",
                    cat=el.get("data-tcat") or "")
    return client.patch(url, json=body)


def _words(text: str) -> str:
    return " ".join((text or "").split())


@dataclass
class Choice:
    kind: str          # pick, box, tick
    el: etree._Element
    field: str
    section: str
    value: str         # what is sent ("" takes off a box the blank has ticked, as a click does)
    label: str         # what the page's list calls it
    nth: int = 0       # which of the controls alike this is
    printed: str = ""  # what the save answered the report prints

    @property
    def name(self) -> str:
        return f"{self.field} {self.kind} {self.value or 'off'}" + (f" #{self.nth + 1}" if self.nth else "")


def _section(el) -> str:
    return next((a.get("data-section") for a in el.iterancestors() if a.get("data-section") is not None), "")


SAME = ("data-fid", "data-tf", "data-tdp", "data-ordinal", "data-tk", "data-tsel", "data-tlab", "data-tscope")


def _alike(doc, ch: Choice) -> list:
    """The controls on a page that are this one, in page order: the same
    field, data point and row -- one per copy of a section drawn for each
    dwelling or unit (D-1 2-4: Building 1 and Building 2)."""
    if ch.kind == "pick":
        return [x for x in doc.iter("span") if "pick" in (x.get("class") or "").split()
                and all(x.get(a) == ch.el.get(a) for a in SAME)]
    if ch.kind == "box":
        return [b for b in doc.iter("span") if "bx" in (b.get("class") or "").split()
                and (b.get("data-fid"), b.get("data-pick"), b.get("data-ordinal"))
                == (ch.el.get("data-fid"), ch.el.get("data-pick"), ch.el.get("data-ordinal"))]
    return [td for td in doc.iter("td") if "tickcell" in (td.get("class") or "").split()
            and (td.get("data-tf"), td.get("data-tval"), td.get("data-tlab"))
            == (ch.el.get("data-tf"), ch.el.get("data-tval"), ch.el.get("data-tlab"))]


def _choices(client, doc) -> list[Choice]:
    out, options = [], {}
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        cls = (el.get("class") or "").split()
        if "v" in cls and "pick" in cls:
            fid = el.get("data-tf") or el.get("data-fid")
            url = f"/api/fields/{fid}/options" + (f"?dp={el.get('data-tdp')}" if el.get("data-tdp") else "")
            if url not in options:
                options[url] = client.get(url).json()["options"]
            # a Yes/No is tried both ways, a list by its first entry -- never
            # the answer the blank already shows (2.004 Traditional Appraisal)
            usable = [o for o in options[url] if o["value"] and not o.get("other")]
            both = {o["value"] for o in usable} == {"true", "false"}
            usable = [o for o in usable if _words(o["label"]) != _words(el.text_content())]
            for o in (usable if both else usable[:1]) or [{"value": "", "label": ""}]:
                ch = Choice("pick", el, fid, _section(el), o["value"], o["label"])
                ch.nth = [id(x) for x in _alike(doc, ch)].index(id(el))
                out.append(ch)
        elif ("bx" in cls and el.get("data-pick") is not None) or "tickcell" in cls:
            kind = "box" if "bx" in cls else "tick"
            ticked = (el.text_content().strip() == TICK if kind == "box"
                      else any(e.get("class") == "tick" for e in el.iter() if isinstance(e.tag, str)))
            # a click on a box or tick the blank has on takes it off (EDIT_JS)
            ch = Choice(kind, el, el.get("data-fid") if kind == "box" else el.get("data-tf"), _section(el),
                        "" if ticked else (el.get("data-pick") if kind == "box" else el.get("data-tval")), "")
            ch.nth = [id(x) for x in _alike(doc, ch)].index(id(el))
            out.append(ch)
    return out


def _section_text(doc, section: str) -> str:
    return " ".join(_words(b.text_content()) for b in doc.iter()
                    if isinstance(b.tag, str) and b.get("data-section") == section)


def _shown(blank, doc, ch: Choice) -> bool:
    """Is the choice on the page drawn again?"""
    if ch.kind in ("box", "tick"):
        alike = _alike(doc, ch)
        if ch.nth >= len(alike):
            return False
        hit = alike[ch.nth]
        on = (hit.text_content().strip() == TICK if ch.kind == "box"
              else any(e.get("class") == "tick" for e in hit.iter() if isinstance(e.tag, str)))
        return on == bool(ch.value)
    # as the list names it, or as the save said the report prints it (8.008:
    # "No Units Above / Below" picked, "No" printed)
    wants = {w for w in (_words(ch.label), _words(ch.printed)) if w}
    before, after = _alike(blank, ch), _alike(doc, ch)
    if not ch.el.get("data-tnew") and len(after) == len(before):
        # the same controls are drawn again: this one shows it (in its own
        # copy of the section, not the first dwelling's or unit's)
        return any(w in _words(after[ch.nth].text_content()) for w in wants)
    # drawn otherwise now: a list shows it as one of its values; a row the
    # empty line made prints it in its section ("Agricultural" heads its own
    # site influence row)
    same = [x for x in doc.iter() if isinstance(x.tag, str)
            and ch.field in (x.get("data-fid"), x.get("data-tf"))
            and (not ch.el.get("data-tdp") or x.get("data-tdp") == ch.el.get("data-tdp"))]
    if any(w in _words(x.text_content()) for x in same for w in wants):
        return True
    return any(_section_text(doc, ch.section).count(w) > _section_text(blank, ch.section).count(w)
               for w in wants)


def _held(xml: bytes, point: str, value: str) -> int:
    """How many elements of this data point hold this value in the XML."""
    return len(re.findall(rf"<{point}(?:\s[^>]*)?>{re.escape(value)}</{point}>".encode(), xml))


def _stored(xml: bytes, before: bytes, ch: Choice, res: dict) -> bool:
    """The value is in the document that ships, in its own data point: what
    the API says it wrote (2.011 "Other", 3.011 "true" -> Condominium), or for
    a table cell the value sent into the row's data point."""
    if "written" in res:
        point, new, old = res["written"]["data_point"], res["written"]["new"], res["written"]["old"]
    else:
        point = ch.el.get("data-tdp") or edit.choose_data_point(edit._binding_for(ch.field))["mismo"]
        new, old = ch.value, None
    if not new:
        return False
    after = _held(xml, point, new)
    return after > _held(before, point, new) or (after > 0 and old == new)


class Run:
    """One report: its blank, the controls on it, and a way back to the blank."""

    def __init__(self, client, template: str):
        self.client, self.case = client, _case(client, template)
        self.st = api.store()
        self.blank_xml = self.st.xml_path(self.case).read_bytes()
        first = self.st.get(self.case)
        self._shape = (first.template, first.property_type)
        self.blank = _editor(self.case)
        self.choices = _choices(client, self.blank)

    def reset(self) -> None:
        self.st.xml_path(self.case).write_bytes(self.blank_xml)
        # a choice that reshaped the report (3.011 Condominium = Yes) changed
        # the case's own record too: the blank's shape comes back with its XML
        self.st.set_shape(self.case, *self._shape)
        # answers a hidden section kept aside (optional_sections, T-1057) and
        # applied worksheets are the case's too: a reset leaves none behind
        for side in ("hidden.json", "worksheets.json"):
            (self.st.folder(self.case) / side).unlink(missing_ok=True)
        self.st.touch(self.case)

    def xml(self) -> bytes:
        return self.st.xml_path(self.case).read_bytes()

    def pick(self, ch: Choice) -> str:
        """Send one choice on the document as it is; '' when it saved."""
        before = self.xml()
        r = _send(self.client, self.case, ch.el, ch.value)
        if r.status_code != 200:
            return f"HTTP {r.status_code}: {r.json().get('detail')}"
        res = r.json()
        if res.get("reshaped") or res.get("structure"):
            return "reshaped"
        ch.printed = res.get("value") if isinstance(res.get("value"), str) else ""
        if not ch.value:
            return ""                    # taken off: the reload says whether it went
        return "" if _stored(self.xml(), before, ch, res) else "answered 200 but nothing was stored"

    def answered(self, ch: Choice, depth: int = 0) -> str:
        """Send it on the document as it is; a refusal that names the answer
        to give first ("Answer ADU (10.011) with Yes first") is followed --
        that answer given in the same copy of the section, then this one
        again.  '' or 'reshaped' when it saved."""
        why = self.pick(ch)
        gate = re.search(r"Answer .+? \((\d+\.\d+(?:\.\d+)?)\)(?: with (.+?))? first", why)
        if not gate or depth > 2:
            return why
        fid, want = gate.group(1), gate.group(2)
        kept = self.xml()
        controls = sorted((c for c in self.choices if c.field == fid and c.kind != "tick"),
                          key=lambda c: c.el.get("data-iscope") != ch.el.get("data-iscope"))
        seen = set()
        for c in controls:
            url = f"/api/fields/{fid}/options" + (f"?dp={c.el.get('data-tdp')}" if c.el.get("data-tdp") else "")
            for o in self.client.get(url).json()["options"]:
                if not o["value"] or (want and _words(o["label"]) != _words(want)) \
                        or (id(c.el), o["value"]) in seen:
                    continue
                seen.add((id(c.el), o["value"]))
                first = Choice(c.kind, c.el, fid, c.section, o["value"], o["label"], c.nth)
                if self.answered(first, depth + 1) in ("", "reshaped") \
                        and (again := self.pick(ch)) in ("", "reshaped") \
                        and (depth or again == "reshaped" or _shown(self.blank, _editor(self.case), ch)):
                    # the answer under which this one applies: Legally Rentable
                    # = No leaves its source out (B-1, T-1066), Yes keeps it
                    return again
                self.st.xml_path(self.case).write_bytes(kept)
                self.st.touch(self.case)
        return why

    def alone(self, ch: Choice) -> str:
        """On a fresh blank, after the answer a refusal names; '' when it
        saved and shows after the reload.  A choice that gives the report
        another shape (3.011 Condominium = Yes) is judged on the reshaped one."""
        self.reset()
        why = self.answered(ch)
        if why and why != "reshaped":
            return why
        return "" if _shown(self.blank, _editor(self.case), ch) else "saved but not shown after the reload"

    def every(self) -> dict[str, str]:
        by_section: OrderedDict[str, list[Choice]] = OrderedDict()
        for ch in self.choices:
            by_section.setdefault(ch.section, []).append(ch)
        passes = [[q[i] for q in by_section.values() if i < len(q)]
                  for i in range(max(len(q) for q in by_section.values()))]
        again: list[Choice] = []
        for batch in passes:
            self.reset()
            sent = []
            for ch in batch:
                why = self.pick(ch)
                if why == "reshaped":
                    # the report took another shape: what this pass wrote is gone
                    again += sent + [ch]
                    sent = []
                    self.reset()
                elif why:
                    again.append(ch)
                else:
                    sent.append(ch)
            doc = _editor(self.case)
            again += [ch for ch in sent if not _shown(self.blank, doc, ch)]
        failed = {}
        for ch in again:
            why = self.alone(ch)
            if why:
                failed[ch.name] = why
        return failed


def _assert_clean(root) -> None:
    """Every relationship still joins two things the document has."""
    labels = {e.get(f"{X}label") for e in root.iter() if isinstance(e.tag, str) and e.get(f"{X}label")}
    loose = [(r.get(f"{X}from"), r.get(f"{X}to")) for r in root.iter(f"{M}RELATIONSHIP")
             if r.get(f"{X}from") not in labels or r.get(f"{X}to") not in labels]
    assert not loose, loose


# ------------------------------------------------------------- the owner's case
def _listing_sources(client, case) -> list[str]:
    """The Subject Listing's sources in the XML that ships, read through the arcrole."""
    root = etree.fromstring(client.get(f"/api/cases/{case}/mismo.xml").content)
    summary = next(bind.subject(root).iter(f"{M}LISTING_INFORMATION_SUMMARY"))
    tied = {r.get(f"{X}from") for r in root.iter(f"{M}RELATIONSHIP")
            if r.get(f"{X}to") == summary.get(f"{X}label")
            and r.get(f"{X}arcrole", "").endswith("DATA_SOURCE_IsDataSourceFor_LISTING_INFORMATION_SUMMARY")}
    return [ds.findtext(f"{M}DataSourceType") for ds in root.iter(f"{M}DATA_SOURCE")
            if ds.get(f"{X}label") in tied]


def _listing_controls(case):
    return [el for el in _editor(case).iter("span") if "19.001" in (el.get("data-fid"), el.get("data-tf"))]


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_subject_listing_data_source_selects_saves_and_reloads(client, template):
    case = _case(client, template)
    before = len(schema.validate(api.store().tree(case)))
    first = _listing_controls(case)
    assert len(first) == 1 and first[0].get("data-fid") == "19.001"
    r = _send(client, case, first[0], "MLS")
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "MLS"
    assert _listing_sources(client, case) == ["MLS"]
    shown = [_words(el.text_content()) for el in _listing_controls(case)]
    assert shown == ["MLS", ""], shown              # its value, then "+ another"
    fields = {f["field_id"]: f for s in client.get(f"/api/cases/{case}/fields?section=19").json()["sections"]
              for f in s["fields"]}
    assert fields["19.001"]["value"] == "MLS" and fields["19.001"]["edit_value"] == "MLS"

    # the reloaded row changes the source, "+ another" adds one, and emptying
    # a row takes that one off -- each through the route the page sends it to
    row, more = _listing_controls(case)
    assert _send(client, case, row, "AssessorRecord").status_code == 200
    assert _listing_sources(client, case) == ["AssessorRecord"]
    row, more = _listing_controls(case)
    r = _send(client, case, more, "PropertyOwner")
    assert r.status_code == 200, r.text
    assert _listing_sources(client, case) == ["AssessorRecord", "PropertyOwner"]
    assert [_words(el.text_content()) for el in _listing_controls(case)] == \
        ["Assessor Record", "Property Owner", ""]
    # "Other" and then its description, as the page's list sends them (the
    # row takes the key the first answer returns)
    row = _listing_controls(case)[1]
    r = _send(client, case, row, "Other")
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/cases/{case}/cells/19.001",
                     json={"value": "Seller's agent", "key": r.json()["key"],
                           "data_point": "DataSourceTypeOtherDescription"})
    assert r.status_code == 200, r.text
    assert "Seller's agent" in _words(" ".join(el.text_content() for el in _listing_controls(case)))
    row = _listing_controls(case)[0]
    assert _send(client, case, row, "").status_code == 200
    assert _listing_sources(client, case) == ["Other"]
    root = api.store().tree(case).getroot()
    _assert_clean(root)
    assert len(schema.validate(api.store().tree(case))) <= before


def test_a_source_tied_to_more_than_the_listing_keeps_its_other_ties(client):
    """D-1 SF5 ties one DATA_SOURCE_MLS to the subject's listing and to its
    prior sales: changing the listing's source leaves the prior sales' alone."""
    case = client.post("/api/cases", json={"template": "sf5_appraisal_v1_2", "blank": False,
                                           "name": "shared"}).json()["case_id"]
    row = next(el for el in _listing_controls(case) if el.get("data-tk"))
    assert _words(row.text_content()) == "MLS"
    r = _send(client, case, row, "AssessorRecord")
    assert r.status_code == 200, r.text
    assert _listing_sources(client, case) == ["AssessorRecord"]
    root = api.store().tree(case).getroot()
    prior = [r.get(f"{X}from") for r in root.iter(f"{M}RELATIONSHIP")
             if r.get(f"{X}arcrole", "").endswith("IsDataSourceFor_PriorSalesOrTransfersIndicator")]
    by = {ds.get(f"{X}label"): ds.findtext(f"{M}DataSourceType") for ds in root.iter(f"{M}DATA_SOURCE")}
    assert prior and all(by.get(p) == "MLS" for p in prior), prior
    _assert_clean(root)


@pytest.mark.parametrize("template", [t.key for t in templates.catalogue()])
def test_every_source_tied_by_arcrole_saves_and_reloads(client, template):
    """The mechanism, not the one field: every data source on the page whose
    sources B-1 / A-1 tie by arcrole (form.data_source_target) -- picked on a
    new report of each of the twelve D-1 kinds, saved, read back, and shown
    after the reload; or refused with the answer it is the source of, and
    saved once that is given (25.052 Cost Data Source on MH1, tied to the
    valuation's COST_APPROACH, was refused outright)."""
    run = Run(client, template)
    tied = [ch for ch in run.choices if ch.kind == "pick" and edit.source_target(
        ch.field, edit.choose_data_point(edit._binding_for(ch.field), ch.el.get("data-tdp") or ""))]
    if template in TEMPLATES:
        assert {"19.001", "17.018", "10.009"} <= {ch.field for ch in tied}
    assert tied
    failed = {ch.name: why for ch in tied if (why := run.alone(ch))}
    assert not failed, failed


@pytest.mark.parametrize("template", TEMPLATES)
def test_every_dropdown_and_yes_no_saves_and_reloads(client, template):
    run = Run(client, template)
    kinds = {k: sum(ch.kind == k for ch in run.choices) for k in ("pick", "box", "tick")}
    assert kinds["pick"] > 200 and kinds["box"] > 20, kinds
    # every list offers something to pick
    assert not [ch.name for ch in run.choices if ch.kind == "pick" and not ch.value]
    failed = run.every()
    unexpected = {k: v for k, v in failed.items() if not _known(k, template)}
    here = {_known(ch.name, template) for ch in run.choices} - {""}
    fixed = sorted(here - {_known(k, template) for k in failed})
    print(f"\n{template}: {len(run.choices)} choices {kinds} on "
          f"{len({ch.field for ch in run.choices})} fields; {len(failed)} known failures "
          f"({len({_known(k, template) for k in failed})} KNOWN entries)")
    assert not unexpected, unexpected
    assert not fixed, f"these now save -- take them off KNOWN: {fixed}"
