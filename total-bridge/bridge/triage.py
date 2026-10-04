"""Sort TOTAL's field validation errors by *what each one actually needs*.

A raw count is not useful on its own.  Ninety errors can be eighty that a
script can close and ten that need the appraiser to go and look at something,
and those two are worth knowing apart before any of them is touched.  This
reads the list TOTAL already gives -- each row carries the field, what it
holds, whether it is on screen, and the exact options the control accepts --
and puts every row in one of five buckets:

``answerable``
    The control offers a way to say what is true and the value is simply
    missing.  Chief case: an option list that carries its own ``None`` /
    ``No`` / ``Not Applicable``.  A script can close these.

``gated``
    The message says the field is required *because of another field* -- "is
    required when physical depreciation is checked", "required based on
    related selections".  The fix is not here; it is the thing that switched
    it on.  Chasing the named field instead of its gate is how a report ends
    up with invented depreciation on an excluded cost approach.

``structural``
    A block that should not exist at all: a supervisory appraiser on a
    report that has none, an empty revision row.  ``HIDDEN_..._COUNT`` fields
    are *outputs* of the repeat state, so writing them does nothing -- these
    need the section's own add/remove control through ``bridge.ui``.

``needs_data``
    A measured or published fact the file does not contain: a photograph, a
    distance, an area, a price, a date, an identifier.  **No script should
    fill these.**  They belong on the handback.

``blocked``
    The control has a closed option list and *none of its options is true*.
    The classic shape is a list of positive conditions -- easements, drainage
    defects, water influences -- with no "none" to choose.  Writing one would
    assert a condition nobody observed, so the answer is a companion
    indicator elsewhere, or the appraiser.

The point of the split is the last two: ``needs_data`` and ``blocked`` are the
rows a fill loop should stop on rather than guess at.
"""
from __future__ import annotations

import re
from collections import defaultdict

#: How a control says "there is none of this".  Checked against the options
#: the control actually offers, never assumed.
NONE_WORDS = ("none", "no", "none noted", "not applicable", "n/a",
              "none observed", "no inspection")

#: Fields whose value is a measured or published fact.  If the file does not
#: carry it, nothing may invent it.
MEASURED = re.compile(
    r"(PHOTO|SKETCH|EXHIBIT|PROX|DISTANCE|DIRECTION|LATITUDE|LONGITUDE|"
    r"_GLA|AREA|SF_|SQUARE_FEET|GBFA|PRICE|SALEPR|_AMOUNT|_DATE|DOM|"
    r"MLS_NUM|ASSESSOR_ID|_ID$|APN|YR_BLT|EFFECTIVE_AGE|ECONOMIC_LIFE|"
    r"VALUE_OPINION|SCMINDVALUE)")

#: A message that blames another field.
GATE_WORDS = re.compile(
    r"required when|required based on|is checked|is selected|"
    r"for the selected|related selection|when an? .* is entered|"
    r"when the .* option", re.I)

#: Blocks that exist but should not.
STRUCTURAL = re.compile(r"^(SUPERVISOR|SUPERVISORY|SRPA)_|^RN_REC_VAL|^HIDDEN_|_COUNT$")


def none_option(problem):
    """The control's own wording for "none", if it offers one."""
    for option in (problem.options or []):
        if str(option).strip().lower() in NONE_WORDS:
            return option
    return None


def classify(problem) -> tuple[str, str]:
    """Which bucket this row belongs in, and why."""
    name, message = problem.field, problem.message or ""

    if STRUCTURAL.search(name):
        return "structural", ("a block that should not exist; remove it with "
                              "the section's own control, not by writing a count")

    exit_option = none_option(problem)
    if exit_option is not None and not str(problem.value or "").strip():
        return "answerable", f"the control offers {exit_option!r}"

    if GATE_WORDS.search(message):
        return "gated", "required by another field; fix that one instead"

    if problem.options:
        return "blocked", ("the option list carries no way to say none: "
                           + " | ".join(problem.options[:6]))

    if MEASURED.search(name):
        return "needs_data", "a measured or published fact; it cannot be inferred"

    return "answerable", "free text"


def triage(problems) -> dict:
    """Group a problem list into the five buckets, each row with its reason."""
    out = defaultdict(list)
    for p in problems:
        bucket, why = classify(p)
        out[bucket].append((p, why))
    return dict(out)


ORDER = ("answerable", "gated", "structural", "blocked", "needs_data")


def summary(problems) -> str:
    """One line per bucket -- what can be closed and what cannot."""
    buckets = triage(problems)
    parts = [f"{len(buckets.get(b, []))} {b}" for b in ORDER]
    return f"{len(problems)} problems: " + ", ".join(parts)


def explain(problems, *, limit: int = 12) -> str:
    """The full picture, in the order worth working it."""
    buckets = triage(problems)
    lines = [summary(problems), ""]
    for bucket in ORDER:
        rows = buckets.get(bucket, [])
        if not rows:
            continue
        lines.append(f"## {bucket} ({len(rows)})")
        seen = set()
        for p, why in rows:
            base = (p.field.split("_", 1)[-1]
                    if p.field.startswith(("GC", "GR")) else p.field)
            if base in seen:
                continue
            seen.add(base)
            if len(seen) > limit:
                lines.append(f"   ... and {len(rows) - limit} more")
                break
            lines.append(f"   {p.field:42} {why}")
        lines.append("")
    return "\n".join(lines)


def answerable_writes(problems) -> list[dict]:
    """The writes that close every row a control can answer by itself.

    Only rows whose control offers its own "none": that is the one case where
    the true answer is known without consulting the file.  Everything else is
    left for a sourced answer or the handback.
    """
    writes = []
    for p, _ in triage(problems).get("answerable", []):
        option = none_option(p)
        if option is not None:
            writes.append({"field": p.field, "instance": p.instance,
                           "value": option})
    return writes
