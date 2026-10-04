"""Make one self-contained UAD 3.6 XML: the appraisal and every picture in it.

Used after Claude writes a report's MISMO XML from a property folder (see
``engine/docs/CLAUDE_XML_PACKAGE.md``).  It

1. reads the XML exactly as the import engine will (``uad/importer.py``):
   namespace, values in A-1 form, list values the schema accepts, elements
   UAD 3.6 does not have;
2. finds every picture an IMAGE names -- in the folder(s) given, by file
   name, case-insensitive, anywhere below them -- and embeds it inside that
   IMAGE (``EXTENSION/OTHER/kech:EmbeddedFile``, base64, SHA-256), which the
   GSE subschema accepts;
3. validates the result against the GSE UAD 3.6 subschema and prints what the
   import will say: values, comparables, pictures embedded / missing,
   anything that could not be read.

    python engine/tools/pack_xml.py appraisal.xml --images "C:/property folder" --out appraisal_portable.xml

Exit code 0 when the file is ready to import with nothing missing, 1 when it
imports but something needs attention, 2 when it cannot be imported.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from lxml import etree  # noqa: E402

from uad import importer, schema  # noqa: E402

PICTURES = set(importer.IMAGE_TYPES) - {".pdf"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xml")
    ap.add_argument("--images", action="append", default=[], help="folder to look for pictures in (repeatable)")
    ap.add_argument("--out", help="the portable XML to write (default: <name>_portable.xml)")
    args = ap.parse_args()

    src = Path(args.xml)
    report = importer.Report(xml_name=src.name)
    try:
        tree = importer.parse(src.read_bytes())
    except importer.ImportError_ as exc:
        print("CANNOT IMPORT:", exc)
        return 2
    carried, state = importer.take_embedded(tree, report)
    importer.normalise(tree, report)
    importer.repair_enumerations(tree, report)

    # every picture file below the folders given, by lower-case name
    found: dict[str, Path] = {}
    for folder in args.images or [str(src.parent)]:
        for path in Path(folder).rglob("*"):
            if path.is_file() and path.suffix.lower() in PICTURES:
                found.setdefault(path.name.lower(), path)
    assets = {k: (v.name, v.read_bytes()) for k, v in found.items()}
    assets.update(carried)
    pictures = importer.pictures(tree, assets, report)
    importer.count(tree, report)

    # write the pictures back inside their IMAGEs, under their final names
    images = {}
    tmp = Path(args.out or src.with_name(src.stem + "_portable.xml")).with_suffix(".images")
    tmp.mkdir(exist_ok=True)
    for pic in pictures:
        (tmp / pic.name).write_bytes(pic.data)
        images[pic.name] = tmp / pic.name
    result = importer.embed(tree, images, state or None)
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()

    out = Path(args.out or src.with_name(src.stem + "_portable.xml"))
    out.write_bytes(etree.tostring(tree, xml_declaration=True, encoding="utf-8", pretty_print=True))
    errors = schema.validate(tree)

    print(f"wrote {out}  ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"values {report.values}  on the report {report.on_report}  comparables {report.comparables}")
    print(f"pictures embedded {result['embedded']}  missing {len(report.pictures_missing)}"
          f"  in the folder but not named by any IMAGE {len(report.pictures_unreferenced)}")
    for m in report.pictures_missing:
        print("  MISSING picture:", m.get("location"), "-", m.get("reason"))
    for path, value, why in report.invalid:
        print("  CHECK:", path, "=", value, "-", why)
    for path, text in report.dropped:
        print("  NOT UAD 3.6 (left out):", path, text[:80])
    for n, (path, old, new) in enumerate(report.normalised):
        if n < 20:
            print("  normalised:", path, repr(old), "->", repr(new))
    print(f"schema: {'valid' if not errors else str(len(errors)) + ' finding(s)'} against the GSE UAD 3.6 subschema")
    for e in errors[:15]:
        print("  SCHEMA:", e.message[:200])
    trouble = report.pictures_missing or report.invalid or report.dropped or errors
    return 1 if trouble else 0


if __name__ == "__main__":
    sys.exit(main())
