"""Validate the compliance engine against the official Appendix D-1 samples.

The twelve GSE samples are compliant by construction -- they are what the
specification publishes as correct.  So any rule this engine fires on an
untouched sample is a rule whose translation from H-1's English is wrong.

This prints the offending rules ranked by how many samples they fire on, which
is the order they should be fixed in: a rule firing on all twelve is a
systematic misreading, one firing on a single sample is usually a scoping
mistake.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import compliance, templates  # noqa: E402


def main(limit: int = 30) -> int:
    cat = templates.catalogue()
    fires: Counter = Counter()
    where: dict[str, list[str]] = defaultdict(list)
    detail: dict[str, compliance.Finding] = {}
    totals = {}

    for tpl in cat:
        tree = etree.parse(str(tpl.path))
        findings = compliance.evaluate(tree)
        hits = [f for f in findings if f.status == compliance.FINDING]
        totals[tpl.key] = len(hits)
        for f in hits:
            fires[f.message_id] += 1
            where[f.message_id].append(tpl.key)
            detail.setdefault(f.message_id, f)

    rs = compliance.rules()
    executable = sum(1 for r in rs if r.executable)
    print(f"{len(rs)} rules, {executable} executable, run against "
          f"{len(cat)} official samples\n")

    for key, n in totals.items():
        mark = "clean" if n == 0 else f"{n} false findings"
        print(f"  {key:<40} {mark}")

    print(f"\n{len(fires)} distinct rules fire on at least one official sample "
          f"(each is an engine defect):\n")
    for mid, n in fires.most_common(limit):
        f = detail[mid]
        rule = next(r for r in rs if r.message_id == mid)
        conds = " ; ".join(str(c) for c in rule.antecedent.conditions()) or "(always)"
        print(f"  {mid}  fires on {n:>2}/{len(cat)}  [{f.severity}] "
              f"needs={f.data_point} roles={rule.roles or '-'}")
        print(f"      if: {conds}")
        print(f"      path : {rule.container_path}")
        print(f"      logic: {rule.logic[:160]}")
    return 0 if not fires else 1


if __name__ == "__main__":
    raise SystemExit(main())
