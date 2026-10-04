"""Walk every section of TOTAL's UAD 3.6 form and record what it can hold.

Read-only with respect to the report: it changes which section is on screen in
order to make each one render (the form only materialises the section you are
looking at), reads the control names, and puts the original section back.  No
value is written.

The result is the field map the bridge needs: TOTAL's own `fn` name for every
control, per section, with its kind and repeat instances.
"""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cdp
from total_bridge import Total

OUT = Path("_work/total_fieldmap.json")

DESCRIBE = r"""
(() => {
  const out = [];
  for (const e of document.querySelectorAll('[fn]')) {
    const fn = e.getAttribute('fn');
    let kind;
    if (e.tagName === 'INPUT' && e.type === 'checkbox') kind = 'checkbox';
    else if (e.tagName === 'INPUT') kind = 'text';
    else if (e.tagName === 'TEXTAREA') kind = 'textarea';
    else if (e.tagName === 'IMG') kind = 'image';
    else if (e.isContentEditable) kind = 'editable';
    else kind = 'readonly';
    out.push({fn, kind,
              fmid: e.getAttribute('fmid') || '',
              instance: e.getAttribute('instance') || '0',
              label: fn.startsWith('LABEL_'),
              value: ((e.tagName === 'INPUT' || e.tagName === 'TEXTAREA')
                      ? (e.value || '')
                      : (e.textContent || '')).trim().slice(0, 30)});
  }
  return out;
})()
"""


def main():
    total = Total.attach()
    try:
        start = total.page.evaluate(
            "window.engine.GetActiveSectionKeyForMode "
            "? window.engine.GetActiveSectionKeyForMode() : null")
        sections = total.sections()
        print(f"{len(sections)} sections; currently on {start!r}\n")

        harvest = {}
        for key in sections:
            total.goto(key)
            time.sleep(1.1)                 # the section has to render
            rows = total.page.evaluate(DESCRIBE) or []
            fields = [r for r in rows if not r["label"]]
            labels = {r["fn"].replace("LABEL_", "", 1): r["value"]
                      for r in rows if r["label"]}
            for r in fields:
                r["label_text"] = labels.get(r["fn"], "")
            harvest[key] = fields
            named = sorted({r["fn"] for r in fields})
            print(f"  {key:<24} {len(fields):>4} controls, {len(named):>4} distinct")

        if start:
            total.goto(start)
            print(f"\nrestored section {start!r}")

        OUT.write_text(json.dumps(harvest, indent=1), encoding="utf-8")
        allf = {r["fn"] for rows in harvest.values() for r in rows}
        withfmid = {r["fn"] for rows in harvest.values() for r in rows if r["fmid"]}
        print(f"\n{len(allf)} distinct field names across {len(harvest)} sections")
        print(f"{len(withfmid)} of them carry a UAD field id (fmid)")
        print(f"-> {OUT}")
    finally:
        total.close()


if __name__ == "__main__":
    main()
