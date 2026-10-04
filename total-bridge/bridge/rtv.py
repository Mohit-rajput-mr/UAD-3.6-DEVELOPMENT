"""TOTAL's own validation run, read as a list of fields.

``validate.sweep`` walks the form section by section and judges what is on
screen.  It works, but it is slow, it can only see a rendered section, and it
reports a field name without telling you which section instance it belongs to.

TOTAL does the same job itself, far better:

    engine.RunGlobalRTV(...)            -> realTimeValidation.ExecuteAllRules
    engine.globalRtvErrorContainer.globalRtvErrors
        -> [{field, sectionKey, errorMessage, sectionFriendlyName}, ...]

Each entry carries the **data field itself** -- its key, its instance, whether
it is visible, what it currently holds -- which is what makes an automatic fix
possible: the error names the thing to write to.  That is the same list the
E&O panel renders under "Field Validation Errors", so the count here is the
count the appraiser sees.

Nothing is bypassed: this is the application's own validation entry point,
called the way the form's own buttons call it.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

_RUN = r"""(async () => {
  const e = window.engine;
  // The build in front of us names it ExecuteGlobalRtvAnalysis; older notes
  // called it RunGlobalRTV.  Either is TOTAL's own entry point.
  const start = e.ExecuteGlobalRtvAnalysis || e.RunGlobalRTV;
  if (!e || typeof start !== 'function') return {error: 'no global RTV entry point'};
  if (typeof e.ResetGlobalRtvErrorContainer === 'function') e.ResetGlobalRtvErrorContainer();
  else { e.globalRtvErrorContainer.globalRtvErrors.length = 0;
         e.globalRtvErrorContainer.analysisComplete = false; }
  try { await start.call(e); } catch (err) { return {error: String(err).slice(0, 200)}; }
  const started = Date.now();
  while (!e.globalRtvErrorContainer.analysisComplete && Date.now() - started < 60000) {
    await new Promise(r => setTimeout(r, 200));
  }
  return {count: e.globalRtvErrorContainer.globalRtvErrors.length};
})()"""

_READ = r"""(() => {
  const rows = window.engine.globalRtvErrorContainer.globalRtvErrors || [];
  return rows.map(r => ({
    field: r.field ? (r.field.key || '') : '',
    instance: r.field ? (r.field.instance ?? 0) : 0,
    value: r.field && r.field.value != null ? String(r.field.value).slice(0, 40) : '',
    visible: r.field ? !!r.field.visible : false,
    options: r.field && r.field.items ? r.field.items.map(i =>
        String(i && (i.value !== undefined ? i.value : i))).slice(0, 24) : [],
    section: r.sectionKey || '',
    friendly: r.sectionFriendlyName || '',
    message: String(r.errorMessage || '').split(/\s+/).join(' ')
  }));
})()"""


@dataclass
class Problem:
    field: str
    instance: int
    value: str
    visible: bool
    options: list
    section: str
    friendly: str
    message: str

    def __str__(self) -> str:
        where = f"{self.field}#{self.instance}"
        return f"{where:46} [{self.friendly[:22]:22}] {self.message[:80]}"


def run(report, *, settle: float = 1.0) -> int:
    """Ask TOTAL to validate the whole report.  Returns how many it found."""
    out = report.page.evaluate(_RUN, await_promise=True) or {}
    if out.get("error"):
        raise RuntimeError(f"RunGlobalRTV: {out['error']}")
    time.sleep(settle)
    return int(out.get("count") or 0)


def problems(report, *, fresh: bool = True) -> list[Problem]:
    """Every field TOTAL's own validation is unhappy with."""
    if fresh:
        run(report)
    return [Problem(**row) for row in (report.page.evaluate(_READ) or [])]


_SET = r"""((writes) => {
  const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const want = new Map(writes.map(w => [w.field + '#' + w.instance, w.value]));
  const hit = new Map();
  // Every copy, not the first: a grid field can appear in more than one
  // container under the same key and instance (comparables 2 and 3 each carry
  // their vehicle-storage popup twice), and writing one of them leaves the
  // other holding the old value for the validator to find.
  const walk = o => { for (const x of (o.dataObjects || [])) {
      const key = (x.key || '') + '#' + (x.instance ?? 0);
      if (want.has(key) && !(x.dataObjects || []).length) {
        x.value = want.get(key);
        hit.set(key, (hit.get(key) || 0) + 1);
      }
      walk(x); } };
  walk({dataObjects: d.dataObjects});
  return {written: [...hit.keys()],
          copies: [...hit.values()].reduce((a, b) => a + b, 0),
          missed: [...want.keys()].filter(k => !hit.has(k))};
})"""


def write(report, writes: list[dict]) -> dict:
    """Put values into the data layer, addressed by field key and instance.

    This is where a fix belongs.  A value typed into a control is a value the
    form may re-render away; the data layer is what the validation, the
    display and the export all read.
    """
    return report.page.evaluate(f"({_SET})({json.dumps(writes)})") or {}


_COMMIT = r"""((keys) => {
  const dl = window.engine.dataLayer;
  const d = dl.DataSets.get(window.engine.currentForm.formName);
  const want = new Set(keys);
  const changed = [];
  const walk = o => { for (const x of (o.dataObjects || [])) {
      if (want.has((x.key || '') + '#' + (x.instance ?? 0))
          && !(x.dataObjects || []).length) changed.push(x);
      walk(x); } };
  walk({dataObjects: d.dataObjects});
  if (!changed.length) return {notified: 0};
  // action 6 is ValueChanged.  Captured off a real typed edit: TOTAL raises
  // 5 (KeyPress) then 6 (ValueChanged) with changedItems and changedKey, and
  // it is 6 that FormCalcs, the renderer and the validator act on.
  for (const f of changed) {
    dl.NotifyObservers({action: 6, changedItems: [f], changedKey: f.key});
  }
  return {notified: changed.length};
})"""


def commit(report, writes: list[dict]) -> dict:
    """Tell the form that these fields changed, so dependants recompute.

    ``write`` assigns ``x.value`` and nothing else.  That is enough for a
    plain required-field fix, because the validator reads the value straight
    off the data object -- which is why a fill run works.  It is **not**
    enough for a field that *gates* something: a section-disable flag, a
    ``HIDDEN_..._COUNT``, ``HAS_SUPERVISOR``.  Those change the shape of the
    form, and the form only reshapes when it is told the value changed.

    So: values through ``write``; anything structural through ``write`` and
    then ``commit``.
    """
    keys = [f"{w['field']}#{w.get('instance', 0)}" for w in writes]
    return report.page.evaluate(f"({_COMMIT})({json.dumps(keys)})") or {}


def put(report, writes: list[dict]) -> dict:
    """Write and commit in one step."""
    out = write(report, writes)
    out.update(commit(report, writes))
    return out
