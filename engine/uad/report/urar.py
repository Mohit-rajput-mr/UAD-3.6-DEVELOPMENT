"""Draw the URAR.

Every number here was measured off the official Appendix D-1 samples, not
designed:

* the sheet is 612 x 1008 pt with 36 pt side margins -- a 45-pica measure;
* the body is two 22-pica columns with a 1-pica gutter, label 4 pt in and
  value 145 pt in, on a 13 pt row;
* a **section tab** is a 14.8 pt black bar at the margin, with a 0.5 pt grey
  rule above it and a 0.5 pt ink rule across the full measure at its foot;
* a **subsection bar** is a 15 pt band of #e6e7e8 across the full measure --
  in the samples it is drawn as a thick *stroke*, which is why an earlier
  version of this module, looking only for filled rectangles, missed most of
  them and set the rest 2 pt short;
* **every field row carries a 0.5 pt #939598 rule beneath it**, spanning its
  whole 264 pt column -- 1,023 of them in one sample.  Without those rules the
  page reads as a list rather than a form, and that single omission is the
  largest reason earlier output did not look like the GSEs';
* **exhibits** sit in a bordered box with a bold caption inside its top-left.

Pagination is computed, not guessed: the content is laid out once in the
browser, every block's real height is read back, and breaks are placed where
the content actually runs out of page.  The same HTML drives the on-screen
preview and the delivered PDF, so what is signed off is what ships.
"""
from __future__ import annotations

import base64
import html as _html
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from lxml import etree

from .. import bind
from . import comparables, fonts, page, typography

SPEC = Path(__file__).resolve().parents[2] / "spec"

# Wingdings 2 draws the form's tick boxes.  Redrawing them as SVG keeps the
# output free of a font that is neither licensed for embedding here nor
# present on every machine, and keeps the box crisp at any scale.
BOX_EMPTY = ("<svg class='ck' viewBox='0 0 12 12'><rect x='0.9' y='0.9' "
             "width='10.2' height='10.2' fill='none' stroke='currentColor' "
             "stroke-width='1'/></svg>")
BOX_TICKED = ("<svg class='ck' viewBox='0 0 12 12'><rect x='0.9' y='0.9' "
              "width='10.2' height='10.2' fill='none' stroke='currentColor' "
              "stroke-width='1'/><path d='M2.7 6.3 L4.9 8.7 L9.3 3.3' "
              "fill='none' stroke='currentColor' stroke-width='1.5' "
              "stroke-linecap='round' stroke-linejoin='round'/></svg>")

# Which grid each section prints, from the B-1 supplement's three sheets.
GRID_SECTIONS = {22: "sales", 23: "rental", 24: "grm"}

# A field whose label reads as a narrative rather than a label/value pair.
PROSE_HINT = ("Commentary", "Comment", "Description", "Analysis", "Statement",
              "Explanation", "Narrative")


def esc(text: Any) -> str:
    return _html.escape(str(text if text is not None else ""), quote=True)


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------
@dataclass
class Row:
    label: str = ""
    value: str = ""
    column: int = 0
    indent: int = 0
    kind: str = "field"          # field | yesno
    field_id: str = ""
    checked: bool | None = None
    findings: list[dict] = field(default_factory=list)

    def html(self) -> str:
        pad = self.indent * page.INDENT_STEP
        attrs = f" data-fid='{esc(self.field_id)}'" if self.field_id else ""
        flag = ""
        if self.findings:
            worst = ("fatal" if any(f.get("severity") == "Fatal"
                                    for f in self.findings) else "warning")
            flag = f" data-flag='{worst}'"
        style = f" style='padding-left:{pad + page.LABEL_INSET}pt'" if pad else ""

        if self.kind == "yesno":
            yes = BOX_TICKED if self.checked else BOX_EMPTY
            no = BOX_EMPTY if self.checked else BOX_TICKED
            cell = (f"<span class='yn'><b>Yes</b>{yes}"
                    f"<b class='no'>No</b>{no}</span>")
        else:
            cell = esc(self.value)
        return (f"<div class='r'{style}{attrs}{flag}>"
                f"<span class='lbl'>{esc(self.label)}</span>"
                f"<span class='val'>{cell}</span></div>")


