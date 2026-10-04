"""Print everything the specs say about a Report Field ID."""
import json,sys,re
from pathlib import Path
SPEC=Path("engine/spec")
IDX=json.loads((SPEC/"field_index.json").read_text(encoding="utf-8"))["fields"]
C1=json.loads((SPEC/"c1_form.json").read_text(encoding="utf-8"))
def c1_hits(fid):
    out=[]
    for pg in C1["pages"]:
        for el in pg["elements"]:
            if fid in (el.get("ids") or []): out.append((pg["page"],el["kind"],el.get("text","")[:90]))
            for row in el.get("rows") or []:
                if fid in (row.get("ids") or []): out.append((pg["page"],"row",str(row.get("label") or row.get("text"))[:90]))
                for c in row.get("cells") or []:
                    if fid in (c.get("ids") or []): out.append((pg["page"],"cell",str(c.get("text"))[:90]))
    return out
for fid in sys.argv[1:]:
    e=IDX.get(fid)
    print("="*100); print("FID",fid)
    if not e: print("  not in field_index"); continue
    for loc in e.get("locations") or []: print("  loc:",loc)
    for dp in e.get("data_points") or []:
        print("  dp:", dp.get("mismo"), "| attr:",dp.get("attribute"),"| fmt:",dp.get("format_type"),dp.get("format_details"),
              "| cond:",dp.get("conditionality"),"| card:",dp.get("cardinality"))
        if dp.get("xpath"): print("      xpath:",dp["xpath"])
        if dp.get("conditionality_details"): print("      when:",str(dp["conditionality_details"])[:300])
        if dp.get("notes"): print("      note:",str(dp["notes"])[:300])
        en=[o.get("value") for o in dp.get("enumerations") or []]
        if en: print("      enum:",", ".join(x for x in en if x)[:400])
    for k,v in e.items():
        if k not in ("locations","data_points"): print("  ",k,":",str(v)[:200])
    print("  C-1:",c1_hits(fid)[:6])
