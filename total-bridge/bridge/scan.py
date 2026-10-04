"""Read TOTAL's **visual** validation state, not just its error list.

``rtv.problems`` asks TOTAL's own validation engine what it thinks.  That list
is authoritative as far as it goes, and it misses things, because TOTAL marks
some problems only on the rendered control:

* a **red field** -- computed border ``rgb(204,0,0)`` over background
  ``rgb(255,230,230)`` with outline ``rgb(153,0,0)``;
* an **``rtv-flag``** marker, TOTAL's own per-field flag element;
* an **empty photo well**, marked by a red outline on the drop zone rather
  than on any field;
* a **dropdown holding a value that is not in its own list**, which renders
  blank and reports nothing;
* a **gap in a repeating row** -- a cell empty where every sibling row has
  one.

None of those appear in ``globalRtvErrors`` reliably, and a section that is
not rendered shows nothing at all, so the scan walks the report section by
section and looks at what is actually on screen.

The output is a list of :class:`Finding`, each naming the control (``fn`` plus
instance), the section it lives in, the row label as a person would read it,
what the field currently holds, what it will accept, and why it was flagged.
That is what makes an automatic fix possible: the finding names the thing to
write to.

Nothing here suppresses or dismisses a validation state.  It only reads.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as _field

#: The red TOTAL paints on a field it is unhappy with, and the red outline it
#: puts round an empty photo well.  Measured off the running application
#: rather than guessed: these are the computed values, not stylesheet names.
_SCAN = r"""((opts) => {
  const RED_BORDER = 'rgb(204, 0, 0)';
  const RED_BG     = 'rgb(255, 230, 230)';
  const RED_OUT    = ['rgb(153, 0, 0)', 'rgb(255, 0, 0)'];
  // The grid paints an adjustment by its SIGN, not by its validity: a negative
  // amount is red on the same palette as an error, and a positive one is green.
  // Reading the red as a fault reports every downward adjustment in the report
  // as a defect.  The green is what proves it is a sign: if the form is using
  // it anywhere, red on an adjustment cell means "negative".
  const GREEN_BORDER = 'rgb(0, 176, 80)';
  let signColouring = false;
  for (const el of document.querySelectorAll('[fn]')) {
    if (el.offsetParent === null) continue;
    if (getComputedStyle(el).borderColor === GREEN_BORDER) { signColouring = true; break; }
  }
  const isAdjustment = (el) => /_ADJ$/.test((el.getAttribute && el.getAttribute('fn')) || '');

  const labelFor = (el) => {
    // the row's own left-hand caption, which is what a person reads
    let row = el.closest('tr, .form-row, .field-row, .sxs-row');
    for (let hop = 0; hop < 3 && row; hop++) {
      const cells = row.querySelectorAll('td, .sxs-sticky-label-cell, .label, label');
      for (const c of cells) {
        const t = (c.innerText || '').trim();
        if (t && t.length < 60 && !/^\$?[\d,.]*$/.test(t)) return t;
      }
      row = row.parentElement && row.parentElement.closest('tr, .form-row, .field-row');
    }
    const aria = el.getAttribute('aria-label') || el.getAttribute('title') || '';
    return aria.trim();
  };

  const out = [];
  const seen = new Set();
  const push = (el, why, extra) => {
    const fn = el.getAttribute ? (el.getAttribute('fn') || '') : '';
    const inst = el.getAttribute ? (el.getAttribute('instance') || '0') : '0';
    const key = fn + '#' + inst + '|' + why;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(Object.assign({
      fn: fn, instance: inst, why: why,
      value: (el.value !== undefined ? String(el.value) : (el.innerText || '').trim()).slice(0, 60),
      label: labelFor(el).slice(0, 60),
      tag: el.tagName
    }, extra || {}));
  };

  // 1. anything painted red, field or not
  for (const el of document.querySelectorAll('*')) {
    if (el.offsetParent === null) continue;
    const cs = getComputedStyle(el);
    const red = cs.borderColor === RED_BORDER
             || cs.backgroundColor === RED_BG
             || RED_OUT.includes(cs.outlineColor);
    if (!red) continue;
    if (el.hasAttribute && el.hasAttribute('fn')) {
      // a negative adjustment is red by design, not by fault
      if (signColouring && isAdjustment(el) && cs.outlineColor !== 'rgb(255, 0, 0)') continue;
      push(el, 'red-field');
      continue;
    }
    // a red thing that is not a field: a photo well, a table cell
    const inner = el.querySelector && el.querySelector('[fn]');
    if (inner) { push(inner, 'red-container'); continue; }
    const looksLikePhoto = /photo|image|drop/i.test(el.className || '') ||
                           /drag and drop/i.test((el.innerText || '').slice(0, 40));
    if (looksLikePhoto) {
      const id = el.id || (el.querySelector('input[type=file]') || {}).id || '';
      out.push({fn: '', instance: '0', why: 'empty-photo-well',
                value: '', label: (el.innerText || '').split('\n')[0].slice(0, 48),
                tag: el.tagName, wellId: id});
    }
  }

  // 2. TOTAL's own per-field flag element
  for (const flag of document.querySelectorAll('[class*="rtv-flag"]')) {
    if (flag.offsetParent === null) continue;
    const host = flag.closest('[fn]') ||
                 (flag.parentElement && flag.parentElement.querySelector('[fn]'));
    if (host) push(host, 'rtv-flag');
  }

  // 3. required and empty, and dropdowns holding a value not in their list
  const ds = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const byKey = {};
  const walk = o => { for (const x of (o.dataObjects || [])) {
      const k = x.key || '';
      if (k && !(x.dataObjects || []).length)
        byKey[k + '#' + (x.instance ?? 0)] = x;
      walk(x); } };
  walk({dataObjects: ds.dataObjects});

  for (const el of document.querySelectorAll('[fn]')) {
    if (el.offsetParent === null) continue;
    const fn = el.getAttribute('fn');
    const inst = el.getAttribute('instance') || '0';
    const obj = byKey[fn + '#' + inst];
    if (!obj) continue;
    const value = String(obj.value ?? '').trim();
    if (obj.required && !value) { push(el, 'required-empty'); continue; }
    const items = (obj.items || []).map(i =>
        String(i && (i.value !== undefined ? i.value : i)));
    if (value && items.length && !items.includes(value)) {
      // TOTAL renders this blank and says nothing
      push(el, 'value-not-in-list', {options: items.slice(0, 20)});
    }
  }

  // 4. a gap in a repeating row: a cell empty where its siblings are filled
  if (opts && opts.rowGaps) {
    const groups = {};
    for (const key of Object.keys(byKey)) {
      const m = key.match(/^(.+)#(\d+)$/);
      if (!m) continue;
      (groups[m[1]] = groups[m[1]] || []).push([parseInt(m[2]), byKey[key]]);
    }
    for (const name of Object.keys(groups)) {
      const rows = groups[name];
      if (rows.length < 2) continue;
      const filled = rows.filter(r => String(r[1].value ?? '').trim()).length;
      if (filled === 0 || filled === rows.length) continue;
      for (const [inst, obj] of rows) {
        if (String(obj.value ?? '').trim()) continue;
        const el = document.querySelector(`[fn="${name}"][instance="${inst}"]`)
                || document.querySelector(`[fn="${name}"]`);
        if (el) push(el, 'row-gap', {sibling: filled + '/' + rows.length});
        else out.push({fn: name, instance: String(inst), why: 'row-gap',
                       value: '', label: '', tag: 'DATA',
                       sibling: filled + '/' + rows.length});
      }
    }
  }
  return out;
})"""


@dataclass
class Finding:
    """One visual validation state, tied to the control responsible for it."""
    section: str
    fn: str
    instance: str
    why: str
    label: str = ""
    value: str = ""
    tag: str = ""
    options: list = _field(default_factory=list)
    well_id: str = ""
    sibling: str = ""

    def __str__(self) -> str:
        where = f"{self.fn}#{self.instance}" if self.fn else (self.well_id or "(no field)")
        return (f"[{self.section[:20]:20}] {self.why:18} {where:40} "
                f"{self.label[:28]:28} {self.value[:20]!r}")


def sweep(report, sections=None, *, row_gaps: bool = True,
          settle: float = 2.2, on_section=None) -> list:
    """Walk the report and read every visual validation state on the way.

    A section that is not rendered shows nothing, so each one is brought up
    before it is read.  That is also what catches the errors that only appear
    once you navigate away from somewhere else.
    """
    keys = sections or report.sections()
    found = []
    # A row gap is read out of the data layer, which is the same everywhere, so
    # it is asked for once; the red paint and the flags are per-rendered-section
    # and have to be asked for in each.  Without this the same gap is reported
    # thirty times and buries the ten findings that matter.
    seen = set()
    for index, key in enumerate(keys):
        try:
            report.goto(key, settle=settle)
        except Exception as exc:                      # a section may refuse
            found.append(Finding(key, "", "0", "section-would-not-open",
                                 label=str(exc)[:50]))
            continue
        want_gaps = row_gaps and index == 0
        rows = report.page.evaluate(
            f"({_SCAN})({json.dumps({'rowGaps': want_gaps})})") or []
        for row in rows:
            mark = (row.get("fn", ""), str(row.get("instance", "0")),
                    row.get("why", ""), row.get("wellId", ""))
            if mark in seen:
                continue
            seen.add(mark)
            found.append(Finding(
                section=key, fn=row.get("fn", ""), instance=str(row.get("instance", "0")),
                why=row.get("why", ""), label=row.get("label", ""),
                value=row.get("value", ""), tag=row.get("tag", ""),
                options=row.get("options", []) or [],
                well_id=row.get("wellId", "") or "",
                sibling=row.get("sibling", "") or ""))
        if on_section:
            on_section(key, len([f for f in found if f.section == key]))
    return found


def summary(found: list) -> str:
    from collections import Counter
    by_why = Counter(f.why for f in found)
    by_sec = Counter(f.section for f in found)
    lines = [f"{len(found)} visual finding(s)"]
    lines.append("  by kind:    " + ", ".join(f"{k} {v}" for k, v in by_why.most_common()))
    lines.append("  by section: " + ", ".join(f"{k} {v}" for k, v in by_sec.most_common(10)))
    return "\n".join(lines)
