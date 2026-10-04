"""Phase 3: prove the output, scenario by scenario, check by check.

Nine checks are run against each of the twelve official Appendix D-1 cases.
Each check is run against the **GSE's own sample first**: a check that faults a
published sample is a broken check, not a broken build, and is reported as such
rather than being allowed to fail the engine's output.

  1  package        the regenerated package against the official one
  2  schema         the MISMO document against the GSE subschema
  3  compliance     Fatal and Warning counts from the 728 H-1 rules
  4  fonts          only Myriad Pro (or Calibri) embedded in the PDF
  5  furniture      header absent on the Summary, present on every other page
  6  grid           the comparable-grid rows against the F-1 supplement
  7  traceability   every value printed on the page found in the XML
  8  archive        the ZIP's structure
  9  overflow       nothing rendered below the body rule, on any page

Nothing here is graded on a curve.  Where the engine does not yet produce
something -- the comparable grids, at the time of writing -- the check reports
that plainly instead of passing.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from decimal import Decimal, InvalidOperation
from html import unescape
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import bind, compliance, review, schema, templates  # noqa: E402
from uad.report import flow, form, urar  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "_work" / "harness"

# Each official sample is bound behind a specification wrapper, and the wrapper
# is not always the same length -- Condo2 runs to three pages where the others
# run to two.  Assuming a fixed two made this harness read the wrapper's
# disclaimer page as the report's first page and fault the sample.  The report
# begins at the first page carrying the form's own footer.
FOOTER_MARK = "Fannie Mae | Freddie Mac"


def report_start(path: Path) -> int:
    """The index of the first report page, skipping the specification wrapper."""
    doc = pymupdf.open(path)
    try:
        for i in range(doc.page_count):
            pg = doc[i]
            for b in pg.get_text("dict")["blocks"]:
                for line in b.get("lines", []):
                    for s in line["spans"]:
                        if (s["bbox"][1] > pg.rect.height - 90
                                and FOOTER_MARK in s["text"]):
                            return i
        return 0
    finally:
        doc.close()

# The faces the GSEs themselves embed in the *report* pages of the samples:
# the five Myriad Pro weights, Wingdings 2 for the tick boxes, Caflisch Script
# for a signature, and Calibri where the Style Guide names it as the
# substitute.  The two-page specification wrapper bound in front of each sample
# also carries Arial, Courier and Symbol, which belong to the wrapper and not
# to the form -- counting those made this check fault all twelve samples.
ALLOWED_FONTS = ("MyriadPro", "Calibri", "Wingdings2", "CaflischScriptPro")

PASS, FAIL, GAP, NA = "pass", "FAIL", "gap", "n/a"


@dataclass
class Result:
    check: str
    status: str
    detail: str = ""

    @property
    def mark(self) -> str:
        return {PASS: "  ok  ", FAIL: " FAIL ", GAP: " gap  ", NA: "  --  "}[self.status]


@dataclass
class Scenario:
    key: str
    results: list[Result] = field(default_factory=list)

    def add(self, check: str, status: str, detail: str = "") -> None:
        self.results.append(Result(check, status, detail))


# --------------------------------------------------------------------- checks
def check_schema(tree) -> Result:
    errors = schema.validate(tree)
    if not errors:
        return Result("schema", PASS, f"valid against v{schema.schema_version()}")
    return Result("schema", FAIL, f"{len(errors)} error(s): {str(errors[0])[:90]}")


def check_compliance(tree) -> Result:
    findings = compliance.evaluate(tree)
    counts = compliance.summarise(findings)
    if counts["fatal"] or counts["warning"]:
        return Result("compliance", FAIL,
                      f"{counts['fatal']} fatal, {counts['warning']} warning")
    return Result("compliance", PASS,
                  f"0 fatal, 0 warning, {counts['review']} for a reader")


def pdf_fonts(path: Path, skip: int = 0) -> set[str]:
    doc = pymupdf.open(path)
    names = set()
    for i in range(skip, doc.page_count):
        for f in doc[i].get_fonts(full=True):
            names.add(f[3].split("+")[-1])
    doc.close()
    return names


def check_fonts(pdf: Path, skip: int = 0) -> Result:
    """Only the form's own faces are embedded.

    ``skip`` passes over the two-page specification wrapper bound in front of
    each official sample, whose Arial, Courier and Symbol belong to the wrapper
    rather than to the report.
    """
    names = {n for n in pdf_fonts(pdf, skip) if n}
    stray = [n for n in names if not any(a in n for a in ALLOWED_FONTS)]
    if not names:
        return Result("fonts", FAIL, "no named font embedded (Type3 output)")
    if stray:
        return Result("fonts", FAIL, f"unexpected: {sorted(stray)}")
    return Result("fonts", PASS, ", ".join(sorted(names)))


def page_furniture(path: Path, skip: int = 0):
    """Which pages carry a header, a footer, and body text of their own."""
    doc = pymupdf.open(path)
    header, footer, body = [], [], []
    for i in range(skip, doc.page_count):
        pg = doc[i]
        n = i - skip + 1
        for b in pg.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    if not s["text"].strip():
                        continue
                    top = s["bbox"][1]
                    if top < 50:
                        header.append(n)
                    elif top > pg.rect.height - 90:
                        footer.append(n)
                    else:
                        body.append(n)
    total = doc.page_count - skip
    doc.close()
    return sorted(set(header)), sorted(set(footer)), sorted(set(body)), total


def check_furniture(pdf: Path, skip: int = 0) -> Result:
    """The header is absent on the Summary and present wherever there is text.

    A page given over entirely to an image carries no header in the GSEs' own
    samples, so the rule is tied to whether the page has body text rather than
    to its number -- requiring one on every page but the first faulted a
    published sample.
    """
    header, footer, body, total = page_furniture(pdf, skip)
    problems = []
    if 1 in header:
        problems.append("a header is printed on the Summary page")
    missing = [n for n in body if n != 1 and n not in header]
    if missing:
        problems.append(f"no header on text page(s) {missing[:6]}")
    no_footer = [n for n in range(1, total + 1) if n not in footer]
    if no_footer and len(no_footer) > len([n for n in no_footer if n not in body]):
        problems.append(f"no footer on text page(s) {no_footer[:6]}")
    if problems:
        return Result("furniture", FAIL, "; ".join(problems))
    return Result("furniture", PASS,
                  f"no header on the Summary, header on {len(header)} of "
                  f"{total} pages, footer on {len(footer)}")


GRID_SHEET = "f1_sales_rows"


def expected_grid_rows() -> list[str]:
    path = Path(__file__).resolve().parents[1] / "spec" / "supplements.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for row in data.get(GRID_SHEET, []):
        label = " ".join(str(row.get("Report Label") or "").split())
        if label:
            out.append(label)
    return out


def check_grid(sections: list[urar.Section], tree) -> Result:
    """The drawn grid against the rows the specification defines.

    Every row drawn must be one the B-1 supplement names, in its order, and
    every row the supplement marks "always" must be drawn.  A grid that invents
    a row, or drops a required one, is wrong even when every figure in it is
    right.
    """
    from uad.report import comparables

    drawn = [g for s in sections for g in s.grids]
    if not drawn:
        comps = comparables.properties(
            tree.getroot() if hasattr(tree, "getroot") else tree,
            "SalesComparable")
        if not comps:
            return Result("grid", NA, "this case has no sales comparables")
        return Result("grid", FAIL, "comparables exist but no grid was drawn")

    # A row the appraiser adds stands in the place of the supplement's own
    # "[Additional Row]" template and is called whatever they named it, so the
    # check reads the expanded rows: everything else must still be the
    # workbook's, in the workbook's order.
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    spec = comparables.specs(root, "sales")
    known = {r.label for r in spec}
    always = {r.label for r in spec if r.always and not r.heading}
    expected = [r.label for r in spec]

    problems = []
    for grid in drawn:
        if grid.kind != "sales":
            continue
        labels = [r.label for r in grid.rows]
        invented = [l for l in labels if l not in known]
        if invented:
            problems.append(f"rows not in the supplement: {invented[:3]}")
        missing = sorted(always - set(labels))
        if missing:
            problems.append(f"{len(missing)} always-display row(s) missing, "
                            f"e.g. {missing[:3]}")
        # Order is judged as a subsequence, walking both lists together.  A
        # label-to-position map cannot judge it: "[Additional Row]" and the
        # section headings each occur many times, so the map keeps only the
        # last position and every correct grid looks out of order.
        i = 0
        for label in labels:
            while i < len(expected) and expected[i] != label:
                i += 1
            if i >= len(expected):
                problems.append(f"row {label!r} comes after where the "
                                "supplement places it")
                break
            i += 1
    if problems:
        return Result("grid", FAIL, "; ".join(dict.fromkeys(problems))[:140])
    blocks = [g for g in drawn if g.kind == "sales"]
    rows_drawn = sum(len(g.rows) for g in blocks)
    added = sum(1 for r in spec if r.item_name)
    named = f", {added} named by the appraiser" if added else ""
    return Result("grid", PASS,
                  f"{len(blocks)} block(s), {rows_drawn} rows, all from the "
                  f"supplement's {len(spec)}{named} and in its order")


MONEY = re.compile(r"[^0-9.\-]")


# A value may be written without its leading zero -- the samples carry
# ".75" where the page prints "0.75" -- so the pattern admits both.
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?|\.\d+")
PAGE_NUMBER = re.compile(r"^Page \d+ of \d+$", re.I)


def _numbers(text: str) -> list[str]:
    """The numeric values in a string, in one canonical form.

    Separators, leading zeros and trailing decimal zeros all vary between the
    XML and the page -- 4.060 is printed 4.06 -- so each figure is reduced to
    the number it represents before the two are compared.

    The reduction is exact.  Going through ``float`` and ``%g`` keeps six
    significant digits, which is fine for money and rates and wrong for the
    long identifiers this report carries: a manufactured home's 16-digit serial
    came back as ``8.74985e+15``, and every serial sharing its first six digits
    would have compared equal.  ``Decimal`` keeps the digits that were written.
    """
    out = []
    for m in NUMBER.finditer(text):
        bare = m.group(0).replace(",", "").rstrip(".")
        if not bare or not bare.strip("0."):
            continue
        try:
            value = Decimal(bare).normalize()
        except InvalidOperation:
            continue
        # normalize() writes 100 as 1E+2; restore the plain digits.
        out.append(format(value, "f"))
    return out


def _wrapped(text: str, below: str, in_xml: set[str]) -> bool:
    """Does the figure ending `text` continue at the start of `below`?

    Only if putting the two together makes a figure the XML actually holds --
    which is what stops a zip code above a street number being read as one
    number.
    """
    tail = re.search(r"[\d,]+\.?\d*$", text)
    head = re.match(r"\d[\d,]*(?:\.\d+)?", below)
    if not tail or not head:
        return False
    whole = _numbers(tail.group(0) + head.group(0))
    return bool(whole) and whole[-1] in in_xml


def check_traceability(pdf: Path, tree) -> Result:
    """Is every figure printed on the page present in the case document?

    A figure on a report that is not in the XML delivered with it is the
    failure that survives every other check, because both files look fine on
    their own.

    The comparison is made on the *numbers*, not on whole lines.  The page
    composes and reformats as it prints -- 491000 becomes "$491,000",
    2019-09-20 becomes "09/20/2019", four address elements become one line --
    so matching strings would flag correct output.  A date is matched on its
    parts for the same reason.
    """
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    in_xml: set[str] = set()
    for node in root.iter():
        if isinstance(node.tag, str) and node.text and node.text.strip():
            in_xml.update(_numbers(node.text.strip()))
    # A figure the specification puts inside an enumeration's display text --
    # "8 Ft.", "2-4 Units" -- is printed from the spec, not from a data value,
    # so it has no counterpart in the XML and is not a traceability failure.
    for fields in bind.page_model().values():
        for pf in fields:
            for option in pf.binding.enumerations:
                in_xml.update(_numbers(option.get("display", "")))

    doc = pymupdf.open(pdf)
    unknown: list[tuple[str, str]] = []
    checked = 0
    # Certification wording comes from C-1, not the case XML. Only exempt
    # spans matching those actual fixed paragraphs, not arbitrary numbers.
    fixed = [" ".join(unescape(re.sub(r"<[^>]+>", "", b.html)).split())
             for b in form.build(tree) if b.kind == "static" and b.visible]
    for i in range(doc.page_count):
        for b in doc[i].get_text("dict")["blocks"]:
            lines = b.get("lines", [])
            # The text of the line below, for the wrapped-figure rescue.
            below_each = ["".join(sp["text"] for sp in ln["spans"]).lstrip()
                          for ln in lines[1:]] + [""]
            for line, below in zip(lines, below_each):
                spans = line["spans"]
                for k, sp in enumerate(spans):
                    text = " ".join(sp["text"].split())
                    if not text or PAGE_NUMBER.match(text):
                        continue
                    if any(text in paragraph for paragraph in fixed):
                        continue
                    values = _numbers(text)
                    last = k == len(spans) - 1
                    for j, value in enumerate(values):
                        checked += 1
                        if value in in_xml:
                            continue
                        if last and j == len(values) - 1 and \
                                _wrapped(text, below, in_xml):
                            # A figure wider than its column wraps, and a
                            # 17-digit parcel number wraps between digits: the
                            # page carries the whole value but no single line
                            # does.  Wrapping is the right behaviour -- the
                            # alternative is clipping a value off the report --
                            # so a figure continued on the line below is traced
                            # against the whole of it.
                            continue
                        unknown.append((value, text[:48]))
    doc.close()
    if unknown:
        seen = list(dict.fromkeys(unknown))
        return Result("traceability", FAIL,
                      f"{len(seen)} figure(s) not in the XML, e.g. "
                      f"{[f'{v} in {t!r}' for v, t in seen[:3]]}")
    return Result("traceability", PASS, f"{checked} printed figures all traced")


def check_archive(data: bytes) -> Result:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return Result("archive", FAIL, "not a readable archive")
    names = zf.namelist()
    missing = [n for n in ("appraisal.pdf", "mismo.xml") if n not in names]
    images = [n for n in names if n.startswith("Images/")]
    if missing:
        return Result("archive", FAIL, f"missing {missing}")
    return Result("archive", PASS,
                  f"appraisal.pdf, mismo.xml, Images/ ({len(images)})")


def check_overflow(diag: dict) -> Result:
    """Nothing may render below the body rule.

    The measurement is the browser's own, taken from the laid-out page rather
    than from the planner's arithmetic -- the two disagreeing is precisely the
    bug this check exists to catch, so asking the planner would prove nothing.
    ``drift`` is how far the plan was out on its worst page; it is reported on
    a pass as well, because it growing is the early warning that a height has
    started being measured wrong again.
    """
    if not diag:
        return Result("overflow", NA, "the renderer reported no page geometry")
    if diag["overflow"]:
        worst = max(diag["overflow"].values())
        return Result("overflow", FAIL,
                      f"{len(diag['overflow'])} page(s) overrun, deepest "
                      f"{worst:.1f}pt against a {flow.BODY_BOTTOM:.0f}pt body "
                      f"rule: {diag['overflow']}")
    return Result("overflow", PASS,
                  f"{diag['pages']} pages clear of the {flow.BODY_BOTTOM:.0f}pt "
                  f"body rule; plan out by {diag['drift']:+.2f}pt at worst, "
                  f"settled in {diag['attempts']} pass(es)")


def check_package(ours: Path, theirs: Path | None) -> Result:
    """Our pages against the published ones."""
    if theirs is None or not theirs.exists():
        return Result("package", NA, "no official PDF alongside this sample")
    mine = pymupdf.open(ours)
    gse = pymupdf.open(theirs)
    skip = report_start(theirs)
    n_mine, n_gse = mine.page_count, gse.page_count - skip
    size_mine = (round(mine[0].rect.width), round(mine[0].rect.height))
    size_gse = (round(gse[skip].rect.width), round(gse[skip].rect.height))
    mine.close()
    gse.close()
    if size_mine != size_gse:
        return Result("package", FAIL, f"page {size_mine} vs {size_gse}")
    if n_mine == n_gse:
        return Result("package", PASS, f"{n_mine} pages, {size_mine[0]}x{size_mine[1]} pt")
    return Result("package", GAP,
                  f"{n_mine} pages against the sample's {n_gse}; "
                  f"page size matches at {size_mine[0]}x{size_mine[1]} pt")


# ------------------------------------------------------------------ the runs
def validate_checks() -> list[Result]:
    """Run the checks against the untouched samples before trusting them."""
    out = []
    ok_schema = ok_comp = ok_font = ok_furn = 0
    for tpl in templates.catalogue():
        tree = etree.parse(str(tpl.path))
        ok_schema += check_schema(tree).status == PASS
        ok_comp += check_compliance(tree).status == PASS
        if tpl.pdf:
            skip = report_start(tpl.pdf)
            ok_font += check_fonts(tpl.pdf, skip).status == PASS
            ok_furn += check_furniture(tpl.pdf, skip).status == PASS
    n = len(templates.catalogue())
    out.append(Result("schema", PASS if ok_schema == n else FAIL,
                      f"{ok_schema}/{n} official samples pass"))
    out.append(Result("compliance", PASS if ok_comp == n else FAIL,
                      f"{ok_comp}/{n} official samples pass"))
    out.append(Result("fonts", PASS if ok_font == n else FAIL,
                      f"{ok_font}/{n} official PDFs pass"))
    out.append(Result("furniture", PASS if ok_furn == n else FAIL,
                      f"{ok_furn}/{n} official PDFs pass"))
    return out


def run(tpl) -> Scenario:
    sc = Scenario(tpl.key)
    OUT.mkdir(parents=True, exist_ok=True)
    tree = etree.parse(str(tpl.path))

    sections = urar.build(tree)
    # Exercise the renderer used by /preview and /report.pdf, with the
    # official case's referenced images, rather than the retired renderer.
    geometry: dict = {}
    html = flow.build(tree, folder=tpl.path.parent, screen=False,
                      diagnostics=geometry)
    pdf = OUT / f"{tpl.key}.pdf"
    flow.to_pdf(html, pdf)

    sc.results.append(check_package(pdf, tpl.pdf))
    sc.results.append(check_schema(tree))
    sc.results.append(check_compliance(tree))
    sc.results.append(check_fonts(pdf))
    sc.results.append(check_furniture(pdf))
    sc.results.append(check_grid(sections, tree))
    sc.results.append(check_traceability(pdf, tree))
    sc.results.append(check_overflow(geometry))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(pdf, "appraisal.pdf")
        zf.writestr("mismo.xml", etree.tostring(tree, xml_declaration=True,
                                                encoding="utf-8"))
        for src in (tpl.images or [])[:8]:
            zf.writestr(f"Images/{src.name}", src.read_bytes())
    sc.results.append(check_archive(buffer.getvalue()))
    return sc


def main(limit: int | str = 12) -> int:
    limit = int(limit)
    print("VALIDATING THE CHECKS against the official samples\n")
    for r in validate_checks():
        print(f"  [{r.mark}] {r.check:<14} {r.detail}")

    print("\n\nRUNNING THE CHECKS against regenerated output\n")
    order = ["package", "schema", "compliance", "fonts", "furniture",
             "grid", "traceability", "overflow", "archive"]
    head = "  scenario".ljust(40) + "".join(c[:5].ljust(7) for c in order)
    print(head)
    print("  " + "-" * (len(head) - 2))

    scenarios = []
    for tpl in templates.catalogue()[:limit]:
        sc = run(tpl)
        scenarios.append(sc)
        marks = {r.check: r for r in sc.results}
        row = "  " + tpl.key[:36].ljust(38)
        for c in order:
            r = marks.get(c)
            row += ({PASS: "ok", FAIL: "FAIL", GAP: "gap", NA: "--"}
                    .get(r.status if r else NA, "?")).ljust(7)
        print(row)

    print("\n\nDETAIL\n")
    for sc in scenarios:
        print(f"  {sc.key}")
        for r in sc.results:
            print(f"     [{r.mark}] {r.check:<13} {r.detail[:96]}")
        print()

    totals: dict[str, int] = {}
    for sc in scenarios:
        for r in sc.results:
            totals[r.status] = totals.get(r.status, 0) + 1
    print(f"  {totals.get(PASS,0)} pass · {totals.get(FAIL,0)} fail · "
          f"{totals.get(GAP,0)} gap · {totals.get(NA,0)} not applicable"
          f"   ({len(scenarios)} scenarios x {len(order)} checks)")
    return 1 if totals.get(FAIL) else 0


if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:] or [])))
