"""Take a report to zero findings, using TOTAL's own validation as the judge.

The loop is: ask TOTAL what is wrong (``rtv.problems`` -- its own global
validation run, which reports the *field*, not just a sentence), decide a value
for each field, write it into the data layer, and ask again.  It stops when a
pass changes nothing.

Two things this fixes that a naive fill cannot.

**Adjustments must not be written by Report Field ID.**  A-1 gives every
adjustment column in the grid the same identifier (1800.0317 covers dozens of
rows), so filling "the adjustment" by that ID writes one number into every
adjustment cell in the column: 234 of them held a value here, $12,900 smeared
down comparable 1, and its net adjustment read $376,200 instead of $23,800.
An adjustment belongs to the row its ``ComparableAdjustmentType`` names and
nowhere else, so this clears the column and puts back only the three the file
actually states.

**A value belongs in the data layer.**  Typing into a control leaves a value
the next render can drop; the data layer is what the validation, the display
and the export all read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as _field

from . import rtv

#: ComparableAdjustmentType -> the grid field that holds that adjustment.
#: Only these three are ever written: they are the ones the rate card supports
#: (living area $75/sq ft, site $10/sq ft, age $500/year).
ADJUSTMENT_FIELD = {
    "LivingUnitStandardFinishedAreaAboveGrade": "SF_GLA_ADJ",
    "SiteSize": "ST_SITSIZE_ADJ",
    "YearBuilt": "YR_BLT_ADJ",
}

#: Adjustment fields TOTAL works out for itself; left alone.
COMPUTED = re.compile(r"^GC\d_NETADJ")


@dataclass
class Answer:
    """What to put in a field, and why -- so the run can be read back.

    ``parts`` is for a cell that prints a sentence assembled from a popup:
    "Garage | 1 | Detached<br>150 Sq. Ft." is not a value you can type, it is
    what TOTAL prints once the popup behind it holds Garage, 1, Detached and
    150.  The validator reads the popup, so an answer for one of those rows
    carries the parts it is made of, addressed by their own field names.
    """
    value: str
    why: str
    parts: dict = _field(default_factory=dict)


@dataclass
class Outcome:
    rounds: int = 0
    before: int = 0
    after: int = 0
    filled: list = _field(default_factory=list)
    cleared: int = 0
    unanswered: list = _field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.before} finding(s) at the start, {self.after} at the end, "
                f"over {self.rounds} pass(es); {len(self.filled)} filled, "
                f"{self.cleared} stray adjustment(s) cleared, "
                f"{len(self.unanswered)} unanswered")


def clear_adjustments(report, case_adjustments: dict) -> int:
    """Empty every adjustment cell, then put back the ones the file states.

    ``case_adjustments`` is {column number: {ComparableAdjustmentType: amount}}.
    """
    writes = []
    for problem in _all_adjustment_fields(report):
        if COMPUTED.match(problem):
            continue
        writes.append({"field": problem, "instance": 0, "value": ""})
    keep = []
    for column, kinds in case_adjustments.items():
        for kind, amount in kinds.items():
            name = ADJUSTMENT_FIELD.get(kind)
            if not name or not amount:
                continue
            keep.append({"field": f"GC{column}_{name}", "instance": 0,
                         "value": _money(amount)})
    if writes:
        rtv.write(report, writes)
    if keep:
        rtv.write(report, keep)
    return len(writes)


def _money(amount) -> str:
    value = int(str(amount).replace(",", "").replace("$", ""))
    return f"$({abs(value):,})" if value < 0 else f"${value:,}"


_FIELDS = r"""(() => {
  const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const out = [];
  const walk = o => { for (const x of (o.dataObjects || [])) {
      const k = x.key || '';
      if (/^GC\d_.*_ADJ$/.test(k) && String(x.value || '').trim()) out.push(k);
      walk(x); } };
  walk({dataObjects: d.dataObjects});
  return out;
})()"""


def _all_adjustment_fields(report) -> list:
    return report.page.evaluate(_FIELDS) or []


def fix(report, answer, *, rounds: int = 6, progress=None) -> Outcome:
    """Answer what TOTAL reports, then ask it again.

    ``answer(problem)`` returns an :class:`Answer` or None.  Nothing decides a
    value here: that judgement belongs to the caller, which knows the case.
    """
    out = Outcome()
    seen = set()

    for attempt in range(1, rounds + 1):
        problems = rtv.problems(report)
        if attempt == 1:
            out.before = len(problems)
        out.rounds, out.after = attempt, len(problems)
        if not problems:
            break

        writes = []
        for problem in problems:
            key = f"{problem.field}#{problem.instance}"
            decided = answer(problem)
            if decided is None:
                if key not in seen:
                    seen.add(key)
                    out.unanswered.append((key, problem.friendly, problem.message))
                continue
            writes.append({"field": problem.field, "instance": problem.instance,
                           "value": decided.value})
            for part, value in (decided.parts or {}).items():
                writes.append({"field": part, "instance": problem.instance,
                               "value": value})
            if key not in seen:
                seen.add(key)
                out.filled.append((key, decided.value, decided.why))
                if progress:
                    progress(key, decided.value, decided.why)
        if not writes:
            break
        rtv.write(report, writes)

    out.after = rtv.run(report)
    return out
