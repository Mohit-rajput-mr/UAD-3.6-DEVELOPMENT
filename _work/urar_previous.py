"""Draw the URAR.

The page is reproduced from measurement, not from a redesign: 612 x 1008 pt,
a 45-pica measure, two 22-pica columns with a 1-pica gutter, a 13 pt row, a
14.8 pt section tab and a 13 pt subsection bar -- every one of those numbers
taken off the official samples by ``uad.spec.measure_geometry``.  Type comes
from ``report.typography``, which was measured the same way, and is set in the
Myriad Pro faces licensed with this machine's Adobe install.

Pagination is computed, not guessed.  The content is laid out once in the
browser, every row's real height is read back -- including rows whose text
wrapped -- and the page breaks are then placed where the content actually runs
out of page.  So the page count follows from the case: a 2-4 unit property with
four units and five comparables simply produces more pages, and a repeated
section picks up its "(continued)" tab automatically.

The same HTML is used for the on-screen preview and for the delivered PDF, so
what the appraiser signs off is what ships.
"""
from __future__ import annotations

import html as _html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from lxml import etree

from .. import bind
from . import comparables, fonts, page, typography

SPEC = Path(__file__).resolve().parents[2] / "spec"

# Wingdings 2 draws the form's checkboxes.  Redrawing them as SVG keeps the
# output free of a font that is neither licensed for embedding here nor
# present on every machine, and makes the box crisp at any scale.
BOX_EMPTY = ("<svg class='ck' viewBox='0 0 12 12'><rect x='0.75' y='0.75' "
             "width='10.5' height='10.5' fill='none' stroke='currentColor' "
             "stroke-width='1'/></svg>")
BOX_TICKED = ("<svg class='ck' viewBox='0 0 12 12'><rect x='0.75' y='0.75' "
              "width='10.5' height='10.5' fill='none' stroke='currentColor' "
              "stroke-width='1'/><path d='M2.6 6.2 L4.9 8.8 L9.4 3.1' "
              "fill='none' stroke='currentColor' stroke-width='1.6' "
              "stroke-linecap='round' stroke-linejoin='round'/></svg>")


def esc(text: Any) -> str:
    return _html.escape(str(text if text is not None else ""), quote=True)


# --------------------------------------------------------------------------
# Content model
# --------------------------------------------------------------------------
@dataclass
class Row:
    label: str = ""
    value: str = ""
    column: int = 0
    indent: int = 0
    kind: str = "field"          # field | heading | note | checkbox | prose
    field_id: str = ""
    checked: bool | None = None
    findings: list[dict] = field(default_factory=list)

    def html(self) -> str:
        pad = self.indent * page.INDENT_STEP
        attrs = (f" data-fid='{esc(self.field_id)}'" if self.field_id else "")
        flag = ""
        if self.findings:
            worst = "fatal" if any(f.get("severity") == "Fatal"
                                   for f in self.findings) else "warning"
            flag = f" data-flag='{worst}'"
        if self.kind == "heading":
            return (f"<div class='r h2' style='padding-left:{pad}pt'{attrs}{flag}>"
                    f"{esc(self.label)}</div>")
        if self.kind == "prose":
            return (f"<div class='r prose' style='padding-left:{pad}pt'{attrs}{flag}>"
                    f"{esc(self.value)}</div>")
        if self.kind == "checkbox":
            box = BOX_TICKED if self.checked else BOX_EMPTY
            return (f"<div class='r ck-row' style='padding-left:{pad}pt'{attrs}{flag}>"
                    f"<span class='lbl'>{esc(self.label)}</span>"
                    f"<span class='val'>{box}</span></div>")
        return (f"<div class='r' style='padding-left:{pad}pt'{attrs}{flag}>"
                f"<span class='lbl'>{esc(self.label)}</span>"
                f"<span class='val'>{esc(self.value)}</span></div>")


