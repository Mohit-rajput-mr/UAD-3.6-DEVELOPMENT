"""Prove the compliance engine detects real defects, not just that it is quiet.

A checker that passes everything passes the twelve official samples too, so
silence on those samples means nothing on its own.  This takes a compliant
sample and breaks it, one rule at a time, in the way that rule is meant to
catch:

  presence     delete the required value
  range        push a supplied value past the published bound
  date_format  rewrite a supplied date in the wrong shape
  uniqueness   duplicate an identifier that must be unique
  cardinality  clone a container that may appear only once

Deleting a value is the wrong test for a uniqueness rule -- with nothing left
there are no duplicates -- so each kind gets the mutation that actually
violates it.  A rule is only tested where it already applies to the sample;
otherwise silence afterwards is the correct answer, not a miss.
"""
from __future__ import annotations

import copy
import sys
from collections import Counter
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import compliance, templates  # noqa: E402

MISMO = compliance.MISMO
TAG = f"{{{MISMO}}}%s"


def findings(tree) -> set[str]:
    return {f.message_id for f in compliance.evaluate(tree)
            if f.status == compliance.FINDING}


def _instances(scope, rule):
    container = [c for c in rule.container_path.strip("/").split("/")
                 if c and c != ".."]
    local = scope.instance_names(container[-1]) if container else frozenset()
    for inst in scope.resolve_path(rule.container_path):
        if rule.roles and scope.property_role(inst) not in rule.roles:
            continue
        if not compliance.holds(rule.antecedent, scope, inst, local):
            continue
        if not compliance.selects(rule.antecedent, scope, inst, local):
            continue
        yield inst


def _applies(scope, rule) -> bool:
    """Does this rule already have something to say about this sample?"""
    if rule.kind == compliance.PRESENCE:
        # A rule whose own data point appears in its condition cannot be
        # tested by deleting that value -- removing it also removes the
        # reason the rule applied.
        if any(c.name == rule.data_point for c in rule.antecedent.conditions()):
            return False
        return any(inst.find(TAG % rule.data_point) is not None
                   for inst in _instances(scope, rule))
    if rule.kind in (compliance.RANGE, compliance.DATE_FORMAT):
        return bool(compliance._values_in(scope, rule))
    if rule.kind == compliance.UNIQUENESS:
        container = rule.unique_container or rule.instance_of
        return len(scope.by_name.get(container, [])) >= 1
    if rule.kind == compliance.CARDINALITY:
        return bool(scope.by_name.get(rule.count_container))
    return False


def mutate(tree, rule) -> str:
    """Break the document the way this rule is meant to catch."""
    scope = compliance.Scope(tree.getroot())

    if rule.kind == compliance.PRESENCE:
        # Where a rule accepts either of two values, both have to go: deleting
        # one leaves the requirement satisfied by the other.
        wanted = rule.requires or (rule.data_point,)
        n = 0
        for inst in list(_instances(scope, rule)):
            for name in wanted:
                for node in inst.findall(TAG % name):
                    node.getparent().remove(node)
                    n += 1
        return f"deleted {n} value(s)" if n else ""

    if rule.kind == compliance.RANGE:
        n = 0
        for inst, _text in compliance._values_in(scope, rule):
            for node in inst.iter(TAG % rule.data_point):
                if rule.minimum is not None:
                    node.text = str(int(rule.minimum) - 1)
                elif rule.maximum is not None:
                    node.text = str(int(rule.maximum) + 1)
                n += 1
        return f"pushed {n} value(s) out of bounds" if n else ""

    if rule.kind == compliance.DATE_FORMAT:
        n = 0
        for inst, _text in compliance._values_in(scope, rule):
            for node in inst.iter(TAG % rule.data_point):
                node.text = "01/02/2026"
                n += 1
        return f"rewrote {n} date(s)" if n else ""

    if rule.kind == compliance.UNIQUENESS:
        # Both copies must sit in a property the rule applies to, and in the
        # same property, since uniqueness is judged per property.
        container = rule.unique_container or rule.instance_of
        holders = [i for i in scope.by_name.get(container, [])
                   if i.find(TAG % rule.unique_name) is not None
                   and (not rule.roles or scope.property_role(i) in rule.roles)]
        for i, first in enumerate(holders):
            for other in holders[i + 1:]:
                if compliance._group(scope, other) != compliance._group(scope, first):
                    continue
                other.find(TAG % rule.unique_name).text = (
                    first.find(TAG % rule.unique_name).text or "").strip()
                return f"duplicated {rule.unique_name}"
        return ""

    if rule.kind == compliance.CARDINALITY:
        # Clone an instance the rule would actually count: one in a property of
        # the right role whose own condition holds.  Cloning any other instance
        # tests nothing, because the rule filters it out before counting.
        local = scope.instance_names(rule.count_container)
        for target in scope.by_name.get(rule.count_container, []):
            if rule.roles and scope.property_role(target) not in rule.roles:
                continue
            if rule.count_condition is not None and not compliance.holds(
                    rule.count_condition, scope, target, local):
                continue
            parent = target.getparent()
            if parent is None:
                continue
            parent.insert(list(parent).index(target) + 1, copy.deepcopy(target))
            return f"cloned a qualifying {rule.count_container}"
        return ""
    return ""


def main(sample: str = "sf1_appraisal_v1_4", limit: int | str = 60) -> int:
    limit = int(limit)
    tpl = templates.get(sample)
    original = etree.parse(str(tpl.path))
    base = findings(original)
    scope = compliance.Scope(original.getroot())

    print(f"mutation test on {tpl.key}")
    print(f"  baseline findings: {len(base)}\n")

    candidates = [r for r in compliance.rules()
                  if r.executable
                  and compliance._NAME.match(r.data_point or "x")
                  and _applies(scope, r)][:limit]

    detected, missed, skipped = 0, [], 0
    by_kind: Counter = Counter()
    hit_kind: Counter = Counter()
    for rule in candidates:
        tree = copy.deepcopy(original)
        note = mutate(tree, rule)
        if not note:
            skipped += 1
            continue
        by_kind[rule.kind] += 1
        now = findings(tree)
        if rule.message_id in now:
            detected += 1
            hit_kind[rule.kind] += 1
        else:
            missed.append((rule, note))

    tested = sum(by_kind.values())
    print(f"  {tested} rules mutated, {skipped} not mutable in this sample\n")
    for kind in sorted(by_kind):
        print(f"    {kind:<16} {hit_kind[kind]:>3}/{by_kind[kind]:<3} detected")
    for rule, note in missed:
        print(f"\n  MISSED {rule.message_id} [{rule.kind}] {note}")
        print(f"     {rule.logic[:140]}")
    print(f"\n{detected}/{tested} deliberate violations detected")
    return 0 if detected == tested else 1


if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:] or [])))
