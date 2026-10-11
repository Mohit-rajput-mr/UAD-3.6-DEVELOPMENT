"""Authoritative child-element ordering, derived from the GSE UAD 3.6 XSD.

The delivery spec's "XML Sort Number" is a listing sequence for the workbook,
not the schema's sequence order, so serialising by it produces XSD-invalid
output.  This module reads the real <xs:sequence> declarations instead.
"""
from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path

from lxml import etree

XS = "{http://www.w3.org/2001/XMLSchema}"

SCHEMA_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "_ref"
    / "schema"
    / "GSE_UAD_3.6.0_v1.3"
    / "Combined"
)
SCHEMA_FILE = SCHEMA_DIR / "GSE_UAD_3.6.0_v1.3.xsd"
CACHE_FILE = Path(__file__).resolve().parent.parent / "spec" / "xsd_order.json"


class ElementOrder:
    """element name -> {child name: position} taken from the XSD."""

    def __init__(self, table: dict[str, dict[str, int]]):
        self.table = table

    def position(self, parent: str, child: str) -> int | None:
        return self.table.get(parent, {}).get(child)

    def children(self, parent: str) -> list[str]:
        order = self.table.get(parent, {})
        return sorted(order, key=order.get)

    # ------------------------------------------------------------- building
    @classmethod
    def from_schema(cls, path: Path = SCHEMA_FILE) -> "ElementOrder":
        root = etree.parse(str(path)).getroot()

        # In this schema every complexType is named after the element it types.
        types: dict[str, etree._Element] = {
            t.get("name"): t for t in root.iterfind(f"{XS}complexType") if t.get("name")
        }

        # Model groups we descend through while collecting element declarations.
        groups = {
            f"{XS}sequence",
            f"{XS}choice",
            f"{XS}all",
            f"{XS}complexContent",
            f"{XS}simpleContent",
        }

        def collect(node: etree._Element, names: list[str], seen: set[str]) -> None:
            for child in node:
                tag = child.tag
                if tag == f"{XS}element":
                    name = child.get("name") or child.get("ref", "").split(":")[-1]
                    if name and name not in names:
                        names.append(name)
                elif tag == f"{XS}extension":
                    base = child.get("base", "").split(":")[-1]
                    if base in types and base not in seen:
                        collect(types[base], names, seen | {base})
                    collect(child, names, seen)
                elif tag in groups:
                    collect(child, names, seen)

        table: dict[str, dict[str, int]] = {}
        for name, node in types.items():
            names: list[str] = []
            collect(node, names, {name})
            if names:
                table[name] = {n: i for i, n in enumerate(names)}
        return cls(_with_aliases(root, table))

    @classmethod
    def load(cls) -> "ElementOrder":
        """Use the cached table when present; otherwise parse and cache it."""
        if CACHE_FILE.exists():
            with open(CACHE_FILE, encoding="utf-8") as fh:
                return cls(json.load(fh))
        order = cls.from_schema()
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(order.table, fh)
        return order


def _aliases(root: etree._Element) -> dict[str, str]:
    """element name -> its complexType where the two differ.

    Nearly every complexType is named after the element it types, but not
    all: ADDITIONAL_ADDRESS is typed ADDRESS.  Without the alias its children
    have no order, the alternate address was written in typing order, and the
    schema refused it (E-080).  A name declared with two different types is
    left out rather than guessed."""
    types = {t.get("name") for t in root.iterfind(f"{XS}complexType") if t.get("name")}
    seen: dict[str, set[str]] = {}
    for el in root.iter(f"{XS}element"):
        name, typ = el.get("name"), (el.get("type") or "").split(":")[-1]
        if name and typ and typ in types and name != typ and name not in types:
            seen.setdefault(name, set()).add(typ)
    return {n: next(iter(t)) for n, t in seen.items() if len(t) == 1}


def _with_aliases(root: etree._Element, table: dict) -> dict:
    for name, typ in _aliases(root).items():
        if typ in table and name not in table:
            table[name] = table[typ]
    return table


_order: ElementOrder | None = None


def load() -> ElementOrder:
    global _order
    if _order is None:
        _order = ElementOrder.load()
    return _order


# ------------------------------------------------------------ required children
REQUIRED_CACHE = CACHE_FILE.with_name("xsd_required.json")


def _schema_file() -> Path:
    if SCHEMA_FILE.exists():
        return SCHEMA_FILE
    from . import schema
    return Path(schema.schema_path())


