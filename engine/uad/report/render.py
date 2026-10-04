"""Render the review document in URAR layout.

The markup follows Appendix C-1 (URAR Layout) and Appendix E (Report Style
Guide): a full-bleed title on the first page, section headings set as dark
tabs, banded grey sub-headings, label/value pairs ruled underneath, and the
sales comparison grid as a subject column plus a value and adjustment column
per comparable.

The same document is the browser editor and the PDF source, so what the
appraiser reviews is exactly what the client receives.  On screen the fields
are editable and a toolbar shows; in print both disappear.
"""
from __future__ import annotations

import html
from typing import Any

from .grid import ComparisonGrid
from .review import CHOICE, LONG_TEXT, READ_ONLY, Section

# Page geometry and type scale taken from the reference reports: legal paper,
# half-inch margins, roughly 7.5pt body text.
PAGE_CSS = """
:root {
  --ink: #000;
  --label: #1a1a1a;
  --value: #222;
  --band: #808080;
  --band-text: #fff;
  --subtle: #e9e9e9;
  --rule: #000;
  --hair: #bfbfbf;
  --tab: #4a4a4a;
  --field: #eef4fa;
  --flag: #8a5a00;
  --flag-bg: #fdf4e3;
  --derived: #14502f;
  --derived-bg: #eef5f0;
  --warn: #8c2b20;
  --warn-bg: #fdeeec;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: #d9dde2;
  color: var(--ink);
  font: 7.5pt/1.32 "Segoe UI", Frutiger, "Helvetica Neue", Arial, sans-serif;
}

.toolbar {
  position: sticky; top: 0; z-index: 99;
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 9px 16px; background: #11161c; color: #eef2f6;
  font-size: 11pt;
}
.toolbar h1 { font-size: 10pt; margin: 0; font-weight: 600; }
.toolbar .spacer { flex: 1; }
.toolbar button {
  font: inherit; font-size: 9pt; font-weight: 600;
  padding: 6px 13px; border-radius: 4px;
  border: 1px solid #39434e; background: #222b34; color: #eef2f6; cursor: pointer;
}
.toolbar button.primary { background: #14502f; border-color: #14502f; }
.toolbar button:disabled { opacity: .5; cursor: default; }
.status { font-size: 9pt; color: #a9b4c0; }
.status.ok { color: #7fd6a2; }
.status.bad { color: #ffab9e; }
.editors { font-size: 9pt; color: #8fa0b3; }
.whoami {
  font: inherit; font-size: 9pt; width: 8.5em;
  padding: 4px 8px; border-radius: 4px;
  border: 1px solid #39434e; background: #11161c; color: #eef2f6;
}
.whoami:focus { outline: 2px solid #2f8f5b; outline-offset: 0; }

/* A value another reviewer just changed lights briefly so it is not missed. */
@keyframes settle { from { background: #fff3c4; } to { background: var(--field); } }
[data-editable].just-changed { animation: settle 1.6s ease-out; }
@media (prefers-reduced-motion: reduce) {
  [data-editable].just-changed { animation: none; outline: 1.5pt solid #b8860b; }
}

.sheet {
  width: 8.5in; margin: 16px auto; padding: 0.5in;
  background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,.18);
}

/* ---------------------------------------------------------- title block */
.cover-title {
  font-size: 26pt; font-weight: 400; letter-spacing: -.01em;
  line-height: 1.05; margin: 0.35in 0 6px;
}
.cover-address {
  font-size: 8pt; font-weight: 700; text-transform: uppercase;
  letter-spacing: .01em; margin-bottom: 0.3in;
}

/* ------------------------------------------------------------- sections */
section { margin-bottom: 15px; break-inside: avoid; }

/* First section on the cover uses a plain heading with a heavy rule. */
h2.plain {
  font-size: 11pt; font-weight: 700; margin: 0 0 0;
  padding-bottom: 3px; border-bottom: 1.6pt solid var(--rule);
  text-transform: uppercase; letter-spacing: .01em;
}

/* Later sections use the dark tab treatment. */
h2.tab {
  display: flex; align-items: stretch; gap: 0;
  font-size: 8pt; font-weight: 700; margin: 0 0 7px; text-transform: none;
}
h2.tab .name {
  background: var(--tab); color: #fff;
  padding: 3px 14px 3px 8px; border-radius: 0 9px 9px 0;
  white-space: nowrap;
}
h2.tab .fill { flex: 1; border-bottom: .6pt solid var(--hair); }

.section-end { border-bottom: 1.6pt solid var(--rule); margin-top: 8px; }

/* Banded sub-heading inside a section. */
.band {
  background: var(--band); color: var(--band-text);
  font-weight: 700; font-size: 7.5pt;
  padding: 2px 7px; margin: 9px 0 0;
}
.band.light { background: var(--subtle); color: #1a1a1a; }

/* ------------------------------------------------------- label / value */
/* Two 22-pica columns with a 1-pica gutter (Appendix E p16). */
.fields { display: grid; grid-template-columns: 22fr 22fr; column-gap: 1.5%; }
.fields .col { min-width: 0; }

/* H1 - subsection title in a 10% black bar (Appendix E p20). */
.h1bar {
  background: #e6e6e6; font-weight: 700; font-size: 10pt; line-height: 13pt;
  padding: 1.5pt 4pt; margin: 13pt 0 2pt;
}
.field {
  display: grid; grid-template-columns: 1.35fr 1fr;
  gap: 6px; align-items: baseline;
  padding: 2.5px 0; border-bottom: .5pt solid var(--hair);
}
.field .label { font-weight: 700; color: var(--label); }
.field .value { color: var(--value); word-break: break-word; }
.field .note {
  grid-column: 1 / -1; font-size: 6.4pt; color: #5a6168;
  font-style: italic; line-height: 1.3; padding: 1px 0 2px;
}
.field.wide { grid-column: 1 / -1; }

[data-editable] {
  background: var(--field); border: .5pt solid #b9c6d2; border-radius: 2px;
  padding: 0 4px; min-width: 52px; display: inline-block;
  font: inherit; color: inherit;
}
[data-editable]:focus { outline: 1.5pt solid #14502f; background: #fff; }

/* CK1 - a Yes/No checkbox pair, boxes aligned right in the column (E p26). */
.ck { display: flex; align-items: baseline; gap: 3pt; justify-content: flex-end; }
.ck .yn { font-size: 8pt; font-weight: 700; }
.ck .box { font-size: 11pt; line-height: 1; margin-right: 5pt; }
.field.ck-row { grid-template-columns: 1.35fr 1fr; }

.badge {
  display: inline-block; font-size: 5.8pt; font-weight: 700;
  letter-spacing: .05em; text-transform: uppercase;
  padding: 0 3px; border-radius: 2px; margin-left: 4px; vertical-align: 1px;
}
.badge.conflict { background: var(--flag-bg); color: var(--flag); }
.badge.derived  { background: var(--derived-bg); color: var(--derived); }
.badge.warning  { background: var(--warn-bg); color: var(--warn); }

/* ------------------------------------------------------------ the grid */
table.grid { width: 100%; border-collapse: collapse; font-size: 6.8pt; }
table.grid th, table.grid td {
  border: .5pt solid var(--hair); padding: 2px 4px; vertical-align: top;
}
table.grid thead th {
  border: none; font-size: 7.5pt; font-weight: 700;
  text-align: center; padding-bottom: 4px;
}
table.grid thead th.corner { border: none; }
/* Appendix E p30-31: three band treatments in the comparable grid. */
table.grid tr.band-row.band-dark td {
  background: #333333; color: #fff; font-weight: 700;   /* TB-SCA_sub-H1, 80% black */
  font-size: 8pt; border-color: #333333;
}
table.grid tr.band-row.band-light td {
  background: #e6e6e6; color: #000; font-weight: 700;   /* TB-SCA_H2, 10% black */
  font-size: 8pt; border-color: #bfbfbf;
}
/* Cell types and rule weights from Appendix E p61-62.
   Type 1 and Type 5 cells carry a 10% black fill and no content; the vertical
   rule separating Subject from each comparable is 100% black (line type A),
   while the value-to-adjustment divider is 50% (line type B). */
table.grid td.rowlabel { text-align: left; width: 17%; }
table.grid td.subject  { text-align: right; border-right: 0.5pt solid #000; }
table.grid td.compval  { text-align: right; border-left: 0.5pt solid #000; }
table.grid td.compadj  { text-align: right; width: 5.5%; white-space: nowrap; }
table.grid td.greyed   { background: #e6e6e6; }
table.grid tr.total td { font-weight: 700; }
table.grid td.addr { white-space: pre-line; text-align: left; }

/* Section tables: half-point 50% black rules, heads ruled below only. */
table.sect { width: 100%; border-collapse: collapse; font-size: 8pt;
  line-height: 9pt; margin: 3pt 0 8pt; }
table.sect th {
  text-align: left; font-size: 9pt; line-height: 10pt; font-weight: 700;
  padding: 0 4pt 3pt; border: none; border-bottom: .5pt solid #808080;
}
table.sect td {
  padding: 3pt 4pt 3.2pt; border: .5pt solid #808080; vertical-align: top;
}
table.sect td:first-child, table.sect th:first-child { border-left: none; }
table.sect td:last-child, table.sect th:last-child { border-right: none; }
.table-name { font-size: 7.5pt; font-weight: 700; margin-top: 8pt; }

.grid-note {
  font-size: 6.4pt; color: var(--flag); font-style: italic;
  margin: 5px 0 0; line-height: 1.35;
}

/* --------------------------------------------------------- narrative */
.narrative { margin-top: 8px; }
.narrative h3 {
  font-size: 7pt; font-weight: 700; margin: 0 0 3px; text-transform: none;
}
.narrative .body {
  line-height: 1.45; text-align: justify;
  border: .5pt solid var(--hair); padding: 5px 7px; min-height: 40px;
}
.narrative .body[data-editable] { background: var(--field); }

/* ----------------------------------------------------------- exhibits */
.photos { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }
.photo { break-inside: avoid; }
.photo img {
  width: 100%; height: 1.45in; object-fit: cover; border: .5pt solid var(--hair);
}
.photo .cap { font-size: 6.4pt; padding-top: 2px; line-height: 1.25; }

/* Appendix E p34: subject photo sets in the right column level with Property
   Description, maximum 22 picas wide by 13 picas 3 points high. */
.inline-photo { margin: 4pt 0 0; }
.inline-photo img {
  width: 100%; max-width: 3.66in; max-height: 2.22in;
  object-fit: cover; border: .5pt solid #bfbfbf; display: block;
}

.signature { margin-top: 8px; }
.signature img { height: 0.45in; display: block; }
.signature .rule { border-bottom: .75pt solid #000; width: 2.6in; }
.signature .who { font-size: 6.8pt; padding-top: 2px; }

.findings { margin: 4px 0 0; padding-left: 14px; }
.findings li { font-size: 6.8pt; margin-bottom: 2px; }
.findings .sev { font-weight: 700; }
.findings .Fatal { color: var(--warn); }
.findings .Warning { color: var(--flag); }

.page-break { break-before: page; }

@media print {
  body { background: #fff; }
  .toolbar { display: none !important; }
  .sheet { width: auto; margin: 0; padding: 0; box-shadow: none; }
  [data-editable] { background: transparent !important; border: none; padding: 0; }
  /* A dropdown must print as plain text, with no control affordance. */
  select[data-editable] {
    appearance: none; -webkit-appearance: none; -moz-appearance: none;
    background-image: none; padding-right: 0;
  }
  .badge { display: none; }
}


/* ---------------------------------------------------------------- phones
   The sheet is a fixed 8.5in page because that is what prints.  On a phone
   that would scroll sideways, so below tablet width the page becomes a single
   fluid column with touch-sized fields, while print keeps the paper size. */
@media screen and (max-width: 820px) {
  body { font-size: 9.5pt; }

  .sheet {
    width: auto; max-width: 100%;
    margin: 8px; padding: 14px;
  }

  .toolbar {
    padding: 8px 12px; gap: 8px;
    font-size: 10pt;
  }
  .toolbar h1 { font-size: 10pt; width: 100%; }
  .toolbar .spacer { display: none; }
  .toolbar button { flex: 1; min-height: 40px; padding: 8px 10px; }
  .editors { width: 100%; }

  /* One column, and the label sits above its value so long labels breathe. */
  .fields { grid-template-columns: 1fr; }
  .field { grid-template-columns: 1fr; gap: 2px; padding: 7px 0; }
  .field .label { font-size: 9pt; }
  .field .value { font-size: 10.5pt; }

  /* Editable fields need a real touch target. */
  [data-editable] {
    display: block; width: 100%; min-height: 34px;
    padding: 7px 9px; font-size: 10.5pt; border-radius: 5px;
  }
  select[data-editable] { min-height: 38px; }

  .ck { justify-content: flex-start; gap: 6px; }
  .ck .box { font-size: 15pt; }

  .cover-title { font-size: 19pt; }
  .h1bar { font-size: 10.5pt; padding: 4px 6px; }

  /* Wide tables scroll in their own container, never the page. */
  table.grid, table.sect { font-size: 8.5pt; min-width: 640px; }
  .scroller {
    overflow-x: auto; -webkit-overflow-scrolling: touch;
    margin: 0 -14px; padding: 0 14px;
  }
  .photos { grid-template-columns: repeat(2, 1fr); }
  .photo img { height: 110px; }
  .inline-photo img { max-width: 100%; }
  .narrative .body { font-size: 10pt; }
}

@media screen and (max-width: 430px) {
  .photos { grid-template-columns: 1fr; }
  .toolbar button { font-size: 9pt; }
}

@page { size: 8.5in 14in; margin: 0.5in 0.5in 0.72in; }
"""

