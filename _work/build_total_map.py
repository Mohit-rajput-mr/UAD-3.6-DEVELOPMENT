"""Derive the mapping between our report fields and TOTAL's form controls.

Both systems key on the same thing.  Our field index is built from Appendix
A-1's Report Field IDs; TOTAL stamps each of its controls with the same ID in
an ``fmid`` attribute.  So the mapping is not written by hand -- it is read off
the two indexes, which is what makes it survive a TOTAL update.

A control's ``fn`` name also says which column of a grid it belongs to:
``GSU_`` is the subject, ``GC1_``/``GC2_``/``GC3_`` the comparables.  The same
field ID therefore appears once per column, and the column has to be carried
alongside it.
"""
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, "engine")

from uad import bind

MAP_IN = Path("_work/total_fieldmap.json")
MAP_OUT = Path("_work/total_field_mapping.json")

FID = re.compile(r"^\d+\.\d+(\.\d+)?$")
COLUMN = re.compile(r"^G(SU|C(\d+))_")


def column_of(fn: str):
    """Which grid column a control belongs to: 0 subject, N comparable, None not a grid."""
    m = COLUMN.match(fn)
    if not m:
        return None
    return 0 if m.group(1) == "SU" else int(m.group(2))


def main():
    total = json.loads(MAP_IN.read_text(encoding="utf-8"))["fields"]

    ours = {}
    for section, page_fields in bind.page_model().items():
        for pf in page_fields:
            ours.setdefault(pf.field_id, (section, pf.label))

    mapping, unmatched, no_fid = {}, [], []
    for fn, meta in total.items():
        fid = meta.get("fmid") or ""
        if not FID.match(fid):
            no_fid.append(fn)
            continue
        if fid not in ours:
            unmatched.append((fn, fid))
            continue
        section, label = ours[fid]
        mapping.setdefault(fid, {"section": section, "label": label, "controls": []})
        mapping[fid]["controls"].append(
            {"fn": fn, "kind": meta["kind"], "column": column_of(fn)})

    MAP_OUT.write_text(json.dumps(mapping, indent=1), encoding="utf-8")

    cols = sum(len(v["controls"]) for v in mapping.values())
    print(f"TOTAL controls seen           : {len(total)}")
    print(f"  carrying a Report Field ID  : {len(total) - len(no_fid)}")
    print(f"  matching our field index    : {cols} controls over {len(mapping)} field IDs")
    print(f"  ID we do not carry          : {len(unmatched)}")
    print(f"  no ID stamped               : {len(no_fid)}")
    print(f"\n-> {MAP_OUT}")

    print("\nmapped, by our section:")
    per = {}
    for v in mapping.values():
        per[v["section"]] = per.get(v["section"], 0) + 1
    for section, n in sorted(per.items(), key=lambda kv: -kv[1])[:14]:
        print(f"   {str(section)[:34]:<34} {n}")

    print("\nexamples:")
    for fid, v in list(mapping.items())[:10]:
        where = ", ".join(f"{c['fn']}(col {c['column']})" for c in v["controls"][:4])
        print(f"   {fid:<10} {str(v['label'])[:30]:<30} {where}")

    if unmatched:
        print("\nIDs TOTAL stamps that our index does not hold:")
        for fn, fid in unmatched[:10]:
            print(f"   {fid:<10} {fn}")


if __name__ == "__main__":
    main()