def required_table() -> dict[str, list[str]]:
    """element name -> the child elements its XSD sequence requires
    (minOccurs not 0, and not one branch of a choice), in schema order.

    A container created without them is invalid however its own value is
    set: an APPRAISER needs its APPRAISER_DETAIL before DESIGNATIONS, a
    LEGAL_ENTITY its LEGAL_ENTITY_DETAIL."""
    if REQUIRED_CACHE.exists():
        return json.loads(REQUIRED_CACHE.read_text(encoding="utf-8"))
    root = etree.parse(str(_schema_file())).getroot()
    types = {t.get("name"): t for t in root.iterfind(f"{XS}complexType") if t.get("name")}

    def walk(node, out, seen, optional):
        for child in node:
            tag = child.tag
            if tag == f"{XS}element":
                name = child.get("name") or child.get("ref", "").split(":")[-1]
                if name and not optional and child.get("minOccurs", "1") != "0" and name not in out:
                    out.append(name)
            elif tag == f"{XS}choice":
                walk(child, out, seen, True)
            elif tag == f"{XS}extension":
                base = child.get("base", "").split(":")[-1]
                if base in types and base not in seen:
                    walk(types[base], out, seen | {base}, optional)
                walk(child, out, seen, optional)
            elif tag in (f"{XS}sequence", f"{XS}all", f"{XS}complexContent", f"{XS}simpleContent"):
                walk(child, out, seen, optional or child.get("minOccurs") == "0")

    table = {}
    for name, node in types.items():
        out: list[str] = []
        walk(node, out, {name}, False)
        if out:
            table[name] = out
    _with_aliases(root, table)
    REQUIRED_CACHE.write_text(json.dumps(table), encoding="utf-8")
    return table


_required: dict[str, list[str]] | None = None


def required(parent: str) -> list[str]:
    global _required
    if _required is None:
        _required = required_table()
    return _required.get(parent, [])


# ------------------------------------------------------------ choice groups
CHOICE_CACHE = CACHE_FILE.with_name("xsd_choices.json")


def choice_table() -> dict[str, list[list[str]]]:
    """element name -> its xs:choice groups (children of which only one may
    appear).  A ROLE is an APPRAISER or a SERVICE_PROVIDER, never both; the
    fee a party charges lives in a second ROLE beside the first (D-1)."""
    if CHOICE_CACHE.exists():
        return json.loads(CHOICE_CACHE.read_text(encoding="utf-8"))
    root = etree.parse(str(_schema_file())).getroot()
    types = {t.get("name"): t for t in root.iterfind(f"{XS}complexType") if t.get("name")}

    def names(node, seen):
        out = []
        for child in node:
            if child.tag == f"{XS}element":
                n = child.get("name") or child.get("ref", "").split(":")[-1]
                if n:
                    out.append(n)
            elif child.tag in (f"{XS}sequence", f"{XS}choice", f"{XS}all"):
                out.extend(names(child, seen))
        return out

    def walk(node, groups, seen):
        for child in node:
            if child.tag == f"{XS}choice":
                members = names(child, seen)
                if len(members) > 1:
                    groups.append(members)
            elif child.tag == f"{XS}extension":
                base = child.get("base", "").split(":")[-1]
                if base in types and base not in seen:
                    walk(types[base], groups, seen | {base})
                walk(child, groups, seen)
            elif child.tag in (f"{XS}sequence", f"{XS}all", f"{XS}complexContent", f"{XS}simpleContent"):
                walk(child, groups, seen)

    table = {}
    for name, node in types.items():
        groups: list[list[str]] = []
        walk(node, groups, {name})
        if groups:
            table[name] = groups
    _with_aliases(root, table)
    CHOICE_CACHE.write_text(json.dumps(table), encoding="utf-8")
    return table


_choices: dict | None = None


def rivals(parent: str, child: str) -> set[str]:
    """The children that exclude ``child`` inside ``parent``."""
    global _choices
    if _choices is None:
        _choices = choice_table()
    out: set[str] = set()
    for group in _choices.get(parent, []):
        if child in group:
            out.update(g for g in group if g != child)
    return out


# ------------------------------------------------------------ how often a child may appear
MAX_CACHE = CACHE_FILE.with_name("xsd_max.json")
UNBOUNDED = -1


def max_table() -> dict[str, dict[str, int]]:
    """element name -> {child: maxOccurs} (``UNBOUNDED`` for unbounded).

    A name is not a cardinality: MISMO calls the holder SALES_CONTRACTS, but
    the GSE subschema lets it hold one SALES_CONTRACT, and a second one makes
    the document invalid ("This element is not expected").  The schema says
    which blocks repeat, so the writer asks it rather than the plural."""
    if MAX_CACHE.exists():
        return json.loads(MAX_CACHE.read_text(encoding="utf-8"))
    root = etree.parse(str(_schema_file())).getroot()
    types = {t.get("name"): t for t in root.iterfind(f"{XS}complexType") if t.get("name")}

    def occurs(node) -> int:
        m = node.get("maxOccurs", "1")
        return UNBOUNDED if m == "unbounded" else int(m)

    def walk(node, out, seen, factor):
        for child in node:
            tag = child.tag
            if tag == f"{XS}element":
                name = child.get("name") or child.get("ref", "").split(":")[-1]
                if name:
                    m = occurs(child)
                    m = UNBOUNDED if UNBOUNDED in (m, factor) else m * factor
                    prev = out.get(name)
                    out[name] = m if prev is None else (UNBOUNDED if UNBOUNDED in (m, prev) else max(m, prev))
            elif tag == f"{XS}extension":
                base = child.get("base", "").split(":")[-1]
                if base in types and base not in seen:
                    walk(types[base], out, seen | {base}, factor)
                walk(child, out, seen, factor)
            elif tag in (f"{XS}sequence", f"{XS}choice", f"{XS}all"):
                f = occurs(child)
                walk(child, out, seen, UNBOUNDED if UNBOUNDED in (f, factor) else f * factor)
            elif tag in (f"{XS}complexContent", f"{XS}simpleContent"):
                walk(child, out, seen, factor)

    table = {}
    for name, node in types.items():
        out: dict[str, int] = {}
        walk(node, out, {name}, 1)
        if out:
            table[name] = out
    _with_aliases(root, table)
    try:
        MAX_CACHE.write_text(json.dumps(table, sort_keys=True), encoding="utf-8")
    except OSError:
        pass                                  # a read-only deployment: computed each start
    return table