SCRIPT = """
/* Shared review session.  Edits are saved per field to the server and pushed
   to everyone with the report open, so two people on different machines are
   always looking at the same values. */
const session = {
  editor: localStorage.getItem('urar.editor') || (crypto.randomUUID ? crypto.randomUUID() : String(Math.random())),
  name: localStorage.getItem('urar.name') || '',
  revision: 0,
  pending: {},
  timer: null,
  connected: false,
};
localStorage.setItem('urar.editor', session.editor);

function setStatus(text, cls) {
  const el = document.getElementById('status');
  if (!el) return;
  el.textContent = text;
  el.className = 'status' + (cls ? ' ' + cls : '');
}

function showEditors(names) {
  const el = document.getElementById('editors');
  if (!el) return;
  const others = (names || []).filter(n => n !== session.name);
  el.textContent = others.length
    ? others.length + ' other' + (others.length > 1 ? 's' : '') + ' editing: ' + others.join(', ')
    : '';
}

function fieldFor(path) {
  return document.querySelector('[data-path="' + CSS.escape(path) + '"]');
}

function applyValue(path, value) {
  const el = fieldFor(path);
  if (!el || el === document.activeElement) return;   /* never fight a typist */
  if (el.tagName === 'SELECT') el.value = value;
  else if (el.innerText.trim() !== value) el.innerText = value;
  el.classList.add('just-changed');
  setTimeout(() => el.classList.remove('just-changed'), 1600);
}

async function pull() {
  const response = await fetch('/api/sync');
  if (!response.ok) return;
  const state = await response.json();
  session.revision = state.revision;
  Object.entries(state.values || {}).forEach(([path, value]) => applyValue(path, value));
  showEditors(state.editors);
}

function listen() {
  const source = new EventSource('/api/stream');
  source.onopen = () => {
    session.connected = true;
    setStatus('Live', 'ok');
    pull();
  };
  source.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.type === 'reset') { location.reload(); return; }
    if (message.type !== 'changes') return;
    session.revision = message.revision;
    Object.entries(message.changes).forEach(([path, value]) => applyValue(path, value));
    if (message.editor && message.editor !== session.name) {
      setStatus('Updated by ' + message.editor, 'ok');
      setTimeout(() => { if (session.connected) setStatus('Live', 'ok'); }, 2500);
    }
  };
  source.onerror = () => {
    session.connected = false;
    setStatus('Reconnecting\u2026', 'bad');
    source.close();
    setTimeout(listen, 3000);
  };
}

async function flush() {
  const batch = session.pending;
  if (!Object.keys(batch).length) return;
  session.pending = {};
  try {
    const response = await fetch('/api/edits', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign({}, batch,
        {__editor: session.editor, __name: session.name})),
    });
    if (!response.ok) throw new Error(await response.text());
    const result = await response.json();
    session.revision = result.revision;
    showEditors(result.editors);
    setStatus('Saved', 'ok');
    setTimeout(() => { if (session.connected) setStatus('Live', 'ok'); }, 1500);
  } catch (err) {
    Object.assign(session.pending, batch);        /* keep it for the next try */
    setStatus('Save failed, retrying', 'bad');
    setTimeout(flush, 4000);
  }
}

function queue(el) {
  const path = el.dataset.path;
  if (!path) return;
  session.pending[path] = el.tagName === 'SELECT' ? el.value : el.innerText.trim();
  setStatus('Saving\u2026');
  clearTimeout(session.timer);
  session.timer = setTimeout(flush, 600);
}

/* The name is taken from a field in the toolbar rather than a dialog: a modal
   prompt blocks the page, is refused outright in some browsers, and is poor on
   a phone. */
function bindName() {
  const input = document.getElementById('whoami');
  if (!input) return;
  input.value = session.name;
  input.addEventListener('change', () => {
    session.name = input.value.trim().slice(0, 40) || 'A reviewer';
    localStorage.setItem('urar.name', session.name);
    fetch('/api/presence', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({editor: session.editor, name: session.name}),
    }).then(r => r.json()).then(r => showEditors(r.editors)).catch(() => {});
  });
}

async function download() {
  const button = document.getElementById('download');
  button.disabled = true;
  setStatus('Building deliverable\u2026');
  try {
    await flush();
    const response = await fetch('/api/package', {method: 'POST'});
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = response.headers.get('X-Filename') || 'appraisal.zip';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setStatus('Deliverable downloaded', 'ok');
  } catch (err) {
    setStatus('Error: ' + err.message, 'bad');
  } finally {
    button.disabled = false;
  }
}

async function revalidate() {
  await flush();
  location.reload();
}

document.addEventListener('input', e => {
  if (e.target.dataset && e.target.dataset.path) queue(e.target);
});
document.addEventListener('change', e => {
  if (e.target.dataset && e.target.dataset.path) queue(e.target);
});
document.addEventListener('blur', e => {
  if (e.target.dataset && e.target.dataset.path) { queue(e.target); flush(); }
}, true);

listen();
bindName();
setInterval(() => {
  fetch('/api/presence', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({editor: session.editor, name: session.name}),
  }).then(r => r.json()).then(r => showEditors(r.editors)).catch(() => {});
}, 20000);
"""


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


