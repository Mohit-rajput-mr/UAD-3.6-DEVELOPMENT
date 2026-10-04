"""Filling a TOTAL report from a UAD 3.6 file, and checking the result.

The mapping between the two sides is not stored anywhere.  TOTAL stamps each
of its controls with the Report Field ID it holds, so the bridge reads that at
run time and pairs it with the same ID in the file.  Nothing to maintain, and
nothing to go stale when a la mode change the form.

Which column a control belongs to is in its own name: ``GSU_`` is the subject,
``GC1_``/``GC2_``/``GC3_`` the comparables.  Fields outside a grid carry no
prefix and are read from the document as a whole.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field as _field

from .mismo import Case
from .total import Report

COLUMN = re.compile(r"^G(?:(SU)|C(\d+))_")

# Controls that hold no value of their own.
SKIP_KINDS = {"image", "readonly"}


def column_of(fn: str) -> int | None:
    """0 for the subject column, N for a comparable, None when not in a grid."""
    m = COLUMN.match(fn)
    if not m:
        return None
    return 0 if m.group(1) else int(m.group(2))


@dataclass
class Outcome:
    written: int = 0
    unchanged: int = 0
    empty: int = 0
    refused: list = _field(default_factory=list)
    mismatched: list = _field(default_factory=list)
    no_value: list = _field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.written} written, {self.unchanged} already correct, "
                f"{self.empty} not in the file, "
                f"{len(self.refused)} refused, {len(self.mismatched)} did not hold")


def plan(case: Case, report: Report, *, sections=None) -> list[dict]:
    """What this file has to say about the controls this report has.

    Walks the report section by section: the form builds only the section it
    is showing, so a control nobody has looked at does not exist in the page
    and cannot be filled.  A control seen in more than one section is kept
    once.
    """
    jobs, seen = [], set()
    wanted = set(sections) if sections else None
    for key, controls, _values in report.walk():
        if wanted and key not in wanted:
            continue
        for control in controls:
            fn, fmid = control["fn"], control["fmid"]
            if fn.startswith("LABEL_") or not fmid:
                continue
            if control["kind"] in SKIP_KINDS:
                continue
            ident = (fn, control["instance"])
            if ident in seen:
                continue
            seen.add(ident)
            column = column_of(fn)
            jobs.append({**control, "section": key, "column": column,
                         "value": case.display(fmid, column),
                         "pick": case.is_enumerated(fmid)
                                 and control["kind"] != "checkbox"})
    return jobs


def run(case: Case, report: Report, *, dry_run: bool = False,
        progress=None) -> Outcome:
    """Fill the report, reading every write back."""
    out = Outcome()
    jobs = plan(case, report)
    # Fill a section at a time, in the order the report presents them: a
    # control can only be written while its section is the one being shown.
    jobs.sort(key=lambda j: (j.get("section") or "", j["fn"]))
    here, live = None, {}

    for n, job in enumerate(jobs, 1):
        fn, inst, value = job["fn"], job["instance"], job["value"]
        if job.get("section") and job["section"] != here:
            here = job["section"]
            report.goto(here)
            live = report.values()
        key = f"{fn}[{inst}]"
        current = (live.get(key) or "").strip()

        if not value:
            out.empty += 1
            out.no_value.append((job["fmid"], fn))
            continue
        if current == value.strip():
            out.unchanged += 1
            continue
        if dry_run:
            out.written += 1
            if progress:
                progress(n, len(jobs), fn, value, "would set")
            continue

        result = (report.pick(fn, value, int(inst)) if job.get("pick")
                  else report.set(fn, value, int(inst)))
        if not result.get("ok"):
            out.refused.append((job["fmid"], fn, result.get("why", "")))
            if progress:
                progress(n, len(jobs), fn, value, f"refused: {result.get('why')}")
            continue
        # What the control kept, not what we sent.
        got = (result.get("got") or "").strip()
        if got != value.strip():
            out.mismatched.append((job["fmid"], fn, value, got))
            if progress:
                progress(n, len(jobs), fn, value, f"did not hold -> {got!r}")
        else:
            out.written += 1
            if progress:
                progress(n, len(jobs), fn, value, "set")
    return out


def verify(case: Case, report: Report) -> dict:
    """Compare what TOTAL would deliver against the source file.

    This asks the engine to serialise its own report, so the comparison is
    against what TOTAL kept rather than against what the bridge believes it
    typed.
    """
    delivered = report.mismo()
    report.render_all(settle=1.0)
    rows = []
    for control in report.controls():
        fmid, fn = control["fmid"], control["fn"]
        if not fmid or fn.startswith("LABEL_") or control["kind"] in SKIP_KINDS:
            continue
        raw = case.value(fmid, column_of(fn))
        if not raw:
            continue
        # The delivery carries the document's own code, not the form's wording.
        rows.append({"fmid": fmid, "fn": fn, "wanted": raw,
                     "shown": case.display(fmid, column_of(fn)),
                     "in_delivery": raw in delivered})
    held = sum(1 for r in rows if r["in_delivery"])
    return {"checked": len(rows), "confirmed": held,
            "missing": [r for r in rows if not r["in_delivery"]],
            "delivered_chars": len(delivered)}