@dataclass
class Exhibit:
    caption: str = ""
    source: str = ""             # a file path, or a data URI
    width: float = page.MEASURE / 2 - 6

    def html(self) -> str:
        img = (f"<img src='{esc(self.source)}' alt='{esc(self.caption)}'>"
               if self.source else
               "<div class='missing'>This image is not in the case folder.</div>")
        return (f"<figure class='exhibit' style='width:{self.width:.1f}pt'>"
                f"<figcaption>{esc(self.caption)}</figcaption>{img}</figure>")


@dataclass
class Table:
    """A repeating component, set as a table rather than as repeated rows.

    Where a block repeats -- Foundation, Roof and Windows each with a detail, a
    quality comment and a condition -- the GSEs print one table with the
    attributes as column heads and one line per component.  Printing it as
    label/value rows instead alternates two subsection bars down the page and
    hides which value belongs to which component.
    """
    columns: list[str] = field(default_factory=list)
    body: list[list[str]] = field(default_factory=list)
    field_ids: list[list[str]] = field(default_factory=list)

    def html(self) -> str:
        head = "".join(f"<th>{esc(c)}</th>" for c in self.columns)
        rows = []
        for line, ids in zip(self.body, self.field_ids or [[]] * len(self.body)):
            cells = []
            for i, cell in enumerate(line):
                fid = ids[i] if i < len(ids) else ""
                attr = f" data-fid='{esc(fid)}'" if fid else ""
                cls = " class='lead'" if i == 0 else ""
                cells.append(f"<td{cls}{attr}>{esc(cell)}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return (f"<table class='tbl'><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>")


@dataclass
class Block:
    """One thing that occupies vertical space on the page."""
    kind: str                    # tab | bar | rows | prose | exhibits | grid | table
    title: str = ""
    rows: list[Row] = field(default_factory=list)
    table: Table | None = None
    text: str = ""
    exhibits: list[Exhibit] = field(default_factory=list)
    grid: Any = None
    section: int = 0
    continued: bool = False

    def html(self) -> str:
        if self.kind == "tab":
            cont = ("<span class='cont'>(continued)</span>"
                    if self.continued else "")
            return (f"<div class='tabwrap'><span class='tab'>"
                    f"{esc(self.title)}{cont}</span></div>")
        if self.kind == "bar":
            return f"<div class='bar'>{esc(self.title)}</div>"
        if self.kind == "prose":
            head = f"<div class='pl'>{esc(self.title)}</div>" if self.title else ""
            return f"<div class='prose'>{head}{esc(self.text)}</div>"
        if self.kind == "table" and self.table is not None:
            return self.table.html()
        if self.kind == "exhibits":
            return ("<div class='exhibits'>"
                    + "".join(e.html() for e in self.exhibits) + "</div>")
        if self.kind == "grid" and self.grid is not None:
            return comparables.html(self.grid)
        left = "".join(r.html() for r in self.rows if r.column == 0)
        right = "".join(r.html() for r in self.rows if r.column == 1)
        return (f"<div class='cols'><div class='col left'>{left}</div>"
                f"<div class='col right'>{right}</div></div>")


@dataclass
class Section:
    number: int
    name: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def tab(self) -> str:
        return bind.TAB_NAME.get(self.number, self.name)

    @property
    def rows(self) -> list[Row]:
        return [r for b in self.blocks for r in b.rows]

    @property
    def grids(self) -> list:
        return [b.grid for b in self.blocks if b.kind == "grid" and b.grid]


# --------------------------------------------------------------------------
# Building a report from a case
# --------------------------------------------------------------------------
def build(tree, *, findings: Iterable | None = None, include_empty: bool = False,
          media: Iterable[dict] | None = None) -> list[Section]:
    """Turn a case document into the blocks the page draws."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    model = bind.page_model()

    flagged: dict[str, list[dict]] = {}
    for f in findings or ():
        fid = (getattr(f, "field_id", None)
               or (f.get("field_id") if isinstance(f, dict) else ""))
        if fid:
            flagged.setdefault(fid, []).append(
                f.to_json() if hasattr(f, "to_json") else dict(f))

    by_section = _media_by_section(media or ())

    out: list[Section] = []
    for number, name in bind.SECTIONS:
        fields = model.get(number, [])
        section = Section(number=number, name=name)
        current: Block | None = None
        subsection = None
        # A-1 interleaves the fields of a repeating component -- Foundation's
        # condition, then its quality, then the Roof's -- so a naive "the
        # subsection changed" test opens a new bar on nearly every row.  A bar
        # is drawn the first time its subsection appears in the section.
        barred: set[str] = set()
        pending: list = []
        pending_group = ""

        def flush() -> None:
            """Emit the repeating block that has just ended, in its place."""
            nonlocal pending, pending_group, current
            if pending:
                section.blocks.extend(_grouped(pending_group, pending, number))
                current = None
            pending, pending_group = [], ""

        for pf in fields:
            groups = bind.read_groups(root, pf.binding, ordinal=pf.ordinal)
            parts = [p for g in groups for p in g]
            values = [v for _n, v in parts]
            text = bind.display_value(groups, pf.binding)
            if not text and not include_empty:
                continue

            clean = _subsection_title(pf.subsection)
            if clean != subsection:
                flush()
                subsection = clean
                current = None
                if subsection and subsection not in barred:
                    barred.add(subsection)
                    section.blocks.append(
                        Block("bar", title=subsection, section=number))

            label = _resolve_label(pf.label, parts, pf.binding)

            # A narrative runs the full measure under its own label, as the
            # samples set commentary.  Squeezing it into a 119 pt value column
            # is what made earlier pages run several times too long.
            if text and _is_prose(pf.label, pf.binding):
                section.blocks.append(
                    Block("prose", title=label, text=text, section=number))
                current = None
                continue

            # A repeating component is gathered up and set as a table once the
            # whole section has been walked.
            if pf.group != pending_group:
                flush()
            if pf.group:
                pending_group = pf.group
                pending.append((pf, label, text))
                current = None
                continue

            if current is None or current.kind != "rows":
                current = Block("rows", section=number)
                section.blocks.append(current)

            row = Row(label=label, value=text, column=pf.column,
                      indent=pf.indent, field_id=pf.field_id,
                      findings=flagged.get(pf.field_id, []))
            if _is_boolean(pf.binding):
                row.kind = "yesno"
                row.checked = bool(values) and values[0].strip().lower() == "true"
                row.value = ""
            else:
                ticked = _label_is_option(pf.label, values, pf.binding)
                if ticked is not None:
                    row.kind = "yesno"
                    row.checked = ticked
                    row.value = ""
            current.rows.append(row)

        flush()

        # The comparable grids belong to their section but ignore its columns.
        if number in GRID_SECTIONS:
            for grid in comparables.build(tree, GRID_SECTIONS[number]):
                section.blocks.append(Block("grid", grid=grid, section=number))

        # Exhibits close a section, under their own bar, as the samples show.
        shots = by_section.get(number, [])
        if shots:
            section.blocks.append(
                Block("bar", title=f"{name} Exhibits", section=number))
            section.blocks.append(
                Block("exhibits", exhibits=shots, section=number))

        if section.blocks:
            out.append(section)
    return out


NO_SUBSECTION = ("{No Subsection}", "(No Subsection)")


def _subsection_title(raw: str) -> str:
    """A subsection's printed name.

    A-1 writes "{No Subsection}" where a field sits directly under its section,
    and a few rows carry it as a prefix on a real name.  Neither belongs on the
    page.
    """
    text = " ".join(str(raw or "").split())
    for marker in NO_SUBSECTION:
        if text == marker:
            return ""
        if text.startswith(marker):
            text = text[len(marker):].lstrip(" -–")
    return text


def _grouped(group: str, entries: list, number: int) -> list[Block]:
    """Turn one repeating component into a table, or into plain rows.

    A group with a single instance is not a table -- it is one row of values,
    and a header above a single line reads as noise.
    """
    order: list[str] = []
    by_ordinal: dict[int, dict[str, str]] = {}
    ids: dict[int, dict[str, str]] = {}
    cols: dict[int, dict[str, int]] = {}
    inds: dict[int, dict[str, int]] = {}
    for pf, label, text in entries:
        if label not in order:
            order.append(label)
        by_ordinal.setdefault(pf.ordinal, {})[label] = text
        ids.setdefault(pf.ordinal, {})[label] = pf.field_id
        cols.setdefault(pf.ordinal, {})[label] = pf.column
        inds.setdefault(pf.ordinal, {})[label] = pf.indent

    filled = [n for n in sorted(by_ordinal)
              if any(v for v in by_ordinal[n].values())]
    if not filled:
        return []

    # A table only makes sense when each repeat answers the *same* questions.
    # Some groups repeat a container while giving each instance its own label --
    # "Client/Lender" then "Client/AMC" -- and those are rows about different
    # things, not a table with two columns.
    sets = [frozenset(k for k, v in by_ordinal[n].items() if v) for n in filled]
    shared = set.intersection(*(set(s) for s in sets)) if sets else set()
    widest = max((len(s) for s in sets), default=0)
    consistent = widest and len(shared) / widest >= 0.6

    name = group.split("|")[-1].replace("_", " ").title()
    if len(filled) < 2 or len(order) < 2 or not consistent:
        rows = []
        for n in filled:
            for label in order:
                value = by_ordinal[n].get(label, "")
                if value:
                    rows.append(Row(label=label, value=value,
                                    column=cols[n].get(label, 0),
                                    indent=inds[n].get(label, 0),
                                    field_id=ids[n].get(label, "")))
        return [Block("rows", rows=rows, section=number)] if rows else []

    table = Table(columns=order)
    for n in filled:
        table.body.append([by_ordinal[n].get(label, "") for label in order])
        table.field_ids.append([ids[n].get(label, "") for label in order])
    return [Block("bar", title=name, section=number),
            Block("table", table=table, section=number)]


def _media_by_section(media: Iterable[dict]) -> dict[int, list[Exhibit]]:
    """Group the case's images by the section each belongs to."""
    out: dict[int, list[Exhibit]] = {}
    for item in media:
        number = int(item.get("section") or 0)
        if not number:
            continue
        source = item.get("source") or _inline(item.get("path"))
        width = float(item.get("width") or (page.MEASURE / 2 - 6))
        caption = item.get("caption") or Path(str(item.get("path", ""))).stem
        out.setdefault(number, []).append(
            Exhibit(caption=caption, source=source, width=width))
    return out


def _inline(path: Any) -> str:
    """Embed an image so the PDF renderer needs no file access."""
    if not path:
        return ""
    p = Path(str(path))
    if not p.is_file():
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _is_prose(label: str, binding: bind.Binding) -> bool:
    if any(word in label for word in PROSE_HINT):
        return True
    for dp in binding.data_points:
        details = str(dp.get("format_details") or "").strip()
        if details.isdigit() and int(details) >= 200:
            return True
    return False


def _label_is_option(label: str, values: list[str],
                     binding: bind.Binding) -> bool | None:
    """Is this label one of the field's own enumerated values?

    Three consecutive fields -- Condominium, Cooperative, Condop -- share one
    data point and each asks whether the property is that kind.  Printing the
    value under all three would report a condop as a condominium as well.
    """
    options: set[str] = set()
    for dp in binding.data_points:
        for opt in dp.get("enumerations") or []:
            if opt.get("value"):
                options.add(opt["value"].casefold())
            if opt.get("display"):
                options.add(opt["display"].casefold())
    flat = label.strip().casefold()
    if flat not in options or len(options) < 2:
        return None
    return any(v.strip().casefold() == flat for v in values)


def _resolve_label(label: str, parts: list[tuple[str, str]],
                   binding: bind.Binding) -> str:
    """Fill a placeholder label -- "Client/[Party Role Type]" -- from the case."""
    if "[" not in label:
        return label

    def fill(match) -> str:
        wanted = match.group(0)[1:-1].replace(" ", "").casefold()
        for name, value in parts:
            if name.casefold() in (wanted, wanted + "type"):
                return bind.display_value([(name, value)], binding) or value
        return match.group(0)

    return bind.PLACEHOLDER.sub(fill, label)


def _is_boolean(binding: bind.Binding) -> bool:
    """Does this field print as a Yes/No pair rather than as text?"""
    kinds = [str(dp.get("format_type", "")).strip().casefold()
             for dp in binding.data_points if dp.get("mismo")]
    return bool(kinds) and all(k == "boolean" for k in kinds)


# --------------------------------------------------------------------------
# Style
# --------------------------------------------------------------------------
def stylesheet(*, embed_fonts: bool = True, screen: bool = False) -> str:
    g = page
    t = typography
    rule = f"{page.RULE['width']}pt solid {page.RULE['colour']}"
    ink_rule = f"{page.RULE_INK['width']}pt solid {page.RULE_INK['colour']}"
    return "\n".join([
        t.stylesheet(embed_fonts=embed_fonts),
        f"""
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;background:{t.PAPER}}}
body{{font-family:'{fonts.FAMILY}',{fonts.FALLBACK};color:{t.INK};
      -webkit-font-smoothing:antialiased}}
@page{{size:{g.PAGE_W}pt {g.PAGE_H}pt;margin:0}}

.page{{position:relative;width:{g.PAGE_W}pt;height:{g.PAGE_H}pt;
       overflow:hidden;background:{t.PAPER};
       break-after:page;page-break-after:always}}
.page:last-child{{break-after:auto;page-break-after:auto}}

.hdr-l{{position:absolute;left:{g.MARGIN_X}pt;top:{g.HEADER['left_text_top']}pt;
        {t.ROLES['HDR-L'].css}}}
.hdr-r{{position:absolute;right:{g.MARGIN_X}pt;top:{g.HEADER['right_text_top']}pt;
        {t.ROLES['HDR-R'].css}}}

.ftr div{{position:absolute}}
.ftr .line{{left:{g.MARGIN_X}pt;top:{g.FOOTER['band_top']}pt;
            width:{g.MEASURE}pt;height:0;border-top:{rule}}}
.ftr .f1{{left:{g.MARGIN_X}pt;top:{g.FOOTER['left_lines'][0]['y']}pt;
          {t.ROLES['FTR-L'].css}}}
.ftr .f2{{left:{g.MARGIN_X}pt;top:{g.FOOTER['left_lines'][1]['y']}pt;
          {t.ROLES['FTR-META'].css}}}
.ftr .f3{{left:{g.MARGIN_X}pt;top:{g.FOOTER['left_lines'][2]['y']}pt;
          {t.ROLES['FTR-META'].css}}}
.ftr .ref{{right:{g.MARGIN_X}pt;text-align:right;white-space:nowrap}}
.ftr .ref b{{{t.ROLES['FTR-R'].css}}}
.ftr .ref span{{{t.ROLES['FTR-V'].css};display:inline-block;
                min-width:56pt;text-align:left;margin-left:10pt}}

.band{{position:absolute;left:{g.MARGIN_X}pt;top:{g.BODY_TOP}pt;
       width:{g.MEASURE}pt}}
.band.summary{{top:{g.BODY_TOP_SUMMARY}pt}}

.title{{{t.ROLES['TITLE'].css};line-height:1.05;margin-bottom:6pt}}
.title-add{{{t.ROLES['TITLE-ADD'].css};margin-bottom:26pt}}
.sum-hd{{{t.ROLES['SUM-HD'].css};margin:0 0 10pt 4pt}}

/* section tab: a grey rule above it, the black tab, an ink rule at its foot */
.tabwrap{{border-top:{rule};border-bottom:{ink_rule};
          margin:13.6pt 0 11.3pt;line-height:0}}
.tabwrap:first-child{{margin-top:0}}
.tab{{display:inline-block;background:{page.TAB['fill']};
      color:{page.TAB['colour']};height:{page.TAB['height']}pt;
      line-height:{page.TAB['height']}pt;
      padding:0 {page.TAB['pad_right']}pt 0 6pt;{t.ROLES['TAB'].css};
      border-radius:0 {page.TAB['radius']}pt {page.TAB['radius']}pt 0}}
.tab .cont{{{t.ROLES['TAB-C'].css};margin-left:3pt}}

/* subsection bar: a 15 pt band across the full measure */
.bar{{width:{g.MEASURE}pt;height:{page.BAR['height']}pt;
      line-height:{page.BAR['height']}pt;background:{page.BAR['fill']};
      padding-left:{page.BAR['text_inset']}pt;
      {t.ROLES['H1'].css};margin:7.4pt 0 5pt}}
.bar:first-child{{margin-top:0}}

.cols{{display:flex;gap:{g.GUTTER}pt;align-items:flex-start}}
.col{{width:{g.COL_W}pt}}

/* every field row is ruled beneath, across its whole column */
.r{{display:flex;min-height:{g.ROW_PITCH}pt;line-height:{g.ROW_PITCH}pt;
    padding-left:{g.LABEL_INSET}pt;border-bottom:{rule}}}
.r .lbl{{width:{g.VALUE_INSET - g.LABEL_INSET}pt;flex:none;
         {t.ROLES['LABEL'].css}}}
.r .val{{width:{g.COL_W - g.VALUE_INSET}pt;{t.ROLES['VALUE'].css}}}
.ck{{width:{g.ROW_PITCH - 3}pt;height:{g.ROW_PITCH - 3}pt;vertical-align:-1.5pt}}
.yn{{display:inline-flex;align-items:center;gap:3pt;white-space:nowrap}}
.yn b{{{t.ROLES['LABEL'].css};font-size:8pt}}
.yn b.no{{margin-left:8pt}}

/* a narrative runs the full measure under its own label */
.prose{{width:{g.MEASURE}pt;margin:2pt 0 6pt;padding-left:{g.LABEL_INSET}pt;
        {t.ROLES['TXR'].css};border-bottom:{rule}}}
.prose .pl{{{t.ROLES['LABEL'].css};margin-bottom:1pt}}

/* exhibits: a bordered box with the caption inside its top-left */
.exhibits{{display:flex;flex-wrap:wrap;gap:8pt;margin:4pt 0 6pt}}
.exhibit{{margin:0;border:{rule};padding:5pt}}
.exhibit figcaption{{{t.ROLES['LABEL'].css};margin-bottom:4pt}}
.exhibit img{{display:block;width:100%;height:auto;max-height:300pt;
              object-fit:contain}}
.exhibit .missing{{{t.ROLES['CAPTION'].css};background:{page.BAR['fill']};
                   padding:28pt 8pt;text-align:center}}

/* a repeating component, set as a table with the attributes as column heads */
table.tbl{{border-collapse:collapse;width:{g.MEASURE}pt;table-layout:auto;
           margin:2pt 0 7pt}}
table.tbl th{{{t.ROLES['LABEL'].css};font-size:8pt;text-align:left;
              padding:1pt {page.GRID['cell_inset']}pt;
              border-bottom:{ink_rule};vertical-align:bottom}}
table.tbl td{{{t.ROLES['VALUE'].css};font-size:8pt;
              padding:1pt {page.GRID['cell_inset']}pt;
              border-bottom:{rule};border-right:{rule};
              vertical-align:top;overflow-wrap:anywhere}}
table.tbl td:last-child{{border-right:0}}
table.tbl td.lead{{{t.ROLES['LABEL'].css};font-size:8pt}}

/* the comparable grid runs the full measure and ignores the body columns */
table.grid{{border-collapse:collapse;width:{g.MEASURE}pt;table-layout:fixed;
            margin:3pt 0 6pt}}
table.grid td,table.grid th{{{t.ROLES['GRID'].css};
    min-height:{g.ROW_PITCH}pt;line-height:{g.ROW_PITCH}pt;
    padding:0 {page.GRID['cell_inset']}pt;border-bottom:{rule};
    overflow-wrap:anywhere;vertical-align:top}}
table.grid th{{{t.ROLES['GRID-B'].css};text-align:center;
               border-bottom:{ink_rule}}}
table.grid td.lbl{{{t.ROLES['GRID-B'].css};text-align:left}}
table.grid td.v{{text-align:right}}
table.grid tr.sub td{{background:{page.GRID['subhead_fill']};
    color:{page.GRID['subhead_colour']};{t.ROLES['GRID-HD'].css};
    text-align:left}}
""",
        _screen_css() if screen else "",
    ])


def _screen_css() -> str:
    return """
body{background:#6f6f6f;padding:16pt}
.page{margin:0 auto 16pt;box-shadow:0 2pt 12pt rgba(0,0,0,.4)}
[data-flag=fatal] .lbl{box-shadow:inset 2.5pt 0 0 #c0392b}
[data-flag=warning] .lbl{box-shadow:inset 2.5pt 0 0 #b8860b}
"""


# --------------------------------------------------------------------------
# Page furniture
# --------------------------------------------------------------------------
@dataclass
class Meta:
    title: str = page.HEADER["title"]
    version: str = "Appraisal Version #1"
    issuer: str = "Fannie Mae | Freddie Mac"
    form_date: str = "September 2024"
    references: list[tuple[str, str]] = field(default_factory=list)

    @classmethod
    def from_case(cls, tree) -> "Meta":
        root = tree.getroot() if hasattr(tree, "getroot") else tree
        m = f"{{{bind.MISMO}}}"

        def one(name: str) -> str:
            node = root.find(f".//{m}{name}")
            return (node.text or "").strip() if node is not None else ""

        version = one("AboutVersionIdentifier")
        refs = []
        for spec in page.FOOTER_IDS:
            value = _reference(root, spec["field"])
            if value:
                refs.append((spec["label"], value))
        return cls(
            version=(f"Appraisal Version #{version}" if version
                     else "Appraisal Version #1"),
            form_date=(one("DocumentFormIssuingEntityVersionIdentifier")
                       or "September 2024"),
            references=refs)


# Three of the four footer reference IDs share ADDITIONAL_IDENTIFIER and are
# told apart by the type beside them (A-1 unique IDs 2100.0004/0006/0008).
REFERENCE_TYPES = {
    "HF.006": "GovernmentAgency",      # Agency Case File ID -- FHA or VA only
    "HF.007": "Client",
    "HF.008": "ManagementCompany",
}
APPRAISER_FILE = "AppraiserFileIdentifier"      # HF.005, always shown


def _reference(root: etree._Element, field_code: str) -> str:
    m = f"{{{bind.MISMO}}}"
    if field_code == "HF.005":
        node = root.find(f".//{m}{APPRAISER_FILE}")
        return (node.text or "").strip() if node is not None else ""
    want = REFERENCE_TYPES.get(field_code)
    if not want:
        return ""
    for node in root.iter(f"{m}ADDITIONAL_IDENTIFIER"):
        kind = node.find(f"{m}AdditionalValuationIdentifierType")
        value = node.find(f"{m}AdditionalValuationIdentifier")
        if (kind is not None and value is not None
                and (kind.text or "").strip() == want):
            return (value.text or "").strip()
    return ""


def _footer(meta: Meta) -> str:
    y = page.FOOTER["right_first_y"]
    refs = []
    for label, value in meta.references:
        refs.append(f"<div class='ref' style='top:{y}pt'>"
                    f"<b>{esc(label)}</b><span>{esc(value)}</span></div>")
        y += page.FOOTER["right_pitch"]
    return ("<div class='ftr'><div class='line'></div>"
            f"<div class='f1'>{esc(meta.version)}</div>"
            f"<div class='f2'>{esc(meta.issuer)}</div>"
            f"<div class='f3'>{esc(meta.form_date)}</div>"
            + "".join(refs) + "</div>")


def _header(meta: Meta, number: int, total: int) -> str:
    return (f"<div class='hdr-l'>{esc(meta.title)}</div>"
            f"<div class='hdr-r'>Page {number} of {total}</div>")


def summary_lead(tree) -> str:
    """The Summary page's two display lines, which carry no running header."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    m = f"{{{bind.MISMO}}}"
    address = ""
    for prop in root.iter(f"{m}PROPERTY"):
        if prop.get("ValuationUseType") != "SubjectProperty":
            continue
        node = prop.find(f".//{m}ADDRESS")
        if node is None:
            break
        street = node.findtext(f"{m}AddressLineText", "").strip()
        city = node.findtext(f"{m}CityName", "").strip()
        state = node.findtext(f"{m}StateCode", "").strip()
        post = node.findtext(f"{m}PostalCode", "").strip()
        rest = ", ".join(b for b in (city, state) if b)
        address = ", ".join(b for b in (street, rest) if b)
        if post:
            address = f"{address} {post}"
        break
    return (f"<div class='title'>{esc(page.HEADER['title'])}</div>"
            f"<div class='title-add'>{esc(address.upper())}</div>"
            f"<div class='sum-hd'>SUMMARY</div>")


# --------------------------------------------------------------------------
# The galley, before it is split into pages
# --------------------------------------------------------------------------
def galley(sections: list[Section], lead: str = "") -> str:
    parts: list[str] = []
    for section in sections:
        if section.number == 1:
            parts.append(f"<div class='blk lead'>{lead}</div>")
        else:
            parts.append(
                f"<div class='blk tabblk' data-section='{section.number}'>"
                f"{Block('tab', title=section.tab).html()}</div>")
        for block in section.blocks:
            kind = {"rows": "rows", "grid": "grid"}.get(block.kind, "solid")
            parts.append(f"<div class='blk {kind}' "
                         f"data-section='{section.number}'>{block.html()}</div>")
    return "".join(parts)


def document(sections: list[Section], meta: Meta, *, screen: bool = False,
             embed_fonts: bool = True, lead: str = "") -> str:
    """The unpaginated document, at the page's width, ready to be measured.

    The galley must not be a page: a page is 1008 pt tall and clips what
    overflows, so every block past the first would measure as zero.
    """
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Uniform Residential Appraisal Report</title>
<style>{stylesheet(embed_fonts=embed_fonts, screen=screen)}
#galley{{position:relative;width:{page.PAGE_W}pt;background:{typography.PAPER}}}
#galley .band{{position:static;margin-left:{page.MARGIN_X}pt;
               width:{page.MEASURE}pt}}</style>
</head><body>
<div id="galley"><div class="band">{galley(sections, lead)}</div></div>
</body></html>"""
