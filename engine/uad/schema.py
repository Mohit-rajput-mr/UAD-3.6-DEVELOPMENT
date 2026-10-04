"""Validate a MISMO document against the GSE UAD subschema.

Only the **v1.3** subschema is published in the material we hold, while the
Appendix D-1 samples declare **v1.4**.  Rather than assume the two agree, this
module validates the untouched samples against v1.3 first and reports exactly
where they diverge.  Anything that makes a GSE sample fail is a fact about the
schema version, not about the document, and is recorded as such.

Validation uses libxml2 through lxml, which parses the 4 MB combined schema
once and then checks documents in milliseconds -- fast enough to run on every
keystroke-driven save in the editor.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .paths import SPEC_ROOT

# The GSEs ship a "Combined" schema that resolves its own imports locally.
SCHEMA_GLOB = "GSE_UAD_3.6.0_v*/Combined/GSE_UAD_3.6.0_v*.xsd"


@dataclass(frozen=True)
class SchemaError:
    line: int
    column: int
    message: str
    path: str = ""

    def __str__(self) -> str:
        where = self.path or f"line {self.line}"
        return f"{where}: {self.message}"


def schema_path() -> Path:
    """The newest combined subschema on disk."""
    found = [p for p in SPEC_ROOT.rglob(SCHEMA_GLOB)
             if "xlink" not in p.name.lower()]
    if not found:
        raise FileNotFoundError(
            f"no GSE UAD subschema under {SPEC_ROOT}; expected {SCHEMA_GLOB}")
    return sorted(found)[-1]


def schema_version() -> str:
    name = schema_path().stem              # GSE_UAD_3.6.0_v1.3
    return name.rsplit("_v", 1)[-1] if "_v" in name else "unknown"


@functools.lru_cache(maxsize=1)
def schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(schema_path())))


def validate(source) -> list[SchemaError]:
    """Validate a path, bytes or parsed tree.  Empty list means clean."""
    if isinstance(source, (bytes, bytearray)):
        tree = etree.fromstring(bytes(source)).getroottree()
    elif isinstance(source, etree._ElementTree):
        tree = source
    elif isinstance(source, etree._Element):
        tree = source.getroottree()
    else:
        tree = etree.parse(str(source))

    validator = schema()
    if validator.validate(tree):
        return []
    out = []
    for e in validator.error_log:
        out.append(SchemaError(line=e.line, column=e.column,
                               message=e.message, path=e.path or ""))
    return out


def main() -> None:
    path = schema_path()
    print(f"schema ... {path.name}  ({path.stat().st_size / 1024:.0f} KB)")
    print(f"version .. v{schema_version()}\n")

    seen: dict[str, Path] = {}
    for p in sorted(SPEC_ROOT.rglob("*_Appraisal_v1.*.xml")):
        seen.setdefault(p.name, p)

    clean = 0
    for name, sample in seen.items():
        errors = validate(sample)
        declared = "1.4" if "v1.4" in name else "1.2"
        if not errors:
            clean += 1
            print(f"  ok    {name:<42} (declares v{declared})")
        else:
            print(f"  {len(errors):>3}   {name:<42} (declares v{declared})")
            for e in errors[:4]:
                print(f"          {e}")
    print(f"\n{clean}/{len(seen)} official samples validate against v{schema_version()}")


if __name__ == "__main__":
    main()
