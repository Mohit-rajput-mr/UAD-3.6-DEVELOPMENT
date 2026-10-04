"""Import a TEST package into the scratch report and diagnose it (TASKS T-995).

Resets the scratch report to a new blank (`roundtrip.reset_blank`), runs the
Import Module (`bridge/deliver.py`) on the package, then `bridge/diagnose.py
after()` with the package as the round-trip reference.  Writes
<package>_result.json beside the package and prints the diagnostics.

    python tools/run_test_package.py --report "SAMPLE BLANK" PACKAGE_TEST_NOT_A_REPORT.xml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from bridge import deliver, diagnose           # noqa: E402
from bridge.total import Report, without_schema_location   # noqa: E402
import roundtrip                               # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True, help="a SCRATCH report (it is reset and overwritten)")
    ap.add_argument("package")
    a = ap.parse_args(argv)
    pkg = Path(a.package)
    if "TEST_NOT_A_REPORT" not in pkg.name:
        raise SystemExit("only *_TEST_NOT_A_REPORT.xml packages go through this tool")
    with Report.attach(a.report) as report:
        print("reset:", roundtrip.reset_blank(report), flush=True)
        result = deliver.run(report, pkg, progress=lambda t: print(" ", t, flush=True))
        if result.get("import_error"):
            print("import failed:", result["import_error"])
            return 1
        found = diagnose.after(report, package=without_schema_location(pkg.read_text(encoding="utf-8")).encode("utf-8"),
                               progress=lambda t: print(" ", t.strip(), flush=True))
    keep = {k: v for k, v in result.items() if k not in ("total_xml", "import_log")}
    out = pkg.with_name(pkg.stem + "_result.json")
    out.write_text(json.dumps({"deliver": keep, "diagnostics": diagnose.as_json(found)}, indent=1, default=str),
                   encoding="utf-8")
    print(diagnose.report_text(found))
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
