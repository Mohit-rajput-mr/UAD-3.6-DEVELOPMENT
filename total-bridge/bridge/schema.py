"""Check the document TOTAL would deliver against the GSE schema itself.

TOTAL reports schema errors one at a time, in the order its own serializer
trips over them, which makes "fix it and see what appears next" the only way
to work. The schema is right there on disk, so the whole document can be
judged in one pass instead: every error at once, each with the line it is on.

The schema is the authority. Not the screen, not a remembered rule -- the
error text here is the parser's, quoting the same content model the delivery
specification publishes.

    from bridge import schema
    for line in schema.errors(report.mismo()):
        print(line)
"""
from __future__ import annotations

import functools
from pathlib import Path

import os

#: The official subschema, unzipped. Combined/ is the one with the imports
#: already resolved, so it validates without a catalogue.  Found the same way
#: the engine finds its specs (engine/uad/spec/paths.py) -- UAD36_SPECS, then
#: the folder's own specs/official, then the original development location --
#: but without importing the engine: the MOD shares no code with it.
_REL = Path("GSE_UAD_3.6.0_v1.3 (1)") / "GSE_UAD_3.6.0_v1.3" / "Combined" / "GSE_UAD_3.6.0_v1.3.xsd"


def _specs_root() -> Path:
    env = os.environ.get("UAD36_SPECS")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parents[2] / "specs" / "official"
    return here if here.exists() else Path(r"C:\3.6 uad zips\_UNZIPPED_ALL")


XSD = _specs_root() / _REL


@functools.lru_cache(maxsize=1)
def _schema():
    from lxml import etree
    if not XSD.exists():
        raise FileNotFoundError(f"GSE subschema not found at {XSD}")
    return etree.XMLSchema(etree.parse(str(XSD)))


def errors(xml: str) -> list[str]:
    """Every schema error in this document, or an empty list when it is valid."""
    from lxml import etree
    doc = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    s = _schema()
    if s.validate(doc):
        return []
    return [f"line {e.line}: {e.message}" for e in s.error_log]


def check(report) -> list[str]:
    """Validate what this report would deliver, right now."""
    return errors(report.mismo())
