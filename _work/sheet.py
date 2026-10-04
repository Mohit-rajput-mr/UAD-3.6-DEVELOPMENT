"""A flat, readable sheet of a case's values -- what to type into another form.

Reads the case the way the report does, so what comes out is what the report
prints, not a raw XML dump.
"""
import sys
sys.path.insert(0, "engine")
from pathlib import Path

from lxml import etree

from uad import bind
from uad.report import comparables

XML = Path(sys.argv[1] if len(sys.argv) > 1
           else r"C:\UAD 3.6 DEVELOPMENT\_work\manhattan\condo.xml")


def main():
    tree = etree.parse(str(XML))
    root = tree.getroot()

    print(f"# {XML.name}\n")

    # ---- subject, by section, as the report reads it
    subject = bind.subject(root)
    shown = 0
    for section, fields in bind.page_model().items():
        rows = []
        for pf in fields:
            fid = pf.field_id
            try:
                value = bind.read(root, fid, scope=subject)
            except Exception:
                continue
            if isinstance(value, (list, tuple)):
                value = ", ".join(str(v) for v in value if v)
            value = (value or "").strip() if isinstance(value, str) else str(value or "")
            if value:
                rows.append((fid, pf.label, value))
        if rows:
            print(f"\n## {section}")
            for fid, label, value in rows:
                print(f"  {fid:<9} {label[:44]:<44} {value[:70]}")
                shown += 1

    print(f"\n\n# comparables")
    for kind, (_sheet, role, _sec) in comparables.SHEETS.items():
        props = comparables.properties(root, role)
        if not props:
            continue
        print(f"\n## {kind}: {len(props)}")
        for n, prop in enumerate(props, start=1):
            print(f"\n### {kind} #{n}")
            for el in prop.iter():
                if not isinstance(el.tag, str) or len(el):
                    continue
                text = (el.text or "").strip()
                if not text or len(text) > 120:
                    continue
                print(f"    {etree.QName(el).localname:<44} {text[:70]}")

    print(f"\n\n{shown} subject values")


if __name__ == "__main__":
    main()
