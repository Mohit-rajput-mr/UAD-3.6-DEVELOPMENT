"""What TOTAL would deliver, compared with the package it was given.

TOTAL serializes its own report to MISMO (`CreateAndReturnMismoXML`); comparing
that with the package, value by value, is the Import Module's verification
(knowledge/ARCHITECTURE.md §5f): it sees what the E&O panel cannot -- a value
the import dropped or changed although nothing requires it.

Comparison model: every leaf value and attribute becomes (scope, path, value).
scope is the property (its ValuationUseType and, for a comparable, its street
address -- TOTAL renumbers grid columns, so position is not identity) or
"report"; path is the element names from the scope down, without positions.
Values are compared as multisets per (scope, path) after normalising case of
booleans, number formatting and surrounding space.  A value moved between two
rows of the same path is therefore not seen -- the diff is about what TOTAL
keeps, drops, changes or adds, not about row order.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from lxml import etree

SKIP_TAGS = {"EXTENSION", "EmbeddedContentXML", "EmbeddedFile"}
SKIP_ATTR = re.compile(r"(^\{http://www\.w3\.org/1999/xlink\}|^xmlns|SensitiveIndicator$)")
NUM = re.compile(r"^-?(\d+(\.\d*)?|\.\d+)$")

#: Data points a value opinion rests on: adjustments, net totals, adjusted
#: prices and rents, multipliers, approach indications, the opinion itself.
#: Any difference in one of these is reported on its own as value-affecting
#: (CATALOG E-038: TOTAL's nets silently short by $2,000-$15,000).
VALUE_POINTS = re.compile(r"^(ComparableAdjustmentAmount|SalePriceNetTotalAdjustmentAmount|AdjustedSalesPrice\w*Amount|"
                          r"RentalUnitAdjustedRentAmount|OpinionOfValueAmount|ValueIndicatedBy\w+Amount|"
                          r"GrossMonthlyRentMultiplierNumber|GrossRentMultiplierFactorNumber|SiteEstimatedValueAmount)$")


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _norm(v: str) -> str:
    v = (v or "").strip()
    if v.lower() in ("true", "false"):
        return v.lower()
    if NUM.match(v):
        f = float(v)
        return str(int(f)) if f == int(f) else repr(f)
    return re.sub(r"\s+", " ", v)


def _scope(prop) -> str:
    """Which property this is: its role, and -- for a comparable -- its street
    address (TOTAL renumbers grid columns, so position is not identity)."""
    role = prop.get("ValuationUseType") or ""
    if not role:
        for e in prop.iter():
            if _local(e.tag) == "ValuationUseType" and (e.text or "").strip():
                role = e.text.strip()
                break
    role = role or "Property"
    if role == "SubjectProperty":
        return role
    street = ""
    for child in prop:
        if _local(child.tag) == "ADDRESS":
            for e in child:
                if _local(e.tag) == "AddressLineText" and (e.text or "").strip():
                    street = re.sub(r"\s+", " ", e.text.strip().upper())
            break
    if street:
        return f"{role}@{street}"
    ordinal = ""
    for e in prop.iter():
        name = _local(e.tag)
        if name.endswith("OrdinalNumber") and (e.text or "").strip():
            ordinal = e.text.strip()
            break
    return f"{role}#{ordinal or '-'}"


def facts(xml: bytes) -> dict:
    """(scope, path) -> Counter(values) for every leaf value and attribute."""
    root = etree.fromstring(xml, etree.XMLParser(huge_tree=True, recover=True))
    out: dict = defaultdict(Counter)

    def walk(node, scope, path):
        name = _local(node.tag)
        if not name or name in SKIP_TAGS:
            return
        if name == "PROPERTY":
            scope, path = _scope(node), ()
        here = path + (name,)
        for k, v in node.attrib.items():
            if not SKIP_ATTR.search(k) and v.strip():
                out[(scope, "/".join(here) + "@" + _local(k))][_norm(v)] += 1
        kids = [c for c in node if isinstance(c.tag, str)]
        if not kids:
            if (node.text or "").strip():
                value = _norm(node.text)
                # TOTAL stores every placed picture as JPEG under its own folder:
                # compare the picture, not its container format (E-033)
                if name == "ImageFileLocationIdentifier":
                    value = re.split(r"[\\/]", value)[-1].rsplit(".", 1)[0].lower()
                elif name == "MIMETypeIdentifier" and value.startswith("image/"):
                    value = "image/*"
                out[(scope, "/".join(here))][value] += 1
            return
        for c in kids:
            walk(c, scope, here)

    walk(root, "report", ())
    return out


def compare(src: bytes, tot: bytes) -> dict:
    """Counts of kept / changed / dropped / added values, and every row that differs."""
    a, b = facts(src), facts(tot)
    kept = dropped = changed = added = 0
    rows = []
    for key in sorted(set(a) | set(b)):
        sa, sb = a.get(key, Counter()), b.get(key, Counter())
        common = sum((sa & sb).values())
        miss = sa - sb
        extra = sb - sa
        kept += common
        if miss and extra:
            changed += min(sum(miss.values()), sum(extra.values()))
        dropped += max(0, sum(miss.values()) - sum(extra.values()))
        added += max(0, sum(extra.values()) - sum(miss.values()))
        if miss or extra:
            rows.append({"scope": key[0], "path": key[1], "data_point": key[1].split("/")[-1],
                         "file": sorted(miss.elements())[:6], "total": sorted(extra.elements())[:6],
                         "kind": "changed" if miss and extra else ("dropped" if miss else "added")})
    total_src = sum(sum(c.values()) for c in a.values())
    return {"source_values": total_src, "kept": kept, "changed": changed, "dropped": dropped,
            "added": added, "rows": rows}


def value_diffs(diff: dict) -> list[dict]:
    """The rows of a comparison that a value opinion rests on (`VALUE_POINTS`)."""
    return [r for r in diff["rows"] if VALUE_POINTS.match(r["data_point"])]
