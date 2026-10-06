"""Data sources tied to what they are the source for.

A-1 keeps every data source once, in VALUATION_ANALYSIS/DATA_SOURCES, and ties
each to what it sources with a relationship whose arcrole names the target:
DATA_SOURCE_IsDataSourceFor_PROPERTY_UNIT_AREA for a unit's area (10.009),
..._MARKET_TREND for the price trend (17.018), ..._AccessoryDwellingUnit
LegallyRentableIndicator for that one answer (10.013).  B-1 states the target
in the field's display rule ("An arcrole is required for each data source from
DATA SOURCE n to PROPERTY UNIT AREA n"), read by ``form.data_source_target``.

So writing such a field is adding (or removing) a DATA_SOURCE and its link,
inside the unit or section the value is entered for -- a source written
without its link reads back as nothing, which is how a typed Area Data Source
used to vanish on any report the template had not pre-linked.
"""
from __future__ import annotations

from lxml import etree

from . import bind, edit, xsd_order

M = f"{{{bind.MISMO}}}"
X = "{http://www.w3.org/1999/xlink}"
ARC = "urn:fdc:mismo.org:2009:residential/DATA_SOURCE_IsDataSourceFor_{}"


def _target_element(root: etree._Element, scope: etree._Element | None, target: str,
                    *, create: bool) -> etree._Element | None:
    base = scope if scope is not None else bind.subject(root)
    if base is None:
        return None
    found = next(base.iter(f"{M}{target}"), None)
    if found is None and create:
        # the target is a container on the unit or property's own path
        # (PROPERTY_UNIT_AREA under PROPERTY_UNIT): made in the schema's order
        if target in edit._order_of(etree.QName(base).localname):
            found = edit.insert_ordered(base, target)
    return found


def linked(root: etree._Element, target_el: etree._Element, target: str) -> list[etree._Element]:
    label = target_el.get(f"{X}label")
    if not label:
        return []
    wanted = [r.get(f"{X}from") for r in root.iter(f"{M}RELATIONSHIP")
              if r.get(f"{X}to") == label and r.get(f"{X}arcrole", "").endswith(f"IsDataSourceFor_{target}")]
    by = {ds.get(f"{X}label"): ds for ds in root.iter(f"{M}DATA_SOURCE")}
    return [by[w] for w in dict.fromkeys(wanted) if w in by]


def _relationships(root: etree._Element) -> etree._Element:
    rels = next(root.iter(f"{M}RELATIONSHIPS"), None)
    if rels is None:
        holder = next(e for e in root.iter() if isinstance(e.tag, str)
                      and "RELATIONSHIPS" in edit._order_of(etree.QName(e).localname))
        rels = edit.insert_ordered(holder, "RELATIONSHIPS")
    return rels


def _sources_holder(root: etree._Element) -> etree._Element:
    va = next(root.iter(f"{M}VALUATION_ANALYSIS"))
    holder = va.find(f"{M}DATA_SOURCES")
    if holder is None:
        holder = edit.insert_ordered(va, "DATA_SOURCES")
    return holder


def write(root: etree._Element, target: str, data_point: str, value: str,
          scope: etree._Element | None = None) -> tuple[str, str]:
    """Add the source ``value`` (a DataSourceType, or another data point of
    the source such as its description) for the target in this scope; an
    empty value removes every source linked there.  Returns (old, new)."""
    target_el = _target_element(root, scope, target, create=bool(value))
    if target_el is None:
        if not value:
            return "", ""
        raise ValueError(f"there is no {target.replace('_', ' ').lower()} here to give a source")
    have = linked(root, target_el, target)
    old = " | ".join((ds.findtext(f"{M}{data_point}") or "").strip() for ds in have
                     if (ds.findtext(f"{M}{data_point}") or "").strip())
    if not value:
        labels = {ds.get(f"{X}label") for ds in have}
        for rel in list(root.iter(f"{M}RELATIONSHIP")):
            if rel.get(f"{X}from") in labels and rel.get(f"{X}to") == target_el.get(f"{X}label"):
                rel.getparent().remove(rel)
        for ds in have:
            still = any(r.get(f"{X}from") == ds.get(f"{X}label") for r in root.iter(f"{M}RELATIONSHIP"))
            if not still:
                ds.getparent().remove(ds)
        return old, ""
    if data_point != "DataSourceType" and have:
        # a description, name or identifier belongs to the source already there
        ds = have[-1]
        node = ds.find(f"{M}{data_point}")
        if node is None:
            node = edit.insert_ordered(ds, data_point)
        node.text = value
        return old, value
    if any((ds.findtext(f"{M}{data_point}") or "").strip() == value for ds in have):
        return old, value                                    # already a source here
    if not target_el.get(f"{X}label"):
        target_el.set(f"{X}label", edit._free_label(root, target))
    ds = edit.insert_ordered(_sources_holder(root), "DATA_SOURCE")
    ds.set(f"{X}label", edit._free_label(root, f"DATA_SOURCE_{target}"))
    edit.insert_ordered(ds, data_point).text = value
    link = edit.insert_ordered(_relationships(root), "RELATIONSHIP")
    link.set(f"{X}arcrole", xsd_order.arcrole("DATA_SOURCE", target) or ARC.format(target))
    link.set(f"{X}from", ds.get(f"{X}label"))
    link.set(f"{X}to", target_el.get(f"{X}label"))
    return old, value