@dataclass
class Section:
    number: int
    name: str
    instance: str = ""
    rows: list[Row] = field(default_factory=list)
    grids: list = field(default_factory=list)
    photos: list[dict] = field(default_factory=list)

    @property
    def tab(self) -> str:
        base = bind.TAB_NAME.get(self.number, self.name)
        return f"{base} - {self.instance}" if self.instance else base


# --------------------------------------------------------------------------
# Building sections from a case
# --------------------------------------------------------------------------
def build(tree, *, findings: Iterable | None = None,
          include_empty: bool = False) -> list[Section]:
    """Turn a case document into the sections the page shows.

    A field is drawn when the case carries a value for it.  ``include_empty``
    draws the whole form instead, which is what the editor wants: an appraiser
    needs to see the field before there is anything in it.
    """
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    model = bind.page_model()
    flagged: dict[str, list[dict]] = {}
    for f in findings or ():
        fid = getattr(f, "field_id", None) or (f.get("field_id") if isinstance(f, dict) else "")
        if fid:
            entry = f.to_json() if hasattr(f, "to_json") else dict(f)
            flagged.setdefault(fid, []).append(entry)

    sections: list[Section] = []
    for number, name in bind.SECTIONS:
        fields = model.get(number, [])
        if not fields:
            continue
        section = Section(number=number, name=name)
        last_subsection = None
        for pf in fields:
            groups = bind.read_groups(root, pf.binding, ordinal=pf.ordinal)
            parts = [p for g in groups for p in g]
            values = [v for _n, v in parts]
            text = bind.display_value(groups, pf.binding)
            if not text and not include_empty:
                continue
            if pf.subsection and pf.subsection != last_subsection:
                section.rows.append(Row(label=pf.subsection, kind="heading",
                                        column=pf.column))
                last_subsection = pf.subsection
            label = _resolve_label(pf.label, parts, pf.binding)
            row = Row(label=label, value=text, column=pf.column,
                      indent=pf.indent, field_id=pf.field_id,
                      findings=flagged.get(pf.field_id, []))
            if _is_boolean(pf.binding) and values:
                row.kind = "checkbox"
                row.checked = values[0].strip().lower() == "true"
                row.value = ""
            else:
                ticked = _label_is_option(pf.label, values, pf.binding)
                if ticked is not None:
                    row.kind = "checkbox"
                    row.checked = ticked
                    row.value = ""
            section.rows.append(row)
        # The comparable grids belong to their section but ignore its two-column
        # layout, so they hang off the section rather than sitting in its rows.
        section.grids = comparables.build(tree, GRID_SECTIONS[number]) \
            if number in GRID_SECTIONS else []
        if section.rows or section.grids:
            sections.append(section)
    return sections


# Which grid each section prints, from the B-1 supplement's three sheets.
GRID_SECTIONS = {22: "sales", 23: "rental", 24: "grm"}


def _label_is_option(label: str, values: list[str],
                     binding: bind.Binding) -> bool | None:
    """Is this label one of the field's own enumerated values?

    Three consecutive fields -- Condominium, Cooperative, Condop -- share one
    data point, ``ProjectLegalStructureType``, and each asks whether the
    property is that kind.  Printing the value under all three would report a
    condop as a condominium as well; each is a tick box, ticked only on the row
    whose label the value names.  Returns None when the label is not one of the
    field's options, meaning the field prints its value as usual.
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
    """Fill a placeholder label from the case.

    A-1 writes "Client/[Party Role Type]" because the second half is whatever
    role the client holds -- Lender, Attorney, Investor.  The page prints the
    resolved label, so the placeholder is replaced with the value that named it.
    """
    if "[" not in label:
        return label

    def _fill(match) -> str:
        wanted = match.group(0)[1:-1].replace(" ", "").casefold()
        for name, value in parts:
            if name.casefold() == wanted or name.casefold() == wanted + "type":
                for dp in binding.data_points:
                    if dp.get("mismo") == name:
                        return bind.display_value([(name, value)], binding) or value
                return value
        return match.group(0)

    return bind.PLACEHOLDER.sub(_fill, label)


def _is_boolean(binding: bind.Binding) -> bool:
    """Does this field print as a tick box rather than as text?

    A field is a box only when every data point behind it is a yes/no.  Several
    fields pair an indicator with an enumeration -- Listing Status carries both
    ``ListedWithinPreviousYearIndicator`` and ``ListingStatusType`` -- and there
    the value is the status, not a tick.
    """
    kinds = [str(dp.get("format_type", "")).strip().casefold()
             for dp in binding.data_points if dp.get("mismo")]
    if not kinds:
        return False
    return all(k == "boolean" for k in kinds)


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------
def stylesheet(*, embed_fonts: bool = True, screen: bool = False) -> str:
    g = page
    css = [
        typography.stylesheet(embed_fonts=embed_fonts),
        f"""
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;background:{typography.PAPER}}}
body{{font-family:'{fonts.FAMILY}',{fonts.FALLBACK};
      color:{typography.INK};-webkit-font-smoothing:antialiased}}
