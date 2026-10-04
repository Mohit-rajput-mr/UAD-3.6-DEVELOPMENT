"""T-925: filling from a source with more comparables leaves an empty column."""
import sys
sys.path.insert(0, "engine")
from pathlib import Path

from lxml import etree

from uad import bind, templates
from uad.report import comparables
from app import autofill

SRC = Path("_work/reference/urar_18_north/mismo.xml")


def cols(tree_or_root, label):
    root = tree_or_root.getroot() if hasattr(tree_or_root, "getroot") else tree_or_root
    tree = root.getroottree()
    print(f"  {label}:")
    for kind, (_s, role, _sec) in comparables.SHEETS.items():
        props = comparables.properties(root, role)
        if props:
            print(f"    {kind:<8} {len(props):>2}  "
                  f"{[tree.getelementpath(p).split('/')[-1] for p in props]}")


target = templates.load("sf1_appraisal_v1_4", blank=True)
source = etree.parse(str(SRC)).getroot()

cols(target, "target BEFORE")
cols(source, "source")

steps = autofill.plan(target, source)
comp_steps = [s for s in steps if s.kind == autofill.COMP]
print(f"\nsteps: {len(steps)}   COMP steps: {len(comp_steps)} "
      f"-> {[(s.comp_kind, s.column) for s in comp_steps]}")

result = autofill.apply(target, steps, source=source)
print(f"apply: written={result['written']} failed={len(result['failed'])} "
      f"dropped={result['dropped']}")
for f in result["failed"][:5]:
    print("   fail:", f["reason"])

cols(target, "target AFTER")

# which comparables ended up empty?
print("\n  empty comparable columns:")
for kind, (_s, role, _sec) in comparables.SHEETS.items():
    for n, prop in enumerate(comparables.properties(target, role), start=1):
        values = [e for e in prop.iter()
                  if isinstance(e.tag, str) and not len(e) and (e.text or "").strip()]
        if len(values) < 3:
            print(f"    {kind} #{n}: only {len(values)} value(s) -- EMPTY COLUMN")
