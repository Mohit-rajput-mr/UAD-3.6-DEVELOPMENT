"""Classify the 728 H-1 compliance rules by the shape of their Rule Logic.

The rules are written in a controlled English that is regular enough to
execute, but not uniformly so.  Before writing an evaluator, this counts how
many rules fall into each grammatical shape, so the engine can be built for the
shapes that actually occur and can say honestly how many it does not cover.

Nothing here decides a rule's outcome.  It only sorts the rule text.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

SPEC = Path(__file__).resolve().parents[2] / "spec"

# The consequent -- what makes the rule fire.
SHAPES = (
    ("not_provided",   re.compile(r"\bis not provided\b", re.I)),
    ("provided",       re.compile(r"\bis provided\b", re.I)),
    ("not_unique",     re.compile(r"\bis not unique\b", re.I)),
    ("not_equal",      re.compile(r"\b(?:does not equal|is not equal to)\b", re.I)),
    ("not_in_set",     re.compile(r"\bis not (?:one of|in)\b", re.I)),
    ("greater_less",   re.compile(r"\bis (?:greater|less) than\b", re.I)),
    ("format",         re.compile(r"\b(?:format|does not match)\b", re.I)),
    ("count",          re.compile(r"\b(?:count|number) of\b", re.I)),
    ("duplicate",      re.compile(r"\bduplicat", re.I)),
    ("selected",       re.compile(r"\bis selected\b", re.I)),
)

COND = re.compile(r'(\w[\w.@]*)\s*(=|<>|!=)\s*"([^"]*)"')
INSTANCE = re.compile(r"\bin a given instance of ([A-Z_]+)", re.I)
ACROSS = re.compile(r"\bacross all instances of ([A-Z_]+)", re.I)


def load() -> list[dict]:
    return json.loads((SPEC / "compliance_rules.json").read_text(encoding="utf-8"))


def classify(logic: str) -> list[str]:
    return [name for name, pat in SHAPES if pat.search(logic)] or ["unclassified"]


def main() -> None:
    rules = load()
    shapes = Counter()
    combos = Counter()
    by_shape: dict[str, list[dict]] = defaultdict(list)
    conditions = Counter()
    severity_by_shape: dict[str, Counter] = defaultdict(Counter)
    has_format = Counter()

    for r in rules:
        logic = " ".join(str(r.get("Rule Logic") or "").split())
        found = classify(logic)
        combos[tuple(found)] += 1
        for name in found:
            shapes[name] += 1
            by_shape[name].append(r)
            severity_by_shape[name][r.get("Severity")] += 1
        for _dp, _op, _val in COND.findall(logic):
            conditions[_dp] += 1
        for col in ("Date Format", "Number Format", "Min Value", "Max Value",
                    "Related Value(s)"):
            if str(r.get(col) or "").strip():
                has_format[col] += 1

    total = len(rules)
    print(f"{total} compliance rules\n")
    print("consequent shape           rules   Fatal  Warning")
    for name, n in shapes.most_common():
        sev = severity_by_shape[name]
        print(f"  {name:<22} {n:>6}  {sev.get('Fatal', 0):>6} {sev.get('Warning', 0):>7}")

    print("\ncombinations of shapes in one rule:")
    for combo, n in combos.most_common(10):
        print(f"  x{n:<5} {' + '.join(combo)}")

    unclassified = by_shape.get("unclassified", [])
    print(f"\nunclassified: {len(unclassified)}")
    for r in unclassified[:12]:
        logic = " ".join(str(r.get("Rule Logic") or "").split())
        print(f"  {r.get('Message ID', '?'):<10} {logic[:104]}")

    print("\nsupporting columns populated:")
    for col, n in has_format.most_common():
        print(f"  {col:<20} {n}")

    print("\nmost-referenced data points in conditions:")
    for dp, n in conditions.most_common(12):
        print(f"  {dp:<48} x{n}")

    print("\ninstance scoping:")
    print(f"  'in a given instance of X' .... "
          f"{sum(1 for r in rules if INSTANCE.search(str(r.get('Rule Logic') or '')))}")
    print(f"  'across all instances of X' ... "
          f"{sum(1 for r in rules if ACROSS.search(str(r.get('Rule Logic') or '')))}")

    with_xpath = sum(1 for r in rules if str(r.get("xPath") or "").strip())
    with_uid = sum(1 for r in rules if str(r.get("Unique ID") or "").strip())
    print(f"\n  rules carrying an xPath ....... {with_xpath}/{total}")
    print(f"  rules carrying a Unique ID .... {with_uid}/{total}")


if __name__ == "__main__":
    main()