@page{{size:{g.PAGE_W}pt {g.PAGE_H}pt;margin:0}}

.page{{position:relative;width:{g.PAGE_W}pt;height:{g.PAGE_H}pt;
       overflow:hidden;background:{typography.PAPER};
       break-after:page;page-break-after:always}}
.page:last-child{{break-after:auto;page-break-after:auto}}

/* running header -- absent on the Summary, per Appendix E-1 */
.hdr-l{{position:absolute;left:{g.MARGIN_X}pt;top:{g.HEADER['left_text_top']}pt;
        {typography.ROLES['HDR-L'].css}}}
.hdr-r{{position:absolute;right:{g.MARGIN_X}pt;top:{g.HEADER['right_text_top']}pt;
        {typography.ROLES['HDR-R'].css}}}

/* running footer */
.ftr div{{position:absolute}}
.ftr .f1{{left:{g.MARGIN_X}pt;top:{g.FOOTER['left_lines'][0]['y']}pt;
          {typography.ROLES['FTR-L'].css}}}
.ftr .f2{{left:{g.MARGIN_X}pt;top:{g.FOOTER['left_lines'][1]['y']}pt;
          {typography.ROLES['FTR-META'].css}}}
.ftr .f3{{left:{g.MARGIN_X}pt;top:{g.FOOTER['left_lines'][2]['y']}pt;
          {typography.ROLES['FTR-META'].css}}}
.ftr .ref{{right:{g.MARGIN_X}pt;text-align:right;white-space:nowrap}}
.ftr .ref b{{{typography.ROLES['FTR-R'].css}}}
.ftr .ref span{{{typography.ROLES['FTR-V'].css};display:inline-block;
                min-width:56pt;text-align:left;margin-left:10pt}}

.band{{position:absolute;left:{g.MARGIN_X}pt;top:{g.BODY_TOP}pt;
       width:{g.MEASURE}pt}}
.band.summary{{top:{g.BODY_TOP_SUMMARY}pt}}

.title{{{typography.ROLES['TITLE'].css};line-height:1.05;margin-bottom:8pt}}
.title-add{{{typography.ROLES['TITLE-ADD'].css};margin-bottom:30pt}}
.sum-hd{{{typography.ROLES['SUM-HD'].css};margin:0 0 12pt 4pt}}

.tab{{display:inline-block;background:{page.TAB['fill']};
      color:{page.TAB['colour']};height:{page.TAB['height']}pt;
      line-height:{page.TAB['height']}pt;
      padding:0 {page.TAB['pad_right']}pt 0 6pt;
      {typography.ROLES['TAB'].css};margin-bottom:11.3pt}}
.tab .cont{{{typography.ROLES['TAB-C'].css};margin-left:2pt}}

.bar{{width:{g.MEASURE}pt;height:{page.BAR['height']}pt;
      line-height:{page.BAR['height']}pt;background:{page.BAR['fill']};
      padding-left:{page.BAR['text_inset']}pt;
      {typography.ROLES['H1'].css};margin:6pt 0 4pt}}

