"""What TOTAL itself says is still wrong, read from TOTAL itself.

TOTAL carries its own UAD rule set: ``window.engine.realTimeValidation``
holds, per section, a map of field name to the validators that field must
pass, and each validator is ``{fn(value, instance, fieldName), message}``.
That is what fills the E&O panel's "Field Validation Errors" list, and it is
the only authority worth working against -- it is TOTAL's reading of the
standard, for whatever form the report happens to be, so a driveby, a
single-family, a condominium and a 2-4 unit are all covered by the same code
without anything being written per form.

Two things have to be true for a sweep to mean anything:

* **A section must be on screen before its fields can be read.**  TOTAL
  renders one section at a time; a validator run against a section that is not
  rendered reads ``null`` for every field and reports the whole form broken.
  The first sweep written here did exactly that -- 610 failures out of 1,041
  checks, nearly all of them fields that were simply not on the page.
* **A validator's own exceptions are not failures.**  Nine of them throw when
  a field they depend on is absent; those are recorded as "could not run"
  rather than counted as errors, because a check that cannot run has not
  found anything.

``sweep`` returns one entry per failing validator: the section, the field, the
message TOTAL shows, the value it read, and the Report Field ID stamped on the
control -- which is what lets the value be looked up in a UAD 3.6 file and
written back.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as _field

# Runs every validator for the section currently on screen.  Values are read
# from the controls themselves, the same way TOTAL reads them.
_SWEEP = r"""
(() => {
  const rtv = window.engine && window.engine.realTimeValidation;
  if (!rtv || !rtv.fieldValidators) return {error: 'no validators'};
  const wanted = %s;
  const out = {checked: 0, failed: [], unrun: [], sections: []};

  const controlFor = (name, instance) => {
    const all = [...document.querySelectorAll('[fn="' + name + '"]')];
    if (!all.length) return null;
    if (instance === null || instance === undefined) return all[0];
    const exact = all.find(e => String(e.getAttribute('instance') || '0') === String(instance));
    return exact || all[0];
  };
  const valueOf = (el) => {
    if (!el) return null;
    if (el.type === 'checkbox' || el.type === 'radio') return el.checked;
    if (el.value !== undefined && el.value !== null) return el.value;
    return (el.textContent || '').trim();
  };

  for (const [section, fields] of rtv.fieldValidators.entries()) {
    if (wanted && wanted !== section) continue;
    out.sections.push(section);
    for (const [name, spec] of fields.entries()) {
      const el = controlFor(name, 0);
      if (!el) continue;                    // not on screen: nothing to judge
      const value = valueOf(el);
      for (const check of (spec.validatorFunctions || [])) {
        out.checked++;
        let ok;
        try { ok = check.fn(value, 0, name); }
        catch (err) { out.unrun.push({section, field: name,
                                      why: String(err).slice(0, 120)}); continue; }
        if (ok) continue;
        out.failed.push({
          section, field: name,
          message: String(check.message || 'Validation failed').slice(0, 200),
          value: value === null ? null : String(value).slice(0, 60),
          fmid: el.getAttribute('fmid') || '',
          instance: el.getAttribute('instance') || '',
          tag: el.tagName.toLowerCase(),
          type: el.getAttribute('type') || ''
        });
      }
    }
  }
  return out;
})()
"""


@dataclass
class Problem:
    """One thing TOTAL will not accept yet."""
    section: str
    field: str
    message: str
    value: str | None
    fmid: str = ""
    instance: str = ""
    tag: str = ""
    type: str = ""

    @property
    def is_empty(self) -> bool:
        return self.value in (None, "", "false", False)

    def __str__(self) -> str:
        where = f"{self.section}/{self.field}"
        fid = f"  [{self.fmid}]" if self.fmid else ""
        return f"{where:52} {self.message[:70]}{fid}"


@dataclass
class Sweep:
    problems: list[Problem] = _field(default_factory=list)
    unrun: list[dict] = _field(default_factory=list)
    checked: int = 0
    sections: list[str] = _field(default_factory=list)

    @property
    def fields(self) -> list[str]:
        return sorted({p.field for p in self.problems})

    def by_section(self) -> dict[str, list[Problem]]:
        out: dict[str, list[Problem]] = {}
        for problem in self.problems:
            out.setdefault(problem.section, []).append(problem)
        return out

    def summary(self) -> str:
        counts = {key: len(value) for key, value in self.by_section().items()}
        worst = sorted(counts.items(), key=lambda kv: -kv[1])
        lines = [f"{len(self.problems)} field validation error(s) "
                 f"over {self.checked} checks"]
        for section, count in worst:
            lines.append(f"   {section:24} {count}")
        if self.unrun:
            lines.append(f"   ({len(self.unrun)} check(s) could not run)")
        return "\n".join(lines)


def sweep_section(report, section: str | None = None) -> Sweep:
    """Run the validators for the section on screen."""
    raw = report.page.evaluate(_SWEEP % (json.dumps(section) if section else "null"))
    if not raw or raw.get("error"):
        return Sweep()
    problems = [Problem(**{k: v for k, v in item.items()
                           if k in Problem.__dataclass_fields__})
                for item in raw.get("failed", [])]
    return Sweep(problems=problems, unrun=raw.get("unrun", []),
                 checked=raw.get("checked", 0), sections=raw.get("sections", []))


def sweep(report, *, settle: float = 1.2, on_section=None) -> Sweep:
    """Walk every section and run its own validators against what is on screen.

    The section the report was sitting on is put back afterwards, because a
    reading of this form depends on where the form is sitting.
    """
    whole = Sweep()
    start = report.page.evaluate("window.engine.currentActiveSectionKey")
    try:
        for key in report.sections():
            report.goto(key, settle)
            here = sweep_section(report, key)
            whole.problems.extend(here.problems)
            whole.unrun.extend(here.unrun)
            whole.checked += here.checked
            whole.sections.append(key)
            if on_section:
                on_section(key, here)
    finally:
        if start:
            report.goto(start, 0.4)
    return whole
