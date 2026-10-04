"""Run TOTAL's E&O check on an open report and print every finding.

    python eo.py "18 north"
    python eo.py "18 north" --ids     also resolve each control to its field id
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge import review
from bridge.total import Report


def main(argv) -> int:
    name = argv[0] if argv and not argv[0].startswith("--") else None
    want_ids = "--ids" in argv

    with Report.attach(name, allow_signed=True) as report:
        print(f"report : {report.name!r}")
        print("running TOTAL's E&O check ...")
        found = review.run(report)
        print()
        print(review.summarise(found))
        if not found:
            return 0

        ids = review.field_ids(report, found) if want_ids else {}

        for section, rows in review.by_section(found).items():
            print()
            print(f"{section}  ({len(rows)})")
            for f in sorted(rows, key=lambda r: (r.field, r.instance)):
                where = f"{f.field}[{f.instance}]" if f.instance else f.field
                fid = ids.get(f.field, "")
                tag = f"  {fid}" if fid else ""
                print(f"   {where:<38}{tag:<10} {f.description}")

        print()
        print(f"{len(found)} to clear before this report is deliverable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