.cols{{display:flex;gap:{g.GUTTER}pt;align-items:flex-start}}
.col{{width:{g.COL_W}pt}}

.r{{display:flex;min-height:{g.ROW_PITCH}pt;line-height:{g.ROW_PITCH}pt;
    padding-left:{g.LABEL_INSET}pt}}
.r .lbl{{width:{g.VALUE_INSET - g.LABEL_INSET}pt;flex:none;
         {typography.ROLES['LABEL'].css}}}
.r .val{{width:{g.COL_W - g.VALUE_INSET}pt;{typography.ROLES['VALUE'].css}}}
.r.h2{{{typography.ROLES['H2'].css};min-height:{g.ROW_PITCH + 6}pt;
       margin-top:13.5pt;line-height:{g.ROW_PITCH}pt}}
/* A heading that lands first on a page keeps no space above it; the page
   break has already provided the separation, and the extra margin pushed the
   last row of the column under the footer. */
.col > :first-child{{margin-top:0}}
.r.prose{{display:block;{typography.ROLES['TXR'].css};
          width:{g.COL_W - g.LABEL_INSET}pt}}
.ck{{width:{g.ROW_PITCH - 2}pt;height:{g.ROW_PITCH - 2}pt;vertical-align:-2pt}}

/* comparable grid -- full measure, ignores the two-column body grid */
table.grid{{border-collapse:collapse;width:{g.MEASURE}pt;table-layout:fixed}}
table.grid td,table.grid th{{{typography.ROLES['GRID'].css};
    min-height:{g.ROW_PITCH}pt;line-height:{g.ROW_PITCH}pt;
    padding:0 {page.GRID['cell_inset']}pt;
    border-bottom:{page.RULE['width']}pt solid {page.RULE['colour']};
    overflow-wrap:anywhere;vertical-align:top}}
table.grid th{{{typography.ROLES['GRID-B'].css};text-align:center}}
table.grid td.lbl{{{typography.ROLES['GRID-B'].css};text-align:left}}
table.grid td.v{{text-align:right}}
table.grid tr.sub td{{background:{page.GRID['subhead_fill']};
    color:{page.GRID['subhead_colour']};{typography.ROLES['GRID-HD'].css}}}
table.grid tr.total td{{background:{typography.BLACK_35}}}

.photo{{background:{page.PHOTO_PLACEHOLDER['fill']};
        {typography.ROLES['CAPTION'].css};display:flex;
        align-items:center;justify-content:center;text-align:center;padding:6pt}}
.photo img{{max-width:100%;max-height:100%;object-fit:contain}}
""",
    ]
    if screen:
        css.append("""
