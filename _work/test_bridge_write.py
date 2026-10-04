"""Does a bridge write reach the report, or only the screen?

The test writes a marker into one commentary field, asks the engine to
serialise the report to MISMO, and looks for the marker in that XML -- the XML
is what TOTAL would deliver, so finding it there is proof the value reached the
data layer and not merely the DOM.  The original value is put back either way.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from total_bridge import Total

MARKER = "BRIDGE-WRITE-TEST-8842"

total = Total.attach()
try:
    fields = total.fields()
    print(f"section has {len(fields)} controls")

    # A commentary field is the safest target: free text, no calculations hang
    # off it, and it is easy to restore exactly.
    target = next((k for k in fields if "COMMENT" in k or "RECONCILE" in k), None)
    if target is None:
        target = next(iter(fields))
    fn, inst = target.rsplit("[", 1)
    inst = int(inst.rstrip("]"))
    original = total.get(fn, inst)
    print(f"target : {fn}[{inst}]")
    print(f"before : {original!r}")

    result = total.set(fn, MARKER, inst)
    print(f"write  : {result}")
    print(f"reads  : {total.get(fn, inst)!r}")

    print("\nserialising the report through the engine ...")
    xml = total.mismo()
    landed = MARKER in xml
    print(f"  {len(xml):,} chars of MISMO")
    print(f"  marker present in the delivered XML: {landed}")

    restored = total.set(fn, original or "", inst)
    print(f"\nrestored -> {total.get(fn, inst)!r}")

    print("\nRESULT:", "the bridge writes real data" if landed
          else "the write did NOT reach the report data")
finally:
    total.close()
