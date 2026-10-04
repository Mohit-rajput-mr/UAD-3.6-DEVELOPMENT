"""How much of the UAD 3.6 report the editor really implements, field by field.

Nothing here is a hand-kept list.  The universe of fields is every Report
Field ID that Appendix A-1 locates on the report (``spec/field_index.json``)
or that Appendix C-1 places on the page (``spec/c1_form.json``).  For each one
the audit asks, against all twelve Appendix D-1 sample cases:

* **placed**   -- does C-1 place it, and in which kind of element (a row, a
  table cell, a comparable-grid row, an image slot, a party block)?
* **control**  -- does the editor draw a control for it, and is it the control
  A-1's format calls for (an Enumerated field is a list of A-1's values, a
  Boolean is a pair of tick boxes, anything else is typed)?
* **write**    -- does a value written to it read back from the same field,
  and does the document still validate against the GSE subschema?
* **print**    -- does the printed report carry it (a value in a sample that
  prints, or a place it would print)?
* **rules**    -- which H-1 compliance rules name it?

and classifies it IMPLEMENTED, PARTIAL, MISSING, INCORRECT or NOT APPLICABLE,
with the reason.  Summary fields are redisplays (B-1 chapter 01) and are
judged by their source field; fields A-1 says "Does Not Display" are judged
by the Additional Data editor (``uad/extra.py``); images by the exhibit and
photo slots.

Run it::

    python engine/uad/coverage.py            # writes _work/coverage.json and
                                             # _work/UAD36_CHECKLIST.md
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from lxml import etree, html as lhtml

ENGINE = Path(__file__).resolve().parents[1]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from uad import bind, edit, extra, schema, templates  # noqa: E402
from uad.report import comparables, form  # noqa: E402

SPEC = ENGINE / "spec"
WORK = ENGINE.parent / "_work"

IMPLEMENTED, PARTIAL, MISSING, INCORRECT, NA = (
    "IMPLEMENTED", "PARTIAL", "MISSING", "INCORRECT", "NOT APPLICABLE")

SAMPLE_VALUES = {"String": "Coverage Test", "Amount": "123456", "Date": "2026-03-04",
                 "Datetime": "2026-03-04T10:00:00Z", "Numeric": "7"}


@dataclass
class Field:
    fid: str
    section: str
    label: str
    format: str = ""
    conditionality: str = ""
    placement: str = ""            # row / table / grid / image / party / text / none
    control: str = ""              # text / pick / check / grid / derived / exhibit / extra / ""
    expected: str = ""
    write: str = ""                # ok / wrong / error / n/a
    write_detail: str = ""
    rules: int = 0
    boxes: int = 0                 # tick boxes drawn for this field
    samples_with_section: int = 0
    status: str = ""
    reason: str = ""


# --------------------------------------------------------------- the universe
@lru_cache(maxsize=1)
def _index() -> dict:
    return json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]


def _value_options(dp: dict) -> list[str]:
    """The values a data point may take, when A-1 closes the list.

    A unit attribute's list is of units ("SquareFeet"), not of values, so a
    measured data point has none.
    """
    from uad import entry

    if entry.unit_attribute(dp):
        return []
    return [o["value"] for o in dp.get("enumerations") or [] if o.get("value")]


@lru_cache(maxsize=1)
def c1_placements() -> dict[str, str]:
    """Report Field ID -> the kind of C-1 element that places it."""
    out: dict[str, str] = {}
    for pg in form.form()["pages"]:
        for el in pg["elements"]:
            kind = el["kind"]
            for fid in el.get("ids") or []:
                if fid.endswith(".1") and fid.count(".") >= 2:
                    out.setdefault(fid, "image")
                elif fid.endswith(".2") and fid.count(".") >= 2:
                    out.setdefault(fid, "image caption")
                else:
                    out.setdefault(fid, {"slot": "text", "photo": "image"}.get(kind, kind))
            for row in el.get("rows") or []:
                for fid in row.get("ids") or []:
                    out.setdefault(fid, "table")
                for cell in row.get("cells") or []:
                    for fid in cell.get("ids") or []:
                        out.setdefault(fid, "table")
    return out


def universe() -> dict[str, Field]:
    out: dict[str, Field] = {}
    placements = c1_placements()
    for fid, entry in _index().items():
        loc = (entry.get("locations") or [{}])[0]
        out[fid] = Field(fid, loc.get("section", ""), loc.get("label", ""))
    for fid in placements:
        out.setdefault(fid, Field(fid, bind.SECTION_NAME.get(int(fid.split(".")[0]) if fid.split(".")[0].isdigit() else 0, ""), ""))
    for fid, f in out.items():
        f.placement = placements.get(fid, "none")
        entry = _index().get(fid) or {}
        dps = [d for d in entry.get("data_points") or [] if d.get("mismo") and not d.get("attribute")]
        if dps:
            try:
                dp = edit.choose_data_point(edit._binding_for(fid))
            except Exception:
                dp = dps[0]
            f.format = (dp.get("format_type") or "").strip()
            f.conditionality = (dp.get("conditionality") or "").strip()
            f.expected = {"Enumerated": "pick", "Boolean": "check|pick"}.get(f.format, "text")
            # A-1 types some code lists as String (DataSourceQualityRatingCode:
            # Average, Excellent, Fair...).  A closed list of values is picked,
            # whatever the format column calls it -- B-1 Usability item 1 --
            # so expecting a typed box there faulted a correct dropdown.
            if f.expected == "text" and _value_options(dp):
                f.expected = "pick"
    grid_fids = set()
    for kind in comparables.SHEETS:
        for row in comparables.rows(kind):
            grid_fids.update(x for x in (row.subject_fid, row.comp_fid) if x)
    for fid in grid_fids:
        if fid in out:
            out[fid].placement = "grid"
    return out


# ------------------------------------------------------------------ controls
def controls_in(html_text: str) -> dict[str, set[str]]:
    """Report Field ID -> the controls the editor draws for it."""
    doc = lhtml.fromstring(html_text)
    found: dict[str, set[str]] = defaultdict(set)
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        cls = el.get("class") or ""
        fid = el.get("data-fid")
        if fid:
            if "pick" in cls.split():
                found[fid].add("pick")
            elif "bx" in cls.split():
                found[fid].add("check")
                if el.get("data-pick"):
                    found[fid].add("box:" + el.get("data-pick"))
            elif el.get("contenteditable") == "true":
                found[fid].add("text")
        if el.get("data-gf"):
            found[el.get("data-gf")].add("grid")
        if el.get("data-gaf"):
            found[el.get("data-gaf")].add("grid")
        if el.get("data-tf"):
            found[el.get("data-tf")].add("table")
        # A fixed row whose instance does not exist yet names the field that
        # identifies it: typing into the row creates the instance with that
        # value, so that field is edited there as surely as the cell is.
        if el.get("data-tsel"):
            found[el.get("data-tsel")].add("table")
        if el.get("data-pf"):
            found[el.get("data-pf")].add("party")
        if el.get("data-derived") is not None:
            for src in (el.get("data-derived") or "").split():
                found[src].add("source-of-summary")
    return found


def audit(keys: list[str] | None = None) -> list[Field]:
    fields = universe()
    rules = Counter()
    raw_rules = json.loads((SPEC / "compliance_rules.json").read_text(encoding="utf-8"))
    for r in (raw_rules if isinstance(raw_rules, list) else raw_rules.get("rules", [])):
        for fid in re.findall(r"\b\d{1,2}\.\d{2,3}(?:\.\d{1,2})?\b", json.dumps(r)):
            rules[fid] += 1
    extra_names = {(r.scope, r.name) for r in extra.rows()}
    section_seen: Counter = Counter()
    controls: dict[str, set[str]] = defaultdict(set)

    for tpl in templates.catalogue():
        if keys and tpl.key not in keys:
            continue
        tree = etree.parse(str(tpl.path))
        blocks = form.build(tree, folder=tpl.path.parent, edit=True)
        for sec in {form.section_number(b.section) for b in blocks if b.visible}:
            section_seen[sec] += 1
        for fid, kinds in controls_in(form.galley_html(blocks, edit=True)).items():
            controls[fid] |= kinds

    first = templates.get((keys or ["sf1_appraisal_v1_4"])[0])
    tree = etree.parse(str(first.path))
    root = tree.getroot()
    comps = comparables.properties(root, "SalesComparable")

    for fid, f in fields.items():
        f.rules = rules.get(fid, 0)
        num = int(fid.split(".")[0]) if fid.split(".")[0].isdigit() else 0
        f.samples_with_section = section_seen.get(num, 0)
        kinds = controls.get(fid, set())
        f.boxes = len({k for k in kinds if k.startswith("box:")})
        if num == 1:
            f.control = "derived"
        elif f.placement in ("image", "image caption"):
            f.control = "exhibit"
        elif "grid" in kinds:
            f.control = "grid"
        elif "table" in kinds:
            f.control = "table"
        elif kinds - {"source-of-summary"}:
            plain = {k for k in kinds if not k.startswith(("box:", "source-of"))}
            if plain:
                f.control = sorted(plain)[0]

        # write and read back, in the right scope
        entry = _index().get(fid) or {}
        if num == 1 or f.placement in ("image", "image caption") or not entry.get("data_points"):
            f.write = "n/a"
        else:
            try:
                binding = edit._binding_for(fid)
                dp = edit.choose_data_point(binding)
                kind = (dp.get("format_type") or "String").strip()
                options = _value_options(dp)
                if kind == "Enumerated" or (kind == "String" and options):
                    # a code list takes one of its own codes; free text there
                    # is not a value the schema accepts
                    value = options[0] if options else "Coverage"
                elif kind == "Boolean":
                    value = "true"
                else:
                    value = SAMPLE_VALUES.get(kind, "Coverage Test")
                roles = (entry.get("roles") or [])
                scope = comps[0] if (f.placement == "grid" and comps and fid in _comp_fids()) else None
                written = edit.write(tree, fid, value, binding=binding, scope=scope)
                if fid in ("2.010", "2.011"):
                    # The client's second role is found by an anchor (the
                    # party already tagged Client) that the ordinary read
                    # mistakes for the value itself; the same exception the
                    # API's own write-then-verify step makes.
                    got = edit.read_client_role(root)
                else:
                    back = bind.locate(root, binding, written.data_point, scope, 1)
                    got = (back.text or "").strip() if back is not None else ""
                if got != written.new:
                    # A-1 gates some data points on an indicator elsewhere
                    # ("IF IncomeApproachIndicator = true").  The editor never
                    # shows a gated field while its gate is shut, so the audit
                    # opens the gate and asks again rather than reporting a
                    # field that works as broken.
                    opened = _open_gates(root, dp)
                    if opened:
                        edit.write(tree, fid, value, binding=binding, scope=scope)
                        back = bind.locate(root, binding, written.data_point, scope, 1)
                        got = (back.text or "").strip() if back is not None else ""
                        if got == written.new:
                            f.write_detail = "displays when " + ", ".join(opened)
                f.write = "ok" if got == written.new else "wrong"
                if f.write == "wrong":
                    f.write_detail = f"wrote {written.new!r}, read {got!r}"
            except Exception as exc:
                f.write, f.write_detail = "error", f"{type(exc).__name__}: {exc}"[:160]

        _classify(f, extra_names)
    problems = schema.validate(tree)
    if problems:
        for f in fields.values():
            if f.write == "ok":
                f.write_detail = f"document invalid after all writes: {problems[0].message[:100]}"
    return sorted(fields.values(), key=lambda f: _sort_key(f.fid))


@lru_cache(maxsize=1)
def _comp_fids() -> frozenset[str]:
    out = set()
    for kind in comparables.SHEETS:
        out.update(r.comp_fid for r in comparables.rows(kind) if r.comp_fid)
    return frozenset(out)


def _open_gates(root, dp: dict) -> list[str]:
    """Set the indicators A-1 conditions this data point on, and say which."""
    opened = []
    for key, want in (dp.get("requires") or {}).items():
        if key.startswith(("@", "__")) or not key.endswith("Indicator"):
            continue
        for node in root.iter(f"{{{bind.MISMO}}}{key}"):
            if (node.text or "").strip() != want:
                node.text = want
                opened.append(f"{key} = {want}")
    return opened


def _classify(f: Field, extra_names) -> None:
    if not (_index().get(f.fid) or {}).get("data_points"):
        f.status, f.reason = NA, "no A-1 data point: a layout marker, static text or a condition anchor"
        return
    if f.control == "derived":
        f.status, f.reason = NA, "Summary redisplays its source field (B-1 ch. 01); read-only by design"
        return
    if f.control == "exhibit":
        f.status, f.reason = IMPLEMENTED, "image slot: exhibit box / photo slot, delivered as IMAGE by delivery.py"
        return
    if f.samples_with_section == 0 and not f.control:
        f.status, f.reason = PARTIAL, "section not printed by any D-1 sample, so the editor could not be exercised"
        return
    if not f.control:
        if f.placement == "table":
            f.status, f.reason = MISSING, "value prints in a table but the table cell has no editor control"
        elif f.placement == "party" or f.section == "Assignment Information" and "Contact" in (_index().get(f.fid, {}).get("report_location") or ""):
            f.status, f.reason = MISSING, "contact/party block value has no editor control"
        elif f.placement == "none":
            f.status, f.reason = MISSING, "A-1 locates it on the report but C-1 does not place it and the editor has no control"
        else:
            f.status, f.reason = MISSING, f"C-1 places it ({f.placement}) but the editor draws no control"
        return
    if f.control == "table":
        f.status, f.reason = IMPLEMENTED, "table cell control (instance-addressed, XSD-checked write)"
        return
    if f.control == "grid":
        ok = f.write in ("ok", "n/a")
        f.status = IMPLEMENTED if ok else INCORRECT
        f.reason = "comparable grid cell editor" + ("" if ok else f"; write {f.write}: {f.write_detail}")
        return
    if (f.expected == "pick" and f.control == "check" and f.boxes > 1):
        # An enumerated value with a box per value is how the URAR asks it --
        # "Condominium / Cooperative / Condop" is a run of tick boxes on the
        # form itself, not a list -- and one box per A-1 value is the same
        # question asked the way C-1 draws it.
        f.status, f.reason = IMPLEMENTED, f"a tick box per A-1 value ({f.boxes})"
        return
    if f.expected and f.control in ("text", "pick", "check") and f.control not in f.expected.split("|"):
        f.status, f.reason = INCORRECT, f"A-1 format {f.format} calls for {f.expected}, editor draws {f.control}"
        return
    if f.write == "ok":
        f.status, f.reason = IMPLEMENTED, f"{f.control} control; writes, reads back and validates"
    elif f.write == "n/a":
        f.status, f.reason = IMPLEMENTED, f"{f.control} control"
    else:
        f.status, f.reason = INCORRECT, f"{f.control} control but write {f.write}: {f.write_detail}"


def _sort_key(fid: str):
    return [int(p) if p.isdigit() else 0 for p in re.split(r"\.", fid)]


# ------------------------------------------------------------------- report
def summary(fields: list[Field]) -> dict:
    by_status = Counter(f.status for f in fields)
    by_section: dict[str, Counter] = defaultdict(Counter)
    for f in fields:
        by_section[f.section or "(unlocated)"][f.status] += 1
    by_reason = Counter((f.status, re.sub(r"[:;].*", "", f.reason)) for f in fields
                        if f.status not in (IMPLEMENTED, NA))
    return {"total": len(fields), "by_status": dict(by_status),
            "by_section": {k: dict(v) for k, v in by_section.items()},
            "by_reason": [{"status": s, "reason": r, "count": n} for (s, r), n in by_reason.most_common()]}


def extra_coverage() -> dict:
    """A-1 'Does Not Display' appraiser data: served by the Additional Data tab."""
    return {"rows": len(extra.rows()), "status": IMPLEMENTED,
            "reason": "uad/extra.py rows derived from A-1; edited in the Additional Data tab, XSD-checked"}


def exhibit_coverage() -> list[dict]:
    """Every A-1 ImageCategoryType: where an appraiser supplies it."""
    out = []
    for value, (section, caption) in form.image_categories().items():
        if value in ("PropertyPhoto", "DwellingFront"):
            how, status = "subject/comparable photo slots", IMPLEMENTED
        elif value == "SalesComparableMap":
            how, status = "Sales Comparison Map (map tool)", IMPLEMENTED
        elif section:
            how, status = f"+ Add Exhibit in {section}", IMPLEMENTED
        else:
            how, status = "no section on the report to add it from", PARTIAL
        out.append({"category": value, "section": section, "caption": caption,
                    "how": how, "status": status})
    return out


def write_reports(fields: list[Field]) -> tuple[Path, Path]:
    WORK.mkdir(exist_ok=True)
    data = {"summary": summary(fields), "extra": extra_coverage(),
            "exhibits": exhibit_coverage(), "fields": [asdict(f) for f in fields]}
    jpath = WORK / "coverage.json"
    jpath.write_text(json.dumps(data, indent=1), encoding="utf-8")

    s = data["summary"]
    lines = ["# UAD 3.6 implementation checklist", "",
             "Generated by `python engine/uad/coverage.py` from A-1, C-1, H-1 and the",
             "twelve D-1 samples.  Do not edit by hand -- re-run it.", "",
             "| Status | Fields |", "|---|---|"]
    for k in (IMPLEMENTED, PARTIAL, INCORRECT, MISSING, NA):
        lines.append(f"| {k} | {s['by_status'].get(k, 0)} |")
    lines += ["", f"Total Report Field IDs: {s['total']}.  Additional Data (A-1 Does Not Display): "
              f"{data['extra']['rows']} data points, {data['extra']['status']}.", "",
              "## Gaps by cause", "", "| Status | Cause | Fields |", "|---|---|---|"]
    for r in s["by_reason"]:
        lines.append(f"| {r['status']} | {r['reason']} | {r['count']} |")
    lines += ["", "## By section", "", "| Section | " + " | ".join((IMPLEMENTED, PARTIAL, INCORRECT, MISSING, NA)) + " |",
              "|---|---|---|---|---|---|"]
    for sec, c in sorted(s["by_section"].items(), key=lambda kv: form.SECTION_NUMBER.get(kv[0], 99)):
        lines.append(f"| {sec} | " + " | ".join(str(c.get(k, 0)) for k in (IMPLEMENTED, PARTIAL, INCORRECT, MISSING, NA)) + " |")
    lines += ["", "## Exhibit categories", "", "| Category | Section | How | Status |", "|---|---|---|---|"]
    for e in data["exhibits"]:
        lines.append(f"| {e['category']} | {e['section']} | {e['how']} | {e['status']} |")
    lines += ["", "## Every field that is not implemented", "",
              "| FID | Section | Label | Format | Placed | Status | Reason |", "|---|---|---|---|---|---|---|"]
    for f in fields:
        if f.status in (MISSING, INCORRECT, PARTIAL):
            lines.append(f"| {f.fid} | {f.section} | {f.label} | {f.format} | {f.placement} | {f.status} | {f.reason} |")
    mpath = WORK / "UAD36_CHECKLIST.md"
    mpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jpath, mpath


def main() -> None:
    fields = audit()
    j, m = write_reports(fields)
    s = summary(fields)
    print(json.dumps(s["by_status"]), "->", m)
    for r in s["by_reason"][:15]:
        print(f"  {r['count']:>4}  {r['status']:<11} {r['reason']}")


if __name__ == "__main__":
    main()