# ------------------------------------------------------------------ fields
def _control(row) -> str:
    if row.kind == READ_ONLY or not row.path:
        return f'<span class="value">{_esc(row.value)}</span>'
    if row.kind == CHOICE:
        options = "".join(
            f'<option value="{_esc(o)}"'
            f'{" selected" if str(o) == str(row.value) else ""}>'
            f"{_esc(row.display_for(o))}</option>"
            for o in row.options
        )
        return f'<select class="value" data-editable data-path="{_esc(row.path)}">{options}</select>'
    return (
        f'<span class="value" data-editable contenteditable="true" '
        f'data-path="{_esc(row.path)}">{_esc(row.value)}</span>'
    )


def _badge(flag: str | None) -> str:
    if not flag:
        return ""
    text = {"conflict": "source conflict", "derived": "market derived",
            "warning": "attention"}.get(flag, flag)
    return f'<span class="badge {_esc(flag)}">{_esc(text)}</span>'


def _checkbox(row) -> str:
    """A Yes/No pair set as CK1 (Appendix E p26-27).

    The guide sets these in Wingdings2; the glyphs here are the Unicode
    equivalents so the page renders without that font installed.
    """
    chosen = str(row.value).strip().lower()
    yes = "☑" if chosen in ("yes", "true") else "☐"
    no = "☑" if chosen in ("no", "false") else "☐"
    editable = (
        f' data-editable data-path="{_esc(row.path)}" data-kind="checkbox"'
        if row.path else ""
    )
    return (
        '<span class="ck"><span class="yn">Yes</span>'
        f'<span class="box"{editable}>{yes}</span>'
        '<span class="yn">No</span>'
        f'<span class="box">{no}</span></span>'
    )