body{background:#8d8d8d;padding:18pt}
.page{margin:0 auto 18pt;box-shadow:0 2pt 10pt rgba(0,0,0,.35)}
[data-flag=fatal] .lbl{box-shadow:inset 2pt 0 0 #c0392b}
[data-flag=warning] .lbl{box-shadow:inset 2pt 0 0 #d68910}
""")
    return "\n".join(css)


@dataclass
class Meta:
    """What the header and footer print."""
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
        refs: list[tuple[str, str]] = []
        for spec in page.FOOTER_IDS:
            value = _reference(root, spec["field"])
            if value:
                refs.append((spec["label"], value))
        return cls(
            version=f"Appraisal Version #{version}" if version else "Appraisal Version #1",
            form_date=one("DocumentFormIssuingEntityVersionIdentifier") or "September 2024",
            references=refs,
        )


# Three of the footer's four reference IDs share one element, ADDITIONAL_
# IDENTIFIER, and are told apart by the AdditionalValuationIdentifierType
# beside them -- the enumeration A-1 gives for each (unique IDs 2100.0004,
# 2100.0006, 2100.0008).  The appraiser's own file number is a separate
# element.  Reading whichever identifier comes first would print the AMC's
# number against the client's label.
REFERENCE_TYPES = {
    "HF.006": "GovernmentAgency",      # Agency Case File ID -- FHA or VA only
    "HF.007": "Client",                # Client Reference ID
    "HF.008": "ManagementCompany",     # AMC Reference ID
}
APPRAISER_FILE = "AppraiserFileIdentifier"   # HF.005, always shown


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
        if kind is not None and value is not None and (kind.text or "").strip() == want:
            return (value.text or "").strip()
    return ""


def _footer(meta: Meta) -> str:
    y = page.FOOTER["right_first_y"]
    refs = []
    for label, value in meta.references:
        refs.append(f"<div class='ref' style='top:{y}pt'>"
                    f"<b>{esc(label)}</b><span>{esc(value)}</span></div>")
        y += page.FOOTER["right_pitch"]
    return ("<div class='ftr'>"
            f"<div class='f1'>{esc(meta.version)}</div>"
            f"<div class='f2'>{esc(meta.issuer)}</div>"
            f"<div class='f3'>{esc(meta.form_date)}</div>"
            + "".join(refs) + "</div>")


def _header(meta: Meta, number: int, total: int) -> str:
    return (f"<div class='hdr-l'>{esc(meta.title)}</div>"
            f"<div class='hdr-r'>Page {number} of {total}</div>")


def galley(sections: list[Section], summary_lead: str = "") -> str:
    """All the content in one continuous column, before it is split into pages."""
    parts: list[str] = []
    for section in sections:
        if section.number == 1:
            parts.append(f"<div class='blk lead'>{summary_lead}</div>")
        else:
            parts.append(f"<div class='blk tabblk' data-section='{section.number}'>"
                         f"<div class='tab'>{esc(section.tab)}</div></div>")
        left = [r for r in section.rows if r.column == 0]
        right = [r for r in section.rows if r.column == 1]
        rows = ("<div class='col left'>" + "".join(r.html() for r in left) + "</div>"
                "<div class='col right'>" + "".join(r.html() for r in right) + "</div>")
        parts.append(f"<div class='blk rows' data-section='{section.number}'>"
                     f"<div class='cols'>{rows}</div></div>")
        for grid in section.grids:
            parts.append(f"<div class='blk grid' data-section='{section.number}'>"
                         f"{comparables.html(grid)}</div>")
    return "".join(parts)


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
        bits = [node.findtext(f"{m}AddressLineText", "").strip(),
                node.findtext(f"{m}CityName", "").strip(),
                node.findtext(f"{m}StateCode", "").strip(),
                node.findtext(f"{m}PostalCode", "").strip()]
        street = bits[0]
        rest = ", ".join(b for b in bits[1:3] if b)
        address = ", ".join(b for b in (street, rest) if b)
        if bits[3]:
            address = f"{address} {bits[3]}"
        break
    return (f"<div class='title'>{esc(page.HEADER['title'])}</div>"
            f"<div class='title-add'>{esc(address.upper())}</div>"
            f"<div class='sum-hd'>SUMMARY</div>")


def document(sections: list[Section], meta: Meta, *, screen: bool = False,
             embed_fonts: bool = True, lead: str = "") -> str:
    """The unpaginated document, ready to be measured.

    The galley must not be a page: a page is 1008 pt tall and clips what
    overflows, so every block past the first page would measure as zero.  It is
    the page's width and type, laid out to whatever height the content needs.
    """
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Uniform Residential Appraisal Report</title>
<style>{stylesheet(embed_fonts=embed_fonts, screen=screen)}
#galley{{position:relative;width:{page.PAGE_W}pt;background:{typography.PAPER}}}
#galley .band{{position:static;margin-left:{page.MARGIN_X}pt;
               width:{page.MEASURE}pt}}</style>
</head><body>
<div id="galley"><div class="band">
{galley(sections, lead)}
</div></div>
</body></html>"""
