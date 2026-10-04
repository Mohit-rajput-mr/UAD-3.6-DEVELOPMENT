import json, sys
n = lambda x: len(x) if isinstance(x, list) else x
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if not line.startswith("{"):
        continue
    d = json.loads(line)
    if "values" not in d:
        if "heap_mb_after" in d: print("    heap", d["heap_mb_after"])
        elif "failed" in d: print("FAILED", d)
        continue
    v = d["values"]; ph = d.get("photos", {}); eo = d.get("eando", {})
    print(f"{d['file'][:34]:<34} kept {v['kept']}/{v['source_values']} drop {v['dropped']} chg {v['changed']} add {v['added']}"
          f" | value diffs {d['value_affecting_diffs']} | photos empty {n(ph.get('slots_still_empty'))}"
          f" | {eo.get('stage')} FV {n(eo.get('field_validation'))} UAD {n(eo.get('uad_rules'))}"
          f" | rows {n(d.get('grid_rows_reshown'))} nets {n(d.get('nets_corrected'))}")