def _field(row) -> str:
    from .review import CHECKBOX, PHOTO

    if row.kind == CHECKBOX:
        note = f'<div class="note">{_esc(row.note)}</div>' if row.note else ""
        return (
            f'<div class="field ck-row"><span class="label">{_esc(row.label)}</span>'
            f"{_checkbox(row)}{note}</div>"
        )
    if row.kind == PHOTO:
        return (
            f'<figure class="inline-photo"><img src="/images/{_esc(row.value)}"'
            ' alt=""></figure>'
        )
    note = f'<div class="note">{_esc(row.note)}</div>' if row.note else ""
    return (
        f'<div class="field"><span class="label">{_esc(row.label)}{_badge(row.flag)}</span>'
        f"{_control(row)}{note}</div>"
    )


def _fields(rows) -> str:
    """Lay out a section body.

    Appendix E Part 2 assigns each label to the left or right page column, and
    a grey H1 bar introduces each subsection and resets the columns below it.
    """
    from .review import SUBHEADING

    blocks: list[str] = []
    left: list = []
    right: list = []

    def flush() -> None:
        if not (left or right):
            return
        blocks.append(
            '<div class="fields">'
            f'<div class="col">{"".join(_field(r) for r in left)}</div>'
            f'<div class="col">{"".join(_field(r) for r in right)}</div>'
            "</div>"
        )
        left.clear()
        right.clear()

    for row in rows:
        if row.kind == SUBHEADING:
            flush()
            blocks.append(f'<div class="h1bar">{_esc(row.label)}</div>')
            continue
        (right if row.column == "right" else left).append(row)
    flush()
    return "".join(blocks)


