"""Clear TOTAL's own field validation errors, and the ones that follow.

The loop is the point.  A validator is not a fixed list: answering one field
turns others on -- ticking "the property is in a project" asks for the project
name, the monthly charge and the units rented; choosing a listing status asks
for the listing type.  TOTAL's own ``dependantFields`` say so.  So a single
pass over the errors, however complete, leaves the report with a fresh set of
them that nobody looked at.

    sweep -> answer what can be answered -> sweep again -> ...

until a pass changes nothing.  What is still failing at that point is
reported: either a field the file does not answer and no default is safe for,
or something TOTAL wants that the appraiser has to give.

Writing follows what the control is, not what the standard says it should be.
TOTAL draws several UAD fields differently from the way A-1 describes them --
the four highest-and-best-use answers are text boxes, not Yes/No -- so each
write is read back, and a value that did not hold is tried the other way
before being reported as refused.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _field

from . import expert, rooms, validate
from .fill import column_of


@dataclass
class Fixed:
    field: str
    fmid: str
    value: str
    source: str


@dataclass
class Outcome:
    fixed: list[Fixed] = _field(default_factory=list)
    refused: list[tuple[str, str, str]] = _field(default_factory=list)
    unanswered: list[tuple[str, str, str]] = _field(default_factory=list)
    rounds: int = 0
    before: int = 0
    after: int = 0

    def summary(self) -> str:
        lines = [f"{self.before} validation error(s) at the start, "
                 f"{self.after} at the end, over {self.rounds} pass(es)",
                 f"   filled     {len(self.fixed)}",
                 f"   refused    {len(self.refused)}",
                 f"   unanswered {len(self.unanswered)}"]
        return "\n".join(lines)


def _value_for(problem: validate.Problem, case) -> tuple[object, str]:
    """What this field should hold: the file first, then a safe default."""
    # A Yes/No pair: the file answers the question once, and that decides
    # which of the two boxes is ticked.
    pair = expert.pair(problem.field)
    if pair is not None and case is not None:
        field_id, is_yes = pair
        said = (case.display(field_id) or "").strip().lower()
        if said in ("yes", "true"):
            return (True, "the file") if is_yes else (False, "the file")
        if said in ("no", "false"):
            return (False, "the file") if is_yes else (True, "the file")

    if case is not None and problem.fmid:
        column = column_of(problem.field)
        try:
            from_file = case.display(problem.fmid, column)
        except Exception:                                   # noqa: BLE001
            from_file = ""
        if from_file:
            return from_file, "the file"
    return expert.answer(problem.field, case)


def _write(report, problem: validate.Problem, value) -> tuple[bool, str]:
    """Put the value in, and say whether the control kept it.

    A tick box is clicked, everything else is typed and then -- if typing did
    not hold -- chosen from the control's own list.  Which of the two works
    depends on how TOTAL drew that particular field, not on what kind of value
    the standard says it is.
    """
    instance = int(problem.instance or 0)
    if isinstance(value, bool):
        want = "true" if value else "false"
        result = report.set(problem.field, want, instance)
        return bool(result.get("ok")), str(result.get("why") or "")

    text = str(value)
    result = report.set(problem.field, text, instance)
    kept = (result.get("got") or "").strip()
    if result.get("ok") and kept and kept.lower() == text.strip().lower():
        return True, ""
    picked = report.pick(problem.field, text, instance)
    if picked.get("ok"):
        return True, ""
    return False, str(picked.get("why") or result.get("why") or "did not hold")


def fix(report, case, *, rounds: int = 4, progress=None) -> Outcome:
    """Answer everything that can be answered, then look again."""
    out = Outcome()
    seen_refused: set[str] = set()

    # Section rules the field validators never report: a kitchen in every unit.
    for done in rooms.ensure_kitchens(report):
        if done.get("did") == "added" and progress:
            progress(f"interior/unit {done['unit']} kitchen", "Kitchen",
                     "TOTAL requires one per living unit")

    for attempt in range(1, rounds + 1):
        sweep = validate.sweep(report, settle=0.9)
        if attempt == 1:
            out.before = len(sweep.problems)
        out.rounds = attempt
        out.after = len(sweep.problems)
        if not sweep.problems:
            break

        filled_here = 0
        for section, problems in sweep.by_section().items():
            report.goto(section, 0.9)
            for problem in problems:
                key = f"{problem.section}/{problem.field}"
                value, source = _value_for(problem, case)
                if value is None or value == "":
                    if key not in seen_refused:
                        seen_refused.add(key)
                        out.unanswered.append((key, problem.message, source))
                    continue
                ok, why = _write(report, problem, value)
                if ok:
                    filled_here += 1
                    out.fixed.append(Fixed(key, problem.fmid, str(value)[:60], source))
                    if progress:
                        progress(key, str(value)[:40], source)
                elif key not in seen_refused:
                    seen_refused.add(key)
                    out.refused.append((key, str(value)[:40], why))
        if not filled_here:
            break

    final = validate.sweep(report, settle=0.9)
    out.after = len(final.problems)
    return out
