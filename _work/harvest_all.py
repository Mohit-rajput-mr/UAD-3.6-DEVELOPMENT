"""Harvest every control TOTAL's UAD 3.6 form exposes, in one render.

`RefreshReport()` notifies the data layer with RenderAll, which materialises
the whole report rather than the section on screen -- so one render gives the
complete field map.  Nothing is written; the section on screen is restored.
"""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from total_bridge import Total

OUT = Path("_work/total_fieldmap.json")

DESCRIBE = r"""
(() => {
  const rows = [];
  for (const e of document.querySelectorAll('[fn]')) {
    const fn = e.getAttribute('fn');
    let kind;
    if (e.tagName === 'INPUT' && e.type === 'checkbox') kind = 'checkbox';
    else if (e.tagName === 'INPUT') kind = 'text';
    else if (e.tagName === 'TEXTAREA') kind = 'textarea';
    else if (e.tagName === 'IMG') kind = 'image';
    else if (e.isContentEditable) kind = 'editable';
    else kind = 'readonly';
    rows.push({fn, kind,
               fmid: e.getAttribute('fmid') || '',
               instance: e.getAttribute('instance') || '0',
               value: ((e.tagName === 'INPUT' || e.tagName === 'TEXTAREA')
                       ? (e.value || '') : (e.textContent || '')).trim().slice(0, 40)});
  }
  return rows;
})()
"""

total = Total.attach()
try:
    start = total.page.evaluate("window.engine.currentActiveSectionKey")
    print(f"current section: {start!r}")

    total.page.evaluate("window.engine.RefreshReport()")
    time.sleep(2.5)
    rows = total.page.evaluate(DESCRIBE) or []

    labels = {r["fn"].replace("LABEL_", "", 1): r["value"]
              for r in rows if r["fn"].startsWith("LABEL_")} if False else {
        r["fn"][6:]: r["value"] for r in rows if r["fn"].startswith("LABEL_")}
    fields = [r for r in rows if not r["fn"].startswith("LABEL_")]
    for r in fields:
        r["label"] = labels.get(r["fn"], "")

    names = {}
    for r in fields:
        names.setdefault(r["fn"], {"kind": r["kind"], "label": r["label"],
                                   "fmid": r["fmid"], "instances": 0})
        names[r["fn"]]["instances"] += 1

    OUT.write_text(json.dumps({"fields": names, "raw": fields}, indent=1),
                   encoding="utf-8")

    by_kind = {}
    for v in names.values():
        by_kind[v["kind"]] = by_kind.get(v["kind"], 0) + 1
    print(f"\n{len(rows)} elements, {len(fields)} controls, "
          f"{len(names)} distinct field names")
    print("by kind:", by_kind)
    print(f"carrying a UAD field id: {sum(1 for v in names.values() if v['fmid'])}")
    print(f"-> {OUT}")

    print("\nsample (name -> label):")
    for fn, v in list(names.items())[:25]:
        print(f"   {fn:<34} {v['kind']:<9} x{v['instances']:<3} {v['label'][:34]!r}")
finally:
    if start:
        total.page.evaluate(
            f"window.engine.currentActiveSectionKey = {json.dumps(start)}")
    total.close()
