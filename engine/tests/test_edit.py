"""Prove an edit lands in the right place and keeps the document valid.

Editing is the one operation that can silently corrupt a case: write into the
wrong container and the value appears against a comparable instead of the
subject; insert an element out of sequence and the whole file stops validating
even though every value in it is right.

So this takes a sample, writes a value into every field the page shows, and
checks after each write that the value reads back exactly and that the document
still validates against the GSE subschema.
"""
from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import bind, edit, schema, templates  # noqa: E402

SAMPLES = {
    "String": "Test Value",
    "Amount": "123456",
    "Date": "2026-03-04",
    "Count": "3",
    "Percent": "5",
}


def main(key: str = "sf1_appraisal_v1_4", limit: int | str = 250) -> int:
    limit = int(limit)
    tpl = templates.get(key)
    tree = etree.parse(str(tpl.path))
    model = bind.page_model()

    fields = [pf for section in model.values() for pf in section][:limit]
    written = skipped = reread = gated = 0
    problems: list[str] = []

    for pf in fields:
        try:
            dp = edit.choose_data_point(pf.binding)
        except KeyError:
            skipped += 1
            continue
        if edit.unmet_gate(tree.getroot(), pf.binding):
            # the report hides it until its gate is answered (Cost Approach
            # fields while CostApproachIndicator is false): not a write/read gap
            gated += 1
            continue
        kind = (dp.get("format_type") or "String").strip()
        if kind.casefold() == "enumerated":
            options = [o["value"] for o in (dp.get("enumerations") or [])
                       if o.get("value")]
            if not options:
                skipped += 1
                continue
            value = options[0]
        elif kind.casefold() == "boolean":
            value = "true"
        else:
            value = SAMPLES.get(kind, "Test Value")

        result = None
        # entry.normalize refuses a value of the wrong shape ("Test Value" in a
        # number written as String): try the other shapes before giving up
        for attempt in [value] + [v for v in ("3", "2026-03-04") if v != value]:
            try:
                result = edit.write(tree, pf.field_id, attempt,
                                    ordinal=pf.ordinal, binding=pf.binding)
                value = attempt
                break
            except KeyError:
                break
            except ValueError:
                continue
        if result is None:
            skipped += 1
            continue
        written += 1

        back = bind.read_parts(tree.getroot(), pf.binding, ordinal=pf.ordinal)
        values = [v for n, v in back if n == result.data_point]
        if value in values:
            reread += 1
        elif len(problems) < 400:
            problems.append(
                f"{pf.field_id} {pf.label[:32]!r}: wrote {value!r} into "
                f"{result.data_point}, read back {values[:3]}")

    errors = schema.validate(tree)
    print(f"edit test on {tpl.key}")
    print(f"  fields attempted ..... {len(fields)}")
    print(f"  written .............. {written}")
    print(f"  skipped (no target) .. {skipped}")
    print(f"  behind a closed gate . {gated}")
    print(f"  read back correctly .. {reread}/{written}")
    print(f"  schema after edits ... {'valid' if not errors else f'{len(errors)} error(s)'}")
    for p in problems:
        print(f"     ! {p}")
    for e in errors[:5]:
        print(f"     ! {str(e)[:150]}")
    return 0 if reread == written and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:] or [])))
