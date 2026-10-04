"""Set the category on each exhibit that has a picture but no category.

    python categorise.py "18 north test"
    python categorise.py "18 north test" --dry-run

TOTAL builds the category list from the room schedule, and refuses the report
until every exhibit carrying a picture says which room it is.  The pictures
arrive captioned, so the two are matched.

An exhibit whose caption matches nothing -- a boiler, a smoke detector -- is
left alone and listed.  Those are not rooms, and inventing a room for them
would file them wrongly while looking finished.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge import pick
from bridge.place import slots
from bridge.total import Report

# Sections whose exhibits are categorised from the room schedule.
SECTIONS = ("interior-1", "site", "sub-prop", "assignment", "garage",
            "amenities", "dwelling-exterior-1", "market", "history")


def caption_of(report, fn: str, instance: str) -> str:
    return report.page.evaluate(f"""
    (() => {{
      const el = document.querySelector('[fn="{fn}"][instance="{instance}"]');
      if (!el) return '';
      let scope = el.closest('.photo-container') || el;
      for (let i = 0; i < 4 && scope.parentElement; i++) scope = scope.parentElement;
      for (const n of scope.querySelectorAll('[fn]')) {{
        const f = n.getAttribute('fn') || '';
        if (/CAPTION|DESCRIPTION/.test(f)) {{
          const t = (n.getAttribute('data-value') || n.textContent || '').trim();
          if (t) return t;
        }}
      }}
      return '';
    }})()
    """) or ""


def main(argv) -> int:
    name = argv[0] if argv and not argv[0].startswith("--") else None
    dry = "--dry-run" in argv

    with Report.attach(name) as report:
        print(f"report : {report.name!r}")
        print("rehearsing (nothing set) ...\n" if dry else "setting categories ...\n")
        set_count = skipped = 0
        left: list[tuple[str, str]] = []

        for section in SECTIONS:
            try:
                report.goto(section, 1.6)
            except Exception:
                continue
            # Only exhibits that actually carry a picture need a category.
            filled = [s for s in slots(report) if not s["empty"]]
            if not filled:
                continue

            controls = [c for c in report.controls()
                        if c["fn"].endswith("_CATEGORY")]
            if not controls:
                continue

            offered, taken = [], set()
            # Read what this section offers, and what is already chosen.
            for control in controls:
                value = report.get(control["fn"], control["instance"])
                if value:
                    taken.add(value)
            for control in controls:
                if report.get(control["fn"], control["instance"]):
                    continue
                caption = caption_of(report, control["fn"], control["instance"])
                if not caption:
                    continue
                if not offered:
                    offered = pick.options(report, control["fn"], control["instance"])
                    if not offered:
                        break
                wanted = pick.match(caption, offered, taken)
                if not wanted:
                    left.append((section, caption))
                    skipped += 1
                    continue
                if dry:
                    print(f"  {section:<22} {caption[:26]:<26} -> {wanted}")
                    taken.add(wanted)
                    set_count += 1
                    continue
                result = pick.choose(report, control["fn"], control["instance"], wanted)
                if result.get("ok"):
                    taken.add(wanted)
                    set_count += 1
                    print(f"  {section:<22} {caption[:26]:<26} -> {wanted}")
                else:
                    print(f"  {section:<22} {caption[:26]:<26} -> FAILED "
                          f"{result.get('why') or result.get('got')!r}")

        print()
        print(f"{set_count} categor{'y' if set_count == 1 else 'ies'} set, "
              f"{skipped} left for a person")
        if left:
            print("\nno room matches these -- they belong in a general exhibit "
                  "section, not a room:")
            for section, caption in left:
                print(f"   {section:<22} {caption}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
