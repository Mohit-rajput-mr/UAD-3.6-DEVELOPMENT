"""Counted findings whose field the editor draws no control for (T-505 input).

    python _work/audit/unreachable_findings.py [template ...]      (~3 min for 12)

For each D-1 sample, full and as a blank report: every Review Master
compliance finding that counts (Fatal / Warning) whose field_id has no
data-fid / data-tf / data-gf / data-gaf in the editor's own markup.  The
Summary's redisplays (1.xxx) are left out: they always have to jump to their
source field.  Each line printed needs a route to its real control (rooms
drawer, client-role, sketch, certifications, computed rent totals), or the
problems panel's click goes nowhere.

2026-10-11 (epic-brahmagupta, on production 31b0644): full samples 0; blank
reports 19-25 each, the same ~20 field IDs throughout.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine"))

from uad import review, templates  # noqa: E402
from uad.report import form  # noqa: E402

ATTR = re.compile(r"""data-(?:fid|tf|gf|gaf)=["']([0-9.]+)["']""")


def drawn(tree) -> set[str]:
    return set(ATTR.findall(form.galley_html(form.build(tree, edit=True), edit=True)))


def main(keys: list[str]) -> int:
    for key in keys or [t.key for t in templates.catalogue()]:
        for blank in (False, True):
            tree = templates.load(key, blank=blank)
            shown = drawn(tree)
            counted = [i for i in review.build(tree).items
                       if i.severity in ("Fatal", "Warning") and i.source == "compliance"]
            missing = collections.Counter(
                (i.code, i.field_id, (i.section or "")[:30]) for i in counted
                if i.field_id and (i.section or "").strip() != "Does Not Display"
                and i.field_id not in shown and not i.field_id.startswith("1."))
            print(f"{key:38s} {'blank' if blank else 'full '} counted={len(counted):4d} "
                  f"unreachable={sum(missing.values())} {sorted(missing)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
