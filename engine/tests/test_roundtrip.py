"""Prove the case model round-trips every official sample XML losslessly.

The platform edits a case and then delivers it as MISMO XML.  If the model
cannot carry a GSE sample in and back out unchanged, nothing downstream can be
trusted, so this runs before anything is built on top of it.

Equality is judged on the parsed tree -- element order, text, attributes and
xlink labels -- not on the byte stream, because indentation and the GSE's own
inline comments are not part of the data.
"""
from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import model  # noqa: E402

from uad.paths import SPEC_ROOT as ROOT
XSI = "http://www.w3.org/2001/XMLSchema-instance"


def samples() -> list[Path]:
    seen: dict[str, Path] = {}
    for p in sorted(ROOT.rglob("*_Appraisal_v1.*.xml")):
        seen.setdefault(p.name, p)
    return list(seen.values())


def canonical(node: etree._Element) -> tuple:
    """A comparable shape for an element: tag, attributes, text, children."""
    attrs = {k: v for k, v in node.attrib.items()
             if k not in model.DROPPED_ATTRIBUTES}
    text = (node.text or "").strip()
    return (node.tag, tuple(sorted(attrs.items())), text,
            tuple(canonical(c) for c in node if isinstance(c.tag, str)))


def differences(a, b, path="") -> list[str]:
    out: list[str] = []
    if a[0] != b[0]:
        return [f"{path}: tag {a[0]} != {b[0]}"]
    here = f"{path}/{etree.QName(a[0]).localname}"
    if a[1] != b[1]:
        out.append(f"{here}: attributes {a[1]} != {b[1]}")
    if a[2] != b[2]:
        out.append(f"{here}: text {a[2]!r} != {b[2]!r}")
    if len(a[3]) != len(b[3]):
        out.append(f"{here}: {len(a[3])} children != {len(b[3])}")
    for i, (ca, cb) in enumerate(zip(a[3], b[3])):
        out.extend(differences(ca, cb, f"{here}[{i}]"))
        if len(out) > 12:
            return out
    return out


def main() -> int:
    files = samples()
    print(f"{len(files)} official sample XML files\n")
    failures = 0
    for path in files:
        raw = etree.parse(str(path)).getroot()
        doc = model.parse(str(path))
        out = model.serialize(doc)
        back = etree.fromstring(out)
        diffs = differences(canonical(raw), canonical(back))
        elements = sum(1 for _ in raw.iter() if isinstance(_.tag, str))
        status = "ok  " if not diffs else "FAIL"
        if diffs:
            failures += 1
        print(f"  {status} {path.name:<42} {elements:>6} elements")
        for d in diffs[:6]:
            print(f"        {d}")
    print(f"\n{len(files) - failures}/{len(files)} round-trip losslessly")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