# -------------------------------------------------------------------- grid
def _grid(grid: ComparisonGrid) -> str:
    """One table per block of three comparables (Appendix E p62)."""
    return "".join(_grid_block(b) for b in grid.blocks())


def _grid_block(grid: ComparisonGrid) -> str:
    span = 2  # every comparable occupies a value column and an adjustment column
    head = ['<th class="corner"></th>', f"<th>{_esc(grid.columns[0])}</th>"]
    head += [f'<th colspan="{span}">{_esc(c)}</th>' for c in grid.columns[1:]]

    body: list[str] = []
    total_cols = 2 + grid.comparable_count * span

    for group in grid.groups:
        css = {
            "TB-SCA_sub-H1": "band-dark",
            "TB-SCA_sub-H1-ADJ": "band-dark band-adj",
            "TB-SCA_H2": "band-light",
        }.get(getattr(group, "band_style", ""), "band-dark")
        body.append(
            f'<tr class="band-row {css}"><td colspan="{total_cols}">'
            f"{_esc(group.title)}</td></tr>"
        )
        for row in group.rows:
            address = row.label == "Property Address"
            addr = " addr" if address else ""
            grey_subject = " greyed" if row.subject_greyed else ""
            grey_adj = " greyed" if row.adjustment_greyed else ""

            cells = [f'<td class="rowlabel">{_esc(row.label)}</td>']
            cells.append(
                f'<td class="subject{addr}{grey_subject}">'
                f"{'' if row.subject_greyed else _esc(row.subject)}</td>"
            )
            for cell in row.cells:
                cells.append(f'<td class="compval{addr}">{_esc(cell.value)}</td>')
                cells.append(
                    f'<td class="compadj{grey_adj}">'
                    f"{'' if row.adjustment_greyed else _esc(cell.adjustment_text)}</td>"
                )
            body.append(f"<tr>{''.join(cells)}</tr>")

    for row in grid.totals:
        cells = [f'<td class="rowlabel">{_esc(row.label)}</td>', '<td class="subject"></td>']
        for cell in row.cells:
            cells.append(f'<td class="compval" colspan="{span}">{_esc(cell.value)}</td>')
        body.append(f'<tr class="total">{"".join(cells)}</tr>')

    notes = "".join(f'<p class="grid-note">{_esc(n)}</p>' for n in grid.notes)
    return (
        f'<div class="scroller"><table class="grid">'
        f'<thead><tr>{"".join(head)}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>{notes}"
    )


