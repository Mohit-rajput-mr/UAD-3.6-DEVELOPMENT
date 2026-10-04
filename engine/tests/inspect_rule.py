"""Show what a rule actually sees in a sample, to settle why it fires.

Prints each instance the rule is scoped to, the value of every condition as
resolved from that instance, and whether the required data point is present --
so a disagreement between the engine and a GSE sample can be read off rather
than guessed at.
"""
from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import compliance, templates  # noqa: E402


def show(message_id: str, sample_key: str, limit: int = 6) -> None:
    rule = next(r for r in compliance.rules() if r.message_id == message_id)
    tpl = templates.get(sample_key)
    tree = etree.parse(str(tpl.path))
    scope = compliance.Scope(tree.getroot())

    print(f"{message_id}  [{rule.severity}]  on {tpl.key}")
    print(f"  logic  : {rule.logic}")
    print(f"  path   : {rule.container_path}")
    print(f"  needs  : {rule.requires or (rule.data_point,)}")
    print(f"  roles  : {rule.roles or '(any)'}")
    print(f"  parsed : {_render(rule.antecedent)}")

    instances = scope.resolve_path(rule.container_path)
    print(f"  {len(instances)} instance(s) of the scoped container\n")
    for i, inst in enumerate(instances[:limit]):
        role = scope.property_role(inst)
        applies = (not rule.roles) or role in rule.roles
        held = compliance.holds(rule.antecedent, scope, inst)
        sel = compliance.selects(rule.antecedent, scope, inst)
        wanted = rule.requires or (rule.data_point,)
        present = any(compliance._present(scope, inst, n) for n in wanted)
        print(f"   [{i}] role={role} in-role={applies} holds={held} "
              f"selects={sel} present={present}")
        for cond in dict.fromkeys(str(c) for c in rule.antecedent.conditions()):
            pass
        for cond in rule.antecedent.conditions():
            got = compliance._value(scope, inst, cond)
            local = inst.find(f".//{{{compliance.MISMO}}}{cond.name}") is not None
            print(f"        {str(cond):<66} -> {got!r}{'  [local]' if local else ''}")
        kids = [etree.QName(k).localname for k in inst]
        print(f"        children: {kids[:12]}")


def _render(expr: compliance.Expr) -> str:
    if expr.op == "true":
        return "(always)"
    if expr.op == "leaf":
        return str(expr.condition)
    joiner = f" {expr.op.upper()} "
    return "(" + joiner.join(_render(c) for c in expr.children) + ")"


if __name__ == "__main__":
    show(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 6)
