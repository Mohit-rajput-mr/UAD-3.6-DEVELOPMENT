"""Record which fields a brand-new UAD 3.6 report already holds, per web-engine build.

An import must go into a new report (IMPORT_PROFILE P5, CATALOG E-029: a
replace-import keeps whatever it does not overwrite).  "New" cannot mean
"empty" or "only TOTAL's declared defaults": a report TOTAL has just created
already holds ~630 values -- its 557 declared defaults plus section GUIDs,
labels, grid column headers, mirrors of the defaults, and the report's name
copied into the subject address.  So the fingerprint of a new report is the
set of fields (key, instance) it holds; a report is fresh when it holds a
value in no other field (`bridge/detect.py freshness`).

    python tools/new_report.py --report "SAMPLE BLANK"      (read-only)

Take it from a report created moments before, nothing typed or imported.
Writes knowledge/total/builds/<build>/new_report.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from bridge import detect                    # noqa: E402
from bridge.total import Report              # noqa: E402

_LEAVES = r"""(() => { const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const out = [];
  const walk = o => { for (const x of (o.dataObjects || [])) {
      if ((x.dataObjects || []).length) { walk(x); continue; }
      const v = String(x.value ?? '').trim();
      if (v) out.push([x.key, x.instance ?? 0, v.slice(0, 80)]); } };
  walk(d); return out; })()"""
GUID = __import__("re").compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True)
    ap.add_argument("--add", metavar="HOW",
                    help="add this observation to the existing fingerprint instead of replacing it, "
                         "saying how the report became new (e.g. 'tools/roundtrip.py reset_blank')")
    a = ap.parse_args(argv)
    with Report.attach(a.report) as report:
        build = detect._build_of(report.page)
        leaves = report.page.evaluate(_LEAVES) or []
        keys = sorted({f"{k}#{i}" for k, i, _v in leaves})
    out = detect.BUILDS / build / "new_report.json"
    # values too (GUIDs and the report's own name aside): what a new report
    # says, so two observations can be compared value by value
    values = {f"{k}#{i}": v for k, i, v in leaves if not GUID.match(v) and v != a.report}
    source = {"report": a.report, "taken": time.strftime("%Y-%m-%d %H:%M"), "how": a.add or "created in TOTAL",
              "fields": len(keys), "values": values}
    if a.add and out.exists():
        old = json.loads(out.read_text(encoding="utf-8"))
        added = sorted(set(keys) - set(old["keys"]))
        keys = sorted(set(old["keys"]) | set(keys))
        sources = old.get("sources", [{"report": old.get("report"), "taken": old.get("taken"),
                                       "how": "created in TOTAL"}]) + [dict(source, added=added)]
    else:
        sources = [source]
    first = sources[0]
    out.write_text(json.dumps({"build": build, "report": first["report"], "taken": first["taken"],
                               "sources": sources, "keys": keys}, indent=1), encoding="utf-8")
    print(f"{len(keys)} fields in the new-report fingerprint ({len(sources)} observation(s)) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