def _table(table) -> str:
    """A section table: TCH column heads, ruled body (Appendix E p28-29)."""
    head = "".join(f"<th>{_esc(c)}</th>" for c in table.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
        for row in table.rows
    )
    notes = "".join(f'<p class="grid-note">{_esc(n)}</p>' for n in table.notes)
    caption = (
        f'<div class="table-name">{_esc(table.name)}</div>'
        if getattr(table, "name", "") else ""
    )
    return (
        f'{caption}<div class="scroller"><table class="sect">'
        f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>{notes}"
    )


def _narrative(row) -> str:
    editable = "" if row.kind == READ_ONLY else ' data-editable contenteditable="true"'
    path = f' data-path="{_esc(row.path)}"' if row.path else ""
    return (
        f'<div class="narrative"><h3>{_esc(row.label)}</h3>'
        f'<div class="body"{editable}{path}>{_esc(row.value)}</div></div>'
    )


def _photos(images) -> str:
    cards = "".join(
        f'<figure class="photo"><img src="/images/{_esc(i["filename"])}" alt="">'
        f'<figcaption class="cap">{_esc(i.get("caption", ""))}</figcaption></figure>'
        for i in images if i.get("role") != "signature"
    )
    return f'<div class="photos">{cards}</div>' if cards else ""