_max: dict | None = None


def max_occurs(parent: str, child: str) -> int:
    """How many ``child`` elements ``parent`` may hold (``UNBOUNDED``: any);
    0 when the schema does not know the pair."""
    global _max
    if _max is None:
        _max = max_table()
    return _max.get(parent, {}).get(child, 0)


MIN_CACHE = CACHE_FILE.with_name("xsd_min.json")


def min_table() -> dict[str, dict[str, int]]:
    """element name -> {child: minOccurs}, for the children it must hold
    (``required``'s rule: not one branch of a choice, not inside an optional
    sequence).  Mostly one; MARKET_INVENTORIES must hold three
    MARKET_INVENTORY, so taking one of them out is as invalid as taking the
    last amenity's AMENITIES."""
    if MIN_CACHE.exists():
        return json.loads(MIN_CACHE.read_text(encoding="utf-8"))
    root = etree.parse(str(_schema_file())).getroot()
    types = {t.get("name"): t for t in root.iterfind(f"{XS}complexType") if t.get("name")}

    def walk(node, out, seen, factor):
        for child in node:
            tag = child.tag
            if tag == f"{XS}element":
                name = child.get("name") or child.get("ref", "").split(":")[-1]
                m = int(child.get("minOccurs", "1")) * factor
                if name and m:
                    out[name] = max(m, out.get(name, 0))
            elif tag == f"{XS}choice":
                walk(child, out, seen, 0)
            elif tag == f"{XS}extension":
                base = child.get("base", "").split(":")[-1]
                if base in types and base not in seen:
                    walk(types[base], out, seen | {base}, factor)
                walk(child, out, seen, factor)
            elif tag in (f"{XS}sequence", f"{XS}all"):
                walk(child, out, seen, factor * int(child.get("minOccurs", "1")))
            elif tag in (f"{XS}complexContent", f"{XS}simpleContent"):
                walk(child, out, seen, factor)

    table = {}
    for name, node in types.items():
        out: dict[str, int] = {}
        walk(node, out, {name}, 1)
        if out:
            table[name] = out
    _with_aliases(root, table)
    try:
        MIN_CACHE.write_text(json.dumps(table, sort_keys=True), encoding="utf-8")
    except OSError:
        pass                                  # a read-only deployment: computed each start
    return table


_min: dict | None = None


def min_occurs(parent: str, child: str) -> int:
    """How many ``child`` elements ``parent`` must hold (0: none)."""
    global _min
    if _min is None:
        _min = min_table()
    return _min.get(parent, {}).get(child, 0)


# ------------------------------------------------------------ xlink arcroles
ARCROLE_CACHE = CACHE_FILE.with_name("xsd_arcroles.json")
ARCROLE_STEM = "urn:fdc:mismo.org:2009:residential/"


def arcroles() -> list[str]:
    """The RELATIONSHIP @xlink:arcrole values the GSE xlink schema allows."""
    if ARCROLE_CACHE.exists():
        return json.loads(ARCROLE_CACHE.read_text(encoding="utf-8"))
    xlink = _schema_file().with_name(_schema_file().name.replace("_v1.3.xsd", "_xlink_v1.3.xsd"))
    root = etree.parse(str(xlink)).getroot()
    out = sorted({e.get("value") for e in root.iter(f"{XS}enumeration")
                  if (e.get("value") or "").startswith(ARCROLE_STEM)})
    try:
        ARCROLE_CACHE.write_text(json.dumps(out, indent=0), encoding="utf-8")
    except OSError:
        pass
    return out


def arcrole(source: str, target: str) -> str:
    """The one allowed arcrole from ``source`` to ``target`` (SIGNATORY ->
    ROLE is IsAssociatedWith, INSPECTION -> ROLE is CompletedBy), or ''."""
    hits = [a for a in arcroles() if a.startswith(f"{ARCROLE_STEM}{source}_") and a.endswith(f"_{target}")]
    return hits[0] if len(hits) == 1 else ""