def _findings(findings) -> str:
    if not findings:
        return '<p class="grid-note">No compliance findings. This report passes UAD ' \
               'schema validation and all executed compliance rules.</p>'
    items = "".join(
        f'<li><span class="sev {_esc(f.get("severity"))}">{_esc(f.get("severity"))}</span> '
        f'{_esc(f.get("rule_id") or "")} — {_esc(f.get("message"))}</li>'
        for f in findings[:40]
    )
    return f'<ul class="findings">{items}</ul>'


def _signature(appraiser: dict) -> str:
    licence = appraiser.get("license", {})
    return (
        '<div class="signature"><img src="/images/SIGNATURE.png" alt="">'
        '<div class="rule"></div>'
        f'<div class="who"><strong>{_esc(appraiser.get("name", {}).get("full", ""))}</strong>'
        f' &middot; {_esc(appraiser.get("company_name", ""))}<br>'
        f'{_esc(licence.get("level_display", ""))} #{_esc(licence.get("identifier", ""))} '
        f'({_esc(licence.get("state", ""))}), expires {_esc(licence.get("expiration_date", ""))}'
        "</div></div>"
    )


def _section(section: Section, *, first: bool, appraiser: dict) -> str:
    heading = (
        f'<h2 class="plain">{_esc(section.title)}</h2>'
        if first
        else f'<h2 class="tab"><span class="name">{_esc(section.title)}</span>'
             f'<span class="fill"></span></h2>'
    )
    parts = [f'<section class="{"page-break" if section.page_break else ""}">', heading]

    if section.rows:
        parts.append(_fields(section.rows))
    if section.comparison_grid is not None:
        parts.append(_grid(section.comparison_grid))
    parts.extend(_table(t) for t in section.tables)
    parts.extend(_narrative(n) for n in section.narrative)

    if any(i.get("role") == "signature" for i in section.images):
        parts.append(_signature(appraiser))

    gallery = [i for i in section.images if i.get("role") != "signature"]
    if gallery:
        parts.append(_photos(gallery))
    if section.title.lower().startswith("compliance"):
        parts.append(_findings(section.findings))

    if first:
        parts.append('<div class="section-end"></div>')
    parts.append("</section>")
    return "".join(parts)


def document(
    sections: list[Section],
    *,
    address: str,
    appraiser: dict,
    editable: bool = True,
) -> str:
    toolbar = (
        '<div class="toolbar"><h1>UAD 3.6 URAR — Shared Review</h1>'
        '<span id="status" class="status">Connecting…</span>'
        '<input id="whoami" class="whoami" placeholder="Your name" '
        'aria-label="Your name, shown to other reviewers" maxlength="40">'
        '<span id="editors" class="editors"></span>'
        '<span class="spacer"></span>'
        '<button onclick="revalidate()">Save &amp; revalidate</button>'
        '<button id="download" class="primary" onclick="download()">Download ZIP</button>'
        "</div>"
        if editable else ""
    )
    body = "".join(
        _section(s, first=(i == 0), appraiser=appraiser)
        for i, s in enumerate(sections)
    )
    script = f"<script>{SCRIPT}</script>" if editable else ""

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Uniform Residential Appraisal Report</title>"
        f"<style>{PAGE_CSS}</style></head><body>{toolbar}"
        '<main class="sheet">'
        '<h1 class="cover-title">Uniform Residential Appraisal Report</h1>'
        f'<div class="cover-address">{_esc(address)}</div>'
        f"{body}</main>{script}</body></html>"
    )
